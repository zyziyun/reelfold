// Runs the app with the Studio off (DESK_STUDIO=0): the pages before the Studio (2026-10 review step 7) stay
// supported behind its flag, and this spec covers them.
// The clip's info inline in the editor (2026-10 review step 5) with the REAL engine sidecar (no mock engine), isolated
// temp profile, window hidden. A talking-head project (fixture/real_project.py: synthetic tone-burst talk + the engine
// tests' fake transcriber) runs on autopilot to the end, then in its clip editor, on one screen:
//   cover (one click on a frame) -> the clip re-renders by itself with progress, and the listing that publishing reads
//   now has the edit's cover and file; caption look; schedule at the next free slot (one click); the copy per platform
//   (the publish drawer's component, same rows). Clicks for "copy + cover + schedule" are counted (with the title:
//   the header title, one more).
import { _electron as electron, expect, test, type ElectronApplication, type Locator, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

let app: ElectronApplication;
let page: Page;
let project = '';
let id = '';
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-clipinfo-'));
const REPO = path.resolve(import.meta.dirname, '../../../..');
const FIXTURE = path.join(import.meta.dirname, 'fixture');
const SHOTS = process.env.DESK_SHOTS_DIR ?? path.resolve(import.meta.dirname, '../../test-results/clip-info');
fs.mkdirSync(SHOTS, { recursive: true });
const engineEnv = {
  VSTUDIO_HOME: path.join(tmp, 'vhome'),
  VSTUDIO_BATCH_BENCH: path.join(tmp, 'bench.json'),
  VSTUDIO_DEFAULT_PERSONA: '1',
  VSTUDIO_TEST_TRUTH: path.join(tmp, 'truth.json'),
  VSTUDIO_LLM_PROVIDER: 'none',
  ...Object.fromEntries(['SEGMENT_PLAN', 'PROOFREAD', 'GLOSSARY', 'COPY', 'SCRIPT', 'PLANNER', 'INTAKE', 'OUTPUT_EDIT'].map((t) => [`VSTUDIO_LLM_${t}_PROVIDER`, 'none'])),
};

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  test.setTimeout(300000);
  const env: NodeJS.ProcessEnv = { ...process.env, ...engineEnv, PYTHONPATH: path.join(REPO, 'lib') };
  for (const k of ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'VSTUDIO_PERSONA']) delete env[k];
  const out = execFileSync(process.env.DESK_PYTHON || 'python3', [path.join(FIXTURE, 'real_project.py'), tmp, '--autopilot'], { env, encoding: 'utf8' });
  const fx = JSON.parse(out.trim().split('\n').pop()!) as { dir: string; status: string };
  expect(fx.status).toBe('done');
  project = fx.dir;
  app = await electron.launch({
    args: [path.resolve(import.meta.dirname, '../..')],
    env: { ...env, PYTHONPATH: '', DESK_ENGINE_MOCK: '', DESK_USER_DATA: path.join(tmp, 'profile'), DESK_HISTORY_WATCH: '', DESK_STUDIO: '0', DESK_HIDE_WINDOW: '1', DESK_SHARED_CACHE: path.join(tmp, 'cache'), DESK_HF_HUB: '', DESK_SKIP_FIRST_RUN: '1', VITE_DEV_SERVER_URL: '' },
  });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForURL(/^app:\/\/desk\//);
  await page.evaluate(async () => {
    localStorage.setItem('i18n.strict', '1');
    await window.desk.setSettings({ lang: 'en', defaultPlatforms: ['xiaohongshu', 'youtube', 'tiktok'] });
  });
  await page.reload();
  await page.waitForURL(/^app:\/\/desk\//);
  expect((await page.evaluate(() => window.desk.engineInfo())).mode).toBe('real');
  await expect
    .poll(async () => (await api<{ items: { id: string; dir: string }[] }>('/api/history')).items.find((i) => fs.realpathSync(i.dir) === fs.realpathSync(project))?.id ?? '', { timeout: 60000 })
    .not.toBe('');
  id = (await api<{ items: { id: string; dir: string }[] }>('/api/history')).items.find((i) => fs.realpathSync(i.dir) === fs.realpathSync(project))!.id;
});

