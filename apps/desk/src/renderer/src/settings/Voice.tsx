// Settings › Voice: the free voices that narrate videos on this Mac. Chinese: Qwen3-TTS with five Mandarin speakers
// (pick one, listen first) - once downloaded it narrates every Chinese version; until then they get English narration
// with Chinese subtitles, or Kokoro's robotic Mandarin when she switches "the built-in Chinese voice" on; English: Kokoro. Each is a one-time download (packaging/assets.json); the samples are
// real takes of each voice shipped with the app (scripts/voice-samples/make_voice_samples.py), so she can choose
// before downloading. The choice applies to the next take (main/v02.ts writes the engine's prefs file).
import { useEffect, useRef, useState } from 'react';
import { Check, Pause, Play } from 'lucide-react';
import type { SystemVoice } from '../../../shared/voices';
import { useEngine } from '../lib/engine';
import { media } from '../v4/kit';
import { EN_VOICE_GROUP, ZH_VOICE_GROUP, ZH_VOICES, zhVoiceOf, type ZhVoice } from '../../../shared/voices';
import type { AssetGroupStatus } from '../../../shared/assets';
import { useAssets } from '../components/assets';
import { t, tk } from '../i18n';
import { errText } from '../v4/msg';
import { useUi } from '../v4/ui';
import { Group, Page, Row, Toggle } from './kit';
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
  const serial = useRef(0);
  const ui = useUi();
  const [playing, setPlaying] = useState<string | null>(null);
  useEffect(() => () => { serial.current++; audio.current?.pause(); }, []);
  const toggle = async (id: string, resolve?: () => Promise<string>) => {
    const ticket = ++serial.current;
    audio.current?.pause();
    if (playing === id) {
      setPlaying(null);
      return;
    }
    setPlaying(id);
    let url: string;
    try { url = resolve ? await resolve() : VOICE_SAMPLES[id as keyof typeof VOICE_SAMPLES]; }
    catch (e) { if (ticket === serial.current) { setPlaying(null); ui.toast(errText(e), {error: true}); } return; }
    if (ticket !== serial.current) return;
    const a = new Audio(url);
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
export function DownloadState({ g, testId }: { g: AssetGroupStatus; testId: string }) {
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
  const { client } = useEngine();
  const [system, setSystem] = useState<SystemVoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    if (!client) return;
    let alive = true;
    setLoading(true); setLoadError(false);
    client.systemVoices().then(r => { if (alive) setSystem(r.voices); })
      .catch(() => { if (alive) setLoadError(true); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [client, refresh]);
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
  const setLocal = (on: boolean) =>
    void save({ zhLocal: on })
      .then(() => ui.toast(t(on ? 'vo.local.on' : 'vo.local.off')))
      .catch((e) => ui.toast(errText(e), { error: true }));
  return (
    <Page title={t('vo.nav')} lead={t('vo.lead')} testId="settings-voice">
      {assets && !zh && !en && !system.length && <div className="s2-note">{t('vo.noMac')}</div>}
      <Group title={t('vo.zh.title')} testId="voice-source">
        <Row label={t('vo.source')} hint={t('vo.source.hint')}>
          <select value={s.zhEngine ?? 'qwen'} data-testid="voice-source-pick" onChange={e => {
            const zhEngine = e.target.value as 'qwen' | 'system';
            void save({zhEngine, ...(zhEngine === 'system' && !s.systemZhVoice && system[0] ? {systemZhVoice: system[0].id} : {})})
              .catch(e => ui.toast(errText(e), {error: true}));
          }}>
            <option value="qwen">{t('vo.zh.engine')}</option>
            <option value="system" disabled={!system.length && s.zhEngine !== 'system'}>{t('vo.system')}</option>
          </select>
        </Row>
        <Row label={t('vo.system')} hint={t('vo.system.hint')}>
          <button className="s2-link" onClick={() => setRefresh(n => n + 1)} data-testid="voice-system-refresh">{t('vo.refresh')}</button>
        </Row>
        {loading ? <p className="s2-note">{t('vo.loading')}</p> : !system.length || loadError ? <p className="s2-note">{t(loadError ? 'vo.system.error' : 'vo.system.empty')}</p> : null}
        {s.zhEngine === 'system' && <Row label={t('vo.system.pick')}>
          <select value={s.systemZhVoice ?? ''} data-testid="voice-system-pick" onChange={e => void save({systemZhVoice: e.target.value}).catch(e => ui.toast(errText(e), {error: true}))}>
            {!system.some(v => v.id === s.systemZhVoice) && <option value={s.systemZhVoice ?? ''} disabled>{s.systemZhVoice ? t('vo.system.missing', {name: s.systemZhVoice}) : t('vo.system.pick')}</option>}
            {system.map(v => <option key={v.id} value={v.id}>{v.name} · {v.lang}</option>)}
          </select>
          <button className="s2-link" disabled={!client || !system.some(v => v.id === s.systemZhVoice)} data-testid="voice-system-play"
            onClick={() => void sample.toggle('system', async () => media((await client!.systemVoicePreview(s.systemZhVoice!)).path))}>
            {sample.playing === 'system' ? <Pause className="ico" /> : <Play className="ico" />}{t(sample.playing === 'system' ? 'vo.stop' : 'vo.system.preview')}
          </button>
        </Row>}
      </Group>
      {s.zhEngine !== 'system' && <Group title={t('vo.zh.title')} testId="voice-zh">
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
      </Group>}
      {s.zhEngine !== 'system' && <p className="s2-lead" style={{ marginTop: -4 }}>
        {t('vo.pickHint')}
      </p>}
      {s.zhEngine !== 'system' && zh && !zh.installed && (
        <Group testId="voice-zh-local">
          <Row label={t('vo.local.label')} hint={t('vo.local.hint')}>
            <Toggle checked={s.zhLocal === true} onChange={setLocal} label={t('vo.local.label')} testId="voice-zh-local-toggle" />
          </Row>
        </Group>
      )}
      <Group title={t('vo.en.title')} testId="voice-en">
        <Row label={t('vo.en.engine')} hint={t('vo.en.engineHint')}>
          {en ? <DownloadState g={en} testId="voice-en" /> : null}
        </Row>
        <Row label={t('vo.en.sample')}>
          <PlayButton id="en" name={t('vo.en.sample')} sample={sample} />
        </Row>
      </Group>
      {s.zhEngine !== 'system' && <p className="s2-lead">{t('vo.keyNote')}</p>}
    </Page>
  );
}
