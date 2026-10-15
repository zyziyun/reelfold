import type { ChannelMsg } from '../../../shared/channels';
import { postAccount } from '../../../shared/publish/account';
import type { CalendarPost } from '../../../shared/v04';
import { t } from '../i18n';

/** A removed saved account stays visible; it never redirects to another one. */
export function PostAccount({ post, channels, disabled, onChange }: {
  post: CalendarPost; channels: ChannelMsg[]; disabled?: boolean;
  onChange: (account: string | null) => void;
}) {
  const value = postAccount(channels.map((c) => c.account), post.account);
  const missing = !!post.account && !channels.some((c) => c.account === post.account);
  return (
    <label className="col small" style={{ gap: 6, marginBlock: 12 }}>
      {t('pl.account.label')}
      <select className="input" value={missing ? post.account! : value ?? ''} disabled={disabled || post.state === 'posted'}
        onChange={(e) => onChange(e.target.value || null)} data-testid="post-account">
        <option value="" disabled>{t(channels.length ? 'pl.account.choose' : 'pl.account.none')}</option>
        {missing && <option value={post.account!} disabled>{t('pl.account.missing', { account: post.account! })}</option>}
        {channels.map((c) => <option key={c.account} value={c.account}>{c.name === c.account ? c.name : `${c.name} · ${c.account}`}</option>)}
      </select>
      {(missing || (!value && channels.length > 1)) && <span className="pb-amber">{t(missing ? 'pl.account.removed' : 'pl.account.required')}</span>}
    </label>
  );
}
