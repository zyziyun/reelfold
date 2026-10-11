// The composer's attached files (lib/attachments): a drone folder's DJI_xxxx_D.MP4 + same-named .SRT (telemetry)
// are one item each; removing one removes both; the summary counts pairs as videos.
import { describe, expect, it } from 'vitest';
import { CHIP_LIMIT, groupAttachments, kindOf, removeItem, summarize } from '../../src/renderer/src/lib/attachments';

const dji = (n: number, ext: string, dir = '/Volumes/DJI/DCIM/100MEDIA') => `${dir}/DJI_${String(n).padStart(4, '0')}_D.${ext}`;

describe('attachments', () => {
  it('pairs a video with its same-named .srt (any case), keeps her order', () => {
    const files = [dji(1, 'MP4'), dji(1, 'SRT'), dji(2, 'mp4'), dji(3, 'MP4'), dji(3, 'srt'), '/x/cover.JPG'];
    const items = groupAttachments(files);
    expect(items.map((i) => i.name)).toEqual(['DJI_0001_D.MP4', 'DJI_0002_D.mp4', 'DJI_0003_D.MP4', 'cover.JPG']);
    expect(items[0]).toMatchObject({ kind: 'video', sidecar: dji(1, 'SRT'), paths: [dji(1, 'MP4'), dji(1, 'SRT')] });
    expect(items[1].sidecar).toBeNull();
    expect(items[3].kind).toBe('photo');
  });

  it('a .srt listed before its video still pairs; one in another folder or with another name stays on its own', () => {
    const files = [dji(5, 'SRT'), dji(5, 'MP4'), dji(6, 'SRT', '/elsewhere'), dji(6, 'MP4'), '/a/notes.srt'];
    const items = groupAttachments(files);
    expect(items.map((i) => [i.name, i.kind, !!i.sidecar])).toEqual([
      ['DJI_0005_D.MP4', 'video', true],
      ['DJI_0006_D.SRT', 'subs', false],
      ['DJI_0006_D.MP4', 'video', false],
      ['notes.srt', 'subs', false],
    ]);
  });

  it('removing a pair removes both paths; other files stay', () => {
    const files = [dji(1, 'MP4'), dji(1, 'SRT'), dji(2, 'MP4'), dji(2, 'SRT')];
    const left = removeItem(files, groupAttachments(files)[0]);
    expect(left).toEqual([dji(2, 'MP4'), dji(2, 'SRT')]);
  });

  it('summarizes a drone card: 50 videos with their .srt, 4 photos, one folder', () => {
    const files: string[] = [];
    for (let i = 1; i <= 50; i++) files.push(dji(i, 'MP4'), dji(i, 'SRT'));
    for (let i = 1; i <= 4; i++) files.push(dji(100 + i, 'JPG'));
    const s = summarize(files);
    expect(s).toMatchObject({ files: 104, items: 54, videos: 50, withSubs: 50, photos: 4, subs: 0, docs: 0, folders: 0, other: 0, dir: '100MEDIA' });
    expect(s.items).toBeGreaterThan(CHIP_LIMIT);
  });

  it('kinds: folders, documents, audio; mixed folders have no common one', () => {
    expect(kindOf('/Users/me/Footage/DJI_2026')).toBe('folder');
    expect(kindOf('/Users/me/Footage/trip/')).toBe('folder');
    expect(kindOf('/a/script.docx')).toBe('doc');
    expect(kindOf('/a/voice.m4a')).toBe('audio');
    expect(kindOf('/a/data.bin')).toBe('other');
    const s = summarize(['/a/x.mp4', '/b/y.pdf', '/b/z']);
    expect(s).toMatchObject({ files: 3, videos: 1, docs: 1, folders: 1, dir: null });
    expect(summarize([]).items).toBe(0);
  });
});
