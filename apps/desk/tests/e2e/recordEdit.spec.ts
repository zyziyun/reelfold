// Runs the app with the Studio off (DESK_STUDIO=0): the pages before the Studio (2026-10 review step 7) stay
// supported behind its flag, and this spec covers them.
// Record -> second pass -> pickup (ux/record/pickups) in the real app with the REAL engine sidecar (no mock engine),
// Chromium's fake camera / microphone, isolated temp profile, window hidden. The only fake is the transcriber
// (fixture/rec_words.py: the fake microphone only beeps). Flow:
//   - Share a screen too: the app's own picker lists what can be shared, a pick shares it (the 0.2.4 button did
//     nothing); with Screen Recording off (DESK_E2E_SCREEN=denied) it says how to turn it on, with the Settings button
//   - record a take, Stop -> lands in the clip editor with the transcript and the automatic cleanup
//   - delete words -> saved by itself
//   - select a word -> Add after -> the player becomes the camera -> record -> the pickup is spliced in, marked in the
//     transcript ("Pickup 1"), the player plays the spliced file
//   - the final render contains it (length = the edited timeline); Undo takes it out again
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-recedit-'));
const FIXTURE = path.join(import.meta.dirname, 'fixture');
const SHOTS = process.env.DESK_SHOTS_DIR ?? path.resolve(import.meta.dirname, '../../test-results/record-edit');
fs.mkdirSync(SHOTS, { recursive: true });
const shot = (page: Page, name: string) => page.screenshot({ path: path.join(SHOTS, `${name}.png`) });

async function launch(profile: string, extra: Record<string, string> = {}) {
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    VSTUDIO_HOME: path.join(tmp, `vhome-${profile}`),
    VSTUDIO_BATCH_BENCH: path.join(tmp, 'bench.json'),
    VSTUDIO_DEFAULT_PERSONA: '1',
    VSTUDIO_LLM_PROVIDER: 'none',
    VSTUDIO_OUTPUT_TRANSCRIBER: `${path.join(FIXTURE, 'rec_words.py')}:words`,
    PYTHONPATH: '',
    DESK_ENGINE_MOCK: '',
    DESK_CREATE: '1',
    DESK_E2E_FAKE_MEDIA: '1',
    DESK_USER_DATA: path.join(tmp, `profile-${profile}`),
    DESK_HISTORY_WATCH: '',
    DESK_STUDIO: '0', DESK_HIDE_WINDOW: '1',
    DESK_SHARED_CACHE: path.join(tmp, 'cache'),
    DESK_HF_HUB: '',
    DESK_SKIP_FIRST_RUN: '1',
    VITE_DEV_SERVER_URL: '',
    ...extra,
  };
  for (const k of ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'VSTUDIO_PERSONA']) delete env[k];
  const app = await electron.launch({ args: [path.resolve(import.meta.dirname, '../..')], env: env as Record<string, string> });
  const page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForURL(/^app:\/\/desk\//);
  await page.evaluate(async () => {
    localStorage.setItem('i18n.strict', '1');
    // speak freely, no 3-2-1, raw sound (the studio pass is tested in the engine)
    localStorage.setItem('rec.prefs', JSON.stringify({ script: false, countdown: false, studio: false }));
    await window.desk.setSettings({ lang: 'en' });
  });
  await page.reload();
  await page.waitForURL(/^app:\/\/desk\//);
  return { app, page };
}

async function api<T>(page: Page, p: string, body?: unknown): Promise<T> {
  return page.evaluate(
    async ([u, b]) => {
      const info = await window.desk.engineInfo();
      const r = await fetch(info.baseUrl + u, { method: b ? 'POST' : 'GET', headers: { Authorization: `Bearer ${info.token}`, 'Content-Type': 'application/json' }, body: b ? JSON.stringify(b) : undefined });
      return r.json();
    },
    [p, body] as const,
  ) as Promise<T>;
}

const probe = (f: string) => Number(execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f], { encoding: 'utf8' }).trim());

test.describe.configure({ mode: 'serial' });

