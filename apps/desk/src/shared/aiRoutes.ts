// AI accounts & models: the providers the desk knows, which provider each AI task uses (default + per-task overrides
// + an ordered fallback list), how those choices become the engine's routes file (VSTUDIO_LLM_ROUTES_FILE, read on
// every engine call), and the "Claude's login expired, Codex answered" notice. Pure: shared by main, renderer, tests.
import { CAPS, type EditionCaps } from './edition';

export const PROVIDER_IDS = [
  'claude-code',
  'codex',
  // coding agents over the Agent Client Protocol (vstudio.acp): international first, the ones made in China after
  'gemini-cli',
  'cursor-agent',
  'copilot',
  'opencode',
  'claude-acp',
  'codex-acp',
  'qwen-code',
  'kimi-cli',
  'codebuddy',
  'iflow',
  'anthropic',
  'openai',
  'openrouter',
  'deepseek',
  'qwen',
  'kimi',
  'glm',
  'doubao',
  'ollama',
  'lmstudio',
  'vllm',
] as const;
export type ProviderId = (typeof PROVIDER_IDS)[number];
export type ProviderKind = 'subscription-cli' | 'api' | 'local';

/** Works from mainland China without a VPN: yes · partly (some models / regions) · no. */
export type ChinaUse = 'yes' | 'partly' | 'no';

export interface ProviderInfo {
  kind: ProviderKind;
  name: string;
  secret?: KeyName;
  /** a coding agent driven over ACP (the user's own installed program and sign-in) */
  acp?: true;
  maker?: string;
  china?: ChinaUse;
}

export const PROVIDERS: Record<ProviderId, ProviderInfo> = {
  'claude-code': { kind: 'subscription-cli', name: 'Claude Code', maker: 'Anthropic', china: 'no' },
  codex: { kind: 'subscription-cli', name: 'Codex', maker: 'OpenAI', china: 'no' },
  'gemini-cli': { kind: 'subscription-cli', name: 'Gemini CLI', acp: true, maker: 'Google', china: 'no' },
  'cursor-agent': { kind: 'subscription-cli', name: 'Cursor CLI', acp: true, maker: 'Cursor', china: 'partly' },
  copilot: { kind: 'subscription-cli', name: 'GitHub Copilot CLI', acp: true, maker: 'GitHub', china: 'partly' },
  opencode: { kind: 'subscription-cli', name: 'OpenCode', acp: true, maker: 'SST', china: 'yes' },
  'claude-acp': { kind: 'subscription-cli', name: 'Claude Code (ACP)', acp: true, maker: 'Anthropic', china: 'no' },
  'codex-acp': { kind: 'subscription-cli', name: 'Codex (ACP)', acp: true, maker: 'OpenAI', china: 'no' },
  'qwen-code': { kind: 'subscription-cli', name: 'Qwen Code', acp: true, maker: 'Alibaba', china: 'yes' },
  'kimi-cli': { kind: 'subscription-cli', name: 'Kimi CLI', acp: true, maker: 'Moonshot AI', china: 'yes' },
  codebuddy: { kind: 'subscription-cli', name: 'CodeBuddy', acp: true, maker: 'Tencent', china: 'yes' },
  iflow: { kind: 'subscription-cli', name: 'iFlow CLI', acp: true, maker: 'Alibaba iFlow', china: 'yes' },
  anthropic: { kind: 'api', name: 'Anthropic API', secret: 'anthropic', china: 'no' },
  openai: { kind: 'api', name: 'OpenAI API', secret: 'openai', china: 'no' },
  openrouter: { kind: 'api', name: 'OpenRouter', secret: 'openrouter', china: 'partly' },
  deepseek: { kind: 'api', name: 'DeepSeek', secret: 'deepseek', china: 'yes' },
  qwen: { kind: 'api', name: 'Qwen', secret: 'qwen', china: 'yes' },
  kimi: { kind: 'api', name: 'Kimi', secret: 'kimi', china: 'yes' },
  glm: { kind: 'api', name: 'GLM', secret: 'glm', china: 'yes' },
  doubao: { kind: 'api', name: 'Doubao', secret: 'ark', china: 'yes' },
  ollama: { kind: 'local', name: 'Ollama' },
  lmstudio: { kind: 'local', name: 'LM Studio' },
  vllm: { kind: 'local', name: 'vLLM' },
};

/** The providers she signs in to with a CLI of her own (Claude Code, Codex, the ACP agents): the only ones the login
 * terminal runs. */
export const CLI_PROVIDER_IDS = PROVIDER_IDS.filter((p) => PROVIDERS[p].kind === 'subscription-cli') as [ProviderId, ...ProviderId[]];

