import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { closeApp } from './closeApp';
test.describe.configure({ mode: 'serial' });
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'reelfold-learning-'));
let app: ElectronApplication;
let page: Page;
let workspaceId = '';
const source = path.join(tmp, 'source.mp4');
const env = { ...process.env, DESK_USER_DATA: path.join(tmp, 'profile'), VSTUDIO_HOME: path.join(tmp, 'vhome'), VSTUDIO_CACHE: path.join(tmp, 'cache'), VSTUDIO_DEFAULT_PERSONA: '1', VSTUDIO_BATCH_BENCH: path.join(tmp, 'bench.json'), DESK_HISTORY_WATCH: '', DESK_ENGINE_MOCK: '', DESK_CREATE: '1', DESK_STUDIO: '1', DESK_HIDE_WINDOW: '1', DESK_E2E_FAKE_MEDIA: '1', DESK_SKIP_FIRST_RUN: '1', VITE_DEV_SERVER_URL: '', ...Object.fromEntries(['', '_INTAKE', '_SEGMENT_PLAN', '_PLANNER', '_COPY'].map((k) => [`VSTUDIO_LLM${k}_PROVIDER`, 'none'])) };
test.beforeAll(async () => {
  execFileSync('ffmpeg', ['-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=red:s=640x360:r=30:d=6', '-f', 'lavfi', '-i', 'sine=frequency=500:duration=6', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', source]);
  app = await electron.launch({ args: [path.resolve(import.meta.dirname, '../..')], env });
  page = await app.firstWindow();
  await page.waitForURL(/^app:\/\/desk\//);
  await page.evaluate(async () => { await window.desk.setSettings({ lang: 'en' }); });
  await page.reload();
});
test.afterAll(async () => { await closeApp(app); });
async function api(method: string, route: string, body?: unknown) {
  return page.evaluate(async ({ method, route, body }) => {
    const info = await window.desk.engineInfo();
    const result = await fetch(info.baseUrl + route, { method, headers: { Authorization: `Bearer ${info.token}`, 'Content-Type': 'application/json' }, ...(body ? { body: JSON.stringify(body) } : {}) });
    if (!result.ok) throw new Error(await result.text());
    return result.json();
  }, { method, route, body });
}
test('human thoughts persist with source times and become an editable post without an AI call', async () => {
  test.setTimeout(120000);
  await page.evaluate(() => { location.hash = '#/create/learning'; });
  await expect(page.getByTestId('learning-create')).toBeVisible();
  await page.getByTestId('learning-idea').fill('A creator thinks before making a post');
  await page.getByTestId('learning-start').click();
  await expect(page.getByTestId('learning-workspace')).toBeVisible();
  const id = await page.evaluate(() => new URLSearchParams(location.hash.split('?')[1]).get('id'));
  expect(id).toMatch(/^[0-9a-f]{12}$/); workspaceId = id!;
  const made = await api('POST', `/api/create/learning/${id}`, { action: 'files', files: [source] });
  const sid = Object.keys(made.sources)[0];
  await page.reload();
  const video = page.getByTestId('learning-source-video');
  await expect(video).toBeVisible();
  await video.evaluate(async (v: HTMLVideoElement) => { await v.play(); });
  await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.currentTime)).toBeGreaterThan(0);
  await page.getByTestId('learning-thought').fill('My own perspective, kept in my own words.');
  await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.paused)).toBe(true);
  await page.getByTestId('learning-save-thought').click();
  await expect(page.getByTestId('learning-notes')).toContainText('My own perspective, kept in my own words.');
  const state = await api('GET', `/api/create/learning/${id}`);
  expect(state.notes[0].source).toBe(sid);
  await page.reload();
  await expect(page.getByTestId('learning-notes')).toContainText('My own perspective, kept in my own words.');
  await page.getByTestId('learning-time-edit').click();
  await page.getByTestId('learning-source-time').fill('1');
  await page.getByTestId('learning-excerpt-tools').click();
  await page.getByTestId('learning-mark-start').click();
  await page.getByTestId('learning-source-time').fill('2');
  await page.getByTestId('learning-keep-range').click();
  await expect(page.getByTestId('learning-block')).toHaveCount(1);
  await page.getByTestId('learning-post').click();
  await expect(page.getByRole('textbox', { name: 'Editable post draft' })).toHaveValue('My own perspective, kept in my own words.');
  const doc = await api('GET', `/api/create/learning/${id}`);
  expect(doc.blocks[0].start).toBe(1);
  expect(doc.blocks[0].end).toBe(2);
});
test('camera and screen sharing stay beside the material; a new take remains editable', async () => {
  test.setTimeout(120000);
  await page.getByTestId('learning-camera-open').click();
  await expect(page.getByTestId('learning-camera-preview')).toBeVisible();
  await page.getByTestId('learning-screen').click();
  await page.getByTestId('learning-material-audio').check();
  await page.getByTestId('rec-screen-toggle').click();
  const first = page.getByTestId('rec-screen-source').first();
  await expect(first).toBeVisible(); await first.click();
  await page.getByTestId('learning-source-video').evaluate(async (v: HTMLVideoElement) => { v.currentTime = 0; v.loop = true; v.muted = false; await v.play(); });
  await page.getByTestId('learning-camera-record').click();
  await expect(page.getByTestId('learning-camera-record')).toContainText('Stop');
  await page.waitForTimeout(1800);
  await page.getByTestId('learning-camera-record').click();
  await expect(page.getByTestId('learning-camera-record')).toContainText('Record my explanation', { timeout: 30000 });
  await expect(page.getByTestId('learning-source-select')).toContainText('My recorded contribution');
  await expect(page.getByTestId('learning-fresh-take')).toBeVisible();
  await page.getByTestId('learning-add-recorded-take').click();
  await expect(page.getByTestId('learning-add-recorded-take')).toBeDisabled();
  await page.getByTestId('learning-source-video').evaluate((v: HTMLVideoElement) => v.pause());
  const doc = await api('GET', `/api/create/learning/${workspaceId}`);
  const take = (Object.values(doc.sources) as { role: string; path: string }[]).find((x) => x.role === 'commentary')!;
  // Chromium's fake-device switch replaces display audio too. This checks track persistence;
  // learningAudio.spec verifies a real app playback tone with that switch absent.
  const pcm = execFileSync('ffmpeg', ['-v', 'error', '-i', take.path, '-vn', '-ac', '1', '-ar', '8000', '-f', 's16le', '-']);
  expect(pcm.length).toBeGreaterThan(8000);
  expect(pcm.some((x) => x !== 0)).toBe(true);
});
test('my ordered draft makes a real demo which opens in the existing editor', async () => {
  test.setTimeout(180000);
  const id = await page.evaluate(() => new URLSearchParams(location.hash.split('?')[1]).get('id'));
  const d = await api('GET', `/api/create/learning/${id}`);
  const take = Object.keys(d.sources).find((s) => d.sources[s].role === 'commentary')!;
  expect(take).toBeTruthy();
  await expect(page.getByTestId('learning-make-demo')).toBeDisabled();
  await page.getByTestId('learning-fill-credit').click();
  await page.getByLabel('Title', { exact: true }).fill('Synthetic test source');
  await page.getByLabel('Author or speaker', { exact: true }).fill('Test fixture');
  await page.getByLabel('Link or edition/page', { exact: true }).fill('Synthetic local media, not a real interview');
  await expect(page.getByTestId('learning-make-demo')).toBeDisabled();
  await page.getByRole('button', { name: 'Save source details', exact: true }).click();
  await expect(page.getByTestId('learning-make-demo')).toBeEnabled();
  await page.reload();
  await expect(page.getByTestId('learning-block')).toHaveCount(2);
  await page.getByTestId('learning-make-demo').click();
  await expect(page.getByTestId('learning-workspace')).toHaveCount(0);
  let item = '';
  let clip = '';
  await expect.poll(async () => {
    const h = await api('GET', '/api/history');
    const entry = h.items.find((x: { dir: string }) => x.dir.endsWith(`learning-${id}`));
    if (!entry) return false;
    item = entry.id;
    const out = await api('GET', `/api/outputs/${item}`);
    const ready = out.clips?.find((x: { id: string; files: unknown[] }) => x.files?.length);
    clip = ready?.id ?? '';
    return !!clip;
  }, { timeout: 120000 }).toBe(true);
  await page.evaluate((url) => { location.hash = url; }, `#/p/${item}/clip/${encodeURIComponent(clip)}`);
  await expect(page.getByTestId('editor')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('editor-player')).toBeVisible();
});