test.describe('recording device interruption', () => {
  let app: ElectronApplication;
  test.afterEach(async () => closeApp(app));
  for (const [kind, lang, message, recording] of [['camera', 'en', 'The camera disconnected', true], ['mic', 'zh-CN', '麦克风已断开', true], ['camera', 'fr', 'La caméra a été déconnectée', true], ['camera', 'en', 'The camera disconnected', false]] as const) {
    test(`pauses and saves when ${kind} disconnects (${lang})${recording ? '' : ' before recording'}`, async () => {
      test.setTimeout(180000);
      const launched = await launch(`lost-${kind}-${lang}-${recording}`, { DESK_STUDIO: '1' });
      app = launched.app;
      const page = launched.page;
      if (lang !== 'en') {
        await page.evaluate((value) => window.desk.setSettings({ lang: value }), lang);
        await page.reload();
      }
      const errors: string[] = [];
      page.on('pageerror', (error) => errors.push(error.message));
      await page.evaluate(() => (location.hash = '#/create/record'));
      await page.evaluate((input) => {
        Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { configurable: true, value: async () => {
          const canvas = document.createElement('canvas'); canvas.width = 640; canvas.height = 360;
          const context = canvas.getContext('2d')!;
          const paint = () => { context.fillStyle = '#238b82'; context.fillRect(0, 0, 640, 360); };
          paint(); setInterval(paint, 40);
          const audio = new AudioContext(); const oscillator = audio.createOscillator(); const destination = audio.createMediaStreamDestination();
          oscillator.connect(destination); oscillator.start();
          const stream = new MediaStream([...canvas.captureStream(24).getVideoTracks(), ...destination.stream.getAudioTracks()]);
          (window as unknown as { inputTracks: MediaStreamTrack[] }).inputTracks = stream.getTracks();
          (window as unknown as { disconnectInput: () => void }).disconnectInput = () => {
            const track = input === 'camera' ? stream.getVideoTracks()[0] : stream.getAudioTracks()[0];
            track.stop(); track.dispatchEvent(new Event('ended'));
          };
          return stream;
        } });
      }, kind);
      await page.getByTestId('create-rec-allow').click();
      await expect(page.getByTestId('create-rec-preview')).toBeVisible();
      // Sharing must end too when the camera/mic setup is no longer usable.
      if (kind === 'camera' && lang === 'en') {
        await page.evaluate(() => {
          Object.defineProperty(navigator.mediaDevices, 'getDisplayMedia', { configurable: true, value: async () => {
            const canvas = document.createElement('canvas'); canvas.width = 640; canvas.height = 360;
            const paint = () => canvas.getContext('2d')!.fillRect(0, 0, 640, 360);
            paint(); setInterval(paint, 40);
            const stream = canvas.captureStream(24);
            (window as unknown as { sharedTracks: MediaStreamTrack[] }).sharedTracks = stream.getTracks();
            return stream;
          } });
        });
        await page.getByTestId('create-rec-screen').click();
        await page.getByTestId('rec-screen-toggle').click();
        await page.getByTestId('rec-screen-source').click();
        await expect(page.getByTestId('rec-screen-preview')).toBeVisible();
      }
      if (recording) {
        await page.getByTestId('create-rec-start').click();
        await page.waitForTimeout(3500);
      }
      await page.evaluate(() => (window as unknown as { disconnectInput: () => void }).disconnectInput());
      if (!recording) {
        await expect(page.getByTestId('create-rec-allow')).toBeVisible();
        await expect(page.getByTestId('rec-error')).toContainText(message);
        expect(await page.evaluate(() => (window as unknown as { inputTracks: MediaStreamTrack[] }).inputTracks.map((track) => track.readyState))).toEqual(['ended', 'ended']);
        expect(await page.evaluate(() => (window as unknown as { sharedTracks: MediaStreamTrack[] }).sharedTracks.map((track) => track.readyState))).toEqual(['ended']);
        expect(errors).toEqual([]);
        return;
      }
      await expect(page.getByTestId('rec-input-interrupted')).toContainText(message);
      await expect(page.getByTestId('create-rec-stop')).toContainText(lang === 'zh-CN' ? '保存当前片段' : lang === 'fr' ? 'Sauvegarder la prise' : 'Save this take');
      await expect(page.getByTestId('rec-pause')).toBeDisabled();
      const clock = await page.getByTestId('create-rec-live').textContent();
      await page.keyboard.press('p');
      await page.waitForTimeout(1500);
      await expect(page.getByTestId('create-rec-live')).toHaveText(clock!);
      await shot(page, `device-${kind}-${lang}-paused`);
      const group = await page.evaluate(() => new URLSearchParams(location.hash.split('?')[1]).get('group')!);
      await page.getByTestId('create-rec-stop').click();
      await expect(page.getByTestId('editor')).toBeVisible({ timeout: 120000 });
      const takes = await page.evaluate((value) => window.desk.rec.list(value), group);
      expect(takes).toHaveLength(1);
      const session = JSON.parse(fs.readFileSync(path.join(takes[0].dir, 'session.json'), 'utf8'));
      for (const track of ['camera', 'mic']) expect(fs.statSync(path.join(takes[0].dir, session.tracks[track].file)).size).toBeGreaterThan(0);
      const duration = probe(path.join(takes[0].dir, 'final', 'recording.mp4'));
      expect(duration).toBeGreaterThan(2);
      expect(duration).toBeLessThan(6);
      if (kind === 'camera' && lang === 'en') {
        expect(await page.evaluate(() => (window as unknown as { sharedTracks: MediaStreamTrack[] }).sharedTracks.map((track) => track.readyState))).toEqual(['ended']);
      }
      expect(errors).toEqual([]);
      await shot(page, `device-${kind}-${lang}-saved`);
    });
  }
});

