// The clip page player at its start and its version chips with the REAL engine (2026-10-13, her "Golden Hour on
// Elliott Bay" clip page sat black at 0:00 - a vlog fades in from black - picking a cover changed nothing she could
// see, and the versions read "Edited · Edited · Edited · Original"). On the project-page fixture's finished vlog
// (fixture/vlog_pages_project.py):
//   * paused at its start the player shows the clip's cover, not a black frame
//   * a cover picked shows at once: the player goes to its start and shows that frame with the title on it; once the
//     clip is rendered again, the render's own cover
//   * the rendered clip's versions are named by what they are ("16:9 · edited", "Original ..."), never just "Edited"
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

let app: ElectronApplication;
let page: Page;
let done = '';
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-clipposter-'));
const REPO = path.resolve(import.meta.dirname, '../../../..');
const SHOTS = process.env.DESK_SHOTS_DIR ?? path.resolve(import.meta.dirname, '../../test-results/clip-poster');
fs.mkdirSync(SHOTS, { recursive: true });
const engineEnv = {
  VSTUDIO_HOME: path.join(tmp, 'vhome'),
  VSTUDIO_CACHE: path.join(tmp, 'vcache'),
  VSTUDIO_MUSIC_DIRS: '',
  VSTUDIO_BATCH_BENCH: path.join(tmp, 'bench.json'),
  VSTUDIO_DEFAULT_PERSONA: '1',
  VSTUDIO_LLM_PROVIDER: 'none',
  ...Object.fromEntries(['SEGMENT_PLAN', 'PROOFREAD', 'GLOSSARY', 'COPY', 'SCRIPT', 'PLANNER', 'INTAKE', 'OUTPUT_EDIT', 'EDIT', 'JUDGE'].map((t) => [`VSTUDIO_LLM_${t}_PROVIDER`, 'none'])),
};

type Hist = { items: { id: string; dir: string }[] };

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  test.setTimeout(300000);
  const env: NodeJS.ProcessEnv = { ...process.env, ...engineEnv, PYTHONPATH: path.join(REPO, 'lib') };
  for (const k of ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'VSTUDIO_PERSONA']) delete env[k];
  const out = execFileSync(process.env.DESK_PYTHON || 'python3', [path.join(import.meta.dirname, 'fixture/vlog_pages_project.py'), tmp], { env, encoding: 'utf8' });
  const fx = JSON.parse(out.trim().split('\n').pop()!) as { done: { dir: string; status: string } };
  expect(fx.done.status).toBe('done');
  app = await electron.launch({
    args: [path.resolve(import.meta.dirname, '../..')],
    env: { ...env, PYTHONPATH: '', DESK_STUDIO: '1', DESK_ENGINE_MOCK: '', DESK_USER_DATA: path.join(tmp, 'profile'), DESK_HISTORY_WATCH: '', DESK_HIDE_WINDOW: '1', DESK_SHARED_CACHE: path.join(tmp, 'cache'), DESK_HF_HUB: '', DESK_SKIP_FIRST_RUN: '1', VITE_DEV_SERVER_URL: '' },
  });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForURL(/^app:\/\/desk\//);
  await page.evaluate(async () => {
    localStorage.setItem('i18n.strict', '1');
    await window.desk.setSettings({ lang: 'en' });
  });
  await page.reload();
  await page.waitForURL(/^app:\/\/desk\//);
  expect((await page.evaluate(() => window.desk.engineInfo())).mode).toBe('real');
  const idOf = async () => (await api<Hist>('/api/history')).items.find((i) => fs.realpathSync(i.dir) === fs.realpathSync(fx.done.dir))?.id ?? '';
  await expect.poll(idOf, { timeout: 60000 }).not.toBe('');
  done = await idOf();
});

test.afterAll(async () => {
  await closeApp(app);
});

const hash = (h: string) => page.evaluate((x) => (location.hash = x), h);
const shot = (name: string) => page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
const api = <T,>(p: string, body?: unknown) =>
  page.evaluate(
    async ([u, b]) => {
      const info = await window.desk.engineInfo();
      const r = await fetch(info.baseUrl + u, { method: b === undefined ? 'GET' : 'POST', headers: { Authorization: `Bearer ${info.token}`, 'Content-Type': 'application/json' }, body: b === undefined ? undefined : JSON.stringify(b) });
      return r.json();
    },
    [p, body] as const,
  ) as Promise<T>;

