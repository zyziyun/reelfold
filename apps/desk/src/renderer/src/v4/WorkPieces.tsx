// The making, piece by piece (2026-10-11, her Seattle vlog: "show each cut's pieces, the effects, the details, so I
// can step in early"): what the run has made so far, as the recipe declares it per stage - the graded segments while
// the render runs, the contact sheets, the cover options, the master - in recipe order, updating by itself while it
// runs. Each tile plays on hover and opens big on a click, with "Ask AI about this" (the project chat, her words
// started) and Pause while it runs. Generic over recipes: the engine's Project.pieces (stage `wip` + `preview`).
import { useEffect, useMemo, useState } from 'react';
import { ChevronRight, FolderOpen, Pause, Sparkles, X } from 'lucide-react';
import type { Piece } from '../../../shared/v04';
import { t } from '../i18n';
import { useEngine, useLoad } from '../lib/engine';
import { pieceLabel } from '../lib/pieces';
import { media, Thumb } from './kit';
import { PlayerOverlay } from './Player';
import { errText } from './msg';
import { useUi } from './ui';
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
  const [big, setBig] = useState<Piece | null>(null);
  const [pausing, setPausing] = useState(false);
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
  return (
    <details className="wp" open={open} data-testid="work-pieces" data-n={pieces.length} data-live={live ? '1' : '0'}>
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
                  <button key={p.path} className={`wp-tile ${p.state}`} onClick={() => setBig(p)} title={label} data-testid="work-piece" data-stage={p.stage} data-kind={p.kind} data-state={p.state}>
                    <Thumb src={isVideo(p) ? null : p.path} video={isVideo(p) ? p.path : null} ratio="16/9" />
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
      {big && (
        <PieceView
          p={big}
          onClose={() => setBig(null)}
          onAsk={() => {
            askProjectChat(item, t('wp.askPrompt', { label: pieceLabel(big) }));
            setBig(null);
          }}
        />
      )}
    </details>
  );
}

function PieceView({ p, onClose, onAsk }: { p: Piece; onClose: () => void; onAsk: () => void }) {
  const label = pieceLabel(p);
  const image = !isVideo(p);
  useEffect(() => {
    if (!image) return; // the player's overlay owns its keys (Esc closes)
    const on = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', on);
    return () => window.removeEventListener('keydown', on);
  }, [image, onClose]);
  const bar = (
    <div className="wp-bar" data-testid="piece-actions">
      <b className="clamp1">{label}</b>
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
  if (isVideo(p)) return <PlayerOverlay files={[{ path: p.path, aspect: '16:9' }]} title={label} onClose={onClose} extra={bar} />;
  return (
    <div className="pl-overlay wp-imgview" onMouseDown={(e) => e.target === e.currentTarget && onClose()} role="dialog" aria-label={label} data-testid="piece-view">
      <div className="wp-imgbox">
        <img src={media(p.path)} alt={label} />
        {bar}
        <button className="btn ghost icon wp-x" onClick={onClose} aria-label={t('wp.close')} data-testid="piece-close">
          <X className="ico" />
        </button>
      </div>
    </div>
  );
}
