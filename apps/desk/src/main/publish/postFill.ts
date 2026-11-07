import { successSnapshot } from '../../shared/publish/successSnapshot';
import type { FillControl } from './fillControl';
// "Time to post" for one 发布 board row: open the platform's upload page in the account's own session, set the
// rendered file made for that platform, type the title / text / tags, outline the Publish button - and then watch
// the page: when she has pressed Publish herself (a success URL or text from the adapter), the row becomes
// "posted" with the post's link when the page shows one. The app never clicks Publish.
import fs from 'node:fs';
import { randomUUID } from 'node:crypto';
import { findJs } from '../../shared/publish/selectors';
import type { WebContents } from 'electron';
import type { EngineClient } from '../../shared/engineClient';
import { loginState } from '../../shared/channels';
import { adapterFor, type Adapter } from '../../shared/publish/adapterSchema';
import { apiOnly } from '../../shared/publish/apiPlatforms';
import { postAccount } from '../../shared/publish/account';
import { planFill } from '../../shared/publish/fillPlan';
import { copyForPost, pickFile, freshPostedSignal, receiptLines, matchesAssistedUpload } from '../../shared/publish/postNow';
import type { CalendarPost } from '../../shared/v04';
import type { PublishBrowser } from './browser';
import { runFill, type StepResult } from './cdpFill';
import { onUploadPage, waitLoaded } from './fill';
import { probeLogin } from './loginProbe';

export type PostFillOutcome =
  | { ok: true; postId: string; adapterId: string; account: string; results: StepResult[]; video: string; cover: string | null }
  | { ok: false; reason: 'no-post' | 'posted' | 'no-adapter' | 'adapter-todo' | 'no-account' | 'no-file' | 'edit-pending' | 'version-unavailable' | 'file-missing' | 'login-required' | 'page-failed' | 'debugger-busy' | 'use-api'; detail?: string; adapterId?: string; account?: string };

export interface PostFillDeps {
  client: EngineClient;
  control?: FillControl;
  adapters: Adapter[];
  browser: PublishBrowser;
  accounts: Record<string, string[]>;
  onStep?: (r: StepResult & { postId: string }) => void;
  /** she pressed Publish and the page said so */
  onPosted?: (postId: string, url: string | null) => void;
  log?: (msg: string) => void;
}

/** What the success check reads in the platform page (isolated world): the text and the links, nothing typed. */
const SUCCESS_JS = `(${successSnapshot.toString()})()`;

type ReceiptSnapshot = { url: string; text: string; links: string[] };
async function readReceipt(wc: WebContents): Promise<ReceiptSnapshot> {
  const page = await wc.executeJavaScriptInIsolatedWorld(1002, [{ code: SUCCESS_JS }]);
  return { ...page, url: wc.getURL() };
}

const watchers = new Map<number, () => void>();

