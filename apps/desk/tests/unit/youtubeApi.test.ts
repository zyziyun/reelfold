// YouTube through the official Data API against a FAKE Google (a real local HTTP server: OAuth consent + token
// endpoint with PKCE checks, channels / playlists, the resumable upload session, thumbnails, playlist items). The app
// code talks to it over real HTTP with the platform fetch: the "system browser" follows the consent redirect to the
// app's loopback port. Also: tokens only in the keychain (encrypted vault), the client choice (Reelfold's / hers),
// chunked upload with resume after a 503 and after a dropped connection, and the embedded-browser refusal pages.
import crypto from 'node:crypto';
import { UploadOutcomeUnknown } from '../../src/main/publish/outcome';
import fs from 'node:fs';
import http from 'node:http';
import type { AddressInfo } from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { loadAdapters } from '../../src/main/publish/adapters';
import { ApiVault } from '../../src/main/publish/api/vault';
import { builtinClient, shortsFit, YouTubeApi, ytMeta, YT_MANAGE, YT_READONLY, YT_UPLOAD, type GoogleEndpoints } from '../../src/main/publish/api/youtube';
import { apiDeliveryState, apiOnly, publishPath, PUBLISH_PATH } from '../../src/shared/publish/apiPlatforms';
import { embeddedBlock, maybeBlockPage, WEBVIEW_RISK } from '../../src/shared/publish/embedBlock';
import { validateIpc } from '../../src/shared/ipc';

const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-yt-'));
/** like safeStorage with a keychain: reversible, but not plain text */
const crypto0 = { isEncryptionAvailable: () => true, encryptString: (s: string) => Buffer.from(`enc:${Buffer.from(s).toString('hex')}`), decryptString: (b: Buffer) => Buffer.from(b.toString().replace(/^enc:/, ''), 'hex').toString() };
const b64url = (b: Buffer) => b.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
const CLIENT = '1234-abc.apps.googleusercontent.com';

interface Session {
  size: number;
  meta: { snippet: { title: string }; status: { privacyStatus: string; publishAt?: string } };
  got: Buffer[];
  received: number;
  done: boolean;
}

/** A fake Google: what the real endpoints check, nothing more. */
class FakeGoogle {
  server!: http.Server;
  base = '';
  secret: string | null = 'GOCSPX-desktop';
  deny = false;
  /** scopes the consent screen grants (null: all asked) */
  grant: string[] | null = null;
  channels = [{ id: 'UC1', snippet: { title: 'Ziyun Studio' } }];
  /** A provider response that differs from the requested public visibility. */
  lockPrivate = false;
  omitStatus = false;
  videoStatus: Record<string, string> | null = { privacyStatus: 'public', uploadStatus: 'processed' };
  statusCode = 200;
  statusReads = 0;
  codes = new Map<string, { challenge: string; redirect: string; scope: string }>();
  refresh = new Map<string, string>();
  access = new Set<string>();
  sessions = new Map<string, Session>();
  /** per chunk index: what goes wrong */
  faults = new Map<number, '503' | 'drop-after-store' | 'stall' | 'invalid-range' | 'pending-final'>();
  retryDelay: string | null = null;
  chunks = 0;
  queries = 0;
  loseReceipt = false;
  thumbs: { videoId: string; type: string; bytes: number }[] = [];
  playlistItems: { playlistId: string; videoId: string }[] = [];
  revoked: string[] = [];
  tokenRequests: URLSearchParams[] = [];

  async start() {
    this.server = http.createServer((req, res) => void this.handle(req, res));
    await new Promise<void>((r) => this.server.listen(0, '127.0.0.1', r));
    this.base = `http://127.0.0.1:${(this.server.address() as AddressInfo).port}`;
  }

  stop() {
    this.server.closeAllConnections();
    return new Promise<void>((r) => this.server.close(() => r()));
  }

  get endpoints(): GoogleEndpoints {
    return { auth: `${this.base}/o/oauth2/v2/auth`, token: `${this.base}/token`, revoke: `${this.base}/revoke`, api: `${this.base}/youtube/v3`, upload: `${this.base}/upload/youtube/v3` };
  }

  private body(req: http.IncomingMessage): Promise<Buffer> {
    return new Promise((r) => {
      const parts: Buffer[] = [];
      req.on('data', (c) => parts.push(c));
      req.on('end', () => r(Buffer.concat(parts)));
    });
  }

  private json(res: http.ServerResponse, status: number, j: unknown, headers: Record<string, string> = {}) {
    res.writeHead(status, { 'Content-Type': 'application/json', ...headers }).end(JSON.stringify(j));
  }

  private authed(req: http.IncomingMessage) {
    return this.access.has((req.headers.authorization ?? '').replace(/^Bearer /, ''));
  }

