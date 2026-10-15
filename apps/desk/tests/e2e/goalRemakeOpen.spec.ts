// Regression: All projects opens after an older resize remake is linked to its collection.
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

let app: ElectronApplication;
let page: Page;
let fx: { goal: string; videos: Record<string, { en: string; zh: string }>; card: string };
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-goaledit-'));
const REPO = path.resolve(import.meta.dirname, '../../../..');
const engineEnv = {
  VSTUDIO_HOME: path.join(tmp, 'vhome'),
  VSTUDIO_CACHE: path.join(tmp, 'vcache'),
  VSTUDIO_MUSIC_DIRS: '',
  VSTUDIO_BATCH_BENCH: path.join(tmp, 'bench.json'),
  VSTUDIO_DEFAULT_PERSONA: '1',
  VSTUDIO_LLM_PROVIDER: 'none',
  ...Object.fromEntries(['SEGMENT_PLAN', 'PROOFREAD', 'GLOSSARY', 'COPY', 'SCRIPT', 'PLANNER', 'INTAKE', 'OUTPUT_EDIT', 'EDIT', 'JUDGE'].map((t) => [`VSTUDIO_LLM_${t}_PROVIDER`, 'none'])),
};

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  test.setTimeout(300000);
  const env: NodeJS.ProcessEnv = { ...process.env, ...engineEnv, PYTHONPATH: path.join(REPO, 'lib') };
  for (const k of ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'VSTUDIO_PERSONA']) delete env[k];
  const out = execFileSync(process.env.DESK_PYTHON || 'python3', [path.join(import.meta.dirname, 'fixture/goal_edit.py'), tmp, path.join(tmp, 'profile', 'engine-data')], { env, encoding: 'utf8' });
  fx = JSON.parse(out.trim().split('\n').pop()!);
  // Pre-fix linked remakes lack survey metadata, even on an otherwise finished collection.
  const gp = path.join(tmp, 'profile', 'engine-data', 'goals', `${fx.goal}.json`);
  const goal = JSON.parse(fs.readFileSync(gp, 'utf8'));
  goal.videos.push({id: 'remake-legacy', title: 'Needle remake 3:4', state: 'you', stories: null, platforms: null, clips: null, projects: []});
  fs.writeFileSync(gp, JSON.stringify(goal));
  app = await electron.launch({
    args: [path.resolve(import.meta.dirname, '../..')],
    env: { ...env, PYTHONPATH: '', DESK_STUDIO: '1', DESK_ENGINE_MOCK: '', DESK_USER_DATA: path.join(tmp, 'profile'), DESK_HISTORY_WATCH: '', DESK_HIDE_WINDOW: '1', DESK_SHARED_CACHE: path.join(tmp, 'cache'), DESK_HF_HUB: '', DESK_SKIP_FIRST_RUN: '1', VITE_DEV_SERVER_URL: '' },
  });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 1000 });
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


test('All projects and collection open with a legacy remake lacking survey metadata', async () => {
  const errors: string[] = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.getByRole('link', { name: 'All projects', exact: true }).click();
  await expect(page.getByTestId('studio')).toBeVisible({timeout:30000});
  await expect(page.locator('.st-list')).toContainText('Needle remake 3:4');
  await page.evaluate(id => { location.hash = `#/studio?goal=${id}`; }, fx.goal);
  await expect(page.getByTestId('goal-page')).toBeVisible();
  await expect(page.getByTestId('goal-page')).toContainText('Needle remake 3:4');
  expect(errors).toEqual([]);
});
