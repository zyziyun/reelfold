// `/model` (the clip chat and Home's composer): what runs now, and her words -> a switch ("5.5" -> Opus 5.5, "sonnet"
// -> the newest Sonnet, "gpt-6-luna" -> Codex on that model, "default" -> the CLI's own). Never sent to a model.
import { availableProviders, effective, offerable, providerName, type AiTask, type ProviderId } from '../../../shared/aiRoutes';
import { effectiveModel, modelLabel, resolveModel } from '../../../shared/aiModels';
import { t } from '../i18n';
import { aiState, catalogOf, loadModels, pickModel, rowOf, routesNow } from './ai';

/** "Claude Code · Opus 5.5" (or "· CLI default") for a job. */
export function currentLine(task: AiTask | 'default'): { provider: string; model: string | null; name: string } | null {
  const r = aiState().routes?.routes;
  if (!r) return null;
  const c = task === 'default' ? r.default : effective(r, task);
  const m = effectiveModel(r, task);
  const def = c.provider === 'none' ? '' : t(c.provider === 'claude-code' || c.provider === 'codex' ? 'mdl.cliDefault' : 'mdl.providerDefault');
  const name = c.provider === 'none' ? t('aiacc.name.rules') : `${providerName(c.provider)} · ${m ? modelLabel(m, catalogOf(c.provider)) : def}`;
  return { provider: c.provider, model: m, name };
}

/** Her words against the models known now (the built-in Claude list before the engine's lists arrive); only when
 * they match nothing, wait for the full lists (each provider asked: local servers, CLIs - seconds) and try again. A
 * `/model 5.5` never waits on a slow probe of models it does not need (it used to: nothing showed for 5+ s). */
export async function soonOrListed<T>(find: () => T | null): Promise<T | null> {
  const listed = loadModels();
  const now = find();
  if (now) return now;
  await listed;
  return find();
}

export interface SwitchResult {
  ok: boolean;
  text: string;
  provider?: string;
  model?: string | null;
}

/** `/model <words>`: switch (saved at once; the next AI call uses it) -> the line for the thread. */
export async function switchByWords(words: string, task: AiTask | 'default'): Promise<SwitchResult> {
  const routes = (await routesNow())?.routes;
  if (!routes) return { ok: false, text: t('mdl.noRoutes') };
  const cur = (task === 'default' ? routes.default : effective(routes, task)).provider;
  // her current provider first, then the others this build can use (a Codex model name switches to Codex)
  const status = aiState().status;
  const order = [cur, ...availableProviders().filter((p) => p !== cur && offerable(p, rowOf(status, p)))].filter((p): p is ProviderId => p !== 'none');
  const find = () => {
    for (const p of order) {
      const hit = resolveModel(words, catalogOf(p));
      if (!hit || (hit === 'default' && p !== cur)) continue;
      return { p, id: hit === 'default' ? null : hit.id };
    }
    return null;
  };
  const got = await soonOrListed(find);
  if (got) {
    await pickModel(task, got.p, got.id);
    const line = currentLine(task);
    return { ok: true, text: t('mdl.switched', { name: line?.name ?? providerName(got.p) }), provider: got.p, model: got.id };
  }
  const list = catalogOf(cur)
    .filter((m) => !m.older)
    .slice(0, 6)
    .map((m) => m.label)
    .join(', ');
  return { ok: false, text: list ? t('mdl.noMatch', { q: words, list }) : t('mdl.noMatchNone', { q: words, provider: providerName(cur) }) };
}
