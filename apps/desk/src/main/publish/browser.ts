// The built-in publish browser: one WebContentsView per (platform, account), each with its own persistent
// session partition `persist:<platform>-<account>`. The creator signs in herself inside the page; the app never
// sees, stores or exports passwords or cookies. Platform pages get no preload, run sandboxed with context
// isolation, cannot reach the local engine, get no device permissions and cannot download.
// Platforms with an official upload API that is wired (YouTube) never open here: Google refuses sign-in in embedded
// browsers, and her rule is the official API whenever there is one. When a sign-in provider refuses this browser
// anyway (another platform's "Continue with Google" / Facebook button), the page is hidden and the renderer explains
// it with the right next step instead of the provider's raw error.
import { app, shell, WebContentsView, type BrowserWindow, type Session, type WebContents, session as electronSession } from 'electron';
import { partitionFor } from '../../shared/ipc';
import { hostAllowed, type Adapter } from '../../shared/publish/adapterSchema';
import { loginState, PAGE_SIGNALS_JS, type PageSignals } from '../../shared/channels';
import { apiOnly } from '../../shared/publish/apiPlatforms';
import { BLOCK_TEXT_JS, embeddedBlock, maybeBlockPage, type EmbedBlock } from '../../shared/publish/embedBlock';
import { isLocalEngineRequest, isSafeExternal, REMOTE_ALLOWED_PERMISSIONS } from '../security';
import { probeLogin } from './loginProbe';
import { cleanUserAgent } from './ua';

/** Sign-in providers platforms open in popups (kept in the same partition so the login sticks). */
const LOGIN_HOSTS = [
  'accounts.google.com',
  '*.google.com',
  'appleid.apple.com',
  '*.facebook.com',
  'x.com',
  'api.twitter.com',
  'open.weixin.qq.com',
  '*.qq.com',
];

export interface PublishState {
  adapterId: string | null;
  account: string | null;
  url: string;
  title: string;
  loading: boolean;
  canGoBack: boolean;
  canGoForward: boolean;
  visible: boolean;
  /** a sign-in provider refused this embedded browser (the page is hidden; the renderer explains) */
  blocked: EmbedBlock | null;
}

/** Refused here: the platform's official API is the path (see shared/publish/apiPlatforms.ts). */
export class ApiOnlyError extends Error {
  constructor(name: string) {
    super(`${name} is published through its official API, not the built-in browser: sign in with Google in your browser (Settings › Publishing accounts)`);
    this.name = 'ApiOnlyError';
  }
}

const hardened = new WeakSet<Session>();

function hardenSession(ses: Session) {
  if (hardened.has(ses)) return;
  hardened.add(ses);
  ses.setPermissionRequestHandler((_wc, perm, cb) => cb(REMOTE_ALLOWED_PERMISSIONS.has(perm)));
  ses.setPermissionCheckHandler((_wc, perm) => REMOTE_ALLOWED_PERMISSIONS.has(perm));
  ses.setDevicePermissionHandler(() => false);
  ses.on('will-download', (e) => e.preventDefault());
  ses.webRequest.onBeforeRequest((details, cb) => cb({ cancel: isLocalEngineRequest(details.url) }));
  // the real Chrome version without the app / Electron tokens (x.com, Instagram and Google sign-in refuse those)
  ses.setUserAgent(cleanUserAgent(ses.getUserAgent(), [app.getName(), 'Reelfold', 'Daycut', 'video-studio-desk', 'video-studio desk']));
}

interface Entry {
  key: string;
  adapter: Adapter;
  account: string;
  view: WebContentsView;
  blocked: EmbedBlock | null;
}

export class PublishBrowser {
  private entries = new Map<string, Entry>();
  private current: Entry | null = null;
  private bounds = { x: 0, y: 0, width: 0, height: 0 };
  private visible = false;

  constructor(
    private win: BrowserWindow,
    private onState: (s: PublishState) => void,
    private onLogin: (adapterId: string, account: string, state: 'in' | 'out') => void = () => undefined,
  ) {}

