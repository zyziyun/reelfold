// The clip page's "On vertical screens" setting (Follow the subject / Fill with blur) reads the vlog's framing of
// that clip: the engine's decision, or her own choice once she changed it.
import { describe, expect, it } from 'vitest';
import { framingOf } from '../../src/renderer/src/v4/ClipInfo';
import type { AutopilotChoice, AutopilotDecision } from '../../src/shared/v04';

const d = (over: Partial<AutopilotDecision>): AutopilotDecision => ({ checkpoint: 'framing', item: 'main', kind: 'reframe-pick', params: { pick: 0, choice: 'follow' }, ...over });
const c = (over: Partial<AutopilotChoice>): AutopilotChoice => ({ checkpoint: 'framing', item: 'main', kind: 'reframe-pick', pick: 1, choice: 'blur', options: ['follow', 'blur'], by: 'her', ...over });

describe('framingOf', () => {
  it('finds the framing decision of the clip (its item, or the item of a version)', () => {
    expect(framingOf({ decisions: [d({})] }, 'main')?.choice).toBe('follow');
    expect(framingOf({ decisions: [d({})] }, 'main/tiktok-vertical')?.checkpoint).toBe('framing');
    expect(framingOf({ decisions: [d({ item: 'other' })] }, 'main')).toBeNull();
    expect(framingOf({ decisions: [d({ kind: 'cover-pick' })] }, 'main')).toBeNull();
    expect(framingOf({ decisions: [d({ asked: true })] }, 'main')).toBeNull(); // taken back: the Inbox asks her
    expect(framingOf(null, 'main')).toBeNull();
  });
  it('her own choice (no longer an autopilot decision) still shows, and wins', () => {
    const f = framingOf({ decisions: [d({})], choices: [c({})] }, 'main');
    expect(f).toEqual({ checkpoint: 'framing', item: 'main', choice: 'blur', options: ['follow', 'blur'] });
    expect(framingOf({ decisions: [], choices: [c({ kind: 'copy-pick' })] }, 'main')).toBeNull();
  });
});
