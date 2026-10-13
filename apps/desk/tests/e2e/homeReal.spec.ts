// Home as triage with the REAL engine sidecar (no mock engine), isolated temp profile, window hidden, the Studio on.
// fixture/home_projects.py makes a small day of real work on tiny synthetic media (the engine tests' fake transcriber
// is the only fake): a clip parked at a filler question, a made clip with posts today (one posted, one filled in and
// waiting on Instagram), a failed script, a project an agent is cutting right now, a fresh recording in a watched
// folder and a request sent twice. Home lands first and shows each from that real data: the chips, the Inbox's top
// rows with one action each that settles them in place, what runs (opening its live page), what goes out today.
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

let app: ElectronApplication;
let page: Page;
let fx: { a: string; b: string; c: string; d: string; watch: string; recording: string };
const ids: Record<'a' | 'b' | 'c' | 'd', string> = { a: '', b: '', c: '', d: '' };
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-home-'));
const profile = path.join(tmp, 'profile');
const REPO = path.resolve(import.meta.dirname, '../../../..');
const SHOTS = process.env.HOME_SHOTS_DIR ?? path.resolve(import.meta.dirname, '../../test-results/home');
fs.mkdirSync(SHOTS, { recursive: true });
const engineEnv = {
  VSTUDIO_HOME: path.join(tmp, 'vhome'),
  VSTUDIO_BATCH_BENCH: path.join(tmp, 'bench.json'),
  VSTUDIO_DEFAULT_PERSONA: '1',
  VSTUDIO_LLM_PROVIDER: 'none',
  ...Object.fromEntries(['SEGMENT_PLAN', 'PROOFREAD', 'GLOSSARY', 'COPY', 'SCRIPT', 'PLANNER', 'INTAKE', 'OUTPUT_EDIT'].map((t) => [`VSTUDIO_LLM_${t}_PROVIDER`, 'none'])),
};

test.describe.configure({ mode: 'serial' });

