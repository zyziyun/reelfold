// Goal mode with the REAL engine sidecar (no mock engine; no AI: the engines' rule planners), isolated temp profile,
// window hidden, the Studio on. Her own request ("make several videos from my DJI card, each with its own theme") with
// a small DJI-like card (fixture/goal_card.py: three stories, DJI .SRT GPS, a panorama folder): the request becomes a
// goal - the footage is surveyed into stories and a plan card of videos waits for her (Settings: ask me first) - she
// renames one, drops and keeps one, merges two, makes them, and the group shows each video's own progress in the
// Studio list, on its run page and on Home, until every video is made; the summary lists each video's files per
// platform and its post.
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

let app: ElectronApplication;
let page: Page;
let card = '';
let gid = '';
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-goal-'));
const profile = path.join(tmp, 'profile');
const REPO = path.resolve(import.meta.dirname, '../../../..');
const SHOTS = process.env.GOAL_SHOTS_DIR ?? path.resolve(import.meta.dirname, '../../test-results/goal');
fs.mkdirSync(SHOTS, { recursive: true });
const engineEnv = {
  VSTUDIO_HOME: path.join(tmp, 'vhome'),
  VSTUDIO_CACHE: path.join(tmp, 'cache'),
  VSTUDIO_BATCH_BENCH: path.join(tmp, 'bench.json'),
  VSTUDIO_DEFAULT_PERSONA: '1',
  VSTUDIO_LLM_PROVIDER: 'none',
  DESK_GOAL_PARALLEL: '2',
  ...Object.fromEntries(['SEGMENT_PLAN', 'PROOFREAD', 'GLOSSARY', 'COPY', 'SCRIPT', 'PLANNER', 'INTAKE', 'OUTPUT_EDIT'].map((t) => [`VSTUDIO_LLM_${t}_PROVIDER`, 'none'])),
};

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  test.setTimeout(300000);
  const env: NodeJS.ProcessEnv = { ...process.env, ...engineEnv, PYTHONPATH: path.join(REPO, 'lib') };
  for (const k of ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'VSTUDIO_PERSONA']) delete env[k];
  const out = execFileSync(process.env.DESK_PYTHON || 'python3', [path.join(import.meta.dirname, 'fixture/goal_card.py'), tmp], { env, encoding: 'utf8', timeout: 240000 });
  card = JSON.parse(out.trim().split('\n').pop()!).card;
  app = await electron.launch({
    args: [path.resolve(import.meta.dirname, '../..')],
    env: {
      ...env,
      PYTHONPATH: '',
      DESK_STUDIO: '1',
      DESK_ENGINE_MOCK: '',
      DESK_USER_DATA: profile,
      DESK_HISTORY_WATCH: '',
      DESK_HIDE_WINDOW: '1',
      DESK_SHARED_CACHE: path.join(tmp, 'shared-cache'),
      DESK_HF_HUB: '',
      DESK_SKIP_FIRST_RUN: '1',
      VITE_DEV_SERVER_URL: '',
    },
  });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.waitForURL(/^app:\/\/desk\//);
  await page.evaluate(async () => {
    localStorage.setItem('i18n.strict', '1');
    // ask me first: the plan card waits for her (on autopilot it is approved the moment it is ready)
    await window.desk.setSettings({ lang: 'en', autopilot: false, defaultPlatforms: ['youtube', 'xiaohongshu'] });
  });
  await page.reload();
  await page.waitForURL(/^app:\/\/desk\//);
  expect((await page.evaluate(() => window.desk.engineInfo())).mode).toBe('real');
});

test.afterAll(async () => {
  await closeApp(app);
});

const hash = (h: string) => page.evaluate((x) => (location.hash = x), h);
const shot = (name: string) => page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
function api<T>(p: string, body?: unknown): Promise<T> {
  return page.evaluate(
    async ([u, b]) => {
      const info = await window.desk.engineInfo();
      const r = await fetch(info.baseUrl + u, {
        method: b === undefined ? 'GET' : 'POST',
        headers: { Authorization: `Bearer ${info.token}`, 'Content-Type': 'application/json' },
        body: b === undefined ? undefined : JSON.stringify(b),
      });
      return r.json();
    },
    [p, body] as const,
  ) as Promise<T>;
}

type G = { id: string; state: string; counts: { total: number; made: number; dropped: number }; videos: { id: string; title: string; state: string; intake?: string | null; projects?: { item: string }[]; versions?: { lang?: string | null; state: string; item?: string }[] | null }[] };

/** Her DJI goal (2026-10-13): the group is the one place its videos are followed - none of its requests / projects /
 * language versions is a loose row of the list (in any group), and none of their steps autopilot answers is in the
 * Inbox. */