/** Watch one platform page until it shows the adapter's success signal (or 45 minutes pass / the page closes). */
export async function watchPosted(wc: WebContents, adapter: Adapter, onPosted: (url: string | null) => void, opts: { timeoutMs?: number; pollMs?: number; baseline?: ReceiptSnapshot } = {}): Promise<() => void> {
  watchers.get(wc.id)?.();
  if (!adapter.success) return () => undefined;
  let done = false;
  let baseline = opts.baseline;
  let checking = false;
  let armed = false;
  let clickRevision = 0;
  const token = `reelfold-publish-${randomUUID()}:`;
  // This listener and nonce live in the isolated world, not the platform's JS.
  const install = async () => {
    if (done || wc.isDestroyed() || !onUploadPage(wc.getURL(), adapter)) return;
    const button = findJs(adapter.publishButton?.selectors ?? [], true);
    await wc.executeJavaScriptInIsolatedWorld(1002, [{ code: `(() => {
      const key = ${JSON.stringify(token)};
      if (globalThis[key]) return;
      const listener = event => {
        if (!event.isTrusted) return;
        const button = ${button};
        if (!button || !event.composedPath().includes(button) || button.disabled || button.getAttribute('aria-disabled') === 'true') return;
        console.debug(key + JSON.stringify({...(${successSnapshot.toString()})(), url: location.href}));
      };
      document.addEventListener('click', listener, true);
      globalThis[key] = () => { document.removeEventListener('click', listener, true); delete globalThis[key]; };
    })()` }]);
  };
  const clicked = (details: Electron.Event<Electron.WebContentsConsoleMessageEventParams>) => {
    if (done || details.frame !== wc.mainFrame || !details.message.startsWith(token) || !onUploadPage(wc.getURL(), adapter)) return;
    try {
      const snapshot = JSON.parse(details.message.slice(token.length)) as ReceiptSnapshot;
      if (typeof snapshot.url !== 'string' || typeof snapshot.text !== 'string' || !Array.isArray(snapshot.links)) return;
      baseline = snapshot;
      armed = true;
      clickRevision++;
    } catch { /* malformed messages never prove a publish action */ }
  };
  const loaded = () => { void install().catch(() => undefined); };
  wc.on('console-message', clicked);
  wc.on('did-finish-load', loaded);
  const check = async () => {
    if (done || checking || wc.isDestroyed()) return;
    checking = true;
    const revision = clickRevision;
    let page: ReceiptSnapshot;
    try {
      page = await readReceipt(wc);
    } catch {
      return; // A navigation/read failure is not evidence that an old receipt disappeared.
    } finally {
      checking = false;
    }
    // An in-flight pre-click read cannot replace the receipt captured at click time.
    if (done || wc.isDestroyed() || revision !== clickRevision) return;
    if (!baseline) { baseline = page; return; }
    const sig = freshPostedSignal(page, baseline, adapter.success);
    // Once an old signal disappears, a later occurrence may describe this upload.
    baseline = { url: baseline.url === page.url ? baseline.url : '',
      text: receiptLines(baseline.text).filter(line => receiptLines(page.text).includes(line)).join('\n'), links: [] };
    if (armed && sig.posted) {
      stop();
      onPosted(sig.url);
    }
  };
  const nav = () => void check();
  const timer = setInterval(nav, opts.pollMs ?? 2000);
  const limit = setTimeout(() => stop(), opts.timeoutMs ?? 45 * 60_000);
  wc.on('did-navigate', nav);
  wc.on('did-navigate-in-page', nav);
  const stop = () => {
    if (done) return;
    done = true;
    clearInterval(timer);
    clearTimeout(limit);
    if (!wc.isDestroyed()) {
      wc.removeListener('console-message', clicked);
      wc.removeListener('did-finish-load', loaded);
      void wc.executeJavaScriptInIsolatedWorld(1002, [{ code: `globalThis[${JSON.stringify(token)}]?.()` }]).catch(() => undefined);
      wc.removeListener('did-navigate', nav);
      wc.removeListener('did-navigate-in-page', nav);
    }
    wc.removeListener('destroyed', stop);
    watchers.delete(wc.id);
  };
  wc.once('destroyed', stop);
  watchers.set(wc.id, stop);
  await install().catch(() => undefined); // Unsupported pages require manual confirmation.
  return stop;
}

