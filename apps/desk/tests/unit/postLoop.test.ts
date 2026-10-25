// The publish loop: due posts on a fake clock, the scheduler (one notification per post, overdue on launch, the
// API path with publishAt / retries / fallback), which file and text a post gets, the success signal, title
// counting, session-cookie login detection, the text selectors, and YouTube's metadata.
import fs from 'node:fs';
import { UploadOutcomeUnknown } from '../../src/main/publish/outcome';
import os from 'node:os';
import path from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import { loadAdapters } from '../../src/main/publish/adapters';
import { apiDeliveryState } from '../../src/shared/publish/apiPlatforms';
import { ytMeta } from '../../src/main/publish/api/youtube';
import { probeLogin } from '../../src/main/publish/loginProbe';
import { PublishScheduler } from '../../src/main/publish/scheduler';
import { saveCapture } from '../../src/main/publish/capture';
import { sessionLoginState } from '../../src/shared/channels';
import { partitionFor, validateIpc } from '../../src/shared/ipc';
import { parseAdapter } from '../../src/shared/publish/adapterSchema';
import { copyForPost, duePosts, localDate, pickFile, postedSignal, titleLength, upcomingPosts } from '../../src/shared/publish/postNow';
import { findJs, parseSelector, selectorError } from '../../src/shared/publish/selectors';
import type { CalendarPost } from '../../src/shared/v04';

const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-loop-'));
const post = (id: string, at: string, extra: Partial<CalendarPost> = {}): CalendarPost => ({ id, item: 'aaaaaaaaaaaa', clip: 'A', title: '再小的博主，也是博主', cover: null, platform: 'xiaohongshu', at, state: 'ready', ...extra });
const adapters = loadAdapters([path.resolve(__dirname, '../../adapters')]).adapters;
const by = Object.fromEntries(adapters.map((a) => [a.id, a]));

describe('due posts', () => {
  const now = new Date(2026, 9, 7, 20, 5); // Wed 7 Oct 2026, 20:05 local
  it('local "at" times; due = time passed, not posted, switched on, within 14 days', () => {
    expect(localDate('2026-10-07T20:00').getHours()).toBe(20);
    const ps = [post('p1', '2026-10-07T20:00'), post('p2', '2026-10-07T20:30'), post('p3', '2026-10-07T19:00', { state: 'posted' }), post('p4', '2026-10-06T09:00', { enabled: false }), post('p5', '2026-09-01T09:00'), post('p6', '2026-10-05T08:00')];
    expect(duePosts(ps, now).map((p) => p.id)).toEqual(['p6', 'p1']);
    expect(upcomingPosts(ps, now, 30 * 60_000).map((p) => p.id)).toEqual(['p2']);
  });
});

