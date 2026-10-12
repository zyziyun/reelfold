// A folder she prepared in a watched folder - a BRIEF.md, raw/ clips, a contact sheet, made by hand or by another
// agent - that Reelfold never ran (promo-027-v2, 2026-10-12): it showed as "Making · Plan" with 0 pieces and no live
// output for two hours because the folder had been edited lately. It is "Not made yet" with a way to make it: the
// folder goes into the composer and is sent as a request like any other.
// Studio on, window hidden, test engine, isolated profile and registries.
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

let app: ElectronApplication;
let page: Page;
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-worknotmade-'));
const watch = path.join(tmp, 'demos');
const promo = path.join(watch, 'promo-027-v2');

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  fs.mkdirSync(path.join(promo, 'raw'), { recursive: true });
  fs.writeFileSync(path.join(promo, 'BRIEF.md'), '# Reelfold 0.2.7 — launch promo brief\n\nA 50-second premium launch promo from the clips in raw/.\n');
  for (const n of ['01-home-landing', '02-request-drop-folder']) {
    execFileSync('ffmpeg', ['-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=320x200:rate=30:duration=1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', path.join(promo, 'raw', `${n}.mp4`)]);
  }
  app = await electron.launch({
    args: [path.resolve(import.meta.dirname, '../..')],
    env: { ...process.env, DESK_STUDIO: '1', DESK_ENGINE_MOCK: '1', DESK_MOCK_STEP: '0.02', DESK_USER_DATA: path.join(tmp, 'profile'), VSTUDIO_HOME: path.join(tmp, 'vhome'), DESK_HISTORY_WATCH: watch, DESK_HIDE_WINDOW: '1', DESK_SHARED_CACHE: path.join(tmp, 'cache'), DESK_HF_HUB: '', DESK_SKIP_FIRST_RUN: '1', VITE_DEV_SERVER_URL: '' },
  });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForURL(/^app:\/\/desk\//);
  await page.evaluate(async () => {
    localStorage.setItem('i18n.strict', '1');
    await window.desk.setSettings({ lang: 'en', defaultPlatforms: ['youtube', 'tiktok'] });
  });
  await page.reload();
  await page.waitForURL(/^app:\/\/desk\//);
});

test.afterAll(async () => {
  await closeApp(app);
});

test('a just-edited folder with only a brief and clips is "Not made yet", never a run stuck at Plan', async () => {
  await page.evaluate(() => (location.hash = '#/studio'));
  const row = page.getByTestId('studio-row').filter({ hasText: 'promo-027-v2' });
  await expect(row).toHaveCount(1, { timeout: 30000 });
  await expect(row).toHaveAttribute('data-tone', 'off');
  await expect(row).toContainText('Not started'); // the Studio's word for one nothing has started
  await row.click();
  // the project page with what it is and the way to make it - not the run page (Making · Plan · 0 pieces, no output)
  await expect(page.getByTestId('hub-work-none')).toBeVisible();
  await expect(page.locator('[data-run=project]')).toHaveCount(0);
  await expect(page.getByTestId('work-pieces')).toHaveCount(0);
  await expect(page.getByTestId('hub-state-line')).toHaveText('Not made yet');
  await expect(page.getByTestId('running-badge')).toHaveCount(0);
});

test('"Make a video from this folder" hands the folder to the composer; sent, a video is made from it', async () => {
  await page.getByTestId('hub-work-make').click();
  const composer = page.getByTestId('composer');
  await expect(composer).toBeVisible();
  await expect(composer.getByTestId('composer-file')).toHaveCount(1);
  await expect(composer.getByTestId('composer-file')).toHaveAttribute('title', promo);
  await composer.getByTestId('composer-input').fill('Make the launch promo the brief describes');
  await composer.getByTestId('composer-input').press('ControlOrMeta+Enter');
  // sent as a request: it is planned and made (the test engine plans at once) - a video comes out of it
  await expect(page.locator('[data-testid=studio-row][data-kind=clip]')).toHaveCount(1, { timeout: 30000 });
  await expect(page.getByTestId('composer-file')).toHaveCount(0);
  // her folder is read, never written
  expect(fs.readdirSync(promo).sort()).toEqual(['BRIEF.md', 'raw']);
});
