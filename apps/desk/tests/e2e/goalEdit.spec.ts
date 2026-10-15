// 「Edit the collection」 with the REAL engine (2026-10-13, her words: "可以针对合集做二次编辑么，比如我希望除了这些多选几个片段").
// fixture/goal_edit.py: a made group of two videos (each an English + a 中文 project) from three stories of real clips,
// her words asking for about 4 (at least 3), Ask-me-first; the first video's cut plays two clips of its story.
//   * the page says the group is short of her number and offers 「Fill up to 4」; the composer has the quick chips
//   * "再做 1 条" -> one new plan card cut from clips no video plays (rules: no model here); rename it; Not these
//   * "给 Blue Hour at Shilshole Bay 换掉第 2 个镜头" -> that video's re-cut: its shots (shot 2 marked out) and the unused
//     clips with their frames; picking one counts the changes
//   * "全部加水印" -> one row per made video, each settles (each clip through its own AI; no model here)
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

let app: ElectronApplication;
let page: Page;
let fx: { goal: string; videos: Record<string, { en: string; zh: string }>; card: string };
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-goaledit-'));
const REPO = path.resolve(import.meta.dirname, '../../../..');
const SHOTS = process.env.DESK_SHOTS_DIR ?? path.resolve(import.meta.dirname, '../../test-results/goal-edit');
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

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  test.setTimeout(300000);
  const env: NodeJS.ProcessEnv = { ...process.env, ...engineEnv, PYTHONPATH: path.join(REPO, 'lib') };
  for (const k of ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'VSTUDIO_PERSONA']) delete env[k];
  const out = execFileSync(process.env.DESK_PYTHON || 'python3', [path.join(import.meta.dirname, 'fixture/goal_edit.py'), tmp, path.join(tmp, 'profile', 'engine-data')], { env, encoding: 'utf8' });
  fx = JSON.parse(out.trim().split('\n').pop()!);
  app = await electron.launch({
    args: [path.resolve(import.meta.dirname, '../..')],
    env: { ...env, PYTHONPATH: '', DESK_STUDIO: '1', DESK_ENGINE_MOCK: '', DESK_USER_DATA: path.join(tmp, 'profile'), DESK_HISTORY_WATCH: '', DESK_HIDE_WINDOW: '1', DESK_SHARED_CACHE: path.join(tmp, 'cache'), DESK_HF_HUB: '', DESK_SKIP_FIRST_RUN: '1', VITE_DEV_SERVER_URL: '' },
  });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.waitForURL(/^app:\/\/desk\//);
  await page.evaluate(async () => {
    localStorage.setItem('i18n.strict', '1');
    await window.desk.setSettings({ lang: 'en' });
  });
  await page.reload();
  await page.waitForURL(/^app:\/\/desk\//);
  expect((await page.evaluate(() => window.desk.engineInfo())).mode).toBe('real');
});

test.afterAll(async () => {
  await closeApp(app);
});

const hash = (h: string) => page.evaluate((x) => (location.hash = x), h);
const shot = (name: string) => page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true });
const say = async (words: string) => {
  await page.getByTestId('goal-chat-input').fill(words);
  await page.getByTestId('goal-chat-send').click();
};

test('a made group says it is short of her number, and has its composer', async () => {
  test.setTimeout(120000);
  await hash(`#/studio?goal=${fx.goal}`);
  await expect(page.getByTestId('goal-page')).toHaveAttribute('data-state', 'done', { timeout: 30000 });
  await expect(page.getByTestId('goal-fill')).toContainText('The collection has 2 — you asked for about 4 (at least 3).');
  await expect(page.getByTestId('goal-fill-btn')).toHaveText('Fill up to 4');
  await expect(page.getByTestId('goal-chat')).toBeVisible();
  await expect(page.getByTestId('goal-chat-input')).toHaveAttribute('placeholder', 'Tell this collection what to change…');
  await expect(page.getByTestId('goal-chat-chip')).toHaveText(['Make 3 more', 'Fill up to 4', 'Add a voice-over to all', 'Swap in other shots']);
  await expect(page.getByTestId('goal-chat-ai')).toBeVisible();
  await expect(page.getByTestId('goal-versions')).toHaveCount(0);
  await shot('E1-composer');
});

