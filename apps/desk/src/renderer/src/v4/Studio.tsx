// The Studio (2026-10 review steps 6-8, layout A): every video in one list on the left - needs you / in progress /
// ready to post / scheduled, each row with its dot, where it is, time left and progress - and the selected video's
// one page on the right (the clip page: player, cover, captions, versions, the question, the transcript, the post,
// one AI bar). A request still being planned or a project with no clips yet opens its own detail; a question about a
// whole project opens the question itself. ＋ New video (⌘N) starts the next one from here; ↑ ↓ and ⌘1–9 switch.
import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';
import { Archive, ArchiveRestore, ChevronDown, ChevronRight, LayoutGrid, MoreHorizontal, PanelLeftClose, PanelLeftOpen, Play, Plus, RotateCcw, Sparkles, Trash2, X } from 'lucide-react';
import type { HistoryItem } from '../../../shared/v02';
import type { CalendarPost, InboxItem, OpenRequest } from '../../../shared/v04';
import { fmtDate, fmtLen, fmtMinutes, t, tk } from '../i18n';
import { useHistory } from '../lib/history';
import { useInbox } from '../lib/inbox';
import { inboxTitle } from '../lib/inboxView';
import { keyHint } from '../lib/keys';
import { reviewInRow } from '../lib/nav';
import { href, routeQuery } from '../lib/router';
import { goalActive, groupVideos, useGoals } from '../lib/goals';
import { GoalGroup, GoalPage } from './GoalView';
import { VIDEO_STATUS_KEY } from '../../../shared/videoStatus';
import { STUDIO_FILTERS, grouped, needsYou, notMadeYet, screenPieces, timeLeft, type ListPiece, type StudioFilter, type StudioGroup, type StudioRow } from '../lib/studio';
import { rowHref, useStudioData } from '../lib/studioData';
import { setStudioView } from '../lib/studioView';
import { platformName } from './Home';
import { ItemPane, useResolve } from './Inbox';
import { Empty, Sk, Thumb } from './kit';
import { OutputEditor } from './OutputEditor';
import { ProjectDetail, stateLine } from './Hub';
import { itemPipeline, stepOfStage } from '../lib/pipeline';
import { failureReason } from './Failure';
import { Composer } from './Composer';
import { AiTag } from './AiPick';
import { isTyping, useUi } from './ui';
import { archivedLine } from '../lib/archive';
import { bulkActions, emptyClip, rangePick, togglePick, type ActionTarget } from '../lib/rowActions';
import { useRowActions, type RowActionsApi } from './RowActions';
import { useBox, usePane } from '../lib/panes';
import { Splitter } from './Splitter';
import { ProjectRun, RequestRun } from './RunView';
import { WithProjectChat } from './ProjectChat';
import { useEngine, useLoad } from '../lib/engine';
import { WatchAll } from './WatchAll';
import { runningJobs } from '../lib/live';
import { findRows, finding, NO_FIND, type Find } from '../lib/studioFind';
import { BulkMore, FindBar, FINDKEY, loadFind, useBulk } from './StudioBulk';
import './studio.css';
import './homeDash.css';

const FKEY = 'studio.filter';
const GKEY = 'studio.folded';
const WKEY = 'studio.watch';
/** the clip page keeps this much room next to the list (its own columns stack below ~700 px) */
export const PAGE_MIN = 560;
/** the list's scroll position while she is elsewhere in the app (Calendar, Settings) */
let listScroll = 0;

function loadFolded(): StudioGroup[] {
  try {
    const v = JSON.parse(localStorage.getItem(GKEY) ?? '[]') as unknown;
    return Array.isArray(v) ? (v.filter((x) => typeof x === 'string') as StudioGroup[]) : [];
  } catch {
    return [];
  }
}

type ListFilter = StudioFilter | 'archived';
const LIST_FILTERS: ListFilter[] = [...STUDIO_FILTERS, 'archived'];

export function targetOf(r: StudioRow): ActionTarget {
  return { key: r.key, kind: r.kind, title: r.title, r: r.r, i: r.i, clip: r.clip, video: r.video };
}

function archivedTargets(items: HistoryItem[], reqs: OpenRequest[]): ActionTarget[] {
  return [
    ...reqs.map((r): ActionTarget => ({ key: `r:${r.id}`, kind: 'request', title: r.name || r.prompt || '', r })),
    ...items.map((i): ActionTarget => ({ key: `p:${i.id}`, kind: 'project', title: i.name, i })),
  ];
}

/** The project a request was made into (its job's ``applied`` folder -> the history item there), once the request is
 * no longer one: asked again whenever the history changes until the project is listed. */
function useMadeFrom(sel: string | null, items: HistoryItem[] | undefined): string | null {
  const { client } = useEngine();
  const [dirs, setDirs] = useState<{ sel: string; dirs: string[] } | null>(null);
  const have = dirs?.sel === sel && dirs.dirs.length > 0;
  useEffect(() => {
    if (!client || !sel || have) return;
    let alive = true;
    let tm = 0;
    const ask = () =>
      client
        .intake(sel)
        .then((j) => {
          if (!alive) return;
          const ds = (j.applied ?? []).map((p) => p.dir).filter(Boolean);
          if (ds.length) setDirs({ sel, dirs: ds });
          else tm = window.setTimeout(ask, 800); // still making the plan into its projects
        })
        .catch(() => undefined); // not a request (an old link): nothing to follow
    void ask();
    return () => {
      alive = false;
      window.clearTimeout(tm);
    };
  }, [client, sel, have]);
  if (!sel || !have) return null;
  // the same folder however it is written (a trailing slash, macOS's /private/var for /var)
  const norm = (p: string) => p.replace(/[\\/]+$/, '').replace(/^\/private(?=\/)/, '');
  const hit = items?.find((i) => dirs.dirs.some((d) => norm(d) === norm(i.dir)));
  return hit?.id ?? null;
}

