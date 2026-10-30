/* Local integration: Chrome fake microphone feeds real Whisper, Ollama and Kokoro. */
const cp = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.RAPHAEL_PLAYWRIGHT || 'playwright');
const root = path.resolve(__dirname, '..');
const python = process.env.RAPHAEL_PYTHON || path.join(root, '.venv/Scripts/python.exe');
const data = path.join(root, 'runtime', 'live-call-qa-' + Date.now());
const url = 'http://127.0.0.1:8878';
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
fs.mkdirSync(data, { recursive: true });
let child, browser, token, log, page;
const checks = [], errors = [], external = [];
async function request(route, body) {
  const response = await fetch(url + route, { headers: { 'Content-Type': 'application/json', 'X-Raphael-Token': token || '' },
    ...(body !== undefined ? { method: 'POST', body: JSON.stringify(body) } : {}), signal: AbortSignal.timeout(15000) });
  const result = await response.json(); assert.ok(response.ok, JSON.stringify(result)); return result;
}
async function job(id) {
  for (let i = 0; i < 900; i++) {
    const result = await request('/api/jobs/' + id);
    if (result.state === 'error') throw Error(result.error);
    if (result.state === 'ready') return result;
    await sleep(250);
  }
  throw Error('Job timed out');
}
async function start() {
  log = fs.createWriteStream(path.join(data, 'test-server.log'));
  child = cp.spawn(python, ['-B', path.join(root, 'server.py'), '--port', '8878', '--data-dir', data], { windowsHide: true });
  child.stdout.pipe(log); child.stderr.pipe(log);
  for (let i = 0; i < 180; i++) {
    let status;
    try { status = await request('/api/status'); } catch (error) {
      if (child.exitCode !== null || i === 179) throw error;
      await sleep(500); continue;
    }
    token = status.token;
    if (['chat', 'voice', 'transcription'].some(k => status[k] === 'error')) throw Error(JSON.stringify(status));
    if (['chat', 'voice', 'transcription'].every(k => status[k] === 'ready')) return status;
    await sleep(500);
  }
  throw Error('Engines not ready');
}
function fixture(wav) {
  // Decode the generated PCM16 WAV and add silence so one capture contains one question.
  let rate, channels, pcm;
  for (let p = 12; p + 8 <= wav.length;) {
    const name = wav.toString('ascii', p, p + 4), size = wav.readUInt32LE(p + 4);
    if (name === 'fmt ') { channels = wav.readUInt16LE(p + 10); rate = wav.readUInt32LE(p + 12); assert.equal(wav.readUInt16LE(p + 22), 16); }
    if (name === 'data') pcm = wav.subarray(p + 8, p + 8 + size);
    p += 8 + size + (size % 2);
  }
  assert.equal(channels, 1); assert.ok(pcm);
  const speechCount = Math.floor(pcm.length / 2 * 16000 / rate), lead = 8000, tail = 32000;
  const count = lead + speechCount + tail, out = Buffer.alloc(44 + count * 2);
  out.write('RIFF', 0); out.writeUInt32LE(36 + count * 2, 4); out.write('WAVEfmt ', 8); out.writeUInt32LE(16, 16);
  out.writeUInt16LE(1, 20); out.writeUInt16LE(1, 22); out.writeUInt32LE(16000, 24); out.writeUInt32LE(32000, 28);
  out.writeUInt16LE(2, 32); out.writeUInt16LE(16, 34); out.write('data', 36); out.writeUInt32LE(count * 2, 40);
  for (let i = 0; i < speechCount; i++) out.writeInt16LE(pcm.readInt16LE(Math.floor(i * rate / 16000) * 2), 44 + (lead + i) * 2);
  return { wav: out, captureSeconds: (lead + speechCount + 8000) / 16000 };
}
async function ready(p) { await p.goto(url); await p.waitForFunction(() => window.RaphaelConnection?.token); }
async function speech(p, trigger) {
  const posted = p.waitForResponse(r => r.url().endsWith('/api/speak'));
  await trigger();
  const response = await posted;
  assert.equal(response.status(), 202);
  const id = (await response.json()).id;
  await p.waitForFunction(() => window.RaphaelVoice.playing, null, { timeout: 120000 });
  assert.equal(await p.evaluate(() => window.RaphaelUI.getState()), 'speaking');
  const levels = [];
  for (let i = 0; i < 10; i++) { levels.push(await p.evaluate(() => window.RaphaelVoice.level)); await sleep(80); }
  assert.ok(Math.max(...levels) > 0.04, 'Speech produces a visible audio-driven pulse');
  // Very short answers (for example "5") may finish during meter sampling.
  await p.evaluate(() => { if (window.RaphaelVoice.playing) window.RaphaelUI.stop(); });
  assert.equal(await p.evaluate(() => window.RaphaelVoice.playing), false);
  return { request: response.request().postDataJSON(), result: await job(id) };
}

