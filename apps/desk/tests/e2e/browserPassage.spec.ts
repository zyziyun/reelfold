// Real Chrome tab-picture/audio -> downloaded MediaRecorder WebM -> native file drop -> creator video.
// The only shared source is a local synthetic page. No real accounts, user tabs, system capture or fake audio.
import { _electron as electron, chromium, expect, test } from '@playwright/test';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { closeApp } from './closeApp';
import { browserCapturePage } from '../../src/main/browserCapture';

const magnitude = (pcm: Buffer, hz: number) => {
  let real = 0, imag = 0; const count = pcm.length / 2;
  for (let n = 0; n < count; n++) { const x = pcm.readInt16LE(n * 2) / 32768; real += x * Math.cos(2 * Math.PI * hz * n / 8000); imag += x * Math.sin(2 * Math.PI * hz * n / 8000); }
  return 2 * Math.hypot(real, imag) / count;
};

test('a browser passage with sound drops into my materials and becomes a video with my own explanation', async () => {
  test.setTimeout(180000);
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'reelfold-browser-passage-'));
  const env = { ...process.env, DESK_USER_DATA: path.join(temp, 'profile'), VSTUDIO_HOME: path.join(temp, 'home'), VSTUDIO_CACHE: path.join(temp, 'cache'), VSTUDIO_DEFAULT_PERSONA: '1', DESK_CREATE: '1', DESK_STUDIO: '1', DESK_HISTORY_WATCH: '', DESK_ENGINE_MOCK: '', DESK_SKIP_FIRST_RUN: '1', DESK_HIDE_WINDOW: '1', VITE_DEV_SERVER_URL: '', VSTUDIO_LLM_PROVIDER: 'none' };
  const app = await electron.launch({ args: [path.resolve(import.meta.dirname, '../..')], env });
  let browser: Awaited<ReturnType<typeof chromium.launch>> | undefined;
  try {
    browser = await chromium.launch({ channel: 'chrome', headless: true, ignoreDefaultArgs: ['--mute-audio'], args: ['--auto-select-tab-capture-source-by-title=Reelfold captured source fixture', '--enable-usermedia-screen-capturing', '--disable-backgrounding-occluded-windows', '--disable-renderer-backgrounding'] });
    const page = await app.firstWindow(); await page.waitForURL(/^app:\/\/desk\//);
    await page.evaluate(async () => { await window.desk.setSettings({ lang: 'en' }); }); await page.reload();
    const api = (method: string, route: string, body?: unknown) => page.evaluate(async ({ method, route, body }) => {
      const engine = await window.desk.engineInfo(); const r = await fetch(engine.baseUrl + route, { method, headers: { Authorization: `Bearer ${engine.token}`, 'Content-Type': 'application/json' }, ...(body ? { body: JSON.stringify(body) } : {}) });
      if (!r.ok) throw new Error(await r.text()); return r.json();
    }, { method, route, body });
    const workspace = await api('POST', '/api/create/learning', { idea: 'Watch, pause and explain https://www.youtube.com/watch?v=6WaeGfLnRvc&t=3198s', files: [] });
    await app.evaluate(({ app, shell }) => { app.getApplicationInfoForProtocol = async () => { throw new Error('Test: intercept browser handoff through OS fallback'); }; (globalThis as unknown as { captureUrl: string }).captureUrl = ''; shell.openExternal = async (url) => { (globalThis as unknown as { captureUrl: string }).captureUrl = url; }; });
    expect(await app.evaluate(async ({ app }) => { try { await app.getApplicationInfoForProtocol('https://'); return false; } catch { return true; } })).toBe(true);
    await page.route('https://www.youtube-nocookie.com/embed/**', (route) => route.fulfill({ contentType: 'text/html', body: '<p>Test player</p>' }));
    await page.evaluate((id) => { location.hash = `#/create/learning?id=${id}`; }, workspace.id);
    await page.getByTestId('learning-browser-tools').click(); await page.getByTestId('learning-browser-capture').click();
    await expect.poll(() => app.evaluate(() => (globalThis as unknown as { captureUrl: string }).captureUrl)).toMatch(/^file:/);
    const captureUrl = await app.evaluate(() => (globalThis as unknown as { captureUrl: string }).captureUrl);
    expect(captureUrl.startsWith('file:')).toBe(true);
    expect(fs.readFileSync(fileURLToPath(captureUrl), 'utf8')).toContain("connect-src 'none'");
    const source = path.join(temp, 'synthetic-source.html');
    fs.writeFileSync(source, '<!doctype html><title>Reelfold captured source fixture</title><style>body{background:green;color:white}</style><h1>Artificial source</h1><button id="play">Play tone</button><script>document.querySelector("#play").onclick=async()=>{const c=new AudioContext();await c.resume();const o=c.createOscillator();o.frequency.value=500;const g=c.createGain();g.gain.value=.1;o.connect(g).connect(c.destination);o.start();};</script>');
    const context = await browser.newContext({ acceptDownloads: true }); const sourceTab = await context.newPage();
    await sourceTab.goto(pathToFileURL(source).href); await sourceTab.locator('#play').click();
    const capture = await context.newPage(); await capture.goto(captureUrl);
    expect(await capture.evaluate(() => isSecureContext)).toBe(true);
    await capture.locator('#start').click(); await expect(capture.locator('#stop')).toBeVisible();
    await capture.waitForTimeout(2200);
    const downloaded = capture.waitForEvent('download'); await capture.locator('#stop').click();
    const raw = path.join(temp, 'browser-passage.webm'); await (await downloaded).saveAs(raw);
    const originalHash = createHash('sha256').update(fs.readFileSync(raw)).digest('hex');
    const pcm = execFileSync('ffmpeg', ['-v', 'error', '-i', raw, '-vn', '-ac', '1', '-ar', '8000', '-f', 's16le', '-']);
    expect(magnitude(pcm, 500)).toBeGreaterThan(0.025); expect(magnitude(pcm, 400)).toBeLessThan(0.01);
    // DOM.setFileInputFiles creates a genuine file-backed File; Electron webUtils resolves its native path.
    await page.evaluate(() => { const input = document.createElement('input'); input.type = 'file'; input.id = 'native-file-drop'; document.body.append(input); });
    await page.locator('#native-file-drop').setInputFiles(raw);
    await page.evaluate(() => { const input = document.querySelector('#native-file-drop') as HTMLInputElement; const data = new DataTransfer(); data.items.add(input.files![0]); document.querySelector('[data-testid="learning-material-panel"]')!.dispatchEvent(new DragEvent('drop', { dataTransfer: data, bubbles: true, cancelable: true })); input.remove(); });
    await expect(page.getByTestId('learning-source-video')).toBeVisible();
    await expect.poll(() => page.getByTestId('learning-source-video').evaluate((v: HTMLVideoElement) => v.duration)).toBeGreaterThan(2);
    let doc = await api('GET', `/api/create/learning/${workspace.id}`); const ref = Object.keys(doc.sources)[0];
    expect(doc.sources[ref].path).not.toBe(raw); expect(doc.sources[ref].has_audio).toBe(true);
    expect(createHash('sha256').update(fs.readFileSync(raw)).digest('hex')).toBe(originalHash);
    await api('POST', `/api/create/learning/${workspace.id}`, { action: 'credit', source: ref, credit: { title: 'Synthetic browser source', creator: 'Test fixture', locator: 'Local test page, not a real interview' } });
    await api('POST', `/api/create/learning/${workspace.id}`, { action: 'block', block: { source: ref, start: 0, end: 1, point: 'The source passage' } });
    const own = path.join(temp, 'my-explanation.mp4'); execFileSync('ffmpeg', ['-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=red:s=320x240:r=30:d=1', '-f', 'lavfi', '-i', 'sine=frequency=660:duration=1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', own]);
    doc = await api('POST', `/api/create/learning/${workspace.id}`, { action: 'take', files: [own] }); const mine = Object.keys(doc.sources).find((id) => doc.sources[id].role === 'commentary')!;
    await api('POST', `/api/create/learning/${workspace.id}`, { action: 'block', block: { source: mine, start: 0, end: 1, point: 'My own explanation' } });
    await page.reload(); await page.getByTestId('learning-make-demo').click(); await expect(page.getByTestId('learning-workspace')).toHaveCount(0);
    let item = '', clip = '';
    await expect.poll(async () => { const h = await api('GET', '/api/history'); const row = h.items.find((x: { dir: string }) => x.dir.endsWith(`learning-${workspace.id}`)); if (!row) return false; item = row.id; clip = (await api('GET', `/api/outputs/${item}`)).clips?.find((x: { id: string; files: unknown[] }) => x.files?.length)?.id ?? ''; return !!clip; }, { timeout: 120000 }).toBe(true);
    await page.evaluate((url) => { location.hash = url; }, `#/p/${item}/clip/${encodeURIComponent(clip)}`);
    const player = page.getByTestId('editor-player').getByTestId('player-video'); await expect(player).toBeVisible();
    await expect.poll(() => player.evaluate((v: HTMLVideoElement) => v.readyState)).toBeGreaterThanOrEqual(2);
    const url = await player.evaluate((v: HTMLVideoElement) => v.currentSrc || v.src); const movie = decodeURIComponent(new URL(url).pathname.slice(1));
    for (const [at, hz, color] of [[0.2, 500, 1], [1.2, 660, 0]]) {
      const audio = execFileSync('ffmpeg', ['-v', 'error', '-ss', String(at), '-i', movie, '-t', '0.5', '-vn', '-ac', '1', '-ar', '8000', '-f', 's16le', '-']); expect(magnitude(audio, hz)).toBeGreaterThan(0.025);
      const pixel = execFileSync('ffmpeg', ['-v', 'error', '-ss', String(at), '-i', movie, '-vf', 'crop=2:2:iw/2:ih/2,scale=1:1', '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']);
      expect(pixel[color]).toBeGreaterThan(pixel[1 - color] + 50);
    }
  } finally { await browser?.close(); await closeApp(app); }
});


