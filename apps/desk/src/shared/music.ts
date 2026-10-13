// Settings › Music (engine: lib/vstudio/music.py, desk_engine/music.py): the CC0 music library every video's music is
// picked from, the built-in beds, and her favourites / bans ($VSTUDIO_HOME/music.json, shared with the CLI skill).

export interface MusicTrack {
  /** lib:<id> */
  id: string;
  title: string;
  artist: string | null;
  mood: string;
  /** piano / ambient / acoustic / cinematic / pop / electronic / lofi / documentary / chinese / world */
  style: string | null;
  tags: string[];
  bpm: number | null;
  energy: number | null;
  duration: number | null;
  license: string;
  /** the track's source page; licence_evidence: the archived page that states its licence */
  origin: string | null;
  licence_evidence: string | null;
  installed: boolean;
  path: string | null;
  steady: boolean;
  favourite: boolean;
  banned: boolean;
  /** how many of her recent videos have it */
  uses: number;
}

export interface MusicBuiltin {
  id: string;
  title: string;
  title_zh: string;
  mood: string;
  bpm: number;
  path: string | null;
  license: string;
  favourite: boolean;
  banned: boolean;
  uses: number;
}

export interface MusicDoc {
  dir: string | null;
  installed: number;
  total: number;
  size: number;
  tracks: MusicTrack[];
  builtins: MusicBuiltin[];
  prefs: { favourites: string[]; banned: string[] };
  recent: { track: string; title: string | null; at: number | null; group: string | null }[];
  recent_n: number;
}

export const MUSIC_GROUP = 'music-library';
export const MUSIC_STYLES = ['acoustic', 'pop', 'electronic', 'cinematic', 'piano', 'ambient', 'lofi', 'documentary', 'chinese', 'world'] as const;

/** The library's tracks grouped by style (the order above; anything else last), each group by title. */
export function byStyle(tracks: MusicTrack[]): [string, MusicTrack[]][] {
  const order = (s: string | null) => {
    const i = (MUSIC_STYLES as readonly string[]).indexOf(s ?? '');
    return i < 0 ? MUSIC_STYLES.length : i;
  };
  const m = new Map<string, MusicTrack[]>();
  for (const t of [...tracks].sort((a, b) => order(a.style) - order(b.style) || a.title.localeCompare(b.title))) {
    const k = t.style ?? 'other';
    m.set(k, [...(m.get(k) ?? []), t]);
  }
  return [...m.entries()];
}
