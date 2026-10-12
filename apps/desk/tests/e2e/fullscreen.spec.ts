// "点全屏打开请保证打开的是系统层面的视频全部打开" (2026-10-12): the players' ⤢ must take the whole screen at the system
// level, not grow inside the window. In 0.2.7 the default session denied the 'fullscreen' permission, so
// requestFullscreen() was refused and the player only filled the window. Here (window hidden, mock engine, isolated
// profile, a tiny real 3:4 + 9:16 clip; the Studio on, as she has it):
//   * the clip page's ⤢ makes the player the document's full-screen element and the window goes full screen; Space
//     plays / pauses, ←/→ seek 5 s, ↑/↓ + M volume, Esc comes back to the clip page on the same frame (not closed)
//   * a 9:16 version is pillarboxed: as tall as it can be, centred on black
//   * ▶ "Play full screen" on a clip card opens straight in system full screen; Esc is back on the project page
//   * keys in full screen reach only the player (the page underneath does not act on them)
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

let app: ElectronApplication;
let page: Page;
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-fullscreen-'));
const watch = path.join(tmp, 'demos');
const proj = path.join(watch, 'fsdemo');
const SHOTS = path.resolve(import.meta.dirname, '../../test-results/fullscreen');
const VISIBLE = process.env.DESK_FS_VISIBLE === '1';
const SHOOT = VISIBLE || process.env.DESK_FS_SHOTS === '1';

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  fs.mkdirSync(path.join(proj, 'final'), { recursive: true });
  const lavfi = (w: number, h: number) => ['-f', 'lavfi', '-i', `testsrc2=size=${w}x${h}:rate=30:duration=14`, '-f', 'lavfi', '-i', 'sine=frequency=440:duration=14', '-shortest', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac'];
  const ff = (args: string[]) => execFileSync('ffmpeg', ['-v', 'error', '-y', ...args]);
  ff([...lavfi(240, 320), path.join(proj, 'final', 'A_全屏.mp4')]);
  ff([...lavfi(180, 320), path.join(proj, 'final', 'A_全屏_9x16.mp4')]);
  ff(['-i', path.join(proj, 'final', 'A_全屏.mp4'), '-frames:v', '1', path.join(proj, 'final', 'A_全屏_cover.jpg')]);
  fs.writeFileSync(path.join(proj, 'final', 'post.md'), '# 发布文案\n\n## A_全屏.mp4  ·  封面 A_全屏_cover.jpg\n\n全屏播放\n\n正文。\n');
  app = await electron.launch({
    args: [path.resolve(import.meta.dirname, '../..')],
    // DESK_FS_VISIBLE=1 shows the window so macOS really enters its full-screen Space (win.isFullScreen(); it takes
    // over the screen for ~10 s). Hidden (the default) the window keeps its size (main: disableHtmlFullscreenWindowResize
    // for test windows) and Electron's enter/leave-html-full-screen (what drives the OS full screen) stand in for it
    env: { ...process.env, DESK_ENGINE_MOCK: '1', DESK_MOCK_STEP: '0.02', DESK_USER_DATA: path.join(tmp, 'profile'), VSTUDIO_HOME: path.join(tmp, 'vhome'), DESK_HISTORY_WATCH: watch, DESK_HIDE_WINDOW: VISIBLE ? '' : '1', DESK_SHARED_CACHE: path.join(tmp, 'cache'), DESK_HF_HUB: '', DESK_SKIP_FIRST_RUN: '1', VITE_DEV_SERVER_URL: '' },
  });
  page = await app.firstWindow();
  if (!VISIBLE) await page.setViewportSize({ width: 1440, height: 900 });
  await app.evaluate(({ BrowserWindow }) => {
    const g = globalThis as unknown as { __htmlFull: boolean };
    g.__htmlFull = false;
    for (const w of BrowserWindow.getAllWindows()) {
      w.webContents.on('enter-html-full-screen', () => (g.__htmlFull = true));
      w.webContents.on('leave-html-full-screen', () => (g.__htmlFull = false));
    }
  });
  await page.waitForURL(/^app:\/\/desk\//);
  await page.evaluate(() => sessionStorage.setItem('v4.pview', 'grid'));
});

test.afterAll(async () => {
  await closeApp(app);
});

