// Found while recording the promo (2026-10-12) on a realistic profile, here with the REAL engine sidecar (no mock
// engine), isolated temp profile, window hidden, the Studio on. Two tiny synthetic talks (fixture/real_project.py:
// tone-burst words + the engine tests' fake transcriber, the only fakes), each parked at a filler question:
//   * "Review in a row" walked only the first project's clips: it walks every waiting review, every project's, in the
//     Inbox's order, with "1 of 2" on top
//   * the run page of a request on autopilot: "Plan ready" for a second, then a skeleton (and once an unrelated
//     clip) - it stays on the request and moves on into its project's making
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

let app: ElectronApplication;
let page: Page;
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-promofix-'));
const REPO = path.resolve(import.meta.dirname, '../../../..');
const SHOTS = process.env.DESK_SHOTS_DIR ?? path.resolve(import.meta.dirname, '../../test-results/promo-fixes');
fs.mkdirSync(SHOTS, { recursive: true });
const engineEnv = {
  VSTUDIO_HOME: path.join(tmp, 'vhome'),
  VSTUDIO_BATCH_BENCH: path.join(tmp, 'bench.json'),
  VSTUDIO_DEFAULT_PERSONA: '1',
  VSTUDIO_TEST_TRUTH: path.join(tmp, 'a', 'truth.json'),
  VSTUDIO_LLM_PROVIDER: 'none',
  ...Object.fromEntries(['SEGMENT_PLAN', 'PROOFREAD', 'GLOSSARY', 'COPY', 'SCRIPT', 'PLANNER', 'INTAKE', 'OUTPUT_EDIT'].map((t) => [`VSTUDIO_LLM_${t}_PROVIDER`, 'none'])),
};
const ids = { a: '', b: '' };
const dirs = { a: '', b: '' };

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  test.setTimeout(400000);
  const env: NodeJS.ProcessEnv = { ...process.env, ...engineEnv, PYTHONPATH: path.join(REPO, 'lib') };
  for (const k of ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'VSTUDIO_PERSONA']) delete env[k];
  for (const [k, name] of [['a', 'Short talk'], ['b', 'Second talk']] as const) {
    const out = execFileSync(process.env.DESK_PYTHON || 'python3', [path.join(import.meta.dirname, 'fixture/real_project.py'), path.join(tmp, k), '--name', name], { env, encoding: 'utf8' });
    const fx = JSON.parse(out.trim().split('\n').pop()!) as { dir: string; pending: string[][] };
    expect(fx.pending).toEqual([['talk', 'filler']]);
    dirs[k] = fx.dir;
  }
  app = await electron.launch({
    args: [path.resolve(import.meta.dirname, '../..')],
    env: { ...env, PYTHONPATH: '', DESK_STUDIO: '1', DESK_ENGINE_MOCK: '', DESK_USER_DATA: path.join(tmp, 'profile'), DESK_HISTORY_WATCH: '', DESK_HIDE_WINDOW: '1', DESK_SHARED_CACHE: path.join(tmp, 'cache'), DESK_HF_HUB: '', DESK_SKIP_FIRST_RUN: '1', VITE_DEV_SERVER_URL: '' },
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
  const find = async (d: string) => (await api<{ items: { id: string; dir: string }[] }>('/api/history')).items.find((i) => fs.realpathSync(i.dir) === fs.realpathSync(d))?.id ?? '';
  for (const k of ['a', 'b'] as const) {
    await expect.poll(() => find(dirs[k]), { timeout: 60000 }).not.toBe('');
    ids[k] = await find(dirs[k]);
  }
});

test.afterAll(async () => {
  await closeApp(app);
});

const hash = (h: string) => page.evaluate((x) => (location.hash = x), h);
const shot = (name: string) => page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
function api<T>(p: string, body?: unknown): Promise<T> {
  return page.evaluate(
    async ([u, b]) => {
      const info = await window.desk.engineInfo();
      const r = await fetch(info.baseUrl + u, {
        method: b === undefined ? 'GET' : 'POST',
        headers: { Authorization: `Bearer ${info.token}`, 'Content-Type': 'application/json' },
        body: b === undefined ? undefined : JSON.stringify(b),
      });
      return r.json();
    },
    [p, body] as const,
  ) as Promise<T>;
}
type Inbox = { items: { key: string; kind: string; project: { id: string | null } }[] };
const reviews = async () => (await api<Inbox>('/api/inbox')).items.filter((x) => x.kind === 'review' || x.kind === 'publish');

