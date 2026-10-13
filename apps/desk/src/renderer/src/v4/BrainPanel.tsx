// "How it's cut" on the project page (the engine's editor brain, desk_engine/brain.py): the template the project is
// cut with and why (Change: the same recipe's other templates), the shot plan with "why this effect" per shot (two
// plain alternatives at most, Reset when she changed it), and the "Could be generated" cards she approves or skips.
// Nothing here spends: an approved idea waits for the Create spend gate. Mockup: ux/editor-brain/mockups.html (A).
import { useEffect, useMemo, useState } from 'react';
import { ChevronRight, RefreshCw, Sparkles } from 'lucide-react';
import type { BrainDoc, BrainProposal, BrainShot, BrainText } from '../../../shared/v04';
import { getLang, t, type MessageKey } from '../i18n';
import { useEngine, useLoad } from '../lib/engine';
import { Thumb } from './kit';
import { errText } from './msg';
import { useUi } from './ui';
import './brain.css';

/** The engine writes its reasons in English and Chinese; French reads the English. */
export const said = (x: BrainText | null | undefined): string => (!x ? '' : getLang() === 'zh-CN' ? x.zh || x.en : x.en || x.zh);

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
export function alternative(s: BrainShot, dim: 'transition' | 'speed'): string | null {
  const cur = dim === 'transition' ? s.transition?.kind : s.speed;
  const c = (s.choices?.[dim] ?? []).map(([k]) => k).filter((k) => k !== cur && k !== 'open' && k !== 'morph-fallback' && k !== 'continuous');
  return c[0] ?? null;
}

export function money(cny: number | null | undefined): string {
  return cny == null ? t('brain.gen.priceUnknown') : `≈ ¥${cny.toFixed(cny < 10 ? 1 : 0)}`;
}

export function BrainPanel({ item }: { item: string }) {
  const { client, subscribe } = useEngine();
  const ui = useUi();
  const [n, setN] = useState(0);
  const { data, setData } = useLoad((c) => c.brain(item), [item, n]);
  const [sel, setSel] = useState<string | null>(null);
  const [menu, setMenu] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => subscribe((e) => (e.type === 'brain' && e.item === item ? setN((x) => x + 1) : undefined)), [subscribe, item]);
  const computing = data?.state === 'computing';
  useEffect(() => {
    if (!computing) return;
    const tm = setInterval(() => setN((x) => x + 1), 4000);
    return () => clearInterval(tm);
  }, [computing]);
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
            <span className="muted">· {t('brain.gen.sum', { n: open.length, cost: money(doc?.cost.cny) })}</span>
          </div>
          <div className="brain-cards">
            {props.map((p) => (
              <GenCard key={p.id} p={p} busy={busy} onAnswer={(action) => client && void apply(() => client.brainGen(item, p.id, action, action === 'approve' ? p.code : undefined))} />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function ShotWhy({ s, busy, onChange }: { s: BrainShot; busy: boolean; onChange: (set: Record<string, string | boolean> | null) => void }) {
  const alt = alternative(s, 'transition');
  const spd = alternative(s, 'speed');
  const fits = (s.choices?.transition ?? []).map(([k, f]) => `${JOIN[k] ? t(JOIN[k]) : k} ${f.toFixed(2)}`).join(' · ');
  return (
    <div className="brain-whybox" data-testid="brain-why">
      <b>{t('brain.whyTitle', { id: s.id })}</b>
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

function GenCard({ p, busy, onAnswer }: { p: BrainProposal; busy: boolean; onAnswer: (a: 'approve' | 'skip' | 'undo') => void }) {
  const price = money(p.estimate.cny);
  return (
    <div className={`brain-card ${p.status}`} data-testid={`brain-gen-${p.kind}`}>
      {p.source?.thumb ? <Thumb src={p.source.thumb} ratio="16/9" /> : <div className="brain-ph"><Sparkles className="ico lg" /></div>}
      <b>{said(p.title)}</b>
      <span className="muted">{said(p.why)}</span>
      <span className="muted brain-meta">
        {[p.estimate.label || p.provider, MODE[p.mode] ? t(MODE[p.mode]) : p.mode, t('brain.secs', { n: p.seconds }), price, t('brain.gen.labelled')].join(' · ')}
      </span>
      <div className="row">
        {p.status === 'proposed' ? (
          <>
            <button className="btn primary sm" disabled={busy || p.estimate.cny == null} onClick={() => onAnswer('approve')} data-testid="brain-approve">
              {t('brain.gen.approve', { price })}
            </button>
            <button className="btn sm" disabled={busy} onClick={() => onAnswer('skip')} data-testid="brain-skip-gen">
              {t('brain.gen.skip')}
            </button>
          </>
        ) : (
          <>
            <span className="muted">{p.status === 'approved' ? t('brain.gen.approved') : t('brain.gen.skipped')}</span>
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
