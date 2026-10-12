// The clip player: large in-page (overlay) and system full screen (⤢, double-click, F; Esc / ⤡ back to where she was:
// the OS's own full screen, lib/fullscreen.ts), frame-accurate scrubbing,
// J/K/L shuttle, ←/→ one frame (Shift: 1 s), I/O selection + loop, speed, size versions (3:4 / 9:16) and the
// captions / safe-area overlays. Embedded in the output editor and the focused review with the same keys.
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { Maximize2, Minimize2, Pause, Play, Repeat, ScanLine, StepBack, StepForward, Subtitles, Volume2, VolumeX, Wand2, X } from 'lucide-react';
import type { CaptionCue, ClipFile, EffectInstance } from '../../../shared/v04';
import type { StripInfo } from '../../../shared/timeline';
import { fmtLen, t } from '../i18n';
import { platformName } from '../lib/platformName';
import { clamp, frameTime, loopTime, safeAreas, seekKey, shuttle, step, timecode, volumeStep } from '../lib/player';
import { screenOwner, useNativeFullscreen } from '../lib/fullscreen';
import { isTyping } from './ui';
import { media } from './kit';
import { Scrubber, type ScrubTick } from './Scrubber';

export interface PlayerApi {
  seek(t: number): void;
  time(): number;
  play(): void;
  pause(): void;
  selection(): { a: number; b: number } | null;
  setSelection(s: { a: number; b: number } | null): void;
  aspect(): string | undefined;
}

export interface PlayerProps {
  files: ClipFile[];
  fps?: number;
  duration?: number;
  captions?: CaptionCue[];
  captionStyle?: { size?: number; color?: string; highlight?: string; position?: string };
  keywords?: { word: string; color: string }[];
  effects?: EffectInstance[];
  /** ranges skipped while playing (inner cuts) and the kept window (trim) */
  cuts?: { start: number; end: number }[];
  trim?: { start: number; end: number } | null;
  marks?: number[];
  /** chapter / edit ticks on the scrub bar (amber draft, teal applied) */
  ticks?: ScrubTick[];
  /** the timeline's sprite sheet: a frame preview while hovering the scrub bar */
  strip?: StripInfo | null;
  onPlaying?: (playing: boolean) => void;
  title?: string;
  /** overlay mode: Esc closes, the player owns the keyboard */
  onClose?: () => void;
  onEdit?: () => void;
  onTime?: (t: number) => void;
  onSelection?: (s: { a: number; b: number } | null) => void;
  keys?: boolean;
  autoPlay?: boolean;
  initialAspect?: string;
  extra?: ReactNode;
  testId?: string;
  /** before / after on the player itself: the "before" overlays left of a draggable divider, this player's own
   * (the "after") on the right; never a modal */
  compare?: { effects: EffectInstance[]; captions?: CaptionCue[]; labels: [string, string] } | null;
  /** a label pinned top-left of the frame (e.g. "Original" while C is held) */
  badge?: string | null;
  /** playing over a cut: how many seconds were skipped (the editor flashes "Skipped 1.7 s") */
  onSkip?: (secs: number) => void;
  /** open straight in system full screen (▶ "Play full screen" on a clip card) */
  startFull?: boolean;
  /** system full screen ended (Esc, ⤡, ⌃⌘F): a player opened only to be watched full screen closes */
  onFullExit?: () => void;
}

const VOL_KEY = 'player.volume';
function savedVolume(): number {
  const v = Number(localStorage.getItem(VOL_KEY));
  return Number.isFinite(v) && localStorage.getItem(VOL_KEY) !== null ? clamp(v, 0, 1) : 1;
}

const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 2];
/** waits before each reload of a file that failed to load (then the error shows) */
const RETRIES = [300, 1000, 2500];

