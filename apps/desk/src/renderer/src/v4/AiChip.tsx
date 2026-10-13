// Provider chip with a dropdown (quick switcher) for one AI task, the "answered by" tag, and the fallback notice
// ("Claude Code login expired, so Codex was used this time · Log in"). Switching is explicit and saved.
import type { MouseEvent } from 'react';
import { ChevronDown, Cpu } from 'lucide-react';
import { availableProviders, effective, offerable, fallbackNotice, pill, PROVIDERS, providerName, usable, type AiTask, type FallbackInfo, type ProviderId } from '../../../shared/aiRoutes';
import { t, tk } from '../i18n';
import { catalogOf, loadModels, pickModel, refreshStatus, rowOf, switchProvider, useAi } from '../lib/ai';
import { effectiveModel, modelLabel, type ModelInfo } from '../../../shared/aiModels';
import { go } from '../lib/router';
import { useUi, type MenuItem } from './ui';

export function ProviderChip({ task, testId }: { task: AiTask; testId?: string }) {
  const { routes, status, models: listed } = useAi();
  const ui = useUi();
  if (!routes) return null;
  const cur = effective(routes.routes, task);
  const own = Boolean(routes.routes.tasks[task]);
  const model = effectiveModel(routes.routes, task);
  const mname = cur.provider === 'none' ? null : model ? modelLabel(model, catalogOf(cur.provider)) : defaultWord(cur.provider);
  const open = (e: MouseEvent) => {
    e.stopPropagation(); // the menu closes on the next window click
    if (!status) void refreshStatus({ probe: false });
    void loadModels();
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    // the models of the provider in use first (the same choice as /model), then the providers
    const models: MenuItem[] =
      cur.provider === 'none'
        ? []
        : [
            ...modelItems(cur.provider, model).map((m) => ({ label: m.label, run: () => void pickModel(task, cur.provider as ProviderId, m.id), testId: `chip-model-${m.id ?? 'default'}` })),
            { label: '', run: () => {}, sep: true },
          ];
    const items: MenuItem[] = availableProviders().filter((p) => {
      const row = rowOf(status, p);
      // offer what works here now (ready, nothing in the way) and the current choice; the rest is set up in
      // Settings › AI (the last item)
      return offerable(p, row, cur.provider) && (p === cur.provider || (status ? usable(row, listed?.providers.find((x) => x.provider === p)?.problem) : PROVIDERS[p].kind === 'subscription-cli'));
    }).map((p) => {
      const row = rowOf(status, p);
      const st = row ? tk(pill(row).key) : '';
      return {
        label: `${p === cur.provider ? '✓ ' : ''}${providerName(p)}${st ? ` · ${st}` : ''}`,
        run: () => void switchProvider(task, p as ProviderId),
        testId: `chip-pick-${p}`,
      };
    });
    items.push({ label: '', run: () => {}, sep: true });
    if (own) items.push({ label: t('aiacc.followDefault'), run: () => void switchProvider(task, null), testId: 'chip-follow-default' });
    items.push({ label: t('aiacc.manage'), run: () => go({ name: 'aiAccounts' }), testId: 'chip-manage' });
    ui.menu({ clientX: r.left, clientY: r.bottom + 4 }, [...models, ...items]);
  };
  const row = rowOf(status, cur.provider);
  const tone = row ? pill(row).tone : 'off';
  return (
    <button className="chip pchip" style={{ height: 24, padding: '0 8px' }} onClick={open} data-tip={t('aiacc.chipTip')} aria-label={t('aiacc.chipTip')} data-testid={testId ?? 'provider-chip'} data-provider={cur.provider} data-model={model ?? ''}>
      <Cpu className="ico" style={{ width: 12, height: 12 }} />
      <span className="clamp1" style={{ maxWidth: 220 }}>{t('aiacc.chip', { name: cur.provider === 'none' ? t('aiacc.name.rules') : `${providerName(cur.provider)} · ${mname}` })}</span>
      {(tone === 'bad' || tone === 'warn') && <i className="dot" style={{ background: 'var(--danger)' }} />}
      <ChevronDown className="ico" style={{ width: 12, height: 12 }} />
    </button>
  );
}

/** Who answered, plus the notice when it was not the chosen provider. */
export function AnsweredBy({ provider, fallback, kind = 'answered', testId }: { provider?: string | null; fallback?: FallbackInfo | null; kind?: 'answered' | 'planned'; testId?: string }) {
  if (!provider) return null;
  const name = provider === 'rules' || provider === 'none' ? t('aiacc.name.rules') : providerName(provider);
  return (
    <div className="col" style={{ gap: 4 }} data-testid={testId ?? 'answered-by'}>
      <span className="faint small" data-provider={provider}>
        {kind === 'planned' ? t('aiacc.plannedBy', { name }) : t('aiacc.answeredBy', { name })}
      </span>
      <FallbackNote fallback={fallback} />
    </div>
  );
}

export function FallbackNote({ fallback, rulesFrom }: { fallback?: FallbackInfo | null; rulesFrom?: string | null }) {
  const n = fallbackNotice(fallback);
  if (!n && !rulesFrom) return null;
  const target = n?.provider ?? rulesFrom!;
  const login = n ? n.login : PROVIDERS[target as ProviderId]?.kind === 'subscription-cli';
  return (
    <div className="notice small row" style={{ gap: 6, flexWrap: 'wrap' }} data-testid="fallback-note">
      <span>{n ? t(n.key, { from: n.from, to: n.to, seconds: n.seconds ?? '' }) : t('aiacc.fb.rules', { from: providerName(rulesFrom) })}</span>
      <span className="faint">·</span>
      <a href={`#/settings/ai/${encodeURIComponent(target)}`} data-testid="fallback-login">
        {login ? t('aiacc.fb.login') : t('aiacc.fb.settings')}
      </a>
    </div>
  );
}

/** "CLI default" for the subscription CLIs, "Provider default" for the rest. */
export function defaultWord(p: string): string {
  return t(PROVIDERS[p as ProviderId]?.kind === 'subscription-cli' ? 'mdl.cliDefault' : 'mdl.providerDefault');
}

/** The pickable models of a provider (newest first, older ones last) + its default, each with ✓ on the current one. */
export function modelItems(p: string, current: string | null): { id: string | null; label: string; info?: ModelInfo }[] {
  const list = catalogOf(p);
  const sorted = [...list.filter((m) => !m.older), ...list.filter((m) => m.older)];
  const mark = (on: boolean) => (on ? '✓ ' : '');
  return [
    ...sorted.map((m) => ({ id: m.id, label: `${mark(m.id === current)}${m.label}${m.older ? ` (${t('mdl.older')})` : ''}`, info: m })),
    { id: null, label: `${mark(!current)}${defaultWord(p)}` },
  ];
}

/** The /model card's picker: the provider's models as chips (her pick goes through the same /model command, so the
 * thread says what changed). */
export function ModelPicker({ provider, current, onPick }: { provider: string; current: string | null; onPick: (id: string | null) => void }) {
  useAi(); // re-render when the models arrive
  return (
    <div className="row" style={{ gap: 6, flexWrap: 'wrap' }} data-testid="model-picker">
      {modelItems(provider, current).map((m) => (
        <button key={m.id ?? 'default'} className={`chip ${m.id === current ? 'on' : ''}`} onClick={() => onPick(m.id)} title={m.info?.note ?? m.id ?? ''} data-testid={`model-pick-${m.id ?? 'default'}`}>
          {m.label.replace(/^✓ /, '')}
        </button>
      ))}
    </div>
  );
}
