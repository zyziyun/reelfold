// The publish loop's clock. Every tick (30 s while the app runs, and once at launch): reads the 发布 calendar,
// finds the posts whose time has come, and
//   - assisted platforms (the default, her standing rule): one notification per post ("Time to post: … → 小红书");
//     clicking it opens the built-in browser with the form filled - she presses Publish herself;
//   - a platform she connected an official API for (YouTube, opt-in): uploads it `leadMs` before the time with the
//     platform's own scheduled publishing (publishAt), or right away when the app was closed at the time (up to
//     `apiGraceMs` late; later than that it falls back to the notification - she decides).
// Posts that came due while the app was closed show as overdue on launch (Publish / Home banner). No electron
// import: the clock, the calendar and the notifier are injected (tests drive it with a fake clock).
import fs from 'node:fs';
import { UploadOutcomeUnknown } from './outcome';
import path from 'node:path';
import { apiDeliveryState, type YtPublishResult } from '../../shared/publish/apiPlatforms';
import type { CalendarPost } from '../../shared/v04';
import { duePosts, localDate, upcomingPosts } from '../../shared/publish/postNow';

export interface ApiAttempt {
  account?: string | null;
  at: string;
  status: 'uploading' | 'done' | 'failed' | 'unverified';
  tries: number;
  detail?: string;
  url?: string;
  lastTry: number;
  /** The upload receipt is durable independently of the local calendar update. */
  calendarSynced?: boolean;
  resolvedAccount?: string;
  result?: YtPublishResult;
  source?: 'manual' | 'scheduled';
  lastCheck?: number;
}

interface State {
  /** post id -> the `at` it was announced for (moving a post re-announces it) */
  notified: Record<string, string>;
  api: Record<string, ApiAttempt>;
}

export type ApiUpload = { ok: true; url: string | null; account?: string; result?: YtPublishResult } | { ok: false; error: string; unverified?: boolean };

export function apiFailure(error: unknown): Extract<ApiUpload, { ok: false }> {
  return { ok: false, error: error instanceof Error ? error.message : String(error),
    ...(error instanceof UploadOutcomeUnknown ? { unverified: true } : {}) };
}

export interface ApiPoster {
  /** this post goes through an official API (connected + switched on for its platform) */
  wants(p: CalendarPost): boolean;
  publish(p: CalendarPost, publishAt: Date | null): Promise<ApiUpload>;
  recover?(p: CalendarPost): Promise<Extract<ApiUpload, { ok: true }> | null>;
  canRefresh?(p: CalendarPost): boolean;
  refresh?(p: CalendarPost, result: YtPublishResult): Promise<YtPublishResult>;
}

export interface SchedulerDeps {
  load(): Promise<CalendarPost[]>;
  now(): Date;
  /** posts that just came due (each announced once) */
  notify(fresh: CalendarPost[]): void;
  /** the due list changed (the renderer's banner) */
  onChange?(due: CalendarPost[]): void;
  markPosted(p: CalendarPost, url: string | null, via: 'api', result?: YtPublishResult): Promise<void>;
  api?: ApiPoster;
  stateFile: string;
  log?(msg: string): void;
  /** upload this long before the time with publishAt (default 60 min) */
  leadMs?: number;
  /** after the time, still auto-post through an API for this long (default 6 h); later: ask her */
  apiGraceMs?: number;
}

const MAX_TRIES = 3;
const RETRY_MS = 10 * 60_000;

export class PublishScheduler {
  private state: State;
  private timer: ReturnType<typeof setInterval> | null = null;
  private busy = false;
  private last: CalendarPost[] = [];
  private stateReadable = true;
  private checking = new Map<string, Promise<YtPublishResult>>();
  private syncing = new Map<string, Promise<void>>();
  private checkedBatchAt = 0;
  private recoveredBatchAt = 0;
  private uploading = new Set<string>();

  constructor(private deps: SchedulerDeps) {
    this.state = this.read();
  }

  private read(): State {
    try {
      const s = JSON.parse(fs.readFileSync(this.deps.stateFile, 'utf8')) as State;
      const record = (v: unknown) => !!v && typeof v === 'object' && !Array.isArray(v);
      if (!record(s) || (s.notified !== undefined && (!record(s.notified) || Object.values(s.notified).some((at) => typeof at !== 'string'))) ||
        (s.api !== undefined && (!record(s.api) || Object.values(s.api).some((a) =>
        !record(a) || typeof a.at !== 'string' || !['uploading', 'done', 'failed', 'unverified'].includes(a.status) ||
        !Number.isInteger(a.tries) || a.tries < 1 || !Number.isFinite(a.lastTry))))) {
        throw new Error('Invalid upload receipt journal');
      }
      return { notified: s.notified ?? {}, api: s.api ?? {} };
    } catch (e) {
      if ((e as NodeJS.ErrnoException).code !== 'ENOENT') {
        this.stateReadable = false;
        this.deps.log?.(`[scheduler] state unreadable; automatic uploads stopped: ${(e as Error).message}`);
      }
      return { notified: {}, api: {} };
    }
  }

