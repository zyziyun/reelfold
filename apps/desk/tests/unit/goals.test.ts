// Goal mode in the UI (lib/goals): the group's line and bar, each video's state words and dot, why one was dropped,
// where rows open, and which platforms a made file stands for.
import { beforeAll, describe, expect, it } from 'vitest';
import type { Goal, GoalVideo } from '../../src/shared/goal';
import { setLang } from '../../src/renderer/src/i18n';
import { countNote, dropReason, goalActive, goalHref, goalLine, goalPct, goalTitle, goalTone, groupVideos, requestTitle, surveyLine, versionLabel, versionLine, versionTone, videoHref, videoLine, videoTitle, videoTone } from '../../src/renderer/src/lib/goals';
import { platformsFor } from '../../src/renderer/src/v4/GoalView';
import { filePlatforms, missingTargets } from '../../src/renderer/src/lib/versions';

const vid = (id: string, x: Partial<GoalVideo> = {}): GoalVideo => ({ id, title: `Video ${id}`, kind: 'film', length_s: 45, clips: 3, stories: ['s1'], platforms: ['youtube', 'xiaohongshu', 'bilibili'], request: 'Make it', state: 'waiting', ...x });
const goal = (videos: GoalVideo[], x: Partial<Goal> = {}): Goal => {
  const vs = videos.filter((v) => v.state !== 'skipped');
  return {
    id: 'aaaaaaaaaaaa',
    prompt: 'make several videos from my card',
    inputs: ['/Volumes/dji/DCIM'],
    mode: 'autopilot',
    state: 'running',
    goal: 'As many videos as the footage supports',
    created: 1,
    videos,
    counts: { total: vs.length, made: vs.filter((v) => v.state === 'made').length, dropped: vs.filter((v) => v.state === 'dropped').length, making: vs.filter((v) => v.state === 'planning' || v.state === 'making').length, you: vs.filter((v) => v.state === 'you').length, waiting: vs.filter((v) => v.state === 'waiting').length },
    ...x,
  };
};

beforeAll(() => setLang('en'));

describe('the group', () => {
  it('says how far it is and fills its bar with made, dropped and the share of the ones being made', () => {
    const g = goal([vid('v1', { state: 'made' }), vid('v2', { state: 'making', progress: 0.5 }), vid('v3', { state: 'dropped', reason_code: 'by-you' }), vid('v4', { state: 'waiting' }), vid('v5', { state: 'skipped' })]);
    expect(groupVideos(g).map((v) => v.id)).toEqual(['v1', 'v2', 'v3', 'v4']);
    expect(goalLine(g)).toBe('1 of 4 made · 1 making · 1 dropped');
    expect(goalPct(g)).toBeCloseTo(2.5 / 4);
    expect(goalTone(g)).toBe('run');
    expect(goalActive(g)).toBe(true);
    expect(goalTitle(g)).toBe('As many videos as the footage supports');
    expect(goalTitle({ goal: null, prompt: 'x'.repeat(100) })).toHaveLength(80);
    // the rule planner's stock line follows the UI language, whatever language it was planned in
    const stock = { goal: '用这些素材尽量多做几个视频，每个主题不同', goal_code: 'default' as const, prompt: 'x' };
    expect(goalTitle(stock)).toBe('As many videos as the footage supports, each with its own theme');
    setLang('zh-CN');
    expect(goalTitle(stock)).toBe('用这些素材尽量多做几个视频，每个主题不同');
    setLang('en');
  });

  it('before the videos exist: what the survey reads, then the plan waiting for her', () => {
    expect(goalLine(goal([], { state: 'surveying', progress: { stage: 'probe', i: 3, n: 79, kind: 'video' } }))).toBe('Reading clip 3 of 79…');
    expect(surveyLine({ progress: { stage: 'model' } })).toBe('Asking the AI for video ideas…');
    const planned = goal([vid('v1', { state: 'planned' }), vid('v2', { state: 'planned', planned_out: true })], { state: 'planned' });
    expect(groupVideos(planned)).toHaveLength(1);
    expect(goalLine(planned)).toBe('1 video planned — check it, then make it');
    expect(goalTone(planned)).toBe('you');
    expect(goalTone(goal([vid('v1', { state: 'made' })], { state: 'done' }))).toBe('done');
    expect(goalTone(goal([], { state: 'failed' }))).toBe('error');
    expect(goalActive(goal([], { state: 'done' }))).toBe(false);
  });
});

