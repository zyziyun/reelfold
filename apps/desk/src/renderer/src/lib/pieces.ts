// A piece of a project's making in words (the work-in-progress tiles): the recipe's label in her UI language (English
// when the recipe has none in it), numbered when the stage made several ("Graded segment 3"); without a label, the
// step it belongs to and what it is ("Render · Shot 2"). Pure: the tiles and the tests share it.
import type { Piece } from '../../../shared/v04';
import { getLang, t, type MessageKey } from '../i18n';
import { stepOfStage } from './pipeline';

export function pieceLabel(p: Pick<Piece, 'label' | 'n' | 'of' | 'stage' | 'kind'>): string {
  const lang = getLang();
  const own = p.label ? (lang === 'zh-CN' ? p.label.zh : lang === 'fr' ? p.label.fr || p.label.en : p.label.en) : '';
  const step = stepOfStage(p.stage);
  const base = own || [step ? t(`hub.step.${step}` as MessageKey) : null, t(`wp.k.${p.kind}` as MessageKey)].filter(Boolean).join(' · ');
  return p.of > 1 ? t('wp.n', { label: base, n: p.n }) : base;
}
