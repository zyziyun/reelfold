// "Export for editing software…": a clip (from its Export card) or every clip of a project (the project page) as a
// Premiere / Resolve XML, a CapCut or 剪映 draft, or an OpenTimelineIO timeline (engine `output nle`). International
// first, Chinese after. The drafts go straight into the app's drafts folder when it is there.
import { useState } from 'react';
import { FolderOpen } from 'lucide-react';
import type { NleFormat, NleResult } from '../../../shared/v04';
import { Modal } from '../components/ui';
import { t, tk } from '../i18n';
import { useEngine } from '../lib/engine';
import { errText } from './msg';

export const NLE_FORMATS: NleFormat[] = ['xmeml', 'capcut', 'otio', 'jianying'];
const IN_APP: NleFormat[] = ['capcut', 'jianying'];

export function nleApp(f: NleFormat): string {
  return tk(`nle.fmt.${f}`);
}

/** The README's "not carried" lines of a clip or of every clip of a project. */
function noteCount(r: NleResult): number {
  return (r.notes?.length ?? 0) + (r.outputs ?? []).reduce((n, x) => n + (x.notes?.length ?? 0), 0);
}

export function NleDialog({ item, clip, count, onClose }: { item: string; clip?: string | null; count?: number; onClose: () => void }) {
  const { client } = useEngine();
  const [fmt, setFmt] = useState<NleFormat>('xmeml');
  const [copy, setCopy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<NleResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const go = async () => {
    if (!client) return;
    setBusy(true);
    setErr(null);
    try {
      const opts = { media: copy ? ('copy' as const) : ('link' as const), to_app: IN_APP.includes(fmt) };
      setRes(clip ? await client.exportNle(item, clip, fmt, opts) : await client.exportNleAll(item, fmt, opts));
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  };
  const app = nleApp(fmt);
  const inApp = res ? (res.in_app ?? res.outputs?.some((x) => x.in_app) ?? false) : false;
  const where = res ? (res.main ?? res.outputs?.[0]?.main ?? res.dir) : null;
  const notes = res ? noteCount(res) : 0;
  return (
    <Modal title={clip ? t('nle.title') : t('nle.titleAll', { n: count ?? 0 })} onClose={onClose}>
      <div className="col" style={{ gap: 10 }} data-testid="nle-dialog">
        {!res && (
          <>
            <p className="muted" style={{ margin: 0, fontSize: 13 }}>
              {t('nle.lead')}
            </p>
            <div className="col" style={{ gap: 6 }} role="radiogroup">
              {NLE_FORMATS.map((f) => (
                <label key={f} className="row" style={{ gap: 8, cursor: 'pointer', alignItems: 'flex-start' }} data-testid={`nle-fmt-${f}`}>
                  <input type="radio" name="nle-fmt" checked={fmt === f} onChange={() => setFmt(f)} disabled={busy} />
                  <span className="col" style={{ gap: 0 }}>
                    <b style={{ fontWeight: 500 }}>{nleApp(f)}</b>
                    <span className="faint" style={{ fontSize: 12 }}>
                      {tk(`nle.hint.${f}`)}
                    </span>
                  </span>
                </label>
              ))}
            </div>
            <label className="row" style={{ gap: 8, fontSize: 12.5, cursor: 'pointer' }}>
              <input type="checkbox" checked={copy} onChange={(e) => setCopy(e.target.checked)} disabled={busy} data-testid="nle-copy" />
              <span>{t('nle.copy')}</span>
            </label>
            {err && (
              <span className="err" style={{ fontSize: 12.5 }} data-testid="nle-error">
                {err}
              </span>
            )}
            <div className="row" style={{ justifyContent: 'flex-end', gap: 8 }}>
              <button className="btn ghost" onClick={onClose}>
                {t('common.cancel')}
              </button>
              <button className="btn primary" disabled={busy || !client} onClick={() => void go()} data-testid="nle-go">
                {busy ? t('nle.busy') : t('nle.go')}
              </button>
            </div>
          </>
        )}
        {res && (
          <>
            <b style={{ fontWeight: 500 }} data-testid="nle-done">
              {t('nle.done', { app })}
            </b>
            {IN_APP.includes(fmt) && <span className="muted" style={{ fontSize: 12.5 }}>{inApp ? t('nle.inApp', { app }) : t('nle.notInApp', { app })}</span>}
            {where && (
              <span className="faint" style={{ fontSize: 12, wordBreak: 'break-all' }} data-content>
                {where}
              </span>
            )}
            {notes > 0 && <span className="muted" style={{ fontSize: 12.5 }}>{t('nle.notes', { n: notes })}</span>}
            {!!res.failed?.length && (
              <span className="err" style={{ fontSize: 12.5 }}>
                {t('nle.failed', { n: res.failed.length, why: res.failed[0].error })}
              </span>
            )}
            <div className="row" style={{ justifyContent: 'flex-end', gap: 8 }}>
              {where && (
                <button className="btn" onClick={() => void window.desk.showItem(where)} data-testid="nle-reveal">
                  <FolderOpen className="ico" />
                  {t('c.reveal')}
                </button>
              )}
              <button className="btn primary" onClick={onClose}>
                {t('ce.done')}
              </button>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
