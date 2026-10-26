import crypto from 'node:crypto';
import fs from 'node:fs';
import type { CaptionArtifact } from '../../../shared/publish/apiPlatforms';

export const YT_CAPTIONS = 'https://www.googleapis.com/auth/youtube.force-ssl';
export interface CaptionReceipt {
  id: string;
  language: string;
  name: string;
  status: 'serving' | 'syncing' | 'failed' | 'unknown';
  failureReason?: string;
}
interface Resource {
  id?: string;
  snippet?: { videoId?: string; language?: string; name?: string; status?: string; failureReason?: string };
}
interface Transport {
  api: string;
  upload: string;
  request: (url: string, init?: RequestInit) => Promise<Response>;
}
function receipt(r: Resource, videoId: string, language: string, name: string): CaptionReceipt {
  if (!r.id || r.snippet?.videoId !== videoId || r.snippet?.language !== language || r.snippet?.name !== name) {
    throw new Error('YouTube caption response did not identify the requested track');
  }
  const status = r.snippet.status;
  return { id: r.id, language, name, status: status === 'serving' || status === 'syncing' || status === 'failed' ? status : 'unknown',
    ...(r.snippet.failureReason ? { failureReason: r.snippet.failureReason } : {}) };
}

/** Upload one verified speech track. Reconcile an ambiguous POST by name before any retry;
 * never overwrite/delete creator tracks or assume that accepted means serving. */
export async function ensureCaption(t: Transport, videoId: string, track: CaptionArtifact): Promise<CaptionReceipt> {
  if (!/^[\w-]+$/.test(videoId) || track.role !== 'speech' || !/^[a-z]{2,3}(?:-[A-Za-z0-9]+)*$/.test(track.lang) || track.lang === 'und' ||
      !['srt', 'vtt'].includes(track.format) || !/^[a-f0-9]{64}$/.test(track.sha256)) throw new Error('Invalid speech caption artifact');
  const size = fs.statSync(track.file).size;
  if (!size || size > 100 * 1024 * 1024) throw new Error('Caption file must be between 1 byte and 100 MB');
  const bytes = fs.readFileSync(track.file);
  if (crypto.createHash('sha256').update(bytes).digest('hex') !== track.sha256) throw new Error('Caption file changed since export');
  const name = `Reelfold ${track.lang} ${track.sha256}`;
  const lookup = async () => {
    const r = await t.request(`${t.api}/captions?${new URLSearchParams({ part: 'snippet', videoId })}`);
    if (!r.ok) throw new Error(`YouTube caption lookup failed (${r.status})`);
    const body = await r.json() as { items?: Resource[] };
    const matches = (body.items ?? []).filter(c => c.snippet?.language === track.lang && c.snippet?.name === name);
    if (matches.length > 1) throw new Error('YouTube returned multiple matching caption tracks');
    return matches[0] ? receipt(matches[0], videoId, track.lang, name) : null;
  };
  const existing = await lookup();
  if (existing) return existing;
  const boundary = `reelfold_${crypto.randomBytes(16).toString('hex')}`;
  const meta = JSON.stringify({ snippet: { videoId, language: track.lang, name, isDraft: false } });
  const body = Buffer.concat([Buffer.from(`--${boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n${meta}\r\n--${boundary}\r\nContent-Type: application/octet-stream\r\n\r\n`), bytes, Buffer.from(`\r\n--${boundary}--\r\n`)]);
  try {
    const r = await t.request(`${t.upload}/captions?uploadType=multipart&part=snippet`, {
      method: 'POST', headers: { 'Content-Type': `multipart/related; boundary=${boundary}` }, body,
    });
    if (!r.ok) throw new Error(`YouTube caption upload failed (${r.status})`);
    return receipt(await r.json() as Resource, videoId, track.lang, name);
  } catch (error) {
    // A dropped response or 409 may still mean the first request created the track.
    const found = await lookup();
    if (found) return found;
    throw error;
  }
}
