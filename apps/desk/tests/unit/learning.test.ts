import { describe, expect, it } from 'vitest';
import { youtubeSource, youtubeTime } from '../../src/renderer/src/create/learning/source';
import { youtubeEmbedIdentity, buildCsp } from '../../src/main/security';
import { createHref, parseCreate } from '../../src/renderer/src/create/routes';

describe('a human creation workspace', () => {
  it('has its own creation route without altering existing recording or series routes', () => {
    expect(parseCreate(['learning'])).toEqual({ screen: 'learning' });
    expect(createHref({ screen: 'learning' })).toBe('#/create/learning');
    expect(parseCreate(['record'])).toEqual({ screen: 'record' });
    expect(parseCreate(['s', 'my-series'])).toEqual({ screen: 'series', sid: 'my-series', tab: 'bible' });
  });
  it('keeps a YouTube source timestamp and uses the official privacy-enhanced player', () => {
    const source = youtubeSource('https://www.youtube.com/watch?v=6WaeGfLnRvc&t=3198s');
    expect(source?.id).toBe('6WaeGfLnRvc');
    expect(source?.start).toBe(3198);
    expect(new URL(source!.embed).hostname).toBe('www.youtube-nocookie.com');
    expect(youtubeSource('https://youtu.be/6WaeGfLnRvc?t=1h2m3s')?.start).toBe(3723);
    for (const u of ['https://youtube.com.evil.test/watch?v=6WaeGfLnRvc', 'javascript:alert(1)', 'http://youtube.com/watch?v=6WaeGfLnRvc', 'https://www.youtube.com/watch?v=wrong']) expect(youtubeSource(u)).toBeNull();
  });
  it('rejects malformed time messages instead of treating them as current source time', () => {
    expect(youtubeTime('{')).toBeNull();
    expect(youtubeTime({ event: 'infoDelivery', info: { currentTime: -4 } })).toBeNull();
    expect(youtubeTime({ event: 'command', info: { currentTime: 12 } })).toBeNull();
    expect(youtubeTime(JSON.stringify({ event: 'infoDelivery', info: { currentTime: 53.2 } }))).toBe(53.2);
  });
  it('identifies only embedded player subframes, keeping remote code out of the app UI', () => {
    expect(youtubeEmbedIdentity('https://www.youtube-nocookie.com/embed/6WaeGfLnRvc', 'subFrame')).toBe('https://app.reelfold.desk/');
    expect(youtubeEmbedIdentity('https://www.youtube-nocookie.com/embed/6WaeGfLnRvc', 'mainFrame')).toBeNull();
    expect(youtubeEmbedIdentity('https://www.youtube-nocookie.com.evil.test/embed/6WaeGfLnRvc', 'subFrame')).toBeNull();
    expect(buildCsp({ dev: false, create: true })).toContain('frame-src https://www.youtube-nocookie.com;');
    expect(buildCsp({ dev: false, create: true })).toContain("script-src 'self';");
    expect(buildCsp({ dev: false })).toContain("frame-src 'none';");
  });
});
