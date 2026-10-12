// Home as triage (2026-10 home dashboard), under the composer, each part only when it has something real:
//   chips     - from her own signals (lib/homeSignals): a new recording in a watched folder, a request she keeps
//               sending, a post that can go on more of her platforms, the next episode, a project with clips left
//   Inbox     - "n need you · about m min", the top three with ONE button each that settles it here (a focused sheet,
//               Try again / Sign in in place, the review player), "n more — …", Review in a row, Open inbox
//   Running   - "n jobs · m waiting its turn": the top three cards (the step in words, time left, progress), each
//               opening its live run page; Watch all
//   Going out today - time, platform icons, where each post is (Posted · views / Scheduled / Waiting on …)
// The page is held on a skeleton until every source has answered (no section popping in, no count changing under
// her), and an answer takes the row away at once (Undo brings it back).
import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowRight, ChevronRight, FolderOpen, LayoutGrid, MoreHorizontal, Play, Repeat, Send, Video } from 'lucide-react';
import type { HistoryItem } from '../../../shared/v02';
import type { CalendarPost, InboxItem, OpenRequest } from '../../../shared/v04';
import { fmtMinutes, fmtTime, getLang, t, type MessageKey } from '../i18n';
import { platformName } from '../lib/platformName';
import { useEngine } from '../lib/engine';
import { homeSignals, type HomeSignal } from '../lib/homeSignals';
import { inboxSub, inboxTitle } from '../lib/inboxView';
import { liveText } from '../lib/liveStatus';
import { clipHref, inboxHref, itemTarget, postHref, projectHref, reviewInRow, selHref } from '../lib/nav';
import { href } from '../lib/router';
import { useInbox } from '../lib/inbox';
import { runningJobs } from '../lib/live';
import type { StudioRow } from '../lib/studio';
import { rowHref } from '../lib/studioData';
import { studioEnabled } from '../lib/studioFlag';
import { FailureActions } from './Failure';
import { InboxThumb, ItemPane } from './Inbox';
import { Sk, StatusPill, Thumb } from './kit';
import { itemStatus, type Status4 } from '../lib/status';
import { errText } from './msg';
import { PlatformIcon } from './PlatformIcon';
import { useUi } from './ui';

const list = (xs: string[]) => xs.join(getLang() === 'zh-CN' ? '、' : ', ');
/** "TikTok, Shorts +2" */
function platformsLabel(ids: string[]): string {
  const n = ids.map(platformName);
  return n.length <= 2 ? list(n) : `${list(n.slice(0, 2))} +${n.length - 2}`;
}

// ---------------------------------------------------------------- skeleton
/** The shape of the page while its sources answer: the same blocks, so nothing moves when they land. */
export function HomeSkeleton({ waits = [] }: { waits?: string[] }) {
  return (
    <div data-testid="home-skeleton" aria-busy="true" data-waits={waits.join(' ')}>
      <div className="ux-ideas">
        {[150, 190, 170].map((w) => (
          <Sk key={w} w={w} h={38} r={19} />
        ))}
      </div>
      <section className="ux-sec">
        <Sk w={220} h={18} />
        <div style={{ marginTop: 12 }}>
          <Sk h={204} r={12} />
        </div>
      </section>
      <section className="ux-sec">
        <Sk w={180} h={18} />
        <div className="ux-runs" style={{ marginTop: 12 }}>
          {[0, 1, 2].map((k) => (
            <Sk key={k} h={78} r={12} />
          ))}
        </div>
      </section>
    </div>
  );
}

// ---------------------------------------------------------------- chips
function chipText(s: HomeSignal): { label: string; sub: string } {
  switch (s.kind) {
    case 'recording':
      return { label: t('hd.sig.recording', { name: s.text }), sub: t('hd.sig.recordingSub', { folder: s.folder ?? '' }) };
    case 'again':
      return { label: s.text, sub: t('hd.sig.againSub', { n: s.n ?? 2 }) };
    case 'share':
      return { label: t('hd.sig.share', { title: s.text, platforms: platformsLabel(s.missing ?? []) }), sub: t('hd.sig.shareSub', { platforms: platformsLabel(s.on ?? []) }) };
    case 'series':
      return { label: t('hd.sig.series', { name: s.text }), sub: t('hd.sig.seriesSub', { n: s.n ?? 1 }) };
    default:
      return { label: t('hd.sig.finish', { name: s.text }), sub: t('hd.sig.finishSub', { n: s.n ?? 1 }) };
  }
}