describe('scheduler', () => {
  const mk = (posts: CalendarPost[], clock: { t: Date }, extra: Partial<ConstructorParameters<typeof PublishScheduler>[0]> = {}) => {
    const notified: string[][] = [];
    const posted: string[] = [];
    const s = new PublishScheduler({
      load: async () => posts,
      now: () => clock.t,
      notify: (fresh) => notified.push(fresh.map((p) => p.id)),
      markPosted: async (p) => void posted.push(p.id),
      stateFile: path.join(tmp(), 'scheduler.json'),
      ...extra,
    });
    return { s, notified, posted };
  };

  it('announces each post once when its time comes; overdue ones at launch; moving a post re-announces it', async () => {
    const clock = { t: new Date(2026, 9, 7, 19, 59) };
    const ps = [post('p1', '2026-10-07T20:00'), post('old', '2026-10-06T21:00')];
    const { s, notified } = mk(ps, clock);
    let r = await s.tick();
    expect(r.due.map((p) => p.id)).toEqual(['old']); // came due while the app was closed
    expect(notified).toEqual([['old']]);
    clock.t = new Date(2026, 9, 7, 20, 0, 30);
    r = await s.tick();
    expect(r.due.map((p) => p.id)).toEqual(['old', 'p1']);
    expect(notified).toEqual([['old'], ['p1']]);
    await s.tick();
    expect(notified.length).toBe(2); // once
    ps[0] = { ...ps[0], at: '2026-10-07T20:00' };
    ps[1] = { ...ps[1], at: '2026-10-07T18:00' }; // she moved it: a new time is a new announcement
    await s.tick();
    expect(notified[2]).toEqual(['old']);
    ps[0] = { ...ps[0], state: 'posted' };
    r = await s.tick();
    expect(r.due.map((p) => p.id)).toEqual(['old']);
  });

  it('a newly chosen account starts its own attempt instead of inheriting another account failure', async () => {
    const clock = { t: new Date(2026, 9, 7, 19, 30) };
    const p = post('y1', '2026-10-07T20:00', { platform: 'youtube', account: 'main' });
    const accounts: string[] = [];
    const { s } = mk([p], clock, { api: { wants: () => true, publish: async (p) => {
      accounts.push(p.account!);
      return { ok: false, error: 'sign in again' };
    } } });
    await s.tick();
    await s.tick();
    expect(accounts).toEqual(['main']);
    p.account = 'brand';
    await s.tick();
    expect(accounts).toEqual(['main', 'brand']);
    expect(s.apiState('y1')).toMatchObject({ account: 'brand', tries: 1 });
  });

  it('the state survives a restart (no second notification for the same post)', async () => {
    const clock = { t: new Date(2026, 9, 7, 21, 0) };
    const file = path.join(tmp(), 's.json');
    const ps = [post('p1', '2026-10-07T20:00')];
    const n1: string[] = [];
    const a = new PublishScheduler({ load: async () => ps, now: () => clock.t, notify: (f) => n1.push(...f.map((p) => p.id)), markPosted: async () => undefined, stateFile: file });
    await a.tick();
    const n2: string[] = [];
    const b = new PublishScheduler({ load: async () => ps, now: () => clock.t, notify: (f) => n2.push(...f.map((p) => p.id)), markPosted: async () => undefined, stateFile: file });
    const r = await b.tick();
    expect(n1).toEqual(['p1']);
    expect(n2).toEqual([]);
    expect(r.due.map((p) => p.id)).toEqual(['p1']); // still due (she has not posted it)
  });

  it('API posts upload an hour ahead with publishAt, never show as hers; failures retry, then fall back to her', async () => {
    const clock = { t: new Date(2026, 9, 7, 19, 30) };
    const yt = post('y1', '2026-10-07T20:00', { platform: 'youtube' });
    const calls: { id: string; at: Date | null }[] = [];
    let fail = false;
    const { s, notified, posted } = mk([yt, post('x1', '2026-10-07T20:00')], clock, {
      api: {
        wants: (p) => p.platform === 'youtube',
        publish: async (p, at) => {
          calls.push({ id: p.id, at });
          return fail ? { ok: false, error: 'quotaExceeded' } : { ok: true, url: 'https://youtu.be/abc' };
        },
      },
    });
    await s.tick();
    expect(calls).toEqual([{ id: 'y1', at: localDate('2026-10-07T20:00') }]);
    expect(posted).toEqual(['y1']);
    await s.tick();
    expect(calls.length).toBe(1);
    clock.t = new Date(2026, 9, 7, 20, 1);
    const r = await s.tick();
    expect(r.due.map((p) => p.id)).toEqual(['x1']); // y1 went through the API
    expect(notified.flat()).toEqual(['x1']);

    // failing API: retried (not announced) until 3 tries, then she gets the notification
    const clock2 = { t: new Date(2026, 9, 8, 9, 5) };
    const y2 = post('y2', '2026-10-08T09:00', { platform: 'youtube' });
    calls.length = 0;
    fail = true;
    const m = mk([y2], clock2, { api: { wants: () => true, publish: async (p, at) => (calls.push({ id: p.id, at }), { ok: false, error: 'quotaExceeded' }) } });
    await m.s.tick();
    expect(calls[0].at).toBeNull(); // late: public now, no publishAt
    expect(m.notified).toEqual([]);
    clock2.t = new Date(2026, 9, 8, 9, 20);
    await m.s.tick();
    clock2.t = new Date(2026, 9, 8, 9, 35);
    const last = await m.s.tick();
    expect(calls.length).toBe(3);
    expect(last.due.map((p) => p.id)).toEqual(['y2']);
    expect(m.notified).toEqual([['y2']]);
    expect(m.s.apiState('y2')).toMatchObject({ status: 'failed', tries: 3, detail: 'quotaExceeded' });
  });

  it('persists uncertain outcomes without repeating manual or scheduled uploads', async () => {
    const clock = { t: new Date(2026, 9, 7, 20, 1) };
    const p = post('uncertain', '2026-10-07T20:00', { platform: 'youtube' });
    const stateFile = path.join(tmp(), 'state.json');
    const publish = vi.fn(async () => { throw new UploadOutcomeUnknown('Check YouTube Studio'); });
    const api = { wants: () => true, publish };
    const first = mk([p], clock, { stateFile, api });
    const tick = await first.s.tick();
    expect(tick.due.map(p => p.id)).toEqual(['uncertain']);
    expect(first.s.apiState(p.id)).toMatchObject({ status: 'unverified', tries: 1 });
    clock.t = new Date(2026, 9, 7, 20, 30);
    const restarted = mk([p], clock, { stateFile, api });
    await restarted.s.tick();
    expect(await restarted.s.upload(p, publish)).toMatchObject({ ok: false, unverified: true });
    await restarted.s.upload({ ...p, account: 'other', at: '2026-10-07T21:00' }, publish);
    expect(publish).toHaveBeenCalledTimes(1);
  });

  it('continues an interrupted manual upload once, sharing ownership with timer recovery', async () => {
    const p = post('manual-resume', '2026-10-07T20:00', { platform: 'youtube', account: 'main' });
    const clock = { t: new Date(2026, 9, 7, 20, 1) };
    const autoRecover = vi.fn(async () => null);
    const m = mk([p], clock, { api: { wants: () => false, publish: vi.fn(), recover: autoRecover } });
    await m.s.upload(p, async () => { throw new UploadOutcomeUnknown('Interrupted'); });
    const result = { id: 'old', url: 'https://youtu.be/old', privacy: 'private', publishAt: null, lockedPrivate: false, warnings: [] };
    let finish!: () => void;
    const held = new Promise<void>(resolve => { finish = resolve; });
    const recover = vi.fn(async () => { await held; return { ok: true as const, url: result.url, result, account: 'main' }; });
    expect(await m.s.recoverUpload({ ...p, account: 'other' }, recover)).toMatchObject({ ok: false });
    expect(await m.s.recoverUpload({ ...p, at: '2026-10-08T20:00' }, recover)).toMatchObject({ ok: false });
    expect(recover).not.toHaveBeenCalled();
    const task = m.s.recoverUpload(p, recover);
    expect(m.s.isUploading(p.id)).toBe(true);
    expect(await m.s.recoverUpload(p, recover)).toMatchObject({ ok: false });
    await m.s.tick();
    expect(autoRecover).not.toHaveBeenCalled();
    finish();
    expect(await task).toMatchObject({ ok: true, result });
    expect(recover).toHaveBeenCalledTimes(1);
    expect(m.posted).toEqual([p.id]);
    expect(m.s.isUploading(p.id)).toBe(false);
    expect(m.s.apiState(p.id)).toMatchObject({ status: 'done', source: 'manual', calendarSynced: true });
  });

  it('retains an interrupted session when manual recovery fails and permits another attempt', async () => {
    const p = post('resume-failed', '2026-10-07T20:00', { platform: 'youtube' });
    const m = mk([p], { t: new Date(2026, 9, 7, 20, 1) });
    await m.s.upload(p, async () => { throw new UploadOutcomeUnknown('Interrupted'); });
    const recover = vi.fn(async () => { throw new Error('Source file changed'); });
    expect(await m.s.recoverUpload(p, recover)).toMatchObject({ ok: false, unverified: true, error: 'Source file changed' });
    expect(m.s.isUploading(p.id)).toBe(false);
    expect(m.s.apiState(p.id)).toMatchObject({ status: 'unverified' });
    await m.s.recoverUpload(p, recover);
    expect(recover).toHaveBeenCalledTimes(2);
    expect(m.posted).toEqual([]);
  });

  it('reconciles an unknown upload after restart even with automatic publishing switched off', async () => {
    const clock = { t: new Date(2026, 9, 7, 20, 1) };
    const p = post('recover', '2026-10-07T20:00', { platform: 'youtube' });
    const stateFile = path.join(tmp(), 'state.json');
    const first = mk([p], clock, { stateFile });
    await first.s.upload(p, async () => { throw new UploadOutcomeUnknown('Receipt unavailable'); });
    const result = { id: 'abc', url: 'https://youtu.be/abc', privacy: 'private', publishAt: null, lockedPrivate: false, warnings: [] };
    const recover = vi.fn(async () => ({ ok: true as const, url: result.url, result, account: 'main' }));
    const publish = vi.fn();
    const restarted = mk([p], clock, { stateFile, api: { wants: () => false, publish, recover } });
    await restarted.s.tick();
    expect(restarted.s.apiState(p.id)).toMatchObject({ status: 'done', calendarSynced: true, result, resolvedAccount: 'main' });
    expect(restarted.posted).toEqual(['recover']);
    expect(recover).toHaveBeenCalledWith(p, false);
    await restarted.s.tick();
    expect(recover).toHaveBeenCalledTimes(1);
    expect(publish).not.toHaveBeenCalled();
  });

  it('shows interrupted uploads as unverified when recovery cannot confirm completion', async () => {
    const clock = { t: new Date(2026, 9, 7, 20, 1) };
    const p = post('interrupted', '2026-10-07T20:00', { platform: 'youtube' });
    const stateFile = path.join(tmp(), 'state.json');
    fs.writeFileSync(stateFile, JSON.stringify({ notified: {}, api: { interrupted: {
      at: p.at, status: 'uploading', tries: 1, lastTry: clock.t.getTime() - 60000,
    } } }));
    const recover = vi.fn(async () => null);
    const m = mk([p], clock, { stateFile, api: { wants: () => true, publish: vi.fn(), recover } });
    expect((await m.s.tick()).due.map(p => p.id)).toEqual(['interrupted']);
    expect(m.s.apiState(p.id)?.status).toBe('unverified');
    expect(recover).toHaveBeenCalledWith(p, true);
    await m.s.tick();
    expect(recover).toHaveBeenCalledTimes(1);
  });

  it('does not query a live manual upload during scheduler ticks', async () => {
    const clock = { t: new Date(2026, 9, 7, 20, 1) };
    const p = post('active', '2026-10-07T20:00', { platform: 'youtube' });
    const recover = vi.fn(async () => null);
    const m = mk([p], clock, { api: { wants: () => false, publish: vi.fn(), recover } });
    let finish!: () => void;
    const upload = m.s.upload(p, async () => {
      await new Promise<void>(resolve => { finish = resolve; });
      return { ok: true, url: 'https://youtu.be/abc' };
    });
    await m.s.tick();
    expect(recover).not.toHaveBeenCalled();
    finish();
    await upload;
  });

  it('recovers a durable upload after calendar failure and restart without uploading again', async () => {
    const clock = { t: new Date(2026, 9, 7, 19, 30) };
    const p = post('y1', '2026-10-07T20:00', { platform: 'youtube' });
    const file = path.join(tmp(), 's.json');
    const publish = vi.fn(async () => ({ ok: true as const, url: 'https://youtu.be/receipt', account: 'brand' }));
    const failedCalendar = vi.fn(async () => { throw new Error('engine unavailable'); });
    const first = mk([p], clock, { stateFile: file, api: { wants: () => true, publish }, markPosted: failedCalendar });
    await first.s.tick();
    expect(JSON.parse(fs.readFileSync(file, 'utf8')).api.y1).toMatchObject({ status: 'done', calendarSynced: false, url: 'https://youtu.be/receipt' });
    // Recover beyond the upload grace window, even after auto-upload is switched off.
    clock.t = new Date(2026, 9, 9, 12);
    const markPosted = vi.fn(async () => undefined);
    const restarted = mk([p], clock, { stateFile: file, api: { wants: () => false, publish }, markPosted });
    await restarted.s.tick();
    await restarted.s.tick();
    expect(publish).toHaveBeenCalledTimes(1);
    expect(markPosted).toHaveBeenCalledExactlyOnceWith({ ...p, account: 'brand' }, 'https://youtu.be/receipt', 'api', undefined);
    expect(restarted.s.apiState('y1')).toMatchObject({ status: 'done', calendarSynced: true });
  });

  it('does not upload when its attempt cannot be saved', async () => {
    const file = path.join(tmp(), 's.json');
    const publish = vi.fn();
    const { s } = mk([post('y1', '2026-10-07T20:00', { platform: 'youtube' })], { t: new Date(2026, 9, 7, 19, 30) }, { stateFile: file, api: { wants: () => true, publish } });
    // The journal's directory was replaced after startup.
    fs.writeFileSync(file, 'keep');
    fs.mkdirSync(file + '.tmp');
    await s.tick();
    expect(publish).not.toHaveBeenCalled();
    expect(s.apiState('y1')).toBeUndefined();
    expect(fs.readFileSync(file, 'utf8')).toBe('keep');
  });

  it.each(['{incomplete receipt', '[]', '{"api":{"y1":null}}', '{"notified":7}'])('preserves corrupt receipts and stops automatic uploads: %s', async (contents) => {
    const file = path.join(tmp(), 's.json');
    fs.writeFileSync(file, contents);
    const publish = vi.fn();
    const { s } = mk([post('y1', '2026-10-07T20:00', { platform: 'youtube' })], { t: new Date(2026, 9, 7, 20, 30) }, { stateFile: file, api: { wants: () => true, publish } });
    await s.tick();
    expect(publish).not.toHaveBeenCalled();
    expect(fs.readFileSync(file, 'utf8')).toBe(contents);
  });

  it('keeps remote success when saving its receipt fails and retries only persistence', async () => {
    const file = path.join(tmp(), 's.json');
    const rename = fs.renameSync;
    let fail = false;
    const save = vi.spyOn(fs, 'renameSync').mockImplementation((from, to) => {
      if (fail && to === file) throw new Error('disk full');
      rename(from, to);
    });
    try {
      const publish = vi.fn(async () => { fail = true; return { ok: true as const, url: 'https://youtu.be/receipt' }; });
      const markPosted = vi.fn(async () => undefined);
      const p = post('y1', '2026-10-07T20:00', { platform: 'youtube' });
      const { s } = mk([p], { t: new Date(2026, 9, 7, 19, 30) }, { stateFile: file, api: { wants: () => true, publish }, markPosted });
      await s.tick();
      expect(s.apiState('y1')?.status).toBe('done');
      expect(JSON.parse(fs.readFileSync(file, 'utf8')).api.y1.status).toBe('uploading');
      expect(markPosted).not.toHaveBeenCalled();
      fail = false;
      await s.tick();
      expect(publish).toHaveBeenCalledTimes(1);
      expect(markPosted).toHaveBeenCalledTimes(1);
      expect(JSON.parse(fs.readFileSync(file, 'utf8')).api.y1.calendarSynced).toBe(true);
    } finally { save.mockRestore(); }
  });

  it('does not repeat an interrupted upload with an unknown remote outcome', async () => {
    const file = path.join(tmp(), 's.json');
    fs.writeFileSync(file, JSON.stringify({ api: { y1: { at: '2026-10-07T20:00', status: 'uploading', tries: 1, lastTry: 0 } } }));
    const publish = vi.fn();
    const { s } = mk([post('y1', '2026-10-07T20:00', { platform: 'youtube' })], { t: new Date(2026, 9, 7, 20, 30) }, { stateFile: file, api: { wants: () => true, publish } });
    await s.tick();
    expect(publish).not.toHaveBeenCalled();
    expect(s.apiState('y1')?.status).toBe('uploading');
  });

  it('manual upload owns the same post while the scheduler and another manual request run', async () => {
    const p = post('y1', '2026-10-07T20:00', { platform: 'youtube' });
    const automatic = vi.fn();
    const { s } = mk([p], { t: new Date(2026, 9, 7, 19, 30) }, { api: { wants: () => true, publish: automatic } });
    let finish!: () => void;
    const waiting = new Promise<void>((resolve) => { finish = resolve; });
    const manual = vi.fn(async () => { await waiting; return { ok: true as const, url: 'https://youtu.be/one' }; });
    const first = s.upload(p, manual);
    await s.tick();
    const second = await s.upload(p, manual);
    expect(second.ok).toBe(false);
    expect(automatic).not.toHaveBeenCalled();
    expect(manual).toHaveBeenCalledTimes(1);
    finish();
    expect((await first).ok).toBe(true);
    await s.tick();
    expect(automatic).not.toHaveBeenCalled();
  });

  it('scheduled upload owns the post before a manual upload can start', async () => {
    const p = post('y1', '2026-10-07T20:00', { platform: 'youtube' });
    let finish!: () => void;
    const waiting = new Promise<void>((resolve) => { finish = resolve; });
    const automatic = vi.fn(async () => { await waiting; return { ok: true as const, url: 'https://youtu.be/one' }; });
    const { s } = mk([p], { t: new Date(2026, 9, 7, 19, 30) }, { api: { wants: () => true, publish: automatic } });
    const ticking = s.tick();
    await vi.waitFor(() => expect(automatic).toHaveBeenCalledTimes(1));
    const manual = vi.fn();
    expect((await s.upload(p, manual)).ok).toBe(false);
    expect(manual).not.toHaveBeenCalled();
    finish();
    await ticking;
  });

  it('manual retry after restart returns the saved provider result, including local sync failures', async () => {
    const p = post('y1', '2026-10-07T20:00', { platform: 'youtube' });
    const stateFile = path.join(tmp(), 's.json');
    const clock = { t: new Date(2026, 9, 7, 19, 30) };
    const result = { url: 'https://youtu.be/one', privacy: 'private', publishAt: '2026-10-08T03:00:00Z', lockedPrivate: false, warnings: ['cover unavailable'] };
    const first = mk([p], clock, { stateFile, markPosted: async () => { throw new Error('calendar offline'); } });
    await first.s.upload(p, async () => ({ ok: true, url: result.url, account: 'main', result }));
    const restarted = mk([p], clock, { stateFile });
    const publish = vi.fn();
    expect(await restarted.s.upload(p, publish)).toMatchObject({ ok: true, result });
    expect(publish).not.toHaveBeenCalled();
    expect(restarted.posted).toEqual(['y1']);
    // Changing an existing remote post does not mean inserting a second video.
    expect((await restarted.s.upload({ ...p, at: '2026-10-08T20:00' }, publish)).ok).toBe(false);
    expect((await restarted.s.upload({ ...p, account: 'brand' }, publish)).ok).toBe(false);
    expect(publish).not.toHaveBeenCalled();
  });

  it('does not retry a failed manual form with automatic visibility defaults', async () => {
    const clock = { t: new Date(2026, 9, 7, 19, 30) };
    const p = post('y1', '2026-10-07T20:00', { platform: 'youtube' });
    const publish = vi.fn();
    const { s, notified } = mk([p], clock, { api: { wants: () => true, publish } });
    await s.upload(p, async () => ({ ok: false, error: 'quota exceeded' }));
    clock.t = new Date(2026, 9, 7, 20, 30);
    await s.tick();
    expect(publish).not.toHaveBeenCalled();
    expect(notified).toEqual([['y1']]);
  });

  it('repairs an older posted row from its private scheduled receipt without another upload', async () => {
    const stateFile = path.join(tmp(), 's.json');
    const p = post('y1', '2026-10-07T20:00', { platform: 'youtube', account: 'main', state: 'posted' });
    const result = { url: 'https://youtu.be/one', privacy: 'private', publishAt: '2026-10-08T03:00:00Z', lockedPrivate: false, warnings: [] };
    fs.writeFileSync(stateFile, JSON.stringify({ api: { y1: { at: p.at, account: 'main', status: 'done', tries: 1, lastTry: 0, calendarSynced: true, result } } }));
    const publish = vi.fn();
    const markPosted = vi.fn(async () => { p.state = 'scheduled'; p.api_result = result; });
    const { s } = mk([p], { t: new Date(2026, 9, 8, 12) }, { stateFile, api: { wants: () => false, publish }, markPosted });
    await s.tick();
    await s.tick();
    expect(markPosted).toHaveBeenCalledExactlyOnceWith(p, result.url, 'api', result);
    expect(publish).not.toHaveBeenCalled();
    expect(p.state).toBe('scheduled');
    p.state = 'posted'; p.via = 'manual'; delete p.api_result;
    await s.tick();
    expect(markPosted).toHaveBeenCalledTimes(1); // Explicit manual confirmation wins over the old upload snapshot.
  });

  it('more than apiGraceMs late: no automatic upload, she decides', async () => {
    const clock = { t: new Date(2026, 9, 8, 18, 0) };
    const publish = vi.fn();
    const { s, notified } = mk([post('y3', '2026-10-08T09:00', { platform: 'youtube' })], clock, { api: { wants: () => true, publish } });
    await s.tick();
    expect(publish).not.toHaveBeenCalled();
    expect(notified).toEqual([['y3']]);
  });
});