describe('a video', () => {
  it('says where it is in plain words with its dot', () => {
    expect(videoLine(vid('v1', { state: 'making', progress: 0.42 }))).toBe('Making · 42%');
    expect(videoLine(vid('v1', { state: 'making', queued: true }))).toBe('Waiting for a free slot');
    expect(videoTone(vid('v1', { state: 'making', queued: true }))).toBe('off');
    // a failure the group retries: what happened and what happens next, in plain words
    expect(videoLine(vid('v1', { state: 'planning', retried: 'ai-timeout', attempts: 2 }))).toBe('Planning the edit · The AI didn’t answer in time — trying again (1 of 1)');
    expect(videoLine(vid('v1', { state: 'planning', retried: 'stalled', attempts: 2 }))).toBe('Planning the edit · Planning took too long — trying again (1 of 1)');
    expect(videoLine(vid('v1', { state: 'made' }))).toBe('Made');
    expect(videoTone(vid('v1', { state: 'made' }))).toBe('done');
    expect(videoTone(vid('v1', { state: 'you' }))).toBe('you');
    expect(videoTone(vid('v1', { state: 'dropped' }))).toBe('error');
  });

  it('says why it was dropped: its own words, or the engine failure in hers', () => {
    expect(videoLine(vid('v1', { state: 'dropped', reason_code: 'stalled' }))).toBe('Dropped — it stopped making progress, twice');
    expect(dropReason({ reason_code: 'by-you' })).toBe('you dropped it');
    expect(dropReason({ reason_code: 'plan-empty' })).toBe('its edit couldn’t be planned, twice');
    expect(dropReason({ reason_code: 'ai-timeout' })).not.toMatch(/⟦|ai-timeout/);
  });

  it('opens its project once it has one, else the goal page with it picked', () => {
    expect(videoHref('aaaaaaaaaaaa', vid('v2'))).toBe('#/studio?goal=aaaaaaaaaaaa&v=v2');
    expect(videoHref('aaaaaaaaaaaa', vid('v2', { projects: [{ dir: '/p', item: 'bbbbbbbbbbbb' }] }))).toBe('#/studio/bbbbbbbbbbbb');
    expect(goalHref('aaaaaaaaaaaa')).toBe('#/studio?goal=aaaaaaaaaaaa');
  });

  it('takes its Chinese title in a Chinese UI', () => {
    expect(videoTitle({ title: 'Golden hour', title_zh: '黄金时刻' }, 'zh-CN')).toBe('黄金时刻');
    expect(videoTitle({ title: 'Golden hour', title_zh: '黄金时刻' }, 'en')).toBe('Golden hour');
    expect(videoTitle({ title: 'Golden hour', title_zh: null }, 'zh-CN')).toBe('Golden hour');
  });
});

describe('a made file', () => {
  it('stands for every platform of the video on its canvas', () => {
    expect(platformsFor({ platform: 'youtube', w: 1920, h: 1080, aspect: '16:9' }, ['youtube', 'xiaohongshu:full', 'bilibili'])).toEqual(['youtube', 'bilibili']);
    expect(platformsFor({ platform: 'xiaohongshu', w: 1080, h: 1920, aspect: '9:16' }, ['youtube', 'xiaohongshu:full', 'bilibili'])).toEqual(['xiaohongshu']);
    expect(platformsFor({ w: 1080, h: 1920, aspect: '9:16' }, ['youtube-shorts', 'bilibili'])).toEqual(['youtube-shorts']);
    // a version of its own (the Chinese one): its file is its own platform's only
    expect(platformsFor({ platform: 'bilibili', w: 1920, h: 1080, aspect: '16:9' }, [])).toEqual(['bilibili']);
  });

  it('a photo story names its versions by the platforms the engine says (her DJI goal: "None 原尺寸")', () => {
    expect(platformsFor({ platform: 'xiaohongshu:vertical', platforms: ['xiaohongshu:vertical'], w: 1080, h: 1440, aspect: '3:4' }, [])).toEqual(['xiaohongshu']);
    expect(platformsFor({ platform: 'youtube', platforms: ['youtube', 'bilibili'], w: 1920, h: 1080, aspect: '16:9' }, [])).toEqual(['youtube', 'bilibili']);
    expect(filePlatforms({ platform: 'None:None' })).toEqual([]);
  });

  it('a planned platform with no version is not made', () => {
    const xhs = { platform: 'xiaohongshu:vertical', platforms: ['xiaohongshu:vertical'], w: 1080, h: 1440, aspect: '3:4' as const };
    const bili = { platform: 'bilibili', platforms: ['bilibili'], w: 1920, h: 1080, aspect: '16:9' as const };
    expect(missingTargets(['xiaohongshu', 'bilibili'], [xhs, bili])).toEqual([]);
    expect(missingTargets(['xiaohongshu', 'bilibili'], [xhs])).toEqual(['bilibili']);
    // a vlog's one 16:9 export (YouTube's) also posts to B站: made
    expect(missingTargets(['youtube', 'bilibili'], [{ platform: 'youtube:horizontal', w: 1920, h: 1080, aspect: '16:9' }])).toEqual([]);
    expect(missingTargets(undefined, [xhs])).toEqual([]);
  });
});

describe('one group, one truth (her DJI goal, 2026-10-13)', () => {
  it('a video\'s language versions are inside it, each with the group\'s words', () => {
    expect(versionLabel({ lang: 'en' })).toBe('English');
    expect(versionLabel({ lang: 'zh' })).toBe('中文');
    expect(versionLabel({ lang: null })).toBe('Video');
    expect(versionLine({ state: 'running', queued: true })).toBe('Waiting for a free slot');
    expect(versionLine({ state: 'running', progress: 0.25 })).toBe('Making · 25%');
    expect(versionLine({ state: 'failed' })).toBe('Failed — the group tries it again');
    expect(versionTone({ state: 'made' })).toBe('done');
  });
  it('a goal\'s request row reads as its video, never the raw request', () => {
    const r = { goal_title: 'The Needle After Dark', goal_title_zh: '夜晚的太空针塔', name: null, prompt: 'Title: "The Needle After Dark". Make a 110-second history explainer' };
    expect(requestTitle(r, 'en')).toBe('The Needle After Dark');
    expect(requestTitle(r, 'zh-CN')).toBe('夜晚的太空针塔');
    expect(requestTitle({ name: null, prompt: 'cut my talk' }, 'en')).toBe('cut my talk');
  });
  it('the count she asked for: met, or why it is short', () => {
    expect(countNote({ count: { min: 10, max: 15, asked: 12, planned: 12 } })).toBe('You asked for 10–15: 12 planned.');
    expect(countNote({ count: { min: 10, max: 15, asked: 12, planned: 8, short: true, photo_only: 9, thin: 1 } })).toBe(
      'You asked for at least 10; the footage carries 8. 9 stories are photos only · 1 has too little video',
    );
    expect(countNote({ count: null })).toBeNull();
  });
});