test('an optional AI demo uses only thoughts I select and keeps my original notes', async () => {
  await page.evaluate((id) => { location.hash = `#/create/learning?id=${id}`; }, workspaceId);
  await expect(page.getByTestId('learning-workspace')).toBeVisible();
  await expect(page.getByTestId('learning-ai-demo')).not.toBeVisible();
  await page.getByTestId('learning-tools').click();
  await expect(page.getByTestId('learning-ai-demo')).toBeDisabled();
  await page.getByLabel('Use this thought for an AI demo').first().check();
  await page.getByTestId('learning-ai-demo').click();
  await expect.poll(async () => (await api('GET', `/api/create/learning/${workspaceId}`)).tool_jobs?.length ?? 0, { timeout: 30000 }).toBe(1);
  const doc = await api('GET', `/api/create/learning/${workspaceId}`);
  expect(doc.notes[0].text).toBe('My own perspective, kept in my own words.');
});


test('a book page with my recording becomes a real editable video and workspaces keep thoughts separate', async () => {
  test.setTimeout(180000);
  const book = path.join(tmp, 'book-page-12.png');
  execFileSync('ffmpeg', ['-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=green:s=360x540', '-frames:v', '1', book]);
  const take = path.join(tmp, 'my-reading.mp4');
  fs.copyFileSync(source, take);
  const d = await api('POST', '/api/create/learning', { idea: 'Read a page and explain my understanding', files: [book] });
  const bookId = Object.keys(d.sources)[0];
  let doc = await api('POST', `/api/create/learning/${d.id}`, { action: 'take', files: [take] });
  const myVoice = Object.keys(doc.sources).find((x) => doc.sources[x].role === 'commentary')!;
  await api('POST', `/api/create/learning/${d.id}`, { action: 'credit', source: bookId, credit: { title: 'A synthetic book page', creator: 'Test author', locator: 'Test edition, page 12' } });
  // Same mounted route, distinct workspace. An unsaved thought cannot leak into another project.
  await page.evaluate((id) => { location.hash = `#/create/learning?id=${id}`; }, workspaceId);
  await expect(page.getByTestId('learning-workspace')).toBeVisible();
  await page.getByTestId('learning-thought').fill('Unsaved thought belonging to the interview');
  await page.evaluate((id) => { location.hash = `#/create/learning?id=${id}`; }, d.id);
  await expect(page.getByRole('heading', { name: 'Read a page and explain my understanding' })).toBeVisible();
  await expect(page.getByTestId('learning-thought')).toHaveValue('');
  await expect(page.getByRole('img', { name: 'Source page' })).toBeVisible();
  await expect(page.getByTestId('learning-source-select')).toHaveValue(bookId);
  await page.getByLabel('My recording for this page').selectOption(myVoice);
  await page.getByTestId('learning-thought').fill('My own reading and practical interpretation.');
  await page.getByTestId('learning-save-thought').click();
  await page.getByRole('button', { name: 'Add page with my voice', exact: true }).click();
  await expect(page.getByTestId('learning-block')).toHaveCount(1);
  doc = await api('GET', `/api/create/learning/${d.id}`);
  expect(doc.blocks[0]).toMatchObject({ source: bookId, voice: myVoice, start: 0, voice_start: 0 });
  expect(doc.notes[0]).toMatchObject({ source: bookId, at: null, text: 'My own reading and practical interpretation.' });
  await page.getByTestId('learning-make-demo').click();
  await expect(page.getByTestId('learning-workspace')).toHaveCount(0);
  let item = '', clip = '';
  await expect.poll(async () => {
    const history = await api('GET', '/api/history');
    const row = history.items.find((x: { dir: string }) => x.dir.endsWith(`learning-${d.id}`));
    if (!row) return false;
    item = row.id;
    clip = (await api('GET', `/api/outputs/${item}`)).clips?.find((x: { id: string; files: unknown[] }) => x.files?.length)?.id ?? '';
    return !!clip;
  }, { timeout: 120000 }).toBe(true);
  await page.evaluate((url) => { location.hash = url; }, `#/p/${item}/clip/${encodeURIComponent(clip)}`);
  await expect(page.getByTestId('editor-player')).toBeVisible({ timeout: 30000 });
  const file = await page.getByTestId('editor-player').getByTestId('player-video').evaluate((v: HTMLVideoElement) => v.currentSrc || v.src);
  expect(file).toBeTruthy();
  // Decode the actual file selected by the editor; do not count a montage manifest as a rendered result.
  await expect.poll(() => page.getByTestId('editor-player').getByTestId('player-video').evaluate((v: HTMLVideoElement) => v.readyState)).toBeGreaterThanOrEqual(2);
  expect(new URL(file).protocol).toBe('vsmedia:');
  const movie = decodeURIComponent(new URL(file).pathname.slice(1));
  expect(movie.startsWith(tmp + path.sep)).toBe(true);
  const green = execFileSync('ffmpeg', ['-v', 'error', '-i', movie, '-vf', 'crop=2:2:iw/2:ih/2,scale=1:1', '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']);
  expect(green[1]).toBeGreaterThan(green[0] + 50);
  expect(green[1]).toBeGreaterThan(green[2] + 50);
  const pcm = execFileSync('ffmpeg', ['-v', 'error', '-i', movie, '-vn', '-ac', '1', '-ar', '8000', '-f', 's16le', '-']);
  let real = 0, imag = 0; const count = pcm.length / 2;
  for (let n = 0; n < count; n++) { const x = pcm.readInt16LE(n * 2) / 32768; real += x * Math.cos(2 * Math.PI * 500 * n / 8000); imag += x * Math.sin(2 * Math.PI * 500 * n / 8000); }
  expect(2 * Math.hypot(real, imag) / count).toBeGreaterThan(0.06);
});


