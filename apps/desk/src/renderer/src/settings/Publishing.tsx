// Settings › Publishing accounts (ux/settings-redesign A4): each account's login state (read from the account's own
// session, so a page she is signed in to counts); the signed-out one gets the page's single primary "Sign in".
// Accounts on platforms she does not post to are listed apart and never nag. Below: how scheduled posts reach her
// (Open at login + menu bar) and the official posting APIs: YouTube signs in with Google in her own browser (official
// Data API, never the built-in browser); the others are documented until they are wired.
import { useEffect, useState } from 'react';
import { ChevronRight, MoreHorizontal, Plus, Send } from 'lucide-react';
import { CAPS } from '../../../shared/edition';
import type { ApiStatusMsg } from '../../../shared/publish/apiPlatforms';
import { fmtAgo, t } from '../i18n';
import { href } from '../lib/router';
import { inUse, useChannels, useChosenPlatforms } from '../v4/Channels';
import { errText } from '../v4/msg';
import { PlatformIcon } from '../v4/PlatformIcon';
import { useUi } from '../v4/ui';
import { Dot, Group, Page, Row, Toggle } from './kit';
import type { SettingsCtx } from './registry';
import { adapterShort, signInChannel } from './status';
import { YT_ADAPTER, YtClientChoice, YtConnectSheet } from '../publish/YouTube';

export function PublishingSection(ctx: Partial<SettingsCtx>) {
  const ui = useUi();
  const { adapters, channels } = useChannels();
  const chosen = useChosenPlatforms();
  const mine = inUse(channels, adapters, chosen);
  const others = channels.filter((c) => !mine.includes(c));
  const firstOut = mine.find((c) => c.login.state === 'out');
  const signed = mine.filter((c) => c.login.state === 'in').length;
  const [ytConnect, setYtConnect] = useState<string | null>(null);
  // YouTube signs in with Google in her browser (official API), never in the built-in browser
  const signIn = (adapterId: string, account: string) => (adapterId === YT_ADAPTER ? setYtConnect(account) : signInChannel(adapterId, account));
  const row = (c: (typeof channels)[number], muted: boolean) => {
    const a = adapters.find((x) => x.id === c.adapterId);
    const st = c.login.state;
    return (
      <div key={`${c.adapterId}/${c.account}`} className={`s2-row ${muted ? 's2-muted' : ''}`} data-testid="settings-channel" data-adapter={c.adapterId} data-in-use={!muted}>
        {a ? <PlatformIcon id={a.packagePlatforms[0]} size={36} /> : <span className="s2-pico plain" />}
        <div className="s2-rtext">
          <div className="s2-rlabel">{a ? adapterShort(a) : c.adapterId}</div>
          <div className="s2-rhint">
            {c.name === c.account ? c.account : `${c.name} · ${c.account}`}
            {muted && ` · ${t('pl.set.notUsed')}`}
          </div>
        </div>
        <div className="s2-rctl">
          <span className={`s2-pill ${st === 'in' ? 'ok' : st === 'out' && !muted ? 'warn' : 'off'}`} data-testid="channel-state" data-state={st}>
            <Dot tone={st === 'in' ? 'ok' : st === 'out' && !muted ? 'warn' : 'off'} />
            {t(`ch.state.${st}`)}
          </span>
          {c.login.at && st === 'in' && <span className="s2-val">{t('s2.ai.checked', { when: fmtAgo(Date.parse(c.login.at) / 1000) })}</span>}
          {st !== 'in' && !muted && (
            <button className={`btn ${c === firstOut ? 'primary' : ''}`} onClick={() => signIn(c.adapterId, c.account)} data-testid="settings-channel-signin">
              {t('ch.login')}
            </button>
          )}
          <button
            className="btn ghost icon"
            aria-label={t('s2.ai.more')}
            onClick={(e) =>
              ui.menu(e, [
                { label: st === 'in' ? t('ch.relogin') : t('ch.login'), run: () => signIn(c.adapterId, c.account) },
                { label: t('s2.pub.manage'), run: () => (location.hash = href({ name: 'channels' })) },
              ])
            }
          >
            <MoreHorizontal className="ico" />
          </button>
        </div>
      </div>
    );
  };
  return (
    <Page title={t('set.channels')} lead={t('s2.pub.lead')} testId="settings-channels">
      <Group title={mine.length ? <span data-testid="settings-signed-count">{t('pl.set.signedIn', { n: signed, total: mine.length })}</span> : undefined}>
        <div className="s2-card">
          {!channels.length && <div className="s2-row s2-rhint">{t('s2.pub.none')}</div>}
          {mine.map((c) => row(c, false))}
          {others.map((c) => row(c, true))}
          <a className="s2-row s2-addrow" href={href({ name: 'channels' })} data-testid="open-channels">
            <Plus className="ico" />
            {t('s2.pub.add')}
          </a>
        </div>
      </Group>
      <Group title={t('pl.set.scheduled')} testId="settings-scheduled">
        <Row label={t('pl.set.atLogin')} hint={t('pl.set.atLoginHint')}>
          <Toggle checked={!!ctx.settings?.openAtLogin} onChange={(v) => void ctx.save?.({ openAtLogin: v })} label={t('pl.set.atLogin')} testId="open-at-login" />
        </Row>
        <div className="s2-row s2-rhint">{t('pl.set.how')}</div>
      </Group>
      <ApiGroup onConnect={setYtConnect} />
      {ytConnect && <YtConnectSheet account={ytConnect} onClose={() => setYtConnect(null)} />}
      <p className="s2-foot">
        <Send className="ico" />
        {t('s2.pub.foot')}
        <a className="s2-link" href={href({ name: 'channels' })}>
          {t('s2.pub.footLink')}
          <ChevronRight className="ico" />
        </a>
      </p>
    </Page>
  );
}

