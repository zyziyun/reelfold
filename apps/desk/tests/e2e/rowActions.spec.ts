// The Studio's row actions (「任务的删除怎么没了」) and an empty recording's clip ("zmian": 0:00, black covers, no
// transcript). Window hidden, mock engine, isolated profile, the Studio on. Every row has a hover ⋯ and a right-click
// menu: Archive (undo toast), ⌫ archives, the Archived filter restores, ⌘-click picks several for the bulk bar, a
// failed request is deleted for good after a confirm, a project's folder goes to the Trash after the main process's
// confirm that names it (her recording stays), and a clip of under a second says so plainly instead of "0:00".
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
  // Delete is not offered: these are her own folders (archive only)
  await expect(bar.getByTestId('studio-bulk-delete')).toHaveCount(0);
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

test('Delete a project: the confirm names its folder and that her recording stays; it goes to the Trash', async () => {
  await app.evaluate(({ dialog, shell }) => {
    const g = globalThis as unknown as { __asked: { message: string; detail: string }[] };
    g.__asked = [];
    dialog.showMessageBox = (async (...a: unknown[]) => {
      const o = (a.length > 1 ? a[1] : a[0]) as { message: string; detail: string };
      g.__asked.push({ message: o.message, detail: o.detail });
      return { response: 1, checkboxChecked: false };
    }) as typeof dialog.showMessageBox;
    // the test's temp folder, not her real Trash
    shell.trashItem = (async (p: string) => {
      const fsm = process.getBuiltinModule('node:fs') as typeof import('node:fs');
      fsm.rmSync(p, { recursive: true, force: true });
    }) as typeof shell.trashItem;
  });
  const p = rowNamed('talkinghead-1');
  await p.hover();
  await p.locator('xpath=..').getByTestId('row-more').click();
  await page.getByTestId('context-menu').getByTestId('row-delete').click();
  await expect(page.getByTestId('toast').filter({ hasText: 'Moved 1 project to the Trash' })).toBeVisible();
  await expect(p).toHaveCount(0);
  const asked = await app.evaluate(() => (globalThis as unknown as { __asked: { message: string; detail: string }[] }).__asked);
  expect(asked).toHaveLength(1);
  expect(asked[0].message).toBe('Move “talkinghead-1” to the Trash?');
  expect(asked[0].detail).toContain(path.join(fs.realpathSync(tmp), 'vhome', 'projects', '512d9d387962'));
  expect(asked[0].detail).toContain('Your recordings stay where they are:');
  expect(asked[0].detail).toContain(rec);
  expect(fs.existsSync(projParent)).toBe(false); // projects/<id> as a whole (only its intake note was beside it)
  expect(fs.existsSync(rec)).toBe(true); // her recording stays
});

test('a failed request: the hover ⋯ offers Try again / Archive / Delete…; Delete asks, then it is gone for good', async () => {
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
  await expect(page.getByTestId('row-delete-body')).toContainText('Your files stay where they are.');
  await page.getByTestId('row-delete-ok').click();
  await expect(page.getByTestId('toast').filter({ hasText: 'Deleted 1 request' })).toBeVisible();
  await expect(page.locator('[data-testid=studio-row][data-kind=request]')).toHaveCount(0);
  expect(fs.existsSync(rec)).toBe(true);
});
