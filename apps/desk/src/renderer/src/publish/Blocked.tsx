// What the built-in browser's slot shows when a sign-in provider refused it (Google "This browser or app may not be
// secure", Facebook "unsupported browser"): a plain explanation and the next step, instead of the raw error page
// (main hides that page). The platform's own login (email / phone / QR) still works there; Upload in your browser
// always does.
import { ShieldAlert } from 'lucide-react';
import type { EmbedBlock } from '../../../shared/publish/embedBlock';
import { t } from '../i18n';
import './publish.css';

export function BlockedNotice({ blocked, pf, onBack, onUploadInBrowser }: { blocked: EmbedBlock; pf: string; onBack: () => void; onUploadInBrowser?: () => void }) {
  const provider = t(`blk.provider.${blocked.provider}`);
  return (
    <div className="blk col" data-testid="blocked-notice" data-provider={blocked.provider}>
      <ShieldAlert className="ico blk-ico" />
      <h3>{t(`blk.${blocked.provider}.title`)}</h3>
      <p>{t(`blk.${blocked.provider}.body`)}</p>
      <p className="muted">{t('blk.otherWay', { pf, provider })}</p>
      <div className="row" style={{ gap: 8, flexWrap: 'wrap', justifyContent: 'center' }}>
        <button className="btn primary" onClick={onBack} data-testid="blocked-back">
          {t('blk.back', { pf })}
        </button>
        {onUploadInBrowser && (
          <button className="btn" onClick={onUploadInBrowser} data-testid="blocked-upload">
            {t('ub.open')}
          </button>
        )}
      </div>
    </div>
  );
}
