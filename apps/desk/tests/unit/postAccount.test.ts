import { describe, expect, it, vi } from 'vitest';
import { postAccount } from '../../src/shared/publish/account';
import { fillScheduledPost, type PostFillDeps } from '../../src/main/publish/postFill';
import { loadAdapters } from '../../src/main/publish/adapters';
import path from 'node:path';

describe('post publishing account', () => {
  it('uses a sole legacy account, but requires a choice among multiple accounts', () => {
    expect(postAccount([])).toBeNull();
    expect(postAccount(['main'])).toBe('main');
    expect(postAccount(['main', 'brand'])).toBeNull();
    expect(postAccount(['main', 'brand'], 'brand')).toBe('brand');
    expect(postAccount(['main'], 'removed')).toBeNull();
  });

  it.each([
    { saved: undefined, requested: undefined, labels: ['main', 'brand'] },
    { saved: undefined, requested: 'removed', labels: ['main'] },
    { saved: 'removed', requested: undefined, labels: ['main'] },
    { saved: 'brand', requested: 'main', labels: ['main', 'brand'] },
  ])('does not open or fill another account: %j', async ({ saved, requested, labels }) => {
    const open = vi.fn();
    const clips = vi.fn();
    const deps = {
      client: { calendar: async () => ({ posts: [{ id: 'aaaaaaaaaaaa', platform: 'xiaohongshu', state: 'planned', account: saved }] }), clips },
      accounts: { xiaohongshu: labels },
      adapters: loadAdapters([path.resolve(__dirname, '../../adapters')]).adapters,
      browser: { open },
    } as unknown as PostFillDeps;
    expect(await fillScheduledPost(deps, { postId: 'aaaaaaaaaaaa', account: requested })).toMatchObject({ ok: false, reason: 'no-account' });
    expect(open).not.toHaveBeenCalled();
    expect(clips).not.toHaveBeenCalled();
  });
});