function ApiGroup({ onConnect }: { onConnect: (account: string) => void }) {
  const ui = useUi();
  const [st, setSt] = useState<ApiStatusMsg[] | null>(null);
  const [busy, setBusy] = useState(false);
  const { channels } = useChannels();
  const reload = () => void window.desk.publish.api.status().then(setSt).catch(() => undefined);
  useEffect(() => {
    reload();
    return window.desk.on('publish:channels', reload);
  }, []);
  const run = async (fn: () => Promise<ApiStatusMsg[]>) => {
    setBusy(true);
    try {
      setSt(await fn());
      return true;
    } catch (e) {
      ui.toast(errText(e), { error: true });
      return false;
    } finally {
      setBusy(false);
    }
  };
  if (!st) return null;
  const api = st.find((a) => a.id === 'youtube')!;
  const yt = api.yt;
  const nameOf = (account: string) => channels.find((c) => c.adapterId === YT_ADAPTER && c.account === account)?.name ?? account;
  const addYouTube = async () => {
    try {
      await window.desk.publish.addAccount(YT_ADAPTER, 'main');
      reload();
      onConnect('main');
    } catch (e) {
      ui.toast(errText(e), { error: true });
    }
  };
  return (
    <>
      <Group title={<span className="row" style={{ gap: 8 }}><PlatformIcon id="youtube" size={18} />{t('yt.title')}</span>} testId="settings-api">
        <div className="s2-row s2-rhint">{t('yt.lead')}</div>
        {!CAPS.youtubeApi || !yt ? (
          <div className="s2-row s2-rhint" data-testid="yt-lite">{t('yt.lite')}</div>
        ) : (
          <>
            <div className="s2-row">
              <YtClientChoice yt={yt} apply={setSt} />
            </div>
            {!yt.accounts.length && (
              <Row label={t('yt.acct.none')} testId="api-youtube-none">
                <button className="btn primary" disabled={!yt.hasClient || !api.keychain} onClick={() => void addYouTube()} data-testid="api-youtube-add">
                  {t('yt.acct.add')}
                </button>
              </Row>
            )}
            {yt.accounts.map((a) => (
              <Row
                key={a.account}
                label={nameOf(a.account)}
                hint={a.connected ? (a.channel ? t('yt.acct.connected', { channel: a.channel.title }) : t('yt.acct.connectedPlain')) : t('yt.acct.not')}
                testId="api-youtube"
              >
                <span className={`s2-pill ${a.connected ? 'ok' : 'warn'}`} data-testid="api-youtube-state" data-state={a.connected ? 'in' : 'out'}>
                  <Dot tone={a.connected ? 'ok' : 'warn'} />
                  {a.connected ? t('yt.acct.connectedPlain') : t('yt.acct.not')}
                </span>
                {a.connected ? (
                  <button className="btn ghost" disabled={busy} onClick={() => void run(() => window.desk.publish.api.disconnect(a.account))} data-testid="api-youtube-disconnect">
                    {t('yt.disconnect')}
                  </button>
                ) : (
                  <button className="btn primary" disabled={busy || !yt.hasClient || !api.keychain} onClick={() => onConnect(a.account)} data-testid="api-youtube-connect">
                    {t('yt.signin')}
                  </button>
                )}
              </Row>
            ))}
            {api.connected && (
              <Row label={t('pl.api.auto')} hint={t('ytp.f.atHint')}>
                <Toggle checked={api.auto} onChange={(v) => void run(() => window.desk.publish.api.setAuto(v))} label={t('pl.api.auto')} testId="api-youtube-auto" />
              </Row>
            )}
            {!api.keychain && <div className="s2-row s2-rhint pb-amber">{t('pl.api.noKeychain')}</div>}
            <div className="s2-row s2-rhint">{t('yt.audit')}</div>
          </>
        )}
      </Group>
      <Group title={t('pl.api.title')} testId="settings-api-later">
        <div className="s2-row s2-rhint">{t('pl.api.lead')}</div>
        {st
          .filter((a) => a.availability === 'later')
          .map((a) => (
            <Row key={a.id} label={<span className="row" style={{ gap: 8 }}><PlatformIcon id={a.platforms[0]} size={20} />{t(`pl.api.name.${a.id}` as 'pl.api.name.tiktok')}</span>} hint={t(`pl.api.later.${a.id}` as 'pl.api.later.tiktok')} testId={`api-${a.id}`}>
              <span className="s2-pill off">{t('pl.api.notYet')}</span>
            </Row>
          ))}
      </Group>
    </>
  );
}
