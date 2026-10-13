// Settings › AI (ux/settings-redesign A2): the AI in use (status, Switch AI…, ⋯), the fallback order in one
// sentence, "different AI for specific jobs" as a second page, other accounts (subscriptions, API keys, models on
// this Mac). Sign-in runs in the sign-in sheet (the terminal is folded under "Show details").
import { useEffect, useState, type ReactNode } from 'react';
import { Bot, ChevronLeft, ChevronRight, Copy, Cpu, KeyRound, MoreHorizontal, Sparkles, TerminalSquare } from 'lucide-react';
import { availableProviders, effective, hasRegions, offerable, pill, PROVIDERS, providerName, type AuthRow, type ProviderId, type Region } from '../../../shared/aiRoutes';
import { LiteAiNote } from '../components/Lite';
import type { AiTestMsg, SecretsStatusMsg } from '../../../shared/deskApi';
import { AI_TASK_IDS } from '../../../shared/aiRoutes';
import { fmtAgo, getLang, has, t, tk } from '../i18n';
import { catalogOf, loadModels, pickModel, refreshStatus, rowOf, saveRoutes, setProviderModel, setRegion, switchProvider, useAi } from '../lib/ai';
import { modelItems } from '../v4/AiChip';
import { missingRow, RouteRow, RoutesEditor } from '../v4/AIAccounts';
import { LoginTerminal, type LoginReq } from '../v4/LoginTerminal';
import { useUi, type MenuItem } from '../v4/ui';
import { Dot, Group, Page, RestartBar, Sheet } from './kit';
import { markRestart, useRestart } from './restart';
import type { SettingsCtx } from './registry';
import { takePendingSignIn } from './status';

const clean = (e: unknown) => (e as Error).message.replace(/^Error invoking remote method '[^']+': (Error: )?/, '');
// what this build can use (the Lite / Mac App Store build has no subscription CLIs)
const PROVIDER_IDS = availableProviders();
const CLI = PROVIDER_IDS.filter((p) => PROVIDERS[p].kind === 'subscription-cli' && !PROVIDERS[p].acp);
// coding agents over ACP (Gemini CLI, Qwen Code, Kimi CLI, CodeBuddy, ...): international first, then made in China
const AGENTS = PROVIDER_IDS.filter((p) => PROVIDERS[p].acp);
const API = PROVIDER_IDS.filter((p) => PROVIDERS[p].kind === 'api');
const LOCAL = PROVIDER_IDS.filter((p) => PROVIDERS[p].kind === 'local');

function Icon({ p, big }: { p: string; big?: boolean }) {
  const kind = PROVIDERS[p as ProviderId]?.kind;
  return (
    <span className={`s2-pico ${p} ${big ? 'big' : ''}`}>
      {p === 'claude-code' ? <Sparkles className="ico" /> : p === 'codex' ? <TerminalSquare className="ico" /> : PROVIDERS[p as ProviderId]?.acp ? <Bot className="ico" /> : kind === 'local' ? <Cpu className="ico" /> : <KeyRound className="ico" />}
    </span>
  );
}

function StatePill({ row, working }: { row: AuthRow | undefined; working?: boolean }) {
  const p = pill(row);
  const tone = p.tone === 'ok' ? 'ok' : p.tone === 'bad' ? 'error' : p.tone === 'warn' ? 'warn' : 'off';
  const plan = row?.state === 'logged-in' && row.account?.plan ? row.account.plan.charAt(0).toUpperCase() + row.account.plan.slice(1) : null;
  return (
    <span className={`s2-pill ${tone}`} data-testid="provider-pill" data-state={row?.state ?? 'checking'}>
      <Dot tone={tone} />
      {working && row?.ready ? t('s2.ai.working') : plan ? t('aiacc.st.loggedInPlan', { plan }) : tk(p.key)}
    </span>
  );
}

