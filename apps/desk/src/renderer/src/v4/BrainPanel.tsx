// "How it's cut" on the project page (the engine's editor brain, desk_engine/brain.py): the template the project is
// cut with and why (Change: the same recipe's other templates), the shot plan with "why this effect" per shot (two
// plain alternatives at most, Reset when she changed it), and the "Could be generated" cards. Generating one goes
// through the Create spend gate (BrainGate: the price, the most it can cost, the month left, every refusal) and only
// her click there spends; the take lands in the edit at the proposed spot and the project re-renders - "Take it out"
// undoes that. Mockup: ux/editor-brain/mockups.html (A).
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { ChevronRight, Loader2, RefreshCw, Sparkles, TriangleAlert } from 'lucide-react';
import type { BrainDoc, BrainProposal, BrainShot, BrainState } from '../../../shared/v04';
import { getLang, t, type MessageKey } from '../i18n';
import { useEngine, useLoad } from '../lib/engine';
import { BrainGate, gateText } from './BrainGate';
import { said } from './brainText';
import { Thumb } from './kit';
import { errText } from './msg';
import { useUi } from './ui';
import './brain.css';

export { said };

const BY: Record<string, MessageKey> = { rules: 'brain.by.rules', her: 'brain.by.her', ai: 'brain.by.ai' };
const JOIN: Record<string, MessageKey> = {
  open: 'brain.join.open',
  cut: 'brain.join.cut',
  'beat-cut': 'brain.join.beat',
  dissolve: 'brain.join.dissolve',
  'match-cut': 'brain.join.match',
  morph: 'brain.join.morph',
  'morph-fallback': 'brain.join.punch',
  continuous: 'brain.join.continuous',
};

/** The tile's short line: how it joins, how long it holds, and a speed when it is not 1x. */
export function shotLine(s: BrainShot): string {
  if (s.skip) return t('brain.shot.out');
  const parts = [JOIN[s.transition?.kind ?? ''] ? t(JOIN[s.transition!.kind]) : s.transition?.kind ?? '', t('brain.secs', { n: Math.round(s.hold_s ?? 0) })];
  if (s.speed === 'slowmo') parts.push(t('brain.speed.slowmo'));
  if (s.speed === 'ramp') parts.push(t('brain.speed.ramp'));
  return parts.filter(Boolean).join(' · ');
}

/** The one plain alternative per decision she may want: the runner-up of the engine's own candidates. */
export function alternative(s: Pick<BrainShot, 'transition' | 'speed' | 'choices'>, dim: 'transition' | 'speed'): string | null {
  const cur = dim === 'transition' ? s.transition?.kind : s.speed;
  const c = (s.choices?.[dim] ?? []).map(([k]) => k).filter((k) => k !== cur && k !== 'open' && k !== 'morph-fallback' && k !== 'continuous');
  return c[0] ?? null;
}

export function money(cny: number | null | undefined): string {
  return cny == null ? t('brain.gen.priceUnknown') : `≈ ¥${cny.toFixed(cny < 10 ? 1 : 0)}`;
}

export type GenView = 'idea' | 'generating' | 'placed' | 'kept' | 'failed' | 'unknown' | 'skipped';

/** What a proposal's card shows: the engine's status, unless this desk session knows a generation is running. */
export function genView(p: BrainProposal, live?: BrainState['generating']): GenView {
  const run = live?.[p.id]?.state;
  if (run === 'generating') return 'generating';
  if (run === 'failed' && (p.status === 'proposed' || p.status === 'approved' || p.status === 'failed')) return 'failed';
  switch (p.status) {
    case 'generating':
      return 'generating';
    case 'placed':
      return 'placed';
    case 'generated':
      return 'kept';
    case 'failed':
      return 'failed';
    case 'unknown-charge':
      return 'unknown';
    case 'skipped':
      return 'skipped';
    default:
      return 'idea';
  }
}

