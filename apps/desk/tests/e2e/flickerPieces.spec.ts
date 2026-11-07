// Real engine + real encoded flash; only the failed project state is seeded.
import { _electron as electron, expect, test } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

test('failed render exposes flicker evidence that opens in the piece viewer', async () => {
  test.setTimeout(120000);
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'reelfold-flicker-ui-'));
  const repo = path.resolve(import.meta.dirname, '../../../..');
  const env: NodeJS.ProcessEnv = { ...process.env, VSTUDIO_HOME: path.join(tmp, 'home'),
    VSTUDIO_CACHE: path.join(tmp, 'cache'), VSTUDIO_DEFAULT_PERSONA: '1', VSTUDIO_LLM_PROVIDER: 'none',
    VSTUDIO_BATCH_BENCH: path.join(tmp, 'bench.json'), PYTHONPATH: path.join(repo, 'lib') };
  for (const key of ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'VSTUDIO_PERSONA']) delete env[key];
  const raw = execFileSync(process.env.DESK_PYTHON || 'python3', [path.join(import.meta.dirname, 'fixture/flicker_project.py'), tmp], { env, encoding: 'utf8' });
  const project = JSON.parse(raw.trim().split('\n').pop()!) as { dir: string };
  const app = await electron.launch({ args: [path.resolve(import.meta.dirname, '../..')], env: {
    ...env, PYTHONPATH: '', DESK_STUDIO: '1', DESK_ENGINE_MOCK: '', DESK_USER_DATA: path.join(tmp, 'profile'),
    DESK_HIDE_WINDOW: '1', DESK_SHARED_CACHE: path.join(tmp, 'cache'), DESK_SKIP_FIRST_RUN: '1', VITE_DEV_SERVER_URL: '',
  } });
  try {
    const page = await app.firstWindow();
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.waitForURL(/^app:\/\/desk\//);
    await page.evaluate(() => window.desk.setSettings({ lang: 'en' }));
    await page.reload();
    const find = () => page.evaluate(async (dir) => {
      const engine = await window.desk.engineInfo();
      const response = await fetch(engine.baseUrl + '/api/history', { headers: { Authorization: `Bearer ${engine.token}` } });
      const history = await response.json();
      return history.items.find((item: { dir: string }) => item.dir === dir)?.id || '';
    }, project.dir);
    await expect.poll(find, { timeout: 30000 }).not.toBe('');
    await page.evaluate((id) => { location.hash = `#/p/${id}/clips`; }, await find());
    const pieces = page.getByTestId('work-pieces');
    await expect(pieces).toBeVisible({ timeout: 30000 });
    if (await pieces.getAttribute('open') === null) await pieces.locator('summary').click();
    const tile = page.getByTestId('work-piece').filter({ hasText: 'Flicker review frames' }).first();
    await expect(tile).toBeVisible();
    await tile.click();
    const view = page.getByTestId('piece-view');
    await expect(view).toBeVisible();
    await expect.poll(() => view.locator('img').evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(192);
    await expect(page.getByTestId('piece-box')).toHaveAttribute('data-ready', '1');
    await page.waitForTimeout(250); // let the existing viewer's opening transition finish
    const actions = await page.getByTestId('piece-actions').boundingBox();
    expect(actions).not.toBeNull();
    expect(actions!.y + actions!.height).toBeLessThanOrEqual(720);
    expect(actions!.x + actions!.width).toBeLessThanOrEqual(1280);
    await page.screenshot({ path: test.info().outputPath('flicker-review.png') });
    await page.keyboard.press('Escape');
    await expect(view).toHaveCount(0);
  } finally { await closeApp(app); }
});