describe('confirmed API delivery states', () => {
  const r = { url: 'https://youtu.be/one', privacy: 'private', publishAt: '2026-10-07T20:00:00Z', lockedPrivate: false, warnings: [] };
  it('persists a fresh read before calendar writes and recovers it after a restart without uploading', async () => {
    const file = path.join(tmp(), 'scheduler.json');
    const p = post('r1', '2026-10-07T20:00', { platform: 'youtube', account: 'main', state: 'scheduled', via: 'api', api_result: r });
    const now = new Date(2026, 9, 8);
    const fresh = { ...r, privacy: 'public', publishAt: null, uploadStatus: 'processed' as const, checkedAt: now.toISOString() };
    const mark = vi.fn(async () => {
      expect(JSON.parse(fs.readFileSync(file, 'utf8')).api.r1.result).toEqual(fresh);
      throw new Error('calendar temporarily unavailable');
    });
    const deps = { load: async () => [p], now: () => now, notify: () => undefined, stateFile: file,
      markPosted: mark, api: { wants: () => false, publish: vi.fn() } };
    const s = new PublishScheduler(deps);
    let finish!: (v: typeof fresh) => void;
    const read = vi.fn(() => new Promise<typeof fresh>(resolve => { finish = resolve; }));
    const first = s.refresh(p, read);
    const second = s.refresh(p, read);
    expect(read).toHaveBeenCalledTimes(1);
    finish(fresh);
    expect(await first).toEqual(fresh);
    expect(await second).toEqual(fresh);
    expect(mark).toHaveBeenCalledTimes(1);
    const restored = vi.fn(async () => undefined);
    await new PublishScheduler({ ...deps, markPosted: restored }).tick();
    expect(restored).toHaveBeenCalledWith(p, fresh.url, 'api', fresh);
    expect(deps.api.publish).not.toHaveBeenCalled();
  });

  it('bounds automatic status reads even when automatic uploading is off', async () => {
    const ps = Array.from({ length: 6 }, (_, i) => post(`r${i}`, '2026-10-07T20:00', { platform: 'youtube', via: 'api', api_result: r }));
    let now = new Date(2026, 9, 8);
    const read = vi.fn(async (_p: CalendarPost, previous: typeof r) => ({ ...previous, checkedAt: now.toISOString() }));
    const s = new PublishScheduler({ load: async () => ps, now: () => now, notify: () => undefined,
      markPosted: async () => undefined, stateFile: path.join(tmp(), 'scheduler.json'),
      api: { wants: () => false, publish: vi.fn(), canRefresh: () => true, refresh: read } });
    await s.tick();
    expect(read.mock.calls.map(([p]) => p.id)).toEqual(['r0', 'r1', 'r2']);
    await s.tick();
    expect(read).toHaveBeenCalledTimes(3);
    now = new Date(now.getTime() + 5 * 60_000);
    await s.tick();
    expect(read.mock.calls.slice(3).map(([p]) => p.id)).toEqual(['r3', 'r4', 'r5']);
  });

  it('does not overwrite a manual confirmation or resurrect a removed post during a pending read', async () => {
    for (const removed of [false, true]) {
      const p = post('r1', '2026-10-07T20:00', { platform: 'youtube', via: 'api', api_result: r });
      let ps = [p];
      const mark = vi.fn(async () => undefined);
      const s = new PublishScheduler({ load: async () => ps, now: () => new Date(), notify: () => undefined,
        markPosted: mark, stateFile: path.join(tmp(), 'scheduler.json') });
      let finish!: (value: typeof r) => void;
      const pending = s.refresh(p, () => new Promise<typeof r>(resolve => { finish = resolve; }));
      ps = removed ? [] : [{ ...p, state: 'posted', via: 'manual', api_result: undefined }];
      finish(r);
      await expect(pending).rejects.toThrow(/Post changed/);
      expect(mark).not.toHaveBeenCalled();
    }
  });

  it('refuses status reads for another account or an ambiguous upload attempt', async () => {
    const file = path.join(tmp(), 'scheduler.json');
    const p = post('r1', '2026-10-07T20:00', { platform: 'youtube', account: 'main', via: 'api', api_result: r });
    for (const rec of [{ account: 'brand', status: 'done' }, { account: 'main', status: 'uploading' }]) {
      fs.writeFileSync(file, JSON.stringify({ api: { r1: { ...rec, at: p.at, tries: 1, lastTry: 0, result: r } } }));
      const read = vi.fn();
      const s = new PublishScheduler({ load: async () => [p], now: () => new Date(), notify: () => undefined,
        markPosted: async () => undefined, stateFile: file });
      await expect(s.refresh(p, read)).rejects.toThrow(/account does not match/);
      expect(read).not.toHaveBeenCalled();
    }
  });
  it('does not infer public visibility from an upload or the passage of its schedule time', () => {
    expect(apiDeliveryState(r)).toBe('scheduled');
    expect(apiDeliveryState({ ...r, privacy: 'public' })).toBe('posted');
    expect(apiDeliveryState({ ...r, privacy: 'unlisted' })).toBe('uploaded');
    expect(apiDeliveryState({ ...r, privacy: 'unknown' })).toBe('uploaded');
    expect(apiDeliveryState({ ...r, lockedPrivate: true })).toBe('uploaded');
    expect(apiDeliveryState({ ...r, publishAt: null })).toBe('uploaded');
    const posts = ['uploaded', 'scheduled', 'posted'].map((state) => post(state, '2026-10-07T20:00', { state: state as CalendarPost['state'] }));
    expect(duePosts(posts, new Date(2026, 9, 8))).toEqual([]);
    expect(upcomingPosts(posts, new Date(2026, 9, 7, 19, 30), 3600_000)).toEqual([]);
  });
});

