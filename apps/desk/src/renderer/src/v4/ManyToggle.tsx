import { Layers } from 'lucide-react';
import { t } from '../i18n';
import './goal.css';

/** 「Several videos」 on the composer: the request is a goal (a survey of the footage, then a group of videos). Off: the
 * engine still recognises a goal-style request by its words (several videos from a folder). */
export function ManyToggle({ on, onChange, compact = false }: { on: boolean; onChange: (v: boolean) => void; compact?: boolean }) {
  return (
    <button className={`btn ghost sm ux-many ${on ? 'on' : ''}`} aria-pressed={on} onClick={() => onChange(!on)} data-tip={t('goal.toggleTip')} data-testid="composer-many">
      <Layers className="ico" />
      {compact ? null : t('goal.toggle')}
    </button>
  );
}
