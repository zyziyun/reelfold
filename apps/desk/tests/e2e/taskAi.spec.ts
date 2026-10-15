// Per-task AI (her words 2026-10-13: "model 的选择和切换可以放到每次的任务里么，现在都是在 setting 一次性配置不够方便").
// REAL engine sidecar, isolated temp profile, window hidden; a talking-head project made by the real engine on the
// rules (fixture/real_project.py). The only stand-ins: ROOT/bin/claude (answers like `claude -p`, logs each call) and a
// Kimi endpoint on 127.0.0.1 (an OpenAI-compatible /v1/chat/completions that logs each request: VSTUDIO_KIMI_BASE_URL,
// a test key in MOONSHOT_API_KEY). Her default stays Claude Code throughout.
//   1. the composer's AI chip: Kimi for THIS request -> the plan is made by Kimi (Claude is never asked), the request
//      shows Kimi on its row and its run page, and the chip is back to her default for the next request
//   2. a project's AI switched on its page -> the next AI step (a clip chat request) runs on it; switched back from
//      the run page header -> the next one runs on Claude again
//   3. `/model kimi` in the project's clip chat -> this project only (project.yaml), her default untouched, said so;
//      "Make this my default" -> her default
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import type { AddressInfo } from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

let app: ElectronApplication;
let page: Page;
let id = '';
let projDir = '';
let kimi: http.Server;
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-taskai-'));
const BIN = path.join(tmp, 'bin');
const HOOK = path.join(tmp, 'hook');
const CLAUDE_LOG = path.join(tmp, 'claude.log');
const KIMI_LOG: { model: string; intake: boolean }[] = [];
const SHOTS = process.env.DESK_SHOTS_DIR ?? path.resolve(import.meta.dirname, '../../test-results/task-ai');
fs.mkdirSync(SHOTS, { recursive: true });

const PLAN = {
  projects: [{ recipe: 'talkinghead', name: 'Kimi talk', materials: ['f1'], inputs: { video: ['f1'] }, items: { method: 'per-file' } }],
  questions: [],
  risks: [],
  summary_zh: 'One clip.',
  summary_lang: 'en',
};
const EDIT = (who: string) => ({ ops: [], summary: `${who} says it already reads well.` });

const CLAUDE = `#!/usr/bin/env python3
"""TESTS ONLY: Claude Code's -p answer; logs each AI request."""
import json, sys
a = sys.argv[1:]
if a[:1] == ["--version"]:
    print("9.9.9 (Claude Code)"); sys.exit(0)
if a[:2] == ["auth", "status"]:
    print(json.dumps({"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "max"})); sys.exit(0)
prompt = sys.stdin.read()
if "Reply with: ok" not in prompt:
    with open(${JSON.stringify(CLAUDE_LOG)}, "a", encoding="utf-8") as f:
        f.write(json.dumps({"intake": "reply_language" in prompt, "argv": [x for x in a if len(x) < 80]}) + "\\n")
model = a[a.index("--model") + 1] if "--model" in a else "claude-opus-4-7[1m]"
out = ${JSON.stringify(PLAN)} if "reply_language" in prompt else ${JSON.stringify(EDIT('Claude'))}
res = {"type": "result", "subtype": "success", "is_error": False, "result": json.dumps(out), "structured_output": out,
       "usage": {"input_tokens": 120, "output_tokens": 9}, "total_cost_usd": 0.01, "modelUsage": {model: {"outputTokens": 9}}}
if "stream-json" in a:
    print(json.dumps({"type": "system", "subtype": "init", "model": model}))
print(json.dumps(res))
`;
const HOOK_PY = `import os, sys
_bin = os.environ.get("MODEL_FAKE_BIN")
if _bin:
    try:
        from vstudio import llm as _llm
        _find, _argv = _llm.find_cli, _llm.cli_argv
        _fakes = {"claude": os.path.join(_bin, "claude")}
        _llm.find_cli = lambda name, opts=None: _fakes.get(name) if name in ("claude", "codex") else _find(name, opts)
        _llm.cli_argv = lambda exe, windows=None: [sys.executable, exe] if exe in _fakes.values() else _argv(exe, windows)
    except Exception:
        pass
    try:
        from vstudio import acp as _acp
        _acp.find = lambda agent, opts=None: None
    except Exception:
        pass
`;

