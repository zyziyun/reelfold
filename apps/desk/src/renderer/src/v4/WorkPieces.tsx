// The making, piece by piece (2026-10-11, her Seattle vlog: "show each cut's pieces, the effects, the details, so I
// can step in early"): what the run has made so far, as the recipe declares it per stage - the graded segments while
// the render runs, the contact sheets, the cover options, the master - in recipe order, updating by itself while it
// runs. Each tile plays on hover and opens big on a click, with "Ask AI about this" (the project chat, her words
// started) and Pause while it runs. Generic over recipes: the engine's Project.pieces (stage `wip` + `preview`).
import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import { ChevronLeft, ChevronRight, FolderOpen, Pause, Sparkles, X } from 'lucide-react';
import type { Piece } from '../../../shared/v04';
import { t } from '../i18n';
import { useEngine, useLoad } from '../lib/engine';
import { pieceLabel } from '../lib/pieces';
import { media, Thumb } from './kit';
import { Player } from './Player';
import { errText } from './msg';
import { isTyping, useUi } from './ui';
import { screenOwner } from '../lib/fullscreen';
import './workpieces.css';

const isVideo = (p: Piece) => p.kind === 'video' || p.kind === 'videos';

/** ask the project chat about something: it opens (if folded) with her words started */
export function askProjectChat(item: string, text: string) {
  window.dispatchEvent(new CustomEvent('project-chat:prefill', { detail: { item, text } }));
}

export function WorkPieces({ item, running, open = true, onPaused }: { item: string; running: boolean; open?: boolean; onPaused?: () => void }) {
  const { client, subscribe } = useEngine();
  const ui = useUi();
  const { data, reload } = useLoad((c) => c.pieces(item).catch(() => null), [item]);
  const [big, setBig] = useState<string | null>(null); // the open piece's path
  const [pausing, setPausing] = useState(false);
  const [expanded, setExpanded] = useState(open);
  useEffect(() => setExpanded(open), [open]);
  const pieces = useMemo(() => data?.pieces ?? [], [data]);
  const live = running || pieces.some((p) => p.state === 'running');
  // updates by itself: every 2.5 s while it runs, and when the run says something moved
  useEffect(() => {
    if (!live) return;
    const tm = window.setInterval(reload, 2500);
    return () => window.clearInterval(tm);
  }, [live]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => subscribe((e) => void ((e.type === 'batches' || e.type === 'run-exit' || e.type === 'inbox') && reload())), [subscribe]); // eslint-disable-line react-hooks/exhaustive-deps
  const jobs = useMemo(() => [...new Set(pieces.map((p) => p.job))], [pieces]);
  const pause = async () => {
    if (!client) return;
    setPausing(true);
    try {
      await client.stopHistory(item);
      ui.toast(t('wp.paused'));
      onPaused?.();
    } catch (e) {
      ui.toast(errText(e), { error: true });
    } finally {
      setPausing(false);
    }
  };
  if (!data) return null;
  if (!pieces.length && !running) return null;
  const newest = pieces.reduce<Piece | null>((a, p) => (p.state === 'running' && (!a || p.mtime > a.mtime) ? p : a), null);
  // the open piece as the run has it now (a contact sheet written again shows its new version), in the same viewer
  const at = big ? pieces.findIndex((p) => p.path === big) : -1;
  const shown = at >= 0 ? pieces[at] : null;
  return (
    <>
      <details className="wp" open={expanded} onToggle={(e) => setExpanded(e.currentTarget.open)} data-testid="work-pieces" data-n={pieces.length} data-live={live ? '1' : '0'}>
        <summary className="wp-hd">
          <ChevronRight className="ico wp-chev" />
          <b>{live ? t('wp.title') : t('wp.titleDone')}</b>
          <span className="muted">· {t('wp.count', { n: pieces.length })}</span>
          <span className="sp" />
          {running && (
            <button
              className="btn sm"
              onClick={(e) => {
                e.preventDefault();
                void pause();
              }}
              disabled={pausing}
              data-testid="wp-pause"
            >
              <Pause className="ico" />
              {t('wp.pause')}
            </button>
          )}
        </summary>
        {!pieces.length && <p className="muted small" data-testid="wp-empty">{t('wp.empty')}</p>}
        {jobs.map((j) => {
          const mine = pieces.filter((p) => p.job === j);
          return (
            <section key={j} className="wp-job" data-job={j}>
              {jobs.length > 1 && <h4 className="clamp1">{mine[0]?.title}</h4>}
              <div className="wp-grid">
                {mine.map((p) => {
                  const label = pieceLabel(p);
                  return (
                    <button key={p.path} className={`wp-tile ${p.state}`} onClick={() => setBig(p.path)} title={label} data-testid="work-piece" data-stage={p.stage} data-kind={p.kind} data-state={p.state}>
                      <Thumb src={isVideo(p) ? null : p.path} video={isVideo(p) ? p.path : null} v={p.mtime} ratio="16/9" />
                      <span className="wp-l clamp1" data-testid="work-piece-label">
                        {p === newest && <i className="dot run" aria-label={t('wp.making')} />}
                        {p.state === 'waiting' && <i className="dot you" aria-label={t('wp.waiting')} />}
                        {label}
                      </span>
                    </button>
                  );
                })}
              </div>
            </section>
          );
        })}
      </details>
      {/* outside the fold: an open piece stays open when the section folds itself (the run is done) */}
      {shown && (
        <PieceView
          p={shown}
          pos={{ n: at + 1, of: pieces.length }}
          onStep={(d) => setBig(pieces[(at + d + pieces.length) % pieces.length].path)}
          onClose={() => setBig(null)}
          onAsk={() => {
            askProjectChat(item, t('wp.askPrompt', { label: pieceLabel(shown) }));
            setBig(null);
          }}
        />
      )}
    </>
  );
}