  private async handle(req: http.IncomingMessage, res: http.ServerResponse) {
    const u = new URL(req.url ?? '/', this.base);
    const body = await this.body(req);
    // ---- consent page: the "browser" lands here and is redirected back to the app's loopback port
    if (u.pathname === '/o/oauth2/v2/auth') {
      const q = u.searchParams;
      const redirect = q.get('redirect_uri')!;
      if (q.get('client_id') !== CLIENT || q.get('code_challenge_method') !== 'S256' || !/^http:\/\/127\.0\.0\.1:\d+$/.test(redirect)) return this.json(res, 400, { error: 'invalid_request' });
      if (this.deny) return res.writeHead(302, { Location: `${redirect}/?error=access_denied&state=${q.get('state')}` }).end();
      const code = b64url(crypto.randomBytes(12));
      const scope = (this.grant ?? q.get('scope')!.split(' ')).join(' ');
      this.codes.set(code, { challenge: q.get('code_challenge')!, redirect, scope });
      return res.writeHead(302, { Location: `${redirect}/?code=${code}&state=${q.get('state')}&scope=${encodeURIComponent(scope)}` }).end();
    }
    if (u.pathname === '/token' && req.method === 'POST') {
      const f = new URLSearchParams(body.toString());
      this.tokenRequests.push(f);
      if (f.get('client_id') !== CLIENT || (this.secret && f.get('client_secret') !== this.secret)) return this.json(res, 401, { error: 'invalid_client' });
      if (f.get('grant_type') === 'authorization_code') {
        const c = this.codes.get(f.get('code') ?? '');
        if (!c) return this.json(res, 400, { error: 'invalid_grant' });
        this.codes.delete(f.get('code')!);
        if (c.redirect !== f.get('redirect_uri')) return this.json(res, 400, { error: 'redirect_uri_mismatch' });
        if (b64url(crypto.createHash('sha256').update(f.get('code_verifier') ?? '').digest()) !== c.challenge) return this.json(res, 400, { error: 'invalid_grant', error_description: 'code verifier mismatch' });
        const at = `at-${b64url(crypto.randomBytes(6))}`;
        const rt = `rt-${b64url(crypto.randomBytes(6))}`;
        this.access.add(at);
        this.refresh.set(rt, c.scope);
        return this.json(res, 200, { access_token: at, refresh_token: rt, expires_in: 3599, scope: c.scope, token_type: 'Bearer' });
      }
      if (f.get('grant_type') === 'refresh_token') {
        if (!this.refresh.has(f.get('refresh_token') ?? '')) return this.json(res, 400, { error: 'invalid_grant' });
        const at = `at-${b64url(crypto.randomBytes(6))}`;
        this.access.add(at);
        return this.json(res, 200, { access_token: at, expires_in: 3599 });
      }
      return this.json(res, 400, { error: 'unsupported_grant_type' });
    }
    if (u.pathname === '/revoke') {
      const tok = new URLSearchParams(body.toString()).get('token') ?? '';
      this.revoked.push(tok);
      this.refresh.delete(tok);
      return this.json(res, 200, {});
    }
    if (!this.authed(req)) return this.json(res, 401, { error: { message: 'Invalid Credentials', errors: [{ reason: 'authError' }] } });
    if (u.pathname === '/youtube/v3/channels') return this.json(res, 200, { items: this.channels });
    if (u.pathname === '/youtube/v3/videos') {
      this.statusReads++;
      return this.json(res, this.statusCode, { items: this.videoStatus ? [{ id: u.searchParams.get('id'), status: this.videoStatus }] : [] });
    }
    if (u.pathname === '/youtube/v3/playlists') return this.json(res, 200, { items: [{ id: 'PL1', snippet: { title: 'Course' } }] });
    if (u.pathname === '/youtube/v3/playlistItems' && req.method === 'POST') {
      const j = JSON.parse(body.toString());
      this.playlistItems.push({ playlistId: j.snippet.playlistId, videoId: j.snippet.resourceId.videoId });
      return this.json(res, 200, { id: 'PLI1' });
    }
    if (u.pathname === '/upload/youtube/v3/thumbnails/set') {
      this.thumbs.push({ videoId: u.searchParams.get('videoId')!, type: String(req.headers['content-type']), bytes: body.length });
      return this.json(res, 200, { items: [] });
    }
    if (u.pathname === '/upload/youtube/v3/videos' && req.method === 'POST' && u.searchParams.get('uploadType') === 'resumable') {
      const id = `S${this.sessions.size + 1}`;
      this.sessions.set(id, { size: Number(req.headers['x-upload-content-length']), meta: JSON.parse(body.toString()), got: [], received: 0, done: false });
      return res.writeHead(200, { Location: `${this.base}/upload/youtube/v3/videos?uploadType=resumable&upload_id=${id}` }).end();
    }
    if (u.pathname === '/upload/youtube/v3/videos' && req.method === 'PUT') {
      const s = this.sessions.get(u.searchParams.get('upload_id') ?? '');
      if (!s) return this.json(res, 404, {});
      const range = String(req.headers['content-range'] ?? '');
      const finish = () => {
        s.done = true;
        if (this.loseReceipt) { req.socket.destroy(); return; }
        const privacy = this.lockPrivate ? 'private' : s.meta.status.privacyStatus;
        return this.json(res, 201, { id: 'vid123', ...(this.omitStatus ? {} : { status: { privacyStatus: privacy, uploadStatus: 'processed', ...(s.meta.status.publishAt && !this.lockPrivate ? { publishAt: s.meta.status.publishAt } : {}) } }) });
      };
      const incomplete = () => res.writeHead(308, { ...(s.received ? { Range: `bytes=0-${s.received - 1}` } : {}), ...(this.retryDelay ? { 'Retry-After': this.retryDelay } : {}) }).end();
      if (range.startsWith('bytes */')) {
        this.queries++;
        return s.done || s.received === s.size ? finish() : incomplete();
      }
      const m = /^bytes (\d+)-(\d+)\/(\d+)$/.exec(range);
      if (!m || Number(m[3]) !== s.size || Number(m[2]) - Number(m[1]) + 1 !== body.length) return this.json(res, 400, { error: { message: `bad range ${range}` } });
      const i = this.chunks++;
      const fault = this.faults.get(i);
      if (fault === 'stall') return incomplete();
      if (fault === 'invalid-range') return res.writeHead(308, { Range: `bytes=0-${s.size}` }).end();
      if (fault === '503') return this.json(res, 503, { error: { message: 'backend error' } });
      if (Number(m[1]) !== s.received) return incomplete();
      s.got.push(body);
      s.received += body.length;
      if (fault === 'pending-final') { s.done = true; return incomplete(); }
      if (fault === 'drop-after-store') {
        req.socket.destroy(); // the bytes arrived, the answer is lost
        return;
      }
      return s.received === s.size ? finish() : incomplete();
    }
    return this.json(res, 404, { error: { message: `no route ${u.pathname}` } });
  }
}

