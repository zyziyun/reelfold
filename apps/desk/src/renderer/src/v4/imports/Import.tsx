// Import finished videos (and their footage) for second-pass editing: one dialog, opened from the composer (its hint
// when what was dropped is finished videos, or its ··· menu), from File › Import Finished Video… and from any code
// through ``openImport``. It shows what the engine found - clips, their platform versions, covers, post copy, the
// footage that goes with them - lets her link a footage folder, imports (the engine copies; her files stay as they
// are) and opens the editor on the first clip.
import { useEffect, useRef, useState } from 'react';
import { Check, Clapperboard, FileText, Film, FolderPlus, Image as ImageIcon, Loader2 } from 'lucide-react';
import type { ImportCheck } from '../../../../shared/imports';
import type { EngineMsg } from '../../../../shared/v04';
import { IS_LITE } from '../../../../shared/edition';
import { t } from '../../i18n';
import { useEngine } from '../../lib/engine';
import { useHistory } from '../../lib/history';
import { platformName } from '../../lib/platformName';
import { href } from '../../lib/router';
import { Modal } from '../../components/ui';
import { media } from '../kit';
import { emsg, errText } from '../msg';
import { PlatformIcon } from '../PlatformIcon';
import { useUi } from '../ui';
import './imports.css';

const EVENT = 'reelfold:import';

/** Open the import dialog on these files / folders (finished videos; footage among them is linked). */
export function openImport(paths: string[], sources: string[] = []) {
  window.dispatchEvent(new CustomEvent(EVENT, { detail: { paths, sources } }));
}

/** Pick finished videos (files or folders) and open the import dialog on them. */
export async function pickImport() {
  const got = await window.desk.openFiles('video');
  if (got.length) openImport(got);
}

/** Mounted once: the dialog, whoever asks for it (openImport, the app menu's File › Import Finished Video…). */
export function ImportHost() {
  const [req, setReq] = useState<{ paths: string[]; sources: string[]; n: number } | null>(null);
  useEffect(() => {
    const on = (e: Event) => {
      const d = (e as CustomEvent<{ paths: string[]; sources?: string[] }>).detail;
      if (d?.paths?.length) setReq({ paths: d.paths, sources: d.sources ?? [], n: Date.now() });
    };
    window.addEventListener(EVENT, on);
    const off = window.desk.on?.('import:open', (d) => {
      const p = (d as { paths?: string[] } | null)?.paths ?? [];
      if (p.length) setReq({ paths: p, sources: [], n: Date.now() });
    });
    return () => {
      window.removeEventListener(EVENT, on);
      off?.();
    };
  }, []);
  if (!req) return null;
  return <ImportDialog key={req.n} paths={req.paths} sources={req.sources} onClose={() => setReq(null)} />;
}

const base = (p: string) => p.replace(/[\\/]+$/, '').split(/[\\/]/).pop() ?? p;