test('"再做 1 条" proposes a new plan card from the clips no video plays', async () => {
  test.setTimeout(120000);
  await say('再做 1 条');
  await expect(page.getByTestId('goal-chat-me').last()).toHaveText('再做 1 条');
  const plan = page.getByTestId('goal-more-plan');
  await expect(plan).toBeVisible({ timeout: 60000 });
  await expect(plan.getByTestId('goal-plan-video')).toHaveCount(1);
  await expect(page.getByTestId('goal-more-line')).toHaveAttribute('data-state', 'ready');
  await expect(plan.getByTestId('goal-plan-where')).toContainText("Coeur d'Alene"); // the story no video uses
  await expect(page.getByTestId('goal-made')).toHaveCount(2);                      // not part of the group yet
  const title = plan.getByTestId('goal-plan-title');
  await title.fill('Spray at Dusk');
  await title.press('Enter');
  await expect(title).toHaveValue('Spray at Dusk', { timeout: 15000 });
  await expect(page.getByTestId('goal-more-approve')).toHaveText('Make this video');
  await shot('E2-more-card');
  await page.getByTestId('goal-more-discard').click();
  await expect(plan).toHaveCount(0, { timeout: 15000 });
});

test('"换掉第 2 个镜头" opens that video\'s re-cut with its shots and the unused clips', async () => {
  test.setTimeout(120000);
  await say('给 Blue Hour at Shilshole Bay 换掉第 2 个镜头');
  const rc = page.getByTestId('goal-recut');
  await expect(rc).toHaveAttribute('data-video', 'v1', { timeout: 30000 });
  await expect(rc.getByTestId('goal-recut-shot')).toHaveCount(2, { timeout: 30000 });
  await expect(rc.locator('[data-testid=goal-recut-shot][data-shot="2"]')).toHaveAttribute('data-out', '1');
  // its story's two clips the cut never plays + the third story's three (the second video's are taken)
  await expect(rc.getByTestId('goal-recut-clip')).toHaveCount(5);
  await expect(rc.getByTestId('goal-recut-clip').first()).toContainText('Same place');
  await expect(rc.getByTestId('goal-recut-clip').first().locator('img')).toHaveCount(1); // the survey's frame
  await expect(rc.getByTestId('goal-recut-go')).toHaveText('Re-cut with 1 change');
  await rc.getByTestId('goal-recut-clip').first().click();
  await expect(rc.getByTestId('goal-recut-go')).toHaveText('Re-cut with 2 changes');
  await expect(rc.getByTestId('goal-recut-ai')).toBeEnabled();
  await shot('E3-recut');
  await rc.getByTestId('goal-recut-close').click();
  await expect(rc).toHaveCount(0);
  // 「换一批镜头」 with no video named: which one?
  await page.locator('[data-testid=goal-chat-chip][data-chip=swap]').click();
  await expect(page.getByTestId('goal-recut-which')).toHaveCount(2);
  await page.getByTestId('goal-recut').getByRole('button', { name: 'Cancel' }).click();
});

test('"全部加水印" goes to every made video, each settles with its own row', async () => {
  test.setTimeout(600000);
  await say('全部加水印');
  const f = page.getByTestId('goal-fanout').last();
  await expect(f).toBeVisible({ timeout: 30000 });
  await expect(f.getByTestId('goal-fan-video')).toHaveCount(2);
  await expect(f).toHaveAttribute('data-state', 'done', { timeout: 540000 });
  for (const row of await f.getByTestId('goal-fan-video').all()) await expect(row).toHaveAttribute('data-state', /^(done|nothing|proposed|failed)$/);
  await expect(f.getByTestId('goal-fan-summary')).toContainText('of 2');
  await shot('E4-fanout');
});

