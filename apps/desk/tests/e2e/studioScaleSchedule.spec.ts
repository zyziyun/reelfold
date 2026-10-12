// All projects' bulk Schedule at scale with the REAL engine sidecar (no mock engine), isolated temp profile, window
// hidden, the Studio on: 210 made videos (fixture/many_made.py: one talk made by the real engine, copied as 210 past
// projects). Found while capturing the 0.2.7 promo on 230 projects: "Schedule · 123" never finished (no toast, the
// page stuck on its skeleton, thumbnails black) and its count did not match "Ready to post 216" - the engine's
// threads hung on the run stores' opens / closes, a third of the per-project requests were refused (a full socket
// backlog) and the bulk asked each project for its clips again, one after another. Each step is timed and written
// to schedule-perf.json next to the shots.
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

const N = 210;
let app: ElectronApplication;
let page: Page;
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-schedscale-'));
const REPO = path.resolve(import.meta.dirname, '../../../..');
const SHOTS = process.env.HOME_SHOTS_DIR ?? path.resolve(import.meta.dirname, '../../test-results/home');
fs.mkdirSync(SHOTS, { recursive: true });
const perf: Record<string, number> = {};

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  test.setTimeout(300000);
  const env: NodeJS.ProcessEnv = { ...process.env, VSTUDIO_HOME: path.join(tmp, 'vhome'), VSTUDIO_DEFAULT_PERSONA: '1', VSTUDIO_LLM_PROVIDER: 'none', PYTHONPATH: path.join(REPO, 'lib') };
  for (const k of ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'VSTUDIO_PERSONA']) delete env[k];
  const out = JSON.parse(execFileSync(process.env.DESK_PYTHON || 'python3', [path.join(import.meta.dirname, 'fixture/many_made.py'), tmp, String(N)], { env, encoding: 'utf8' }).trim().split('\n').pop()!);
  expect(out.n).toBe(N);
  app = await electron.launch({
    args: [path.resolve(import.meta.dirname, '../..')],
    env: { ...env, PYTHONPATH: '', DESK_STUDIO: '1', DESK_ENGINE_MOCK: '', DESK_USER_DATA: path.join(tmp, 'profile'), DESK_HISTORY_WATCH: '', DESK_HIDE_WINDOW: '1', DESK_SHARED_CACHE: path.join(tmp, 'cache'), DESK_HF_HUB: '', DESK_SKIP_FIRST_RUN: '1', VITE_DEV_SERVER_URL: '' },
  });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForURL(/^app:\/\/desk\//);
  await page.evaluate(async () => {
    localStorage.setItem('i18n.strict', '1');
    await window.desk.setSettings({ lang: 'en', defaultPlatforms: ['tiktok', 'youtube-shorts'] });
  });
  await page.reload();
  await page.waitForURL(/^app:\/\/desk\//);
  expect((await page.evaluate(() => window.desk.engineInfo())).mode).toBe('real');
});

test.afterAll(async () => {
  fs.writeFileSync(path.join(SHOTS, 'schedule-perf.json'), JSON.stringify({ videos: N, ms: perf }, null, 2));
  console.log(`Bulk Schedule of ${N} videos (ms):`, JSON.stringify(perf));
  await closeApp(app);
});

const api = <T,>(p: string) =>
  page.evaluate(async (u) => {
    const info = await window.desk.engineInfo();
    const r = await fetch(info.baseUrl + u, { headers: { Authorization: `Bearer ${info.token}` } });
    return r.json();
  }, p) as Promise<T>;

