// A project's own AI in the renderer: read it (GET /api/ai/<item>), switch it (the run page, the project page, the
// clip chat's chip and /model), and tell every view of that project at once (a tiny event: the chip in the chat and
// the one on the run page agree without a reload).
import { useEffect, useState } from 'react';
import { availableProviders, offerable, providerName, type ProviderId } from '../../../shared/aiRoutes';
import { aiFromWords, aiLabel, effectiveAi, type ProjectAi } from '../../../shared/projectAi';
import type { EngineClient } from '../../../shared/engineClient';
import { t } from '../i18n';
import { aiState, catalogOf, loadModels, rowOf, routesNow } from './ai';

type Listener = (item: string, ai: ProjectAi | null) => void;
const listeners = new Set<Listener>();
const known = new Map<string, ProjectAi | null>();

function announce(item: string, ai: ProjectAi | null) {
  known.set(item, ai);
  listeners.forEach((f) => f(item, ai));
}

/** The project's AI (null = the app's default; undefined = not loaded yet) and whether it can have one. */
export function useProjectAi(client: EngineClient | null, item: string | null | undefined, seed?: ProjectAi | null) {
  const [state, setState] = useState<{ ai: ProjectAi | null | undefined; supported: boolean }>(() => ({ ai: item && known.has(item) ? known.get(item) : seed, supported: true }));
  useEffect(() => {
    if (!client || !item) return;
    let alive = true;
    client
      .projectAi(item)
      .then((r) => {
        if (!alive) return;
        known.set(item, r.ai ?? null);
        setState({ ai: r.ai ?? null, supported: r.supported });
      })
      .catch(() => alive && setState((s) => ({ ...s, supported: false })));
    const f: Listener = (it, ai) => it === item && setState((s) => ({ ...s, ai }));
    listeners.add(f);
    return () => {
      alive = false;
      listeners.delete(f);
    };
  }, [client, item]);
  return state;
}

/** "Claude Code · Opus 5.5" for a choice (null = the app's default). */
export function labelOf(ai: ProjectAi | null | undefined): string {
  return aiLabel(ai, aiState().routes?.routes, catalogOf, { cliDefault: t('mdl.cliDefault'), providerDefault: t('mdl.providerDefault'), rules: t('aiacc.name.rules') });
}

/** Switch a project's AI (from its next AI step) -> the line to show / say. */
export async function setProjectAi(client: EngineClient, item: string, ai: ProjectAi | null, by: 'you' | 'chat' | 'group' = 'you'): Promise<string> {
  await client.setProjectAi(item, ai, by);
  announce(item, ai);
  return ai ? t('tai.switched', { name: labelOf(ai) }) : t('tai.switchedDefault', { name: labelOf(null) });
}

export interface ChatSwitch {
  ok: boolean;
  text: string;
  provider?: string;
  model?: string | null;
}

/** `/model <words>` in a project's chat: the PROJECT switches (never her default), and the line says so. */
export async function switchProjectByWords(client: EngineClient, item: string, words: string, current: ProjectAi | null | undefined): Promise<ChatSwitch> {
  const routes = (await routesNow())?.routes;
  if (!routes) return { ok: false, text: t('mdl.noRoutes') };
  await loadModels();
  const eff = effectiveAi(current ?? null, routes);
  const status = aiState().status;
  const providers = availableProviders().filter((p) => p === eff?.provider || offerable(p, rowOf(status, p)));
  const next = aiFromWords(words, { provider: eff?.provider ?? 'none', model: eff?.model ?? null }, providers as ProviderId[], catalogOf);
  if (!next) {
    const cur = eff?.provider ?? '';
    const list = catalogOf(cur)
      .filter((m) => !m.older)
      .slice(0, 6)
      .map((m) => m.label)
      .join(', ');
    return { ok: false, text: list ? t('mdl.noMatch', { q: words, list }) : t('mdl.noMatchNone', { q: words, provider: providerName(cur) }) };
  }
  await client.setProjectAi(item, next, 'chat');
  announce(item, next);
  return { ok: true, text: t('tai.chatSwitched', { name: labelOf(next), def: labelOf(null) }), provider: next.provider, model: next.model ?? null };
}
