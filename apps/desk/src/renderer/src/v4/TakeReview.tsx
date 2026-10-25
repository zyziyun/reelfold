import { useState } from 'react';
import type { InboxItem, TakeCandidate, TakeScorecard } from '../../../shared/v04';
import { t, has, type MessageKey } from '../i18n';
import { media } from './kit';

const checkLabel = (key: string) => has(`take.check.${key}`) ? t(`take.check.${key}` as MessageKey) : t('take.unknown');

export function reviewed(card: TakeScorecard): boolean {
  return Object.keys(card.hard ?? {}).length > 0 && Object.values(card.hard).every((v) => v === false)
    && Object.keys(card.soft ?? {}).length > 0 && Object.values(card.soft).every((v) => typeof v === 'boolean')
    && Object.values(card.soft).filter(Boolean).length < 3
    && ['A', 'B', 'C'].every((key) => typeof card.scores?.[key] === 'number' && card.scores[key]! >= 4 && card.scores[key]! <= 5);
}

export function TakeReview({ x, onDone, onSkip, onRefresh }: { x: InboxItem; onDone: (answer?: Record<string, unknown>) => void; onSkip: () => void; onRefresh?: () => Promise<void> }) {
  const [requesting, setRequesting] = useState(false);
  const reviewing = requesting || x.take_review?.state === 'running';
  const refresh = async () => {
    if (!onRefresh || reviewing) return;
    setRequesting(true);
    try { await onRefresh(); } catch { /* The host displays the request error. */ }
    finally { setRequesting(false); }
  };
  const units = x.take_units ?? [];
  const [picks, setPicks] = useState<Record<string, string>>(() => Object.fromEntries(units.map((u) =>
    [u.unit, (u.takes.find((v) => v.review === 'pass' && !v.stale) ?? u.takes[0])?.file ?? ''])));
  const [edits, setEdits] = useState<Record<string, TakeScorecard>>({});
  const selected = units.map((u) => ({ unit: u.unit, take: u.takes.find((v) => v.file === picks[u.unit]) }));
  const ready = !reviewing && selected.length > 0 && selected.every(({ take }) => take && !take.stale && take.revision && reviewed(edits[take.file] ?? take.scorecard));
  const change = (take: TakeCandidate, section: 'hard' | 'soft' | 'scores', key: string, value: boolean | number | null) => {
    setEdits((old) => {
      const card = old[take.file] ?? take.scorecard;
      return { ...old, [take.file]: { ...card, [section]: { ...card[section], [key]: value } } };
    });
  };
  const submit = () => {
    if (!ready) return;
    const reviews = Object.fromEntries(selected.filter(({ take }) => take && edits[take.file]).map(({ unit, take }) => {
      const card = edits[take!.file];
      return [unit, { revision: take!.revision, hard: card.hard, soft: card.soft, scores: card.scores }];
    }));
    onDone({ picks, reviews });
  };
  return <div className="card" style={{ padding: 24 }} data-testid="take-review">
    <h2>{t('take.title')}</h2><p className="muted">{t('take.help')}</p>
    {onRefresh && (units.some((u) => u.takes.some((v) => v.stale)) || reviewing || x.take_review?.state === 'failed') && <div>
      <button className="btn" onClick={() => void refresh()} disabled={reviewing}>{t(reviewing ? 'take.refreshing' : 'take.refresh')}</button>
      <p className="small muted" role="status">{t(x.take_review?.state === 'failed' ? 'take.refreshFailed' : 'take.refreshHelp')}</p>
    </div>}
    {units.map((u, i) => {
      const take = u.takes.find((v) => v.file === picks[u.unit]);
      if (!take) return null;
      const card = edits[take.file] ?? take.scorecard;
      const checks = (section: 'hard' | 'soft', unknown: boolean) => Object.entries(card[section] ?? {}).filter(([, v]) => (v === null) === unknown).map(([key, value]) =>
        <label key={`${section}.${key}`} className="col" style={{ gap: 5, margin: '12px 0' }}>
          <span>{checkLabel(key)}</span>
          <select aria-label={checkLabel(key)} value={value === null ? '' : String(value)} disabled={take.stale || reviewing}
            onChange={(e) => change(take, section, key, e.target.value === '' ? null : e.target.value === 'true')}>
            <option value="">{t('take.unknown')}</option><option value="false">{t('take.clear')}</option><option value="true">{t('take.issue')}</option>
          </select>
          {card.evidence?.[`${section}.${key}`]?.reason && <span className="small muted">{card.evidence[`${section}.${key}`].reason}</span>}
        </label>);
      return <section key={u.unit} style={{ borderTop: '1px solid var(--border)', padding: '20px 0' }} data-testid="take-unit">
        <h3>{t('take.shot', { n: i + 1 })}</h3>
        <div className="row" style={{ flexWrap: 'wrap', marginBottom: 12 }}>{u.takes.map((v, j) => <label key={v.file}>
          <input type="radio" name={`take-${u.unit}`} checked={v.file === picks[u.unit]} onChange={() => setPicks((p) => ({ ...p, [u.unit]: v.file }))} />
          {t('take.version', { n: j + 1 })} · {t(v.stale ? 'take.staleShort' : reviewed(edits[v.file] ?? v.scorecard) ? 'take.passed' : 'take.needsReview')}
        </label>)}</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 24 }}>
          <div><video key={take.file + take.revision} src={media(take.file, take.revision)} controls preload="metadata" style={{ width: '100%', maxHeight: 360 }} />
            {!!card.references?.length && <details><summary>{t('take.references')}</summary><div className="row" style={{ flexWrap: 'wrap' }}>{card.references.map((r) => <figure key={r.path}><img src={media(r.path)} alt={r.id} style={{ maxWidth: 160, maxHeight: 160 }} /><figcaption>{r.id}</figcaption></figure>)}</div></details>}
          </div>
          <div>
            {take.stale && <p role="alert">{t('take.stale')}</p>}
            {checks('hard', true)}{checks('soft', true)}
            <details open={Object.values(card.scores ?? {}).some((v) => v === null || v < 4) || Object.values(card.hard ?? {}).some((v) => v === true)}><summary>{t('take.details')}</summary>
              {checks('hard', false)}{checks('soft', false)}
              {(['A', 'B', 'C'] as const).map((key) => <label className="col" key={key} style={{ margin: '12px 0', gap: 5 }}>{t(`take.score.${key}`)}
                <select aria-label={t(`take.score.${key}`)} value={card.scores?.[key] ?? ''} disabled={take.stale || reviewing} onChange={(e) => change(take, 'scores', key, e.target.value ? Number(e.target.value) : null)}>
                  <option value="">{t('take.unknown')}</option>{[1, 2, 3, 4, 5].map((v) => <option key={v} value={v}>{v} / 5</option>)}
                </select></label>)}
            </details>
            <p className="small muted">{t(reviewed(card) && !take.stale ? 'take.passed' : 'take.requirement')}</p>
          </div>
        </div>
      </section>;
    })}
    <div className="row" style={{ marginTop: 20 }}><button className="btn ghost" onClick={onSkip}>{t('inbox.skip')}</button><span className="sp" />
      <button className="btn primary" disabled={!ready} onClick={submit} data-testid="take-continue">{t('take.continue')}</button></div>
  </div>;
}
