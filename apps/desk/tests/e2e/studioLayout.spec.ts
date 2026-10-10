// The Studio's layout (studio-polish): every split can be resized by a real mouse drag, by the keyboard (focus the
// divider, arrows), double-click puts it back, sizes stay on this Mac across a reload; the video list folds to the
// edge (⌘B or its button) and comes back; at the smallest window the page still reads (the clip page stacks).
// Window hidden, mock engine, isolated profile, synthetic media. Screenshots: DESK_SHOTS_DIR or test-results/layout.
import { _electron as electron, expect, test, type ElectronApplication, type Locator, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

let app: ElectronApplication;
let page: Page;
let fuyeId = '';
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-layout-'));
const watch = path.join(tmp, 'demos');
const fuye = path.join(watch, 'fuye');
const SHOTS = process.env.DESK_SHOTS_DIR ?? path.resolve(import.meta.dirname, '../../test-results/layout');
fs.mkdirSync(SHOTS, { recursive: true });

function ffmpeg(args: string[]) {
  execFileSync('ffmpeg', ['-v', 'error', '-y', ...args]);
}

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  fs.mkdirSync(path.join(fuye, 'final'), { recursive: true });
  const lavfi = (d: number) => ['-f', 'lavfi', '-i', `testsrc2=size=240x320:rate=30:duration=${d}`, '-f', 'lavfi', '-i', `sine=frequency=330:duration=${d}`, '-shortest', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac'];
  const clips = ['A_换圈子', 'B_自媒体', 'C_底气'];
  for (const c of clips) {
    ffmpeg([...lavfi(6), path.join(fuye, 'final', `${c}.mp4`)]);
    ffmpeg(['-i', path.join(fuye, 'final', `${c}.mp4`), '-ss', '1', '-frames:v', '1', path.join(fuye, 'final', `${c}_cover.jpg`)]);
  }
  const W = ['你在', '副业', '当中，', '其实', '是', '底气。', '同一个', '行业', '待', '越久，', '思路', '越窄。'].map((word, i) => ({ word, start: 0.3 + i * 0.4, end: 0.68 + i * 0.4 }));
  fs.writeFileSync(path.join(fuye, 'final', 'A_换圈子.mp4.asr.json'), JSON.stringify({ segments: [{ start: 0.3, end: 5, words: W }] }));
  fs.writeFileSync(path.join(fuye, 'final', 'post.md'), clips.map((c, i) => `## ${c}.mp4  ·  封面 ${c}_cover.jpg\n\n${['同一个行业待越久，思路越窄：我换了三次圈子之后才明白的一件事', '再小的博主，也是博主', '副业给我的不是钱，是底气'][i]}\n\n正文。\n\n#副业\n`).join('\n'));
  app = await electron.launch({
    args: [path.resolve(import.meta.dirname, '../..')],
    env: { ...process.env, DESK_STUDIO: '1', DESK_ENGINE_MOCK: '1', DESK_MOCK_STEP: '0.02', DESK_USER_DATA: path.join(tmp, 'profile'), VSTUDIO_HOME: path.join(tmp, 'vhome'), DESK_HISTORY_WATCH: watch, DESK_HIDE_WINDOW: '1', DESK_SHARED_CACHE: path.join(tmp, 'cache'), DESK_HF_HUB: '', DESK_SKIP_FIRST_RUN: '1', VITE_DEV_SERVER_URL: '' },
  });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForURL(/^app:\/\/desk\//);
  await page.evaluate(async () => {
    localStorage.setItem('i18n.strict', '1');
    await window.desk.setSettings({ lang: 'en', theme: 'studio-dark', defaultPlatforms: ['youtube', 'tiktok', 'xiaohongshu'] });
  });
  await page.reload();
  await page.waitForURL(/^app:\/\/desk\//);
  await expect(page.getByTestId('engine-status')).toBeVisible({ timeout: 30000 });
  fuyeId = await page.evaluate(async () => {
    const info = await window.desk.engineInfo();
    for (let i = 0; i < 60; i++) {
      const h = await (await fetch(info.baseUrl + '/api/history', { headers: { Authorization: `Bearer ${info.token}` } })).json();
      const it = (h.items as { id: string; name: string }[]).find((x) => x.name === 'fuye');
      if (it) return it.id;
      await new Promise((r) => setTimeout(r, 500));
    }
    return '';
  });
  expect(fuyeId).toMatch(/^[0-9a-f]{12}$/);
});

test.afterAll(async () => {
  await closeApp(app);
});

const clipA = () => `#/studio/${fuyeId}/${encodeURIComponent('A_换圈子')}`;
async function openClip() {
  await page.evaluate((h) => (location.hash = h), clipA());
  await expect(page.getByTestId('editor')).toHaveAttribute('data-layout', 'studio', { timeout: 30000 });
  await expect(page.getByTestId('editor-title')).toBeVisible();
  await expect(page.locator('[data-testid=transcript-body] .w').first()).toBeVisible({ timeout: 30000 });
}
const shot = async (name: string) => {
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
};
const width = (l: Locator) => l.evaluate((e) => Math.round(e.getBoundingClientRect().width));
const height = (l: Locator) => l.evaluate((e) => Math.round(e.getBoundingClientRect().height));
/** a real mouse drag of a divider by dx / dy, from its centre */
async function drag(l: Locator, dx: number, dy = 0) {
  const b = (await l.boundingBox())!;
  const x = b.x + b.width / 2;
  const y = b.y + b.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  for (let i = 1; i <= 8; i++) await page.mouse.move(x + (dx * i) / 8, y + (dy * i) / 8);
  await page.mouse.up();
}

test('screenshots: the Studio and a clip page at the usual, smallest and widest windows, dark and light', async () => {
  test.setTimeout(120000);
  await openClip();
  await shot('01-clip-1440-dark');
  await page.getByTestId('studio-ai-toggle').click();
  await shot('02-ai-open-1440-dark');
  await page.getByTestId('studio-ai-toggle').click();
  await page.setViewportSize({ width: 1100, height: 700 });
  await shot('03-clip-1100-min');
  await page.setViewportSize({ width: 2560, height: 1080 });
  await shot('04-clip-2560-ultrawide');
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.evaluate(async () => window.desk.setSettings({ theme: 'notebook-light' }));
  await page.reload();
  await openClip();
  await shot('05-clip-1440-light');
  await page.evaluate(async () => window.desk.setSettings({ theme: 'studio-dark' }));
  await page.reload();
  await openClip();
});

const list = () => page.locator('.st-list');
const listSplit = () => page.getByTestId('studio-list-split');

test('the list: drag its edge, the size stays after a reload, double-click puts it back, arrows on the focused divider', async () => {
  await openClip();
  const w0 = await width(list());
  expect(w0).toBe(300);
  await drag(listSplit(), 100);
  await expect.poll(() => width(list())).toBe(400);
  await page.reload();
  await openClip();
  expect(await width(list())).toBe(400);
  await listSplit().dblclick();
  await expect.poll(() => width(list())).toBe(300);
  // keyboard: focus, → grows 16, ⇧← shrinks 64, End = the most it can take, Home folds it (it can fold)
  await listSplit().focus();
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('ArrowRight');
  await expect.poll(() => width(list())).toBe(332);
  await page.keyboard.press('Shift+ArrowLeft');
  await expect.poll(() => width(list())).toBe(268);
  await expect(listSplit()).toHaveAttribute('aria-valuenow', '268');
  // ↑ ↓ on the divider do not switch videos
  const url = page.url();
  await page.keyboard.press('ArrowDown');
  expect(page.url()).toBe(url);
  await page.keyboard.press('End');
  await expect.poll(() => width(list())).toBe(480);
  // never narrower than its min
  await drag(listSplit(), -270); // 480 - 270 = 210: under the min, not far enough to fold
  await expect.poll(() => width(list())).toBe(232);
  await listSplit().dblclick();
  await expect.poll(() => width(list())).toBe(300);
});

test('the list folds to the edge (⌘B, its button, a drag past its min) and comes back at its size', async () => {
  await openClip();
  await drag(listSplit(), 40);
  await expect.poll(() => width(list())).toBe(340);
  await page.keyboard.press('ControlOrMeta+b');
  await expect(page.getByTestId('studio-rail')).toBeVisible();
  await expect(list()).toHaveCount(0);
  await expect.poll(() => width(page.getByTestId('studio-page'))).toBeGreaterThan(1440 - 56 - 60 - 2);
  await shot('10-list-folded');
  // still folded after a reload
  await page.reload();
  await openClip();
  await expect(page.getByTestId('studio-rail')).toBeVisible();
  await page.keyboard.press('ControlOrMeta+b');
  await expect(list()).toBeVisible();
  expect(await width(list())).toBe(340);
  // its own button
  await page.getByTestId('studio-list-toggle').click();
  await expect(page.getByTestId('studio-rail')).toBeVisible();
  await page.getByTestId('studio-list-toggle').click();
  await expect.poll(() => width(list())).toBe(340);
  // dragged well past its min: folds, keeps its size for next time
  await drag(listSplit(), -260);
  await expect(page.getByTestId('studio-rail')).toBeVisible();
  await page.getByTestId('studio-list-toggle').click();
  await expect.poll(() => width(list())).toBe(340);
  // ⌘N with it folded: it opens with the composer
  await page.keyboard.press('ControlOrMeta+b');
  await page.getByTestId('studio-rail-new').click();
  await expect(page.getByTestId('studio-composer')).toBeVisible();
  await page.getByTestId('studio-new').click();
  await listSplit().dblclick();
});

test('the clip page: the player column and the AI conversation resize, stay after a reload, reset by double-click', async () => {
  await openClip();
  const left = page.locator('.cs-left');
  const ps = page.getByTestId('studio-player-split');
  expect(await width(left)).toBe(380);
  await drag(ps, 120);
  await expect.poll(() => width(left)).toBe(500);
  await ps.focus();
  await page.keyboard.press('ArrowLeft');
  await expect.poll(() => width(left)).toBe(484);
  // the AI conversation: its left edge (dragging left makes it wider)
  await page.getByTestId('studio-ai-toggle').click();
  const pane = page.getByTestId('studio-ai-pane');
  await expect(pane).toBeVisible();
  await expect.poll(() => width(pane)).toBe(440);
  await drag(page.getByTestId('studio-ai-split'), -100);
  await expect.poll(() => width(pane)).toBe(540);
  await page.getByTestId('studio-ai-split').focus();
  await page.keyboard.press('Shift+ArrowLeft');
  await expect.poll(() => width(pane)).toBe(604);
  await shot('11-resized-ai-open');
  await page.reload();
  await openClip();
  expect(await width(left)).toBe(484);
  await page.getByTestId('studio-ai-toggle').click();
  await expect.poll(() => width(pane)).toBe(604);
  await page.getByTestId('studio-ai-split').dblclick();
  await expect.poll(() => width(pane)).toBe(440);
  await page.getByTestId('studio-ai-toggle').click();
  await expect(pane).toBeHidden();
  await ps.dblclick();
  await expect.poll(() => width(left)).toBe(380);
});

test('the header: room around the title, the whole title in its tip, every action at least 28 px', async () => {
  await openClip();
  const top = page.getByTestId('studio-header');
  expect(await height(top)).toBeGreaterThanOrEqual(80);
  const pad = await top.evaluate((e) => {
    const cs = getComputedStyle(e);
    return [cs.paddingTop, cs.paddingLeft].map((x) => parseFloat(x));
  });
  expect(pad[0]).toBeGreaterThanOrEqual(16);
  expect(pad[1]).toBeGreaterThanOrEqual(24);
  await expect(page.getByTestId('editor-title')).toHaveAttribute('title', /同一个行业待越久，思路越窄：我换了三次圈子之后才明白的一件事/);
  const small = await page.locator('.cs-top button:visible, .cs-ai button:visible, .st-list button:visible').evaluateAll((els) =>
    els.map((e) => ({ id: e.getAttribute('data-testid') ?? e.className, h: Math.round(e.getBoundingClientRect().height) })).filter((x) => x.h < 28),
  );
  expect(small).toEqual([]);
});

test('the smallest window: nothing spills sideways; a wide list stacks the clip page; the ultrawide one caps its columns', async () => {
  await openClip();
  await page.setViewportSize({ width: 1100, height: 700 });
  const spill = () => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  await expect.poll(spill).toBeLessThanOrEqual(0);
  await expect(page.getByTestId('studio-schedule')).toBeInViewport();
  await expect(page.getByTestId('editor-title')).toBeInViewport();
  await expect(page.getByTestId('toggle-precise').locator('.lbl')).toBeHidden(); // icon only, its name in the tip
  await shot('20-min-1100');
  // the list as wide as it goes: the page keeps its room and stacks the player above the words
  await listSplit().focus();
  await page.keyboard.press('End');
  const cols = () => page.locator('.cs-body').evaluate((e) => getComputedStyle(e).gridTemplateColumns.split(' ').length);
  await expect.poll(cols).toBe(1);
  await expect.poll(spill).toBeLessThanOrEqual(0);
  expect(await width(page.getByTestId('studio-page'))).toBeGreaterThanOrEqual(560);
  await shot('21-min-1100-stacked');
  await listSplit().dblclick();
  await expect.poll(cols).toBe(3);
  await page.setViewportSize({ width: 2560, height: 1080 });
  await listSplit().focus();
  await page.keyboard.press('End');
  await expect.poll(() => width(list())).toBe(480);
  await page.getByTestId('studio-player-split').focus();
  await page.keyboard.press('End');
  await expect.poll(() => width(page.locator('.cs-left'))).toBe(720);
  await shot('22-ultrawide-max');
  await listSplit().dblclick();
  await page.getByTestId('studio-player-split').dblclick();
  await page.setViewportSize({ width: 1440, height: 900 });
});

test('zh-CN + fr: the new words read in her language', async () => {
  for (const lang of ['zh-CN', 'fr'] as const) {
    await page.evaluate(async (l) => window.desk.setSettings({ lang: l }), lang);
    await page.reload();
    await openClip();
    const text = await page.evaluate(() => document.body.innerText + [...document.querySelectorAll('[aria-label],[title],[data-tip]')].map((e) => `${e.getAttribute('aria-label')} ${e.getAttribute('title')} ${e.getAttribute('data-tip')}`).join(' '));
    expect(text.match(/⟦[^⟧]+⟧/g) ?? []).toEqual([]);
    expect(text.match(/\b(st|lay|ce)\.[a-zA-Z][\w.-]+/g) ?? []).toEqual([]);
    await page.keyboard.press('ControlOrMeta+b');
    await shot(`30-folded-${lang}`);
    await page.keyboard.press('ControlOrMeta+b');
  }
  await page.evaluate(async () => window.desk.setSettings({ lang: 'en' }));
});
