/* Local integration: Chrome fake microphone feeds real Whisper, Ollama and Kokoro. */
const cp = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.RAPHAEL_PLAYWRIGHT || 'playwright');
const root = path.resolve(__dirname, '..');
const python = process.env.RAPHAEL_PYTHON || path.join(root, '.venv/Scripts/python.exe');
const data = path.join(root, 'runtime', 'microphone-qa-' + Date.now());
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
(async () => {
  const status = await start(); console.log('All three local engines ready');
  const sample = await job((await request('/api/speak', { text: 'What is two plus three? Please answer briefly.', voice: 'heart', speed: 1 })).id);
  const audio = await fetch(url + '/api/audio/' + sample.id, { headers: { 'X-Raphael-Token': token } });
  assert.ok(audio.ok);
  const testAudio = fixture(Buffer.from(await audio.arrayBuffer())), wavPath = path.join(data, 'test-microphone.wav');
  fs.writeFileSync(wavPath, testAudio.wav);
  browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--mute-audio', '--use-fake-ui-for-media-stream',
    '--use-fake-device-for-media-stream', '--use-file-for-fake-audio-capture=' + wavPath] });
  page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => { if (!r.url().startsWith(url)) external.push(r.url()); });
  await page.addInitScript(() => {
    window.qaStreams = [];
    const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia = async constraints => { const stream = await original(constraints); window.qaStreams.push(stream); return stream; };
  });
  await ready(page);
  assert.equal(await page.evaluate(() => window.qaStreams.length), 0);
  const posts = [];
  page.on('request', r => { if (r.method() === 'POST') posts.push(new URL(r.url()).pathname); });
  await page.locator('#replyVoiceToggle').click();
  await page.locator('#messageInput').fill('What is 2 plus 3? Answer only the number.');
  await page.locator('#commandForm').evaluate(f => f.requestSubmit());
  await page.waitForFunction(() => window.RaphaelUI.getMessages().at(-1)?.status === 'complete', null, { timeout: 180000 });
  assert.match(await page.locator('#replyPreview').textContent(), /5|five/i);
  await page.waitForFunction(() => window.RaphaelUI.getState() === 'idle');
  assert.ok(!posts.includes('/api/speak')); checks.push('Text to text: real AI reply with no speech generation');
  console.log(checks.at(-1));
  await page.locator('#replyVoiceToggle').click();
  const spoken = await speech(page, async () => {
    await page.locator('#messageInput').fill('Say hello and welcome me in one warm sentence.');
    await page.locator('#commandForm').evaluate(f => f.requestSubmit());
  });
  assert.ok((await page.locator('#replyPreview').textContent()).startsWith(spoken.request.text), 'The first streamed phrase belongs to the reply');
  checks.push('Text to speech: real AI reply, real local voice and audio-driven orb pulse'); console.log(checks.at(-1));
  const beforeDirect = posts.filter(p => p === '/api/chat').length;
  await speech(page, async () => { await page.locator('#messageInput').fill('This is a direct text to speech test.'); await page.locator('#readTypedText').click(); });
  assert.equal(posts.filter(p => p === '/api/chat').length, beforeDirect);
  checks.push('Read my text aloud speaks entered text without asking the AI');

  assert.equal(await page.evaluate(() => window.qaStreams.length), 0, 'Reply controls do not start recording');
  await page.locator('#voiceButton').click();
  await page.waitForFunction(() => window.RaphaelMicrophone.state === 'recording');
  await page.waitForFunction(n => window.RaphaelMicrophone.seconds >= n, testAudio.captureSeconds, { timeout: 20000 });
  assert.equal(await page.locator('#micToggle span').textContent(), 'Finish & send');
  await page.screenshot({ path: path.join(root, 'docs/microphone-preview.png') });
  const transcribed = page.waitForResponse(r => r.url().endsWith('/api/transcribe'));
  const turn = speech(page, () => page.locator('#micToggle').click());
  const transcriptionResponse = await transcribed;
  assert.equal(transcriptionResponse.status(), 202);
  assert.equal(await page.evaluate(() => window.qaStreams.every(s => s.getTracks().every(t => t.readyState === 'ended'))), true);
  const transcript = await job((await transcriptionResponse.json()).id);
  assert.match(transcript.text, /two|2/i); assert.match(transcript.text, /three|3/i);
  const speechReply = await turn;
  assert.match(speechReply.request.text, /five|5/i);
  assert.equal(await page.evaluate(() => window.RaphaelMicrophone.state), 'idle');
  assert.match(await page.locator('#heardText').textContent(), /two|2/i);
  checks.push('Speech to speech: browser capture → real offline Whisper → AI → spoken answer; microphone released before processing');
  console.log(checks.at(-1));

  const beforeStop = posts.filter(p => p === '/api/transcribe').length;
  await page.locator('#voiceButton').click(); await page.waitForFunction(() => window.RaphaelMicrophone.state === 'recording');
  await page.locator('#stopButton').click(); await sleep(500);
  assert.equal(posts.filter(p => p === '/api/transcribe').length, beforeStop);
  assert.equal(await page.evaluate(() => window.qaStreams.every(s => s.getTracks().every(t => t.readyState === 'ended'))), true);
  await page.locator('#voiceButton').click(); await page.waitForFunction(() => window.RaphaelMicrophone.state === 'recording');
  await page.locator('#replyVoiceToggle').click();
  assert.equal(await page.evaluate(() => window.qaStreams.every(s => s.getTracks().every(t => t.readyState === 'ended'))), true);
  checks.push('Stop and switching modes release capture without submitting a recording');

  const denied = await browser.newPage();
  await denied.addInitScript(() => { navigator.mediaDevices.getUserMedia = async () => { throw new DOMException('Denied', 'NotAllowedError'); }; });
  await ready(denied); await denied.locator('#voiceButton').click();
  await denied.waitForFunction(() => document.getElementById('microphoneStatus').textContent.includes('permission is blocked'));
  assert.equal(await denied.evaluate(() => window.RaphaelMicrophone.state), 'idle');
  await denied.close(); checks.push('Permission denied shows recovery instructions and keeps microphone off');

  for (const width of [390, 768, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.locator('#voiceButton').scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(data, 'layout-' + width + '.png'), fullPage: true });
  }
  checks.push('Compact reply and microphone controls fit phone, tablet and desktop widths');
  assert.deepEqual(errors, []); assert.deepEqual(external, []);
  checks.push('No browser exceptions or external browser requests');
  const report = { result: 'passed', tested_at: new Date().toISOString(), version: status.version, checks,
    transcript: transcript.text, recognition: transcript.details, reply: speechReply.request.text,
    hardware_microphone_tested: false, input: 'Locally generated WAV through Chrome fake microphone', data };
  fs.writeFileSync(path.join(root, 'docs/microphone-test-results.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
})().catch(async error => {
  console.error(error.stack); process.exitCode = 1;
  if (page) { try { await page.screenshot({ path: path.join(data, 'failure.png'), fullPage: true }); console.error(await page.locator('body').innerText()); } catch {} }
}).finally(async () => {
  if (browser) await browser.close();
  if (child) {
    try { await request('/api/shutdown', {}); } catch {}
    for (let i = 0; i < 50 && child.exitCode === null; i++) await sleep(200);
    if (child.exitCode === null) { child.kill(); process.exitCode = 1; }
    log.end();
  }
});

