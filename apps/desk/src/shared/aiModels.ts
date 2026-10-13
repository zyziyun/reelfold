// Model choice per AI provider (pure: main, renderer, tests): the models a provider can use (the engine's
// `python -m vstudio.llm models --json`; the Claude list below until it answers), her words -> one model ("5.5" ->
// Opus 5.5, "sonnet" -> the newest Sonnet; the same rules as vstudio.llm_models.resolve), and the routes change a
// pick makes (the provider's model for every job, or a job's own choice).
import { effective, PROVIDERS, providerName, type AiRoutes, type AiTask, type ProviderId, type RouteChoice } from './aiRoutes';

export interface ModelInfo {
  id: string;
  label: string;
  family?: string;
  version?: string;
  aliases?: string[];
  older?: boolean;
  note?: string;
}

export interface ModelProblem {
  code: string;
  params?: Record<string, unknown>;
  message?: string;
  message_zh?: string;
}

/** One provider's row of `vstudio.llm models --json`. */
export interface ProviderModels {
  provider: string;
  /** cli: the CLI's own catalog for this login (Codex) | list: a maintained list | api: the provider's /models | server: a local server */
  source: 'cli' | 'list' | 'api' | 'server' | string;
  models: ModelInfo[];
  /** the model the CLI's own config picks when no model is passed (Codex config.toml) */
  cli_default?: string | null;
  /** e.g. codex-model-unsupported: her Codex config names a model her login cannot use */
  problem?: ModelProblem | null;
}

export interface ModelsMsg {
  providers: ProviderModels[];
  at: number;
  error?: string;
}

/** The current Claude models (mirror of vstudio.llm_models.CLAUDE_MODELS: the list the pickers show before the engine
 * answers; a unit test keeps the two in step). */
export const CLAUDE_MODELS: ModelInfo[] = [
  { id: 'claude-opus-5-5', label: 'Opus 5.5', family: 'opus', version: '5.5', aliases: ['opus'] },
  { id: 'claude-sonnet-5-5', label: 'Sonnet 5.5', family: 'sonnet', version: '5.5', aliases: ['sonnet'] },
  { id: 'claude-haiku-5-5', label: 'Haiku 5.5', family: 'haiku', version: '5.5', aliases: ['haiku'] },
  { id: 'claude-fable-5-1', label: 'Fable 5.1', family: 'fable', version: '5.1', aliases: ['fable'] },
  { id: 'claude-opus-5', label: 'Opus 5', family: 'opus', version: '5', older: true },
  { id: 'claude-haiku-4-5', label: 'Haiku 4.5', family: 'haiku', version: '4.5', older: true },
];
const FAMILY_RANK = ['opus', 'sonnet', 'haiku', 'fable'];

/** What a provider offers before the engine has answered. */
export function baseModels(p: string): ModelInfo[] {
  return p === 'claude-code' || p === 'anthropic' ? CLAUDE_MODELS : [];
}

export function modelsOf(msg: ModelsMsg | null | undefined, p: string): ModelInfo[] {
  const row = msg?.providers.find((x) => x.provider === p);
  return row?.models.length ? row.models : baseModels(p);
}