describe('what a scheduled post sends', () => {
  const files = [
    { path: '/o/A_9x16.mp4', aspect: '9:16' },
    { path: '/o/A_3x4.mp4', aspect: '3:4' },
    { path: '/o/A_16x9.mp4', aspect: '16:9' },
  ];
  it('the file made for the platform, else the aspect it posts', () => {
    expect(pickFile(files, 'xiaohongshu')?.path).toBe('/o/A_3x4.mp4');
    expect(pickFile(files, 'xiaohongshu:full')?.path).toBe('/o/A_9x16.mp4');
    expect(pickFile(files, 'douyin')?.path).toBe('/o/A_9x16.mp4');
    expect(pickFile(files, 'youtube')?.path).toBe('/o/A_16x9.mp4');
    expect(pickFile([...files, { path: '/o/A_dy.mp4', aspect: '9:16', platform: 'douyin' }], 'douyin')?.path).toBe('/o/A_dy.mp4');
    expect(pickFile([], 'x')).toBeNull();
  });
  it('title from the post; the caption without the repeated title; the tag line becomes tags', () => {
    const p = { title: '再小的博主，也是博主', caption: '再小的博主，也是博主\n\n正文第一行\n第二行\n\n#副业 #口播' };
    expect(copyForPost(p, true)).toEqual({ title: '再小的博主，也是博主', description: '正文第一行\n第二行', tags: ['副业', '口播'] });
    expect(copyForPost({ ...p, title: '新标题' }, true, ['再小的博主，也是博主'])).toEqual({ title: '新标题', description: '正文第一行\n第二行', tags: ['副业', '口播'] });
    expect(copyForPost(p, false)).toEqual({ title: '', description: '再小的博主，也是博主\n\n正文第一行\n第二行', tags: ['副业', '口播'] });
  });
  it('小红书 counts latin letters as half', () => {
    expect(titleLength('xiaohongshu', '再小的博主')).toBe(5);
    expect(titleLength('xiaohongshu:full', 'ab 再')).toBe(2.5);
    expect(titleLength('douyin', 'ab 再')).toBe(4);
  });
});

