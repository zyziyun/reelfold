// An imported clip's own section on its page (and in the editor's inspector): the footage linked and whether its
// shots were found in it, the shots with another take for any of them (a still of each take; picking one is a
// shot_swap edit, undoable like every edit), a version in another language (export_add with lang: translated,
// voiced again, captioned), and "Rewrite post copy" for a video made elsewhere.
import { useCallback, useEffect, useState } from 'react';
import { Check, FolderPlus, Languages, Loader2, RefreshCw, RotateCcw, Sparkles } from 'lucide-react';
import type { ImportInfoClip, ImportTakes } from '../../../../shared/imports';
import type { EditOp, OutputDoc } from '../../../../shared/v04';
import type { StripInfo } from '../../../../shared/timeline';
import { t, type MessageKey } from '../../i18n';
import { useEngine } from '../../lib/engine';
import { platformName } from '../../lib/platformName';
import { media } from '../kit';
import { errText } from '../msg';
import { useUi } from '../ui';
import './imports.css';

type EditFn = (ops: EditOp[], undoToast?: boolean) => Promise<boolean>;

const LANGS = ['en', 'zh', 'fr', 'es', 'ja', 'ko', 'de', 'pt'] as const;
const TARGETS = ['youtube', 'youtube-shorts', 'tiktok', 'instagram', 'xiaohongshu', 'douyin', 'bilibili'] as const;

/** The import's state for this clip (footage, shot match), refreshed on its events. */
function useImportClip(item: string, clip: string): { c: ImportInfoClip | null; reload: () => void } {
  const { client, subscribe } = useEngine();
  const [c, setC] = useState<ImportInfoClip | null>(null);
  const [n, setN] = useState(0);
  const reload = useCallback(() => setN((x) => x + 1), []);
  useEffect(() => {
    if (!client) return;
    let alive = true;
    client
      .importInfo(item)
      .then((r) => alive && setC(r.clips.find((x) => x.id === clip) ?? null))
      .catch(() => alive && setC(null));
    return () => {
      alive = false;
    };
  }, [client, item, clip, n]);
  useEffect(
    () =>
      subscribe((e) => {
        if (e.type === 'import-match' && e.item === item && e.clip === clip) {
          setC((cur) => (cur ? { ...cur, match: { ...cur.match, state: e.state, progress: e.progress, matched: e.matched ?? cur.match.matched, shots: e.shots ?? cur.match.shots } } : cur));
          if (e.state !== 'running') reload();
        }
        if (e.type === 'import-copy' && e.item === item && e.clip === clip) setC((cur) => (cur ? { ...cur, copy: e.state } : cur));
      }),
    [subscribe, item, clip, reload],
  );
  return { c, reload };
}

function Tile({ strip, at, w = 46 }: { strip: StripInfo; at: number; w?: number }) {
  const [tw, th] = strip.tile;
  const h = Math.round((w * th) / tw);
  const i = Math.max(0, Math.min(strip.n - 1, Math.round(at / strip.interval)));
  const sc = w / tw;
  return (
    <span
      className="ci-tile"
      style={{
        width: w,
        height: h,
        backgroundImage: `url("${media(strip.sprite)}")`,
        backgroundSize: `${strip.cols * tw * sc}px ${strip.rows * th * sc}px`,
        backgroundPosition: `-${(i % strip.cols) * tw * sc}px -${Math.floor(i / strip.cols) * th * sc}px`,
      }}
    />
  );
}