export function ImportDialog({ paths, sources: initial, onClose }: { paths: string[]; sources: string[]; onClose: () => void }) {
  const { client, subscribe } = useEngine();
  const ui = useUi();
  const { reload } = useHistory();
  const [sources, setSources] = useState<string[]>(initial);
  const [check, setCheck] = useState<ImportCheck | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<{ id: string; progress: number } | null>(null);
  const jobRef = useRef<string | null>(null);

  useEffect(() => {
    if (!client) return;
    let alive = true;
    setCheck(null);
    setError(null);
    if (IS_LITE) void window.desk.grantAccess?.([...paths, ...sources]).catch(() => undefined);
    client
      .importCheck([...paths, ...sources])
      .then((r) => alive && setCheck(r))
      .catch((e) => alive && setError(errText(e)));
    return () => {
      alive = false;
    };
  }, [client, paths, sources]);

  useEffect(
    () =>
      subscribe((e) => {
        if (e.type !== 'import' || e.job !== jobRef.current) return;
        if (e.state === 'copying') setJob({ id: e.job, progress: e.progress ?? 0 });
        if (e.state === 'failed') {
          setJob(null);
          jobRef.current = null;
          setError(e.error?.code ? emsg({ code: e.error.code, params: {}, message: e.error.message ?? t('im.failed') } as EngineMsg) : t('im.failed'));
        }
        if (e.state === 'done' && e.item && e.clip) {
          reload();
          ui.toast(t('im.done', { name: check?.clips[0]?.title ?? base(paths[0]) }));
          location.hash = href({ name: 'clip', id: e.item, clip: e.clip });
          onClose();
        }
      }),
    [subscribe, reload, ui, check, paths, onClose],
  );

  const link = async () => {
    const d = await window.desk.openFolder();
    if (d) setSources((s) => [...new Set([...s, d])]);
  };
  const go = async () => {
    if (!client || !check) return;
    try {
      const r = await client.importStart(paths, sources);
      jobRef.current = r.job;
      setJob({ id: r.job, progress: 0 });
    } catch (e) {
      setError(errText(e));
    }
  };
  const nFootage = check ? check.counts.raw : 0;
  const can = !!check && check.clips.length > 0 && !job;
  return (
    <Modal title={t('im.title')} onClose={job ? () => undefined : onClose}>
      <div className="im-dlg" data-testid="import-dialog" data-verdict={check?.verdict ?? ''}>
        {!check && !error && (
          <p className="im-wait">
            <Loader2 className="ico spin" />
            {t('im.checking')}
          </p>
        )}
        {error && (
          <p className="im-err" data-testid="import-error">
            {error}
          </p>
        )}
        {check && !check.clips.length && <p className="im-note">{t('im.noFinished')}</p>}
        {check && check.clips.length > 0 && (
          <>
            <p className="im-sum" data-testid="import-summary">
              <Film className="ico" />
              {t('im.summary', { n: check.counts.finished, c: check.clips.length })}
            </p>
            <ul className="im-clips">
              {check.clips.slice(0, 8).map((c) => (
                <li key={c.key} data-testid="import-clip">
                  <span className="im-thumb">{c.versions.find((v) => v.cover)?.cover ? <img src={media(c.versions.find((v) => v.cover)!.cover!)} alt="" /> : <Clapperboard className="ico" />}</span>
                  <span className="im-main">
                    <span className="im-t clamp1">{c.title}</span>
                    <span className="im-vers">
                      {c.versions.map((v) => (
                        <span key={v.file} className="im-ver" title={v.file} data-testid="import-version" data-platform={v.platform ?? ''}>
                          {v.platform ? <PlatformIcon id={v.platform} size={12} /> : null}
                          {v.platform ? platformName(v.platform) : base(v.file)}
                          {v.aspect ? <i>{v.aspect}</i> : null}
                          {v.cover ? <ImageIcon className="ico" aria-label={t('im.cover')} /> : null}
                          {v.post ? <FileText className="ico" aria-label={t('im.post')} /> : null}
                        </span>
                      ))}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
            {check.clips.length > 1 && <p className="im-note">{t('im.group', { n: check.clips.length })}</p>}
            <div className="im-foot-row" data-tip={t('im.footageTip')}>
              <span data-testid="import-footage" data-n={nFootage}>
                {nFootage ? <Check className="ico ok" /> : null}
                {t('im.footage', { n: nFootage })}
              </span>
              <button className="btn ghost sm" onClick={() => void link()} disabled={!!job} data-testid="import-link">
                <FolderPlus className="ico" />
                {t('im.linkFootage')}
              </button>
            </div>
            <p className="im-note">{t('im.originals')}</p>
          </>
        )}
        <div className="im-btns">
          {job ? (
            <span className="ci-render running" data-testid="import-progress">
              <Loader2 className="ico spin" />
              {t('im.copying', { p: Math.round(job.progress * 100) })}
            </span>
          ) : (
            <button className="btn ghost" onClick={onClose} data-testid="import-cancel">
              {t('im.cancel')}
            </button>
          )}
          <button className="btn primary" disabled={!can} onClick={() => void go()} data-testid="import-go">
            {t('im.go')}
          </button>
        </div>
      </div>
    </Modal>
  );
}

/** The composer's hint: what she dropped looks like finished videos -> import them to edit (debounced check). */
export function useImportHint(files: string[]): ImportCheck | null {
  const { client } = useEngine();
  const [hint, setHint] = useState<ImportCheck | null>(null);
  const key = files.join('\n');
  useEffect(() => {
    setHint(null);
    if (!client || !files.length || !files.some((f) => /\.(mp4|mov|m4v|mkv|webm)$/i.test(f) || !/\.[a-z0-9]{2,4}$/i.test(f))) return;
    let alive = true;
    const tm = window.setTimeout(() => {
      client
        .importCheck(files)
        .then((r) => alive && setHint(r.clips.length && (r.verdict === 'finished' || r.verdict === 'mixed') ? r : null))
        .catch(() => undefined);
    }, 400);
    return () => {
      alive = false;
      window.clearTimeout(tm);
    };
  }, [client, key]); // eslint-disable-line react-hooks/exhaustive-deps
  return hint;
}