test.describe('recording final data delivery', () => {
  let app: ElectronApplication;
  test.afterEach(async () => closeApp(app));
  for (const navigate of [false, true]) test(`waits for final data and stop events after devices become inactive${navigate ? ' when navigating away' : ''}`, async () => {
    test.setTimeout(120000);
    const profile = navigate ? 'final-events-nav' : 'final-events';
    const launched = await launch(profile, { DESK_STUDIO: '1' });
    app = launched.app;
    const page = launched.page;
    await page.evaluate(() => { location.hash = '#/create/record'; });
    await page.evaluate(() => {
      const state = { pending: [] as (() => void)[], recorders: [] as MediaRecorder[], nativeStops: 0 };
      (window as unknown as { finalEvents: typeof state }).finalEvents = state;
      const Native = MediaRecorder;
      const data = Object.getOwnPropertyDescriptor(Native.prototype, 'ondataavailable')!;
      window.MediaRecorder = new Proxy(Native, { construct(Target, args) {
        const recorder = Reflect.construct(Target, args) as MediaRecorder;
        state.recorders.push(recorder);
        Object.defineProperty(recorder, 'ondataavailable', { set(handler) {
          data.set!.call(recorder, (event: BlobEvent) => {
            const deliver = () => handler.call(recorder, event);
            if (recorder.state === 'inactive') state.pending.push(deliver); else deliver();
          });
        } });
        const listen = recorder.addEventListener.bind(recorder);
        listen('stop', () => { state.nativeStops++; });
        recorder.addEventListener = ((type: string, listener: EventListenerOrEventListenerObject | null, options?: AddEventListenerOptions | boolean) => {
          const delayed = type === 'stop' ? (event: Event) => state.pending.push(() => {
            if (typeof listener === 'function') listener.call(recorder, event); else listener?.handleEvent(event);
          }) : listener;
          if (delayed) listen(type, delayed, options);
        }) as MediaRecorder['addEventListener'];
        return recorder;
      } });
      Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { configurable: true, value: async () => {
        const canvas = document.createElement('canvas'); canvas.width = 640; canvas.height = 360;
        const paint = () => { const c = canvas.getContext('2d')!; c.fillStyle = '#238b82'; c.fillRect(0, 0, 640, 360); };
        paint(); setInterval(paint, 40);
        const audio = new AudioContext(); const tone = audio.createOscillator(); const dest = audio.createMediaStreamDestination();
        tone.connect(dest); tone.start();
        const stream = new MediaStream([...canvas.captureStream(24).getVideoTracks(), ...dest.stream.getAudioTracks()]);
        (window as unknown as { endFinalInputs: () => void }).endFinalInputs = () => {
          stream.getTracks().forEach((track) => { track.stop(); track.dispatchEvent(new Event('ended')); });
        };
        return stream;
      } });
    });
    await page.getByTestId('create-rec-allow').click();
    await expect(page.getByTestId('create-rec-preview')).toBeVisible();
    await page.getByTestId('create-rec-start').click();
    await page.waitForTimeout(1800);
    if (navigate) await page.evaluate(() => (location.hash = '#/'));
    else await page.evaluate(() => (window as unknown as { endFinalInputs: () => void }).endFinalInputs());
    await expect.poll(() => page.evaluate(() => {
      const s = (window as unknown as { finalEvents: { pending: unknown[]; recorders: MediaRecorder[]; nativeStops: number } }).finalEvents;
      return s.recorders.length === 2 && s.recorders.every((r) => r.state === 'inactive') && s.nativeStops === 2;
    })).toBe(true);
    const recordings = path.join(tmp, `vhome-${profile}`, 'recordings');
    const take = path.join(recordings, fs.readdirSync(recordings)[0]);
    if (!navigate) await page.getByTestId('create-rec-stop').click();
    await page.waitForTimeout(250); // deliberately longer than the old arbitrary 50ms wait
    expect(JSON.parse(fs.readFileSync(path.join(take, 'session.json'), 'utf8')).ended).toBeUndefined();
    await page.evaluate(() => {
      const s = (window as unknown as { finalEvents: { pending: (() => void)[] } }).finalEvents;
      s.pending.splice(0).forEach((deliver) => deliver());
    });
    if (navigate) {
      await expect.poll(() => fs.existsSync(path.join(take, 'recording.lock'))).toBe(false);
      expect(JSON.parse(fs.readFileSync(path.join(take, 'session.json'), 'utf8')).secs).toBeGreaterThan(1.4);
      for (const track of ['camera', 'mic']) {
        // MediaRecorder WebM has no duration header; inspect the actual packet timeline.
        const packets = JSON.parse(execFileSync('ffprobe', ['-v', 'error', '-show_packets', '-show_entries', 'packet=pts_time,duration_time', '-of', 'json', path.join(take, `${track}.webm`)], { encoding: 'utf8' })).packets as { pts_time: string; duration_time?: string }[];
        expect(Math.max(...packets.map(packet => Number(packet.pts_time) + Number(packet.duration_time ?? 0)))).toBeGreaterThan(1.4);
      }
    } else {
      await expect(page.getByTestId('editor')).toBeVisible({ timeout: 90000 });
      expect(fs.existsSync(path.join(take, 'recording.lock'))).toBe(false);
      expect(probe(path.join(take, 'final', 'recording.mp4'))).toBeGreaterThan(1.4);
    }
  });
});

test.describe('recording permission lifecycle', () => {
  let app: ElectronApplication;
  test.afterEach(async () => closeApp(app));
  for (const capture of ['camera', 'screen'] as const) {
    test(`releases a late ${capture} stream after leaving the recording page`, async () => {
      const launched = await launch(`late-${capture}`, { DESK_STUDIO: '1' });
      app = launched.app;
      const page = launched.page;
      await page.evaluate(() => (location.hash = '#/create/record'));
      await page.evaluate((kind) => {
        const state = window as unknown as { finishCapture?: () => void; lateTracks?: MediaStreamTrack[]; capturePending?: boolean };
        const makeStream = (audio: boolean) => {
          const canvas = document.createElement('canvas'); canvas.width = 640; canvas.height = 360;
          const ctx = canvas.getContext('2d')!; ctx.fillStyle = '#238b82'; ctx.fillRect(0, 0, 640, 360);
          const tracks = canvas.captureStream(24).getVideoTracks();
          if (audio) {
            const context = new AudioContext(); const oscillator = context.createOscillator(); const destination = context.createMediaStreamDestination();
            oscillator.connect(destination); oscillator.start(); tracks.push(...destination.stream.getAudioTracks());
          }
          return new MediaStream(tracks);
        };
        const late = () => new Promise<MediaStream>((resolve) => {
          state.capturePending = true;
          state.finishCapture = () => {
            const stream = makeStream(kind === 'camera');
            state.lateTracks = stream.getTracks();
            resolve(stream);
          };
        });
        Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { configurable: true, value: kind === 'camera' ? late : async () => makeStream(true) });
        Object.defineProperty(navigator.mediaDevices, 'getDisplayMedia', { configurable: true, value: late });
      }, capture);
      await page.getByTestId('create-rec-allow').click();
      if (capture === 'screen') {
        await expect(page.getByTestId('create-rec-preview')).toBeVisible();
        await page.getByTestId('create-rec-screen').click();
        await page.getByTestId('rec-screen-toggle').click();
        await page.getByTestId('rec-screen-source').click();
      }
      await expect.poll(() => page.evaluate(() => !!(window as unknown as { capturePending?: boolean }).capturePending)).toBe(true);
      await page.evaluate(() => (location.hash = '#/'));
      await expect(page.getByTestId('create-rec-allow')).toHaveCount(0);
      await page.evaluate(() => (window as unknown as { finishCapture: () => void }).finishCapture());
      await expect.poll(() => page.evaluate(() => (window as unknown as { lateTracks: MediaStreamTrack[] }).lateTracks?.map((t) => t.readyState))).toEqual(capture === 'camera' ? ['ended', 'ended'] : ['ended']);
    });
  }
});

