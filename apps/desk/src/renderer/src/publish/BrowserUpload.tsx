// "Upload in your browser": a manual helper, never a sign-in. The platform's upload page opens in her default
// browser (where she is signed in herself), the video is shown in Finder to drag in, and the title / description /
// tags go to the clipboard one at a time. She presses Publish there, then pastes the link to mark the post posted.
import { useEffect, useState } from 'react';
import { Check, Copy, ExternalLink, FolderOpen, Image } from 'lucide-react';
import type { PostPackageMsg } from '../../../shared/publish/apiPlatforms';
import { t } from '../i18n';
import { Sheet } from '../settings/kit';
import { errText } from '../v4/msg';
import { useUi } from '../v4/ui';
import { CaptionFiles } from './CaptionFiles';
import './publish.css';

export function UploadInBrowserSheet({ postId, pf, onClose, onPosted }: { postId: string; pf: string; onClose: () => void; onPosted: (url: string) => void }) {
  const ui = useUi();
  const [pkg, setPkg] = useState<PostPackageMsg | null>(null);
  const [done, setDone] = useState<Set<string>>(new Set());
  const [url, setUrl] = useState('');
  useEffect(() => {
    let active = true;
    setPkg(null);
    setDone(new Set());
    setUrl('');
    void window.desk.publish
      .postPackage(postId)
      .then(value => { if (active) setPkg(value); })
      .catch((e) => {
        if (!active) return;
        ui.toast(errText(e), { error: true });
        onClose();
      });
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [postId]);
  const mark = (k: string) => setDone((s) => new Set(s).add(k));
  const copy = async (k: string, text: string) => {
    await window.desk.copyText(text);
    mark(k);
    ui.toast(t('ub.copied', { pf }));
  };
  const step = (k: string, icon: React.ReactNode, label: string, run: () => void | Promise<void>, preview?: string) => (
    <li key={k} className={`ub-step ${done.has(k) ? 'done' : ''}`} data-testid={`ub-${k}`} data-done={done.has(k)}>
      <button className="btn" onClick={() => void run()}>
        {done.has(k) ? <Check className="ico" /> : icon}
        {label}
      </button>
      {preview !== undefined && <span className="muted small clamp1">{preview || t('ub.empty')}</span>}
    </li>
  );
  const okUrl = /^https:\/\/\S+$/.test(url.trim());
  return (
    <Sheet title={t('ub.title')} onClose={onClose} testId="ub-sheet">
      <p className="muted small">{t('ub.lead')}</p>
      {!pkg ? (
        <div className="pb-loading" aria-busy="true" />
      ) : (
        <ol className="ub-steps">
          {pkg.uploadUrl &&
            step('open', <ExternalLink className="ico" />, t('ub.s.open', { pf }), async () => {
              await window.desk.openExternal(pkg.uploadUrl!);
              mark('open');
            })}
          {step('reveal', <FolderOpen className="ico" />, t('ub.s.reveal'), async () => {
            await window.desk.showItem(pkg.video);
            mark('reveal');
          })}
          {pkg.title && step('title', <Copy className="ico" />, t('ub.s.title'), () => copy('title', pkg.title), pkg.title)}
          {step('desc', <Copy className="ico" />, t('ub.s.desc'), () => copy('desc', pkg.description), pkg.description.split('\n')[0])}
          {pkg.tags.length > 0 && step('tags', <Copy className="ico" />, t('ub.s.tags'), () => copy('tags', pkg.tags.join(', ')), pkg.tags.join(', '))}
          {pkg.cover &&
            step('cover', <Image className="ico" />, t('ub.s.cover'), async () => {
              await window.desk.showItem(pkg.cover!);
              mark('cover');
            })}
          {!!(pkg.sidecars?.length || pkg.captionIssues?.length) && <li><CaptionFiles pkg={pkg} onReveal={path => { void window.desk.showItem(path).catch(e => ui.toast(errText(e), { error: true })); }} /></li>}
          <li className="ub-step col" style={{ alignItems: 'stretch', gap: 6 }}>
            <span className="small">{t('ub.s.done')}</span>
            <span className="row" style={{ gap: 8 }}>
              <input className="input" style={{ flex: 1 }} value={url} onChange={(e) => setUrl(e.target.value)} placeholder={t('pl.post.urlPh')} aria-label={t('pl.post.urlPh')} data-testid="ub-url" />
              <button className="btn primary" disabled={!okUrl} onClick={() => onPosted(url.trim())} data-testid="ub-posted">
                {t('pl.post.markPosted')}
              </button>
            </span>
          </li>
        </ol>
      )}
    </Sheet>
  );
}