/** A coding agent driven over ACP (Gemini CLI, Qwen Code, Kimi CLI, CodeBuddy, ...). */
export function isAcp(p: string | null | undefined): boolean {
  return Boolean(p && PROVIDERS[p as ProviderId]?.acp);
}

/** Worth offering in a picker: anything but an ACP agent not known to be installed here (ten of them, most absent;
 * before the status is checked none is offered); the current choice always. */
export function offerable(p: ProviderId, row: { state?: string } | null | undefined, current?: string | null): boolean {
  return p === current || !isAcp(p) || (!!row && row.state !== 'not-installed');
}

/** API providers with a mainland China and an international endpoint (vstudio.llm PRESETS regions). */
export const REGION_PROVIDERS = ['qwen', 'kimi', 'glm', 'doubao'] as const;
export type Region = 'cn' | 'intl';
export function hasRegions(p: string): boolean {
  return (REGION_PROVIDERS as readonly string[]).includes(p);
}

/** The providers this build can use: the Lite (Mac App Store) build has no subscription CLIs (it is sandboxed and
 * cannot run the claude / codex she installed): API keys and local model servers only. */
export function availableProviders(caps: EditionCaps = CAPS): ProviderId[] {
  return PROVIDER_IDS.filter((p) => caps.cliLogins || PROVIDERS[p].kind !== 'subscription-cli');
}

export function providerAllowed(p: string, caps: EditionCaps = CAPS): boolean {
  return p === 'none' || (isProvider(p) && (caps.cliLogins || PROVIDERS[p].kind !== 'subscription-cli'));
}

/** What a fresh profile uses when nothing is configured: her subscription CLIs (Claude Code, Codex as fallback); in
 * the Lite build the Anthropic API, then OpenAI, then a local Ollama (whichever she sets up answers). */
export function defaultChoice(caps: EditionCaps = CAPS): RouteChoice {
  return caps.cliLogins ? { provider: 'claude-code', model: null, fallback: ['codex'] } : { provider: 'anthropic', model: null, fallback: ['openai', 'ollama'] };
}

/** API keys kept in the OS keychain (Electron safeStorage) and handed to the engine as these variables only. */
export const KEY_NAMES = ['anthropic', 'openai', 'deepseek', 'qwen', 'kimi', 'glm', 'openrouter', 'minimax', 'gemini', 'ark', 'kling', 'hedra'] as const;
export type KeyName = (typeof KEY_NAMES)[number];
export const KEY_ENV: Record<KeyName, string> = {
  anthropic: 'ANTHROPIC_API_KEY',
  openai: 'OPENAI_API_KEY',
  deepseek: 'DEEPSEEK_API_KEY',
  qwen: 'DASHSCOPE_API_KEY',
  kimi: 'MOONSHOT_API_KEY',
  glm: 'ZHIPUAI_API_KEY',
  openrouter: 'OPENROUTER_API_KEY',
  // Create page (video generation services): MiniMax Hailuo API, Google Veo (Gemini API), Seedance via Volcengine Ark,
  // and the Kling MCP access token the creator got from Kling's own sign-in (never read from another app)
  minimax: 'MINIMAX_API_KEY',
  gemini: 'GEMINI_API_KEY',
  ark: 'ARK_API_KEY',
  kling: 'KLING_MCP_TOKEN',
  // the AI presenter (talking head from her own photo + the narration): her Hedra plan's API key
  hedra: 'HEDRA_API_KEY',
};

/** The desk's AI tasks -> the engine's routing task names. */
export const AI_TASKS = {
  plan: 'intake',
  segments: 'segment_plan',
  proofread: 'proofread',
  glossary: 'glossary',
  copy: 'copy',
  edit: 'output_edit',
} as const;
export type AiTask = keyof typeof AI_TASKS;
export const AI_TASK_IDS = Object.keys(AI_TASKS) as AiTask[];

export interface RouteChoice {
  provider: ProviderId | 'none';
  model?: string | null;
  fallback: ProviderId[];
}
/** Saved in the desk settings. A task without an entry follows the default. */
export interface AiRoutes {
  default: RouteChoice;
  tasks: Partial<Record<AiTask, RouteChoice>>;
  /** the model each provider runs on for every job (a job's own `model` wins); absent = the CLI's / provider's default */
  models?: Partial<Record<ProviderId, string>>;
  /** mainland China or international endpoint of a provider that has both (absent = cn) */
  regions?: Partial<Record<ProviderId, Region>>;
}

