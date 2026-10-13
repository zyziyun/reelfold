// Delete (「archived 可以加个删除按钮，删除 hardware 的文件，记得给个二次弹窗确认是软删除还是硬删除」): one dialog for
// every kind - a project, a batch / group, an import, a work folder, one video, a request - from the row menu, a group's
// header menu, the bulk bar and All projects. It lists exactly what goes (names, file count, size, the Reelfold-made
// paths) and what never does (her recordings / footage, her other files in the folder), then asks: Move to Trash
// (the default: Undo on the toast, then the system Trash, restorable there) or Delete permanently (a second, red step
// she has to tick). The engine re-checks the plan she saw (sig) before anything happens (engine/desk_engine/purge.py).
import { useState, type ReactNode } from 'react';
import { AlertTriangle, Trash2 } from 'lucide-react';
import type { DeletePlan, DeletePlanItem, DeleteSel } from '../../../shared/v04';
import { Modal } from '../components/ui';
import { t } from '../i18n';
import { useEngine } from '../lib/engine';
import { useHistory } from '../lib/history';
import { deleteTitle, fmtSize, okItems, refusedItems } from '../lib/purge';
import { errText } from './msg';
import { useUi } from './ui';
import './delete.css';

export interface DeleteApi {
  /** plan, then the dialog; ``onDone`` once something went (or went pending) */
  ask(sel: DeleteSel, onDone?: () => void): Promise<void>;
  modal: ReactNode;
}

interface Asking {
  sel: DeleteSel;
  plan: DeletePlan;
  step: 'choose' | 'hard';
  sure: boolean;
  busy: boolean;
  onDone?: () => void;
}

const SHOW = 6;

function Paths({ x }: { x: DeletePlanItem }) {
  if (x.kind === 'request') return <span className="faint">{t('del.noFiles')}</span>;
  const shown = x.targets.slice(0, SHOW);
  return (
    <>
      <span className="faint">{t('del.files', { n: x.files, size: fmtSize(x.bytes) })}</span>
      <ul className="del-paths" data-testid="delete-paths">
        {shown.map((p) => (
          <li key={p} title={p}>
            <code>{x.whole && x.targets.length === 1 ? `${p}  (${t('del.whole')})` : p}</code>
          </li>
        ))}
        {x.targets.length > SHOW && <li className="faint">{t('del.moreN', { n: x.targets.length - SHOW })}</li>}
      </ul>
    </>
  );
}

