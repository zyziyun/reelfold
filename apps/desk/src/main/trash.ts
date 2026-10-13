// Delete › Move to Trash (「删除」, the soft way): her confirm is the renderer's Delete dialog (it names every path that
// goes and the recordings that stay); the engine then holds the things out of every list (a pending delete, Undo still
// possible). Once the Undo toast is gone the renderer asks for it here: the engine's own paths for that pending delete
// (never a path the renderer sends), each checked again - absolute, there, deep enough, never home / a top folder -
// are moved to the macOS Trash / Windows Recycle Bin (restorable there), and the engine is told which moved so their
// notes go and the rest comes back. Her source footage is never a target (engine/desk_engine/purge.py).
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { shell } from 'electron';
import type { EngineClient } from '../shared/engineClient';
import { cleanupPathOk } from './cleanupPolicy';

export interface TrashDeps {
  client: EngineClient | null;
  trash?: (p: string) => Promise<void>;
  home?: string;
}

/** A target the Trash may take: absolute, there, at least three levels deep, never home or a top folder. */
export function trashTargetOk(p: string, home = os.homedir()): boolean {
  if (!path.isAbsolute(p)) return false;
  try {
    fs.lstatSync(p);
  } catch {
    return false;
  }
  // any kind of file (a run store, a report), not only media: the engine named it as Reelfold's own
  return cleanupPathOk(p, true, home);
}

export async function trashPending(id: string, d: TrashDeps): Promise<{ trashed: string[]; failed: string[]; back: { key: string; name: string }[] }> {
  const c = d.client;
  if (!c) throw new Error('engine not running');
  const p = await c.deletePendingOne(id);
  const trashed: string[] = [];
  const failed: string[] = [];
  for (const t of p.targets) {
    try {
      if (!trashTargetOk(t, d.home)) throw new Error('unsafe');
      await (d.trash ?? ((x: string) => shell.trashItem(x)))(t);
      trashed.push(t);
    } catch {
      if (fs.existsSync(t)) failed.push(t);
      else trashed.push(t); // already gone (moved by hand): nothing to keep
    }
  }
  const r = await c.deleteCommit(id, trashed, failed);
  return { trashed, failed, back: r.back };
}

/** The app quit while a delete's Undo toast was up: its paths go to the Trash on the next start. */
export async function trashStale(d: TrashDeps): Promise<{ n: number }> {
  const c = d.client;
  if (!c) return { n: 0 };
  const { items } = await c.deletePending();
  let n = 0;
  for (const x of items.filter((y) => y.stale)) {
    await trashPending(x.id, d).catch(() => undefined);
    n++;
  }
  return { n };
}
