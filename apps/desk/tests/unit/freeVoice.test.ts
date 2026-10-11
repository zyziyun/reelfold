// The free offline voice (Kokoro via mlx-audio, Apple silicon): bundled code, weights downloaded once through the
// first-run asset system (packaging/assets.json tts-kokoro: pinned Hugging Face revision, sha256 per file, optional,
// shown in Settings > Downloads). Before that download the voice step fails as tool-voice and the desk offers it.
import fs from 'node:fs';
import path from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { AssetManifest, AssetsStatusMsg } from '../../src/shared/assets';
import { groupsFor } from '../../src/shared/assets';
import type { PilotFailure } from '../../src/shared/v02';
import { setLang, tk } from '../../src/renderer/src/i18n';
import { ensureFreeVoice, FREE_VOICE_GROUP } from '../../src/renderer/src/lib/freeVoice';
import { failureReason } from '../../src/renderer/src/v4/Failure';

afterEach(() => setLang('en'));

const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, '..', '..', 'packaging', 'assets.json'), 'utf8')) as AssetManifest;

describe('the free voice download (packaging/assets.json)', () => {
  const g = manifest.groups.find((x) => x.id === FREE_VOICE_GROUP)!;
  it('is optional, Apple silicon only, pinned and checksummed', () => {
    expect(g).toBeTruthy();
    expect(g.required).toBe(false); // never part of the first-run download: fetched the first time a video needs it
    expect(g.targets).toEqual(['darwin-arm64']);
    expect(groupsFor(manifest, 'win32-x64').map((x) => x.id)).not.toContain(FREE_VOICE_GROUP);
    expect(g.env).toEqual({ VSTUDIO_KOKORO_MODEL: '' });
    expect(g.licence).toMatch(/Apache-2\.0/);
    for (const f of g.files) {
      expect(f.url).toMatch(/^https:\/\/huggingface\.co\/mlx-community\/Kokoro-82M-bf16\/resolve\/[0-9a-f]{40}\//);
      expect(f.sha256).toMatch(/^[0-9a-f]{64}$/);
      expect(f.size).toBeGreaterThan(0);
    }
    const dests = g.files.map((f) => f.dest.replace(/^\.\//, ''));
    // the engine's defaults: zf_xiaobei (Chinese), af_heart (English)
    expect(dests).toEqual(expect.arrayContaining(['config.json', 'kokoro-v1_0.safetensors', 'voices/zf_xiaobei.safetensors', 'voices/af_heart.safetensors']));
    const total = g.files.reduce((a, f) => a + f.size, 0);
    expect(total).toBeGreaterThan(300e6);
    expect(total).toBeLessThan(360e6); // "about 330 MB" in the failure's words
  });

  it('has a name in Settings > Downloads in every language', () => {
    for (const lang of ['en', 'zh-CN', 'fr'] as const) {
      setLang(lang);
      expect(tk(`assets.group.${FREE_VOICE_GROUP}`)).not.toMatch(/assets\.group/);
    }
  });
});

describe('before the download', () => {
  const st = (over: Partial<AssetsStatusMsg['groups'][0]> = {}): AssetsStatusMsg & { bundled: boolean } => ({
    bundled: true,
    dir: '/x',
    busy: false,
    restartNeeded: false,
    groups: [{ id: 'core', required: true, installed: true, bytes: 1, licence: '' }, { id: FREE_VOICE_GROUP, required: false, installed: false, bytes: 1, licence: '', ...over }],
  });

  it('the voice failure says what is missing and how to get it', () => {
    const f: PilotFailure = { state: 'failed', code: 'tool-voice', provider: null, error: 'x', at: 1, stage: 'voice', params: { tool: 'voice', fix: 'download-voice' } };
    expect(failureReason(f)).toBe('The free voice isn’t downloaded on this computer yet. Download it once (about 330 MB), then press Try again.');
    setLang('zh-CN');
    expect(failureReason(f)).toMatch(/^这台电脑上还没有下载免费配音。\s?下载一次（约 330 MB）/);
  });

  it('ensureFreeVoice starts the download once, only when it is missing', async () => {
    const install = vi.fn(async () => st({ queued: true }));
    expect(await ensureFreeVoice({ status: async () => st(), install })).toBe('started');
    expect(install).toHaveBeenCalledWith([FREE_VOICE_GROUP]);
    expect(await ensureFreeVoice({ status: async () => st({ installed: true }), install })).toBe('installed');
    for (const over of [{ queued: true }, { progress: { received: 1, total: 2, file: 'w' } }]) {
      expect(await ensureFreeVoice({ status: async () => st(over), install })).toBe('downloading');
    }
    // an app without the group (Intel Mac / Windows): nothing to download
    expect(await ensureFreeVoice({ status: async () => ({ ...st(), groups: st().groups.slice(0, 1) }), install })).toBe('unavailable');
    expect(install).toHaveBeenCalledTimes(1);
  });
});
