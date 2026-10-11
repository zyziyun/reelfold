// The project page with the REAL engine (2026-10-11, her "Seattle Red Leaves Film" read "Ready · not scheduled" with
// the step bar short of the end, "0 of 1 ready", an empty "Ready" tile, "Not started" under In progress, no chat, and
// no way into the editor). Two travel vlogs on tiny synthetic clips with no audio (fixture/vlog_pages_project.py, the vlog
// recipe on autopilot, no AI account): one made before the app starts, one the app starts and we watch.
//   * a finished vlog is Ready to post with its cover, 1 clip made; clicking it opens the editor, timeline first (no
//     words); an export version opens the same clip on that version
//   * while one is made its pieces show up as they appear (contact sheets, graded segments, the master...)
//   * the project chat is on the running page, the ready project's details and the clip page, and it acts: it pauses
//     the run and runs it on
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
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-projectpage-'));
const REPO = path.resolve(import.meta.dirname, '../../../..');
const SHOTS = process.env.DESK_SHOTS_DIR ?? path.resolve(import.meta.dirname, '../../test-results/project-page');
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

type Hist = { items: { id: string; dir: string; stopped?: number; status?: string; thumb?: string | null; live?: { state?: string } | null }[] };

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  test.setTimeout(300000);
  const env: NodeJS.ProcessEnv = { ...process.env, ...engineEnv, PYTHONPATH: path.join(REPO, 'lib') };
  for (const k of ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'VSTUDIO_PERSONA']) delete env[k];
  const out = execFileSync(process.env.DESK_PYTHON || 'python3', [path.join(import.meta.dirname, 'fixture/vlog_pages_project.py'), tmp, '--fresh-secs', '24'], { env, encoding: 'utf8' });
  const fx = JSON.parse(out.trim().split('\n').pop()!) as { done: { dir: string; status: string; pending: unknown[] }; fresh: { dir: string } };
  expect([fx.done.status, fx.done.pending]).toEqual(['done', []]);
  dirs.done = fx.done.dir;
  dirs.fresh = fx.fresh.dir;
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
const row = (key: string) => page.locator(`[data-testid=studio-row][data-row="${key}"]`);
const noMissingWords = () => expect(page.locator('body')).not.toContainText('⟦');

test('a finished vlog is Ready to post with its cover; it opens in the editor, timeline first', async () => {
  test.setTimeout(120000);
  await hash('#/studio');
  await expect(page.getByTestId('studio')).toBeVisible({ timeout: 30000 });
  const r = row(`${done}/main`);
  await expect(r).toHaveAttribute('data-group', 'ready', { timeout: 60000 });
  await expect(r).toHaveAttribute('data-tone', 'done');
  await expect(page.getByTestId('studio-group-ready')).toContainText('Ready to post');
  await expect(r.locator('.st-th img')).toHaveAttribute('src', /cover/);
  await expect(r).not.toContainText('Not started');
  const h = (await api<Hist>('/api/history')).items.find((i) => i.id === done)!;
  expect(h.status).toBe('done');
  expect(h.thumb).toMatch(/exports[/\\].*cover.*\.jpg$/);
  // 1 of 1 made: the clip has its files, its cover and its length
  const cl = await api<{ clips: { id: string; files: { aspect: string }[]; cover: string | null; duration: number | null }[] }>(`/api/outputs/${done}`);
  expect(cl.clips.map((c) => [c.id, c.files.map((f) => f.aspect).sort(), !!c.cover, (c.duration ?? 0) > 1])).toEqual([['main', ['16:9', '9:16'], true, true]]);
  await r.click();
  await expect(page.getByTestId('editor')).toHaveAttribute('data-layout', 'studio', { timeout: 30000 });
  await expect(page.getByTestId('lower-pane')).toHaveAttribute('data-tab', 'timeline'); // no speech: the timeline first
  await expect(page.getByTestId('editor-player')).toBeVisible();
  await noMissingWords();
  await shot('P1-ready-clip-opens-editor');
});

