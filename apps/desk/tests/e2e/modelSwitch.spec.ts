// Switching the AI model (her report 2026-10-12: "/model" and "/model 5.5" in the clip chat got "Nothing to change
// for that", the chip only said "AI: Claude Code"). REAL engine sidecar, isolated temp profile, window hidden, a
// talking-head project made on autopilot by the real engine (fixture/real_project.py); the only stand-ins are the two
// CLIs: ROOT/bin/claude answers like `claude -p` with the model it was given (--model, else "its default"
// claude-opus-4-7[1m]) and logs its arguments; ROOT/bin/codex lists a ChatGPT login's models (`codex debug models`).
// In the clip chat: "/" lists the commands; "/model" says what runs and offers a picker; a request is answered by the
// CLI default; "/model 5.5" switches THIS PROJECT to Opus 5.5 (said in the thread, the chip shows it, project.yaml
// keeps it, her default in the routes file stays) and the NEXT reply says claude-opus-5-5 (the CLI really got --model
// claude-opus-5-5); "/model sonnet" -> Sonnet 5.5; "/foo" is not a command - and none of the commands ever reached
// the model.
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

let app: ElectronApplication;
let page: Page;
let id = '';
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-model-'));
const REPO = path.resolve(import.meta.dirname, '../../../..');
const BIN = path.join(tmp, 'bin');
const HOOK = path.join(tmp, 'hook');
const LOG = path.join(tmp, 'claude.log');
const SHOTS = process.env.DESK_SHOTS_DIR ?? path.resolve(import.meta.dirname, '../../test-results/model-switch');
fs.mkdirSync(SHOTS, { recursive: true });

const CLAUDE = `#!/usr/bin/env python3
"""TESTS ONLY: Claude Code's -p answer, from the model it was given."""
import json, sys
a = sys.argv[1:]
if a[:1] == ["--version"]:
    print("9.9.9 (Claude Code)"); sys.exit(0)
if a[:2] == ["auth", "status"]:
    print(json.dumps({"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "max"})); sys.exit(0)
prompt = sys.stdin.read()
if "Reply with: ok" not in prompt:                  # the login check of Settings is not an AI request
    with open(${JSON.stringify(LOG)}, "a", encoding="utf-8") as f:
        f.write(json.dumps([x for x in a if not x.startswith("{") and len(x) < 80]) + "\\n")
model = a[a.index("--model") + 1] if "--model" in a else "claude-opus-4-7[1m]"
out = {"ops": [], "summary": "It already reads well."}
res = {"type": "result", "subtype": "success", "is_error": False, "result": json.dumps(out), "structured_output": out,
       "usage": {"input_tokens": 120, "output_tokens": 9}, "total_cost_usd": 0.01, "modelUsage": {model: {"outputTokens": 9}}}
if "stream-json" in a:
    print(json.dumps({"type": "system", "subtype": "init", "model": model}))
print(json.dumps(res))
`;
const CODEX = `#!/usr/bin/env python3
"""TESTS ONLY: a ChatGPT login's Codex model catalog."""
import json, sys
a = sys.argv[1:]
if a[:1] == ["--version"]:
    print("codex-cli 9.9.9"); sys.exit(0)
if a[:2] == ["debug", "models"]:
    print(json.dumps({"models": [{"slug": "gpt-6-luna", "display_name": "GPT-6-Luna", "visibility": "list", "priority": 4},
                                 {"slug": "gpt-5.6-terra", "display_name": "GPT-5.6-Terra", "visibility": "list", "priority": 8}]}))
    sys.exit(0)
if a[:2] == ["login", "status"]:
    print("Logged in using ChatGPT"); sys.exit(0)
sys.exit(1)
`;
// the app puts its own bin folders first on PATH: the stand-ins are pinned in the engine's vstudio.llm instead, and
// run by this Python (Windows has no shebangs: an extensionless script cannot be exec'd there)
const HOOK_PY = `import os, sys
_bin = os.environ.get("MODEL_FAKE_BIN")
if _bin:
    try:
        from vstudio import llm as _llm
        _find, _argv = _llm.find_cli, _llm.cli_argv
        _fakes = {n: os.path.join(_bin, n) for n in ("claude", "codex")}
        _llm.find_cli = lambda name, opts=None: _fakes[name] if name in _fakes else _find(name, opts)
        _llm.cli_argv = lambda exe, windows=None: [sys.executable, exe] if exe in _fakes.values() else _argv(exe, windows)
    except Exception:
        pass
    try:
        from vstudio import acp as _acp
        _acp.find = lambda agent, opts=None: None   # the ACP agents installed on this Mac never answer here
    except Exception:
        pass
`;

