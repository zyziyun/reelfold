// Small platform marks for chips, tabs and calendar posts: a coloured rounded square with a short glyph (not the
// platforms' trademarked logos). Unknown ids get a neutral letter mark. Marks and the display order come from the
// shared platform registry (src/shared/platforms.ts).
import { PLATFORMS, PLATFORM_IDS } from '../../../shared/platforms';
import { platformKey, platformName } from '../lib/platformName';

/** Platforms the calendar can schedule to, in display order: English / global, Chinese, other languages. */
export const SCHEDULE_PLATFORMS = PLATFORM_IDS;
export { platformKey };

export function PlatformIcon({ id, size = 16, title }: { id: string; size?: number; title?: string }) {
  const k = platformKey(id);
  const m = PLATFORMS.find((p) => p.id === k)?.mark ?? { g: (k[0] ?? '?').toUpperCase(), bg: 'var(--border-strong)' };
  const label = title ?? platformName(id);
  return (
    <span
      className="pfi"
      role="img"
      aria-label={label}
      title={label}
      data-pf={k}
      style={{
        display: 'inline-grid',
        placeItems: 'center',
        width: size,
        height: size,
        borderRadius: Math.round(size / 4),
        background: m.bg,
        color: m.fg ?? '#fff',
        fontSize: Math.round(size * (m.g.length > 1 ? 0.5 : 0.62)),
        fontWeight: 700,
        lineHeight: 1,
        flex: 'none',
      }}
    >
      {m.g}
    </span>
  );
}