test(`${N} made videos: every one listed as a video, Ready to post ${N}, no project left as a bare row`, async () => {
  test.setTimeout(180000);
  const t0 = Date.now();
  await page.evaluate(() => (location.hash = '#/studio?f=ready'));
  await expect(page.getByTestId('studio-n-ready')).toHaveText(String(N), { timeout: 120000 });
  perf.listReady = Date.now() - t0;
  expect(perf.listReady).toBeLessThan(60000);
  await expect(page.locator('[data-testid=studio-row][data-kind=clip]')).toHaveCount(N);
  await expect(page.locator('[data-testid=studio-row][data-kind=project]')).toHaveCount(0);
  // 200+ projects' clips asked for in a few seconds: none refused by the engine, none shown as "no videos"
  const burst = await page.evaluate(async () => {
    const info = await window.desk.engineInfo();
    const h = (await (await fetch(info.baseUrl + '/api/history', { headers: { Authorization: `Bearer ${info.token}` } })).json()) as { items: { id: string }[] };
    const rs = await Promise.all(h.items.map((i) => fetch(info.baseUrl + `/api/outputs/${i.id}`, { headers: { Authorization: `Bearer ${info.token}` } }).then((r) => r.status)));
    return { n: rs.length, bad: rs.filter((s) => s !== 200).length };
  });
  expect(burst).toEqual({ n: N, bad: 0 });
});

test(`⌘A then Schedule: the button says ${N} (what Ready to post says), progress, one toast with Undo, every one scheduled`, async () => {
  test.setTimeout(180000);
  await page.getByTestId('studio-row').first().click();
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+a' : 'Control+a');
  const bar = page.getByTestId('studio-bulk');
  await expect(bar).toContainText(`${N} selected`);
  const btn = bar.getByTestId('studio-bulk-schedule');
  await expect(btn).toHaveText(`Schedule · ${N}`);
  const ms = await page.evaluate(async () => {
    const seen: string[] = [];
    const t0 = performance.now();
    document.querySelector<HTMLElement>('[data-testid=studio-bulk-schedule]')!.click();
    while (performance.now() - t0 < 60000) {
      const p = document.querySelector('[data-testid=studio-bulk-scheduling]')?.textContent;
      if (p && seen[seen.length - 1] !== p) seen.push(p);
      if ([...document.querySelectorAll('[data-testid=toast]')].some((x) => /Scheduled \d+ videos/.test(x.textContent ?? ''))) break;
      await new Promise((r) => requestAnimationFrame(r));
    }
    return { ms: performance.now() - t0, seen };
  });
  perf.bulkSchedule = Math.round(ms.ms);
  expect(ms.seen[0]).toMatch(new RegExp(`Scheduling \\d+ of ${N}`));
  expect(ms.ms).toBeLessThan(20000); // ~1 s on a quiet Mac (never finished before)
  const toast = page.getByTestId('toast').filter({ hasText: `Scheduled ${N} videos` });
  await expect(toast).toBeVisible();
  await expect(toast.getByTestId('toast-undo')).toBeVisible();
  await page.screenshot({ path: path.join(SHOTS, 'bulk-schedule-scale.png') });
  // one free day each, on the platforms each clip was made for
  const posts = (await api<{ posts: { item: string; clip: string; at: string }[] }>('/api/calendar?queue=0')).posts;
  const clips = new Set(posts.map((p) => `${p.item}/${p.clip}`));
  expect(clips.size).toBe(N);
  const days = new Map<string, Set<string>>();
  for (const p of posts) days.set(p.at.slice(0, 10), new Set([...(days.get(p.at.slice(0, 10)) ?? []), `${p.item}/${p.clip}`]));
  expect([...days.values()].every((s) => s.size === 1)).toBe(true);
  const t1 = Date.now();
  await expect(page.getByTestId('studio-n-scheduled')).toHaveText(String(N), { timeout: 30000 });
  perf.listScheduled = Date.now() - t1;
  await expect(page.getByTestId('studio-n-ready')).toHaveCount(0);
  // Undo takes every one of them off again, in one step
  const t2 = Date.now();
  await toast.getByTestId('toast-undo').click();
  await expect(page.getByTestId('studio-n-ready')).toHaveText(String(N), { timeout: 30000 });
  perf.undo = Date.now() - t2;
  expect((await api<{ posts: unknown[] }>('/api/calendar?queue=0')).posts).toHaveLength(0);
});
