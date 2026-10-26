// Runs the app with the Studio off (DESK_STUDIO=0) and the mock engine, window hidden, isolated profile, Playwright's
// mock keychain. Publishing accounts with YouTube on the official Data API:
//   - Settings › Publishing accounts: no Reelfold client in this build -> her own Google Cloud client through the
//     guide; "Add YouTube" signs in with Google in the SYSTEM browser (never the built-in browser); connected as the
//     channel; the built-in browser refuses to open YouTube;
//   - Publishing accounts: each platform says its path (official API / built-in browser); YouTube's Sign in opens the
//     Google sheet; a TikTok "Continue with Google" that lands on Google's "This browser or app may not be secure"
//     page shows the plain explanation instead (back to TikTok's own login / Upload in your browser);
//   - a YouTube Short post: the form, Schedule only after she answers Made for kids, uploaded through the API,
//     marked posted with its link;
//   - Upload in your browser: the upload page in her browser, the file shown, the title / tags copied, posted by link.
// Only the network and the OS hand-offs are faked, in the test: shell.openExternal (the "browser" consents and Google
// redirects to the app's loopback port), Google's endpoints (main's fetch), the reveal / clipboard calls (recorded,
// so her Finder and clipboard are not touched), and the TikTok partition's pages.
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { closeApp } from './closeApp';

let app: ElectronApplication;
let page: Page;
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vsdesk-yt-'));
const watch = path.join(tmp, 'demos');
const work = path.join(watch, 'shorts');
const SHOTS = process.env.PUBTEST_SHOTS || path.join(tmp, 'shots');
const pad = (n: number) => String(n).padStart(2, '0');
const at = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
const CLIENT = '1234-e2e.apps.googleusercontent.com';

