import { useEffect, useRef, useState } from 'react';
import { Mic } from 'lucide-react';
import { t } from '../../i18n';
import { useEngine } from '../../lib/engine';
import { media } from '../../v4/kit';
import { errText } from '../../v4/msg';

/** A voice input tool, not an agent prompt: plain local transcription returns to the editable note field. */
export function VoiceNote({ id, onText, onStart, disabled }: { id: string; onText: (text: string, audio: string) => void; onStart: () => void; disabled: boolean }) {
  const { client } = useEngine();
  const active = useRef<{ recorder: MediaRecorder; stream: MediaStream; session: string; dir: string; t0: number; chain: Promise<unknown>; seq: number } | null>(null);
  const [state, setState] = useState<'idle' | 'recording' | 'busy'>('idle');
  const saved = useRef<string | null>(null);
  const [audio, setAudio] = useState<string | null>(null);
  const [error, setError] = useState('');
  useEffect(() => () => {
    const a = active.current;
    if (a) {
      const done = new Promise<void>((resolve) => {
        if (a.recorder.state === 'inactive') return resolve();
        a.recorder.addEventListener('stop', () => resolve(), { once: true }); a.recorder.stop();
      });
      a.stream.getTracks().forEach((x) => x.stop());
      void done.then(() => a.chain).then(() => window.desk.rec.end(a.session, (performance.now() - a.t0) / 1000)).catch(() => undefined);
    }
  }, []);
  const toggle = async () => {
    if (!client || state === 'busy') return;
    setError('');
    try {
      const old = active.current;
      if (old) {
        setState('busy');
        await new Promise<void>((resolve) => { old.recorder.addEventListener('stop', () => resolve(), { once: true }); old.recorder.stop(); });
        await old.chain;
        old.stream.getTracks().forEach((x) => x.stop());
        await window.desk.rec.end(old.session, (performance.now() - old.t0) / 1000);
        active.current = null;
        saved.current = old.dir; setAudio(`${old.dir}/mic.webm`);
        const result = await client.dictateLearning(id, old.dir);
        onText(result.text, result.audio);
        setState('idle');
        return;
      }
      setState('busy');
      const permission = await window.desk.rec.ask('microphone');
      if (!permission) throw new Error(t('learning.micDenied'));
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      const mime = ['audio/webm;codecs=opus', 'audio/webm'].find((x) => MediaRecorder.isTypeSupported(x));
      const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      const result = await window.desk.rec.begin({ slug: 'thought', title: t('learning.voiceThought'), script: [], tracks: ['mic'], mime: { mic: recorder.mimeType } });
      const row = { recorder, stream, session: result.sessionId, dir: result.dir, t0: performance.now(), chain: Promise.resolve() as Promise<unknown>, seq: 0 };
      recorder.ondataavailable = (event) => {
        if (!event.data.size) return;
        row.chain = row.chain.then(async () => window.desk.rec.chunk({ sessionId: row.session, track: 'mic', seq: row.seq++, data: new Uint8Array(await event.data.arrayBuffer()) }));
      };
      active.current = row;
      onStart();
      recorder.start(500);
      setState('recording');
    } catch (e) {
      active.current?.stream.getTracks().forEach((x) => x.stop());
      active.current = null;
      setState('idle');
      setError(errText(e));
    }
  };
  return <div>
    <button className="btn" disabled={disabled || state === 'busy'} onClick={() => void toggle()} data-testid="learning-dictate"><Mic className="ico" />{state === 'recording' ? t('learning.stopDictation') : state === 'busy' ? t('learning.transcribing') : t('learning.dictate')}</button>
    {error && <p role="alert">{error}</p>}
    {audio && <audio controls src={media(audio)} style={{ maxWidth: '100%', marginTop: 8 }} />}
    {error && saved.current && <button className="btn ghost sm" disabled={state !== 'idle'} onClick={() => void (async () => {
      if (!client || !saved.current) return;
      setState('busy');
      try { const r = await client.dictateLearning(id, saved.current); onText(r.text, r.audio); setError(''); }
      catch (e) { setError(errText(e)); } finally { setState('idle'); }
    })()}>{t('fail.retry')}</button>}
  </div>;
}
