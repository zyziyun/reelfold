// The piece viewer ("How it is being made" -> a piece opened big) with the REAL engine (2026-10-13, Reelfold 0.2.8:
// a 16:9 "Picture 3" opened on a running project had its action bar cut in half by the bottom of the box, the Live
// pane showing under it). On the project-page fixture (fixture/vlog_pages_project.py, the vlog recipe on autopilot):
//   * on the run page (the Live pane docked under it) a contact sheet and a graded segment open over the whole window,
//     at 1280x720 and 1440x900: the overlay covers the window, the media and its action bar sit inside the box and the
//     window, the buttons are on top (nothing over them); Esc and a click outside close it; ← → step between pieces
//   * on the finished project's page a 9:16 and a 1:1 segment and a tall image fit the same way
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

let app: ElectronApplication;
let page: Page;
let done = '';
let fresh = '';
const dirs = { done: '', fresh: '' };
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-pieceviewer-'));
const REPO = path.resolve(import.meta.dirname, '../../../..');
const SHOTS = process.env.DESK_SHOTS_DIR ?? path.resolve(import.meta.dirname, '../../test-results/piece-viewer');
fs.mkdirSync(SHOTS, { recursive: true });
const SIZES = [
  { width: 1280, height: 720 },
  { width: 1440, height: 900 },
];
const engineEnv = {
  VSTUDIO_HOME: path.join(tmp, 'vhome'),
  VSTUDIO_CACHE: path.join(tmp, 'vcache'),
  VSTUDIO_MUSIC_DIRS: '',
  VSTUDIO_BATCH_BENCH: path.join(tmp, 'bench.json'),
  VSTUDIO_DEFAULT_PERSONA: '1',
  VSTUDIO_LLM_PROVIDER: 'none',
  ...Object.fromEntries(['SEGMENT_PLAN', 'PROOFREAD', 'GLOSSARY', 'COPY', 'SCRIPT', 'PLANNER', 'INTAKE', 'OUTPUT_EDIT', 'EDIT', 'JUDGE'].map((t) => [`VSTUDIO_LLM_${t}_PROVIDER`, 'none'])),
};

type Hist = { items: { id: string; dir: string; stopped?: number; live?: { state?: string } | null }[] };

test.describe.configure({ mode: 'serial' });

const ffmpeg = (...a: string[]) => execFileSync('ffmpeg', ['-loglevel', 'error', '-y', ...a]);

