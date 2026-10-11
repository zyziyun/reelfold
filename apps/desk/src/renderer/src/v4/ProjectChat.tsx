// The project chat beside a project's page (2026-10-11: "why is there no chat while it is being made, or in Details?"):
// the running page, the ready page and Details all have the AI again - one request for the whole project (pause, pick
// the music or the cover again, cut it again) or for every finished clip at once. Resizable with the app's one
// Splitter, folds to a slim rail (saved on this Mac, `project.chat`); "Ask AI about this" on a piece opens it with her
// words started.
import { useEffect, type ReactNode } from 'react';
import { Sparkles } from 'lucide-react';
import type { Clip } from '../../../shared/v04';
import { t } from '../i18n';
import { useBox, usePane } from '../lib/panes';
import { ProjectAIPanel } from './ProjectAIPanel';
import { Splitter } from './Splitter';
import './workpieces.css';

/** the page keeps at least this much width next to the chat */
const MAIN_MIN = 420;

export function WithProjectChat({
  item,
  clips,
  selected = null,
  running = false,
  liveText = null,
  onApplied,
  children,
}: {
  item: string;
  /** the finished clips (what "all" means) */
  clips: Pick<Clip, 'id' | 'title'>[];
  selected?: Pick<Clip, 'id' | 'title'> | null;
  running?: boolean;
  liveText?: string | null;
  onApplied?: () => void;
  children: ReactNode;
}) {
  const [boxRef, box] = useBox<HTMLDivElement>();
  const room = box.w ? box.w - MAIN_MIN : undefined;
  const pane = usePane('project.chat', room);
  // "Ask AI about this" (a piece of the making): open the chat if it is folded; the panel takes the words
  useEffect(() => {
    const on = (e: Event) => {
      const d = (e as CustomEvent<{ item: string }>).detail;
      if (d?.item === item && pane.collapsed) pane.set({ size: pane.size, collapsed: false });
    };
    window.addEventListener('project-chat:prefill', on);
    return () => window.removeEventListener('project-chat:prefill', on);
  }, [item, pane]);
  return (
    <div className={`pchat ${pane.collapsed ? 'folded' : ''}`} ref={boxRef} style={{ ['--pchat' as string]: `${pane.size}px` }} data-testid="project-chat-wrap">
      <div className="pchat-main">{children}</div>
      {pane.collapsed ? (
        <button className="pchat-rail" onClick={pane.toggle} aria-expanded={false} aria-label={t('pc.open')} data-testid="project-chat-open">
          <Sparkles className="ico" />
          {t('pc.open')}
        </button>
      ) : (
        <>
          <Splitter
            orient="col"
            sign={-1}
            state={{ size: pane.size, collapsed: false }}
            spec={pane.spec}
            room={room}
            onChange={pane.set}
            onReset={pane.reset}
            label={t('pc.resize')}
            tip={t('lay.dragTip')}
            testId="project-chat-split"
          />
          <div className="pchat-side">
            <ProjectAIPanel item={item} clips={clips} selected={selected} running={running} liveText={liveText} onApplied={onApplied} onFold={pane.toggle} testId="project-chat" />
          </div>
        </>
      )}
    </div>
  );
}
