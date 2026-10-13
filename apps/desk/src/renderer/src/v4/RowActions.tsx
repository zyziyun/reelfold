// The Studio's row actions (「任务的删除怎么没了」): one hook for the list's hover ⋯ and right-click menu, the bulk
// bar, ⌫ and the page header's ⋯. Archive is the default (undo toast); Delete… opens the Delete dialog for every kind
// (DeleteDialog.tsx: what Reelfold made goes - to the Trash with Undo, or permanently after a second step - her
// recordings never); Stop / Try again for a run; Rename; Show in Finder.
import { useState, type ReactNode } from 'react';
import { Archive, ArchiveRestore, FolderOpen, Pencil, RotateCcw, Square, Trash2 } from 'lucide-react';
import { PromptModal } from '../components/ui';
import { t } from '../i18n';
import { useEngine } from '../lib/engine';
import { useHistory } from '../lib/history';
import { alsoGoes, busy, deleteSel, rowActions, split, type ActionTarget, type RowAction } from '../lib/rowActions';
import { useDelete } from './DeleteDialog';
import { errText } from './msg';
import { useUi, type MenuItem } from './ui';

export interface RowActionsApi {
  /** the menu of one row (or of the picked rows when it is one of them) */
  items(x: ActionTarget, picked?: ActionTarget[]): MenuItem[];
  run(a: RowAction, xs: ActionTarget[]): Promise<void>;
  archive(xs: ActionTarget[]): Promise<boolean>;
  /** the rename prompt and the Delete dialog (render once) */
  modal: ReactNode;
}

const ICON: Record<RowAction, ReactNode> = {
  'open-folder': <FolderOpen className="ico" />,
  rename: <Pencil className="ico" />,
  stop: <Square className="ico" />,
  retry: <RotateCcw className="ico" />,
  archive: <Archive className="ico" />,
  restore: <ArchiveRestore className="ico" />,
  delete: <Trash2 className="ico" />,
};

/** ``all``: every row on screen (a picked video's project siblings are named in the delete confirm). */
export function useRowActions(all: ActionTarget[], onDone?: (a: RowAction, xs: ActionTarget[]) => void): RowActionsApi {
  const { client } = useEngine();
  const { reload, wantArchived } = useHistory();
  const ui = useUi();
  const [renaming, setRenaming] = useState<ActionTarget | null>(null);
  const del = useDelete();

  const fail = (e: unknown) => ui.toast(errText(e), { error: true });

  const restore = async (xs: ActionTarget[], quiet = false) => {
    if (!client) return;
    const s = split(xs);
    try {
      if (s.requests.length) await client.restoreRequests(s.requests);
      if (s.dirs.length) await client.restoreHistory(s.dirs);
    } catch (e) {
      return fail(e);
    }
    reload();
    if (!quiet)
      ui.toast(t('ra.restoredN', { n: s.requests.length + s.dirs.length }), {
        undo: () => void archive(xs, true),
      });
  };

  const archive = async (xs: ActionTarget[], quiet = false): Promise<boolean> => {
    if (!client || !xs.length) return false;
    const s = split(xs);
    const going = s.items.find(busy);
    if (going) {
      ui.toast(t('ra.running', { name: going.name }), { error: true });
      return false;
    }
    try {
      if (s.requests.length) await client.archiveRequests(s.requests);
      if (s.dirs.length) await client.archiveHistory(s.dirs);
    } catch (e) {
      fail(e);
      return false;
    }
    wantArchived(); // the Archived filter shows at once
    reload();
    if (!quiet)
      ui.toast(t('ra.archivedN', { n: s.requests.length + s.dirs.length }), {
        undo: () => void restore(xs, true),
      });
    onDone?.('archive', xs);
    return true;
  };

  const run = async (a: RowAction, xs: ActionTarget[]) => {
    const x = xs[0];
    if (!x || !client) return;
    try {
      switch (a) {
        case 'open-folder':
          for (const y of xs.slice(0, 5)) await window.desk.showItem(y.kind === 'clip' && y.video ? y.video : y.i!.dir);
          return;
        case 'rename':
          setRenaming(x);
          return;
        case 'archive':
          await archive(xs);
          return;
        case 'restore':
          await restore(xs);
          return;
        case 'stop':
          if (x.kind === 'request') await client.stopIntake(x.r!.id);
          else await client.stopHistory(x.i!.id);
          ui.toast(t('ra.stoppedToast'));
          reload();
          return;
        case 'retry':
          if (x.kind === 'request') await client.retryIntake(x.r!.id);
          else if (x.i!.stopped && !x.i!.failure) await client.resumeHistory(x.i!.id);
          else await client.retryPilot(x.i!.id);
          ui.toast(t('ra.retrying'));
          reload();
          return;
        case 'delete':
          await del.ask(deleteSel(xs, all), () => onDone?.('delete', xs));
          return;
      }
    } catch (e) {
      fail(e);
    }
  };

  const items = (x: ActionTarget, picked: ActionTarget[] = []): MenuItem[] => {
    const many = picked.length > 1 && picked.some((y) => y.key === x.key);
    const xs = many ? picked : [x];
    const acts = many ? (['archive', 'restore', 'delete'] as RowAction[]).filter((a) => xs.every((y) => rowActions(y).includes(a))) : rowActions(x);
    const siblings = !many && x.kind === 'clip' ? alsoGoes([x], all) + 1 : 1;
    const label = (a: RowAction) =>
      a === 'archive'
        ? siblings > 1
          ? t('ra.archiveProject', { n: siblings })
          : t('ra.archive')
        : a === 'delete'
          ? t('ra.delete')
          : a === 'open-folder'
            ? t('c.reveal')
            : a === 'rename'
              ? t('c.rename')
              : t(`ra.${a}` as 'ra.stop');
    const out: MenuItem[] = [];
    acts.forEach((a) => {
      if (a === 'archive' || a === 'restore') {
        if (out.length) out.push({ label: '', sep: true, run: () => undefined });
      }
      out.push({
        label: many ? `${label(a)} · ${xs.length}` : label(a),
        icon: ICON[a],
        run: () => run(a, xs),
        testId: `row-${a}`,
      });
    });
    return out;
  };

  const modal = (
    <>
      {renaming && (
        <PromptModal
          title={t('ra.renameTitle', { name: renaming.kind === 'clip' ? renaming.title : (renaming.i?.name ?? renaming.title) })}
          placeholder={renaming.kind === 'clip' ? renaming.title : (renaming.i?.name ?? renaming.title)}
          okLabel={t('c.rename')}
          onCancel={() => setRenaming(null)}
          onOk={(v) => {
            const x = renaming;
            setRenaming(null);
            if (!v || !client || !x.i) return;
            const it = x.i;
            // a video row names the video (its title); a project row names the project
            const save = x.kind === 'clip' && x.clip ? (name: string) => client.setClipTitle(it.id, x.clip!, name) : (name: string) => client.renameHistory(it.dir, name);
            const old = x.kind === 'clip' ? x.title : it.name;
            void save(v)
              .then(() => {
                reload();
                ui.toast(t('editor.saved'), { undo: () => void save(old).then(reload) });
              })
              .catch(fail);
          }}
        />
      )}
      {del.modal}
    </>
  );

  return { items, run, archive, modal };
}