interface Rec {
  opened: string[];
  requestedScopes?: string;
  shown: string[];
  copied: string[];
  meta: { snippet: { title: string; categoryId: string }; status: Record<string, unknown> } | null;
  puts: number;
  thumbs: number;
  verifier: string | null;
  remote?: Record<string, string>;
  reads?: number;
  inserts?: number;
  failNext?: boolean;
  incomplete?: boolean;
  failPlaylists?: boolean;
}
const rec = () => app.evaluate(() => (globalThis as unknown as { __yt: Rec }).__yt);

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const fin = path.join(work, 'final');
  fs.mkdirSync(fin, { recursive: true });
  execFileSync('ffmpeg', ['-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=180x320:rate=30:duration=90', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=90', '-shortest', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', path.join(fin, 'A_tip.mp4')]);
  execFileSync('ffmpeg', ['-v', 'error', '-y', '-i', path.join(fin, 'A_tip.mp4'), '-frames:v', '1', path.join(fin, 'A_tip_cover.jpg')]);
  fs.writeFileSync(path.join(fin, 'post.md'), '# Posts\n\n## A_tip.mp4  ·  cover A_tip_cover.jpg\n\nOne tip a day\n\nThe body text.\n\n#tips #creator\n');
  const env: Record<string, string> = { ...(process.env as Record<string, string>), DESK_ENGINE_MOCK: '1', DESK_USER_DATA: path.join(tmp, 'profile'), VSTUDIO_HOME: path.join(tmp, 'vhome'), DESK_HISTORY_WATCH: watch, DESK_STUDIO: '0', DESK_HIDE_WINDOW: '1', DESK_SHARED_CACHE: path.join(tmp, 'cache'), DESK_HF_HUB: '', DESK_SKIP_FIRST_RUN: '1', VITE_DEV_SERVER_URL: '' };
  delete env.REELFOLD_GOOGLE_CLIENT_ID; // this test build has no Reelfold client: she brings her own
  delete env.REELFOLD_GOOGLE_CLIENT_SECRET;
  app = await electron.launch({ args: [path.resolve(import.meta.dirname, '../..')], env });
  // the OS hand-offs and Google, faked in the test (the app code runs as shipped)
  await app.evaluate(({ shell, clipboard }) => {
    const g = globalThis as unknown as { __yt: Rec };
    g.__yt = { opened: [], shown: [], copied: [], meta: null, puts: 0, thumbs: 0, verifier: null };
    const real = globalThis.fetch;
    shell.openExternal = async (url: string) => {
      g.__yt.opened.push(url);
      const u = new URL(url);
      if (u.hostname === 'accounts.google.com' && u.pathname === '/o/oauth2/v2/auth') {
        // she consents in her browser; Google redirects to the app's loopback port
        const q = u.searchParams;
        g.__yt.requestedScopes = q.get('scope') ?? '';
        setTimeout(() => void real(`${q.get('redirect_uri')}/?code=e2e-code&state=${q.get('state')}`).catch(() => undefined), 50);
      }
    };
    (shell as { showItemInFolder: (p: string) => void }).showItemInFolder = (p: string) => void g.__yt.shown.push(p);
    (clipboard as { writeText: (t: string) => void }).writeText = (t: string) => void g.__yt.copied.push(t);
    const json = (status: number, j: unknown, h: Record<string, string> = {}) => new Response(JSON.stringify(j), { status, headers: { 'content-type': 'application/json', ...h } });
    globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
      const url = input instanceof Request ? input.url : String(input);
      const u = new URL(url);
      if (url === 'https://oauth2.googleapis.com/token') {
        const f = new URLSearchParams(String(init?.body));
        if (f.get('grant_type') === 'authorization_code' && f.get('code') === 'e2e-code' && f.get('client_id') === '1234-e2e.apps.googleusercontent.com') {
          g.__yt.verifier = f.get('code_verifier');
          return json(200, { access_token: 'at', refresh_token: 'rt', expires_in: 3600, scope: g.__yt.requestedScopes });
        }
        if (f.get('grant_type') === 'refresh_token') return json(200, { access_token: 'at', expires_in: 3600 });
        return json(400, { error: 'invalid_grant' });
      }
      if (u.hostname === 'oauth2.googleapis.com' && u.pathname === '/revoke') return json(200, {});
      if (u.hostname === 'www.googleapis.com') {
        if (u.pathname === '/youtube/v3/videos') {
          g.__yt.reads = (g.__yt.reads ?? 0) + 1;
          return json(200, { items: g.__yt.remote ? [{ id: u.searchParams.get('id'), status: g.__yt.remote }] : [] });
        }
        if (u.pathname === '/youtube/v3/channels') return json(200, { items: [{ id: 'UCe2e', snippet: { title: 'E2E Channel' } }] });
        if (u.pathname === '/youtube/v3/playlists') return g.__yt.failPlaylists ? json(503, { error: { message: 'Playlist temporarily unavailable' } }) : json(200, { items: [] });
        if (u.pathname === '/upload/youtube/v3/videos' && init?.method === 'POST') {
          g.__yt.inserts = (g.__yt.inserts ?? 0) + 1;
          g.__yt.meta = JSON.parse(String(init.body));
          return new Response('', { status: 200, headers: { location: 'https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=E2E' } });
        }
        if (u.pathname === '/upload/youtube/v3/videos' && init?.method === 'PUT') {
          g.__yt.puts++;
          if (g.__yt.failNext) {
            g.__yt.failNext = false;
            g.__yt.incomplete = true;
            return json(400, { error: { message: 'Interrupted test upload' } });
          }
          if (g.__yt.incomplete) {
            if (new Headers(init.headers).get('Content-Range')?.startsWith('bytes */')) return new Response(null, { status: 308 });
            await new Promise(resolve => setTimeout(resolve, 1000));
            g.__yt.incomplete = false;
          }
          return json(201, { id: 'e2eVid', status: { privacyStatus: 'private', uploadStatus: 'processed', publishAt: (g.__yt.meta?.status as { publishAt?: string }).publishAt } });
        }
        if (u.pathname === '/upload/youtube/v3/thumbnails/set') {
          g.__yt.thumbs++;
          return json(200, {});
        }
      }
      return real(input, init);
    }) as typeof fetch;
  });
  // TikTok's partition: its login page sends "Continue with Google" once to Google's refusal page
  await app.evaluate(async ({ session }) => {
    let sent = 0;
    session.fromPartition('persist:tiktok-main').protocol.handle('https', (req) => {
      const u = new URL(req.url);
      const html = (b: string) => new Response(`<!doctype html><meta charset="utf-8"><title>t</title><body>${b}</body>`, { headers: { 'content-type': 'text/html; charset=utf-8' } });
      if (u.hostname === 'accounts.google.com') return html("<h1>Couldn't sign you in</h1><p>This browser or app may not be secure.</p>");
      if (u.hostname === 'www.tiktok.com' && u.pathname.startsWith('/login'))
        return html(sent++ === 0 ? "<script>location.href='https://accounts.google.com/v3/signin/rejected?continue=x'</script>" : '<h1>Log in to TikTok</h1><input type="password">');
      return new Response('offline in tests', { status: 404 });
    });
  });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForURL(/^app:\/\/desk\//);
  await page.evaluate(async () => {
    localStorage.setItem('i18n.strict', '1');
    await window.desk.publish.addAccount('xiaohongshu', 'main');
    await window.desk.setSettings({ defaultPlatforms: ['youtube-shorts', 'xiaohongshu:full'] });
  });
  await page.reload();
  await page.waitForURL(/^app:\/\/desk\//);
});

