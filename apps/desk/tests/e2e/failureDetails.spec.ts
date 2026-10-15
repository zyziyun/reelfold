// A failed launch render, real sidecar, isolated project/profile.
import { _electron as electron, expect, test, type ElectronApplication } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'reelfold-failure-details-'));
const repo = path.resolve(import.meta.dirname, '../../../..');
let app: ElectronApplication;
const error = 'render: RuntimeError: launch_kit.py exit 1: launch-kit render failed: TypeError: sequence item 5: expected str instance, NoneType found';
test.afterAll(async () => { if (app) await closeApp(app); });
test('failed promo exposes selectable, copyable diagnostics in English, Chinese and French', async () => {
  const env = { ...process.env, VSTUDIO_HOME: path.join(tmp, 'vhome'), VSTUDIO_CACHE: path.join(tmp, 'vcache'), VSTUDIO_DEFAULT_PERSONA: '1', VSTUDIO_LLM_PROVIDER: 'none' };
  const project = path.join(tmp, 'projects', 'promo');
  execFileSync(process.env.DESK_PYTHON || 'python3', ['-c', `
import json, os, sys
from vstudio.project.core import Project
p = Project.create(sys.argv[1], recipe='launch-kit', name='Promo failed render', items=[dict(id='main')])
p.plan()
with open(os.path.join(p.dir, 'desk-pilot.json'), 'w') as f: json.dump(dict(exit=1, started=1, finished=2, offset=0), f)
with open(os.path.join(p.dir, 'desk-pilot.log'), 'w') as f:
 for e in [dict(event='stage-fail', job='main', stage='render', error=sys.argv[2]), dict(event='job-done', job='main', state='failed', reasons=[sys.argv[2]]), dict(event='project-end', exit_code=1)]: f.write(json.dumps(e)+'\\n')
`, project, error], { env: { ...env, PYTHONPATH: path.join(repo, 'lib') }, encoding: 'utf8' });
  app = await electron.launch({ args: [path.resolve(import.meta.dirname, '../..')], env: { ...env, PYTHONPATH: '', DESK_ENGINE_MOCK: '', DESK_USER_DATA: path.join(tmp, 'profile'), DESK_HISTORY_WATCH: path.join(tmp, 'projects'), DESK_STUDIO: '1', DESK_HIDE_WINDOW: '1', DESK_SHARED_CACHE: path.join(tmp, 'cache'), DESK_HF_HUB: '', DESK_SKIP_FIRST_RUN: '1', VITE_DEV_SERVER_URL: '' } });
  const page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.waitForURL(/^app:\/\/desk\//);
  expect((await page.evaluate(() => window.desk.engineInfo())).mode).toBe('real');
  for (const lang of ['en', 'zh-CN', 'fr'] as const) {
    await page.evaluate(async lang => { localStorage.setItem('i18n.strict', '1'); await window.desk.setSettings({ lang }); }, lang);
    await page.reload();
    await page.evaluate(() => { location.hash = '#/inbox'; });
    const preview = page.getByTestId('inbox-preview');
    await expect(preview).toHaveAttribute('data-kind', 'failed', { timeout: 30000 });
    const details = preview.getByTestId('failure-details');
    await expect(details).not.toHaveAttribute('open', '');
    await details.locator('summary').click();
    await expect(details.locator('pre')).toContainText('TypeError: sequence item 5');
    expect(await details.locator('pre').evaluate(e => getComputedStyle(e).userSelect)).toBe('text');
    await details.getByTestId('failure-copy').click();
    expect(await app.evaluate(({ clipboard }) => clipboard.readText())).toContain('NoneType found');
    const box = await details.boundingBox();
    expect(box!.x + box!.width).toBeLessThanOrEqual(1440);
    await page.screenshot({ path: path.join(tmp, `failure-${lang}.png`) });
  }
});
