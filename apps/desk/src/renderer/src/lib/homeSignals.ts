// Home's suggestion chips (pure, unit-tested), from her own signals only - never a canned idea:
//   recording - a fresh recording in a watched folder no project uses yet (the engine's /api/home/suggestions)
//   again     - a request she has sent more than once
//   share     - a post that went out on some of her platforms and not the others yet
//   series    - the next episode of a series she makes
//   finish    - a project with clips still to make
// No signal, no chip: Home hides the row.
import type { HistoryItem } from '../../../shared/v02';
import type { CalendarPost, HomeSuggestions } from '../../../shared/v04';
import { orderPlatforms } from '../../../shared/platforms';

export type SignalKind = 'recording' | 'again' | 'share' | 'series' | 'finish';

export interface HomeSignal {
  id: string;
  kind: SignalKind;
  /** recording: the file; again: the request; series / finish: the project's name; share: the post's title */
  text: string;
  /** again: how many times; finish: clips left; series: the next episode */
  n?: number;
  /** recording: its watched folder */
  folder?: string;
  /** share: the platforms it is not on yet (international first); where it already went */
  missing?: string[];
  on?: string[];
  thumb?: string | null;
  /** recording: its path (goes into the composer) */
  path?: string;
  /** share: the clip to open (its page publishes) */
  item?: string;
  clip?: string;
}

const base = (p: string) => p.split(':')[0];
const SHARE_DAYS = 14;

/** Posts that went out on some of her platforms: one per clip, the ones still missing (international first). */
export function shareSignals(posts: CalendarPost[], mine: string[], now = Date.now()): HomeSignal[] {
  const want = [...new Set(mine.map(base))];
  if (!want.length) return [];
  const by = new Map<string, CalendarPost[]>();
  for (const p of posts) {
    if (p.enabled === false) continue;
    const k = `${p.item}/${p.clip}`;
    by.set(k, [...(by.get(k) ?? []), p]);
  }
  const out: HomeSignal[] = [];
  const when = new Map<string, number>();
  for (const [k, ps] of by) {
    const posted = ps.filter((p) => p.state === 'posted');
    if (!posted.length) continue;
    const at = Math.max(...posted.map((p) => new Date(p.posted_at ?? p.at).getTime()));
    if (!Number.isFinite(at) || now - at > SHARE_DAYS * 86400000) continue;
    const on = new Set(ps.map((p) => base(p.platform)));
    const missing = orderPlatforms(want.filter((w) => !on.has(w)));
    if (!missing.length) continue;
    const p0 = posted[0];
    when.set(`share-${k}`, at);
    out.push({ id: `share-${k}`, kind: 'share', text: p0.title, missing, on: orderPlatforms([...on]), thumb: p0.cover, item: p0.item, clip: p0.clip });
  }
  return out.sort((a, b) => (when.get(b.id) ?? 0) - (when.get(a.id) ?? 0));
}

/** The next episode of a series she makes; a project with clips still to make (finished, not running). */
export function workSignals(items: HistoryItem[]): HomeSignal[] {
  const out: HomeSignal[] = [];
  const done = items.filter((i) => i.live?.state !== 'running' && !i.archived);
  const series = done.find((i) => i.series || i.type === 'aigc');
  if (series) out.push({ id: `series-${series.id}`, kind: 'series', text: series.series ?? series.name, n: (series.counts?.total ?? 0) + 1, thumb: series.thumb });
  const left = (i: HistoryItem) => (i.counts ? i.counts.total - Math.max(i.counts.done, i.counts.approved) : 0);
  const unfinished = done.find((i) => i !== series && i.counts?.total > 0 && left(i) > 0 && left(i) < i.counts.total && !i.failure && !i.stopped);
  if (unfinished) out.push({ id: `finish-${unfinished.id}`, kind: 'finish', text: unfinished.name, n: left(unfinished), thumb: unfinished.thumb });
  return out;
}

/** Every chip, strongest signal first: what just landed, what she keeps asking for, what can go further. */
export function homeSignals(s: HomeSuggestions | null | undefined, items: HistoryItem[], posts: CalendarPost[], mine: string[], now = Date.now()): HomeSignal[] {
  const rec: HomeSignal[] = (s?.recordings ?? []).map((r) => ({ id: `rec-${r.path}`, kind: 'recording', text: r.name, folder: r.folder, path: r.path }));
  const again: HomeSignal[] = (s?.recurring ?? []).map((r, k) => ({ id: `again-${k}`, kind: 'again', text: r.prompt, n: r.n }));
  return [...rec, ...again, ...shareSignals(posts, mine, now), ...workSignals(items)];
}