test.describe('recording encoder interruption', () => {
  let app: ElectronApplication;
  test.afterEach(async () => closeApp(app));
  for (const [index, lang, message] of [[0, 'en', 'A recording input stopped unexpectedly'], [1, 'zh-CN', '录制发生错误']] as const) {
    test(`preserves native encoder failure data (${lang})`, async () => {
      test.setTimeout(120000);
      const { app: launched, page } = await launch(`encoder-${lang}`, { DESK_STUDIO: '1' });
      app = launched;
      const pageErrors: string[] = [];
      page.on('pageerror', error => {
        pageErrors.push(error.message);
        fs.appendFileSync(test.info().outputPath('renderer-errors.txt'), error.stack + '\n');
      });
      await page.evaluate(async (lang) => { await window.desk.setSettings({ lang }); }, lang);
      await page.reload();
      await page.evaluate(() => {
        const Original = window.MediaRecorder;
        const state = window as unknown as { nativeRecorders: MediaRecorder[]; recorderEvents: string[] };
        state.nativeRecorders = []; state.recorderEvents = [];
        window.MediaRecorder = new Proxy(Original, {
          construct(Target, args) {
            const recorder = new Target(...args as [MediaStream, MediaRecorderOptions?]);
            state.nativeRecorders.push(recorder);
            for (const kind of ['error', 'dataavailable', 'stop']) recorder.addEventListener(kind, () => state.recorderEvents.push(kind));
            return recorder;
          },
        });
        location.hash = '#/create/record';
      });
      await page.getByTestId('create-rec-allow').click();
      await page.getByTestId('create-rec-start').click();
      await expect(page.getByTestId('create-rec-live')).toBeVisible();
      await page.waitForTimeout(1600);
      // Changing the track set forces the browser's real InvalidModificationError,
      // followed by its final dataavailable and stop events (no synthetic error).
      await page.evaluate(index => {
        const recorders = (window as unknown as { nativeRecorders: MediaRecorder[] }).nativeRecorders;
        const r = recorders[index];
        r.stream.addTrack(r.stream.getTracks()[0].clone());
      }, index);
      await expect(page.getByTestId('rec-input-interrupted')).toContainText(message);
      await expect(page.getByTestId('rec-pause')).toBeDisabled();
      const states = await page.evaluate(() => (window as unknown as { nativeRecorders: MediaRecorder[] }).nativeRecorders.map(r => r.state));
      expect(states[index]).toBe('inactive');
      expect(states[1-index]).toBe('paused');
      const clock = await page.getByTestId('create-rec-live').textContent();
      await page.waitForTimeout(1100);
      expect(await page.getByTestId('create-rec-live').textContent()).toBe(clock);
      const events = await page.evaluate(() => (window as unknown as { recorderEvents: string[] }).recorderEvents);
      expect(events.slice(events.indexOf('error'),events.indexOf('error')+3)).toEqual(['error','dataavailable','stop']);
      await shot(page, `encoder-${lang}-paused`);
      await page.getByTestId('create-rec-stop').click();
      await expect(page.getByTestId('editor')).toBeVisible({ timeout: 90000 });
      const root = path.join(tmp, `vhome-encoder-${lang}`, 'recordings');
      const names = fs.readdirSync(root); expect(names).toHaveLength(1);
      const take = path.join(root,names[0]);
      expect(fs.existsSync(path.join(take,'recording.lock'))).toBe(false);
      for (const track of ['camera','mic']) expect(fs.statSync(path.join(take,`${track}.webm`)).size).toBeGreaterThan(1000);
      expect(probe(path.join(take,'final','recording.mp4'))).toBeGreaterThan(.5);
      expect(pageErrors).toEqual([]);
    });
  }
});

