// Delete (engine/desk_engine/purge.py): the plan's words for the dialog - which things go, which are refused, sizes,
// short paths. Pure: unit-tested.
import type { DeletePlan, DeletePlanItem } from '../../../shared/v04';
import { getLang, t } from '../i18n';

export function okItems(p: DeletePlan): DeletePlanItem[] {
  return p.items.filter((x) => x.ok);
}

export function refusedItems(p: DeletePlan): DeletePlanItem[] {
  return p.items.filter((x) => !x.ok);
}

/** 1.2 GB / 35 MB / 0.4 MB / 12 KB (a comma in French). */
export function fmtSize(n: number, lang = getLang()): string {
  const v = n >= 1e9 ? `${(n / 1e9).toFixed(1)} GB` : n >= 1e7 ? `${Math.round(n / 1e6)} MB` : n >= 1e5 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(0, Math.round(n / 1e3))} KB`;
  return lang === 'fr' ? v.replace('.', ',') : v;
}

export function deleteTitle(ok: DeletePlanItem[]): string {
  return ok.length === 1 ? t('del.titleOne', { name: ok[0].name }) : t('del.titleMany', { n: ok.length });
}
