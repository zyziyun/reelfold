// Per-task AI (shared/projectAi): a request's / project's own AI from untrusted data, what it runs on (its model, else
// the model picked for that provider, else the app's default), the chip's label, `/model <words>` in a project's chat
// -> the project's new AI, and the routes file passing each provider's model to the engine (a project on Kimi without
// a model of its own runs on the Kimi model picked in Settings).
import { describe, expect, it } from 'vitest';
import { CLAUDE_MODELS, type ModelInfo } from '../../src/shared/aiModels';
import { routesFile, type AiRoutes, type ProviderId } from '../../src/shared/aiRoutes';
import { aiFromWords, aiLabel, aiShort, cleanAi, effectiveAi, sameAi } from '../../src/shared/projectAi';

const KIMI: ModelInfo[] = [
  { id: 'kimi-k2-turbo-preview', label: 'Kimi K2 Turbo' },
  { id: 'kimi-k2-0905-preview', label: 'Kimi K2' },
];
const CODEX: ModelInfo[] = [{ id: 'gpt-6-luna', label: 'GPT-6-Luna' }];
const cat = (p: string) => (p === 'claude-code' ? CLAUDE_MODELS : p === 'kimi' ? KIMI : p === 'codex' ? CODEX : []);
const words = { cliDefault: 'CLI default', providerDefault: 'Provider default', rules: 'Rules' };
const routes: AiRoutes = { default: { provider: 'claude-code', model: null, fallback: ['codex'] }, tasks: {}, models: { 'claude-code': 'claude-opus-5-5', kimi: 'kimi-k2-turbo-preview' } };
const providers: ProviderId[] = ['claude-code', 'codex', 'kimi', 'deepseek'];

describe('project AI', () => {
  it('cleans untrusted choices', () => {
    expect(cleanAi({ provider: 'kimi', model: 'kimi-k2-0905-preview' })).toEqual({ provider: 'kimi', model: 'kimi-k2-0905-preview' });
    expect(cleanAi({ provider: 'kimi', model: 'bad model id!' })).toEqual({ provider: 'kimi' });
    expect(cleanAi({ provider: 'nope' })).toBeNull();
    expect(cleanAi(null)).toBeNull();
    expect(cleanAi('kimi')).toBeNull();
  });

  it('runs on its own model, else the provider’s model from Settings, else the default', () => {
    expect(effectiveAi({ provider: 'kimi', model: 'kimi-k2-0905-preview' }, routes)).toEqual({ provider: 'kimi', model: 'kimi-k2-0905-preview', own: true });
    expect(effectiveAi({ provider: 'kimi' }, routes)).toEqual({ provider: 'kimi', model: 'kimi-k2-turbo-preview', own: true });
    expect(effectiveAi(null, routes)).toEqual({ provider: 'claude-code', model: 'claude-opus-5-5', own: false });
    expect(effectiveAi(null, null)).toBeNull();
  });

  it('labels the chip and the list rows', () => {
    expect(aiLabel(null, routes, cat, words)).toBe('Claude Code · Opus 5.5');
    expect(aiLabel({ provider: 'kimi', model: 'kimi-k2-0905-preview' }, routes, cat, words)).toBe('Kimi · Kimi K2');
    expect(aiLabel({ provider: 'codex' }, routes, cat, words)).toBe('Codex · CLI default');
    expect(aiLabel({ provider: 'deepseek' }, routes, cat, words)).toBe('DeepSeek · Provider default');
    expect(aiShort(null, cat)).toBeNull();
    expect(aiShort({ provider: 'kimi' }, cat)).toBe('Kimi');
    expect(aiShort({ provider: 'kimi', model: 'kimi-k2-0905-preview' }, cat)).toBe('Kimi · Kimi K2');
    expect(sameAi(null, undefined)).toBe(true);
    expect(sameAi({ provider: 'kimi' }, { provider: 'kimi', model: null })).toBe(true);
    expect(sameAi({ provider: 'kimi' }, { provider: 'kimi', model: 'x' })).toBe(false);
  });

  it('/model words in a project’s chat -> the project’s new AI', () => {
    const cur = { provider: 'claude-code', model: 'claude-opus-5-5' };
    expect(aiFromWords('sonnet', cur, providers, cat)).toEqual({ provider: 'claude-code', model: 'claude-sonnet-5-5' });
    expect(aiFromWords('default', cur, providers, cat)).toEqual({ provider: 'claude-code' });
    expect(aiFromWords('kimi', cur, providers, cat)).toEqual({ provider: 'kimi' });
    expect(aiFromWords('Claude Code', { provider: 'kimi', model: null }, providers, cat)).toEqual({ provider: 'claude-code' });
    expect(aiFromWords('kimi k2', cur, providers, cat)).toEqual({ provider: 'kimi', model: 'kimi-k2-0905-preview' });
    expect(aiFromWords('gpt-6-luna', cur, providers, cat)).toEqual({ provider: 'codex', model: 'gpt-6-luna' });
    expect(aiFromWords('zzz', cur, providers, cat)).toBeNull();
    expect(aiFromWords('  ', cur, providers, cat)).toBeNull();
  });

  it('the routes file passes each provider’s model (the engine’s project AI uses it)', () => {
    expect(routesFile(routes).models).toEqual({ 'claude-code': 'claude-opus-5-5', kimi: 'kimi-k2-turbo-preview' });
    expect(routesFile({ default: { provider: 'codex', fallback: [] }, tasks: {} }).models).toBeUndefined();
  });
});
