// A platform's display name in the UI language for any id the engine or the app uses: "instagram", "x:vertical",
// a package key ("instagram-reels", "tiktok-vertical"), or an adapter id ("x-web"). Never returns a raw `pf.*` key.
import { platformInfo } from '../../../shared/platforms';
import { has, tk } from '../i18n';

const ALIASES: Record<string, string> = { shipinhao: 'wechat-channels', 'x-web': 'x', 'youtube-studio': 'youtube' };

/** "x:vertical" / "instagram-reels" / "x-web" (adapter id) -> the platform it is for. */
export function platformKey(id: string): string {
  const base = id.split(':')[0];
  if (platformInfo(base)) return base;
  if (ALIASES[base]) return ALIASES[base];
  const i = base.lastIndexOf('-');
  return i > 0 && platformInfo(base.slice(0, i)) ? base.slice(0, i) : base;
}

/** "instagram-reels" -> "Instagram Reels" (its own name when there is one), "tiktok-vertical" -> "TikTok". */
export function platformName(id: string): string {
  const own = id.trim().replace(':', '-');
  if (has(`pf.${own}`)) return tk(`pf.${own}`);
  const k = platformKey(id.trim());
  if (has(`pf.${k}`)) return tk(`pf.${k}`);
  return platformInfo(k)?.labels.en ?? k;
}
