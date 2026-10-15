import { useEffect, useRef } from 'react';
import type { LearningSource } from '../../../../shared/learning';
import { t } from '../../i18n';
import { media } from '../../v4/kit';
import { youtubeSource, youtubeTime } from './source';

export function SourcePlayer({ source, link, onTime, seek, pause }: { source?: LearningSource; link?: string; onTime: (t: number) => void; seek: number | null; pause: number }) {
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
  if (source?.image) return <img src={media(source.path)} alt={t('learning.sourcePage')} style={{ maxWidth: '100%', maxHeight: 500, objectFit: 'contain' }} />;
  if (source) return <video ref={video} src={media(source.path)} controls playsInline onTimeUpdate={(e) => onTime(e.currentTarget.currentTime)} style={{ width: '100%', maxHeight: 480 }} data-testid="learning-source-video" />;
  if (yt) return <div>
    <iframe ref={iframe} key={yt.id} src={yt.embed} title={t('learning.youtubePlayer')} allow="accelerometer; encrypted-media; gyroscope; picture-in-picture; fullscreen" allowFullScreen referrerPolicy="strict-origin-when-cross-origin" style={{ width: '100%', aspectRatio: '16/9', minHeight: 240, border: 0 }} data-testid="learning-youtube" onLoad={() => iframe.current?.contentWindow?.postMessage(JSON.stringify({ event: 'listening', id: 'reelfold-learning' }), 'https://www.youtube-nocookie.com')} />
    <p className="small muted">{t('learning.youtubeHint')}</p>
    <button className="btn ghost sm" onClick={() => void window.desk.openExternal(link!)}>{t('learning.openOriginal')}</button>
  </div>;
  if (link) return <div className="ux-opt"><p>{t('learning.webHint')}</p><button className="btn" onClick={() => void window.desk.openExternal(link)} data-testid="learning-open-site">{t('learning.openOriginal')}</button></div>;
  return <div className="ux-opt muted">{t('learning.pickSource')}</div>;
}
