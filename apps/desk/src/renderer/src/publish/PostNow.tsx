// #/publish/post/<id>: "Time to post" for one scheduled post. Left: the post, what Reelfold did and what is left to
// her; right: the platform's upload page in the built-in browser (her account's own session). Fill sets the file
// made for that platform and types title / text / tags, outlines Publish - she presses it. When the page shows the
// platform's success signal the post becomes "posted" (with its link when the page has one). Opened from the
// notification with ?go=1, the fill starts by itself. A platform published through its official API (YouTube) never
// opens in the built-in browser: the right side is its publish form, and Publish / Schedule is her click. Every
// platform also offers "Upload in your browser" (her default browser, the pieces handed over one by one).
import { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowLeft, Check, CheckCircle2, Copy, ExternalLink, FolderOpen, Loader2, LogIn, RotateCcw, Send, TriangleAlert } from 'lucide-react';
import type { FillStepMsg, PostFillMsg, PublishStateMsg } from '../../../shared/deskApi';
import { adapterFor } from '../../../shared/publish/adapterSchema';
import { apiOnly, publishPath, type YtPublishResult } from '../../../shared/publish/apiPlatforms';
import { CAPS } from '../../../shared/edition';
import type { CalendarPost } from '../../../shared/v04';
import { fmtAgo, fmtDate, getLang, t } from '../i18n';
import { useEngine, useLoad } from '../lib/engine';
import { go, routeQuery } from '../lib/router';
import { useChannels } from '../v4/Channels';
import { platformName } from '../v4/Home';
import { PlatformIcon } from '../v4/PlatformIcon';
import { Thumb } from '../v4/kit';
import { errText } from '../v4/msg';
import { useUi } from '../v4/ui';
import { BrowserPane } from './BrowserPane';
import { UploadInBrowserSheet } from './BrowserUpload';
import { YtPublishForm } from './YouTube';
import { base } from './model';
import { postAccount } from '../../../shared/publish/account';
import { PostAccount } from './PostAccount';
import './publish.css';

type Phase = { k: 'idle' } | { k: 'filling' } | { k: 'filled'; r: Extract<PostFillMsg, { ok: true }> } | { k: 'failed'; r: Extract<PostFillMsg, { ok: false }> } | { k: 'posted'; url: string | null };

