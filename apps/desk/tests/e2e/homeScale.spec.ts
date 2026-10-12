// Home chips and the Studio's empty states with the REAL engine sidecar (no mock engine), an isolated temp profile,
// window hidden, the Studio on. Found while capturing the 0.2.7 promo on a profile with 230 projects:
//   - "Finish <project>… N clips left" filled the composer with a request that carried no files, so it parked at
//     "Add the recordings you want cut": the chip runs that project on (its recordings are in it) and opens it
//   - a chip read "Next intake-Cut-this-week-s-reco…" (a folder id): it says the project's own title
//   - a question about a whole project opened from the Inbox showed "Pick a video on the left" / another project's
//     video: it shows that question
//   - a video not made yet said "This video has no file… the recording may have been empty": "Not made yet - step N
//     of M"
//   - the list said "No videos yet" while it was still loading: a skeleton until it has answered
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

let app: ElectronApplication;
let page: Page;
let fx: { u: string; s: string; c: string; a: string; series: string };
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-homescale-'));
const REPO = path.resolve(import.meta.dirname, '../../../..');
const SHOTS = process.env.HOME_SHOTS_DIR ?? path.resolve(import.meta.dirname, '../../test-results/home');
fs.mkdirSync(SHOTS, { recursive: true });
const engineEnv = {
  VSTUDIO_HOME: path.join(tmp, 'vhome'),
  VSTUDIO_BATCH_BENCH: path.join(tmp, 'bench.json'),
  VSTUDIO_DEFAULT_PERSONA: '1',
  VSTUDIO_LLM_PROVIDER: 'none',
  ...Object.fromEntries(['SEGMENT_PLAN', 'PROOFREAD', 'GLOSSARY', 'COPY', 'SCRIPT', 'PLANNER', 'INTAKE', 'OUTPUT_EDIT'].map((t) => [`VSTUDIO_LLM_${t}_PROVIDER`, 'none'])),
};

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  test.setTimeout(400000);
  const env: NodeJS.ProcessEnv = { ...process.env, ...engineEnv, PYTHONPATH: path.join(REPO, 'lib') };
  for (const k of ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'VSTUDIO_PERSONA']) delete env[k];
  fx = JSON.parse(execFileSync(process.env.DESK_PYTHON || 'python3', [path.join(import.meta.dirname, 'fixture/home_scale.py'), tmp], { env, encoding: 'utf8' }).trim().split('\n').pop()!);
  app = await electron.launch({
    args: [path.resolve(import.meta.dirname, '../..')],
    env: { ...env, VSTUDIO_TEST_TRUTH: path.join(tmp, 'u', 'truth.json'), PYTHONPATH: '', DESK_STUDIO: '1', DESK_ENGINE_MOCK: '', DESK_USER_DATA: path.join(tmp, 'profile'), DESK_HISTORY_WATCH: '', DESK_HIDE_WINDOW: '1', DESK_SHARED_CACHE: path.join(tmp, 'cache'), DESK_HF_HUB: '', DESK_SKIP_FIRST_RUN: '1', VITE_DEV_SERVER_URL: '' },
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
const api = <T,>(p: string) =>
  page.evaluate(async (u) => {
    const info = await window.desk.engineInfo();
    const r = await fetch(info.baseUrl + u, { headers: { Authorization: `Bearer ${info.token}` } });
    return r.json();
  }, p) as Promise<T>;
type Item = { id: string; dir: string; name: string };
const idOf = async (dir: string) => (await api<{ items: Item[] }>('/api/history')).items.find((i) => fs.realpathSync(i.dir) === fs.realpathSync(dir))!.id;

test('the list never says "No videos yet" while it is loading: a skeleton, then the videos', async () => {
  await hash('#/studio?f=all');
  await page.reload();
  await page.waitForURL(/^app:\/\/desk\//);
  const seen = await page.evaluate(async () => {
    const out = { empty: false, skeleton: false };
    const t0 = performance.now();
    while (!document.querySelector('[data-testid=studio-n-all]') && performance.now() - t0 < 60000) {
      const txt = document.querySelector('[data-testid=studio]')?.textContent ?? '';
      if (/No videos yet/.test(txt)) out.empty = true;
      if (document.querySelector('[data-testid=studio-list-skeleton], [data-testid=studio-page-skeleton]')) out.skeleton = true;
      await new Promise((r) => requestAnimationFrame(r));
    }
    return out;
  });
  expect(seen.empty).toBe(false);
  await expect(page.getByTestId('studio-n-all')).toBeVisible();
  await expect(page.getByText('No videos yet')).toHaveCount(0);
});

test('a video not made yet says so, and where it is (never "no file, the recording may have been empty")', async () => {
  const id = await idOf(fx.u);
  const clips = (await api<{ clips: { id: string; state: string; files: unknown[] }[] }>(`/api/outputs/${id}`)).clips;
  const next = clips.find((c) => !c.files.length)!;
  expect(next).toBeTruthy();
  await hash(`#/studio/${id}/${encodeURIComponent(next.id)}`);
  const note = page.getByTestId('studio-not-made');
  await expect(note).toBeVisible({ timeout: 30000 });
  await expect(note).toContainText('Not made yet');
  await expect(note).toContainText('step 2 of 2');
  await expect(page.getByTestId('studio-empty-clip')).toHaveCount(0);
  await page.screenshot({ path: path.join(SHOTS, 'not-made-yet.png') });
});

test('a question about a whole project, opened from the Inbox, is that question (not another video, not "Pick a video")', async () => {
  const cid = await idOf(fx.c);
  const inbox = await api<{ items: { key: string; kind: string; project: { id: string | null } }[] }>('/api/inbox');
  const x = inbox.items.find((i) => i.project.id === cid)!;
  expect(x).toBeTruthy();
  await hash(`#/inbox?item=${encodeURIComponent(x.key)}`);
  const ask = page.getByTestId('studio-project-ask');
  await expect(ask).toBeVisible({ timeout: 30000 });
  // its only video carries the project's question (one video: pinned on it), the page says which project
  await expect(ask).toContainText('Failed script');
  await expect(ask).not.toContainText('Short talk');
  await expect(page.getByText('Pick a video on the left')).toHaveCount(0);
  await expect(page.locator(`[data-testid=studio-row][aria-current=true]`)).toHaveAttribute('data-row', new RegExp(cid));
  await page.screenshot({ path: path.join(SHOTS, 'project-question-from-inbox.png') });
});

test("Home chips say the project's own title and the Finish chip runs that project on", async () => {
  test.setTimeout(240000);
  const uid = await idOf(fx.u);
  await hash('#/');
  const chips = page.getByTestId('home-idea');
  await expect(chips.first()).toBeVisible({ timeout: 30000 });
  const texts = await chips.allTextContents();
  expect(texts.join(' | ')).not.toMatch(/intake-|Cut-this-week/);
  await expect(chips.filter({ hasText: 'Next Workshop talk' })).toHaveCount(1);
  const finish = chips.filter({ hasText: 'Finish Office hours' });
  await expect(finish).toHaveCount(1);
  await expect(finish).toContainText('1 clip left');
  await page.screenshot({ path: path.join(SHOTS, 'home-chips-titles.png') });
  await finish.click();
  await expect(page.getByTestId('toast').filter({ hasText: 'Finishing Office hours' })).toBeVisible({ timeout: 15000 });
  await expect.poll(() => page.evaluate(() => location.hash), { timeout: 15000 }).toContain(`#/studio/${uid}`);
  // the project's own run goes on to its next clip (no new request, no "Add the recordings you want cut")
  await expect
    .poll(async () => (await api<{ clips: { files: unknown[]; state: string }[] }>(`/api/outputs/${uid}`)).clips.map((c) => c.state).join(','), { timeout: 180000, intervals: [1000] })
    .not.toMatch(/planned/);
});