  private create(adapter: Adapter, account: string): Entry {
    const partition = partitionFor(adapter.id, account);
    const ses = electronSession.fromPartition(partition);
    hardenSession(ses);
    const view = new WebContentsView({
      webPreferences: {
        partition,
        sandbox: true,
        contextIsolation: true,
        nodeIntegration: false,
        nodeIntegrationInSubFrames: false,
        webviewTag: false,
        safeDialogs: true,
        spellcheck: false,
        // deliberately no preload: platform pages get no privileged API
      },
    });
    const wc = view.webContents;
    const entry: Entry = { key: partition, adapter, account, view, blocked: null };
    const allowedPopup = (url: string) => {
      try {
        const u = new URL(url);
        return u.protocol === 'https:' && (hostAllowed(u.hostname, adapter.allowedHosts) || hostAllowed(u.hostname, LOGIN_HOSTS));
      } catch {
        return false;
      }
    };
    wc.setWindowOpenHandler(({ url }) => {
      if (allowedPopup(url)) {
        return {
          action: 'allow',
          overrideBrowserWindowOptions: {
            width: 520,
            height: 720,
            parent: this.win,
            webPreferences: { partition, sandbox: true, contextIsolation: true, nodeIntegration: false },
          },
        };
      }
      if (isSafeExternal(url)) void shell.openExternal(url);
      return { action: 'deny' };
    });
    wc.on('will-navigate', (e, url) => {
      if (!url.startsWith('https:')) e.preventDefault();
    });
    wc.on('will-attach-webview', (e) => e.preventDefault());
    const emit = () => this.emit();
    // a provider's "not secure / unsupported browser" page (here or in a sign-in popup): hide it, say why
    const setBlocked = (b: EmbedBlock | null) => {
      if (JSON.stringify(b) === JSON.stringify(entry.blocked)) return;
      entry.blocked = b;
      if (this.current === entry) entry.view.setVisible(this.visible && !b);
      this.emit();
    };
    const checkBlock = async (w: WebContents, popup: boolean) => {
      if (w.isDestroyed()) return;
      const url = w.getURL();
      let b = embeddedBlock(url);
      if (!b && maybeBlockPage(url)) {
        try {
          b = embeddedBlock(url, String(await w.executeJavaScriptInIsolatedWorld(1004, [{ code: BLOCK_TEXT_JS }])));
        } catch {
          /* navigating */
        }
      }
      if (popup) {
        if (b) {
          setBlocked(b);
          if (!w.isDestroyed()) w.close();
        }
      } else if (!w.isDestroyed() && w.getURL() === url) setBlocked(b);
    };
    wc.on('did-navigate', () => void checkBlock(wc, false));
    wc.on('did-navigate-in-page', () => void checkBlock(wc, false));
    wc.on('did-stop-loading', () => void checkBlock(wc, false));
    wc.on('did-create-window', (child) => {
      const cw = child.webContents;
      cw.on('did-navigate', () => void checkBlock(cw, true));
      cw.on('did-navigate-in-page', () => void checkBlock(cw, true));
      let blockTimer: NodeJS.Timeout | null = null;
      cw.on('did-stop-loading', () => {
        void checkBlock(cw, true);
        if (blockTimer) clearTimeout(blockTimer);
        blockTimer = setTimeout(() => void checkBlock(cw, true), 2500);
      });
      cw.once('destroyed', () => { if (blockTimer) clearTimeout(blockTimer); });
    });
    // login state: the URL first, then what the page shows a moment after it settled (SPAs redirect late)
    let check: NodeJS.Timeout | null = null;
    // the session cookies decide when the adapter names them (any page of the platform counts, 小红书's creator home
    // too); otherwise the URL and what the page shows
    const seen = () => {
      if (check) clearTimeout(check);
      void probeLogin(ses, entry.adapter).then((st) => {
        if (st) return this.onLogin(entry.adapter.id, account, st);
        const quick = loginState(wc.isDestroyed() ? '' : wc.getURL(), entry.adapter, null);
        if (quick) this.onLogin(entry.adapter.id, account, quick);
      });
      check = setTimeout(async () => {
        if (wc.isDestroyed()) return;
        void checkBlock(wc, false);
        const byCookie = await probeLogin(ses, entry.adapter);
        if (byCookie) return this.onLogin(entry.adapter.id, account, byCookie);
        let page: PageSignals | null = null;
        try {
          page = (await wc.executeJavaScriptInIsolatedWorld(1001, [{ code: PAGE_SIGNALS_JS }])) as PageSignals;
        } catch {
          /* navigated away */
        }
        const st = loginState(wc.getURL(), entry.adapter, page);
        if (st) this.onLogin(entry.adapter.id, account, st);
      }, 2500);
    };
    wc.on('did-stop-loading', seen);
    wc.on('did-navigate-in-page', seen);
    // signing in inside the panel (or its sign-in popup) sets the session cookie: re-check right away
    let cookieTimer: NodeJS.Timeout | null = null;
    const names = new Set(adapter.session?.cookies ?? []);
    const onCookie = (_e: unknown, c: { name: string }) => {
      if (!names.has(c.name) || wc.isDestroyed()) return;
      if (cookieTimer) clearTimeout(cookieTimer);
      cookieTimer = setTimeout(() => void probeLogin(ses, entry.adapter).then((st) => st && this.onLogin(entry.adapter.id, account, st)), 800);
    };
    if (names.size) {
      ses.cookies.on('changed', onCookie);
      wc.once('destroyed', () => ses.cookies.removeListener('changed', onCookie));
    }
    for (const ev of ['did-navigate', 'did-navigate-in-page', 'page-title-updated', 'did-start-loading', 'did-stop-loading'] as const) {
      wc.on(ev as 'did-navigate', emit);
    }
    this.entries.set(partition, entry);
    return entry;
  }

