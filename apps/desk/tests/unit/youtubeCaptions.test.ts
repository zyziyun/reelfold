import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, expect, it, vi } from 'vitest';
import { ensureCaption } from '../../src/main/publish/api/youtubeCaptions';
import type { CaptionArtifact } from '../../src/shared/publish/apiPlatforms';
const dirs: string[] = [];
afterEach(() => { for (const d of dirs.splice(0)) fs.rmSync(d, { recursive: true, force: true }); });
function artifact(): CaptionArtifact {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'caption-api-')); dirs.push(d);
  const text = '1\n00:00:00,000 --> 00:00:01,000\nBonjour.\n';
  const file = path.join(d, 'speech.srt'); fs.writeFileSync(file, text);
  return { file, format: 'srt', lang: 'fr', role: 'speech', cues: 1, render_key: 'revision', sha256: crypto.createHash('sha256').update(text).digest('hex') };
}
it.each(['serving', 'syncing', 'failed'])('reconciles dropped upload and preserves %s status without another insert', async status => {
  const a = artifact();
  const item = { id: 'caption1', snippet: { videoId: 'video1', language: 'fr', name: `Reelfold fr ${a.sha256}`, status } };
  let stored = false;
  const request = vi.fn(async (_url: string, init?: RequestInit) => {
    if (init?.method === 'POST') { stored = true; expect(String(init.body)).toContain('Bonjour.'); throw new Error('connection lost'); }
    return Response.json({ items: stored ? [item] : [] });
  });
  const t = { api: 'https://example.test/api', upload: 'https://example.test/upload', request };
  expect((await ensureCaption(t, 'video1', a)).status).toBe(status);
  expect((await ensureCaption(t, 'video1', a)).id).toBe('caption1');
  expect(request.mock.calls.filter(c => c[1]?.method === 'POST')).toHaveLength(1);
});
it('does not upload a changed artifact or editorial captions', async () => {
  const a = artifact(); const request = vi.fn(); const t = { api: '', upload: '', request };
  await expect(ensureCaption(t, 'video1', { ...a, role: 'rendered-captions' })).rejects.toThrow('Invalid');
  fs.appendFileSync(a.file, 'changed');
  await expect(ensureCaption(t, 'video1', a)).rejects.toThrow('changed');
  expect(request).not.toHaveBeenCalled();
});
it('leaves creator tracks intact and reports an unconfirmed insert', async () => {
  const a = artifact();
  const request = vi.fn(async (_url: string, init?: RequestInit) => init?.method === 'POST'
    ? new Response('', { status: 503 }) : Response.json({ items: [{ id: 'mine', snippet: { language: 'fr', name: 'My captions' } }] }));
  await expect(ensureCaption({ api: '', upload: '', request }, 'video1', a)).rejects.toThrow('503');
  expect(request.mock.calls.filter(c => c[1]?.method === 'POST')).toHaveLength(1);
  expect(request.mock.calls.some(c => c[1]?.method === 'DELETE')).toBe(false);
});