test.beforeAll(async () => {
  test.setTimeout(300000);
  const env: NodeJS.ProcessEnv = { ...process.env, ...engineEnv, PYTHONPATH: path.join(REPO, 'lib') };
  for (const k of ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'VSTUDIO_PERSONA']) delete env[k];
  const out = execFileSync(process.env.DESK_PYTHON || 'python3', [path.join(import.meta.dirname, 'fixture/vlog_pages_project.py'), tmp, '--fresh-secs', '24'], { env, encoding: 'utf8' });
  const fx = JSON.parse(out.trim().split('\n').pop()!) as { done: { dir: string; status: string }; fresh: { dir: string } };
  expect(fx.done.status).toBe('done');
  dirs.done = fx.done.dir;
  dirs.fresh = fx.fresh.dir;
  // the finished project's pieces in other shapes (its own files, rewritten): a 9:16 and a 1:1 graded segment, a
  // tall contact sheet
  const work = path.join(dirs.done, 'items', 'main', 'work');
  ffmpeg('-f', 'lavfi', '-i', 'testsrc=size=1080x1920:rate=30:duration=2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', path.join(work, 'clips', 'seg_01.mp4'));
  ffmpeg('-f', 'lavfi', '-i', 'testsrc=size=1080x1080:rate=30:duration=2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', path.join(work, 'clips', 'seg_02.mp4'));
  ffmpeg('-f', 'lavfi', '-i', 'testsrc=size=900x2400', '-frames:v', '1', path.join(work, 'sheets', 'DJI_0002_D_sheet.jpg'));
  app = await electron.launch({
    args: [path.resolve(import.meta.dirname, '../..')],
    env: { ...env, PYTHONPATH: '', DESK_STUDIO: '1', DESK_ENGINE_MOCK: '', DESK_USER_DATA: path.join(tmp, 'profile'), DESK_HISTORY_WATCH: '', DESK_HIDE_WINDOW: '1', DESK_SHARED_CACHE: path.join(tmp, 'cache'), DESK_HF_HUB: '', DESK_SKIP_FIRST_RUN: '1', VITE_DEV_SERVER_URL: '' },
  });
  page = await app.firstWindow();
  await page.setViewportSize(SIZES[1]);
  await page.waitForURL(/^app:\/\/desk\//);
  await page.evaluate(async () => {
    localStorage.setItem('i18n.strict', '1');
    await window.desk.setSettings({ lang: 'en' });
  });
  await page.reload();
  await page.waitForURL(/^app:\/\/desk\//);
  expect((await page.evaluate(() => window.desk.engineInfo())).mode).toBe('real');
  const idOf = async (d: string) => (await api<Hist>('/api/history')).items.find((i) => fs.realpathSync(i.dir) === fs.realpathSync(d))?.id ?? '';
  await expect.poll(() => idOf(dirs.done), { timeout: 60000 }).not.toBe('');
  await expect.poll(() => idOf(dirs.fresh), { timeout: 60000 }).not.toBe('');
  done = await idOf(dirs.done);
  fresh = await idOf(dirs.fresh);
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

type Box = { x: number; y: number; width: number; height: number };
const inside = (what: string, a: Box | null, b: Box) => {
  expect(a, what).not.toBeNull();
  const e = 0.5;
  expect([a!.x >= b.x - e, a!.y >= b.y - e, a!.x + a!.width <= b.x + b.width + e, a!.y + a!.height <= b.y + b.height + e], `${what}: ${JSON.stringify(a)} in ${JSON.stringify(b)}`).toEqual([true, true, true, true]);
};

/** the open piece fits: the overlay over the whole window, the box in it, the media and both actions in the box, the
 * actions on top (what is under their middle is the button) */
async function fits(name: string) {
  const vp = page.viewportSize()!;
  const win = { x: 0, y: 0, ...vp };
  const view = page.getByTestId('piece-view');
  await expect(view).toBeVisible();
  // laid out: the image is in / the video knows its shape
  await expect.poll(() => view.locator('img, video').first().evaluate((m) => (m instanceof HTMLImageElement ? m.complete && m.naturalWidth > 0 : (m as HTMLVideoElement).readyState >= 1)), { timeout: 15000 }).toBe(true);
  await page.waitForTimeout(250); // the fade-in
  await shot(name);
  const ov = await view.boundingBox();
  expect(ov).toEqual(win);
  const box = await view.getByTestId('piece-box').boundingBox();
  inside(`${name} box`, box, win);
  const media = await view.locator('img, video').first().boundingBox();
  inside(`${name} media`, media, box!);
  expect(media!.height, `${name} media shows`).toBeGreaterThan(120);
  for (const id of ['piece-ask', 'piece-reveal']) {
    const b = view.getByTestId(id);
    await expect(b).toBeVisible();
    const r = await b.boundingBox();
    inside(`${name} ${id}`, r, box!);
    inside(`${name} ${id}`, r, win);
    const top = await page.evaluate(([x, y, tid]) => !!document.elementFromPoint(x, y)?.closest(`[data-testid=${tid}]`), [r!.x + r!.width / 2, r!.y + r!.height / 2, id] as const);
    expect(top, `${name} ${id} on top`).toBe(true);
  }
}

const tiles = () => page.locator('[data-testid=work-piece]');
const shown = () => page.getByTestId('piece-view').getAttribute('data-path');

test('on the run page a piece opens over the whole window and fits it, at 1280x720 and 1440x900', async () => {
  test.setTimeout(300000);
  await hash('#/studio');
  const pr = page.locator(`[data-testid=studio-row][data-row="${fresh}/main"]`);
  await expect(pr).toHaveAttribute('data-group', 'run', { timeout: 60000 });
  await pr.click();
  await api(`/api/history/item/${encodeURIComponent(fresh)}/resume`, {});
  const run = page.locator('[data-testid=hub-project][data-run=project]');
  await expect(run).toBeVisible({ timeout: 60000 });
  await expect(page.getByTestId('live-split')).toBeVisible(); // the Live pane docked under the page
  const sheet = page.locator('[data-testid=work-piece][data-stage=sheets]').first();
  const seg = page.locator('[data-testid=work-piece][data-stage=render][data-kind=videos]').first();
  await expect(sheet).toBeVisible({ timeout: 90000 });
  await expect(seg).toBeVisible({ timeout: 120000 });
  for (const s of SIZES) {
    await page.setViewportSize(s);
    const tag = `${s.width}x${s.height}`;
    await sheet.click();
    await fits(`run-${tag}-sheet`);
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('piece-view')).toHaveCount(0);
    await seg.click();
    await fits(`run-${tag}-segment-16x9`);
    // a click outside the box closes it
    await page.mouse.click(4, s.height - 4);
    await expect(page.getByTestId('piece-view')).toHaveCount(0);
  }
  // ← → step between the pieces (a video's own frame steps are Shift ← → and its buttons)
  await page.setViewportSize(SIZES[1]);
  await tiles().first().click();
  const first = await shown();
  await page.keyboard.press('ArrowRight');
  await expect.poll(shown).not.toBe(first);
  await expect(page.getByTestId('piece-pos')).toContainText('2 /');
  await page.keyboard.press('ArrowLeft');
  await expect.poll(shown).toBe(first);
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('piece-view')).toHaveCount(0);
  await api(`/api/history/item/${encodeURIComponent(fresh)}/stop`, {});
});

test('on a finished project a 9:16 and a 1:1 segment and a tall image fit the window too', async () => {
  test.setTimeout(120000);
  await hash(`#/p/${done}/clips`);
  await expect(page.getByTestId('project')).toBeVisible({ timeout: 30000 });
  const wp = page.getByTestId('work-pieces');
  await expect(wp).toHaveAttribute('data-live', '0', { timeout: 15000 });
  if ((await wp.getAttribute('open')) === null) await wp.locator('summary').click();
  const segs = page.locator('[data-testid=work-piece][data-stage=render][data-kind=videos]');
  const sheets = page.locator('[data-testid=work-piece][data-stage=sheets]');
  await expect(segs).toHaveCount(3);
  for (const s of SIZES) {
    await page.setViewportSize(s);
    const tag = `${s.width}x${s.height}`;
    for (const [name, tile] of [
      ['segment-9x16', segs.nth(1)],
      ['segment-1x1', segs.nth(2)],
      ['sheet-tall', sheets.nth(2)],
    ] as const) {
      await tile.scrollIntoViewIfNeeded();
      await tile.click();
      await fits(`done-${tag}-${name}`);
      await page.keyboard.press('Escape');
      await expect(page.getByTestId('piece-view')).toHaveCount(0);
    }
  }
});
