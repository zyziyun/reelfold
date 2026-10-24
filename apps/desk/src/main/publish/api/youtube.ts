// YouTube Data API v3: the only way Reelfold posts to YouTube. Google refuses sign-in inside embedded browsers
// ("This browser or app may not be secure"), so there is no built-in-browser path for YouTube at all.
//   - Sign-in: OAuth 2.0 for installed apps in her SYSTEM browser, PKCE (S256) + a loopback redirect
//     (http://127.0.0.1:<random port>), scopes youtube.upload + youtube.readonly (adding to a playlist needs the
//     broader `youtube` scope, asked only when she turns playlists on).
//   - The OAuth client: Reelfold's own (its ID / secret come from the build environment, never the repo) or her own
//     Google Cloud "Desktop app" client pasted in Settings. Google treats a desktop client's secret as not secret.
//   - Tokens: one refresh token per publishing account, encrypted in the OS keychain (ApiVault); never sent to the
//     renderer, the engine or a log.
//   - Upload: videos.insert as a resumable session, sent in chunks; a dropped connection or a 5xx asks the session
//     how much arrived and resumes from there (exponential backoff). Then thumbnails.set and, when she chose one,
//     playlistItems.insert. A time ahead = private + status.publishAt: YouTube itself publishes at her time.
//   - Nothing is uploaded unless she pressed Publish / Schedule (or switched on scheduled posting herself).
// Report the visibility YouTube actually returns. A private response does not identify the policy/account cause.
import crypto from 'node:crypto';
import { UploadOutcomeUnknown } from '../outcome';
import fs from 'node:fs';
import http from 'node:http';
import type { AddressInfo } from 'node:net';
import path from 'node:path';
import type { ApiSecret, ApiVault } from './vault';
import type { YtPublishResult } from '../../../shared/publish/apiPlatforms';
export { shortsFit } from '../../../shared/publish/apiPlatforms';

export const YT_UPLOAD = 'https://www.googleapis.com/auth/youtube.upload';
export const YT_READONLY = 'https://www.googleapis.com/auth/youtube.readonly';
/** playlists only (playlistItems.insert accepts no narrower scope) */
export const YT_MANAGE = 'https://www.googleapis.com/auth/youtube';
export const YT_SCOPES = [YT_UPLOAD, YT_READONLY];
/** @deprecated the upload scope; kept for older callers */
export const YT_SCOPE = YT_UPLOAD;

export interface GoogleEndpoints {
  auth: string;
  token: string;
  revoke: string;
  /** https://www.googleapis.com/youtube/v3 */
  api: string;
  /** https://www.googleapis.com/upload/youtube/v3 */
  upload: string;
}

export const GOOGLE: GoogleEndpoints = {
  auth: 'https://accounts.google.com/o/oauth2/v2/auth',
  token: 'https://oauth2.googleapis.com/token',
  revoke: 'https://oauth2.googleapis.com/revoke',
  api: 'https://www.googleapis.com/youtube/v3',
  upload: 'https://www.googleapis.com/upload/youtube/v3',
};

export type Fetch = typeof fetch;

export interface OAuthClient {
  clientId: string;
  /** Google shows one for "Desktop app" clients and wants it in the token request; it is not confidential */
  clientSecret?: string;
}

// set by scripts/build.mjs from REELFOLD_GOOGLE_CLIENT_ID / REELFOLD_GOOGLE_CLIENT_SECRET at build time
declare const __REELFOLD_GOOGLE_CLIENT_ID__: string | undefined;
declare const __REELFOLD_GOOGLE_CLIENT_SECRET__: string | undefined;

const CLIENT_ID_RE = /^[\w.-]{5,200}\.apps\.googleusercontent\.com$/;
const SECRET_RE = /^[\x21-\x7e]{8,200}$/;

/** Reelfold's own OAuth client, when this build has one (the build environment, or the environment in development). */
export function builtinClient(env: Record<string, string | undefined> = process.env): OAuthClient | null {
  const id = env.REELFOLD_GOOGLE_CLIENT_ID || (typeof __REELFOLD_GOOGLE_CLIENT_ID__ === 'string' ? __REELFOLD_GOOGLE_CLIENT_ID__ : '');
  const secret = env.REELFOLD_GOOGLE_CLIENT_SECRET || (typeof __REELFOLD_GOOGLE_CLIENT_SECRET__ === 'string' ? __REELFOLD_GOOGLE_CLIENT_SECRET__ : '');
  if (!id || !CLIENT_ID_RE.test(id)) return null;
  return { clientId: id, ...(secret && SECRET_RE.test(secret) ? { clientSecret: secret } : {}) };
}

