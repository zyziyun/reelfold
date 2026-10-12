// The live pane (ux/run-view A, like tmux + Claude Code): what the planner / the run is doing, line by line - the model
// CLIs' turns as they stream (the prompt sent, thinking, tool calls, replies, tokens) and the engine's own stages and
// log, interleaved and labelled. Monospace, ANSI-safe, follows the end unless she scrolls up ("Jump to live"), Copy,
// Search, a filter (everything / the AI / the engine). Never invented: an empty pane says nothing has come yet.
import { ChevronDown, ChevronUp, Copy, Minus, PanelBottom, PanelRight, Search, X } from 'lucide-react';
import { memo, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { LiveLine } from '../../../shared/v04';
import { t } from '../i18n';
import { ansiSpans, clockOf, filterLines, lastModel, lineTag, searchHits, transcriptText, type LiveFilter, type LiveState } from '../lib/live';
import { providerName } from '../../../shared/aiRoutes';
import { modelLabel } from '../../../shared/aiModels';
import { useUi } from './ui';
import './livepane.css';

const STICK_PX = 28;

const Line = memo(function Line({ l, hit, cur, first }: { l: LiveLine; hit: boolean; cur: boolean; first: boolean }) {
  const spans = useMemo(() => ansiSpans(l.text), [l.text]);
  return (
    <div className={`lv-ln k-${l.kind} s-${l.src} ${hit ? 'lv-hit' : ''} ${cur ? 'lv-cur' : ''} ${l.kind === 'turn' && !first ? 'lv-gap' : ''}`} data-testid="live-line" data-src={l.src} data-kind={l.kind}>
      <span className="lv-t">{clockOf(l.at)}</span>
      <span className="lv-tag">{lineTag(l)}</span>
      <span className="lv-x">
        {l.kind === 'turn' ? '▸ ' : ''}
        {spans.map((s, i) => (s.cls ? <span key={i} className={s.cls}>{s.text}</span> : s.text))}
      </span>
    </div>
  );
});

export function LivePane({
  live,
  title,
  sub,
  compact = false,
  layout,
  onLayout,
  onCollapse,
  onTitle,
  testId = 'live-pane',
}: {
  live: LiveState;
  title?: string;
  sub?: string;
  compact?: boolean;
  layout?: 'below' | 'side';
  onLayout?: () => void;
  onCollapse?: () => void;
  /** the title opens the job (Watch all's tiles) */
  onTitle?: () => void;
  testId?: string;
}) {
  const ui = useUi();
  const [filter, setFilter] = useState<LiveFilter>('all');
  const [searching, setSearching] = useState(false);
  const [q, setQ] = useState('');
  const [hitAt, setHitAt] = useState(0);
  const body = useRef<HTMLDivElement | null>(null);
  const [stick, setStick] = useState(true);
  const seenCount = useRef(0);
  const [unseen, setUnseen] = useState(0);
  const lines = useMemo(() => filterLines(live.lines, filter), [live.lines, filter]);
  const hits = useMemo(() => searchHits(lines, q), [lines, q]);
  const hitSet = useMemo(() => new Set(hits), [hits]);
  const curHit = hits.length ? hits[Math.min(hitAt, hits.length - 1)] : -1;

  // follow the end while she is at the end; count what arrives while she reads further up
  useLayoutEffect(() => {
    const el = body.current;
    if (!el) return;
    const added = Math.max(0, lines.length - seenCount.current);
    seenCount.current = lines.length;
    if (stick && !q) el.scrollTop = el.scrollHeight;
    else if (added) setUnseen((n) => n + added);
  }, [lines.length]); // eslint-disable-line react-hooks/exhaustive-deps
  const onScroll = () => {
    const el = body.current;
    if (!el) return;
    const atEnd = el.scrollHeight - el.scrollTop - el.clientHeight < STICK_PX;
    setStick(atEnd);
    if (atEnd) setUnseen(0);
  };
  const jump = () => {
    const el = body.current;
    if (el) el.scrollTop = el.scrollHeight;
    setStick(true);
    setUnseen(0);
  };
  // a search hit scrolls into view (and stops following)
  useEffect(() => {
    if (curHit < 0) return;
    const el = body.current?.querySelectorAll('[data-testid=live-line]')[curHit] as HTMLElement | undefined;
    if (el) {
      setStick(false);
      el.scrollIntoView({ block: 'center' });
    }
  }, [curHit, q]);
  const step = (d: 1 | -1) => hits.length && setHitAt((k) => (Math.min(k, hits.length - 1) + d + hits.length) % hits.length);
  const copy = async () => {
    try {
      await window.desk.copyText(transcriptText(lines));
      ui.toast(t('lp.copied', { n: lines.length }));
    } catch {
      ui.toast(t('lp.copyFailed'), { error: true });
    }
  };
  const running = live.running;
  const lm = useMemo(() => lastModel(live.lines), [live.lines]);
  return (
    <section className={`lv ${compact ? 'lv-compact' : ''}`} data-testid={testId} aria-label={title ?? t('lp.title')} data-running={running ? '1' : '0'}>
      <header className="lv-hd">
        <span className={`lv-dot ${running ? 'on' : ''}`} aria-hidden />
        {onTitle ? (
          <button className="lv-title lv-open clamp1" onClick={onTitle} data-testid="live-open">
            {title}
          </button>
        ) : (
          <b className="lv-title clamp1">{title ?? t('lp.title')}</b>
        )}
        {sub ? <span className="lv-sub clamp1">{sub}</span> : null}
        {lm ? (
          <span className="lv-model clamp1" title={t('lp.model', { model: lm.model })} data-testid="live-model" data-model={lm.model}>
            {lm.provider ? `${providerName(lm.provider)} · ` : ''}
            {modelLabel(lm.model)}
          </span>
        ) : null}
        <span className="sp" />
        {!compact && (
          <div className="lv-seg" role="radiogroup" aria-label={t('lp.filter')}>
            {(['all', 'agent', 'engine'] as LiveFilter[]).map((f) => (
              <button key={f} role="radio" aria-checked={filter === f} className={filter === f ? 'on' : ''} onClick={() => setFilter(f)} data-testid={`live-filter-${f}`}>
                {t(`lp.f.${f}`)}
              </button>
            ))}
          </div>
        )}
        {searching ? (
          <span className="lv-search">
            <Search className="ico" />
            <input
              autoFocus
              value={q}
              onChange={(e) => (setQ(e.target.value), setHitAt(0))}
              onKeyDown={(e) => {
                if (e.key === 'Enter') step(e.shiftKey ? -1 : 1);
                if (e.key === 'Escape') {
                  setSearching(false);
                  setQ('');
                }
              }}
              placeholder={t('lp.search')}
              aria-label={t('lp.search')}
              data-testid="live-search"
            />
            <span className="lv-n tnum" data-testid="live-search-count">
              {q ? (hits.length ? `${Math.min(hitAt, hits.length - 1) + 1}/${hits.length}` : '0/0') : ''}
            </span>
            <button className="lv-ic" onClick={() => step(-1)} aria-label={t('lp.prev')} data-testid="live-search-prev">
              <ChevronUp className="ico" />
            </button>
            <button className="lv-ic" onClick={() => step(1)} aria-label={t('lp.next')} data-testid="live-search-next">
              <ChevronDown className="ico" />
            </button>
            <button className="lv-ic" onClick={() => (setSearching(false), setQ(''))} aria-label={t('lp.searchClose')}>
              <X className="ico" />
            </button>
          </span>
        ) : (
          <button className="lv-ic" onClick={() => setSearching(true)} aria-label={t('lp.search')} data-tip={t('lp.search')} data-testid="live-search-btn">
            <Search className="ico" />
          </button>
        )}
        <button className="lv-ic" onClick={() => void copy()} aria-label={t('lp.copy')} data-tip={t('lp.copy')} data-testid="live-copy" disabled={!lines.length}>
          <Copy className="ico" />
        </button>
        {onLayout && (
          <button className="lv-ic" onClick={onLayout} aria-label={t(layout === 'side' ? 'lp.below' : 'lp.side')} data-tip={t(layout === 'side' ? 'lp.below' : 'lp.side')} data-testid="live-layout" data-layout={layout}>
            {layout === 'side' ? <PanelBottom className="ico" /> : <PanelRight className="ico" />}
          </button>
        )}
        {onCollapse && (
          <button className="lv-ic" onClick={onCollapse} aria-label={t('lp.hide')} data-tip={t('lp.hide')} data-testid="live-collapse">
            <Minus className="ico" />
          </button>
        )}
      </header>
      <div className="lv-body" ref={body} onScroll={onScroll} role="log" aria-live="off" data-testid="live-body" data-stick={stick ? '1' : '0'}>
        {lines.length ? (
          lines.map((l, i) => <Line key={i} l={l} hit={hitSet.has(i)} cur={i === curHit} first={i === 0} />)
        ) : (
          <p className="lv-empty" data-testid="live-empty">
            {!live.loaded ? t('lp.loading') : running ? t('lp.waiting') : t('lp.none')}
          </p>
        )}
      </div>
      {!stick && (
        <button className="lv-jump" onClick={jump} data-testid="live-jump">
          ↓ {unseen > 0 ? t('lp.jumpN', { n: unseen }) : t('lp.jump')}
        </button>
      )}
    </section>
  );
}
