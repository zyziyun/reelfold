// The editor brain on the REAL engine, seen (2026-10-12): the project page's "How it's cut" (template + why, the
// shot strip with "why this" and her change, the "Could be generated" cards), the Create spend gate for one idea,
// and the shot plan on the clip timeline (one block per shot of the builder's edit list, why + alternatives, the
// AI-generated shot) - in English and Chinese. Fixture: fixture/brain_project.py (a calm film made by the real engine
// on autopilot; one idea generated with the Create TEST STAND-IN provider, never a paid service).
//
// Screens go to BRAIN_SHOTS_DIR (default test-results/brain-screens). Nothing here presses "Generate".
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

let app: ElectronApplication;
let page: Page;
let id = '';
let dir = '';
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-brain-'));
const SHOTS = process.env.BRAIN_SHOTS_DIR ?? path.resolve(import.meta.dirname, '../../test-results/brain-screens');
fs.mkdirSync(SHOTS, { recursive: true });
const engineEnv = {
  VSTUDIO_HOME: path.join(tmp, 'vhome'),
  VSTUDIO_CACHE: path.join(tmp, 'vcache'),
  VSTUDIO_MUSIC_DIRS: '',
  VSTUDIO_BATCH_BENCH: path.join(tmp, 'bench.json'),
  VSTUDIO_DEFAULT_PERSONA: '1',
  VSTUDIO_LLM_PROVIDER: 'none',
  ...Object.fromEntries(['SEGMENT_PLAN', 'PROOFREAD', 'GLOSSARY', 'COPY', 'SCRIPT', 'PLANNER', 'INTAKE', 'OUTPUT_EDIT', 'EDIT', 'JUDGE'].map((t) => [`VSTUDIO_LLM_${t}_PROVIDER`, 'none'])),
};

type Hist = { items: { id: string; dir: string }[] };

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  test.setTimeout(600000);
  const env: NodeJS.ProcessEnv = { ...process.env, ...engineEnv, PYTHONPATH: path.join(path.resolve(import.meta.dirname, '../../../..'), 'lib') };
  for (const k of ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'VSTUDIO_PERSONA', 'KLING_MCP_TOKEN', 'MINIMAX_API_KEY', 'GEMINI_API_KEY']) delete env[k];
  const out = execFileSync(process.env.DESK_PYTHON || 'python3', [path.join(import.meta.dirname, 'fixture/brain_project.py'), tmp], { env, encoding: 'utf8', maxBuffer: 64 << 20 });
  const fx = JSON.parse(out.trim().split('\n').pop()!) as { dir: string; status2: string; placed?: { id: string } };
  expect(fx.status2).toBe('done');
  expect(fx.placed?.id).toBeTruthy();
  dir = fx.dir;
  app = await electron.launch({
    args: [path.resolve(import.meta.dirname, '../..')],
    env: { ...env, PYTHONPATH: '', DESK_STUDIO: '1', DESK_ENGINE_MOCK: '', DESK_USER_DATA: path.join(tmp, 'profile'), DESK_HISTORY_WATCH: '', DESK_HIDE_WINDOW: '1', DESK_SHARED_CACHE: path.join(tmp, 'cache'), DESK_HF_HUB: '', DESK_SKIP_FIRST_RUN: '1', VITE_DEV_SERVER_URL: '' },
  });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForURL(/^app:\/\/desk\//);
  await lang('en');
  expect((await page.evaluate(() => window.desk.engineInfo())).mode).toBe('real');
  await expect.poll(async () => (await api<Hist>('/api/history')).items.find((i) => fs.realpathSync(i.dir) === fs.realpathSync(dir))?.id ?? '', { timeout: 60000 }).not.toBe('');
  id = (await api<Hist>('/api/history')).items.find((i) => fs.realpathSync(i.dir) === fs.realpathSync(dir))!.id;
});

test.afterAll(async () => {
  await closeApp(app);
});