export async function fillScheduledPost(deps: PostFillDeps, req: { postId: string; account?: string }): Promise<PostFillOutcome> {
  const cal = await deps.client.calendar(undefined, { queue: false });
  const post: CalendarPost | undefined = cal.posts.find((p) => p.id === req.postId);
  if (!post) return { ok: false, reason: 'no-post' };
  if (post.state === 'posted') return { ok: false, reason: 'posted' };
  const adapter = adapterFor(post.platform.split(':')[0], deps.adapters);
  if (!adapter) return { ok: false, reason: 'no-adapter', detail: post.platform };
  // an official API is the path (YouTube): never a sign-in or a form in the built-in browser
  if (apiOnly(adapter.id)) return { ok: false, reason: 'use-api', adapterId: adapter.id };
  if (adapter.status === 'todo') return { ok: false, reason: 'adapter-todo', adapterId: adapter.id };
  const accounts = deps.accounts[adapter.id] ?? [];
  const account = postAccount(accounts, post.account ?? req.account);
  if (!account || (post.account && req.account && post.account !== req.account)) return { ok: false, reason: 'no-account', adapterId: adapter.id };

  const clips = await deps.client.clips(post.item);
  const clip = clips.clips.find((c) => c.id === post.clip);
  if (clip?.edited_stale) return { ok: false, reason: 'edit-pending', detail: post.clip, adapterId: adapter.id, account };
  const file = clip ? pickFile(clip.files, post.platform, post.video_path) : null;
  if (clip && post.video_path && !file) return { ok: false, reason: 'version-unavailable', detail: post.clip, adapterId: adapter.id, account };
  if (!clip || !file) return { ok: false, reason: 'no-file', detail: post.clip, adapterId: adapter.id, account };
  if (!fs.existsSync(file.path)) return { ok: false, reason: 'file-missing', detail: file.path, adapterId: adapter.id, account };
  const cover = clip.cover && fs.existsSync(clip.cover) ? clip.cover : null;
  const copy = copyForPost(post, adapter.fields.title !== null, [clip.title, clip.post?.title ?? ''].filter(Boolean));

  if (post.account !== account) await deps.client.updatePost(post.id, { account });
  await deps.control?.checkpoint();
  const entry = deps.browser.open(adapter, account, 'upload');
  const wc = entry.view.webContents;
  await waitLoaded(wc);
  if (!onUploadPage(wc.getURL(), adapter)) {
    await wc.loadURL(adapter.uploadUrl).catch(() => undefined);
    await waitLoaded(wc);
  }
  const ses = wc.session;
  const byCookie = await probeLogin(ses, adapter);
  if (byCookie === 'out' || loginState(wc.getURL() || adapter.uploadUrl, adapter, null) === 'out') {
    return { ok: false, reason: 'login-required', adapterId: adapter.id, account };
  }
  if (!onUploadPage(wc.getURL(), adapter)) return { ok: false, reason: 'page-failed', detail: wc.getURL(), adapterId: adapter.id, account };

  await deps.control?.checkpoint();
  watchers.get(wc.id)?.();
  let baseline: ReceiptSnapshot | undefined;
  try { baseline = await readReceipt(wc); } catch { /* first successful watch read establishes baseline */ }
  const steps = planFill(adapter, { videoPath: file.path, coverPath: cover, copy });
  const dbg = wc.debugger;
  let attachedHere = false;
  try {
    if (!dbg.isAttached()) {
      dbg.attach('1.3');
      attachedHere = true;
    }
  } catch (e) {
    return { ok: false, reason: 'debugger-busy', detail: (e as Error).message, adapterId: adapter.id, account };
  }
  let results: StepResult[];
  try {
    results = await runFill((method, params) => dbg.sendCommand(method, params), steps, { onStep: (r) => deps.onStep?.({ ...r, postId: post.id }), control: deps.control });
  } finally {
    if (attachedHere && dbg.isAttached()) dbg.detach();
  }
  await deps.control?.checkpoint();
  if (results.some((r) => r.field === 'file' && r.status === 'ok')) {
    await deps.client.updatePost(post.id, { state: 'filled' });
    await watchPosted(wc, adapter, (url) => {
      void deps.client.calendar(undefined, { queue: false }).then((cal) => {
        // Ignore receipts from an obsolete upload, including already delivered rows.
        if (!matchesAssistedUpload(cal.posts.find((p) => p.id === post.id), post, account)) return;
        return deps.client.updatePost(post.id, { state: 'posted', via: 'assisted', ...(url ? { url } : {}) })
          .then(() => deps.onPosted?.(post.id, url));
      }).catch((e) => deps.log?.(`[publish] could not mark ${post.id} posted: ${(e as Error).message}`));
    }, { baseline });
  }
  return { ok: true, postId: post.id, adapterId: adapter.id, account, results, video: file.path, cover };
}
