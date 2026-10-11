// Her MCP course (2026-10-11): Claude Code timed out, the scenes fell back to the rules and the autopilot rendered a
// 5:34 video of text lines. REAL engine sidecar, isolated temp profile, window hidden; fixture/explainer_project.py
// makes two explainer projects on autopilot with stand-ins for Claude Code, the renderer and the voice only:
//   - Needs you: the scenes step stops with "The visuals need an AI model — Claude Code didn’t answer" (Try again,
//     Settings › AI), nothing rendered; Try again draws them, Accept renders the video;
//   - a finished explainer whose scenes are text lines: "Redo the visuals" on its clip page - first while the model
//     does not answer (the failure in her words, the old video kept), then with it: every scene drawn again, render
//     and exports again, the narration untouched; the clip chat's 「画面太素了」 does the same.
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

let app: ElectronApplication;
let page: Page;
let fx: { needs: string; plain: string; bin: string; hook: string; needs_exit: number; plain_exit: number; needs_pending: string[]; rendered: boolean };
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-visuals-'));
const REPO = path.resolve(import.meta.dirname, '../../../..');
const SHOTS = process.env.DESK_SHOTS_DIR ?? path.resolve(import.meta.dirname, '../../test-results/explainer-visuals');
fs.mkdirSync(SHOTS, { recursive: true });
const engineEnv = {
  VSTUDIO_HOME: path.join(tmp, 'vhome'),
  VSTUDIO_BATCH_BENCH: path.join(tmp, 'bench.json'),
  VSTUDIO_DEFAULT_PERSONA: '1',
  VSTUDIO_MUSIC_DIRS: '',
  VSTUDIO_CLI_EXTRA_DIRS: '',
  VSTUDIO_LLM_PROVIDER: 'none',
  ...Object.fromEntries(['SEGMENT_PLAN', 'PROOFREAD', 'GLOSSARY', 'COPY', 'SCRIPT', 'INTAKE', 'OUTPUT_EDIT'].map((t) => [`VSTUDIO_LLM_${t}_PROVIDER`, 'none'])),
  VSTUDIO_LLM_PLANNER_PROVIDER: 'claude-code', // her route: Claude Code (the test stand-in in ROOT/bin)
};

const item = (dir: string) => path.join(dir, 'items', 'ep1');
const renders = (dir: string) =>
  fs.existsSync(path.join(tmp, 'renders.log'))
    ? fs
        .readFileSync(path.join(tmp, 'renders.log'), 'utf8')
        .split('\n')
        .filter((l) => l && l.includes(fs.realpathSync(dir))).length
    : 0;
const aiScenes = (dir: string) => {
  const c = path.join(item(dir), 'compositions');
  const fs_ = fs.readdirSync(c).filter((f) => f.endsWith('.html') && f !== 'captions.html');
  return fs_.length > 0 && fs_.every((f) => fs.readFileSync(path.join(c, f), 'utf8').startsWith('<!-- reelfold:scene by=ai -->'));
};
const down = (on: boolean) => (on ? fs.writeFileSync(path.join(tmp, 'claude-down'), '') : fs.rmSync(path.join(tmp, 'claude-down'), { force: true }));

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  test.setTimeout(420000);
  const env: NodeJS.ProcessEnv = { ...process.env, ...engineEnv, PYTHONPATH: path.join(REPO, 'lib') };
  for (const k of ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'VSTUDIO_PERSONA', 'VSTUDIO_TTS_ENGINE']) delete env[k];
  const out = execFileSync(process.env.DESK_PYTHON || 'python3', [path.join(import.meta.dirname, 'fixture/explainer_project.py'), tmp], { env, encoding: 'utf8', timeout: 400000 });
  fx = JSON.parse(out.trim().split('\n').pop()!);
  expect(fx.needs_exit).toBe(7); // waiting for her
  expect(fx.needs_pending).toEqual(['scenes']);
  expect(fs.existsSync(path.join(item(fx.needs), 'renders'))).toBe(false); // never a text-only video
  expect(fx.plain_exit).toBe(0);
  expect(fx.rendered).toBe(true);
  app = await electron.launch({
    args: [path.resolve(import.meta.dirname, '../..')],
    env: {
      ...env,
      PYTHONPATH: fx.hook, // pins the stand-ins for Claude Code and the renderer (the app's own bin folders come first)
      EXPLAINER_FAKE_BIN: fx.bin,
      VSTUDIO_SCENE_LINT: '0',
      DESK_STUDIO: '0',
      DESK_ENGINE_MOCK: '',
      DESK_USER_DATA: path.join(tmp, 'profile'),
      DESK_HISTORY_WATCH: '',
      DESK_HIDE_WINDOW: '1',
      DESK_SHARED_CACHE: path.join(tmp, 'cache'),
      DESK_HF_HUB: '',
      DESK_SKIP_FIRST_RUN: '1',
      VITE_DEV_SERVER_URL: '',
    },
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
});