const calls = () => (fs.existsSync(LOG) ? fs.readFileSync(LOG, 'utf8').trim().split('\n').filter(Boolean).map((l) => JSON.parse(l) as string[]) : []);
const modelArg = (c: string[]) => (c.includes('--model') ? c[c.indexOf('--model') + 1] : null);
const routes = () => JSON.parse(fs.readFileSync(path.join(tmp, 'profile', 'llm-routes.json'), 'utf8'));
let projDir = '';
// the project's own AI (project.yaml `ai`), as the engine reads it on each AI step
const projAi = () => {
  const m = /\nai:\n((?: {2}.*\n)+)/.exec(fs.readFileSync(path.join(projDir, 'project.yaml'), 'utf8'));
  return m ? Object.fromEntries(m[1].trim().split('\n').map((l) => l.trim().split(': ').map((x) => x.replace(/^'|'$/g, '')))) : null;
};

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  test.setTimeout(300000);
  fs.mkdirSync(BIN, { recursive: true });
  fs.mkdirSync(HOOK, { recursive: true });
  for (const [n, body] of [['claude', CLAUDE], ['codex', CODEX]] as const) {
    fs.writeFileSync(path.join(BIN, n), body);
    fs.chmodSync(path.join(BIN, n), 0o755);
  }
  fs.writeFileSync(path.join(HOOK, 'sitecustomize.py'), HOOK_PY);
  fs.writeFileSync(path.join(tmp, 'codex-config.toml'), 'model = "gpt-6-astra"\n');
  const base: NodeJS.ProcessEnv = { ...process.env, VSTUDIO_HOME: path.join(tmp, 'vhome'), VSTUDIO_BATCH_BENCH: path.join(tmp, 'bench.json'), VSTUDIO_DEFAULT_PERSONA: '1', VSTUDIO_TEST_TRUTH: path.join(tmp, 'truth.json'), VSTUDIO_CODEX_CONFIG: path.join(tmp, 'codex-config.toml'), VSTUDIO_AUTH_CACHE: path.join(tmp, 'auth-cache.json') };
  for (const k of Object.keys(base)) if (k.startsWith('VSTUDIO_LLM_')) delete base[k];
  for (const k of ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'VSTUDIO_PERSONA']) delete base[k];
  // made on autopilot by the rules (no model for the run itself)
  const fxEnv = { ...base, PYTHONPATH: path.join(REPO, 'lib'), VSTUDIO_LLM_PROVIDER: 'none', ...Object.fromEntries(['SEGMENT_PLAN', 'PROOFREAD', 'GLOSSARY', 'COPY', 'SCRIPT', 'PLANNER', 'INTAKE', 'OUTPUT_EDIT'].map((t) => [`VSTUDIO_LLM_${t}_PROVIDER`, 'none'])) };
  const out = execFileSync(process.env.DESK_PYTHON || 'python3', [path.join(import.meta.dirname, 'fixture', 'real_project.py'), tmp, '--autopilot'], { env: fxEnv, encoding: 'utf8' });
  const fx = JSON.parse(out.trim().split('\n').pop()!) as { dir: string; status: string };
  expect(fx.status).toBe('done');
  // the app: her routes (Claude Code, Codex as fallback) come from the desk's own routes file, nothing in the env
  app = await electron.launch({
    args: [path.resolve(import.meta.dirname, '../..')],
    env: { ...base, PYTHONPATH: HOOK, MODEL_FAKE_BIN: BIN, VSTUDIO_CLI_EXTRA_DIRS: '', DESK_ENGINE_MOCK: '', DESK_USER_DATA: path.join(tmp, 'profile'), DESK_HISTORY_WATCH: '', DESK_HIDE_WINDOW: '1', DESK_SHARED_CACHE: path.join(tmp, 'cache'), DESK_HF_HUB: '', DESK_SKIP_FIRST_RUN: '1', VITE_DEV_SERVER_URL: '' },
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
  const find = async () => (await api<{ items: { id: string; dir: string }[] }>('/api/history')).items.find((i) => fs.realpathSync(i.dir) === fs.realpathSync(fx.dir))?.id ?? '';
  await expect.poll(find, { timeout: 60000 }).not.toBe('');
  id = await find();
  projDir = fx.dir;
});

