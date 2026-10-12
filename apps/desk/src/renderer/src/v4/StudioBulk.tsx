// All projects for hundreds of videos: the search + filters above the list, and what the bulk bar does beyond
// Archive / Restore / Delete - Approve (the picked videos' questions, the recommended way), Schedule (made ones, the
// next free slots on her platforms, one Undo), Try again (failed / stopped runs) and Change with AI… (one request
// per project for exactly the picked videos; each project's chat shows the changes to apply).
import { useEffect, useRef, useState } from 'react';
import { CalendarPlus, Check, RotateCcw, SlidersHorizontal, Wand2, X } from 'lucide-react';
import type { CalendarPost } from '../../../shared/v04';
import { Modal } from '../components/ui';
import { fmtDate, t, tk } from '../i18n';
import { approveAnswer, bulkWork, chunks, count, localDay, schedulePlan } from '../lib/bulk';
import { useEngine } from '../lib/engine';
import { useHistory } from '../lib/history';
import { useInbox } from '../lib/inbox';
import { useStudioData } from '../lib/studioData';
import { go } from '../lib/router';
import type { StudioRow } from '../lib/studio';
import { findOptions, finding, NO_FIND, type Find, type FindDate } from '../lib/studioFind';
import type { ActionTarget } from '../lib/rowActions';
import { keyHint } from '../lib/keys';
import { errText } from './msg';
import { postPlatforms } from './Project';
import { askProjectInBackground } from './ProjectAIPanel';
import type { RowActionsApi } from './RowActions';
import { useUi } from './ui';

export const FINDKEY = 'studio.find';

export function loadFind(): Find {
  try {
    const v = JSON.parse(sessionStorage.getItem(FINDKEY) ?? 'null') as Partial<Find> | null;
    return v ? { ...NO_FIND, ...v, date: (['any', 'today', 'week'] as FindDate[]).includes(v.date as FindDate) ? (v.date as FindDate) : 'any' } : NO_FIND;
  } catch {
    return NO_FIND;
  }
}

const pf = (id: string) => tk(`pf.${id}`);

// ---------------------------------------------------------------- search + filters
export function FindBar({ find, onChange, rows, posts }: { find: Find; onChange: (f: Find) => void; rows: StudioRow[]; posts: CalendarPost[] }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    window.addEventListener('mousedown', close);
    return () => window.removeEventListener('mousedown', close);
  }, [open]);
  const opts = open ? findOptions(rows, posts) : null;
  const set = (p: Partial<Find>) => onChange({ ...find, ...p });
  const projectName = find.project ? (rows.find((r) => r.item === find.project)?.i?.name ?? '') : '';
  const active = !!(find.platform || find.project || find.date !== 'any');
  return (
    <>
      <div className="st-find" ref={box}>
        <input
          className="inp"
          type="search"
          value={find.q}
          onChange={(e) => set({ q: e.target.value })}
          onKeyDown={(e) => {
            if (e.key === 'Escape' && find.q) {
              e.stopPropagation();
              set({ q: '' });
            }
          }}
          placeholder={t('hd.search')}
          aria-label={t('hd.search')}
          data-search
          data-testid="studio-search"
        />
        <button className={`btn ghost icon ${active ? 'on' : ''}`} onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-label={t('hd.filters')} data-tip={t('hd.filters')} data-testid="studio-filters">
          <SlidersHorizontal className="ico" />
        </button>
        {open && opts && (
          <div className="ux-pop st-fpop" role="dialog" aria-label={t('hd.filters')} data-testid="studio-filter-pop">
            <label htmlFor="st-f-platform">{t('hd.f.platform')}</label>
            <select id="st-f-platform" className="inp" value={find.platform ?? ''} onChange={(e) => set({ platform: e.target.value || null })} data-testid="studio-f-platform">
              <option value="">{t('hd.f.any')}</option>
              {opts.platforms.map((p) => (
                <option key={p} value={p}>
                  {pf(p)}
                </option>
              ))}
            </select>
            <label htmlFor="st-f-project">{t('hd.f.project')}</label>
            <select id="st-f-project" className="inp" value={find.project ?? ''} onChange={(e) => set({ project: e.target.value || null })} data-testid="studio-f-project">
              <option value="">{t('hd.f.any')}</option>
              {opts.projects.map(([id, name]) => (
                <option key={id} value={id}>
                  {name}
                </option>
              ))}
            </select>
            <label htmlFor="st-f-date">{t('hd.f.date')}</label>
            <select id="st-f-date" className="inp" value={find.date} onChange={(e) => set({ date: e.target.value as FindDate })} data-testid="studio-f-date">
              <option value="any">{t('hd.f.any')}</option>
              <option value="today">{t('hd.date.today')}</option>
              <option value="week">{t('hd.date.week')}</option>
            </select>
          </div>
        )}
      </div>
      {finding(find) && (find.platform || find.project || find.date !== 'any') && (
        <div className="st-fchips" data-testid="studio-find-chips">
          {find.platform && <Chip label={pf(find.platform)} onClear={() => set({ platform: null })} />}
          {find.project && <Chip label={projectName || t('hd.f.project')} onClear={() => set({ project: null })} />}
          {find.date !== 'any' && <Chip label={t(find.date === 'today' ? 'hd.date.today' : 'hd.date.week')} onClear={() => set({ date: 'any' })} />}
          <button className="btn ghost sm" onClick={() => onChange(NO_FIND)} data-testid="studio-find-clear">
            {t('hd.f.clear')}
          </button>
        </div>
      )}
    </>
  );
}