/** the mean brightness (0-255) of what the player shows in its frame (a screenshot: the media itself is cross-origin) */
const brightness = async () => {
  const png = (await page.locator('[data-testid=editor-player] .frame').screenshot()).toString('base64');
  return page.evaluate(async (b64) => {
    const img = new Image();
    img.src = `data:image/png;base64,${b64}`;
    await img.decode();
    const c = document.createElement('canvas');
    c.width = 64;
    c.height = 36;
    const g = c.getContext('2d')!;
    g.drawImage(img, 0, 0, 64, 36);
    const d = g.getImageData(0, 0, 64, 36).data;
    let s = 0;
    for (let i = 0; i < d.length; i += 4) s += (d[i] + d[i + 1] + d[i + 2]) / 3;
    return s / (d.length / 4);
  }, png);
};

test('paused at its start the clip page player shows the cover; a cover picked shows at once, then its render', async () => {
  test.setTimeout(300000);
  await hash('#/studio');
  const r = page.locator(`[data-testid=studio-row][data-row="${done}/main"]`);
  await expect(r).toHaveAttribute('data-group', 'ready', { timeout: 60000 });
  await r.click();
  await expect(page.getByTestId('editor')).toHaveAttribute('data-layout', 'studio', { timeout: 30000 });
  const player = page.getByTestId('editor-player');
  const video = player.getByTestId('player-video');
  await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.readyState), { timeout: 20000 }).toBeGreaterThanOrEqual(2);
  await page.waitForTimeout(400);
  await shot('C1-clip-page-at-start');
  // the clip's cover over the black first frame (the vlog fades in from black)
  const poster = player.getByTestId('player-poster');
  await expect(poster).toBeVisible();
  await expect(poster.locator('img')).toHaveAttribute('data-kind', 'cover');
  await expect.poll(() => poster.locator('img').evaluate((i: HTMLImageElement) => i.complete && i.naturalWidth > 0)).toBe(true);
  expect(await brightness()).toBeGreaterThan(25);
  // playing: the video itself; paused at its start again: the cover
  await player.getByTestId('player-play').click();
  await expect(poster).toHaveCount(0);
  await player.getByTestId('player-play').click();
  await page.keyboard.press('Home');
  await expect(poster).toBeVisible();
  // a cover picked mid-clip: at once the player is at its start showing that frame with the title on it
  const covers = page.getByTestId('ci-cover');
  await expect(covers.first()).toBeVisible({ timeout: 30000 });
  await video.evaluate((v: HTMLVideoElement) => (v.currentTime = Math.min(2, v.duration / 2)));
  await expect(poster).toHaveCount(0);
  const pick = covers.nth(2);
  const at = Number(((await pick.getAttribute('aria-label')) ?? '').match(/[\d.]+/)?.[0]);
  await pick.click();
  const frame = poster.locator('video[data-kind=frame]');
  await expect(frame).toBeVisible({ timeout: 2000 });
  expect(Number(await frame.getAttribute('data-t'))).toBeCloseTo(at, 1);
  await expect(player.getByTestId('player-poster-title')).not.toBeEmpty();
  await expect.poll(() => frame.evaluate((v: HTMLVideoElement) => v.readyState >= 2 && !v.seeking && Math.abs(v.currentTime - Number(v.dataset.t)) < 0.1), { timeout: 15000 }).toBe(true);
  expect(await brightness()).toBeGreaterThan(25);
  expect(await video.evaluate((v: HTMLVideoElement) => v.paused && v.currentTime < 0.05)).toBe(true);
  await shot('C2-cover-picked');
  // the clip renders again by itself: then the render's own cover
  await expect(page.getByTestId('ci-render')).toHaveAttribute('data-phase', 'done', { timeout: 240000 });
  await expect(poster.locator('img[data-kind=cover]')).toHaveAttribute('data-src', /renders[\\/].*cover.*\.jpg$/, { timeout: 30000 });
  await expect.poll(() => poster.locator('img').evaluate((i: HTMLImageElement) => i.complete && i.naturalWidth > 0)).toBe(true);
  expect(await brightness()).toBeGreaterThan(25);
  await shot('C3-cover-rendered');
});

test('the rendered clip\'s versions are named by what they are, never just "Edited"', async () => {
  const chips = page.locator('[data-testid=editor-player] .vers button');
  await expect(chips.first()).toBeVisible({ timeout: 30000 });
  const names = await chips.allInnerTexts();
  await shot('C4-version-chips');
  expect(names[0]).toBe('16:9 · edited');
  expect(names).not.toContain('Edited');
  expect(names.some((n) => /^Original\b/.test(n))).toBe(true);
  expect(new Set(names).size).toBe(names.length);
});