test.afterAll(async () => {
  await closeApp(app);
});

const hash = (h: string) => page.evaluate((x) => (location.hash = x), h);
const shot = (name: string) => page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
async function api<T>(p: string): Promise<T> {
  return page.evaluate(async (u) => {
    const info = await window.desk.engineInfo();
    return (await fetch(info.baseUrl + u, { headers: { Authorization: `Bearer ${info.token}` } })).json();
  }, p) as Promise<T>;
}
const input = () => page.getByTestId('chat-input');
async function say(text: string) {
  await input().fill(text);
  await input().press('Enter');
}

test('/model in the clip chat: what runs, a picker; a request uses the CLI default', async () => {
  test.setTimeout(240000);
  await hash(`#/p/${id}/clip/talk`);
  await expect(page.getByTestId('editor')).toBeVisible({ timeout: 60000 });
  await page.getByTestId('studio-ai-input').fill('/model');
  await page.getByTestId('studio-ai-input').press('Enter');
  const turn = page.getByTestId('chat-model-turn').last();
  await expect(turn).toBeVisible({ timeout: 30000 });
  await expect(turn.getByTestId('model-current')).toHaveText('Using Claude Code · CLI default.');
  await expect(turn.getByTestId('model-picker')).toBeVisible();
  await expect(turn.getByTestId('model-pick-claude-opus-5-5')).toBeVisible();
  await expect(page.getByTestId('ce-provider-chip')).toContainText('Claude Code · CLI default');
  expect(calls()).toEqual([]); // a command is never sent to the model
  // "/" lists the commands, /model first, /help last
  await input().fill('/');
  await expect(page.getByTestId('slash-menu').getByRole('option')).toHaveText([/\/model/, /\/trim/, /\/captions/, /\/effect/, /\/cover/, /\/export/, /\/help/]);
  await input().fill('');
  // a request: answered by Claude Code on its own default (no --model), and the reply says which model that was
  await say('does this need any change?');
  await expect(page.getByTestId('chat-ai').last().getByTestId('chat-cost')).toContainText('Claude Code · claude-opus-4-7[1m]', { timeout: 120000 });
  await expect(page.getByTestId('chat-ai').last().getByTestId('chat-say')).toHaveText('It already reads well.'); // the model's own words
  expect(calls().length).toBe(1);
  expect(modelArg(calls()[0])).toBeNull();
  await shot('M1-model-current');
});

test('/model 5.5 switches to Opus 5.5: said in the thread, on the chip, and the next reply runs on it', async () => {
  test.setTimeout(240000);
  await say('/model 5.5');
  const reply = page.getByTestId('chat-model-turn').last().getByTestId('model-reply');
  await expect(reply).toHaveText('This project now uses Claude Code · Opus 5.5, from its next AI step. Your default stays Claude Code · CLI default.', { timeout: 30000 });
  await expect(page.getByTestId('ce-provider-chip')).toHaveAttribute('data-model', 'claude-opus-5-5');
  await expect(page.getByTestId('ce-provider-chip')).toContainText('Claude Code · Opus 5.5');
  expect(projAi()).toEqual({ provider: 'claude-code', model: 'claude-opus-5-5' });
  expect(routes().default.model ?? null).toBeNull(); // her default is untouched: only this project switched
  expect(calls().length).toBe(1);
  await say('and now?');
  await expect(page.getByTestId('chat-ai').last().getByTestId('chat-cost')).toContainText('Claude Code · claude-opus-5-5', { timeout: 120000 });
  expect(modelArg(calls()[calls().length - 1])).toBe('claude-opus-5-5');
  await shot('M2-model-switched');
});

