// The free offline voice (Kokoro, Apple silicon): its weights are a one-time download (packaging/assets.json
// tts-kokoro), not in the installer. Started from the voice failure ("Download the free voice") and when she picks
// the free voice for a video that had no key.
export const FREE_VOICE_GROUP = 'tts-kokoro';

type AssetsApi = Pick<Window['desk']['assets'], 'status' | 'install'>;

/** Where the free voice's download stands after asking for it: started now, already on its way, on disk, or not
 * offered by this app (Intel Mac / Windows). */
export type FreeVoiceState = 'started' | 'downloading' | 'installed' | 'unavailable';

/** Start the free voice's download when this app has it and it isn't on disk or on its way. */
export async function ensureFreeVoice(assets: AssetsApi | undefined = window.desk?.assets): Promise<FreeVoiceState> {
  if (!assets) return 'unavailable';
  const s = await assets.status();
  const g = s.groups.find((x) => x.id === FREE_VOICE_GROUP);
  if (!g) return 'unavailable';
  if (g.installed) return 'installed';
  if (g.queued || g.progress) return 'downloading';
  await assets.install([FREE_VOICE_GROUP]);
  return 'started';
}
