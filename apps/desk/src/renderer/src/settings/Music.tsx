// Settings › Music: the CC0 music library every video's music is picked from (engine: vstudio.music), grouped by
// style, each track with a listen button, its tempo, licence and source, a favourite heart and "Never use". The
// library is a first-run download (asset group music-library); until it is on disk videos use the built-in beds,
// listed below it. Favourites / bans apply at once ($VSTUDIO_HOME/music.json, the engine reads it per pick).
import { useCallback, useEffect, useRef, useState } from 'react';
import { Ban, ExternalLink, Heart, Pause, Play } from 'lucide-react';
import { byStyle, MUSIC_GROUP, type MusicDoc } from '../../../shared/music';
import { useAssets } from '../components/assets';
import { getLang, t, tk } from '../i18n';
import { useEngine } from '../lib/engine';
import { media } from '../v4/kit';
import { errText } from '../v4/msg';
import { useUi } from '../v4/ui';
import { Group, Page, Row } from './kit';
import { DownloadState } from './Voice';

/** One shared player: a new track stops the one playing; the same button again stops it. */
function usePlayer() {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  useEffect(() => () => audio.current?.pause(), []);
  const toggle = (id: string, path: string) => {
    audio.current?.pause();
    if (playing === id) {
      setPlaying(null);
      return;
    }
    const a = new Audio(media(path));
    a.onended = () => setPlaying((p) => (p === id ? null : p));
    audio.current = a;
    setPlaying(id);
    void a.play().catch(() => setPlaying(null));
  };
  return { playing, toggle };
}

interface RowTrack {
  id: string;
  title: string;
  path: string | null;
  favourite: boolean;
  banned: boolean;
  uses: number;
}

function Actions({ tr, player, onPref }: { tr: RowTrack; player: ReturnType<typeof usePlayer>; onPref: (id: string, p: { favourite?: boolean; banned?: boolean }) => void }) {
  const on = player.playing === tr.id;
  const slug = tr.id.replace(/[^a-z0-9]+/gi, '-');
  return (
    <span className="row" style={{ gap: 6 }}>
      {tr.path && (
        <button className="s2-link" onClick={() => player.toggle(tr.id, tr.path!)} aria-label={on ? t('mu.stop') : t('mu.play', { name: tr.title })} title={on ? t('mu.stop') : t('mu.play', { name: tr.title })} data-testid={`music-play-${slug}`}>
          {on ? <Pause className="ico" /> : <Play className="ico" />}
        </button>
      )}
      <button className={`s2-link${tr.favourite ? '' : ' muted'}`} aria-pressed={tr.favourite} onClick={() => onPref(tr.id, { favourite: !tr.favourite })} aria-label={tr.favourite ? t('mu.unfav') : t('mu.fav')} title={tr.favourite ? t('mu.unfav') : t('mu.fav')} data-testid={`music-fav-${slug}`}>
        <Heart className="ico" fill={tr.favourite ? 'currentColor' : 'none'} />
      </button>
      <button className={`s2-link${tr.banned ? '' : ' muted'}`} aria-pressed={tr.banned} onClick={() => onPref(tr.id, { banned: !tr.banned })} aria-label={tr.banned ? t('mu.unban') : t('mu.ban')} title={tr.banned ? t('mu.unban') : t('mu.ban')} data-testid={`music-ban-${slug}`}>
        <Ban className="ico" />
      </button>
    </span>
  );
}

export function MusicSection() {
  const { client } = useEngine();
  const ui = useUi();
  const assets = useAssets();
  const player = usePlayer();
  const [doc, setDoc] = useState<MusicDoc | null>(null);
  const group = assets?.groups.find((g) => g.id === MUSIC_GROUP);
  const installed = group?.installed;

  useEffect(() => {
    if (!client) return;
    void client.music().then(setDoc, (e) => ui.toast(errText(e), { error: true }));
  }, [client, installed, ui]);

  const onPref = useCallback(
    (id: string, p: { favourite?: boolean; banned?: boolean }) => {
      if (!client) return;
      void client.setMusicPref(id, p).then(setDoc, (e) => ui.toast(errText(e), { error: true }));
    },
    [client, ui],
  );

  const hint = (bpm: number | null, licence: string, uses: number, banned: boolean) =>
    [banned ? t('mu.banned') : null, bpm ? t('mu.bpm', { n: Math.round(bpm) }) : t('mu.free'), licence, uses ? t('mu.uses', { n: uses }) : null].filter(Boolean).join(' · ');

  return (
    <Page title={t('mu.nav')} lead={t('mu.lead')} testId="settings-music">
      <Group title={t('mu.library')} testId="music-library">
        <Row label={doc ? t('mu.installed', { n: doc.installed, total: doc.total }) : t('mu.library')} hint={doc ? t('mu.libraryHint', { n: doc.total }) : undefined}>
          {group ? <DownloadState g={group} testId="music-library" /> : null}
        </Row>
        {doc && doc.installed === 0 && <div className="s2-note">{t('mu.notInstalled')}</div>}
      </Group>
      {doc &&
        doc.installed > 0 &&
        byStyle(doc.tracks.filter((x) => x.installed)).map(([style, rows]) => (
          <Group key={style} title={tk(`mu.style.${style}`)} testId={`music-style-${style}`}>
            {rows.map((tr) => (
              <Row
                key={tr.id}
                testId={`music-track-${tr.id.replace(/[^a-z0-9]+/gi, '-')}`}
                label={
                  <span style={{ opacity: tr.banned ? 0.5 : 1 }}>
                    {tr.title}
                    {tr.artist ? <span className="muted"> — {tr.artist}</span> : null}
                  </span>
                }
                hint={
                  <span>
                    {hint(tr.bpm, tr.license, tr.uses, tr.banned)}
                    {tr.licence_evidence && (
                      <>
                        {' · '}
                        <a href={tr.licence_evidence} target="_blank" rel="noreferrer" className="s2-link" title={t('mu.licence')}>
                          {t('mu.licence')} <ExternalLink className="ico" />
                        </a>
                      </>
                    )}
                  </span>
                }
              >
                <Actions tr={tr} player={player} onPref={onPref} />
              </Row>
            ))}
          </Group>
        ))}
      {doc && (
        <Group title={t('mu.builtin')} testId="music-builtin">
          <div className="s2-note">{t('mu.builtinHint')}</div>
          {doc.builtins.map((b) => (
            <Row key={b.id} testId={`music-track-${b.id.replace(/[^a-z0-9]+/gi, '-')}`} label={getLang() === 'zh-CN' ? b.title_zh : b.title} hint={hint(b.bpm, b.license, b.uses, b.banned)}>
              <Actions tr={b} player={player} onPref={onPref} />
            </Row>
          ))}
        </Group>
      )}
      <p className="s2-lead">
        <strong>{t('mu.ownTitle')}</strong> — {t('mu.ownHint')}
      </p>
    </Page>
  );
}