function chipIcon(s: HomeSignal) {
  if (s.thumb) return <img src={window.desk.mediaUrl(s.thumb)} alt="" />;
  if (s.kind === 'recording') return <Video className="ico" />;
  if (s.kind === 'share') return <Send className="ico" />;
  if (s.kind === 'again') return <Repeat className="ico" />;
  return <FolderOpen className="ico" />;
}

/** What a chip does: a recording goes into the composer, a request fills it again, a post opens on its clip's page
 * (publishing is there), the next episode becomes a request. The rest of a project is that project run on (its
 * recordings are already in it; the run skips what is made) and its run page opens - never a new request with no
 * files, which only stopped at "Add the recordings you want cut". */
export function useChipAction(fill: (prompt: string) => void, addFile: (path: string) => void) {
  const { client } = useEngine();
  const ui = useUi();
  return (s: HomeSignal) => {
    if (s.kind === 'recording' && s.path) return addFile(s.path);
    if (s.kind === 'again') return fill(s.text);
    if (s.kind === 'share' && s.item && s.clip) return void (location.hash = clipHref(s.item, s.clip));
    if (s.kind === 'series') return fill(t('home.sug.nextPrompt', { name: s.text, n: s.n ?? 1 }));
    if (s.kind === 'finish' && s.item && client) {
      const item = s.item;
      return void client
        .finishHistory(item)
        .then((r) => {
          ui.toast(t(r.started ? 'hd.sig.finishing' : 'hd.sig.finishAsk', { name: s.text }));
          location.hash = studioEnabled() ? href({ name: 'studio', id: item }) : projectHref(item);
        })
        .catch((e) => ui.toast(errText(e), { error: true }));
    }
    return fill(t('home.sug.finishPrompt', { name: s.text }));
  };
}

/** The chips, strongest first; the row is not there at all without a signal. */
export function HomeChips({ signals, onPick }: { signals: HomeSignal[]; onPick: (s: HomeSignal) => void }) {
  const ui = useUi();
  if (!signals.length) return null;
  const shown = signals.slice(0, 4);
  const rest = signals.slice(4);
  return (
    <div className="ux-ideas" role="list" aria-label={t('hd.sigLabel')} data-testid="home-ideas">
      {shown.map((s) => {
        const w = chipText(s);
        return (
          <button key={s.id} role="listitem" className="ux-idea" onClick={() => onPick(s)} data-kind={s.kind} data-testid="home-idea" title={`${w.label} · ${w.sub}`}>
            {chipIcon(s)}
            <span className="clamp1">{w.label}</span>
            <span className="faint clamp1">{w.sub}</span>
          </button>
        );
      })}
      {rest.length > 0 && (
        <button
          className="ux-idea more"
          aria-label={t('hd.sig.more')}
          data-tip={t('hd.sig.more')}
          onClick={(e) => {
            const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
            ui.menu({ clientX: r.left - 160, clientY: r.bottom + 6 }, rest.map((s) => ({ label: chipText(s).label, run: () => onPick(s) })));
          }}
          data-testid="home-more-ideas"
        >
          <MoreHorizontal className="ico" />
        </button>
      )}
    </div>
  );
}

/** Her platforms (accounts she has, else her default) for the "share on more" chips. */
export function useMyPlatforms(): string[] {
  const [v, setV] = useState<string[]>([]);
  useEffect(() => {
    void window.desk.getSettings().then((s) => {
      const acc = Object.keys(s.accounts ?? {}).filter((k) => (s.accounts[k] ?? []).length);
      setV(acc.length ? acc : (s.defaultPlatforms ?? []));
    });
  }, []);
  return v;
}

export { homeSignals };

// ---------------------------------------------------------------- Inbox
/** The one action that settles an item, in its own words. */
function actOf(x: InboxItem): { key: MessageKey; how: 'fail' | 'focus' | 'link' | 'sheet' } {
  if (x.failure && x.project.id) return { key: x.failure.code === 'ai-login' || x.failure.code === 'ai-missing' ? 'fail.login' : 'fail.retry', how: 'fail' };
  if (x.href) return { key: 'home.act.open', how: 'link' };
  if (x.kind === 'needs') return { key: 'hd.act.addFiles', how: 'link' };
  if (x.kind === 'failed') return { key: 'home.act.fix', how: 'link' };
  if (x.kind === 'review' && x.project.id) return { key: 'home.act.review', how: 'focus' };
  if (x.kind === 'cover-pick') return { key: 'hd.act.cover', how: 'sheet' };
  if (/-pick$/.test(x.kind)) return { key: 'hd.act.pick', how: 'sheet' };
  if (x.code === 'inbox.spend' || x.kind === 'budget-approval') return { key: 'home.act.decide', how: 'sheet' };
  return { key: 'home.act.review', how: 'sheet' };
}