test.afterAll(async () => {
  await closeApp(app);
});

const hash = (h: string) => page.evaluate((x) => (location.hash = x), h);
const shot = (name: string) => page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
async function api<T>(p: string, body?: unknown): Promise<T> {
  return page.evaluate(
    async ([u, b]) => {
      const info = await window.desk.engineInfo();
      const r = await fetch(info.baseUrl + u, { method: b ? 'POST' : 'GET', headers: { Authorization: `Bearer ${info.token}`, 'Content-Type': 'application/json' }, body: b ? JSON.stringify(b) : undefined });
      return r.json();
    },
    [p, body] as const,
  ) as Promise<T>;
}
let clicks = 0;
const click = async (l: Locator) => {
  clicks++;
  await l.click();
};

test('cover, captions, schedule and copy on the clip editor; the clip re-renders by itself and goes out edited', async () => {
  test.setTimeout(300000);
  await hash(`#/p/${id}/clip/talk`);
  await expect(page.getByTestId('editor')).toBeVisible({ timeout: 60000 });
  const info = page.getByTestId('clip-info');
  await expect(info).toBeVisible();
  await expect(info.getByTestId('ci-cover').first()).toBeVisible({ timeout: 30000 }); // frames from the filmstrip
  await shot('B1-clip-info');
  const before = await api<{ clips: { id: string; cover: string | null; files: { path: string }[]; edited?: boolean }[] }>(`/api/outputs/${id}`);
  const orig = before.clips.find((c) => c.id === 'talk')!;
  expect(orig.edited).toBeFalsy();

  // cover: one click on a frame -> saved -> the clip re-renders by itself, with progress
  await click(info.getByTestId('ci-cover').nth(1));
  await expect(page.getByTestId('ci-render')).toBeVisible({ timeout: 15000 });
  await expect(page.getByTestId('ci-render')).toHaveAttribute('data-phase', /waiting|running/);
  await shot('B2-rendering');
  await expect(page.getByTestId('ci-render')).toHaveAttribute('data-phase', 'done', { timeout: 180000 });
  // what goes out is the edit: the listing publishing reads has the rendered file and cover
  const after = await api<typeof before>(`/api/outputs/${id}`);
  const ed = after.clips.find((c) => c.id === 'talk')!;
  expect(ed.edited).toBe(true);
  expect(ed.files[0].path).toContain(`${path.sep}renders${path.sep}`);
  expect(ed.cover).toContain(`${path.sep}renders${path.sep}`);

  // caption look: one click, the style is saved
  await info.getByTestId('ci-look-box').click();
  await expect(info.getByTestId('ci-look-box')).toHaveAttribute('aria-pressed', 'true', { timeout: 15000 });

  // schedule: her platforms are on, one click at the next free slot (international first)
  const sched = info.getByTestId('ci-schedule');
  await expect(sched).toHaveAttribute('data-state', 'unscheduled');
  await expect(sched.getByTestId('ci-pf').first()).toHaveAttribute('data-pf', 'youtube');
  await click(sched.getByTestId('ci-schedule-btn'));
  await expect(sched).toHaveAttribute('data-state', 'scheduled', { timeout: 15000 });
  const cal = await api<{ posts: { item: string; clip: string; platform: string }[] }>('/api/calendar');
  expect(cal.posts.filter((p) => p.item === id && p.clip === 'talk').map((p) => p.platform.split(':')[0]).sort()).toEqual(['tiktok', 'xiaohongshu', 'youtube']);

  // the copy per platform: the publish drawer's component on the same rows
  await expect(sched.getByTestId('pb-ctab').first()).toHaveAttribute('data-pf', 'youtube');
  const cap = sched.getByTestId('pb-caption');
  await click(cap);
  await cap.fill('One recording, a week of posts. #creator');
  await expect
    .poll(async () => (await api<{ posts: { item: string; clip: string; platform: string; caption: string }[] }>('/api/calendar')).posts.find((p) => p.item === id && p.platform.startsWith('youtube'))?.caption, { timeout: 15000 })
    .toBe('One recording, a week of posts. #creator');
  // the title, in the header of the same screen: one click, type, Enter - every platform's title follows
  await click(page.getByTestId('editor-title-edit'));
  await page.getByTestId('editor-title-input').fill('One recording, a week of posts');
  await page.getByTestId('editor-title-input').press('Enter');
  await expect(page.getByTestId('editor-title')).toHaveText('One recording, a week of posts');
  await expect
    .poll(async () => (await api<{ posts: { item: string; clip: string; title: string }[] }>('/api/calendar')).posts.filter((p) => p.item === id && p.clip === 'talk').map((p) => p.title), { timeout: 15000 })
    .toEqual(['One recording, a week of posts', 'One recording, a week of posts', 'One recording, a week of posts']);
  await shot('B3-scheduled-copy');
  // title + copy + cover + schedule: 4 clicks on one screen (the review measured 14+ over 4 screens before)
  expect(clicks).toBe(4);
  fs.writeFileSync(path.join(SHOTS, 'clicks.json'), JSON.stringify({ title_copy_cover_schedule: clicks, screens: 1 }));
});