async function makeAudio(text,name){
  const sample=await job((await request('/api/speak',{text,voice:'heart',speed:1})).id);
  const response=await fetch(url+'/api/audio/'+sample.id,{headers:{'X-Raphael-Token':token}});
  assert.ok(response.ok);const prepared=fixture(Buffer.from(await response.arrayBuffer()));
  const file=path.join(data,name+'.wav');fs.writeFileSync(file,prepared.wav);return file;
}
async function newBrowser(file){
  if(browser)await browser.close();
  browser=await chromium.launch({channel:'chrome',headless:true,args:['--mute-audio','--use-fake-ui-for-media-stream',
    '--use-fake-device-for-media-stream','--use-file-for-fake-audio-capture='+file]});
  page=await browser.newPage({viewport:{width:1440,height:960}});
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',r=>{if(!r.url().startsWith(url))external.push(r.url());});
  await page.addInitScript(()=>{
    window.qaStreams=[];const original=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia=async constraints=>{const stream=await original(constraints);window.qaStreams.push(stream);return stream;};
  });
  await ready(page);
  await page.locator('#chatConnection').click();
  await page.locator('#modelSelect').selectOption('llama3.2:latest');
  await page.locator('#closeDrawer').click();
}
async function tracksOff(){assert.equal(await page.evaluate(()=>window.qaStreams.every(s=>s.getTracks().every(t=>t.readyState==='ended'))),true);}
async function waitState(state){await page.waitForFunction(value=>document.body.dataset.callState===value,state,{timeout:180000});}
async function wakeOn(){await page.locator('.main-nav [data-panel="voice"]').click();await page.locator('#enableWake').check();await waitState('armed');}
async function endCall(){await page.locator('#endCall').click();await waitState('off');await tracksOff();assert.equal(await page.locator('#enableWake').isChecked(),false);}