/** The system browser: opens the consent URL and follows Google's redirect to the app's loopback port. */
const browser = (seen: string[] = []) => (url: string) => {
  seen.push(url);
  setTimeout(() => void fetch(url).then((r) => r.text()).catch(() => undefined), 10);
};

let g: FakeGoogle;
beforeEach(async () => {
  g = new FakeGoogle();
  await g.start();
});
afterEach(async () => {
  await g.stop();
});

const mk = (dir = tmp(), extra: Partial<ConstructorParameters<typeof YouTubeApi>[0]> = {}) => {
  const vault = new ApiVault(dir, crypto0, 'darwin');
  const seen: string[] = [];
  const yt = new YouTubeApi({ vault, endpoints: g.endpoints, builtin: null, openExternal: browser(seen), sleep: async () => undefined, chunkBytes: 256 * 1024, ...extra });
  return { yt, vault, dir, seen };
};

describe('OAuth in the system browser (fake Google)', () => {
  it('reads actual video processing and visibility without another upload', async () => {
    const { yt } = mk();
    yt.setClient(CLIENT, 'GOCSPX-desktop');
    await yt.connect('main', { timeoutMs: 5000 });
    const previous = { url: 'https://youtu.be/vid123', privacy: 'private', publishAt: null, lockedPrivate: true, warnings: ['Cover unavailable'] };
    for (const [status, expected] of [
      [{ privacyStatus: 'public', uploadStatus: 'processed' }, 'posted'],
      [{ privacyStatus: 'public', uploadStatus: 'uploaded' }, 'uploaded'],
      [{ privacyStatus: 'public', uploadStatus: 'failed', failureReason: 'codec' }, 'uploaded'],
      [{ privacyStatus: 'public', uploadStatus: 'rejected', rejectionReason: 'copyright' }, 'uploaded'],
      [{ privacyStatus: 'private', uploadStatus: 'processed', publishAt: '2026-10-20T12:00:00Z' }, 'scheduled'],
      [{ privacyStatus: 'private', uploadStatus: 'uploaded', publishAt: '2026-10-20T12:00:00Z' }, 'scheduled'],
      [{ privacyStatus: 'public' }, 'uploaded'],
    ] as [Record<string, string>, string][]) {
      g.videoStatus = status;
      const r = await yt.videoStatus('main', previous);
      expect(apiDeliveryState(r)).toBe(expected);
      expect(r.checkedAt).toMatch(/^\d{4}-/);
      expect(r.warnings).toEqual(previous.warnings);
      expect(r.failureReason).toBe(status.failureReason ?? status.rejectionReason);
    }
    expect(g.sessions.size).toBe(0);
    g.videoStatus = null;
    await expect(yt.videoStatus('main', previous)).rejects.toThrow(/unavailable to this account/);
    g.statusCode = 503;
    await expect(yt.videoStatus('main', previous)).rejects.toThrow(/status unavailable/);
    expect(previous.privacy).toBe('private');
  });

  it('never fetches an arbitrary receipt URL or accepts a forged video ID', async () => {
    const { yt } = mk();
    const previous = { privacy: 'private', publishAt: null, lockedPrivate: false, warnings: [] };
    for (const url of ['https://evil.test/watch?v=vid123', 'https://youtube.com.evil.test/watch?v=vid123', 'http://youtu.be/vid123', 'https://u:p@youtu.be/vid123']) {
      await expect(yt.videoStatus('main', { ...previous, url })).rejects.toThrow();
    }
    await expect(yt.videoStatus('main', { ...previous, url: 'https://youtu.be/vid123', id: '../other' })).rejects.toThrow(/video ID/);
    expect(g.statusReads).toBe(0);
  });

  it('PKCE + loopback with her own client: the refresh token is stored encrypted, the channel is named', async () => {
    const { yt, dir, seen } = mk();
    expect(() => yt.setClient('not-a-client')).toThrow(/client ID/);
    yt.setClient(CLIENT, 'GOCSPX-desktop');
    expect(yt.status(['main'])).toMatchObject({ source: 'own', hasClient: true, builtin: false, accounts: [{ account: 'main', connected: false }] });
    const st = await yt.connect('main', { timeoutMs: 5000 });
    expect(st).toMatchObject({ connected: true, channel: { id: 'UC1', title: 'Ziyun Studio' }, playlists: false });
    const q = new URL(seen[0]).searchParams;
    expect(q.get('scope')).toBe(`${YT_UPLOAD} ${YT_READONLY}`);
    expect(q.get('code_challenge_method')).toBe('S256');
    expect(q.get('access_type')).toBe('offline');
    expect(q.get('redirect_uri')).toMatch(/^http:\/\/127\.0\.0\.1:\d+$/);
    // the token exchange carried the verifier and the secret
    const ex = g.tokenRequests.find((f) => f.get('grant_type') === 'authorization_code')!;
    expect(ex.get('code_verifier')!.length).toBeGreaterThanOrEqual(43);
    expect(ex.get('client_secret')).toBe('GOCSPX-desktop');
    // keychain only: nothing readable on disk
    const disk = fs.readFileSync(path.join(dir, 'publish-api.json'), 'utf8');
    const rt = [...g.refresh.keys()][0];
    expect(disk).not.toContain(rt);
    expect(disk).not.toContain('GOCSPX-desktop');
    expect(new ApiVault(dir, crypto0, 'darwin').get('youtube/main').refreshToken).toBe(rt);
    await yt.disconnect('main');
    expect(g.revoked).toEqual([rt]);
    expect(yt.accountStatus('main').connected).toBe(false);
  });

  it('a client without a secret sends none; the playlists permission is asked only when she wants it', async () => {
    g.secret = null;
    const { yt, seen } = mk();
    yt.setClient(CLIENT);
    await yt.connect('main', { playlists: true, timeoutMs: 5000 });
    expect(new URL(seen[0]).searchParams.get('scope')).toBe(`${YT_UPLOAD} ${YT_READONLY} ${YT_MANAGE}`);
    expect(g.tokenRequests[0].has('client_secret')).toBe(false);
    expect(yt.accountStatus('main').playlists).toBe(true);
  });

  it('refused consent, a forged state, an unticked upload permission, no channel: not connected, plain errors', async () => {
    const { yt } = mk();
    yt.setClient(CLIENT, 'GOCSPX-desktop');
    g.deny = true;
    await expect(yt.connect('main', { timeoutMs: 5000 })).rejects.toThrow(/did not allow/);
    g.deny = false;
    g.grant = [YT_READONLY];
    await expect(yt.connect('main', { timeoutMs: 5000 })).rejects.toThrow(/upload videos was not ticked/);
    g.grant = null;
    g.channels = [];
    await expect(yt.connect('main', { timeoutMs: 5000 })).rejects.toThrow(/no YouTube channel/);
    expect(yt.accountStatus('main').connected).toBe(false);
    const forged = new YouTubeApi({
      vault: new ApiVault(tmp(), crypto0, 'darwin'),
      endpoints: g.endpoints,
      builtin: null,
      openExternal: (url) => {
        const q = new URL(url).searchParams;
        setTimeout(() => http.get(`${q.get('redirect_uri')}/?code=c&state=forged`, (r) => r.resume()), 10);
      },
    });
    forged.setClient(CLIENT, 'GOCSPX-desktop');
    await expect(forged.connect('main', { timeoutMs: 5000 })).rejects.toThrow(/did not match/);
  });

  it('she abandons the consent: Cancel stops the wait and frees the port', async () => {
    const { yt } = mk(tmp(), { openExternal: () => undefined });
    yt.setClient(CLIENT, 'GOCSPX-desktop');
    const p = yt.connect('main', { timeoutMs: 60_000 });
    setTimeout(() => yt.cancelConnect(), 30);
    await expect(p).rejects.toThrow(/cancelled/);
  });

  it('Reelfold’s client from the build; switching clients forgets every token', async () => {
    expect(builtinClient({})).toBeNull();
    expect(builtinClient({ REELFOLD_GOOGLE_CLIENT_ID: 'bad' })).toBeNull();
    expect(builtinClient({ REELFOLD_GOOGLE_CLIENT_ID: CLIENT, REELFOLD_GOOGLE_CLIENT_SECRET: 'GOCSPX-desktop' })).toEqual({ clientId: CLIENT, clientSecret: 'GOCSPX-desktop' });
    const { yt } = mk(tmp(), { builtin: { clientId: CLIENT, clientSecret: 'GOCSPX-desktop' } });
    expect(yt.status()).toMatchObject({ source: 'reelfold', hasClient: true, builtin: true });
    await yt.connect('main', { timeoutMs: 5000 });
    expect(yt.accountStatus('main').connected).toBe(true);
    yt.setClient(CLIENT, 'GOCSPX-desktop');
    expect(yt.status(['main'])).toMatchObject({ source: 'own', accounts: [{ connected: false }] });
    yt.forgetClient();
    expect(yt.status()).toMatchObject({ source: 'reelfold', ownClientId: null });
  });

  it('a token stored before per-account sign-in moves to the "main" account', () => {
    const dir = tmp();
    const v = new ApiVault(dir, crypto0, 'darwin');
    v.set('youtube', { clientId: CLIENT, clientSecret: 'GOCSPX-desktop', refreshToken: 'rt-old', connectedAt: '2026-10-01T00:00:00Z' });
    const yt = new YouTubeApi({ vault: v, endpoints: g.endpoints, builtin: null, openExternal: () => undefined });
    expect(yt.status(['main'])).toMatchObject({ source: 'own', accounts: [{ account: 'main', connected: true }] });
    expect(v.get('youtube').refreshToken).toBeUndefined();
  });

  it('no keychain: nothing is stored', () => {
    const v = new ApiVault(tmp(), { ...crypto0, isEncryptionAvailable: () => false }, 'darwin');
    expect(() => v.set('youtube/main', { refreshToken: 'x' })).toThrow(/keychain/);
    const linux = new ApiVault(tmp(), { ...crypto0, getSelectedStorageBackend: () => 'basic_text' }, 'linux');
    expect(linux.keychain()).toBe(false);
  });
});

