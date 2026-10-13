// The free offline voices (Apple silicon): their weights are one-time downloads (packaging/assets.json), not in the
// installer - English: Kokoro (tts-kokoro, about 330 MB); Chinese: Qwen3-TTS (tts-qwen-zh, about 3 GB). Started from
// the voice failure ("Download the free voice" / "Download the Chinese voice"), when she picks the free voice for a
// video that had no key, and from Settings > Voice.
import { EN_VOICE_GROUP, ZH_VOICE_GROUP } from '../../../shared/voices';

export const FREE_VOICE_GROUP = EN_VOICE_GROUP;
export const CHINESE_VOICE_GROUP = ZH_VOICE_GROUP;

type AssetsApi = Pick<Window['desk']['assets'], 'status' | 'install'>;

/** Where the free voice's download stands after asking for it: started now, already on its way, on disk, or not
 * offered by this app (Intel Mac / Windows). */
export type FreeVoiceState = 'started' | 'downloading' | 'installed' | 'unavailable';

/** Start a free voice's download (default: the English one) when this app has it and it isn't on disk or on its way. */
export async function ensureFreeVoice(assets: AssetsApi | undefined = window.desk?.assets, group: string = FREE_VOICE_GROUP): Promise<FreeVoiceState> {
  if (!assets) return 'unavailable';
  const s = await assets.status();
  const g = s.groups.find((x) => x.id === group);
  if (!g) return 'unavailable';
  if (g.installed) return 'installed';
  if (g.queued || g.progress) return 'downloading';
  await assets.install([group]);
  return 'started';
}
