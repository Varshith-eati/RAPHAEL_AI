const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {chromium}=require(process.env.RAPHAEL_PLAYWRIGHT||'playwright');
const root=path.resolve(__dirname,'..'),data=path.join(root,'runtime','laptop-browser-'+Date.now());
const origin='http://127.0.0.1:8879';
let server,browser,token;
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
  fs.mkdirSync(data,{recursive:true});
  server=spawn(path.join(root,'.venv','Scripts','python.exe'),['-B',path.join(__dirname,'laptop_fixture.py'),data],{cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});
  let logs='';server.stderr.on('data',chunk=>logs+=chunk);
  for(let i=0;i<100;i++){try{const s=await(await fetch(origin+'/api/status')).json();token=s.token;if(s.chat==='ready')break;}catch{}await delay(100);}
  assert.ok(token,logs);
  browser=await chromium.launch({channel:'chrome',headless:true,args:['--mute-audio','--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream']});
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto(origin);await page.waitForFunction(()=>window.RaphaelConnection?.token);
  await page.locator('#replyVoiceToggle').click();
  await page.locator('[data-panel=laptop]').first().click();
  await page.locator('#checkHardware').click();
  await page.waitForFunction(()=>document.getElementById('hardwareResult').textContent.includes('TEST CPU'));
  await page.locator('#closeDrawer').click();
  async function propose(text){
    await page.locator('#messageInput').fill(text);await page.locator('#commandForm').evaluate(form=>form.requestSubmit());
    await page.waitForFunction(()=>document.getElementById('detailDialog').open&&!document.getElementById('laptopPanel').hidden);
    await page.locator('.approval-card .approval-actions').first().waitFor();
  }
  await propose('Create approved file');
  assert.equal(fs.existsSync(path.join(data,'workspace','approved.txt')),false);
  assert.equal(await page.locator('.approval-card img').count(),0);
  assert.equal(await page.evaluate(()=>window.injected),undefined);
  assert.match(await page.locator('.approval-card pre').first().textContent(),/<img/);
  await page.screenshot({path:path.join(root,'docs','laptop-approval-desktop.png')});
  await page.getByRole('button',{name:'Approve',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.approval-state').textContent.includes('Saved'));
  assert.equal(fs.readFileSync(path.join(data,'workspace','approved.txt'),'utf8'),'Review test\n<img src=x onerror="window.injected=true">\n');
  await page.locator('#closeDrawer').click();
  await propose('Create reject file');
  await page.getByRole('button',{name:'Reject',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.approval-state').textContent.includes('Rejected'));
  assert.equal(fs.existsSync(path.join(data,'workspace','reject.txt')),false);
  await page.locator('#closeDrawer').click();
  await page.locator('#callButton').click();
  await page.waitForFunction(()=>document.body.dataset.callState==='listening');
  await page.evaluate(()=>window.RaphaelUI.sendMessage('Create a note during the call',{live:true}));
  await page.waitForFunction(()=>document.body.dataset.callState==='paused');
  assert.equal(await page.evaluate(()=>window.RaphaelMicrophone.state),'idle');
  await page.getByRole('button',{name:'Reject',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.approval-state').textContent.includes('Rejected'));
  assert.equal(await page.evaluate(()=>document.body.dataset.callState),'paused');
  await page.locator('#closeDrawer').click();await page.locator('#endCall').click();
  await page.locator('[data-panel=laptop]').first().click();
  for(const name of ['Chrome','Gmail','YouTube','Google','GitHub','File Explorer']){
    assert.equal(await page.getByRole('button',{name,exact:true}).count(),1);
  }
  await page.getByRole('button',{name:'Gmail',exact:true}).click(); // Fixture mocks app launching.
  const outside=path.join(data,'outside');fs.mkdirSync(outside);
  fs.writeFileSync(path.join(outside,'private.txt'),'OUTSIDE_SECRET\n<img src=x onerror="window.injected=true">');
  await page.locator('#fileAccess summary').click();
  await page.locator('#fileAccessPath').fill(outside);
  await page.getByRole('button',{name:'Browse folder',exact:true}).click();
  await page.getByRole('button',{name:'Approve',exact:true}).waitFor();
  assert.equal((await page.locator('body').textContent()).includes('OUTSIDE_SECRET'),false);
  await page.getByRole('button',{name:'Approve',exact:true}).click();
  const fileButton=page.getByRole('button',{name:'File · private.txt',exact:true});await fileButton.waitFor();
  assert.equal((await page.locator('body').textContent()).includes('OUTSIDE_SECRET'),false);
  await fileButton.click();await page.getByRole('button',{name:'Reject',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.approval-state').textContent.includes('Rejected'));
  assert.equal((await page.locator('body').textContent()).includes('OUTSIDE_SECRET'),false);
  await fileButton.click();await page.getByRole('button',{name:'Approve',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.approval-card pre')?.textContent.includes('OUTSIDE_SECRET'));
  assert.equal(await page.evaluate(()=>window.injected),undefined);
  assert.ok(fs.readFileSync(path.join(outside,'private.txt'),'utf8').startsWith('OUTSIDE_SECRET'));
  await page.screenshot({path:path.join(root,'docs','external-file-approval.png')});
  await page.locator('#laptopEnabled').uncheck();
  await page.waitForFunction(()=>document.getElementById('laptopStatus').textContent==='Off');
  assert.equal(await page.locator('#checkHardware').isDisabled(),true);
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:path.join(root,'docs','laptop-panel-mobile.png')});
  const layout=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
  assert.ok(layout.scroll<=layout.width+1,JSON.stringify(layout));
  await page.locator('#closeDrawer').click();
  await page.screenshot({path:path.join(root,'docs','laptop-core-mobile.png')});
  assert.deepEqual(errors,[]);
  const report={result:'passed',checked_at:new Date().toISOString(),inference:'simulated; real HTTP and file approval implementation',
    checks:['hardware panel','proposal does not write','preview is inert text','approve writes exact reviewed bytes','reject makes no file','call pauses and releases simulated microphone for approval','website buttons','external folder needs approval','external file needs a separate approval','rejection reveals no contents','approved content is inert and file unchanged','access-off disables tools','390px layout','no browser exceptions']};
  fs.writeFileSync(path.join(root,'docs','laptop-browser-results.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{
  if(browser)await browser.close();
  if(token)try{await fetch(origin+'/api/shutdown',{method:'POST',headers:{'Content-Type':'application/json','X-Raphael-Token':token},body:'{}'});}catch{}
  if(server){await delay(800);if(server.exitCode===null)server.kill();}
});