const fsEl = () => page.evaluate(() => document.fullscreenElement?.getAttribute('data-testid') ?? null);
/** the window is in the OS's full screen (shown), or Electron took the page's request to it (hidden window) */
const winFull = () =>
  app.evaluate(({ BrowserWindow }, visible) => (visible ? BrowserWindow.getAllWindows().some((w) => w.isFullScreen()) : (globalThis as unknown as { __htmlFull: boolean }).__htmlFull), VISIBLE);
const video = (sel: string) => page.locator(`${sel} video`).first();
const vt = (sel: string) => video(sel).evaluate((v: HTMLVideoElement) => v.currentTime);
const paused = (sel: string) => video(sel).evaluate((v: HTMLVideoElement) => v.paused);

async function openProject() {
  await page.getByTestId('nav-projects').click();
  await page.getByTestId('project-card').filter({ hasText: 'fsdemo' }).click({ timeout: 30000 });
  await expect(page.getByTestId('clip-card')).toHaveCount(1, { timeout: 30000 });
}

/** the clip's own page in the Studio (her default): the player column, ⤢ right of loop and safe area */
async function openClipPage() {
  await page.evaluate(() => (location.hash = '#/studio'));
  await expect(page.getByTestId('studio')).toBeVisible({ timeout: 30000 });
  await page.locator('[data-testid=studio-row]').filter({ hasText: 'fsdemo' }).click({ timeout: 30000 });
  await expect(page.getByTestId('editor')).toHaveAttribute('data-layout', 'studio', { timeout: 30000 });
}

test('the clip page: ⤢ is system full screen; Space, ←/→, volume, Esc back to the same place', async () => {
  await openClipPage();
  const P = '[data-testid=editor-player]';
  const player = page.locator(P);
  await page.waitForFunction((s) => ((document.querySelector(`${s} video`) as HTMLVideoElement | null)?.readyState ?? 0) >= 1, P);
  expect(await fsEl()).toBeNull();

  await player.getByTestId('fullscreen').click();
  await expect.poll(fsEl).toBe('editor-player'); // the player itself is the document's full-screen element
  await expect(player).toHaveAttribute('data-native-full', '1');
  await expect.poll(winFull, { timeout: 10000 }).toBe(true); // and the window is the OS's full screen
  await expect(player.getByTestId('fullscreen')).toHaveAttribute('aria-label', /Exit full screen|退出全屏/);
  // the picture fills the screen's height (letterboxed on black), the controls are there
  const box = await video(P).boundingBox();
  const vp = await page.evaluate(() => ({ w: innerWidth, h: innerHeight }));
  expect(box!.height).toBeGreaterThan(vp.h * 0.75);
  expect(Math.abs(box!.x + box!.width / 2 - vp.w / 2)).toBeLessThan(4);
  expect(await player.evaluate((el) => getComputedStyle(el).backgroundColor)).toBe('rgb(0, 0, 0)');
  if (SHOOT) {
    await page.waitForTimeout(800); // the first frame painted
    await page.screenshot({ path: path.join(SHOTS, 'clip-page-fullscreen.png') });
  }
  for (const id of ['player-play', 'player-mute', 'player-volume', 'timecode', 'fullscreen']) await expect(player.getByTestId(id)).toBeVisible();
  await expect(player.getByRole('slider').first()).toBeVisible(); // the scrub bar

  // Space plays and pauses (keys reach the player, not the editor underneath)
  expect(await paused(P)).toBe(true);
  await page.keyboard.press('Space');
  await expect.poll(() => paused(P)).toBe(false);
  await page.keyboard.press('Space');
  await expect.poll(() => paused(P)).toBe(true);
  expect(await fsEl()).toBe('editor-player');
  // ←/→ seek 5 s
  await page.keyboard.press('Home');
  await expect.poll(() => vt(P)).toBeLessThan(0.1);
  await page.keyboard.press('ArrowRight');
  await expect.poll(() => vt(P)).toBeGreaterThan(4.9);
  await page.keyboard.press('ArrowRight');
  await expect.poll(() => vt(P)).toBeGreaterThan(9.9);
  await page.keyboard.press('ArrowLeft');
  await expect.poll(() => vt(P)).toBeLessThan(5.1);
  // volume: ↓ lowers it, M mutes
  await page.keyboard.press('ArrowDown');
  await expect.poll(() => video(P).evaluate((v: HTMLVideoElement) => v.volume)).toBeCloseTo(0.9, 2);
  await page.keyboard.press('m');
  await expect.poll(() => video(P).evaluate((v: HTMLVideoElement) => v.muted)).toBe(true);
  await page.keyboard.press('m');
  await expect.poll(() => video(P).evaluate((v: HTMLVideoElement) => v.muted)).toBe(false);
  const at = await vt(P);

  // Esc: back to the clip page, the same frame, the editor still open
  await page.keyboard.press('Escape');
  await expect.poll(fsEl).toBeNull();
  await expect(player).toHaveAttribute('data-full', '0');
  await expect.poll(winFull, { timeout: 10000 }).toBe(false);
  await expect(page.getByTestId('editor')).toBeVisible();
  expect(Math.abs((await vt(P)) - at)).toBeLessThan(0.05);

  // the button again, and the button (not Esc) out
  await player.getByTestId('fullscreen').click();
  await expect.poll(fsEl).toBe('editor-player');
  await player.getByTestId('fullscreen').click();
  await expect.poll(fsEl).toBeNull();
  await expect(page.getByTestId('editor')).toBeVisible();
});

