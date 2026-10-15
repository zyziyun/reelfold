import { useEffect, useRef, useState } from 'react';
import type { LearningWorkspace } from '../../../../shared/learning';
import { t, fmtClock } from '../../i18n';
import { useEngine } from '../../lib/engine';
import { errText } from '../../v4/msg';
import { useRecorder } from '../record/useRecorder';
import { ScreenPicker } from '../record/ScreenPicker';

/** Existing crash-safe recorder and screen picker, kept beside the source instead of navigating away. */
export function CameraCapture({ id, onSaved, script }: { id: string; onSaved: (doc: LearningWorkspace) => void; script: string }) {
  const { client } = useEngine();
  const rec = useRecorder();
  const stopRecording = rec.stop;
  useEffect(() => () => {
    void stopRecording().then((take) => take && client?.captureLearning(id, take.dir)).catch(() => undefined);
  }, [id, client, stopRecording]);
  const video = useRef<HTMLVideoElement | null>(null);
  const [screen, setScreen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { if (video.current) video.current.srcObject = rec.stream; }, [rec.stream]);
  const live = ['recording', 'paused', 'stopping'].includes(rec.state);
  const start = async () => {
    setError('');
    try { await rec.start({ slug: 'learning', title: t('learning.creation'), script: script.split('\n').filter(Boolean).slice(0, 300).map((s) => s.slice(0, 500)), studio: false }); }
    catch (e) { setError(errText(e)); }
  };
  const stop = async () => {
    if (!client) return;
    setBusy(true);
    try {
      const take = await rec.stop();
      if (take) onSaved(await client.captureLearning(id, take.dir));
    } catch (e) { setError(errText(e)); }
    finally { setBusy(false); }
  };
  return <section className="learning-capture" data-testid="learning-camera">
    <h3>{t('learning.captureTitle')}</h3>
    {rec.stream && <video ref={video} autoPlay muted playsInline style={{ width: 180, maxHeight: 160 }} data-testid="learning-camera-preview" />}
    <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
      {!rec.stream ? <button className="btn" onClick={() => void rec.open()} data-testid="learning-camera-open">{t('learning.openCamera')}</button> : <>
        <button className="btn" disabled={busy || rec.state === 'stopping'} onClick={() => void (live ? stop() : start())} data-testid="learning-camera-record">{live ? t('rec.stop') : t('learning.recordHere')} {live ? fmtClock(rec.elapsed) : ''}</button>
        {!live && <button className="btn ghost" onClick={() => setScreen(!screen)} data-testid="learning-screen">{t('learning.shareScreen')}</button>}
        {rec.state === 'recording' && <button className="btn" onClick={rec.pause}>{t('rec.pause')}</button>}
        {rec.state === 'paused' && !rec.screenInterrupted && <button className="btn" onClick={rec.resume}>{t('rec.resume')}</button>}
      </>}
    </div>
    {screen && !live && <ScreenPicker on={rec.screenOn} share={rec.shareScreen} stop={rec.stopScreen} done={() => setScreen(false)} />}
    {rec.screenOn && <p className="muted">{t('rec.screenSharing')}</p>}
    {rec.screenInterrupted && <p role="alert">{t('rec.screenFinishTake')}</p>}
    {(error || rec.error) && <p role="alert">{error || rec.error}</p>}
    {busy && <p>{t('rec.saving')}</p>}
  </section>;
}