test('the details page: Ready to post, 1 clip, the chat beside it; a version opens the clip on that version', async () => {
  test.setTimeout(120000);
  await hash(`#/p/${done}/clips`);
  await expect(page.getByTestId('project')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('tab-clips')).toContainText('1');
  await expect(page.locator('[data-testid=project] [data-testid=status]').first()).toHaveText('Ready to post');
  const card = page.locator('[data-testid=clip-card][data-clip=main]');
  await expect(card).toHaveAttribute('data-state', 'done');
  await expect(card.locator('img')).toBeVisible();
  // the chat is back on Details
  await expect(page.getByTestId('project-chat')).toBeVisible();
  await expect(page.getByTestId('project-chat-split')).toBeVisible();
  // "how it was made": the pieces, folded once it is done
  await expect(page.getByTestId('work-pieces')).toHaveAttribute('data-live', '0', { timeout: 15000 });
  await noMissingWords();
  await shot('P2-details-chat');
  // the chat folds to its edge and opens again
  await page.getByTestId('project-chat-fold').click();
  await expect(page.getByTestId('project-chat')).toHaveCount(0);
  await page.getByTestId('project-chat-open').click();
  await expect(page.getByTestId('project-chat')).toBeVisible();
  // a version chip opens the clip in the editor on that version
  await card.getByTestId('clip-size-9:16').click();
  await expect(page.getByTestId('editor')).toBeVisible({ timeout: 30000 });
  expect(await page.evaluate(() => decodeURIComponent(location.hash))).toMatch(/[?&]v=9:16/);
  await expect(page.locator('[data-testid=editor] [data-testid="size-9:16"]').first()).toHaveClass(/\bon\b/);
  // the clip page has its own chat (this clip / all clips)
  await page.getByTestId('studio-ai-toggle').click();
  await expect(page.getByTestId('studio-ai-pane')).toBeVisible();
  await shot('P3-version-opens-editor-clip-chat');
  await page.getByTestId('studio-ai-close').click();
});

test('while a vlog is made its pieces show up as they appear; the chat pauses it and runs it on', async () => {
  test.setTimeout(300000);
  await hash('#/studio');
  const pr = row(`${fresh}/main`);
  await expect(pr).toHaveAttribute('data-group', 'run', { timeout: 60000 });
  await expect(pr).toContainText('Not started');
  await pr.click();
  await expect(page.getByTestId('project-chat')).toBeVisible({ timeout: 30000 }); // not started yet: the chat is there
  await api(`/api/history/item/${fresh}/resume`, {});
  // the run page: its pieces in recipe order, updating while it runs
  const run = page.locator('[data-testid=hub-project][data-run=project]');
  await expect(run).toBeVisible({ timeout: 60000 });
  await expect(page.getByTestId('project-chat')).toBeVisible();
  const wp = page.getByTestId('work-pieces');
  await expect(wp).toHaveAttribute('data-live', '1', { timeout: 60000 });
  await expect(page.locator('[data-testid=work-piece][data-stage=sheets]').first()).toBeVisible({ timeout: 60000 });
  await expect(page.locator('[data-testid=work-piece]').first()).toHaveAttribute('data-stage', 'sheets');
  await expect(page.locator('[data-testid=work-piece][data-stage=render]').first()).toBeVisible({ timeout: 90000 });
  await expect(run).toBeVisible(); // still being made
  await expect(page.locator('[data-testid=work-piece][data-stage=render][data-kind=videos]').first()).toContainText(/Graded segment \d/);
  await noMissingWords();
  await shot('P4-running-pieces-chat');
  // a piece opens big, with "Ask AI about this" (the chat, her words started)
  await page.locator('[data-testid=work-piece][data-stage=sheets]').first().click();
  await expect(page.getByTestId('piece-actions')).toBeVisible();
  await shot('P5-piece-open');
  await page.getByTestId('piece-ask').click();
  await expect(page.locator('[data-testid=project-chat] [data-testid=ai-input]')).toHaveValue(/Contact sheet 1/);
  // the chat acts on the run: pause it ...
  const input = page.locator('[data-testid=project-chat] [data-testid=ai-input]');
  await input.fill('pause it');
  await input.press('Enter');
  const stop = page.locator('[data-testid=project-chat] [data-testid=pai-project-action][data-kind=stop]');
  await expect(stop).toBeVisible({ timeout: 15000 });
  await stop.click();
  await expect.poll(async () => !!(await api<Hist>('/api/history')).items.find((i) => i.id === fresh)?.stopped, { timeout: 30000 }).toBe(true);
  await shot('P6-chat-paused');
  // ... and run it on
  await input.fill('继续');
  await input.press('Enter');
  const go = page.locator('[data-testid=project-chat] [data-testid=pai-project-action][data-kind=resume]');
  await expect(go).toBeVisible({ timeout: 15000 });
  await go.click();
  await expect
    .poll(async () => (await api<Hist>('/api/history')).items.find((i) => i.id === fresh)?.live?.state, { timeout: 240000, intervals: [2000] })
    .toBe('done');
  await hash('#/studio');
  await expect(row(`${fresh}/main`)).toHaveAttribute('data-group', 'ready', { timeout: 60000 });
});