export interface YtDeps {
  vault: ApiVault;
  fetch?: Fetch;
  /** opens the consent page in the system browser */
  openExternal: (url: string) => Promise<void> | void;
  log?: (msg: string) => void;
  endpoints?: Partial<GoogleEndpoints>;
  /** Reelfold's client (default: builtinClient()) */
  builtin?: OAuthClient | null;
  sleep?: (ms: number) => Promise<void>;
  /** bytes per PUT (a multiple of 256 KiB; default 8 MiB) */
  chunkBytes?: number;
  /** tries per chunk after a network error / 5xx (default 6) */
  maxRetries?: number;
}

export type YtPrivacy = 'public' | 'unlisted' | 'private';

export interface YtVideo {
  file: string;
  title: string;
  description: string;
  tags: string[];
  /** a time ahead: uploaded private, YouTube publishes it then. null: `privacy` now */
  publishAt: Date | null;
  privacy?: YtPrivacy;
  categoryId?: string;
  /** "Made for kids" (COPPA): she answers it; YouTube needs the answer */
  madeForKids?: boolean;
  /** "Altered or synthetic content" */
  synthetic?: boolean;
  /** a Short: vertical / square and <= 180 s (marked #Shorts) */
  short?: boolean;
  thumbnail?: string | null;
  playlistId?: string | null;
}

export interface YtResult {
  id: string;
  url: string;
  /** as YouTube answered; no assumption about the account or API-project restrictions */
  privacy: string;
  publishAt: string | null;
  /** asked public / unlisted but YouTube returned private, or did not retain the requested schedule */
  lockedPrivate: boolean;
  /** the thumbnail / playlist steps that did not work (the video itself is up) */
  warnings: string[];
  uploadStatus?: YtPublishResult['uploadStatus'];
}

export interface YtChannel {
  id: string;
  title: string;
}

export interface YtAccountStatus {
  account: string;
  connected: boolean;
  connectedAt: string | null;
  channel: YtChannel | null;
  playlists: boolean;
}

export interface YtStatus {
  /** which client signs in: Reelfold's, hers, or none yet */
  source: 'reelfold' | 'own' | null;
  hasClient: boolean;
  /** this build carries Reelfold's client */
  builtin: boolean;
  ownClientId: string | null;
  accounts: YtAccountStatus[];
}

/** YouTube's video categories (videoCategories.list, region US); 22 = People & Blogs is the default. */
export const YT_CATEGORIES = ['1', '2', '10', '15', '17', '19', '20', '22', '23', '24', '25', '26', '27', '28', '29'] as const;

const b64url = (b: Buffer) => b.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
const CHUNK_UNIT = 256 * 1024;