test.describe('recording save recovery', () => {
  let app: ElectronApplication;
  test.afterEach(async () => closeApp(app));

  test('stops on a chunk write failure and saves all retained data on retry', async () => {
    test.setTimeout(120000);
    const { app: launched, page } = await launch('chunk-retry', { DESK_STUDIO: '1' });
    app = launched;
    await app.evaluate(() => {
      const fs = process.mainModule!.require('node:fs') as typeof import('node:fs');
      const open = fs.openSync;
      const write = fs.writeSync;
      let target: number | undefined;
      let broken = true;
      fs.openSync = ((...args: Parameters<typeof open>) => {
        const fd = open(...args);
        if (String(args[0]).endsWith('/camera.webm')) target = fd;
        return fd;
      }) as typeof open;
      fs.writeSync = ((...args: Parameters<typeof write>) => {
        if (args[0] === target && broken) throw new Error('ENOSPC: test recording disk full');
        return write(...args);
      }) as typeof write;
      (globalThis as unknown as { repairRecordingDisk: () => void }).repairRecordingDisk = () => { broken = false; };
    });
    await page.evaluate(() => { location.hash = '#/create/record'; });
    await page.getByTestId('create-rec-allow').click();
    await expect(page.getByTestId('create-rec-preview')).toBeVisible();
    await page.getByTestId('create-rec-start').click();
    const retry = page.getByRole('button', { name: 'Try saving again', exact: true });
    await expect(retry).toBeEnabled({ timeout: 15000 });
    await expect(page.getByTestId('rec-pause')).toBeDisabled();
    await retry.click();
    await expect(retry).toBeEnabled();
    await expect(page.getByTestId('editor')).toHaveCount(0);
    const root = path.join(tmp, 'vhome-chunk-retry', 'recordings');
    const names = fs.readdirSync(root);
    expect(names).toHaveLength(1);
    const take = path.join(root, names[0]);
    expect(fs.existsSync(path.join(take, 'recording.lock'))).toBe(true);
    await app.evaluate(() => (globalThis as unknown as { repairRecordingDisk: () => void }).repairRecordingDisk());
    await retry.click();
    await expect(page.getByTestId('editor')).toBeVisible({ timeout: 90000 });
    expect(fs.readdirSync(root)).toEqual(names);
    expect(fs.existsSync(path.join(take, 'recording.lock'))).toBe(false);
    expect(probe(path.join(take, 'final', 'recording.mp4'))).toBeGreaterThan(0.5);
    expect(fs.statSync(path.join(take, 'camera.webm')).size).toBeGreaterThan(1000);
    expect(fs.statSync(path.join(take, 'mic.webm')).size).toBeGreaterThan(1000);
  });

  test('retries finalizing the same stopped take after a metadata failure', async () => {
    test.setTimeout(120000);
    const { app: launched, page } = await launch('save-retry', { DESK_STUDIO: '1' });
    app = launched;
    await page.evaluate(() => { location.hash = '#/create/record'; });
    await page.getByTestId('create-rec-allow').click();
    await expect(page.getByTestId('create-rec-preview')).toBeVisible();
    await page.getByTestId('create-rec-start').click();
    await page.waitForTimeout(1800);
    const recordings = path.join(tmp, 'vhome-save-retry', 'recordings');
    const names = fs.readdirSync(recordings);
    expect(names).toHaveLength(1);
    const take = path.join(recordings, names[0]);
    const meta = path.join(take, 'session.json');
    const original = fs.readFileSync(meta);
    // Real finalization fails after the camera/mic files have been flushed and closed.
    fs.writeFileSync(meta, '{');
    await page.getByTestId('create-rec-stop').click();
    const retry = page.getByRole('button', { name: 'Try saving again', exact: true });
    await expect(retry).toBeEnabled();
    await expect(page.getByTestId('rec-pause')).toBeDisabled();
    await expect(page.getByText('Recording stopped. Saving failed; try again.', { exact: false }).first()).toBeVisible();
    expect(fs.existsSync(path.join(take, 'recording.lock'))).toBe(true);
    const bytes = ['camera', 'mic'].map(track => fs.readFileSync(path.join(take, `${track}.webm`)));
    await shot(page, 'save-retry');
    await page.waitForTimeout(1200); // retry latency must not become part of the take
    fs.writeFileSync(meta, original);
    await retry.click();
    await expect(page.getByTestId('editor')).toBeVisible({ timeout: 90000 });
    expect(fs.readdirSync(recordings)).toEqual(names);
    expect(fs.existsSync(path.join(take, 'recording.lock'))).toBe(false);
    const saved = JSON.parse(fs.readFileSync(meta, 'utf8'));
    expect(saved.secs).toBeGreaterThan(1.4);
    expect(saved.secs).toBeLessThan(3);
    for (const [i, track] of ['camera', 'mic'].entries()) expect(fs.readFileSync(path.join(take, `${track}.webm`))).toEqual(bytes[i]);
    expect(probe(path.join(take, 'final', 'recording.mp4'))).toBeGreaterThan(1.4);
  });
});

test.describe('recording startup lifecycle', () => {
  let app: ElectronApplication;
  test.afterEach(async () => closeApp(app));

  for (const leave of [false, true]) {
    test(`serializes pending startup and closes it${leave ? ' after navigation' : ' after a track fails'}`, async () => {
      const launched = await launch(`begin-${leave}`, { DESK_STUDIO: '1' });
      app = launched.app;
      const page = launched.page;
      await app.evaluate(({ ipcMain }) => {
        const fixture = { begins: 0, ends: [] as unknown[], release: null as null | (() => void) };
        (globalThis as unknown as { startupFixture: typeof fixture }).startupFixture = fixture;
        ipcMain.removeHandler('rec:begin');
        ipcMain.removeHandler('rec:end');
        ipcMain.removeHandler('rec:chunk');
        ipcMain.handle('rec:begin', () => {
          fixture.begins++;
          return new Promise(resolve => { fixture.release = () => resolve({ sessionId: 'startup-test', dir: '/tmp/startup-test' }); });
        });
        ipcMain.handle('rec:chunk', () => ({ ok: true }));
        ipcMain.handle('rec:end', (_event, value) => {
          fixture.ends.push(value);
          return { dir: '/tmp/startup-test', tracks: [], marks: 0 };
        });
      });
      await page.evaluate(() => (location.hash = '#/create/record'));
      await page.getByTestId('create-rec-allow').click();
      await expect(page.getByTestId('create-rec-preview')).toBeVisible();
      await page.evaluate((leaving) => {
        const Native = window.MediaRecorder;
        const records: MediaRecorder[] = [];
        (window as unknown as { startedRecorders: MediaRecorder[] }).startedRecorders = records;
        window.MediaRecorder = class extends Native {
          start(timeslice?: number) {
            if (!leaving && records.length === 1) throw new Error('Test microphone startup failed');
            super.start(timeslice);
            records.push(this);
          }
        };
      }, leave);
      await page.getByTestId('create-rec-start').click();
      await expect(page.getByTestId('create-rec-start')).toBeDisabled();
      await expect(page.getByTestId('create-rec-start')).toHaveAttribute('aria-busy', 'true');
      const button = await page.getByTestId('create-rec-start').boundingBox();
      expect(button!.width).toBe(button!.height);
      await shot(page, `startup-pending-${leave}`);
      await page.keyboard.press('Space');
      expect(await app.evaluate(() => (globalThis as unknown as { startupFixture: { begins: number } }).startupFixture.begins)).toBe(1);
      if (leave) {
        await page.evaluate(() => (location.hash = '#/'));
        await expect(page.getByTestId('create-rec-start')).toHaveCount(0);
      }
      await app.evaluate(() => (globalThis as unknown as { startupFixture: { release: () => void } }).startupFixture.release());
      await expect.poll(() => app.evaluate(() => (globalThis as unknown as { startupFixture: { ends: unknown[] } }).startupFixture.ends.length)).toBe(1);
      expect(await page.evaluate(() => (window as unknown as { startedRecorders: MediaRecorder[] }).startedRecorders.map(r => r.state))).toEqual(leave ? [] : ['inactive']);
      if (!leave) await expect(page.getByTestId('create-rec-start')).toBeEnabled();
    });
  }
});

