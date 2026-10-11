// All projects at scale with the REAL engine sidecar (no mock engine), isolated temp profile, window hidden, the
// Studio on: 220 script projects (fixture/many_projects.py, registered the way the desk's own projects are) - the
// list, its search, ⌘A over every row, J / K and a bulk Archive + Undo across all of them stay quick. Each step is
// timed in the page (from the key / input to the next painted frame) and written to perf.json next to the shots.
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

const N = 220;
let app: ElectronApplication;
let page: Page;
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-scale-'));
const REPO = path.resolve(import.meta.dirname, '../../../..');
const SHOTS = process.env.HOME_SHOTS_DIR ?? path.resolve(import.meta.dirname, '../../test-results/home');
fs.mkdirSync(SHOTS, { recursive: true });
const perf: Record<string, number> = {};

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  test.setTimeout(300000);
  const env: NodeJS.ProcessEnv = { ...process.env, VSTUDIO_HOME: path.join(tmp, 'vhome'), VSTUDIO_DEFAULT_PERSONA: '1', VSTUDIO_LLM_PROVIDER: 'none', PYTHONPATH: path.join(REPO, 'lib') };
  for (const k of ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'VSTUDIO_PERSONA']) delete env[k];
  const out = JSON.parse(execFileSync(process.env.DESK_PYTHON || 'python3', [path.join(import.meta.dirname, 'fixture/many_projects.py'), tmp, String(N)], { env, encoding: 'utf8' }).trim().split('\n').pop()!);
  expect(out.n).toBe(N);
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
});

test.afterAll(async () => {
  fs.writeFileSync(path.join(SHOTS, 'perf.json'), JSON.stringify({ rows: N, ms: perf }, null, 2));
  console.log(`All projects with ${N} videos (ms):`, JSON.stringify(perf));
  await closeApp(app);
});

type Act = { key: string; meta?: boolean } | { type: string } | { click: string };
type Done = { rows: number } | { rowsBelow: number } | { notCurrent: string } | { bulk: string };

/** Do ``act`` in the page and time it to the frame after ``done`` holds (checked every frame). */
async function timed(name: string, act: Act, done: Done): Promise<number> {
  const ms = await page.evaluate(
    async ([a, d]) => {
      const n = () => document.querySelectorAll('[data-testid=studio-row]').length;
      const ok = () =>
        'rows' in d ? n() === d.rows : 'rowsBelow' in d ? n() > 0 && n() < d.rowsBelow : 'notCurrent' in d ? document.querySelector('[data-testid=studio-row][aria-current=true]')?.getAttribute('data-row') !== d.notCurrent : !!document.querySelector('[data-testid=studio-bulk]')?.textContent?.includes(d.bulk);
      const t0 = performance.now();
      if ('key' in a) document.activeElement?.dispatchEvent(new KeyboardEvent('keydown', { key: a.key, bubbles: true, cancelable: true, metaKey: !!a.meta, ctrlKey: !!a.meta }));
      else if ('type' in a) {
        const el = document.querySelector<HTMLInputElement>('[data-testid=studio-search]')!;
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(el, a.type);
        el.dispatchEvent(new Event('input', { bubbles: true }));
      } else document.querySelector<HTMLElement>(`[data-testid=${a.click}]`)!.click();
      while (!ok() && performance.now() - t0 < 60000) await new Promise((r) => requestAnimationFrame(r));
      await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
      return ok() ? performance.now() - t0 : -1;
    },
    [act, done] as const,
  );
  perf[name] = Math.round(ms);
  return ms;
}

const rows = () => page.getByTestId('studio-row');

test(`${N} videos: the list comes in whole and its counts settle once`, async () => {
  test.setTimeout(180000);
  const t0 = Date.now();
  await page.evaluate(() => (location.hash = '#/studio?f=all'));
  await expect(page.getByTestId('studio-n-all')).toHaveText(String(N), { timeout: 120000 });
  perf.listReady = Date.now() - t0;
  expect(perf.listReady).toBeLessThan(60000); // from a cold start: every project's clips asked at once
  await expect(rows()).toHaveCount(N);
  await page.screenshot({ path: path.join(SHOTS, 'all-projects-scale.png') });
});

test('search narrows hundreds of rows while she types', async () => {
  const ms = await timed('searchType', { type: 'calmer' }, { rowsBelow: N });
  expect(ms).toBeGreaterThan(0);
  await expect(rows()).toHaveCount(Math.ceil((N - 3) / 6));
  await timed('searchClear', { type: '' }, { rows: N });
  expect(ms).toBeLessThan(500);
});

test('J moves, ⌘A picks every row, the bulk bar follows at once', async () => {
  await rows().first().click();
  const first = await rows().first().getAttribute('data-row');
  const j = await timed('keyJ', { key: 'j' }, { notCurrent: first! });
  expect(j).toBeGreaterThan(0);
  expect(j).toBeLessThan(300);
  const all = await timed('selectAll', { key: 'a', meta: true }, { bulk: `${N} selected` });
  expect(all).toBeGreaterThan(0);
  expect(all).toBeLessThan(500);
  await expect(page.getByTestId('studio-bulk')).toContainText(`${N} selected`);
});

test(`a bulk Archive of ${N} projects empties the list, Undo brings every one back`, async () => {
  test.setTimeout(120000);
  const arch = await timed('bulkArchive', { click: 'studio-bulk-archive' }, { rows: 0 });
  expect(arch).toBeGreaterThan(0);
  expect(arch).toBeLessThan(5000); // one engine call + one listing (it was 21 s while every lookup listed again)
  const undo = await timed('undoArchive', { click: 'toast-undo' }, { rows: N });
  expect(undo).toBeGreaterThan(0);
  expect(undo).toBeLessThan(10000);
  await expect(page.getByTestId('studio-n-all')).toHaveText(String(N));
});
