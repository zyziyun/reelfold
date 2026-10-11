// Delete a project from the Studio's row menu: the engine says what would go (POST /api/history/trash-plan: only a
// project folder the app made or found, never one with her footage inside, never a running one), the main process
// asks once in a native dialog that names every folder, its size and the recordings that stay, then moves the
// folders to the Trash (restorable there) and tells the engine to forget them. Her source footage is never touched.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { dialog, shell, type BrowserWindow } from 'electron';
import type { EngineClient } from '../shared/engineClient';
import type { TrashPlanItem } from '../shared/v04';
import { cleanupPathOk } from './cleanupPolicy';

export type TrashLang = 'en' | 'zh' | 'fr';

export interface TrashResult {
  confirmed: boolean;
  trashed: string[];
  /** projects not deleted and why (TrashPlanItem.reason, or 'failed' when the Trash refused) */
  refused: { dir: string; name: string; reason: string }[];
}

function size(n: number, lang: TrashLang): string {
  const mb = n / 1e6;
  const v = mb >= 1000 ? `${(mb / 1000).toFixed(1)} GB` : `${mb >= 10 ? Math.round(mb) : mb.toFixed(1)} MB`;
  return lang === 'fr' ? v.replace('.', ',') : v;
}

const WORDS = {
  en: {
    one: (name: string) => `Move “${name}” to the Trash?`,
    many: (n: number) => `Move these ${n} projects to the Trash?`,
    files: (n: number, s: string) => `${n} file${n === 1 ? '' : 's'}, ${s}`,
    keep: 'Your recordings stay where they are:',
    back: 'You can put it back from the Trash.',
    buttons: ['Cancel', 'Move to Trash'],
  },
  zh: {
    one: (name: string) => `把「${name}」移到废纸篓？`,
    many: (n: number) => `把这 ${n} 个项目移到废纸篓？`,
    files: (n: number, s: string) => `${n} 个文件，${s}`,
    keep: '你的原始录像不动，留在原处：',
    back: '可以从废纸篓放回来。',
    buttons: ['取消', '移到废纸篓'],
  },
  fr: {
    one: (name: string) => `Mettre « ${name} » à la corbeille ?`,
    many: (n: number) => `Mettre ces ${n} projets à la corbeille ?`,
    files: (n: number, s: string) => `${n} fichier${n === 1 ? '' : 's'}, ${s}`,
    keep: 'Vos enregistrements restent où ils sont :',
    back: 'Vous pouvez les récupérer dans la corbeille.',
    buttons: ['Annuler', 'Mettre à la corbeille'],
  },
} as const;

/** The exact confirmation: every folder that goes (with its file count and size) and the recordings that stay. */
export function trashDialogText(items: TrashPlanItem[], lang: TrashLang) {
  const w = WORDS[lang] ?? WORDS.en;
  const ok = items.filter((x) => x.ok && x.target);
  const list = ok.map((x) => `• ${x.name}\n   ${x.target}  (${w.files(x.files ?? 0, size(x.bytes ?? 0, lang))})`).join('\n');
  const keep = [...new Set(ok.flatMap((x) => x.keep ?? []))].slice(0, 12);
  return {
    message: ok.length === 1 ? w.one(ok[0].name) : w.many(ok.length),
    detail: list + (keep.length ? `\n\n${w.keep}\n${keep.map((k) => `• ${k}`).join('\n')}` : '') + `\n\n${w.back}`,
    buttons: [...w.buttons],
  };
}

export async function trashProjects(
  dirs: string[],
  d: {
    win: BrowserWindow | null;
    client: EngineClient | null;
    lang: TrashLang;
    trash?: (p: string) => Promise<void>;
  },
): Promise<TrashResult> {
  const c = d.client;
  if (!c) throw new Error('engine not running');
  const plan = (await c.historyTrashPlan(dirs)).items;
  const refused: TrashResult['refused'] = plan.filter((x) => !x.ok).map((x) => ({ dir: x.dir, name: x.name, reason: x.reason ?? 'unsafe' }));
  const ok = plan.filter((x) => x.ok && x.target);
  if (!ok.length) return { confirmed: false, trashed: [], refused };
  const txt = trashDialogText(ok, d.lang);
  const opts = {
    type: 'warning' as const,
    message: txt.message,
    detail: txt.detail,
    buttons: txt.buttons,
    defaultId: 0,
    cancelId: 0,
    noLink: true,
  };
  const r = d.win ? await dialog.showMessageBox(d.win, opts) : await dialog.showMessageBox(opts);
  if (r.response !== 1) return { confirmed: false, trashed: [], refused };
  const trashed: string[] = [];
  const home = os.homedir();
  for (const x of ok) {
    const target = x.target!;
    try {
      // the engine's own guard again, here where the folder is moved: a folder deep enough, never home or a top folder
      if (!fs.statSync(target).isDirectory() || !cleanupPathOk(target, true, home) || !path.isAbsolute(x.dir)) throw new Error('unsafe');
      await (d.trash ?? ((p: string) => shell.trashItem(p)))(target);
      trashed.push(x.dir);
    } catch {
      refused.push({ dir: x.dir, name: x.name, reason: 'failed' });
    }
  }
  if (trashed.length) await c.forgetHistory(trashed).catch(() => undefined);
  return { confirmed: true, trashed, refused };
}