describe('resumable upload (fake API)', () => {
  const video = (dir: string, bytes = 700 * 1024) => {
    const f = path.join(dir, 'v.mp4');
    fs.writeFileSync(f, crypto.randomBytes(bytes));
    return f;
  };
  const connected = async () => {
    const m = mk();
    m.yt.setClient(CLIENT, 'GOCSPX-desktop');
    await m.yt.connect('main', { playlists: true, timeoutMs: 5000 });
    return m;
  };

  it('chunks with Content-Range, resumes after a 503 and after a dropped connection; thumbnail + playlist', async () => {
    const { yt, dir } = await connected();
    const file = video(dir);
    const cover = path.join(dir, 'c.jpg');
    fs.writeFileSync(cover, crypto.randomBytes(2048));
    g.faults.set(1, '503').set(3, 'drop-after-store');
    const progress: number[] = [];
    const at = new Date(Date.now() + 86400_000);
    const r = await yt.upload('main', { file, title: 'A <b>title</b>', description: 'd', tags: ['#x'], publishAt: at, categoryId: '27', madeForKids: false, synthetic: true, thumbnail: cover, playlistId: 'PL1' }, (s) => progress.push(s));
    expect(r).toMatchObject({ id: 'vid123', url: 'https://youtu.be/vid123', privacy: 'private', publishAt: at.toISOString(), lockedPrivate: false, warnings: [] });
    const s = g.sessions.get('S1')!;
    expect(Buffer.concat(s.got).equals(fs.readFileSync(file))).toBe(true); // every byte once, in order
    expect(s.meta).toMatchObject({ snippet: { title: 'A btitle/b', categoryId: '27' }, status: { privacyStatus: 'private', publishAt: at.toISOString(), selfDeclaredMadeForKids: false, containsSyntheticMedia: true } });
    expect(g.queries).toBe(2); // asked how much arrived after each failure
    expect(progress.at(-1)).toBe(fs.statSync(file).size);
    expect(g.thumbs).toEqual([{ videoId: 'vid123', type: 'image/jpeg', bytes: 2048 }]);
    expect(g.playlistItems).toEqual([{ playlistId: 'PL1', videoId: 'vid123' }]);
    expect(await yt.playlists('main')).toEqual([{ id: 'PL1', title: 'Course' }]);
  });

  it('gives up after the retries, with a plain error', async () => {
    const { yt, dir } = await connected();
    for (let i = 0; i < 20; i++) g.faults.set(i, '503');
    await expect(yt.upload('main', { file: video(dir), title: 't', description: '', tags: [], publishAt: null })).rejects.toThrow(/after 6 retries/);
  });

  it('reports an uncertain outcome when the final receipt remains unreachable', async () => {
    const { yt, dir } = await connected();
    g.loseReceipt = true;
    await expect(yt.upload('main', { file: video(dir, 100), title: 't', description: '', tags: [], publishAt: null }))
      .rejects.toBeInstanceOf(UploadOutcomeUnknown);
    expect(g.sessions.size).toBe(1);
    expect([...g.sessions.values()][0]).toMatchObject({ done: true, received: 100 });
    expect(g.queries).toBeGreaterThan(0);
  });

  it('recovers the original receipt after restart using an encrypted session without reuploading', async () => {
    const { yt, dir, vault } = await connected();
    const request = { file: video(dir, 100), title: 't', description: '', tags: [], publishAt: null };
    g.loseReceipt = true;
    await expect(yt.upload('main', request, undefined, 'post-1')).rejects.toBeInstanceOf(UploadOutcomeUnknown);
    expect(vault.get('youtube-upload/post-1').uploadSession?.size).toBe(100);
    expect(fs.readFileSync(path.join(dir, 'publish-api.json'), 'utf8')).not.toContain('upload_id=');
    const chunks = g.chunks;
    g.loseReceipt = false;
    const restarted = mk(dir);
    const recovered = await restarted.yt.recover('post-1');
    expect(recovered).toMatchObject({ account: 'main', result: { id: 'vid123', privacy: 'public' } });
    expect(restarted.vault.get('youtube-upload/post-1').uploadSession).toBeUndefined();
    expect(await restarted.yt.upload('main', request, undefined, 'post-1')).toMatchObject({ id: 'vid123' });
    expect(g.sessions.size).toBe(1);
    expect(g.chunks).toBe(chunks);
  });

  it('resumes a partial upload after restart only when enabled, preserving bytes and schedule', async () => {
    const { yt, dir, vault } = await connected();
    const file = video(dir);
    const at = new Date(Date.now() + 86400_000);
    for (let i = 1; i < 20; i++) g.faults.set(i, '503');
    await expect(yt.upload('main', { file, title: 't', description: '', tags: [], publishAt: at }, undefined, 'partial'))
      .rejects.toBeInstanceOf(UploadOutcomeUnknown);
    expect(g.sessions.get('S1')!.received).toBe(256 * 1024);
    expect(vault.get('youtube-upload/partial').uploadSession?.sha256).toMatch(/^[a-f0-9]{64}$/);
    const restarted = mk(dir);
    const chunks = g.chunks;
    expect(await restarted.yt.recover('partial')).toBeNull();
    expect(g.chunks).toBe(chunks);
    g.faults.clear();
    const recovered = await restarted.yt.recover('partial', true);
    expect(recovered?.result).toMatchObject({ id: 'vid123', privacy: 'private', publishAt: at.toISOString() });
    expect(g.sessions.size).toBe(1);
    expect(Buffer.concat(g.sessions.get('S1')!.got)).toEqual(fs.readFileSync(file));
  });

  it('checks the current account before resuming or querying a saved upload', async () => {
    const { yt, dir, vault } = await connected();
    const file = video(dir);
    for (let i = 1; i < 20; i++) g.faults.set(i, '503');
    await expect(yt.upload('main', { file, title: 't', description: '', tags: [], publishAt: null }, undefined, 'account-change'))
      .rejects.toBeInstanceOf(UploadOutcomeUnknown);
    const chunks = g.chunks, queries = g.queries;
    g.faults.clear();
    const restarted = mk(dir);
    for (const account of ['other', null]) {
      await expect(restarted.yt.recover('account-change', true, account)).rejects.toThrow('another publishing account');
    }
    await expect(restarted.yt.upload('other', { file, title: 't', description: '', tags: [], publishAt: null }, undefined, 'account-change'))
      .rejects.toThrow('another publishing account');
    expect(g.chunks).toBe(chunks);
    expect(g.queries).toBe(queries);
    expect(vault.get('youtube-upload/account-change').uploadSession?.account).toBe('main');
    const recovered = await restarted.yt.recover('account-change', true, 'main');
    expect(recovered?.account).toBe('main');
    expect(g.sessions.size).toBe(1);
    expect(Buffer.concat(g.sessions.get('S1')!.got)).toEqual(fs.readFileSync(file));
    await expect(restarted.yt.recover('account-change', false, 'other')).rejects.toThrow('another publishing account');
  });

  it('refuses to append a changed same-size video to a saved session', async () => {
    const { yt, dir } = await connected();
    const file = video(dir);
    for (let i = 1; i < 20; i++) g.faults.set(i, '503');
    await expect(yt.upload('main', { file, title: 't', description: '', tags: [], publishAt: null }, undefined, 'changed'))
      .rejects.toBeInstanceOf(UploadOutcomeUnknown);
    const chunks = g.chunks;
    fs.writeFileSync(file, Buffer.alloc(fs.statSync(file).size, 42));
    g.faults.clear();
    await expect(mk(dir).yt.recover('changed', true)).rejects.toThrow('unavailable or changed');
    expect(g.chunks).toBe(chunks);
    expect(g.sessions.size).toBe(1);
  });

  it('rejects saved sessions on an unexpected host before sending credentials', async () => {
    const { yt, vault } = await connected();
    vault.set('youtube-upload/bad', { uploadSession: { url: 'https://example.com/session', account: 'main', size: 100,
      privacy: 'public', publishAt: null, followups: false } });
    await expect(yt.recover('bad')).rejects.toThrow('Invalid saved upload session');
    expect(g.queries).toBe(0);
  });

  it('bounds repeated incomplete responses without progress', async () => {
    const { yt, dir } = await connected();
    for (let i = 0; i < 20; i++) g.faults.set(i, 'stall');
    await expect(yt.upload('main', { file: video(dir), title: 't', description: '', tags: [], publishAt: null })).rejects.toThrow(/no progress after 6 retries/);
    expect(g.chunks).toBe(7);
    expect(g.sessions.size).toBe(1);
  });

  it('recovers from a stalled chunk without duplicating stored bytes', async () => {
    const { yt, dir } = await connected();
    const file = video(dir);
    g.faults.set(1, 'stall');
    expect((await yt.upload('main', { file, title: 't', description: '', tags: [], publishAt: null })).id).toBe('vid123');
    expect(Buffer.concat(g.sessions.get('S1')!.got)).toEqual(fs.readFileSync(file));
  });

  it('rejects out-of-bounds provider ranges before reading another chunk', async () => {
    const { yt, dir } = await connected();
    g.faults.set(0, 'invalid-range');
    await expect(yt.upload('main', { file: video(dir), title: 't', description: '', tags: [], publishAt: null })).rejects.toThrow(/invalid upload range/);
    expect(g.chunks).toBe(1);
  });

  it('honors the provider retry delay on incomplete uploads', async () => {
    const delays: number[] = [];
    const { yt, dir } = mk(undefined, { sleep: async (ms) => { delays.push(ms); } });
    yt.setClient(CLIENT, 'GOCSPX-desktop');
    await yt.connect('main', { timeoutMs: 5000 });
    g.retryDelay = '3';
    await yt.upload('main', { file: video(dir), title: 't', description: '', tags: [], publishAt: null });
    expect(delays).toEqual([3000, 3000]);
  });

  it('queries the receipt when all bytes are acknowledged with 308', async () => {
    const { yt, dir } = await connected();
    g.faults.set(0, 'pending-final');
    expect((await yt.upload('main', { file: video(dir, 1000), title: 't', description: '', tags: [], publishAt: null })).id).toBe('vid123');
    expect(g.chunks).toBe(1);
    expect(g.queries).toBe(1);
  });

  it('an expired access token is refreshed once; the provider returns private visibility', async () => {
    const { yt, dir } = await connected();
    g.access.clear(); // the cached access token is no longer valid
    g.lockPrivate = true;
    // the session init needs a fresh token first: the cached one fails -> refresh on 401 is for chunks; init uses the cache
    // so drop the cache by forcing expiry
    (yt as unknown as { access: Map<string, unknown> }).access.clear();
    const r = await yt.upload('main', { file: video(dir, 1000), title: 't', description: '', tags: [], publishAt: null, privacy: 'public' });
    expect(r).toMatchObject({ privacy: 'private', lockedPrivate: true });
    expect(g.tokenRequests.filter((f) => f.get('grant_type') === 'refresh_token').length).toBe(1);
  });

  it('does not claim requested public visibility or publish time when the provider omits status', async () => {
    const { yt, dir } = await connected();
    g.omitStatus = true;
    const r = await yt.upload('main', { file: video(dir, 1000), title: 't', description: '', tags: [], publishAt: new Date(Date.now() + 3600_000), privacy: 'public' });
    expect(r).toMatchObject({ privacy: 'unknown', publishAt: null });
  });

  it('a thumbnail YouTube refuses or a playlist without permission: the video is up, with notes', async () => {
    const m = mk();
    m.yt.setClient(CLIENT, 'GOCSPX-desktop');
    await m.yt.connect('main', { timeoutMs: 5000 });
    const big = path.join(m.dir, 'big.png');
    fs.writeFileSync(big, crypto.randomBytes(2 * 1024 * 1024 + 1));
    const r = await m.yt.upload('main', { file: video(m.dir, 1000), title: 't', description: '', tags: [], publishAt: null, thumbnail: big, playlistId: 'PL1' });
    expect(r.id).toBe('vid123');
    expect(r.warnings.join('\n')).toMatch(/over 2 MB/);
    expect(r.warnings.join('\n')).toMatch(/playlist: allow/);
  });

  it('not connected: no upload', async () => {
    const { yt, dir } = mk();
    yt.setClient(CLIENT, 'GOCSPX-desktop');
    await expect(yt.upload('main', { file: video(dir, 10), title: 't', description: '', tags: [], publishAt: null })).rejects.toThrow(/not connected/);
    expect(g.sessions.size).toBe(0);
  });
});

