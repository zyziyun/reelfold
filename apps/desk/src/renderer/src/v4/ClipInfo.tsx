// A clip's info where the clip is (2026-10 review step 5): cover choices, caption style, versions, the copy per
// platform and when it goes out - in the editor's inspector (layout B) and placed one by one on the Studio's clip page
// (layout A). The copy and the schedule are the publish drawer's own component and calendar rows (PostCopy); cover
// and caption changes re-render the clip in the background (useAutoRender), with the progress shown here.
import { postDelivered } from '../../../shared/publish/apiPlatforms';
import { StatusMark } from '../publish/Board';
import { useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, CalendarClock, CalendarDays, Check, Clock, Loader2, Plus, RefreshCw, Sparkles } from 'lucide-react';
import type { AutopilotChoice, AutopilotDoc, ClipFile, EditOp, OutputDoc } from '../../../shared/v04';
import type { PilotFailure } from '../../../shared/v02';
import type { StripInfo } from '../../../shared/timeline';
import { fmtDate, fmtList, getLang, t, type MessageKey } from '../i18n';
import { useEngine } from '../lib/engine';
import { nextFreeDay } from '../lib/nextSlot';
import { versionFor } from '../lib/versions';
import type { RenderState } from '../lib/autoRender';
import { href } from '../lib/router';
import { useChannels, useChosenPlatforms } from './Channels';
import { platformName } from './Home';
import { media } from './kit';
import { PlatformIcon } from './PlatformIcon';
import { errText } from './msg';
import { FailureActions, failureReason } from './Failure';
import { useUi } from './ui';
import { base, groupPosts, iso, sortIds } from '../publish/model';
import { firstTab, PostCopy, type Row } from '../publish/PostCopy';
import { useAccounts, usePublishData } from '../publish/usePublish';
import '../publish/publish.css';
import './clipinfo.css';
import { useResizeChoice } from './ResizeChoice';
import { ClipImported, ImportCopyRewrite } from './imports/ClipImported';

type EditFn = (ops: EditOp[], undoToast?: boolean) => Promise<boolean>;

// ---------------------------------------------------------------- cover
/** Frames to choose a cover from: spread over the clip (the sprite's tiles; no extra work). */
export function coverTimes(duration: number, n = 5): number[] {
  if (!duration) return [];
  return Array.from({ length: n }, (_, k) => Math.round(((duration * (k + 0.5)) / n) * 100) / 100);
}

