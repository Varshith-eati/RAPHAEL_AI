"""Laptop access boundaries and approval behavior; all writes use temporary folders."""
from dataclasses import replace
from pathlib import Path
import http.client
import json
import os
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from raphael.application import Application
from raphael.config import load_config, LaptopConfig
from raphael.contracts import Cancellation, ChatRequest, Message, Profile
from raphael.errors import AppError, Cancelled
from raphael.http_api import LocalServer
from raphael.laptop.service import LaptopTools
from raphael.laptop.native import NativeLaptop
from raphael.services.chat import ChatService
from test_backend import FakeChat, FakeVoice, FakeTranscriber, ROOT


class FakeNative:
    def system_info(self):
        return {'cpu': 'TEST CPU', 'ram_gb': 16}
    def open_app(self, app):
        return {'message': 'Opened '+app}


class LaptopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = replace(load_config(ROOT/'config.toml'), data_dir=self.root/'runtime',
                              laptop=LaptopConfig(True, str(self.root)))
        self.tools = LaptopTools(self.config, native=FakeNative())
        self.cancel = Cancellation()

    def tearDown(self):
        self.tools.close()
        self.temp.cleanup()

    def proposal(self, path='note.txt', content='Hello'):
        return self.tools.execute('write_text', {'path': path, 'content': content}, self.cancel)['approval']

    def test_changes_wait_for_approval_and_rejection_never_writes(self):
        item = self.proposal()
        self.assertFalse((self.root/'note.txt').exists())
        self.assertEqual(self.tools.approvals.decide(item['id'], 'reject')['state'], 'rejected')
        self.assertFalse((self.root/'note.txt').exists())
        with self.assertRaises(AppError):
            self.tools.approvals.decide(item['id'], 'approve')

    def test_exact_single_use_write_and_original_backup(self):
        (self.root/'note.txt').write_text('original', encoding='utf-8')
        item = self.proposal(content='changed\n')
        result = self.tools.approvals.decide(item['id'], 'approve')
        self.assertEqual(result['state'], 'completed')
        self.assertEqual((self.root/'note.txt').read_text(), 'changed\n')
        self.assertEqual(Path(result['result']['backup']).read_text(), 'original')
        with self.assertRaises(AppError):
            self.tools.approvals.decide(item['id'], 'approve')

    def test_stale_preview_and_new_file_collision_do_not_overwrite(self):
        for original in (None, 'before'):
            target = self.root/'note.txt'
            if target.exists(): target.unlink()
            if original is not None: target.write_text(original)
            item = self.proposal()
            target.write_text('edited elsewhere')
            self.assertEqual(self.tools.approvals.decide(item['id'], 'approve')['state'], 'failed')
            self.assertEqual(target.read_text(), 'edited elsewhere')

    def test_disable_and_expiration_revoke_pending(self):
        item = self.proposal()
        self.tools.set_enabled(False)
        with self.assertRaises(AppError): self.tools.approvals.decide(item['id'], 'approve')
        with self.assertRaises(AppError): self.tools.execute('system_info', {}, self.cancel)
        self.tools.set_enabled(True)
        self.tools.approvals.ttl=-1
        item=self.proposal()
        with self.assertRaises(AppError): self.tools.approvals.decide(item['id'], 'approve')
        self.assertFalse((self.root/'note.txt').exists())

    def test_two_previews_cannot_overwrite_each_other(self):
        from concurrent.futures import ThreadPoolExecutor
        (self.root/'note.txt').write_text('original')
        proposals=[self.proposal(content=text) for text in ('first','second')]
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda item:self.tools.approvals.decide(item['id'],'approve'),proposals))
        self.assertEqual(sorted(item['state'] for item in results),['completed','failed'])

    def test_paths_and_executable_types_blocked(self):
        for path in ('../escape.txt', 'C:/outside.txt', '//server/share/a.txt', 'x.txt:stream',
                     '.hidden/a.txt', 'CON.txt', 'a./b.txt', 'a.ps1', 'a.exe', 'a.bat', 'a.html', 'a.lnk', 'a//b.txt'):
            with self.subTest(path=path), self.assertRaises(AppError): self.proposal(path)

    def test_hardlinks_and_junctions_blocked(self):
        outside=self.root/'outside';outside.mkdir();(outside/'x.txt').write_text('private')
        folder=self.root/'approved';folder.mkdir()
        from raphael.laptop.workspace import Workspace
        workspace=Workspace(folder)
        os.link(outside/'x.txt',folder/'hard.txt')
        with self.assertRaises(AppError): workspace.read('hard.txt')
        if os.name=='nt':
            import subprocess
            subprocess.run(['powershell.exe','-NoProfile','-Command',
                            "New-Item -ItemType Junction -Path '"+str(folder/'linked')+"' -Target '"+str(outside)+"' | Out-Null"],check=True)
            try:
                with self.assertRaises(AppError): workspace.read('linked/x.txt')
            finally: os.rmdir(folder/'linked')

    def test_model_cannot_supply_approval_or_commands(self):
        for name,args in [('approve',{'id':'x'}),('shell',{'command':'calc'}),
                          ('write_text',{'path':'a.txt','content':'hi','approved':'true'}),
                          ('open_app',{'app':'calculator','command':'other'})]:
            with self.assertRaises(AppError):self.tools.execute(name,args,self.cancel)
        native=NativeLaptop(self.tools.workspace)
        with self.assertRaises(AppError): native.open_app('powershell')

    def test_folder_creation_requires_approval(self):
        item=self.tools.execute('create_folder',{'path':'Notes'},self.cancel)['approval']
        self.assertFalse((self.root/'Notes').exists())
        self.assertEqual(self.tools.approvals.decide(item['id'],'approve')['state'],'completed')
        self.assertTrue((self.root/'Notes').is_dir())

    def test_tool_conversation_and_cancellation(self):
        class Model(FakeChat):
            def tool_turn(model,request,messages,cancel,schemas,context):
                if messages[-1]['role']=='tool':
                    assert 'TEST CPU' in messages[-1]['content']
                    return {'content':'Your CPU is TEST CPU.'},{}
                return {'tool_calls':[{'function':{'name':'system_info','arguments':{}}}]},{}
        request=ChatRequest('test-local',(Message('user','Which CPU do I have?'),),Profile())
        parts=[]
        ChatService(Model(),self.tools).execute(request,self.cancel,parts.append)
        self.assertIn('Processor: TEST CPU',''.join(parts))
        self.assertIn('RAM: 16 GB',''.join(parts))
        class Writer(FakeChat):
            def tool_turn(model,*args):
                return {'tool_calls':[{'function':{'name':'write_text','arguments':{'path':'note.txt','content':'Hello'}}}]},{}
        result=ChatService(Writer(),self.tools).execute(request,self.cancel,parts.append)
        self.assertEqual(len(result.details['approvals']),1)
        self.assertFalse((self.root/'note.txt').exists())
        self.cancel.cancel()
        self.assertEqual(self.tools.approvals.list()[0]['state'],'cancelled')

    def test_http_requires_origin_token_and_immutable_proposal(self):
        app=Application(self.config,chat_provider=FakeChat(),voice_provider=FakeVoice(),
                        transcription_provider=FakeTranscriber(),laptop_tools=self.tools)
        server=LocalServer(app,port=0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        item=self.proposal()
        def post(payload,token=None,origin=None):
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port)
            headers={'Content-Type':'application/json'}
            if token:headers['X-Raphael-Token']=token
            if origin:headers['Origin']=origin
            connection.request('POST','/api/laptop/approvals/'+item['id'],json.dumps(payload),headers)
            response=connection.getresponse();status=response.status;response.read();connection.close();return status
        try:
            self.assertEqual(post({'decision':'approve'}),403)
            self.assertEqual(post({'decision':'approve'},server.token,'https://example.com'),403)
            self.assertEqual(post({'decision':'approve','content':'replacement'},server.token),400)
            self.assertFalse((self.root/'note.txt').exists())
            self.assertEqual(post({'decision':'approve'},server.token),200)
            self.assertEqual((self.root/'note.txt').read_text(),'Hello')
        finally:server.shutdown();server.server_close();thread.join();app.close()

    def test_printed_action_json_is_not_executed(self):
        class Broken(FakeChat):
            def tool_turn(model,*args):
                return {'content':'{"name":"write_text","parameters":{"path":"note.txt","content":"unsafe"}}'},{}
        request=ChatRequest('test-local',(Message('user','Make a note'),),Profile())
        output=[]
        with self.assertRaises(AppError):ChatService(Broken(),self.tools).execute(request,self.cancel,output.append)
        self.assertEqual(output,[])
        self.assertEqual(self.tools.approvals.list(),[])
        self.assertFalse((self.root/'note.txt').exists())

    def test_supported_app_uses_fixed_executable_without_shell(self):
        native=NativeLaptop(self.tools.workspace)
        with patch('raphael.laptop.native.subprocess.Popen') as launch:
            native.open_app('calculator')
            args,kwargs=launch.call_args
            self.assertEqual(args[0],[str(native.windows/'System32/calc.exe')])
            self.assertFalse(kwargs.get('shell',False))

    def test_provider_constrains_and_validates_action_format(self):
        from raphael.providers.ollama import OllamaProvider
        from raphael.laptop.service import SCHEMAS
        provider=OllamaProvider(self.config);provider.models=['test-local']
        connection=Mock();response=connection.getresponse.return_value;response.status=200
        request=ChatRequest('test-local',(Message('user','Make a note'),),Profile())
        decision={'action':'write_text','arguments':{'path':'note.txt','content':'Hi'},'reply':''}
        response.read.return_value=json.dumps({'done':True,'message':{'content':json.dumps(decision)}}).encode()
        with patch('raphael.providers.ollama.http.client.HTTPConnection',return_value=connection):
            message,details=provider.tool_turn(request,[{'role':'user','content':'Make a note'}],self.cancel,SCHEMAS,self.tools.context())
            self.assertEqual(message['tool_calls'][0]['function']['name'],'write_text')
            body=json.loads(connection.request.call_args.args[2])
            self.assertEqual(body['format']['properties']['action']['enum'][0],'reply')
            decision['action']='approve'
            response.read.return_value=json.dumps({'done':True,'message':{'content':json.dumps(decision)}}).encode()
            with self.assertRaises(AppError):provider.tool_turn(request,[],self.cancel,SCHEMAS,self.tools.context())
        self.assertFalse((self.root/'note.txt').exists())


if __name__=='__main__':unittest.main()
