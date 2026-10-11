// A vlog finished BEFORE the vertical framing and post copy steps existed (her Seattle project, app 0.2.6), with the
// REAL engine sidecar (no mock engine), isolated temp profile, window hidden. fixture/vlog_project.py --old: its
// exports are on a blurred fill, each post.md is the title only, no framing / copy decision is recorded, no
// shots.json. On the clip page "On vertical screens" still shows (Fill with blur, read from its exports); "Rewrite
// post copy" writes every platform's copy (from the facts: no AI account here); Follow the subject re-makes only the
// vertical version with a crop; and the clip chat's "竖屏用模糊背景" runs that setting, not "add a 9:16 version".
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
let clip = '';
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-vlogrefresh-'));
const REPO = path.resolve(import.meta.dirname, '../../../..');
const SHOTS = process.env.DESK_SHOTS_DIR ?? path.resolve(import.meta.dirname, '../../test-results/vlog-refresh');
fs.mkdirSync(SHOTS, { recursive: true });
const engineEnv = {
  VSTUDIO_HOME: path.join(tmp, 'vhome'),
  VSTUDIO_BATCH_BENCH: path.join(tmp, 'bench.json'),
  VSTUDIO_DEFAULT_PERSONA: '1',
  VSTUDIO_MUSIC_DIRS: '',
  VSTUDIO_LLM_PROVIDER: 'none',
  ...Object.fromEntries(['SEGMENT_PLAN', 'PROOFREAD', 'GLOSSARY', 'COPY', 'SCRIPT', 'PLANNER', 'INTAKE', 'OUTPUT_EDIT'].map((t) => [`VSTUDIO_LLM_${t}_PROVIDER`, 'none'])),
};

type Entry = { platform: string; file: string; reframe: { mode_used: string; plan: string }; post?: string };
const exportsDir = () => path.join(project, 'items', 'main', 'exports');
const manifest = (): { exports: Entry[] } | null => {
  try {
    return JSON.parse(fs.readFileSync(path.join(exportsDir(), 'manifest.json'), 'utf8')) as { exports: Entry[] };
  } catch {
    return null; // being rewritten right now
  }
};
const entry = (pf: string) => manifest()?.exports.find((e) => e.platform === pf);
const tiktokMode = () => entry('tiktok')?.reframe.mode_used ?? '';
const postLines = (pf: string) => {
  const e = entry(pf);
  if (!e?.post) return 0;
  return fs.readFileSync(path.join(exportsDir(), e.post), 'utf8').split('\n').filter((x) => x.trim()).length;
};

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  test.setTimeout(420000);
  const env: NodeJS.ProcessEnv = { ...process.env, ...engineEnv, PYTHONPATH: path.join(REPO, 'lib') };
  for (const k of ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'VSTUDIO_PERSONA']) delete env[k];
  const out = execFileSync(process.env.DESK_PYTHON || 'python3', [path.join(import.meta.dirname, 'fixture/vlog_project.py'), tmp, '--old'], { env, encoding: 'utf8', timeout: 400000 });
  const fx = JSON.parse(out.trim().split('\n').pop()!) as { dir: string; exit: number; decisions: Record<string, unknown> };
  expect(fx.exit).toBe(0);
  expect(fx.decisions.framing).toBeUndefined(); // made "before": nothing recorded
  expect(fx.decisions.copy).toBeUndefined();
  project = fx.dir;
  expect(tiktokMode()).toBe('pad-blur');
  expect(postLines('tiktok')).toBe(1); // the title only
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
  const outs = await api<{ clips: { id: string }[] }>(`/api/outputs/${encodeURIComponent(id)}`);
  clip = outs.clips.find((c) => c.id.includes('tiktok'))?.id ?? outs.clips[0].id;
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
const idle = () =>
  expect.poll(async () => (await api<{ running: boolean }>(`/api/autopilot/${encodeURIComponent(id)}`)).running, { timeout: 240000, intervals: [2000] }).toBe(false);
const noMissingKeys = async () => {
  const text = await page.evaluate(() => document.body.innerText);
  expect(text.match(/⟦[^⟧]+⟧/g) ?? []).toEqual([]);
};

