// Actual MAS main -> Python -> socket -> native dialog -> refusal path.
import { _electron as electron, expect, test } from '@playwright/test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

test('MAS refuses AI content before transmission and exposes permission reset', async () => {
  test.skip(process.platform !== 'darwin' || process.env.DESK_EXPECT_EDITION !== 'mas', 'compile BUILD_EDITION=mas first');
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'reelfold-consent-e2e-'));
  const app = await electron.launch({ args: [path.resolve(import.meta.dirname, '../..')], env: {
    ...process.env, DESK_USER_DATA: profile, VSTUDIO_HOME: path.join(profile, 'vhome'), DESK_SHARED_CACHE: path.join(profile, 'cache'), DESK_HF_HUB: '', DESK_HISTORY_WATCH: '', DESK_ENGINE_MOCK: '1', DESK_SKIP_FIRST_RUN: '1', DESK_HIDE_WINDOW: '1', VITE_DEV_SERVER_URL: '',
    ANTHROPIC_API_KEY: 'test-only-not-a-secret', ANTHROPIC_BASE_URL: 'https://consent-test.invalid/private?token=hidden',
  } });
  try {
    const page = await app.firstWindow(); await page.waitForURL(/^app:\/\/desk\//);
    expect((await page.evaluate(() => window.desk.getSettings())).edition).toBe('mas');
    await app.evaluate(({ dialog }) => {
      (globalThis as unknown as { consentDialogs: unknown[] }).consentDialogs = [];
      dialog.showMessageBox = (async (...args: unknown[]) => {
        (globalThis as unknown as { consentDialogs: unknown[] }).consentDialogs.push(args.at(-1));
        return { response: 0, checkboxChecked: false };
      }) as typeof dialog.showMessageBox;
    });
    const result = await page.evaluate(() => window.desk.ai.test('anthropic'));
    expect(result.ok).toBe(false);
    const dialogs = await app.evaluate(() => (globalThis as unknown as { consentDialogs: { detail: string; defaultId: number; cancelId: number; buttons: string[] }[] }).consentDialogs);
    expect(dialogs).toHaveLength(1);
    expect(dialogs[0]).toMatchObject({ defaultId: 0, cancelId: 0, buttons: ['Don’t Allow', 'Allow'] });
    expect(dialogs[0].detail).toContain('https://consent-test.invalid');
    expect(dialogs[0].detail).toContain('transcripts');
    expect(dialogs[0].detail).not.toContain('hidden');
    expect(dialogs[0].detail).not.toContain('/private');
    expect(fs.existsSync(path.join(profile, 'ai-sharing-permissions.json'))).toBe(false);
    await app.evaluate(({ Menu }) => Menu.getApplicationMenu()!.getMenuItemById('reset-ai-consent')!.click());
    expect(JSON.parse(fs.readFileSync(path.join(profile, 'ai-sharing-permissions.json'), 'utf8')).grants).toEqual([]);
  } finally { await closeApp(app); fs.rmSync(profile, { recursive: true, force: true }); }
});
