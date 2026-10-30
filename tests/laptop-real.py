"""Real installed-model tool use; approved test writes stay in an isolated QA folder."""
from dataclasses import replace
from pathlib import Path
import json
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from raphael.config import load_config, LaptopConfig
from raphael.contracts import Cancellation, ChatRequest, Message, Profile
from raphael.laptop.service import LaptopTools
from raphael.providers.ollama import OllamaProvider
from raphael.services.chat import ChatService

data=ROOT/'runtime'/('laptop-real-'+str(int(time.time())));data.mkdir(parents=True)
config=replace(load_config(ROOT/'config.toml'),data_dir=data,laptop=LaptopConfig(True,str(data)))
provider=OllamaProvider(config);tools=LaptopTools(config);service=ChatService(provider,tools)
model=sys.argv[1] if len(sys.argv)>1 else 'qwen3.5:4b'
report={'model':model,'checks':[]}
try:
    provider.start()
    actual=tools.native.system_info();assert actual.get('cpu') and actual.get('ram_gb')
    (data/'report.txt').write_text('The project code is SAPPHIRE-42. The meeting is on Monday.',encoding='utf-8')
    for text,name in [('What CPU and RAM does my laptop have?','system_info'),
                      ('Prepare a file named test-note.txt inside Raphael Workspace with content "Hello from Raphael" (no punctuation or extra text). Ask for approval before saving.','write_text'),
                      ('Read report.txt in my workspace and tell me the project code from it.','read_text')]:
        output=[];result=service.execute(ChatRequest(model,(Message('user',text),),Profile()),Cancellation(),output.append)
        print(json.dumps({'tools':result.details.get('tools_used'),'reply':''.join(output)},ensure_ascii=False),flush=True)
        assert name in result.details.get('tools_used',[])
        if name=='write_text':
            assert not (data/'test-note.txt').exists()
            approval=result.details['approvals'][0]
            assert approval['content']=='Hello from Raphael'
            # This is an isolated QA proposal, explicitly approved by the test harness.
            assert tools.approvals.decide(approval['id'],'approve')['state']=='completed'
            assert (data/'test-note.txt').read_text()=='Hello from Raphael'
        elif name=='system_info':
            assert str(round(actual['ram_gb'])) in ''.join(output) or str(actual['ram_gb']) in ''.join(output)
        else:
            assert 'SAPPHIRE-42' in ''.join(output)
        report['checks'].append(name)
    report['result']='passed'
    report['checked_at']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    (ROOT/'docs'/'laptop-real-results.json').write_text(json.dumps(report,indent=2))
finally:tools.close();provider.close()
