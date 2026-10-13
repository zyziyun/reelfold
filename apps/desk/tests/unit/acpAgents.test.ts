// Coding agents over ACP and the China-friendly providers: which providers exist and in what order, what pickers
// offer, the mainland / international endpoint going into the engine's routes file, the region-blocked notice and
// pill, IPC validation, and the copy for every agent in every language.
import { describe, expect, it } from 'vitest';
import {
  CLI_PROVIDER_IDS,
  fallbackNotice,
  hasRegions,
  isAcp,
  normalizeRoutes,
  offerable,
  pill,
  PROVIDER_IDS,
  PROVIDERS,
  routesFile,
  type AiRoutes,
} from '../../src/shared/aiRoutes';
import { withModel, withProviderModel } from '../../src/shared/aiModels';
import { validateIpc } from '../../src/shared/ipc';
import { LANGS, LOCALES } from '../../src/renderer/src/i18n';

const ACP = ['gemini-cli', 'cursor-agent', 'copilot', 'opencode', 'claude-acp', 'codex-acp', 'qwen-code', 'kimi-cli', 'codebuddy', 'iflow'];

describe('providers', () => {
  it('every ACP agent of the engine (vstudio.acp.IDS), international first, then the ones made in China', () => {
    expect(PROVIDER_IDS.filter(isAcp)).toEqual(ACP);
    const china = ACP.filter((p) => PROVIDERS[p as keyof typeof PROVIDERS].china === 'yes' && p !== 'opencode');
    expect(ACP.slice(-china.length)).toEqual(china);
    expect(CLI_PROVIDER_IDS).toEqual(['claude-code', 'codex', ...ACP]);
    expect(PROVIDERS.doubao).toMatchObject({ kind: 'api', secret: 'ark', china: 'yes' });
    expect(PROVIDER_IDS.indexOf('openrouter')).toBeLessThan(PROVIDER_IDS.indexOf('deepseek'));
    expect(['qwen', 'kimi', 'glm', 'doubao'].every(hasRegions) && !hasRegions('deepseek')).toBe(true);
  });

  it('pickers offer an agent only once it is installed (and always the current choice)', () => {
    expect(offerable('qwen-code', { state: 'not-installed' })).toBe(false);
    expect(offerable('qwen-code', { state: 'not-installed' }, 'qwen-code')).toBe(true);
    expect(offerable('qwen-code', { state: 'installed' })).toBe(true);
    expect(offerable('qwen-code', undefined)).toBe(false); // not checked yet: not offered
    expect(offerable('codex', { state: 'not-installed' })).toBe(true);
  });
});

describe('regions', () => {
  const base: AiRoutes = { default: { provider: 'qwen-code', model: null, fallback: ['deepseek', 'qwen'] }, tasks: {} };

  it('the international endpoint goes into the routes file; cn is the default and is not written', () => {
    const r = normalizeRoutes({ ...base, regions: { qwen: 'intl', kimi: 'cn', deepseek: 'intl', bogus: 'intl' } });
    expect(r.regions).toEqual({ qwen: 'intl', kimi: 'cn' });
    const f = routesFile(r);
    expect(f.regions).toEqual({ qwen: 'intl', kimi: 'cn' });
    expect(f.default).toEqual({ provider: 'qwen-code', fallback: ['deepseek', 'qwen'] });
    expect(routesFile(base).regions).toBeUndefined();
  });

  it('picking a model keeps the endpoints', () => {
    const r = { ...base, regions: { glm: 'intl' as const } };
    expect(withModel(r, 'default', 'kimi-cli', 'kimi-k2').regions).toEqual({ glm: 'intl' });
    expect(withProviderModel(r, 'qwen-code', 'qwen3-coder-plus').regions).toEqual({ glm: 'intl' });
  });

  it('IPC accepts cn / intl only', () => {
    expect(validateIpc('ai:setRoutes', { routes: { ...base, regions: { qwen: 'intl' } } })).toBeTruthy();
    expect(() => validateIpc('ai:setRoutes', { routes: { ...base, regions: { qwen: 'mars' } } })).toThrow();
    expect(validateIpc('ai:test', { provider: 'kimi-cli' })).toBeTruthy();
    expect(validateIpc('ai:status', { providers: [...ACP, 'doubao'] })).toBeTruthy();
  });
});

describe('plain words', () => {
  it('region-blocked: the fallback notice and the pill say so', () => {
    expect(fallbackNotice({ from: 'gemini-cli', to: 'qwen-code', code: 'region-blocked' })).toMatchObject({ key: 'aiacc.fb.region', from: 'Gemini CLI', to: 'Qwen Code', login: false });
    expect(fallbackNotice({ from: 'kimi-cli', to: 'deepseek', code: 'not-logged-in' })).toMatchObject({ key: 'aiacc.fb.notLoggedIn', login: true });
    expect(pill({ provider: 'gemini-cli', kind: 'subscription-cli', state: 'error', ready: false, code: 'region-blocked' }).key).toBe('agents.st.region');
    expect(pill({ provider: 'qwen-code', kind: 'subscription-cli', state: 'installed', ready: true })).toEqual({ tone: 'ok', key: 'agents.st.installed' });
  });

  it('every agent has its description and sign-in line, and every region provider its key line, in every language', () => {
    for (const l of LANGS) {
      const m = LOCALES[l].messages as Record<string, string>;
      for (const p of ACP) {
        expect(m[`aiacc.desc.${p}`], `${l} aiacc.desc.${p}`).toBeTruthy();
        expect(m[`agents.acct.${p}`], `${l} agents.acct.${p}`).toBeTruthy();
      }
      for (const p of ['deepseek', 'qwen', 'kimi', 'glm', 'doubao']) expect(m[`agents.key.${p}`], `${l} agents.key.${p}`).toBeTruthy();
      expect(m['fail.reason.ai-region']).toContain('{provider}');
    }
    expect((LOCALES['zh-CN'].messages as Record<string, string>)['agents.china.yes']).toBe('国内可直接用');
  });
});