const claudeCalls = () => (fs.existsSync(CLAUDE_LOG) ? fs.readFileSync(CLAUDE_LOG, 'utf8').trim().split('\n').filter(Boolean).map((l) => JSON.parse(l) as { intake: boolean; argv: string[] }) : []);
const routes = () => JSON.parse(fs.readFileSync(path.join(tmp, 'profile', 'llm-routes.json'), 'utf8'));
const projAi = () => {
  // Python writes native CRLF on Windows; read the same persisted AI block on every runner.
  const yaml = fs.readFileSync(path.join(projDir, 'project.yaml'), 'utf8').replace(/\r\n/g, '\n');
  const m = /\nai:\n((?: {2}.*\n)+)/.exec(yaml);
  return m ? Object.fromEntries(m[1].trim().split('\n').map((l) => l.trim().split(': ').map((x) => x.replace(/^'|'$/g, '')))) : null;
};

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  test.setTimeout(300000);
  // the Kimi stand-in: an OpenAI-compatible chat endpoint on this machine
  kimi = http.createServer((req, res) => {
    let body = '';
    req.on('data', (c) => (body += c));
    req.on('end', () => {
      const doc = JSON.parse(body || '{}') as { model?: string; messages?: { content: string }[] };
      const text = (doc.messages ?? []).map((m) => m.content).join('\n');
      const intake = text.includes('reply_language');
      KIMI_LOG.push({ model: doc.model ?? '', intake });
      const out = intake ? PLAN : EDIT('Kimi');
      res.setHeader('content-type', 'application/json');
      res.end(JSON.stringify({ id: 'x', object: 'chat.completion', created: 0, model: doc.model, choices: [{ index: 0, finish_reason: 'stop', message: { role: 'assistant', content: JSON.stringify(out) } }], usage: { prompt_tokens: 50, completion_tokens: 9, total_tokens: 59 } }));
    });
  });
  await new Promise<void>((r) => kimi.listen(0, '127.0.0.1', () => r()));
  const port = (kimi.address() as AddressInfo).port;
  fs.mkdirSync(BIN, { recursive: true });
  fs.mkdirSync(HOOK, { recursive: true });
  fs.writeFileSync(path.join(BIN, 'claude'), CLAUDE);
  fs.chmodSync(path.join(BIN, 'claude'), 0o755);
  fs.writeFileSync(path.join(HOOK, 'sitecustomize.py'), HOOK_PY);
  const base: NodeJS.ProcessEnv = { ...process.env, VSTUDIO_HOME: path.join(tmp, 'vhome'), VSTUDIO_BATCH_BENCH: path.join(tmp, 'bench.json'), VSTUDIO_DEFAULT_PERSONA: '1', VSTUDIO_TEST_TRUTH: path.join(tmp, 'truth.json'), VSTUDIO_AUTH_CACHE: path.join(tmp, 'auth-cache.json') };
  for (const k of Object.keys(base)) if (k.startsWith('VSTUDIO_LLM_') || k.startsWith('VSTUDIO_KIMI_')) delete base[k];
  for (const k of ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'MOONSHOT_API_KEY', 'VSTUDIO_PERSONA', 'VSTUDIO_PROJECT_DIR']) delete base[k];
  const REPO = path.resolve(import.meta.dirname, '../../../..');
  const fxEnv = { ...base, PYTHONPATH: path.join(REPO, 'lib'), VSTUDIO_LLM_PROVIDER: 'none', ...Object.fromEntries(['SEGMENT_PLAN', 'PROOFREAD', 'GLOSSARY', 'COPY', 'SCRIPT', 'PLANNER', 'INTAKE', 'OUTPUT_EDIT'].map((t) => [`VSTUDIO_LLM_${t}_PROVIDER`, 'none'])) };
  const out = execFileSync(process.env.DESK_PYTHON || 'python3', [path.join(import.meta.dirname, 'fixture', 'real_project.py'), tmp, '--autopilot'], { env: fxEnv, encoding: 'utf8' });
  const fx = JSON.parse(out.trim().split('\n').pop()!) as { dir: string; status: string };
  expect(fx.status).toBe('done');
  projDir = fx.dir;
  app = await electron.launch({
    args: [path.resolve(import.meta.dirname, '../..')],
    env: { ...base, PYTHONPATH: HOOK, MODEL_FAKE_BIN: BIN, VSTUDIO_KIMI_BASE_URL: `http://127.0.0.1:${port}/v1`, MOONSHOT_API_KEY: 'test-moonshot-key', VSTUDIO_CLI_EXTRA_DIRS: '', DESK_ENGINE_MOCK: '', DESK_USER_DATA: path.join(tmp, 'profile'), DESK_HISTORY_WATCH: '', DESK_HIDE_WINDOW: '1', DESK_SHARED_CACHE: path.join(tmp, 'cache'), DESK_HF_HUB: '', DESK_SKIP_FIRST_RUN: '1', VITE_DEV_SERVER_URL: '' },
  });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForURL(/^app:\/\/desk\//);
  // ask me first: the request stops at its plan card (the plan is what this test is about)
  await page.evaluate(async () => {
    localStorage.setItem('i18n.strict', '1');
    await window.desk.setSettings({ lang: 'en', autopilot: false });
  });
  await page.reload();
  await page.waitForURL(/^app:\/\/desk\//);
  expect((await page.evaluate(() => window.desk.engineInfo())).mode).toBe('real');
  const find = async () => (await api<{ items: { id: string; dir: string }[] }>('/api/history')).items.find((i) => fs.realpathSync(i.dir) === fs.realpathSync(fx.dir))?.id ?? '';
  await expect.poll(find, { timeout: 60000 }).not.toBe('');
  id = await find();
});