const day = (h: string) => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}T${h}`;
};

test.beforeAll(async () => {
  test.setTimeout(400000);
  const env: NodeJS.ProcessEnv = { ...process.env, ...engineEnv, PYTHONPATH: path.join(REPO, 'lib') };
  for (const k of ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'VSTUDIO_PERSONA']) delete env[k];
  const out = execFileSync(process.env.DESK_PYTHON || 'python3', [path.join(import.meta.dirname, 'fixture/home_projects.py'), tmp, profile], { env, encoding: 'utf8', timeout: 300000 });
  fx = JSON.parse(out.trim().split('\n').pop()!);
  app = await electron.launch({
    args: [path.resolve(import.meta.dirname, '../..')],
    env: {
      ...env,
      VSTUDIO_TEST_TRUTH: path.join(tmp, 'a', 'truth.json'),
      PYTHONPATH: '',
      DESK_STUDIO: '1',
      DESK_ENGINE_MOCK: '',
      DESK_USER_DATA: profile,
      DESK_HISTORY_WATCH: fx.watch,
      DESK_HIDE_WINDOW: '1',
      DESK_SHARED_CACHE: path.join(tmp, 'cache'),
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
    await window.desk.setSettings({ lang: 'en', defaultPlatforms: ['tiktok', 'youtube-shorts'] });
  });
  await page.reload();
  await page.waitForURL(/^app:\/\/desk\//);
  expect((await page.evaluate(() => window.desk.engineInfo())).mode).toBe('real');
  const find = async (dir: string) => (await api<{ items: { id: string; dir: string }[] }>('/api/history')).items.find((i) => fs.realpathSync(i.dir) === fs.realpathSync(dir))?.id ?? '';
  for (const k of ['a', 'b', 'c', 'd'] as const) {
    await expect.poll(() => find(fx[k]), { timeout: 60000 }).not.toBe('');
    ids[k] = await find(fx[k]);
  }
  // today's posts for the made clip: TikTok went out this morning (with its views), Instagram is filled in and
  // waits for the platform this evening
  const made = await api<{ ok: boolean; posts: { id: string; platform: string }[] }>('/api/calendar/many', {
    posts: [
      { item: ids.b, clip: 'talk', platform: 'tiktok', at: day('09:00') },
      { item: ids.b, clip: 'talk', platform: 'instagram', at: day('18:30') },
    ],
  });
  expect(made.ok).toBe(true);
  const tiktok = made.posts.find((p) => p.platform.startsWith('tiktok'))!;
  const insta = made.posts.find((p) => p.platform.startsWith('instagram'))!;
  await api(`/api/calendar/${tiktok.id}`, { state: 'posted', stats: { views: 1240 }, via: 'manual' });
  await api(`/api/calendar/${insta.id}`, { state: 'filled' });
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

test('Home is where the app lands: Home · All projects · Publish, Settings and the engine at the bottom', async () => {
  await hash('#/');
  await expect(page.getByTestId('home')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('nav-home')).toHaveAttribute('aria-current', 'page');
  const order = await page.locator('nav.side a.nav').evaluateAll((els) => els.map((e) => e.getAttribute('data-testid')));
  expect(order).toEqual(['nav-home', 'nav-projects', 'nav-publish', 'nav-settings']);
  await expect(page.getByTestId('engine-status')).toContainText('Ready on this computer');
  // one list item carries what needs her: its count is the one Home says
  await expect(page.getByTestId('inbox-badge')).toHaveText(/^[1-9]$/, { timeout: 60000 });
});

test('every section comes from the real work: chips, the Inbox top rows, what runs, what goes out today', async () => {
  test.setTimeout(120000);
  await hash('#/');
  // held on its skeleton until every source has answered: then the sections are there at once
  await expect(page.getByTestId('home-skeleton')).toHaveCount(0, { timeout: 60000 });
  const chips = page.getByTestId('home-idea');
  await expect(chips.filter({ hasText: 'monday-qa.mp4' })).toHaveAttribute('data-kind', 'recording');
  await expect(chips.filter({ hasText: 'in watch' })).toHaveCount(1);
  // the request she sent twice (in its newest wording)
  await expect(chips.filter({ hasText: /cut my weekly Q&A into clips/i })).toContainText('asked 2 times');
  // out on TikTok (and filled in on Instagram), not on YouTube Shorts yet - one of her platforms
  await expect(chips.filter({ hasText: /Share “.*” on YouTube Shorts/ })).toHaveAttribute('data-kind', 'share');
  await expect(chips.filter({ hasText: /Share/ })).toContainText('out on TikTok, Instagram');
  await expect(chips).toHaveCount(3); // nothing canned beside them

  const inbox = page.getByTestId('home-inbox');
  await expect(inbox.getByTestId('home-inbox-count')).toHaveText(/need you · about \d+ min|needs you · about \d+ min/);
  const n = Number(await page.getByTestId('inbox-badge').innerText());
  await expect(inbox.getByTestId('home-inbox-count')).toContainText(`${n} need`);
  const filler = inbox.getByTestId('home-inbox-row').filter({ hasText: 'Short talk' });
  await expect(filler).toHaveCount(1);
  await expect(filler.getByTestId('home-inbox-act')).toHaveText('Review');
  const failed = inbox.getByTestId('home-inbox-row').filter({ hasText: 'Failed script' });
  await expect(failed.getByTestId('home-inbox-act')).toContainText('Try again');

  const run = page.getByTestId('live-lane');
  await expect(run.getByTestId('home-running-count')).toHaveText('1 job');
  const card = run.getByTestId('live-row').filter({ hasText: 'Q&A cut' });
  await expect(card.getByTestId('live-step')).toContainText('Cutting clip 3 of 8');
  await expect(card).toContainText('4 min left');

  const today = page.getByTestId('home-today');
  const post = today.getByTestId('home-post');
  await expect(post).toHaveCount(2);
  await expect(post.nth(0).getByTestId('home-post-state')).toHaveText(/Posted · 1,240 views/);
  await expect(post.nth(1).getByTestId('home-post-state')).toHaveText(/Waiting on Instagram…/);
  // the whole page in one picture (the mockup of record)
  await page.setViewportSize({ width: 1440, height: 1180 });
  await shot('home');
  await page.setViewportSize({ width: 1440, height: 960 });
});

test('a chip does its one thing: the new recording goes into the composer, the repeated request fills it', async () => {
  await hash('#/');
  await page.getByTestId('home-idea').filter({ hasText: 'monday-qa.mp4' }).click();
  await expect(page.getByTestId('composer-files')).toContainText('monday-qa.mp4');
  await page.getByTestId('home-idea').filter({ hasText: /cut my weekly Q&A/i }).click();
  await expect(page.getByTestId('composer-input')).toHaveValue(/weekly Q&A into clips/i);
  await page.getByTestId('composer-input').fill('');
  await page.getByTestId('composer-files').locator('button.x').click();
});

test('the Inbox row settles in place: Review opens the question in a sheet, one key answers it, the row goes', async () => {
  test.setTimeout(180000);
  await hash('#/');
  const before = Number(await page.getByTestId('inbox-badge').innerText());
  const row = page.getByTestId('home-inbox-row').filter({ hasText: 'Short talk' });
  await row.getByTestId('home-inbox-act').click();
  const sheet = page.getByTestId('home-sheet');
  await expect(sheet.getByTestId('inbox-preview')).toBeVisible();
  await page.waitForTimeout(250); // its fade-in
  await shot('home-sheet');
  // the sheet has the keyboard: ↵ is the pane's primary answer
  await page.keyboard.press('Enter');
  await expect(sheet).toHaveCount(0);
  // gone at once (optimistic), the count follows, Undo is offered
  await expect(row).toHaveCount(0);
  await expect(page.getByTestId('toast-undo').first()).toBeVisible();
  await expect.poll(async () => Number((await page.getByTestId('inbox-badge').innerText().catch(() => '0')) || 0), { timeout: 60000 }).toBeLessThan(before);
});

test('Try again on a failed project runs it again from Home, in place', async () => {
  test.setTimeout(120000);
  await hash('#/');
  const row = page.getByTestId('home-inbox-row').filter({ hasText: 'Failed script' });
  await row.getByTestId('fail-retry').click();
  await expect(row).toHaveCount(0);
  await expect.poll(async () => (await api<{ items: { id: string; failure?: unknown }[] }>('/api/history')).items.find((i) => i.id === ids.c)?.failure ?? null, { timeout: 90000 }).toBeNull();
});

test('a running card opens its live run page in the Studio', async () => {
  await hash('#/');
  await page.getByTestId('live-row').filter({ hasText: 'Q&A cut' }).click();
  await expect(page).toHaveURL(new RegExp(`#/studio/${ids.d}`));
  await expect(page.getByTestId('studio-page')).toContainText('Q&A cut');
  await expect(page.getByTestId('nav-projects')).toHaveAttribute('aria-current', 'page');
});

