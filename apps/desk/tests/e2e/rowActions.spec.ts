// The Studio's row actions (「任务的删除怎么没了」) and an empty recording's clip ("zmian": 0:00, black covers, no
// transcript). Window hidden, mock engine, isolated profile, the Studio on. Every row has a hover ⋯ and a right-click
// menu: Archive (undo toast), ⌫ archives, the Archived filter restores, ⌘-click picks several for the bulk bar, and
// Delete… opens one dialog for every kind (a request, a project, her work folders, from the row menu, the Archived
// filter and the bulk bar) that names what Reelfold made and goes and what of hers stays: Move to Trash (Undo, then
// the Trash - a test folder here) or Delete permanently after a second, red step. A clip of under a second says so
// plainly instead of "0:00".
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

let app: ElectronApplication;
let page: Page;
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-rowact-'));
const vhome = path.join(tmp, 'vhome');
const watch = path.join(tmp, 'demos');
const rec = path.join(tmp, 'recordings', 'take1', 'assembled.mp4');
const projParent = path.join(vhome, 'projects', '512d9d387962');
const proj = path.join(projParent, '01-talkinghead-1');
const SHOTS = process.env.DESK_SHOTS_DIR ?? path.resolve(import.meta.dirname, '../../test-results/row-actions');
fs.mkdirSync(SHOTS, { recursive: true });

