// Camera + mic (+ screen) recording with separate tracks, 1 s chunks streamed to main (crash-safe), a level meter,
// line / retake marks, pause / resume and device choice. Studio sound is applied at ingest, not live (raw, no browser
// noise suppression). Mark times and the clock leave out paused time (MediaRecorder leaves it out of the file too).
import { useCallback, useEffect, useRef, useState } from 'react';
import { t } from '../../i18n';
import { recorderLifecycle } from './recorderLifecycle';

export type RecTrack = 'camera' | 'mic' | 'screen';
export type RecState = 'idle' | 'asking' | 'denied' | 'ready' | 'recording' | 'paused' | 'stopping' | 'error';

export interface Device {
  id: string;
  label: string;
}

const SCREEN_AUDIO_TYPES = ['video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus', 'video/webm'];
const VIDEO_TYPES = ['video/webm;codecs=vp9', 'video/webm;codecs=h264', 'video/webm', 'video/mp4;codecs=avc1'];
const AUDIO_TYPES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'];

export function pickMime(kinds: string[], supported: (t: string) => boolean = (t) => typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(t)): string | undefined {
  return kinds.find((k) => supported(k));
}

interface Session {
  id: string;
  dir: string;
  t0: number;
  recorders: MediaRecorder[];
  stops: (() => Promise<void>)[];
  saving?: Promise<{ dir: string; tracks: string[]; marks: number; sessionId: string; secs: number }>;
  chains: Promise<unknown>[];
  /** paused time so far (ms) and when the current pause began */
  pausedMs: number;
  pausedAt: number | null;
}

/** Seconds of recording at ``now``: wall time since the start minus every pause. */
const DEVICES_KEY = 'rec.devices';

/** The camera and mic last recorded with (pickups use the same ones). */
export function loadDevices(): { cam: string | null; mic: string | null } {
  try {
    const v = JSON.parse(localStorage.getItem(DEVICES_KEY) ?? 'null') as { cam?: unknown; mic?: unknown } | null;
    return { cam: typeof v?.cam === 'string' ? v.cam : null, mic: typeof v?.mic === 'string' ? v.mic : null };
  } catch {
    return { cam: null, mic: null };
  }
}

function saveDevices(d: { cam: string | null; mic: string | null }) {
  try {
    localStorage.setItem(DEVICES_KEY, JSON.stringify(d));
  } catch {
    /* private mode: the system default is used next time */
  }
}

export type ScreenResult = 'on' | 'denied' | { error: string };

/** A failed getDisplayMedia -> 'denied' (the OS refused: Screen Recording is off) or the browser's message. */
export function screenFailure(e: unknown): ScreenResult {
  const name = (e as { name?: string } | null)?.name ?? '';
  const msg = String((e as { message?: string } | null)?.message ?? e ?? '');
  if (name === 'NotAllowedError' || /permission|not allowed|denied/i.test(msg)) return 'denied';
  return { error: msg || name || 'screen' };
}

export function recordedSeconds(s: { t0: number; pausedMs: number; pausedAt: number | null }, now: number): number {
  const paused = s.pausedMs + (s.pausedAt !== null ? now - s.pausedAt : 0);
  return Math.max(0, (now - s.t0 - paused) / 1000);
}