test.afterAll(async () => {
  await closeApp(app);
});

const hash = (h: string) => page.evaluate((x) => (location.hash = x), h);
const shot = (name: string) => page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
const api = <T,>(p: string, method = 'GET', body?: unknown) =>
  page.evaluate(
    async ([u, m, b]) => {
      const info = await window.desk.engineInfo();
      const r = await fetch(info.baseUrl + u, { method: m, headers: { Authorization: `Bearer ${info.token}`, 'Content-Type': 'application/json' }, body: b ? JSON.stringify(b) : undefined });
      return r.json();
    },
    [p, method, body] as const,
  ) as Promise<T>;
const idOf = async (dir: string) => {
  const find = async () => (await api<{ items: { id: string; dir: string }[] }>('/api/history')).items.find((i) => fs.realpathSync(i.dir) === fs.realpathSync(dir))?.id ?? '';
  await expect.poll(find, { timeout: 60000 }).not.toBe('');
  return find();
};
const idle = (id: string) =>
  expect.poll(async () => (await api<{ running: boolean; queued: number | null }>(`/api/autopilot/${encodeURIComponent(id)}`)).running, { timeout: 240000, intervals: [1500] }).toBe(false);
const noMissingKeys = async () => {
  const text = await page.evaluate(() => document.body.innerText);
  expect(text.match(/⟦[^⟧]+⟧/g) ?? []).toEqual([]);
};

test('Needs you: the visuals need an AI model; Try again draws them and Accept makes the video', async () => {
  test.setTimeout(300000);
  await hash('#/inbox');
  const row = page.getByTestId('inbox-item').filter({ hasText: 'Check the scenes' });
  await expect(row).toHaveCount(1, { timeout: 60000 });
  await row.click();
  const nm = page.getByTestId('draft-needs-model');
  await expect(nm).toContainText('The visuals need an AI model — Claude Code didn’t answer. Try again, or choose another model in Settings › AI.');
  await expect(page.getByTestId('draft-error')).toHaveCount(0); // her words, not the raw error
  await expect(page.getByTestId('draft-needs-model-ai')).toBeVisible();
  await noMissingKeys();
  await shot('V1-needs-model');
  await page.getByTestId('draft-needs-model-retry').click(); // the model answers now
  await expect.poll(() => aiScenes(fx.needs), { timeout: 120000, intervals: [1000] }).toBe(true);
  await expect(page.getByTestId('draft-needs-model')).toHaveCount(0, { timeout: 60000 });
  await expect(page.getByTestId('draft-summary')).toBeVisible({ timeout: 60000 });
  await shot('V2-scenes-drawn');
  await page.getByTestId('inbox-confirm').click();
  await expect.poll(() => renders(fx.needs), { timeout: 240000, intervals: [2000] }).toBe(1);
  await expect.poll(() => fs.existsSync(path.join(item(fx.needs), 'exports', 'manifest.json')), { timeout: 240000, intervals: [2000] }).toBe(true);
});