test.afterAll(async () => {
  await closeApp(app);
});

const hash = (h: string) => page.evaluate((x) => (location.hash = x), h);
const api = <T,>(p: string, body?: unknown) =>
  page.evaluate(
    async ([u, b]) => {
      const info = await window.desk.engineInfo();
      const r = await fetch(info.baseUrl + u, { method: b ? 'POST' : 'GET', headers: { Authorization: `Bearer ${info.token}`, 'Content-Type': 'application/json' }, body: b ? JSON.stringify(b) : undefined });
      return r.json();
    },
    [p, body] as const,
  ) as Promise<T>;
type Row = { id: string; clip: string; platform: string; at: string; state: string; url?: string; via?: string };

test('Settings: her own Google Cloud client, then YouTube signs in with Google in the system browser', async () => {
  await hash('#/settings/accounts');
  await expect(page.getByTestId('settings-api')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('yt-no-builtin')).toBeVisible();
  await expect(page.getByTestId('yt-client')).toHaveAttribute('data-source', 'none');
  await expect(page.getByTestId('api-youtube-add')).toBeDisabled(); // no client yet
  await page.getByTestId('yt-own-add').click();
  await expect(page.getByTestId('yt-guide')).toBeVisible();
  await expect(page.getByTestId('yt-guide')).toContainText('Desktop app');
  await expect(page.getByTestId('yt-guide-save')).toBeDisabled();
  await page.getByTestId('yt-client-id').fill(CLIENT);
  await page.getByTestId('yt-client-secret').fill('GOCSPX-e2e-secret');
  await page.screenshot({ path: path.join(SHOTS, 'yt-guide.png') });
  await page.getByTestId('yt-guide-save').click();
  await expect(page.getByTestId('yt-client')).toHaveAttribute('data-source', 'own');
  // no YouTube account yet: Add YouTube -> the Google sheet (permissions first)
  await page.getByTestId('api-youtube-add').click();
  await expect(page.getByTestId('yt-connect')).toBeVisible();
  await expect(page.getByTestId('yt-connect')).toContainText('upload videos');
  await expect(page.getByTestId('yt-connect-captions')).not.toBeChecked();
  await page.getByTestId('yt-connect-go').click();
  await expect(page.getByTestId('yt-connect')).toHaveCount(0, { timeout: 15000 });
  await expect(page.getByTestId('api-youtube-state')).toHaveAttribute('data-state', 'in');
  await expect(page.getByTestId('api-youtube')).toContainText('E2E Channel');
  const r = await rec();
  const consent = new URL(r.opened.find((u) => u.startsWith('https://accounts.google.com/'))!);
  expect(consent.searchParams.get('code_challenge_method')).toBe('S256');
  expect(consent.searchParams.get('redirect_uri')).toMatch(/^http:\/\/127\.0\.0\.1:\d+$/);
  expect(consent.searchParams.get('scope')).toBe('https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly');
  expect(r.verifier?.length).toBeGreaterThanOrEqual(43);
  // the account list reads the API sign-in; the built-in browser never opens YouTube
  await expect(page.locator('[data-testid="settings-channel"][data-adapter="youtube-studio"] [data-testid="channel-state"]')).toHaveAttribute('data-state', 'in', { timeout: 15000 });
  const err = await page.evaluate(() => window.desk.publish.open('youtube-studio', 'main', 'login').then(() => '', (e: Error) => e.message));
  expect(err).toMatch(/official API/);
  // the tokens are only in the keychain-encrypted vault
  const disk = fs.readFileSync(path.join(tmp, 'profile', 'publish-api.json'), 'utf8');
  expect(disk).not.toMatch(/GOCSPX|"rt"|1234-e2e/);
  await page.screenshot({ path: path.join(SHOTS, 'yt-settings.png') });
});