test.describe('screen sharing with Screen Recording off', () => {
  let app: ElectronApplication;
  let page: Page;
  test.afterAll(async () => closeApp(app));

  test('says how to turn it on, with the System Settings button (never a silent no-op)', async () => {
    ({ app, page } = await launch('denied', { DESK_E2E_SCREEN: 'denied' }));
    expect((await page.evaluate(() => window.desk.engineInfo())).mode).toBe('real');
    await page.evaluate(() => (location.hash = '#/create/record'));
    // Synthetic browser tracks avoid a CoreAudio fake-device hang on headless macOS runners.
    await page.evaluate(() => {
      const canvas = document.createElement('canvas'); canvas.width=640; canvas.height=360;
      const ctx = canvas.getContext('2d')!; ctx.fillStyle='#238b82'; ctx.fillRect(0,0,640,360);
      setInterval(() => ctx.fillRect(0,0,640,360), 40);
      Object.defineProperty(navigator.mediaDevices, 'getUserMedia', {configurable:true, value:async()=>{
        const audio = new AudioContext(); const tone=audio.createOscillator(); const dest=audio.createMediaStreamDestination();
        tone.connect(dest); tone.start();
        return new MediaStream([...canvas.captureStream(24).getVideoTracks(), ...dest.stream.getAudioTracks()]);
      }});
    });
    await page.getByTestId('create-rec-allow').click();
    await expect(page.getByTestId('create-rec-preview')).toBeVisible({ timeout: 20000 });
    await page.getByTestId('create-rec-screen').click();
    await page.getByTestId('rec-screen-toggle').click();
    const denied = page.getByTestId('rec-screen-denied');
    await expect(denied).toBeVisible();
    await expect(denied).toContainText('Screen & System Audio Recording');
    await expect(page.getByTestId('rec-screen-settings')).toContainText('Open System Settings');
    await expect(page.getByTestId('create-rec-screen')).not.toContainText('Sharing');
    await shot(page, 'R0-screen-denied');
  });
});