describe('success after her click', () => {
  it('a success URL or text; the post link when the page shows one', () => {
    const s = by.xiaohongshu.success!;
    expect(postedSignal('https://creator.xiaohongshu.com/publish/publish', '上传视频', [], s)).toEqual({ posted: false, url: null });
    expect(postedSignal('https://creator.xiaohongshu.com/publish/success?x=1', '', ['https://www.xiaohongshu.com/explore/66f0a1b2c3d4e5f60718293a?xsec=1'], s)).toEqual({ posted: true, url: 'https://www.xiaohongshu.com/explore/66f0a1b2c3d4e5f60718293a' });
    expect(postedSignal('https://creator.xiaohongshu.com/publish/publish', '发布成功 去看看', [], s)).toEqual({ posted: true, url: null });
    expect(postedSignal('https://x', '发布成功', [], null)).toEqual({ posted: false, url: null });
    expect(postedSignal('https://creator.douyin.com/creator-micro/content/manage', '', ['https://www.douyin.com/video/7412345678901234567'], by.douyin.success!).url).toBe('https://www.douyin.com/video/7412345678901234567');
  });
});

describe('login from session cookies', () => {
  const xhs = by.xiaohongshu;
  it('signed in on any page once the session cookie is set (the creator home too); none = signed out', () => {
    expect(sessionLoginState([{ name: 'galaxy_creator_session_id', value: 'x', domain: '.xiaohongshu.com' }], xhs)).toBe('in');
    expect(sessionLoginState([{ name: 'web_session', value: 'x', domain: '.xiaohongshu.com' }], xhs)).toBe('out'); // a guest cookie
    expect(sessionLoginState([{ name: 'galaxy_creator_session_id', value: '', domain: '.xiaohongshu.com' }], xhs)).toBe('out');
    expect(sessionLoginState([{ name: 'galaxy_creator_session_id', value: 'x', domain: '.xiaohongshu.com', expirationDate: 1000 }], xhs, 2000)).toBe('out');
    expect(sessionLoginState([{ name: 'galaxy_creator_session_id', value: 'x', domain: '.evil.com' }], xhs)).toBe('out');
    expect(sessionLoginState([], { session: null })).toBeNull();
  });
  it('the probe reads only the named cookies of the partition the panel uses', async () => {
    const asked: unknown[] = [];
    const jar = { cookies: { get: async (f: Record<string, unknown>) => (asked.push(f), f.name === 'access-token-creator.xiaohongshu.com' ? [{ name: f.name as string, value: 'secret-value', domain: 'creator.xiaohongshu.com' }] : []) } };
    expect(await probeLogin(jar, xhs)).toBe('in');
    expect(asked.every((f) => typeof (f as { name?: string }).name === 'string')).toBe(true);
    expect(partitionFor('xiaohongshu', 'main')).toBe('persist:xiaohongshu-main');
  });
});