  private write(): boolean {
    if (!this.stateReadable) return false;
    try {
      fs.mkdirSync(path.dirname(this.deps.stateFile), { recursive: true });
      const tmp = this.deps.stateFile + '.tmp';
      fs.writeFileSync(tmp, JSON.stringify(this.state, null, 1));
      fs.renameSync(tmp, this.deps.stateFile);
      return true;
    } catch (e) {
      this.deps.log?.(`[scheduler] could not save state: ${(e as Error).message}`);
      return false;
    }
  }

  /** Due posts she still has to publish (API posts in progress or done are not hers to do). */
  get due(): CalendarPost[] {
    return this.last;
  }

  apiState(id: string): ApiAttempt | undefined {
    return this.state.api[id];
  }

  start(intervalMs = 30_000) {
    this.stop();
    void this.tick();
    this.timer = setInterval(() => void this.tick(), intervalMs);
    (this.timer as { unref?: () => void }).unref?.();
  }

  stop() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  async tick(): Promise<{ due: CalendarPost[]; fresh: CalendarPost[]; api: string[] }> {
    if (this.busy) return { due: this.last, fresh: [], api: [] };
    this.busy = true;
    try {
      let posts: CalendarPost[];
      try {
        posts = await this.deps.load();
      } catch (e) {
        this.deps.log?.(`[scheduler] calendar not readable: ${(e as Error).message}`);
        return { due: this.last, fresh: [], api: [] };
      }
      const now = this.deps.now();
      const apiRan = await this.runApi(posts, now);
      const byApi = (p: CalendarPost) => {
        const a = this.state.api[p.id];
        return a && a.at === p.at && (a.account ?? null) === (p.account ?? null) && (a.status === 'uploading' || a.status === 'done' || (a.status === 'failed' && a.source !== 'manual' && a.tries < MAX_TRIES && this.deps.api?.wants(p)));
      };
      const due = duePosts(posts, now).filter((p) => !byApi(p));
      const fresh = due.filter((p) => this.state.notified[p.id] !== p.at);
      for (const p of fresh) this.state.notified[p.id] = p.at;
      // forget posts that are gone or posted
      const live = new Set(posts.filter((p) => p.state !== 'posted').map((p) => p.id));
      for (const id of Object.keys(this.state.notified)) if (!live.has(id)) delete this.state.notified[id];
      if (fresh.length || apiRan.length) this.write();
      if (fresh.length) this.deps.notify(fresh);
      const changed = due.map((p) => `${p.id}@${p.at}`).join() !== this.last.map((p) => `${p.id}@${p.at}`).join();
      this.last = due;
      if (changed) this.deps.onChange?.(due);
      return { due, fresh, api: apiRan };
    } finally {
      this.busy = false;
    }
  }