export function BrainPanel({ item }: { item: string }) {
  const { client, subscribe } = useEngine();
  const ui = useUi();
  const [n, setN] = useState(0);
  const { data, setData } = useLoad((c) => c.brain(item), [item, n]);
  const [sel, setSel] = useState<string | null>(null);
  const [menu, setMenu] = useState(false);
  const [busy, setBusy] = useState(false);
  const [gate, setGate] = useState<BrainProposal | null>(null);
  useEffect(() => subscribe((e) => (e.type === 'brain' && e.item === item ? setN((x) => x + 1) : undefined)), [subscribe, item]);
  const computing = data?.state === 'computing';
  const generating = Object.values(data?.generating ?? {}).some((g) => g.state === 'generating');
  useEffect(() => {
    if (!computing && !generating) return;
    const tm = setInterval(() => setN((x) => x + 1), 4000);
    return () => clearInterval(tm);
  }, [computing, generating]);
  const doc = data?.doc ?? null;
  const shots = useMemo(() => doc?.plan?.shots ?? [], [doc]);
  const used = shots.filter((s) => !s.skip);
  const cur = shots.find((s) => s.id === sel) ?? null;
  if (!data || !data.supported) return null;
  if (data.state === 'failed' && !doc) return null; // the engine could not read the footage: nothing to show
  const apply = async (fn: () => Promise<{ doc: BrainDoc }>) => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await fn();
      setData({ ...data, state: 'ready', doc: r.doc });
    } catch (e) {
      ui.toast(errText(e), { error: true });
    } finally {
      setBusy(false);
    }
  };
  const tpl = doc?.template;
  const props = doc?.proposals ?? [];
  const open = props.filter((p) => p.status === 'proposed');
  const inEdit = props.filter((p) => p.status === 'placed').length;
  const answer = (p: BrainProposal, action: 'take' | 'skip' | 'undo' | 'out' | 'in') => {
    if (!client) return;
    if (action === 'take') return setGate(p);
    if (action === 'out' || action === 'in')
      return void apply(async () => {
        const r = await client.brainPlace(item, p.id, action === 'out');
        ui.toast(action === 'out' ? t('brain.gen.tookOut') : t('brain.gen.putBack'));
        return r;
      });
    void apply(() => client.brainGen(item, p.id, action));
  };
  return (
    <section className="brain" data-testid="brain">
      <div className="brain-hd">
        <span className="muted">{t('brain.madeAs')}</span>
        {tpl ? (
          <span className="brain-chip" data-testid="brain-template">
            {getLang() === 'zh-CN' ? tpl.label_zh : tpl.label}
          </span>
        ) : (
          <span className="muted">{computing ? t('brain.reading') : '—'}</span>
        )}
        {tpl && <span className="tag" data-testid="brain-by">{t(BY[tpl.by] ?? 'brain.by.rules')}</span>}
        <span className="sp" />
        {computing && <span className="muted brain-busy">{t('brain.reading')}</span>}
        {tpl && tpl.alternatives.length > 0 && (
          <div className="brain-menu">
            <button className="btn sm" onClick={() => setMenu(!menu)} aria-expanded={menu} data-testid="brain-change">
              {t('brain.change')}
            </button>
            {menu && (
              <div className="brain-pop" role="menu">
                {tpl.alternatives.map((a) => (
                  <button
                    key={a.id}
                    role="menuitem"
                    className="brain-alt"
                    disabled={busy}
                    data-testid={`brain-alt-${a.id}`}
                    onClick={() => {
                      setMenu(false);
                      if (client) void apply(() => client.brainTemplate(item, a.id));
                    }}
                  >
                    <b>{getLang() === 'zh-CN' ? a.label_zh : a.label}</b>
                    <span className="muted">{a.blurb}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        <button className="btn ghost icon sm" disabled={computing || !client} onClick={() => client && void client.brainRefresh(item).then(() => setN((x) => x + 1))} aria-label={t('brain.refresh')} data-tip={t('brain.refresh')}>
          <RefreshCw className="ico" />
        </button>
      </div>
      {tpl && (
        <p className="muted brain-why" data-testid="brain-reason">
          {said(tpl.reason)}
        </p>
      )}
      {used.length > 0 && (
        <details className="brain-shots" open={!!sel}>
          <summary className="wp-hd">
            <ChevronRight className="ico chev" />
            <b>{t('brain.shots')}</b>
            <span className="muted">· {t('brain.shotsSum', { used: used.length, all: shots.length, secs: Math.round(doc?.plan?.summary.seconds ?? 0) })}</span>
          </summary>
          <div className="brain-strip" data-testid="brain-strip">
            {shots.map((s) => (
              <button key={s.id} className={`brain-tile${s.skip ? ' out' : ''}${sel === s.id ? ' on' : ''}`} onClick={() => setSel(sel === s.id ? null : s.id)} data-testid={`brain-shot-${s.id}`}>
                <Thumb src={s.thumb ?? null} ratio="16/9" />
                <span className="brain-l">
                  {s.by === 'her' && <i className="dot you" />}
                  {shotLine(s)}
                </span>
              </button>
            ))}
          </div>
          {cur && <ShotWhy s={cur} busy={busy} onChange={(set) => client && void apply(() => client.brainShot(item, cur.id, set))} />}
        </details>
      )}
      {props.length > 0 && (
        <div className="brain-gen" data-testid="brain-gen">
          <div className="row">
            <Sparkles className="ico" />
            <b>{t('brain.gen.title')}</b>
            <span className="muted">
              ·{' '}
              {[open.length ? t('brain.gen.sum', { n: open.length, cost: money(doc?.cost.cny) }) : null, inEdit ? t('brain.gen.sumPlaced', { n: inEdit }) : null]
                .filter(Boolean)
                .join(' · ') || t('brain.gen.sumNone')}
            </span>
          </div>
          <div className="brain-cards">
            {props.map((p) => (
              <GenCard key={p.id} p={p} view={genView(p, data.generating)} live={data.generating?.[p.id]} busy={busy} onAnswer={(a) => answer(p, a)} />
            ))}
          </div>
        </div>
      )}
      {gate && client && (
        <BrainGate
          item={item}
          p={gate}
          onClose={() => setGate(null)}
          onStarted={() => {
            setGate(null);
            setN((x) => x + 1);
          }}
        />
      )}
    </section>
  );
}

/** "Why this" for one shot with the plain alternatives (the project page's strip and the clip timeline's shots lane
 * show the same box). */
export function ShotWhy({
  s,
  busy,
  onChange,
  extra,
}: {
  s: Pick<BrainShot, 'id' | 'why' | 'choices' | 'skip' | 'by' | 'transition' | 'speed'>;
  busy: boolean;
  onChange: (set: Record<string, string | boolean> | null) => void;
  extra?: ReactNode;
}) {
  const alt = alternative(s, 'transition');
  const spd = alternative(s, 'speed');
  const fits = (s.choices?.transition ?? []).map(([k, f]) => `${JOIN[k] ? t(JOIN[k]) : k} ${f.toFixed(2)}`).join(' · ');
  return (
    <div className="brain-whybox" data-testid="brain-why">
      <b>{t('brain.whyTitle', { id: s.id })}</b>
      {extra}
      <ul>
        {s.why.map((w, i) => (
          <li key={i}>{said(w)}</li>
        ))}
      </ul>
      <div className="row">
        {fits && <span className="muted brain-fit">{fits}</span>}
        <span className="sp" />
        {!s.skip && alt && (
          <button className="btn sm" disabled={busy} onClick={() => onChange({ transition: alt })} data-testid="brain-alt-join">
            {t('brain.instead', { what: JOIN[alt] ? t(JOIN[alt]) : alt })}
          </button>
        )}
        {!s.skip && spd && (
          <button className="btn sm" disabled={busy} onClick={() => onChange({ speed: spd })} data-testid="brain-alt-speed">
            {spd === 'normal' ? t('brain.speed.toNormal') : spd === 'slowmo' ? t('brain.speed.toSlow') : t('brain.speed.toRamp')}
          </button>
        )}
        <button className="btn sm" disabled={busy} onClick={() => onChange({ skip: !s.skip })} data-testid="brain-skip">
          {s.skip ? t('brain.useShot') : t('brain.leaveOut')}
        </button>
        {s.by === 'her' && (
          <button className="btn ghost sm" disabled={busy} onClick={() => onChange(null)} data-testid="brain-reset">
            {t('brain.reset')}
          </button>
        )}
      </div>
    </div>
  );
}

const MODE: Record<string, MessageKey> = {
  'image-to-video': 'brain.mode.i2v',
  'text-to-video': 'brain.mode.t2v',
  'first-last-frame': 'brain.mode.fl',
  'text-to-image': 'brain.mode.t2i',
};

function GenCard({
  p,
  view,
  live,
  busy,
  onAnswer,
}: {
  p: BrainProposal;
  view: GenView;
  live?: { error?: string | null; code?: string | null; params?: Record<string, unknown> | null };
  busy: boolean;
  onAnswer: (a: 'take' | 'skip' | 'undo' | 'out' | 'in') => void;
}) {
  const price = money(p.estimate.cny);
  const who = p.estimate.label || p.provider;
  const failText = live?.code ? gateText({ code: live.code, params: live.params ?? {} }, who) : p.run?.code ? gateText({ code: p.run.code, params: {} }, who) : '';
  const still = p.file && /\.(jpe?g|png)$/i.test(p.file);
  return (
    <div className={`brain-card ${view}`} data-testid={`brain-gen-${p.kind}`} data-state={view}>
      {p.file && !still && (view === 'placed' || view === 'kept') ? (
        <Thumb src={null} video={p.file} ratio="16/9" />
      ) : still ? (
        <Thumb src={p.file} ratio="16/9" />
      ) : p.source?.thumb ? (
        <Thumb src={p.source.thumb} ratio="16/9" />
      ) : (
        <div className="brain-ph">
          <Sparkles className="ico lg" />
        </div>
      )}
      <b>{said(p.title)}</b>
      <span className="muted">{said(p.why)}</span>
      <span className="muted brain-meta">
        {[who, MODE[p.mode] ? t(MODE[p.mode]) : p.mode, t('brain.secs', { n: p.seconds }), price, t('brain.gen.labelled')].join(' · ')}
      </span>
      {view === 'generating' && (
        <span className="brain-state" data-testid="brain-generating">
          <Loader2 className="ico spin" />
          {t('brain.gen.making', { who })}
        </span>
      )}
      {view === 'placed' && <span className="brain-state ok">{t('brain.gen.placed')}</span>}
      {view === 'kept' && <span className="brain-state">{p.kind === 'cover' ? t('brain.gen.keptCover') : t('brain.gen.kept')}</span>}
      {view === 'failed' && (
        <span className="brain-state bad" data-testid="brain-gen-failed">
          {t('brain.gen.failed')}
          {failText ? ` · ${failText}` : ''}
        </span>
      )}
      {view === 'unknown' && (
        <span className="brain-state bad">
          <TriangleAlert className="ico" />
          {t('brain.gen.unknown', { who })}
        </span>
      )}
      <div className="row">
        {(view === 'idea' || view === 'failed') && (
          <>
            <button className="btn primary sm" disabled={busy || p.estimate.cny == null} onClick={() => onAnswer('take')} data-testid="brain-approve">
              {view === 'failed' ? t('brain.gen.again', { price }) : t('brain.gen.approve', { price })}
            </button>
            {p.status === 'proposed' && (
              <button className="btn sm" disabled={busy} onClick={() => onAnswer('skip')} data-testid="brain-skip-gen">
                {t('brain.gen.skip')}
              </button>
            )}
          </>
        )}
        {view === 'placed' && (
          <button className="btn sm" disabled={busy} onClick={() => onAnswer('out')} data-testid="brain-take-out">
            {t('brain.gen.takeOut')}
          </button>
        )}
        {view === 'kept' && p.kind !== 'cover' && (
          <button className="btn sm" disabled={busy} onClick={() => onAnswer('in')} data-testid="brain-put-back">
            {t('brain.gen.putIn')}
          </button>
        )}
        {view === 'skipped' && (
          <>
            <span className="muted">{t('brain.gen.skipped')}</span>
            <span className="sp" />
            <button className="btn ghost sm" disabled={busy} onClick={() => onAnswer('undo')} data-testid="brain-undo">
              {t('brain.gen.undo')}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
