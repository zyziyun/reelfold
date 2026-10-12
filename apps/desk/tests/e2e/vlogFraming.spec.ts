// Landscape footage on vertical platforms, with the REAL engine sidecar (no mock engine), isolated temp profile,
// window hidden. A vlog project from two tiny synthetic DJI-like clips (fixture/vlog_project.py: a
// red disk crossing a textured ground, a DJI flight log beside each) ran on autopilot to the end: its TikTok version
// follows the subject (the "framing" decision) and every platform's post has a body and hashtags (the "copy"
// decision, written from the facts: no AI account here). On the clip page, "On vertical screens" shows the decision;
// "Fill with blur" changes it and the vertical version is made again with the blurred fill.
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

let app: ElectronApplication;
let page: Page;
let project = '';
let id = '';
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-vlogframing-'));
const REPO = path.resolve(import.meta.dirname, '../../../..');
const SHOTS = process.env.DESK_SHOTS_DIR ?? path.resolve(import.meta.dirname, '../../test-results/vlog-framing');
fs.mkdirSync(SHOTS, { recursive: true });
const engineEnv = {
  VSTUDIO_HOME: path.join(tmp, 'vhome'),
  VSTUDIO_BATCH_BENCH: path.join(tmp, 'bench.json'),
  VSTUDIO_DEFAULT_PERSONA: '1',
  VSTUDIO_MUSIC_DIRS: '',
  VSTUDIO_LLM_PROVIDER: 'none',
  ...Object.fromEntries(['SEGMENT_PLAN', 'PROOFREAD', 'GLOSSARY', 'COPY', 'SCRIPT', 'PLANNER', 'INTAKE', 'OUTPUT_EDIT'].map((t) => [`VSTUDIO_LLM_${t}_PROVIDER`, 'none'])),
};

type Manifest = { exports: { platform: string; reframe: { mode_used: string; shots?: Record<string, number> }; post?: string }[] };
const manifest = (): Manifest | null => {
  try {
    return JSON.parse(fs.readFileSync(path.join(project, 'items', 'main', 'exports', 'manifest.json'), 'utf8')) as Manifest;
  } catch {
    return null; // being rewritten right now
  }
};
const tiktokMode = () => manifest()?.exports.find((e) => e.platform === 'tiktok')?.reframe.mode_used ?? '';

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  test.setTimeout(420000);
  const env: NodeJS.ProcessEnv = { ...process.env, ...engineEnv, PYTHONPATH: path.join(REPO, 'lib') };
  for (const k of ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'VSTUDIO_PERSONA']) delete env[k];
  const out = execFileSync(process.env.DESK_PYTHON || 'python3', [path.join(import.meta.dirname, 'fixture/vlog_project.py'), tmp], { env, encoding: 'utf8', timeout: 400000 });
  const fx = JSON.parse(out.trim().split('\n').pop()!) as { dir: string; exit: number; decisions: Record<string, { choice?: string }> };
  expect(fx.exit).toBe(0);
  expect(fx.decisions.framing?.choice).toBe('follow');
  expect(fx.decisions.copy?.choice).toBe('rules');
  project = fx.dir;
  app = await electron.launch({
    args: [path.resolve(import.meta.dirname, '../..')],
    env: { ...env, PYTHONPATH: '', DESK_STUDIO: '0', DESK_ENGINE_MOCK: '', DESK_USER_DATA: path.join(tmp, 'profile'), DESK_HISTORY_WATCH: '', DESK_HIDE_WINDOW: '1', DESK_SHARED_CACHE: path.join(tmp, 'cache'), DESK_HF_HUB: '', DESK_SKIP_FIRST_RUN: '1', VITE_DEV_SERVER_URL: '' },
  });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForURL(/^app:\/\/desk\//);
  await page.evaluate(async () => {
    localStorage.setItem('i18n.strict', '1');
    await window.desk.setSettings({ lang: 'en' });
  });
  await page.reload();
  await page.waitForURL(/^app:\/\/desk\//);
  expect((await page.evaluate(() => window.desk.engineInfo())).mode).toBe('real');
  const find = async () => (await api<{ items: { id: string; dir: string }[] }>('/api/history')).items.find((i) => fs.realpathSync(i.dir) === fs.realpathSync(project))?.id ?? '';
  await expect.poll(find, { timeout: 60000 }).not.toBe('');
  id = await find();
});

test.afterAll(async () => {
  await closeApp(app);
});

const hash = (h: string) => page.evaluate((x) => (location.hash = x), h);
const shot = (name: string) => page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
const api = <T,>(p: string) =>
  page.evaluate(async (u) => {
    const info = await window.desk.engineInfo();
    const r = await fetch(info.baseUrl + u, { headers: { Authorization: `Bearer ${info.token}` } });
    return r.json();
  }, p) as Promise<T>;

