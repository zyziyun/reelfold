import { expect, it, vi } from 'vitest';
import { TikTokTransport, tikTokChunks } from '../../src/main/publish/api/tiktok';
import { UploadOutcomeUnknown } from '../../src/main/publish/outcome';
const ok = (data: unknown) => new Response(JSON.stringify({ error: { code: 'ok' }, data }));
const session = { publish_id: 'v_inbox_file~123', upload_url: 'https://open-upload.tiktokapis.com/video/?upload_token=secret' };
it('merges trailing bytes and rejects invalid file sizes', () => {
  expect(tikTokChunks(50_000_123)).toEqual({ size: 50_000_123, chunkSize: 10_000_000, chunks: 5 });
  expect(tikTokChunks(123).chunkSize).toBe(123);
  for (const n of [0, -1, NaN, Infinity, 1.5, 4 * 1024 ** 3 + 1]) expect(() => tikTokChunks(n)).toThrow();
});
it('transfers exact ranges without sending bearer credentials to the upload URL', async () => {
  const f = vi.fn<typeof fetch>().mockResolvedValueOnce(ok(session)).mockResolvedValueOnce(new Response(null, { status: 206 })).mockResolvedValueOnce(new Response(null, { status: 201 }));
  const api = new TikTokTransport(async () => 'token', f);
  const upload = await api.initInbox(20_000_123);
  expect(JSON.parse(String(f.mock.calls[0][1]?.body))).toEqual({ source_info: { source: 'FILE_UPLOAD', video_size: 20_000_123, chunk_size: 10_000_000, total_chunk_count: 2 } });
  await api.putChunk(upload, 0, new Uint8Array(10_000_000));
  await api.putChunk(upload, 1, new Uint8Array(10_000_123));
  expect(f.mock.calls[2][1]?.headers).toEqual({ 'Content-Type': 'video/mp4', 'Content-Length': '10000123', 'Content-Range': 'bytes 10000000-20000122/20000123' });
  expect(f.mock.calls[2][1]?.redirect).toBe('error');
  await expect(api.putChunk(upload, 1, new Uint8Array(1))).rejects.toThrow('wrong size');
  expect(f).toHaveBeenCalledTimes(3);
});
it.each([['SEND_TO_USER_INBOX', 'draft'], ['PUBLISH_COMPLETE', 'posted'], ['FAILED', 'failed'], ['PROCESSING_UPLOAD', 'processing'], ['PROCESSING_DOWNLOAD', 'processing'], ['NEW_STATUS', 'unknown']])('maps %s to %s', async (status, expected) => {
  const api = new TikTokTransport(async () => 'token', vi.fn<typeof fetch>().mockResolvedValue(ok({ status })));
  expect((await api.getStatus('id')).state).toBe(expected);
});
it('preserves string int64 IDs and refuses rounded numeric IDs', async () => {
  const f = vi.fn<typeof fetch>().mockResolvedValueOnce(ok({ status: 'PUBLISH_COMPLETE', publicaly_available_post_id: ['7412345678901234567'] })).mockResolvedValueOnce(ok({ status: 'PUBLISH_COMPLETE', publicaly_available_post_id: [Number('7412345678901234567')] }));
  const api = new TikTokTransport(async () => 'token', f);
  expect((await api.getStatus('id')).postIds).toEqual(['7412345678901234567']);
  await expect(api.getStatus('id')).rejects.toThrow('Invalid TikTok status');
});
it.each([new Response('bad'), new Response('{}', { status: 503 }), ok({}), ok({ ...session, upload_url: 'https://tiktokapis.com.attacker.test/video/' })])('never retries ambiguous initialization', async (response) => {
  const f = vi.fn<typeof fetch>().mockResolvedValue(response);
  await expect(new TikTokTransport(async () => 'token', f).initInbox(3)).rejects.toBeInstanceOf(UploadOutcomeUnknown);
  expect(f).toHaveBeenCalledTimes(1);
});
it('does not replay a chunk after losing its acknowledgement', async () => {
  const f = vi.fn<typeof fetch>().mockResolvedValueOnce(ok(session)).mockRejectedValueOnce(new Error('secret URL'));
  const api = new TikTokTransport(async () => 'token', f);
  await expect(api.putChunk(await api.initInbox(3), 0, new Uint8Array(3))).rejects.toThrow('progress must be checked');
  expect(f).toHaveBeenCalledTimes(2);
});
it('omits arbitrary server error text', async () => {
  const f = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({ error: { code: 'scope_not_authorized', message: 'secret' } }), { status: 401 }));
  await expect(new TikTokTransport(async () => 'token', f).initInbox(3)).rejects.toThrow('TikTok request failed: scope_not_authorized (HTTP 401)');
});
it('does not send already-cancelled requests', async () => {
  const f = vi.fn<typeof fetch>();
  await expect(new TikTokTransport(async () => 'token', f).initInbox(3, AbortSignal.abort())).rejects.toThrow();
  expect(f).not.toHaveBeenCalled();
});
