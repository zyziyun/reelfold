import http from 'node:http';
import type { AddressInfo } from 'node:net';
import { expect, it } from 'vitest';
import { TikTokTransport } from '../../src/main/publish/api/tiktok';

it('sends real HTTP bytes and stops at the inbox draft receipt', async () => {
  const requests: { path: string; auth?: string; range?: string; body: Buffer }[] = [];
  const server = http.createServer(async (req, res) => {
    const chunks: Buffer[] = [];
    for await (const chunk of req) chunks.push(Buffer.from(chunk));
    requests.push({ path: req.url!, auth: req.headers.authorization, range: req.headers['content-range'] as string | undefined, body: Buffer.concat(chunks) });
    if (req.method === 'PUT') { res.writeHead(201); res.end(); return; }
    res.setHeader('Content-Type', 'application/json');
    const data = req.url?.includes('/init/')
      ? { publish_id: 'id', upload_url: 'https://open-upload.tiktokapis.com/video/?upload_token=signed' }
      : { status: 'SEND_TO_USER_INBOX', uploaded_bytes: 3 };
    res.end(JSON.stringify({ error: { code: 'ok' }, data }));
  });
  await new Promise<void>((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  try {
    const port = (server.address() as AddressInfo).port;
    // Only the injected test transport redirects endpoints; production URLs stay fixed.
    const localFetch: typeof fetch = (input, init) => {
      const url = new URL(String(input));
      return fetch(`http://127.0.0.1:${port}${url.pathname}${url.search}`, init);
    };
    const api = new TikTokTransport(async () => 'test-token', localFetch);
    const session = await api.initInbox(3);
    await api.putChunk(session, 0, new Uint8Array([0, 128, 255]));
    expect((await api.getStatus(session.publishId)).state).toBe('draft');
    expect(requests).toHaveLength(3);
    expect(requests[0].auth).toBe('Bearer test-token');
    expect(requests[1].auth).toBeUndefined();
    expect(requests[1].range).toBe('bytes 0-2/3');
    expect([...requests[1].body]).toEqual([0, 128, 255]);
    expect(JSON.parse(requests[2].body.toString())).toEqual({ publish_id: 'id' });
  } finally {
    server.closeAllConnections();
    await new Promise<void>(resolve => server.close(() => resolve()));
  }
});
