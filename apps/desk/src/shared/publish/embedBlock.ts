// Sign-in providers that refuse embedded browsers. Google answers a sign-in inside an app's web view with
// "Couldn't sign you in - This browser or app may not be secure" (accounts.google.com/v3/signin/rejected) or, for
// OAuth, "Error 403: disallowed_useragent"; Facebook Login shows an "unsupported browser" page. Reelfold detects
// those pages in the built-in browser (and in its sign-in popups) and shows a plain explanation and the right next
// step instead of the provider's raw error. Pure: main, renderer and tests share it.

export type BlockProvider = 'google' | 'facebook' | 'apple' | 'microsoft';

export interface EmbedBlock {
  provider: BlockProvider;
  /** what was seen: a known rejection URL, or the rejection text on a sign-in page */
  by: 'url' | 'text';
  kind?: 'passkey';
}

const hostIs = (h: string, d: string) => h === d || h.endsWith(`.${d}`);

const GOOGLE_PATHS = [/\/signin\/rejected/i, /\/v\d\/signin\/rejected/i, /\/ServiceLogin\/rejected/i, /\/signin\/v\d\/rejected/i];
const GOOGLE_TEXT = [
  /This browser or app may not be secure/i,
  /disallowed_useragent/i,
  /Use secure browsers/i,
  /此浏览器或应用可能不安全/,
  /此瀏覽器或應用程式可能不安全/,
  /Ce navigateur ou cette application ne sont peut-être pas sécurisés/i,
  /Este navegador o esta aplicación pueden no ser seguros/i,
];
const FB_TEXT = [/isn['’]t supported in this browser|browser isn['’]t supported|browser (?:is )?not supported|unsupported browser/i, /此浏览器不受支持|不支持此浏览器/];
const APPLE_TEXT = [/This browser is not supported/i];

/** The provider refused this embedded browser (null: nothing seen). `text` is the page's visible text, when read. */
export function embeddedBlock(url: string, text = ''): EmbedBlock | null {
  let u: URL;
  try {
    u = new URL(url);
  } catch {
    return null;
  }
  if (u.protocol !== 'https:') return null;
  const h = u.hostname.toLowerCase();
  if (hostIs(h, 'accounts.google.com') || hostIs(h, 'accounts.youtube.com')) {
    if (/\/challenge\/(pk|passkey)(?:\/|$)/i.test(u.pathname)) return { provider: 'google', by: 'url', kind: 'passkey' };
    if (/complete sign-in using your passkey|use your passkey to (?:sign in|verify)|使用.*通行密钥|用.*通行密钥.*登录|connecter.*clé d’accès/i.test(text))
      return { provider: 'google', by: 'text', kind: 'passkey' };
    if (GOOGLE_PATHS.some((p) => p.test(u.pathname))) return { provider: 'google', by: 'url' };
    if (/disallowed_useragent/i.test(u.search)) return { provider: 'google', by: 'url' };
    if (text && GOOGLE_TEXT.some((p) => p.test(text))) return { provider: 'google', by: 'text' };
    return null;
  }
  if (hostIs(h, 'facebook.com')) {
    if (/\/unsupportedbrowser|\/unsupported_browser|\/login\/unsupported/i.test(u.pathname)) return { provider: 'facebook', by: 'url' };
    if (text && /\/(login|dialog\/oauth|v\d+\.\d+\/dialog\/oauth)/i.test(u.pathname) && FB_TEXT.some((p) => p.test(text))) return { provider: 'facebook', by: 'text' };
    return null;
  }
  if (hostIs(h, 'appleid.apple.com')) {
    if (text && APPLE_TEXT.some((p) => p.test(text))) return { provider: 'apple', by: 'text' };
    return null;
  }
  if (hostIs(h, 'login.microsoftonline.com') || hostIs(h, 'login.live.com')) {
    if (/embedded/i.test(u.search) && /error/i.test(u.search)) return { provider: 'microsoft', by: 'url' };
    return null;
  }
  return null;
}

/** Hosts whose pages are worth reading for the rejection text (the URL alone is not always enough). */
export function maybeBlockPage(url: string): boolean {
  try {
    const h = new URL(url).hostname.toLowerCase();
    return ['accounts.google.com', 'accounts.youtube.com', 'facebook.com', 'appleid.apple.com'].some((d) => hostIs(h, d));
  } catch {
    return false;
  }
}

/** Reads the visible text of a sign-in page (isolated world; nothing typed is read: inputs are not text). */
export const BLOCK_TEXT_JS = `(() => ((document.title || '') + '\\n' + ((document.body && document.body.innerText) || '')).slice(0, 4000))()`;

/** Which publishing platforms meet these blocks in the built-in browser, and the sign-in that still works there.
 * youtube-studio is a Google sign-in itself, so it never signs in there: YouTube goes through the official API. */
export const WEBVIEW_RISK: Record<string, { providers: BlockProvider[]; works: 'none' | 'own-login' }> = {
  'youtube-studio': { providers: ['google'], works: 'none' },
  tiktok: { providers: ['google', 'facebook', 'apple'], works: 'own-login' },
  instagram: { providers: ['facebook'], works: 'own-login' },
  threads: { providers: ['facebook'], works: 'own-login' },
  facebook: { providers: [], works: 'own-login' },
  'x-web': { providers: ['google', 'apple'], works: 'own-login' },
  pinterest: { providers: ['google', 'facebook'], works: 'own-login' },
  reddit: { providers: ['google', 'apple'], works: 'own-login' },
  linkedin: { providers: ['google', 'apple', 'microsoft'], works: 'own-login' },
  dailymotion: { providers: ['google', 'facebook', 'apple'], works: 'own-login' },
  snapchat: { providers: [], works: 'own-login' },
};