  open(adapter: Adapter, account: string, page: 'upload' | 'login'): Entry {
    if (apiOnly(adapter.id)) throw new ApiOnlyError(adapter.name);
    const key = partitionFor(adapter.id, account);
    let e = this.entries.get(key);
    const fresh = !e;
    if (!e) e = this.create(adapter, account);
    e.adapter = adapter;
    if (this.current && this.current !== e) this.win.contentView.removeChildView(this.current.view);
    this.current = e;
    this.win.contentView.addChildView(e.view);
    e.view.setBounds(this.bounds);
    e.view.setVisible(this.visible && !e.blocked);
    // an existing view keeps its page (a half-filled upload form must survive switching tabs)
    if (fresh) void e.view.webContents.loadURL(page === 'login' ? adapter.loginUrl : adapter.uploadUrl);
    this.emit();
    return e;
  }

  get active(): Entry | null {
    return this.current;
  }

  setBounds(b: { x: number; y: number; width: number; height: number }) {
    this.bounds = b;
    this.visible = b.width > 0 && b.height > 0;
    if (this.current) {
      this.current.view.setBounds(b);
      this.current.view.setVisible(this.visible && !this.current.blocked);
    }
  }

  hide() {
    this.visible = false;
    this.current?.view.setVisible(false);
    this.emit();
  }

  navigate(action: 'back' | 'forward' | 'reload' | 'upload' | 'login') {
    const e = this.current;
    if (!e) return;
    const wc = e.view.webContents;
    if (e.blocked) {
      // she leaves the refusal page: show the panel again (a new refusal hides it again)
      e.blocked = null;
      e.view.setVisible(this.visible);
    }
    if (action === 'back' && wc.navigationHistory.canGoBack()) wc.navigationHistory.goBack();
    else if (action === 'forward' && wc.navigationHistory.canGoForward()) wc.navigationHistory.goForward();
    else if (action === 'reload') wc.reload();
    else if (action === 'upload') void wc.loadURL(e.adapter.uploadUrl);
    else if (action === 'login') void wc.loadURL(e.adapter.loginUrl);
  }

  private emit() {
    const e = this.current;
    const wc = e?.view.webContents;
    this.onState({
      adapterId: e?.adapter.id ?? null,
      account: e?.account ?? null,
      url: wc?.getURL() ?? '',
      title: wc?.getTitle() ?? '',
      loading: wc?.isLoading() ?? false,
      canGoBack: wc?.navigationHistory.canGoBack() ?? false,
      canGoForward: wc?.navigationHistory.canGoForward() ?? false,
      visible: this.visible,
      blocked: e?.blocked ?? null,
    });
  }

  /** Close an account's view (before its session storage is cleared). */
  forget(adapterId: string, account: string) {
    const key = partitionFor(adapterId, account);
    const e = this.entries.get(key);
    if (!e) return;
    try {
      this.win.contentView.removeChildView(e.view);
    } catch {
      /* not attached */
    }
    e.view.webContents.close();
    this.entries.delete(key);
    if (this.current === e) this.current = null;
    this.emit();
  }

  destroy() {
    for (const e of this.entries.values()) {
      try {
        this.win.contentView.removeChildView(e.view);
      } catch {
        /* window gone */
      }
      e.view.webContents.close();
    }
    this.entries.clear();
    this.current = null;
  }
}