test('/model sonnet -> the newest Sonnet; the picker; unknown commands never reach the model', async () => {
  test.setTimeout(120000);
  const n = calls().length;
  await say('/model sonnet');
  await expect(page.getByTestId('chat-model-turn').last().getByTestId('model-reply')).toHaveText(/Sonnet 5\.5/, { timeout: 30000 });
  await expect(page.getByTestId('ce-provider-chip')).toHaveAttribute('data-model', 'claude-sonnet-5-5');
  // nothing matches: said so, nothing changes
  await say('/model 4.7');
  await expect(page.getByTestId('chat-model-turn').last().getByTestId('model-reply')).toHaveText(/No model matches “4\.7”\. Try one of: Opus 5\.5, Sonnet 5\.5/, { timeout: 30000 });
  await expect(page.getByTestId('ce-provider-chip')).toHaveAttribute('data-model', 'claude-sonnet-5-5');
  // the picker of a fresh /model: Haiku
  await say('/model');
  await page.getByTestId('chat-model-turn').last().getByTestId('model-pick-claude-haiku-5-5').click();
  await expect(page.getByTestId('chat-model-turn').last().getByTestId('model-reply')).toHaveText(/Haiku 5\.5/, { timeout: 30000 });
  // an earlier /model keeps what ran then (not what runs now), and only the newest one has the picker
  await expect(page.getByTestId('chat-model-turn').first().getByTestId('model-current')).toHaveText('Using Claude Code · CLI default.');
  await expect(page.getByTestId('model-picker')).toHaveCount(0);
  expect(projAi()).toEqual({ provider: 'claude-code', model: 'claude-haiku-5-5' });
  expect(routes().default.model ?? null).toBeNull();
  // the chip's menu offers the same models
  await page.getByTestId('ce-provider-chip').click();
  await page.getByTestId('ce-provider-chip-model-claude-opus-5-5').click();
  await expect(page.getByTestId('ce-provider-chip')).toHaveAttribute('data-model', 'claude-opus-5-5');
  await say('/foo');
  await expect(page.getByTestId('chat-help-turn').last()).toContainText('“/foo” isn’t a command.', { timeout: 30000 });
  await expect(page.getByTestId('chat-help-turn').last().getByTestId('slash-help')).toContainText('/model');
  expect(calls().length).toBe(n); // none of these went to the model
  const missing = await page.evaluate(() => document.body.innerText.match(/⟦[^⟧]+⟧|\b(?:mdl|ce|aiacc)\.[a-z][\w.-]+/g));
  expect(missing).toBeNull();
  await shot('M3-commands');
});

test('Settings › AI: the model of the AI in use, and Codex’s config model her login cannot use', async () => {
  test.setTimeout(120000);
  await hash('#/settings/ai');
  await expect(page.getByTestId('ai-accounts')).toBeVisible({ timeout: 30000 });
  // the clip chat's /model switched only that project: her default is still the CLI's own model
  await expect(page.getByTestId('model-select-claude-code')).toHaveValue('', { timeout: 30000 });
  await page.getByTestId('model-select-claude-code').selectOption('claude-opus-5-5');
  await expect.poll(() => routes().default.model ?? routes().models?.['claude-code'] ?? null).toBe('claude-opus-5-5');
  // Codex: the catalog of her login (the stand-in's), and her config.toml's gpt-6-astra flagged with the fix
  const problem = page.getByTestId('model-problem-codex');
  await expect(problem).toContainText('gpt-6-astra', { timeout: 60000 });
  await expect(problem).toContainText('config.toml');
  // the unusable CLI default is never offered by name: "Codex — fix model"
  await expect(page.getByTestId('model-select-codex').locator('option[value=""]')).toHaveText('Codex — fix model');
  await page.getByTestId('ai-switch').click();
  await expect(page.getByTestId('switch-codex')).toHaveText('Codex — fix model');
  await expect(page.getByTestId('switch-setup-more')).toBeVisible();
  await page.keyboard.press('Escape');
  await problem.getByTestId('model-fix-codex').click();
  await expect(problem).toHaveCount(0);
  await expect(page.getByTestId('model-select-codex')).toHaveValue('gpt-6-luna');
  expect(routes().default.fallback).toEqual([{ provider: 'codex', model: 'gpt-6-luna' }]);
  await page.getByTestId('model-select-claude-code').selectOption('');
  await expect.poll(() => routes().default.model ?? null).toBeNull();
  await shot('M4-settings');
});
