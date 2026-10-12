// Import a finished video made elsewhere for second-pass editing, in the real app with the REAL engine sidecar (no
// mock engine), isolated temp profile, window hidden. The fixture (fixture/import_fixture.py) is a synthetic "export"
// folder - youtube.mp4 + douyin.mp4 + a cover + post.md - and the two camera clips it was cut from; the only fake is
// the transcriber (fixture/import_asr.py: what the video says). Dropped on Home with its footage:
//   - the composer says these are finished videos -> Import to edit -> the dialog lists the clip, its two platform
//     versions (cover, post copy) and the footage -> import -> the editor opens on the clip, on its words
//   - in the background its shots are found in the footage; another take of a shot is picked from stills (shot swap)
//   - a chat edit (rules, no AI account) applies and renders; a 3:4 version is added and rendered
//   - her files are never written
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

let app: ElectronApplication;
let page: Page;
let fx: { out: string; raw: string };
let item = '';
let clip = '';
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-import-'));
const REPO = path.resolve(import.meta.dirname, '../../../..');
const FIXTURE = path.join(import.meta.dirname, 'fixture');
const SHOTS = process.env.DESK_SHOTS_DIR ?? path.resolve(import.meta.dirname, '../../test-results/import');
fs.mkdirSync(SHOTS, { recursive: true });
const engineEnv = {
  VSTUDIO_HOME: path.join(tmp, 'vhome'),
  VSTUDIO_CACHE: path.join(tmp, 'vcache'),
  VSTUDIO_BATCH_BENCH: path.join(tmp, 'bench.json'),
  VSTUDIO_DEFAULT_PERSONA: '1',
  VSTUDIO_OUTPUT_TRANSCRIBER: `${path.join(FIXTURE, 'import_asr.py')}:words`,
  VSTUDIO_LLM_PROVIDER: 'none',
  ...Object.fromEntries(['SEGMENT_PLAN', 'PROOFREAD', 'GLOSSARY', 'COPY', 'SCRIPT', 'PLANNER', 'INTAKE', 'OUTPUT_EDIT', 'TRANSLATE'].map((t) => [`VSTUDIO_LLM_${t}_PROVIDER`, 'none'])),
};
const sha = (f: string) => execFileSync('shasum', [f], { encoding: 'utf8' }).split(' ')[0];
let before: Record<string, string> = {};

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  test.setTimeout(300000);
  const env: NodeJS.ProcessEnv = { ...process.env, ...engineEnv, PYTHONPATH: path.join(REPO, 'lib') };
  for (const k of ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'VSTUDIO_PERSONA']) delete env[k];
  const out = execFileSync(process.env.DESK_PYTHON || 'python3', [path.join(FIXTURE, 'import_fixture.py'), tmp], { env, encoding: 'utf8' });
  fx = JSON.parse(out.trim().split('\n').pop()!);
  before = Object.fromEntries(fs.readdirSync(fx.out).map((n) => [n, sha(path.join(fx.out, n))]));
  app = await electron.launch({
    args: [path.resolve(import.meta.dirname, '../..')],
    env: { ...env, PYTHONPATH: '', DESK_ENGINE_MOCK: '', DESK_USER_DATA: path.join(tmp, 'profile'), DESK_HISTORY_WATCH: '', DESK_HIDE_WINDOW: '1', DESK_SHARED_CACHE: path.join(tmp, 'cache'), DESK_HF_HUB: '', DESK_SKIP_FIRST_RUN: '1', VITE_DEV_SERVER_URL: '' },
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

const shot = (name: string) => page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
async function api<T>(p: string, body?: unknown): Promise<T> {
  return page.evaluate(
    async ([u, b]) => {
      const info = await window.desk.engineInfo();
      const r = await fetch(info.baseUrl + u, { method: b ? 'POST' : 'GET', headers: { Authorization: `Bearer ${info.token}`, 'Content-Type': 'application/json' }, body: b ? JSON.stringify(b) : undefined });
      return r.json();
    },
    [p, body] as const,
  ) as Promise<T>;
}
type Doc = { words: { w: string }[]; steps: { id: string }[]; speed: number; exports: { target: string }[]; imported: { shots: { i: number; source: string | null; swap: unknown }[] | null } | null };
const clipDoc = () => api<Doc>(`/api/outputs/${item}/${clip}`);
const dur = (f: string) => Number(execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f], { encoding: 'utf8' }).trim());

