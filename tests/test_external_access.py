from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from raphael.config import load_config, LaptopConfig
from raphael.contracts import Cancellation
from raphael.errors import AppError
from raphael.laptop.service import LaptopTools
from raphael.laptop.native import NativeLaptop, SITES
from test_backend import ROOT
from test_laptop import FakeNative


class ExternalAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.workspace=self.root/'workspace';self.workspace.mkdir()
        self.external=self.root/'outside';self.external.mkdir()
        (self.external/'private.txt').write_text('PRIVATE CONTENT',encoding='utf-8')
        config=replace(load_config(ROOT/'config.toml'),laptop=LaptopConfig(True,str(self.workspace)))
        self.tools=LaptopTools(config,native=FakeNative())
    def tearDown(self):self.tools.close();self.temp.cleanup()
    def proposal(self,action,path):
        return self.tools.execute(action,{'path':str(path)},Cancellation())['approval']
    def test_proposals_never_list_or_read(self):
        with patch('raphael.laptop.filesystem.os.scandir',side_effect=AssertionError('listed before approval')), \
             patch.object(self.tools.workspace,'_read',side_effect=AssertionError('read before approval')):
            folder=self.proposal('browse_folder',self.external)
            file=self.proposal('read_file',self.external/'private.txt')
            self.assertNotIn('PRIVATE CONTENT',str(file))
            self.tools.approvals.decide(folder['id'],'reject')
            self.tools.approvals.decide(file['id'],'reject')
    def test_folder_approval_does_not_grant_file_or_subfolder_access(self):
        folder=self.proposal('browse_folder',self.external)
        result=self.tools.approvals.decide(folder['id'],'approve')
        self.assertEqual(result['state'],'completed')
        self.assertEqual(result['result']['items'][0]['name'],'private.txt')
        self.assertNotIn('PRIVATE CONTENT',str(result))
        file=self.proposal('read_file',self.external/'private.txt')
        self.assertEqual(file['state'],'pending')
        self.assertNotIn('PRIVATE CONTENT',str(file))
        result=self.tools.approvals.decide(file['id'],'approve')
        self.assertEqual(result['result']['text'],'PRIVATE CONTENT')
        self.assertEqual((self.external/'private.txt').read_text(),'PRIVATE CONTENT')
        with self.assertRaises(AppError):self.tools.approvals.decide(file['id'],'approve')
    def test_outside_writes_still_blocked(self):
        with self.assertRaises(AppError):self.tools.execute('write_text',{'path':str(self.external/'private.txt'),'content':'changed'},Cancellation())
        with self.assertRaises(AppError):self.tools.files.prepare('write_text',str(self.external/'private.txt'))
        self.assertEqual((self.external/'private.txt').read_text(),'PRIVATE CONTENT')
    def test_network_device_and_ambiguous_paths_blocked(self):
        for path in ('\\\\server\\share','\\\\?\\C:\\secret.txt','C:relative.txt','../secret.txt','C:/test.txt:stream','https://example.com','shell:Desktop'):
            with self.subTest(path=path),self.assertRaises(AppError):self.proposal('read_file',path)
    def test_disabled_access_revokes_pending_reads(self):
        file=self.proposal('read_file',self.external/'private.txt');self.tools.set_enabled(False)
        with self.assertRaises(AppError):self.tools.approvals.decide(file['id'],'approve')
    def test_large_binary_and_executable_files_are_not_read(self):
        for name,data in [('large.txt',b'x'*32001),('binary.txt',b'\0'*10),('program.exe',b'script')]:
            target=self.external/name;target.write_bytes(data)
            if name.endswith('.exe'):
                with self.assertRaises(AppError):self.proposal('read_file',target)
            else:
                file=self.proposal('read_file',target)
                result=self.tools.approvals.decide(file['id'],'approve')
                self.assertEqual(result['state'],'failed');self.assertNotIn('text',result['result'])
    def test_websites_use_fixed_urls_and_never_model_arguments(self):
        native=NativeLaptop(self.tools.workspace);chrome=Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
        with patch.object(native,'chrome_path',return_value=chrome),patch('raphael.laptop.native.subprocess.Popen') as launch:
            for app,url in SITES.items():
                native.open_app(app)
                self.assertEqual(launch.call_args.args[0],[str(chrome),url])
                self.assertFalse(launch.call_args.kwargs.get('shell',False))
            native.open_app('chrome');self.assertEqual(launch.call_args.args[0],[str(chrome),'about:blank'])
        with self.assertRaises(AppError):self.tools.execute('open_app',{'app':'gmail','url':'https://example.com'},Cancellation())
    def test_websites_fall_back_but_missing_chrome_is_reported(self):
        native=NativeLaptop(self.tools.workspace)
        with patch.object(native,'chrome_path',return_value=None),patch('raphael.laptop.native.os.startfile') as start:
            native.open_app('github');start.assert_called_once_with(SITES['github'])
            with self.assertRaises(AppError):native.open_app('chrome')

if __name__=='__main__':unittest.main()