// An AI edit renders the clip again into the SAME file (renders/primary.final.mp4, replaced in place): the edited
// version must play after each render - the player loads the new file (a versioned URL: Chromium keeps a URL's media
// bytes for minutes and mixed the old file into the new one -> "This file can't be played here").
test('after an AI edit re-renders the clip, the edited version plays (no stale media, no error)', async () => {
  test.setTimeout(300000);
  const player = page.getByTestId('editor-player');
  const video = player.getByTestId('player-video');
  await page.getByTestId('tab-timeline').click();
  type Doc = { renders: { target: string; quality?: string; fresh?: boolean; at?: string; duration?: number }[] };
  const final = (d: Doc) => d.renders.find((r) => r.target === 'primary' && r.quality === 'final' && r.fresh);
  const playsEdited = async () => {
    await expect(video).toHaveAttribute('src', /(%2F|%5C)renders(%2F|%5C)primary\.final\.mp4/, { timeout: 30000 });
    // the file on disk, not what the player cached of the one it replaced
    const want = final(await api<Doc>(`/api/outputs/${id}/talk`))!.duration!;
    await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.duration), { timeout: 20000 }).toBeCloseTo(want, 1);
    const t0 = await video.evaluate((v: HTMLVideoElement) => ((v.muted = true), v.currentTime));
    await player.getByTestId('player-play').click();
    await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.currentTime), { timeout: 20000 }).toBeGreaterThan(t0 + 0.5);
    expect(await video.evaluate((v: HTMLVideoElement) => v.error?.code ?? 0)).toBe(0);
    await expect(player.getByText('This file can’t be played here.')).toHaveCount(0);
    await player.getByTestId('player-play').click(); // pause
  };
  await playsEdited();
  const fresh = (d: Doc) => final(d)?.at ?? '';
  const at0 = fresh(await api<Doc>(`/api/outputs/${id}/talk`));
  expect(at0).not.toBe('');
  // the AI's change (what the clip chat applies): faster -> a new, shorter final render at the same path
  await api(`/api/outputs/${id}/talk/edit`, { ops: [{ op: 'speed', value: 1.25 }], by: 'ai', note: 'test' });
  await expect
    .poll(async () => {
      const at = fresh(await api<Doc>(`/api/outputs/${id}/talk`));
      return at && at !== at0;
    }, { timeout: 180000 })
    .toBe(true);
  await expect(page.getByTestId('ci-render')).toHaveAttribute('data-phase', 'done', { timeout: 60000 });
  await playsEdited();
  await shot('B4-edited-plays');
  // its cover is written again in place too (renders/primary.final.cover.jpg): listed with the render's key, and the
  // project's clip tile loads it under that key (never the cover Chromium cached for the same path)
  type Clips = { clips: { id: string; cover: string | null; cover_v?: string | null }[] };
  const c = (await api<Clips>(`/api/outputs/${id}`)).clips.find((x) => x.id === 'talk')!;
  expect(c.cover).toMatch(/renders\/.*cover\.jpg$/);
  expect(c.cover_v).toBeTruthy();
  await hash(`#/p/${id}`);
  await expect(page.locator(`img[src*="v=${encodeURIComponent(c.cover_v!)}"]`).first()).toBeAttached({ timeout: 30000 });
});
