// A different canvas needs a new composition, or a cover for the unchanged video.
import { useState } from 'react';
import type { EditOp, OutputDoc } from '../../../shared/v04';
import { Modal } from '../components/ui';
import { t } from '../i18n';
import { useEngine } from '../lib/engine';
import { targetAspect } from '../lib/versions';
import { errText } from './msg';
import { newVideo, useUi } from './ui';

type Edit = (ops: EditOp[], undoToast?: boolean) => Promise<boolean>;
export function useResizeChoice(doc: OutputDoc, edit: Edit) {
  const { client } = useEngine();
  const ui = useUi();
  const [target, setTarget] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const aspect = target ? targetAspect(target) : null;
  const remake = async () => {
    if (!client || !aspect) return;
    setBusy(true);
    try {
      const owner = await client.historyItem(doc.item);
      location.hash = '#/studio';
      newVideo();
      ui.setDropped([owner.dir]);
      ui.setPrefill(t('resize.brief', { title: doc.title, aspect }), true);
      setTarget(null);
    } catch (e) { ui.toast(errText(e), { error: true }); }
    finally { setBusy(false); }
  };
  const cover = async () => {
    if (!aspect) return;
    setBusy(true);
    try {
      const ops: EditOp[] = doc.exports.filter((x) => targetAspect(x.target) === aspect)
        .map((x) => ({ op: 'export_remove', target: x.target }));
      ops.push({ op: 'cover', t: doc.cover_edit?.t ?? 0, text: `${doc.title}\n${t('resize.watchOriginal')}`, style: 'card', aspect } as EditOp);
      if (await edit(ops, true)) setTarget(null);
    } catch (e) { ui.toast(errText(e), { error: true }); }
    finally { setBusy(false); }
  };
  return {
    choose: (v: string) => setTarget(v),
    intercept: (ops: EditOp[]) => {
      const x = ops.find((op) => op.op === 'export_add' && targetAspect(op.target) && targetAspect(op.target) !== doc.files[0]?.aspect);
      if (!x || x.op !== 'export_add') return false;
      setTarget(x.target);
      return true;
    },
    dialog: target && <Modal title={t('resize.title', { aspect: aspect ?? target })} onClose={() => !busy && setTarget(null)}>
      <div className="col" style={{ padding: 20, gap: 14 }} data-testid="resize-choice">
        <p>{t('resize.help')}</p>
        <button className="btn primary" disabled={busy} onClick={() => void remake()} data-testid="resize-remake">{t('resize.remake')}</button>
        <p className="muted small">{t('resize.remakeHelp')}</p>
        <button className="btn" disabled={busy || doc.caps.cover === false} onClick={() => void cover()} data-testid="resize-cover">{t('resize.cover')}</button>
        <p className="muted small">{t('resize.coverHelp')}</p>
        <button className="btn ghost" disabled={busy} onClick={() => setTarget(null)}>{t('resize.cancel')}</button>
      </div>
    </Modal>,
  };
}