test('connected accounts can add subtitle permission and retain existing grants', async () => {
  await page.getByTestId('api-youtube-permissions').click();
  await expect(page.getByTestId('yt-connect-captions')).not.toBeChecked();
  await page.getByTestId('yt-connect-captions').check();
  await expect(page.getByTestId('yt-caption-permission-hint')).toContainText('delete');
  await page.getByTestId('yt-connect-go').click();
  await expect(page.getByTestId('yt-connect')).toHaveCount(0);
  await expect(page.getByTestId('api-youtube-state')).toHaveAttribute('data-state', 'in');
  const consent = new URL((await rec()).opened.filter(u => u.startsWith('https://accounts.google.com/')).at(-1)!);
  expect(consent.searchParams.get('scope')).toContain('youtube.force-ssl');
  await page.reload();
  await page.getByTestId('api-youtube-permissions').click();
  await expect(page.getByTestId('yt-connect-captions')).toBeChecked();
  await expect(page.getByTestId('yt-connect-captions')).toBeDisabled();
  await page.getByTestId('yt-connect-go').click();
  await expect(page.getByTestId('yt-connect')).toHaveCount(0);
});

test('Publishing accounts: each platform says its path; Google’s refusal page becomes a plain explanation', async () => {
  await hash('#/publish/accounts');
  await expect(page.getByTestId('channels')).toBeVisible({ timeout: 30000 });
  await expect(page.locator('[data-testid="channel-platform"][data-adapter="youtube-studio"] [data-testid="channel-path"]')).toHaveAttribute('data-path', 'api');
  await expect(page.locator('[data-testid="channel-platform"][data-adapter="xiaohongshu"] [data-testid="channel-path"]')).toHaveAttribute('data-path', 'assisted');
  await expect(page.locator('[data-testid="channel-platform"][data-adapter="tiktok"] [data-testid="channel-path"]')).toHaveAttribute('data-path', 'api-later');
  // YouTube's Sign in is the Google sheet, not a page in the built-in browser
  await page.locator('[data-testid="channel-platform"][data-adapter="youtube-studio"] [data-testid="channel-login"]').click();
  await expect(page.getByTestId('yt-connect')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('yt-connect')).toHaveCount(0);
  // TikTok: "Continue with Google" lands on Google's refusal
  await page.locator('[data-testid="channel-platform"][data-adapter="tiktok"] [data-testid="channel-add"]').click();
  await expect(page.getByTestId('blocked-notice')).toBeVisible({ timeout: 20000 });
  await expect(page.getByTestId('blocked-notice')).toHaveAttribute('data-provider', 'google');
  await expect(page.getByTestId('blocked-notice')).toContainText('Google doesn’t allow signing in here');
  await expect(page.getByTestId('blocked-notice')).not.toContainText('may not be secure');
  await page.screenshot({ path: path.join(SHOTS, 'blocked.png') });
  await page.getByTestId('blocked-upload').click();
  expect((await rec()).opened.at(-1)).toBe('https://www.tiktok.com/tiktokstudio/upload');
  await page.getByTestId('blocked-back').click(); // TikTok's own login works in the panel
  await expect(page.getByTestId('blocked-notice')).toHaveCount(0, { timeout: 15000 });
});

