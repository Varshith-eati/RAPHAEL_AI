/* Optional full integration test. Requires installed local models and Playwright. */
const cp = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.RAPHAEL_PLAYWRIGHT || 'playwright');
const root = path.resolve(__dirname, '..');
const python = process.env.RAPHAEL_PYTHON || path.resolve(root, '.venv/Scripts/python.exe');
const data = path.join(root, 'runtime', 'qa-' + Date.now());
const url = 'http://127.0.0.1:8878';
fs.mkdirSync(data, { recursive: true });
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
let child, browser, token, log;
const checks = [];

async function request(route, body) {
  const response = await fetch(url + route, {
    headers: { 'Content-Type': 'application/json', 'X-Raphael-Token': token || '' },
    ...(body !== undefined ? { method: 'POST', body: JSON.stringify(body) } : {}),
    signal: AbortSignal.timeout(15000)
  });
  const result = await response.json();
  assert.ok(response.ok, JSON.stringify(result));
  return result;
}

async function start() {
  log = fs.createWriteStream(path.join(data, 'test-server.log'), { flags: 'a' });
  child = cp.spawn(python, ['-B', path.join(root, 'server.py'), '--port', '8878', '--data-dir', data],
    { windowsHide: true, env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' } });
  child.stdout.pipe(log); child.stderr.pipe(log);
  for (let i = 0; i < 160; i++) {
    let status;
    try { status = await request('/api/status'); } catch (error) {
      if (child.exitCode !== null || i === 159) throw error;
      await sleep(500); continue;
    }
    token = status.token;
    if (status.chat === 'error' || status.voice === 'error') throw Error(JSON.stringify(status));
    if (status.chat === 'ready' && status.voice === 'ready') return status;
    await sleep(500);
  }
  throw Error('Engines did not become ready');
}

async function stop() {
  if (!child) return;
  try { await request('/api/shutdown', {}); } catch {}
  for (let i = 0; i < 50 && child.exitCode === null; i++) await sleep(200);
  assert.notEqual(child.exitCode, null, 'Backend should stop itself cleanly');
  assert.equal(child.exitCode, 0);
  log.end(); child = null; token = null;
}

async function job(id) {
  for (let i = 0; i < 600; i++) {
    const result = await request('/api/jobs/' + id);
    if (result.state === 'error') throw Error(result.error);
    if (result.state === 'ready') return result;
    await sleep(250);
  }
  throw Error('Job timed out');
}

(async () => {
  const engines = await start();
  console.log('Local engines ready: ' + engines.models.join(', '));
  browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--mute-audio'] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  const errors = [], external = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (!request.url().startsWith(url)) external.push(request.url()); });
  await page.goto(url);
  await page.waitForFunction(() => window.RaphaelConnection?.token);
  await page.locator('.main-nav [data-panel="voice"]').click();
  await page.locator('#autoSpeak').uncheck();
  await page.locator('#closeDrawer').click();
  async function send(text, count) {
    await page.locator('#messageInput').fill(text);
    await page.locator('#commandForm').evaluate(form => form.requestSubmit());
    await page.waitForFunction(n => window.RaphaelUI.getMessages().filter(m => m.role === 'assistant' && m.status === 'complete').length === n, count, { timeout: 180000 });
    return await page.evaluate(() => window.RaphaelUI.getMessages().at(-1).content);
  }
  assert.match(await send('Remember this for our conversation: the codename is Blue Lantern. Reply in one short sentence.', 1), /Blue Lantern/i);
  assert.match(await send('What codename did I just give you? Answer only the name.', 2), /Blue Lantern/i);
  checks.push('Real Qwen response and follow-up context');
  console.log('Real conversation context passed.');

  await page.locator('.main-nav [data-panel="memory"]').click();
  await page.locator('#preferredName').fill('Mira');
  await page.locator('#saveName').click();
  await page.waitForFunction(() => !document.getElementById('saveName').disabled);
  await page.locator('#memoryInput').fill('Please keep explanations concise.');
  await page.locator('#memoryForm').evaluate(form => form.requestSubmit());
  await page.waitForFunction(() => document.getElementById('memoryList').textContent.includes('concise'));
  assert.equal((await request('/api/profile')).name, 'Mira');
  const secondContext = await browser.newContext();
  const secondPage = await secondContext.newPage();
  await secondPage.goto(url);
  await secondPage.locator('.main-nav [data-panel="memory"]').click();
  await secondPage.waitForFunction(() => document.getElementById('preferredName').value === 'Mira');
  assert.match(await secondPage.locator('#memoryList').textContent(), /concise/);
  await secondContext.close();
  checks.push('Name and notes shared across independent browser contexts');
  await page.locator('#closeDrawer').click();
  assert.match(await send('What name have I asked you to call me? Reply only with that name.', 3), /Mira/);
  checks.push('Saved backend profile included in real model context');

  await page.locator('.main-nav [data-panel="voice"]').click();
  await page.locator('#autoSpeak').check();
  await page.locator('#closeDrawer').click();
  const voicePost = page.waitForResponse(response => response.url().endsWith('/api/speak'));
  const reply = await send('Say hello warmly in one brief sentence.', 4);
  const voiceResponse = await voicePost;
  assert.ok(reply.startsWith(voiceResponse.request().postDataJSON().text));
  const voiceId = (await voiceResponse.json()).id;
  await page.waitForFunction(() => window.RaphaelVoice.playing, null, { timeout: 90000 });
  const levels = [];
  for (let i = 0; i < 8; i++) { levels.push(await page.evaluate(() => window.RaphaelVoice.level)); await sleep(100); }
  assert.ok(Math.max(...levels) - Math.min(...levels) > 0.03);
  assert.equal(await page.evaluate(() => window.RaphaelUI.getState()), 'speaking');
  const speech = await request('/api/jobs/' + voiceId);
  await page.screenshot({ path: path.join(root, 'docs/preview.png') });
  await page.locator('#stopButton').click();
  assert.equal(await page.evaluate(() => window.RaphaelVoice.playing), false);
  checks.push('Real Kokoro auto-speech uses generated reply; orb follows audio; stop halts playback');
  console.log('Real voice and pulse passed: ' + JSON.stringify(speech.details));

  await page.locator('.main-nav [data-panel="voice"]').click();
  await page.locator('#autoSpeak').uncheck();
  await page.locator('#closeDrawer').click();
  const chatPost = page.waitForResponse(response => response.url().endsWith('/api/chat'));
  await page.locator('#messageInput').fill('Write a detailed story about a lighthouse in ten paragraphs.');
  await page.locator('#commandForm').evaluate(form => form.requestSubmit());
  const cancelled = await (await chatPost).json();
  await sleep(500);
  await page.locator('#stopButton').click();
  await sleep(400);
  assert.equal((await request('/api/jobs/' + cancelled.id)).state, 'cancelled');
  const stoppedText = await page.evaluate(() => window.RaphaelUI.getMessages().at(-1).content);
  await sleep(600);
  assert.equal(await page.evaluate(() => window.RaphaelUI.getMessages().at(-1).content), stoppedText);
  checks.push('Real model cancellation has no late UI updates');

  const alternative = await request('/api/chat', { model: 'llama3.2:latest', messages: [{ role: 'user', content: 'What is 7 plus 8? Answer only the number.' }] });
  const alternativeResult = await job(alternative.id);
  assert.match(alternativeResult.text, /15/);
  checks.push('Alternate installed Llama model answers correctly');
  for (const width of [390, 768, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  }
  await page.locator('.original-link').click();
  await page.waitForURL('**/original');
  assert.equal(await page.locator('#demoButton span').first().textContent(), 'Play the experience');
  checks.push('Responsive interface and original design route retained');

  await stop();
  await start();
  assert.deepEqual(await request('/api/profile'), { name: 'Mira', notes: ['Please keep explanations concise.'] });
  await page.goto(url);
  await page.locator('.main-nav [data-panel="memory"]').click();
  await page.waitForFunction(() => document.getElementById('preferredName').value === 'Mira');
  await page.locator('#memoryList button').click();
  await page.waitForFunction(() => document.getElementById('memoryList').textContent === '');
  assert.deepEqual((await request('/api/profile')).notes, []);
  await request('/api/profile', { name: '', notes: [] });
  checks.push('Saved preferences survive backend restart; Forget deletes the saved note');
  assert.deepEqual(errors, []);
  assert.deepEqual(external, []);
  checks.push('No browser errors or external browser requests');
  await stop();
  checks.push('Clean shutdown after both runs');
  const result = { result: 'passed', tested_at: new Date().toISOString(), checks, voice: speech.details,
    alternate_model: alternativeResult.details };
  fs.writeFileSync(path.join(root, 'docs/test-results.json'), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result, null, 2));
})().catch(error => { console.error(error.stack); process.exitCode = 1; }).finally(async () => {
  if (browser) await browser.close();
  try { await stop(); } catch (error) { console.error(error.message); if (child) child.kill(); process.exitCode = 1; }
});