test('read attached text, quote it, then add my own thought without executing the source', async () => {
  const notes = path.join(tmp, 'source-notes.md');
  fs.writeFileSync(notes, '# A source passage\n原文观点。<img src=x onerror="window.sourceExecuted=true">');
  const d = await api('POST', '/api/create/learning', { idea: 'Read source notes and think', files: [notes] });
  const sid = Object.keys(d.readings)[0];
  await page.evaluate((id) => { location.hash = `#/create/learning?id=${id}`; }, d.id);
  const reading = page.getByTestId('learning-source-reading');
  await expect(reading).toContainText('原文观点。<img');
  await expect(page.getByTestId('learning-source-select')).toHaveValue(sid);
  expect(await page.evaluate(() => 'sourceExecuted' in window)).toBe(false);
  await page.getByRole('button', { name: 'Source excerpt', exact: true }).click();
  await page.getByTestId('learning-thought').fill('原文观点。');
  await page.getByTestId('learning-save-thought').click();
  let doc = await api('GET', `/api/create/learning/${d.id}`);
  expect(doc.notes[0]).toMatchObject({ source: sid, at: null, kind: 'quote' });
  expect(doc.script).toBe('');
  await page.getByRole('button', { name: 'My thought', exact: true }).click();
  await page.getByTestId('learning-thought').fill('My interpretation stays separate from the quoted text.');
  await page.getByTestId('learning-save-thought').click();
  await page.getByTestId('learning-post').click();
  await expect(page.getByRole('textbox', { name: 'Editable post draft' })).toHaveValue('My interpretation stays separate from the quoted text.');
  await page.reload();
  await expect(reading).toContainText('原文观点。');
  doc = await api('GET', `/api/create/learning/${d.id}`);
  expect(doc.notes).toHaveLength(2);
  expect(fs.readFileSync(notes, 'utf8')).toContain('# A source passage');
});


