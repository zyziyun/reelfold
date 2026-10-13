// The AI of one request / project / goal (per-task AI): a chip "Claude Code · Opus 5.5" that opens the models of the
// AI in use, then the other AIs that work here now (ready-only), then "Use my default" and "Set up more…". The
// composer's chip picks it for one request; the run page, the project page, the clip chat and a goal's group switch
// it for that project (from its next AI step). AiTag: the small label in the lists.
import { useEffect, type MouseEvent } from 'react';
import { ChevronDown, Cpu } from 'lucide-react';
import { availableProviders, offerable, pill, PROVIDERS, providerName, usable, type AiTask, type ProviderId } from '../../../shared/aiRoutes';
import { aiLabel, aiShort, effectiveAi, sameAi, type ProjectAi } from '../../../shared/projectAi';
import { t, tk } from '../i18n';
import { aiState, catalogOf, loadModels, refreshStatus, rowOf, useAi } from '../lib/ai';
import { go } from '../lib/router';
import { modelItems, ProviderChip } from './AiChip';
import { useUi, type MenuItem } from './ui';
import { useEngine } from '../lib/engine';
import { useHistory } from '../lib/history';
import { setProjectAi, useProjectAi } from '../lib/projectAi';
import { errText } from './msg';

/** "Claude Code · Opus 5.5" for a choice (null = the app's default). */
export function useAiLabel(value: ProjectAi | null | undefined): string {
  const { routes } = useAi();
  return aiLabel(value, routes?.routes, catalogOf, { cliDefault: t('mdl.cliDefault'), providerDefault: t('mdl.providerDefault'), rules: t('aiacc.name.rules') });
}

export function AiPickChip({
  value,
  onChange,
  testId = 'ai-pick',
  extra,
  title,
  compact = false,
  disabled = false,
}: {
  value: ProjectAi | null | undefined;
  onChange: (v: ProjectAi | null) => unknown;
  testId?: string;
  /** more menu items at the end (the chat's "Make this my default") */
  extra?: MenuItem[];
  title?: string;
  compact?: boolean;
  disabled?: boolean;
}) {
  const { routes, status } = useAi();
  const ui = useUi();
  const label = useAiLabel(value);
  const eff = effectiveAi(value, routes?.routes);
  const cur = eff?.provider ?? null;
  // what works here is known before she opens the menu (ready-only: an unchecked AI is never offered)
  useEffect(() => {
    if (!aiState().status && !aiState().checking) void refreshStatus({ probe: false }).catch(() => undefined);
    void loadModels();
  }, []);
  const pick = (v: ProjectAi | null) => {
    if (!sameAi(v, value ?? null)) void onChange(v);
  };
  const open = async (e: MouseEvent) => {
    e.stopPropagation();
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    if (!aiState().status) await refreshStatus({ probe: false }).catch(() => undefined);
    await loadModels();
    const { status, models: listed } = aiState();
    const items: MenuItem[] = [];
    if (cur && cur !== 'none') {
      for (const m of modelItems(cur, eff?.model ?? null)) items.push({ label: m.label, run: () => pick({ provider: cur as ProviderId, ...(m.id ? { model: m.id } : {}) }), testId: `${testId}-model-${m.id ?? 'default'}` });
      items.push({ label: '', run: () => {}, sep: true });
    }
    for (const p of availableProviders()) {
      const row = rowOf(status, p);
      const ok = offerable(p, row, cur) && (p === cur || (status ? usable(row, listed?.providers.find((x) => x.provider === p)?.problem) : PROVIDERS[p].kind === 'subscription-cli'));
      if (!ok) continue;
      const st = row ? tk(pill(row).key) : '';
      items.push({ label: `${p === cur ? '✓ ' : ''}${providerName(p)}${st ? ` · ${st}` : ''}`, run: () => pick(p === cur && value ? value : { provider: p }), testId: `${testId}-pick-${p}` });
    }
    items.push({ label: '', run: () => {}, sep: true });
    if (value) {
      const def = aiLabel(null, routes?.routes, catalogOf, { cliDefault: t('mdl.cliDefault'), providerDefault: t('mdl.providerDefault'), rules: t('aiacc.name.rules') });
      items.push({ label: t('tai.useDefault', { name: def }), run: () => pick(null), testId: `${testId}-default` });
    }
    items.push(...(extra ?? []));
    items.push({ label: t('aiacc.setupMore'), run: () => go({ name: 'aiAccounts' }), testId: `${testId}-setup` });
    ui.menu({ clientX: r.left, clientY: r.bottom + 4 }, items);
  };
  const row = rowOf(status, cur);
  const tone = row ? pill(row).tone : 'off';
  return (
    <button
      type="button"
      className={`chip pchip ux-aichip ${value ? 'own' : ''}`}
      style={{ height: 24, padding: '0 8px' }}
      onClick={(e) => void open(e)}
      disabled={disabled}
      data-tip={title ?? t('tai.chipTip')}
      aria-label={`${title ?? t('tai.chipTip')}: ${label}`}
      data-testid={testId}
      data-provider={eff?.provider ?? ''}
      data-model={eff?.model ?? ''}
      data-own={value ? '1' : '0'}
    >
      <Cpu className="ico" style={{ width: 12, height: 12 }} />
      <span className="clamp1" style={{ maxWidth: compact ? 140 : 220 }}>
        {label || t('aiacc.st.checking')}
      </span>
      {(tone === 'bad' || tone === 'warn') && <i className="dot" style={{ background: 'var(--danger)' }} />}
      <ChevronDown className="ico" style={{ width: 12, height: 12 }} />
    </button>
  );
}

/** The small label a list row shows when a project runs on an AI of its own (nothing for the default). */
export function AiTag({ ai, testId = 'ai-tag' }: { ai: ProjectAi | null | undefined; testId?: string }) {
  useAi();
  const s = aiShort(ai, catalogOf);
  if (!s) return null;
  return (
    <span className="ux-aitag faint small" data-testid={testId} data-provider={ai?.provider} title={t('tai.tagTip', { name: s })}>
      <Cpu className="ico" style={{ width: 11, height: 11 }} />
      {s}
    </span>
  );
}

/** A project's AI: shows what it runs on, switches it from its next AI step (a running step is never interrupted). */
/** ``orTask``: a folder that is not a recipe project (an imported / adopted work) has no AI of its own - the chip of
 * that app-wide job instead. */
export function ProjectAiChip({ item, seed, testId = 'project-ai', extra, compact, orTask }: { item: string; seed?: ProjectAi | null; testId?: string; extra?: MenuItem[]; compact?: boolean; orTask?: AiTask }) {
  const { client } = useEngine();
  const ui = useUi();
  const { reload } = useHistory();
  const { ai, supported } = useProjectAi(client, item, seed);
  if (!supported) return orTask ? <ProviderChip task={orTask} testId={testId} /> : null;
  const change = async (v: ProjectAi | null) => {
    if (!client) return;
    try {
      ui.toast(await setProjectAi(client, item, v, 'you'));
      reload();
    } catch (e) {
      ui.toast(errText(e), { error: true });
    }
  };
  return <AiPickChip value={ai ?? null} onChange={change} testId={testId} extra={extra} compact={compact} title={t('tai.projectTip')} />;
}
