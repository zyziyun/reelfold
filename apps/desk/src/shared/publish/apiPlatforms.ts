// How each platform is published, and the official posting APIs. Her standing rule: when a platform has an official
// upload API, Reelfold uses it (OAuth in her system browser, tokens in the keychain) - never a sign-in inside the
// built-in browser. The built-in browser (fill the platform's own upload form, she presses Publish) is only for
// platforms with no official upload API she can use, and, until their API is wired, the ones marked 'api-later'.
// Nothing is ever published without her click (Publish / Schedule), or a scheduled-posting switch she turned on.
// The audit behind this table: references/PUBLISHING.md.
import { YOUTUBE_FORMATS } from '../platforms';

/** Display-only saved upload details. No resumable URI, source path or credentials. */
export interface YtResumeInfo {
  account: string;
  privacy: string;
  publishAt: string | null;
  canResume: boolean;
  busy: boolean;
}

export type ApiId = 'youtube' | 'tiktok' | 'x' | 'instagram';

export interface ApiPlatform {
  id: ApiId;
  /** board platforms it posts */
  platforms: string[];
  /** available: connect + post works in this build; later: documented, not built (why in references/PUBLISHING.md) */
  availability: 'available' | 'later';
  /** what she grants, shown before connecting */
  scopes: string[];
  docs: string;
}

export const API_PLATFORMS: ApiPlatform[] = [
  {
    id: 'youtube',
    platforms: ['youtube', 'youtube-shorts'],
    availability: 'available',
    scopes: ['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.readonly'],
    docs: 'https://developers.google.com/youtube/v3/docs/videos/insert',
  },
  {
    id: 'tiktok',
    platforms: ['tiktok'],
    availability: 'later',
    scopes: ['video.upload', 'video.publish'],
    docs: 'https://developers.tiktok.com/doc/content-posting-api-get-started',
  },
  {
    id: 'x',
    platforms: ['x'],
    availability: 'later',
    scopes: ['tweet.write', 'media.write', 'users.read', 'offline.access'],
    docs: 'https://docs.x.com/x-api/media/upload-media',
  },
  {
    id: 'instagram',
    platforms: ['instagram'],
    availability: 'later',
    scopes: ['instagram_business_basic', 'instagram_business_content_publish'],
    docs: 'https://developers.facebook.com/docs/instagram-platform/content-publishing',
  },
];

/** api: official API, wired (the only path); api-later: an official API exists, not wired yet (assisted fill until
 * then); assisted: no official upload API she can use (the built-in browser is the path). */
export type PublishPath = 'api' | 'api-later' | 'assisted';

/** Per publishing-account adapter. Unknown adapters: assisted. */
export const PUBLISH_PATH: Record<string, PublishPath> = {
  'youtube-studio': 'api',
  tiktok: 'api-later',
  instagram: 'api-later',
  facebook: 'api-later',
  threads: 'api-later',
  linkedin: 'api-later',
  'x-web': 'api-later',
  pinterest: 'api-later',
  dailymotion: 'api-later',
  bilibili: 'api-later',
  kuaishou: 'api-later',
  reddit: 'assisted',
  snapchat: 'assisted',
  xiaohongshu: 'assisted',
  douyin: 'assisted',
  'wechat-channels': 'assisted',
  weibo: 'assisted',
  zhihu: 'assisted',
  kwai: 'assisted',
};

export const publishPath = (adapterId: string): PublishPath => PUBLISH_PATH[adapterId] ?? 'assisted';

/** The adapter's account signs in only through the official API (never a page in the built-in browser). */
export const apiOnly = (adapterId: string) => publishPath(adapterId) === 'api';

/** Where "Upload in your browser" opens (her default browser, her own sign-in there). */
export const BROWSER_UPLOAD_URL: Record<string, string> = {
  'youtube-studio': 'https://studio.youtube.com/',
};

export interface YtAccountMsg {
  account: string;
  connected: boolean;
  connectedAt: string | null;
  channel: { id: string; title: string } | null;
  /** she allowed adding videos to playlists */
  playlists: boolean;
}

export interface YtStatusMsg {
  /** which OAuth client signs in: Reelfold's (built into this build), hers, or none chosen yet */
  source: 'reelfold' | 'own' | null;
  hasClient: boolean;
  /** this build carries Reelfold's client */
  builtin: boolean;
  ownClientId: string | null;
  accounts: YtAccountMsg[];
}

