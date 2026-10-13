// Settings › Publishing › Video length: how long each platform's version of a video is. Every platform has its own
// habits per kind (engine: references/platforms/<name>.md - YouTube / B站 long cuts with chapters, Shorts / 小红书 /
// TikTok short ones); here she sets her own shortest / longest per platform, which every plan then keeps to. The
// platforms she posts to come first; the rest open on demand. Applies at once ($VSTUDIO_HOME/platforms.json).
import { useEffect, useState } from 'react';
import { fmtDuration, parseSecs, typicalRange, type PlatformLengthRow, type PlatformLengthsDoc } from '../../../shared/platformLengths';
import { getLang, t } from '../i18n';
import { useEngine } from '../lib/engine';
import { platformName } from '../lib/platformName';
import { errText } from '../v4/msg';
import { PlatformIcon } from '../v4/PlatformIcon';
import { useUi } from '../v4/ui';
import { Group, Row } from './kit';

function SecsInput({ value, placeholder, lo, hi, label, onSet, testId }: { value?: number; placeholder: number; lo: number; hi: number; label: string; onSet: (n: number | null) => void; testId: string }) {
  const [v, setV] = useState(value != null ? String(value) : '');
  useEffect(() => setV(value != null ? String(value) : ''), [value]);
  const commit = () => {
    if (!v.trim()) return value != null && onSet(null);
    const n = parseSecs(v, lo, hi);
    if (n == null) return setV(value != null ? String(value) : '');
    if (n !== value) onSet(n);
  };
  return (
    <input
      type="number"
      className="s2-num"
      min={lo}
      max={hi}
      step={5}
      value={v}
      placeholder={String(placeholder)}
      aria-label={label}
      title={label}
      onChange={(e) => setV(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => e.key === 'Enter' && (e.currentTarget as HTMLInputElement).blur()}
      data-testid={testId}
      style={{ width: 76 }}
    />
  );
}

export function VideoLengthGroup({ chosen }: { chosen: string[] | null }) {
  const { client } = useEngine();
  const ui = useUi();
  const [doc, setDoc] = useState<PlatformLengthsDoc | null>(null);
  const [all, setAll] = useState(false);
  useEffect(() => {
    if (!client) return;
    void client.platformLengths().then(setDoc, () => undefined);       // an older engine: the group stays hidden
  }, [client]);
  if (!doc) return null;
  const lang = getLang();
  const mine = chosen?.length ? doc.platforms.filter((r) => chosen.includes(r.platform)) : doc.platforms;
  const rows = all || !chosen?.length ? doc.platforms : mine;
  const set = (r: PlatformLengthRow, v: { min_s?: number; max_s?: number; reset?: boolean }) => {
    if (!client) return;
    void client.setPlatformLength(r.platform, v).then(setDoc, (e) => ui.toast(errText(e), { error: true }));
  };
  const hiOf = (r: PlatformLengthRow) => Math.min(7200, r.hard.max ?? 7200);
  const loOf = (r: PlatformLengthRow) => Math.max(1, Math.ceil(r.hard.min ?? 1));
  return (
    <Group
      title={t('pls.title')}
      testId="settings-video-length"
      action={
        chosen?.length && mine.length < doc.platforms.length ? (
          <button className="s2-link" onClick={() => setAll(!all)} data-testid="video-length-all">
            {all ? t('pls.mine') : t('pls.all', { n: doc.platforms.length })}
          </button>
        ) : undefined
      }
    >
      <div className="s2-row s2-rhint">{t('pls.lead')}</div>
      {rows.map((r) => {
        const [lo, hi] = typicalRange(r);
        const own = r.source === 'settings' && (r.limits.min_s != null || r.limits.max_s != null);
        return (
          <Row
            key={r.platform}
            icon={<PlatformIcon id={r.platform} size={20} />}
            label={platformName(r.platform)}
            hint={
              <span data-testid="video-length-hint">
                {r.form === 'long' ? t('pls.long') : t('pls.short')} · {t('pls.typical', { lo: fmtDuration(lo, lang), hi: fmtDuration(hi, lang) })}
                {own ? ` · ${t('pls.yours')}` : ''}
              </span>
            }
            testId={`video-length-${r.platform}`}
          >
            <SecsInput value={r.limits.min_s} placeholder={lo} lo={loOf(r)} hi={hiOf(r)} label={t('pls.min', { name: platformName(r.platform) })} onSet={(n) => (n == null ? set(r, { reset: true }) : set(r, { min_s: n }))} testId={`video-length-min-${r.platform}`} />
            <span className="faint">–</span>
            <SecsInput value={r.limits.max_s} placeholder={hi} lo={loOf(r)} hi={hiOf(r)} label={t('pls.max', { name: platformName(r.platform) })} onSet={(n) => (n == null ? set(r, { reset: true }) : set(r, { max_s: n }))} testId={`video-length-max-${r.platform}`} />
            <span className="faint small">{t('pls.secs')}</span>
            {own && (
              <button className="s2-link" onClick={() => set(r, { reset: true })} data-testid={`video-length-reset-${r.platform}`}>
                {t('pls.reset')}
              </button>
            )}
          </Row>
        );
      })}
      <div className="s2-row s2-rhint">{t('pls.foot')}</div>
    </Group>
  );
}