test('review in a row walks every project’s waiting reviews, "1 of 2" across both', async () => {
  test.setTimeout(400000);
  // both fillers answered on their pages: each project runs on to its review before publishing
  for (const k of ['a', 'b'] as const) {
    await hash('#/studio?f=you');
    const row = page.locator(`[data-testid=studio-row][data-row="${ids[k]}/talk"]`);
    await expect(row).toHaveAttribute('data-group', 'you', { timeout: 60000 });
    await row.click();
    await expect(page.getByTestId('inbox-preview')).toHaveAttribute('data-kind', 'filler-confirm', { timeout: 30000 });
    await page.getByTestId('inbox-confirm').click();
    await expect(page.locator('.toast.error')).toHaveCount(0);
  }
  await expect.poll(async () => new Set((await reviews()).map((x) => x.project.id)).size, { timeout: 240000, intervals: [2000] }).toBe(2);
  const order = (await reviews()).map((x) => x.project.id);
  await hash('#/studio?f=you');
  // the list has both reviews (the Inbox the app holds has caught up with the engine's)
  for (const k of ['a', 'b'] as const) await expect(page.locator(`[data-testid=studio-row][data-row="${ids[k]}/talk"]`)).toContainText(/review/i, { timeout: 60000 });
  await page.getByTestId('studio-in-row').click();
  const count = page.getByTestId('triage-count');
  await expect(count).toHaveText('1 of 2', { timeout: 30000 });
  expect(await page.evaluate(() => location.hash)).toContain(order[0]!);
  await shot('F1-review-row-1');
  await page.getByTestId('triage-next').click();
  await expect(count).toHaveText('2 of 2', { timeout: 30000 });
  expect(await page.evaluate(() => location.hash)).toContain(order[1]!);
  await shot('F2-review-row-2');
  await page.getByTestId('triage-back').click();
});

test('a request on autopilot stays on its run page and moves on into its project, never a skeleton or another video', async () => {
  test.setTimeout(300000);
  const talk = path.join(tmp, 'a', 'media', 'talk.mp4');
  expect(fs.existsSync(talk)).toBe(true);
  const { id: rid } = await api<{ id: string }>('/api/intake', { prompt: 'Cut this talk into a short clip', inputs: [talk], mode: 'autopilot', lang: 'en' });
  // watch the page while it plans, applies and starts: record every moment it showed a skeleton or another row
  await page.evaluate(() => {
    const w = window as unknown as { seen: string[] };
    w.seen = [];
    const note = () => {
      const pg = document.querySelector('[data-testid=studio-page]');
      if (pg?.querySelector('[data-testid=studio-page-skeleton]')) w.seen.push('skeleton');
      w.seen.push(location.hash);
    };
    new MutationObserver(note).observe(document.body, { subtree: true, childList: true, attributes: true });
  });
  await hash(`#/studio?sel=${rid}`);
  await expect(page.locator('[data-testid=hub-request]')).toBeVisible({ timeout: 30000 });
  // the plan is made into its project at once: the page moves on to that project (its address too)
  await expect.poll(async () => (await api<{ applied?: { dir: string }[] }>(`/api/intake/${rid}`)).applied?.length ?? 0, { timeout: 180000, intervals: [1000] }).toBeGreaterThan(0);
  const dir = (await api<{ applied: { dir: string }[] }>(`/api/intake/${rid}`)).applied[0].dir;
  await expect.poll(async () => (await api<{ items: { id: string; dir: string }[] }>('/api/history')).items.find((i) => fs.realpathSync(i.dir) === fs.realpathSync(dir))?.id ?? '', { timeout: 60000 }).not.toBe('');
  const pid = (await api<{ items: { id: string; dir: string }[] }>('/api/history')).items.find((i) => fs.realpathSync(i.dir) === fs.realpathSync(dir))!.id;
  await expect.poll(() => page.evaluate(() => location.hash), { timeout: 60000 }).toContain(pid);
  await page.waitForTimeout(1500);
  await shot('F3-request-into-project');
  const seen = await page.evaluate(() => (window as unknown as { seen: string[] }).seen);
  // only the request's address and then its project's, never another video's in between
  const from = seen.findIndex((h) => h.includes(rid));
  expect(from).toBeGreaterThanOrEqual(0);
  const after = seen.slice(from);
  expect(after).not.toContain('skeleton');
  expect(after.filter((h) => h !== 'skeleton' && !h.includes(rid) && !h.includes(pid))).toEqual([]);
});
