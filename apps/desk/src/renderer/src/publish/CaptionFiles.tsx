import type { PostPackageMsg } from '../../../shared/publish/apiPlatforms';
import { t } from '../i18n';
import { langName } from '../lib/langVersions';

/** One compact handoff for API and browser publishing. Browser handoff is manual; API speech upload is explicitly authorized. */
export function CaptionFiles({ pkg, onReveal, automatic = false }: { automatic?: boolean; pkg: PostPackageMsg | null; onReveal: (path: string) => void }) {
  const files = pkg?.sidecars ?? [];
  const issues = pkg?.captionIssues ?? [];
  if (!files.length && !issues.length) return null;
  return <details className="col small" open={issues.length ? true : undefined} data-testid="publish-captions">
    <summary>{t('publish.captions.title')}</summary>
    <p className="muted">{t(automatic ? 'ytp.captionAuto' : 'publish.captions.hint')}</p>
    {files.length > 0 && <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
      {files.map(file => <button key={file.file} className="btn" onClick={() => onReveal(file.file)}>
        {file.role === 'speech' ? t('publish.captions.speech', { language: langName(file.lang), format: file.format.toUpperCase() }) : t('publish.captions.show', { format: file.format.toUpperCase() })}
      </button>)}
    </div>}
    {issues.length > 0 && <p className="pb-amber" role="status">{t('publish.captions.invalid')}</p>}
  </details>;
}
