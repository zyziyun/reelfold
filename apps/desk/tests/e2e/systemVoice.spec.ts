// Actual macOS voices, real sidecar, isolated prefs/cache; no hardware or model download.
import { _electron as electron, expect, test } from '@playwright/test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

test.skip(process.platform !== 'darwin', 'macOS system speech');
test('choose and preview an installed Chinese system voice, retain the choice after reload', async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'reelfold-system-voice-'));
  const profile = path.join(tmp, 'profile');
  const app = await electron.launch({args: [path.resolve(import.meta.dirname, '../..'), '--mute-audio'], env: {
    ...process.env, DESK_ENGINE_MOCK: '', DESK_USER_DATA: profile, VSTUDIO_HOME: path.join(tmp, 'home'),
    DESK_HISTORY_WATCH: '', DESK_HIDE_WINDOW: '1', DESK_SHARED_CACHE: path.join(tmp, 'cache'), DESK_HF_HUB: '',
    DESK_SKIP_FIRST_RUN: '1', VITE_DEV_SERVER_URL: '',
  }});
  try {
    const page = await app.firstWindow();
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.waitForURL(/^app:\/\/desk\//);
    await page.evaluate(async () => { await window.desk.setSettings({lang: 'en'}); location.hash = '#/settings/voice'; });
    const source = page.getByTestId('voice-source-pick');
    await expect(source).toBeVisible();
    await expect(source.locator('option[value=system]')).toBeEnabled({timeout:30000});
    await source.selectOption('system');
    const pick = page.getByTestId('voice-system-pick');
    await expect(pick).toBeVisible();
    const names = await pick.locator('option:not([disabled])').evaluateAll(es => es.map(e => (e as HTMLOptionElement).value));
    expect(names.length).toBeGreaterThan(0);
    const voice = names.find(n => n.includes('Premium')) ?? names[0];
    await pick.selectOption(voice);
    await expect.poll(() => JSON.parse(fs.readFileSync(path.join(profile, 'tts-prefs.json'), 'utf8'))).toMatchObject({zh_engine:'system', system_voice:voice});
    const response = page.waitForResponse(r => r.url().includes('/system-voices/preview'));
    await page.getByTestId('voice-system-play').click();
    const r = await response;
    expect(r.status()).toBe(200);
    const {path: wav} = await r.json();
    expect(fs.statSync(wav).size).toBeGreaterThan(1000);
    await page.reload();
    await expect(page.getByTestId('voice-source-pick')).toHaveValue('system');
    await expect(page.getByTestId('voice-system-pick')).toHaveValue(voice);
    await page.getByTestId('voice-source-pick').selectOption('qwen');
    await expect(page.getByTestId('voice-zh')).toBeVisible();
    expect(errors).toEqual([]);
  } finally { await closeApp(app); }
});
