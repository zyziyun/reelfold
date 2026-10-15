// Microphone ownership across failures, navigation and late transcription. Only Chromium's synthetic mic is used.
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';
let app: ElectronApplication, page: Page;
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'reelfold-voice-ownership-'));
const session = '20261015-130000-thought';
test.describe.configure({ mode: 'serial' });
test.beforeAll(async () => {
  app = await electron.launch({ args: [path.resolve(import.meta.dirname, '../..')], env: { ...process.env, DESK_USER_DATA: path.join(temp, 'profile'), VSTUDIO_HOME: path.join(temp, 'home'), VSTUDIO_CACHE: path.join(temp, 'cache'), DESK_CREATE: '1', DESK_STUDIO: '1', DESK_SKIP_FIRST_RUN: '1', DESK_HISTORY_WATCH: '', DESK_ENGINE_MOCK: '', DESK_E2E_FAKE_MEDIA: '1', DESK_HIDE_WINDOW: '1', VITE_DEV_SERVER_URL: '', VSTUDIO_DEFAULT_PERSONA: '1', VSTUDIO_LLM_PROVIDER: 'none' } });
  page = await app.firstWindow(); await page.waitForURL(/^app:\/\/desk\//);
  await page.evaluate(async () => { await window.desk.setSettings({ lang: 'en' }); });
});
test.afterAll(async () => { await closeApp(app); });
async function create() {
  return page.evaluate(async () => {
    const e = await window.desk.engineInfo(); const r = await fetch(e.baseUrl + '/api/create/learning', { method: 'POST', headers: { Authorization: `Bearer ${e.token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ idea: 'Thought ownership', files: [] }) }); return r.json();
  });
}
async function open() { const w = await create(); await page.evaluate((id) => { location.hash = `#/create/learning?id=${id}`; }, w.id); await expect(page.getByTestId('learning-dictate')).toBeEnabled(); return w; }
async function device(delay = false) {
  await page.evaluate((hold) => {
    const media = navigator.mediaDevices; delete (media as unknown as Record<string, unknown>).getUserMedia;
    const native = media.getUserMedia.bind(media);
    media.getUserMedia = async (options) => {
      const stream = await native(options); const state = window as unknown as { voiceStream: MediaStream; releaseMic?: () => void };
      state.voiceStream = stream;
      if (hold) await new Promise<void>((resolve) => { state.releaseMic = resolve; });
      return stream;
    };
  }, delay);
}
const stopped = () => page.evaluate(() => (window as unknown as { voiceStream?: MediaStream }).voiceStream?.getTracks().every((t) => t.readyState === 'ended') ?? false);
async function backend(mode: 'fail' | 'pending' | 'ok' | 'chunk-fail') {
  await app.evaluate(({ ipcMain }, { mode, session, dir }) => {
    const state = globalThis as unknown as { beginCalls: number; endCalls: string[]; releaseBegin?: () => void };
    state.beginCalls = 0; state.endCalls = []; state.releaseBegin = undefined;
    for (const channel of ['rec:begin', 'rec:end', 'rec:chunk']) ipcMain.removeHandler(channel);
    ipcMain.handle('rec:begin', async () => {
      state.beginCalls++;
      if (mode === 'fail') throw new Error('Test session could not be saved');
      if (mode === 'pending') await new Promise<void>((resolve) => { state.releaseBegin = resolve; });
      return { sessionId: session, dir };
    });
    ipcMain.handle('rec:end', (_event, p) => { state.endCalls.push(p.sessionId); return { dir }; });
    ipcMain.handle('rec:chunk', () => { if (mode === 'chunk-fail') throw new Error('Test chunk write failed'); return { ok: true }; });
  }, { mode, session, dir: path.join(temp, 'thought') });
}

test('a session-creation failure releases the already acquired microphone', async () => {
  await page.reload(); await open(); await device(); await backend('fail');
  await page.getByTestId('learning-dictate').click(); await expect(page.getByRole('alert')).toContainText('Test session could not be saved');
  await expect.poll(stopped).toBe(true);
});
test('a delayed microphone result is released after leaving the workspace without starting a session', async () => {
  await page.reload(); await open(); await device(true); await backend('fail');
  await page.getByTestId('learning-dictate').click();
  await expect.poll(() => page.evaluate(() => typeof (window as unknown as { releaseMic?: unknown }).releaseMic)).toBe('function');
  await page.evaluate(() => { location.hash = '#/'; }); await expect(page.getByTestId('learning-workspace')).toHaveCount(0);
  await page.evaluate(() => (window as unknown as { releaseMic: () => void }).releaseMic());
  await expect.poll(stopped).toBe(true);
  expect(await app.evaluate(() => (globalThis as unknown as { beginCalls: number }).beginCalls)).toBe(0);
});
test('leaving while a session is being saved stops the mic immediately and closes the late session once', async () => {
  await page.reload(); await open(); await device(); await backend('pending');
  await page.getByTestId('learning-dictate').click();
  await expect.poll(() => app.evaluate(() => typeof (globalThis as unknown as { releaseBegin?: unknown }).releaseBegin)).toBe('function');
  await page.evaluate(() => { location.hash = '#/'; }); await expect(page.getByTestId('learning-workspace')).toHaveCount(0);
  await expect.poll(stopped).toBe(true);
  await app.evaluate(() => (globalThis as unknown as { releaseBegin: () => void }).releaseBegin());
  await expect.poll(() => app.evaluate(() => (globalThis as unknown as { endCalls: string[] }).endCalls)).toEqual([session]);
});
test('late transcription cannot fill the next workspace and stopping closes the recording only once', async () => {
  await page.reload(); const first = await open(); await device(); await backend('ok');
  await page.evaluate((id) => {
    const native = window.fetch.bind(window);
    const state = window as unknown as { releaseTranscript?: () => void; transcriptRead?: boolean };
    window.fetch = async (input, options) => {
      if (String(input).endsWith(`/api/create/learning/${id}/dictate`)) return new Promise<Response>((resolve) => {
        state.releaseTranscript = () => {
          const response = new Response(JSON.stringify({ text: 'Old workspace words', audio: '/test/raw-voice.webm' }), { headers: { 'Content-Type': 'application/json' } });
          const read = response.text.bind(response);
          response.text = async () => { const value = await read(); state.transcriptRead = true; return value; };
          resolve(response);
        };
      });
      return native(input, options);
    };
  }, first.id);
  await page.getByTestId('learning-dictate').click(); await expect(page.getByTestId('learning-dictate')).toContainText('Finish and transcribe');
  await page.waitForTimeout(600); await page.getByTestId('learning-dictate').click();
  await expect.poll(() => page.evaluate(() => typeof (window as unknown as { releaseTranscript?: unknown }).releaseTranscript)).toBe('function'); await expect.poll(stopped).toBe(true);
  await open(); await page.getByTestId('learning-thought').fill('New workspace thoughts');
  await page.evaluate(() => (window as unknown as { releaseTranscript: () => void }).releaseTranscript());
  await expect.poll(() => page.evaluate(() => (window as unknown as { transcriptRead?: boolean }).transcriptRead)).toBe(true);
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await expect(page.getByTestId('learning-thought')).toHaveValue('New workspace thoughts');
  expect(await app.evaluate(() => (globalThis as unknown as { endCalls: string[] }).endCalls)).toEqual([session]);
});
test('a failed chunk write stops the mic and offers a visible retry', async () => {
  await page.reload(); await open(); await device(); await backend('chunk-fail');
  await page.getByTestId('learning-dictate').click(); await expect(page.getByRole('alert')).toContainText('Test chunk write failed');
  await expect.poll(stopped).toBe(true);
  await expect.poll(() => app.evaluate(() => (globalThis as unknown as { endCalls: string[] }).endCalls)).toEqual([session]);
  await expect(page.getByTestId('learning-dictate')).toBeEnabled();
});