/** YouTube refuses < and > in titles / descriptions; title max 100 chars, description 5000 bytes, tags 500 chars. */
export function ytMeta(v: Pick<YtVideo, 'title' | 'description' | 'tags' | 'publishAt'> & Partial<Pick<YtVideo, 'privacy' | 'categoryId' | 'madeForKids' | 'synthetic' | 'short'>>) {
  const clean = (s: string) => s.replace(/[<>]/g, '');
  let title = Array.from(clean(v.title).trim() || 'Untitled').slice(0, 100).join('');
  let description = clean(v.description);
  if (v.short && !/#shorts\b/i.test(`${title} ${description}`)) {
    if (Array.from(title).length + 8 <= 100) title = `${title} #Shorts`;
    else description = description ? `${description}\n\n#Shorts` : '#Shorts';
  }
  while (Buffer.byteLength(description, 'utf8') > 5000) description = Array.from(description).slice(0, -1).join('');
  const tags: string[] = [];
  let len = 0;
  for (const t of v.tags.map((x) => clean(x).replace(/^#/, '').trim()).filter(Boolean)) {
    const add = t.length + (t.includes(' ') ? 2 : 0) + (tags.length ? 1 : 0);
    if (len + add > 500) break;
    tags.push(t);
    len += add;
  }
  const category = v.categoryId && (YT_CATEGORIES as readonly string[]).includes(v.categoryId) ? v.categoryId : '22';
  const kids = v.madeForKids ?? false;
  const extra = v.synthetic === undefined ? {} : { containsSyntheticMedia: v.synthetic };
  return {
    snippet: { title, description, tags, categoryId: category },
    status: v.publishAt
      ? { privacyStatus: 'private', publishAt: v.publishAt.toISOString(), selfDeclaredMadeForKids: kids, ...extra }
      : { privacyStatus: v.privacy ?? 'public', selfDeclaredMadeForKids: kids, ...extra },
  };
}

const vaultKey = (account: string) => `youtube/${account}`;

export class YouTubeApi {
  private access = new Map<string, { token: string; until: number }>();
  private pending: (() => void) | null = null;
  private ep: GoogleEndpoints;
  private builtin: OAuthClient | null;

  constructor(private d: YtDeps) {
    this.ep = { ...GOOGLE, ...(d.endpoints ?? {}) };
    this.builtin = d.builtin === undefined ? builtinClient() : d.builtin;
    this.migrate();
  }

  private get f(): Fetch {
    return this.d.fetch ?? fetch;
  }

  private sleep(ms: number) {
    return this.d.sleep ? this.d.sleep(ms) : new Promise<void>((r) => setTimeout(r, ms));
  }

  /** before per-account tokens: one token under "youtube" = the "main" account, the client = hers */
  private migrate() {
    try {
      const old = this.d.vault.get('youtube');
      if (!old.refreshToken) return;
      this.d.vault.set(vaultKey('main'), { refreshToken: old.refreshToken, scope: old.scope, connectedAt: old.connectedAt });
      this.d.vault.set('youtube', { refreshToken: undefined, scope: undefined, connectedAt: undefined, source: old.source ?? (old.clientId ? 'own' : undefined) });
    } catch {
      /* no keychain: nothing to move */
    }
  }

  /** the client that signs in now */
  client(): OAuthClient | null {
    const s = this.d.vault.get('youtube');
    const source = s.source ?? (s.clientId ? 'own' : this.builtin ? 'reelfold' : undefined);
    if (source === 'own' && s.clientId) return { clientId: s.clientId, ...(s.clientSecret ? { clientSecret: s.clientSecret } : {}) };
    if (source === 'reelfold' && this.builtin) return this.builtin;
    return null;
  }

  private source(): 'reelfold' | 'own' | null {
    const s = this.d.vault.get('youtube');
    const src = s.source ?? (s.clientId ? 'own' : this.builtin ? 'reelfold' : null);
    return src === 'reelfold' && !this.builtin ? null : (src ?? null);
  }

  /** Her own Google Cloud OAuth client (Desktop app). Tokens from another client stop working: every account
   * connects again. */
  setClient(clientId: string, clientSecret?: string) {
    const id = clientId.trim();
    const secret = clientSecret?.trim() || undefined;
    if (!CLIENT_ID_RE.test(id)) throw new Error('client ID: the "….apps.googleusercontent.com" ID of a Desktop-app OAuth client');
    if (secret !== undefined && !SECRET_RE.test(secret)) throw new Error('client secret: the secret shown next to that client ID');
    this.d.vault.set('youtube', { source: 'own', clientId: id, clientSecret: secret });
    this.forgetTokens();
  }

  /** Sign in with Reelfold's client (only when this build has one). */
  useBuiltin() {
    if (!this.builtin) throw new Error('this build has no Reelfold OAuth client: add your own Google Cloud OAuth client');
    if (this.source() === 'reelfold') return;
    this.d.vault.set('youtube', { source: 'reelfold' });
    this.forgetTokens();
  }

  /** Remove her own client (back to Reelfold's when there is one). */
  forgetClient() {
    this.d.vault.set('youtube', { source: this.builtin ? 'reelfold' : undefined, clientId: undefined, clientSecret: undefined });
    this.forgetTokens();
  }

  private forgetTokens() {
    for (const a of this.accountsInVault()) this.d.vault.set(vaultKey(a), null);
    this.access.clear();
  }

  private accountsInVault(): string[] {
    return this.d.vault.ids().filter((k) => k.startsWith('youtube/')).map((k) => k.slice('youtube/'.length));
  }

  accountStatus(account: string): YtAccountStatus {
    const s = this.d.vault.get(vaultKey(account));
    return { account, connected: !!s.refreshToken, connectedAt: s.connectedAt ?? null, channel: s.channel ?? null, playlists: (s.scope ?? '').split(/\s+/).includes(YT_MANAGE) };
  }

  status(accounts: string[] = []): YtStatus {
    const s = this.d.vault.get('youtube');
    const all = [...new Set([...accounts, ...this.accountsInVault()])];
    return {
      source: this.source(),
      hasClient: !!this.client(),
      builtin: !!this.builtin,
      ownClientId: s.clientId ?? null,
      accounts: all.map((a) => this.accountStatus(a)),
    };
  }

  /** Stop waiting for a consent she abandoned. */
  cancelConnect() {
    this.pending?.();
  }

  /** OAuth in the system browser; resolves once Google redirected back to the loopback port (or after 5 minutes). */
  async connect(account: string, opts: { playlists?: boolean; timeoutMs?: number } = {}): Promise<YtAccountStatus> {
    const client = this.client();
    if (!client) throw new Error('choose how to sign in first: Reelfold’s Google client or your own');
    this.cancelConnect();
    const scopes = [...YT_SCOPES, ...(opts.playlists ? [YT_MANAGE] : [])];
    const verifier = b64url(crypto.randomBytes(48));
    const challenge = b64url(crypto.createHash('sha256').update(verifier).digest());
    const state = b64url(crypto.randomBytes(16));
    const timeoutMs = opts.timeoutMs ?? 5 * 60_000;
    const { code, redirect } = await new Promise<{ code: string; redirect: string }>((resolve, reject) => {
      let settled = false;
      let port = 0;
      const page = (ok: boolean) =>
        `<!doctype html><meta charset="utf-8"><title>Reelfold</title><body style="font:16px system-ui;margin:4em auto;max-width:32em;text-align:center">${
          ok ? '<h2>Reelfold is connected to YouTube</h2><p>You can close this tab and go back to Reelfold.</p>' : '<h2>Not connected</h2><p>Go back to Reelfold and try again.</p>'
        }</body>`;
      const server = http.createServer((req, res) => {
        const u = new URL(req.url ?? '/', 'http://127.0.0.1');
        if (u.pathname !== '/') {
          res.writeHead(404).end();
          return;
        }
        if (u.searchParams.get('state') !== state) {
          // not our redirect (a stale tab, a forged request): refuse, keep waiting for the real one
          res.writeHead(400, { 'Content-Type': 'text/html; charset=utf-8' }).end(page(false));
          finish(new Error('the sign-in answer did not match: try again'), null);
          return;
        }
        const c = u.searchParams.get('code');
        res.writeHead(c ? 200 : 400, { 'Content-Type': 'text/html; charset=utf-8' });
        res.end(page(!!c));
        const err = u.searchParams.get('error');
        finish(c ? null : new Error(err === 'access_denied' ? 'you did not allow access in Google’s page' : err || 'the consent was not completed'), c);
      });
      const timer = setTimeout(() => finish(new Error('no answer from Google within 5 minutes: try again'), null), timeoutMs);
      const finish = (err: Error | null, c: string | null) => {
        if (settled) return;
        settled = true;
        this.pending = null;
        clearTimeout(timer);
        server.close();
        if (err || !c) reject(err ?? new Error('no code'));
        else resolve({ code: c, redirect: `http://127.0.0.1:${port}` });
      };
      this.pending = () => finish(new Error('sign-in cancelled'), null);
      server.on('error', (e) => finish(e, null));
      server.listen(0, '127.0.0.1', () => {
        port = (server.address() as AddressInfo).port;
        const q = new URLSearchParams({
          client_id: client.clientId,
          redirect_uri: `http://127.0.0.1:${port}`,
          response_type: 'code',
          scope: scopes.join(' '),
          code_challenge: challenge,
          code_challenge_method: 'S256',
          state,
          access_type: 'offline',
          include_granted_scopes: 'true',
          prompt: 'consent select_account',
        });
        void Promise.resolve(this.d.openExternal(`${this.ep.auth}?${q}`)).catch((e: Error) => finish(e, null));
      });
    });
    const r = await this.f(this.ep.token, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        code,
        client_id: client.clientId,
        ...(client.clientSecret ? { client_secret: client.clientSecret } : {}),
        redirect_uri: redirect,
        grant_type: 'authorization_code',
        code_verifier: verifier,
      }),
    });
    const j = (await r.json().catch(() => ({}))) as { access_token?: string; refresh_token?: string; expires_in?: number; scope?: string; error_description?: string; error?: string };
    if (!r.ok || !j.refresh_token) throw new Error(`Google did not grant access: ${j.error_description || j.error || r.status}`);
    const granted = (j.scope ?? scopes.join(' ')).split(/\s+/);
    if (!granted.includes(YT_UPLOAD)) throw new Error('the permission to upload videos was not ticked in Google’s page: connect again and allow it');
    if (j.access_token) this.access.set(account, { token: j.access_token, until: Date.now() + (j.expires_in ?? 3000) * 1000 - 60_000 });
    let channel: YtChannel | null = null;
    if (j.access_token && granted.includes(YT_READONLY)) {
      const c = await this.f(`${this.ep.api}/channels?part=snippet&mine=true`, { headers: { Authorization: `Bearer ${j.access_token}` } }).catch(() => null);
      const cj = c && c.ok ? ((await c.json().catch(() => ({}))) as { items?: { id: string; snippet?: { title?: string } }[] }) : null;
      if (cj && !cj.items?.length) throw new Error('this Google account has no YouTube channel yet: create one on youtube.com, then connect again');
      if (cj?.items?.[0]) channel = { id: cj.items[0].id, title: cj.items[0].snippet?.title ?? cj.items[0].id };
    }
    const rec: ApiSecret = { refreshToken: j.refresh_token, scope: granted.join(' '), connectedAt: new Date().toISOString(), channel: channel ?? undefined };
    this.d.vault.set(vaultKey(account), rec);
    this.d.log?.(`[youtube] ${account} connected${channel ? ` (${channel.id})` : ''}`);
    return this.accountStatus(account);
  }

  async disconnect(account: string) {
    const s = this.d.vault.get(vaultKey(account));
    if (s.refreshToken) {
      await this.f(this.ep.revoke, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams({ token: s.refreshToken }) }).catch(() => undefined);
    }
    this.d.vault.set(vaultKey(account), null);
    this.access.delete(account);
  }

  private async token(account: string, fresh = false): Promise<string> {
    const cached = this.access.get(account);
    if (!fresh && cached && cached.until > Date.now()) return cached.token;
    const s = this.d.vault.get(vaultKey(account));
    const client = this.client();
    if (!s.refreshToken || !client) throw new Error('YouTube is not connected: sign in with Google in your browser first');
    const r = await this.f(this.ep.token, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ client_id: client.clientId, ...(client.clientSecret ? { client_secret: client.clientSecret } : {}), refresh_token: s.refreshToken, grant_type: 'refresh_token' }),
    });
    const j = (await r.json().catch(() => ({}))) as { access_token?: string; expires_in?: number; error?: string };
    if (!r.ok || !j.access_token) {
      if (j.error === 'invalid_grant') this.d.vault.set(vaultKey(account), null);
      throw new Error(`YouTube sign-in expired or was revoked (${j.error ?? r.status}): sign in with Google again`);
    }
    this.access.set(account, { token: j.access_token, until: Date.now() + (j.expires_in ?? 3000) * 1000 - 60_000 });
    return j.access_token;
  }

  /** Her playlists (playlists.list, youtube.readonly). */
  async playlists(account: string): Promise<{ id: string; title: string }[]> {
    const token = await this.token(account);
    const r = await this.f(`${this.ep.api}/playlists?part=snippet&mine=true&maxResults=50`, { headers: { Authorization: `Bearer ${token}` } });
    if (!r.ok) throw new Error(`YouTube did not list the playlists: ${await errText(r)}`);
    const j = (await r.json()) as { items?: { id: string; snippet?: { title?: string } }[] };
    return (j.items ?? []).map((p) => ({ id: p.id, title: p.snippet?.title ?? p.id }));
  }

  /** Read only a known uploaded video through the fixed official endpoint, never fetch the receipt URL. */
  async videoStatus(account: string, previous: YtPublishResult): Promise<YtPublishResult> {
    let id = previous.id;
    if (!id) {
      const u = new URL(previous.url);
      if (u.protocol !== 'https:' || u.username || u.password || u.port) throw new Error('Invalid YouTube video link');
      if (u.hostname === 'youtu.be') id = u.pathname.slice(1);
      else if (['youtube.com', 'www.youtube.com'].includes(u.hostname) && u.pathname === '/watch') id = u.searchParams.get('v') ?? undefined;
    }
    if (!id || !/^[\w-]{1,64}$/.test(id)) throw new Error('No verified YouTube video ID');
    const token = await this.token(account);
    const r = await this.f(`${this.ep.api}/videos?part=status&id=${encodeURIComponent(id)}`, {
      headers: { Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(15_000),
    });
    if (!r.ok) throw new Error(`YouTube status unavailable: ${await errText(r)}`);
    const j = await r.json() as { items?: { id: string; status?: { privacyStatus?: string; publishAt?: string; uploadStatus?: string; failureReason?: string; rejectionReason?: string } }[] };
    const status = j.items?.find(v => v.id === id)?.status;
    if (!status) throw new Error('Video unavailable to this account; check YouTube Studio');
    const privacy = ['public', 'private', 'unlisted'].includes(status.privacyStatus ?? '') ? status.privacyStatus! : 'unknown';
    const publishAt = typeof status.publishAt === 'string' && /T.*(?:Z|[+-]\d\d:\d\d)$/.test(status.publishAt) && Number.isFinite(Date.parse(status.publishAt)) ? new Date(status.publishAt).toISOString() : null;
    const uploadStatus = ['uploaded', 'processed', 'failed', 'rejected', 'deleted'].includes(status.uploadStatus ?? '') ? status.uploadStatus as NonNullable<YtPublishResult['uploadStatus']> : 'unknown';
    const reason = uploadStatus === 'failed' ? status.failureReason : uploadStatus === 'rejected' ? status.rejectionReason : null;
    return { id, url: `https://youtu.be/${id}`, privacy, publishAt, uploadStatus,
      lockedPrivate: privacy === 'private' && !publishAt && previous.lockedPrivate,
      warnings: previous.warnings, checkedAt: new Date().toISOString(),
      ...(typeof reason === 'string' ? { failureReason: reason.slice(0, 200) } : {}),
    };
  }

  /** Query only the saved session. Never create another upload while its outcome is unknown. */
  async recover(postId: string, resume = false): Promise<{ account: string; result: YtPublishResult } | null> {
    const key = `youtube-upload/${postId}`;
    const saved = this.d.vault.get(key);
    if (saved.uploadReceipt) return saved.uploadReceipt;
    const session = saved.uploadSession;
    if (!session) return null;
    const url = new URL(session.url);
    if (url.origin !== new URL(this.ep.upload).origin || url.username || url.password ||
        !Number.isSafeInteger(session.size) || session.size <= 0) throw new Error('Invalid saved upload session');
    const token = await this.token(session.account);
    // 308 means Resume Incomplete here, not a redirect. Inspect it without following Location.
    const r = await this.f(url.toString(), { method: 'PUT', redirect: 'manual',
      headers: { Authorization: `Bearer ${token}`, 'Content-Length': '0', 'Content-Range': `bytes */${session.size}` },
      signal: AbortSignal.timeout(15_000) });
    let done: Inserted;
    if (r.status === 308) {
      if (!resume) return null;
      if (!session.file || !session.sha256 || !fs.existsSync(session.file) || fs.statSync(session.file).size !== session.size ||
          await fileDigest(session.file) !== session.sha256) throw new Error('The original upload file is unavailable or changed; check YouTube Studio');
      done = await this.transfer(session.account, session.file, session.url, session.size, nextOffset(r, session.size));
    } else {
      if (r.status !== 200 && r.status !== 201) throw new Error('Upload result is still unconfirmed; check YouTube Studio');
      done = await r.json() as Inserted;
    }
    const result = uploadResult(done, session.privacy, session.publishAt);
    if (session.followups) result.warnings.push('Recovered upload: check the cover and playlist in YouTube Studio.');
    const receipt = { account: session.account, result };
    this.d.vault.set(key, { uploadReceipt: receipt, uploadSession: undefined });
    return receipt;
  }

  /** videos.insert (resumable, chunked, resumed after errors), then the thumbnail and the playlist. */
  async upload(account: string, v: YtVideo, onProgress?: (sent: number, total: number) => void, postId?: string): Promise<YtResult> {
    const receiptKey = postId ? `youtube-upload/${postId}` : null;
    if (postId) {
      const saved = this.d.vault.get(receiptKey!);
      if (saved.uploadSession || saved.uploadReceipt) {
        const recovered = await this.recover(postId);
        if (recovered) {
          if (recovered.account !== account) throw new UploadOutcomeUnknown('This post was uploaded with another account. Check YouTube Studio.');
          return recovered.result as YtResult;
        }
        throw new UploadOutcomeUnknown('The previous upload is still unconfirmed. Check YouTube Studio.');
      }
    }
    const size = fs.statSync(v.file).size;
    if (!size) throw new Error('the video file is empty');
    const meta = ytMeta(v);
    const sha256 = receiptKey ? await fileDigest(v.file) : undefined;
    const token = await this.token(account);
    const init = await this.f(`${this.ep.upload}/videos?uploadType=resumable&part=snippet,status`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json; charset=UTF-8',
        'X-Upload-Content-Length': String(size),
        'X-Upload-Content-Type': 'video/*',
      },
      body: JSON.stringify(meta),
    });
    const loc = init.headers.get('location');
    if (!init.ok || !loc) throw new Error(`YouTube refused the upload: ${await errText(init)}`);
    if (new URL(loc).origin !== new URL(this.ep.upload).origin) throw new Error('unexpected upload location');

    if (receiptKey) this.d.vault.set(receiptKey, { uploadSession: { url: loc, size, account, file: v.file, sha256,
      privacy: meta.status.privacyStatus, publishAt: v.publishAt?.toISOString() ?? null,
      followups: !!(v.thumbnail || v.playlistId) } });

    let done: Inserted & { id: string };
    try { done = await this.transfer(account, v.file, loc, size, 0, onProgress); }
    catch (e) {
      if (receiptKey) throw new UploadOutcomeUnknown('Upload interrupted; its saved session will be checked before retrying.');
      throw e;
    }
    const id = done.id;
    const privacy = ['public', 'private', 'unlisted'].includes(done.status?.privacyStatus ?? '') ? done.status!.privacyStatus! : 'unknown';
    const asked = meta.status.privacyStatus;
    const warnings: string[] = [];
    if (v.thumbnail) {
      const w = await this.setThumbnail(account, id, v.thumbnail);
      if (w) warnings.push(w);
    }
    if (v.playlistId) {
      const w = await this.addToPlaylist(account, id, v.playlistId);
      if (w) warnings.push(w);
    }
    this.d.log?.(`[youtube] uploaded ${id} (${privacy}${'publishAt' in meta.status ? `, at ${meta.status.publishAt}` : ''})`);
    const result = uploadResult(done, asked, v.publishAt?.toISOString() ?? null);
    result.warnings = warnings;
    if (receiptKey) {
      try { this.d.vault.set(receiptKey, { uploadReceipt: { account, result }, uploadSession: undefined }); }
      catch { throw new UploadOutcomeUnknown('Video uploaded, but its receipt could not be saved. Check YouTube Studio.'); }
    }
    return result;
  }

  /** Shared bounded transfer for fresh uploads and verified restart recovery. */
  private async transfer(account: string, file: string, loc: string, size: number, start: number, onProgress?: (sent: number, total: number) => void): Promise<Inserted & { id: string }> {
    let token = await this.token(account);
    const unit = Math.max(1, Math.round((this.d.chunkBytes ?? 32 * CHUNK_UNIT) / CHUNK_UNIT)) * CHUNK_UNIT;
    const maxRetries = this.d.maxRetries ?? 6;
    let offset = start;
    let tries = 0;
    let highWater = start;
    let authRetried = false;
    let done = null as Inserted | null;
    let mayHaveCompleted = false;
    const fd = fs.openSync(file, 'r');
    try {
      while (!done) {
        const end = Math.min(offset + unit, size);
        const buf = Buffer.alloc(end - offset);
        if (fs.readSync(fd, buf, 0, buf.length, offset) !== buf.length) throw new Error('The video file changed during upload');
        let r: Response | null = null;
        try {
          if (end === size) mayHaveCompleted = true;
          r = await this.f(loc, {
            method: 'PUT', redirect: 'manual', signal: AbortSignal.timeout(120_000),
            headers: { Authorization: `Bearer ${token}`, 'Content-Length': String(buf.length), 'Content-Range': offset === size ? `bytes */${size}` : `bytes ${offset}-${end - 1}/${size}` },
            body: buf,
          });
        } catch (e) {
          this.d.log?.(`[youtube] chunk at ${offset} failed: ${(e as Error).message}`);
        }
        if (r && (r.status === 200 || r.status === 201)) {
          done = (await r.json().catch(() => ({}))) as Inserted;
          break;
        }
        if (r && r.status === 308) {
          offset = nextOffset(r, size);
          if (offset > highWater) {
            highWater = offset;
            tries = 0;
          } else if (++tries > maxRetries) {
            throw new Error(`YouTube upload made no progress after ${maxRetries} retries`);
          }
          const delay = Math.max(retryAfter(r), tries ? Math.min(64_000, 1000 * 2 ** (tries - 1)) : 0);
          if (delay) await this.sleep(delay);
          onProgress?.(offset, size);
          continue;
        }
        if (r && r.status === 401 && !authRetried) {
          authRetried = true;
          token = await this.token(account, true);
        } else if (r && (r.status === 404 || r.status === 410)) {
          throw new Error('the upload session expired: press Publish again to start over');
        } else if (r && !retryable(r.status)) {
          throw new Error(`YouTube upload failed: ${await errText(r)}`);
        } else {
          if (++tries > maxRetries) throw new Error(`YouTube upload failed after ${maxRetries} retries${r ? ` (${r.status})` : ' (network)'}`);
          await this.sleep(Math.min(64_000, 1000 * 2 ** (tries - 1)) + Math.floor(Math.random() * 250));
        }
        // ask the session how much it has, then go on from there
        const q = await this.f(loc, { method: 'PUT', redirect: 'manual', signal: AbortSignal.timeout(120_000), headers: { Authorization: `Bearer ${token}`, 'Content-Length': '0', 'Content-Range': `bytes */${size}` } }).catch(() => null);
        if (q && (q.status === 200 || q.status === 201)) {
          done = (await q.json().catch(() => ({}))) as Inserted;
        } else if (q && q.status === 308) {
          offset = nextOffset(q, size);
          if (offset > highWater) {
            highWater = offset;
            tries = 0;
          }
          const delay = retryAfter(q);
          if (delay) await this.sleep(delay);
          onProgress?.(offset, size);
        } else if (q && (q.status === 404 || q.status === 410)) {
          throw new Error('the upload session expired: press Publish again to start over');
        }
        // anything else: the next PUT tries again from the same offset
      }
    } catch (e) {
      if (mayHaveCompleted) throw new UploadOutcomeUnknown(`YouTube upload outcome is unconfirmed. Check YouTube Studio before uploading again. ${e instanceof Error ? e.message : String(e)}`);
      throw e;
    } finally {
      fs.closeSync(fd);
    }
    if (!done?.id) throw new UploadOutcomeUnknown('YouTube did not return the new video ID. Check YouTube Studio before uploading again.');
    onProgress?.(size, size);
    return done as Inserted & { id: string };
  }

  /** thumbnails.set: JPEG / PNG up to 2 MB; a channel that is not phone-verified cannot set one. -> a warning or null */
  async setThumbnail(account: string, videoId: string, file: string): Promise<string | null> {
    try {
      const ext = path.extname(file).toLowerCase();
      const type = ext === '.png' ? 'image/png' : ext === '.jpg' || ext === '.jpeg' ? 'image/jpeg' : null;
      if (!type) return 'thumbnail: only JPEG or PNG covers can be set';
      const body = fs.readFileSync(file);
      if (body.length > 2 * 1024 * 1024) return 'thumbnail: the cover is over 2 MB, set it in YouTube Studio';
      const token = await this.token(account);
      const r = await this.f(`${this.ep.upload}/thumbnails/set?videoId=${encodeURIComponent(videoId)}&uploadType=media`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': type, 'Content-Length': String(body.length) },
        body,
      });
      if (r.ok) return null;
      const e = await errText(r);
      return /forbidden|403/.test(e) ? 'thumbnail: YouTube allows custom thumbnails after the channel is verified (youtube.com/verify)' : `thumbnail: ${e}`;
    } catch (e) {
      return `thumbnail: ${(e as Error).message}`;
    }
  }

  /** playlistItems.insert (needs the playlists permission). -> a warning or null */
  async addToPlaylist(account: string, videoId: string, playlistId: string): Promise<string | null> {
    if (!this.accountStatus(account).playlists) return 'playlist: allow Reelfold to manage playlists (connect again with playlists on)';
    try {
      const token = await this.token(account);
      const r = await this.f(`${this.ep.api}/playlistItems?part=snippet`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json; charset=UTF-8' },
        body: JSON.stringify({ snippet: { playlistId, resourceId: { kind: 'youtube#video', videoId } } }),
      });
      return r.ok ? null : `playlist: ${await errText(r)}`;
    } catch (e) {
      return `playlist: ${(e as Error).message}`;
    }
  }
}

