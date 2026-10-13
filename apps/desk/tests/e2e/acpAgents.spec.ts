// Settings › AI › Coding agents (ACP) and the China-friendly API keys (window hidden, mock engine, isolated profile;
// the engine's `auth status` / `models` / `test` stand in through DESK_AI_MOCK - the engine side runs against a
// stand-in ACP agent in tests/test_acp.py). Detection: installed agents as rows (signed in, not signed in, region
// blocked), the absent ones folded with their install command; the one-click test call; an agent's model; Qwen's
// international endpoint and a fallback chain Claude Code -> Qwen Code -> DeepSeek in the engine's routes file;
// zh copy with no missing keys.
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

let app: ElectronApplication;
let page: Page;
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-acp-'));
const mock = path.join(tmp, 'ai-mock');
const routesFile = () => JSON.parse(fs.readFileSync(path.join(tmp, 'profile', 'llm-routes.json'), 'utf8'));

const row = (provider: string, state: string, extra: Record<string, unknown> = {}) => ({
  provider,
  kind: 'subscription-cli',
  state,
  ready: ['logged-in', 'installed'].includes(state),
  can_login: true,
  can_logout: false,
  install: { url: `https://example.com/${provider}`, command: `npm install -g ${provider}` },
  ...extra,
});
const agent = (provider: string, state: string, china: string, extra: Record<string, unknown> = {}) =>
  row(provider, state, { acp: true, china, ...extra });

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  fs.mkdirSync(mock, { recursive: true });
  fs.writeFileSync(
    path.join(mock, 'status.json'),
    JSON.stringify({
      providers: [
        row('claude-code', 'not-installed'),
        row('codex', 'not-installed'),
        agent('gemini-cli', 'error', 'no', { code: 'region-blocked', message: { code: 'agent-region', message: 'Not available in your region: User location is not supported', message_zh: '你所在的地区用不了：User location is not supported' } }),
        agent('cursor-agent', 'not-installed', 'partly'),
        agent('copilot', 'not-installed', 'partly'),
        agent('opencode', 'not-installed', 'yes'),
        agent('claude-acp', 'not-installed', 'no'),
        agent('codex-acp', 'not-installed', 'no'),
        agent('qwen-code', 'logged-in', 'yes', { verified: true, models: ['qwen3-coder-plus', 'qwen3-coder-flash'] }),
        agent('kimi-cli', 'not-logged-in', 'yes', { message: { code: 'agent-not-logged-in', message: 'Not signed in: run kimi login and sign in', message_zh: '未登录：运行 kimi login 登录' } }),
        agent('codebuddy', 'not-installed', 'yes'),
        agent('iflow', 'not-installed', 'yes'),
        { provider: 'deepseek', kind: 'api', state: 'configured', ready: true, key_env: 'DEEPSEEK_API_KEY', install: { url: 'https://platform.deepseek.com/api_keys', command: 'pip install openai' } },
        { provider: 'qwen', kind: 'api', state: 'not-configured', ready: false, key_env: 'DASHSCOPE_API_KEY', region: 'cn', regions: ['cn', 'intl'], install: { url: 'https://dashscope.console.aliyun.com/apiKey', command: 'pip install openai' } },
        { provider: 'doubao', kind: 'api', state: 'not-configured', ready: false, key_env: 'ARK_API_KEY', region: 'cn', regions: ['cn', 'intl'], install: { url: 'https://console.volcengine.com/ark', command: 'pip install openai' } },
      ],
    }),
  );
  fs.writeFileSync(
    path.join(mock, 'models.json'),
    JSON.stringify({
      providers: [
        { provider: 'qwen-code', source: 'agent', cli_default: 'qwen3-coder-plus', models: [{ id: 'qwen3-coder-plus', label: 'Qwen3 Coder Plus' }, { id: 'qwen3-coder-flash', label: 'Qwen3 Coder Flash' }] },
        { provider: 'kimi-cli', source: 'list', models: [] },
      ],
    }),
  );
  fs.writeFileSync(
    path.join(mock, 'test.json'),
    JSON.stringify({
      'qwen-code': { ok: true, provider: 'qwen-code', model: 'qwen3-coder-plus', seconds: 4.2 },
      'kimi-cli': { ok: false, provider: 'kimi-cli', error: 'Kimi CLI is not logged in: run `kimi login` in a terminal and sign in' },
    }),
  );
  const persona = { provider: 'claude-code', model: null, fallback: ['codex'] };
  fs.writeFileSync(path.join(mock, 'routes.json'), JSON.stringify(Object.fromEntries(['default', 'segment_plan', 'proofread', 'glossary', 'copy', 'intake', 'output_edit'].map((k) => [k, persona]))));
  app = await electron.launch({
    args: [path.resolve(import.meta.dirname, '../..')],
    env: {
      ...process.env,
      DESK_ENGINE_MOCK: '1',
      DESK_AI_MOCK: mock,
      DESK_USER_DATA: path.join(tmp, 'profile'),
      VSTUDIO_HOME: path.join(tmp, 'vhome'),
      DESK_HISTORY_WATCH: path.join(tmp, 'demos'),
      DESK_STUDIO: '0',
      DESK_HIDE_WINDOW: '1',
      DESK_SHARED_CACHE: path.join(tmp, 'cache'),
      DESK_HF_HUB: '',
      DESK_SKIP_FIRST_RUN: '1',
      VITE_DEV_SERVER_URL: '',
    },
  });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForURL(/^app:\/\/desk\//);
});