/** Answer with the row gone at once; Undo (or a refusal) brings it back. */
function useSettle() {
  const { client } = useEngine();
  const { reload } = useInbox();
  const ui = useUi();
  const [gone, setGone] = useState<Set<string>>(new Set());
  const hide = (k: string, on: boolean) =>
    setGone((g) => {
      const n = new Set(g);
      if (on) n.add(k);
      else n.delete(k);
      return n;
    });
  const answer = async (x: InboxItem, a?: Record<string, unknown>) => {
    if (!client) return;
    hide(x.key, true);
    try {
      await client.answerInbox([x.key], a);
      reload();
      ui.toast(t('inbox.resolved', { what: inboxTitle(x) }), {
        undo: async () => {
          hide(x.key, false);
          await client.undoInbox([x.key]);
          reload();
        },
      });
    } catch (e) {
      hide(x.key, false);
      ui.toast(errText(e), { error: true });
    }
  };
  return { gone, hide, answer };
}

export function HomeInbox({ items }: { items: InboxItem[] }) {
  const { gone, hide, answer } = useSettle();
  const [open, setOpen] = useState<InboxItem | null>(null);
  const live = items.filter((x) => !gone.has(x.key));
  if (!live.length) return null;
  const top = live.slice(0, 3);
  const rest = live.slice(3);
  const minutes = live.reduce((s, x) => s + (x.minutes ?? 1), 0);
  return (
    <section className="ux-sec" data-testid="home-inbox">
      <div className="ux-sech">
        <h2>{t('nav.inbox')}</h2>
        <span className="muted" data-testid="home-inbox-count">
          {t('hd.inboxLine', { n: live.length, m: minutes })}
        </span>
        <span className="sp" />
        {live.length > 1 && (
          <button className="ux-link" onClick={() => reviewInRow(live)} data-testid="home-in-row">
            {t('st.inRow')} <Play className="ico" />
          </button>
        )}
        <a className="ux-link" href={href({ name: 'inbox' })} data-testid="home-open-inbox">
          {t('home.openInbox')} <ArrowRight className="ico" />
        </a>
      </div>
      <div className="card ux-hlist" data-testid="home-needs-you">
        {top.map((x, i) => (
          <InboxRow key={x.key} x={x} first={i === 0} onSheet={() => setOpen(x)} onFixed={() => hide(x.key, true)} />
        ))}
        {rest.length > 0 && (
          <a className="ux-hmore" href={href({ name: 'inbox' })} data-testid="home-inbox-more">
            <span className="clamp1">{t('home.nMore', { n: rest.length, what: rest.map((x) => inboxTitle(x).toLocaleLowerCase()).join(', ') })}</span>
            <span className="sp" />
            <ChevronRight className="ico" />
          </a>
        )}
      </div>
      {open && (
        <ItemSheet
          x={open}
          onClose={() => setOpen(null)}
          onDone={(a) => {
            const x = open;
            setOpen(null);
            void answer(x, a);
          }}
        />
      )}
    </section>
  );
}

function InboxRow({ x, first, onSheet, onFixed }: { x: InboxItem; first: boolean; onSheet: () => void; onFixed: () => void }) {
  const th = (x.options ?? []).find((o) => o.cover)?.cover ?? x.project.thumb;
  const act = actOf(x);
  const cls = `btn ${first ? 'soft' : ''}`;
  return (
    <div className="ux-hrow" data-testid="home-inbox-row" data-kind={x.kind} data-key={x.key}>
      <a href={itemTarget(x)} className="ux-hrow-main">
        <InboxThumb x={x} src={th} />
        <div className="tx">
          <div className="clamp1">
            <b>{inboxTitle(x)}</b>
            {x.project.name && <span className="muted"> · {x.project.name}</span>}
          </div>
          <div className="muted clamp1">{inboxSub(x)}</div>
        </div>
      </a>
      <span className="muted num">{t('inbox.minutes', { n: x.minutes ?? 1 })}</span>
      {act.how === 'fail' && x.failure && x.project.id ? (
        <span className="ux-hacts" data-testid="home-inbox-act">
          <FailureActions item={x.project.id} failure={x.failure} primary={first} only onDone={onFixed} />
        </span>
      ) : act.how === 'focus' ? (
        <a className={cls} href={href({ name: 'focus', id: x.project.id! })} data-testid="home-inbox-act">
          {t(act.key)}
        </a>
      ) : act.how === 'link' ? (
        <a className={cls} href={x.kind === 'needs' || x.kind === 'failed' ? (x.href ?? selOf(x)) : itemTarget(x)} data-testid="home-inbox-act">
          {t(act.key)}
        </a>
      ) : (
        <button className={cls} onClick={onSheet} data-testid="home-inbox-act">
          {t(act.key)}
        </button>
      )}
    </div>
  );
}