describe('text selectors', () => {
  it('parse and validate', () => {
    expect(parseSelector('button:has-text(/^\\s*发布\\s*$/)')).toEqual({ css: 'button', kind: 'has-text', regex: { source: '^\\s*发布\\s*$', flags: '' } });
    expect(parseSelector('input:near-text(标题)')).toEqual({ css: 'input', kind: 'near-text', text: '标题' });
    expect(parseSelector('input[type="file"]')).toEqual({ css: 'input[type="file"]', kind: 'css' });
    expect(selectorError('button:has-text(/[/)')).toMatch(/bad regular expression/);
    expect(findJs(['a'], true)).toContain('getClientRects');
    const bad = { ...JSON.parse(fs.readFileSync(path.resolve(__dirname, '../../adapters/douyin.json'), 'utf8')) };
    bad.publishButton = { selectors: ['button:has-text(/(/)'] };
    expect(parseAdapter(bad).ok).toBe(false);
  });
  it('小红书 and 抖音: never a click, title limits, publish button only outlined', () => {
    for (const a of [by.xiaohongshu, by.douyin]) {
      expect(a.status).toBe('unverified');
      expect(a.publishButton?.selectors.some((s) => s.includes('发布'))).toBe(true);
      if (a.id === 'xiaohongshu') expect(a.fields.cover?.selectors.length).toBeGreaterThan(0);
      else expect(a.fields.cover).toBeNull();
    }
    expect(by.xiaohongshu.fields.title?.maxLength).toBe(20);
    expect(by.douyin.fields.title?.maxLength).toBe(30);
  });
});

