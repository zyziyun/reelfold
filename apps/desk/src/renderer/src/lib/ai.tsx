// Shared AI accounts state for the renderer: the routes (which provider each task uses) and the last provider
// status, kept in one small store so the settings page, the 让 AI 改 chip and the composer chip agree.
import { useEffect, useSyncExternalStore } from 'react';
import { effective, type AiRoutes, type AiTask, type AuthRow, type AuthStatusMsg, type ProviderId, type Region, type RouteChoice } from '../../../shared/aiRoutes';
import type { AiRoutesMsg } from '../../../shared/deskApi';
import { modelsOf, withModel, withProviderModel, type ModelInfo, type ModelsMsg } from '../../../shared/aiModels';

interface State {
  routes: AiRoutesMsg | null;
  status: AuthStatusMsg | null;
  checking: boolean;
  /** the models each provider can use (vstudio.llm models) */
  models: ModelsMsg | null;
}

let state: State = { routes: null, status: null, checking: false, models: null };
const subs = new Set<() => void>();
function set(patch: Partial<State>) {
  state = { ...state, ...patch };
  subs.forEach((f) => f());
}
const subscribe = (f: () => void) => {
  subs.add(f);
  return () => subs.delete(f);
};

let routesLoading: Promise<void> | null = null;
let listening = false;
function ensureRoutes() {
  if (!listening && window.desk?.on) {
    listening = true;
    window.desk.on('ai:routes', (m) => set({ routes: m as AiRoutesMsg }));
  }
  if (state.routes || routesLoading || !window.desk?.ai) return;
  routesLoading = window.desk.ai
    .routes()
    .then((r) => set({ routes: r }))
    .catch(() => undefined)
    .finally(() => {
      routesLoading = null;
    });
}

/** Ask main for the status (cached there unless refresh). probe=false: no claude round-trip. */
export async function refreshStatus(opts: { refresh?: boolean; probe?: boolean; providers?: string[] } = {}) {
  if (!window.desk?.ai) return;
  set({ checking: true });
  try {
    set({ status: await window.desk.ai.status(opts) });
  } finally {
    set({ checking: false });
  }
}

export async function saveRoutes(r: AiRoutes | null) {
  set({ routes: await window.desk.ai.setRoutes(r) });
}

/** Switch one task (or the default) to a provider; null = follow the default again. Explicit, persisted. */
export async function switchProvider(task: AiTask | 'default', provider: ProviderId | 'none' | null) {
  const cur = state.routes?.routes;
  if (!cur) return;
  const next: AiRoutes = { ...cur, default: { ...cur.default }, tasks: { ...cur.tasks } };
  if (task === 'default') {
    if (!provider) return;
    next.default = { ...next.default, provider, model: provider === cur.default.provider ? cur.default.model : null, fallback: cur.default.fallback.filter((x) => x !== provider) };
  } else if (!provider) {
    delete next.tasks[task];
  } else {
    const base: RouteChoice = effective(cur, task);
    next.tasks[task] = { provider, model: provider === base.provider ? base.model : null, fallback: base.fallback.filter((x) => x !== provider) };
  }
  await saveRoutes(next);
}

let modelsLoading: Promise<ModelsMsg | null> | null = null;
/** The models each provider can use (main caches them; refresh after a sign-in). */
export function loadModels(opts: { refresh?: boolean } = {}): Promise<ModelsMsg | null> {
  if (!window.desk?.ai?.models) return Promise.resolve(null);
  if (state.models && !opts.refresh) return Promise.resolve(state.models);
  modelsLoading ??= window.desk.ai
    .models(opts)
    .then((m) => (set({ models: m }), m))
    .catch(() => null)
    .finally(() => {
      modelsLoading = null;
    });
  return modelsLoading;
}

/** The models a provider offers (the Claude list until the engine has answered). */
export function catalogOf(p: string): ModelInfo[] {
  return modelsOf(state.models, p);
}

/** She picked a model (the chip, /model, Settings' current AI): that provider's model for every job, and the job
 * (or the default) runs on that provider. null = the CLI's / provider's own default. Saved; the engine reads it on
 * its next call. */
export async function pickModel(task: AiTask | 'default', provider: ProviderId, model: string | null) {
  const cur = state.routes?.routes;
  if (!cur) return;
  await saveRoutes(withModel(cur, task, provider, model));
}

/** A provider's model for every job that uses it (Settings › AI rows: Codex as the fallback). */
export async function setProviderModel(provider: ProviderId, model: string | null) {
  const cur = state.routes?.routes;
  if (!cur) return;
  await saveRoutes(withProviderModel(cur, provider, model));
}

/** The endpoint (mainland China / international) of a provider that has both: every job that uses it. */
export async function setRegion(provider: ProviderId, region: Region) {
  const cur = state.routes?.routes;
  if (!cur) return;
  const regions = { ...(cur.regions ?? {}) };
  if (region === 'cn') delete regions[provider];
  else regions[provider] = region;
  const next: AiRoutes = { ...cur };
  if (Object.keys(regions).length) next.regions = regions;
  else delete next.regions;
  await saveRoutes(next);
}

export function useAi() {
  const s = useSyncExternalStore(subscribe, () => state);
  useEffect(() => {
    ensureRoutes();
  }, []);
  return s;
}

export function rowOf(status: AuthStatusMsg | null, p: string | null | undefined): AuthRow | undefined {
  return status?.providers.find((r) => r.provider === p);
}

/** The store as it is now (outside React: the /model command). */
export function aiState(): Readonly<State> {
  return state;
}

/** The routes, loaded if nobody has asked yet. */
export async function routesNow(): Promise<AiRoutesMsg | null> {
  if (state.routes) return state.routes;
  ensureRoutes();
  await routesLoading;
  return state.routes;
}

/** test hook */
export function _resetAiStore() {
  state = { routes: null, status: null, checking: false, models: null };
}
