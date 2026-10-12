// Model choice (shared/aiModels + the routes file): her words -> a model ("5.5" -> Opus 5.5, "sonnet" -> the newest
// Sonnet), the pick saved as the provider's model (the job switches provider when it names another one), what the
// engine's routes file then says (each entry's model, each fallback's own model), the Claude list kept in step with
// the engine's, and the live pane's model line.
import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { CLAUDE_MODELS, effectiveModel, modelLabel, modelsOf, resolveModel, withModel, withProviderModel, type ModelInfo } from '../../src/shared/aiModels';
import { fallbackNotice, normalizeRoutes, routesFile, routesFromEngine, type AiRoutes } from '../../src/shared/aiRoutes';
import { lastModel } from '../../src/renderer/src/lib/live';

const id = (q: string, cat: ModelInfo[] = CLAUDE_MODELS) => {
  const r = resolveModel(q, cat);
  return r === 'default' ? 'default' : (r?.id ?? null);
};

const CODEX: ModelInfo[] = [
  { id: 'gpt-6-luna', label: 'GPT-6-Luna' },
  { id: 'gpt-5.6-terra', label: 'GPT-5.6-Terra' },
  { id: 'gpt-5.6-luna', label: 'GPT-5.6-Luna' },
];

describe('her words -> a model', () => {
  it.each([
    ['5.5', 'claude-opus-5-5'],
    ['opus 5.5', 'claude-opus-5-5'],
    ['Opus 5.5', 'claude-opus-5-5'],
    ['opus-5-5', 'claude-opus-5-5'],
    ['claude-opus-5-5', 'claude-opus-5-5'],
    ['opus', 'claude-opus-5-5'],
    ['sonnet', 'claude-sonnet-5-5'],
    ['Son', 'claude-sonnet-5-5'],
    ['haiku', 'claude-haiku-5-5'],
    ['haiku 4.5', 'claude-haiku-4-5'],
    ['fable', 'claude-fable-5-1'],
    ['5.1', 'claude-fable-5-1'],
    ['opus 5', 'claude-opus-5'],
    ['default', 'default'],
    ['默认', 'default'],
  ])('%s -> %s', (q, want) => expect(id(q)).toBe(want));
  it('nothing matches: no guess', () => {
    for (const q of ['4.7', 'gpt', 'opus 9', '']) expect(id(q)).toBeNull();
  });
  it('Codex names: the newest of a name, a version', () => {
    expect(id('luna', CODEX)).toBe('gpt-6-luna');
    expect(id('5.6 luna', CODEX)).toBe('gpt-5.6-luna');
    expect(id('6', CODEX)).toBe('gpt-6-luna');
    expect(id('terra', CODEX)).toBe('gpt-5.6-terra');
  });
  it('labels', () => {
    expect(modelLabel('claude-opus-5-5')).toBe('Opus 5.5');
    expect(modelLabel('opus')).toBe('Opus 5.5');
    expect(modelLabel('gpt-6-luna')).toBe('gpt-6-luna');
    expect(modelLabel(null)).toBeNull();
    expect(modelsOf(null, 'claude-code')).toBe(CLAUDE_MODELS);
    expect(modelsOf({ providers: [{ provider: 'codex', source: 'cli', models: CODEX }], at: 0 }, 'codex')).toBe(CODEX);
    expect(modelsOf(null, 'codex')).toEqual([]);
  });
  it('the Claude list is the engine’s (vstudio.llm_models.CLAUDE_MODELS)', () => {
    const py = fs.readFileSync(path.resolve(import.meta.dirname, '../../../../lib/vstudio/llm_models.py'), 'utf8');
    const ids = [...py.matchAll(/dict\(id="(claude-[a-z0-9-]+)", label="([^"]+)"/g)].map((m) => [m[1], m[2]]);
    expect(ids).toEqual(CLAUDE_MODELS.map((m) => [m.id, m.label]));
  });
});

const base = (): AiRoutes => ({ default: { provider: 'claude-code', model: null, fallback: ['codex'] }, tasks: {} });

describe('a pick -> the routes -> the engine’s routes file', () => {
  it('/model 5.5 in the clip chat: Claude Code’s model for every job; the file passes it', () => {
    const r = withModel(base(), 'edit', 'claude-code', 'claude-opus-5-5');
    expect(r.models).toEqual({ 'claude-code': 'claude-opus-5-5' });
    expect(r.tasks.edit).toBeUndefined(); // no job of its own: the default carries it
    expect(effectiveModel(r, 'edit')).toBe('claude-opus-5-5');
    expect(effectiveModel(r, 'copy')).toBe('claude-opus-5-5');
    const f = routesFile(r);
    expect(f.default).toEqual({ provider: 'claude-code', model: 'claude-opus-5-5', fallback: ['codex'] });
    expect(f.tasks.output_edit.model).toBe('claude-opus-5-5');
    expect(f.tasks.script.model).toBe('claude-opus-5-5');
  });
  it('a Codex model names Codex: the default switches; Codex runs on it as a fallback too', () => {
    let r = withProviderModel(base(), 'codex', 'gpt-6-luna');
    expect(r.default.provider).toBe('claude-code');
    expect(routesFile(r).default.fallback).toEqual([{ provider: 'codex', model: 'gpt-6-luna' }]);
    r = withModel(r, 'edit', 'codex', 'gpt-6-luna');
    expect(r.default.provider).toBe('codex');
    expect(r.default.fallback).toEqual([]);
    expect(routesFile(r).tasks.output_edit).toEqual({ provider: 'codex', model: 'gpt-6-luna' });
  });
  it('a job with its own choice keeps it: the pick changes that job; "default" removes the model', () => {
    let r: AiRoutes = { ...base(), tasks: { edit: { provider: 'claude-code', model: 'claude-haiku-5-5', fallback: [] } } };
    expect(effectiveModel(r, 'edit')).toBe('claude-haiku-5-5');
    r = withModel(r, 'edit', 'claude-code', 'claude-sonnet-5-5');
    expect(r.tasks.edit!.model).toBeNull();
    expect(effectiveModel(r, 'edit')).toBe('claude-sonnet-5-5');
    r = withModel(r, 'edit', 'claude-code', null);
    expect(r.models).toEqual({});
    expect(effectiveModel(r, 'edit')).toBeNull();
    expect(routesFile(r).tasks.output_edit).toEqual({ provider: 'claude-code' }); // the CLI's own default: no --model
  });
  it('a job’s own model wins over the provider’s', () => {
    const r: AiRoutes = { ...base(), models: { 'claude-code': 'claude-opus-5-5' }, tasks: { copy: { provider: 'claude-code', model: 'claude-haiku-5-5', fallback: [] } } };
    expect(routesFile(r).tasks.copy.model).toBe('claude-haiku-5-5');
    expect(routesFile(r).tasks.output_edit.model).toBe('claude-opus-5-5');
  });
  it('untrusted routes: models kept only for known providers and sane ids', () => {
    const r = normalizeRoutes({ default: { provider: 'claude-code', model: 'claude-opus-5-5', fallback: [] }, tasks: {}, models: { codex: 'gpt-6-luna', bogus: 'x', 'claude-code': 'rm -rf /' } });
    expect(r.models).toEqual({ codex: 'gpt-6-luna' });
    expect(normalizeRoutes({ default: { provider: 'codex', model: '$(boom)', fallback: [] }, tasks: {} }).default.model).toBeNull();
  });
  it('a persona fallback with its own model seeds that provider’s model', () => {
    const r = routesFromEngine({ default: { provider: 'claude-code', fallback: [{ provider: 'codex', model: 'gpt-6-luna' }], source: 'persona llm.default' } });
    expect(r.models).toEqual({ codex: 'gpt-6-luna' });
  });
  it('the fallback notice names a model the login cannot use', () => {
    expect(fallbackNotice({ from: 'codex', to: 'claude-code', code: 'model-unsupported' })!.key).toBe('aiacc.fb.model');
  });
});

describe('the live pane says the model', () => {
  it('the newest AI call’s model, from its result / session / turn line', () => {
    expect(lastModel([])).toBeNull();
    expect(
      lastModel([
        { src: 'agent', kind: 'turn', text: 'copy · claude-code (CLI default model)', provider: 'claude-code' },
        { src: 'agent', kind: 'info', text: 'session · claude-opus-4-7[1m]', provider: 'claude-code', model: 'claude-opus-4-7[1m]' },
        { src: 'engine', kind: 'event', text: 'stage-done' },
      ]),
    ).toEqual({ provider: 'claude-code', model: 'claude-opus-4-7[1m]' });
    expect(lastModel([{ src: 'agent', kind: 'result', text: 'claude-opus-5-5 · 10 in', provider: 'claude-code', model: 'claude-opus-5-5' }])!.model).toBe('claude-opus-5-5');
  });
});