let item = '';
test('a YouTube Short: the form, Schedule after Made for kids, uploaded through the API, scheduled with its link', async () => {
  await page.evaluate(() => window.desk.publish.hide());
  await expect.poll(async () => (await api<{ items: { id: string; dir: string }[] }>('/api/history')).items.find((i) => i.dir === work)?.id ?? '', { timeout: 30000 }).not.toBe('');
  item = (await api<{ items: { id: string; dir: string }[] }>('/api/history')).items.find((i) => i.dir === work)!.id;
  const when = new Date(Date.now() + 2 * 86400_000);
  when.setHours(18, 0, 0, 0);
  const r = await api<{ ids: string[] }>('/api/calendar/many', { posts: [{ item, clip: 'A_tip', platform: 'youtube-shorts', at: at(when) }] });
  const id = r.ids[0];
  await hash(`#/publish/post/${id}`);
  await expect(page.getByTestId('ytp-form')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('post-path')).toHaveAttribute('data-path', 'api');
  await expect(page.getByTestId('post-fill')).toHaveCount(0); // no built-in browser fill for YouTube
  await app.evaluate(() => { (globalThis as unknown as { __yt: Rec }).__yt.failPlaylists = true; });
  await page.reload();
  await expect(page.getByText(/YouTube did not list the playlists: 503/)).toBeVisible();
  await expect(page.getByTestId('ytp-playlist')).toBeDisabled();
  await app.evaluate(() => { (globalThis as unknown as { __yt: Rec }).__yt.failPlaylists = false; });
  await page.reload();
  await expect(page.getByTestId('ytp-title')).toHaveValue('One tip a day');
  await expect(page.getByTestId('ytp-short')).toBeChecked(); // a real 90s file passes the same UI + main eligibility check
  await expect(page.getByTestId('ytp-at')).toBeChecked(); // its time is ahead: scheduled
  await expect(page.getByTestId('ytp-publish')).toBeDisabled(); // Made for kids is hers to answer
  await expect(page.getByTestId('ytp-publish')).toHaveText(/Schedule/);
  await page.getByTestId('ytp-kids-no').check();
  await page.getByTestId('ytp-category').selectOption('27');
  await page.screenshot({ path: path.join(SHOTS, 'yt-form.png') });
  expect((await rec()).puts).toBe(0); // nothing uploaded before her click
  await page.getByTestId('ytp-publish').click();
  await expect(page.getByTestId('ytp-done')).toBeVisible({ timeout: 20000 });
  await expect(page.getByTestId('ytp-done')).toContainText('Scheduled');
  const m = (await rec()).meta!;
  expect(m.snippet.title).toContain('#Shorts');
  expect(m.snippet.categoryId).toBe('27');
  expect(m.status).toMatchObject({ privacyStatus: 'private', selfDeclaredMadeForKids: false, publishAt: new Date(`${at(when)}:00`).toISOString() });
  const row = (await api<{ posts: Row[] }>('/api/calendar')).posts.find((x) => x.id === id)!;
  expect(row).toMatchObject({ state: 'scheduled', via: 'api', url: 'https://youtu.be/e2eVid' });
  expect(row).not.toHaveProperty('posted_at');
  await expect(page.getByTestId('post-posted')).toContainText('Scheduled on platform');
  await page.reload(); // Renderer state is gone: the receipt must come from the calendar.
  await expect(page.getByTestId('ytp-done')).toContainText('Scheduled', { timeout: 15000 });
  await expect(page.getByTestId('ytp-form')).toHaveCount(0);
  expect((await rec()).puts).toBe(1);
  await page.screenshot({ path: path.join(SHOTS, 'yt-scheduled.png') });
  await hash('#/publish');
  // The scheduled date can fall in the next week when this test runs on a weekend.
  if ((when.getDay() + 6) % 7 < (new Date().getDay() + 6) % 7) await page.getByRole('button', { name: 'Next week', exact: true }).click();
  const card = page.getByTestId('pub-post').filter({ has: page.getByTestId('pb-status').filter({ hasText: 'Scheduled on platform' }) }).first();
  await expect(card).toHaveAttribute('draggable', 'false');
  await card.locator('.pc-top').click();
  await expect(page.getByTestId('pb-date')).toBeDisabled();
  await expect(page.getByTestId('pb-time')).toBeDisabled();
  await expect(page.getByTestId('pb-publish-now')).toHaveCount(0);
  await page.getByTestId('pb-done').click();
});

test('a private upload remains uploaded, not posted, after reopening the page', async () => {
  const r = await api<{ ids: string[] }>('/api/calendar/many', { posts: [{ item, clip: 'A_tip', platform: 'youtube', at: at(new Date(Date.now() + 86400_000)) }] });
  const id = r.ids[0];
  await hash(`#/publish/post/${id}?now=1`);
  await expect(page.getByTestId('ytp-form')).toBeVisible();
  await page.getByTestId('ytp-privacy').selectOption('private');
  await page.getByTestId('ytp-kids-no').check();
  await page.getByTestId('ytp-publish').click();
  await expect(page.getByTestId('ytp-done')).toHaveAttribute('data-privacy', 'private');
  await expect(page.getByTestId('post-posted')).toContainText('Uploaded · not public');
  const row = (await api<{ posts: Row[] }>('/api/calendar')).posts.find((x) => x.id === id)!;
  expect(row.state).toBe('uploaded');
  expect(row).not.toHaveProperty('posted_at');
  await page.reload();
  await expect(page.getByTestId('post-posted')).toContainText('Uploaded · not public');
  await expect(page.getByTestId('ytp-done')).toHaveAttribute('data-privacy', 'private');
  await expect(page.getByTestId('ytp-form')).toHaveCount(0);
  await page.screenshot({ path: path.join(SHOTS, 'yt-private.png') });
});