test('cancelled or audio-less sharing gives a retry, not a silent recording', async () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'reelfold-browser-capture-failures-'));
  const file = path.join(temp, 'capture.html'); fs.writeFileSync(file, browserCapturePage('en'));
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage();
    await page.goto(pathToFileURL(file).href);
    await page.evaluate(() => { navigator.mediaDevices.getDisplayMedia = async () => { throw new DOMException('User cancelled', 'NotAllowedError'); }; });
    await page.locator('#start').click(); await expect(page.locator('#status')).toContainText('cancelled');
    await expect(page.locator('#start')).toBeEnabled(); await expect(page.locator('#download')).not.toBeVisible();
    await page.evaluate(() => {
      const canvas = document.createElement('canvas'); canvas.width = 16; canvas.height = 16;
      const stream = canvas.captureStream(1); (window as unknown as { noAudio: MediaStream }).noAudio = stream;
      navigator.mediaDevices.getDisplayMedia = async () => stream;
    });
    await page.locator('#start').click(); await expect(page.locator('#status')).toContainText('No tab audio');
    expect(await page.evaluate(() => (window as unknown as { noAudio: MediaStream }).noAudio.getTracks().every((t) => t.readyState === 'ended'))).toBe(true);
    await expect(page.locator('#start')).toBeEnabled(); await expect(page.locator('#download')).not.toBeVisible();
  } finally { await browser.close(); }
});