export function useDelete(): DeleteApi {
  const { client } = useEngine();
  const { reload } = useHistory();
  const ui = useUi();
  const [st, setSt] = useState<Asking | null>(null);
  const fail = (e: unknown) => ui.toast(errText(e), { error: true });

  const ask = async (sel: DeleteSel, onDone?: () => void) => {
    if (!client) return;
    try {
      const plan = await client.deletePlan(sel);
      if (!okItems(plan).length) {
        const r = refusedItems(plan)[0];
        ui.toast(r ? `${r.name}: ${t(`del.why.${r.reason ?? 'unsafe'}` as 'del.why.unsafe')}` : t('del.nothing'), { error: true, ms: 8000 });
        return;
      }
      setSt({ sel, plan, step: 'choose', sure: false, busy: false, onDone });
    } catch (e) {
      fail(e);
    }
  };

  const soft = async (a: Asking) => {
    if (!client) return;
    setSt({ ...a, busy: true });
    try {
      const r = await client.deleteStage(a.sel, a.plan.sig);
      setSt(null);
      reload();
      a.onDone?.();
      const n = okItems(a.plan).length;
      ui.toast(t('del.trashedN', { n }), {
        undo: async () => {
          try {
            await client.deleteUndo(r.id);
            reload();
            ui.toast(t('del.putBack'));
          } catch (e) {
            fail(e);
          }
        },
        // the Undo window is over: now the files go to the system Trash (main/trash.ts checks every path again)
        onGone: async () => {
          try {
            const res = await window.desk.trashPending(r.id);
            reload();
            if (res.back.length) ui.toast(t('del.backN', { n: res.back.length }), { error: true, ms: 8000 });
          } catch (e) {
            fail(e);
          }
        },
      });
    } catch (e) {
      setSt(null);
      fail(e);
    }
  };

  const hard = async (a: Asking) => {
    if (!client || !a.sure) return;
    setSt({ ...a, busy: true });
    try {
      const r = await client.deleteHard(a.sel, a.plan.sig);
      setSt(null);
      reload();
      a.onDone?.();
      if (r.deleted.length) ui.toast(t('del.goneN', { n: r.deleted.length }));
      for (const f of r.failed.slice(0, 3)) ui.toast(t('del.failed', { name: f.name }), { error: true, ms: 8000 });
    } catch (e) {
      setSt(null);
      fail(e);
    }
  };

  let modal: ReactNode = null;
  if (st) {
    const ok = okItems(st.plan);
    const refused = refusedItems(st.plan);
    const other = [...new Set(ok.flatMap((x) => x.other))];
    const total = t('del.files', { n: st.plan.files, size: fmtSize(st.plan.bytes) });
    const close = () => !st.busy && setSt(null);
    modal =
      st.step === 'choose' ? (
        <Modal title={deleteTitle(ok)} onClose={close}>
          <div className="del-body" data-testid="delete-dialog">
            <section>
              <h4>{t('del.goes')}</h4>
              <ul className="del-items">
                {ok.map((x) => (
                  <li key={x.key} data-testid="delete-item" data-kind={x.kind}>
                    <b>{x.name}</b> <span className="del-kind">{t(`del.kind.${x.kind}` as 'del.kind.project')}</span>
                    {x.kind === 'clip' && x.project ? <span className="faint"> · {t('del.inFolder', { where: x.project })}</span> : null}
                    <div>
                      <Paths x={x} />
                    </div>
                  </li>
                ))}
              </ul>
              {ok.length > 1 && st.plan.files > 0 && <p className="faint del-total">{t('del.total', { files: total })}</p>}
            </section>
            {st.plan.keep.length > 0 && (
              <section className="del-keep" data-testid="delete-keep">
                <h4>{t('del.keep')}</h4>
                <ul className="del-paths">
                  {st.plan.keep.slice(0, SHOW).map((p) => (
                    <li key={p} title={p}>
                      <code>{p}</code>
                    </li>
                  ))}
                  {st.plan.keep.length > SHOW && <li className="faint">{t('del.moreN', { n: st.plan.keep.length - SHOW })}</li>}
                </ul>
              </section>
            )}
            {other.length > 0 && <p className="faint" data-testid="delete-other">{t('del.other', { names: other.slice(0, 8).join(', ') })}</p>}
            {refused.length > 0 && (
              <section className="del-refused" data-testid="delete-refused">
                <h4>{t('del.refused')}</h4>
                <ul>
                  {refused.map((x) => (
                    <li key={x.key}>
                      <b>{x.name}</b>: {t(`del.why.${x.reason ?? 'unsafe'}` as 'del.why.unsafe')}
                    </li>
                  ))}
                </ul>
              </section>
            )}
            <p className="faint del-hint">{t('del.softHint')}</p>
          </div>
          <div className="row del-actions">
            <button className="btn ghost danger" disabled={st.busy} onClick={() => setSt({ ...st, step: 'hard', sure: false })} data-testid="delete-hard">
              {t('del.hard')}
            </button>
            <span className="sp" />
            <button className="btn" disabled={st.busy} onClick={close} data-testid="delete-cancel">
              {t('common.cancel')}
            </button>
            <button className="btn primary" autoFocus disabled={st.busy} onClick={() => void soft(st)} data-testid="delete-soft">
              <Trash2 className="ico" />
              {t('del.soft')}
            </button>
          </div>
        </Modal>
      ) : (
        <Modal title={t('del.hardTitle')} onClose={close}>
          <div className="del-body del-hardstep" data-testid="delete-hard-step">
            <p className="del-warn">
              <AlertTriangle className="ico" />
              <span>{t('del.hardBody', { files: total })}</span>
            </p>
            <ul className="del-items">
              {ok.slice(0, SHOW).map((x) => (
                <li key={x.key}>
                  <b>{x.name}</b> <span className="del-kind">{t(`del.kind.${x.kind}` as 'del.kind.project')}</span>
                </li>
              ))}
              {ok.length > SHOW && <li className="faint">{t('del.moreN', { n: ok.length - SHOW })}</li>}
            </ul>
            <p className="faint">{t('del.hardKeep')}</p>
            <label className="del-sure">
              <input type="checkbox" checked={st.sure} onChange={(e) => setSt({ ...st, sure: e.target.checked })} data-testid="delete-sure" />
              {t('del.hardSure')}
            </label>
          </div>
          <div className="row del-actions">
            <button className="btn" disabled={st.busy} onClick={() => setSt({ ...st, step: 'choose' })} data-testid="delete-back">
              {t('del.back')}
            </button>
            <span className="sp" />
            <button className="btn" disabled={st.busy} onClick={close}>
              {t('common.cancel')}
            </button>
            <button className="btn danger solid" disabled={!st.sure || st.busy} onClick={() => void hard(st)} data-testid="delete-hard-ok">
              <Trash2 className="ico" />
              {t('del.hardOk')}
            </button>
          </div>
        </Modal>
      );
  }
  return { ask, modal };
}
