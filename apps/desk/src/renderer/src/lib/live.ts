// The live pane's model (ux/run-view A): a job's transcript - the model CLIs' turns as they streamed and the engine's
// own stages / log (desk_engine.live) - fetched from a cursor whenever the engine says it grew (the `live` stream
// event), plus the pure pieces the pane and the run page share: ANSI-safe spans, the line's tag, search, the text
// that Copy puts on the clipboard, and "what happened" per stage (runStory) built from the same lines.
import { useCallback, useEffect, useRef, useState } from 'react';
import type { LiveDoc, LiveLine } from '../../../shared/v04';
import { useEngine } from './engine';
import { stepOfStage, type StepId } from './pipeline';
import { stepOf, PLAN_STEPS, type PlanStep } from './planProgress';
import type { IntakeStage } from '../../../shared/v04';
import type { StudioRow } from './studio';
import { providerName } from '../../../shared/aiRoutes';

export const LIVE_CAP = 4000;

// ---------------------------------------------------------------- ANSI-safe text
export interface Span {
  text: string;
  cls?: string;
}

const SGR_COLOR: Record<number, string> = { 30: 'k', 31: 'r', 32: 'g', 33: 'y', 34: 'bl', 35: 'm', 36: 'c', 37: 'w', 90: 'k', 91: 'r', 92: 'g', 93: 'y', 94: 'bl', 95: 'm', 96: 'c', 97: 'w' };
// CSI ... final byte | OSC ... BEL / ST | other single ESC sequences
// eslint-disable-next-line no-control-regex
const ESC_RX = /\x1b\[([0-9;?]*)([@-~])|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?|\x1b[@-_]/g;
// eslint-disable-next-line no-control-regex
const CTRL_RX = /[\x00-\x08\x0b-\x1f\x7f]/g;

/** A log line with ANSI colour codes -> plain spans with a colour class (SGR colours, bold, dim); every other escape
 * sequence and control character is dropped. Never HTML: the pane renders each span as text. */
export function ansiSpans(raw: string): Span[] {
  const out: Span[] = [];
  let color: string | null = null;
  let bold = false;
  let dim = false;
  let last = 0;
  const push = (s: string) => {
    const text = s.replace(CTRL_RX, '');
    if (!text) return;
    const cls = [color ? `a-${color}` : '', bold ? 'a-bold' : '', dim ? 'a-dim' : ''].filter(Boolean).join(' ');
    out.push(cls ? { text, cls } : { text });
  };
  for (const m of raw.matchAll(ESC_RX)) {
    push(raw.slice(last, m.index));
    last = (m.index ?? 0) + m[0].length;
    if (m[2] !== 'm') continue;
    const codes = (m[1] || '0').split(';').map((x) => Number(x) || 0);
    for (const c of codes) {
      if (c === 0) {
        color = null;
        bold = false;
        dim = false;
      } else if (c === 1) bold = true;
      else if (c === 2) dim = true;
      else if (c === 22) {
        bold = false;
        dim = false;
      } else if (c === 39) color = null;
      else if (SGR_COLOR[c]) color = SGR_COLOR[c];
    }
  }
  push(raw.slice(last));
  return out;
}

export function plain(raw: string): string {
  return raw.replace(ESC_RX, '').replace(CTRL_RX, '');
}

// ---------------------------------------------------------------- tags, copy, search
const PROVIDER_TAG: Record<string, string> = { 'claude-code': 'claude', codex: 'codex', anthropic: 'claude api', openai: 'openai', gemini: 'gemini', ollama: 'ollama' };

/** The model the newest AI call ran on (its result, the CLI's session line, else what the call asked for), with its
 * provider - the pane's header says it, so a fallback or the CLI's own default is visible. null: no AI call yet. */
export function lastModel(lines: LiveLine[]): { provider: string; model: string } | null {
  for (let i = lines.length - 1; i >= 0; i--) {
    const l = lines[i];
    if (l.src === 'agent' && l.model && (l.kind === 'result' || l.kind === 'info' || l.kind === 'turn')) return { provider: l.provider ?? '', model: l.model };
  }
  return null;
}

/** The gutter word of a line: the CLI for an agent line's turn / reply, the kind for the rest, `engine` for the
 * engine's own. Untranslated on purpose: the pane is a log. */
export function lineTag(l: LiveLine): string {
  if (l.src === 'engine') return l.kind === 'error' ? 'error' : 'engine';
  if (l.kind === 'turn' || l.kind === 'say' || l.kind === 'info') return PROVIDER_TAG[l.provider ?? ''] ?? l.provider ?? 'model';
  return l.kind;
}

export function clockOf(at: number | null | undefined): string {
  if (!at) return '';
  const d = new Date(at * 1000);
  return [d.getHours(), d.getMinutes(), d.getSeconds()].map((n) => String(n).padStart(2, '0')).join(':');
}

/** What Copy puts on the clipboard: one line each, time, tag, text (no colour codes). */
export function transcriptText(lines: LiveLine[]): string {
  return lines.map((l) => `${clockOf(l.at).padEnd(8)}  ${lineTag(l).padEnd(11)}  ${plain(l.text)}`.trimEnd()).join('\n');
}

/** Indexes of the lines that hold ``q`` (case-insensitive, in the tag or the text). */
export function searchHits(lines: LiveLine[], q: string): number[] {
  const s = q.trim().toLowerCase();
  if (!s) return [];
  const out: number[] = [];
  lines.forEach((l, i) => {
    if (plain(l.text).toLowerCase().includes(s) || lineTag(l).toLowerCase().includes(s)) out.push(i);
  });
  return out;
}

export type LiveFilter = 'all' | 'agent' | 'engine';

export function filterLines(lines: LiveLine[], f: LiveFilter): LiveLine[] {
  // the engine's progress counters move the hero, not the log
  const l = lines.filter((x) => x.kind !== 'progress');
  return f === 'all' ? l : l.filter((x) => x.src === f);
}

export function appendLines(prev: LiveLine[], next: LiveLine[], cap = LIVE_CAP): LiveLine[] {
  if (!next.length) return prev;
  const all = prev.concat(next);
  return all.length > cap ? all.slice(all.length - cap) : all;
}

// ---------------------------------------------------------------- what happened, per stage
export interface StoryFile {
  name: string;
  state: 'done' | 'now' | 'todo';
}

export interface StoryEntry {
  /** a plan step (scan | media | transcribe | model | write) or a pipeline step (transcribe | cut | ...) */
  step: string;
  state: 'done' | 'now';
  start: number;
  end: number | null;
  /** facts as i18n key + params (the page words them) */
  facts: { key: string; params: Record<string, string | number> }[];
  files: StoryFile[];
  /** what the AI said / decided while this step ran (its replies, in its own words) */
  ai: { text: string; provider?: string; at: number }[];
  /** the engine's decisions (auto-answer events) during the step */
  decided: { kind: string; by: string; job?: string; at: number }[];
}

const isJsonish = (s: string) => /^\s*[[{]/.test(s);

function aiLine(l: LiveLine): { text: string; provider?: string; at: number } | null {
  if (l.src !== 'agent' || l.kind !== 'say' || !l.text.trim()) return null;
  const text = plain(l.text).trim();
  return { text: isJsonish(text) ? '' : text.length > 280 ? `${text.slice(0, 280)}…` : text, provider: l.provider, at: l.at ?? 0 };
}

/** A request being planned: one entry per plan step from the engine's stage lines; the files it read (per-file
 * progress), the minutes it transcribed, the model it asked and what that model answered. */
export function planStory(lines: LiveLine[], now = Date.now() / 1000): StoryEntry[] {
  const out: StoryEntry[] = [];
  let cur: StoryEntry | null = null;
  const files = new Map<string, StoryFile>();
  for (const l of lines) {
    const at: number = l.at ?? cur?.start ?? now;
    const d = (l.data ?? {}) as Record<string, unknown>;
    if (l.src === 'engine' && (l.kind === 'stage' || l.kind === 'progress') && typeof d.stage === 'string') {
      const step: PlanStep = stepOf(d.stage as IntakeStage);
      if (!PLAN_STEPS.includes(step)) continue;
      if (!cur || cur.step !== step) {
        if (cur) {
          cur.state = 'done';
          cur.end = at;
        }
        cur = { step, state: 'now', start: at, end: null, facts: [], files: [], ai: [], decided: [] };
        out.push(cur);
      }
      if (step === 'scan' && typeof d.files === 'number') cur.facts = [{ key: 'run.f.found', params: { n: d.files } }];
      if (step === 'media' && typeof d.file === 'string') {
        for (const f of files.values()) if (f.state === 'now') f.state = 'done';
        files.set(d.file, { name: d.file, state: 'now' });
        cur.files = [...files.values()];
        if (typeof d.i === 'number' && typeof d.n === 'number') cur.facts = [{ key: 'run.f.read', params: { i: d.i, n: d.n } }];
      }
      if (step === 'transcribe' && typeof d.total_s === 'number') {
        const mins = Math.max(1, Math.round(d.total_s / 60));
        cur.facts = [{ key: d.cached ? 'run.f.transcribedCached' : 'run.f.transcribe', params: { m: mins } }];
      }
      if (step === 'model' && typeof d.provider === 'string') cur.facts = [{ key: 'run.f.asked', params: { p: providerName(d.provider) || d.provider } }];
      continue;
    }
    if (!cur) continue;
    // stopped / failed while on a step: that step ends there (never left "now" under a stopped request)
    if (l.src === 'engine' && (l.kind === 'stop' || l.kind === 'error') && cur.state === 'now') {
      cur.state = 'done';
      cur.end = at;
      cur.facts = [...cur.facts, { key: l.kind === 'stop' ? 'run.f.stoppedHere' : 'run.f.failedHere', params: {} }];
      continue;
    }
    const ai = aiLine(l);
    if (ai?.text) cur.ai.push(ai);
    if (l.src === 'agent' && l.kind === 'result') cur.facts = [...cur.facts.filter((f) => f.key !== 'run.f.tokens'), { key: 'run.f.tokens', params: { t: plain(l.text) } }];
    if (l.src === 'engine' && l.kind === 'done' && typeof d.projects === 'number') {
      if (cur.step !== 'write') {
        cur.state = 'done';
        cur.end = at;
        cur = { step: 'write', state: 'done', start: at, end: at, facts: [], files: [], ai: [], decided: [] };
        out.push(cur);
      }
      cur.facts = [{ key: 'run.f.planned', params: { n: d.projects } }];
      cur.state = 'done';
      cur.end = at;
    }
  }
  if (out.length) {
    const media = out.find((e) => e.step === 'media');
    if (media && media.state === 'done') media.files = media.files.map((f) => ({ ...f, state: 'done' }));
  }
  return out;
}

/** A project's run: one entry per pipeline step from the run's stage events (which clips are past it, which one is
 * on it now), the engine's decisions (auto-answer) and the AI's replies inline, each with its time. */
export function runStory(lines: LiveLine[], now = Date.now() / 1000, clips = 0): StoryEntry[] {
  const byStep = new Map<StepId, StoryEntry>();
  const order: StepId[] = [];
  const jobStep = new Map<string, StepId>();
  const jobs: string[] = [];
  const done = new Set<string>();
  let total = 0;
  let last: StoryEntry | null = null;
  const rank = (s: StepId) => ['plan', 'transcribe', 'cut', 'captions', 'render', 'check', 'copy', 'ready', 'out'].indexOf(s);
  for (const l of lines) {
    const at: number = l.at ?? last?.start ?? now;
    const d = (l.data ?? {}) as Record<string, unknown>;
    const ev = typeof d.event === 'string' ? d.event : null;
    if (l.src === 'engine' && ev === 'run-start' && typeof d.n === 'number') total = d.n;
    if (l.src === 'engine' && (ev === 'stage-start' || ev === 'stage-done') && typeof d.stage === 'string') {
      const step = stepOfStage(d.stage);
      if (!step) continue;
      const job = typeof d.job === 'string' ? d.job : '';
      if (job && !jobs.includes(job)) jobs.push(job);
      if (job) {
        const prev = jobStep.get(job);
        if (!prev || rank(step) >= rank(prev)) jobStep.set(job, step);
      }
      let e = byStep.get(step);
      if (!e) {
        e = { step, state: 'now', start: at, end: null, facts: [], files: [], ai: [], decided: [] };
        byStep.set(step, e);
        order.push(step);
      }
      e.end = at;
      last = e;
      continue;
    }
    if (l.src === 'engine' && ev === 'job-done' && typeof d.job === 'string') {
      done.add(d.job);
      if (!jobs.includes(d.job)) jobs.push(d.job);
      continue;
    }
    if (!last) continue;
    if (l.src === 'engine' && ev === 'auto-answer') last.decided.push({ kind: String(d.kind ?? d.checkpoint_kind ?? d.checkpoint ?? ''), by: String(d.by ?? ''), job: typeof d.job === 'string' ? d.job : typeof d.item === 'string' ? d.item : undefined, at });
    const ai = aiLine(l);
    if (ai?.text) last.ai.push(ai);
  }
  const n = Math.max(total, clips, jobs.length);
  const steps = order.sort((a, b) => rank(a) - rank(b));
  const maxStep = jobs.length ? Math.max(...jobs.map((j) => (done.has(j) ? 99 : rank(jobStep.get(j) ?? 'plan')))) : -1;
  return steps.map((s) => {
    const e = byStep.get(s)!;
    const past = jobs.filter((j) => done.has(j) || rank(jobStep.get(j) ?? 'plan') > rank(s));
    const on = jobs.filter((j) => !done.has(j) && jobStep.get(j) === s);
    e.files = jobs.map((j) => ({ name: j, state: past.includes(j) ? 'done' : on.includes(j) ? 'now' : 'todo' }));
    e.state = on.length || (rank(s) >= maxStep && done.size < n) ? 'now' : 'done';
    if (e.state === 'now') e.end = null;
    e.facts = n ? [{ key: 'run.f.clips', params: { done: past.length, n } }] : [];
    return e;
  });
}

// ---------------------------------------------------------------- Watch all
/** The jobs running now, one per request / project (a running project lists several clip rows): Watch all's tiles. */
export function runningJobs(rows: StudioRow[]): StudioRow[] {
  const seen = new Set<string>();
  const out: StudioRow[] = [];
  for (const r of rows) {
    if (r.group !== 'run' || r.tone !== 'run') continue;
    const id = r.kind === 'request' ? `r:${r.r?.id}` : `p:${r.item}`;
    if ((r.kind !== 'request' && !r.item) || seen.has(id)) continue;
    seen.add(id);
    out.push(r);
  }
  return out;
}

// ---------------------------------------------------------------- the hook
export interface LiveState {
  lines: LiveLine[];
  running: boolean;
  loaded: boolean;
  error: string | null;
  /** lines that came in since mount (the pane counts them for "Jump to live") */
  version: number;
}

/** A job's transcript, live: the backlog first, then whatever the engine announces (`live` events), with a slow
 * re-read as a safety net (it also keeps the engine watching the job). */
export function useLive(kind: 'request' | 'project' | 'ask', id: string | null | undefined, enabled = true): LiveState {
  const { client, subscribe } = useEngine();
  const [st, setSt] = useState<LiveState>({ lines: [], running: false, loaded: false, error: null, version: 0 });
  const cursor = useRef<string | null>(null);
  const busy = useRef(false);
  const again = useRef(false);
  const alive = useRef(true);
  const key = id ? `${kind}:${id}` : null;

  const pull = useCallback(async () => {
    if (!client || !id) return;
    if (busy.current) {
      again.current = true;
      return;
    }
    busy.current = true;
    try {
      for (let k = 0; k < 20; k++) {
        const doc: LiveDoc = await client.live(kind, id, cursor.current);
        if (!alive.current) return;
        cursor.current = doc.cursor;
        setSt((s) => ({ lines: appendLines(s.lines, doc.lines), running: doc.running, loaded: true, error: null, version: s.version + (doc.lines.length ? 1 : 0) }));
        if (!doc.more) break;
      }
    } catch (e) {
      if (alive.current) setSt((s) => ({ ...s, loaded: true, error: e instanceof Error ? e.message : String(e) }));
    } finally {
      busy.current = false;
      if (again.current && alive.current) {
        again.current = false;
        void pull();
      }
    }
  }, [client, kind, id]);

  useEffect(() => {
    alive.current = true;
    cursor.current = null;
    setSt({ lines: [], running: false, loaded: false, error: null, version: 0 });
    if (!enabled || !key) return () => void (alive.current = false);
    void pull();
    const off = subscribe((e) => {
      if (e.type === 'live' && e.key === key) void pull();
    });
    const tm = window.setInterval(() => void pull(), 5000);
    return () => {
      alive.current = false;
      off();
      window.clearInterval(tm);
    };
  }, [key, enabled, pull, subscribe]);
  return st;
}