export function useRecorder() {
  const [state, setState] = useState<RecState>('idle');
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [level, setLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [cameras, setCameras] = useState<Device[]>([]);
  const [mics, setMics] = useState<Device[]>([]);
  const [cameraId, setCameraId] = useState<string | null>(null);
  const [micId, setMicId] = useState<string | null>(null);
  const [screenOn, setScreenOn] = useState(false);
  const [screenStream, setScreenStream] = useState<MediaStream | null>(null);
  const [interruption, setInterruption] = useState<RecTrack | null>(null);
  const interrupted = useRef(false);
  const sess = useRef<Session | null>(null);
  const screen = useRef<MediaStream | null>(null);
  const raf = useRef<number | null>(null);
  const actx = useRef<AudioContext | null>(null);
  // Permission requests may resolve after navigation. Own each stream before
  // React commits state, and invalidate pending requests when this view closes.
  const mounted = useRef(false);
  const openRequest = useRef(0);
  const screenRequest = useRef(0);
  const camera = useRef<MediaStream | null>(null);

  const stopStream = useCallback((s: MediaStream | null) => s?.getTracks().forEach((tr) => tr.stop()), []);
  const releaseCamera = useCallback(() => {
    if (raf.current) cancelAnimationFrame(raf.current);
    raf.current = null;
    void actx.current?.close().catch(() => undefined);
    actx.current = null;
    stopStream(camera.current);
    camera.current = null;
  }, [stopStream]);

  useEffect(
    () => {
      mounted.current = true;
      return () => {
        mounted.current = false;
        openRequest.current++;
        screenRequest.current++;
        releaseCamera();
        stopStream(screen.current);
      };
    },
    [stopStream, releaseCamera],
  );
  useEffect(() => () => stopStream(stream), [stream, stopStream]);

  /** Stop sharing the screen. */
  const stopScreen = useCallback(() => {
    screenRequest.current++;
    stopStream(screen.current);
    screen.current = null;
    setScreenOn(false);
    setScreenStream(null);
  }, [stopStream]);

  const interruptCapture = useCallback((track: RecTrack) => {
    const s = sess.current;
    if (!s) {
      if (track !== 'screen') {
        stopScreen();
        releaseCamera();
        setStream(null);
        setLevel(0);
        setState('error');
        setError(t(track === 'camera' ? 'rec.cameraDisconnected' : 'rec.micDisconnected'));
      }
      return;
    }
    if (interrupted.current || s.saving) return;
    if (s.pausedAt === null) s.pausedAt = performance.now();
    for (const r of s.recorders) if (r.state === 'recording') r.pause();
    interrupted.current = true;
    setInterruption(track);
    setElapsed(recordedSeconds(s, s.pausedAt));
    setState('paused');
  }, [releaseCamera, stopScreen]);

  const listDevices = useCallback(async () => {
    const all = await navigator.mediaDevices.enumerateDevices();
    if (!mounted.current) return;
    const name = (d: MediaDeviceInfo, i: number, kind: string) => d.label || `${kind} ${i + 1}`;
    setCameras(all.filter((d) => d.kind === 'videoinput').map((d, i) => ({ id: d.deviceId, label: name(d, i, 'Camera') })));
    setMics(all.filter((d) => d.kind === 'audioinput' && d.deviceId !== 'default' && d.deviceId !== 'communications').map((d, i) => ({ id: d.deviceId, label: name(d, i, 'Microphone') })));
  }, []);

  /** Ask (macOS) and open the camera + mic (``cam`` / ``mic``: a device id, else the system default). */
  const open = useCallback(async (want: { cam?: string | null; mic?: string | null } = {}) => {
    const request = ++openRequest.current;
    const active = () => mounted.current && openRequest.current === request;
    setState('asking');
    setError(null);
    try {
      const st = await window.desk.rec.status();
      if (!active()) return;
      if (st.camera !== 'granted' || st.microphone !== 'granted') {
        const cam = st.camera === 'granted' || (await window.desk.rec.ask('camera'));
        if (!active()) return;
        const mic = st.microphone === 'granted' || (await window.desk.rec.ask('microphone'));
        if (!active()) return;
        if (!cam || !mic) {
          setState('denied');
          return;
        }
      }
      const ask = (cam?: string | null, mic?: string | null) =>
        navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 1080 }, height: { ideal: 1920 }, frameRate: { ideal: 30 }, ...(cam ? { deviceId: { exact: cam } } : {}) },
          audio: { noiseSuppression: false, echoCancellation: false, autoGainControl: false, ...(mic ? { deviceId: { exact: mic } } : {}) },
        });
      let s: MediaStream;
      try {
        s = await ask(want.cam, want.mic);
      } catch (e) {
        if (!active()) return;
        // the camera / mic used last time is gone (unplugged): the system default instead
        if (!(want.cam || want.mic) || !['OverconstrainedError', 'NotFoundError'].includes((e as Error).name)) throw e;
        s = await ask(null, null);
      }
      if (!active()) {
        stopStream(s);
        return;
      }
      camera.current = s;
      for (const track of s.getTracks()) {
        track.addEventListener('ended', () => {
          if (mounted.current && camera.current === s) interruptCapture(track.kind === 'video' ? 'camera' : 'mic');
        }, { once: true });
      }
      setStream(s);
      const cam = s.getVideoTracks()[0]?.getSettings().deviceId ?? want.cam ?? null;
      const mic = s.getAudioTracks()[0]?.getSettings().deviceId ?? want.mic ?? null;
      setCameraId(cam);
      setMicId(mic);
      saveDevices({ cam, mic }); // a pickup later records with the same camera and mic
      void listDevices().catch(() => undefined);
      if (raf.current) cancelAnimationFrame(raf.current);
      void actx.current?.close().catch(() => undefined);
      const ctx = new AudioContext();
      actx.current = ctx;
      const an = ctx.createAnalyser();
      an.fftSize = 512;
      ctx.createMediaStreamSource(new MediaStream(s.getAudioTracks())).connect(an);
      const buf = new Uint8Array(an.fftSize);
      const tick = () => {
        an.getByteTimeDomainData(buf);
        let peak = 0;
        for (const v of buf) peak = Math.max(peak, Math.abs(v - 128));
        setLevel(peak / 128);
        raf.current = requestAnimationFrame(tick);
      };
      tick();
      setState('ready');
    } catch (e) {
      if (!active()) return;
      const name = (e as Error).name;
      setState(name === 'NotAllowedError' ? 'denied' : 'error');
      setError((e as Error).message);
    }
  }, [listDevices, stopStream, interruptCapture]);

  /** Switch the camera or the microphone (not while recording). */
  const switchDevice = useCallback(
    async (kind: 'camera' | 'mic', id: string) => {
      if (sess.current) return;
      stopStream(stream);
      await open(kind === 'camera' ? { cam: id, mic: micId } : { cam: cameraId, mic: id });
    },
    [open, stream, stopStream, cameraId, micId],
  );

  /** Share the screen / window she picked (rec:screens -> id). Never silent: -> 'on' | 'denied' (Screen Recording
   * is off for the app) | an error message. */
  const shareScreen = useCallback(
    async (id: string, appAudio = false): Promise<ScreenResult> => {
      if (sess.current) return { error: t('rec.screenFinishTake') };
      stopScreen();
      const request = screenRequest.current;
      const active = () => mounted.current && screenRequest.current === request;
      try {
        await window.desk.rec.screenPick(id, appAudio);
        if (!active()) return { error: t('rec.screenFinishTake') };
        const st = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: appAudio });
        if (!active()) {
          stopStream(st);
          return { error: t('rec.screenFinishTake') };
        }
        if (appAudio && !st.getAudioTracks().length) {
          stopStream(st);
          return { error: t('learning.materialAudioMissing') };
        }
        screen.current = st;
        st.getVideoTracks()[0]?.addEventListener('ended', () => {
          if (screen.current === st) {
            // Any lost input pauses the surviving tracks together. Replacing a
            // recorder mid-take would make their saved timelines disagree.
            interruptCapture('screen');
            // Closing a shared window may end only its video track. Release
            // companion system audio before losing ownership of this stream.
            stopStream(st);
            screen.current = null;
            setScreenOn(false);
            setScreenStream(null);
          }
        });
        setScreenOn(true);
        setScreenStream(st);
        return 'on';
      } catch (e) {
        if (!active()) return screenFailure(e);
        screen.current = null;
        setScreenOn(false);
        setScreenStream(null);
        return screenFailure(e);
      }
    },
    [stopScreen, stopStream, interruptCapture],
  );

  const start = useCallback(
    async (req: { slug: string; title?: string; script: string[]; series?: string; episode?: string; shot?: string; studio?: boolean; group?: string; pickup?: boolean }) => {
      if (!stream || sess.current) return;
      interrupted.current = false;
      setInterruption(null);
      const vMime = pickMime(VIDEO_TYPES);
      const aMime = pickMime(AUDIO_TYPES);
      const screenMime = screen.current?.getAudioTracks().length ? pickMime(SCREEN_AUDIO_TYPES) : vMime;
      const tracks: RecTrack[] = ['camera', 'mic', ...(screen.current ? (['screen'] as RecTrack[]) : [])];
      const { sessionId, dir } = await window.desk.rec.begin({ ...req, tracks, mime: { camera: vMime ?? '', mic: aMime ?? '', ...(screen.current ? { screen: screenMime ?? '' } : {}) } });
      const s: Session = { id: sessionId, dir, t0: performance.now(), recorders: [], stops: [], chains: [], pausedMs: 0, pausedAt: null };
      const add = (track: RecTrack, ms: MediaStream, mime?: string) => {
        const r = new MediaRecorder(ms, mime ? { mimeType: mime } : undefined);
        let seq = 0;
        let chain: Promise<unknown> = Promise.resolve();
        const i = s.chains.length;
        s.chains.push(chain);
        r.ondataavailable = (ev) => {
          if (!ev.data || !ev.data.size) return;
          const n = seq++;
          const startMs = n === 0 ? Date.now() - 1000 : undefined;
          chain = chain.then(async () => {
            const data = new Uint8Array(await ev.data.arrayBuffer());
            await window.desk.rec.chunk(startMs === undefined ? { sessionId, track, seq: n, data } : { sessionId, track, seq: n, data, startMs });
          });
          s.chains[i] = chain.catch((e) => setError(String((e as Error).message)));
        };
        const lifecycle = recorderLifecycle(r);
        lifecycle.start(1000);
        s.stops.push(lifecycle.stop);
        s.recorders.push(r);
      };
      add('camera', new MediaStream(stream.getVideoTracks()), vMime);
      add('mic', new MediaStream(stream.getAudioTracks()), aMime);
      if (screen.current) add('screen', screen.current, screenMime);
      sess.current = s;
      setElapsed(0);
      setState('recording');
    },
    [stream],
  );

  useEffect(() => {
    if (state !== 'recording') return;
    const tm = window.setInterval(() => sess.current && setElapsed(recordedSeconds(sess.current, performance.now())), 250);
    return () => window.clearInterval(tm);
  }, [state]);

  const pause = useCallback(() => {
    const s = sess.current;
    if (!s || s.saving || s.pausedAt !== null) return;
    for (const r of s.recorders) if (r.state === 'recording') r.pause();
    s.pausedAt = performance.now();
    setElapsed(recordedSeconds(s, s.pausedAt));
    setState('paused');
  }, []);

  const resume = useCallback(() => {
    const s = sess.current;
    if (!s || s.saving || s.pausedAt === null || interrupted.current) return;
    s.pausedMs += performance.now() - s.pausedAt;
    s.pausedAt = null;
    for (const r of s.recorders) if (r.state === 'paused') r.resume();
    setState('recording');
  }, []);

  const mark = useCallback(async (kind: 'line' | 'retake', line: number) => {
    const s = sess.current;
    if (!s) return;
    await window.desk.rec.mark({ sessionId: s.id, t: recordedSeconds(s, performance.now()), kind, line });
  }, []);

  /** Stop -> every chunk written -> main closes the session. -> {dir} */
  const stop = useCallback(async () => {
    const s = sess.current;
    if (!s) return null;
    if (s.saving) return s.saving;
    if (s.pausedAt !== null) {
      s.pausedMs += performance.now() - s.pausedAt;
      s.pausedAt = null;
    }
    const secs = recordedSeconds(s, performance.now());
    setState('stopping');
    s.saving = (async () => {
      await Promise.all(s.stops.map((stop) => stop()));
      await Promise.all(s.chains);
      const out = await window.desk.rec.end(s.id, secs);
      sess.current = null;
      const missing = camera.current?.getVideoTracks().some((tr) => tr.readyState === 'live') ?
        camera.current.getAudioTracks().some((tr) => tr.readyState === 'live') ? null : 'mic' : 'camera';
      setState(missing ? 'error' : 'ready');
      if (missing) {
        stopScreen();
        releaseCamera();
        setStream(null);
        setLevel(0);
        setError(t(missing === 'camera' ? 'rec.cameraDisconnected' : 'rec.micDisconnected'));
      }
      return { ...out, sessionId: s.id, secs };
    })();
    return s.saving;
  }, [releaseCamera, stopScreen]);

  const interruptionMessage = interruption ? t(interruption === 'camera' ? 'rec.cameraInterrupted' : interruption === 'mic' ? 'rec.micInterrupted' : 'rec.screenInterrupted') : null;
  return { state, stream, level, error, elapsed, cameras, mics, cameraId, micId, screenOn, screenStream, interruption, interruptionMessage, open, switchDevice, start, stop, pause, resume, mark, shareScreen, stopScreen };
}