(async()=>{
  const status=await start();console.log('Call test: three engines ready.');
  const normal=await makeAudio('What is two plus three? Please answer briefly.','normal');
  const wakeQuestion=await makeAudio('Hey Raphael, what is two plus three? Please answer briefly.','wake-question');
  const wakeOnly=await makeAudio('Hey Raphael.','wake-only');
  await newBrowser(normal);
  const posts=[];page.on('request',r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname);});
  assert.equal(await page.evaluate(()=>window.qaStreams.length),0);
  await page.locator('#callButton').click();await waitState('listening');
  assert.equal(await page.locator('#microphoneControls').isVisible(),false);
  const spokenResponse=page.waitForResponse(r=>r.url().endsWith('/api/speak'),{timeout:180000});
  const spoken=await spokenResponse;assert.match(spoken.request().postDataJSON().text,/5|five/i);
  await tracksOff();
  await page.waitForFunction(()=>window.RaphaelVoice.playing,null,{timeout:120000});
  await page.screenshot({path:path.join(root,'docs/live-call-preview.png')});
  await waitState('listening');
  await page.waitForFunction(()=>window.RaphaelUI.getMessages().filter(m=>m.role==='assistant'&&m.status==='complete').length>=2,null,{timeout:180000});
  await waitState('listening');await endCall();
  const completedPosts=posts.filter(p=>p==='/api/chat').length;await sleep(1800);
  assert.equal(posts.filter(p=>p==='/api/chat').length,completedPosts);
  assert.equal(completedPosts,2);checks.push('Two automatic speech → local AI → real voice turns without Finish & send; End releases mic and prevents restart');console.log(checks.at(-1));

  await page.locator('#callButton').click();await waitState('listening');
  await page.locator('#muteCall').click();await waitState('paused');await tracksOff();await sleep(500);
  await page.locator('#muteCall').click();await waitState('listening');await endCall();
  checks.push('Mute/resume controls pause and restart capture');
  await page.locator('#callButton').click();await waitState('replying');
  await page.locator('#interruptCall').click();await waitState('listening');await endCall();
  checks.push('Interrupt cancels the active turn and returns to listening');

  const denied=await browser.newPage();
  await denied.addInitScript(()=>{navigator.mediaDevices.getUserMedia=async()=>{throw new DOMException('Denied','NotAllowedError');};});
  await ready(denied);await denied.locator('#callButton').click();
  await denied.waitForFunction(()=>document.getElementById('toast').textContent.includes('permission is blocked'));
  assert.equal(await denied.locator('#callControls').isVisible(),false);await denied.close();
  checks.push('Denied microphone permission ends the attempted call cleanly');

  await newBrowser(normal);let unrelatedChat=0;
  page.on('request',r=>{if(r.url().endsWith('/api/chat'))unrelatedChat++;});
  await wakeOn();
  const unrelated=await page.waitForResponse(r=>r.url().endsWith('/api/transcribe'),{timeout:30000});
  const unrelatedResult=await job((await unrelated.json()).id);await waitState('armed');
  assert.match(unrelatedResult.text,/two|2/i);assert.equal(unrelatedChat,0);await endCall();
  checks.push('Wake mode recognizes but does not send unrelated speech to the AI');console.log(checks.at(-1));

  await newBrowser(wakeQuestion);await wakeOn();
  const awakenedResponse=await page.waitForResponse(r=>r.url().endsWith('/api/speak'),{timeout:180000});
  const answer=awakenedResponse.request().postDataJSON().text;assert.match(answer,/5|five/i);
  await page.waitForFunction(()=>window.RaphaelVoice.playing,null,{timeout:120000});await tracksOff();
  await waitState('listening');
  assert.equal(await page.locator('#enableWake').isChecked(),true);
  const heard=await page.locator('#heardText').textContent();assert.match(heard,/two|2/i);assert.doesNotMatch(heard,/hey raphael/i);
  await endCall();checks.push('Real “Hey Raphael” plus question wakes the call, strips the address and speaks the answer');console.log(checks.at(-1));

  await newBrowser(wakeOnly);await wakeOn();
  const greeting=await page.waitForResponse(r=>r.url().endsWith('/api/speak'),{timeout:180000});
  assert.match(greeting.request().postDataJSON().text,/I'm here/);
  await page.waitForFunction(()=>window.RaphaelVoice.playing,null,{timeout:120000});await waitState('listening');await endCall();
  checks.push('Wake phrase alone gets a spoken greeting and opens continuous conversation');
  for(const width of[390,768,1440]){
    await page.setViewportSize({width,height:900});await page.locator('#callButton').click();await waitState('listening');
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.screenshot({path:path.join(data,'call-layout-'+width+'.png'),fullPage:true});await endCall();
  }
  checks.push('Call bar fits phone, tablet and desktop; wake listening resets when the call ends');
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
  const report={result:'passed',tested_at:new Date().toISOString(),version:status.version,checks,hardware_microphone_tested:false,
    input:'Locally generated recordings through Chrome fake microphone',model:'llama3.2:latest',wake_question:heard,wake_answer:answer,data};
  fs.writeFileSync(path.join(root,'docs/live-call-test-results.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
})().catch(async error=>{
  console.error(error.stack);process.exitCode=1;
  if(page){try{await page.screenshot({path:path.join(data,'failure.png'),fullPage:true});console.error(await page.locator('body').innerText());}catch{}}
}).finally(async()=>{
  if(browser)await browser.close();
  if(child){try{await request('/api/shutdown',{});}catch{}
    for(let i=0;i<50&&child.exitCode===null;i++)await sleep(200);
    if(child.exitCode===null){child.kill();process.exitCode=1;}log.end();}
});