export function PostNow({ id }: { id: string }) {
  const ui = useUi();
  const cal = useLoad((c) => c.calendar(), []);
  const { client } = useEngine();
  const { adapters, channels } = useChannels();
  const post: CalendarPost | null = cal.data?.posts.find((p) => p.id === id) ?? null;
  const pf = post ? base(post.platform) : '';
  const adapter = useMemo(() => (pf ? adapterFor(pf, adapters) : undefined), [pf, adapters]);
  const accounts = channels.filter((c) => c.adapterId === adapter?.id);
  const chosen = postAccount(accounts.map((c) => c.account), post?.account);
  const account = accounts.find((c) => c.account === chosen);
  const [savingAccount, setSavingAccount] = useState(false);
  const [apiBusy, setApiBusy] = useState(false);
  const [phase, setPhase] = useState<Phase>({ k: 'idle' });
  const [steps, setSteps] = useState<FillStepMsg[]>([]);
  const [bstate, setBstate] = useState<PublishStateMsg | null>(null);
  const [manual, setManual] = useState<string | null>(null);
  const [autoGo] = useState(() => routeQuery().go === '1');
  const [immediate] = useState(() => routeQuery().now === '1');
  const [inBrowser, setInBrowser] = useState(false);
  /** sent through the API just now: what YouTube answered stays on the page */
  const [ytSent, setYtSent] = useState<YtPublishResult | null>(null);
  const viaApi = !!adapter && apiOnly(adapter.id);
  const zh = getLang() === 'zh-CN';

  useEffect(() => {
    const offs = [
      window.desk.on('publish:state', (s) => setBstate(s as PublishStateMsg)),
      window.desk.on('publish:fillStep', (s) => {
        const st = s as FillStepMsg & { postId?: string };
        if (st.postId === id) setSteps((x) => [...x, st]);
      }),
      window.desk.on('publish:posted', (d) => {
        const p = d as { postId: string; url: string | null };
        if (p.postId === id) {
          setPhase({ k: 'posted', url: p.url });
          cal.reload();
        }
      }),
    ];
    return () => {
      offs.forEach((f) => f());
      void window.desk.publish.hide();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    if (post?.state === 'posted' && phase.k !== 'posted') setPhase({ k: 'posted', url: post.url ?? null });
  }, [post, phase.k]);

  const fill = useCallback(async () => {
    setSteps([]);
    setPhase({ k: 'filling' });
    try {
      const r = await window.desk.publish.fillPost(id, account?.account);
      setPhase(r.ok ? { k: 'filled', r } : { k: 'failed', r });
      cal.reload();
    } catch (e) {
      setPhase({ k: 'idle' });
      ui.toast(errText(e), { error: true });
    }
  }, [id, account?.account, cal, ui]);

  const [started, setStarted] = useState(false);
  useEffect(() => {
    if (autoGo && !started && post && post.state !== 'posted' && adapter && account && adapter.status !== 'todo' && !viaApi) {
      setStarted(true);
      void fill();
    }
  }, [autoGo, started, post, adapter, account, fill, viaApi]);

  const openPage = async (page: 'login' | 'upload') => {
    if (!adapter || !account) return;
    try {
      await window.desk.publish.open(adapter.id, account.account, page);
      await window.desk.publish.navigate(page);
    } catch (e) {
      ui.toast(errText(e), { error: true });
    }
  };
  const chooseAccount = async (account: string | null) => {
    if (!client || !post) return;
    setSavingAccount(true);
    try {
      await client.updatePost(post.id, { account });
      await window.desk.publish.hide();
      setBstate(null);
      setPhase({ k: 'idle' });
      setSteps([]);
      cal.reload();
    } catch (e) { ui.toast(errText(e), { error: true }); }
    finally { setSavingAccount(false); }
  };
  const markPosted = async (url: string) => {
    if (!client || !post) return;
    const u = url.trim();
    if (u && !/^https:\/\/\S+$/.test(u)) return ui.toast(t('pl.post.badUrl'), { error: true });
    try {
      await client.updatePost(post.id, { state: 'posted', via: 'manual', ...(u ? { url: u } : {}) });
      setManual(null);
      setPhase({ k: 'posted', url: u || null });
      cal.reload();
    } catch (e) {
      ui.toast(errText(e), { error: true });
    }
  };

  if (!cal.data) return <div className="scroll pb" data-testid="post-now"><div className="pb-loading" aria-busy="true" /></div>;
  if (!post)
    return (
      <div className="scroll pb" data-testid="post-now">
        <div className="pb-page">
          <p className="muted">{t('pl.post.gone')}</p>
          <button className="btn" onClick={() => go({ name: 'calendar' })}>
            {t('pl.post.back')}
          </button>
        </div>
      </div>
    );

  const browserOpen = !!bstate && !!adapter && bstate.adapterId === adapter.id && !!account && bstate.account === account.account;
  const due = new Date(`${post.at}:00`);
  const late = Date.now() - due.getTime();
  const fail = phase.k === 'failed' ? phase.r : null;
  const choices = adapter?.herChoices ? (zh ? adapter.herChoices.zh : adapter.herChoices.en) : [];

  return (
    <div className="pl-post" data-testid="post-now" data-phase={phase.k}>
      <aside className="pl-side">
        <button className="pb-link muted" onClick={() => go({ name: 'calendar' })}>
          <ArrowLeft className="ico" /> {t('pl.post.back')}
        </button>
        <div className="pb-dclip">
          <Thumb src={post.cover} ratio="3/4" />
          <div className="col" style={{ gap: 6, minWidth: 0 }}>
            <h3 lang="zh-CN" data-testid="post-title">{post.title}</h3>
            <span className="row" style={{ gap: 6 }}>
              <PlatformIcon id={pf} size={18} />
              <b>{platformName(pf)}</b>
              {account && <span className="muted">· {account.name}</span>}
            </span>
            {adapter && <span className="muted small" data-testid="post-path" data-path={publishPath(adapter.id)}>{t(`pp.${publishPath(adapter.id)}`)}</span>}
            <span className={`muted small ${late > 0 && post.state !== 'posted' ? 'pb-amber' : ''}`}>
              {immediate && post.state !== 'posted' ? t('pb.d.publishNow') : fmtDate(due, { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false })}
              {!immediate && late > 60_000 && post.state !== 'posted' ? ` · ${t('pl.due.ago', { when: fmtAgo(due.getTime() / 1000) })}` : ''}
            </span>
          </div>
        </div>

        {adapter && <PostAccount post={post} channels={accounts} disabled={savingAccount || apiBusy || phase.k === 'filling'} onChange={(account) => void chooseAccount(account)} />}
        {phase.k === 'posted' ? (
          <div className="pl-card ok" data-testid="post-posted">
            <CheckCircle2 className="ico" />
            <div className="col" style={{ gap: 6 }}>
              <b>{t('pl.post.posted')}</b>
              {phase.url ? (
                <button className="pb-link" onClick={() => void window.desk.openExternal(phase.url!)} data-testid="post-url">
                  {phase.url} <ExternalLink className="ico" />
                </button>
              ) : (
                <span className="muted small">{t('pl.post.noUrl')}</span>
              )}
            </div>
          </div>
        ) : !adapter ? (
          <div className="pl-card warn">
            <TriangleAlert className="ico" />
            <span>{t('pl.post.noAdapter', { pf: platformName(pf) })}</span>
          </div>
        ) : !account ? (
          <div className="pl-card warn" data-testid="post-no-account">
            <TriangleAlert className="ico" />
            <div className="col" style={{ gap: 8 }}>
              <span>{accounts.length ? t(post.account ? 'pl.account.removed' : 'pl.account.required') : t('pl.post.noAccount', { pf: platformName(pf) })}</span>
              <button className="btn primary" onClick={() => go({ name: 'channels' })}>
                {t('pl.post.addAccount', { pf: platformName(pf) })}
              </button>
            </div>
          </div>
        ) : viaApi ? null : adapter.status === 'todo' || fail?.reason === 'adapter-todo' ? (
          <div className="pl-card warn" data-testid="post-todo">
            <TriangleAlert className="ico" />
            <div className="col" style={{ gap: 8 }}>
              <span>{t('pl.post.todo', { pf: platformName(pf) })}</span>
              <button className="btn" onClick={() => void openPage('upload')}>
                {t('pl.post.openUpload')}
              </button>
            </div>
          </div>
        ) : (
          <>
            {phase.k === 'idle' && (
              <div className="pl-card">
                <Send className="ico" />
                <div className="col" style={{ gap: 8 }}>
                  <span>{t('pl.post.idle', { pf: platformName(pf) })}</span>
                  <button className="btn primary lg" onClick={() => void fill()} data-testid="post-fill">
                    {t('pl.post.fill')}
                  </button>
                </div>
              </div>
            )}
            {phase.k === 'filling' && (
              <div className="pl-card" aria-busy="true">
                <Loader2 className="ico spin" />
                <span>{t('pl.post.filling', { pf: platformName(pf) })}</span>
              </div>
            )}
            {phase.k === 'filled' && (
              <div className="pl-card ok" data-testid="post-filled">
                <Check className="ico" />
                <div className="col" style={{ gap: 6 }}>
                  <b>{phase.r.results.some((r) => r.status !== 'ok') ? t('pl.post.filledPartly') : t('pl.post.filled')}</b>
                  <span className="muted small">{t('pl.post.watching')}</span>
                </div>
              </div>
            )}
            {fail && (
              <div className="pl-card warn" data-testid="post-failed" data-reason={fail.reason}>
                <TriangleAlert className="ico" />
                <div className="col" style={{ gap: 8 }}>
                  <span>{t(`pl.fail.${fail.reason}` as 'pl.fail.no-post', { pf: platformName(pf), detail: fail.detail ?? '' })}</span>
                  {fail.reason === 'login-required' ? (
                    <span className="row" style={{ gap: 8 }}>
                      <button className="btn primary" onClick={() => void openPage('login')} data-testid="post-signin">
                        <LogIn className="ico" />
                        {t('pl.post.signIn', { pf: platformName(pf) })}
                      </button>
                      <button className="btn" onClick={() => void fill()}>
                        {t('pl.post.again')}
                      </button>
                    </span>
                  ) : (
                    <button className="btn" onClick={() => void fill()}>
                      {t('pl.post.again')}
                    </button>
                  )}
                </div>
              </div>
            )}
          </>
        )}

        {steps.length > 0 && (
          <ul className="pl-steps" data-testid="post-steps">
            {steps.map((s, i) => (
              <li key={i} className={s.status} data-field={s.field} data-status={s.status}>
                {s.status === 'ok' ? <Check className="ico" /> : <TriangleAlert className="ico" />}
                {t(`pl.step.${s.field}` as 'pl.step.file')}
                {s.status !== 'ok' && <span className="muted small"> — {t(s.status === 'not-found' ? 'pl.step.notFound' : 'pl.step.error')}</span>}
              </li>
            ))}
          </ul>
        )}

        {phase.k !== 'posted' && adapter && account && (
          <>
            {choices.length > 0 && !viaApi && (
              <>
                <h4>{t('pl.post.yours')}</h4>
                <ul className="pl-choices">
                  {choices.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
              </>
            )}
            {!viaApi && <p className="pb-hint">{zh ? adapter.disclosure.zh : adapter.disclosure.en}</p>}
            <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
              {phase.k === 'filled' && phase.r.cover && (
                <button className="btn sm" onClick={() => void window.desk.showItem((phase as { r: { cover: string } }).r.cover)}>
                  <FolderOpen className="ico" />
                  {t('pl.post.cover')}
                </button>
              )}
              <button className="btn sm" onClick={() => void window.desk.copyText(post.caption ?? '').then(() => ui.toast(t('pl.post.copied')))}>
                <Copy className="ico" />
                {t('pl.post.copy')}
              </button>
              {phase.k === 'filled' && (
                <button className="btn ghost sm" onClick={() => void fill()}>
                  <RotateCcw className="ico" />
                  {t('pl.post.again')}
                </button>
              )}
              <button className="btn sm" onClick={() => setInBrowser(true)} data-testid="post-in-browser">
                <ExternalLink className="ico" />
                {t('ub.open')}
              </button>
              <button className="btn ghost sm" onClick={() => setManual('')} data-testid="post-manual">
                {t('pl.post.manual')}
              </button>
            </div>
            {manual !== null && (
              <div className="row" style={{ gap: 8 }}>
                <input className="input" style={{ flex: 1 }} value={manual} onChange={(e) => setManual(e.target.value)} placeholder={t('pl.post.urlPh')} aria-label={t('pl.post.urlPh')} data-testid="post-manual-url" autoFocus />
                <button className="btn primary" onClick={() => void markPosted(manual)} data-testid="post-manual-ok">
                  {t('pl.post.markPosted')}
                </button>
              </div>
            )}
          </>
        )}
      </aside>
      <section className="pl-browser">
        {viaApi ? (
          (phase.k !== 'posted' || ytSent) && account && CAPS.youtubeApi ? (
            <YtPublishForm key={account.account} immediate={immediate} post={post} account={account.account} result={ytSent} onBusy={setApiBusy} onPosted={(r) => (setYtSent(r), setPhase({ k: 'posted', url: r.url }), cal.reload())} />
          ) : null
        ) : (
          <BrowserPane open={browserOpen} hidden={inBrowser} state={bstate} hint={t('pl.post.slot')} onUploadInBrowser={() => setInBrowser(true)} pf={platformName(pf)} />
        )}
      </section>
      {inBrowser && <UploadInBrowserSheet postId={post.id} pf={platformName(pf)} onClose={() => setInBrowser(false)} onPosted={(url) => (setInBrowser(false), void markPosted(url))} />}
    </div>
  );
}