async function onlyInTheGroup(g: G) {
  const items = g.videos.flatMap((v) => (v.projects ?? []).map((p) => p.item));
  for (const it of items) await expect(page.locator(`[data-testid^=studio-group-] [data-row^="${it}"]`)).toHaveCount(0);
  for (const v of g.videos) if (v.intake) await expect(page.locator(`[data-testid^=studio-group-] [data-row="r:${v.intake}"]`)).toHaveCount(0);
  const inbox = await api<{ items: { project: { id: string | null } }[] }>('/api/inbox');
  const waiting = new Set(g.videos.filter((v) => v.state === 'you').flatMap((v) => (v.projects ?? []).map((p) => p.item)));
  expect(inbox.items.filter((x) => x.project.id && items.includes(x.project.id) && !waiting.has(x.project.id))).toEqual([]);
}

test('her request becomes a goal: the footage is surveyed into stories and a plan card of videos waits', async () => {
  test.setTimeout(240000);
  await hash('#/');
  await expect(page.getByTestId('home')).toBeVisible({ timeout: 30000 });
  const hers = `在尝试帮我做多个dji航拍视频的剪辑吧，在${card}，可以先归纳一下，然后几个类似的做视频，可以尝试并行做多个视频，每个视频的主题可以不同，如果素材比较有内容，可以尝试介绍这个地方，做个history的介绍，如果素材就是好看，可以尝试一些高端的鸡汤文或者就是配乐也可，我可以发视频（youtube和小红书以及B站）`;
  await page.getByTestId('composer-input').fill(hers);
  await expect(page.getByTestId('composer-many')).toBeVisible();
  await page.getByTestId('make-plan').click();
  await expect(page.getByText('Reading your footage to plan several videos')).toBeVisible({ timeout: 15000 });
  await expect.poll(async () => (await api<{ goals: G[] }>('/api/goals')).goals.length, { timeout: 15000 }).toBe(1);
  gid = (await api<{ goals: G[] }>('/api/goals')).goals[0].id;
  // the request is not also a plain request
  expect((await api<{ items: unknown[] }>('/api/intake/open')).items).toHaveLength(0);
  await hash(`#/studio?goal=${gid}`);
  const pg = page.getByTestId('goal-page');
  await expect(pg).toBeVisible({ timeout: 20000 });
  await expect(pg).toHaveAttribute('data-state', 'planned', { timeout: 180000 });
  await expect(page.getByTestId('goal-title')).toHaveText('As many videos as the footage supports, each with its own theme');
  await expect(page.getByTestId('goal-found')).toContainText('6 clips · 0 photos · 2 days · 1 panorama · 4 stories');
  await expect(page.getByTestId('goal-rules-note')).toBeVisible();
  const cards = page.getByTestId('goal-plan-video');
  await expect(cards).toHaveCount(3);
  await expect(cards.nth(0).getByTestId('goal-plan-where')).toContainText('Seattle');
  await expect(page.getByTestId('goal-approve')).toHaveText('Make these 3 videos');
  await expect(page.getByTestId('goal-story')).toHaveCount(4);
  // the plan waits in the Inbox too
  await expect.poll(async () => (await api<{ items: { code?: string }[] }>('/api/inbox')).items.some((x) => x.code === 'goal.inbox')).toBe(true);
  // the group heads the Studio list
  await expect(page.getByTestId('studio-goal')).toHaveAttribute('data-state', 'planned');
  await shot('01-plan-card');
});

test('she renames one, drops and keeps one, merges two and makes them', async () => {
  test.setTimeout(60000);
  const cards = page.getByTestId('goal-plan-video');
  const title = cards.nth(0).getByTestId('goal-plan-title');
  await title.fill('Night at the Space Needle');
  await title.press('Enter');
  await expect.poll(async () => (await api<G>(`/api/goals/${gid}`)).videos[0].title).toBe('Night at the Space Needle');
  // the card's request follows the edit (what the video's own plan starts from)
  expect((await api<{ videos: { request: string }[] }>(`/api/goals/${gid}`)).videos[0].request).toContain('Title: "Night at the Space Needle"');
  await cards.nth(2).getByTestId('goal-plan-drop').click();
  await expect(cards.nth(2)).toHaveAttribute('data-out', 'true');
  await expect(page.getByTestId('goal-approve')).toHaveText('Make these 2 videos');
  await shot('02-plan-dropped');
  await cards.nth(2).getByTestId('goal-plan-keep').click();
  await expect(cards.nth(2)).not.toHaveAttribute('data-out', 'true');
  await expect(page.getByTestId('goal-approve')).toHaveText('Make these 3 videos');
  // noon and after dark at the same spot: one video
  await cards.nth(1).getByTestId('goal-plan-pick').check();
  await cards.nth(2).getByTestId('goal-plan-pick').check();
  await page.getByTestId('goal-merge').click();
  await expect(cards.nth(2)).toHaveAttribute('data-out', 'true');
  await expect(cards.nth(2).getByTestId('goal-plan-out')).toContainText('Merged into');
  await expect(cards.nth(1).getByTestId('goal-plan-where')).toContainText('4 clips');
  await expect(page.getByTestId('goal-approve')).toHaveText('Make these 2 videos');
  await shot('02-plan-edited');
  await page.getByTestId('goal-approve').click();
  await expect(page.getByTestId('goal-page')).toHaveAttribute('data-state', 'running', { timeout: 15000 });
  await expect(page.getByTestId('goal-video')).toHaveCount(2);
  await expect(page.getByTestId('goal-now')).toContainText('0 of 2 made');
});