test('one list in the sidebar: it opens on what needs her while something does; All is every video', async () => {
  // the badge is what needs her (the Inbox): with one it opens on Needs you, without on everything
  const needs = (await page.getByTestId('inbox-badge').count()) > 0;
  await page.getByTestId('nav-projects').click();
  await expect(page.getByTestId('studio')).toBeVisible();
  await expect(page.getByTestId(needs ? 'studio-f-you' : 'studio-f-all')).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByTestId('nav-projects')).toHaveAttribute('aria-current', 'page');
  await page.getByTestId('studio-f-all').click();
  await expect(page.getByTestId('studio-f-all')).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByTestId('nav-projects')).toHaveAttribute('aria-current', 'page');
  // #/inbox still opens it on Needs you
  await hash('#/inbox');
  await expect(page.getByTestId('studio-f-you')).toHaveAttribute('aria-selected', 'true');
});

test('All projects: search, filters and keys over the real list', async () => {
  await page.getByTestId('nav-projects').click();
  await page.getByTestId('studio-f-all').click();
  const rows = page.getByTestId('studio-row');
  await expect(rows.first()).toBeVisible();
  const all = await rows.count();
  await page.getByTestId('studio-search').fill('weekly');
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText('Weekly tips');
  await page.getByTestId('studio-search').fill('');
  await expect(rows).toHaveCount(all);
  // a platform it is posted on
  await page.getByTestId('studio-filters').click();
  await page.getByTestId('studio-f-platform').selectOption('tiktok');
  await expect(rows).toHaveCount(1);
  await expect(page.getByTestId('studio-find-chip')).toHaveText(/TikTok/);
  await page.getByTestId('studio-find-clear').click();
  await expect(rows).toHaveCount(all);
  // J / K move while the list has the keyboard, X picks, the bulk bar says what it can do
  await rows.first().click();
  const first = await rows.first().getAttribute('data-row');
  await page.keyboard.press('j');
  await expect(page.locator('[data-testid=studio-row][aria-current=true]')).not.toHaveAttribute('data-row', first!);
  await page.keyboard.press('k');
  await expect(page.locator('[data-testid=studio-row][aria-current=true]')).toHaveAttribute('data-row', first!);
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+a' : 'Control+a');
  await expect(page.getByTestId('studio-bulk')).toContainText(`${all} selected`);
  await shot('all-projects-bulk');
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('studio-bulk')).toHaveCount(0);
});