test.describe('record -> edit -> pickup', () => {
  let app: ElectronApplication;
  let page: Page;
  test.afterAll(async () => closeApp(app));

  test('share a screen: the picker lists it, a pick shares it', async () => {
    test.setTimeout(120000);
    ({ app, page } = await launch('main'));
    await page.evaluate(() => (location.hash = '#/create/record'));
    // Synthetic browser tracks avoid a CoreAudio fake-device hang on headless macOS runners.
    await page.evaluate((frameMs) => {
      const canvas = document.createElement('canvas'); canvas.width=640; canvas.height=360;
      const ctx = canvas.getContext('2d')!; ctx.fillStyle='#238b82'; ctx.fillRect(0,0,640,360);
      setInterval(() => ctx.fillRect(0,0,640,360), frameMs);
      Object.defineProperty(navigator.mediaDevices, 'getUserMedia', {configurable:true, value:async()=>{
        const audio = new AudioContext(); const tone=audio.createOscillator(); const dest=audio.createMediaStreamDestination();
        tone.connect(dest); tone.start();
        return new MediaStream([...canvas.captureStream(24).getVideoTracks(), ...dest.stream.getAudioTracks()]);
      }});
    }, Number(process.env.DESK_RECORD_FRAME_MS || 40));
    await page.getByTestId('create-rec-allow').click();
    await expect(page.getByTestId('create-rec-preview')).toBeVisible({ timeout: 20000 });
    await page.getByTestId('create-rec-screen').click();
    await page.getByTestId('rec-screen-toggle').click();
    await expect(page.getByTestId('rec-screen-source')).toHaveCount(1);
    await shot(page, 'R1-screen-picker');
    await page.getByTestId('rec-screen-source').click();
    await expect(page.getByTestId('create-rec-screen')).toContainText('Sharing', { timeout: 15000 });
    await expect(page.getByTestId('rec-screen-preview')).toBeVisible();
    await expect(page.getByTestId('create-rec-preview')).toHaveClass(/rs-camera-pip/);
    await page.getByTestId('create-rec-screen').click();
    await page.getByTestId('rec-screen-toggle').click();
    await expect(page.getByTestId('create-rec-screen')).not.toContainText('Sharing');
    await expect(page.getByTestId('rec-screen-preview')).toHaveCount(0);
  });

  test('stop -> the clip editor with the transcript and the automatic cleanup', async () => {
    test.setTimeout(240000);
    await page.keyboard.press('Space');
    await expect(page.getByTestId('create-rec-live')).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(6500);
    await page.keyboard.press('Space');
    await expect(page.getByTestId('rec-preparing')).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId('editor')).toBeVisible({ timeout: 180000 });
    await expect(page.getByTestId('transcript-body')).toContainText('everyone', { timeout: 60000 });
    await expect(page.getByTestId('editor-finish')).toBeVisible();
    await expect(page.getByTestId('editor-finish')).toHaveClass(/primary/);
    await expect(page.getByTestId('editor-takes')).toBeVisible();
    // the "um" was cut automatically: a marker in the transcript + the card that brings it back
    await expect(page.getByTestId('auto-clean-card')).toBeVisible();
    await expect(page.getByTestId('cut-marker').first()).toContainText('um');
    await shot(page, 'R2-lands-in-editor');
  });

  test('delete words: saved by itself', async () => {
    const w = (i: number) => page.locator(`[data-testid="transcript-body"] .w[data-i="${i}"]`);
    await w(2).click();
    await page.keyboard.press('Alt+Shift+ArrowRight'); // + "we" (the bar above the words would catch a Shift-click)
    await page.keyboard.press('Delete');
    await expect(page.getByTestId('cut-status')).toHaveAttribute('data-state', 'saved', { timeout: 30000 });
    await expect(page.getByTestId('cut-marker')).toHaveCount(2); // "today we" collapsed to a marker (+ the um)
    await expect(page.locator('[data-testid="transcript-body"] .w', { hasText: 'today' })).toHaveCount(0);
  });

  test('a pickup after a word: recorded in place of the player, spliced in, marked, playing', async () => {
    test.setTimeout(240000);
    const before = await page.evaluate(() => document.querySelector<HTMLVideoElement>('[data-testid="editor-player"] video')?.currentSrc ?? '');
    const w = page.locator('[data-testid="transcript-body"] .w', { hasText: 'editing' });
    await w.click();
    await expect(page.getByTestId('selection-bar')).toBeVisible();
    await page.getByTestId('sel-add-after').click();
    await expect(page.getByTestId('pickup-stage')).toBeVisible();
    await expect(page.getByTestId('pickup-preview')).toBeVisible({ timeout: 20000 });
    await shot(page, 'R3-pickup-ready');
    await page.getByTestId('pickup-record').click();
    await expect(page.getByTestId('pickup-live')).toBeVisible({ timeout: 10000 });
    await page.waitForTimeout(3500);
    await shot(page, 'R4-pickup-recording');
    await page.getByTestId('pickup-stop').click();
    await expect(page.getByTestId('pickup-stage')).toHaveCount(0, { timeout: 180000 });
    await expect(page.getByTestId('pickup-error')).toHaveCount(0);
    const tag = page.getByTestId('pickup-tag');
    await expect(tag).toHaveText('Pickup 1', { timeout: 30000 });
    // the pickup's words come right after "editing", before "by"
    const ws = (await page.locator('[data-testid="transcript-body"] .w').allInnerTexts()).map((x) => x.trim());
    expect(ws.slice(ws.indexOf('editing'), ws.indexOf('editing') + 4)).toEqual(['editing', 'pickup', 'line', 'by']);
    await expect(page.locator('[data-testid="transcript-body"] .w.pk')).toHaveCount(2);
    // the player plays the spliced file now, and plays through the pickup
    await expect.poll(() => page.evaluate(() => document.querySelector<HTMLVideoElement>('[data-testid="editor-player"] video')?.currentSrc ?? ''), { timeout: 20000 }).not.toBe(before);
    const src = await page.evaluate(() => document.querySelector<HTMLVideoElement>('[data-testid="editor-player"] video')?.currentSrc ?? '');
    expect(decodeURIComponent(src)).toContain('pickups');
    await page.locator('[data-testid="transcript-body"] .w.pk').first().click();
    const t0 = await page.evaluate(() => document.querySelector<HTMLVideoElement>('[data-testid="editor-player"] video')!.currentTime);
    await page.evaluate(() => document.querySelector<HTMLVideoElement>('[data-testid="editor-player"] video')!.play());
    await expect.poll(() => page.evaluate(() => document.querySelector<HTMLVideoElement>('[data-testid="editor-player"] video')!.currentTime), { timeout: 10000 }).toBeGreaterThan(t0 + 0.3);
    await page.evaluate(() => document.querySelector<HTMLVideoElement>('[data-testid="editor-player"] video')!.pause());
    await shot(page, 'R5-pickup-spliced');
  });

  test('the export contains the pickup; Undo takes it out', async () => {
    test.setTimeout(240000);
    const m = /#\/p\/([^/]+)\/clip\/([^/?]+)/.exec(await page.evaluate(() => location.hash));
    expect(m).not.toBeNull();
    const [item, clip] = [m![1], decodeURIComponent(m![2])];
    const doc = await api<{ file: string; fps: number; duration: number; words: { w: string }[]; pickups: { start: number; end: number }[]; cuts: { start: number; end: number }[] }>(page, `/api/outputs/${item}/${encodeURIComponent(clip)}`);
    expect(doc.pickups).toHaveLength(1);
    expect(doc.words.map((x) => x.w)).toContain('pickup');
    const r = await api<{ targets: { file: string }[] }>(page, `/api/outputs/${item}/${encodeURIComponent(clip)}/render`, { quality: 'final', targets: 'primary' });
    const file = r.targets[0].file;
    const kept = doc.duration - doc.cuts.reduce((s, c) => s + (c.end - c.start), 0);
    const actual = probe(file);
    const info = (p: string) => JSON.parse(execFileSync('ffprobe', ['-v', 'error', '-show_streams', '-show_format', '-of', 'json', p], { encoding: 'utf8' }));
    fs.writeFileSync(test.info().outputPath('pickup-duration.json'), JSON.stringify({ doc, kept, actual, base: info(doc.file), render: info(file) }, null, 2));
    if (Math.abs(actual - kept) >= 0.5) {
      // Preserve only this test's synthetic media for a failing CI diagnosis.
      for (const [name, source] of [['base.mp4', doc.file], ['render.mp4', file]]) {
        expect(fs.realpathSync(source).startsWith(fs.realpathSync(tmp) + path.sep)).toBe(true);
        fs.copyFileSync(source, test.info().outputPath(name));
      }
    }
    // Frame-snapped joins and encoder padding stay within half a second.
    expect(Math.abs(actual - kept)).toBeLessThan(0.5);
    expect(kept).toBeGreaterThan(doc.pickups[0].end - doc.pickups[0].start);
    await page.getByTestId('editor-undo').click();
    await expect(page.getByTestId('pickup-tag')).toHaveCount(0, { timeout: 20000 });
    await expect(page.locator('[data-testid="transcript-body"] .w.pk')).toHaveCount(0);
    await page.getByTestId('editor-redo').click();
    await expect(page.getByTestId('pickup-tag')).toHaveText('Pickup 1', { timeout: 20000 });
  });

  test('Takes: the visit\'s takes; Record another take goes back to the recorder with them', async () => {
    await page.getByTestId('editor-takes').click();
    await expect(page.getByTestId('editor-take')).toHaveCount(1);
    await page.getByTestId('editor-record-another').click();
    await expect(page.getByTestId('create-record')).toBeVisible();
    await expect(page.getByTestId('create-rec-take')).toHaveCount(1, { timeout: 10000 });
    await expect(page.getByTestId('rec-take-edit')).toBeVisible();
  });
});