function Chip({ label, onClear }: { label: string; onClear: () => void }) {
  return (
    <span className="st-fchip" data-testid="studio-find-chip">
      {label}
      <button className="btn ghost icon sm" onClick={onClear} aria-label={`${t('c.remove')} ${label}`}>
        <X className="ico" />
      </button>
    </span>
  );
}

// ---------------------------------------------------------------- bulk work
export interface BulkApi {
  approve(rows: StudioRow[]): Promise<void>;
  /** ``onProgress(done, n)`` as the requests come back, ``(null, n)`` when it is over */
  schedule(rows: StudioRow[], onProgress?: (done: number | null, n: number) => void): Promise<void>;
  change(rows: StudioRow[], prompt: string): Promise<void>;
}

export function useBulk(): BulkApi {
  const { client } = useEngine();
  const inbox = useInbox();
  const studio = useStudioData();
  const ui = useUi();
  const fail = (e: unknown) => ui.toast(errText(e), { error: true });
  return {
    async approve(rows) {
      if (!client) return;
      const xs = bulkWork(rows, []).approve;
      if (!xs.length) return void ui.toast(t('hd.bulk.nothing'));
      const done: string[] = [];
      try {
        for (const x of xs) {
          await client.answerInbox([x.key], approveAnswer(x));
          done.push(x.key);
        }
      } catch (e) {
        fail(e);
      }
      inbox.reload();
      if (done.length)
        ui.toast(t('hd.bulk.approved', { n: done.length }), {
          undo: async () => {
            await client.undoInbox(done);
            inbox.reload();
          },
        });
    },
    async schedule(rows, onProgress) {
      if (!client) return;
      const by = bulkWork(rows, []).schedule;
      const n = count(by);
      if (!n) return void ui.toast(t('hd.bulk.nothing'));
      const made: string[] = [];
      try {
        // the list has every project's clips and the posts already: one request per 100 videos, not one per project
        const defaults = (await window.desk.getSettings()).defaultPlatforms ?? [];
        const have = { ...studio.clips };
        const missing = [...by.keys()].filter((id) => !have[id]);
        for (const id of missing) have[id] = (await client.clips(id)).clips;
        const plan = schedulePlan(by, have, studio.posts, (c) => postPlatforms(c, defaults));
        if (!plan.todo.length) return void ui.toast(plan.noPlatform ? t('project.noPlatforms') : t('hd.bulk.nothing'), { error: plan.noPlatform > 0 });
        const parts = chunks(plan.todo);
        const today = localDay();
        let done = 0;
        let skipped = 0;
        let first: string | null = null;
        let last: string | null = null;
        onProgress?.(0, plan.todo.length);
        for (const [k, part] of parts.entries()) {
          // quiet until the last one: the list and the calendar reload once, not once per request
          const r = await client.scheduleClips({ clips: part, today, quiet: k < parts.length - 1 });
          made.push(...r.ids);
          done += part.length;
          skipped += r.skipped;
          first = first ?? r.first;
          last = r.last ?? last;
          onProgress?.(done, plan.todo.length);
        }
        const nMade = plan.todo.length - skipped;
        const when = first ? (first.slice(0, 10) === last?.slice(0, 10) ? fmtDate(first) : `${fmtDate(first)} – ${fmtDate(last!)}`) : '';
        const extra = [skipped ? t('hd.bulk.skipped', { n: skipped }) : '', plan.noPlatform ? t('project.noPlatforms') : ''].filter(Boolean);
        ui.toast([`${t('hd.bulk.scheduled', { n: nMade })}${when ? ` · ${when}` : ''}`, ...extra].join(' · '), {
          undo: made.length ? () => client.unscheduleMany(made).then(() => undefined) : undefined,
          ms: 10000,
        });
      } catch (e) {
        // all or none: what the earlier requests put on the calendar comes off again
        if (made.length) await client.unscheduleMany(made).catch(() => undefined);
        ui.toast(t('hd.bulk.scheduleFailed', { why: errText(e) }), { error: true, ms: 10000 });
      } finally {
        onProgress?.(null, n);
      }
    },
    async change(rows, prompt) {
      if (!client || !prompt.trim()) return;
      const by = bulkWork(rows, []).change;
      if (!by.size) return void ui.toast(t('hd.bulk.nothing'));
      const asked: string[] = [];
      try {
        for (const [item, clips] of by) {
          await askProjectInBackground(client, item, prompt.trim(), clips);
          asked.push(item);
        }
      } catch (e) {
        fail(e);
      }
      if (!asked.length) return;
      ui.toast(t('hd.bulk.asked', { n: asked.length }), { ms: 8000 });
      go({ name: 'project', id: asked[0], tab: 'clips' });
    },
  };
}

