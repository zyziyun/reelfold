// Plan a new series (C01 / C02 / C03; #/create/new[/<format>]): one sentence + a format -> a planned series. This
// month's spend, and on first run (no service connected) a calm notice + the sample series. Its starts (the formats,
// write a script, record) and her series in progress are on Home (v4/HomeCreate) - Create lives under Home.
import { useMemo, useRef, useState } from 'react';
import { ChevronDown, Cloud, CircleDollarSign, Layers, Paperclip, Sparkles } from 'lucide-react';
import type { Format, FormatId, Msg, SeriesDraft, SeriesSummary } from '../../../shared/create';
import { yuan } from '../../../shared/create';
import { orderPlatforms } from '../../../shared/platforms';
import { t } from '../i18n';
import { JobError, lastStep, useAction, useCreate, useCreateLoad, waitJob } from './api';
import { PlanError, PlanProgress } from './PlanStatus';
import { BoardDrop, ImportBoardButton, ImportNote, useBoardImport } from './ImportBoard';
import { Crumbs, FormatArt, l10n, uiLang3 } from './bits';
import { createHref, goCreate } from './routes';
import { keyHint } from '../lib/keys';

const BUDGETS = [0, 30, 60, 100, 300, 1000];
/** the engine gives up after 200 s and the sidecar stops it at 260 s; the page stops waiting a little later */
const PLAN_WAIT_MS = 280_000;
// international first, Chinese after (the shared platform registry's order), everywhere they are listed
const PLATS = orderPlatforms(['youtube-shorts', 'tiktok', 'instagram', 'xiaohongshu', 'douyin', 'bilibili']);
const PLAT_STYLE: Record<string, { bg: string; g: string }> = {
  douyin: { bg: '#111', g: '\u6296' },
  xiaohongshu: { bg: '#e8293b', g: '\u7ea2' },
  tiktok: { bg: '#111', g: '♪' },
  'youtube-shorts': { bg: '#e62117', g: '▶' },
  bilibili: { bg: '#00a1d6', g: 'b' },
  instagram: { bg: '#c13584', g: '◎' },
};