function ffmpeg(args: string[]) {
  execFileSync('ffmpeg', ['-v', 'error', '-y', ...args]);
}
const lavfi = (d: number) => ['-f', 'lavfi', '-i', `testsrc2=size=240x320:rate=30:duration=${d}`, '-f', 'lavfi', '-i', `sine=frequency=330:duration=${d}`, '-shortest', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac'];

const rowNamed = (name: string) => page.locator('[data-testid=studio-row]', { hasText: name });

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  // her recording (outside every project folder) and an app-made project that points at it
  fs.mkdirSync(path.dirname(rec), { recursive: true });
  ffmpeg([...lavfi(2), rec]);
  fs.mkdirSync(proj, { recursive: true });
  fs.writeFileSync(path.join(proj, 'project.yaml'), `name: talkinghead-1\nrecipe: talkinghead\nitems:\n- id: assembled\n  inputs:\n    video: ${rec}\n`);
  fs.writeFileSync(path.join(projParent, 'intake.json'), '{}');
  fs.writeFileSync(path.join(vhome, 'projects.json'), JSON.stringify([{ dir: proj, name: 'talkinghead-1' }]));
  // work folders with clips: an almost empty recording (0.9 s, like "zmian") and two ordinary ones
  for (const [name, dur] of [['zmian-take', 0.9], ['travel-a', 4], ['travel-b', 4]] as const) {
    fs.mkdirSync(path.join(watch, name, 'final'), { recursive: true });
    ffmpeg([...lavfi(dur), path.join(watch, name, 'final', `${name}.mp4`)]);
  }
  // two projects whose run failed (a file could not be read): one with a single video, one with two ("为什么有两个task")
  const failed = (dir: string) => {
    fs.writeFileSync(path.join(dir, 'desk-pilot.json'), JSON.stringify({ pid: 1, exit: 5, offset: 0, started: Date.now() / 1000 - 60, finished: Date.now() / 1000 }));
    fs.writeFileSync(path.join(dir, 'desk-pilot.log'), JSON.stringify({ event: 'stage-fail', ok: false, error: 'Invalid data found when processing input', stage: 'render' }) + '\n');
  };
  for (const [name, clips] of [['leaves-film', ['leaves-red']], ['mcp-course', ['mcp-part1', 'mcp-part2']]] as const) {
    fs.mkdirSync(path.join(watch, name, 'final'), { recursive: true });
    for (const c of clips) ffmpeg([...lavfi(3), path.join(watch, name, 'final', `${c}.mp4`)]);
    failed(path.join(watch, name));
  }
  app = await electron.launch({
    args: [path.resolve(import.meta.dirname, '../..')],
    env: { ...process.env, DESK_STUDIO: '1', DESK_ENGINE_MOCK: '1', DESK_MOCK_STEP: '0.02', DESK_MOCK_PLAN_FAIL: '1', DESK_USER_DATA: path.join(tmp, 'profile'), VSTUDIO_HOME: vhome, DESK_HISTORY_WATCH: watch, DESK_HIDE_WINDOW: '1', DESK_SHARED_CACHE: path.join(tmp, 'cache'), DESK_HF_HUB: '', DESK_SKIP_FIRST_RUN: '1', VITE_DEV_SERVER_URL: '' },
  });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForURL(/^app:\/\/desk\//);
  await page.evaluate(async () => {
    localStorage.setItem('i18n.strict', '1');
    await window.desk.setSettings({ lang: 'en', theme: 'studio-dark', defaultPlatforms: ['youtube'] });
  });
  await page.reload();
  await page.waitForURL(/^app:\/\/desk\//);
  await page.evaluate(() => (location.hash = '#/studio')); // the app lands on Home; the list is All projects
  await expect(page.getByTestId('studio')).toBeVisible({ timeout: 30000 });
  await expect(rowNamed('talkinghead-1')).toHaveCount(1, { timeout: 30000 });
});

test.afterAll(async () => {
  await closeApp(app);
});

test('right-click: Archive with undo; ⌫ archives; the Archived filter restores', async () => {
  const p = rowNamed('talkinghead-1');
  await p.click({ button: 'right' });
  const menu = page.getByTestId('context-menu');
  await expect(menu).toBeVisible();
  for (const id of ['row-open-folder', 'row-rename', 'row-archive', 'row-delete']) await expect(menu.getByTestId(id)).toBeVisible();
  await menu.getByTestId('row-archive').click();
  await expect(p).toHaveCount(0);
  const t1 = page.getByTestId('toast').filter({ hasText: 'Archived 1 item' });
  await expect(t1).toBeVisible();
  await t1.getByTestId('toast-undo').click();
  await expect(p).toHaveCount(1);

  // ⌫ with the row in focus in the list
  await p.click();
  await expect(p).toHaveAttribute('aria-current', 'true');
  await p.focus();
  await page.keyboard.press('Backspace');
  await expect(p).toHaveCount(0);
  const arch = page.getByTestId('studio-f-archived');
  await expect(arch).toBeVisible();
  await expect(arch).toContainText('1');
  await arch.click();
  const ar = page.getByTestId('studio-archived-row').filter({ hasText: 'talkinghead-1' });
  await expect(ar).toBeVisible();
  await expect(ar).toContainText('Archived');
  await page.screenshot({ path: path.join(SHOTS, 'archived-filter.png') });
  await page.getByTestId('studio-restore').click();
  await expect(page.getByTestId('toast').filter({ hasText: 'Restored 1 item' })).toBeVisible();
  await page.getByTestId('studio-f-all').click();
  await expect(rowNamed('talkinghead-1')).toHaveCount(1);
});

test('⌘-click picks several: the bulk bar archives them (undo brings them back)', async () => {
  const a = rowNamed('travel-a');
  const b = rowNamed('travel-b');
  await expect(a).toHaveCount(1, { timeout: 30000 });
  await expect(b).toHaveCount(1);
  await a.click();
  await b.click({ modifiers: [process.platform === 'darwin' ? 'Meta' : 'Control'] });
  const bar = page.getByTestId('studio-bulk');
  await expect(bar).toContainText('2 selected');
  await expect(a).toHaveAttribute('aria-selected', 'true');
  // Delete… is offered too (only what Reelfold made in them would go)
  await expect(bar.getByTestId('studio-bulk-delete')).toBeVisible();
  await page.screenshot({ path: path.join(SHOTS, 'bulk-bar.png') });
  await bar.getByTestId('studio-bulk-archive').click();
  await expect(a).toHaveCount(0);
  await expect(b).toHaveCount(0);
  const t2 = page.getByTestId('toast').filter({ hasText: 'Archived 2 items' });
  await expect(t2).toBeVisible();
  await t2.getByTestId('toast-undo').click();
  await expect(a).toHaveCount(1);
  await expect(b).toHaveCount(1);
});

test('one row per video: a failed one-video project is one red row; a two-video project is one header + its videos', async () => {
  const leaves = page.locator('[data-testid=studio-row]', { hasText: 'leaves-red' });
  await expect(leaves).toHaveCount(1, { timeout: 30000 });
  await expect(leaves).toHaveAttribute('data-tone', 'error');
  await expect(leaves).toHaveAttribute('data-kind', 'clip');
  await expect(page.locator('[data-testid=studio-row][data-kind=project]', { hasText: 'leaves-film' })).toHaveCount(0); // no sibling row
  const head = page.getByTestId('studio-project-head').filter({ hasText: 'mcp-course' });
  await expect(head).toHaveCount(1);
  await expect(head.getByTestId('studio-project-badge')).toBeVisible();
  await expect(page.locator('.st-rowwrap.nested [data-testid=studio-row]', { hasText: 'mcp-part' })).toHaveCount(2);
  await expect(page.locator('[data-testid=studio-row]', { hasText: 'mcp-part' })).toHaveCount(2); // listed once
  await page.screenshot({ path: path.join(SHOTS, 'one-row-per-video.png') });
  // the header opens the project's question, laid out across the whole page
  await head.getByTestId('studio-row').click();
  const ask = page.getByTestId('studio-project-ask');
  await expect(ask).toBeVisible();
  const [pw, aw] = await Promise.all([page.getByTestId('studio-page').evaluate((e) => e.getBoundingClientRect().width), ask.evaluate((e) => e.getBoundingClientRect().width)]);
  expect(aw).toBeGreaterThan(pw - 2);
  const card = await page.getByTestId('inbox-preview').evaluate((e) => e.getBoundingClientRect().width);
  expect(card).toBeGreaterThan(pw * 0.8);
  await page.screenshot({ path: path.join(SHOTS, 'project-question.png') });
  // the one-video project: its video's page, with the question pinned on it
  await leaves.click();
  await expect(page.getByTestId('editor')).toBeVisible({ timeout: 20000 });
  await expect(page.getByTestId('studio-ask-chip')).toBeVisible();
});

test('Rename on a video row names the video, not its project', async () => {
  await rowNamed('travel-a').click({ button: 'right' });
  await page.getByTestId('context-menu').getByTestId('row-rename').click();
  const box = page.getByRole('dialog').locator('input');
  await box.fill('Sunrise over the bay');
  await box.press('Enter');
  await expect(rowNamed('Sunrise over the bay')).toHaveCount(1, { timeout: 15000 });
  await expect(rowNamed('Sunrise over the bay')).toContainText('travel-a'); // the project line keeps its name
});

test('an almost empty recording: its length is 0:00.9, said plainly, with Archive from the page ⋯ too', async () => {
  const z = rowNamed('zmian-take');
  await expect(z).toHaveCount(1, { timeout: 30000 });
  await z.click();
  const note = page.getByTestId('studio-empty-clip');
  await expect(note).toBeVisible({ timeout: 20000 });
  await expect(note).toContainText('only 0:00.9 long');
  await expect(page.getByTestId('editor-length')).toContainText('0:00.9');
  await expect(note.getByTestId('studio-empty-archive')).toBeVisible();
  await page.screenshot({ path: path.join(SHOTS, 'empty-clip.png') });
  await page.getByTestId('studio-page-more').click();
  await expect(page.getByTestId('context-menu').getByTestId('row-archive')).toBeVisible();
  await page.keyboard.press('Escape');
  await note.getByTestId('studio-empty-keep').click();
  await expect(note).toHaveCount(0);
});

/** The main process's Trash: a folder of the test (not her real Trash); returns where things went. */
async function stubTrash() {
  const trash = path.join(tmp, 'Trash');
  fs.mkdirSync(trash, { recursive: true });
  await app.evaluate(({ shell }, dest) => {
    shell.trashItem = (async (p: string) => {
      const fsm = process.getBuiltinModule('node:fs') as typeof import('node:fs');
      const pm = process.getBuiltinModule('node:path') as typeof import('node:path');
      fsm.renameSync(p, pm.join(dest, `${Date.now()}-${pm.basename(p)}`));
    }) as typeof shell.trashItem;
  }, trash);
  return trash;
}

test('Delete a project: the dialog names what goes and that her recording stays; Undo, then the Trash', async () => {
  const trash = await stubTrash();
  const p = rowNamed('talkinghead-1');
  await p.hover();
  await p.locator('xpath=..').getByTestId('row-more').click();
  await page.getByTestId('context-menu').getByTestId('row-delete').click();
  const dlg = page.getByTestId('delete-dialog');
  await expect(dlg).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveAttribute('aria-label', 'Delete “talkinghead-1”?');
  await expect(dlg.getByTestId('delete-item')).toHaveCount(1);
  await expect(dlg.getByTestId('delete-paths')).toContainText(path.join(fs.realpathSync.native(tmp), 'vhome', 'projects', '512d9d387962'));
  await expect(dlg.getByTestId('delete-keep')).toContainText('Never deleted');
  await expect(dlg.getByTestId('delete-keep')).toContainText(fs.realpathSync.native(rec));
  await expect(page.getByTestId('delete-soft')).toBeFocused(); // Move to Trash is the default
  await page.screenshot({ path: path.join(SHOTS, 'delete-dialog.png') });
  await page.getByTestId('delete-soft').click();
  const toast = page.getByTestId('toast').filter({ hasText: 'Moved 1 item to the Trash' });
  await expect(toast).toBeVisible();
  await expect(p).toHaveCount(0);
  expect(fs.existsSync(projParent)).toBe(true); // nothing moved while Undo is possible
  await toast.getByTestId('toast-undo').click();
  await expect(p).toHaveCount(1, { timeout: 15000 });
  // again, and this time the toast goes by: then the folder goes to the Trash
  await p.click({ button: 'right' });
  await page.getByTestId('context-menu').getByTestId('row-delete').click();
  await page.getByTestId('delete-soft').click();
  await expect(p).toHaveCount(0);
  await expect.poll(() => fs.existsSync(projParent), { timeout: 20000 }).toBe(false); // projects/<id> as a whole
  expect(fs.readdirSync(trash).some((f) => f.endsWith('512d9d387962'))).toBe(true);
  expect(fs.existsSync(rec)).toBe(true); // her recording stays
});

test('a failed request: the hover ⋯ offers Try again / Archive / Delete…; Delete says nothing on disk goes', async () => {
  await app.evaluate(({ dialog }, paths) => {
    dialog.showOpenDialog = (async () => ({ canceled: false, filePaths: paths })) as typeof dialog.showOpenDialog;
  }, [rec]);
  await page.getByTestId('studio-new').click();
  await page.getByTestId('composer-input').fill('Two short clips from this take');
  await page.getByTestId('composer-attach').click();
  await page.getByTestId('make-plan').click();
  const r = page.locator('[data-testid=studio-row][data-kind=request][data-tone=error]');
  await expect(r).toHaveCount(1, { timeout: 30000 });
  await r.hover();
  await r.locator('xpath=..').getByTestId('row-more').click();
  const menu = page.getByTestId('context-menu');
  for (const id of ['row-retry', 'row-archive', 'row-delete']) await expect(menu.getByTestId(id)).toBeVisible();
  await page.screenshot({ path: path.join(SHOTS, 'request-menu.png') });
  await menu.getByTestId('row-delete').click();
  await expect(page.getByTestId('delete-dialog')).toContainText('Nothing on disk: only the request goes.');
  await page.getByTestId('delete-soft').click();
  await expect(page.getByTestId('toast').filter({ hasText: 'Moved 1 item to the Trash' })).toBeVisible();
  await expect(page.locator('[data-testid=studio-row][data-kind=request]')).toHaveCount(0);
  expect(fs.existsSync(rec)).toBe(true);
});

test('Archived: Delete permanently needs a second, red step; the Reelfold-made files are gone from disk', async () => {
  const dir = path.join(watch, 'travel-a');
  await rowNamed('travel-a').click({ button: 'right' }); // renamed video "Sunrise…", project travel-a
  await page.getByTestId('context-menu').getByTestId('row-archive').click();
  await page.getByTestId('studio-f-archived').click();
  const ar = page.getByTestId('studio-archived-row').filter({ hasText: 'travel-a' });
  await expect(ar).toBeVisible();
  await ar.click({ button: 'right' });
  await page.getByTestId('context-menu').getByTestId('row-delete').click();
  const dlg = page.getByTestId('delete-dialog');
  await expect(dlg.getByTestId('delete-item')).toContainText('travel-a');
  await expect(dlg.getByTestId('delete-paths')).toContainText(fs.realpathSync.native(dir));
  await page.getByTestId('delete-hard').click();
  const step = page.getByTestId('delete-hard-step');
  await expect(step).toContainText('cannot be put back');
  const ok = page.getByTestId('delete-hard-ok');
  await expect(ok).toBeDisabled();
  await page.screenshot({ path: path.join(SHOTS, 'delete-hard-step.png') });
  await page.getByTestId('delete-sure').check();
  await ok.click();
  await expect(page.getByTestId('toast').filter({ hasText: 'Deleted 1 item permanently' })).toBeVisible();
  await expect(ar).toHaveCount(0);
  expect(fs.existsSync(dir)).toBe(false); // final/ was all there was: the folder goes whole
});

test('Archived bulk bar: pick several, Delete…, Move to Trash', async () => {
  const trash = await stubTrash();
  await page.getByTestId('studio-f-all').click();
  for (const name of ['travel-b', 'mcp-part1']) {
    await rowNamed(name).click({ button: 'right' });
    await page.getByTestId('context-menu').getByTestId('row-archive').click();
    await expect(rowNamed(name)).toHaveCount(0);
  }
  await page.getByTestId('studio-f-archived').click();
  const rows = page.getByTestId('studio-archived-row');
  const b = rows.filter({ hasText: 'travel-b' });
  const m = rows.filter({ hasText: 'mcp-course' });
  const mod = process.platform === 'darwin' ? 'Meta' : 'Control';
  await b.click({ modifiers: [mod] });
  await m.click({ modifiers: [mod] });
  const bar = page.getByTestId('studio-bulk');
  await expect(bar).toContainText('2 selected');
  await bar.getByTestId('studio-bulk-delete').click();
  await expect(page.getByRole('dialog')).toHaveAttribute('aria-label', 'Delete 2 items?');
  await expect(page.getByTestId('delete-item')).toHaveCount(2);
  await page.getByTestId('delete-soft').click();
  await expect(page.getByTestId('toast').filter({ hasText: 'Moved 2 items to the Trash' })).toBeVisible();
  await expect(b).toHaveCount(0);
  await expect(m).toHaveCount(0);
  await expect.poll(() => fs.existsSync(path.join(watch, 'travel-b')), { timeout: 20000 }).toBe(false);
  // mcp-course: its exports and run notes were all Reelfold made, so the folder goes whole
  await expect.poll(() => fs.existsSync(path.join(watch, 'mcp-course')), { timeout: 20000 }).toBe(false);
  expect(fs.readdirSync(trash).length).toBeGreaterThan(1);
});