describe('metadata', () => {
  it('Shorts: vertical or square and <= 180 s, marked #Shorts; made for kids and visibility as she chose', () => {
    expect(shortsFit({ w: 1080, h: 1920, duration: 59 })).toEqual({ ok: true });
    expect(shortsFit({ w: 1920, h: 1080, duration: 30 })).toEqual({ ok: false, why: 'not-vertical' });
    expect(shortsFit({ w: 1080, h: 1920, duration: 75 })).toEqual({ ok: true });
    expect(shortsFit({ w: 1080, h: 1080, duration: 180 })).toEqual({ ok: true });
    expect(shortsFit({ w: 1080, h: 1920, duration: 180.01 })).toEqual({ ok: false, why: 'too-long' });
    for (const duration of [0, -1, NaN, Infinity]) expect(shortsFit({ w: 1080, h: 1920, duration })).toEqual({ ok: false, why: 'unknown' });
    expect(shortsFit({ w: -1080, h: 1920, duration: 75 })).toEqual({ ok: false, why: 'unknown' });
    expect(shortsFit({ w: null, h: null, duration: null }).ok).toBe(false);
    const m = ytMeta({ title: 'Tip', description: 'd', tags: [], publishAt: null, short: true, madeForKids: true, privacy: 'unlisted', categoryId: '999' });
    expect(m.snippet).toMatchObject({ title: 'Tip #Shorts', categoryId: '22' });
    expect(m.status).toEqual({ privacyStatus: 'unlisted', selfDeclaredMadeForKids: true });
    expect(ytMeta({ title: 'x'.repeat(98), description: '', tags: [], publishAt: null, short: true }).snippet.description).toBe('#Shorts');
  });
});