test('dropped finished videos -> Import to edit -> the editor opens on the clip, on its words', async () => {
  test.setTimeout(300000);
  // what she dropped on Home (the composer keeps its files in the session draft)
  await page.evaluate((files) => sessionStorage.setItem('v4.composer', JSON.stringify({ prompt: '', files })), [fx.out, fx.raw]);
  await page.evaluate(() => (location.hash = '#/home'));
  await page.reload();
  const hint = page.getByTestId('composer-import-hint');
  await expect(hint).toBeVisible({ timeout: 60000 });
  await expect(hint).toContainText('These look like 2 finished videos.');
  await shot('01-composer-hint');
  await hint.getByTestId('composer-import').click();
  const dlg = page.getByTestId('import-dialog');
  await expect(dlg).toHaveAttribute('data-verdict', 'mixed', { timeout: 60000 });
  await expect(page.getByTestId('import-summary')).toContainText('2 finished videos · 1 clip');
  await expect(page.getByTestId('import-clip')).toContainText('City lights from above');
  await expect(page.getByTestId('import-version')).toHaveCount(2);
  await expect(page.getByTestId('import-version').first()).toHaveAttribute('data-platform', 'youtube'); // international first
  await expect(page.getByTestId('import-footage')).toHaveAttribute('data-n', '2');
  await shot('02-import-dialog');
  await page.getByTestId('import-go').click();
  // the editor on the clip (the Studio's clip page), words first: transcribed in the background with the engine
  await expect(page.getByTestId('editor')).toBeVisible({ timeout: 120000 });
  const m = /#\/(?:studio|p)\/([0-9a-f]{12})(?:\/clip)?\/([^/?]+)/.exec(page.url());
  expect(m).not.toBeNull();
  [item, clip] = [m![1], decodeURIComponent(m![2])];
  expect(clip).toBe('01-city');
  await expect.poll(async () => (await clipDoc()).words.map((w) => w.w).join(' '), { timeout: 120000 }).toContain('city lights');
  await expect(page.locator('[data-testid=transcript-body] .w').first()).toBeVisible({ timeout: 60000 });
  // the shots are found in the footage, then listed on the page
  await expect(page.getByTestId('im-matched')).toBeVisible({ timeout: 180000 });
  await expect(page.getByTestId('im-matched')).toContainText('2 of 2 shots found in the footage');
  await shot('03-editor-imported');
  // her files: untouched, nothing written next to them
  for (const [n, h] of Object.entries(before)) expect(sha(path.join(fx.out, n))).toBe(h);
  expect(fs.existsSync(path.join(fx.out, '.vstudio'))).toBe(false);
  expect(fs.existsSync(path.join(fx.raw, '.vstudio'))).toBe(false);
});

test('another take of a shot from the footage (stills), undoable', async () => {
  test.setTimeout(300000);
  await page.locator('[data-testid=im-shot][data-shot="1"]').click();
  const takes = page.getByTestId('im-takes');
  await expect(takes.getByTestId('im-take').first()).toBeVisible({ timeout: 60000 });
  await expect(takes.locator('img').first()).toBeVisible();
  await shot('04-other-takes');
  await takes.getByTestId('im-take').first().click();
  await expect.poll(async () => (await clipDoc()).imported?.shots?.[1]?.swap ?? null, { timeout: 30000 }).not.toBeNull();
  await expect(page.locator('[data-testid=im-shot][data-shot="1"]')).toHaveAttribute('data-swapped', '1');
});

test('a chat edit applies and renders; a 3:4 version is made; a language version needs a model', async () => {
  test.setTimeout(400000);
  await page.getByTestId('studio-ai-input').fill('1.1倍速');
  await page.getByTestId('studio-ai-input').press('Enter');
  await expect(page.getByTestId('studio-ai-pane')).toBeVisible();
  const card = page.getByTestId('applied-card');
  await expect(card).toBeVisible({ timeout: 120000 });
  await expect.poll(async () => (await clipDoc()).speed, { timeout: 30000 }).toBe(1.1);
  await shot('05-chat-applied');
  if (await page.getByTestId('studio-ai-pane').isVisible()) await page.getByTestId('studio-ai-close').click();
  await page.getByTestId('ci-version-3:4').click();
  await expect.poll(async () => (await clipDoc()).exports.map((e) => e.target), { timeout: 30000 }).toContain('xiaohongshu:vertical');
  // the renders with both edits (the shot swap + the speed), primary and the new vertical version
  const r = await api<{ ok: boolean; targets: { target: string; file: string }[] }>(`/api/outputs/${item}/${clip}/render`, { quality: 'preview', targets: 'all' });
  const prim = r.targets.find((x) => x.target === 'primary');
  const vert = r.targets.find((x) => x.target === 'xiaohongshu:vertical');
  expect(prim && vert).toBeTruthy();
  expect(dur(prim!.file)).toBeLessThan(6 / 1.1 + 0.3);
  expect(execFileSync('ffprobe', ['-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', vert!.file], { encoding: 'utf8' }).trim()).toBe('1080,1440');
  // a language version: translating needs an AI account; without one it says so and nothing changes
  await page.getByTestId('im-lang').selectOption('zh');
  await page.getByTestId('im-lang-make').click();
  await expect(page.getByText('Translating needs an AI model')).toBeVisible({ timeout: 60000 });
  await shot('06-versions');
});
