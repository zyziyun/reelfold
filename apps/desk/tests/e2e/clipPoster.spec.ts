// The clip page player at its start and its versions with the REAL engine (2026-10-13: her "Golden Hour on Elliott
// Bay" clip page sat black at 0:00 - a vlog fades in from black - picking a cover changed nothing she could see, the
// versions read "Edited · Edited · Edited · Original", a version chip started a render, and the other language's cut
// of the same goal video was nowhere on the page). On a goal video made in English and 中文
// (fixture/vlog_lang_pair.py: two finished vlog projects, YouTube / TikTok and 小红书 / B站, and their goal record):
//   * paused at its start the player shows the clip's cover, not a black frame
//   * a cover picked shows at once: the player goes to its start and shows that frame with the title on it; once the
//     clip is rendered again, the render's own cover
//   * the rendered clip's versions are named by what they are ("16:9 · edited", "Original ..."), never just "Edited"
//   * Versions is one switcher grouped by language: a click plays that version's file at once (its shape), never a
//     render; each platform chip says which version it posts; the 中文 cut's 小红书 3:4 plays here with its post copy
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
  const out = execFileSync(process.env.DESK_PYTHON || 'python3', [path.join(import.meta.dirname, 'fixture/vlog_lang_pair.py'), tmp, path.join(tmp, 'profile', 'engine-data')], { env, encoding: 'utf8' });
  const fx = JSON.parse(out.trim().split('\n').pop()!) as { en: { dir: string; status: string; item: string }; zh: { dir: string; status: string; item: string } };
  expect([fx.en.status, fx.zh.status]).toEqual(['done', 'done']);
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
  const idOf = async () => (await api<Hist>('/api/history')).items.find((i) => fs.realpathSync(i.dir) === fs.realpathSync(fx.en.dir))?.id ?? '';
  await expect.poll(idOf, { timeout: 60000 }).not.toBe('');
  done = await idOf();
  expect(done).toBe(fx.en.item);
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
  await hash(`#/p/${done}/clip/main`);
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

// every request the page makes while she only picks versions: none may render, export or edit
const watchRequests = () => {
  const urls: string[] = [];
  const on = (r: { url(): string; method(): string }) => void (r.method() === 'POST' && urls.push(r.url()));
  page.on('request', on);
  return { urls, stop: () => page.off('request', on) };
};

const video = () => page.getByTestId('editor-player').getByTestId('player-video');
const shape = () => video().evaluate((v: HTMLVideoElement) => (v.readyState >= 1 && v.videoHeight ? v.videoWidth / v.videoHeight : 0));
const WANT: Record<string, number> = { '16:9': 16 / 9, '9:16': 9 / 16, '3:4': 3 / 4 };

test('the Versions switcher plays each version at once (never a render); each platform shows the version it posts', async () => {
  test.setTimeout(120000);
  const detail = page.getByTestId('ci-version-detail');
  const req = watchRequests();
  const play = async (a: string) => {
    const b = page.getByTestId(`ci-version-${a}`);
    await expect(b).toHaveAttribute('data-made', '1');
    await b.click();
    await expect(b).toHaveAttribute('aria-checked', 'true');
    await expect(detail).toHaveAttribute('data-aspect', a);
    await expect.poll(shape, { timeout: 15000 }).toBeCloseTo(WANT[a], 2);
    return video().getAttribute('src');
  };
  const srcs = [await play('9:16')];
  // the vertical platforms post the 9:16 version: they are listed under it, and their chips say so
  await expect(detail.locator('[data-testid=ci-version-pf][data-pf=tiktok]')).toBeVisible();
  await expect(page.locator('[data-testid=ci-pf][data-pf=tiktok] [data-testid=ci-pf-version]')).toHaveText('9:16');
  await shot('C5-version-9x16');
  srcs.push(await play('16:9'));
  await expect(detail.locator('[data-testid=ci-version-pf][data-pf=tiktok]')).toHaveCount(0);
  expect(new Set(srcs).size).toBe(2);
  req.stop();
  expect(req.urls.filter((u) => /\/(render|export|edit)\b/.test(u))).toEqual([]);
});

test('a goal video made in two languages: the 中文 cut\'s versions play here too, grouped by language', async () => {
  test.setTimeout(120000);
  const mine = page.getByTestId('ci-versions-mine');
  const zh = page.locator('[data-testid=ci-versions-other][data-lang=zh]');
  await expect(zh).toBeVisible({ timeout: 30000 });
  await expect(mine).toHaveAttribute('data-lang', 'en');
  await expect(mine).toContainText('English');
  await expect(zh).toContainText('中文');
  const req = watchRequests();
  // English 16:9 -> 中文 小红书 3:4: another file, another shape, its language's post copy
  await page.getByTestId('ci-version-16:9').click();
  await expect.poll(shape, { timeout: 15000 }).toBeCloseTo(WANT['16:9'], 2);
  const en = await video().getAttribute('src');
  const x = page.getByTestId('ci-version-zh-3:4');
  await x.click();
  await expect(x).toHaveAttribute('aria-checked', 'true');
  await expect.poll(shape, { timeout: 15000 }).toBeCloseTo(WANT['3:4'], 2);
  const src = (await video().getAttribute('src')) ?? '';
  expect(src).not.toBe(en);
  expect(decodeURIComponent(src)).toMatch(/[/\\]zh[/\\].*xiaohongshu/);
  await expect(page.getByTestId('player-badge')).toContainText('中文');
  const detail = page.getByTestId('ci-version-detail');
  await expect(detail).toHaveAttribute('data-lang', 'zh');
  await expect(detail.locator('[data-testid=ci-version-pf]')).toHaveAttribute('data-pf', 'xiaohongshu');
  await expect(page.getByTestId('ci-version-post')).toContainText(/[\u4e00-\u9fff]/);
  await expect(page.getByTestId('ci-version-16:9')).toHaveAttribute('aria-checked', 'false');
  await shot('C6-version-zh-3x4');
  await page.getByTestId('ci-versions').screenshot({ path: path.join(SHOTS, 'C7-versions-switcher.png') });
  await expect(page.getByTestId('player-badge')).toBeVisible();
  // and back to this clip's English 16:9
  await page.getByTestId('ci-version-16:9').click();
  await expect.poll(() => video().getAttribute('src'), { timeout: 15000 }).toBe(en);
  req.stop();
  expect(req.urls.filter((u) => /\/(render|export|edit)\b/.test(u))).toEqual([]);
});