/** A piece big: over the whole window (on <body>, so no page around it can clip it or sit over it), dimmed behind.
 * The box is never taller than the window - the media takes what is left after its title, controls and actions
 * (scaled to fit, its shape kept), so "Ask AI about this" always shows (2026-10-13, 0.2.8: a 16:9 "Picture 3" on a
 * running project had its action bar cut in half). Esc or a click outside closes it, ← → step through the pieces. */
function PieceView({ p, pos, onStep, onClose, onAsk }: { p: Piece; pos: { n: number; of: number }; onStep: (d: 1 | -1) => void; onClose: () => void; onAsk: () => void }) {
  const label = pieceLabel(p);
  const image = !isVideo(p);
  const view = useRef<HTMLDivElement | null>(null);
  // shown once its image is in (or failed): the box sizes to the image, so laid out before it its actions sit at the
  // top and jump down under her pointer when it loads
  const [loaded, setLoaded] = useState<string | null>(null); // the path whose image is in
  const ready = loaded === p.path;
  // a video's own shape: the box is as wide as the video can be shown at the height left for it
  const [shape, setShape] = useState<{ path: string; ar: number } | null>(null);
  const ar = shape?.path === p.path ? shape.ar : null;
  useEffect(() => {
    if (image) return;
    const v = view.current?.querySelector('video');
    if (!v) return;
    const path = p.path;
    const on = () => void (v.videoWidth && v.videoHeight && setShape({ path, ar: v.videoWidth / v.videoHeight }));
    on();
    v.addEventListener('loadedmetadata', on);
    return () => v.removeEventListener('loadedmetadata', on);
  }, [image, p.path]);
  useEffect(() => {
    // before the player's own keys (← → are its frame steps): here they step through the pieces; Shift ← → still
    // seek, and in full screen the player has every key
    const on = (e: KeyboardEvent) => {
      if (screenOwner() || isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey || document.querySelector('.scrim, .ctx')) return;
      if ((e.key === 'ArrowLeft' || e.key === 'ArrowRight') && !e.shiftKey) {
        e.preventDefault();
        e.stopImmediatePropagation();
        if (pos.of > 1) onStep(e.key === 'ArrowRight' ? 1 : -1);
      } else if (image && e.key === 'Escape') onClose(); // a video: the player's Esc closes (it knows full screen)
    };
    window.addEventListener('keydown', on, true);
    return () => window.removeEventListener('keydown', on, true);
  }, [image, onClose, onStep, pos.of]);
  const bar = (
    <div className="wp-bar" data-testid="piece-actions">
      {image && <b className="clamp1">{label}</b>}
      {pos.of > 1 && (
        <span className="wp-step">
          <button className="btn ghost icon sm" onClick={() => onStep(-1)} aria-label={t('wp.prev')} data-tip={`${t('wp.prev')} · ←`} data-testid="piece-prev">
            <ChevronLeft className="ico" />
          </button>
          <span className="muted tnum" data-testid="piece-pos">
            {t('wp.pos', { n: pos.n, of: pos.of })}
          </span>
          <button className="btn ghost icon sm" onClick={() => onStep(1)} aria-label={t('wp.next')} data-tip={`${t('wp.next')} · →`} data-testid="piece-next">
            <ChevronRight className="ico" />
          </button>
        </span>
      )}
      <span className="sp" />
      <button className="btn sm primary" onClick={onAsk} data-testid="piece-ask">
        <Sparkles className="ico" />
        {t('wp.ask')}
      </button>
      <button className="btn sm ghost" onClick={() => void window.desk.showItem(p.path)} data-testid="piece-reveal">
        <FolderOpen className="ico" />
        {t('wp.reveal')}
      </button>
    </div>
  );
  return createPortal(
    <div
      ref={view}
      className={`pl-overlay wp-view ${image ? 'wp-imgview' : 'wp-vidview'}`}
      style={ar ? ({ '--ar': ar } as CSSProperties) : undefined}
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
      role="dialog"
      aria-modal="true"
      aria-label={label}
      data-testid="piece-view"
      data-path={p.path}
    >
      {image ? (
        <div className="wp-imgbox" data-ready={ready ? '1' : '0'} data-testid="piece-box">
          <img key={p.path} src={media(p.path, p.mtime)} alt={label} onLoad={() => setLoaded(p.path)} onError={() => setLoaded(p.path)} />
          {bar}
          <button className="btn ghost icon wp-x" onClick={onClose} aria-label={t('wp.close')} data-testid="piece-close">
            <X className="ico" />
          </button>
        </div>
      ) : (
        // the app's big player (its keys, Esc closes, full screen), the piece's actions under it
        <Player key={p.path} files={[{ path: p.path, aspect: '16:9' }]} title={label} onClose={onClose} autoPlay keys extra={bar} testId="piece-box" />
      )}
    </div>,
    document.body,
  );
}
