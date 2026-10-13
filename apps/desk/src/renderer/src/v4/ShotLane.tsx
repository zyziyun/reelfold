// The shot plan on the clip timeline: the builder's per-shot edit list (python -m vstudio.brain shots: which take
// each shot plays, from build_vlog / build_fun / the photo-story renderer / the talking-head compose) with the editor
// brain's "why this" + alternatives - the same box as the project page's "How it's cut", acting the same way (her
// change goes into the plan and the drafted edit, the clip re-renders). An AI-generated shot says so and can be
// taken out again.
import { useCallback, useEffect, useState } from 'react';
import { Sparkles, X } from 'lucide-react';
import type { ClipShot, ClipShots } from '../../../shared/v04';
import { t } from '../i18n';
import { useEngine } from '../lib/engine';
import { said } from './brainText';
import { ShotWhy, shotLine } from './BrainPanel';
import { errText } from './msg';
import { useUi } from './ui';

/** The clip's shots, re-read when the brain or the project changes. */
export function useClipShots(item: string, clip: string | null) {
  const { client, subscribe } = useEngine();
  const [doc, setDoc] = useState<ClipShots | null>(null);
  const [n, setN] = useState(0);
  const reload = useCallback(() => setN((x) => x + 1), []);
  useEffect(() => {
    if (!client || !clip) return;
    let live = true;
    client
      .brainShots(item, clip)
      .then((d) => live && setDoc(d))
      .catch(() => live && setDoc(null));
    return () => {
      live = false;
    };
  }, [client, item, clip, n]);
  useEffect(() => subscribe((e) => (e.type === 'brain' && e.item === item ? reload() : undefined)), [subscribe, item, reload]);
  return { shots: doc?.supported ? doc.shots : [], doc, reload };
}

/** The short label a shot block carries on the lane. */
export function laneLabel(s: ClipShot): string {
  if (s.gen) return `${t('brain.tl.aiShort')} · ${said(s.gen.title)}`;
  if (s.role === 'hook') return t('brain.tl.hook');
  if (s.brain?.transition) return shotLine({ ...s.brain, skip: false, hold_s: s.t1 - s.t0 } as Parameters<typeof shotLine>[0]);
  return s.file ?? '';
}

/** The block's tooltip: the shot id, how it is cut, the take it plays. */
export function laneTitle(s: ClipShot): string {
  const take = s.file && s.src_in != null && s.src_out != null ? `${s.file} ${s.src_in.toFixed(1)}–${s.src_out.toFixed(1)} s` : (s.file ?? '');
  return [s.brain?.id, laneLabel(s), take].filter(Boolean).join(' · ');
}

export function ShotPop({ item, shot, onClose, onChanged }: { item: string; shot: ClipShot; onClose: () => void; onChanged: () => void }) {
  const { client } = useEngine();
  const ui = useUi();
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<unknown>, said_: string) => {
    if (busy) return;
    setBusy(true);
    try {
      await fn();
      ui.toast(said_);
      onChanged();
    } catch (e) {
      ui.toast(errText(e), { error: true });
    } finally {
      setBusy(false);
    }
  };
  const take =
    shot.file && shot.src_in != null && shot.src_out != null
      ? t('brain.tl.take', {
          file: shot.file,
          a: shot.src_in.toFixed(1),
          b: shot.src_out.toFixed(1),
        })
      : (shot.file ?? '');
  return (
    <div className="shot-pop" role="dialog" aria-label={shot.brain ? t('brain.whyTitle', { id: shot.brain.id }) : t('brain.tl.lane')} data-testid="tl-shot-pop">
      <button className="btn ghost icon sm x" onClick={onClose} aria-label={t('brain.tl.close')}>
        <X className="ico" />
      </button>
      {shot.gen ? (
        <div className="brain-whybox gen">
          <b>
            <Sparkles className="ico" /> {t('brain.tl.ai', { title: said(shot.gen.title) })}
          </b>
          <p className="muted">{said(shot.gen.why)}</p>
          <div className="row">
            <span className="muted brain-fit">{take}</span>
            <span className="sp" />
            {client && (
              <button
                className="btn sm"
                disabled={busy}
                onClick={() => void run(() => client.brainPlace(item, shot.gen!.id, true), t('brain.gen.tookOut'))}
                data-testid="tl-shot-takeout"
              >
                {t('brain.gen.takeOut')}
              </button>
            )}
          </div>
        </div>
      ) : shot.brain ? (
        <ShotWhy
          s={{
            ...shot.brain,
            why: shot.brain.why ?? [],
            skip: !!shot.brain.skip,
            by: shot.brain.by ?? 'rules',
          }}
          busy={busy}
          extra={take ? <div className="muted brain-take">{take}</div> : null}
          onChange={(set) => client && void run(() => client.brainShot(item, shot.brain!.id, set), t('brain.tl.redo'))}
        />
      ) : (
        <div className="brain-whybox">
          <b>{take}</b>
        </div>
      )}
    </div>
  );
}
