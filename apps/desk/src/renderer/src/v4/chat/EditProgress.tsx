// A chat edit while it runs (「二次编辑的进度条」): the step it is on (read the clip -> the AI plans -> check -> apply),
// step x of y, the time so far and "about N s left" only when her past edits on this model say so; under it the AI's
// own log as it streams (the model CLI's thinking, tool calls, replies - lib/live, redacted by the engine): the last
// lines by default, the whole log on demand, Copy. Long silence reads "still working", never a frozen bar.
import { Copy } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import type { LiveLine } from '../../../../shared/v04';
import { t, type MessageKey } from '../../i18n';
import { EDIT_STEPS, editProgress, logTail, secondsLeft, type EditLocal, type EditPhase } from '../../lib/editProgress';
import { ansiSpans, lineTag, transcriptText, useLive } from '../../lib/live';
import { agoText } from '../../lib/liveStatus';
import { useUi } from '../ui';
import { FallbackNote } from '../AiChip';
import '../livepane.css';

export function phaseWords(p: EditPhase, applying?: number | null): string {
  if (p === 'apply') return t('ce.pg.apply', { n: applying ?? 0 });
  return t(`ce.pg.${p}` as MessageKey);
}

function LogLine({ l }: { l: LiveLine }) {
  const spans = useMemo(() => ansiSpans(l.text.replace(/\s+/g, ' ')), [l.text]);
  return (
    <div className={`lv-ln k-${l.kind} s-${l.src}`} data-testid="edit-log-line" data-kind={l.kind}>
      <span className="lv-tag">{lineTag(l)}</span>
      <span className="lv-x">{spans.map((s, i) => (s.cls ? <span key={i} className={s.cls}>{s.text}</span> : s.text))}</span>
    </div>
  );
}

export function EditProgress({
  live: id,
  started,
  local,
  estimate,
  failed,
  label,
}: {
  /** the request's live id (GET /api/live/ask/<id>) */
  live: string | null;
  /** when she sent it (ms) */
  started: number;
  local: EditLocal;
  /** her usual time on this model (s), or null */
  estimate: number | null;
  /** the request failed (her words for why) */
  failed?: string | null;
  /** what it is about ("Looking at 0:02-0:05") */
  label?: string | null;
}) {
  const live = useLive('ask', id, !!id);
  const [now, setNow] = useState(Date.now());
  const pg = editProgress(live.lines, local, started / 1000, now / 1000);
  const ended = !!failed || pg.stopped || !!pg.failedAt || pg.phase === 'done';
  useEffect(() => {
    if (ended) return;
    const tm = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(tm);
  }, [ended]);
  const elapsed = Math.max(0, (now - started) / 1000);
  const left = ended ? null : secondsLeft(estimate, elapsed);
  const failStep = failed || pg.failedAt ? (pg.failedAt ?? pg.phase) : null;
  const idx = EDIT_STEPS.indexOf(pg.phase === 'done' ? 'apply' : pg.phase);
  return (
    <div className={`ep ${failStep ? 'bad' : ''}`} data-testid="edit-progress" data-phase={failStep ? 'failed' : pg.phase} data-step={pg.step} aria-live="polite">
      <div className="ep-hd">
        <b className="clamp1" data-testid="edit-phase">
          {failStep ? t('ce.pg.failedAt', { step: phaseWords(failStep, local.applying) }) : pg.stopped ? t('ce.pg.stopped') : phaseWords(pg.phase, local.applying)}
        </b>
        <span className="sp" />
        <span className="ep-meta" data-testid="edit-meta">
          {[t('ce.pg.step', { i: pg.step, n: pg.steps }), agoText(elapsed), left != null ? t('ce.pg.left', { s: left }) : ''].filter(Boolean).join(' · ')}
        </span>
      </div>
      {label ? <div className="ep-what clamp1 muted">{label}</div> : null}
      <div className="ep-bar" role="progressbar" aria-valuemin={0} aria-valuemax={pg.steps} aria-valuenow={pg.phase === 'done' ? pg.steps : idx}>
        {EDIT_STEPS.map((s, i) => (
          <i key={s} className={i < idx || pg.phase === 'done' ? 'done' : i === idx ? (failStep || pg.stopped ? 'bad' : 'now') : ''} data-step={s} />
        ))}
      </div>
      {failed ? <div className="ep-why drop1" data-testid="edit-failed">{failed}</div> : null}
      {pg.fallback && <FallbackNote fallback={pg.fallback} />}
      {pg.quiet && !failStep ? (
        <div className="ep-quiet muted" data-testid="edit-quiet">
          {t('ce.pg.quiet')}
        </div>
      ) : null}
      <AgentLog lines={live.lines} />
    </div>
  );
}

/** The AI's own log under a request (lib/live lines, redacted by the engine): the newest 3 lines, the whole log on
 * demand, Copy. */
export function AgentLog({ lines: all }: { lines: LiveLine[] }) {
  const ui = useUi();
  const [open, setOpen] = useState(false);
  const lines = useMemo(() => all.filter((l) => l.kind !== 'progress' && l.text.trim()), [all]);
  const tail = open ? lines : logTail(lines, 3);
  const copy = async () => {
    try {
      await window.desk.copyText(transcriptText(lines));
      ui.toast(t('lp.copied', { n: lines.length }));
    } catch {
      ui.toast(t('lp.copyFailed'), { error: true });
    }
  };
  return (
    <>
      <div className={`ep-log lv ${open ? 'open' : ''}`} data-testid="edit-log">
        {tail.length ? tail.map((l, i) => <LogLine key={`${lines.length}-${i}`} l={l} />) : <div className="lv-ln ep-wait">{t('ce.pg.wait')}</div>}
      </div>
      {lines.length > 0 && (
        <div className="ep-ft">
          <button className="btn ghost sm" onClick={() => setOpen((v) => !v)} data-testid="edit-log-toggle" aria-expanded={open}>
            {open ? t('ce.pg.logHide') : t('ce.pg.log', { n: lines.length })}
          </button>
          <button className="btn ghost sm" onClick={() => void copy()} data-testid="edit-log-copy">
            <Copy className="ico" />
            {t('ce.pg.copy')}
          </button>
        </div>
      )}
    </>
  );
}