  private async runApi(posts: CalendarPost[], now: Date): Promise<string[]> {
    const api = this.deps.api;
    if (!api || !this.stateReadable) return [];
    // Reconcile receipts even outside the upload window or after auto-upload is switched off.
    // A remote success must never become a new upload because the local calendar was unavailable.
    for (const p of posts) {
      const receipt = this.state.api[p.id];
      if (p.state === 'posted' && p.via === 'manual') continue;
      if (receipt?.status === 'done' && (!receipt.calendarSynced || (receipt.result && (apiDeliveryState(receipt.result) !== p.state || !p.api_result))) && receipt.at === p.at && ((receipt.account ?? null) === (p.account ?? null) || (!!receipt.resolvedAccount && receipt.resolvedAccount === p.account))) {
        await this.syncReceipt(p, receipt);
      }
    }
    // Read back pending uploads after restart without sending video bytes or changing visibility.
    if (api.recover && now.getTime() - this.recoveredBatchAt >= 5 * 60_000) {
      this.recoveredBatchAt = now.getTime();
      const pending = posts.filter(p => {
        const a = this.state.api[p.id];
        return a && ['uploading', 'unverified'].includes(a.status) && !this.uploading.has(p.id) &&
          a.at === p.at && (a.account ?? null) === (p.account ?? null) &&
          now.getTime() - (a.lastCheck ?? 0) >= 5 * 60_000 && p.state !== 'posted';
      }).sort((a, b) => (this.state.api[a.id]?.lastCheck ?? 0) - (this.state.api[b.id]?.lastCheck ?? 0)).slice(0, 3);
      for (const p of pending) {
        const previous = this.state.api[p.id];
        previous.lastCheck = now.getTime();
        if (!this.write()) continue;
        try {
          const r = await api.recover(p);
          if (this.state.api[p.id] !== previous) continue;
          if (!r) {
            previous.status = 'unverified';
            previous.detail = 'Upload completion is not confirmed. Check YouTube Studio.';
            this.write();
            continue;
          }
          const current = (await this.deps.load()).find(row => row.id === p.id);
          if (!current || current.at !== p.at || (current.account ?? null) !== (p.account ?? null) || current.state === 'posted') continue;
          const receipt: ApiAttempt = { ...previous, status: 'done', calendarSynced: false,
            url: r.url ?? undefined, result: r.result, resolvedAccount: r.account };
          this.state.api[p.id] = receipt;
          await this.syncReceipt(current, receipt);
        } catch (e) {
          previous.status = 'unverified';
          previous.detail = 'Upload verification is unavailable. Check YouTube Studio.';
          this.write();
          this.deps.log?.(`[scheduler] upload verification pending: ${(e as Error).message}`);
        }
      }
    }
    // Bounded readback independent of opt-in uploads: at most three reads per five minutes.
    if (api.refresh && now.getTime() - this.checkedBatchAt >= 5 * 60_000) {
      this.checkedBatchAt = now.getTime();
      const candidates = posts.filter(p => p.via === 'api' && p.api_result && api.canRefresh?.(p) &&
        now.getTime() - (this.state.api[p.id]?.lastCheck ?? 0) >= 5 * 60_000 &&
        (!p.api_result.uploadStatus || !['failed', 'rejected', 'deleted'].includes(p.api_result.uploadStatus)))
        .sort((a, b) => (this.state.api[a.id]?.lastCheck ?? 0) - (this.state.api[b.id]?.lastCheck ?? 0)).slice(0, 3);
      for (const p of candidates) {
        try { await this.refresh(p, r => api.refresh!(p, r)); }
        catch (e) { this.deps.log?.(`[scheduler] status check ${p.id} failed: ${(e as Error).message}`); }
      }
    }
    const lead = this.deps.leadMs ?? 60 * 60_000;
    const grace = this.deps.apiGraceMs ?? 6 * 3600_000;
    const t = now.getTime();
    const candidates = [
      ...upcomingPosts(posts, now, lead),
      ...duePosts(posts, now).filter((p) => t - localDate(p.at).getTime() <= grace),
    ].filter((p) => api.wants(p));
    const ran: string[] = [];
    for (const p of candidates) {
      const prev = this.state.api[p.id];
      // A manual form can contain different visibility/audience choices. Never retry it
      // with the scheduler's defaults after a failure.
      if (prev?.source === 'manual') continue;
      const same = prev && prev.at === p.at && (prev.account ?? null) === (p.account ?? null);
      if (prev && ['done', 'uploading', 'unverified'].includes(prev.status)) continue;
      if (same) {
        if (prev.status !== 'failed' || prev.tries >= MAX_TRIES || t - prev.lastTry < RETRY_MS) continue;
      }
      const at = localDate(p.at);
      // YouTube refuses a publishAt in the past or too close: schedule only when it is comfortably ahead
      const publishAt = at.getTime() - t > 15 * 60_000 ? at : null;
      const r = await this.upload(p, () => api.publish(p, publishAt), 'scheduled');
      if (r.ok || this.state.api[p.id]?.lastTry === t) ran.push(p.id);
    }
    return ran;
  }

