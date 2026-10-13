// The editor brain's card (v4/BrainPanel): a shot's short line, the one plain alternative per decision, prices,
// the engine's two-language reasons by UI language, and every new string in the three languages.
import { afterEach, describe, expect, it } from 'vitest';
import { setLang } from '../../src/renderer/src/i18n';
import { brainEn, brainFr, brainZh } from '../../src/renderer/src/i18n/locales/brain';
import { alternative, money, said, shotLine } from '../../src/renderer/src/v4/BrainPanel';
import type { BrainShot } from '../../src/shared/v04';

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
});
