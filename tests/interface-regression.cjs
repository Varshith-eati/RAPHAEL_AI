/* Deterministic UI checks with intercepted local API responses; no inference. */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.RAPHAEL_PLAYWRIGHT || 'playwright');
const root = path.resolve(__dirname, '..');
const origin = 'http://127.0.0.1:18978';
let browser;
(async () => {
  browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--mute-audio'] });
  const page = await browser.newPage();
  const errors = [], requests = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => {
    Object.defineProperty(window, 'AudioContext', { value: undefined });
    Object.defineProperty(window, 'webkitAudioContext', { value: undefined });
  });
  await page.route(origin + '/**', async route => {
    const request = route.request(), target = new URL(request.url()).pathname;
    const json = value => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(value) });
    if (target === '/api/status') return json({ app: 'raphael-modular', token: 'review-token',
      chat: 'ready', voice: 'ready', transcription: 'ready', models: ['test-model:latest'], default_model: 'test-model:latest' });
    if (target === '/api/profile') return json({ name: '', notes: [] });
    if (target === '/api/chat') {
      requests.push(request.postDataJSON());
      return route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify({ id: String(requests.length) }) });
    }
    if (target === '/api/jobs/7') return json({kind:'chat',state:'generating',text:'Start by reviewing the first chapter.',details:{}});
    if (target.startsWith('/api/jobs/')) return json({ kind: 'chat', state: 'ready', text: 'Test reply. ' + 'x'.repeat(1780), details: {} });
    if (target.startsWith('/api/cancel/')) return json({ state: 'cancelled' });
    const files = { '/': 'index.html', '/laptop.js': 'laptop.js', '/app.js': 'app.js', '/voice.js': 'voice.js', '/styles.css': 'styles.css', '/microphone.js': 'microphone.js', '/live-call.js': 'live-call.js', '/recorder-worklet.js': 'recorder-worklet.js' };
    if (files[target]) return route.fulfill({ path: path.join(root, 'web', files[target]) });
    return route.fulfill({ status: 404, body: 'Unexpected request' });
  });
  await page.goto(origin);
  await page.waitForFunction(() => window.RaphaelConnection?.token);
  await page.locator('#replyVoiceToggle').click();
  await page.locator('#chatConnection').click();
  await page.waitForFunction(() => document.getElementById('modelSelect').value === 'test-model:latest');
  assert.equal(await page.locator('#modelSelect option[value="test-model:latest"]').textContent(), 'test-model:latest');
  await page.locator('#closeDrawer').click();
  assert.equal(await page.locator('#contextNotice').evaluate(el => el.hidden), true);
  for (let count = 1; count <= 6; count++) {
    await page.locator('#messageInput').fill('Question ' + count + ': ' + 'a'.repeat(1000));
    await page.locator('#commandForm').evaluate(form => form.requestSubmit());
    await page.waitForFunction(n => window.RaphaelUI.getMessages().filter(m => m.role === 'assistant' && m.status === 'complete').length === n, count);
    await page.waitForFunction(() => window.RaphaelUI.getState() === 'idle');
  }
  assert.equal(requests.length, 6);
  for (const payload of requests) {
    assert.ok(payload.messages.reduce((total, message) => total + message.content.length, 0) <= 8000);
    assert.equal(payload.messages[0].role, 'user');
    assert.equal(payload.messages.at(-1).role, 'user');
  }
  assert.ok(!requests.at(-1).messages.some(message => message.content.startsWith('Question 1:')));
  await page.locator('.main-nav [data-panel="conversation"]').click();
  assert.equal(await page.locator('#contextNotice').isVisible(), true);
  assert.equal((await page.evaluate(() => window.RaphaelUI.getMessages())).length, 12);
  await page.locator('#clearConversation').click();
  assert.equal(await page.locator('#contextNotice').evaluate(el => el.hidden), true);
  await page.locator('#closeDrawer').click();
  // Calling the public UI entry point with oversized text must not freeze the tab.
  await page.evaluate(() => window.RaphaelUI.sendMessage('a'.repeat(8001)));
  assert.equal(requests.length, 6);
  assert.equal(await page.evaluate(() => window.RaphaelUI.getState()), 'idle');
  assert.match(await page.locator('#toast').textContent(), /6,000/);
  // A mode change must also revoke a permission request that resolves late.
  await page.evaluate(() => {
    window.qaTrack = { readyState: 'live', stop() { this.readyState = 'ended'; } };
    navigator.mediaDevices.getUserMedia = () => new Promise(resolve => { window.qaGrant = () => resolve({ getTracks: () => [window.qaTrack] }); });
  });
  await page.locator('#voiceButton').click();
  assert.equal(await page.evaluate(() => window.RaphaelMicrophone.state), 'requesting');
  await page.locator('#replyVoiceToggle').click();
  await page.evaluate(() => window.qaGrant());
  await page.waitForFunction(() => window.qaTrack.readyState === 'ended');
  assert.equal(await page.evaluate(() => window.RaphaelMicrophone.state), 'idle');
  assert.equal(requests.length, 6);
  await page.locator('#replyVoiceToggle').click();
  assert.equal(await page.locator('#readTypedText').isVisible(), true);
  await page.reload();
  await page.waitForFunction(() => window.RaphaelConnection?.token);
  assert.equal(await page.locator('#replyVoiceToggle').getAttribute('aria-pressed'), 'true');
  assert.equal(await page.locator('#microphoneControls').isVisible(), false);
  assert.equal(await page.locator('[data-mode]').count(), 0);
  assert.equal(await page.locator('.experience .state-panel').count(), 0);
  await page.locator('[data-panel="appearance"]').click();
  assert.equal(await page.locator('[data-state-option="idle"]').isVisible(), false);
  await page.locator('.core-explorer summary').click();
  assert.equal(await page.locator('[data-state-option="idle"]').isVisible(), true);
  await page.locator('[data-state-option="idle"]').click();
  assert.equal(await page.locator('#detailDialog').evaluate(el => el.open), false);
  await page.locator('#replyVoiceToggle').click();
  await page.evaluate(() => {window.qaInterrupted=window.RaphaelUI.sendMessage('Help me prepare for my history exam.');});
  await page.waitForFunction(() => window.RaphaelUI.getMessages().at(-1)?.content === 'Start by reviewing the first chapter.');
  await page.evaluate(() => window.RaphaelUI.stop());
  await page.evaluate(() => window.RaphaelUI.sendMessage('Make that simpler.'));
  const followup=requests.at(-1).messages;
  assert.equal(followup[0].content,'Help me prepare for my history exam.');
  assert.equal(followup[1].content,'[Interrupted response; incomplete] Start by reviewing the first chapter.');
  assert.equal(followup[2].content,'Make that simpler.');
  assert.deepEqual(errors, []);
  const result = { result: 'passed', tested_at: new Date().toISOString(), checks: [
    'text chat survives unavailable browser audio', 'additional local model label preserved',
    'six-turn history stays within budget and retains whole turns',
    'context notice appears after trimming; messages remain visible; Clear resets notice',
    'oversized programmatic input is rejected without freezing',
    'late microphone permission is released after mode switch; no chat starts',
    'compact spoken-reply preference survives refresh; read aloud remains available',
    'large mode controls removed; core previews accessible only through Appearance drawer',
    'interrupted question and labeled partial answer remain available to follow-up', 'no browser exceptions'],
    sent_message_counts: requests.map(request => request.messages.length), inference: 'simulated' };
  fs.writeFileSync(path.join(root, 'docs/interface-test-results.json'), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result, null, 2));
})().catch(error => { console.error(error.stack); process.exitCode = 1; }).finally(async () => { if (browser) await browser.close(); });

