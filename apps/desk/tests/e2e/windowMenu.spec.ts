// App Review guideline 4: the menu must remain usable with no main window.
import { _electron as electron, expect, test } from '@playwright/test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

test('Window > Open Reelfold restores and recreates the main window', async () => {
  test.skip(process.platform !== 'darwin', 'macOS retains the app menu after closing the last window');
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'reelfold-window-menu-'));
  const app = await electron.launch({
    args: [path.resolve(import.meta.dirname, '../..')],
    env: { ...process.env, DESK_USER_DATA: profile, VSTUDIO_HOME: path.join(profile, 'vhome'), DESK_HISTORY_WATCH: '', DESK_SHARED_CACHE: path.join(profile, 'cache'), DESK_HF_HUB: '', DESK_ENGINE_MOCK: '1', DESK_SKIP_FIRST_RUN: '1', DESK_HIDE_WINDOW: '1', VITE_DEV_SERVER_URL: '' },
  });
  try {
    const page = await app.firstWindow();
    await page.waitForURL(/^app:\/\/desk\//);
    const original = await app.evaluate(({ BrowserWindow, Menu }) => {
      const w = BrowserWindow.getAllWindows().find((w) => w.webContents.getURL().startsWith('app://desk/'))!;
      const item = Menu.getApplicationMenu()!.getMenuItemById('open-main-window')!;
      if (!item.enabled) throw new Error('Open Reelfold is disabled');
      w.hide();
      item.click();
      return { id: w.id, visible: w.isVisible() };
    });
    expect(original.visible).toBe(true);
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().find((w) => w.webContents.getURL().startsWith('app://desk/'))!.close());
    await expect.poll(() => app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().filter((w) => w.webContents.getURL().startsWith('app://desk/')).length)).toBe(0);
    const reopened = app.waitForEvent('window');
    await app.evaluate(({ Menu }) => Menu.getApplicationMenu()!.getMenuItemById('open-main-window')!.click());
    const fresh = await reopened;
    await fresh.waitForURL(/^app:\/\/desk\//);
    await expect(fresh.getByTestId('home')).toBeVisible();
    expect(await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().find((w) => w.webContents.getURL().startsWith('app://desk/'))!.id)).not.toBe(original.id);
    await app.evaluate(({ Menu }) => Menu.getApplicationMenu()!.getMenuItemById('open-main-window')!.click());
    expect(await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().filter((w) => w.webContents.getURL().startsWith('app://desk/')).length)).toBe(1);
  } finally {
    await closeApp(app);
    fs.rmSync(profile, { recursive: true, force: true });
  }
});