const MODEL_ID = /^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,119}$/;
function cleanModels(m: unknown): Partial<Record<ProviderId, string>> {
  const out: Partial<Record<ProviderId, string>> = {};
  if (!m || typeof m !== 'object') return out;
  for (const [k, v] of Object.entries(m as Record<string, unknown>)) if (isProvider(k) && typeof v === 'string' && MODEL_ID.test(v)) out[k] = v;
  return out;
}

function cleanRegions(m: unknown): Partial<Record<ProviderId, Region>> {
  const out: Partial<Record<ProviderId, Region>> = {};
  if (!m || typeof m !== 'object') return out;
  for (const [k, v] of Object.entries(m as Record<string, unknown>)) if (isProvider(k) && hasRegions(k) && (v === 'cn' || v === 'intl')) out[k] = v;
  return out;
}

export function isProvider(x: unknown): x is ProviderId {
  return typeof x === 'string' && (PROVIDER_IDS as readonly string[]).includes(x);
}

function cleanChoice(c: Partial<RouteChoice> | undefined | null, caps: EditionCaps = CAPS): RouteChoice | null {
  if (!c || !(isProvider(c.provider) || c.provider === 'none') || !providerAllowed(c.provider, caps)) return null;
  const fb = (c.fallback ?? []).filter((x, i, a) => isProvider(x) && providerAllowed(x, caps) && x !== c.provider && a.indexOf(x) === i).slice(0, 4);
  return { provider: c.provider, model: c.model && MODEL_ID.test(String(c.model)) ? String(c.model) : null, fallback: fb };
}

/** The engine's `python -m vstudio.llm route --json` (persona / client values) -> the initial desk choices. */
/** A task route the engine resolved from a task-specific setting (persona / config `llm.tasks.<task>`, the desk file's
 * tasks, `VSTUDIO_LLM_<TASK>_PROVIDER`) rather than inherited from the default. Without a `source` (older engine)
 * every entry counts as its own. */
function ownTaskRoute(r: { source?: string }): boolean {
  const s = r.source;
  if (!s) return true;
  return /llm\.tasks\./.test(s) || (/^env VSTUDIO_LLM_.+_PROVIDER$/.test(s) && s !== 'env VSTUDIO_LLM_PROVIDER');
}

export function routesFromEngine(
  engine: Record<string, { provider?: string; model?: string | null; fallback?: unknown; source?: string }> | null | undefined,
  caps: EditionCaps = CAPS,
): AiRoutes {
  const pick = (r?: { provider?: string; model?: string | null; fallback?: unknown }): RouteChoice | null =>
    r
      ? cleanChoice({
          provider: (r.provider === 'none' ? 'none' : r.provider) as ProviderId,
          model: r.model ?? null,
          fallback: (Array.isArray(r.fallback) ? r.fallback : []).map((x) => (typeof x === 'object' && x ? (x as { provider?: string }).provider : x)) as ProviderId[],
        }, caps)
      : null;
  // nothing configured (no persona / client route: the engine reports "none") -> the subscription CLIs, which the
  // routes file then hands to the engine, so what the page shows is what runs (P1-6)
  // a fallback the persona gives its own model ({provider: codex, model: ...}): that provider's model
  const models: Partial<Record<ProviderId, string>> = {};
  for (const r of Object.values(engine ?? {}))
    for (const f of Array.isArray(r?.fallback) ? r.fallback : [])
      if (f && typeof f === 'object' && isProvider((f as { provider?: string }).provider) && typeof (f as { model?: unknown }).model === 'string')
        models[(f as { provider: ProviderId }).provider] ??= (f as { model: string }).model;
  const engineDef = pick(engine?.default);
  const def = engineDef && engineDef.provider !== 'none' ? engineDef : defaultChoice(caps);
  const tasks: AiRoutes['tasks'] = {};
  for (const k of AI_TASK_IDS) {
    const raw = engine?.[AI_TASKS[k]];
    // a task that only inherits the engine's default is not a choice of its own: with nothing configured the engine
    // reports "none" for every task, which used to pin six jobs to rules while the page said Claude Code
    if (!raw || !ownTaskRoute(raw)) continue;
    const c = pick(raw);
    if (c && !sameChoice(c, def)) tasks[k] = c;
  }
  const out: AiRoutes = { default: def, tasks };
  const clean = cleanModels(models);
  if (Object.keys(clean).length) out.models = clean;
  return out;
}

export function sameChoice(a: RouteChoice, b: RouteChoice): boolean {
  return a.provider === b.provider && (a.model ?? null) === (b.model ?? null) && a.fallback.join() === b.fallback.join();
}

