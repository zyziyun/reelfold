// Microphone ownership across failures, navigation and late transcription. Only Chromium's synthetic mic is used.
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import fs from 'node:fs';
import { execFileSync } from 'node:child_process';
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

test('a real voice recording retains failed disk writes and retries the same take', async () => {
  await page.reload(); const workspace = await open(); await device();
  await app.evaluate(() => {
    const fs = process.mainModule!.require('node:fs') as typeof import('node:fs');
    const open = fs.openSync; const write = fs.writeSync;
    let fd: number | undefined;
    fs.openSync = ((...args: Parameters<typeof open>) => {
      const result = open(...args);
      if (String(args[0]).endsWith('/mic.webm')) fd = result;
      return result;
    }) as typeof open;
    fs.writeSync = ((...args: Parameters<typeof write>) => {
      if (args[0] === fd) throw new Error('ENOSPC: test voice disk full');
      return write(...args);
    }) as typeof write;
    (globalThis as unknown as { repairVoiceDisk: () => void }).repairVoiceDisk = () => { fs.openSync = open; fs.writeSync = write; };
  });
  // Synthetic microphone beeps have no words: isolate only the transcription response.
  await page.evaluate((id) => {
    const native = window.fetch.bind(window);
    window.fetch = async (input, options) => String(input).endsWith(`/api/create/learning/${id}/dictate`)
      ? new Response(JSON.stringify({ text: 'Recovered voice note', audio: '/test/voice.webm' }), { headers: { 'Content-Type': 'application/json' } })
      : native(input, options);
  }, workspace.id);
  await page.getByTestId('learning-dictate').click();
  await expect(page.getByRole('alert')).toContainText('test voice disk full');
  await expect.poll(stopped).toBe(true);
  const retry = page.getByTestId('learning-dictate');
  await expect(retry).toHaveText('Try saving again');
  const root = path.join(temp, 'home', 'recordings');
  const names = fs.readdirSync(root);
  expect(names).toHaveLength(1);
  const take = path.join(root, names[0]);
  expect(fs.existsSync(path.join(take, 'recording.lock'))).toBe(true);
  await retry.click();
  await expect(retry).toHaveText('Try saving again');
  await expect(page.getByTestId('learning-thought')).toHaveValue('');
  await app.evaluate(() => (globalThis as unknown as { repairVoiceDisk: () => void }).repairVoiceDisk());
  await retry.click();
  await expect(page.getByTestId('learning-thought')).toHaveValue('Recovered voice note');
  expect(fs.readdirSync(root)).toEqual(names);
  expect(fs.existsSync(path.join(take, 'recording.lock'))).toBe(false);
  const pcm = execFileSync('ffmpeg', ['-v', 'error', '-i', path.join(take, 'mic.webm'), '-ac', '1', '-ar', '8000', '-f', 's16le', '-']);
  expect(pcm.length).toBeGreaterThan(1000);
  expect(pcm.some(x => x !== 0)).toBe(true);
  expect(JSON.parse(fs.readFileSync(path.join(take, 'session.json'), 'utf8')).secs).toBeLessThan(1.5);
});

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
test('a failed chunk write stops the mic without finalizing an incomplete take', async () => {
  await page.reload(); await open(); await device(); await backend('chunk-fail');
  await page.getByTestId('learning-dictate').click(); await expect(page.getByRole('alert')).toContainText('Test chunk write failed');
  await expect.poll(stopped).toBe(true);
  await expect.poll(() => app.evaluate(() => (globalThis as unknown as { endCalls: string[] }).endCalls)).toEqual([]);
  await expect(page.getByTestId('learning-dictate')).toBeEnabled();
  await expect(page.getByTestId('learning-dictate')).toHaveText('Try saving again');
});
