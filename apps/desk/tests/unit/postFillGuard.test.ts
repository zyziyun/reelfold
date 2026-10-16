import path from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import { fillScheduledPost, type PostFillDeps } from '../../src/main/publish/postFill';
import { loadAdapters } from '../../src/main/publish/adapters';
const adapters = loadAdapters([path.resolve(__dirname, '../../adapters')]).adapters;
function fixture(clip: Record<string, unknown>, selected?: string): PostFillDeps {
  return { adapters, accounts: { xiaohongshu: ['main'] }, browser: { open: vi.fn() }, client: {
    calendar: vi.fn().mockResolvedValue({ posts: [{ id: 'post', item: 'item', clip: 'clip', platform: 'xiaohongshu', account: 'main', state: 'ready', video_path: selected }] }),
    clips: vi.fn().mockResolvedValue({ clips: [{ id: 'clip', ...clip }] }), updatePost: vi.fn(),
  } } as unknown as PostFillDeps;
}
describe('publishing edited clips', () => {
  it.each([undefined, '/previous.final.mp4'])('blocks stale edits even with an available original (selection %s)', async selected => {
    const deps = fixture({ edited_stale: true, files: [{ path: '/original.mp4', aspect: '16:9' }] }, selected);
    expect(await fillScheduledPost(deps, { postId: 'post' })).toMatchObject({ ok: false, reason: 'edit-pending' });
    expect(deps.browser.open).not.toHaveBeenCalled();
    expect(deps.client.updatePost).not.toHaveBeenCalled();
  });
  it('distinguishes an unavailable explicit version from a clip never exported', async () => {
    const deps = fixture({ files: [{ path: '/original.mp4', aspect: '16:9' }] }, '/previous.final.mp4');
    expect(await fillScheduledPost(deps, { postId: 'post' })).toMatchObject({ ok: false, reason: 'version-unavailable' });
    expect(deps.browser.open).not.toHaveBeenCalled();
  });
  it('keeps no-export for a clip without files or selection', async () => {
    expect(await fillScheduledPost(fixture({ files: [] }), { postId: 'post' })).toMatchObject({ ok: false, reason: 'no-file' });
  });
});