async function lang(l: 'en' | 'zh-CN') {
  await page.evaluate(async (x) => {
    localStorage.setItem('i18n.strict', '1');
    await window.desk.setSettings({ lang: x });
  }, l);
  await page.reload();
  await page.waitForURL(/^app:\/\/desk\//);
}
const hash = (h: string) => page.evaluate((x) => (location.hash = x), h);
const shot = (name: string) => page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
const api = <T,>(p: string, body?: unknown) =>
  page.evaluate(
    async ([u, b]) => {
      const info = await window.desk.engineInfo();
      const r = await fetch(info.baseUrl + u, { method: b === undefined ? 'GET' : 'POST', headers: { Authorization: `Bearer ${info.token}`, 'Content-Type': 'application/json' }, body: b === undefined ? undefined : JSON.stringify(b) });
      return r.json();
    },
    [p, body] as const,
  ) as Promise<T>;
const noMissingWords = () => expect(page.locator('body')).not.toContainText('⟦');

async function openPanel() {
  await hash(`#/p/${id}/clips`);
  const brain = page.getByTestId('brain');
  await expect(brain).toBeVisible({ timeout: 60000 });
  await expect(page.getByTestId('brain-template')).toBeVisible({ timeout: 120000 });
  await brain.scrollIntoViewIfNeeded();
  return brain;
}

async function screensOfThePanel(tag: string) {
  const brain = await openPanel();
  await page.evaluate(() => document.querySelector('[data-testid=brain]')?.scrollIntoView({ block: 'start' }));
  await noMissingWords();
  await shot(`B1-how-its-cut-${tag}`);
  // the shot strip: her change carries the "you" dot; a tile opens why this + the alternatives
  await brain.locator('summary').first().click();
  await expect(page.getByTestId('brain-strip')).toBeVisible();
  const her = page.locator('[data-testid^=brain-shot-]').filter({ has: page.locator('.dot.you') }).first();
  await expect(her).toBeVisible();
  await her.click();
  await expect(page.getByTestId('brain-why')).toBeVisible();
  await page.getByTestId('brain-strip').scrollIntoViewIfNeeded();
  await noMissingWords();
  await shot(`B2-shot-strip-why-${tag}`);
  await brain.locator('[data-testid=brain-strip]').screenshot({ path: path.join(SHOTS, `B2b-shot-strip-${tag}.png`) });
  // the ideas: one in the edit already (Take it out), one still an idea (Generate ≈ ¥X)
  const gen = page.getByTestId('brain-gen');
  await gen.scrollIntoViewIfNeeded();
  await expect(gen.locator('[data-state=placed]')).toHaveCount(1);
  await expect(gen.locator('[data-state=idea]').first()).toBeVisible();
  await gen.screenshot({ path: path.join(SHOTS, `B3-could-be-generated-${tag}.png`) });
  await shot(`B3b-could-be-generated-page-${tag}`);
}

test('How it is cut, the shot strip and the ideas (English)', async () => {
  test.setTimeout(240000);
  await screensOfThePanel('en');
});

test('the spend gate prices one idea; without the service connected it says so and sends nothing', async () => {
  test.setTimeout(120000);
  const gen = page.getByTestId('brain-gen');
  await gen.locator('[data-state=idea] [data-testid=brain-approve]').first().click();
  const gate = page.getByTestId('brain-gate');
  await expect(gate).toBeVisible();
  await expect(page.getByTestId('brain-gate-total')).toContainText('¥', { timeout: 60000 });
  await expect(page.getByTestId('brain-gate-blocked')).toContainText(/Kling.*not connected/);
  await expect(page.getByTestId('brain-gate-confirm')).toBeDisabled();
  await noMissingWords();
  await shot('B4-gate-not-connected-en');
  await page.getByTestId('brain-gate-cancel').click();
  await expect(gate).toHaveCount(0);
  expect(fs.existsSync(path.join(dir, 'state', 'brain', 'gen', 'spend.jsonl'))).toBe(true); // the stand-in's one take
  const led = fs.readFileSync(path.join(dir, 'state', 'brain', 'gen', 'spend.jsonl'), 'utf8').trim().split('\n');
  expect(led.length).toBe(1); // pricing in the gate added nothing
});

test('the shot plan on the clip timeline: why this, the alternatives, the AI shot (English)', async () => {
  test.setTimeout(240000);
  await timelineScreens('en');
});

test('the same in Chinese', async () => {
  test.setTimeout(300000);
  await lang('zh-CN');
  await screensOfThePanel('zh');
  await timelineScreens('zh');
});

async function timelineScreens(tag: string) {
  await hash(`#/p/${id}/clip/main`);
  await expect(page.getByTestId('editor')).toBeVisible({ timeout: 60000 });
  const tl = page.getByTestId('lower-pane');
  await expect(tl).toHaveAttribute('data-tab', 'timeline', { timeout: 30000 });
  const lane = page.getByTestId('tl-shots');
  await expect(lane).toBeVisible({ timeout: 60000 });
  await expect(page.getByTestId('tl-film')).toHaveAttribute('data-ready', '1', { timeout: 60000 });
  expect(await page.getByTestId('tl-shot').count()).toBeGreaterThanOrEqual(5);
  await noMissingWords();
  await shot(`B5-timeline-shots-${tag}`);
  await page.locator('[data-testid=tl-shot][data-brain="C2.S1"]').click();
  await expect(page.getByTestId('tl-shot-pop')).toBeVisible();
  await expect(page.locator('[data-testid=tl-shot-pop] [data-testid=brain-why]')).toBeVisible();
  await noMissingWords();
  await shot(`B6-timeline-why-${tag}`);
  await page.locator('[data-testid=tl-shot].ai').first().click();
  await expect(page.getByTestId('tl-shot-takeout')).toBeVisible();
  await noMissingWords();
  await shot(`B7-timeline-ai-shot-${tag}`);
  await page.locator('[data-testid=tl-shot-pop] .x').click();
}
