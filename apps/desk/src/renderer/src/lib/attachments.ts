// What she attached to the composer, as she thinks of it: a drone folder of DJI_0001_D.MP4 + DJI_0001_D.SRT (the
// .SRT is the drone's telemetry, engine intake/docs.py role "telemetry") is one video with its .srt, not two files.
// Pure: grouping, removal and the counts behind the composer's one-line summary.

export type AttachKind = 'video' | 'photo' | 'audio' | 'doc' | 'subs' | 'folder' | 'other';

export interface AttachItem {
  /** the main path (the video for a pair); also the React key */
  path: string;
  /** every path this item stands for (video + its same-named .srt); removing the item removes all of them */
  paths: string[];
  kind: AttachKind;
  name: string;
  /** a video's same-named .srt / .vtt next to it */
  sidecar: string | null;
}

export interface AttachSummary {
  /** paths attached (a pair is 2) */
  files: number;
  /** items in the list (a pair is 1) */
  items: number;
  videos: number;
  /** videos that came with their same-named .srt */
  withSubs: number;
  photos: number;
  audio: number;
  docs: number;
  /** subtitle files with no video of the same name */
  subs: number;
  folders: number;
  other: number;
  /** the one folder every file sits in, when they share one (a dropped drone card) */
  dir: string | null;
}

const VIDEO = ['mp4', 'mov', 'm4v', 'mkv', 'webm', 'avi', 'mts'];
const PHOTO = ['jpg', 'jpeg', 'png', 'webp', 'heic', 'dng'];
const AUDIO = ['wav', 'mp3', 'm4a', 'aac', 'flac'];
const DOC = ['pdf', 'docx', 'pptx', 'md', 'txt'];
const SUBS = ['srt', 'vtt'];

/** above this many items the composer shows the summary line instead of every chip */
export const CHIP_LIMIT = 4;

const trim = (p: string) => p.replace(/[\\/]+$/, '');
export const baseName = (p: string) => trim(p).split(/[\\/]/).pop() ?? p;
const dirOf = (p: string) => {
  const t = trim(p);
  const i = Math.max(t.lastIndexOf('/'), t.lastIndexOf('\\'));
  return i > 0 ? t.slice(0, i) : '';
};
const extOf = (p: string) => {
  const b = baseName(p);
  const i = b.lastIndexOf('.');
  return i > 0 ? b.slice(i + 1).toLowerCase() : '';
};
/** dir + name without extension, case-insensitive: the pairing key */
const stemKey = (p: string) => {
  const b = baseName(p);
  const i = b.lastIndexOf('.');
  return `${dirOf(p)}/${(i > 0 ? b.slice(0, i) : b).toLowerCase()}`;
};

export function kindOf(p: string): AttachKind {
  const e = extOf(p);
  if (VIDEO.includes(e)) return 'video';
  if (PHOTO.includes(e)) return 'photo';
  if (AUDIO.includes(e)) return 'audio';
  if (DOC.includes(e)) return 'doc';
  if (SUBS.includes(e)) return 'subs';
  if (!e || /[\\/]$/.test(p)) return 'folder';
  return 'other';
}

/** the attached paths as list items, in the order she added them; a video and its same-named .srt are one item */
export function groupAttachments(files: string[]): AttachItem[] {
  const videoAt = new Map<string, string>();
  for (const f of files) if (kindOf(f) === 'video' && !videoAt.has(stemKey(f))) videoAt.set(stemKey(f), f);
  const sidecarOf = new Map<string, string>();
  for (const f of files) {
    if (kindOf(f) !== 'subs') continue;
    const v = videoAt.get(stemKey(f));
    if (v && !sidecarOf.has(v)) sidecarOf.set(v, f);
  }
  const taken = new Set(sidecarOf.values());
  const out: AttachItem[] = [];
  for (const f of files) {
    if (taken.has(f)) continue;
    const kind = kindOf(f);
    const sidecar = kind === 'video' ? (sidecarOf.get(f) ?? null) : null;
    out.push({ path: f, paths: sidecar ? [f, sidecar] : [f], kind, name: baseName(f), sidecar });
  }
  return out;
}

/** the paths left after removing one item (a pair goes as a whole) */
export function removeItem(files: string[], item: AttachItem): string[] {
  const drop = new Set(item.paths);
  return files.filter((f) => !drop.has(f));
}

export function summarize(files: string[], items: AttachItem[] = groupAttachments(files)): AttachSummary {
  const n = (k: AttachKind) => items.filter((i) => i.kind === k).length;
  const dirs = new Set(files.map(dirOf));
  const only = dirs.size === 1 ? [...dirs][0] : '';
  return {
    files: files.length,
    items: items.length,
    videos: n('video'),
    withSubs: items.filter((i) => i.sidecar).length,
    photos: n('photo'),
    audio: n('audio'),
    docs: n('doc'),
    subs: n('subs'),
    folders: n('folder'),
    other: n('other'),
    dir: files.length > 1 && only ? baseName(only) || null : null,
  };
}
