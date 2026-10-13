// The clip page player at its start, paused (2026-10-13, her "Golden Hour on Elliott Bay" sat black at 0:00 and
// picking a cover changed nothing she could see): the cover she picked - its frame with the title on it as the cover
// will have it, then the render's own cover once the clip is rendered again - or the clip's cover, or a frame from
// inside it; never the black first frame of a fade-in.
import { media, posterAt } from './kit';

export type PosterLook =
  /** a finished cover (the render's, or the clip's own) */
  | { kind: 'cover'; src: string; v?: string | number | null }
  /** a frame of the clip at `t`, with the cover's title on it while the cover is not rendered yet */
  | { kind: 'frame'; file: string; t: number; text?: string | null; style?: string | null };

/** what the player shows paused at its start: the picked cover (rendered or not yet), the clip's cover, a frame */
export function posterLook(o: {
  pick: { t: number; text?: string | null; style?: string | null } | null;
  rendered: string | null;
  renderedV?: string | number | null;
  cover: string | null;
  coverV?: string | number | null;
  file: string | null;
  duration: number;
}): PosterLook | null {
  if (o.rendered) return { kind: 'cover', src: o.rendered, v: o.renderedV };
  if (o.pick && o.file) return { kind: 'frame', file: o.file, t: o.pick.t, text: o.pick.text, style: o.pick.style };
  if (o.cover) return { kind: 'cover', src: o.cover, v: o.coverV };
  return o.file ? { kind: 'frame', file: o.file, t: posterAt(o.duration) } : null;
}

export function CoverPoster({ look }: { look: PosterLook }) {
  if (look.kind === 'cover') return <img src={media(look.src, look.v)} alt="" data-kind="cover" data-src={look.src} />;
  return (
    <>
      <video
        key={look.file}
        src={media(look.file)}
        muted
        preload="auto"
        data-kind="frame"
        data-t={look.t}
        onLoadedMetadata={(e) => {
          const v = e.currentTarget;
          v.currentTime = Math.max(0, Math.min((v.duration || look.t) - 0.05, look.t));
        }}
        ref={(v) => {
          // a new pick on the same file: the same element seeks there
          if (v && v.readyState >= 1 && Math.abs(v.currentTime - look.t) > 0.02) v.currentTime = Math.max(0, Math.min((v.duration || look.t) - 0.05, look.t));
        }}
      />
      {look.text ? (
        <span className={`pp-tt ${look.style ?? 'card'}`} lang="zh-CN" data-testid="player-poster-title">
          {look.text.replace(/\|/g, '\n')}
        </span>
      ) : null}
    </>
  );
}
