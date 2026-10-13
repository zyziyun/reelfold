import { describe, expect, it } from 'vitest';
import { fmtDuration, parseSecs, typicalRange } from '../../src/shared/platformLengths';
import { en } from '../../src/renderer/src/i18n/locales/en';
import { zhCN } from '../../src/renderer/src/i18n/locales/zh-CN';
import { fr } from '../../src/renderer/src/i18n/locales/fr';

describe('platform lengths', () => {
  it('formats lengths the way the engine does', () => {
    expect(fmtDuration(90)).toBe('90 s');
    expect(fmtDuration(240)).toBe('4 min');
    expect(fmtDuration(330, 'zh-CN')).toBe('5.5 分钟');
    expect(fmtDuration(45, 'zh-CN')).toBe('45 秒');
  });
  it('reads a typed length only inside its range', () => {
    expect(parseSecs('60', 10, 180)).toBe(60);
    expect(parseSecs(' 62.4 ', 10, 180)).toBe(62);
    expect(parseSecs('', 10, 180)).toBeNull();
    expect(parseSecs('600', 10, 180)).toBeNull();
    expect(parseSecs('abc', 10, 180)).toBeNull();
  });
  it('the typical range spans every kind', () => {
    const b = (min: number, max: number) => ({ min, target: min, max, form: 'short' as const, chapters: false });
    expect(typicalRange({ lengths: { film: b(30, 120), reel: b(20, 60) } as never })).toEqual([20, 120]);
  });
  it('the plan card and Settings speak en / zh / fr', () => {
    for (const k of ['goal.lengths', 'goal.possible', 'goal.cutLong', 'pls.title', 'pls.lead'] as const) {
      expect(en[k]).toBeTruthy();
      expect(zhCN[k]).toBeTruthy();
      expect(fr[k]).toBeTruthy();
    }
    expect(zhCN['goal.possible']).toContain('{len}');
  });
});