export function CreatePlan({ format }: { format?: FormatId }) {
  const c = useCreate();
  const formats = useCreateLoad((x) => x.formats(), []);
  const series = useCreateLoad((x) => x.listSeries(), []);
  const providers = useCreateLoad((x) => x.providers(), []);
  const spend = useCreateLoad((x) => x.spend(), []);
  const [prompt, setPrompt] = useState('');
  const [fmt, setFmt] = useState<FormatId | null>(format ?? null);
  const [budget, setBudget] = useState(60);
  const [plats, setPlats] = useState<string[]>(['youtube-shorts', 'tiktok', 'xiaohongshu', 'douyin']);
  const shown = useMemo(() => orderPlatforms(plats), [plats]);
  const [platOpen, setPlatOpen] = useState(false);
  const act = useAction();
  const sample = useAction();
  const imp = useBoardImport();
  const ta = useRef<HTMLTextAreaElement | null>(null);

  const connected = (providers.data?.providers ?? []).some((p) => p.ready && (p.kind === 'cloud' || p.kind === 'mcp'));
  const rows: SeriesSummary[] = series.data?.series ?? [];
  const firstRun = providers.data !== null && !connected && rows.length === 0;
  const fmts: Format[] = useMemo(() => formats.data?.formats ?? [], [formats.data]);
  const fmtName = useMemo(() => fmts.find((f) => f.id === fmt), [fmts, fmt]);

  const [step, setStep] = useState<Record<string, unknown> | null>(null);
  const [since, setSince] = useState(0);
  const [planErr, setPlanErr] = useState<Msg | null>(null);
  const plan = (mode: 'auto' | 'template' = 'auto') =>
    act.run(async () => {
      if (!c) return;
      if (fmt === 'record' && !prompt.trim()) return goCreate({ screen: 'record' });
      setPlanErr(null);
      setStep(null);
      setSince(Date.now());
      try {
        const { job } = await c.plan({ prompt: prompt.trim() || undefined, format: fmt ?? undefined, budget_cny: budget || undefined, platforms: shown.map((p) => (p === 'xiaohongshu' ? 'xiaohongshu:full' : p)), lang: uiLang3(), mode });
        const res = await waitJob<{ draft: SeriesDraft }>(c, job, (j) => setStep(lastStep(j)), 400, PLAN_WAIT_MS);
        const made = await c.createSeries(res.draft);
        goCreate({ screen: 'series', sid: made.series, tab: 'bible' });
      } catch (e) {
        if (e instanceof JobError) setPlanErr(e.msg);
        else throw e;
      } finally {
        setStep(null);
      }
    });

  const used = spend.data?.used ?? 0;
  return (
    <div className="cr cr-home" data-testid="create-new">
      <Crumbs items={[{ label: t('create.crumb'), to: { screen: 'home' } }, { label: fmtName ? l10n(fmtName.labels) : t('create.start.script') }]} />
      <h1 className="hello">{t('create.home.title')}</h1>
      <div className="tag">{firstRun ? t('create.home.tagFirst') : t('create.home.tag')}</div>
      <BoardDrop className="cr-cmp" onPath={(p) => void imp.run(p)}>
        <textarea
          ref={ta}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder={t('create.home.placeholder')}
          aria-label={t('create.home.placeholder')}
          data-testid="create-prompt"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              void plan('auto');
            }
          }}
        />
        <div className="ft">
          <button className="cr-opt icon" title={t('create.import.hint')} aria-label={t('create.import.button')} onClick={() => void imp.pick()} disabled={!!imp.busy}>
            <Paperclip className="ico" />
          </button>
          <label className="cr-opt" data-testid="create-format">
            <Layers className="ico" />
            {fmtName ? t('create.home.formatIs', { name: l10n(fmtName.labels) }) : t('create.home.formatAuto')}
            <ChevronDown className="ico" />
            <select value={fmt ?? ''} onChange={(e) => setFmt((e.target.value || null) as FormatId | null)} aria-label={t('create.home.formatAuto')}>
              <option value="">{t('create.home.formatAuto')}</option>
              {fmts.map((f) => (
                <option key={f.id} value={f.id}>
                  {l10n(f.labels)}
                </option>
              ))}
            </select>
          </label>
          <label className="cr-opt" data-testid="create-budget">
            <CircleDollarSign className="ico" />
            {budget ? t('create.home.budget', { n: yuan(budget) }) : t('create.home.budgetNone')}
            <ChevronDown className="ico" />
            <select value={budget} onChange={(e) => setBudget(Number(e.target.value))} aria-label={t('create.home.budgetNone')}>
              {BUDGETS.map((b) => (
                <option key={b} value={b}>
                  {b ? yuan(b) : t('create.home.budgetNone')}
                </option>
              ))}
            </select>
          </label>
          <span style={{ position: 'relative' }}>
            <button className="cr-opt" onClick={() => setPlatOpen(!platOpen)} data-testid="create-platforms">
              <span className="cr-plats">
                {shown.slice(0, 3).map((p) => (
                  <i key={p} style={{ background: PLAT_STYLE[p]?.bg }}>
                    {PLAT_STYLE[p]?.g}
                  </i>
                ))}
              </span>
              {shown.length
                ? shown.length > 2
                  ? t('create.home.platforms', { first: shown.slice(0, 2).map((p) => t(`create.plat.${p}` as 'create.plat.douyin')).join(', '), n: shown.length - 2 })
                  : shown.map((p) => t(`create.plat.${p}` as 'create.plat.douyin')).join(', ')
                : t('create.home.platformsNone')}
              <ChevronDown className="ico" />
            </button>
            {platOpen && (
              <div className="cr-pop" onMouseLeave={() => setPlatOpen(false)}>
                {PLATS.map((p) => (
                  <label key={p}>
                    <input type="checkbox" checked={plats.includes(p)} onChange={(e) => setPlats(orderPlatforms(e.target.checked ? [...plats, p] : plats.filter((x) => x !== p)))} />
                    {t(`create.plat.${p}` as 'create.plat.douyin')}
                  </label>
                ))}
              </div>
            )}
          </span>
          <span className="sp" />
          <span className="cr-hint">{keyHint('⌘↵')}</span>
          <button className="btn primary lg" disabled={act.busy || (!prompt.trim() && !fmt)} onClick={() => void plan('auto')} data-testid="create-plan">
            <Sparkles className="ico" />
            {act.busy ? t('create.home.planning') : t('create.home.plan')}
          </button>
        </div>
      </BoardDrop>
      <div className="row" style={{ gap: 10, marginTop: 10, alignItems: 'center' }}>
        <ImportBoardButton imp={imp} testId="create-import-board" small />
        <span className="muted" style={{ fontSize: 13 }}>
          {t('create.import.hint')}
        </span>
      </div>
      <ImportNote imp={imp} />
      {act.busy && <PlanProgress step={step} since={since} />}
      {!act.busy && planErr && <PlanError msg={planErr} busy={act.busy} onRetry={() => void plan('auto')} onTemplate={() => void plan('template')} />}
      {act.error && (
        <div className="cr-err" style={{ marginTop: 10 }} data-testid="create-plan-error">
          {act.error}
        </div>
      )}

      {rows.length > 0 && (
        <>
          <div className="cr-costbar" data-testid="create-costbar">
            <CircleDollarSign className="ico muted" />
            <span className="muted">{t('create.cost.thisMonth')}</span>
            <b style={{ fontWeight: 500 }}>{t('create.cost.spent', { n: yuan(used) })}</b>
            <span className="sp" />
            <span className="muted">{spend.data?.cap ? t('create.cost.cap', { n: yuan(spend.data.cap) }) : t('create.cost.noCap')}</span>
            <a className="link" href={createHref({ screen: 'settings' })} style={{ fontSize: 16 }}>
              {t('create.cost.manage')}
            </a>
          </div>
        </>
      )}

      {firstRun && (
        <>
          <div className="cr-notice" data-testid="create-first-run">
            <span className="ic">
              <Cloud className="ico lg" />
            </span>
            <div style={{ minWidth: 0 }}>
              <div className="t1">{t('create.first.title')}</div>
              <div className="t2">{t('create.first.body')}</div>
            </div>
            <span className="sp" />
            <a className="btn" href={createHref({ screen: 'settings' })}>
              {t('create.first.connect')}
            </a>
          </div>
        </>
      )}
      {(firstRun || !rows.some((s) => s.sample)) && rows.length < 3 && (
        <div className="cr-sample" data-testid="create-sample">
          <FormatArtMini />
          <div style={{ minWidth: 0 }}>
            <div className="t1">{t('create.sample.title')}</div>
            <div className="t2">{t('create.sample.body')}</div>
          </div>
          <span className="sp" />
          <button
            className="btn"
            disabled={sample.busy}
            onClick={() =>
              void sample.run(async () => {
                if (!c) return;
                const r = await c.sample(uiLang3());
                if (r.episode) goCreate({ screen: 'episode', eid: r.episode, tab: 'storyboard' });
                else goCreate({ screen: 'series', sid: r.series, tab: 'bible' });
              })
            }
            data-testid="create-open-sample"
          >
            {t('create.sample.open')}
          </button>
        </div>
      )}
      {(sample.error || series.error) && <div className="cr-err" style={{ marginTop: 10 }}>{sample.error ?? series.error}</div>}
    </div>
  );
}

function FormatArtMini() {
  return (
    <div style={{ width: 56, height: 72, borderRadius: 8, overflow: 'hidden', flex: 'none' }}>
      <FormatArt id="series-ad" badge={false} />
    </div>
  );
}
