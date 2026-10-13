// A goal's summary of photo stories with the REAL engine (2026-10-13, her DJI goal "8 of 8 made": each beat short showed
// its per-platform tiles - "YouTube 1920×1080 · 0:28", its cover and post copy - but every photo-story "Music film"
// showed a striped tile, "None 原尺寸" and a title with no copy). fixture/photo_story_pair.py: two goal videos, each an
// English photo story for YouTube and its 中文 sibling for 小红书 3:4 + B站 16:9 (out/story.mp4 + out/bilibili/), the
// second one's B站 version never made.
//   * every made version is listed with its platform, size, duration, cover and post copy - never "None"
//   * a planned platform with no version says "not made" with Make; Make makes it and it is listed
//   * the clip page's versions read the same versions
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

let app: ElectronApplication;
let page: Page;
let fx: { goal: string; videos: Record<string, { en: string; zh: string }> };
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-goalstory-'));
const REPO = path.resolve(import.meta.dirname, '../../../..');
const SHOTS = process.env.DESK_SHOTS_DIR ?? path.resolve(import.meta.dirname, '../../test-results/goal-story');
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
  const out = execFileSync(process.env.DESK_PYTHON || 'python3', [path.join(import.meta.dirname, 'fixture/photo_story_pair.py'), tmp, path.join(tmp, 'profile', 'engine-data')], { env, encoding: 'utf8' });
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

test('every photo-story version is listed with its platform, size, duration, cover and post copy', async () => {
  test.setTimeout(120000);
  await hash(`#/studio?goal=${fx.goal}`);
  await expect(page.getByTestId('goal-page')).toHaveAttribute('data-state', 'done', { timeout: 30000 });
  const v1 = page.locator('[data-testid=goal-made][data-video=v1]');
  await expect(v1.getByTestId('goal-made-file')).toHaveCount(3, { timeout: 30000 }); // YouTube · 小红书 · B站
  await expect(v1.getByTestId('goal-made-file').nth(0)).toContainText(/YouTube\s*1920×1080 · 0:0[23]/);
  await expect(v1).toContainText(/Xiaohongshu\s*1080×1440/);
  await expect(v1).toContainText(/Bilibili\s*1920×1080/);
  await expect(v1.getByTestId('goal-made-post')).toHaveCount(2); // one per language version
  await expect(v1.getByTestId('goal-made-post').first()).toContainText('Blue Hour at Shilshole Bay — a quiet drone film');
  await expect(v1.getByTestId('goal-made-post').nth(1)).toContainText('日落之后的半小时');
  // the cover thumbnail, not the striped placeholder
  await expect(v1.locator('.goalv-th img')).toHaveCount(2);
  await expect(page.getByTestId('goal-summary')).not.toContainText('None');
  await expect(page.getByTestId('goal-summary')).not.toContainText('原尺寸');
  await expect(v1.getByTestId('goal-made-missing')).toHaveCount(0);
  await shot('S1-summary');
});

test('a planned version that was not made says so and Make makes it', async () => {
  test.setTimeout(600000);
  const v2 = page.locator('[data-testid=goal-made][data-video=v2]');
  await expect(v2.getByTestId('goal-made-file')).toHaveCount(2, { timeout: 30000 });
  const miss = v2.getByTestId('goal-made-missing');
  await expect(miss).toHaveCount(1);
  await expect(miss).toHaveAttribute('data-pf', 'bilibili');
  await expect(miss).toContainText(/Bilibili\s*not made/);
  await shot('S2-not-made');
  await miss.getByTestId('goal-made-make').click();
  await expect(v2.getByTestId('goal-made-missing')).toHaveCount(0, { timeout: 540000 });
  await expect(v2).toContainText(/Bilibili\s*1920×1080/);
  await shot('S3-made');
});

test('the clip page reads the same versions', async () => {
  test.setTimeout(120000);
  await hash(`#/p/${fx.videos.v1.zh}/clip/v1-zh`);
  await expect(page.getByTestId('ci-versions')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('ci-version-3:4')).toHaveAttribute('data-made', '1');
  await expect(page.getByTestId('ci-version-16:9')).toHaveAttribute('data-made', '1');
  await expect(page.getByTestId('ci-versions-other')).toContainText('YouTube');
  // the playing 3:4 is 小红书's, the 16:9 B站's (no "None:None" platform, no 原尺寸 chip)
  await expect(page.getByTestId('ci-version-detail').getByTestId('ci-version-pf')).toHaveAttribute('data-pf', 'xiaohongshu');
  await page.getByTestId('ci-version-16:9').click();
  await expect(page.getByTestId('ci-version-detail').getByTestId('ci-version-pf')).toHaveAttribute('data-pf', 'bilibili');
  await expect(page.getByTestId('ci-versions')).not.toContainText('原尺寸');
  await shot('S4-clip-versions');
});