export const Player = forwardRef<PlayerApi, PlayerProps>(function Player(p, ref) {
  const box = useRef<HTMLDivElement | null>(null);
  const v = useRef<HTMLVideoElement | null>(null);
  const [vi, setVi] = useState(() => Math.max(0, p.files.findIndex((f) => f.aspect === p.initialAspect)));
  const file = p.files[vi] ?? p.files[0];
  const aspect = file?.aspect;
  const fps = file?.fps || p.fps || 30;
  const [dur, setDur] = useState(file?.duration || p.duration || 0);
  const [cur, setCur] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [rate, setRate] = useState(0); // shuttle rate (J/K/L); 0 = paused
  const [speed, setSpeed] = useState(1);
  const [sel, setSelS] = useState<{ a: number; b: number } | null>(null);
  const [loop, setLoop] = useState(false);
  const [caps, setCaps] = useState(false);
  const [split, setSplit] = useState(50);
  const [safe, setSafe] = useState(false);
  const keyRef = useRef<((e: KeyboardEvent) => void) | null>(null);
  // full screen: every key comes here (and only here) whether or not this player's keys are on in the page
  const fs = useNativeFullscreen(box, { onExit: p.onFullExit, onKey: (e) => keyRef.current?.(e) });
  const full = fs.on;
  const fullNow = useCallback(() => full || (!!box.current && screenOwner() === box.current), [full]);
  const [vol, setVol] = useState(savedVolume);
  const [muted, setMuted] = useState(false);
  const [ar, setAr] = useState<number | null>(null); // the video's own shape: full screen fills the screen with it
  const [err, setErr] = useState(false);
  const [buffered, setBuffered] = useState<[number, number][]>([]);
  const selRef = useRef(sel);
  selRef.current = sel;
  const setSel = useCallback(
    (s: { a: number; b: number } | null) => {
      setSelS(s);
      p.onSelection?.(s);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [p.onSelection],
  );

  const seek = useCallback(
    (x: number) => {
      const el = v.current;
      if (!el) return;
      const tt = clamp(x, 0, el.duration || dur || 0);
      el.currentTime = tt;
      setCur(tt);
      p.onTime?.(tt);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [dur, p.onTime],
  );

  useImperativeHandle(
    ref,
    () => ({
      seek,
      time: () => v.current?.currentTime ?? 0,
      play: () => void v.current?.play().catch(() => undefined),
      pause: () => v.current?.pause(),
      selection: () => selRef.current,
      setSelection: setSel,
      aspect: () => aspect,
    }),
    [seek, setSel, aspect],
  );

  // keep position (and playing) when the file under the player changes: another size version, a new render of the
  // same version (its `v`), or a reload after a load error
  const keepAt = useRef(0);
  const resume = useRef(false);
  // a load error is retried with a fresh URL before it is shown: the file may have been replaced while it played (a
  // render writes the same path again) or be missing for a moment between the two
  const [retry, setRetry] = useState(0); // a reload's nonce in the URL
  const fails = useRef(0); // failed loads in a row
  const retryTm = useRef(0);
  const ver = file?.v ?? null;
  const src = file ? media(file.path, retry ? `${ver ?? ''}~${retry}` : ver) : '';
  const lastFile = useRef({ path: file?.path, v: ver });
  useEffect(() => {
    const was = lastFile.current;
    lastFile.current = { path: file?.path, v: ver };
    if (was.path === file?.path && was.v === ver) return;
    const el = v.current;
    if (el && was.path === file?.path) {
      keepAt.current = el.currentTime;
      resume.current = !el.paused;
    }
    window.clearTimeout(retryTm.current);
    fails.current = 0;
    setRetry(0);
    setErr(false);
  }, [file?.path, ver]);
  useEffect(() => () => window.clearTimeout(retryTm.current), []);
  const onMeta = (el: HTMLVideoElement) => {
    setDur(el.duration || dur);
    if (el.videoWidth && el.videoHeight) setAr(el.videoWidth / el.videoHeight);
    if (keepAt.current) el.currentTime = Math.min(keepAt.current, el.duration || keepAt.current);
    keepAt.current = 0;
    fails.current = 0;
    setErr(false);
    if (resume.current) void el.play().catch(() => undefined);
    resume.current = false;
  };
  const onError = (el: HTMLVideoElement) => {
    const n = fails.current++;
    if (n >= RETRIES.length) return setErr(true);
    keepAt.current = el.currentTime || keepAt.current;
    resume.current = resume.current || rate > 0;
    window.clearTimeout(retryTm.current);
    retryTm.current = window.setTimeout(() => setRetry((x) => x + 1), RETRIES[n]);
  };

  // play loop: time, selection loop, skip cuts / outside trim, reverse shuttle
  useEffect(() => {
    let raf = 0;
    let lastT = -1;
    let last = performance.now();
    const tick = (now: number) => {
      const el = v.current;
      const dt = (now - last) / 1000;
      last = now;
      if (el) {
        if (rate < 0) {
          const nt = Math.max(0, el.currentTime + rate * dt);
          el.currentTime = nt;
          if (nt <= 0) setRate(0);
        }
        let tt = el.currentTime;
        if (!el.paused || rate < 0) {
          const back = loopTime(tt, selRef.current, loop);
          if (back !== null) {
            el.currentTime = back;
            tt = back;
          } else if (rate >= 0) {
            // jump a frame early (rAF runs ~16 ms apart) so the cut never plays; the volume dips over the seek
            // (a seek lands on a frame boundary, a little before the asked time: past the cut's last 50 ms = done)
            const c = (p.cuts ?? []).find((x) => tt >= x.start - 0.03 && tt < x.end - 0.05);
            if (c) {
              const vol = el.volume;
              el.volume = 0;
              el.currentTime = c.end + 0.01;
              tt = c.end + 0.01;
              el.addEventListener('seeked', () => (el.volume = vol), { once: true });
              p.onSkip?.(c.end - c.start);
            } else if (p.trim && tt < p.trim.start - 0.05) {
              el.currentTime = p.trim.start;
              tt = p.trim.start;
            } else if (p.trim && tt >= p.trim.end) {
              el.pause();
              el.currentTime = p.trim.end;
              tt = p.trim.end;
            }
          }
        }
        if (Math.abs(tt - lastT) > 0.04 || (el.paused && tt !== lastT)) {
          lastT = tt;
          setCur(tt);
          p.onTime?.(tt);
        }
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rate, loop, p.cuts, p.trim, p.onTime, p.onSkip]);

  useEffect(() => {
    const el = v.current;
    if (!el) return;
    if (rate > 0) {
      el.playbackRate = rate * speed;
      void el.play().catch(() => undefined);
    } else if (rate < 0) el.pause();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rate]);
  useEffect(() => {
    if (v.current && rate >= 0) v.current.playbackRate = Math.max(1, rate || 1) * speed;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [speed]);

  const toggle = useCallback(() => {
    const el = v.current;
    if (!el) return;
    if (el.paused && rate <= 0) {
      setRate(1);
    } else {
      setRate(0);
      el.pause();
    }
  }, [rate]);

  const toggleFull = fs.toggle;
  const startFull = useRef(p.startFull);
  useEffect(() => {
    // the click that opened the player is still the user gesture the request needs
    if (startFull.current) void fs.enter();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // volume: the element follows the slider / mute; the level is remembered across players
  useEffect(() => {
    const el = v.current;
    if (!el) return;
    el.volume = vol;
    el.muted = muted || vol === 0;
    localStorage.setItem(VOL_KEY, String(vol));
  }, [vol, muted, file?.path]);

  // keyboard
  const keysOn = p.keys !== false;
  const onClose = p.onClose;
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      // the screen as it is now, not as last rendered: the fullscreenchange that updates `full` is dispatched with the
      // next frame (a hidden window on Windows paints late), and a key routed here before it must still act full screen
      const full = fullNow();
      if (full && e.key === 'Escape') {
        e.preventDefault();
        void fs.exit(); // back to where she was: the page, the overlay, the same frame
        return;
      }
      if (isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      if (!full && document.querySelector('.scrim, .ctx')) return;
      const el = v.current;
      if (!el) return;
      const k = e.key;
      const lower = k.toLowerCase();
      if (k === ' ' || lower === 'k') {
        e.preventDefault();
        if (lower === 'k') {
          setRate(0);
          el.pause();
        } else toggle();
      } else if (lower === 'j' || (lower === 'l' && !e.shiftKey)) {
        e.preventDefault();
        setRate((r) => shuttle(el.paused && r > 0 ? 0 : r, lower as 'j' | 'l'));
      } else if (lower === 'l' && e.shiftKey) {
        e.preventDefault();
        setLoop((x) => !x);
      } else if (k === 'ArrowLeft' || k === 'ArrowRight') {
        e.preventDefault();
        const dir = k === 'ArrowRight' ? 1 : -1;
        if (full && !e.shiftKey) {
          seek(seekKey(el.currentTime, dir, fps, el.duration || dur, false, true)); // watching: 5 s, playback goes on
          return;
        }
        setRate(0);
        el.pause();
        seek(seekKey(el.currentTime, dir, fps, el.duration || dur, e.shiftKey, full));
      } else if (full && (k === 'ArrowUp' || k === 'ArrowDown')) {
        e.preventDefault();
        setMuted(false);
        setVol((x) => volumeStep(x, k === 'ArrowUp' ? 1 : -1));
      } else if (lower === 'm') {
        e.preventDefault();
        setMuted((x) => !x);
      } else if (k === 'Home' || k === 'End') {
        e.preventDefault();
        setRate(0);
        el.pause();
        seek(k === 'Home' ? (p.trim?.start ?? 0) : (p.trim?.end ?? (el.duration || dur)));
      } else if (lower === 'i') {
        const a = el.currentTime;
        setSel({ a, b: Math.max(a + 0.1, selRef.current?.b ?? Math.min(dur, a + 3)) });
      } else if (lower === 'o') {
        const b = el.currentTime;
        setSel({ a: Math.min(selRef.current?.a ?? Math.max(0, b - 3), b - 0.1), b });
      } else if (lower === 'f') {
        e.preventDefault();
        toggleFull();
      } else if (k === 'Escape') {
        if (!fs.escSpent() && onClose) onClose();
      }
    };
    keyRef.current = on;
    if (!keysOn) return;
    window.addEventListener('keydown', on);
    return () => window.removeEventListener('keydown', on);
  }, [keysOn, onClose, toggle, toggleFull, seek, setSel, fps, dur, fullNow, fs, p.trim]);

  const areas = safeAreas(file?.aspect ?? '', file?.safe_box, file?.caption_box, file?.w, file?.h);
  const cue = caps ? (p.captions ?? []).find((c) => !c.removed && cur >= c.start && cur <= c.end) : undefined;
  const style = p.captionStyle ?? {};
  const fxAt = (list: EffectInstance[] | undefined) => (list ?? []).filter((x) => cur >= x.start && cur <= x.end && typeof x.params?.text === 'string' && x.params.text);
  const liveFx = fxAt(p.effects);
  const cueAt = (list: CaptionCue[] | undefined) => (caps ? (list ?? []).find((c) => !c.removed && cur >= c.start && cur <= c.end) : undefined);
  const overlays = (c: CaptionCue | undefined, fx: EffectInstance[], tag: string) => (
    <>
      {c && (
        <div className={`capov ${style.position ?? 'bottom'}`} style={{ color: style.color ?? '#fff', fontSize: style.size ? `calc(clamp(14px, 2.4vh, 26px) * ${style.size})` : undefined }} data-testid={`caption-overlay${tag}`}>
          {highlight(c.text, p.keywords ?? [], style.highlight)}
        </div>
      )}
      {fx.map((x) => (
        <div key={x.id} className="capov middle fxov" style={{ color: String(x.params?.color ?? '#FFD60A'), fontSize: `calc(clamp(22px, 4vh, 44px) * ${Math.max(0.6, Math.min(2, Number(x.params?.size ?? 0.11) / 0.11))})` }} data-testid={`fx-overlay${tag}`}>
          {String(x.params?.text ?? '')}
        </div>
      ))}
    </>
  );

  return (
    <div ref={box} className={`pl ${full ? 'full' : ''}`} tabIndex={-1} data-testid={p.testId ?? 'player'} data-full={full ? '1' : '0'} data-native-full={fs.native ? '1' : '0'}>
      {(p.title || p.onClose) && (
        <div className="row">
          {p.title && <b className="clamp1" style={{ fontWeight: 500, fontSize: 15 }}>{p.title}</b>}
          <span className="sp" />
          {p.onEdit && (
            <button className="btn sm" onClick={p.onEdit} data-testid="player-edit">
              <Wand2 className="ico" />
              {t('player.edit')}
            </button>
          )}
          {p.onClose && (
            <button className="btn ghost icon sm" onClick={p.onClose} aria-label={t('player.close')} data-tip={`${t('player.close')} · Esc`} data-testid="player-close">
              <X className="ico" />
            </button>
          )}
        </div>
      )}
      <div className="stage" onDoubleClick={toggleFull}>
        {file ? (
          <div className="frame" style={ar ? ({ '--ar': ar } as CSSProperties) : undefined}>
            <video
              ref={v}
              src={src}
              preload="auto"
              playsInline
              autoPlay={p.autoPlay}
              onPlay={() => (setPlaying(true), p.onPlaying?.(true))}
              onPause={() => (setPlaying(false), p.onPlaying?.(false))}
              onProgress={(e) => {
                const b = (e.target as HTMLVideoElement).buffered;
                setBuffered(Array.from({ length: b.length }, (_, i) => [b.start(i), b.end(i)] as [number, number]));
              }}
              onLoadedMetadata={(e) => onMeta(e.target as HTMLVideoElement)}
              onError={(e) => onError(e.target as HTMLVideoElement)}
              onClick={() => toggle()}
              data-testid="player-video"
            />
            {safe && areas && (
              <>
                <div className="safe" style={{ left: pct2(areas.safe.l), top: pct2(areas.safe.t), right: pct2(areas.safe.r), bottom: pct2(areas.safe.b) }}>
                  <span>{t('player.safe')}</span>
                </div>
                <div className="safe cap" style={{ left: pct2(areas.cap.l), top: pct2(areas.cap.t), right: pct2(areas.cap.r), bottom: pct2(areas.cap.b) }} />
              </>
            )}
            {p.compare ? (
              <>
                <div className="ovl" style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }}>{overlays(cueAt(p.compare.captions ?? p.captions), fxAt(p.compare.effects), '-before')}</div>
                <div className="ovl" style={{ clipPath: `inset(0 0 0 ${split}%)` }}>{overlays(cue, liveFx, '')}</div>
                <div
                  className="wipe"
                  style={{ left: `${split}%` }}
                  onClick={(e) => e.stopPropagation()}
                  onDoubleClick={(e) => e.stopPropagation()}
                  onPointerDown={(e) => {
                    e.stopPropagation();
                    const fr = (e.currentTarget.parentElement as HTMLElement).getBoundingClientRect();
                    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
                    const mv = (ev: PointerEvent) => setSplit(clamp(((ev.clientX - fr.left) / fr.width) * 100, 4, 96));
                    const up = () => {
                      window.removeEventListener('pointermove', mv);
                      window.removeEventListener('pointerup', up);
                    };
                    window.addEventListener('pointermove', mv);
                    window.addEventListener('pointerup', up);
                  }}
                  data-testid="compare-wipe"
                >
                  <span className="l">{p.compare.labels[0]}</span>
                  <i />
                  <span className="r">{p.compare.labels[1]}</span>
                </div>
              </>
            ) : (
              overlays(cue, liveFx, '')
            )}
            {p.badge && <span className="pbadge" data-testid="player-badge">{p.badge}</span>}
          </div>
        ) : (
          <div className="muted" style={{ padding: 48 }}>{t('player.noVideo')}</div>
        )}
        {err && (
          <div className="note" style={{ position: 'absolute', bottom: 12 }} data-testid="player-error">
            {t('player.cantPlay')}
          </div>
        )}
      </div>
      <Scrubber
        duration={dur}
        time={cur}
        buffered={buffered}
        strip={p.strip}
        ticks={[...(p.ticks ?? []), ...(p.marks ?? []).map((m) => ({ t: m, tone: 'chapter' as const }))]}
        selection={sel}
        trim={p.trim}
        label={t('player.seek')}
        onSeek={(x, final) => seek(final ? frameTime(x, fps) : x)}
      />
      <div className="ctl">
        <button className="btn icon sm" onClick={() => seek(step(cur, -1, fps, dur))} aria-label={t('player.frameBack')} data-tip={`${t('player.frameBack')} · ←`}>
          <StepBack className="ico" />
        </button>
        <button className="btn icon" onClick={toggle} aria-label={playing ? t('player.pause') : t('player.play')} data-tip={`${playing ? t('player.pause') : t('player.play')} · Space`} data-testid="player-play">
          {playing ? <Pause className="ico" /> : <Play className="ico" />}
        </button>
        <button className="btn icon sm" onClick={() => seek(step(cur, 1, fps, dur))} aria-label={t('player.frameFwd')} data-tip={`${t('player.frameFwd')} · →`}>
          <StepForward className="ico" />
        </button>
        <span className="tc num" data-testid="timecode">
          <TC v={timecode(cur, fps)} /> <span className="of">/ {fmtLen(dur)}</span>
        </span>
        {rate !== 0 && rate !== 1 && <span className="muted num">{rate > 0 ? `${rate}×` : `◀ ${-rate}×`}</span>}
        <span className="sp" />
        {p.files.length > 1 && (
          <div className="vers" role="group" aria-label={t('player.size')}>
            {p.files.map((f, i) => (
              <button
                key={i}
                className={i === vi ? 'on' : ''}
                onClick={() => {
                  keepAt.current = v.current?.currentTime ?? 0;
                  setVi(i);
                }}
                data-testid={`size-${f.aspect}`}
              >
                {f.label ? `${f.platform && f.label !== t('c.original') ? platformName(f.platform) : f.label} ${/^\d+:\d+$/.test(f.aspect) ? f.aspect : ''}`.trim() : /^\d+:\d+$/.test(f.aspect) ? f.aspect : t('c.original')}
              </button>
            ))}
          </div>
        )}
        <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))} aria-label={t('player.speed')} data-testid="speed">
          {SPEEDS.map((s) => (
            <option key={s} value={s}>
              {s}×
            </option>
          ))}
        </select>
        <button className={`btn icon sm toggle ${loop ? 'on' : ''}`} onClick={() => setLoop((x) => !x)} aria-pressed={loop} aria-label={t('player.loop')} data-tip={`${t('player.loop')} · Shift L`} data-testid="loop">
          <Repeat className="ico" />
        </button>
        {(p.captions?.length ?? 0) > 0 && (
          <button className={`btn icon sm toggle ${caps ? 'on' : ''}`} onClick={() => setCaps((x) => !x)} aria-pressed={caps} aria-label={t('player.captions')} data-tip={t('player.captions')} data-testid="toggle-captions">
            <Subtitles className="ico" />
          </button>
        )}
        {areas && (
          <button className={`btn icon sm toggle ${safe ? 'on' : ''}`} onClick={() => setSafe((x) => !x)} aria-pressed={safe} aria-label={t('player.safe')} data-tip={t('player.safe')} data-testid="toggle-safe">
            <ScanLine className="ico" />
          </button>
        )}
        <div className="vol" role="group" aria-label={t('player.volume')}>
          <button className="btn icon sm" onClick={() => (vol === 0 ? (setVol(1), setMuted(false)) : setMuted((x) => !x))} aria-label={muted || vol === 0 ? t('player.unmute') : t('player.mute')} data-tip={`${muted || vol === 0 ? t('player.unmute') : t('player.mute')} · M`} data-testid="player-mute">
            {muted || vol === 0 ? <VolumeX className="ico" /> : <Volume2 className="ico" />}
          </button>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={muted ? 0 : vol}
            onChange={(e) => (setVol(Number(e.target.value)), setMuted(false))}
            onPointerUp={(e) => e.currentTarget.blur()}
            aria-label={t('player.volume')}
            data-testid="player-volume"
          />
        </div>
        <button className="btn icon sm" onClick={toggleFull} aria-label={full ? t('player.exitFullscreen') : t('player.fullscreen')} data-tip={`${full ? t('player.exitFullscreen') : t('player.fullscreen')} · F`} data-testid="fullscreen">
          {full ? <Minimize2 className="ico" /> : <Maximize2 className="ico" />}
        </button>
      </div>
      {p.extra}
      {p.onClose && <div className="help">{t('player.help')}</div>}
    </div>
  );
});

