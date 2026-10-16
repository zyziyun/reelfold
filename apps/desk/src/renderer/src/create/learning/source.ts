/** Sources are references, not commands. Only official YouTube embed hosts may become a remote frame. */
export function youtubeSource(value: string): { id: string; start: number; embed: string } | null {
  try {
    const u = new URL(value);
    if (u.protocol !== 'https:') return null;
    const host = u.hostname.toLowerCase();
    const id = host === 'youtu.be' ? u.pathname.slice(1) : ['www.youtube.com', 'youtube.com', 'm.youtube.com'].includes(host) ? (u.pathname === '/watch' ? u.searchParams.get('v') : u.pathname.match(/^\/(?:shorts|embed)\/([\w-]+)/)?.[1]) : null;
    if (!id || !/^[\w-]{11}$/.test(id)) return null;
    const time = u.searchParams.get('t') ?? u.searchParams.get('start') ?? u.hash.match(/t=([^&]+)/)?.[1] ?? '0';
    const start = /^\d+$/.test(time) ? Number(time) : Array.from(time.matchAll(/(\d+)(h|m|s)/g)).reduce((n, x) => n + Number(x[1]) * ({ h: 3600, m: 60, s: 1 }[x[2]] ?? 0), 0);
    return { id, start, embed: `https://www.youtube-nocookie.com/embed/${id}?start=${start}&playsinline=1&enablejsapi=1&widget_referrer=https%3A%2F%2Fapp.reelfold.desk` };
  } catch { return null; }
}

export function youtubeTime(data: unknown): number | null {
  try {
    const msg = (typeof data === 'string' ? JSON.parse(data) : data) as { event?: string; info?: { currentTime?: unknown } };
    const value = msg?.info?.currentTime;
    return msg?.event === 'infoDelivery' && typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
  } catch { return null; }
}

/** Hand off playback/login to the user's normal browser at the chosen source position. */
export function youtubeBrowserUrl(value: string, at?: number): string | null {
  const source = youtubeSource(value);
  if (!source) return null;
  const time = typeof at === 'number' && Number.isFinite(at) && at >= 0 ? Math.floor(at) : source.start;
  return `https://www.youtube.com/watch?v=${source.id}&t=${time}s`;
}