test('the group shows each video’s own progress in the list, on its page and on Home', async () => {
  test.setTimeout(120000);
  const group = page.getByTestId('studio-goal');
  await expect(group.getByTestId('studio-goal-row')).toHaveCount(2);
  // both in flight at once (two at a time)
  await expect.poll(async () => (await api<G>(`/api/goals/${gid}`)).videos.filter((v) => v.state === 'planning' || v.state === 'making').length, { timeout: 30000 }).toBe(2);
  await expect(group.getByTestId('studio-goal-row').first()).toHaveAttribute('data-state', /planning|making|made/);
  // a video made in two languages (YouTube English, Xiaohongshu Chinese) is ONE row with its versions inside it
  await expect
    .poll(async () => (await api<G>(`/api/goals/${gid}`)).videos.some((v) => (v.versions ?? []).map((x) => x.lang).sort().join() === 'en,zh'), { timeout: 90000, intervals: [2000] })
    .toBe(true);
  await onlyInTheGroup(await api<G>(`/api/goals/${gid}`));
  await shot('03-running');
  await hash('#/');
  const card = page.getByTestId('home-goal');
  await expect(card).toBeVisible({ timeout: 20000 });
  await expect(card.getByTestId('home-goal-line')).toContainText(/of 2 made/);
  await expect(card.getByTestId('home-goal-video')).toHaveCount(2);
  // its jobs are inside the card, not repeated as cards of their own
  await expect(page.getByTestId('live-row')).toHaveCount(0);
  await shot('04-home-running');
});

test('every video is made: the goal finishes with what was made per platform and its post', async () => {
  test.setTimeout(600000);
  await expect.poll(async () => (await api<G>(`/api/goals/${gid}`)).state, { timeout: 540000, intervals: [3000] }).toBe('done');
  const g = await api<G>(`/api/goals/${gid}`);
  expect(g.counts.made + g.counts.dropped).toBe(2);
  expect(g.counts.made).toBe(2);
  await hash(`#/studio?goal=${gid}`);
  await expect(page.getByTestId('goal-page')).toHaveAttribute('data-state', 'done', { timeout: 20000 });
  await expect(page.getByTestId('goal-now')).toContainText('2 of 2 made');
  const made = page.getByTestId('goal-made');
  await expect(made).toHaveCount(2);
  await expect(made.first().getByTestId('goal-made-file').first()).toBeVisible({ timeout: 30000 });
  expect(await made.first().getByTestId('goal-made-file').count()).toBeGreaterThanOrEqual(2); // one per platform
  // every made file names its platform and its size, never "None 原尺寸" (her DJI goal's photo stories, 2026-10-13)
  for (const f of await page.getByTestId('goal-made-file').all()) {
    await expect(f).not.toContainText('None');
    await expect(f).toContainText(/\d+×\d+/);
  }
  await expect(made.first().getByTestId('goal-made-post').first()).toBeVisible(); // one per version (a language each)
  // the made projects sit in the group, not twice in Ready to post
  const items = g.videos.flatMap((v) => (v.projects ?? []).map((p) => p.item));
  expect(items.length).toBeGreaterThanOrEqual(2);
  await expect(page.getByTestId('studio-goal').getByTestId('studio-goal-row')).toHaveCount(2);
  for (const it of items) await expect(page.locator(`[data-testid=studio-group-ready] [data-row^="${it}"]`)).toHaveCount(0);
  await onlyInTheGroup(g);
  await shot('05-done-summary');
  // a row opens its video
  await page.getByTestId('studio-goal').getByTestId('studio-goal-row').first().click();
  await expect(page).toHaveURL(new RegExp(`#/studio/${items[0]}`));
  await expect(page.getByTestId('studio-page')).toBeVisible();
  await shot('06-video-opened');
});

test('the same page in Chinese and French', async () => {
  test.setTimeout(60000);
  for (const [lang, name, word] of [['zh-CN', '07-done-zh', '已做好 2/2'], ['fr', '08-done-fr', '2 sur 2 faites']] as const) {
    await page.evaluate(async (l) => window.desk.setSettings({ lang: l }), lang);
    await page.reload();
    await page.waitForURL(/^app:\/\/desk\//);
    await hash(`#/studio?goal=${gid}`);
    await expect(page.getByTestId('goal-now')).toContainText(word, { timeout: 20000 });
    await expect(page.locator('body')).not.toContainText('⟦');
    await shot(name);
  }
  await page.evaluate(async () => window.desk.setSettings({ lang: 'en' }));
});