type Inserted = { id?: string; status?: { privacyStatus?: string; publishAt?: string; uploadStatus?: string } };

function uploadResult(done: Inserted, askedPrivacy: string, askedPublishAt: string | null): YtResult {
  if (!done.id || !/^[\w-]{1,64}$/.test(done.id)) throw new UploadOutcomeUnknown('YouTube did not return a valid video ID. Check YouTube Studio.');
  const privacy = ['public', 'private', 'unlisted'].includes(done.status?.privacyStatus ?? '') ? done.status!.privacyStatus! : 'unknown';
  return { id: done.id, url: `https://youtu.be/${done.id}`, privacy,
    uploadStatus: ['uploaded', 'processed', 'failed', 'rejected', 'deleted'].includes(done.status?.uploadStatus ?? '') ? done.status!.uploadStatus as YtPublishResult['uploadStatus'] : 'unknown',
    publishAt: done.status?.publishAt ?? null,
    lockedPrivate: askedPrivacy !== 'private' ? privacy === 'private' : !!askedPublishAt && !!done.status && !done.status.publishAt,
    warnings: [],
  };
}

/** 308 Resume Incomplete: "Range: bytes=0-N" -> N+1; no Range: nothing arrived yet. */
function nextOffset(r: Response, size: number): number {
  const range = r.headers.get('range');
  if (range === null) return 0;
  const m = /^bytes=0-(\d+)$/.exec(range);
  const offset = m ? Number(m[1]) + 1 : NaN;
  if (!Number.isSafeInteger(offset) || offset < 1 || offset > size) throw new Error('YouTube returned an invalid upload range');
  return offset;
}

function retryAfter(r: Response): number {
  const value = r.headers.get('retry-after');
  if (!value) return 0;
  const ms = /^\d+$/.test(value) ? Number(value) * 1000 : Date.parse(value) - Date.now();
  return Number.isFinite(ms) ? Math.max(0, ms) : 0;
}

const retryable = (s: number) => s === 408 || s === 429 || s >= 500;

async function errText(r: Response): Promise<string> {
  try {
    const j = (await r.json()) as { error?: { message?: string; errors?: { reason?: string }[] } };
    return `${r.status} ${j.error?.errors?.[0]?.reason ?? ''} ${j.error?.message ?? ''}`.replace(/\s+/g, ' ').trim();
  } catch {
    return String(r.status);
  }
}

async function fileDigest(file: string): Promise<string> {
  const hash = crypto.createHash('sha256');
  for await (const chunk of fs.createReadStream(file)) hash.update(chunk);
  return hash.digest('hex');
}
