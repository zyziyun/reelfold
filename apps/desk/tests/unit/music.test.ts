import { describe, expect, it } from 'vitest';
import { byStyle, type MusicTrack } from '../../src/shared/music';

const tr = (id: string, style: string | null): MusicTrack => ({
  id: `lib:${id}`, title: id, artist: null, mood: 'calm', style, tags: [], bpm: null, energy: null, duration: 60, license: 'CC0 1.0',
  origin: null, licence_evidence: null, installed: true, path: null, steady: false, favourite: false, banned: false, uses: 0,
});

describe('Settings › Music grouping', () => {
  it('groups the library by style in the fixed order, titles sorted, unknown styles last', () => {
    const g = byStyle([tr('b', 'piano'), tr('z', 'acoustic'), tr('a', 'piano'), tr('x', 'mystery'), tr('c', 'electronic')]);
    expect(g.map(([s]) => s)).toEqual(['acoustic', 'electronic', 'piano', 'mystery']);
    expect(g[2][1].map((t) => t.title)).toEqual(['a', 'b']);
  });
});
