"""Real local model routing; browser launches are mocked and files are isolated."""
from dataclasses import replace
from pathlib import Path
import json
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from raphael.config import load_config,LaptopConfig
from raphael.contracts import ChatRequest,Message,Profile,Cancellation
from raphael.laptop.service import LaptopTools
from raphael.providers.ollama import OllamaProvider
from raphael.services.chat import ChatService

class LaunchRecorder:
    def __init__(self):self.opened=[]
    def open_app(self,app):self.opened.append(app);return {'message':'Requested opening '+app+'.'}

data=ROOT/'runtime'/('expanded-real-'+str(int(time.time())))
workspace=data/'workspace';outside=data/'outside';workspace.mkdir(parents=True);outside.mkdir()
file=outside/'sample.txt';file.write_text('Only approved access can read this sample.',encoding='utf-8')
config=replace(load_config(ROOT/'config.toml'),data_dir=data,laptop=LaptopConfig(True,str(workspace)))
native=LaunchRecorder();tools=LaptopTools(config,native=native);provider=OllamaProvider(config);service=ChatService(provider,tools)
model='llama3.2:latest';checks=[]
def ask(text):
    output=[];result=service.execute(ChatRequest(model,(Message('user',text),),Profile()),Cancellation(),output.append)
    print(json.dumps({'request':text,'tools':result.details.get('tools_used'),'reply':''.join(output)}),flush=True)
    return result
try:
    provider.start()
    for prompt,app in [('Open Gmail','gmail'),('Open YouTube','youtube'),('Open Google','google'),
                       ('Open GitHub','github'),('Open Chrome','chrome'),('Open File Explorer','explorer')]:
        result=ask(prompt);assert result.details.get('tools_used')==['open_app'];assert native.opened[-1]==app;checks.append(app)
    result=ask('Browse my Downloads folder. Ask me for approval first.')
    assert result.details.get('tools_used')==['browse_folder']
    proposal=result.details['approvals'][0];assert proposal['access_only'];assert proposal['result'] is None
    tools.approvals.decide(proposal['id'],'reject');checks.append('folder approval')
    result=ask('Read this file outside the workspace: '+str(file))
    assert result.details.get('tools_used')==['read_file']
    proposal=result.details['approvals'][0];assert proposal['result'] is None
    result=tools.approvals.decide(proposal['id'],'approve')
    assert result['result']['text']=='Only approved access can read this sample.'
    checks.append('outside file approval')
    report={'result':'passed','model':model,'checks':checks,'app_launches':'mocked; routing used real inference',
            'checked_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
    (ROOT/'docs'/'expanded-access-real-results.json').write_text(json.dumps(report,indent=2))
finally:tools.close();provider.close()
