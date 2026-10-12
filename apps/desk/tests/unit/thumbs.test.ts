// The making's tiles: a video's still comes from well inside it (a graded segment fades in from black), and a file
// written again in place gets a new URL (its version), so a tile never keeps a black / broken first look.
import { describe, expect, it, vi } from 'vitest';

vi.stubGlobal('window', { desk: { mediaUrl: (p: string) => `vsmedia://f${p}` } });
const { media, posterAt } = await import('../../src/renderer/src/v4/kit');

describe('thumbs', () => {
  it('take a video’s still inside it, never its first frame', () => {
    expect(posterAt(6.67)).toBeCloseTo(2.668, 2);
    expect(posterAt(40)).toBe(3);
    expect(posterAt(0.5)).toBeCloseTo(0.2, 5);
    expect(posterAt(0)).toBe(0);
    expect(posterAt(Number.NaN)).toBe(0);
  });
  it('carry the file’s version in the URL', () => {
    expect(media('/p/work/sheets/a_sheet.jpg', 1791770208.09)).toBe('vsmedia://f/p/work/sheets/a_sheet.jpg?v=1791770208.09');
    expect(media('/p/renders/primary.final.cover.jpg', 'k1')).not.toBe(media('/p/renders/primary.final.cover.jpg', 'k2'));
  });
});
