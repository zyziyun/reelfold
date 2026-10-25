// YouTube through the official Data API: which Google OAuth client signs in (Reelfold's or her own Google Cloud
// client, with the setup guide), "Sign in with Google in your browser" per YouTube account, and the publish form of
// one post (title, description, tags, category, visibility, now / at a time, made for kids, altered content, Short,
// thumbnail, playlist). Uploading starts only from her Publish / Schedule click.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CheckCircle2, Copy, ExternalLink, Loader2, TriangleAlert, Upload } from 'lucide-react';
import { CAPS } from '../../../shared/edition';
import { apiDeliveryState, apiProcessingFailed, shortsFit, type ApiStatusMsg, type PostPackageMsg, type YtAccountMsg, type YtPublishResult, type YtResumeInfo, type YtStatusMsg } from '../../../shared/publish/apiPlatforms';
import type { CalendarPost } from '../../../shared/v04';
import { fmtDate, t } from '../i18n';
import type { MessageKey } from '../i18n';
import { Sheet } from '../settings/kit';
import { errText } from '../v4/msg';
import { useUi } from '../v4/ui';
import { CaptionFiles } from './CaptionFiles';
import './publish.css';

export const YT_ADAPTER = 'youtube-studio';
const CATEGORIES = ['22', '24', '27', '28', '26', '1', '10', '20', '23', '17', '19', '15', '25', '29', '2'];

