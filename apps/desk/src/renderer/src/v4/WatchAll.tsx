// Watch all (ux/run-view D, herdr-like): every running job's live pane tiled - the requests being planned and the
// projects being made - each with its title (opens its page), where it is and its progress. The Studio header's
// toggle shows it in place of the selected video's page.
import { LayoutGrid } from 'lucide-react';
import { t } from '../i18n';
import { useLive } from '../lib/live';
import type { StudioRow } from '../lib/studio';
import { rowHref } from '../lib/studioData';
import { Empty } from './kit';
import { LivePane } from './LivePane';
import './runview.css';

function Tile({ r, line, onOpen }: { r: StudioRow; line: string; onOpen: () => void }) {
  const live = useLive(r.kind === 'request' ? 'request' : 'project', r.kind === 'request' ? r.r?.id : r.item);
  const pct = r.p.progress == null ? null : Math.round(r.p.progress * 100);
  return (
    <div className="wa-tile" data-testid="watch-tile" data-row={r.key}>
      <LivePane live={live} title={r.title || t('home.planningRow')} sub={[line, pct != null ? `${pct}%` : null].filter(Boolean).join(' · ')} compact onTitle={onOpen} />
      <div className="wa-bar" aria-hidden>
        <i style={{ width: `${pct ?? 0}%` }} />
      </div>
    </div>
  );
}

export function WatchAll({ rows, lineOf, onClose }: { rows: StudioRow[]; lineOf: (r: StudioRow) => string; onClose: () => void }) {
  const n = rows.length;
  // the Studio closes Watch all when the page it shows changes (the route): closing it here first would let the Studio
  // pick its first row before the new route arrives
  const open = (r: StudioRow) => {
    const to = rowHref(r);
    if (location.hash === to) onClose();
    else location.hash = to;
  };
  const cols = n <= 1 ? 1 : n <= 4 ? 2 : 3;
  return (
    <div className="wa" data-testid="watch-all">
      <header className="wa-hd">
        <LayoutGrid className="ico" />
        <h2>{t('watch.title', { n })}</h2>
        <span className="sp" />
        <button className="btn" onClick={onClose} data-testid="watch-close">
          {t('watch.close')}
        </button>
      </header>
      {n ? (
        <div className="wa-grid" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
          {rows.map((r) => (
            <Tile key={r.key} r={r} line={lineOf(r)} onOpen={() => open(r)} />
          ))}
        </div>
      ) : (
        <div className="wa-empty">
          <Empty title={t('watch.none')} />
        </div>
      )}
    </div>
  );
}