  /** One durable owner for manual and scheduled uploads. No await before claiming the post. */
  async upload(p: CalendarPost, publish: () => Promise<ApiUpload>, source: 'manual' | 'scheduled' = 'manual'): Promise<ApiUpload> {
    if (!this.stateReadable) return { ok: false, error: 'Upload history is unreadable; check the platform before uploading again.' };
    const prev = this.state.api[p.id];
    if (prev?.status === 'unverified') return { ok: false, unverified: true, error: prev.detail ?? 'Upload outcome unconfirmed. Check YouTube Studio before uploading again.' };
    if (prev?.status === 'uploading') return { ok: false, error: 'This post has an upload in progress or awaiting verification. Check the platform before uploading again.' };
    if (prev?.status === 'done') {
      if (prev.at !== p.at || (prev.account ?? null) !== (p.account ?? null)) {
        return { ok: false, error: 'This post was already uploaded. Edit its time or account on the platform, or create a separate post.' };
      }
      if (!prev.calendarSynced) await this.syncReceipt(p, prev);
      return { ok: true, url: prev.url ?? prev.result?.url ?? null, account: prev.resolvedAccount, result: prev.result };
    }
    const rec: ApiAttempt = { at: p.at, account: p.account, source, status: 'uploading', tries: (prev?.at === p.at && (prev.account ?? null) === (p.account ?? null) ? prev.tries : 0) + 1, lastTry: this.deps.now().getTime() };
    this.state.api[p.id] = rec;
    if (!this.write()) {
      if (prev) this.state.api[p.id] = prev;
      else delete this.state.api[p.id];
      return { ok: false, error: 'Could not save upload history. No upload was started.' };
    }
    this.uploading.add(p.id);
    try {
      let r: ApiUpload;
      try { r = await publish(); }
      catch (e) { r = apiFailure(e); }
      if (r.ok) {
        const receipt: ApiAttempt = { ...rec, status: 'done', calendarSynced: false, ...(r.account ? { resolvedAccount: r.account } : {}), ...(r.url ? { url: r.url } : {}), ...(r.result ? { result: r.result } : {}) };
        this.state.api[p.id] = receipt;
        await this.syncReceipt(p, receipt);
      } else {
        this.state.api[p.id] = { ...rec, status: r.unverified ? 'unverified' : 'failed', detail: r.error };
        this.deps.log?.(`[scheduler] API post ${p.id} failed: ${r.error}`);
      }
      this.write();
      return r;
    } finally { this.uploading.delete(p.id); }
  }

  /** Keep readback and calendar reconciliation ordered for this post, including a concurrent timer tick. */
  refresh(p: CalendarPost, read: (previous: YtPublishResult) => Promise<YtPublishResult>): Promise<YtPublishResult> {
    const running = this.checking.get(p.id);
    if (running) return running;
    const task = this.refreshOnce(p, read).finally(() => this.checking.delete(p.id));
    this.checking.set(p.id, task);
    return task;
  }

  private async refreshOnce(p: CalendarPost, read: (previous: YtPublishResult) => Promise<YtPublishResult>): Promise<YtPublishResult> {
    if (!this.stateReadable || p.via !== 'api' || !p.api_result) throw new Error('No confirmed API upload to check');
    const old = this.state.api[p.id];
    if (old && (old.status !== 'done' || ![old.account ?? null, old.resolvedAccount ?? null].includes(p.account ?? null))) throw new Error('Upload account does not match its receipt');
    const receipt: ApiAttempt = old ?? { at: p.at, account: p.account, status: 'done', tries: 1, lastTry: 0, result: p.api_result };
    receipt.lastCheck = this.deps.now().getTime();
    this.state.api[p.id] = receipt;
    if (!this.write()) throw new Error('Could not save upload history');
    const result = await read(receipt.result ?? p.api_result);
    const current = (await this.deps.load()).find(row => row.id === p.id);
    if (!current || current.via !== 'api' || !current.api_result || current.account !== p.account || current.api_result.url !== p.api_result.url) throw new Error('Post changed while checking its status');
    const fresh = { ...receipt, at: current.at, result, url: result.url, calendarSynced: false };
    this.state.api[p.id] = fresh;
    if (!this.write()) throw new Error('Status read, but could not save upload history');
    await this.syncReceipt(current, fresh);
    return result;
  }

  private async syncReceipt(p: CalendarPost, receipt: ApiAttempt): Promise<void> {
    const previous = this.syncing.get(p.id) ?? Promise.resolve();
    const task = previous.then(() => this.syncReceiptOnce(p, receipt));
    this.syncing.set(p.id, task);
    try { await task; }
    finally { if (this.syncing.get(p.id) === task) this.syncing.delete(p.id); }
  }

  private async syncReceiptOnce(p: CalendarPost, receipt: ApiAttempt): Promise<void> {
    if (this.state.api[p.id] !== receipt) return;
    // Save remote success before touching the calendar. Keep it in memory on disk errors,
    // while the previous durable 'uploading' record prevents a restart from re-uploading.
    if (!this.write()) return;
    try {
      if (p.state !== (receipt.result ? apiDeliveryState(receipt.result) : 'posted') || (receipt.result && JSON.stringify(p.api_result) !== JSON.stringify(receipt.result))) {
        await this.deps.markPosted(receipt.resolvedAccount ? { ...p, account: receipt.resolvedAccount } : p, receipt.url ?? receipt.result?.url ?? null, 'api', receipt.result);
      }
      receipt.calendarSynced = true;
      this.write();
    } catch (e) {
      this.deps.log?.(`[scheduler] API post ${p.id} uploaded; calendar sync pending: ${(e as Error).message}`);
    }
  }
}