test('Redo the visuals: no model -> said plainly, the old video kept; then every scene drawn again, voice kept', async () => {
  test.setTimeout(400000);
  const id = await idOf(fx.plain);
  const outs = await api<{ clips: { id: string }[] }>(`/api/outputs/${encodeURIComponent(id)}`);
  const clip = outs.clips[0].id;
  await hash(`#/p/${id}/clip/${encodeURIComponent(clip)}`);
  await expect(page.getByTestId('editor')).toBeVisible({ timeout: 60000 });
  const vis = page.getByTestId('ci-visuals').first();
  await expect(vis).toBeVisible({ timeout: 30000 });
  await expect(vis).toHaveAttribute('data-by', 'rules');
  await noMissingKeys();
  await shot('V3-clip-redo-visuals');
  const nar = path.join(item(fx.plain), 'audio', 'narration.wav');
  const narT = fs.statSync(nar).mtimeMs;
  const before = renders(fx.plain);
  // the model does not answer: the failure in her words, nothing rendered again
  down(true);
  await vis.getByTestId('ci-visuals-redo').click();
  await expect(page.getByTestId('toast').filter({ hasText: 'The visuals need an AI model — Claude Code didn’t answer' })).toBeVisible({ timeout: 180000 });
  expect(renders(fx.plain)).toBe(before);
  expect(aiScenes(fx.plain)).toBe(false);
  const fail = (await api<{ failure: { code: string } | null }>(`/api/autopilot/${encodeURIComponent(id)}`)).failure;
  expect(fail?.code).toBe('ai-needs-model');
  await shot('V4-redo-no-model');
  // the model answers: every scene drawn again, render + exports again, the voice untouched
  down(false);
  await expect(vis.getByTestId('ci-visuals-redo')).toBeEnabled({ timeout: 30000 });
  await vis.getByTestId('ci-visuals-redo').click();
  await expect(page.getByTestId('ci-visuals').first()).toHaveAttribute('data-busy', '1', { timeout: 30000 });
  await expect.poll(() => renders(fx.plain), { timeout: 240000, intervals: [2000] }).toBe(before + 1);
  await idle(id);
  expect(aiScenes(fx.plain)).toBe(true);
  expect(fs.statSync(nar).mtimeMs).toBe(narT);
  await expect(page.getByTestId('toast').filter({ hasText: 'The visuals are redrawn' })).toBeVisible({ timeout: 60000 });
  await expect(page.getByTestId('ci-visuals').first()).toHaveAttribute('data-by', 'ai', { timeout: 60000 });
  await shot('V5-redrawn');
});

