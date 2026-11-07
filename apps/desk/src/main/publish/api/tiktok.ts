// TikTok Content Posting API transport. Not enabled in API_PLATFORMS until
// Login Kit, durable upload recovery and the consent UI are wired and verified.
// https://developers.tiktok.com/docs/en/content-posting-api-media-transfer-guide
import { z } from 'zod';
import { UploadOutcomeUnknown } from '../outcome';

const API = 'https://open.tiktokapis.com/v2/post/publish/';
const id = z.string().min(1).max(64);
const envelope = z.object({ error: z.object({ code: z.string() }), data: z.unknown().optional() });
const initialized = z.object({ publish_id: id, upload_url: z.string().url() });
const status = z.object({
  status: z.string().min(1),
  fail_reason: z.string().optional(),
  // API spelling is intentional. Numeric int64 IDs cannot safely pass through JS numbers.
  publicaly_available_post_id: z.array(z.union([z.string().regex(/^\d+$/), z.number().int().nonnegative().refine(Number.isSafeInteger)]).transform(String)).optional(),
  uploaded_bytes: z.number().int().nonnegative().refine(Number.isSafeInteger).optional(),
});

export interface TikTokUpload {
  provider: 'tiktok';
  publishId: string;
  /** Signed credential: persist encrypted in main only, never expose to renderer/logs. */
  uploadUrl: string;
  size: number;
  chunkSize: number;
  chunks: number;
}

/** TikTok appends the remainder to the LAST chunk (floor, not ceil). */
export function tikTokChunks(size: number) {
  if (!Number.isSafeInteger(size) || size <= 0 || size > 4 * 1024 ** 3) throw new Error('Invalid TikTok video size');
  const chunkSize = Math.min(size, 10_000_000);
  return { size, chunkSize, chunks: Math.max(1, Math.floor(size / chunkSize)) };
}

function uploadUrl(raw: string) {
  const u = new URL(raw);
  if (u.protocol !== 'https:' || !u.hostname.endsWith('.tiktokapis.com') || u.username || u.password || u.hash || (u.port && u.port !== '443')) {
    throw new Error('Invalid TikTok upload destination');
  }
  return u.href;
}

/** Token acquisition/refresh belongs to Login Kit's confidential service, not this transport. */
export class TikTokTransport {
  constructor(private token: () => Promise<string>, private fetcher: typeof fetch = fetch) {}

  private async request(route: string, body: unknown, signal?: AbortSignal, mutation = false): Promise<unknown> {
    // Acquire credentials before entering the ambiguous remote-mutation boundary.
    const token = await this.token();
    if (!token || /[\r\n]/.test(token)) throw new Error('TikTok sign-in is required');
    signal?.throwIfAborted();
    let response: Response;
    try {
      response = await this.fetcher(API + route, {
        method: 'POST', redirect: 'error', signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(30_000)]) : AbortSignal.timeout(30_000),
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json; charset=UTF-8' },
        body: JSON.stringify(body),
      });
    } catch {
      if (mutation) throw new UploadOutcomeUnknown('TikTok upload initialization could not be confirmed. Do not start another upload automatically.');
      throw new Error('TikTok status could not be retrieved');
    }
    const parsed = envelope.safeParse(await response.json().catch(() => null));
    if (response.status >= 500 || !parsed.success) {
      if (mutation) throw new UploadOutcomeUnknown('TikTok upload initialization returned an unconfirmed response.');
      throw new Error('Invalid TikTok status response');
    }
    if (!response.ok || parsed.data.error.code !== 'ok') {
      // Do not include arbitrary server messages, signed URLs or tokens in errors.
      const code = /^[a-z_]{1,80}$/.test(parsed.data.error.code) ? parsed.data.error.code : 'request_failed';
      throw new Error(`TikTok request failed: ${code} (HTTP ${response.status})`);
    }
    return parsed.data.data;
  }

  /** Creates an inbox draft; this does NOT publish a video. Persist before sending bytes. */
  async initInbox(size: number, signal?: AbortSignal): Promise<TikTokUpload> {
    const plan = tikTokChunks(size);
    const raw = await this.request('inbox/video/init/', { source_info: {
      source: 'FILE_UPLOAD', video_size: size, chunk_size: plan.chunkSize, total_chunk_count: plan.chunks,
    } }, signal, true);
    try {
      const data = initialized.parse(raw);
      return { provider: 'tiktok', publishId: data.publish_id, uploadUrl: uploadUrl(data.upload_url), ...plan };
    } catch {
      throw new UploadOutcomeUnknown('TikTok created an upload but its recovery information could not be verified.');
    }
  }

  /** Caller supplies one bounded file chunk and persists progress; never reinitializes on failure. */
  async putChunk(upload: TikTokUpload, index: number, bytes: Uint8Array, signal?: AbortSignal): Promise<void> {
    const plan = tikTokChunks(upload.size);
    if (upload.provider !== 'tiktok' || upload.chunkSize !== plan.chunkSize || upload.chunks !== plan.chunks || !Number.isInteger(index) || index < 0 || index >= plan.chunks) throw new Error('Invalid TikTok upload chunk');
    const start = index * plan.chunkSize;
    const last = index === plan.chunks - 1;
    const length = last ? plan.size - start : plan.chunkSize;
    if (bytes.byteLength !== length) throw new Error('TikTok upload chunk has the wrong size');
    const url = uploadUrl(upload.uploadUrl);
    signal?.throwIfAborted();
    try {
      const response = await this.fetcher(url, {
        method: 'PUT', redirect: 'error', signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(120_000)]) : AbortSignal.timeout(120_000),
        headers: { 'Content-Type': 'video/mp4', 'Content-Length': String(length), 'Content-Range': `bytes ${start}-${start + length - 1}/${plan.size}` },
        body: new Uint8Array(bytes),
      });
      if (response.status !== (last ? 201 : 206)) throw new Error('unconfirmed chunk');
    } catch {
      throw new UploadOutcomeUnknown('TikTok upload progress must be checked before retrying.');
    }
  }

  async getStatus(publishId: string, signal?: AbortSignal) {
    id.parse(publishId);
    const parsed = status.safeParse(await this.request('status/fetch/', { publish_id: publishId }, signal));
    if (!parsed.success) throw new Error('Invalid TikTok status response');
    const data = parsed.data;
    const state = data.status === 'PUBLISH_COMPLETE' ? 'posted' : data.status === 'SEND_TO_USER_INBOX' ? 'draft' : data.status === 'FAILED' ? 'failed' : ['PROCESSING_UPLOAD', 'PROCESSING_DOWNLOAD'].includes(data.status) ? 'processing' : 'unknown';
    return { provider: 'tiktok' as const, publishId, state, uploadedBytes: data.uploaded_bytes, postIds: data.publicaly_available_post_id ?? [], failureReason: data.fail_reason };
  }
}