export interface ApiStatusMsg {
  id: ApiId;
  availability: 'available' | 'later';
  platforms: string[];
  scopes: string[];
  /** an OAuth client is chosen (YouTube: Reelfold's or her own Google Cloud "Desktop app" client) */
  hasClient: boolean;
  /** at least one account is connected */
  connected: boolean;
  connectedAt: string | null;
  /** post scheduled rows of these platforms through the API at their time (her switch) */
  auto: boolean;
  /** the OS keychain can hold tokens (no keychain: connecting is refused) */
  keychain: boolean;
  /** YouTube's details */
  yt?: YtStatusMsg;
}

/** What she chose in the YouTube publish form; main adds the file, the cover and the copy of the post. */
export interface YtPublishReq {
  postId: string;
  account: string;
  title: string;
  description: string;
  tags: string[];
  categoryId: string;
  privacy: 'public' | 'unlisted' | 'private';
  /** local "YYYY-MM-DDTHH:MM": schedule (uploaded private, YouTube publishes then); null: now */
  publishAt: string | null;
  madeForKids: boolean;
  synthetic: boolean;
  short: boolean;
  thumbnail: boolean;
  playlistId: string | null;
}

export interface YtPublishResult {
  id?: string;
  url: string;
  privacy: string;
  publishAt: string | null;
  lockedPrivate: boolean;
  warnings: string[];
  uploadStatus?: 'uploaded' | 'processed' | 'failed' | 'rejected' | 'deleted' | 'unknown';
  failureReason?: string;
  checkedAt?: string;
}

export interface CaptionArtifact {
  file: string;
  format: 'srt' | 'vtt';
  lang: string;
  role: 'rendered-captions' | 'speech';
  cues: number;
  render_key: string;
  sha256: string;
}
export interface CaptionIssue {
  format?: string;
  reason: string;
}

/** One post's ready-made package: the file made for its platform, the cover, the copy (Upload in your browser, the
 * YouTube form). */
export interface PostPackageMsg {
  /** Verified local artifacts; composite rendered captions are not auto-uploadable language tracks. */
  sidecars?: CaptionArtifact[];
  captionIssues?: CaptionIssue[];
  postId: string;
  platform: string;
  video: string;
  cover: string | null;
  title: string;
  description: string;
  tags: string[];
  w: number | null;
  h: number | null;
  duration: number | null;
  /** where Upload in your browser opens */
  uploadUrl: string | null;
}

/** Current YouTube uploads: square or taller, at most three minutes. Source: YouTube Help 15424877. */
export function shortsFit(f: { w?: number | null; h?: number | null; duration?: number | null }): { ok: boolean; why?: 'not-vertical' | 'too-long' | 'unknown' } {
  if (!f.w || !f.h || !f.duration || ![f.w, f.h, f.duration].every((n) => Number.isFinite(n) && n > 0)) return { ok: false, why: 'unknown' };
  if (f.h < f.w) return { ok: false, why: 'not-vertical' };
  if (f.duration > YOUTUBE_FORMATS[1].maxSeconds) return { ok: false, why: 'too-long' };
  return { ok: true };
}

/** Last confirmed platform response; time passing alone is not proof of publication. */
export function apiProcessingFailed(r: YtPublishResult): boolean {
  return !!r.uploadStatus && ['failed', 'rejected', 'deleted'].includes(r.uploadStatus);
}

export function apiDeliveryState(r: YtPublishResult): 'uploaded' | 'scheduled' | 'posted' {
  if (r.uploadStatus && !['processed', 'uploaded'].includes(r.uploadStatus)) return 'uploaded';
  // Older receipts may omit processing status; public visibility alone is not completion evidence.
  if (r.privacy === 'public') return r.uploadStatus === 'processed' ? 'posted' : 'uploaded';
  return r.privacy === 'private' && r.publishAt && !r.lockedPrivate ? 'scheduled' : 'uploaded';
}

/** Already on a platform, so a local edit cannot change its remote schedule/file/account. */
export function postDelivered(p: { state: string }): boolean {
  return ['uploaded', 'scheduled', 'posted'].includes(p.state);
}