test('the clip chat: 「画面太素了」 redoes the visuals', async () => {
  test.setTimeout(400000);
  const id = await idOf(fx.plain);
  const before = renders(fx.plain);
  await page.reload();
  await page.waitForURL(/^app:\/\/desk\//);
  await expect(page.getByTestId('chat-input')).toBeVisible({ timeout: 60000 });
  await page.getByTestId('chat-input').fill('画面太素了，重新设计一下，多一些图解');
  await page.getByTestId('chat-input').press('Enter');
  await expect(page.getByTestId('chat-say').last()).toContainText('Drawing the visuals again', { timeout: 60000 });
  await expect(page.getByTestId('applied-card')).toHaveCount(0); // no edit guessed
  await expect.poll(() => renders(fx.plain), { timeout: 240000, intervals: [2000] }).toBe(before + 1);
  await idle(id);
  await noMissingKeys();
  await shot('V6-chat');
});

// her MCP course again (2026-10-11): after ~22 min the redo stopped on "1 of 14 scenes could not be drawn
// (f14-mcp-a2a: remove fetch())", nothing was rendered and the finished course fell into Needs you as "The first clip
// stopped" with a Confirm button. Now the brief forbids the network, the repair round names the fix, a scene that
// still calls fetch() keeps its old version while the others are redrawn and rendered, and a redo that drew nothing
// is a notice on the Ready clip with Try again (only the missing scenes).
const sceneIds = (dir: string) => (JSON.parse(fs.readFileSync(path.join(item(dir), 'scenes.config.json'), 'utf8')) as { scenes: { id: string }[] }).scenes.map((s) => s.id);
const fetchy = (ids: string[]) => (ids.length ? fs.writeFileSync(path.join(tmp, 'claude-fetch'), ids.join('\n')) : fs.rmSync(path.join(tmp, 'claude-fetch'), { force: true }));
const sceneCalls = () =>
  fs
    .readFileSync(path.join(tmp, 'claude.log'), 'utf8')
    .split('\n')
    .filter(Boolean)
    .map((l) => JSON.parse(l) as { kind: string; scene: string | null; offline?: boolean; fetch_fix?: boolean })
    .filter((x) => x.kind === 'scene');
const projectRow = async (dir: string) =>
  (await api<{ items: { dir: string; status?: string; failure?: unknown; remake_failure?: { code: string } }[] }>('/api/history')).items.find((i) => fs.realpathSync(i.dir) === fs.realpathSync(dir))!;

test('a scene that keeps calling fetch() is kept as before; the other is redrawn and rendered; Redraw scene 2', async () => {
  test.setTimeout(500000);
  const id = await idOf(fx.plain);
  const [s1, s2] = sceneIds(fx.plain);
  const comp = path.join(item(fx.plain), 'compositions');
  const old2 = fs.readFileSync(path.join(comp, `${s2}.html`), 'utf8');
  const calls0 = sceneCalls().length;
  const before = renders(fx.plain);
  const outs = await api<{ clips: { id: string }[] }>(`/api/outputs/${encodeURIComponent(id)}`);
  await hash(`#/p/${id}/clip/${encodeURIComponent(outs.clips[0].id)}`);
  await expect(page.getByTestId('editor')).toBeVisible({ timeout: 60000 });
  fetchy([s2]);
  const vis = page.getByTestId('ci-visuals').first();
  await expect(vis.getByTestId('ci-visuals-redo')).toBeEnabled({ timeout: 30000 });
  await vis.getByTestId('ci-visuals-redo').click();
  await expect.poll(() => renders(fx.plain), { timeout: 300000, intervals: [2000] }).toBe(before + 1); // made anyway
  await idle(id);
  const calls = sceneCalls().slice(calls0);
  expect(calls.every((c) => c.offline)).toBe(true); // the network is forbidden up front
  expect(calls.filter((c) => c.scene === s2).length).toBe(3); // the first answer + two targeted repairs
  expect(calls.some((c) => c.scene === s2 && c.fetch_fix)).toBe(true); // the exact finding and its fix fed back
  expect(fs.readFileSync(path.join(comp, `${s2}.html`), 'utf8')).toBe(old2); // kept as before
  expect(fs.readFileSync(path.join(comp, `${s1}.html`), 'utf8')).toContain('reelfold:scene by=ai');
  const kept = page.getByTestId('ci-visuals-kept');
  await expect(kept).toContainText('1 of 2 scenes redrawn; scene 2 kept as before', { timeout: 60000 });
  await expect(page.getByTestId('toast').filter({ hasText: '1 of 2 scenes redrawn; scene 2 kept as before' })).toBeVisible({ timeout: 60000 });
  const row = await projectRow(fx.plain);
  expect(row.status).not.toBe('failed');
  expect(row.failure ?? null).toBeNull();
  await noMissingKeys();
  await shot('V7-scene-kept');
  // the model draws it now: "Redraw scene 2" asks for that one only
  fetchy([]);
  const calls1 = sceneCalls().length;
  await kept.getByTestId('ci-visuals-redraw-missing').click();
  await expect.poll(() => renders(fx.plain), { timeout: 300000, intervals: [2000] }).toBe(before + 2);
  await idle(id);
  expect([...new Set(sceneCalls().slice(calls1).map((c) => c.scene))]).toEqual([s2]);
  expect(fs.readFileSync(path.join(comp, `${s2}.html`), 'utf8')).toContain('reelfold:scene by=ai');
  await expect(page.getByTestId('ci-visuals-kept')).toHaveCount(0, { timeout: 60000 });
});

test('a redo that drew no scene: which and why on the Ready clip, Try again draws only the missing ones', async () => {
  test.setTimeout(500000);
  const id = await idOf(fx.plain);
  const ids = sceneIds(fx.plain);
  const before = renders(fx.plain);
  await page.reload();
  await page.waitForURL(/^app:\/\/desk\//);
  fetchy(ids);
  const vis = page.getByTestId('ci-visuals').first();
  await expect(vis.getByTestId('ci-visuals-redo')).toBeEnabled({ timeout: 60000 });
  await vis.getByTestId('ci-visuals-redo').click();
  const note = page.getByTestId('ci-visuals-failed');
  await expect(note).toContainText('2 of 2 scenes couldn’t be redrawn: the AI kept loading data from the internet, which a video can’t do. Your video is unchanged', { timeout: 300000 });
  await expect(note).toHaveAttribute('data-code', 'stage-visuals-failed');
  await expect(note.getByTestId('ci-visuals-retry')).toHaveClass(/primary/);
  expect(renders(fx.plain)).toBe(before);
  // Ready with a notice: never Needs you, no "first clip stopped" card
  const row = await projectRow(fx.plain);
  expect(row.status).not.toBe('failed');
  expect(row.remake_failure?.code).toBe('stage-visuals-failed');
  const inbox = await api<{ items: { kind: string; project: { id: string | null } }[] }>('/api/inbox');
  expect(inbox.items.filter((x) => x.kind === 'failed' && x.project.id === id)).toEqual([]);
  await noMissingKeys();
  await shot('V8-redo-failed-notice');
  fetchy([]);
  const calls1 = sceneCalls().length;
  await note.getByTestId('ci-visuals-retry').click();
  await expect.poll(() => renders(fx.plain), { timeout: 300000, intervals: [2000] }).toBe(before + 1);
  await idle(id);
  expect(sceneCalls().slice(calls1).length).toBe(ids.length); // the missing ones, once each
  await expect(page.getByTestId('ci-visuals-failed')).toHaveCount(0, { timeout: 60000 });
  await expect(page.getByTestId('toast').filter({ hasText: 'The visuals are redrawn' })).toBeVisible({ timeout: 60000 });
});
