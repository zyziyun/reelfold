// The AI one request / project / goal runs on (per-task AI, her words 2026-10-13: "model 的选择和切换可以放到每次的任务
// 里"). The composer's AI chip picks it for one request; the engine stores it on the request and in each project it
// becomes (project.yaml `ai: {provider, model}`) and every AI step of that project uses it (vstudio.llm.project_ai:
// step override > project ai > task route > default; the global fallback order behind it). null = the app's default
// (Settings › AI). Pure: shared by the renderer and the tests.
import { isProvider, providerName, PROVIDERS, type AiRoutes, type ProviderId } from './aiRoutes';
import { effectiveModel, modelLabel, resolveModel, type ModelInfo } from './aiModels';

export interface ProjectAi {
  provider: ProviderId;
  model?: string | null;
}

const MODEL_ID = /^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,119}$/;

/** A clean choice from untrusted data (the engine, sessionStorage), or null. */
export function cleanAi(x: unknown): ProjectAi | null {
  if (!x || typeof x !== 'object') return null;
  const o = x as { provider?: unknown; model?: unknown };
  if (!isProvider(o.provider)) return null;
  const m = typeof o.model === 'string' && MODEL_ID.test(o.model) ? o.model : null;
  return { provider: o.provider, ...(m ? { model: m } : {}) };
}

export function sameAi(a: ProjectAi | null | undefined, b: ProjectAi | null | undefined): boolean {
  return (a?.provider ?? null) === (b?.provider ?? null) && (a?.model ?? null) === (b?.model ?? null);
}

/** What a project with this choice runs on: its own AI (its model, else the model picked for that provider in
 * Settings), else the app's default. `own` = the project has a choice of its own. */
export function effectiveAi(ai: ProjectAi | null | undefined, routes: AiRoutes | null | undefined): { provider: string; model: string | null; own: boolean } | null {
  if (ai) return { provider: ai.provider, model: ai.model || routes?.models?.[ai.provider] || null, own: true };
  if (!routes) return null;
  return { provider: routes.default.provider, model: effectiveModel(routes, 'default'), own: false };
}

/** "Claude Code · Opus 5.5" / "Kimi · Kimi K2" / "Codex · CLI default". `rules`: the word for no model. */
export function aiLabel(
  ai: ProjectAi | null | undefined,
  routes: AiRoutes | null | undefined,
  catalog: (p: string) => ModelInfo[],
  words: { cliDefault: string; providerDefault: string; rules: string },
): string {
  const e = effectiveAi(ai, routes);
  if (!e) return '';
  if (e.provider === 'none') return words.rules;
  const def = PROVIDERS[e.provider as ProviderId]?.kind === 'subscription-cli' ? words.cliDefault : words.providerDefault;
  return `${providerName(e.provider)} · ${e.model ? modelLabel(e.model, catalog(e.provider)) : def}`;
}

/** The short name for a list row: "Kimi" (the model only when it is not the provider's default). */
export function aiShort(ai: ProjectAi | null | undefined, catalog: (p: string) => ModelInfo[]): string | null {
  if (!ai) return null;
  const m = ai.model ? modelLabel(ai.model, catalog(ai.provider)) : null;
  return m ? `${providerName(ai.provider)} · ${m}` : providerName(ai.provider);
}

/** `/model <words>` in a project's chat -> the project's new AI: her current provider's models first ("5.5", "sonnet",
 * "default"), then a provider by name ("kimi", "codex"), then another provider's model ("gpt-6-luna" -> Codex).
 * null = nothing matched. */
export function aiFromWords(words: string, current: { provider: string; model: string | null }, providers: ProviderId[], catalog: (p: string) => ModelInfo[]): ProjectAi | null {
  const q = words.trim().toLowerCase();
  if (!q) return null;
  const cur = isProvider(current.provider) ? current.provider : null;
  if (cur) {
    const hit = resolveModel(q, catalog(cur));
    if (hit === 'default') return { provider: cur };
    if (hit) return { provider: cur, model: hit.id };
  }
  // a provider by its name or id: "kimi", "Claude Code", "codex"
  const norm = (s: string) => s.toLowerCase().replace(/[\s_-]+/g, '');
  const byName = providers.find((p) => norm(p) === norm(q) || norm(PROVIDERS[p].name) === norm(q));
  if (byName) return { provider: byName };
  // "kimi k2" / "codex gpt-6-luna": a provider and one of its models
  for (const p of providers) {
    const n = PROVIDERS[p].name.toLowerCase();
    for (const head of [p, n]) {
      if (q.startsWith(head + ' ')) {
        const rest = q.slice(head.length + 1);
        const hit = resolveModel(rest, catalog(p));
        if (hit === 'default') return { provider: p };
        if (hit) return { provider: p, model: hit.id };
      }
    }
  }
  for (const p of providers) {
    if (p === cur) continue;
    const hit = resolveModel(q, catalog(p));
    if (hit && hit !== 'default') return { provider: p, model: hit.id };
  }
  return null;
}
