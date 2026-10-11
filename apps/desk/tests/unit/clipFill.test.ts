// The clip page's "On vertical screens" setting (Follow the subject / Fill with blur) reads the vlog's framing of
// that clip: the engine's decision, or her own choice once she changed it.
import { describe, expect, it } from 'vitest';
import { copyOf, framingOf } from '../../src/renderer/src/v4/ClipInfo';
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

describe('a vlog made before the framing / copy steps', () => {
  it('shows the framing its exports have (by: before) and offers to write the post copy', () => {
    const old = { decisions: [], choices: [c({ by: 'before' }), c({ checkpoint: 'copy', kind: 'copy-pick', pick: null, choice: null, options: ['ai', 'rules'], by: 'before' })] };
    expect(framingOf(old, 'seattle-fall-foliage/youtube-horizontal')).toBeNull(); // another item
    const clip = 'main/youtube-horizontal';
    expect(framingOf(old, clip)).toEqual({ checkpoint: 'framing', item: 'main', choice: 'blur', options: ['follow', 'blur'] });
    expect(copyOf(old, clip)).toEqual({ checkpoint: 'copy', item: 'main', choice: null });
    expect(copyOf({ choices: [c({})] }, clip)).toBeNull(); // no copy step: no Rewrite button
    expect(copyOf(null, clip)).toBeNull();
  });
});