export function ClipImported({ doc, item, clip, strip, edit, onSeek }: { doc: OutputDoc; item: string; clip: string; strip: StripInfo | null; edit: EditFn; onSeek?: (t: number) => void }) {
  const { client } = useEngine();
  const ui = useUi();
  const { c, reload } = useImportClip(item, clip);
  const [open, setOpen] = useState<number | null>(null);
  const [takes, setTakes] = useState<ImportTakes | null>(null);
  const [lang, setLang] = useState<string>(() => (/[一-鿿]/.test(doc.title) ? 'en' : 'zh'));
  const [target, setTarget] = useState<string>(() => (/[一-鿿]/.test(doc.title) ? 'youtube' : 'xiaohongshu'));
  const [making, setMaking] = useState(false);
  const imp = doc.imported;
  useEffect(() => {
    setOpen(null);
    setTakes(null);
  }, [item, clip]);
  if (!imp) return null;
  const shots = imp.shots ?? [];
  const m = c?.match;
  const link = async () => {
    const d = await window.desk.openFolder();
    if (!d || !client) return;
    try {
      await client.importLink(item, clip, [d]);
      reload();
    } catch (e) {
      ui.toast(errText(e), { error: true });
    }
  };
  const showTakes = async (i: number) => {
    if (open === i) return setOpen(null);
    setOpen(i);
    setTakes(null);
    onSeek?.(shots[i].start);
    try {
      setTakes(await client!.importTakes(item, clip, i));
    } catch (e) {
      ui.toast(errText(e), { error: true });
      setOpen(null);
    }
  };
  const use = async (i: number, source?: string, at?: number) => {
    const ok = await edit([(source == null ? { op: 'shot_swap', shot: i, restore: true } : { op: 'shot_swap', shot: i, source, t: at }) as EditOp], true);
    if (ok) setOpen(null);
  };
  const makeLang = async () => {
    setMaking(true);
    try {
      await edit([{ op: 'export_add', target, lang } as EditOp], true);
    } finally {
      setMaking(false);
    }
  };
  const langs = doc.exports.filter((e) => e.lang);
  return (
    <div className="ci-sec im-sec" data-testid="ci-imported" data-match={m?.state ?? ''}>
      <span className="ci-lbl">{t('im.sec')}</span>
      <div className="im-status">
        {!imp.sources.length ? (
          <span className="ci-note" data-testid="im-no-footage">
            <span>{t('im.noFootage')}</span>
          </span>
        ) : m?.state === 'running' ? (
          <span className="ci-render running" data-testid="im-matching">
            <Loader2 className="ico spin" />
            {t('im.matching', { p: Math.round((m.progress ?? 0) * 100) })}
          </span>
        ) : shots.length ? (
          <span className="im-ok" data-testid="im-matched">
            <Check className="ico" />
            {t('im.matched', { m: shots.filter((s) => s.source).length, n: shots.length })}
          </span>
        ) : (
          <span className="im-row">
            <span className="ci-note">
              <span>{m?.state === 'failed' ? t('im.matchFailed') : t('im.notMatched')}</span>
            </span>
            <button className="btn ghost sm" onClick={() => void client?.importMatch(item, clip).then(reload)} data-testid="im-match">
              <RefreshCw className="ico" />
              {t('im.matchNow')}
            </button>
          </span>
        )}
        <button className="btn ghost sm" onClick={() => void link()} data-tip={t('im.footageTip')} data-testid="im-link">
          <FolderPlus className="ico" />
          {t('im.linkFootage')}
        </button>
      </div>
      {shots.length > 0 && (
        <>
          <span className="ci-lbl">{t('im.shots')}</span>
          <div className="im-shots" data-testid="im-shots">
            {shots.map((s) => (
              <button key={s.i} className={`im-shot ${s.swap ? 'swapped' : ''} ${open === s.i ? 'on' : ''}`} disabled={!s.source && !shots.some((x) => x.source)} onClick={() => void showTakes(s.i)} title={`${t('im.shot', { n: s.i + 1 })} · ${s.start.toFixed(1)}–${s.end.toFixed(1)} s`} data-testid="im-shot" data-shot={s.i} data-swapped={s.swap ? '1' : undefined}>
                {strip?.sprite ? <Tile strip={strip} at={(s.start + s.end) / 2} /> : <span className="im-n">{s.i + 1}</span>}
                {s.swap && <i className="im-dot" />}
              </button>
            ))}
          </div>
          {open != null && (
            <div className="im-takes" data-testid="im-takes">
              <span className="ci-lbl">{t('im.otherTakes', { n: open + 1 })}</span>
              {!takes ? (
                <Loader2 className="ico spin" />
              ) : (
                <div className="im-take-row">
                  {shots[open].swap && takes.original && (
                    <button className="im-take" onClick={() => void use(open)} data-testid="im-take-original">
                      {takes.original.still && <img src={media(takes.original.still)} alt="" />}
                      <span>
                        <RotateCcw className="ico" />
                        {t('im.original')}
                      </span>
                    </button>
                  )}
                  {takes.takes.map((k) => (
                    <button key={`${k.source}@${k.t}`} className="im-take" onClick={() => void use(open, k.source, k.t)} title={`${k.name} · ${k.t.toFixed(1)} s`} data-testid="im-take">
                      {k.still && <img src={media(k.still)} alt="" />}
                      <span>{t(`im.take.${k.why}` as MessageKey)}</span>
                    </button>
                  ))}
                  {!takes.takes.length && <p className="ci-note">{t('im.noTakes')}</p>}
                </div>
              )}
            </div>
          )}
        </>
      )}
      <span className="ci-lbl" data-tip={t('im.langTip')}>
        {t('im.lang')}
      </span>
      {langs.length > 0 && (
        <div className="ci-chips" data-testid="im-langs">
          {langs.map((e) => (
            <span key={e.target} className="ci-chip on" data-testid="im-lang-version">
              <Languages className="ico" />
              {t(`im.lang.${e.lang}` as MessageKey)} · {platformName(e.target)}
            </span>
          ))}
        </div>
      )}
      <div className="im-row im-lang">
        <select value={lang} onChange={(e) => setLang(e.target.value)} aria-label={t('im.lang')} data-testid="im-lang">
          {LANGS.map((l) => (
            <option key={l} value={l}>
              {t(`im.lang.${l}` as MessageKey)}
            </option>
          ))}
        </select>
        <span className="muted">{t('im.langFor')}</span>
        <select value={target} onChange={(e) => setTarget(e.target.value)} aria-label={t('im.langFor')} data-testid="im-lang-target">
          {TARGETS.map((x) => (
            <option key={x} value={x}>
              {platformName(x)}
            </option>
          ))}
        </select>
        <button className="btn ghost sm" disabled={making || doc.caps.export === false} onClick={() => void makeLang()} data-testid="im-lang-make">
          {making ? <Loader2 className="ico spin" /> : <Sparkles className="ico" />}
          {t('im.langMake')}
        </button>
      </div>
    </div>
  );
}

