// Settings › Voice: the free voices that narrate videos on this Mac. Chinese: Qwen3-TTS with five Mandarin speakers
// (pick one, listen first); English: Kokoro. Each is a one-time download (packaging/assets.json); the samples are
// real takes of each voice shipped with the app (scripts/voice-samples/make_voice_samples.py), so she can choose
// before downloading. The choice applies to the next take (main/v02.ts writes the engine's prefs file).
import { useEffect, useRef, useState } from 'react';
import { Check, Pause, Play } from 'lucide-react';
import { EN_VOICE_GROUP, ZH_VOICE_GROUP, ZH_VOICES, zhVoiceOf, type ZhVoice } from '../../../shared/voices';
import type { AssetGroupStatus } from '../../../shared/assets';
import { useAssets } from '../components/assets';
import { t, tk } from '../i18n';
import { errText } from '../v4/msg';
import { useUi } from '../v4/ui';
import { Group, Page, Row } from './kit';
import type { SettingsCtx } from './registry';
import enKokoro from './voice-samples/en-kokoro.mp3';
import zhDylan from './voice-samples/zh-dylan.mp3';
import zhEric from './voice-samples/zh-eric.mp3';
import zhSerena from './voice-samples/zh-serena.mp3';
import zhUncleFu from './voice-samples/zh-uncle_fu.mp3';
import zhVivian from './voice-samples/zh-vivian.mp3';

export const VOICE_SAMPLES: Record<ZhVoice | 'en', string> = {
  serena: zhSerena,
  vivian: zhVivian,
  uncle_fu: zhUncleFu,
  dylan: zhDylan,
  eric: zhEric,
  en: enKokoro,
};

/** One shared player: a new sample stops the one playing; the same button again stops it. */
function useSample() {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  useEffect(() => () => audio.current?.pause(), []);
  const toggle = (id: string) => {
    audio.current?.pause();
    if (playing === id) {
      setPlaying(null);
      return;
    }
    const a = new Audio(VOICE_SAMPLES[id as keyof typeof VOICE_SAMPLES]);
    a.onended = () => setPlaying((p) => (p === id ? null : p));
    audio.current = a;
    setPlaying(id);
    void a.play().catch(() => setPlaying(null));
  };
  return { playing, toggle };
}

function PlayButton({ id, name, sample }: { id: string; name: string; sample: ReturnType<typeof useSample> }) {
  const on = sample.playing === id;
  return (
    <button className="s2-link" onClick={() => sample.toggle(id)} aria-label={on ? t('vo.stop') : t('vo.play', { name })} title={on ? t('vo.stop') : t('vo.play', { name })} data-testid={`voice-play-${id}`}>
      {on ? <Pause className="ico" /> : <Play className="ico" />}
    </button>
  );
}

/** Download / progress / Ready for one asset group. */
function DownloadState({ g, testId }: { g: AssetGroupStatus; testId: string }) {
  const ui = useUi();
  const act = (p: Promise<unknown>) => void p.catch((e) => ui.toast(errText(e), { error: true }));
  if (g.installed) {
    return (
      <span className="s2-val" data-testid={`${testId}-ready`}>
        <Check className="ico" /> {t('vo.ready')}
      </span>
    );
  }
  if (g.progress || g.queued) {
    const pct = g.progress?.total ? Math.floor((g.progress.received / g.progress.total) * 100) : 0;
    return (
      <span className="row" style={{ gap: 12 }}>
        <span className="s2-val" data-testid={`${testId}-progress`}>
          {g.progress ? t('vo.downloading', { pct }) : t('vo.queued')}
        </span>
        <button className="s2-link muted" onClick={() => act(window.desk.assets.cancel(g.id))}>
          {t('vo.cancel')}
        </button>
      </span>
    );
  }
  return (
    <button className="btn" onClick={() => act(window.desk.assets.install([g.id]))} data-testid={`${testId}-download`}>
      {g.error ? t('vo.retry') : t('vo.download')}
    </button>
  );
}

export function VoiceSection({ settings: s, save }: SettingsCtx) {
  const assets = useAssets();
  const ui = useUi();
  const sample = useSample();
  const zh = assets?.groups.find((g) => g.id === ZH_VOICE_GROUP);
  const en = assets?.groups.find((g) => g.id === EN_VOICE_GROUP);
  const current = zhVoiceOf(s.zhVoice);
  const pick = (v: ZhVoice) => {
    if (v === current) return;
    void save({ zhVoice: v })
      .then(() => ui.toast(t('vo.saved', { name: tk(`vo.v.${v}`) })))
      .catch((e) => ui.toast(errText(e), { error: true }));
  };
  return (
    <Page title={t('vo.nav')} lead={t('vo.lead')} testId="settings-voice">
      {assets && !zh && !en && <div className="s2-note">{t('vo.noMac')}</div>}
      <Group title={t('vo.zh.title')} testId="voice-zh">
        <Row label={t('vo.zh.engine')} hint={t('vo.zh.engineHint')}>
          {zh ? <DownloadState g={zh} testId="voice-zh" /> : null}
        </Row>
        <div role="radiogroup" aria-label={t('vo.zh.title')}>
          {ZH_VOICES.map((v) => (
            <Row
              key={v}
              testId={`voice-zh-${v}`}
              label={
                <label className="row" style={{ gap: 10, cursor: 'pointer' }}>
                  <input type="radio" name="zh-voice" checked={v === current} onChange={() => pick(v)} data-testid={`voice-pick-${v}`} />
                  <span>{tk(`vo.v.${v}`)}</span>
                </label>
              }
              hint={tk(`vo.v.${v}.hint`)}
            >
              <PlayButton id={v} name={tk(`vo.v.${v}`)} sample={sample} />
            </Row>
          ))}
        </div>
      </Group>
      <p className="s2-lead" style={{ marginTop: -4 }}>
        {t('vo.pickHint')}
      </p>
      <Group title={t('vo.en.title')} testId="voice-en">
        <Row label={t('vo.en.engine')} hint={t('vo.en.engineHint')}>
          {en ? <DownloadState g={en} testId="voice-en" /> : null}
        </Row>
        <Row label={t('vo.en.sample')}>
          <PlayButton id="en" name={t('vo.en.sample')} sample={sample} />
        </Row>
      </Group>
      <p className="s2-lead">{t('vo.keyNote')}</p>
    </Page>
  );
}