describe('embedded-browser refusals', () => {
  it('Google’s "This browser or app may not be secure" page, by URL and by text', () => {
    expect(embeddedBlock('https://accounts.google.com/v3/signin/rejected?continue=https%3A%2F%2Fwww.youtube.com')).toEqual({ provider: 'google', by: 'url' });
    expect(embeddedBlock('https://accounts.google.com/signin/rejected')).toEqual({ provider: 'google', by: 'url' });
    expect(embeddedBlock('https://accounts.google.com/signin/oauth/error?authError=ZGlzYWxsb3dlZF91c2VyYWdlbnQ&disallowed_useragent=1')).toEqual({ provider: 'google', by: 'url' });
    expect(embeddedBlock('https://accounts.google.com/v3/signin/identifier', "Couldn't sign you in\nThis browser or app may not be secure. Learn more")).toEqual({ provider: 'google', by: 'text' });
    expect(embeddedBlock('https://accounts.google.com/v3/signin/identifier', '无法登录\n此浏览器或应用可能不安全。')).toEqual({ provider: 'google', by: 'text' });
    // the normal sign-in page, other sites: nothing
    expect(embeddedBlock('https://accounts.google.com/v3/signin/identifier', 'Sign in\nUse your Google Account')).toBeNull();
    expect(embeddedBlock('https://www.tiktok.com/login', 'This browser or app may not be secure')).toBeNull();
    expect(embeddedBlock('http://accounts.google.com/signin/rejected')).toBeNull();
    expect(embeddedBlock('not a url')).toBeNull();
  });

  it('Facebook Login’s unsupported-browser page', () => {
    expect(embeddedBlock('https://www.facebook.com/unsupportedbrowser')).toEqual({ provider: 'facebook', by: 'url' });
    expect(embeddedBlock('https://www.facebook.com/v19.0/dialog/oauth?client_id=1', 'This browser isn’t supported')).toEqual({ provider: 'facebook', by: 'text' });
    expect(embeddedBlock('https://www.facebook.com/reel/1', 'unsupported browser')).toBeNull();
  });

  it('only sign-in hosts are read for text; YouTube never opens in the built-in browser', () => {
    expect(maybeBlockPage('https://accounts.google.com/x')).toBe(true);
    expect(maybeBlockPage('https://m.facebook.com/login')).toBe(true);
    expect(maybeBlockPage('https://creator.xiaohongshu.com/')).toBe(false);
    expect(apiOnly('youtube-studio')).toBe(true);
    expect(WEBVIEW_RISK['youtube-studio'].works).toBe('none');
    expect(publishPath('xiaohongshu')).toBe('assisted');
    expect(publishPath('tiktok')).toBe('api-later');
    expect(publishPath('unknown-adapter')).toBe('assisted');
  });

  it('every adapter has a publishing path', () => {
    const { adapters } = loadAdapters([path.resolve(__dirname, '../../adapters')]);
    expect(adapters.length).toBeGreaterThan(15);
    for (const a of adapters) expect(PUBLISH_PATH[a.id], a.id).toBeDefined();
    expect(Object.keys(PUBLISH_PATH).filter((id) => !adapters.some((a) => a.id === id))).toEqual([]);
  });
});

