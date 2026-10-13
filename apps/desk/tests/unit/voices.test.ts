// The free Chinese voice (Qwen3-TTS CustomVoice via mlx-audio, Apple silicon): a one-time download like Kokoro
// (packaging/assets.json tts-qwen-zh), five Mandarin speakers picked in Settings › Voice, the choice handed to the
// engine through its prefs file (vstudio.tts.prefs / zh_voice).
import fs from 'node:fs';
import path from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { AssetManifest, AssetsStatusMsg } from '../../src/shared/assets';
import { groupsFor } from '../../src/shared/assets';
import { ipcSchemas } from '../../src/shared/ipc';
import type { PilotFailure } from '../../src/shared/v02';
import { ttsPrefsOf, ZH_VOICE_DEFAULT, ZH_VOICE_GROUP, ZH_VOICES, zhVoiceOf } from '../../src/shared/voices';
import { setLang, tk } from '../../src/renderer/src/i18n';
import { CHINESE_VOICE_GROUP, ensureFreeVoice } from '../../src/renderer/src/lib/freeVoice';
import { failureReason } from '../../src/renderer/src/v4/Failure';

afterEach(() => setLang('en'));

const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, '..', '..', 'packaging', 'assets.json'), 'utf8')) as AssetManifest;
const ttsPy = fs.readFileSync(path.resolve(__dirname, '../../../../lib/vstudio/tts.py'), 'utf8');

describe('the Chinese voice download (packaging/assets.json tts-qwen-zh)', () => {
  const g = manifest.groups.find((x) => x.id === ZH_VOICE_GROUP)!;
  it('is optional, Apple silicon only, pinned and checksummed, Apache-2.0', () => {
    expect(CHINESE_VOICE_GROUP).toBe(ZH_VOICE_GROUP);
    expect(g.required).toBe(false); // about 3 GB: never part of the first-run download
    expect(g.targets).toEqual(['darwin-arm64']);
    expect(groupsFor(manifest, 'win32-x64').map((x) => x.id)).not.toContain(ZH_VOICE_GROUP);
    expect(g.env).toEqual({ VSTUDIO_QWEN_TTS_MODEL: '' });
    expect(g.licence).toMatch(/Apache-2\.0/);
    for (const f of g.files) {
      expect(f.url).toMatch(/^https:\/\/huggingface\.co\/mlx-community\/Qwen3-TTS-12Hz-1\.7B-CustomVoice-8bit\/resolve\/[0-9a-f]{40}\//);
      expect(f.sha256).toMatch(/^[0-9a-f]{64}$/);
      expect(f.size).toBeGreaterThan(0);
    }
    const dests = g.files.map((f) => f.dest.replace(/^\.\//, ''));
    // the text tokenizer is read by vstudio.qwen_bpe (vocab + merges + the special tokens of tokenizer_config)
    expect(dests).toEqual(expect.arrayContaining(['config.json', 'model.safetensors', 'vocab.json', 'merges.txt', 'tokenizer_config.json', 'speech_tokenizer/model.safetensors']));
    const total = g.files.reduce((a, f) => a + f.size, 0);
    expect(total).toBeGreaterThan(2.8e9);
    expect(total).toBeLessThan(3.3e9); // "about 3 GB" in the app's words
  });

  it('has a name in Settings > Downloads in every language', () => {
    for (const lang of ['en', 'zh-CN', 'fr'] as const) {
      setLang(lang);
      expect(tk(`assets.group.${ZH_VOICE_GROUP}`)).not.toMatch(/assets\.group/);
    }
  });
});

describe('the Chinese speakers', () => {
  it('are the engine’s (vstudio.tts.QWEN_ZH_VOICES), serena first and the default', () => {
    const m = ttsPy.match(/QWEN_ZH_VOICES = \(([^)]*)\)/);
    expect(m).toBeTruthy();
    expect([...m![1].matchAll(/"([a-z_]+)"/g)].map((x) => x[1])).toEqual([...ZH_VOICES]);
    expect(ttsPy).toMatch(/ZH_VOICE = \{[^}]*"qwen": "serena"/);
    expect(ZH_VOICE_DEFAULT).toBe('serena');
  });

  it('reach the engine as its prefs file; anything else is the default', () => {
    expect(ttsPrefsOf({ zhVoice: 'vivian' })).toEqual({ zh_voice: 'vivian' });
    expect(ttsPrefsOf({})).toEqual({ zh_voice: 'serena' });
    expect(zhVoiceOf('zf_xiaobei')).toBe('serena');
    expect(ipcSchemas['settings:set'].safeParse({ zhVoice: 'dylan' }).success).toBe(true);
    expect(ipcSchemas['settings:set'].safeParse({ zhVoice: 'zf_xiaobei' }).success).toBe(false);
  });

  it('each has a name, a hint and a sample in every language', () => {
    for (const lang of ['en', 'zh-CN', 'fr'] as const) {
      setLang(lang);
      for (const v of ZH_VOICES) {
        expect(tk(`vo.v.${v}`)).not.toMatch(/vo\.v/);
        expect(tk(`vo.v.${v}.hint`)).not.toMatch(/vo\.v/);
      }
    }
    const dir = path.join(__dirname, '..', '..', 'src', 'renderer', 'src', 'settings', 'voice-samples');
    for (const f of [...ZH_VOICES.map((v) => `zh-${v}.mp3`), 'en-kokoro.mp3']) {
      const st = fs.statSync(path.join(dir, f));
      expect(st.size).toBeGreaterThan(10e3);
      expect(st.size).toBeLessThan(120e3);
    }
  });
});

describe('before the Chinese voice is downloaded', () => {
  const st = (over: Partial<AssetsStatusMsg['groups'][0]> = {}): AssetsStatusMsg & { bundled: boolean } => ({
    bundled: true,
    dir: '/x',
    busy: false,
    restartNeeded: false,
    groups: [{ id: ZH_VOICE_GROUP, required: false, installed: false, bytes: 1, licence: '', ...over }],
  });

  it('the voice failure offers the Chinese voice', () => {
    const f: PilotFailure = { state: 'failed', code: 'tool-voice', provider: null, error: 'x', at: 1, stage: 'voice', params: { tool: 'voice', fix: 'download-zh-voice' } };
    expect(failureReason(f)).toMatch(/Download the free Chinese voice once \(about 3 GB\)/);
    setLang('zh-CN');
    expect(failureReason(f)).toMatch(/下载一次免费的中文配音（约 3 GB）/);
  });

  it('ensureFreeVoice starts that group', async () => {
    const install = vi.fn(async () => st({ queued: true }));
    expect(await ensureFreeVoice({ status: async () => st(), install }, ZH_VOICE_GROUP)).toBe('started');
    expect(install).toHaveBeenCalledWith([ZH_VOICE_GROUP]);
  });
});
