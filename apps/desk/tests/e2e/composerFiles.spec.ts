// A drone card in the Studio's "＋ New video" composer ("滚动不了"): 50 DJI_xxxx_D.MP4 + their same-named .SRT
// (telemetry) + a few photos, attached through the real "Attach" button (the OS open panel is stubbed in the main
// process), at 1100×700. One plain summary line instead of 100 chips; Make it stays in view; the list opens and
// scrolls; a video goes with its .srt; Remove all. Window hidden, mock engine, isolated profile.
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

let app: ElectronApplication;
let page: Page;
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-cfiles-'));
const card = path.join(tmp, 'DJI_202610', 'DCIM', '100MEDIA');
const SHOTS = process.env.DESK_SHOTS_DIR ?? path.resolve(import.meta.dirname, '../../test-results/composer-files');
fs.mkdirSync(SHOTS, { recursive: true });
const files: string[] = [];

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  fs.mkdirSync(card, { recursive: true });
  for (let i = 1; i <= 50; i++) {
    const n = String(i).padStart(4, '0');
    files.push(path.join(card, `DJI_${n}_D.MP4`), path.join(card, `DJI_${n}_D.SRT`));
  }
  for (let i = 1; i <= 3; i++) files.push(path.join(card, `DJI_${String(900 + i).padStart(4, '0')}.JPG`));
  for (const f of files) fs.writeFileSync(f, '');
  app = await electron.launch({
    args: [path.resolve(import.meta.dirname, '../..')],
    env: { ...process.env, DESK_STUDIO: '1', DESK_ENGINE_MOCK: '1', DESK_MOCK_STEP: '0.02', DESK_USER_DATA: path.join(tmp, 'profile'), VSTUDIO_HOME: path.join(tmp, 'vhome'), DESK_HISTORY_WATCH: '', DESK_HIDE_WINDOW: '1', DESK_SHARED_CACHE: path.join(tmp, 'cache'), DESK_HF_HUB: '', DESK_SKIP_FIRST_RUN: '1', VITE_DEV_SERVER_URL: '' },
  });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1100, height: 700 });
  await page.waitForURL(/^app:\/\/desk\//);
  await page.evaluate(async () => {
    localStorage.setItem('i18n.strict', '1');
    await window.desk.setSettings({ lang: 'en', theme: 'studio-dark', defaultPlatforms: ['youtube', 'tiktok'] });
  });
  await page.reload();
  await page.waitForURL(/^app:\/\/desk\//);
  await expect(page.getByTestId('studio')).toBeVisible({ timeout: 30000 });
  await app.evaluate(({ dialog }, paths) => {
    dialog.showOpenDialog = (async () => ({ canceled: false, filePaths: paths })) as typeof dialog.showOpenDialog;
  }, files);
});

test.afterAll(async () => {
  await closeApp(app);
});

test('a drone card: one summary line, Make it in view, the list scrolls, a video goes with its .srt, Remove all', async () => {
  await page.getByTestId('studio-new').click();
  await expect(page.getByTestId('studio-composer')).toBeVisible();
  await page.getByTestId('composer-attach').click();
  const summary = page.getByTestId('composer-files-summary');
  await expect(summary).toHaveText('103 files · 50 videos (50 with their .srt) · 3 photos');
  await expect(page.getByTestId('composer-files-toggle')).toContainText('100MEDIA');
  // collapsed: no chip wall
  await expect(page.getByTestId('composer-file')).toHaveCount(0);
  const make = page.getByTestId('make-plan');
  await expect(make).toBeInViewport();
  await expect(page.getByTestId('composer-input')).toBeInViewport();
  await page.getByTestId('composer-input').fill('A calm travel vlog from the drone flight');
  await expect(make).toBeEnabled();
  await make.click({ trial: true });

  // open: a list that scrolls inside a max height; Make it still in view
  await page.getByTestId('composer-files-toggle').click();
  const list = page.getByTestId('composer-files-list');
  await expect(list).toBeVisible();
  await expect(page.getByTestId('composer-file')).toHaveCount(53);
  await expect(page.getByTestId('composer-file').first()).toContainText('DJI_0001_D.MP4');
  await expect(page.getByTestId('composer-file').first()).toContainText('+ .srt');
  const dims = await list.evaluate((el) => ({ sh: el.scrollHeight, ch: el.clientHeight }));
  expect(dims.sh).toBeGreaterThan(dims.ch);
  await list.evaluate((el) => (el.scrollTop = el.scrollHeight));
  await expect.poll(() => list.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
  await expect(page.getByTestId('composer-file').last()).toBeInViewport();
  await page.screenshot({ path: path.join(SHOTS, 'composer-files-open.png') });
  // the composer itself fits in the list column; Make it reachable without scrolling the page
  await page.getByTestId('studio-composer').evaluate((el) => (el.scrollTop = el.scrollHeight));
  await expect(make).toBeInViewport();
  await make.click({ trial: true });

  // a video and its .srt are removed together
  await page.getByTestId('composer-file').first().getByTestId('composer-file-remove').click();
  await expect(summary).toHaveText('101 files · 49 videos (49 with their .srt) · 3 photos');
  await expect(page.getByTestId('composer-file')).toHaveCount(52);
  await expect(page.getByTestId('composer-file').first()).toContainText('DJI_0002_D.MP4');

  await page.getByTestId('composer-files-clear').click();
  await expect(page.getByTestId('composer-files')).toHaveCount(0);
  await expect(page.getByTestId('composer-file')).toHaveCount(0);
  await expect(make).toBeInViewport();
});

test('a few files stay plain chips; a video with its .srt is one chip', async () => {
  await app.evaluate(({ dialog }, paths) => {
    dialog.showOpenDialog = (async () => ({ canceled: false, filePaths: paths })) as typeof dialog.showOpenDialog;
  }, files.slice(0, 4));
  await page.getByTestId('composer-attach').click();
  await expect(page.getByTestId('composer-file')).toHaveCount(2);
  await expect(page.getByTestId('composer-files-summary')).toHaveCount(0);
  await expect(page.getByTestId('composer-file').first()).toContainText('+ .srt');
  await page.getByTestId('composer-file').first().getByTestId('composer-file-remove').click();
  await expect(page.getByTestId('composer-file')).toHaveCount(1);
  await expect(page.getByTestId('composer-file')).toContainText('DJI_0002_D.MP4');
});

test('a dropped folder is one chip that says how many files it holds', async () => {
  await page.getByTestId('composer-file').first().getByTestId('composer-file-remove').click();
  await app.evaluate(({ dialog }, dir) => {
    dialog.showOpenDialog = (async () => ({ canceled: false, filePaths: [dir] })) as typeof dialog.showOpenDialog;
  }, card);
  await page.getByTestId('composer-attach').click();
  const chip = page.locator('[data-testid=composer-file][data-kind=folder]');
  await expect(chip).toContainText('100MEDIA');
  await expect(chip.getByTestId('composer-folder-count')).toHaveText('103 files');
});
