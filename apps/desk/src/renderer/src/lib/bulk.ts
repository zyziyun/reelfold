// All projects' bulk bar for hundreds of videos (pure, unit-tested): which of the picked videos each action can
// take - Approve (their questions, answered the recommended way), Schedule (made and not scheduled yet), Try again
// (failed / stopped runs), Change with AI (made videos, one request per project) - so a button shows only when it
// does something and says how many it takes.
import type { InboxItem } from '../../../shared/v04';
import { answerOf } from './inboxView';
import { rowActions, type ActionTarget } from './rowActions';
import type { StudioRow } from './studio';

/** A question that has a recommended answer to take as it is (not a failure, not one that waits for her files or
 * owns its own screen, not a draft still being written, not a voice with no free one to fall back to). */
export function canApprove(x: InboxItem): boolean {
  if (x.failure || x.kind === 'failed' || x.kind === 'needs' || x.kind === 'plan' || x.href) return false;
  if (x.author) return !!x.author.review && !x.author.drafting;
  if (x.no_key) return !!x.no_key.free_engine;
  return true;
}

/** The answer Approve sends: the recommended choices (what the Inbox's primary button sends untouched). */
export function approveAnswer(x: InboxItem): Record<string, unknown> | undefined {
  if (x.author || x.no_key) return undefined;
  return x.kind === 'confirm' || (x.options ?? []).length > 0 || x.code === 'inbox.spend' ? answerOf(x) : undefined;
}

export interface BulkWork {
  /** the questions to approve, once each (a project's question pinned on several of its videos counts once) */
  approve: InboxItem[];
  /** made videos with no post yet, by project */
  schedule: Map<string, string[]>;
  /** failed / stopped runs (one per project / request) */
  retry: ActionTarget[];
  /** made videos, by project (Change with AI asks once per project for exactly these) */
  change: Map<string, string[]>;
}

const add = (m: Map<string, string[]>, k: string, v: string) => m.set(k, [...new Set([...(m.get(k) ?? []), v])]);

export function bulkWork(rows: StudioRow[], targets: ActionTarget[]): BulkWork {
  const approve = new Map<string, InboxItem>();
  const schedule = new Map<string, string[]>();
  const change = new Map<string, string[]>();
  for (const r of rows) {
    if (r.ask && canApprove(r.ask)) approve.set(r.ask.key, r.ask);
    if (r.kind === 'clip' && r.item && r.clip && r.video) {
      add(change, r.item, r.clip);
      if (r.group === 'ready') add(schedule, r.item, r.clip);
    }
  }
  const seen = new Set<string>();
  const retry = targets.filter((x) => {
    const k = x.r ? `r:${x.r.id}` : x.i ? x.i.dir : x.key;
    if (seen.has(k) || !rowActions(x).includes('retry')) return false;
    seen.add(k);
    return true;
  });
  return { approve: [...approve.values()], schedule, retry, change };
}

export const count = (m: Map<string, string[]>) => [...m.values()].reduce((s, v) => s + v.length, 0);
