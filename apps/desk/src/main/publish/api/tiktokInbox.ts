import fs from 'node:fs/promises';
import { createHash } from 'node:crypto';
import type { ApiVault } from './vault';
import { TikTokTransport, tikTokChunks, type TikTokUpload } from './tiktok';
import { UploadOutcomeUnknown } from '../outcome';

export interface TikTokAttempt {
  account: string;
  file: string;
  sha256: string;
  size: number;
  /** Written BEFORE init. No session means the remote outcome is unknown. */
  session?: TikTokUpload;
}

/** Main-process coordinator; one instance per vault. No credential/session goes to the UI. */
export class TikTokInbox {
  private busy = new Set<string>();
  constructor(private vault: ApiVault, private transport: (account: string) => TikTokTransport) {}

  async upload(postId: string, account: string, file: string, signal?: AbortSignal) {
    if (!postId || !account) throw new Error('A post and TikTok account are required');
    const key = `tiktok-upload/${postId}`;
    if (this.busy.has(key)) throw new Error('This TikTok upload is already running');
    this.busy.add(key);
    try {
      const saved = this.vault.get(key, true).tiktokAttempt;
      if (saved && (saved.account !== account || saved.file !== file)) throw new Error('This post already has a TikTok upload for another account or file');
      if (saved && !saved.session) throw new UploadOutcomeUnknown('TikTok initialization is unconfirmed. Check the account before starting another upload.');
      const api = this.transport(account);
      // Reconcile first: completed remote uploads remain recoverable even if the local file moved.
      const remote = saved?.session ? await api.getStatus(saved.session.publishId, signal) : null;
      if (remote && remote.state !== 'processing') return remote;
      if (remote && remote.uploadedBytes === saved?.size) return remote;
      const handle = await fs.open(file, 'r');
      try {
        const stat = await handle.stat();
        if (!stat.isFile()) throw new Error('TikTok upload needs a video file');
        const plan = tikTokChunks(stat.size);
        const hash = createHash('sha256');
        // Bounded reads on the same descriptor subsequently used for upload.
        const buffer = Buffer.alloc(Math.min(plan.chunkSize, 1024 * 1024));
        for (let pos = 0; pos < plan.size;) {
          signal?.throwIfAborted();
          const { bytesRead } = await handle.read(buffer, 0, Math.min(buffer.length, plan.size - pos), pos);
          if (!bytesRead) throw new Error('The upload file changed');
          hash.update(buffer.subarray(0, bytesRead)); pos += bytesRead;
        }
        const sha256 = hash.digest('hex');
        if (saved && (saved.size !== stat.size || saved.sha256 !== sha256)) throw new Error('The original TikTok upload file has changed');
        let attempt: TikTokAttempt;
        if (saved) attempt = saved;
        else {
          signal?.throwIfAborted();
          attempt = { account, file, size: stat.size, sha256 };
          this.vault.set(key, { tiktokAttempt: attempt });
          const session = await api.initInbox(stat.size, signal);
          attempt = { ...attempt, session };
          // If this write fails, the prior init marker survives and prohibits a duplicate.
          this.vault.set(key, { tiktokAttempt: attempt });
        }
        const session = attempt.session!;
        const uploaded = remote ? remote.uploadedBytes : 0;
        // A missing/partial/unexpected offset is not permission to resend from zero.
        if (uploaded === undefined || uploaded > plan.size || uploaded % plan.chunkSize !== 0) {
          throw new UploadOutcomeUnknown('TikTok has not confirmed a resumable chunk boundary. Check its status again.');
        }
        for (let index = uploaded / plan.chunkSize; index < plan.chunks; index++) {
          signal?.throwIfAborted();
          const now = await handle.stat();
          if (now.size !== stat.size || now.mtimeMs !== stat.mtimeMs) throw new Error('The upload file changed');
          const start = index * plan.chunkSize;
          const length = index === plan.chunks - 1 ? plan.size - start : plan.chunkSize;
          const chunk = Buffer.alloc(length);
          let read = 0;
          while (read < length) {
            const result = await handle.read(chunk, read, length - read, start + read);
            if (!result.bytesRead) throw new Error('The upload file changed');
            read += result.bytesRead;
          }
          await api.putChunk(session, index, chunk, signal);
        }
        return await api.getStatus(session.publishId, signal);
      } finally { await handle.close(); }
    } finally { this.busy.delete(key); }
  }
}