test('an interrupted manual upload survives reload and continues its original session', async () => {
  const r = await api<{ ids: string[] }>('/api/calendar/many', { posts: [{ item, clip: 'A_tip', platform: 'youtube', at: at(new Date(Date.now() + 3 * 86400_000)) }] });
  const id = r.ids[0];
  const initial = (await rec()).inserts ?? 0;
  await hash(`#/publish/post/${id}`);
  await expect(page.getByTestId('ytp-form')).toBeVisible();
  await page.getByTestId('ytp-title').fill('Original scheduled title');
  await page.getByTestId('ytp-kids-no').check();
  await app.evaluate(() => { (globalThis as unknown as { __yt: Rec }).__yt.failNext = true; });
  await page.getByTestId('ytp-publish').click();
  await expect(page.getByTestId('ytp-resume-card')).toBeVisible();
  const original = (await rec()).meta;
  expect(original?.snippet.title).toBe('Original scheduled title');
  await expect(page.getByTestId('ytp-resume-card')).toContainText('Account: main');
  await expect(page.getByTestId('ytp-form')).toHaveCount(0);
  await page.reload();
  await expect(page.getByTestId('ytp-resume')).toBeEnabled();
  await page.screenshot({ path: path.join(SHOTS, 'yt-resume-ready.png') });
  expect((await rec()).inserts).toBe(initial + 1);
  await page.getByTestId('ytp-resume').click();
  await expect(page.getByTestId('ytp-resume')).toBeDisabled();
  await page.screenshot({ path: path.join(SHOTS, 'yt-resume-running.png') });
  await expect(page.getByTestId('ytp-done')).toContainText('Scheduled');
  expect((await rec()).inserts).toBe(initial + 1);
  expect((await rec()).meta).toEqual(original);
  const row = (await api<{ posts: Row[] }>('/api/calendar')).posts.find(x => x.id === id)!;
  expect(row).toMatchObject({ state: 'scheduled', via: 'api', url: 'https://youtu.be/e2eVid' });
});

test('status readback distinguishes processing, public and rejected, persists after reload, never uploads again', async () => {
  const puts = (await rec()).puts;
  for (const [status, state, text] of [
    [{ privacyStatus: 'public', uploadStatus: 'uploaded' }, 'uploaded', 'processing'],
    [{ privacyStatus: 'private', uploadStatus: 'uploaded', publishAt: '2026-10-25T12:00:00Z' }, 'scheduled', 'Scheduled'],
    [{ privacyStatus: 'public', uploadStatus: 'processed' }, 'posted', 'Public on YouTube at the last check'],
    [{ privacyStatus: 'public', uploadStatus: 'rejected', rejectionReason: 'copyright' }, 'uploaded', 'copyright'],
  ] as [Record<string, string>, string, string][]) {
    await app.evaluate((_app, remote) => { (globalThis as unknown as { __yt: Rec }).__yt.remote = remote; }, status);
    await page.getByTestId('ytp-refresh').click();
    await expect(page.getByTestId('ytp-done')).toContainText(text);
    await expect(page.getByTestId('ytp-checked')).toBeVisible();
    const id = (await page.url()).split('/post/')[1].split('?')[0];
    await expect.poll(async () => (await api<{ posts: Row[] }>('/api/calendar')).posts.find(p => p.id === id)?.state).toBe(state);
    expect((await rec()).puts).toBe(puts);
  }
  await page.reload();
  await expect(page.getByTestId('ytp-done')).toContainText('copyright');
  await expect(page.getByTestId('post-posted')).toHaveClass(/warn/);
  await expect(page.getByTestId('post-posted')).not.toContainText('Published');
  await page.screenshot({ path: path.join(SHOTS, 'yt-status-rejected.png') });
  await app.evaluate(() => { (globalThis as unknown as { __yt: Rec }).__yt.remote = undefined; });
  await page.getByTestId('ytp-refresh').click();
  await expect(page.getByTestId('ytp-done')).toContainText('copyright'); // Missing to this account is not proof of deletion.
  expect((await rec()).puts).toBe(puts);
});

test('Upload in your browser: the page in her browser, the file shown, the copy handed over, posted by link', async () => {
  const r = await api<{ ids: string[] }>('/api/calendar/many', { posts: [{ item, clip: 'A_tip', platform: 'xiaohongshu', at: at(new Date(Date.now() + 86400_000)) }] });
  await hash(`#/publish/post/${r.ids[0]}`);
  await expect(page.getByTestId('post-in-browser')).toBeVisible({ timeout: 30000 });
  await page.getByTestId('post-in-browser').click();
  await expect(page.getByTestId('ub-sheet')).toBeVisible();
  await page.getByTestId('ub-open').getByRole('button').click();
  await page.getByTestId('ub-reveal').getByRole('button').click();
  await page.getByTestId('ub-desc').getByRole('button').click();
  await page.getByTestId('ub-tags').getByRole('button').click();
  await expect(page.getByTestId('ub-tags')).toHaveAttribute('data-done', 'true');
  const rr = await rec();
  expect(rr.opened.at(-1)).toBe('https://creator.xiaohongshu.com/publish/publish?from=menu&target=video');
  expect(rr.shown.at(-1)).toMatch(/A_tip.*\.mp4$/);
  expect(rr.copied.at(-1)).toBe('tips, creator');
  await page.getByTestId('ub-url').fill('https://www.xiaohongshu.com/explore/abc');
  await page.getByTestId('ub-posted').click();
  await expect(page.getByTestId('post-posted')).toBeVisible({ timeout: 15000 });
});

