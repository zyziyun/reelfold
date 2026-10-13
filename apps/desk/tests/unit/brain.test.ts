// The editor brain's card (v4/BrainPanel): a shot's short line, the one plain alternative per decision, prices,
// the engine's two-language reasons by UI language, and every new string in the three languages.
import { afterEach, describe, expect, it } from 'vitest';
import { setLang } from '../../src/renderer/src/i18n';
import { brainEn, brainFr, brainZh } from '../../src/renderer/src/i18n/locales/brain';
import { alternative, genView, money, said, shotLine } from '../../src/renderer/src/v4/BrainPanel';
import { gateText } from '../../src/renderer/src/v4/BrainGate';
import { laneLabel, laneTitle } from '../../src/renderer/src/v4/ShotLane';
import type { BrainProposal, BrainShot, ClipShot } from '../../src/shared/v04';

const shot = (x: Partial<BrainShot> = {}): BrainShot => ({
  id: 'C2.S1',
  clip: '/x/a.mp4',
  start: 0,
  end: 12,
  skip: false,
  hold_s: 9.6,
  speed: 'normal',
  transition: { kind: 'dissolve', s: 0.8 },
  why: [],
  by: 'rules',
  choices: { transition: [['dissolve', 0.95], ['cut', 0.55]], speed: [['normal', 0.6]] },
  ...x,
});

afterEach(() => setLang('en'));

describe('brain card', () => {
  it('says how a shot joins, holds and plays', () => {
    expect(shotLine(shot())).toBe('dissolve · 10 s');
    expect(shotLine(shot({ speed: 'slowmo', transition: { kind: 'cut', s: 0 } }))).toBe('cut · 10 s · slow-mo');
    expect(shotLine(shot({ skip: true }))).toBe('left out');
    setLang('zh-CN');
    expect(shotLine(shot())).toBe('叠化 · 10 秒');
  });

  it('offers the runner-up as the one alternative, never the bookkeeping kinds', () => {
    expect(alternative(shot(), 'transition')).toBe('cut');
    expect(alternative(shot(), 'speed')).toBeNull();
    expect(alternative(shot({ choices: { transition: [['continuous', 0.95]] } }), 'transition')).toBeNull();
  });

  it('prices and reasons', () => {
    expect(money(5)).toBe('≈ ¥5.0');
    expect(money(42.4)).toBe('≈ ¥42');
    expect(money(null)).toBe('price unknown');
    const r = { en: 'the light changes', zh: '光线变了' };
    expect(said(r)).toBe('the light changes');
    setLang('zh-CN');
    expect(said(r)).toBe('光线变了');
    setLang('fr');
    expect(said(r)).toBe('the light changes');
  });

  it('has every string in the three languages', () => {
    for (const loc of [brainZh, brainFr]) expect(Object.keys(loc).sort()).toEqual(Object.keys(brainEn).sort());
    for (const v of [...Object.values(brainZh), ...Object.values(brainFr)]) expect(v.trim()).not.toBe('');
  });

  it('says where a generated idea is: an idea, being made, in the edit, kept, failed, maybe charged', () => {
    const p = (status: BrainProposal['status']): BrainProposal => ({
      id: 'g1234abcd',
      kind: 'establishing',
      title: { en: 'An establishing shot to open', zh: '开场的全景镜头' },
      why: { en: 'x', zh: 'x' },
      mode: 'text-to-video',
      prompt: '',
      seconds: 5,
      provider: 'kling-mcp',
      model: 'kling-video-v3_0_omni',
      estimate: { cny: 3.7 },
      status,
      code: 'abcdef',
    });
    expect(genView(p('proposed'))).toBe('idea');
    expect(genView(p('approved'))).toBe('idea');
    expect(genView(p('proposed'), { g1234abcd: { state: 'generating' } })).toBe('generating');
    expect(genView(p('proposed'), { g1234abcd: { state: 'failed', code: 'create.provider-not-ready' } })).toBe('failed');
    expect(genView(p('placed'))).toBe('placed');
    expect(genView(p('generated'))).toBe('kept');
    expect(genView(p('unknown-charge'))).toBe('unknown');
    expect(genView(p('skipped'))).toBe('skipped');
  });

  it('names the service in a gate refusal', () => {
    expect(gateText({ code: 'create.provider-not-ready', params: { provider: 'kling-mcp' } })).toBe('Kling is not connected.');
    expect(gateText({ code: 'create.over-cap', params: { used: 290, cap: 300, need: 12 } })).toContain('300');
  });

  it('labels a shot on the clip timeline', () => {
    const s = (x: Partial<ClipShot>): ClipShot => ({ i: 0, t0: 0, t1: 8, brain: null, gen: null, ...x });
    expect(laneLabel(s({ brain: { id: 'C2.S1', transition: { kind: 'dissolve', s: 0.8 }, speed: 'normal' } }))).toBe('dissolve · 8 s');
    expect(laneTitle(s({ brain: { id: 'C2.S1', transition: { kind: 'cut', s: 0 }, speed: 'slowmo' }, file: 'a.mp4', src_in: 2, src_out: 6 }))).toBe('C2.S1 · cut · 8 s · slow-mo · a.mp4 2.0–6.0 s');
    expect(laneLabel(s({ gen: { id: 'g1', kind: 'establishing', title: { en: 'An opening', zh: '开场' }, why: { en: '', zh: '' }, status: 'placed' } }))).toBe('AI · An opening');
    expect(laneLabel(s({ role: 'hook' }))).toBe('hook');
    expect(laneLabel(s({ file: 'a.mp4' }))).toBe('a.mp4');
  });
});
