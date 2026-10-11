// All projects' search and filters (pure, unit-tested): words (a video's title, its project, the request it came
// from), a platform it is scheduled or posted on, one project, and when it last changed. Cheap enough to run on
// every keystroke over hundreds of rows.
import type { CalendarPost } from '../../../shared/v04';
import { orderPlatforms } from '../../../shared/platforms';
import type { StudioRow } from './studio';

export type FindDate = 'any' | 'today' | 'week';

export interface Find {
  q: string;
  platform: string | null;
  project: string | null;
  date: FindDate;
}

export const NO_FIND: Find = { q: '', platform: null, project: null, date: 'any' };

export function finding(f: Find): boolean {
  return !!(f.q.trim() || f.platform || f.project || f.date !== 'any');
}

/** The platforms each video (`item/clip`) and each project (`item`) has a post on. */
export function platformsByRow(posts: CalendarPost[]): Map<string, Set<string>> {
  const m = new Map<string, Set<string>>();
  for (const p of posts) {
    if (p.enabled === false) continue;
    const id = p.platform.split(':')[0];
    for (const k of [`${p.item}/${p.clip}`, p.item]) {
      const s = m.get(k) ?? new Set<string>();
      s.add(id);
      m.set(k, s);
    }
  }
  return m;
}

const norm = (s: string | null | undefined) => (s ?? '').toLocaleLowerCase().normalize('NFKC');

function startOfDay(now: number): number {
  const d = new Date(now);
  d.setHours(0, 0, 0, 0);
  return d.getTime() / 1000;
}

export function matches(r: StudioRow, f: Find, plats: Map<string, Set<string>>, now = Date.now()): boolean {
  if (f.project && r.item !== f.project) return false;
  if (f.platform) {
    const s = plats.get(r.kind === 'clip' ? r.key : (r.item ?? ''));
    if (!s?.has(f.platform)) return false;
  }
  if (f.date !== 'any') {
    const from = f.date === 'today' ? startOfDay(now) : now / 1000 - 7 * 86400;
    if (r.at < from) return false;
  }
  const q = norm(f.q).trim();
  if (q) {
    const hay = norm([r.title, r.project, r.i?.name, r.i?.prompt, r.r?.prompt, r.r?.name].filter(Boolean).join(' '));
    // every word she typed, in any order
    if (!q.split(/\s+/).every((w) => hay.includes(w))) return false;
  }
  return true;
}

export function findRows(rows: StudioRow[], f: Find, posts: CalendarPost[], now = Date.now()): StudioRow[] {
  if (!finding(f)) return rows;
  const plats = platformsByRow(posts);
  return rows.filter((r) => matches(r, f, plats, now));
}

/** What the filter menus offer: the platforms her posts are on (international first), the projects in the list. */
export function findOptions(rows: StudioRow[], posts: CalendarPost[]): { platforms: string[]; projects: [string, string][] } {
  const platforms = orderPlatforms(posts.filter((p) => p.enabled !== false).map((p) => p.platform.split(':')[0]));
  const projects = new Map<string, string>();
  for (const r of rows) if (r.item && r.kind !== 'request') projects.set(r.item, r.i?.name ?? r.project ?? r.title);
  return { platforms, projects: [...projects.entries()].sort((a, b) => a[1].localeCompare(b[1])) };
}
