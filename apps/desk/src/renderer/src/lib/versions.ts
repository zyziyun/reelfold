// The clip page player's version chips, each named by what it is (2026-10-13, her clip page read "Edited · Edited ·
// Edited · Original"): "16:9 · edited", "9:16 TikTok · edited", "3:4 Xiaohongshu · edited", "Original". An edit's fresh
// renders (one per target: primary + her exports; the final when there is one, else the preview) first, then the
// original files. Pure: the editor and the unit tests share it.
import type { ClipFile, OutputDoc } from '../../../shared/v04';
import { EXPORT_PLATFORMS } from '../../../shared/chatEdit';
import { t } from '../i18n';
import { platformName } from './platformName';

const RATIO = /^\d+:\d+$/;

export interface RenderRow {
  target: string;
  quality?: string;
  file: string;
  fresh?: boolean;
  simulated?: boolean;
  key?: string | number | null;
  at?: string | null;
}

/** an export target's shape: "9:16" itself, a platform target by its profile ("xiaohongshu:vertical" -> 3:4) */
export function targetAspect(target: string): string | null {
  if (RATIO.test(target)) return target;
  const p = EXPORT_PLATFORMS.find((x) => x.target === target);
  if (p) return p.aspect;
  const ori = target.split(':')[1];
  return ori === 'vertical' ? '9:16' : ori === 'horizontal' ? '16:9' : null;
}

/** "youtube:vertical" -> "YouTube Shorts", "tiktok:vertical" -> "TikTok" */
function targetPlatform(target: string): string | null {
  if (RATIO.test(target)) return null;
  const [name, ori] = target.split(':');
  return platformName(name === 'youtube' && ori === 'vertical' ? 'youtube-shorts' : name);
}

/** The files the clip page plays after an edit was rendered: each fresh render (one per target), then the originals,
 * each with its chip label. */
export function editedFiles(renders: RenderRow[], originals: ClipFile[]): ClipFile[] {
  const best = new Map<string, RenderRow>();
  for (const r of renders) {
    if (!r.fresh || r.simulated) continue;
    const had = best.get(r.target);
    if (!had || (had.quality !== 'final' && r.quality === 'final')) best.set(r.target, r);
  }
  const primary = originals[0]?.aspect;
  const edited = [...best.values()].map((r) => {
    const aspect = r.target === 'primary' ? (primary ?? '3:4') : (targetAspect(r.target) ?? r.target);
    const what = [RATIO.test(aspect) ? aspect : null, r.target === 'primary' ? null : targetPlatform(r.target)].filter(Boolean).join(' ');
    return { path: r.file, v: r.key ?? r.at, aspect, label: what ? t('st.verEdited', { v: what }) : t('editor.editedVersion') };
  });
  const many = originals.length > 1;
  return [...edited, ...originals.map((f) => ({ ...f, label: many && RATIO.test(f.aspect) ? t('st.verOriginal', { v: f.aspect }) : t('c.original') }))];
}

// ---------------------------------------------------------------- which version a platform posts
// Each platform's shapes, its default first (mirrors desk_engine/workpkg.py _FALLBACK / vstudio.platform).
const V = '9:16';
const H = '16:9';
const PF_SHAPES: Record<string, string[]> = {
  youtube: [H],
  'youtube-shorts': [V],
  tiktok: [V],
  instagram: [V, '4:5'],
  x: [H, '1:1', V],
  facebook: [V, '4:5', H],
  linkedin: [H, '1:1', '4:5'],
  threads: [V, H],
  reddit: [H, '1:1', V],
  pinterest: [V, '2:3', '1:1'],
  snapchat: [V],
  xiaohongshu: ['3:4', V, H],
  douyin: [V, H],
  'wechat-channels': [V, H],
  bilibili: [H, V],
  kuaishou: [V, H],
  weibo: [H, V],
  zhihu: [H, V],
  dailymotion: [H, V],
  kwai: [V],
};

const ratio = (a: string | null | undefined): number | null => {
  const m = /^(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)$/.exec(a ?? '');
  return m && Number(m[2]) ? Number(m[1]) / Number(m[2]) : null;
};
const fileRatio = (f: Pick<ClipFile, 'aspect' | 'w' | 'h'>) => (f.w && f.h ? f.w / f.h : ratio(f.aspect));

/** The clip file a platform posts, as the publisher picks it (workpkg.pick_version): the first of the platform's
 * shapes (its default first) the clip has, else the version closest to its default shape. */
export function versionFor<F extends Pick<ClipFile, 'aspect' | 'w' | 'h'>>(platform: string, files: F[]): F | null {
  if (!files.length) return null;
  const shapes = PF_SHAPES[platform.split(':')[0]] ?? [H];
  for (const s of shapes) {
    const want = ratio(s)!;
    const f = files.find((x) => {
      const r = fileRatio(x);
      return r != null && Math.abs(r - want) < 0.04;
    });
    if (f) return f;
  }
  const want = ratio(shapes[0])!;
  return files.reduce((a, f) => (Math.abs((fileRatio(f) ?? want) - want) < Math.abs((fileRatio(a) ?? want) - want) ? f : a), files[0]);
}

/** The platforms a file is for: the ones the engine says (``platforms``), else its own export platform. Bare names. */
export function filePlatforms(f: Pick<ClipFile, 'platform' | 'platforms'>): string[] {
  const xs = f.platforms?.length ? f.platforms : f.platform ? [f.platform] : [];
  return [...new Set(xs.map((x) => x.split(':')[0]).filter((x) => x && x !== 'None'))];
}

/** The planned platforms (``targets``) a clip has no version for: none of its files is for it, and none has the
 * platform's own default shape (a 3:4 小红书 story alone leaves B站's 16:9 not made). */
export function missingTargets(targets: string[] | null | undefined, files: Pick<ClipFile, 'platform' | 'platforms' | 'aspect' | 'w' | 'h'>[]): string[] {
  const have = new Set(files.flatMap(filePlatforms));
  return [...new Set((targets ?? []).map((x) => x.split(':')[0]))].filter((pf) => {
    if (have.has(pf)) return false;
    const want = ratio((PF_SHAPES[pf] ?? [H])[0])!;
    return !files.some((f) => {
      const r = fileRatio(f);
      return r != null && Math.abs(r - want) < 0.04;
    });
  });
}

/** A rendered narration/grade keeps the transcript's timestamps when the edit did not retime the clip.
 * Only source-time editing (cuts, trim, speed or pickups) needs the original while the transcript is open. */
export function transcriptNeedsSource(doc: Pick<OutputDoc, 'cuts' | 'trim' | 'speed' | 'duration' | 'pickups'>): boolean {
  return doc.cuts.some((c) => c.end > c.start)
    || !!(doc.trim && (doc.trim.start > 0 || doc.trim.end < doc.duration))
    || doc.speed !== 1
    || !!doc.pickups?.length;
}