/** The choice a task uses (its own entry, else the default). */
export function effective(routes: AiRoutes, task: AiTask): RouteChoice {
  return routes.tasks[task] ?? routes.default;
}

/** Validated copy of untrusted routes (IPC). Throws on a bad default. */
export function normalizeRoutes(r: unknown): AiRoutes {
  const o = (r ?? {}) as Partial<AiRoutes>;
  const def = cleanChoice(o.default);
  if (!def) throw new Error('routes: default provider required');
  const tasks: AiRoutes['tasks'] = {};
  for (const k of AI_TASK_IDS) {
    const c = cleanChoice(o.tasks?.[k]);
    if (c) tasks[k] = c;
  }
  const models = cleanModels(o.models);
  const regions = cleanRegions(o.regions);
  return { default: def, tasks, ...(Object.keys(models).length ? { models } : {}), ...(Object.keys(regions).length ? { regions } : {}) };
}

type EngineEntry = { provider: string; model?: string; fallback?: (string | { provider: string; model: string })[] };
/** The engine's routes file. Every task gets an explicit entry - "follow the default" is written out - because the
 * engine ranks the persona's llm.tasks above any default: an omitted task would silently use the persona's route.
 * Each entry carries its model (the job's own, else the provider's) and each fallback its provider's model, so a
 * fallback Codex runs on the model picked for Codex (never on whatever its config.toml says). */
export function routesFile(r: AiRoutes): { default: EngineEntry; tasks: Record<string, EngineEntry>; regions?: Partial<Record<ProviderId, Region>> } {
  const pm = r.models ?? {};
  const entry = (c: RouteChoice): EngineEntry => {
    const model = c.model || (c.provider !== 'none' ? pm[c.provider] : undefined);
    const fb = c.fallback.map((p) => (pm[p] ? { provider: p, model: pm[p]! } : p));
    return { provider: c.provider, ...(model ? { model } : {}), ...(fb.length ? { fallback: fb } : {}) };
  };
  const tasks: Record<string, EngineEntry> = {};
  for (const k of AI_TASK_IDS) tasks[AI_TASKS[k]] = entry(effective(r, k));
  // tasks the desk has no control for (scripts, the batch planner) follow the default too
  for (const extra of ['script', 'planner']) tasks[extra] = entry(r.default);
  // the endpoint of each provider that has two (the engine reads `regions` on every call)
  const regions = cleanRegions(r.regions);
  return { default: entry(r.default), tasks, ...(Object.keys(regions).length ? { regions } : {}) };
}

/** Engine fallback record (vstudio.llm complete -> output ai / intake planner). */
export interface FallbackInfo {
  from: string;
  to: string;
  code: string;
  error?: string;
  /** how long the first provider was given (s) when it timed out */
  limit?: number | null;
  /** skipped at once: it timed out on an earlier request a few minutes ago */
  cached?: boolean;
  seconds?: number | null;
}

export type FallbackKey = 'aiacc.fb.region' | 'aiacc.fb.expired' | 'aiacc.fb.notLoggedIn' | 'aiacc.fb.notInstalled' | 'aiacc.fb.failed' | 'aiacc.fb.timeout' | 'aiacc.fb.skipped' | 'aiacc.fb.limited' | 'aiacc.fb.model';

/** The notice for a run that did not use the chosen provider, or null. key + vars for t(). */
export function fallbackNotice(fb: FallbackInfo | null | undefined): { key: FallbackKey; from: string; to: string; provider: string; login: boolean; seconds?: number } | null {
  if (!fb || !fb.from || !fb.to || fb.from === fb.to) return null;
  // say WHY it fell back: "did not answer" alone hid a 90 s limit on a big request and a skip after an earlier timeout
  const limit = fb.limit ?? (fb.code === 'timeout' ? Number(/timed out after\s*([0-9.]+)\s*s/.exec(fb.error ?? '')?.[1]) || null : null);
  const key: FallbackKey =
    fb.code === 'auth-expired'
      ? 'aiacc.fb.expired'
      : fb.code === 'not-logged-in'
        ? 'aiacc.fb.notLoggedIn'
        : fb.code === 'not-installed'
          ? 'aiacc.fb.notInstalled'
          : fb.code === 'rate-limited'
            ? 'aiacc.fb.limited'
            : fb.code === 'model-unsupported'
              ? 'aiacc.fb.model'
            : fb.code === 'region-blocked'
              ? 'aiacc.fb.region'
            : fb.code === 'timeout' && fb.cached
              ? 'aiacc.fb.skipped'
              : fb.code === 'timeout' && limit
                ? 'aiacc.fb.timeout'
                : 'aiacc.fb.failed';
  const login = PROVIDERS[fb.from as ProviderId]?.kind === 'subscription-cli' && (fb.code === 'auth-expired' || fb.code === 'not-logged-in');
  return { key, from: providerName(fb.from), to: providerName(fb.to), provider: fb.from, login, ...(key === 'aiacc.fb.timeout' && limit ? { seconds: Math.round(limit) } : {}) };
}