describe('IPC', () => {
  it('validates the YouTube calls', () => {
    expect(() => validateIpc('publish:apiConnect', { id: 'youtube', account: 'main' })).not.toThrow();
    expect(() => validateIpc('publish:apiConnect', { id: 'youtube', account: '../x' })).toThrow();
    expect(() => validateIpc('publish:apiClient', { id: 'youtube', clientId: CLIENT })).not.toThrow();
    const ok = { postId: 'aaaaaaaaaaaa', account: 'main', title: 't', description: '', tags: [], categoryId: '22', privacy: 'public', publishAt: null, madeForKids: false, synthetic: false, short: false, thumbnail: true, playlistId: null };
    expect(() => validateIpc('publish:ytPublish', ok)).not.toThrow();
    expect(() => validateIpc('publish:ytPublish', { ...ok, privacy: 'friends' })).toThrow();
    expect(() => validateIpc('publish:ytPublish', { ...ok, madeForKids: undefined })).toThrow(); // she has to answer
    expect(() => validateIpc('publish:ytPublish', { ...ok, publishAt: '2026-10-20 10:00' })).toThrow();
  });
});


it('detects the Google passkey challenge without mistaking another site or password login', () => {
  expect(embeddedBlock('https://accounts.google.com/v3/signin/challenge/pk')).toEqual({ provider: 'google', by: 'url', kind: 'passkey' });
  expect(embeddedBlock('https://accounts.google.com/v3/signin/challenge', 'Complete sign-in using your passkey')).toEqual({ provider: 'google', by: 'text', kind: 'passkey' });
  expect(embeddedBlock('https://x.com/login', 'Complete sign-in using your passkey')).toBeNull();
  expect(embeddedBlock('https://accounts.google.com/v3/signin/challenge/pwd', 'Enter your password')).toBeNull();
});