test.afterAll(async () => {
  await closeApp(app);
});

const hash = (h: string) => page.evaluate((x) => (location.hash = x), h);
const card = (p: string) => page.getByTestId(`provider-${p}`);

test('detection: installed agents as rows, the absent ones folded with their install command', async () => {
  await hash('#/settings/ai');
  const group = page.getByTestId('ai-agents');
  await expect(group).toBeVisible();
  await expect(card('qwen-code').getByTestId('provider-pill')).toHaveAttribute('data-state', 'logged-in', { timeout: 15000 });
  await expect(card('qwen-code').getByTestId('china-qwen-code')).toHaveText('Works in China');
  await expect(card('kimi-cli').getByTestId('provider-pill')).toHaveText('Not logged in');
  await expect(card('kimi-cli').getByTestId('login-kimi-cli')).toBeVisible();
  await expect(card('gemini-cli').getByTestId('provider-pill')).toHaveText('Not available in your region');
  await expect(card('gemini-cli').getByTestId('agent-msg-gemini-cli')).toContainText('User location is not supported');
  // not installed: folded until asked for, then each with its install command
  await expect(card('codebuddy')).toHaveCount(0);
  await page.getByTestId('agents-more').click();
  await expect(card('codebuddy').getByTestId('install-cmd-codebuddy')).toHaveText('npm install -g codebuddy');
  await expect(card('codebuddy').getByTestId('china-codebuddy')).toHaveText('Works in China');
  await expect(card('copilot').getByTestId('china-copilot')).toHaveText('Partly in China');
  await page.getByTestId('agents-more').click();
  await expect(card('codebuddy')).toHaveCount(0);
  // the switcher offers installed agents only
  await page.getByTestId('ai-switch').click();
  await expect(page.getByTestId('switch-qwen-code')).toBeVisible();
  await expect(page.getByTestId('switch-codebuddy')).toHaveCount(0);
  await page.keyboard.press('Escape');
});

test('the one-click test call says whether it works, in plain words', async () => {
  await card('qwen-code').getByTestId('agent-test-qwen-code').click();
  await expect(page.getByText('Works · qwen3-coder-plus · 4.2 s')).toBeVisible();
  await card('kimi-cli').getByTestId('agent-test-kimi-cli').click();
  await expect(page.getByText(/Did not work: Kimi CLI is not logged in/)).toBeVisible();
});

test('an agent’s model, Qwen’s international endpoint and the fallback chain reach the engine’s routes file', async () => {
  await card('qwen-code').getByTestId('model-select-qwen-code').selectOption('qwen3-coder-flash');
  await expect.poll(() => routesFile().default).toEqual({ provider: 'claude-code', fallback: ['codex'] });
  // the order sheet: Claude Code -> Qwen Code -> DeepSeek key
  await page.getByTestId('ai-order').click();
  await page.getByTestId('route-default-fallbacks').getByTestId('fallback-item').filter({ hasText: 'Codex' }).getByRole('button').click();
  await page.getByTestId('route-default-add-fallback').selectOption('qwen-code');
  await page.getByTestId('route-default-add-fallback').selectOption('deepseek');
  await expect.poll(() => routesFile().default).toEqual({ provider: 'claude-code', fallback: [{ provider: 'qwen-code', model: 'qwen3-coder-flash' }, 'deepseek'] });
  await expect(page.getByTestId('route-default-add-fallback').locator('option[value="codebuddy"]')).toHaveCount(0); // not installed
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('ai-fallback-sentence')).toContainText('Qwen Code → DeepSeek');
  // API keys: Qwen on its international endpoint
  await page.getByTestId('ai-add-key').click();
  await expect(card('doubao')).toContainText('Volcengine Ark');
  await page.getByTestId('region-qwen').selectOption('intl');
  await expect.poll(() => routesFile().regions).toEqual({ qwen: 'intl' });
  await page.getByTestId('region-qwen').selectOption('cn');
  await expect.poll(() => routesFile().regions).toBeUndefined();
  await page.keyboard.press('Escape');
});

test('the agents in 简体中文: no missing keys', async () => {
  await page.evaluate(async () => {
    localStorage.setItem('i18n.strict', '1');
    await window.desk.setSettings({ lang: 'zh-CN' });
  });
  await page.reload();
  await page.waitForURL(/^app:\/\/desk\//);
  await hash('#/settings/ai');
  await expect(card('qwen-code').getByTestId('china-qwen-code')).toHaveText('国内可直接用', { timeout: 15000 });
  await expect(page.getByTestId('ai-agents')).toContainText('编程助手');
  await expect(card('kimi-cli')).toContainText('用 Kimi / 月之暗面账号登录');
  await expect(card('gemini-cli').getByTestId('provider-pill')).toHaveText('你所在的地区用不了');
  await page.getByTestId('agents-more').click();
  await expect(card('codebuddy')).toContainText('国内站');
  await page.getByTestId('ai-add-key').click();
  await expect(card('qwen')).toContainText('阿里云百炼');
  const missing = await page.evaluate(() => document.body.innerText.match(/⟦[^⟧]+⟧|\b(aiacc|agents)\.[\w.-]+/g));
  expect(missing).toBeNull();
  await page.evaluate(() => localStorage.removeItem('i18n.strict'));
});