test('account status failures stay visible and retry in settings and sign-in', async () => {
  const status = await page.evaluate(() => window.desk.publish.api.status());
  await app.evaluate(({ ipcMain }, value) => {
    const g = globalThis as unknown as { __statusFails: boolean };
    g.__statusFails = true;
    ipcMain.removeHandler('publish:apiStatus');
    ipcMain.handle('publish:apiStatus', () => {
      if (g.__statusFails) throw new Error('Account status unavailable');
      return value;
    });
  }, status);
  await hash('#/settings/accounts');
  await expect(page.getByTestId('api-status-error')).toContainText('Account status unavailable');
  await expect(page.getByTestId('api-status-error')).not.toContainText('publish:apiStatus');
  await expect(page.getByTestId('settings-api')).toHaveCount(0);
  await app.evaluate(() => { (globalThis as unknown as { __statusFails: boolean }).__statusFails = false; });
  await page.getByTestId('api-status-retry').click();
  await expect(page.getByTestId('settings-api')).toBeVisible();
  await expect(page.getByTestId('api-status-error')).toHaveCount(0);
  await hash('#/publish/accounts');
  await app.evaluate(() => { (globalThis as unknown as { __statusFails: boolean }).__statusFails = true; });
  await page.locator('[data-testid="channel-platform"][data-adapter="youtube-studio"] [data-testid="channel-login"]').click();
  await expect(page.getByTestId('yt-connect').getByTestId('api-status-error')).toContainText('Account status unavailable');
  await expect(page.getByTestId('yt-connect-go')).toBeDisabled();
  await expect(page.getByTestId('api-status-loading')).toHaveCount(0);
  await page.screenshot({ path: path.join(SHOTS, 'yt-status-load-error.png') });
  await app.evaluate(() => { (globalThis as unknown as { __statusFails: boolean }).__statusFails = false; });
  await page.getByTestId('api-status-retry').click();
  await expect(page.getByTestId('yt-connect-go')).toBeEnabled();
  await expect(page.getByTestId('api-status-error')).toHaveCount(0);
  await page.keyboard.press('Escape');
});

test('subtitle handoff exposes verified files and explains invalid tracks without uploading them', async () => {
  const r = await api<{ ids: string[] }>('/api/calendar/many', { posts: [
    { item, clip: 'A_tip', platform: 'youtube', at: at(new Date(Date.now() + 86400_000)) },
    { item, clip: 'A_tip', platform: 'xiaohongshu', at: at(new Date(Date.now() + 86400_000)) },
  ] });
  const pkg = await page.evaluate(id => window.desk.publish.postPackage(id), r.ids[0]);
  const file = path.join(tmp, 'captions.srt');
  fs.writeFileSync(file, '1\n00:00:00,000 --> 00:00:01,000\nTest captions\n');
  const speech = path.join(tmp, 'speech.fr.srt');
  fs.writeFileSync(speech, '1\n00:00:00,000 --> 00:00:01,000\nBonjour.\n');
  await app.evaluate(({ ipcMain }, value) => {
    ipcMain.removeHandler('publish:postPackage');
    ipcMain.handle('publish:postPackage', (_event, request) => ({ ...value.pkg, postId: request.postId,
      sidecars: [{ file: value.file, format: 'srt', cues: 1, lang: 'und', role: 'rendered-captions', render_key: 'test', sha256: 'test' },
        { file: value.speech, format: 'srt', cues: 1, lang: 'fr', role: 'speech', render_key: 'test', sha256: 'test' }],
      captionIssues: [{ format: 'vtt', reason: 'file-changed' }],
    }));
  }, { pkg, file, speech });
  const puts = (await rec()).puts;
  await hash(`#/publish/post/${r.ids[0]}?now=1`);
  const captions = page.getByTestId('publish-captions');
  await expect(captions).toContainText('no longer match this video');
  await captions.getByRole('button', { name: 'Show SRT file' }).click();
  expect((await rec()).shown.at(-1)).toBe(file);
  await captions.getByRole('button', { name: 'Français speech · SRT' }).click();
  expect((await rec()).shown.at(-1)).toBe(speech);
  await page.screenshot({ path: path.join(SHOTS, 'yt-caption-files.png') });
  await hash(`#/publish/post/${r.ids[1]}`);
  await page.getByTestId('post-in-browser').click();
  await expect(page.getByTestId('ub-sheet').getByTestId('publish-captions')).toContainText('does not upload them automatically');
  await page.getByTestId('ub-sheet').getByRole('button', { name: 'Show SRT file' }).click();
  expect((await rec()).shown.at(-1)).toBe(file);
  expect((await rec()).puts).toBe(puts);
});

