// The app's free voices (Apple silicon, offline): English = Kokoro (asset group tts-kokoro), Chinese = Qwen3-TTS
// CustomVoice (asset group tts-qwen-zh). The Chinese speakers are vstudio.tts.QWEN_ZH_VOICES (tests/unit/voices.test.ts
// keeps the two lists equal); the choice reaches the engine through the prefs file (main/v02.ts ttsPrefs, env
// VSTUDIO_TTS_PREFS), read on every take - no engine restart.
export const EN_VOICE_GROUP = 'tts-kokoro';
export const ZH_VOICE_GROUP = 'tts-qwen-zh';
export const ZH_VOICES = ['serena', 'vivian', 'uncle_fu', 'dylan', 'eric'] as const;
export type ZhVoice = (typeof ZH_VOICES)[number];
export const ZH_VOICE_DEFAULT: ZhVoice = 'serena';

export function zhVoiceOf(v: unknown): ZhVoice {
  return (ZH_VOICES as readonly string[]).includes(String(v)) ? (v as ZhVoice) : ZH_VOICE_DEFAULT;
}

/** The engine's prefs file content for settings `zhVoice`. */
export function ttsPrefsOf(s: { zhVoice?: string }): { zh_voice: ZhVoice } {
  return { zh_voice: zhVoiceOf(s.zhVoice) };
}