export function AiSection({ sub }: SettingsCtx) {
  const ui = useUi();
  const { status, checking, routes, models } = useAi();
  const [login, setLogin] = useState<LoginReq | null>(null);
  const [keys, setKeys] = useState<SecretsStatusMsg | null>(null);
  const [sheet, setSheet] = useState<'order' | 'keys' | 'local' | null>(null);
  const [tests, setTests] = useState<Record<string, AiTestMsg | 'running'>>({});
  const restart = useRestart();
  const focus = sub && sub !== 'jobs' ? sub : undefined;
  useEffect(() => {
    void refreshStatus({ refresh: true });
    void loadModels({ refresh: true });
    void window.desk.secrets.status().then(setKeys);
    const p = takePendingSignIn();
    if (p) setLogin({ provider: p, action: 'login' });
  }, []);
  useEffect(() => {
    if (!focus) return;
    const kind = PROVIDERS[focus as ProviderId]?.kind;
    if (kind === 'api') setSheet('keys');
    else if (kind === 'local') setSheet('local');
  }, [focus]);

  const row = (p: ProviderId) => rowOf(status, p) ?? (status ? (status.error ? { ...missingRow(p), state: 'error' } : missingRow(p)) : undefined);
  const def = (routes?.routes.default.provider ?? null) as ProviderId | 'none' | null;
  const cur = def && def !== 'none' ? def : null;
  const runTest = async (p: ProviderId) => {
    setTests((x) => ({ ...x, [p]: 'running' }));
    const r = await window.desk.ai.test(p);
    setTests((x) => ({ ...x, [p]: r }));
    ui.toast(r.ok ? t('aiacc.testOk', { model: r.model ?? '-', s: r.seconds ?? '-' }) : t('aiacc.testFail', { error: (r.error ?? '').slice(0, 200) }), { error: !r.ok });
  };
  const menuFor = (p: ProviderId): MenuItem[] => {
    const r = row(p);
    const cli = PROVIDERS[p].kind === 'subscription-cli';
    const cp = p;
    const items: MenuItem[] = [];
    if (cli && r?.can_login !== false && r?.state !== 'not-installed') items.push({ label: t(r?.state === 'logged-in' || r?.state === 'expired' ? 's2.ai.signInAgain' : 's2.ai.signIn'), run: () => setLogin({ provider: cp, action: 'login' }), testId: `menu-login-${p}` });
    if (cli && p === 'claude-code') {
      items.push({ label: `${t('s2.ai.otherWays')}: ${t('aiacc.variant.console')}`, run: () => setLogin({ provider: cp, action: 'login', variant: 'console' }) });
      items.push({ label: `${t('s2.ai.otherWays')}: ${t('aiacc.variant.sso')}`, run: () => setLogin({ provider: cp, action: 'login', variant: 'sso' }) });
    }
    if (cli && p === 'codex') items.push({ label: `${t('s2.ai.otherWays')}: ${t('aiacc.variant.device')}`, run: () => setLogin({ provider: cp, action: 'login', variant: 'device' }) });
    if (r?.state !== 'not-installed') items.push({ label: t('s2.ai.test'), run: () => void runTest(p), testId: `test-${p}` });
    if (def !== p && r?.ready) items.push({ label: t('s2.ai.useForAll'), run: () => void switchProvider('default', p) });
    if (r?.install) items.push({ label: t('s2.ai.install'), run: () => void window.desk.openExternal(r.install!.url) });
    if (cli && r?.can_logout && (r.state === 'logged-in' || r.state === 'expired'))
      items.push({ label: '', sep: true, run: () => undefined }, { label: t('s2.ai.signOut'), run: () => window.confirm(t('aiacc.logoutConfirm', { name: providerName(p) })) && setLogin({ provider: cp, action: 'logout' }), testId: `logout-${p}` });
    return items;
  };
  /** A provider's model (every job that uses it); `primary`: the AI in use (picking also makes it the default). */
  const ModelSelect = ({ p, primary }: { p: ProviderId; primary?: boolean }) => {
    if (!routes) return null;
    const cur = routes.routes.models?.[p] ?? (primary ? routes.routes.default.model : null) ?? null;
    const items = modelItems(p, cur);
    const mrow = models?.providers.find((x) => x.provider === p);
    if (items.length <= 1 && !catalogOf(p).length) return null;
    return (
      <label className="s2-model row" style={{ gap: 8 }} title={mrow?.source === 'cli' ? t('mdl.fromCli', { provider: providerName(p) }) : undefined}>
        <span className="s2-rhint">{t('mdl.label')}</span>
        <select
          className="input"
          style={{ width: 'auto', minWidth: 170 }}
          value={cur ?? ''}
          onChange={(e) => {
            const v = e.target.value || null;
            void (primary ? pickModel('default', p, v) : setProviderModel(p, v))
              .then(() => ui.toast(t('mdl.picked', { name: `${providerName(p)} · ${items.find((m) => m.id === v)?.label.replace(/^✓ /, '') ?? v}` })))
              .catch((err) => ui.toast(clean(err), { error: true }));
          }}
          aria-label={`${providerName(p)} · ${t('mdl.label')}`}
          data-testid={`model-select-${p}`}
        >
          {cur && !items.some((m) => m.id === cur) && <option value={cur}>{cur}</option>}
          {items.map((m) => (
            <option key={m.id ?? ''} value={m.id ?? ''}>
              {m.id === null && mrow?.cli_default ? t('mdl.cliDefaultIs', { model: mrow.cli_default }) : m.label.replace(/^✓ /, '')}
            </option>
          ))}
        </select>
      </label>
    );
  };
  /** Codex's own config picks a model her login cannot use (gpt-6-astra on a ChatGPT login): say so, with the fix. Only
   * while no Codex model is picked here (a picked one is passed as --model and wins). */
  const ModelProblem = ({ p }: { p: ProviderId }) => {
    const mrow = models?.providers.find((x) => x.provider === p);
    if (!mrow?.problem || routes?.routes.models?.[p]) return null;
    const pr = mrow.problem;
    const suggest = typeof pr.params?.suggest === 'string' ? pr.params.suggest : null;
    return (
      <div className="s2-note warn row" style={{ gap: 10, flexWrap: 'wrap' }} data-testid={`model-problem-${p}`} data-code={pr.code}>
        <span style={{ flex: 1 }}>{getLang() === 'zh-CN' ? (pr.message_zh ?? pr.message) : pr.message}</span>
        {suggest && (
          <button className="btn" onClick={() => void setProviderModel(p, suggest).catch((err) => ui.toast(clean(err), { error: true }))} data-testid={`model-fix-${p}`}>
            {t('mdl.useSuggested', { model: catalogOf(p).find((m) => m.id === suggest)?.label ?? suggest })}
          </button>
        )}
      </div>
    );
  };
  const More = ({ p }: { p: ProviderId }) => (
    <button className="btn ghost icon" aria-label={t('s2.ai.more')} data-tip={t('s2.ai.more')} onClick={(e) => (e.stopPropagation(), ui.menu(e, menuFor(p)))} data-testid={`more-${p}`}>
      <MoreHorizontal className="ico" />
    </button>
  );
  const SignIn = ({ p, primary }: { p: ProviderId; primary?: boolean }) => {
    const r = row(p);
    if (PROVIDERS[p].kind !== 'subscription-cli' || r?.ready || r?.can_login === false || r?.state === 'not-installed' || !r) return null;
    return (
      <button className={`btn ${primary ? 'primary' : ''}`} onClick={() => setLogin({ provider: p, action: 'login' })} data-testid={`login-${p}`}>
        {r.state === 'expired' ? t('s2.ai.signInAgain') : t('s2.ai.signIn')}
      </button>
    );
  };

  if (sub === 'jobs')
    return (
      <Page title={t('s2.ai.jobsTitle')} testId="ai-accounts">
        <a className="s2-back" href="#/settings/ai" data-testid="ai-jobs-back">
          <ChevronLeft className="ico" />
          {t('s2.nav.ai')}
        </a>
        {routes && <RoutesEditor routes={routes.routes} own={Boolean(routes.saved)} />}
      </Page>
    );

  const fb = routes?.routes.default.fallback ?? [];
  const chain = [...fb.map((p) => providerName(p)), t('s2.ai.rules')];
  const overridden = routes ? AI_TASK_IDS.filter((k) => routes.routes.tasks[k] && effective(routes.routes, k).provider !== routes.routes.default.provider).length : 0;
  const nKeys = keys ? Object.values(keys.keys).filter(Boolean).length : 0;
  const localUp = LOCAL.map((p) => rowOf(status, p)).find((r) => r?.ready);
  const curRow = cur ? row(cur) : undefined;
  return (
    <Page title={t('s2.nav.ai')} lead={t('s2.ai.lead')} testId="ai-accounts">
      {status?.error && (
        <div className="s2-note warn" data-testid="ai-status-error">
          {has(`aiacc.err.${status.error}`) ? tk(`aiacc.err.${status.error}`) : t('aiacc.err.failed')}
        </div>
      )}
      {status?.probeTimedOut && !status.error && (
        <div className="s2-note" data-testid="ai-probe-slow">
          {t('aiacc.probeSlow')}
        </div>
      )}
      <LiteAiNote />
      {restart.what === 'key' && <RestartBar text={t('s2.ai.keyRestart')} onRestart={() => window.desk.restartEngine().then(() => markRestart(null))} />}
      <div className="s2-card s2-current" data-testid={cur ? `provider-${cur}` : 'provider-none'} data-provider-card={cur ?? 'none'}>
        <div className="s2-curtop">
          {cur ? <Icon p={cur} big /> : <span className="s2-pico big" />}
          <div className="s2-rtext">
            <div className="row" style={{ gap: 10 }}>
              <b className="s2-curname">{cur ? providerName(cur) : t('aiacc.none')}</b>
              {cur && <StatePill row={curRow} working />}
            </div>
            <span className="s2-rhint" data-testid="provider-account">
              {cur ? tk(PROVIDERS[cur].kind === 'subscription-cli' ? `aiacc.desc.${cur}` : PROVIDERS[cur].kind === 'api' ? 'aiacc.desc.api' : 'aiacc.desc.local') : t('s2.st.aiNoneBody')}
              {curRow?.account?.email ? ` · ${curRow.account.email}` : ''}
              {status?.at ? ` · ${t('s2.ai.checked', { when: fmtAgo(status.at) })}` : ''}
            </span>
          </div>
          {cur && <SignIn p={cur} primary />}
          <button
            className="btn"
            onClick={(e) =>
              ui.menu(
                e,
                [...PROVIDER_IDS]
                  .sort((a, b) => Number(!!rowOf(status, b)?.ready) - Number(!!rowOf(status, a)?.ready))
                  .filter((p) => p !== cur && offerable(p, rowOf(status, p)))
                  .map((p) => ({ label: `${providerName(p)}${rowOf(status, p)?.ready ? '' : ` (${t('aiacc.notReady')})`}`, run: () => void switchProvider('default', p), testId: `switch-${p}` })),
              )
            }
            data-testid="ai-switch"
          >
            {t('s2.ai.switch')}
          </button>
          {cur && <More p={cur} />}
        </div>
        {cur && (
          <div className="s2-curmodel" data-testid="ai-current-model">
            <ModelSelect p={cur} primary />
            <span className="s2-rhint">{t('mdl.hint', { provider: providerName(cur) })}</span>
          </div>
        )}
        {cur && <ModelProblem p={cur} />}
        <div className="s2-curfoot">
          <span data-testid="ai-fallback-sentence">
            {fb.length ? (
              <>
                {t('s2.ai.fb', { chain: '\u0000' }).split('\u0000')[0]}
                {chain.map((c, i) => (
                  <span key={c}>
                    {i > 0 && ' → '}
                    <b>{c}</b>
                  </span>
                ))}
                {t('s2.ai.fb', { chain: '\u0000' }).split('\u0000')[1]}
              </>
            ) : (
              t('s2.ai.fbNone')
            )}
          </span>
          <button className="s2-link" onClick={() => setSheet('order')} data-testid="ai-order">
            {t('s2.ai.order')}
          </button>
        </div>
      </div>
      <a className="s2-card s2-linkrow" href="#/settings/ai/jobs" data-testid="ai-perjob">
        <span className="s2-rtext">
          <span className="s2-rlabel">{t('s2.ai.perJob')}</span>
          <span className="s2-rhint">{t('s2.ai.perJobHint')}</span>
        </span>
        <span className="s2-val">{overridden ? t('s2.ai.perJobMixed', { n: overridden }) : cur ? t('s2.ai.perJobAll', { name: providerName(cur) }) : ''}</span>
        <ChevronRight className="ico" />
      </a>
      <Group
        title={t('s2.ai.others')}
        action={
          <button className="s2-link" onClick={() => void refreshStatus({ refresh: true })} disabled={checking} data-testid="ai-refresh">
            {checking ? t('s2.ai.checking') : t('s2.ai.check')}
          </button>
        }
      >
        {CLI.filter((p) => p !== cur).map((p) => {
          const r = row(p);
          return (
            <div key={p} className={`s2-row ${focus === p ? 'focus' : ''}`} data-testid={`provider-${p}`} data-provider-card={p}>
              <Icon p={p} />
              <div className="s2-rtext">
                <div className="s2-rlabel">{providerName(p)}</div>
                <div className="s2-rhint">{tk(`aiacc.desc.${p}`)}</div>
              </div>
              <div className="s2-rctl">
                <ModelSelect p={p} />
                <StatePill row={r} />
                <SignIn p={p} />
                <More p={p} />
              </div>
              <ModelProblem p={p} />
            </div>
          );
        })}
        <div className="s2-row" data-testid="ai-keys">
          <span className="s2-pico plain">
            <KeyRound className="ico" />
          </span>
          <div className="s2-rtext">
            <div className="s2-rlabel">{t('s2.ai.keys')}</div>
            <div className="s2-rhint">{t('s2.ai.keysHint')}</div>
          </div>
          <div className="s2-rctl">
            <span className="s2-val">{nKeys ? t('s2.ai.keysN', { n: nKeys }) : t('s2.ai.keysNone')}</span>
            <button className="s2-link" onClick={() => setSheet('keys')} data-testid="ai-add-key">
              {t('s2.ai.addKey')}
            </button>
          </div>
        </div>
        <div className="s2-row" data-testid="ai-local">
          <span className="s2-pico plain">
            <Cpu className="ico" />
          </span>
          <div className="s2-rtext">
            <div className="s2-rlabel">{t('s2.ai.local')}</div>
            <div className="s2-rhint">{t('s2.ai.localHint')}</div>
          </div>
          <div className="s2-rctl">
            <span className="s2-val">{localUp ? t('s2.ai.localUp', { name: providerName(localUp.provider) }) : t('s2.ai.localNone')}</span>
            <button className="s2-link" onClick={() => setSheet('local')} data-testid="ai-local-setup">
              {t('s2.ai.localSetup')}
            </button>
          </div>
        </div>
      </Group>

      {AGENTS.length > 0 && (
        <AgentsGroup
          ids={AGENTS.filter((p) => p !== cur)}
          row={row}
          focus={focus}
          tests={tests}
          onTest={(p) => void runTest(p)}
          renderControls={(p) => (
            <>
              <ModelSelect p={p} />
              <SignIn p={p} />
              <More p={p} />
            </>
          )}
          renderProblem={(p) => <ModelProblem p={p} />}
        />
      )}

      {sheet === 'order' && routes && (
        <Sheet title={t('s2.ai.orderTitle', { name: cur ? providerName(cur) : t('aiacc.none') })} onClose={() => setSheet(null)} wide testId="ai-order-sheet" footer={<button className="btn primary" onClick={() => setSheet(null)}>{t('s2.done')}</button>}>
          <p className="s2-rhint">{t('s2.ai.orderBody')}</p>
          <RouteRow
            title={t('aiacc.default')}
            choice={routes.routes.default}
            label={(p) => (p === 'none' ? t('aiacc.none') : `${providerName(p)}${rowOf(status, p) && !rowOf(status, p)!.ready ? ` (${t('aiacc.notReady')})` : ''}`)}
            onChange={(c) => c && void saveRoutes({ ...routes.routes, default: c }).catch((e) => ui.toast(clean(e), { error: true }))}
            testId="route-default"
            providerModels={routes.routes.models}
          />
        </Sheet>
      )}
      {sheet === 'keys' && (
        <Sheet title={t('s2.ai.keySheet')} onClose={() => setSheet(null)} wide testId="ai-keys-sheet">
          <p className="s2-rhint">{keys?.backend === 'keychain' ? t('s2.ai.keySheetBody') : t('keys.noKeychain')}</p>
          <div className="s2-card">
            {API.map((p) => (
              <KeyRow
                key={p}
                p={p}
                row={row(p)}
                keys={keys}
                focused={focus === p}
                region={routes?.routes.regions?.[p] ?? 'cn'}
                onRegion={(r) =>
                  void setRegion(p, r)
                    .then(() => refreshStatus({ refresh: true, probe: false, providers: [p] }))
                    .then(() => ui.toast(t('agents.region.saved', { name: providerName(p), region: t(r === 'cn' ? 'agents.region.cn' : 'agents.region.intl') })))
                    .catch((err) => ui.toast(clean(err), { error: true }))
                }
                onKeys={(k) => (setKeys(k), markRestart('key'), void refreshStatus({ refresh: true, probe: false, providers: [p] }))}
              />
            ))}
          </div>
        </Sheet>
      )}
      {sheet === 'local' && (
        <Sheet title={t('s2.ai.local')} onClose={() => setSheet(null)} wide testId="ai-local-sheet">
          <p className="s2-rhint">{t('s2.ai.localBody')}</p>
          <div className="s2-card">
            {LOCAL.map((p) => {
              const r = row(p);
              const tr = tests[p];
              return (
                <div key={p} className="s2-row" data-testid={`provider-${p}`} data-provider-card={p}>
                  <Icon p={p} />
                  <div className="s2-rtext">
                    <div className="s2-rlabel">{providerName(p)}</div>
                    <div className="s2-rhint">
                      {r?.models?.length ? t('aiacc.models', { n: r.models.length, list: r.models.slice(0, 4).join(', ') }) : tk('aiacc.desc.local')}
                    </div>
                  </div>
                  <div className="s2-rctl">
                    <StatePill row={r} />
                    {r?.state !== 'server-down' && r && (
                      <button className="btn" onClick={() => void runTest(p)} disabled={tr === 'running'}>
                        {tr === 'running' ? t('aiacc.testing') : t('s2.ai.test')}
                      </button>
                    )}
                    {r?.install && (
                      <button className="s2-link" onClick={() => void window.desk.openExternal(r.install!.url)}>
                        {t('s2.ai.install')}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </Sheet>
      )}
      {login && <LoginTerminal req={login} onClose={() => setLogin(null)} />}
    </Page>
  );
}

/** Works in mainland China? A small tag beside a provider's name. */
function ChinaTag({ p }: { p: ProviderId }) {
  const c = PROVIDERS[p].china;
  if (!c) return null;
  return (
    <span className={`s2-china ${c}`} data-testid={`china-${p}`} data-china={c}>
      {t(c === 'yes' ? 'agents.china.yes' : c === 'partly' ? 'agents.china.partly' : 'agents.china.no')}
    </span>
  );
}

/** Settings › AI › Coding agents: the installed ones as rows (model, test, sign in, ⋯); the others folded, each with
 * its maker, whether it works in China, how it signs in, and its install command. */
function AgentsGroup({
  ids,
  row,
  focus,
  tests,
  onTest,
  renderControls,
  renderProblem,
}: {
  ids: ProviderId[];
  row: (p: ProviderId) => AuthRow | undefined;
  focus?: string;
  tests: Record<string, AiTestMsg | 'running'>;
  onTest: (p: ProviderId) => void;
  renderControls: (p: ProviderId) => ReactNode;
  renderProblem: (p: ProviderId) => ReactNode;
}) {
  const ui = useUi();
  const [open, setOpen] = useState(false);
  const installed = ids.filter((p) => row(p) && row(p)!.state !== 'not-installed');
  const absent = ids.filter((p) => !installed.includes(p));
  const shown = open || focus ? [...installed, ...absent] : installed;
  return (
    <Group
      title={t('agents.group')}
      testId="ai-agents"
      action={
        absent.length > 0 && (
          <button className="s2-link" onClick={() => setOpen(!open)} data-testid="agents-more">
            {open ? t('agents.less') : t('agents.more', { n: absent.length })}
          </button>
        )
      }
    >
      <div className="s2-row s2-rhint" style={{ display: 'block' }}>
        {t('agents.groupHint')}
        {installed.length === 0 && !open && <div style={{ marginTop: 6 }}>{t('agents.none')}</div>}
      </div>
      {shown.map((p) => {
        const r = row(p);
        const tr = tests[p];
        const absentRow = !r || r.state === 'not-installed';
        return (
          <div key={p} className={`s2-row ${focus === p ? 'focus' : ''}`} data-testid={`provider-${p}`} data-provider-card={p} data-state={r?.state ?? 'checking'}>
            <Icon p={p} />
            <div className="s2-rtext">
              <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                <span className="s2-rlabel">{providerName(p)}</span>
                <ChinaTag p={p} />
              </div>
              <div className="s2-rhint">
                {PROVIDERS[p].maker ? `${t('agents.by', { maker: PROVIDERS[p].maker! })} · ` : ''}
                {tk(`agents.acct.${p}`)}
              </div>
              {absentRow && r?.install && (
                <code className="s2-rhint" style={{ userSelect: 'all' }} data-testid={`install-cmd-${p}`}>
                  {r.install.command}
                </code>
              )}
              {r?.message && !absentRow && r.state !== 'logged-in' && r.state !== 'installed' && (
                <div className="s2-rhint warn" data-testid={`agent-msg-${p}`}>
                  {getLang() === 'zh-CN' ? (r.message.message_zh ?? r.message.message) : r.message.message}
                </div>
              )}
            </div>
            <div className="s2-rctl">
              <StatePill row={r} />
              {absentRow ? (
                r?.install && (
                  <>
                    <button
                      className="btn ghost icon"
                      aria-label={t('agents.copy')}
                      data-tip={t('agents.copy')}
                      onClick={() => void navigator.clipboard?.writeText(r.install!.command).then(() => ui.toast(t('agents.copied', { cmd: r.install!.command })))}
                      data-testid={`copy-install-${p}`}
                    >
                      <Copy className="ico" />
                    </button>
                    <button className="s2-link" onClick={() => void window.desk.openExternal(r.install!.url)} data-testid={`install-${p}`}>
                      {t('agents.install')}
                    </button>
                  </>
                )
              ) : (
                <>
                  <button className="btn" onClick={() => onTest(p)} disabled={tr === 'running'} data-testid={`agent-test-${p}`}>
                    {tr === 'running' ? t('aiacc.testing') : t('s2.ai.test')}
                  </button>
                  {renderControls(p)}
                </>
              )}
            </div>
            {!absentRow && renderProblem(p)}
          </div>
        );
      })}
    </Group>
  );
}

function KeyRow({
  p,
  row,
  keys,
  focused,
  region,
  onRegion,
  onKeys,
}: {
  p: ProviderId;
  row: AuthRow | undefined;
  keys: SecretsStatusMsg | null;
  focused: boolean;
  region: Region;
  onRegion: (r: Region) => void;
  onKeys: (k: SecretsStatusMsg) => void;
}) {
  const [key, setKey] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const secret = PROVIDERS[p].secret;
  const hasKey = secret ? Boolean(keys?.keys[secret]) : false;
  if (!secret) return null;
  return (
    <div className={`s2-row ${focused ? 'focus' : ''}`} data-testid={`provider-${p}`} data-provider-card={p}>
      <div className="s2-rtext">
        <div className="row" style={{ gap: 10, flexWrap: 'wrap' }}>
          <span className="s2-rlabel">{PROVIDERS[p].name}</span>
          <ChinaTag p={p} />
          <StatePill row={row} />
        </div>
        {has(`agents.key.${p}`) && <div className="s2-rhint">{tk(`agents.key.${p}`)}</div>}
        {err && <div className="s2-rhint warn">{err}</div>}
      </div>
      <div className="s2-rctl">
        {hasRegions(p) && (
          <select
            className="input"
            style={{ width: 'auto' }}
            value={region}
            onChange={(e) => onRegion(e.target.value as Region)}
            aria-label={`${PROVIDERS[p].name} · ${t('agents.region.label')}`}
            data-testid={`region-${p}`}
          >
            <option value="cn">{t('agents.region.cn')}</option>
            <option value="intl">{t('agents.region.intl')}</option>
          </select>
        )}
        {row?.install && (
          <button className="s2-link" onClick={() => void window.desk.openExternal(row.install!.url)} data-testid={`get-key-${p}`}>
            {t('agents.getKey')}
          </button>
        )}
        <input
          className="input s2-key"
          type="password"
          autoComplete="off"
          spellCheck={false}
          aria-label={PROVIDERS[p].name}
          placeholder={hasKey ? t('aiacc.keyReplace') : t('s2.ai.keyPh')}
          value={key}
          disabled={keys?.backend !== 'keychain'}
          onChange={(e) => setKey(e.target.value)}
          data-testid={`key-input-${p}`}
        />
        <button
          className="btn"
          disabled={!key.trim() || keys?.backend !== 'keychain'}
          onClick={async () => {
            setErr(null);
            try {
              onKeys(await window.desk.secrets.set(secret, key.trim()));
              setKey('');
            } catch (e) {
              setErr(clean(e));
            }
          }}
        >
          {t('s2.ai.save')}
        </button>
        {hasKey && (
          <button className="s2-link muted" onClick={async () => onKeys(await window.desk.secrets.clear(secret))}>
            {t('s2.ai.remove')}
          </button>
        )}
      </div>
    </div>
  );
}