test('late package response cannot replace the next post copy or subtitle files', async () => {
  const r = await api<{ ids: string[] }>('/api/calendar/many', { posts: [
    { item, clip: 'A_tip', platform: 'youtube', at: at(new Date(Date.now() + 2 * 86400_000)) },
    { item, clip: 'A_tip', platform: 'youtube', at: at(new Date(Date.now() + 3 * 86400_000)) },
  ] });
  const pkg = await page.evaluate(id => window.desk.publish.postPackage(id), r.ids[1]);
  await app.evaluate(({ ipcMain }, value) => {
    const g = globalThis as unknown as { __latePackage?: () => void };
    ipcMain.removeHandler('publish:postPackage');
    ipcMain.handle('publish:postPackage', (_event, request) => {
      const result = { ...value.pkg, postId: request.postId, title: request.postId === value.first ? 'Old post' : 'Next post',
        sidecars: [], captionIssues: request.postId === value.first ? [{ reason: 'file-missing' }] : [] };
      return request.postId === value.first ? new Promise(resolve => { g.__latePackage = () => resolve(result); }) : result;
    });
  }, { pkg, first: r.ids[0] });
  await page.keyboard.press('Escape');
  await hash(`#/publish/post/${r.ids[0]}?now=1`);
  await expect.poll(() => app.evaluate(() => !!(globalThis as unknown as { __latePackage?: () => void }).__latePackage)).toBe(true);
  await hash(`#/publish/post/${r.ids[1]}?now=1`);
  await expect(page.getByTestId('ytp-title')).toHaveValue('Next post');
  await app.evaluate(() => (globalThis as unknown as { __latePackage: () => void }).__latePackage());
  await expect(page.getByTestId('publish-captions')).toHaveCount(0);
  await expect(page.getByTestId('ytp-title')).toHaveValue('Next post');
});

test('caption progress stays busy until completion and ignores late events', async () => {
  const r = await api<{ ids: string[] }>('/api/calendar/many', { posts: [
    { item, clip: 'A_tip', platform: 'youtube', at: at(new Date(Date.now() + 3 * 86400_000)) },
  ] });
  const id = r.ids[0];
  // Delay the provider response deterministically; exercise the shipped renderer listener.
  await app.evaluate(({ ipcMain }) => {
    ipcMain.removeHandler('publish:ytPublish');
    ipcMain.handle('publish:ytPublish', (event, p) => new Promise(resolve => {
      (globalThis as unknown as { finishCaption: () => void }).finishCaption = () => resolve({
        id: 'captionVideo', url: 'https://youtu.be/captionVideo', privacy: 'private', publishAt: null,
        lockedPrivate: false, warnings: [], captions: [{ id: 'track1', language: 'fr', status: 'syncing' }],
      });
      event.sender.send('publish:ytProgress', { postId: p.postId, stage: 'captions', index: 1, total: 1 });
    }));
  });
  await hash(`#/publish/post/${id}?now=1`);
  await page.getByTestId('ytp-kids-no').check();
  await page.getByTestId('ytp-publish').click();
  await expect(page.getByTestId('ytp-progress')).toHaveText('Uploading subtitles… 1 of 1');
  await expect(page.getByTestId('ytp-publish')).toBeDisabled();
  await app.evaluate(() => (globalThis as unknown as { finishCaption: () => void }).finishCaption());
  await expect(page.getByTestId('ytp-done')).toBeVisible();
  await expect(page.getByTestId('ytp-caption-status')).toContainText('Processing');
  await app.evaluate(({ BrowserWindow }, postId) => BrowserWindow.getAllWindows()[0].webContents.send('publish:ytProgress', {
    postId, stage: 'captions', index: 1, total: 1,
  }), id);
  await expect(page.getByTestId('ytp-done')).toBeVisible();
  await expect(page.getByTestId('ytp-progress')).toHaveCount(0);
});