// ---------------------------------------------------------------- her words -> a model
function tokens(s: string | null | undefined): string[] {
  return (String(s ?? '').toLowerCase().match(/[a-z]+|\d+(?:[.\-_]\d+)*/g) ?? []).map((t) => (/^\d/.test(t) ? t.replace(/[-_]/g, '.') : t));
}
/** case, spaces and punctuation out ("Opus 5.5" == "opus-5-5"); other scripts kept ("默认") */
const norm = (s: string | null | undefined) => String(s ?? '').toLowerCase().replace(/[\s\-_.:/()'"]/g, '');
const DEFAULT_WORDS = new Set(['default', 'clidefault', 'auto', 'reset', '默认', 'défaut', 'defaut', 'par défaut'].map(norm).filter(Boolean));

function versionKey(v: string | undefined): number[] {
  const parts = String(v ?? '').split('.').map((x) => Number(x));
  return parts.every((x) => Number.isFinite(x)) && v ? parts : [];
}
function versionOf(id: string): string {
  const m = /(\d+(?:[.-]\d+)*)/.exec(id);
  return m ? m[1].replace(/-/g, '.') : '';
}
function cmp(a: (number | number[])[], b: (number | number[])[]): number {
  for (let i = 0; i < a.length; i++) {
    const x = a[i];
    const y = b[i];
    if (Array.isArray(x) && Array.isArray(y)) {
      for (let k = 0; k < Math.max(x.length, y.length); k++) {
        const d = (x[k] ?? -1) - (y[k] ?? -1);
        if (d) return d;
      }
    } else if (x !== y) return (x as number) - (y as number);
  }
  return 0;
}

/** Her words -> the best model, `'default'` (the CLI's / provider's own default), or null (nothing matches).
 * Exact id / alias / label first ("sonnet" = the newest Sonnet); then every word must be in the model's id / label /
 * family (prefixes count), a version must be equal ("5.5" never matches 5.1); ties: opus, sonnet, haiku, fable, then
 * the newest version, then the list order. */
export function resolveModel(query: string, catalog: ModelInfo[]): ModelInfo | 'default' | null {
  const q = query.trim();
  if (!q) return null;
  if (DEFAULT_WORDS.has(norm(q))) return 'default';
  const qn = norm(q);
  const qt = tokens(q);
  let best: ModelInfo | null = null;
  let bestKey: (number | number[])[] | null = null;
  catalog.forEach((m, i) => {
    const names = [m.id, m.label, ...(m.aliases ?? [])];
    let score: number;
    if (names.some((x) => norm(x) === qn)) score = 100;
    else {
      const mt = new Set([...tokens(names.join(' ')), ...tokens(m.family)]);
      if (m.version) mt.add(m.version);
      const words = [...mt].filter((x) => !/^\d/.test(x));
      const ok = qt.length > 0 && qt.every((t) => (/^\d/.test(t) ? mt.has(t) : words.some((x) => x.startsWith(t))));
      if (!ok) return;
      score = 50;
    }
    const fam = FAMILY_RANK.indexOf(m.family ?? '');
    const key = [score, -(fam >= 0 ? fam : FAMILY_RANK.length), m.older ? 0 : 1, versionKey(m.version || versionOf(m.id)), -i];
    if (!bestKey || cmp(key, bestKey) > 0) {
      best = m;
      bestKey = key;
    }
  });
  return best;
}

/** "Opus 5.5" for a known id, the id itself otherwise; null -> null (the caller says "CLI default"). */
export function modelLabel(id: string | null | undefined, catalog: ModelInfo[] = CLAUDE_MODELS): string | null {
  if (!id) return null;
  return catalog.find((m) => m.id === id || (m.aliases ?? []).includes(id))?.label ?? id;
}

// ---------------------------------------------------------------- routes
/** The model a job runs on: its own choice, else the provider's model, else null (the CLI's / provider's default). */
export function effectiveModel(routes: AiRoutes, task: AiTask | 'default'): string | null {
  const c = task === 'default' ? routes.default : effective(routes, task);
  return c.model || routes.models?.[c.provider as ProviderId] || null;
}

/** The provider + model a job runs on, for the chip / the thread: "Claude Code · Opus 5.5". */
export function routeLabel(routes: AiRoutes, task: AiTask | 'default', catalog: (p: string) => ModelInfo[], defaultWord: string): { provider: string; model: string | null; text: string } {
  const c = task === 'default' ? routes.default : effective(routes, task);
  const m = effectiveModel(routes, task);
  const name = providerName(c.provider);
  return { provider: c.provider, model: m, text: `${name} · ${m ? modelLabel(m, catalog(c.provider)) : defaultWord}` };
}

/** The routes after she picks `model` (null = the default) for `provider`: it becomes that provider's model for every
 * job; the job she picked it from (`task`, or the default) switches to that provider; a job's own model for that
 * provider is replaced there. */
export function withModel(routes: AiRoutes, task: AiTask | 'default', provider: ProviderId, model: string | null): AiRoutes {
  const models = { ...(routes.models ?? {}) };
  if (model) models[provider] = model;
  else delete models[provider];
  const next: AiRoutes = { ...routes, default: { ...routes.default }, tasks: { ...routes.tasks }, models };
  const pick = (c: RouteChoice): RouteChoice => ({ ...c, provider, model: null, fallback: c.fallback.filter((x) => x !== provider) });
  if (task !== 'default' && next.tasks[task]) next.tasks[task] = pick(next.tasks[task]!);
  else next.default = pick(next.default);
  return next;
}

/** A provider's model for every job that uses it (Settings › AI, a provider's own row): no job switches provider. */
export function withProviderModel(routes: AiRoutes, provider: ProviderId, model: string | null): AiRoutes {
  const models = { ...(routes.models ?? {}) };
  if (model) models[provider] = model;
  else delete models[provider];
  const def = routes.default.provider === provider ? { ...routes.default, model: null } : routes.default;
  return { ...routes, default: def, tasks: { ...routes.tasks }, models };
}

/** Is `p` a provider whose models can be picked here (not "none")? */
export function pickable(p: string): p is ProviderId {
  return p in PROVIDERS;
}