export function Studio({ id, clip }: { id?: string; clip?: string }) {
  const { data: hist, archived: archDoc, archivedRequests, nArchivedRequests, wantArchived } = useHistory();
  const ui = useUi();
  const inbox = useInbox();
  const { rows: allRows, posts, ready } = useStudioData();
  // search + filters (hundreds of videos): typing stays instant, the list follows a beat later
  const [find, setFindS] = useState<Find>(loadFind);
  const setFind = (f: Find) => {
    setFindS(f);
    sessionStorage.setItem(FINDKEY, JSON.stringify(f));
  };
  const dfind = useDeferredValue(find);
  const rows = useMemo(() => findRows(allRows, dfind, posts), [allRows, dfind, posts]);
  useGoalParam(); // a new ?goal= is a new page (the route itself stays #/studio)
  const q = routeQuery();
  // goal mode: the groups of videos one request asked for, each above the list with its videos under it. The group
  // is the one place they are followed: none of a goal's requests / projects (its language versions, what a retry
  // left behind) is a loose row of its own, in any group - their state is the group's, never a contradicting one
  const { goals } = useGoals();
  const inGoal = useMemo(() => {
    const ids = new Set(goals.map((g) => g.id));
    return (r: StudioRow) => {
      const gid = r.i?.goal ?? r.r?.goal;
      return !!gid && ids.has(gid);
    };
  }, [goals]);
  const freeRows = useMemo(() => rows.filter((r) => !inGoal(r)), [rows, inGoal]);
  const freeAll = useMemo(() => allRows.filter((r) => !inGoal(r)), [allRows, inGoal]);
  const groups = useMemo(() => grouped(freeRows), [freeRows]);
  // the goals' own videos, counted where the group shows them (needs you / in progress / ready)
  const goalN = useMemo(() => {
    const n = { you: 0, run: 0, ready: 0, scheduled: 0 } as Record<StudioGroup, number>;
    for (const g of goals) {
      if (g.state === 'planned' || g.state === 'failed') n.you += 1;
      for (const v of groupVideos(g)) {
        if (v.state === 'you') n.you += 1;
        else if (v.state === 'waiting' || v.state === 'planning' || v.state === 'making') n.run += 1;
        else if (v.state === 'made') n.ready += 1;
      }
    }
    return n;
  }, [goals]);
  const goalSel = !id && q.goal ? q.goal : null;
  const [filter, setFilterS] = useState<ListFilter>(() => (LIST_FILTERS.includes(q.f as ListFilter) ? (q.f as ListFilter) : ((sessionStorage.getItem(FKEY) as ListFilter | null) ?? 'all')));
  useEffect(() => {
    const on = (e?: Event) => {
      // the Inbox is the Studio's Needs you filter now (an old link, a notification, ⌘K)
      if (/^#\/inbox\b/.test(location.hash)) {
        const rest = location.hash.split('?')[1];
        history.replaceState(null, '', `#/studio?f=you${rest ? `&${rest}` : ''}`);
      }
      // the link she followed (the list may already have moved the address on to its first video)
      const to = e instanceof HashChangeEvent && e.newURL ? new URL(e.newURL).hash : location.hash;
      const f = (/^#\/inbox\b/.test(to) ? 'you' : (routeQuery(to).f ?? routeQuery().f)) as ListFilter | undefined;
      if (f && LIST_FILTERS.includes(f)) setFilterS(f);
    };
    on();
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);
  // the sidebar lights Inbox for Needs you, All projects for the rest
  useEffect(() => setStudioView(filter), [filter]);
  useEffect(() => () => setStudioView(null), []);
  const setFilter = (f: ListFilter) => {
    setFilterS(f);
    setPicked(new Set());
    sessionStorage.setItem(FKEY, f);
  };
  const inArchive = filter === 'archived';
  useEffect(() => {
    if (inArchive) wantArchived();
  }, [inArchive, wantArchived]);
  const order: StudioGroup[] = inArchive ? [] : filter === 'all' ? ['you', 'run', 'ready', 'scheduled'] : [filter];
  // a project with several videos is one header with its videos under it (its question as the header's badge)
  const listRows = freeRows;
  const pieces = useMemo(() => screenPieces(listRows, order), [listRows, order.join()]); // eslint-disable-line react-hooks/exhaustive-deps
  const shownGoals = inArchive || finding(dfind) ? [] : goals.filter((g) => filter === 'all' || (filter === 'run' && goalActive(g) && g.state !== 'planned') || (filter === 'you' && (g.state === 'planned' || g.state === 'failed' || g.counts.you > 0)) || (filter === 'ready' && g.state === 'done'));
  const list = pieces.flatMap((x) => x.pieces.flatMap((pc) => (pc.kind === 'row' ? [pc.r] : pc.r ? [pc.r] : [])));
  // the Archived filter: archived requests and projects, each with Restore (nothing in it counts anywhere else)
  const archived = useMemo(() => archivedTargets(archDoc?.items ?? [], archivedRequests), [archDoc, archivedRequests]);
  const nArchived = (archDoc ? archDoc.items.length : typeof hist?.archived === 'number' ? hist.archived : 0) + nArchivedRequests;
  // multi-select: ⌘-click one more, ⇧-click a range; the bulk bar, ⌫ and the menus act on what is picked
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const anchor = useRef<string | null>(null);
  const targets = useMemo(() => (inArchive ? archived : allRows.map(targetOf)), [inArchive, archived, allRows]);
  const screen = inArchive ? archived.map((x) => x.key) : list.map((r) => r.key);
  const pickedT = targets.filter((x) => picked.has(x.key));
  const ra = useRowActions(allRows.map(targetOf), (_a, xs) => {
    setPicked(new Set());
    if (cur && xs.some((x) => x.key === cur.key || (x.i && cur.i && x.i.dir === cur.i.dir))) location.hash = href({ name: 'studio' });
  });
  const pick = (e: React.MouseEvent, key: string): boolean => {
    if (e.metaKey || e.ctrlKey) {
      e.preventDefault();
      setPicked((p) => togglePick(p.size ? p : cur && !inArchive ? new Set([cur.key]) : p, key));
      anchor.current = key;
      return true;
    }
    if (e.shiftKey) {
      e.preventDefault();
      setPicked((p) => rangePick(screen, anchor.current ?? cur?.key ?? null, key, p));
      return true;
    }
    anchor.current = key;
    if (picked.size) setPicked(new Set());
    return false;
  };
  const menuAt = (e: { clientX: number; clientY: number; preventDefault?: () => void }, x: ActionTarget) => {
    const many = picked.has(x.key) && picked.size > 1;
    ui.menu(e, ra.items(x, many ? pickedT : []));
  };
  // a question opened from the Inbox / Home / a notification (?item=<key>): the row it is pinned on (a video's, else
  // its project's header / row); a question with no row of its own (a request's, an old project's) is shown by itself
  const askKey = !id && q.item ? q.item : null;
  const askItem = askKey ? (inbox.items.find((x) => x.key === askKey) ?? null) : null;
  const askRow = askKey ? (allRows.find((r) => r.ask?.key === askKey) ?? (askItem?.project.id ? allRows.find((r) => r.item === askItem.project.id && (r.header || r.kind === 'project')) : undefined)) : undefined;
  // a request she is watching that became its project (autopilot makes the plan into projects at once): the
  // project's row, so the page moves on into the making instead of losing its place
  const madeFrom = useMadeFrom(!id && q.sel && !allRows.some((r) => r.key === `r:${q.sel}` || r.item === q.sel) ? q.sel : null, hist?.items);
  const madeRow = madeFrom ? (allRows.find((r) => r.item === madeFrom && (r.kind === 'project' || r.header)) ?? allRows.find((r) => r.item === madeFrom)) : undefined;
  const selKey = clip && id ? `${id}/${clip}` : id ? `p:${id}` : askRow ? askRow.key : q.sel ? (allRows.some((r) => r.key === `r:${q.sel}`) ? `r:${q.sel}` : allRows.some((r) => r.item === q.sel) ? `p:${q.sel}` : (madeRow?.key ?? null)) : null;
  // the request's own row while it is one, kept on screen for the moment between the request going and its project
  // showing up (never a skeleton or another video in between)
  const lastReq = useRef<StudioRow | null>(null);
  const reqRow = q.sel ? allRows.find((r) => r.key === `r:${q.sel}`) : undefined;
  if (reqRow) lastReq.current = reqRow;
  // a project's own link (a notification, ⌘K) with one video: that video's page, its question pinned on it
  const cur =
    (selKey ? (allRows.find((r) => r.key === selKey) ?? (id && !clip ? allRows.find((r) => r.item === id && r.kind === 'clip') : undefined)) : null) ??
    (!id && q.sel && lastReq.current?.r?.id === q.sel ? lastReq.current : null);
  // the request became its project: the address follows (Back, a reload and the list's highlight all agree)
  useEffect(() => {
    if (madeRow && !id) history.replaceState(null, '', rowHref(madeRow));
    if (madeRow && !id) window.dispatchEvent(new HashChangeEvent('hashchange'));
  }, [madeRow?.key]); // eslint-disable-line react-hooks/exhaustive-deps
  // nothing chosen: the first video of the list (what needs her first). A request she just sent (?sel=<id>) is not
  // a row until the history reloads: wait for it instead of jumping to an unrelated video (give up after 20 s)
  const first = list[0] ?? null;
  const [gaveUp, setGaveUp] = useState<string | null>(null);
  const waiting = !!goalSel || (!!q.sel && !selKey && !cur && !id && gaveUp !== q.sel) || (!!askKey && !askRow && (!!askItem || !inbox.loaded));
  useEffect(() => {
    if (!q.sel || selKey) return;
    const sel = q.sel;
    const t = window.setTimeout(() => setGaveUp(sel), 20000);
    return () => window.clearTimeout(t);
  }, [q.sel, selKey]);
  useEffect(() => {
    // the address already names a video or a goal (a render between the address changing and the page following
    // it): never replaced by the first row
    if (/^#\/studio\/[0-9a-f]{12}/.test(location.hash) || routeQuery(location.hash).goal) return;
    if (!selKey && !cur && !waiting && first && hist) history.replaceState(null, '', rowHref(first));
    if (!selKey && !cur && !waiting && first && hist) window.dispatchEvent(new HashChangeEvent('hashchange'));
  }, [selKey, !!cur, waiting, first?.key, !!hist]); // eslint-disable-line react-hooks/exhaustive-deps
  // ＋ New video from anywhere (⌘N, ⌘K): the composer opens here
  const [composer, setComposer] = useState(() => sessionStorage.getItem('studio.compose') === '1');
  useEffect(() => {
    sessionStorage.removeItem('studio.compose');
    const on = () => (sessionStorage.removeItem('studio.compose'), setComposer(true));
    window.addEventListener('studio:compose', on);
    return () => window.removeEventListener('studio:compose', on);
  }, []);

  // Watch all: every running job's live pane tiled in place of the page (the header's toggle)
  const [watch, setWatchS] = useState(() => sessionStorage.getItem(WKEY) === '1');
  const setWatch = (v: boolean) => {
    setWatchS(v);
    if (v) sessionStorage.setItem(WKEY, '1');
    else sessionStorage.removeItem(WKEY);
  };
  const watching = useMemo(() => runningJobs(allRows), [allRows]);
  // a video opened from a tile (or anywhere else) is shown: Watch all steps aside
  const routeKey = `${id ?? ''}/${clip ?? ''}`;
  const lastRoute = useRef(routeKey);
  useEffect(() => {
    if (lastRoute.current === routeKey) return;
    lastRoute.current = routeKey;
    setWatch(false);
  }, [routeKey]);
  const watchTip = t(watch ? 'watch.close' : 'watch.open');

  const bulk = useBulk();
  const pickedRows = useMemo(() => allRows.filter((r) => picked.has(r.key)), [allRows, picked]);
  /** ↵: where the video needs doing - its question's own place (the review player for a review), else its page's
   * first button */
  const openWork = (r: StudioRow) => {
    if (r.ask?.kind === 'review' && r.ask.project.id) return void (location.hash = href({ name: 'focus', id: r.ask.project.id }));
    if (rowHref(r) !== location.hash) location.hash = rowHref(r);
    window.setTimeout(() => {
      const page = document.querySelector<HTMLElement>('.st-page');
      const btn = page?.querySelector<HTMLElement>('.btn.primary:not([disabled]), button.primary:not([disabled])');
      (btn ?? page)?.focus();
    }, 60);
  };
  /** E: the page's AI bar, ready for her words (the clip's, else the project's chat) */
  const editWork = () =>
    window.setTimeout(() => {
      const box = document.querySelector<HTMLElement>('.st-page [data-testid=studio-ai-input], .st-page [data-testid=ai-panel] textarea, .st-page textarea');
      box?.focus();
    }, 30);

  // ↑ ↓ the next / previous video, ⌘1–9 the n-th one in the list
  const go = useCallback((r: StudioRow | undefined) => r && (location.hash = rowHref(r)), []);
  const keys = useRef<(e: KeyboardEvent) => void>(() => undefined);
  keys.current = (e: KeyboardEvent) => {
    if (document.querySelector('.scrim, .ctx, .palette')) return;
    const mod = e.metaKey || e.ctrlKey;
    if (mod && !e.shiftKey && !e.altKey && e.key.toLowerCase() === 'b' && !isTyping(e.target)) {
      e.preventDefault();
      e.stopImmediatePropagation();
      togglePane.current();
      return;
    }
    if (mod && !e.shiftKey && !e.altKey && /^[1-9]$/.test(e.key)) {
      e.preventDefault();
      e.stopImmediatePropagation();
      go(list[Number(e.key) - 1]);
      return;
    }
    if (!isTyping(e.target) && !mod && !e.altKey && e.key === 'Escape' && picked.size) {
      setPicked(new Set());
      return;
    }
    // ⌫ archives what is picked (or the row in focus in the list), with undo
    if (!isTyping(e.target) && !mod && !e.altKey && (e.key === 'Backspace' || e.key === 'Delete') && !inArchive) {
      const inList = !!(e.target as HTMLElement | null)?.closest?.('.st-list');
      const xs = pickedT.length ? pickedT : inList && cur ? [targetOf(cur)] : [];
      if (xs.length && bulkActions(xs).includes('archive')) {
        e.preventDefault();
        e.stopImmediatePropagation();
        void ra.archive(xs);
      }
      return;
    }
    // the list has the keyboard (she clicked a row or moved with the keys): J / K move, ↵ goes to what needs doing,
    // E edits with AI, S schedules, X picks, ⌘A picks every video shown - the page's own keys (the player's J K L,
    // E for its drawer) stay the page's while it has the focus
    const inList = !!(e.target as HTMLElement | null)?.closest?.('.st-list') && !isTyping(e.target);
    if (inList && mod && !e.shiftKey && !e.altKey && e.key.toLowerCase() === 'a' && !inArchive) {
      e.preventDefault();
      e.stopImmediatePropagation();
      setPicked(new Set(list.map((r) => r.key)));
      return;
    }
    if (inList && !mod && !e.altKey && !e.shiftKey && cur) {
      const lk = e.key.toLowerCase();
      const act = lk === 'enter' ? () => openWork(cur) : lk === 'e' ? () => editWork() : lk === 's' ? () => void bulk.schedule(pickedRows.length ? pickedRows : [cur]) : lk === 'x' ? () => setPicked((p) => togglePick(p, cur.key)) : null;
      if (act) {
        e.preventDefault();
        e.stopImmediatePropagation();
        act();
        return;
      }
    }
    if (isTyping(e.target) || mod || e.altKey || e.shiftKey) return;
    const down = e.key === 'ArrowDown' || (inList && e.key.toLowerCase() === 'j');
    const up = e.key === 'ArrowUp' || (inList && e.key.toLowerCase() === 'k');
    if (!down && !up) return;
    if ((e.target as HTMLElement | null)?.closest?.('[data-testid=transcript-body], .tl, [role=slider], [role=separator]')) return;
    const k = cur ? list.findIndex((r) => r.key === cur.key) : -1;
    const next = list[Math.max(0, Math.min(list.length - 1, k + (down ? 1 : -1)))];
    if (inList) {
      e.preventDefault();
      e.stopImmediatePropagation(); // J / K are the player's shuttle on the page: never both
    }
    if (next && next.key !== cur?.key) {
      e.preventDefault();
      go(next);
      const el = document.querySelector<HTMLElement>(`[data-row="${CSS.escape(next.key)}"]`);
      el?.scrollIntoView({ block: 'nearest' });
      if (inList) el?.focus({ preventScroll: true });
    }
  };
  useEffect(() => {
    const on = (e: KeyboardEvent) => keys.current(e);
    window.addEventListener('keydown', on, true);
    return () => window.removeEventListener('keydown', on, true);
  }, []);

  const count = (g: ListFilter) => (g === 'all' ? freeRows.length + goalN.you + goalN.run + goalN.ready : g === 'archived' ? nArchived : groups[g].length + goalN[g]);
  const youN = needsYou(freeAll) + goalN.you;
  // the list: resizable, folds to the edge (⌘B, its button, or dragged past its min); saved on this Mac
  const [boxRef, box] = useBox<HTMLDivElement>();
  const pane = usePane('studio.list', box.w ? box.w - PAGE_MIN : undefined);
  const folded = pane.collapsed;
  const togglePane = useRef(pane.toggle);
  togglePane.current = pane.toggle;
  const [foldedGroups, setFoldedGroups] = useState<StudioGroup[]>(loadFolded);
  const foldGroup = (g: StudioGroup) =>
    setFoldedGroups((x) => {
      const n = x.includes(g) ? x.filter((y) => y !== g) : [...x, g];
      localStorage.setItem(GKEY, JSON.stringify(n));
      return n;
    });
  const rowsEl = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const el = rowsEl.current;
    if (!el || folded) return;
    el.scrollTop = listScroll;
    const on = () => (listScroll = el.scrollTop);
    el.addEventListener('scroll', on, { passive: true });
    return () => el.removeEventListener('scroll', on);
  }, [folded, !!hist]); // eslint-disable-line react-hooks/exhaustive-deps
  // ⌘N with the list folded: it opens with the composer
  useEffect(() => {
    if (composer && folded) pane.set({ size: pane.size, collapsed: false });
  }, [composer]); // eslint-disable-line react-hooks/exhaustive-deps
  const listTip = `${folded ? t('st.listShow') : t('st.listHide')} · ${keyHint('⌘B')}`;
  return (
    <div className={`studio ${folded ? 'list-folded' : ''}`} data-testid="studio" ref={boxRef} style={{ ['--st-list' as string]: `${pane.size}px` }}>
      {folded ? (
        <aside className="st-rail" aria-label={t('st.list')} data-testid="studio-rail">
          <button className="btn ghost icon" onClick={pane.toggle} aria-label={listTip} data-tip={listTip} data-tip-x="start" aria-expanded={false} data-testid="studio-list-toggle">
            <PanelLeftOpen className="ico" />
          </button>
          <button className="btn ghost icon" onClick={() => setComposer(true)} aria-label={t('st.new')} data-tip={`${t('st.new')} · ${keyHint('⌘N')}`} data-tip-x="start" data-testid="studio-rail-new">
            <Plus className="ico" />
          </button>
          {watching.length > 0 && (
            <button className={`btn ghost icon ${watch ? 'on' : ''}`} onClick={() => setWatch(!watch)} aria-pressed={watch} aria-label={watchTip} data-tip={watchTip} data-tip-x="start" data-testid="studio-watch">
              <LayoutGrid className="ico" />
            </button>
          )}
          {ready && youN > 0 && (
            <button className="st-rail-you" onClick={() => (setFilter('you'), pane.toggle())} aria-label={`${t('st.f.you')} · ${youN}`} data-tip={t('st.f.you')} data-tip-x="start" data-testid="studio-rail-you">
              <i className="dot you" /> {youN}
            </button>
          )}
        </aside>
      ) : (
      <aside className="st-list" aria-label={t('st.list')} id="studio-list">
        <div className="st-head">
          <button className={`st-new ${composer ? 'on' : ''}`} onClick={() => setComposer((v) => !v)} aria-expanded={composer} data-testid="studio-new">
            <Plus className="ico" />
            <span className="tx">{composer ? t('st.new') : t('st.newHint')}</span>
            <span className="kbd">{keyHint('⌘N')}</span>
          </button>
          {watching.length > 0 && (
            <button className={`btn ghost icon st-watch ${watch ? 'on' : ''}`} onClick={() => setWatch(!watch)} aria-pressed={watch} aria-label={watchTip} data-tip={watchTip} data-testid="studio-watch">
              <LayoutGrid className="ico" />
              <b className="n" aria-hidden>
                {watching.length}
              </b>
            </button>
          )}
          <button className="btn ghost icon st-fold" onClick={pane.toggle} aria-label={listTip} data-tip={listTip} aria-expanded aria-controls="studio-list" data-testid="studio-list-toggle">
            <PanelLeftClose className="ico" />
          </button>
        </div>
        {composer && (
          <div className="st-composer" data-testid="studio-composer">
            <Composer compact autoFocus onSent={(rid, goal) => (setComposer(false), (location.hash = goal ? `${href({ name: 'studio' })}?goal=${rid}` : `${href({ name: 'studio' })}?sel=${rid}`))} onClose={() => setComposer(false)} />
          </div>
        )}
        {!inArchive && <FindBar find={find} onChange={setFind} rows={allRows} posts={posts} />}
        <div className="st-filters" role="tablist" aria-label={t('st.filters')} aria-busy={!ready}>
          {LIST_FILTERS.filter((f) => f !== 'archived' || nArchived > 0 || inArchive).map((f) => (
            <button key={f} role="tab" aria-selected={filter === f} className={`st-f ${filter === f ? 'on' : ''} ${f === 'you' && ready && count('you') ? 'you' : ''} ${f === 'archived' ? 'arch' : ''}`} onClick={() => setFilter(f)} data-testid={`studio-f-${f}`}>
              {f === 'all' ? t('st.f.all') : f === 'archived' ? t('ra.f.archived') : t(VIDEO_STATUS_KEY[f])}
              {!ready && f !== 'archived' ? <b className="n wait" aria-hidden data-testid={`studio-n-wait-${f}`} /> : count(f) > 0 && <b className="n" data-testid={`studio-n-${f}`}>{count(f)}</b>}
            </button>
          ))}
        </div>
        <div className="st-rows" data-testid="studio-rows" ref={rowsEl}>
          {!inArchive && !allRows.length && !shownGoals.length && (!hist || !ready) && <ListSkeleton />}
          {!inArchive && !allRows.length && !shownGoals.length && hist && ready && <p className="st-empty muted">{t('st.emptyAll')}</p>}
          {!inArchive && allRows.length > 0 && !list.length && !shownGoals.length && (finding(dfind) ? (
            <div className="st-empty muted" data-testid="studio-find-none">
              <p>{t('hd.f.none')}</p>
              <button className="btn sm" onClick={() => setFind(NO_FIND)} data-testid="studio-find-clear-all">
                {t('hd.f.clear')}
              </button>
            </div>
          ) : (
            <p className="st-empty muted">{t('st.empty')}</p>
          ))}
          {inArchive && (archDoc ? !archived.length : !nArchived) && <p className="st-empty muted">{t('ra.archivedEmpty')}</p>}
          {inArchive && archived.map((x) => <ArchivedRow key={x.key} x={x} picked={picked.has(x.key)} onPick={pick} onMenu={menuAt} ra={ra} />)}
          {shownGoals.map((g) => (
            <GoalGroup key={g.id} g={g} on={goalSel === g.id && !q.v} vid={goalSel === g.id ? q.v : undefined} item={id} />
          ))}
          {pieces.map(({ g, pieces: pc }) => {
            const l = groups[g];
            const shown = pc.filter((x) => x.kind === 'row' || x.r).length;
            if (!pc.length) return null;
            const left = g === 'run' ? timeLeft(l) : null;
            const shut = foldedGroups.includes(g) && !l.some((r) => r.key === cur?.key);
            return (
              <section key={g} className={`st-group ${shut ? 'shut' : ''}`} data-testid={`studio-group-${g}`}>
                <h3>
                  <button className="st-gtoggle" onClick={() => foldGroup(g)} aria-expanded={!shut} data-testid={`studio-group-toggle-${g}`}>
                    {shut ? <ChevronRight className="ico" /> : <ChevronDown className="ico" />}
                    {t(VIDEO_STATUS_KEY[g])}{ready ? ` · ${g === 'you' ? l.length : shown}` : ''}
                  </button>
                  <span className="sp" />
                  {g === 'you' && inbox.items.length > 0 && (
                    <button className="st-inrow" onClick={() => reviewInRow(inbox.items)} data-testid="studio-in-row">
                      {t('st.inRow')} <Play className="ico" />
                    </button>
                  )}
                  {left ? <span className="muted">{t('st.left', { t: fmtMinutes(Math.max(1, Math.round(left / 60))) })}</span> : null}
                </h3>
                {!shut &&
                  pc.map((x) =>
                    x.kind === 'head' ? (
                      <ProjectHead key={`h:${x.item}`} x={x} kids={pc} on={!!x.r && cur?.key === x.r.key} n={x.r ? list.indexOf(x.r) + 1 : 0} picked={!!x.r && picked.has(x.r.key)} onPick={pick} onMenu={menuAt} />
                    ) : (
                      <StudioListRow key={x.r.key} r={x.r} nested={x.nested} on={cur?.key === x.r.key} n={list.indexOf(x.r) + 1} picked={picked.has(x.r.key)} onPick={pick} onMenu={menuAt} />
                    ),
                  )}
              </section>
            );
          })}
        </div>
        {picked.size > 0 && <BulkBar xs={pickedT} rows={allRows.filter((r) => picked.has(r.key))} ra={ra} inArchive={inArchive} onClear={() => setPicked(new Set())} />}
        <footer className="st-foot muted">
          <span>{t('st.jump', { key: keyHint('⌘K') })}</span>
          <span className="sp" />
          {ready && youN > 0 && (
            <span className="st-you" data-testid="studio-you-count">
              <i className="dot you" /> {youN}
            </span>
          )}
        </footer>
      </aside>
      )}
      {folded ? (
        <span className="st-rail-line" aria-hidden />
      ) : (
        <Splitter
          orient="col"
          sign={1}
          state={{ size: pane.size, collapsed: false }}
          spec={pane.spec}
          room={box.w ? box.w - PAGE_MIN : undefined}
          onChange={pane.set}
          onReset={pane.reset}
          label={t('st.listResize')}
          tip={`${t('lay.dragTip')} · ${listTip}`}
          testId="studio-list-split"
        />
      )}
      <section className="st-page" data-testid="studio-page" tabIndex={-1}>
        {watch ? (
          <WatchAll rows={watching} lineOf={lineOf} onClose={() => setWatch(false)} />
        ) : goalSel ? (
          <GoalPage key={goalSel} gid={goalSel} vid={q.v} />
        ) : cur ? (
          <Page key={cur.key} r={cur} posts={posts} more={(e) => menuAt(e, targetOf(cur))} ra={ra} />
        ) : askItem && !askRow ? (
          <AskPage key={askItem.key} x={askItem} where={t('st.projectAsk')} title={askItem.project.name ?? inboxTitle(askItem)} />
        ) : !ready || waiting ? (
          <PageSkeleton />
        ) : (
          <Empty title={allRows.length ? t('st.pick') : t('st.emptyAll')} />
        )}
      </section>
      {ra.modal}
    </div>
  );
}

/** Re-render when the address's ``goal`` / ``v`` change (#/studio?goal=…: the route itself stays the Studio); any
 * other address change is the route's own. */
function useGoalParam() {
  const read = () => {
    const q = routeQuery();
    return `${q.goal ?? ''}\u0000${q.v ?? ''}`;
  };
  const [, setV] = useState(read);
  useEffect(() => {
    const on = () => setV(read());
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);
}

function lineOf(r: StudioRow): string {
  // the control room's words (Hub.stateLine): one vocabulary for where a video is
  if (r.kind === 'request') return stateLine(r.p, undefined, r.r);
  if (r.ask) return inboxTitle(r.ask);
  if (r.group === 'you') return r.tone === 'error' ? t('hub.s.failed') : t('hub.s.you');
  if (r.group === 'run') {
    // not in the run line (no queue place): it has simply not been started - never "waiting its turn"
    if (r.tone === 'off' && !r.i?.queued && r.p.state !== 'stopped') return t('st.r.notStarted');
    return stateLine(r.p, r.i);
  }
  if (r.group === 'scheduled' && r.post) {
    const when = fmtDate(r.post.at, { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
    return r.posted ? t('st.r.posted', { when }) : `${when} · ${platformName(r.post.platform)}`;
  }
  return t('st.r.made', { d: r.duration ? fmtLen(r.duration) : '—' });
}

type PickFn = (e: React.MouseEvent, key: string) => boolean;
type MenuFn = (e: { clientX: number; clientY: number; preventDefault?: () => void }, x: ActionTarget) => void;

/** The hover ⋯ of a row / the page header: the same menu as a right-click. */
function MoreButton({ onMenu, testId = 'row-more', className = '' }: { onMenu: (e: { clientX: number; clientY: number }) => void; testId?: string; className?: string }) {
  return (
    <button
      className={`btn ghost icon st-more ${className}`}
      aria-label={t('ra.more')}
      aria-haspopup="menu"
      data-tip={t('ra.more')}
      data-testid={testId}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        const b = e.currentTarget.getBoundingClientRect();
        onMenu({ clientX: b.right - 220, clientY: b.bottom + 4 });
      }}
    >
      <MoreHorizontal className="ico" />
    </button>
  );
}

/** A project with several videos, once: its name and how many videos, its question as a badge (then it opens the
 * question's page), the project's own menu; its videos follow, indented. */
function ProjectHead({ x, kids, on, n, picked, onPick, onMenu }: { x: Extract<ListPiece, { kind: 'head' }>; kids: ListPiece[]; on: boolean; n: number; picked: boolean; onPick: PickFn; onMenu: MenuFn }) {
  const first = kids.find((k): k is Extract<ListPiece, { kind: 'row' }> => k.kind === 'row' && k.r.item === x.item)?.r;
  const i = x.r?.i ?? first?.i;
  const target: ActionTarget = x.r ? targetOf(x.r) : { key: `p:${x.item}`, kind: 'project', title: x.name, i };
  const body = (
    <>
      <span className="tx">
        <b className="clamp1">{x.name}</b>
        <span className="s clamp1">
          {x.r?.ask ? (
            <span className={`st-badge ${x.r.tone}`} data-testid="studio-project-badge">
              <i className={`dot ${x.r.tone}`} />
              {inboxTitle(x.r.ask)}
            </span>
          ) : (
            <span className="faint">{t('st.headN', { n: x.n })}</span>
          )}
        </span>
      </span>
    </>
  );
  return (
    <div className={`st-rowwrap st-headwrap ${picked ? 'picked' : ''}`} onContextMenu={(e) => onMenu(e, target)} data-testid="studio-project-head" data-item={x.item}>
      {x.r ? (
        <a className={`st-row st-head ${on ? 'on' : ''} ${picked ? 'picked' : ''}`} href={rowHref(x.r)} onClick={(e) => onPick(e, x.r!.key)} aria-current={on ? 'true' : undefined} data-testid="studio-row" data-row={x.r.key} data-group={x.r.group} data-kind="project" data-tone={x.r.tone} title={n > 0 && n < 10 ? `${x.name} · ${keyHint(`⌘${n}`)}` : x.name}>
          {body}
        </a>
      ) : (
        <div className="st-row st-head plain">{body}</div>
      )}
      {i && <MoreButton onMenu={(e) => onMenu(e, target)} />}
    </div>
  );
}

function StudioListRow({ r, on, n, picked, onPick, onMenu, nested = false }: { r: StudioRow; on: boolean; n: number; picked: boolean; onPick: PickFn; onMenu: MenuFn; nested?: boolean }) {
  const pct = r.p.progress == null ? null : Math.round(r.p.progress * 100);
  // under its project's header the project's name is said once, above
  const where = [nested ? null : r.project, r.pos ? `${r.pos[0]}/${r.pos[1]}` : null].filter(Boolean).join(' · ');
  const x = targetOf(r);
  return (
    <div className={`st-rowwrap ${picked ? 'picked' : ''} ${nested ? 'nested' : ''}`} onContextMenu={(e) => onMenu(e, x)} data-picked={picked ? 'true' : undefined}>
    <a className={`st-row ${on ? 'on' : ''} ${picked ? 'picked' : ''}`} href={rowHref(r)} onClick={(e) => onPick(e, r.key)} aria-current={on ? 'true' : undefined} aria-selected={picked || undefined} data-testid="studio-row" data-row={r.key} data-group={r.group} data-kind={r.kind} data-tone={r.tone} title={n > 0 && n < 10 ? `${r.title} · ${keyHint(`⌘${n}`)}` : r.title}>
      <Thumb src={r.thumb} v={r.thumbV} className="st-th" />
      <span className="tx">
        <b className="clamp1" lang="zh-CN">
          {r.title || t('home.planningRow')}
        </b>
        <span className="s clamp1">
          <i className={`dot ${r.tone}`} />
          {lineOf(r)}
          {r.kind === 'project' && r.i?.autopilot ? <Sparkles className="ico ap" aria-label={t('ap.auto')} /> : null}
          {r.kind !== 'clip' && <AiTag ai={r.i?.ai ?? r.r?.ai} testId="studio-row-ai" />}
        </span>
        {where && <span className="w clamp1 faint">{where}</span>}
        {r.group === 'run' && r.tone === 'run' && (
          <span className={`bar ${pct == null ? 'indet' : ''}`}>
            <i style={{ width: `${Math.max(4, pct ?? 30)}%` }} />
          </span>
        )}
      </span>
    </a>
    <MoreButton onMenu={(e) => onMenu(e, x)} />
    </div>
  );
}

/** A row of the Archived filter: dimmed, its archived date, Restore at hand (and the same menu). */
function ArchivedRow({ x, picked, onPick, onMenu, ra }: { x: ActionTarget; picked: boolean; onPick: PickFn; onMenu: MenuFn; ra: RowActionsApi }) {
  const when = x.i ? archivedLine(x.i) : x.r?.archived_at ? archivedLine({ archived_at: x.r.archived_at }) : t('projects.archivedNoDate');
  return (
    <div className={`st-rowwrap archived ${picked ? 'picked' : ''}`} onContextMenu={(e) => onMenu(e, x)} data-picked={picked ? 'true' : undefined}>
      <div className={`st-row ${picked ? 'picked' : ''}`} role="button" tabIndex={0} onClick={(e) => onPick(e, x.key)} data-testid="studio-archived-row" data-row={x.key} data-kind={x.kind}>
        <Thumb src={x.i?.thumb ?? null} className="st-th" />
        <span className="tx">
          <b className="clamp1">{x.title || t('home.planningRow')}</b>
          <span className="s clamp1">{when}</span>
        </span>
      </div>
      <button className="btn sm st-restore" onClick={() => void ra.run('restore', [x])} data-testid="studio-restore">
        <ArchiveRestore className="ico" />
        {t('ra.restore')}
      </button>
      <MoreButton onMenu={(e) => onMenu(e, x)} />
    </div>
  );
}

/** What is picked: how many, Archive (or Restore under Archived), Delete… when every picked row can go, Clear. */
function BulkBar({ xs, rows, ra, inArchive, onClear }: { xs: ActionTarget[]; rows: StudioRow[]; ra: RowActionsApi; inArchive: boolean; onClear: () => void }) {
  const acts = bulkActions(xs);
  return (
    <div className="st-bulk" data-testid="studio-bulk" role="toolbar" aria-label={t('c.selected', { n: xs.length })}>
      <b>{t('c.selected', { n: xs.length })}</b>
      <span className="sp" />
      {!inArchive && <BulkMore rows={rows} xs={xs} ra={ra} />}
      {!inArchive && acts.includes('archive') && (
        <button className="btn sm" onClick={() => void ra.run('archive', xs)} data-testid="studio-bulk-archive" data-tip={keyHint('⌫')}>
          <Archive className="ico" />
          {t('ra.archive')}
        </button>
      )}
      {acts.includes('restore') && (
        <button className="btn sm" onClick={() => void ra.run('restore', xs)} data-testid="studio-bulk-restore">
          <ArchiveRestore className="ico" />
          {t('ra.restore')}
        </button>
      )}
      {acts.includes('delete') && (
        <button className="btn sm danger" onClick={() => void ra.run('delete', xs)} data-testid="studio-bulk-delete">
          <Trash2 className="ico" />
          {t('ra.delete')}
        </button>
      )}
      <button className="btn ghost icon sm" onClick={onClear} aria-label={t('ra.clear')} data-tip={t('ra.clear')} data-testid="studio-bulk-clear">
        <X className="ico" />
      </button>
    </div>
  );
}

/** A video with nothing in it (no file, or under a second and a half): said plainly, with Delete… / Archive. */
function EmptyClip({ r, ra, kind }: { r: StudioRow; ra: RowActionsApi; kind: 'none' | 'short' }) {
  const x = targetOf(r);
  const [hide, setHide] = useState(false);
  const acts = new Set(ra.items(x).map((m) => m.testId));
  if (hide) return null;
  return (
    <div className={`st-emptyclip ${kind}`} role="status" data-testid="studio-empty-clip" data-kind={kind}>
      <span className="tx">{kind === 'none' ? t('st.emptyClip.none') : t('st.emptyClip.short', { d: fmtLen(r.duration) })}</span>
      <span className="sp" />
      {acts.has('row-delete') && (
        <button className="btn sm danger" onClick={() => void ra.run('delete', [x])} data-testid="studio-empty-delete">
          <Trash2 className="ico" />
          {t('ra.delete')}
        </button>
      )}
      {acts.has('row-archive') && (
        <button className="btn sm" onClick={() => void ra.run('archive', [x])} data-testid="studio-empty-archive">
          <Archive className="ico" />
          {t('ra.archive')}
        </button>
      )}
      {kind === 'short' && (
        <button className="btn sm ghost" onClick={() => setHide(true)} data-testid="studio-empty-keep">
          {t('st.emptyClip.keep')}
        </button>
      )}
    </div>
  );
}

/** A video that stopped before it was made (its step failed): where and why, in plain words, and what she can do -
 * never "the recording may have been empty". */
function FailedClip({ r, ra }: { r: StudioRow; ra: RowActionsApi }) {
  const x = targetOf(r);
  const acts = new Set(ra.items(x).map((m) => m.testId));
  const f = r.i?.failure ?? null;
  const step = stepOfStage(f?.stage) ?? (f ? null : r.p.current);
  return (
    <div className="st-emptyclip failed" role="status" data-testid="studio-failed-clip">
      <span className="tx">
        <b>{t('st.failedClip.title')}</b>
        {step ? <span className="muted"> · {t('st.failedClip.at', { step: tk(`hub.step.${step}`) })}</span> : null}
        {f ? <span className="muted"> · {failureReason(f)}</span> : null}
        <br />
        <span className="muted small">{t('st.failedClip.next')}</span>
      </span>
      <span className="sp" />
      {acts.has('row-retry') && (
        <button className="btn sm primary" onClick={() => void ra.run('retry', [x])} data-testid="studio-failed-retry">
          <RotateCcw className="ico" />
          {t('run.tryAgain')}
        </button>
      )}
      {acts.has('row-archive') && (
        <button className="btn sm" onClick={() => void ra.run('archive', [x])} data-testid="studio-failed-drop">
          <Archive className="ico" />
          {t('st.failedClip.drop')}
        </button>
      )}
    </div>
  );
}

/** The right side: the video's page, or what a request / a project without clips / a project's question needs. */
function Page({ r, posts, more, ra }: { r: StudioRow; posts: CalendarPost[]; more: (e: { clientX: number; clientY: number }) => void; ra: RowActionsApi }) {
  const head = <MoreButton onMenu={more} testId="studio-page-more" className="st-pagemore" />;
  const failed = r.kind === 'clip' && !r.video && r.clipState === 'failed';
  const empty = r.kind === 'clip' && r.group !== 'run' && !notMadeYet(r) && !failed ? emptyClip(r.video, r.duration) : null;
  // a made clip: its page; one still being made: what it waits for (its question), else where its project is
  if (r.kind === 'clip' && r.video)
    return <OutputEditor id={r.item!} clip={r.clip!} layout="studio" ask={r.ask} place={{ project: r.project, pos: r.pos }} more={<MoreButton onMenu={more} testId="studio-page-more" />} notice={empty ? <EmptyClip r={r} ra={ra} kind={empty} /> : null} />;
  if (failed && !r.ask && r.p.state !== 'run' && r.p.state !== 'queued')
    return (
      <div className="st-detail st-withmore">
        {head}
        <FailedClip r={r} ra={ra} />
      </div>
    );
  if (r.kind === 'clip' && empty === 'none' && !r.ask)
    return (
      <div className="st-detail st-withmore">
        {head}
        <EmptyClip r={r} ra={ra} kind="none" />
      </div>
    );
  // a request being planned and a project being made: the run page (hero, what happened, the live pane)
  if (r.kind === 'request')
    return (
      <div className="st-run st-withmore">
        {head}
        <RequestRun r={r.r!} />
      </div>
    );
  // (a video not made yet in a project being made: the project's run page too - its pieces, the chat, the live pane)
  if (!r.ask && r.i && (r.p.state === 'run' || r.p.state === 'queued') && (r.kind !== 'clip' || !r.video))
    return (
      <div className="st-run st-withmore">
        {head}
        <ProjectRun i={r.i} p={itemPipeline(r.i, posts)} posts={posts} />
      </div>
    );
  if (r.ask)
    return (
      <AskPage
        x={r.ask}
        kind={r.kind}
        where={r.kind === 'clip' ? [r.project, r.pos ? `${r.pos[0]}/${r.pos[1]}` : null].filter(Boolean).join(' · ') : t('st.projectAsk')}
        title={r.title}
        more={<MoreButton onMenu={more} testId="studio-page-more" />}
      />
    );
  // a video not made yet (waiting its turn, its project paused or not started): where it is, never "empty" - above
  // its project's page and chat
  return <ProjectPage r={r} posts={posts} head={head} notice={notMadeYet(r) ? <NotMade r={r} /> : null} />;
}

/** A question on its own page, laid out like a video's page: the header (where it is, its name, ⋯) across the top,
 * the question below. */
function AskPage({ x, kind = 'project', where, title, more }: { x: InboxItem; kind?: StudioRow['kind']; where: string; title: string; more?: React.ReactNode }) {
  const resolve = useResolve();
  return (
    <div className="st-askpage" data-testid="studio-project-ask" data-kind={kind}>
      <header className="cs-top">
        <div className="cs-title">
          <span className="cs-where muted clamp1" data-testid="studio-where">
            {where}
          </span>
          <span className="cs-name">
            <h2 className="clamp1">{title}</h2>
          </span>
        </div>
        <div className="cs-actions">{more}</div>
      </header>
      <div className="st-askbody">
        <ItemPane key={x.key} x={x} onDone={(a) => void resolve(x, a)} onSkip={() => undefined} />
      </div>
    </div>
  );
}

/** "Not made yet - it's step 2 of 3": a video of a project that makes its videos one after another. */
function NotMade({ r }: { r: StudioRow }) {
  return (
    <div className="st-notmade" role="status" data-testid="studio-not-made">
      <b>{t('st.notMade')}</b>
      <span className="muted">{r.pos ? t('st.notMadeStep', { n: r.pos[0], m: r.pos[1] }) : t('st.notMadeOne')}</span>
    </div>
  );
}

/** The list's shape while its sources answer (never "No videos yet" before they have). */
function ListSkeleton() {
  return (
    <div className="st-sk" aria-busy="true" aria-label={t('c.loading')} data-testid="studio-list-skeleton">
      {Array.from({ length: 6 }, (_, k) => (
        <div key={k} className="st-skrow">
          <Sk w={64} h={40} r={6} />
          <span>
            <Sk w="70%" h={12} />
            <Sk w="45%" h={10} />
          </span>
        </div>
      ))}
    </div>
  );
}

function PageSkeleton() {
  return (
    <div className="st-detail" aria-busy="true" aria-label={t('c.loading')} data-testid="studio-page-skeleton">
      <Sk w="40%" h={14} />
      <div style={{ height: 10 }} />
      <Sk w="60%" h={22} />
      <div style={{ height: 18 }} />
      <Sk h={280} r={10} />
    </div>
  );
}

/** A project's own page in the Studio (ready with several videos, or not made yet): its details with the project chat
 * beside it (every finished clip at once, or the project itself: pick the music again, cut it again). */
function ProjectPage({ r, posts, head, notice = null }: { r: StudioRow; posts: CalendarPost[]; head: React.ReactNode; notice?: React.ReactNode }) {
  const i = r.i!;
  const { data, reload } = useLoad((c) => c.clips(i.id), [i.id, i.updated]);
  const made = (data?.clips ?? []).filter((c) => !c.extra && c.files.length && !['queued', 'planned', 'running', 'failed', 'waiting'].includes(c.state));
  return (
    <WithProjectChat item={i.id} clips={made} running={r.p.state === 'run'} onApplied={reload}>
      <div className="st-detail st-withmore">
        {head}
        {notice}
        <ProjectDetail i={i} p={itemPipeline(i, posts)} posts={posts} />
      </div>
    </WithProjectChat>
  );
}