// Current Studio routing: the OS can end display capture independently of camera and mic.
test.describe('shared window ends during a take', () => {
  let app: ElectronApplication;
  test.afterAll(async () => closeApp(app));
  test('pauses all tracks, prevents an incomplete resume and saves the take', async () => {
    test.setTimeout(240000);
    const launched = await launch('screen-ended', { DESK_STUDIO: '1' });
    app = launched.app;
    const page = launched.page;
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await page.evaluate(() => (location.hash = '#/create/record'));
    await page.evaluate(() => {
      const makeVideo = (colour: string) => {
        const canvas = document.createElement('canvas'); canvas.width = 640; canvas.height = 360;
        const ctx = canvas.getContext('2d')!;
        const draw = () => { ctx.fillStyle = colour; ctx.fillRect(0, 0, 640, 360); };
        draw(); setInterval(draw, 40);
        return canvas.captureStream(24).getVideoTracks()[0];
      };
      Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { configurable: true, value: async () => {
        const audio = new AudioContext(); const tone = audio.createOscillator(); const dest = audio.createMediaStreamDestination();
        tone.connect(dest); tone.start();
        return new MediaStream([makeVideo('#238b82'), ...dest.stream.getAudioTracks()]);
      }});
      Object.defineProperty(navigator.mediaDevices, 'getDisplayMedia', { configurable: true, value: async () => {
        const track = makeVideo('#fafafa');
        const audio = new AudioContext();
        const tone = audio.createOscillator(); const dest = audio.createMediaStreamDestination();
        tone.connect(dest); tone.start();
        const sharedAudio = dest.stream.getAudioTracks()[0];
        (window as unknown as { sharedAudio: MediaStreamTrack }).sharedAudio = sharedAudio;
        (window as unknown as { endSharedWindow: () => void }).endSharedWindow = () => {
          track.stop();
          // stop() itself does not fire ended; the OS dispatches it when a shared window closes.
          track.dispatchEvent(new Event('ended'));
        };
        return new MediaStream([track, sharedAudio]);
      }});
    });
    await page.getByTestId('create-rec-allow').click();
    await expect(page.getByTestId('create-rec-preview')).toBeVisible();
    await page.getByTestId('create-rec-screen').click();
    await page.getByTestId('rec-screen-toggle').click();
    await page.getByTestId('rec-screen-source').click();
    await expect(page.getByTestId('rec-screen-preview')).toBeVisible();
    await page.getByTestId('create-rec-start').click();
    await expect(page.getByTestId('create-rec-live')).toContainText('REC');
    await page.waitForTimeout(6500);
    await page.evaluate(() => (window as unknown as { endSharedWindow: () => void }).endSharedWindow());
    await expect(page.getByTestId('create-rec-live')).toContainText('Paused');
    await expect(page.getByTestId('rec-screen-interrupted')).toContainText('Stop to save this take');
    expect(await page.evaluate(() => (window as unknown as { sharedAudio: MediaStreamTrack }).sharedAudio.readyState)).toBe('ended');
    await expect(page.getByTestId('rec-takes')).toContainText('Paused');
    await expect(page.getByTestId('rec-pause')).toBeDisabled();
    await shot(page, 'R7-screen-ended-paused');
    const clock = await page.getByTestId('create-rec-live').textContent();
    await page.keyboard.press('p');
    await page.waitForTimeout(1500);
    await expect(page.getByTestId('create-rec-live')).toHaveText(clock!);
    const group = await page.evaluate(() => new URLSearchParams(location.hash.split('?')[1]).get('group')!);
    await page.getByTestId('create-rec-stop').click();
    await expect(page.getByTestId('editor')).toBeVisible({ timeout: 180000 });
    const takes = await page.evaluate((g) => window.desk.rec.list(g), group);
    expect(takes).toHaveLength(1);
    const saved = JSON.parse(fs.readFileSync(path.join(takes[0].dir, 'session.json'), 'utf8'));
    expect(fs.statSync(path.join(takes[0].dir, saved.tracks.screen.file)).size).toBeGreaterThan(0);
    expect(fs.statSync(path.join(takes[0].dir, saved.tracks.camera.file)).size).toBeGreaterThan(0);
    expect(fs.statSync(path.join(takes[0].dir, saved.tracks.mic.file)).size).toBeGreaterThan(0);
    const duration = probe(path.join(takes[0].dir, 'final', 'recording.mp4'));
    expect(duration).toBeGreaterThan(5);
    expect(duration).toBeLessThan(9);
    expect(errors).toEqual([]);
    await shot(page, 'R8-screen-ended-saved');
  });
});