function Tile({ strip, at, w = 34 }: { strip: StripInfo; at: number; w?: number }) {
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

export function ClipCovers({ doc, strip, time, edit }: { doc: OutputDoc; strip: StripInfo | null; time: number; edit: EditFn }) {
  if (doc.caps.cover === false) return null;
  const cur = doc.cover_edit?.t;
  const text = doc.cover_edit?.text ?? doc.title;
  const pick = (at: number) => void edit([{ op: 'cover', t: Math.round(at * 100) / 100, text, style: 'card' } as EditOp], true);
  const times = coverTimes(doc.duration);
  return (
    <div className="ci-covers" data-testid="ci-covers">
      {doc.cover && (
        <span className={`ci-cover on`} title={t('ci.coverNow')}>
          <img src={media(doc.cover, doc.cover_v)} alt="" />
        </span>
      )}
      {strip?.sprite
        ? times.map((at) => (
            <button key={at} className={`ci-cover ${cur != null && Math.abs(cur - at) < 0.3 ? 'on' : ''}`} onClick={() => pick(at)} aria-label={t('ci.coverAt', { s: at.toFixed(1) })} data-testid="ci-cover">
              <Tile strip={strip} at={at} />
            </button>
          ))
        : null}
      <button className="ci-cover here" onClick={() => pick(time)} data-tip={t('ci.coverHere')} aria-label={t('ci.coverHere')} data-testid="ci-cover-here">
        <Plus className="ico" />
      </button>
    </div>
  );
}

// ---------------------------------------------------------------- captions
type Look = 'clean' | 'bold' | 'box';
const LOOKS: Record<Look, Record<string, unknown>> = {
  clean: { box: false, stroke: 0.03 },
  bold: { box: false, stroke: 0.12, stroke_color: '#000000' },
  box: { box: true, box_color: '#000000', stroke: 0 },
};
export function lookOf(s: Record<string, unknown> | null | undefined): Look {
  if (s?.box) return 'box';
  return typeof s?.stroke === 'number' && s.stroke >= 0.08 ? 'bold' : 'clean';
}
const POS = ['bottom', 'middle', 'top'] as const;

export function CaptionLooks({ doc, edit }: { doc: OutputDoc; edit: EditFn }) {
  const can = doc.caps.caption_style !== false && (!!doc.caps.captions_ours || doc.captions.some((c) => c.added));
  if (!can) return <p className="ci-note" data-testid="ci-caps-burned">{t('ci.capsBurned')}</p>;
  const s = (doc.caption_style ?? {}) as Record<string, unknown>;
  const look = lookOf(s);
  const pos = (s.position as string) ?? 'bottom';
  const kw = !!s.highlight && s.highlight !== s.color;
  const set = (style: Record<string, unknown>) => void edit([{ op: 'caption_style', style } as EditOp]);
  return (
    <div className="ci-chips" data-testid="ci-captions">
      {(Object.keys(LOOKS) as Look[]).map((k) => (
        <button key={k} className={`ci-chip ${look === k ? 'on' : ''}`} aria-pressed={look === k} onClick={() => look !== k && set(LOOKS[k])} data-testid={`ci-look-${k}`}>
          {t(`ci.look.${k}` as MessageKey)}
        </button>
      ))}
      <button className="ci-chip" onClick={() => set({ position: POS[(POS.indexOf(pos as (typeof POS)[number]) + 1) % POS.length] })} data-testid="ci-pos">
        {t('ci.pos', { p: t(`editor.pos.${POS.includes(pos as (typeof POS)[number]) ? pos : 'bottom'}` as MessageKey) })}
      </button>
      <button className={`ci-chip ${kw ? 'on' : ''}`} aria-pressed={kw} onClick={() => set({ highlight: kw ? ((s.color as string) ?? '#FFFFFF') : '#FFD60A' })} data-testid="ci-keywords">
        <i className="ci-sw" style={{ background: kw ? (s.highlight as string) : 'transparent' }} />
        {t('ci.keywords')}
      </button>
    </div>
  );
}

// ---------------------------------------------------------------- versions
export const VERSIONS = ['9:16', '16:9', '3:4'] as const; // international first
export const ASPECT_TARGET: Record<string, string> = { '3:4': 'xiaohongshu:vertical', '9:16': 'douyin:vertical', '16:9': 'youtube:horizontal' };

/** The shapes each platform takes: a clip made for some platforms offers only their shapes as versions. */
const PLATFORM_SHAPES: Record<string, string[]> = {
  youtube: ['16:9'], 'youtube-shorts': ['9:16'], tiktok: ['9:16'], douyin: ['9:16'], instagram: ['9:16'], kuaishou: ['9:16'],
  'wechat-channels': ['9:16'], xiaohongshu: ['3:4', '9:16'], bilibili: ['16:9'], x: ['16:9'], facebook: ['16:9'], linkedin: ['16:9'],
};

export function versionsFor(targets: string[] | null | undefined): readonly string[] {
  const ts = (targets ?? []).map((x) => x.split(':')[0]);
  if (!ts.length || ts.some((x) => !PLATFORM_SHAPES[x])) return VERSIONS;
  const want = new Set(ts.flatMap((x) => PLATFORM_SHAPES[x]));
  return VERSIONS.filter((v) => want.has(v));
}

export function ClipVersions({ doc, edit }: { doc: OutputDoc; edit: EditFn }) {
  const orig = new Set(doc.files.map((f) => f.aspect));
  // the shapes of the platforms it is made for (a goal video's English cut: YouTube's 16:9), plus what it already has
  // the engine keeps an export by its platform target (3:4 -> xiaohongshu:vertical): the chip is on either way
  const added = new Set(doc.exports.flatMap((e) => [e.target, ...Object.entries(ASPECT_TARGET).filter(([, x]) => x === e.target).map(([a]) => a)]));
  const resize = useResizeChoice(doc, edit);
  return (
    <div className="ci-chips" data-testid="ci-versions">
      {resize.dialog}
      {VERSIONS.map((v) => {
        const own = orig.has(v);
        const on = own || added.has(v);
        return (
          <button
            key={v}
            className={`ci-chip ${on ? 'on' : ''}`}
            aria-pressed={on}
            disabled={own || doc.caps.export === false}
            title={own ? t('ci.vOwn') : undefined}
            onClick={() => on ? void edit([{ op: 'export_remove', target: v }] as EditOp[], true) : resize.choose(v)}
            data-testid={`ci-version-${v}`}
          >
            {on && <Check className="ico" />}
            {t(`ci.v.${v}` as MessageKey)}
          </button>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------- landscape on vertical screens + the post copy
/** The framing of a clip made from landscape footage (the vlog's ``framing``: follow the subject / fill with blur),
 * whoever chose it - the engine, her, or what a project made before the recipe asked has in its exports (``by:
 * before``). Changing it makes only the vertical versions again (``remake``). */
export function framingOf(doc: Pick<AutopilotDoc, 'decisions' | 'choices'> | null, clip: string): { checkpoint: string; item: string; choice: string; options: string[] } | null {
  const c = (doc?.choices ?? []).find((x) => x.kind === 'reframe-pick' && mineItem(x.item, clip));
  if (c) return { checkpoint: c.checkpoint, item: c.item, choice: c.choice === 'blur' ? 'blur' : 'follow', options: c.options?.length ? c.options : [...FILLS] };
  const d = (doc?.decisions ?? []).find((x) => x.kind === 'reframe-pick' && !x.asked && mineItem(x.item, clip));
  return d ? { checkpoint: d.checkpoint, item: d.item, choice: d.params?.choice === 'blur' ? 'blur' : 'follow', options: [...FILLS] } : null;
}

/** The post copy step of a finished clip (the vlog's ``copy``), also on a project made before it existed (never
 * written: ``choice`` null) - what "Rewrite post copy" makes again. */
export function copyOf(doc: Pick<AutopilotDoc, 'choices'> | null, clip: string): { checkpoint: string; item: string; choice: string | null } | null {
  const c = (doc?.choices ?? []).find((x) => x.kind === 'copy-pick' && mineItem(x.item, clip));
  return c ? { checkpoint: c.checkpoint, item: c.item, choice: c.choice } : null;
}

const mineItem = (it: string, clip: string) => it === clip || clip.startsWith(`${it}/`);
const FILLS = ['follow', 'blur'] as const; // the engine's option order (vstudio.project.adapters.vlog.FILLS)

/** The clip's project settings (its autopilot doc), refreshed on the bus; ``pending`` is the setting she just asked to
 * make again, until the background remake has finished (``onDone`` then). */
function useClipSettings(item: string, onDone?: (what: string, doc: AutopilotDoc) => void) {
  const { client, subscribe } = useEngine();
  const ui = useUi();
  const [doc, setDoc] = useState<AutopilotDoc | null>(null);
  const [n, setN] = useState(0);
  const [pending, setPending] = useState<string | null>(null);
  const evt = useRef(0);
  const seen = useRef(0);
  // reloads in order; ``after``: only a reload that started once the remake call returned can end it (a reload sent
  // before the run started - an event's, while the call was on its way - still says "nothing running")
  const req = useRef(0);
  const after = useRef(0);
  useEffect(() => {
    if (!client) return;
    let alive = true;
    const at = evt.current;
    const no = ++req.current;
    client
      .autopilot(item)
      .then((d) => {
        if (!alive) return;
        setDoc(d);
        // finished: a reload after the engine said something happened (the run ended), with nothing running
        if (!d.running && !d.queued && at > seen.current && no > after.current) {
          seen.current = at;
          setPending((p) => {
            if (p) onDone?.(p, d);
            return null;
          });
        }
      })
      .catch(() => alive && setDoc(null));
    return () => {
      alive = false;
    };
  }, [client, item, n]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(
    () =>
      subscribe((e) => {
        if (e.type === 'inbox' || e.type === 'batches') {
          evt.current += 1;
          setN((x) => x + 1);
        }
      }),
    [subscribe],
  );
  const remake = async (sub: string, todo: Record<string, string | null>, what: string) => {
    if (!client || pending) return false;
    if (doc?.running || doc?.queued) {
      ui.toast(t('hub.changeBusy'));
      return false;
    }
    setPending(what);
    after.current = Number.MAX_SAFE_INTEGER;
    try {
      await client.autopilotRemake(item, sub, todo);
      after.current = req.current;
      // the run is started (or in line) when the call returns: the next reload that finds nothing running ends it -
      // also a remake that failed at once (no model: the visuals are not drawn), before any later event came
      seen.current = evt.current - 1;
      setN((x) => x + 1);
      return true;
    } catch (e) {
      after.current = 0;
      setPending(null);
      ui.toast(errText(e), { error: true });
      return false;
    }
  };
  return { doc, pending, remake, busy: !!pending || !!doc?.running };
}

/** ``onRemade``: the vertical version was made again (its file replaced in place) - the page reloads the clip, so
 * the player loads the new file under its new version. */
export function ClipFill({ item, clip, onRemade }: { item: string; clip: string; onRemade?: () => void }) {
  const [mine, setMine] = useState<string | null>(null);
  const s = useClipSettings(item, () => (setMine(null), onRemade?.()));
  useEffect(() => setMine(null), [item, clip]);
  const f = framingOf(s.doc, clip);
  if (!f) return null;
  const cur = mine ?? f.choice;
  const making = s.pending === 'framing';
  const pick = async (k: (typeof FILLS)[number]) => {
    if (k === cur || s.busy || !f.options.includes(k)) return;
    if (await s.remake(f.item, { [f.checkpoint]: k }, 'framing')) setMine(k);
  };
  return (
    <div className="ci-sec" data-testid="ci-fill" data-choice={cur} data-busy={making ? '1' : undefined}>
      <span className="ci-lbl" data-tip={t('ci.fill.tip')}>
        {t('ci.fill')}
      </span>
      <div className="ci-chips">
        {FILLS.map((k) => (
          <button key={k} className={`ci-chip ${cur === k ? 'on' : ''}`} aria-pressed={cur === k} disabled={s.busy} onClick={() => void pick(k)} data-testid={`ci-fill-${k}`}>
            {cur === k && <Check className="ico" />}
            {t(`ci.fill.${k}` as MessageKey)}
          </button>
        ))}
      </div>
      {making && (
        <span className="ci-render running" data-testid="ci-fill-making">
          <Loader2 className="ico spin" />
          {t('ci.fill.making')}
        </span>
      )}
    </div>
  );
}

/** An explainer's visuals (``remake_as: visuals``: its scenes) of this clip, when the engine can draw them again;
 * ``kept``: the scenes the last redo could not draw and kept (as before / as a simple diagram). */
export function visualsOf(
  doc: Pick<AutopilotDoc, 'choices'> | null,
  clip: string,
): { checkpoint: string; item: string; by: string | null; kept: NonNullable<AutopilotChoice['kept']>; total: number | null; missing: boolean } | null {
  const c = (doc?.choices ?? []).find((x) => x.remake_as === 'visuals' && mineItem(x.item, clip));
  return c ? { checkpoint: c.checkpoint, item: c.item, by: c.choice, kept: c.kept ?? [], total: c.total ?? null, missing: (c.options ?? []).includes('missing') } : null;
}

/** The narration voice the casting step picked for this clip (``remake_as: voice``): speaker, its label in the UI's
 * language and the one-line reason; null when the recipe casts no voice (or the clip has none). */
export function voiceOf(
  doc: Pick<AutopilotDoc, 'choices'> | null,
  clip: string,
  zh = false,
): { checkpoint: string; item: string; speaker: string; label: string; reason: string | null; by: string } | null {
  const c = (doc?.choices ?? []).find((x) => x.remake_as === 'voice' && mineItem(x.item, clip));
  if (!c || !c.choice) return null;
  const label = (zh ? c.label_zh : c.label) || c.label || c.choice;
  return { checkpoint: c.checkpoint, item: c.item, speaker: c.choice, label, reason: c.reason ?? null, by: c.by };
}

const VOICE_ASKS = ['ci.voice.male', 'ci.voice.female', 'ci.voice.calmer', 'ci.voice.livelier'] as const;

/** "Voice: Uncle Fu — calm, deep male · why" + a few plain asks (a male voice, calmer ...): the AI casts again for
 * those words and only the voice and the mix are made again (the cut stays). Anything else: say it in the chat. */
export function ClipVoice({ item, clip }: { item: string; clip: string }) {
  const ui = useUi();
  const s = useClipSettings(item, () => ui.toast(t('ci.voice.done')));
  const v = voiceOf(s.doc, clip, getLang() === 'zh-CN');
  if (!v) return null;
  const making = s.pending === 'voice';
  return (
    <div className="ci-sec" data-testid="ci-voice" data-speaker={v.speaker} data-by={v.by}>
      <span className="ci-lbl">{t('ci.voice')}</span>
      <div className="muted small" data-testid="ci-voice-what">
        <b>{v.label}</b>
        {v.reason ? ` — ${v.reason}` : ''}
      </div>
      <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
        {VOICE_ASKS.map((k) => (
          <button key={k} className="btn ghost sm" disabled={s.busy} onClick={() => void s.remake(v.item, { [v.checkpoint]: t(k) }, 'voice')} data-tip={t('ci.voice.tip')} data-testid={`ci-voice-${k.slice(9)}`}>
            {making ? <Loader2 className="ico spin" /> : null}
            {t(k)}
          </button>
        ))}
      </div>
    </div>
  );
}

/** "13 of 14 scenes redrawn; scene 14 kept as before" (pure: unit-tested). */
export function keptNote(kept: NonNullable<AutopilotChoice['kept']>, total: number | null): string {
  if (!kept.length) return '';
  const all = total ?? kept.length;
  const names = (ks: typeof kept) => {
    const ns = ks.map((k) => k.n).sort((a, b) => a - b);
    return ns.length === 1 ? t('ci.visuals.scene', { n: ns[0] }) : t('ci.visuals.scenes', { list: fmtList(ns.map(String)) });
  };
  const before = kept.filter((k) => k.how === 'before');
  const diagram = kept.filter((k) => k.how !== 'before');
  const what = [before.length ? t('ci.visuals.keptBefore', { scenes: names(before) }) : '', diagram.length ? t('ci.visuals.keptDiagram', { scenes: names(diagram) }) : '']
    .filter(Boolean)
    .join(t('ci.visuals.keptSep'));
  return t('ci.visuals.kept', { done: Math.max(0, all - kept.length), total: all, what });
}

/** The visuals' failed redo (the clip's video still stands: a notice here, not Needs you), or null. */
export function visualsFailure(doc: Pick<AutopilotDoc, 'failure' | 'running' | 'queued'> | null, checkpoint: string | undefined): PilotFailure | null {
  const f = doc?.failure;
  if (!f || doc?.running || doc?.queued || !f.remake) return null;
  return !f.stage || f.stage === checkpoint || f.code === 'stage-visuals-failed' || f.code === 'ai-needs-model' ? f : null;
}

/** "Redo the visuals" (an explainer whose scenes came out plain): every scene drawn again by the AI as diagrams and
 * animation, then rendered and exported again - the voice and captions kept. A redo that stopped says which scene
 * and why, with Try again (only the missing scenes are drawn); a redo that kept a scene says so, with "Redraw scene
 * 14" - the clip stays Ready either way (its video stands). */
export function ClipVisualsRedo({ item, clip, onDone, bare }: { item: string; clip: string; onDone?: () => void; bare?: boolean }) {
  const ui = useUi();
  const s = useClipSettings(item, (_w, d) => {
    const v2 = visualsOf(d, clip);
    const f = visualsFailure(d, v2?.checkpoint);
    if (f) ui.toast(visualsFailText(f), { error: true });
    else if (v2?.kept.length) ui.toast(keptNote(v2.kept, v2.total));
    else ui.toast(t('ci.visuals.done'));
    onDone?.();
  });
  const v = visualsOf(s.doc, clip);
  if (!v) return null;
  const making = s.pending === 'visuals';
  const fail = making ? null : visualsFailure(s.doc, v.checkpoint);
  const redo = (choice: string | null) => void s.remake(v.item, { [v.checkpoint]: choice }, 'visuals');
  const btn = (
    <button className={`btn ${bare ? '' : 'ghost sm'}`} disabled={s.busy} onClick={() => redo(null)} data-tip={t('ci.visuals.tip')} data-testid="ci-visuals-redo">
      {making ? <Loader2 className="ico spin" /> : <Sparkles className="ico" />}
      {making ? t('ci.visuals.making') : t('ci.visuals.redo')}
    </button>
  );
  const kept = !making && !fail && v.kept.length ? v.kept : null;
  return (
    <div className={bare ? 'row' : 'ci-sec'} style={bare ? { gap: 8, flexWrap: 'wrap' } : { gap: 8, flexWrap: 'wrap', alignItems: 'center' }} data-testid="ci-visuals" data-by={v.by ?? ''} data-busy={making ? '1' : undefined}>
      {fail ? (
        <div className="ci-note" role="status" data-testid="ci-visuals-failed" data-code={fail.code}>
          <AlertTriangle className="ico" />
          <span>{visualsFailText(fail)}</span>
          {fail.code === 'ai-needs-model' ? (
            <FailureActions item={item} failure={fail} only />
          ) : (
            <button className="btn primary sm" disabled={s.busy} onClick={() => redo(v.missing ? 'missing' : null)} data-testid="ci-visuals-retry">
              <RefreshCw className="ico" />
              {t('fail.retry')}
            </button>
          )}
        </div>
      ) : kept ? (
        <div className="ci-note" role="status" data-testid="ci-visuals-kept">
          <Check className="ico" />
          <span>{keptNote(kept, v.total)}</span>
          <button className="btn sm" disabled={s.busy || !v.missing} onClick={() => redo('missing')} data-testid="ci-visuals-redraw-missing">
            <Sparkles className="ico" />
            {kept.length === 1 ? t('ci.visuals.redrawOne', { n: kept[0].n }) : t('ci.visuals.redrawMany', { n: kept.length })}
          </button>
        </div>
      ) : null}
      {btn}
    </div>
  );
}

function visualsFailText(f: PilotFailure): string {
  return f.code === 'stage-visuals-failed' || f.code === 'ai-needs-model' ? failureReason(f) : t('ci.visuals.failed');
}

/** "Rewrite post copy": every platform's title, text and hashtags written again (the routed AI, else from the facts)
 * and the post text of every version replaced - in the clip's post area. */
export function ClipCopyRewrite({ item, clip, onDone, imported }: { item: string; clip: string; onDone?: () => void; imported?: boolean }) {
  if (imported) return <ImportCopyRewrite item={item} clip={clip} onDone={onDone} />;
  return <ProjectCopyRewrite item={item} clip={clip} onDone={onDone} />;
}

function ProjectCopyRewrite({ item, clip, onDone }: { item: string; clip: string; onDone?: () => void }) {
  const ui = useUi();
  const s = useClipSettings(item, () => {
    ui.toast(t('ci.copy.done'));
    onDone?.();
  });
  const c = copyOf(s.doc, clip);
  if (!c) return null;
  const writing = s.pending === 'copy';
  return (
    <div className="ci-copyre" data-testid="ci-copy" data-written={c.choice ?? 'never'}>
      <button className="btn ghost sm" disabled={s.busy} onClick={() => void s.remake(c.item, { [c.checkpoint]: null }, 'copy')} data-tip={t('ci.copy.tip')} data-testid="ci-copy-rewrite">
        {writing ? <Loader2 className="ico spin" /> : <RefreshCw className="ico" />}
        {writing ? t('ci.copy.writing') : t('ci.copy.rewrite')}
      </button>
    </div>
  );
}

// ---------------------------------------------------------------- the background render
export function RenderPill({ s, onRetry }: { s: RenderState; onRetry?: () => void }) {
  const [clock, setClock] = useState(Date.now());
  useEffect(() => {
    if (s.phase !== 'running') return;
    const timer = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [s.phase]);
  if (s.phase === 'idle') return null;
  const stage = s.stage ? t(`ci.render.${['splice','canvas','timeline','audio','final','frames','cover'].includes(s.stage) ? s.stage : 'prepare'}` as MessageKey) : t('ci.render.prepare');
  return (
    <span className="ci-render-wrap"><span className={`ci-render ${s.phase}`} data-testid="ci-render" data-phase={s.phase}>
      {s.phase === 'done' ? <Check className="ico" /> : s.phase === 'failed' ? <AlertTriangle className="ico" /> : <Loader2 className="ico spin" />}
      {s.phase === 'waiting' && t('ci.r.waiting')}
      {s.phase === 'running' && t('ci.r.running', { p: Math.round(s.progress * 100) })}
      {s.phase === 'done' && t('ci.r.done')}
      {s.phase === 'failed' && t('ci.r.failed')}
      {s.phase === 'failed' && onRetry && (
        <button className="pb-link" onClick={onRetry} data-testid="ci-render-retry">
          <RefreshCw className="ico" />
          {t('ci.r.retry')}
        </button>
      )}
      {s.phase === 'running' && <i className="ci-bar" style={{ width: `${Math.round(s.progress * 100)}%` }} />}
    </span>
    {s.phase === 'running' && <small className="muted" data-testid="ci-render-detail">{stage} · {t('ci.render.version', {n:s.targetIndex ?? 1, total:s.targets ?? 1})} · {Math.max(0, Math.floor((clock - (s.started ?? clock)) / 1000))}s</small>}
    {s.phase === 'failed' && s.error && <small className="muted">{s.error}</small>}
    </span>
  );
}

// ---------------------------------------------------------------- copy + when
/** A clip's calendar rows, its platforms and the next free slot - shared by the post section and the Studio's
 * 「排期发布」 in the page header (one load of the calendar). */
/** ``targets``: the platforms the clip is made for (its project's own, e.g. YouTube for a goal video's English cut):
 * only those are on by default - never every account she has (the English cut is not scheduled to 小红书). */
export function useClipSchedule(item: string, clip: string, targets?: string[] | null) {
  const ui = useUi();
  const { subscribe } = useEngine();
  const { data, actions, client, reload } = usePublishData();
  const { adapters, channels } = useChannels();
  const chosen = useChosenPlatforms();
  const accounts = useAccounts(adapters, channels, chosen);
  useEffect(() => subscribe((e) => (e.type === 'calendar' || (e.type === 'output-edit' && e.item === item && e.clip === clip) ? reload() : undefined)), [subscribe, item, clip]); // eslint-disable-line react-hooks/exhaustive-deps
  const posts = useMemo(() => data?.posts ?? [], [data]);
  const mine = useMemo(() => posts.filter((p) => p.item === item && p.clip === clip), [posts, item, clip]);
  const today = iso(new Date());
  const groups = useMemo(() => groupPosts(mine, accounts.connected), [mine, accounts.connected]);
  const g = groups.find((x) => x.day >= today && x.status !== 'posted') ?? groups[groups.length - 1] ?? null;
  const [offS, setOff] = useState<string[] | null>(null);
  const tkey = (targets ?? []).join();
  const off = useMemo(() => {
    if (offS) return offS;
    const want = new Set((targets ?? []).map(channelOf));
    return want.size ? accounts.connected.filter((pf) => !want.has(channelOf(pf))) : [];
  }, [offS, tkey, accounts.connected]); // eslint-disable-line react-hooks/exhaustive-deps
  const pfs = useMemo(() => accounts.connected.filter((pf) => !off.includes(pf)), [accounts.connected, off]);
  const day = useMemo(() => nextFreeDay(posts, new Date(), pfs.map((pf) => accounts.timeOf(pf))), [posts, pfs, accounts]);
  const rows: Row[] = useMemo(() => (g ? sortIds(g.on.map((p) => base(p.platform))).map((pf) => ({ pf, post: g.on.find((p) => base(p.platform) === pf)! })) : []), [g]);
  const [tab, setTab] = useState('');
  const fmtWhen = (d: string, hm: string) => fmtDate(`${d}T${hm}`, { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
  const when = pfs[0] ? fmtWhen(day, accounts.timeOf(pfs[0])) : '';
  const scheduleNow = () => (pfs.length ? actions.add(pfs.map((pf) => ({ item, clip, platform: pf, at: `${day}T${accounts.timeOf(pf)}` }))) : Promise.resolve(undefined));
  const shorten = async (text: string, platform: string) => {
    try {
      return await client?.shortenCaption({ text, platform });
    } catch (e) {
      ui.toast(errText(e), { error: true });
      return undefined;
    } finally {
      reload();
    }
  };
  return { item, clip, loaded: !!data, g, rows, accounts, actions, off, setOff, pfs, when, scheduledWhen: g ? fmtWhen(g.day, g.time) : '', scheduleNow, tab: rows.some((r) => r.pf === tab) ? tab : firstTab(rows), setTab, shorten, reload };
}
export type ClipScheduleState = ReturnType<typeof useClipSchedule>;

/** The account a platform id posts through ("youtube-shorts:vertical" -> "youtube"). */
export function channelOf(p: string): string {
  const b = p.split(':')[0];
  return b === 'youtube-shorts' ? 'youtube' : b;
}

/** The clip's post: unscheduled -> its platforms + "Schedule · <next free slot>"; scheduled -> when, where, and the
 * copy per platform (the publish drawer's component, same rows). */
export function ClipSchedule({ item, clip, compact = false }: { item: string; clip: string; compact?: boolean }) {
  return <ClipScheduleView s={useClipSchedule(item, clip)} compact={compact} />;
}

/** which version a platform chip posts (the clip page): its shape after the name */
function PfVersion({ pf, files, selected }: { pf: string; files?: ClipFile[]; selected?: string | null }) {
  const a = files?.length ? (selected ? files.find(f => f.path === selected) : versionFor(pf, files))?.aspect : null;
  return a && /^\d+:\d+$/.test(a) ? (
    <span className="ci-pf-v" title={t('ci.pfVersion', { v: a })} data-testid="ci-pf-version">
      {a}
    </span>
  ) : null;
}

export function ClipScheduleView({ s, compact = false, files }: { s: ClipScheduleState; compact?: boolean; files?: ClipFile[] }) {
  const { g, accounts, actions, off, setOff, pfs, rows } = s;
  if (!s.loaded) return <div className="ci-sched" data-testid="ci-schedule" aria-busy="true" />;
  if (!g) {
    if (!accounts.connected.length)
      return (
        <div className="ci-sched" data-testid="ci-schedule">
          <a className="pb-link" href={href({ name: 'settings', section: 'accounts' })} data-testid="ci-pick-platforms">
            {t('ci.noPlatforms')}
          </a>
        </div>
      );
    return (
      <div className="ci-sched" data-testid="ci-schedule" data-state="unscheduled">
        <div className="ci-chips">
          {accounts.connected.map((pf) => {
            const on = !off.includes(pf);
            return (
              <button key={pf} className={`ci-chip ${on ? 'on' : ''}`} aria-pressed={on} onClick={() => setOff(on ? [...off, pf] : off.filter((x) => x !== pf))} data-testid="ci-pf" data-pf={pf}>
                <PlatformIcon id={pf} size={13} />
                {platformName(pf)}
                <PfVersion pf={pf} files={files} />
              </button>
            );
          })}
        </div>
        <button className="btn ci-schedule-btn" disabled={!pfs.length} onClick={() => void s.scheduleNow()} data-testid="ci-schedule-btn">
          <CalendarClock className="ico" />
          {t('ci.schedule', { when: s.when })}
        </button>
        {!compact && <p className="ci-note">{t('ci.assist')}</p>}
      </div>
    );
  }
  return (
    <div className="ci-sched" data-testid="ci-schedule" data-state="scheduled">
      {g.posts.some(postDelivered) && <><StatusMark s={g.status} /><p className="ci-note">{t('pl.post.remoteEdit')}</p></>}
      <div className="ci-when">
        <label className="pb-field">
          <CalendarDays className="ico" />
          <input type="date" aria-label={t('pb.d.date')} disabled={g.posts.some(postDelivered)} value={g.day} onChange={(e) => e.target.value && void actions.retime(g, e.target.value)} data-testid="ci-date" />
        </label>
        <label className="pb-field narrow">
          <Clock className="ico" />
          <input type="time" aria-label={t('pb.d.time')} disabled={g.posts.some(postDelivered)} value={g.time} onChange={(e) => /^\d{2}:\d{2}$/.test(e.target.value) && void actions.retime(g, g.day, e.target.value)} data-testid="ci-time" />
        </label>
        <a className="pb-link muted" href={href({ name: 'calendar' })} data-testid="ci-calendar">
          {t('ci.openCalendar')}
        </a>
      </div>
      <div className="ci-chips">
        {sortIds([...new Set([...accounts.connected, ...g.posts.map((p) => base(p.platform))])]).map((pf) => {
          const row = g.posts.find((p) => base(p.platform) === pf);
          const on = !!row && row.enabled !== false;
          return (
            <button
              key={pf}
              className={`ci-chip ${on ? 'on' : ''}`}
              aria-pressed={on}
              disabled={!!row && postDelivered(row)}
              onClick={() => void actions.togglePlatform(g, pf, !on, `${g.day}T${accounts.timeOf(pf)}`, platformName(pf))}
              data-testid="ci-pf"
              data-pf={pf}
            >
              <PlatformIcon id={pf} size={13} />
              {platformName(pf)}
              <PfVersion pf={pf} files={files} selected={row?.video_path} />
            </button>
          );
        })}
      </div>
      {rows.length > 0 && <PostCopy rows={rows} tab={s.tab} setTab={s.setTab} accounts={accounts} actions={actions} shorten={s.shorten} />}
      {!compact && <p className="ci-note">{t('ci.assist')}</p>}
    </div>
  );
}

// ---------------------------------------------------------------- the inspector (layout B)
export function ClipInfoPanel({ doc, strip, time, edit, sched, item, clip, onRemade }: { doc: OutputDoc; strip: StripInfo | null; time: number; edit: EditFn; sched: ClipScheduleState; item?: string; clip?: string; onRemade?: () => void }) {
  return (
    <section className="ci" data-testid="clip-info">
      <div className="ci-sec">
        <span className="ci-lbl">{t('ci.cover')}</span>
        <ClipCovers doc={doc} strip={strip} time={time} edit={edit} />
      </div>
      <div className="ci-sec">
        <span className="ci-lbl">{t('ci.captions')}</span>
        <CaptionLooks doc={doc} edit={edit} />
      </div>
      <div className="ci-sec">
        <span className="ci-lbl">{t('ci.versions')}</span>
        <ClipVersions doc={doc} edit={edit} />
      </div>
      {item && clip && <ClipFill item={item} clip={clip} onRemade={onRemade} />}
      {item && clip && <ClipVisualsRedo item={item} clip={clip} />}
      {item && clip && <ClipVoice item={item} clip={clip} />}
      {item && clip && doc.imported && <ClipImported doc={doc} item={item} clip={clip} strip={strip} edit={edit} />}
      <div className="ci-sec">
        <span className="ci-lbl">{t('ci.post')}</span>
        <ClipScheduleView s={sched} />
        {item && clip && <ClipCopyRewrite item={item} clip={clip} onDone={sched.reload} imported={!!doc.imported} />}
      </div>
    </section>
  );
}