test('the vertical version follows the subject and every post has a body and hashtags', async () => {
  const m = manifest()!;
  const tk = m.exports.find((e) => e.platform === 'tiktok')!;
  expect(tk.reframe.mode_used).toBe('subject');
  expect(Object.keys(tk.reframe.shots ?? {})).not.toContain('pad-blur');
  for (const e of m.exports) {
    const post = fs.readFileSync(path.join(project, 'items', 'main', 'exports', e.post!), 'utf8');
    expect(post.split('\n').filter((x) => x.trim()).length).toBeGreaterThanOrEqual(4); // title + body + tags
    expect(post).toMatch(/#Seattle/);
  }
  // the decisions in words on the project
  const ap = await api<{ decisions: { checkpoint: string; reason_code: string }[] }>(`/api/autopilot/${encodeURIComponent(id)}`);
  const codes = Object.fromEntries(ap.decisions.map((d) => [d.checkpoint, d.reason_code]));
  expect(codes.framing).toBe('reframe-follow');
  expect(codes.copy).toBe('copy-rules');
});

test('On vertical screens on the clip page: Fill with blur re-makes the vertical version', async () => {
  test.setTimeout(300000);
  const outs = await api<{ clips: { id: string }[] }>(`/api/outputs/${encodeURIComponent(id)}`);
  expect(outs.clips.length).toBeGreaterThan(0);
  await hash(`#/p/${id}/clip/${outs.clips[0].id}`);
  await expect(page.getByTestId('editor')).toBeVisible({ timeout: 60000 });
  const fill = page.getByTestId('clip-info').getByTestId('ci-fill');
  await expect(fill).toBeVisible({ timeout: 30000 });
  await expect(fill).toContainText('On vertical screens');
  await expect(page.getByTestId('ci-fill-follow')).toHaveAttribute('aria-pressed', 'true');
  await shot('V1-follow');
  await page.getByTestId('ci-fill-blur').click();
  await expect(page.locator('.toast.error')).toHaveCount(0);
  await expect(page.getByTestId('ci-fill-blur')).toHaveAttribute('aria-pressed', 'true');
  await expect.poll(tiktokMode, { timeout: 240000, intervals: [2000] }).toBe('pad-blur');
  await shot('V2-blur');
  // now hers: the clip page still shows it, and she can switch back
  await expect
    .poll(async () => (await api<{ running: boolean }>(`/api/autopilot/${encodeURIComponent(id)}`)).running, { timeout: 120000, intervals: [2000] })
    .toBe(false);
  await page.reload();
  await page.waitForURL(/^app:\/\/desk\//);
  const fill2 = page.getByTestId('clip-info').getByTestId('ci-fill');
  await expect(fill2).toHaveAttribute('data-choice', 'blur', { timeout: 60000 });
  type Outs = { clips: { id: string; files: { path: string; aspect: string; v?: string | null }[] }[] };
  const vertical = async () => (await api<Outs>(`/api/outputs/${encodeURIComponent(id)}`)).clips[0].files.find((f) => f.aspect === '9:16');
  const v0 = (await vertical())?.v;
  expect(v0).toBeTruthy();
  // the vertical version plays in the clip's player before the re-render (Chromium caches its bytes)
  const player = page.getByTestId('editor-player');
  const video = player.getByTestId('player-video');
  await player.getByRole('button', { name: '9:16', exact: true }).click();
  await expect(video).toHaveAttribute('src', new RegExp(`v=${v0}`), { timeout: 30000 });
  await page.getByTestId('ci-fill-follow').click();
  await expect(page.locator('.toast.error')).toHaveCount(0);
  await expect.poll(tiktokMode, { timeout: 240000, intervals: [2000] }).toBe('subject');
  // the file was written again in place: a new version, and the player loads and plays that one (b221faa)
  await expect.poll(async () => (await vertical())?.v, { timeout: 60000 }).not.toBe(v0);
  const v1 = (await vertical())!.v!;
  await expect(video).toHaveAttribute('src', new RegExp(`v=${v1}`), { timeout: 60000 });
  const t0 = await video.evaluate((v: HTMLVideoElement) => ((v.muted = true), v.currentTime));
  await player.getByTestId('player-play').click();
  await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.currentTime), { timeout: 20000 }).toBeGreaterThan(t0 + 0.5);
  expect(await video.evaluate((v: HTMLVideoElement) => v.error?.code ?? 0)).toBe(0);
  await expect(player.getByTestId('player-error')).toHaveCount(0);
  await shot('V3-follow-plays');
});
