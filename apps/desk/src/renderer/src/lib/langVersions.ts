// A goal video made in several languages (goal mode: an English project for YouTube / TikTok, a 中文 one for 小红书 /
// B站): the clip page shows every language's versions in one switcher. The siblings come from the goal's record (the
// video's language versions, one project each); each sibling's clip is its project's made clip.
import type { Clip } from '../../../shared/v04';
import type { GoalVersion } from '../../../shared/goal';
import { useLoad } from './engine';
import { useHistory } from './history';

export interface LangVersion {
  /** the sibling project's history id */
  item: string;
  lang: string;
  name: string;
  clip: Clip;
}

/** "… (English)" / "… (中文)" -> en / zh (the engine's goals._lang_of) */
export function langOfName(n: string | null | undefined): string | null {
  const s = String(n ?? '');
  if (/[(（]\s*(English|EN)\s*[)）]/i.test(s)) return 'en';
  if (/[(（]\s*(中文|Chinese|ZH)\s*[)）]/i.test(s)) return 'zh';
  if (/[(（]\s*(Français|French|FR)\s*[)）]/i.test(s)) return 'fr';
  return null;
}

/** a language by its own name (the switcher's group labels read the same in every UI language) */
export function langName(l: string): string {
  return ({ en: 'English', zh: '中文', fr: 'Français' } as Record<string, string>)[l] ?? l;
}

/** this project's language and its siblings' made clips ({mine: null, others: []} outside a goal) */
export function useLangVersions(item: string): { mine: string | null; others: LangVersion[] } {
  const hist = useHistory();
  const me = hist.data?.items.find((i) => i.id === item);
  const gid = me?.goal ?? null;
  const vid = me?.goal_video ?? null;
  const { data } = useLoad(
    async (c) => {
      if (!gid || !vid) return null;
      const g = await c.goal(gid);
      const v = g.videos.find((x) => x.id === vid);
      const vs: GoalVersion[] = v?.versions?.length ? v.versions : (v?.projects ?? []).map((p) => ({ ...p, lang: langOfName(p.name), state: 'made' as const }));
      const mine = vs.find((x) => x.item === item)?.lang ?? langOfName(me?.name) ?? null;
      const others = await Promise.all(
        vs
          .filter((x) => x.item && x.item !== item && x.lang)
          .map(async (x) => {
            const cd = await c.clips(x.item!).catch(() => null);
            const clip = cd?.clips.find((cl) => cl.files.length > 0);
            return clip ? { item: x.item!, lang: x.lang!, name: x.name ?? '', clip } : null;
          }),
      );
      return { mine, others: others.filter((x): x is LangVersion => !!x) };
    },
    [gid, vid, item],
  );
  return data ?? { mine: null, others: [] };
}
