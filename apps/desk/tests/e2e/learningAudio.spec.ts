// Native Electron tab audio, without Chromium's fake media devices or OS desktop capture.
import { _electron as electron, expect, test } from '@playwright/test';
import { buildSync } from 'esbuild';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { closeApp } from './closeApp';

test('material playback audio is captured from this app, without system loopback', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'reelfold-material-audio-'));
  const main = path.join(dir, 'main.cjs');
  const output = path.join(dir, 'material.webm');
  // Import the actual product handler. Only the picker source is the test window itself.
  const recorder = path.resolve(import.meta.dirname, '../../src/main/recorder.ts');
  const html = `<button id="record">Record test sound</button><div id="state"></div><script>
    document.querySelector('#record').onclick = async () => {
      try {
        const ctx = new AudioContext(); await ctx.resume();
        const oscillator = ctx.createOscillator(); oscillator.frequency.value = 500;
        const gain = ctx.createGain(); gain.gain.value = 0.1;
        oscillator.connect(gain).connect(ctx.destination); oscillator.start();
        const stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: true });
        if (!stream.getAudioTracks().length) throw new Error('No app audio track');
        const chunks = []; const rec = new MediaRecorder(stream, { mimeType: 'video/webm;codecs=vp9,opus' });
        rec.ondataavailable = e => chunks.push(e.data);
        rec.onstop = async () => {
          await window.fixture.save(new Uint8Array(await new Blob(chunks).arrayBuffer()));
          stream.getTracks().forEach(t => t.stop()); oscillator.stop(); await ctx.close();
          document.querySelector('#state').textContent = 'Saved';
        };
        rec.start(); setTimeout(() => rec.stop(), 2200);
      } catch (e) { document.querySelector('#state').textContent = String(e); }
    };
  </script>`;
  fs.writeFileSync(path.join(dir, 'page.html'), html);
  fs.writeFileSync(path.join(dir, 'preload.cjs'), `const {contextBridge,ipcRenderer}=require('electron'); contextBridge.exposeInMainWorld('fixture',{save:b=>ipcRenderer.invoke('save',b)});`);
  buildSync({ stdin: { contents: `
    import { app, BrowserWindow, ipcMain } from 'electron';
    import fs from 'node:fs';
    import { installDisplayMedia, ScreenPick, FAKE_SCREEN_ID } from ${JSON.stringify(recorder)};
    app.setPath('userData', ${JSON.stringify(path.join(dir, 'profile'))});
    app.whenReady().then(async () => {
      const win = new BrowserWindow({show:false, webPreferences:{preload:${JSON.stringify(path.join(dir, 'preload.cjs'))}, backgroundThrottling:false}});
      win.webContents.session.setPermissionCheckHandler(() => true);
      win.webContents.session.setPermissionRequestHandler((wc,p,cb) => cb(true));
      const pick = new ScreenPick(); pick.arm(FAKE_SCREEN_ID, Date.now(), true);
      installDisplayMedia(win.webContents.session, {flag:()=>true,pick,fakeMedia:true});
      ipcMain.handle('save',(e,b)=>fs.writeFileSync(${JSON.stringify(output)},b));
      await win.loadFile(${JSON.stringify(path.join(dir, 'page.html'))});
    });`, resolveDir: path.resolve(import.meta.dirname, '../..'), loader: 'ts' }, platform: 'node', format: 'cjs', bundle: true, external: ['electron'], outfile: main });
  const app = await electron.launch({ args: [main], env: { ...process.env, DESK_E2E_FAKE_MEDIA: '' } });
  try {
    const page = await app.firstWindow();
    expect(await app.evaluate(({ app }) => app.commandLine.hasSwitch('use-fake-device-for-media-stream'))).toBe(false);
    await page.locator('#record').click();
    await expect(page.locator('#state')).toHaveText('Saved', { timeout: 15000 });
    const pcm = execFileSync('ffmpeg', ['-v', 'error', '-i', output, '-vn', '-ac', '1', '-ar', '8000', '-f', 's16le', '-']);
    const count = pcm.length / 2;
    const magnitude = (hz: number) => {
      let real = 0, imag = 0;
      for (let n = 0; n < count; n++) { const x = pcm.readInt16LE(n * 2) / 32768; real += x * Math.cos(2 * Math.PI * hz * n / 8000); imag += x * Math.sin(2 * Math.PI * hz * n / 8000); }
      return 2 * Math.hypot(real, imag) / count;
    };
    // Chromium's mixer scales playback gain; verify identity and a usable signal, not device gain.
    expect(magnitude(500)).toBeGreaterThan(0.02);
    expect(magnitude(400)).toBeLessThan(0.005);
  } finally { await closeApp(app); }
});
