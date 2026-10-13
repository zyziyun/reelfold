// Per-platform video lengths (engine: lib/vstudio/platform_habits.py, references/platforms/<name>.md;
// desk_engine/platform_lengths.py): each platform's length band per content kind, and her own range per platform
// (Settings › Publishing › Video length, $VSTUDIO_HOME/platforms.json - shared with the CLI skill).

export type LengthKind = 'history' | 'essay' | 'film' | 'photos' | 'reel' | 'vlog' | 'talking_head' | 'course';

export interface LengthBand {
  min: number;
  target: number;
  max: number;
  form: 'long' | 'short';
  chapters: boolean;
  source?: string | null;
}

export interface PlatformLengthRow {
  platform: string;
  label: string;
  form: 'long' | 'short';
  /** file | persona | settings | builtin: where the numbers come from */
  source: string;
  /** her own range (Settings), clamping every kind */
  limits: { min_s?: number; max_s?: number };
  hard: { min?: number | null; max?: number | null };
  lengths: Record<LengthKind, LengthBand>;
}

export interface PlatformLengthsDoc {
  kinds: LengthKind[];
  platforms: PlatformLengthRow[];
}

/** One render of a goal video: the platforms that share a length (engine: platform_habits.cuts). */
export interface GoalCut {
  id: string;
  platforms: string[];
  length_s: number;
  form: 'long' | 'short';
  chapters: boolean;
}

/** 90 -> "90 s", 240 -> "4 min", 330 -> "5.5 min" (zh: 秒 / 分钟) - the engine's fmt_len. */
export function fmtDuration(secs: number, lang = 'en'): string {
  const zh = lang.startsWith('zh');
  if (secs < 120) return zh ? `${Math.round(secs)} 秒` : `${Math.round(secs)} s`;
  const m = Math.round((secs / 60) * 2) / 2;
  return zh ? `${m} 分钟` : `${m} min`;
}

/** The typical range of a platform over every kind: [shortest min, longest max]. */
export function typicalRange(row: Pick<PlatformLengthRow, 'lengths'>): [number, number] {
  const bands = Object.values(row.lengths);
  if (!bands.length) return [0, 0];
  return [Math.min(...bands.map((b) => b.min)), Math.max(...bands.map((b) => b.max))];
}

/** A typed number of seconds -> a whole number in [lo, hi], or null (empty / not a number / out of range). */
export function parseSecs(text: string, lo: number, hi: number): number | null {
  const n = Math.round(Number(String(text).trim()));
  if (!String(text).trim() || !Number.isFinite(n) || n < lo || n > hi) return null;
  return n;
}
