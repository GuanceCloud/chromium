// Small Linux smoke test. Requires Node.js 22+; no npm packages or credentials.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { setTimeout: delay } = require('node:timers/promises');

async function main() {
  const binary = process.argv[2];
  assert(binary, 'Usage: node smoke.cjs /path/to/headless_shell [screenshot.png]');
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'datakit-shell-smoke-'));
  const server = http.createServer((request, response) => {
    response.setHeader('Content-Type', 'text/html; charset=utf-8');
    response.end(`<!doctype html><meta charset="utf-8"><title>DataKit smoke</title>
      <style>button { width: 140px; height: 40px; }</style>
      <form name="frmLogin"><select name="lang"><option value="cn">中文</option></select>
      <input name="userid" value="local-smoke"><button type="button"
      onclick="setTimeout(() => document.body.dataset.clicked='yes', 20)">Continue</button></form>`);
  });
  let browser;
  let socket;
  let logs = '';
  const pending = new Map();
  try {
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    browser = spawn(binary, [
      '--headless', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
      '--disable-background-networking', '--site-per-process',
      '--blink-settings=imagesEnabled=false', '--disable-remote-fonts',
      '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0',
      `--user-data-dir=${profile}`, 'about:blank',
    ], { detached: true, stdio: ['ignore', 'ignore', 'pipe'] });
    browser.stderr.on('data', data => { logs = (logs + data).slice(-16000); });
    browser.on('error', error => { logs += String(error); });
    let endpoint;
    for (let attempt = 0; attempt < 100; attempt++) {
      endpoint = logs.match(/DevTools listening on (ws:\/\/\S+)/)?.[1];
      if (endpoint) break;
      assert(browser.exitCode === null, `Browser exited: ${logs}`);
      await delay(100);
    }
    assert(endpoint, `No CDP endpoint: ${logs}`);
    socket = new WebSocket(endpoint);
    await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
    let nextId = 0;
    socket.onmessage = event => {
      const message = JSON.parse(event.data);
      const callback = pending.get(message.id);
      if (!callback) return;
      pending.delete(message.id);
      clearTimeout(callback.timer);
      if (message.error) callback.reject(new Error(JSON.stringify(message.error)));
      else callback.resolve(message.result);
    };
    function send(method, params = {}, sessionId) {
      return new Promise((resolve, reject) => {
        const id = ++nextId;
        const timer = setTimeout(() => { pending.delete(id); reject(new Error(`Timeout: ${method}`)); }, 10000);
        pending.set(id, { resolve, reject, timer });
        socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
      });
    }
    async function page() {
      const { browserContextId } = await send('Target.createBrowserContext', { disposeOnDetach: true });
      const { targetId } = await send('Target.createTarget', { url: 'about:blank', browserContextId });
      const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
      const cmd = (method, params) => send(method, params, sessionId);
      const evaluate = async expression => {
        const result = await cmd('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
        assert(!result.exceptionDetails, JSON.stringify(result.exceptionDetails));
        return result.result.value;
      };
      await cmd('Page.enable');
      await cmd('Page.navigate', { url: `http://127.0.0.1:${server.address().port}/` });
      let ready = false;
      for (let attempt = 0; attempt < 50; attempt++) {
        if (await evaluate('document.readyState === "complete" && !!document.frmLogin')) { ready = true; break; }
        await delay(50);
      }
      assert(ready, 'Local page did not become ready');
      return { cmd, evaluate, browserContextId };
    }
    const first = await page();
    assert.equal(await first.evaluate('document.frmLogin.lang.value'), 'cn');
    assert.equal(await first.evaluate('document.frmLogin.userid.value'), 'local-smoke');
    const box = await first.evaluate('(()=>{const r=document.querySelector("button").getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2,width:r.width}})()');
    assert.equal(box.width, 140);
    await first.cmd('Input.dispatchMouseEvent', { type: 'mousePressed', x: box.x, y: box.y, button: 'left', clickCount: 1 });
    await first.cmd('Input.dispatchMouseEvent', { type: 'mouseReleased', x: box.x, y: box.y, button: 'left', clickCount: 1 });
    await delay(100);
    assert.equal(await first.evaluate('document.body.dataset.clicked'), 'yes');
    await first.evaluate('localStorage.setItem("tenant-smoke", "first-context")');
    const second = await page();
    assert.equal(await second.evaluate('localStorage.getItem("tenant-smoke")'), null);
    const screenshot = await first.cmd('Page.captureScreenshot', { format: 'png' });
    const png = Buffer.from(screenshot.data, 'base64');
    assert.equal(png.subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
    if (process.argv[3]) fs.writeFileSync(process.argv[3], png);
    const version = await send('Browser.getVersion');
    console.log(JSON.stringify({ passed: true, version: version.product, checks: ['named form controls', 'layout', 'mouse click', 'timer', 'context storage separation', 'PNG screenshot'], screenshotBytes: png.length }));
    await send('Browser.close');
  } finally {
    for (const callback of pending.values()) clearTimeout(callback.timer);
    socket?.close();
    if (browser?.pid) {
      try { process.kill(-browser.pid, 'SIGTERM'); } catch (error) { if (error.code !== 'ESRCH') throw error; }
      await delay(300);
      try { process.kill(-browser.pid, 'SIGKILL'); } catch (error) { if (error.code !== 'ESRCH') throw error; }
    }
    server.close();
    fs.rmSync(profile, { recursive: true, force: true });
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