test('a 9:16 version is pillarboxed: full height, centred on black', async () => {
  const P = '[data-testid=editor-player]';
  const player = page.locator(P);
  await player.getByTestId('size-9:16').click();
  await page.waitForFunction((s) => ((document.querySelector(`${s} video`) as HTMLVideoElement).videoWidth ?? 0) === 180, P);
  await player.getByTestId('fullscreen').click();
  await expect.poll(fsEl).toBe('editor-player');
  const vp = await page.evaluate(() => ({ w: innerWidth, h: innerHeight }));
  await expect.poll(async () => (await video(P).boundingBox())!.height).toBeGreaterThan(vp.h * 0.75);
  const box = (await video(P).boundingBox())!;
  expect(box.width / box.height).toBeCloseTo(180 / 320, 1);
  expect(box.width).toBeLessThan(vp.w * 0.6); // black on both sides
  if (SHOOT) await page.screenshot({ path: path.join(SHOTS, 'vertical-fullscreen.png') });
  expect(Math.abs(box.x + box.width / 2 - vp.w / 2)).toBeLessThan(4);
  await page.keyboard.press('Escape');
  await expect.poll(fsEl).toBeNull();
  await expect(page.getByTestId('editor')).toBeVisible();
  await expect.poll(winFull, { timeout: 10000 }).toBe(false); // the Space has closed before the next test
});

test('Esc leaves full screen even before the page has heard it began (a hidden window on Windows paints late)', async () => {
  const P = '[data-testid=editor-player]';
  const player = page.locator(P);
  // hold back the first fullscreenchange, as a window that has not painted its next frame yet does: the player is the
  // full-screen element but has not re-rendered as full screen
  await page.evaluate(() => window.addEventListener('fullscreenchange', (e) => e.stopImmediatePropagation(), { capture: true, once: true }));
  await player.getByTestId('fullscreen').click();
  await expect.poll(fsEl).toBe('editor-player');
  await expect(player).toHaveAttribute('data-native-full', '0');
  await page.keyboard.press('Escape');
  await expect.poll(fsEl).toBeNull();
  await expect(page.getByTestId('editor')).toBeVisible();
  await expect.poll(winFull, { timeout: 10000 }).toBe(false);
});

test('▶ Play full screen on a clip card opens straight in system full screen; Esc is back on the project page', async () => {
  await page.evaluate(() => window.desk.setSettings({ studio: false })); // the project page's clip cards (Studio off)
  await page.reload();
  await page.waitForURL(/^app:\/\/desk\//);
  await openProject();
  await page.getByTestId('clip-card').getByTestId('clip-play').click();
  await expect.poll(fsEl).toBe('player');
  await expect.poll(winFull, { timeout: 10000 }).toBe(true);
  await page.keyboard.press('Escape');
  await expect.poll(fsEl).toBeNull();
  await expect(page.getByTestId('player-overlay')).toHaveCount(0); // watched full screen, back where she was
  await expect(page.getByTestId('clip-card')).toBeVisible();
  await expect.poll(winFull, { timeout: 10000 }).toBe(false);
});