/** The bulk bar's own buttons (each only when it takes something, with how many). */
export function BulkMore({ rows, xs, ra }: { rows: StudioRow[]; xs: ActionTarget[]; ra: RowActionsApi }) {
  const bulk = useBulk();
  const { reload } = useHistory();
  const [asking, setAsking] = useState(false);
  const [text, setText] = useState('');
  const [sched, setSched] = useState<{ done: number; n: number } | null>(null);
  const w = bulkWork(rows, xs);
  const nSched = count(w.schedule);
  const nChange = count(w.change);
  return (
    <>
      {w.approve.length > 0 && (
        <button className="btn sm primary" onClick={() => void bulk.approve(rows)} data-testid="studio-bulk-approve">
          <Check className="ico" />
          {t('hd.bulk.approve')} · {w.approve.length}
        </button>
      )}
      {(nSched > 0 || sched) && (
        <button
          className={`btn sm ${sched ? 'busy' : ''}`}
          disabled={!!sched}
          aria-busy={!!sched}
          onClick={() => void bulk.schedule(rows, (done, n) => setSched(done == null ? null : { done, n }))}
          data-testid="studio-bulk-schedule"
          data-tip={keyHint('S')}
          style={sched ? { ['--p' as string]: `${Math.round((100 * sched.done) / Math.max(1, sched.n))}%` } : undefined}
        >
          <CalendarPlus className="ico" />
          {sched ? <span data-testid="studio-bulk-scheduling">{t('hd.bulk.scheduling', { done: sched.done, n: sched.n })}</span> : `${t('hd.bulk.schedule')} · ${nSched}`}
        </button>
      )}
      {w.retry.length > 0 && (
        <button className="btn sm" onClick={() => void ra.run('retry', w.retry).then(reload)} data-testid="studio-bulk-retry">
          <RotateCcw className="ico" />
          {t('hd.bulk.retry')} · {w.retry.length}
        </button>
      )}
      {nChange > 0 && (
        <button className="btn sm" onClick={() => setAsking(true)} data-testid="studio-bulk-change">
          <Wand2 className="ico" />
          {t('hd.bulk.change')}
        </button>
      )}
      {asking && (
        <Modal title={t('hd.bulk.changeTitle', { n: nChange })} onClose={() => setAsking(false)}>
          <textarea
            className="input"
            rows={3}
            autoFocus
            value={text}
            maxLength={500}
            placeholder={t('hd.bulk.changePh')}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && text.trim()) {
                e.preventDefault();
                setAsking(false);
                void bulk.change(rows, text);
              }
            }}
            data-testid="studio-bulk-change-input"
          />
          <div className="row" style={{ justifyContent: 'flex-end', gap: 8 }}>
            <button className="btn ghost" onClick={() => setAsking(false)}>
              {t('common.cancel')}
            </button>
            <button
              className="btn primary"
              disabled={!text.trim()}
              onClick={() => {
                setAsking(false);
                void bulk.change(rows, text);
              }}
              data-testid="studio-bulk-change-ok"
            >
              {t('hd.bulk.changeOk')}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
