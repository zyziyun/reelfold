// The clip page's version chips name each version by what it is, never "Edited · Edited · Edited · Original".
import { afterAll, describe, expect, it } from 'vitest';
import { setLang } from '../../src/renderer/src/i18n';
import { editedFiles, targetAspect, transcriptNeedsSource } from '../../src/renderer/src/lib/versions';

afterAll(() => setLang('en'));

const orig = [{ path: '/p/youtube-horizontal.mp4', aspect: '16:9', platform: 'youtube:horizontal' }];
const r = (target: string, quality = 'final', fresh = true) => ({ target, quality, file: `/r/${target}.${quality}.mp4`, fresh, key: 3 });

describe('version chips', () => {
  it('an export target has its shape', () => {
    expect(['9:16', 'xiaohongshu:vertical', 'tiktok:vertical', 'youtube:horizontal', 'youtube:vertical', 'weird'].map(targetAspect)).toEqual(['9:16', '3:4', '9:16', '16:9', '9:16', null]);
  });

  it('each fresh render once (the final over the preview), by shape and platform, then the original', () => {
    setLang('en');
    const fs = editedFiles([r('primary', 'preview'), r('primary'), r('youtube:vertical'), r('xiaohongshu:vertical'), r('tiktok:vertical', 'final', false)], orig);
    expect(fs.map((f) => f.label)).toEqual(['16:9 · edited', '9:16 YouTube Shorts · edited', '3:4 Xiaohongshu · edited', 'Original']);
    expect(fs[0]).toMatchObject({ path: '/r/primary.final.mp4', aspect: '16:9', v: 3 });
    expect(new Set(fs.map((f) => f.label)).size).toBe(fs.length);
  });

  it('several originals say their shape; other languages too', () => {
    setLang('zh-CN');
    const fs = editedFiles([r('primary')], [...orig, { path: '/p/tiktok-vertical.mp4', aspect: '9:16', platform: 'tiktok:vertical' }]);
    expect(fs.map((f) => f.label)).toEqual(['16:9 · 改后', '原片 16:9', '原片 9:16']);
  });
});


describe('rendered sound in the transcript player', () => {
  const doc = { duration: 50, cuts: [], trim: null, speed: 1 };

  it('plays the fresh narration render after comparison closes and on reopening', () => {
    expect(transcriptNeedsSource(doc)).toBe(false);
    expect(transcriptNeedsSource({ ...doc, trim: { start: 0, end: 50 } })).toBe(false);
  });

  it('keeps original timestamps for text cuts, trim, speed and recorded pickups', () => {
    expect(transcriptNeedsSource({ ...doc, cuts: [{ start: 2, end: 3, index: 0 }] })).toBe(true);
    expect(transcriptNeedsSource({ ...doc, trim: { start: 1, end: 50 } })).toBe(true);
    expect(transcriptNeedsSource({ ...doc, trim: { start: 0, end: 49 } })).toBe(true);
    expect(transcriptNeedsSource({ ...doc, speed: 1.05 })).toBe(true);
    expect(transcriptNeedsSource({ ...doc, pickups: [{ id: 'take', start: 1, end: 2, text: 'new line', replaced: 'old line' }] })).toBe(true);
  });
});