test.afterAll(async () => {
  await closeApp(app);
  kimi?.close();
});

const hash = (h: string) => page.evaluate((x) => (location.hash = x), h);
const shot = (name: string) => page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
async function api<T>(p: string): Promise<T> {
  return page.evaluate(async (u) => {
    const info = await window.desk.engineInfo();
    return (await fetch(info.baseUrl + u, { headers: { Authorization: `Bearer ${info.token}` } })).json();
  }, p) as Promise<T>;
}
const noMissing = async () => expect(await page.evaluate(() => document.body.innerText.match(/⟦[^⟧]+⟧|\b(?:tai|mdl|aiacc)\.[a-z][\w.-]+/g))).toBeNull();

test('the composer’s AI chip: Kimi for this request plans it with Kimi; her default is back for the next one', async () => {
  test.setTimeout(300000);
  await hash('#/');
  await page.evaluate((f) => sessionStorage.setItem('v4.composer', JSON.stringify({ prompt: 'Cut this talk into a short clip', files: [f] })), path.join(tmp, 'media', 'talk.mp4'));
  await page.reload();
  await page.waitForURL(/^app:\/\/desk\//);
  const chip = page.getByTestId('composer-ai');
  await expect(chip).toHaveAttribute('data-provider', 'claude-code', { timeout: 30000 });
  await expect(chip).toHaveAttribute('data-own', '0');
  await chip.click();
  // ready-only: Kimi (its key is set) is offered; "Set up more…" for the rest
  await expect(page.getByTestId('composer-ai-pick-kimi')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('composer-ai-setup')).toBeVisible();
  await page.getByTestId('composer-ai-pick-kimi').click();
  await expect(chip).toHaveAttribute('data-provider', 'kimi');
  await expect(chip).toHaveAttribute('data-own', '1');
  await expect(chip).toContainText('Kimi');
  await shot('T1-composer-kimi');
  await page.getByTestId('make-plan').click();
  // the plan: made by Kimi, never by Claude
  await expect.poll(() => KIMI_LOG.filter((x) => x.intake).length, { timeout: 180000 }).toBeGreaterThan(0);
  expect(claudeCalls().filter((c) => c.intake)).toEqual([]);
  const open = async () => (await api<{ items: { id: string; ai?: { provider: string } | null; state: string }[] }>('/api/intake/open')).items[0];
  await expect.poll(async () => (await open())?.state, { timeout: 180000 }).toBe('done');
  expect((await open()).ai).toMatchObject({ provider: 'kimi' });
  // the chip is her default again for the next request
  await expect(chip).toHaveAttribute('data-provider', 'claude-code');
  await expect(chip).toHaveAttribute('data-own', '0');
  // the request's row and its run page say Kimi
  await hash('#/studio');
  await expect(page.getByTestId('studio-row-ai').filter({ hasText: 'Kimi' }).first()).toBeVisible({ timeout: 30000 });
  await page.getByTestId('studio-row-ai').filter({ hasText: 'Kimi' }).first().click();
  await expect(page.getByTestId('run-ai-chip')).toHaveAttribute('data-provider', 'kimi', { timeout: 30000 });
  expect(routes().default.provider).toBe('claude-code');
  await noMissing();
  await shot('T2-request-kimi');
});

test('a project’s AI switched on its page: the next AI step runs on it; switched back, Claude again', async () => {
  test.setTimeout(300000);
  await hash(`#/p/${id}/clip/talk`);
  await expect(page.getByTestId('editor')).toBeVisible({ timeout: 60000 });
  // the clip's chat opens with her first words (a command: never sent to a model)
  await page.getByTestId('studio-ai-input').fill('/help');
  await page.getByTestId('studio-ai-input').press('Enter');
  await expect(page.getByTestId('chat-help-turn').last()).toBeVisible({ timeout: 30000 });
  const chip = page.getByTestId('ce-provider-chip');
  await expect(chip).toHaveAttribute('data-provider', 'claude-code', { timeout: 30000 });
  await chip.click();
  await page.getByTestId('ce-provider-chip-pick-kimi').click();
  await expect(chip).toHaveAttribute('data-provider', 'kimi');
  await expect.poll(projAi).toEqual({ provider: 'kimi' });
  expect(routes().default.provider).toBe('claude-code');
  const before = { kimi: KIMI_LOG.length, claude: claudeCalls().length };
  await page.getByTestId('chat-input').fill('does this need any change?');
  await page.getByTestId('chat-input').press('Enter');
  await expect(page.getByTestId('chat-ai').last().getByTestId('chat-say')).toHaveText('Kimi says it already reads well.', { timeout: 120000 });
  expect(KIMI_LOG.length).toBe(before.kimi + 1);
  expect(claudeCalls().length).toBe(before.claude);
  // the switch is in the project's decisions log
  expect(fs.readFileSync(path.join(projDir, 'state', 'autopilot.jsonl'), 'utf8')).toContain('"event": "ai"');
  await shot('T3-project-kimi');
  // back to her default from the project's own page: the next AI step is Claude's
  await hash(`#/p/${id}/clips`);
  const pchip = page.getByTestId('project-ai');
  await expect(pchip).toHaveAttribute('data-provider', 'kimi', { timeout: 30000 });
  await pchip.click();
  await page.getByTestId('project-ai-default').click();
  await expect(pchip).toHaveAttribute('data-own', '0');
  await expect.poll(projAi).toBeNull();
  await hash(`#/p/${id}/clip/talk`);
  await expect(page.getByTestId('editor')).toBeVisible({ timeout: 60000 });
  await page.getByTestId('studio-ai-input').fill('and now?');
  await page.getByTestId('studio-ai-input').press('Enter');
  await expect(page.getByTestId('chat-ai').last().getByTestId('chat-say')).toHaveText('Claude says it already reads well.', { timeout: 120000 });
  expect(KIMI_LOG.length).toBe(before.kimi + 1);
  await noMissing();
});

test('/model kimi in the project’s chat switches this project only, says so; “Make this my default”', async () => {
  test.setTimeout(240000);
  const n = KIMI_LOG.length;
  await page.getByTestId('chat-input').fill('/model kimi');
  await page.getByTestId('chat-input').press('Enter');
  const turn = page.getByTestId('chat-model-turn').last();
  await expect(turn.getByTestId('model-reply')).toHaveText(/^This project now uses Kimi · .+, from its next AI step\. Your default stays Claude Code · CLI default\.$/, { timeout: 30000 });
  await expect(page.getByTestId('ce-provider-chip')).toHaveAttribute('data-provider', 'kimi');
  expect(projAi()?.provider).toBe('kimi');
  expect(routes().default.provider).toBe('claude-code'); // her default untouched
  expect(KIMI_LOG.length).toBe(n); // a command never reaches the model
  await shot('T4-model-kimi');
  await turn.getByTestId('model-make-default').click();
  await expect.poll(() => routes().default.provider).toBe('kimi');
  await noMissing();
});

test('the composer default is saved for this request even when the intake task has an older route', async () => {
  test.setTimeout(180000);
  await page.evaluate(async () => {
    const doc = await window.desk.ai.routes();
    await window.desk.ai.setRoutes({...doc.routes, default:{provider:'claude-code', fallback:[]}, tasks:{...doc.routes.tasks, plan:{provider:'none', fallback:[]}}});
  });
  await hash('#/');
  await page.evaluate(f => sessionStorage.setItem('v4.composer', JSON.stringify({prompt:'Plan first: cut this talk into a short clip', files:[f]})), path.join(tmp,'media','talk.mp4'));
  await page.reload();
  await expect(page.getByTestId('composer-ai')).toHaveAttribute('data-provider','claude-code');
  const before = claudeCalls().filter(x=>x.intake).length;
  await page.getByTestId('make-plan').click();
  await expect.poll(()=>claudeCalls().filter(x=>x.intake).length, {timeout:120000}).toBeGreaterThan(before);
  await expect.poll(async () => (await api<{items:{ai?:{provider:string}; prompt:string}[]}>('/api/intake/open')).items.some(x=>x.prompt.startsWith('Plan first:') && x.ai?.provider==='claude-code')).toBe(true);
});