/** A request's question (it waits for files, its plan failed): its row in All projects, where it is answered. */
function selOf(x: InboxItem): string {
  const id = x.key.match(/[0-9a-f]{12}/)?.[0];
  return id ? selHref(id) : inboxHref({ item: x.key });
}

/** One question in a focused sheet over Home: the same pane as the Inbox (preview, options, one primary button);
 * Skip for now, Esc or a click outside closes it. */
function ItemSheet({ x, onDone, onClose }: { x: InboxItem; onDone: (a?: Record<string, unknown>) => void; onClose: () => void }) {
  const box = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const on = (e: KeyboardEvent) => e.key === 'Escape' && (e.stopPropagation(), onClose());
    window.addEventListener('keydown', on, true);
    box.current?.focus();
    return () => window.removeEventListener('keydown', on, true);
  }, [onClose]);
  return (
    <div className="ux-sheetbg" onMouseDown={(e) => e.target === e.currentTarget && onClose()} data-testid="home-sheet">
      <div className="ux-isheet" role="dialog" aria-modal="true" aria-label={inboxTitle(x)} tabIndex={-1} ref={box}>
        <ItemPane x={x} onDone={onDone} onSkip={onClose} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- Running
interface RunCardModel {
  key: string;
  title: string;
  thumb: string | null;
  line: string;
  eta: number | null;
  progress: number | null;
  href: string;
  /** its state in the list's words (read out with the card) */
  status: Status4;
}

/** The running jobs as cards: from the Studio's rows (each opens its live run page there), else from the history. */
export function runCards(rows: StudioRow[] | null, live: HistoryItem[], requests: OpenRequest[]): RunCardModel[] {
  if (rows) {
    return runningJobs(rows).map((r) => ({
      key: r.key,
      title: r.kind === 'request' ? r.title || t('home.planningRow') : (r.i?.name ?? r.title),
      thumb: r.kind === 'request' ? null : (r.i?.thumb ?? r.thumb),
      // what it is doing in words ("Cutting clip 3 of 8"), else the step it is at
      line: r.kind === 'request' ? t('home.planningRow') : liveText(r.i?.live) || t(`hub.step.${r.p.current}` as MessageKey),
      eta: r.p.eta ?? null,
      progress: r.kind === 'request' ? null : (r.p.progress ?? null),
      href: rowHref(r),
      status: 'run' as Status4,
    }));
  }
  return [
    ...requests.filter((r) => r.state === 'running').map((r) => ({ key: `r:${r.id}`, title: r.name || r.prompt || t('home.planningRow'), thumb: null, line: t('home.planningRow'), eta: null, progress: null, href: selHref(r.id), status: 'run' as Status4 })),
    ...live
      .filter((i) => i.live?.state === 'running')
      .map((i) => ({ key: i.id, title: i.name, thumb: i.thumb, line: liveText(i.live) || t('status.running'), eta: i.live?.eta ?? null, progress: i.live?.progress ?? null, href: projectHref(i.id), status: (itemStatus(i) ?? 'run') as Status4 })),
  ];
}

export function HomeRunning({ cards, waiting }: { cards: RunCardModel[]; waiting: number }) {
  if (!cards.length && !waiting) return null;
  // the Studio opens on the first running job with every running job tiled over its page
  const watch = () => {
    sessionStorage.setItem('studio.watch', '1');
    location.hash = cards[0].href;
  };
  return (
    <section className="ux-sec" data-testid="live-lane">
      <div className="ux-sech">
        <h2>{t('home.running')}</h2>
        <span className="muted" data-testid="home-running-count">
          {[cards.length ? t('home.jobs', { n: cards.length }) : null, waiting ? t('hd.waiting', { n: waiting }) : null].filter(Boolean).join(' · ')}
        </span>
        <span className="sp" />
        {studioEnabled() && cards.length > 1 && (
          <button className="ux-link" onClick={watch} data-testid="home-watch-all">
            <LayoutGrid className="ico" /> {t('hd.watchAll')}
          </button>
        )}
        <a className="ux-link" href={href({ name: 'projects' })}>
          {t('home.allProjects')} <ArrowRight className="ico" />
        </a>
      </div>
      {cards.length > 0 && (
        <div className="ux-runs">
          {cards.slice(0, 3).map((c) => (
            <a key={c.key} className="card ux-run" href={c.href} data-testid="live-row" data-key={c.key}>
              <Thumb src={c.thumb} className="ux-runth" />
              <div className="tx">
                <div className="row1">
                  <b className="clamp1">{c.title}</b>
                </div>
                <div className="row1 muted">
                  <span className="clamp1" data-testid="live-step">
                    {c.line}
                  </span>
                  <span className="sp" />
                  {c.eta ? <span className="num">{t('hd.left', { t: fmtMinutes(Math.max(1, Math.round(c.eta / 60))) })}</span> : null}
                </div>
                <div className={`bar ${c.progress == null ? 'indet' : ''}`}>
                  <i style={{ width: `${Math.max(4, Math.round((c.progress ?? 0.3) * 100))}%` }} />
                </div>
                <span className="sr">
                  <StatusPill s={c.status} testId="live-state" />
                </span>
              </div>
            </a>
          ))}
        </div>
      )}
      {cards.length > 3 && (
        <a className="ux-link" href={href({ name: 'projects' })} style={{ marginTop: 8, display: 'inline-flex' }} data-testid="home-more-running">
          {t('home.nMoreRunning', { n: cards.length - 3 })}
        </a>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- Going out today
interface OutGroup {
  key: string;
  at: string;
  title: string;
  cover: string | null;
  platforms: string[];
  posts: CalendarPost[];
}

/** Today's posts, one entry per clip and time (its platforms side by side), in time order. */
export function outGroups(posts: CalendarPost[]): OutGroup[] {
  const by = new Map<string, OutGroup>();
  for (const p of posts) {
    if (p.enabled === false) continue;
    const k = `${p.item}/${p.clip}@${p.at.slice(0, 16)}`;
    const g = by.get(k) ?? { key: k, at: p.at, title: p.title, cover: p.cover, platforms: [], posts: [] };
    g.posts.push(p);
    if (!g.platforms.includes(p.platform.split(':')[0])) g.platforms.push(p.platform.split(':')[0]);
    by.set(k, g);
  }
  return [...by.values()].sort((a, b) => a.at.localeCompare(b.at));
}

/** Where a group is, in words: every post out -> Posted (· views); one filled in, waiting for the platform; ready;
 * else scheduled. */
export function outState(g: OutGroup): { text: string; tone: 'done' | 'you' | 'off' } {
  const ps = g.posts;
  if (ps.every((p) => p.state === 'posted')) {
    const views = ps.reduce((s, p) => s + (p.stats?.views ?? 0), 0);
    return { text: views ? t('hd.post.views', { n: views }) : t('hd.post.posted'), tone: 'done' };
  }
  const filled = ps.find((p) => p.state === 'filled');
  if (filled) return { text: t('hd.post.waiting', { platform: platformName(filled.platform) }), tone: 'you' };
  if (ps.some((p) => p.state === 'ready')) return { text: t('hd.post.ready'), tone: 'you' };
  return { text: t('hd.post.scheduled'), tone: 'off' };
}

export function HomeGoingOut({ posts }: { posts: CalendarPost[] }) {
  const groups = useMemo(() => outGroups(posts), [posts]);
  if (!groups.length) return null;
  return (
    <section className="ux-sec" data-testid="home-today">
      <div className="ux-sech">
        <h2>{t('home.goingOut')}</h2>
        <span className="muted">{t('home.posts', { n: posts.filter((p) => p.enabled !== false).length })}</span>
        <span className="sp" />
        <a className="ux-link" href={href({ name: 'calendar' })} data-testid="home-calendar">
          {t('home.calendar')} <ArrowRight className="ico" />
        </a>
      </div>
      <div className="card ux-strip">
        {groups.slice(0, 4).map((g) => {
          const s = outState(g);
          return (
            <a key={g.key} className="ux-post" href={postHref(g.posts[0].id)} data-testid="home-post" data-state={s.tone}>
              <Thumb src={g.cover} className="ux-postth" />
              <span className="tx">
                <span className="row1">
                  <b className="num">{fmtTime(g.at)}</b>
                  <span className="ux-pfics">
                    {g.platforms.map((p) => (
                      <PlatformIcon key={p} id={p} size={16} />
                    ))}
                  </span>
                </span>
                <span className="muted clamp1" data-testid="home-post-state">
                  <i className={`dot ${s.tone}`} /> {s.text}
                </span>
              </span>
            </a>
          );
        })}
      </div>
    </section>
  );
}
