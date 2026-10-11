// Runs the app with the Studio off (DESK_STUDIO=0, the Inbox page), the REAL engine sidecar, an isolated temp profile,
// window hidden. Dogfood 2026-10-11: her course explainer (Chinese narration, autopilot, no OpenAI key) stopped at the
// voice with a raw "OPENAI_API_KEY is not set in the environment" traceback. fixture/voice_project.py makes that
// project (approved for OpenAI, then the voice ran without the key) and an Ask-me-first one waiting at the voice; a
// test-only sitecustomize says this computer has the free voice (Kokoro) and records each take instead of making it.
//   - the failure names the service and the fix (never the env var / a traceback), with "Add a key" and Try again;
//   - Try again recovers it on autopilot: the free Mandarin voice, the decision recorded;
//   - Ask me first: "No OpenAI key for the voice" offers the free voice and Settings › AI; the free voice goes on.
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

let app: ElectronApplication;
let page: Page;
let fx: { course: string; asking: string; hook: string; log: string; exit: number; pending: string[][] };
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-voicekey-'));
const REPO = path.resolve(import.meta.dirname, '../../../..');
const engineEnv = {
  VSTUDIO_HOME: path.join(tmp, 'vhome'),
  VSTUDIO_BATCH_BENCH: path.join(tmp, 'bench.json'),
  VSTUDIO_DEFAULT_PERSONA: '1',
  VSTUDIO_LLM_PROVIDER: 'none',
  ...Object.fromEntries(['SEGMENT_PLAN', 'PROOFREAD', 'GLOSSARY', 'COPY', 'SCRIPT', 'PLANNER', 'INTAKE', 'OUTPUT_EDIT'].map((t) => [`VSTUDIO_LLM_${t}_PROVIDER`, 'none'])),
};

type Take = { engine: string; voice: string | null; out: string };
const takes = (): Take[] =>
  fs.existsSync(fx.log)
    ? fs
        .readFileSync(fx.log, 'utf8')
        .split('\n')
        .filter(Boolean)
        .map((l) => JSON.parse(l) as Take)
    : [];
/** the first take recorded for a project (its folder, as given or as the real path: /var -> /private/var) */
const firstTake = (dir: string) => {
  const roots = [dir, fs.realpathSync(dir)];
  const x = takes().find((t) => roots.some((r) => t.out.startsWith(r + path.sep)));
  return x ? `${x.engine}:${x.voice}` : undefined;
};
/** project.yaml as text: one item, one voice answer */
const answer = (dir: string) => fs.readFileSync(path.join(dir, 'project.yaml'), 'utf8');

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  test.setTimeout(300000);
  const env: NodeJS.ProcessEnv = { ...process.env, ...engineEnv, PYTHONPATH: path.join(REPO, 'lib') };
  for (const k of ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'VSTUDIO_PERSONA', 'VSTUDIO_TTS_ENGINE']) delete env[k];
  const out = execFileSync(process.env.DESK_PYTHON || 'python3', [path.join(import.meta.dirname, 'fixture/voice_project.py'), tmp], { env, encoding: 'utf8' });
  fx = JSON.parse(out.trim().split('\n').pop()!);
  expect(fx.exit).toBe(1);
  expect(fx.pending).toEqual([['ep1', 'voice']]);
  app = await electron.launch({
    args: [path.resolve(import.meta.dirname, '../..')],
    env: {
      ...env,
      PYTHONPATH: fx.hook,
      VOICEKEY_LOG: fx.log,
      VOICEKEY_FREE: 'kokoro',
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

test('Ask me first: a plain "no OpenAI key" question, Settings for the key, the free voice goes on', async () => {
  test.setTimeout(240000);
  await hash('#/inbox');
  const item = page.getByTestId('inbox-item').filter({ hasText: 'No OpenAI key for the voice' });
  await expect(item).toHaveCount(1, { timeout: 60000 });
  await item.click();
  const pane = page.getByTestId('inbox-preview');
  await expect(pane).toHaveAttribute('data-kind', 'voice-pick');
  await expect(pane).toContainText('there’s no OpenAI key in Reelfold');
  await expect(page.getByTestId('inbox-no-key')).toContainText('The free voice on this computer reads the script (zf_xiaobei)');
  await expect(pane).not.toContainText('OPENAI_API_KEY');
  await page.getByTestId('no-key-add').click();
  await expect.poll(() => page.evaluate(() => location.hash)).toBe('#/settings/ai/openai');
  await expect(page.getByTestId('provider-openai').first()).toBeVisible();
  await hash('#/inbox');
  await page.getByTestId('inbox-item').filter({ hasText: 'No OpenAI key for the voice' }).click();
  await page.getByTestId('no-key-free').click();
  // the answer is the free voice; the run goes on and makes the voice with it (recorded by the test hook)
  await expect.poll(() => firstTake(fx.asking), { timeout: 120000 }).toBe('kokoro:zf_xiaobei');
  expect(answer(fx.asking)).toContain('engine: kokoro');
});

test('her project: the failure names the key, and Try again makes the voice with the free voice', async () => {
  test.setTimeout(240000);
  await hash('#/inbox');
  const item = page.getByTestId('inbox-item').filter({ hasText: 'MCP course' });
  await expect(item).toHaveCount(1, { timeout: 60000 });
  await expect(item.getByTestId('inbox-failed-reason')).toContainText('There’s no OpenAI key in Reelfold');
  await item.click();
  const pane = page.getByTestId('inbox-preview');
  await expect(pane).toContainText('Press Try again to make the voice with the free voice on this computer');
  await expect(pane).not.toContainText('OPENAI_API_KEY');
  await expect(pane).not.toContainText('Traceback');
  await expect(page.getByTestId('fail-add-key')).toHaveText('Add your OpenAI key');
  await page.getByTestId('fail-retry').click();
  await expect.poll(() => firstTake(fx.course), { timeout: 180000 }).toBe('kokoro:zf_xiaobei');
  const a = answer(fx.course);
  expect(a).toContain('reason_code: free-voice');
  expect(a).toContain('used the free local voice — no OpenAI key');
});