const pct2 = (f: number) => `${f * 100}%`;

/** 00:00:23:12 with the leading zero groups dimmed (the text stays the full timecode). */
function TC({ v }: { v: string }) {
  const m = /^((?:00:)*)(.*)$/.exec(v);
  const lead = m?.[1] ?? '';
  return (
    <>
      {lead && <span className="z">{lead}</span>}
      {m?.[2] ?? v}
    </>
  );
}

function highlight(text: string, kws: { word: string; color: string }[], fallback?: string): ReactNode {
  if (!kws.length) return text;
  const parts: ReactNode[] = [];
  let rest = text;
  let k = 0;
  while (rest) {
    let best: { i: number; w: { word: string; color: string } } | null = null;
    for (const w of kws) {
      const i = rest.indexOf(w.word);
      if (i >= 0 && (!best || i < best.i)) best = { i, w };
    }
    if (!best) {
      parts.push(rest);
      break;
    }
    if (best.i) parts.push(rest.slice(0, best.i));
    parts.push(
      <span key={k++} style={{ color: best.w.color || fallback }}>
        {best.w.word}
      </span>,
    );
    rest = rest.slice(best.i + best.w.word.length);
  }
  return parts;
}

/** The large in-page player over everything (Esc closes; ⤢ / F / double-click for system full screen). With
 * startFull it opens straight in system full screen and closes when that ends, so she is back where she was. */
export function PlayerOverlay(props: PlayerProps & { onClose: () => void }) {
  return (
    <div className="pl-overlay" onMouseDown={(e) => e.target === e.currentTarget && props.onClose()} data-testid="player-overlay">
      <Player {...props} autoPlay keys />
    </div>
  );
}