test('the old clip shows its framing (from its exports) and Rewrite post copy writes every platform', async () => {
  test.setTimeout(300000);
  await hash(`#/p/${id}/clip/${encodeURIComponent(clip)}`);
  await expect(page.getByTestId('editor')).toBeVisible({ timeout: 60000 });
  const info = page.getByTestId('clip-info');
  const fill = info.getByTestId('ci-fill');
  await expect(fill).toBeVisible({ timeout: 30000 });
  await expect(fill).toHaveAttribute('data-choice', 'blur');
  await expect(info.getByTestId('ci-fill-blur')).toHaveAttribute('aria-pressed', 'true');
  const rw = info.getByTestId('ci-copy-rewrite');
  await expect(rw).toBeVisible();
  await expect(info.getByTestId('ci-copy')).toHaveAttribute('data-written', 'never');
  await noMissingKeys();
  await shot('R1-old-clip');
  await rw.click();
  await expect(page.locator('.toast.error')).toHaveCount(0);
  await expect.poll(() => Math.min(postLines('tiktok'), postLines('youtube')), { timeout: 240000, intervals: [2000] }).toBeGreaterThanOrEqual(3);
  for (const pf of ['tiktok', 'youtube']) expect(fs.readFileSync(path.join(exportsDir(), entry(pf)!.post!), 'utf8')).toMatch(/#Seattle/);
  await idle();
  await expect(info.getByTestId('ci-copy')).toHaveAttribute('data-written', 'rules', { timeout: 30000 });
  expect(tiktokMode()).toBe('pad-blur'); // the copy alone made no video again
  await shot('R2-copy-written');
});

test('Follow the subject re-makes only the vertical version, cropped', async () => {
  test.setTimeout(300000);
  const yt = path.join(exportsDir(), entry('youtube')!.file);
  const ytT = fs.statSync(yt).mtimeMs;
  await page.getByTestId('clip-info').getByTestId('ci-fill-follow').click();
  await expect(page.locator('.toast.error')).toHaveCount(0);
  await expect(page.getByTestId('ci-fill-follow')).toHaveAttribute('aria-pressed', 'true');
  await expect.poll(tiktokMode, { timeout: 240000, intervals: [2000] }).toBe('subject');
  const plan = JSON.parse(fs.readFileSync(path.join(exportsDir(), entry('tiktok')!.reframe.plan), 'utf8')) as { rects: number[][] | null; src_w: number };
  expect(plan.rects?.some((r) => r && r[2] < plan.src_w)).toBe(true);
  expect(fs.statSync(yt).mtimeMs).toBe(ytT); // the YouTube version untouched
  expect(fs.existsSync(path.join(project, 'items', 'main', 'work', 'vlog_master.shots.json'))).toBe(true);
  await idle();
  await shot('R3-follow');
});

test('the clip chat runs the framing setting instead of adding a 9:16 version', async () => {
  test.setTimeout(300000);
  await page.reload();
  await page.waitForURL(/^app:\/\/desk\//);
  await expect(page.getByTestId('chat-input')).toBeVisible({ timeout: 60000 });
  await page.getByTestId('chat-input').fill('竖屏用模糊背景填充，然后重新导出');
  await page.getByTestId('chat-input').press('Enter');
  await expect(page.getByTestId('chat-say').last()).toContainText('Making the vertical versions again', { timeout: 60000 });
  await expect(page.getByTestId('applied-card')).toHaveCount(0); // no 9:16 export added
  await expect.poll(tiktokMode, { timeout: 240000, intervals: [2000] }).toBe('pad-blur');
  await idle();
  await expect(page.getByTestId('clip-info').getByTestId('ci-fill')).toHaveAttribute('data-choice', 'blur', { timeout: 60000 });
  const doc = await api<{ exports?: { target: string }[] }>(`/api/outputs/${encodeURIComponent(id)}/${encodeURIComponent(clip)}`);
  expect((doc.exports ?? []).map((e) => e.target)).not.toContain('douyin:vertical');
  await noMissingKeys();
  await shot('R4-chat');
});
