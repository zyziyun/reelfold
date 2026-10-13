// The clip page player's version chips, each named by what it is (2026-10-13, her clip page read "Edited · Edited ·
// Edited · Original"): "16:9 · edited", "9:16 TikTok · edited", "3:4 Xiaohongshu · edited", "Original". An edit's fresh
// renders (one per target: primary + her exports; the final when there is one, else the preview) first, then the
// original files. Pure: the editor and the unit tests share it.
import type { ClipFile } from '../../../shared/v04';
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
