// 「Edit the collection」 in the UI (lib/goals): the new plan cards are not part of the group until she makes them, one
// chip per platform and file in the summary (her "Seattle's Working Waterfront" showed two "YouTube 1920×1080 · 1:20"),
// and the line that says the group is short of what she asked for.
import { beforeAll, describe, expect, it } from 'vitest';
import type { Goal, GoalVideo } from '../../src/shared/goal';
import { setLang } from '../../src/renderer/src/i18n';
import { dedupeFiles, fillLine, goalPct, groupVideos, proposedVideos } from '../../src/renderer/src/lib/goals';
import { platformsFor } from '../../src/renderer/src/v4/GoalView';

const vid = (id: string, x: Partial<GoalVideo> = {}): GoalVideo => ({ id, title: `Video ${id}`, kind: 'film', length_s: 45, clips: 3, stories: ['s1'], platforms: ['youtube', 'xiaohongshu'], request: 'Make it', state: 'made', ...x });
const goal = (videos: GoalVideo[], x: Partial<Goal> = {}): Goal => ({
  id: 'aaaaaaaaaaaa',
  prompt: '做 12 条左右，最少 10 条',
  inputs: ['/Volumes/dji/DCIM'],
  mode: 'ask',
  state: 'done',
  created: 1,
  videos,
  counts: { total: 2, made: 2, dropped: 0, making: 0, you: 0, waiting: 0 },
  ...x,
});

beforeAll(() => setLang('en'));

describe('the new plan cards', () => {
  it('stay out of the group (its rows, its bar) until she makes them', () => {
    const g = goal([vid('v1'), vid('v2'), vid('v3', { state: 'planned', proposed: true, extra: 1 })]);
    expect(groupVideos(g).map((v) => v.id)).toEqual(['v1', 'v2']);
    expect(proposedVideos(g).map((v) => v.id)).toEqual(['v3']);
    expect(goalPct(g)).toBe(1);
  });
});

describe('the summary of a made video', () => {
  it('shows one chip per platform and file', () => {
    const files = [
      { path: '/p/renders/primary.final.mp4', w: 1920, h: 1080, aspect: '16:9', duration: 80.2 },
      { path: '/p/renders/youtube-horizontal.final.mp4', platform: 'youtube', w: 1920, h: 1080, aspect: '16:9', duration: 80.4 },
      { path: '/p/renders/youtube-horizontal.final.mp4', platform: 'youtube', w: 1920, h: 1080, aspect: '16:9', duration: 80.4 },
      { path: '/p/out/xhs.mp4', platform: 'xiaohongshu', w: 1080, h: 1440, aspect: '3:4', duration: 80 },
    ];
    const out = dedupeFiles(files, (f) => platformsFor(f, ['youtube', 'xiaohongshu']));
    expect(out.map((f) => f.path)).toEqual(['/p/renders/youtube-horizontal.final.mp4', '/p/out/xhs.mp4']); // the platform's own
    // another size of one platform is its own version
    const two = dedupeFiles([files[1], { ...files[1], path: '/p/short.mp4', w: 1080, h: 1920, aspect: '9:16', duration: 30 }], (f) => platformsFor(f, ['youtube']));
    expect(two).toHaveLength(2);
    // a file with no platform is told apart by its path
    expect(dedupeFiles([{ path: '/a.mp4' }, { path: '/b.mp4' }], () => [])).toHaveLength(2);
  });
});

describe('the group short of her number', () => {
  it('says how many it has against what she asked for', () => {
    expect(fillLine(goal([], { fill: { target: 12, min: 10, have: 8, need: 4 } }))).toBe('The collection has 8 — you asked for about 12 (at least 10).');
    expect(fillLine(goal([], { fill: { target: 5, have: 3, need: 2 } }))).toBe('The collection has 3 — you asked for 5.');
    expect(fillLine(goal([], { fill: { target: 5, have: 5, need: 0 } }))).toBeNull();
    expect(fillLine(goal([]))).toBeNull();
    setLang('zh-CN');
    expect(fillLine(goal([], { fill: { target: 12, min: 10, have: 8, need: 4 } }))).toBe('合集里有 8 条，你要的是 12 条左右（最少 10 条）。');
    setLang('en');
  });
});
