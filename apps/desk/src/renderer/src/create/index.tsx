// The Create page module: one import site in App.tsx (its screens; its landing is Home's Start from row, the Home nav
// item is lit on every #/create page), one in Settings.tsx (Labs card) and v4/HomeCreate (Home's starts + series).
// Everything else (routes, api, screens, copy, css) lives under create/.
import './create.css';
import type { SettingsMsg } from '../../../shared/deskApi';
import { LearningCreate } from './LearningCreate';
import { CreatePlan } from './CreatePlan';
import { EpisodeScreen } from './episode/EpisodeScreen';
import { RecordStudio } from './record/RecordStudio';
import { parseCreate } from './routes';
import { SeriesScreen } from './series/SeriesScreen';
import { VideoGenSection } from './settings/VideoGenSection';

export { setCreatePrefs, useCreateEnabled, createEnabled } from './flag';
export { CreateSettingsCard } from './settings/VideoGenSection';

/** #/create (or a path it does not know): Create has no landing of its own - Home shows its starts. */
export function isCreateLanding(path: string[]): boolean {
  return parseCreate(path).screen === 'home';
}

export function CreateScreen({ path, onSettings }: { path: string[]; onSettings?: (s: SettingsMsg) => void }) {
  const r = parseCreate(path);
  switch (r.screen) {
    case 'learning':
      return <div className="scroll"><LearningCreate /></div>;
    case 'series':
      return (
        <div className="scroll">
          <SeriesScreen key={r.sid} sid={r.sid} tab={r.tab} />
        </div>
      );
    case 'episode':
      return (
        <div className="scroll">
          <EpisodeScreen key={r.eid} eid={r.eid} tab={r.tab} />
        </div>
      );
    case 'record':
      return <RecordStudio key={`${r.eid ?? ''}${r.shot ?? ''}${r.sid ?? ''}`} sid={r.sid} eid={r.eid} shot={r.shot} />;
    case 'settings':
      return (
        <div className="scroll">
          <VideoGenSection onSettings={onSettings} />
        </div>
      );
    case 'new':
      return (
        <div className="scroll">
          <CreatePlan key={r.format ?? ''} format={r.format} />
        </div>
      );
    default:
      return null; // the landing is Home (App renders it for isCreateLanding)
  }
}
