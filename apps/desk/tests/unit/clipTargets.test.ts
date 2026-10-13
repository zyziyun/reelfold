// A goal video's language cut is made for its own platforms (her DJI goal, 2026-10-13: the English cut of "Seattle's
// Working Waterfront" offered TikTok and 小红书 and was about to be scheduled there): the schedule turns on only the
// clip's platforms, and the versions it offers are their shapes.
import { describe, expect, it } from 'vitest';
import { channelOf, versionsFor } from '../../src/renderer/src/v4/ClipInfo';

describe('a clip made for some platforms', () => {
  it('offers the shapes of those platforms only', () => {
    expect(versionsFor(['youtube'])).toEqual(['16:9']);
    expect(versionsFor(['xiaohongshu:vertical', 'bilibili'])).toEqual(['9:16', '16:9', '3:4']);
    expect(versionsFor(['youtube-shorts', 'youtube'])).toEqual(['9:16', '16:9']);
    expect(versionsFor([])).toEqual(['9:16', '16:9', '3:4']); // not known: every shape
    expect(versionsFor(['somewhere-new'])).toEqual(['9:16', '16:9', '3:4']);
  });
  it('posts through the platform\'s own account', () => {
    expect(channelOf('youtube-shorts:vertical')).toBe('youtube');
    expect(channelOf('xiaohongshu:vertical')).toBe('xiaohongshu');
  });
});
