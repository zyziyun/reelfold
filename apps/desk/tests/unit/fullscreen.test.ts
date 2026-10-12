// System full screen for the players: the window lets the app's own page go full screen (it was denied, so the
// player only grew inside the window), keys go to the player that has the screen, and the Esc that ends it is spent.
import { describe, expect, it } from 'vitest';
import { allowAppPermission } from '../../src/shared/recIpc';
import { ESC_GRACE_MS, escSpent, SETTLE_MS, settleWait, routeKey } from '../../src/renderer/src/lib/fullscreen';
import { FULL_SEEK, seekKey, step, volumeStep } from '../../src/renderer/src/lib/player';

describe('fullscreen permission', () => {
  const base = { flag: false, fromMainWindow: true, isAppUrl: true, permission: 'fullscreen' };
  it("allows the app window's own page, with or without the Create flag", () => {
    expect(allowAppPermission(base)).toBe(true);
    expect(allowAppPermission({ ...base, flag: true })).toBe(true);
  });
  it('refuses other windows and other pages', () => {
    expect(allowAppPermission({ ...base, fromMainWindow: false })).toBe(false);
    expect(allowAppPermission({ ...base, isAppUrl: false })).toBe(false);
  });
  it('keeps everything else as before (media only with the flag; notifications, geolocation never)', () => {
    expect(allowAppPermission({ ...base, permission: 'media', mediaTypes: ['video'] })).toBe(false);
    expect(allowAppPermission({ ...base, permission: 'media', mediaTypes: ['video'], flag: true })).toBe(true);
    expect(allowAppPermission({ ...base, permission: 'notifications', flag: true })).toBe(false);
    expect(allowAppPermission({ ...base, permission: 'geolocation', flag: true })).toBe(false);
  });
});

describe('full-screen keys', () => {
  const key = (k: string) => ({ key: k }) as KeyboardEvent;
  const el = {} as Element;
  it('every key goes to the player that has the screen', () => {
    expect(routeKey(key(' '), el, () => {}, 0, 1000)).toBe('owner');
    expect(routeKey(key('Escape'), el, () => {}, 0, 1000)).toBe('owner');
  });
  it('the Esc that just ended full screen does not also close the page underneath', () => {
    expect(routeKey(key('Escape'), null, undefined, 1000, 1000 + ESC_GRACE_MS - 1)).toBe('spent');
    expect(routeKey(key('Escape'), null, undefined, 1000, 1000 + ESC_GRACE_MS + 1)).toBe('page');
    expect(routeKey(key(' '), null, undefined, 1000, 1001)).toBe('page');
    expect(routeKey(key('Escape'), null, undefined, 0, 10)).toBe('page');
    expect(escSpent(0, 100)).toBe(false);
  });
  it('a request waits for the last full-screen change to settle (macOS animates the Space)', () => {
    expect(settleWait(0, 5)).toBe(0);
    expect(settleWait(1000, 1000)).toBe(SETTLE_MS);
    expect(settleWait(1000, 1000 + SETTLE_MS / 2)).toBe(SETTLE_MS / 2);
    expect(settleWait(1000, 1000 + SETTLE_MS + 1)).toBe(0);
  });
  it('←/→ seek 5 s in full screen (Shift: one frame), frame / second steps in the page', () => {
    expect(seekKey(10, 1, 30, 60, false, true)).toBe(10 + FULL_SEEK);
    expect(seekKey(2, -1, 30, 60, false, true)).toBe(0);
    expect(seekKey(58, 1, 30, 60, false, true)).toBe(60);
    expect(seekKey(10, 1, 30, 60, true, true)).toBe(step(10, 1, 30, 60));
    expect(seekKey(10, 1, 30, 60, false, false)).toBe(step(10, 1, 30, 60));
    expect(seekKey(10, 1, 30, 60, true, false)).toBe(11);
  });
  it('↑/↓ volume in tenths, within 0..1', () => {
    expect(volumeStep(0.5, 1)).toBe(0.6);
    expect(volumeStep(0.95, 1)).toBe(1);
    expect(volumeStep(0.05, -1)).toBe(0);
  });
});