/** Shared settings/login status reader. A late read must not undo a completed account change. */
export function usePublishingApi() {
  const [all, setAll] = useState<ApiStatusMsg[] | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const generation = useRef(0);
  const apply = useCallback((value: ApiStatusMsg[]) => {
    generation.current++;
    setAll(value);
    setError('');
    setLoading(false);
  }, []);
  const reload = useCallback(async () => {
    const request = ++generation.current;
    setLoading(true);
    setError('');
    try {
      const value = await window.desk.publish.api.status();
      if (request === generation.current) setAll(value);
    } catch (e) {
      if (request === generation.current) setError(errText(e).replace(/^Error invoking remote method '[^']+': (Error: )?/, ''));
    } finally {
      if (request === generation.current) setLoading(false);
    }
  }, []);
  useEffect(() => {
    void reload();
    const off = window.desk.on('publish:channels', () => void reload());
    // Invalidate the latest request, including reloads started after this effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    return () => { generation.current++; off(); };
  }, [reload]);
  return { all, error, loading, apply, reload };
}

export function ApiStatusFeedback({ error, loading, reload }: { error: string; loading: boolean; reload: () => Promise<void> }) {
  if (!error) return loading ? <div className="pb-loading" aria-busy="true" data-testid="api-status-loading" /> : null;
  return <div className="pl-card" role="alert" data-testid="api-status-error">
    <span>{error}</span>
    <button className="btn" onClick={() => void reload()} data-testid="api-status-retry">{t('c.retry')}</button>
  </div>;
}

/** The YouTube API status, refreshed when an account's state changes. */
export function useYt() {
  const state = usePublishingApi();
  const api = state.all?.find((a) => a.id === 'youtube') ?? null;
  return { ...state, api, yt: api?.yt ?? null };
}

export const ytAccount = (yt: YtStatusMsg | null, account: string): YtAccountMsg | null => yt?.accounts.find((a) => a.account === account) ?? null;

/** Reelfold's Google app or her own Google Cloud client. */
export function YtClientChoice({ yt, apply }: { yt: YtStatusMsg; apply: (s: ApiStatusMsg[]) => void }) {
  const ui = useUi();
  const [guide, setGuide] = useState(false);
  const run = async (fn: () => Promise<ApiStatusMsg[]>) => {
    try {
      apply(await fn());
    } catch (e) {
      ui.toast(errText(e), { error: true });
    }
  };
  const own = yt.source === 'own';
  return (
    <div className="col yt-client" style={{ gap: 6 }} data-testid="yt-client" data-source={yt.source ?? 'none'}>
      <span className="small muted">{t('yt.how')}</span>
      {yt.builtin ? (
        <label className="row yt-radio">
          <input type="radio" name="yt-client" checked={yt.source === 'reelfold'} onChange={() => void run(() => window.desk.publish.api.useBuiltin())} data-testid="yt-client-reelfold" />
          <span className="col" style={{ gap: 2 }}>
            <b>{t('yt.how.reelfold')}</b>
            <span className="muted small">{t('yt.how.reelfoldHint')}</span>
          </span>
        </label>
      ) : (
        <span className="muted small" data-testid="yt-no-builtin">
          {t('yt.how.noBuiltin')}
        </span>
      )}
      <label className="row yt-radio">
        <input type="radio" name="yt-client" checked={own} onChange={() => (yt.ownClientId ? void run(() => window.desk.publish.api.setClient(yt.ownClientId!)) : setGuide(true))} data-testid="yt-client-own" />
        <span className="col" style={{ gap: 2 }}>
          <b>{t('yt.how.own')}</b>
          <span className="muted small">{own && yt.ownClientId ? t('yt.own.set', { id: yt.ownClientId.replace(/^(.{10}).*(\.apps\.googleusercontent\.com)$/, '$1…$2') }) : t('yt.how.ownHint')}</span>
        </span>
      </label>
      <span className="row" style={{ gap: 6, paddingLeft: 26 }}>
        <button className="btn sm" onClick={() => setGuide(true)} data-testid="yt-own-add">
          {yt.ownClientId ? t('yt.own.change') : t('yt.own.add')}
        </button>
        {yt.ownClientId && (
          <button className="btn ghost sm" onClick={() => void run(() => window.desk.publish.api.disconnect(undefined, true))} data-testid="yt-own-remove">
            {t('yt.own.remove')}
          </button>
        )}
      </span>
      {guide && <YtGuideSheet onClose={() => setGuide(false)} onSaved={(s) => (apply(s), setGuide(false))} />}
    </div>
  );
}

/** Her own Google Cloud OAuth client: the steps, then the ID (and the secret Google shows with Desktop-app clients). */
export function YtGuideSheet({ onClose, onSaved }: { onClose: () => void; onSaved: (s: ApiStatusMsg[]) => void }) {
  const ui = useUi();
  const [cid, setCid] = useState('');
  const [secret, setSecret] = useState('');
  const [busy, setBusy] = useState(false);
  const steps = (['yt.guide.s1', 'yt.guide.s2', 'yt.guide.s3', 'yt.guide.s4', 'yt.guide.s5', 'yt.guide.s6'] as const).map((k) => t(k));
  const copyGuide = async () => {
    try {
      await window.desk.copyText([t('yt.guide.title'), t('yt.guide.lead'), ...steps.map((line, i) => `${i + 1}. ${line}`), t('yt.guide.note')].join('\n\n'));
      ui.toast(t('yt.guide.copied'));
    } catch (e) { ui.toast(errText(e), { error: true }); }
  };
  const ok = /^[\w.-]{5,200}\.apps\.googleusercontent\.com$/.test(cid.trim());
  const save = async () => {
    setBusy(true);
    try {
      onSaved(await window.desk.publish.api.setClient(cid.trim(), secret.trim() || undefined));
    } catch (e) {
      ui.toast(errText(e), { error: true });
    } finally {
      setBusy(false);
    }
  };
  return (
    <Sheet
      title={t('yt.guide.title')}
      onClose={onClose}
      testId="yt-guide"
      footer={
        <button className="btn primary" disabled={busy || !ok} onClick={() => void save()} data-testid="yt-guide-save">
          {t('yt.save')}
        </button>
      }
    >
      <p className="muted small sel">{t('yt.guide.lead')}</p>
      <ol className="yt-steps small sel" data-testid="yt-guide-steps">
        {steps.map((line, i) => <li key={i}>{line}</li>)}
      </ol>
      <button className="btn sm" onClick={() => void copyGuide()} data-testid="yt-guide-copy">
        <Copy className="ico" />{t('yt.guide.copy')}
      </button>
      <button className="btn sm" onClick={() => void window.desk.openExternal('https://console.cloud.google.com/apis/credentials')}>
        <ExternalLink className="ico" />
        {t('yt.guide.open')}
      </button>
      <label className="col small" style={{ gap: 4 }}>
        {t('yt.clientId')}
        <input className="input mono" value={cid} onChange={(e) => setCid(e.target.value)} placeholder="1234-abc.apps.googleusercontent.com" data-testid="yt-client-id" autoFocus />
      </label>
      <label className="col small" style={{ gap: 4 }}>
        {t('yt.clientSecret')}
        <input className="input mono" type="password" value={secret} onChange={(e) => setSecret(e.target.value)} data-testid="yt-client-secret" />
        <span className="muted">{t('yt.clientSecretHint')}</span>
      </label>
      <p className="muted small sel">{t('yt.guide.note')}</p>
    </Sheet>
  );
}

/** "Sign in with Google in your browser" for one YouTube account: the permissions first, then the system browser. */
export function YtConnectSheet({ account, onClose, onDone }: { account: string; onClose: () => void; onDone?: (s: ApiStatusMsg[]) => void }) {
  const ui = useUi();
  const { api, yt, apply, error, loading, reload } = useYt();
  const [waiting, setWaiting] = useState(false);
  const [playlists, setPlaylists] = useState(false);
  const close = () => {
    if (waiting) void window.desk.publish.api.cancel();
    onClose();
  };
  const go = async () => {
    setWaiting(true);
    try {
      const s = await window.desk.publish.api.connect(account, playlists);
      apply(s);
      const a = ytAccount(s.find((x) => x.id === 'youtube')?.yt ?? null, account);
      ui.toast(t('yt.connected', { channel: a?.channel?.title ?? account }));
      onDone?.(s);
      onClose();
    } catch (e) {
      if (!/cancelled/.test(errText(e))) ui.toast(errText(e), { error: true });
    } finally {
      setWaiting(false);
    }
  };
  return (
    <Sheet
      title={t('yt.connectTitle')}
      onClose={close}
      testId="yt-connect"
      footer={
        waiting ? (
          <span className="row" style={{ gap: 8 }}>
            <Loader2 className="ico spin" />
            <span className="muted">{t('yt.waiting')}</span>
            <button className="btn" onClick={() => void window.desk.publish.api.cancel()} data-testid="yt-connect-cancel">
              {t('yt.cancel')}
            </button>
          </span>
        ) : (
          <button className="btn primary" disabled={loading || !!error || !yt?.hasClient || !api?.keychain} onClick={() => void go()} data-testid="yt-connect-go">
            {t('yt.connectGo')}
          </button>
        )
      }
    >
      {!CAPS.youtubeApi ? (
        <p>{t('yt.lite')}</p>
      ) : error || loading ? (
        <ApiStatusFeedback error={error} loading={loading} reload={reload} />
      ) : !yt ? (
        <p>{t('yt.lite')}</p>
      ) : (
        <>
          {!yt.hasClient || !yt.builtin ? <YtClientChoice yt={yt} apply={apply} /> : null}
          <p>{t('yt.scopes')}</p>
          <label className="row small" style={{ gap: 6 }}>
            <input type="checkbox" checked={playlists} onChange={(e) => setPlaylists(e.target.checked)} data-testid="yt-connect-playlists" />
            {t('yt.playlistsScope')}
          </label>
          <p className="muted small">{t('yt.revoke')}</p>
          {!api?.keychain && <p className="pb-amber small">{t('pl.api.noKeychain')}</p>}
        </>
      )}
    </Sheet>
  );
}

type Phase = { k: 'form' } | { k: 'uploading'; pct: number } | { k: 'done'; r: YtPublishResult };

const pad = (n: number) => String(n).padStart(2, '0');
const localAt = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;

/** A post's YouTube form; Publish / Schedule is her click. */
export function YtPublishForm({ post, account, result, onPosted, onBusy, immediate = false }: { onBusy?: (busy: boolean) => void; immediate?: boolean; post: CalendarPost; account: string; result?: YtPublishResult | null; onPosted: (r: YtPublishResult) => void }) {
  const ui = useUi();
  const { yt, apply, error, loading, reload } = useYt();
  const acct = ytAccount(yt, account);
  const [pkg, setPkg] = useState<PostPackageMsg | null>(null);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [tags, setTags] = useState('');
  const [categoryId, setCategoryId] = useState('22');
  const [privacy, setPrivacy] = useState<'public' | 'unlisted' | 'private'>('public');
  const due = useMemo(() => new Date(`${post.at}:00`), [post.at]);
  const ahead = due.getTime() - Date.now() > 10 * 60_000;
  const [when, setWhen] = useState<'now' | 'at'>(!immediate && ahead ? 'at' : 'now');
  const [at, setAt] = useState(post.at);
  const [kids, setKids] = useState<boolean | null>(null);
  const [synthetic, setSynthetic] = useState(false);
  const [thumb, setThumb] = useState(true);
  const [short, setShort] = useState(post.platform.startsWith('youtube-shorts'));
  const [playlist, setPlaylist] = useState('');
  const playlistToast = ui.toast;
  const [lists, setLists] = useState<{ id: string; title: string }[] | null>(null);
  const [phase, setPhase] = useState<Phase>({ k: 'form' });
  const [pending, setPending] = useState<YtResumeInfo | null>();
  const [pendingError, setPendingError] = useState('');
  const [pendingReload, setPendingReload] = useState(0);
  useEffect(() => {
    if (result || phase.k === 'done') return;
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const read = async () => {
      try {
        const info = await window.desk.publish.api.pendingUpload(post.id);
        if (!active) return;
        setPending(info);
        setPendingError('');
        if (info?.busy) timer = setTimeout(() => void read(), 3000);
      } catch (e) { if (active) setPendingError(errText(e)); }
    };
    void read();
    return () => { active = false; clearTimeout(timer); };
  }, [post.id, phase.k, result, pendingReload]);
  const resume = async () => {
    if (!pending || pending.busy) return;
    setPhase({ k: 'uploading', pct: 0 });
    try {
      const r = await window.desk.publish.api.resume(post.id, pending.account);
      setPhase({ k: 'done', r });
      onPosted(r);
    } catch (e) {
      setPhase({ k: 'form' });
      ui.toast(errText(e), { error: true });
    }
  };

  useEffect(() => { onBusy?.(phase.k === 'uploading'); return () => onBusy?.(false); }, [phase.k, onBusy]);
  const [connect, setConnect] = useState(false);
  const [checking, setChecking] = useState(false);
  const refresh = async () => {
    setChecking(true);
    try { onPosted(await window.desk.publish.api.refresh(post.id)); }
    catch (e) { ui.toast(errText(e), { error: true }); }
    finally { setChecking(false); }
  };

  useEffect(() => {
    let active = true;
    setPkg(null);
    if (result) return; // Status checks need the platform receipt, not the original local file.
    void window.desk.publish
      .postPackage(post.id)
      .then((p) => {
        if (!active) return;
        setPkg(p);
        setTitle(p.title);
        setDescription(p.description);
        setTags(p.tags.join(', '));
      })
      .catch((e) => { if (active) ui.toast(errText(e), { error: true }); });
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [post.id, !!result]);
  useEffect(() => {
    let active = true;
    setLists(null);
    setPlaylist('');
    if (!acct?.connected) return;
    void window.desk.publish.api
      .playlists(account)
      .then(value => { if (active) setLists(value); })
      .catch(e => {
        if (!active) return;
        setLists([]);
        playlistToast(errText(e), { error: true });
      });
    return () => { active = false; };
  }, [acct?.connected, account, playlistToast]);
  useEffect(
    () =>
      window.desk.on('publish:ytProgress', (d) => {
        const p = d as { postId: string; sent: number; total: number };
        if (p.postId === post.id) setPhase({ k: 'uploading', pct: Math.floor((p.sent / Math.max(1, p.total)) * 100) });
      }),
    [post.id],
  );

  const fit = pkg ? shortsFit(pkg) : null;
  const shortOk = !!fit?.ok;
  const publish = async () => {
    if (kids === null || !pkg) return;
    setPhase({ k: 'uploading', pct: 0 });
    try {
      const r = await window.desk.publish.api.publish({
        postId: post.id,
        account,
        title: title.trim(),
        description,
        tags: tags.split(/[,，\n]/).map((x) => x.trim()).filter(Boolean),
        categoryId,
        privacy,
        publishAt: when === 'at' ? at : null,
        madeForKids: kids,
        synthetic,
        short: short && shortOk,
        thumbnail: thumb && !!pkg.cover,
        playlistId: playlist || null,
      });
      setPhase({ k: 'done', r });
      onPosted(r);
    } catch (e) {
      setPhase({ k: 'form' });
      ui.toast(errText(e), { error: true });
    }
  };

  // what YouTube answered (kept by the page: this form may be mounted again while the calendar reloads)
  const sent = result ?? (phase.k === 'done' ? phase.r : null);
  if (!CAPS.youtubeApi) return null;
  if (!sent && (error || loading)) return <ApiStatusFeedback error={error} loading={loading} reload={reload} />;
  if (!acct?.connected && !sent)
    return (
      <div className="pl-card" data-testid="ytp-connect">
        <Upload className="ico" />
        <div className="col" style={{ gap: 8 }}>
          <span>{t('ytp.connectFirst')}</span>
          <button className="btn primary" onClick={() => setConnect(true)} data-testid="ytp-signin">
            {t('yt.signin')}
          </button>
        </div>
        {connect && <YtConnectSheet account={account} onClose={() => setConnect(false)} />}
      </div>
    );
  if (sent) {
    const r = sent;
    const failed = apiProcessingFailed(r);
    const processing = r.uploadStatus === 'uploaded' || r.uploadStatus === 'unknown';
    return (
      <div className={`pl-card ${r.lockedPrivate || failed ? 'warn' : 'ok'}`} data-testid="ytp-done" data-privacy={r.privacy} data-locked={r.lockedPrivate}>
        {r.lockedPrivate || failed ? <TriangleAlert className="ico" /> : <CheckCircle2 className="ico" />}
        <div className="col" style={{ gap: 6 }}>
          <b>{failed ? t('ytp.status.failed', { reason: r.failureReason ?? r.uploadStatus! }) : apiDeliveryState(r) === 'scheduled' ? t('ytp.done.scheduled', { when: fmtDate(r.publishAt!, { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }) }) : processing ? t('ytp.status.processing') : apiDeliveryState(r) === 'posted' ? t('ytp.done.now') : t('ytp.done.private', { privacy: t(`ytp.f.${['public', 'private', 'unlisted'].includes(r.privacy) ? r.privacy : 'unknown'}` as MessageKey) })}</b>
          {processing && apiDeliveryState(r) === 'scheduled' && <span className="muted small">{t('ytp.status.processing')}</span>}
          {r.checkedAt && <span className="muted small" data-testid="ytp-checked">{t('ytp.status.checked', { when: fmtDate(r.checkedAt, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) })}</span>}
          <button className="pb-link" disabled={checking || !acct?.connected} onClick={() => void refresh()} data-testid="ytp-refresh">{checking ? t('ytp.status.checking') : t('ytp.status.refresh')}</button>
          {r.lockedPrivate && <span className="small">{t('ytp.locked')}</span>}
          {r.warnings.length > 0 && <span className="muted small">{t('ytp.notes', { list: r.warnings.join(' · ') })}</span>}
          <button className="pb-link" onClick={() => void window.desk.openExternal(r.url)} data-testid="ytp-url">
            {r.url} <ExternalLink className="ico" />
          </button>
        </div>
      </div>
    );
  }
  if (!acct) return null;
  const busy = phase.k === 'uploading';
  if (pendingError || pending === undefined) return (
    <div className="pl-card" data-testid="ytp-recovery-loading">
      <span>{pendingError || t('ytp.status.checking')}</span>
      {pendingError && <button className="btn" onClick={() => setPendingReload(n => n + 1)}>{t('ytp.status.refresh')}</button>}
    </div>
  );
  if (pending) return (
    <div className="pl-card warn" data-testid="ytp-resume-card">
      <TriangleAlert className="ico" />
      <div className="col" style={{ gap: 12 }}>
        <b>{t('ytp.resume.title')}</b>
        <span>{t('ytp.resume.account', { account: pending.account })}</span>
        <span>{t('ytp.f.privacy')}: {pending.publishAt ? t('ytp.resume.scheduledVisibility') : t(`ytp.f.${['public', 'private', 'unlisted'].includes(pending.privacy) ? pending.privacy : 'unknown'}` as MessageKey)}</span>
        <span>{t('ytp.f.when')}: {pending.publishAt ? fmtDate(pending.publishAt, { dateStyle: 'medium', timeStyle: 'short' }) : t('ytp.f.now')}</span>
        <span className="muted small">{t('ytp.resume.hint')}</span>
        {pending.account !== account && <span>{t('ytp.resume.accountChanged')}</span>}
        {!pending.canResume && <span>{t('ytp.resume.unavailable')}</span>}
        <button className="btn primary" data-testid="ytp-resume" disabled={busy || pending.busy || !pending.canResume || pending.account !== account} onClick={() => void resume()}>
          {(busy || pending.busy) && <Loader2 className="ico spin" />}
          {busy || pending.busy ? t('ytp.uploading', { pct: phase.k === 'uploading' ? phase.pct : 0 }) : t('ytp.resume.button')}
        </button>
        <button className="pb-link" onClick={() => void window.desk.openExternal('https://studio.youtube.com')}>{t('ytp.resume.studio')} <ExternalLink className="ico" /></button>
      </div>
    </div>
  );
  const atDate = new Date(`${at}:00`);
  const atOk = when === 'now' || atDate.getTime() > Date.now() + 5 * 60_000;
  return (
    <div className="yt-form col" data-testid="ytp-form">
      <div className="col" style={{ gap: 2 }}>
        <h3>{t('ytp.title')}</h3>
        <span className="muted small">{t('ytp.lead', { channel: acct.channel?.title ?? account })}</span>
      </div>
      <label className="col small">
        {t('ytp.f.title')}
        <input className="input" value={title} maxLength={100} onChange={(e) => setTitle(e.target.value)} data-testid="ytp-title" />
        <span className="muted num">{Array.from(title).length} / 100</span>
      </label>
      <label className="col small">
        {t('ytp.f.description')}
        <textarea className="input" rows={6} value={description} onChange={(e) => setDescription(e.target.value)} data-testid="ytp-description" />
      </label>
      <label className="col small">
        {t('ytp.f.tags')}
        <input className="input" value={tags} onChange={(e) => setTags(e.target.value)} placeholder={t('ytp.f.tagsHint')} data-testid="ytp-tags" />
      </label>
      <div className="yt-grid">
        <label className="col small">
          {t('ytp.f.category')}
          <select className="input" value={categoryId} onChange={(e) => setCategoryId(e.target.value)} data-testid="ytp-category">
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {t(`ytp.cat.${c}` as MessageKey)}
              </option>
            ))}
          </select>
        </label>
        <label className="col small">
          {t('ytp.f.privacy')}
          <select className="input" value={when === 'at' ? 'public' : privacy} disabled={when === 'at'} onChange={(e) => setPrivacy(e.target.value as typeof privacy)} data-testid="ytp-privacy">
            {(['public', 'unlisted', 'private'] as const).map((p) => (
              <option key={p} value={p}>
                {t(`ytp.f.${p}`)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <fieldset className="col small yt-field">
        <legend>{t('ytp.f.when')}</legend>
        <label className="row" style={{ gap: 6 }}>
          <input type="radio" checked={when === 'now'} onChange={() => setWhen('now')} data-testid="ytp-now" />
          {t('ytp.f.now')}
        </label>
        <label className="row" style={{ gap: 6 }}>
          <input type="radio" checked={when === 'at'} onChange={() => setWhen('at')} data-testid="ytp-at" />
          {t('ytp.f.at')}
          <input className="input" type="datetime-local" value={at} min={localAt(new Date(Date.now() + 10 * 60_000))} disabled={when !== 'at'} onChange={(e) => setAt(e.target.value)} data-testid="ytp-at-time" />
        </label>
        {when === 'at' && <span className="muted">{t('ytp.f.atHint')}</span>}
      </fieldset>
      <fieldset className="col small yt-field" data-testid="ytp-kids">
        <legend>{t('ytp.f.kids')}</legend>
        <label className="row" style={{ gap: 6 }}>
          <input type="radio" checked={kids === false} onChange={() => setKids(false)} data-testid="ytp-kids-no" />
          {t('ytp.f.kidsNo')}
        </label>
        <label className="row" style={{ gap: 6 }}>
          <input type="radio" checked={kids === true} onChange={() => setKids(true)} data-testid="ytp-kids-yes" />
          {t('ytp.f.kidsYes')}
        </label>
        {kids === null && <span className="pb-amber">{t('ytp.f.kidsNeed')}</span>}
      </fieldset>
      <label className="row small" style={{ gap: 6 }}>
        <input type="checkbox" checked={synthetic} onChange={(e) => setSynthetic(e.target.checked)} data-testid="ytp-synthetic" />
        {t('ytp.f.synthetic')}
      </label>
      <label className="row small" style={{ gap: 6 }} title={fit && !fit.ok ? t(`ytp.f.short.${fit.why}` as MessageKey) : undefined}>
        <input type="checkbox" checked={short && shortOk} disabled={!shortOk} onChange={(e) => setShort(e.target.checked)} data-testid="ytp-short" />
        {t('ytp.f.short')}
        {fit && !fit.ok && <span className="muted">· {t(`ytp.f.short.${fit.why}` as MessageKey)}</span>}
      </label>
      {pkg?.cover && (
        <label className="row small" style={{ gap: 6 }} title={t('ytp.f.thumbHint')}>
          <input type="checkbox" checked={thumb} onChange={(e) => setThumb(e.target.checked)} data-testid="ytp-thumb" />
          {t('ytp.f.thumb')}
        </label>
      )}
      <CaptionFiles pkg={pkg} onReveal={path => { void window.desk.showItem(path).catch(e => ui.toast(errText(e), { error: true })); }} />
      <label className="col small">
        {t('ytp.f.playlist')}
        <span className="row" style={{ gap: 6 }}>
          <select className="input" style={{ flex: 1 }} value={playlist} disabled={!acct.playlists || !lists?.length} onChange={(e) => setPlaylist(e.target.value)} data-testid="ytp-playlist">
            <option value="">{t('ytp.f.playlistNone')}</option>
            {(lists ?? []).map((l) => (
              <option key={l.id} value={l.id}>
                {l.title}
              </option>
            ))}
          </select>
          {!acct.playlists && (
            <button
              className="btn sm"
              onClick={() =>
                void window.desk.publish.api
                  .connect(account, true)
                  .then(apply)
                  .catch((e) => ui.toast(errText(e), { error: true }))
              }
              data-testid="ytp-playlist-allow"
            >
              {t('ytp.f.playlistAllow')}
            </button>
          )}
        </span>
      </label>
      <div className="row" style={{ gap: 8, alignItems: 'center' }}>
        <button className="btn primary lg" disabled={busy || !pkg || kids === null || !title.trim() || !atOk} onClick={() => void publish()} data-testid="ytp-publish">
          {busy ? <Loader2 className="ico spin" /> : <Upload className="ico" />}
          {when === 'at' ? t('ytp.schedule') : t('ytp.publish')}
        </button>
        {phase.k === 'uploading' && <span className="muted num" data-testid="ytp-progress">{t('ytp.uploading', { pct: phase.pct })}</span>}
      </div>
      <p className="muted small">{t('yt.audit')}</p>
    </div>
  );
}
