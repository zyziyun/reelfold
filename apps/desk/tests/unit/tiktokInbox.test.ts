import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, expect, it, vi } from 'vitest';
import { ApiVault } from '../../src/main/publish/api/vault';
import { TikTokTransport } from '../../src/main/publish/api/tiktok';
import { TikTokInbox } from '../../src/main/publish/api/tiktokInbox';
const dirs: string[] = [];
afterEach(() => { for (const dir of dirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true }); });
const crypto = { isEncryptionAvailable: () => true, encryptString: (s: string) => Buffer.from(Buffer.from(s).map(b => b ^ 77)), decryptString: (b: Buffer) => Buffer.from(b).map(x => x ^ 77).toString() };
const ok = (data: unknown) => new Response(JSON.stringify({ error: { code: 'ok' }, data }));
function setup() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'tiktok-inbox-')); dirs.push(dir);
  const file = path.join(dir, 'clip.mp4'); fs.writeFileSync(file, Buffer.from([1, 2, 3]));
  const f = vi.fn<typeof fetch>();
  const vault = new ApiVault(dir, crypto);
  const make = () => new TikTokInbox(new ApiVault(dir, crypto), () => new TikTokTransport(async () => 'access-token', f));
  return { dir, file, f, vault, make };
}
it('recovers a lost final acknowledgement after restart without uploading twice', async () => {
  const { dir, file, f, make } = setup();
  f.mockResolvedValueOnce(ok({ publish_id: 'id', upload_url: 'https://open-upload.tiktokapis.com/video/?upload_token=secret' })).mockRejectedValueOnce(new Error('connection lost'));
  await expect(make().upload('post', 'account', file)).rejects.toThrow('progress must be checked');
  const raw = fs.readFileSync(path.join(dir, 'publish-api.json'), 'utf8');
  expect(raw).not.toContain('upload_token'); expect(raw).not.toContain(file);
  fs.unlinkSync(file);
  f.mockResolvedValueOnce(ok({ status: 'SEND_TO_USER_INBOX' }));
  expect((await make().upload('post', 'account', file)).state).toBe('draft');
  expect(f.mock.calls.map(c => c[1]?.method)).toEqual(['POST', 'PUT', 'POST']);
});
it('persists initialization intent before a lost response and prohibits replay', async () => {
  const { file, f, make, vault } = setup();
  f.mockImplementationOnce(async () => {
    expect(vault.get('tiktok-upload/post', true).tiktokAttempt?.sha256).toHaveLength(64);
    throw new Error('lost');
  });
  await expect(make().upload('post', 'account', file)).rejects.toThrow('initialization could not be confirmed');
  await expect(make().upload('post', 'account', file)).rejects.toThrow('initialization is unconfirmed');
  expect(f).toHaveBeenCalledTimes(1);
});
it('refuses resume with changed file bytes or account', async () => {
  const { file, f, make } = setup();
  f.mockResolvedValueOnce(ok({ publish_id: 'id', upload_url: 'https://open-upload.tiktokapis.com/video/' })).mockRejectedValueOnce(new Error('lost'));
  await expect(make().upload('post', 'account', file)).rejects.toThrow();
  await expect(make().upload('post', 'other', file)).rejects.toThrow('another account');
  fs.writeFileSync(file, Buffer.from([3, 2, 1]));
  f.mockResolvedValueOnce(ok({ status: 'PROCESSING_UPLOAD', uploaded_bytes: 0 }));
  await expect(make().upload('post', 'account', file)).rejects.toThrow('file has changed');
  expect(f).toHaveBeenCalledTimes(3);
});
it('does not infer zero bytes from absent remote progress', async () => {
  const { file, f, make } = setup();
  f.mockResolvedValueOnce(ok({ publish_id: 'id', upload_url: 'https://open-upload.tiktokapis.com/video/' })).mockRejectedValueOnce(new Error('lost'));
  await expect(make().upload('post', 'account', file)).rejects.toThrow();
  f.mockResolvedValueOnce(ok({ status: 'PROCESSING_UPLOAD' }));
  await expect(make().upload('post', 'account', file)).rejects.toThrow('chunk boundary');
  expect(f).toHaveBeenCalledTimes(3);
});
it('does not start a remote upload if encrypted persistence is unavailable', async () => {
  const { dir, file, f } = setup();
  const vault = new ApiVault(dir, { ...crypto, isEncryptionAvailable: () => false });
  const inbox = new TikTokInbox(vault, () => new TikTokTransport(async () => 'token', f));
  await expect(inbox.upload('post', 'account', file)).rejects.toThrow('keychain');
  expect(f).not.toHaveBeenCalled();
});
it('resumes only the remaining chunk at a confirmed remote boundary', async () => {
  const { file, f, make } = setup();
  fs.writeFileSync(file, Buffer.alloc(20_000_123, 7));
  f.mockResolvedValueOnce(ok({ publish_id: 'id', upload_url: 'https://open-upload.tiktokapis.com/video/' }))
    .mockResolvedValueOnce(new Response(null, { status: 206 })).mockRejectedValueOnce(new Error('lost'));
  await expect(make().upload('post', 'account', file)).rejects.toThrow();
  f.mockResolvedValueOnce(ok({ status: 'PROCESSING_UPLOAD', uploaded_bytes: 10_000_000 }))
    .mockResolvedValueOnce(new Response(null, { status: 201 }))
    .mockResolvedValueOnce(ok({ status: 'SEND_TO_USER_INBOX' }));
  expect((await make().upload('post', 'account', file)).state).toBe('draft');
  expect((f.mock.calls[4][1]?.headers as Record<string, string>)['Content-Range']).toBe('bytes 10000000-20000122/20000123');
  expect(f.mock.calls.filter(c => String(c[0]).endsWith('inbox/video/init/'))).toHaveLength(1);
});