describe('page capture file', () => {
  it('writes a local html file with a header saying what was removed', () => {
    const dir = tmp();
    const f = saveCapture(dir, 'xiaohongshu', { url: 'https://creator.xiaohongshu.com/publish/publish', title: 't', html: '<html></html>', nodes: 3 }, new Date('2026-10-07T12:00:00Z'));
    expect(path.basename(f)).toBe('xiaohongshu-2026-10-07T12-00-00.html');
    expect(fs.readFileSync(f, 'utf8')).toMatch(/No cookies/);
  });
});

describe('YouTube Data API metadata', () => {
  it('metadata: private + publishAt ahead, public when late; YouTube’s limits', () => {
    const at = new Date('2026-10-07T12:00:00Z');
    expect(ytMeta({ title: 'a<b>', description: 'd', tags: ['#x', 'y'], publishAt: at })).toEqual({
      snippet: { title: 'ab', description: 'd', tags: ['x', 'y'], categoryId: '22' },
      status: { privacyStatus: 'private', publishAt: '2026-10-07T12:00:00.000Z', selfDeclaredMadeForKids: false },
    });
    expect(ytMeta({ title: 't'.repeat(150), description: '', tags: [], publishAt: null }).snippet.title.length).toBe(100);
    expect(ytMeta({ title: 't', description: '', tags: [], publishAt: null }).status.privacyStatus).toBe('public');
  });

  // OAuth, the upload, the keychain: tests/unit/youtubeApi.test.ts (a fake Google over real HTTP)
});

describe('IPC for the loop', () => {
  it('validates post ids, client ids and the open-at-login switch', () => {
    expect(() => validateIpc('publish:fillPost', { postId: 'abc' })).toThrow();
    expect(validateIpc('publish:fillPost', { postId: '0123456789ab', account: 'main' })).toEqual({ postId: '0123456789ab', account: 'main' });
    expect(() => validateIpc('publish:apiConnect', { id: 'tiktok' })).toThrow();
    expect(validateIpc('settings:set', { openAtLogin: true })).toEqual({ openAtLogin: true });
  });
});

it('an explicit horizontal video wins for Xiaohongshu; a missing choice never falls back', () => {
 const files = [{path: '/vertical.mp4', aspect: '3:4', platform: 'xiaohongshu'}, {path: '/wide.mp4', aspect: '16:9', platform: 'youtube'}];
 expect(pickFile(files, 'xiaohongshu', '/wide.mp4')?.path).toBe('/wide.mp4');
 expect(pickFile(files, 'xiaohongshu', '/removed.mp4')).toBeNull();
 expect(pickFile(files, 'xiaohongshu', null)?.path).toBe('/vertical.mp4');
});
