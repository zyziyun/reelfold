import { useEffect, useRef, useState } from 'react';
import type { LearningReading, LearningSource } from '../../../../shared/learning';
import { t } from '../../i18n';
import { media } from '../../v4/kit';
import { errText } from '../../v4/msg';
import { youtubeBrowserUrl, youtubeSource, youtubeTime } from './source';

export function SourcePlayer({ source, reading, link, browserTime, onTime, seek, pause }: { source?: LearningSource; reading?: LearningReading; link?: string; browserTime?: number; onTime: (t: number) => void; seek: number | null; pause: number }) {
  const [browserError, setBrowserError] = useState('');
  const video = useRef<HTMLVideoElement | null>(null);
  const iframe = useRef<HTMLIFrameElement | null>(null);
  const yt = link ? youtubeSource(link) : null;
  const videoId = yt?.id;
  useEffect(() => {
    if (!pause) return;
    video.current?.pause();
    iframe.current?.contentWindow?.postMessage(JSON.stringify({ event: 'command', func: 'pauseVideo', args: [] }), 'https://www.youtube-nocookie.com');
  }, [pause]);
  useEffect(() => {
    if (seek !== null && video.current) video.current.currentTime = seek;
  }, [seek]);
  useEffect(() => {
    if (!videoId) return;
    const receive = (e: MessageEvent) => {
      if (e.origin !== 'https://www.youtube-nocookie.com' || e.source !== iframe.current?.contentWindow) return;
      const time = youtubeTime(e.data);
      if (time !== null) onTime(time);
    };
    window.addEventListener('message', receive);
    return () => window.removeEventListener('message', receive);
  }, [videoId, onTime]);
  if (reading) return <article className="ux-opt" data-testid="learning-source-reading">
    <h3>{reading.path.split(/[\\/]/).pop()}</h3>
    {reading.unavailable ? <p role="alert">{t('learning.readingUnavailable')}</p> : <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 500, overflow: 'auto', font: 'inherit' }}>{reading.text}</pre>}
    {reading.truncated && <p className="small muted">{t('learning.readingTruncated')}</p>}
  </article>;
  if (source?.image) return <img src={media(source.path)} alt={t('learning.sourcePage')} style={{ maxWidth: '100%', maxHeight: 500, objectFit: 'contain' }} />;
  if (source) return <video ref={video} src={media(source.path)} controls playsInline onTimeUpdate={(e) => onTime(e.currentTarget.currentTime)} style={{ width: '100%', maxHeight: 480 }} data-testid="learning-source-video" />;
  if (yt) return <div>
    <iframe ref={iframe} key={yt.id} src={yt.embed} title={t('learning.youtubePlayer')} allow="accelerometer; encrypted-media; gyroscope; picture-in-picture; fullscreen" allowFullScreen referrerPolicy="strict-origin-when-cross-origin" style={{ width: '100%', aspectRatio: '16/9', minHeight: 240, border: 0 }} data-testid="learning-youtube" onLoad={() => iframe.current?.contentWindow?.postMessage(JSON.stringify({ event: 'listening', id: 'reelfold-learning' }), 'https://www.youtube-nocookie.com')} />
    <button className="btn" data-testid="learning-youtube-browser" onClick={() => {
      setBrowserError('');
      void window.desk.openExternal(youtubeBrowserUrl(link!, browserTime)!).catch((e) => setBrowserError(errText(e)));
    }}>{t('learning.youtubeBrowser')}</button>
    <p className="small muted">{t('learning.youtubeLoginHint')}</p>
    {browserError && <p role="alert">{browserError}</p>}
  </div>;
  if (link) return <div className="ux-opt"><p>{t('learning.webHint')}</p><button className="btn" onClick={() => void window.desk.openExternal(link)} data-testid="learning-open-site">{t('learning.openOriginal')}</button></div>;
  return <div className="ux-opt muted">{t('learning.pickSource')}</div>;
}
