"""Isolated browser-test server; never accesses the user's real workspace or apps."""
from dataclasses import replace
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from raphael.application import Application
from raphael.config import load_config, LaptopConfig
from raphael.http_api import LocalServer
from raphael.laptop.service import LaptopTools
from test_backend import FakeChat, FakeVoice, FakeTranscriber
from test_laptop import FakeNative


class ToolChat(FakeChat):
    def tool_turn(self,request,messages,cancel,tools,context):
        prompt=messages[-1]['content']
        file='reject.txt' if 'reject' in prompt else 'approved.txt'
        return {'tool_calls':[{'function':{'name':'write_text','arguments':{
            'path':file,'content':'Review test\n<img src=x onerror="window.injected=true">\n'}}}]},{}


data=Path(sys.argv[1]);workspace=data/'workspace';workspace.mkdir(parents=True,exist_ok=True)
config=replace(load_config(ROOT/'config.toml'),data_dir=data,chat=replace(load_config(ROOT/'config.toml').chat,models=('test-local',)),
               laptop=LaptopConfig(True,str(workspace)))
app=Application(config,chat_provider=ToolChat(),voice_provider=FakeVoice(),transcription_provider=FakeTranscriber(),
                laptop_tools=LaptopTools(config,native=FakeNative()))
server=LocalServer(app,port=8879)
try:
    app.start();server.serve_forever(poll_interval=.1)
finally:
    app.close();server.server_close()