test('YouTube login hands playback to the normal browser at my chosen time and keeps my thoughts', async () => {
  const d = await api('POST', '/api/create/learning', { idea: 'Think alongside this interview https://www.youtube.com/watch?v=6WaeGfLnRvc&t=3198s', files: [] });
  await page.route('https://www.youtube-nocookie.com/embed/**', (route) => route.fulfill({ contentType: 'text/html', body: '<p>Test player: sign in to continue</p>' }));
  await app.evaluate(({ shell }) => {
    const state = globalThis as unknown as { originalBrowserOpen: typeof shell.openExternal; browserUrls: string[] };
    state.originalBrowserOpen = shell.openExternal; state.browserUrls = [];
    shell.openExternal = async (url) => { state.browserUrls.push(url); };
  });
  try {
    await page.evaluate((id) => { location.hash = `#/create/learning?id=${id}`; }, d.id);
    await expect(page.getByTestId('learning-youtube-browser')).toBeVisible();
    await page.getByTestId('learning-thought').fill('My idea before signing in.');
    await page.getByTestId('learning-save-thought').click();
    await page.getByTestId('learning-time-edit').click();
    await page.getByTestId('learning-source-time').fill('3201');
    await page.getByTestId('learning-youtube-browser').click();
    expect(await app.evaluate(() => (globalThis as unknown as { browserUrls: string[] }).browserUrls)).toEqual(['https://www.youtube.com/watch?v=6WaeGfLnRvc&t=3201s']);
    await expect(page.getByTestId('learning-workspace')).toBeVisible();
    await expect(page.getByTestId('learning-notes')).toContainText('My idea before signing in.');
    await page.reload();
    await expect(page.getByTestId('learning-notes')).toContainText('My idea before signing in.');
  } finally {
    await app.evaluate(({ shell }) => { shell.openExternal = (globalThis as unknown as { originalBrowserOpen: typeof shell.openExternal }).originalBrowserOpen; });
    await page.unroute('https://www.youtube-nocookie.com/embed/**');
  }
});
