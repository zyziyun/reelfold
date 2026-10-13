// A chat edit's progress (「和 AI 一起改」 bubble): which step it is on, from the request's live transcript
// (desk_engine.outputs.live_path: the engine's own steps - start / read / think / check / done, error, stop - and the
// model CLI's streamed lines) plus what the panel itself is doing (applying the answer). Nothing is timed to look
// busy: a step moves only when a line says so; "about N s left" only from her own past edits on the same model.
// Pure (unit-tested) apart from the small local store of past durations.
import type { LiveLine } from '../../../shared/v04';

export type EditPhase = 'read' | 'think' | 'check' | 'apply' | 'done';
/** the steps the bar shows (done is the end, not a step) */
export const EDIT_STEPS: EditPhase[] = ['read', 'think', 'check', 'apply'];
/** no new line for this long while the AI works: say it is still thinking (never a frozen bar) */
export const QUIET_S = 25;

export interface EditLocal {
  /** the answer is being put on the clip (n changes) */
  applying?: number | null;
  /** the answer is on the clip */
  applied?: boolean;
}

export interface EditProgress {
  phase: EditPhase;
  /** 1-based step of EDIT_STEPS */
  step: number;
  steps: number;
  /** a line said it failed: the step it was on */
  failedAt: EditPhase | null;
  stopped: boolean;
  /** the AI she picked failed and the request went on with another (the engine's fallback line) */
  fallback: { from: string; to: string; code: string } | null;
  /** the model's provider / model, once a line named them */
  provider: string | null;
  model: string | null;
  /** seconds since the newest line (or the start) */
  quietFor: number;
  quiet: boolean;
}

const STAGE_PHASE: Record<string, EditPhase> = { start: 'read', read: 'read', think: 'think', ask: 'think', rules: 'check', check: 'check', plan: 'check', done: 'done' };
const rank = (p: EditPhase) => (p === 'done' ? 4 : EDIT_STEPS.indexOf(p));

/** The step a chat edit is on. ``started``: when she sent it (epoch s); ``now``: epoch s. */
export function editProgress(lines: LiveLine[], local: EditLocal, started: number, now: number): EditProgress {
  let phase: EditPhase = 'read';
  let failedAt: EditPhase | null = null;
  let stopped = false;
  let provider: string | null = null;
  let model: string | null = null;
  let fallback: EditProgress['fallback'] = null;
  let last = started;
  const up = (p: EditPhase) => {
    if (rank(p) > rank(phase)) phase = p;
  };
  for (const l of lines) {
    if (l.at && l.at > last) last = l.at;
    const d = (l.data ?? {}) as Record<string, unknown>;
    if (l.src === 'engine') {
      if (l.kind === 'stage' && typeof d.stage === 'string' && STAGE_PHASE[d.stage]) up(STAGE_PHASE[d.stage]);
      if (l.kind === 'stage' && typeof d.provider === 'string') provider = d.provider;
      if (l.kind === 'stage' && typeof d.model === 'string') model = d.model;
      if (l.kind === 'error') failedAt = failedAt ?? phase;
      if (l.kind === 'stop') stopped = true;
      if (l.kind === 'fallback' && typeof d.from === 'string' && typeof d.to === 'string') fallback = { from: d.from, to: d.to, code: String(d.code ?? 'failed') };
    } else {
      up('think'); // the model is working: it read the clip
      if (l.provider) provider = l.provider;
      if (l.model) model = l.model;
    }
  }
  // the engine answered: the panel puts the changes on the clip (its own request), then it is done
  if (local.applying != null && !local.applied) phase = 'apply';
  if (local.applied) phase = 'done';
  const quietFor = Math.max(0, now - last);
  const working = !failedAt && !stopped && phase !== 'done';
  return {
    phase,
    step: Math.min(EDIT_STEPS.length, (phase === 'done' ? EDIT_STEPS.length - 1 : rank(phase)) + 1),
    steps: EDIT_STEPS.length,
    failedAt,
    stopped,
    fallback,
    provider,
    model,
    quietFor,
    quiet: working && phase !== 'apply' && quietFor >= QUIET_S,
  };
}

/** The newest lines worth showing under the bar (the model's stream and the engine's steps; progress counters out). */
export function logTail(lines: LiveLine[], n = 3): LiveLine[] {
  return lines.filter((l) => l.kind !== 'progress' && l.text.trim()).slice(-n);
}

// ---------------------------------------------------------------- how long her edits took (this computer only)
const STORE = 'ce.editTimes';
const KEEP = 8;

export function timeKey(provider: string | null | undefined, model: string | null | undefined): string | null {
  return provider ? `${provider}/${model ?? ''}` : null;
}

function load(): Record<string, number[]> {
  try {
    const v = JSON.parse(localStorage.getItem(STORE) ?? '{}');
    return v && typeof v === 'object' ? v : {};
  } catch {
    return {};
  }
}

/** a finished edit (answer received) on this model: how long it took, in seconds */
export function rememberEditTime(key: string | null, seconds: number): void {
  if (!key || !(seconds > 0) || seconds > 3600) return;
  try {
    const all = load();
    all[key] = [...(all[key] ?? []), Math.round(seconds)].slice(-KEEP);
    localStorage.setItem(STORE, JSON.stringify(all));
  } catch {
    /* no storage: no estimate */
  }
}

/** The typical time of an edit on this model (the median of her last ones), or null under 2 of them. */
export function editEstimate(key: string | null, times: Record<string, number[]> = load()): number | null {
  const xs = key ? (times[key] ?? []).filter((x) => x > 0) : [];
  if (xs.length < 2) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

/** Seconds left from the estimate (rounded to 5 s), or null when there is none or it is already past it. */
export function secondsLeft(estimate: number | null, elapsed: number): number | null {
  if (estimate == null) return null;
  const left = estimate - elapsed;
  if (left < 3) return null;
  return Math.max(5, Math.round(left / 5) * 5);
}
