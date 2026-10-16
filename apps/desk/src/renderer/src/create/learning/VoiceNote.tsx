import { useEffect, useRef, useState } from 'react';
import { Mic } from 'lucide-react';
import { t } from '../../i18n';
import { useEngine } from '../../lib/engine';
import { media } from '../../v4/kit';
import { errText } from '../../v4/msg';

interface VoiceCapture { recorder: MediaRecorder; stream: MediaStream; session: string; dir: string; t0: number; chain: Promise<unknown>; seq: number; finished?: Promise<void>; failure?: unknown }

/** Stop the device immediately, then flush final chunks and close this session exactly once. */
function finishVoice(a: VoiceCapture): Promise<void> {
  if (a.finished) return a.finished;
  a.finished = (async () => {
    const stopped = new Promise<void>((resolve) => {
      if (a.recorder.state === 'inactive') return resolve();
      a.recorder.addEventListener('stop', () => resolve(), { once: true }); a.recorder.stop();
    });
    a.stream.getTracks().forEach((track) => track.stop());
    try { await stopped; await a.chain; }
    finally { await window.desk.rec.end(a.session, (performance.now() - a.t0) / 1000); }
    if (a.failure) throw a.failure;
  })();
  return a.finished;
}

/** A voice input tool, not an agent prompt: plain local transcription returns to the editable note field. */
export function VoiceNote({ id, onText, onStart, disabled }: { id: string; onText: (text: string, audio: string) => void; onStart: () => void; disabled: boolean }) {
  const { client } = useEngine();
  const active = useRef<VoiceCapture | null>(null);
  const mounted = useRef(true);
  const opening = useRef<MediaStream | null>(null);
  const [state, setState] = useState<'idle' | 'opening' | 'recording' | 'busy'>('idle');
  const saved = useRef<string | null>(null);
  const [audio, setAudio] = useState<string | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      opening.current?.getTracks().forEach((track) => track.stop()); opening.current = null;
      const a = active.current; active.current = null;
      if (a) void finishVoice(a).catch(() => undefined);
    };
  }, []);
  const toggle = async () => {
    if (state === 'busy' || state === 'opening' || (!client && !active.current)) return;
    setError('');
    let openingStream: MediaStream | null = null;
    try {
      const old = active.current;
      if (old) {
        setState('busy');
        await finishVoice(old);
        if (!mounted.current) return;
        active.current = null;
        saved.current = old.dir; setAudio(`${old.dir}/mic.webm`);
        if (!client) throw new Error(t('learning.voiceEngineWait'));
        const result = await client.dictateLearning(id, old.dir);
        if (!mounted.current) return;
        onText(result.text, result.audio);
        setState('idle');
        return;
      }
      setState('opening');
      const permission = await window.desk.rec.ask('microphone');
      if (!mounted.current) return;
      if (!permission) throw new Error(t('learning.micDenied'));
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      openingStream = stream; opening.current = stream;
      if (!mounted.current) { stream.getTracks().forEach((track) => track.stop()); opening.current = null; return; }
      const mime = ['audio/webm;codecs=opus', 'audio/webm'].find((x) => MediaRecorder.isTypeSupported(x));
      const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      const result = await window.desk.rec.begin({ slug: 'thought', title: t('learning.voiceThought'), script: [], tracks: ['mic'], mime: { mic: recorder.mimeType } });
      if (!mounted.current) { stream.getTracks().forEach((track) => track.stop()); opening.current = null; await window.desk.rec.end(result.sessionId, 0); return; }
      const row: VoiceCapture = { recorder, stream, session: result.sessionId, dir: result.dir, t0: performance.now(), chain: Promise.resolve() as Promise<unknown>, seq: 0 };
      const failed = (error: unknown) => {
        row.failure = error;
        if (active.current === row) active.current = null;
        void finishVoice(row).catch(() => undefined).finally(() => {
          if (mounted.current) { saved.current = row.dir; setAudio(`${row.dir}/mic.webm`); setState('idle'); setError(errText(error)); }
        });
      };
      recorder.ondataavailable = (event) => {
        if (!event.data.size || row.failure) return;
        row.chain = row.chain.then(async () => window.desk.rec.chunk({ sessionId: row.session, track: 'mic', seq: row.seq++, data: new Uint8Array(await event.data.arrayBuffer()) })).catch(failed);
      };
      recorder.onerror = () => failed(new Error(t('learning.voiceInterrupted')));
      active.current = row; openingStream = null; opening.current = null;
      onStart();
      recorder.start(500);
      setState('recording');
    } catch (e) {
      openingStream?.getTracks().forEach((track) => track.stop()); opening.current = null;
      const row = active.current; active.current = null;
      if (row) await finishVoice(row).catch(() => undefined);
      if (mounted.current) { setState('idle'); setError(errText(e)); }
    }
  };
  return <div>
    <button className="btn" disabled={state === 'busy' || state === 'opening' || (state !== 'recording' && (disabled || !client))} onClick={() => void toggle()} data-testid="learning-dictate"><Mic className="ico" />{state === 'recording' ? t('learning.stopDictation') : state === 'busy' ? t('learning.transcribing') : state === 'opening' ? t('learning.openingMic') : t('learning.dictate')}</button>
    {error && <p role="alert">{error}</p>}
    {audio && <audio controls src={media(audio)} style={{ maxWidth: '100%', marginTop: 8 }} />}
    {error && saved.current && <button className="btn ghost sm" disabled={state !== 'idle' || !client} onClick={() => void (async () => {
      if (!client || !saved.current) return;
      setState('busy');
      try { const r = await client.dictateLearning(id, saved.current); if (mounted.current) { onText(r.text, r.audio); setError(''); } }
      catch (e) { if (mounted.current) setError(errText(e)); } finally { if (mounted.current) setState('idle'); }
    })()}>{t('fail.retry')}</button>}
  </div>;
}