export function providerName(p: string | null | undefined): string {
  if (!p) return '';
  if (p === 'rules' || p === 'none') return p;
  return PROVIDERS[p as ProviderId]?.name ?? p;
}

// ---------------------------------------------------------------- status rows (python -m vstudio.llm auth status)
export type AuthState =
  | 'installed'
  | 'logged-in'
  | 'expired'
  | 'not-logged-in'
  | 'not-installed'
  | 'configured'
  | 'not-configured'
  | 'ready'
  | 'server-down'
  | 'no-models'
  | 'unavailable'
  | 'error';

export interface EngineMsgLite {
  code: string;
  params?: Record<string, unknown>;
  message?: string;
  message_zh?: string;
}

export interface AuthRow {
  provider: string;
  kind: ProviderKind | 'unknown';
  state: AuthState;
  ready: boolean;
  installed?: boolean | null;
  version?: string | null;
  verified?: boolean;
  account?: { email?: string | null; plan?: string | null; auth_method?: string | null; org?: string | null } | null;
  key_env?: string | null;
  base_url?: string | null;
  models?: string[] | null;
  can_login?: boolean;
  can_logout?: boolean;
  install?: { url: string; command: string } | null;
  message?: EngineMsgLite | null;
  detail?: string | null;
  /** ACP agents (vstudio.llm_auth): it is one, who makes it, whether it works in mainland China, which account */
  acp?: boolean;
  maker?: string;
  china?: ChinaUse;
  account_hint?: string;
  /** a provider with two endpoints: the one in use, and both */
  region?: Region;
  regions?: Region[];
  /** why a check failed, as a code: region-blocked | timeout | not-acp */
  code?: string;
}

export interface AuthStatusMsg {
  providers: AuthRow[];
  at: number;
  /** a code, never engine text: engine (the bundled engine is broken) | timeout | failed */
  error?: 'engine' | 'timeout' | 'failed' | string;
  /** the claude-code login round-trip took too long: rows are from the quick check */
  probeTimedOut?: boolean;
}

/** Pill tone + message key for a status row. */
export function pill(row: AuthRow | undefined): { tone: 'ok' | 'warn' | 'bad' | 'off'; key: string } {
  switch (row?.state) {
    case 'logged-in':
      return { tone: 'ok', key: 'aiacc.st.loggedIn' };
    case 'installed':
      return { tone: 'ok', key: 'agents.st.installed' };
    case 'expired':
      return { tone: 'bad', key: 'aiacc.st.expired' };
    case 'not-logged-in':
      return { tone: 'warn', key: 'aiacc.st.notLoggedIn' };
    case 'not-installed':
      return { tone: 'off', key: 'aiacc.st.notInstalled' };
    case 'configured':
      return { tone: row.ready ? 'ok' : 'warn', key: row.ready ? 'aiacc.st.configured' : 'aiacc.st.needsPackage' };
    case 'not-configured':
      return { tone: 'off', key: 'aiacc.st.notConfigured' };
    case 'ready':
      return { tone: 'ok', key: 'aiacc.st.localUp' };
    case 'server-down':
      return { tone: 'off', key: 'aiacc.st.localDown' };
    case 'no-models':
      return { tone: 'warn', key: 'aiacc.st.noModels' };
    case 'unavailable':
      return { tone: 'off', key: 'aiacc.st.unavailable' };
    case undefined:
      return { tone: 'off', key: 'aiacc.st.checking' };
    default:
      return row?.code === 'region-blocked' ? { tone: 'bad', key: 'agents.st.region' } : row?.code === 'not-acp' ? { tone: 'warn', key: 'agents.st.notAcp' } : { tone: 'bad', key: 'aiacc.st.error' };
  }
}

/** Variables a login terminal runs without ("X_*" = every X_ variable), so the CLI uses the user's own login. */
export function stripEnv(env: Record<string, string | undefined>, unset: string[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(env)) {
    if (v === undefined) continue;
    if (unset.some((u) => k === u || (u.endsWith('*') && k.startsWith(u.slice(0, -1))))) continue;
    out[k] = v;
  }
  return out;
}
