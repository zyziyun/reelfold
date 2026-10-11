// The run page (ux/run-view A) in the Studio: window hidden, test engine, isolated profile, a synthetic recording.
// A request being planned shows the calm hero (what it is doing in one sentence, the big number, the slim timeline),
// "what happened" stage by stage and the live pane: the engine's stages and the model's turn (prompt, thinking, tool
// call, reply, tokens) as they stream - redacted (a planted key never shows), following the end until she scrolls up
// ("Jump to live"), Copy, Search, the AI / engine filter, docked below or beside, folded and back. Stop ends a plan
// and gives her words back. Two projects running at once tile their live panes in Watch all; a tile opens its page.
// Screenshots go to test-results/run-view.
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

let app: ElectronApplication;
let page: Page;
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-run-'));
const recording = path.join(tmp, 'live_1010.mp4');
const SHOTS = process.env.DESK_SHOTS_DIR ?? path.resolve(import.meta.dirname, '../../test-results/run-view');
fs.mkdirSync(SHOTS, { recursive: true });
const shot = (name: string) => page.screenshot({ path: path.join(SHOTS, `${name}.png`) });

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  execFileSync('ffmpeg', ['-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=180x320:rate=30:duration=4', '-f', 'lavfi', '-i', 'sine=frequency=330:duration=4', '-shortest', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', recording]);
  app = await electron.launch({
    args: [path.resolve(import.meta.dirname, '../..')],
    env: {
      ...process.env,
      DESK_STUDIO: '1',
      DESK_ENGINE_MOCK: '1',
      DESK_MOCK_STEP: process.platform === 'win32' ? '1.5' : '1',
      DESK_MOCK_PLAN_DELAY: '18',
      DESK_MOCK_SECRET: '1',
      DESK_MAX_RUNS: '2',
      DESK_USER_DATA: path.join(tmp, 'profile'),
      VSTUDIO_HOME: path.join(tmp, 'vhome'),
      DESK_HISTORY_WATCH: '',
      DESK_HIDE_WINDOW: '1',
      DESK_SHARED_CACHE: path.join(tmp, 'cache'),
      DESK_HF_HUB: '',
      DESK_SKIP_FIRST_RUN: '1',
      VITE_DEV_SERVER_URL: '',
    },
  });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForURL(/^app:\/\/desk\//);
  await page.evaluate(async () => {
    localStorage.setItem('i18n.strict', '1');
    // a short live pane, so a few lines already scroll
    localStorage.setItem('ui.panes', JSON.stringify({ 'run.live': { size: 200, collapsed: false } }));
    await window.desk.setSettings({ lang: 'en', theme: 'studio-dark' });
  });
  await page.reload();
  await page.waitForURL(/^app:\/\/desk\//);
});

test.afterAll(async () => {
  await closeApp(app);
});

const hash = (h: string) => page.evaluate((x) => (location.hash = x), h);

async function send(prompt: string) {
  await hash('#/studio');
  await expect(page.getByTestId('studio')).toBeVisible({ timeout: 30000 });
  await page.evaluate((f) => sessionStorage.setItem('v4.composer', JSON.stringify({ prompt: '', files: [f] })), recording);
  if (await page.getByTestId('studio-composer').isVisible()) await page.getByTestId('studio-new').click();
  await page.getByTestId('studio-new').click();
  await expect(page.getByTestId('composer-files')).toContainText('live_1010.mp4');
  await page.getByTestId('composer-input').fill(prompt);
  await page.getByTestId('make-plan').click();
  await expect(page.getByTestId('studio-composer')).toHaveCount(0, { timeout: 15000 });
}

const pane = () => page.getByTestId('live-pane');
const lines = () => pane().getByTestId('live-line');

test('a request being planned: the hero, what happened and the live pane streaming the model turn', async () => {
  test.setTimeout(120000);
  await send('把这条直播剪成 2 条小红书切片');
  const run = page.locator('[data-testid=hub-request][data-run=request]');
  await expect(run).toBeVisible({ timeout: 15000 });
  await expect(page.getByTestId('plan-stop')).toBeVisible();
  await expect(page.getByTestId('hub-discard')).toBeVisible();
  await expect(page.getByTestId('hub-request-mode')).toBeVisible();
  await expect(page.getByTestId('hub-title')).toContainText('小红书');
  // the timeline moves through the plan's steps; the hero says what it is doing in words
  await expect(page.getByTestId('plan-step-model')).toHaveAttribute('data-state', 'current', { timeout: 20000 });
  await expect(page.getByTestId('run-now')).not.toHaveText('');
  await expect(page.getByTestId('run-pct')).toHaveText(/\d+%/);
  // the live pane: the engine's stages, then the model's turn as it streams, each line labelled
  await expect(lines().filter({ hasText: 'probe · live_1010.mp4' })).toHaveCount(1);
  await expect(pane().locator('[data-src=agent][data-kind=turn]')).toContainText('intake · claude-code', { timeout: 15000 });
  for (const k of ['prompt', 'thinking', 'tool', 'tool-result', 'say', 'result']) await expect(pane().locator(`[data-src=agent][data-kind=${k}]`).first()).toBeVisible({ timeout: 15000 });
  await expect(pane().locator('[data-kind=tool]')).toContainText('Read  inventory.json');
  // redacted before it is stored: the planted key never reaches the pane
  await expect(pane()).toContainText('[redacted');
  await expect(pane()).not.toContainText('PLANTEDSECRET');
  // what happened, step by step, with the file it read and what the AI answered
  await expect(page.getByTestId('run-story-step').first()).toBeVisible();
  await expect(page.locator('[data-testid=run-story-step][data-step=media] [data-testid=run-file]')).toContainText('live_1010.mp4');
  await expect(page.getByTestId('run-ai').first()).toContainText('Plan: slices of the recording');
  await shot('01-planning-hero-live');
});

test('the live pane follows the end, Jump to live after scrolling up, Copy, Search, the filter', async () => {
  test.setTimeout(60000);
  const body = page.getByTestId('live-body');
  await expect(body).toHaveAttribute('data-stick', '1');
  const atEnd = () => body.evaluate((el) => el.scrollHeight - el.scrollTop - el.clientHeight < 30);
  expect(await atEnd()).toBe(true);
  // she scrolls up: it stops following, "Jump to live" appears and brings her back
  await body.evaluate((el) => {
    el.scrollTop = 0;
    el.dispatchEvent(new Event('scroll'));
  });
  await expect(page.getByTestId('live-jump')).toBeVisible();
  await expect(body).toHaveAttribute('data-stick', '0');
  await page.getByTestId('live-jump').click();
  await expect(page.getByTestId('live-jump')).toHaveCount(0);
  expect(await atEnd()).toBe(true);
  // Copy: the whole log as text, time, tag, line
  await page.getByTestId('live-copy').click();
  await expect(page.getByTestId('toast').filter({ hasText: /Copied \d+ lines/ })).toBeVisible();
  const clip = await app.evaluate(({ clipboard }) => clipboard.readText());
  expect(clip).toContain('engine');
  expect(clip).toContain('intake · claude-code');
  expect(clip).not.toContain('PLANTEDSECRET');
  // Search: the hits counted, the current one marked
  await page.getByTestId('live-search-btn').click();
  await page.getByTestId('live-search').fill('inventory');
  await expect(page.getByTestId('live-search-count')).toHaveText(/^1\/\d+$/);
  await expect(pane().locator('.lv-ln.lv-cur')).toContainText('inventory');
  await page.getByTestId('live-search').press('Escape');
  // the filter: the AI's lines only, then the engine's only
  await page.getByTestId('live-filter-agent').click();
  await expect(pane().locator('[data-src=engine]')).toHaveCount(0);
  await page.getByTestId('live-filter-engine').click();
  await expect(pane().locator('[data-src=agent]')).toHaveCount(0);
  await page.getByTestId('live-filter-all').click();
});

test('docked beside, folded, back below', async () => {
  await page.getByTestId('live-layout').click();
  await expect(page.locator('.runv.runv-side')).toBeVisible();
  await shot('02-planning-side');
  await page.getByTestId('live-collapse').click();
  await expect(page.getByTestId('live-pane')).toHaveCount(0);
  await expect(page.getByTestId('live-show')).toBeVisible();
  await page.getByTestId('live-show').click();
  await page.getByTestId('live-layout').click();
  await expect(page.locator('.runv.runv-below')).toBeVisible();
  await expect(page.getByTestId('live-pane')).toBeVisible();
});

test('Stop ends a plan: nothing is made and her words are back in New video', async () => {
  test.setTimeout(60000);
  const prompt = '再剪 3 条抖音切片，每条 30 秒';
  await send(prompt);
  await expect(page.locator('[data-testid=hub-request][data-run=request]')).toBeVisible({ timeout: 15000 });
  await expect(page.getByTestId('hub-title')).toContainText('抖音');
  await page.getByTestId('plan-stop').click();
  await expect(page.getByTestId('studio-composer')).toBeVisible();
  await expect(page.getByTestId('composer-input')).toHaveValue(prompt);
  await expect(page.getByTestId('studio-row').filter({ hasText: prompt })).toHaveCount(0);
  await page.getByTestId('studio-new').click();
});

test('two projects running: their live panes tiled in Watch all; a tile opens its run page', async () => {
  test.setTimeout(240000);
  // a longer one (6 clips) and a shorter one (3): both still being made while she watches, and the long one still
  // running when its page opens (the first request's project may still be finishing: wait for these two by name)
  await send('剪 6 条 YouTube Shorts 切片');
  await send('再剪 3 条抖音切片');
  // both requests become projects and run side by side (two run slots)
  const running = page.locator('[data-testid=studio-group-run] [data-testid=studio-row][data-kind=project][data-tone=run]');
  await expect(running.filter({ hasText: '6 条切片' })).toHaveCount(1, { timeout: 120000 });
  await expect(running.filter({ hasText: '3 条切片' })).toHaveCount(1, { timeout: 120000 });
  await expect(page.getByTestId('studio-watch')).toBeVisible();
  await page.getByTestId('studio-watch').click();
  const tiles = page.getByTestId('watch-tile');
  await expect(tiles).toHaveCount(2);
  for (const name of ['6 条切片', '3 条切片']) {
    const tile = tiles.filter({ hasText: name });
    await expect(tile.getByTestId('live-line').filter({ hasText: 'stage-start' }).first()).toBeVisible({ timeout: 15000 });
    await expect(tile.locator('[data-src=agent][data-kind=turn]').first()).toContainText('cleanup · claude-code', { timeout: 15000 });
  }
  await shot('03-watch-all');
  // a tile's title opens that project's run page (the 6-clip one: still running when it opens)
  await tiles.filter({ hasText: '6 条切片' }).getByTestId('live-open').click();
  await expect(page.getByTestId('watch-all')).toHaveCount(0);
  const run = page.locator('[data-testid=hub-project][data-run=project]');
  await expect(run).toBeVisible();
  await expect(page.getByTestId('hub-steps')).toBeVisible();
  await expect(page.getByTestId('hub-mode')).toBeVisible();
  await expect(page.getByTestId('run-story-step').first()).toBeVisible({ timeout: 20000 });
  await expect(page.getByTestId('run-files').first()).toContainText('s01');
  await expect(pane().locator('[data-src=engine][data-kind=event]').first()).toBeVisible();
  await shot('04-project-running');
  // light theme: the same page
  await page.evaluate(async () => window.desk.setSettings({ theme: 'notebook-light' }));
  await page.reload();
  await expect(page.locator('[data-testid=hub-project][data-run=project]')).toBeVisible({ timeout: 15000 });
  await expect(page.getByTestId('live-line').first()).toBeVisible();
  await shot('05-project-running-light');
  await page.evaluate(async () => window.desk.setSettings({ theme: 'studio-dark' }));
});