test('a failed language keeps the made version and offers its own retry', async () => {
  const goalPath = path.join(tmp, 'profile', 'engine-data', 'goals', `${fx.goal}.json`);
  const g = JSON.parse(fs.readFileSync(goalPath, 'utf8'));
  const v = g.videos[0];
  v.state = 'dropped';
  v.reason_code = 'unknown';
  g.state = 'done';
  const failed = v.projects[1];
  fs.writeFileSync(path.join(failed.dir, 'desk-pilot.json'), JSON.stringify({ exit: 1, finished: Date.now() / 1000, offset: 0 }));
  fs.writeFileSync(path.join(failed.dir, 'desk-pilot.log'), JSON.stringify({ event: 'stage-fail', stage: 'render', error: 'There is no Stream(gpu, 0) in current thread.' }) + '\n');
  fs.writeFileSync(goalPath, JSON.stringify(g));
  // Restart only this isolated test app: the engine loads goals into memory.
  await closeApp(app);
  app = await electron.launch({ args: [path.resolve(import.meta.dirname, '../..')], env: {
    ...process.env, ...engineEnv, PYTHONPATH: '', DESK_STUDIO: '1', DESK_ENGINE_MOCK: '',
    DESK_USER_DATA: path.join(tmp, 'profile'), DESK_HISTORY_WATCH: '', DESK_HIDE_WINDOW: '1',
    DESK_SHARED_CACHE: path.join(tmp, 'cache'), DESK_HF_HUB: '', DESK_SKIP_FIRST_RUN: '1', VITE_DEV_SERVER_URL: '',
  } });
  page = await app.firstWindow();
  await page.waitForURL(/^app:\/\/desk\//);
  await hash(`#/studio?goal=${fx.goal}`);
  const row = page.getByTestId('goal-video').filter({ has: page.getByText(v.title, { exact: true }) });
  await expect(row.getByTestId('goal-video-line')).toContainText('1 of 2 versions made', { timeout: 30000 });
  await expect(row.getByTestId('goal-version').first()).toHaveAttribute('data-state', 'made');
  await expect(row.getByTestId('goal-version').last()).toHaveAttribute('data-state', 'failed');
  await expect(row.getByTestId('goal-version').last()).toContainText('Slow-motion rendering');
  await page.addStyleTag({ content: '.goalv-vers { width: 240px; }' });
  const failedRow = row.getByTestId('goal-version').last();
  expect(await failedRow.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
  const bounds = await failedRow.boundingBox();
  const retryBounds = await row.getByTestId('goal-version-retry').boundingBox();
  expect(retryBounds!.x + retryBounds!.width).toBeLessThanOrEqual(bounds!.x + bounds!.width + 1);
  await expect(row.getByTestId('goal-video-open')).toHaveAttribute('href', `#/studio/${v.projects[0].item}`);
  // Resume the real, already-rendered fixture project. Only its forced failure record changes.
  const madeRecord = path.join(v.projects[0].dir, 'desk-pilot.json');
  const before = fs.existsSync(madeRecord) ? fs.readFileSync(madeRecord, 'utf8') : null;
  await row.getByTestId('goal-version-retry').click();
  await expect.poll(() => JSON.parse(fs.readFileSync(path.join(failed.dir, 'desk-pilot.json'), 'utf8')).started).toBeGreaterThan(0);
  expect(fs.existsSync(madeRecord) ? fs.readFileSync(madeRecord, 'utf8') : null).toBe(before);
  await shot('E5-partial-versions');
});

test('a version waiting for confirmation opens its checkpoint without retrying', async () => {
  const goalPath = path.join(tmp, 'profile', 'engine-data', 'goals', `${fx.goal}.json`);
  const prior = JSON.parse(fs.readFileSync(goalPath, 'utf8')).videos[0].projects[1];
  // The preceding retry is real and may still be writing its stage state on a slow runner.
  await page.evaluate(async (id) => {
    const info = await window.desk.engineInfo();
    const response = await fetch(`${info.baseUrl}/api/history/item/${id}/stop`, {
      method: 'POST', headers: { Authorization: `Bearer ${info.token}`, 'Content-Type': 'application/json' }, body: '{}',
    });
    if (!response.ok) throw new Error(`stop fixture run: ${response.status}`);
  }, prior.item);
  await expect.poll(() => page.evaluate(async (id) => {
    const info = await window.desk.engineInfo();
    const response = await fetch(`${info.baseUrl}/api/history/item/${id}/progress`, { headers: { Authorization: `Bearer ${info.token}` } });
    if (!response.ok) throw new Error(`fixture progress: ${response.status}`);
    return (await response.json() as { running: boolean }).running;
  }, prior.item), { timeout: 30000 }).toBe(false);
  await closeApp(app);
  const g = JSON.parse(fs.readFileSync(goalPath, 'utf8'));
  const v = g.videos[0];
  const waiting = v.projects[1];
  // An actual pending recipe gate, in this test's private project/store only.
  execFileSync(process.env.DESK_PYTHON || 'python3', ['-c', `
import json, pathlib, sys
from vstudio.project.core import Project
from vstudio.batch.store import Store
p = Project(sys.argv[1])
p.data['answers'].pop('story', None)
p.save()
st = Store(p.state_dir)
try:
    job = st.jobs()[0]['id']
    st.set_job(job, state='planned')
    st.set_stage(job, 'cp_story', state='failed', error='CheckpointPending: story')
finally:
    st.close()
pay = dict(id='story', kind='media-selection', scope='item', item=job, recipe='photo-story',
           project_dir=p.dir, labels=dict(en='Selection and chapters', zh='选片与章节'),
           options=[], previews=[], default=dict(done=True), digest='review-test',
           answer_schema=dict(type='object', properties=dict(done=dict(type='boolean'))))
dest = pathlib.Path(p.state_dir) / 'checkpoints' / job / 'story.json'
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(json.dumps(pay))
assert any(x['id'] == 'story' for x in p.pending()), 'fixture checkpoint must be unanswered'
`, waiting.dir], { env: { ...process.env, ...engineEnv, PYTHONPATH: path.join(REPO, 'lib') } });
  v.state = 'you';
  v.versions[1].state = 'you';
  g.state = 'done';
  fs.writeFileSync(goalPath, JSON.stringify(g));
  app = await electron.launch({ args: [path.resolve(import.meta.dirname, '../..')], env: {
    ...process.env, ...engineEnv, PYTHONPATH: '', DESK_STUDIO: '1', DESK_ENGINE_MOCK: '',
    DESK_USER_DATA: path.join(tmp, 'profile'), DESK_HISTORY_WATCH: '', DESK_HIDE_WINDOW: '1',
    DESK_SHARED_CACHE: path.join(tmp, 'cache'), DESK_HF_HUB: '', DESK_SKIP_FIRST_RUN: '1', VITE_DEV_SERVER_URL: '',
  } });
  page = await app.firstWindow();
  await page.waitForURL(/^app:\/\/desk\//);
  await hash(`#/studio?goal=${fx.goal}`);
  const row = page.getByTestId('goal-video').filter({ has: page.getByText(v.title, { exact: true }) });
  const version = row.getByTestId('goal-version').last();
  await expect(version).toContainText('Waiting for your review');
  await expect(version.getByTestId('goal-version-retry')).toHaveCount(0);
  const pilot = path.join(waiting.dir, 'desk-pilot.json');
  const before = fs.existsSync(pilot) ? fs.readFileSync(pilot, 'utf8') : null;
  await version.getByTestId('goal-version-review').focus();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(new RegExp(`/studio/${waiting.item}`));
  await expect(page.getByTestId('pinned-question')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('pin-confirm')).toBeVisible();
  await expect(page.getByTestId('pin-confirm')).toHaveClass(/primary/);
  await expect(page.locator('.btn.primary:visible')).toHaveCount(1);
  expect(fs.existsSync(pilot) ? fs.readFileSync(pilot, 'utf8') : null).toBe(before);
  await shot('E6-waiting-review');
});