/** "Rewrite post copy" for a video made elsewhere: every version's copy written again (the engine's post copy). */
export function ImportCopyRewrite({ item, clip, onDone }: { item: string; clip: string; onDone?: () => void }) {
  const { client, subscribe } = useEngine();
  const ui = useUi();
  const [busy, setBusy] = useState(false);
  useEffect(
    () =>
      subscribe((e) => {
        if (e.type !== 'import-copy' || e.item !== item || e.clip !== clip || e.state === 'running') return;
        setBusy(false);
        if (e.state === 'done') {
          ui.toast(t('ci.copy.done'));
          onDone?.();
        } else ui.toast(e.error || t('im.failed'), { error: true });
      }),
    [subscribe, item, clip, ui, onDone],
  );
  return (
    <div className="ci-copyre" data-testid="ci-copy" data-imported="1">
      <button
        className="btn ghost sm"
        disabled={busy}
        onClick={() => {
          setBusy(true);
          client?.importCopy(item, clip).catch((e) => (setBusy(false), ui.toast(errText(e), { error: true })));
        }}
        data-tip={t('ci.copy.tip')}
        data-testid="ci-copy-rewrite"
      >
        {busy ? <Loader2 className="ico spin" /> : <RefreshCw className="ico" />}
        {busy ? t('ci.copy.writing') : t('ci.copy.rewrite')}
      </button>
    </div>
  );
}
