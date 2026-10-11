// Dogfood 2026-10-11: her course explainer (Chinese narration, autopilot) stopped at the voice with a raw
// "RuntimeError: OPENAI_API_KEY is not set in the environment" traceback. A missing key now reads as the service and
// the fix; the voice question offers the free voice (or the key, when this computer has no free voice); and the
// autopilot's choice of the free voice is said in her words. English, 简体中文, Français.
import { afterEach, describe, expect, it } from 'vitest';
import type { AutopilotDecision, InboxItem } from '../../src/shared/v04';
import type { PilotFailure } from '../../src/shared/v02';
import { setLang, tk } from '../../src/renderer/src/i18n';
import { sessionFixesEn, sessionFixesFr, sessionFixesZh } from '../../src/renderer/src/i18n/locales/sessionFixes';
import { inboxTitle, noKeyBody } from '../../src/renderer/src/lib/inboxView';
import { decisionWords } from '../../src/renderer/src/lib/pipeline';
import { failureReason, keyFocus } from '../../src/renderer/src/v4/Failure';

afterEach(() => setLang('en'));

const f = (o: Partial<PilotFailure>): PilotFailure => ({ state: 'failed', code: 'unknown', provider: null, error: 'x', at: 1, ...o });

const voice = (free: string | null): InboxItem => ({
  key: 'b'.repeat(16),
  kind: 'voice-pick',
  group: 'spend',
  project: { id: 'p1', name: 'MCP 课', kind: 'project' },
  code: 'checkpoint.voice-pick',
  params: { n: free ? 1 : 0 },
  text: '配音确认',
  options: [],
  source: 'engine',
  no_key: { service: 'OpenAI', engine: 'openai', free_engine: free, free_voice: free ? 'zf_xiaobei' : null },
});

describe('a missing key names the service and the fix', () => {
  it('the voice: Try again takes the free voice, or add the key', () => {
    const x = f({ code: 'ai-key-missing', stage: 'voice', params: { service: 'OpenAI', fix: 'free-voice' } });
    expect(failureReason(x)).toBe(
      'There’s no OpenAI key in Reelfold, so this step couldn’t run. Press Try again to make the voice with the free voice on this computer, or add the key in Settings › AI.',
    );
    expect(failureReason(x)).not.toMatch(/OPENAI_API_KEY|Traceback|RuntimeError/);
    expect(keyFocus(x)).toBe('openai');
    setLang('zh-CN');
    expect(failureReason(x)).toMatch(/^千剪里还没有 OpenAI 密钥.*免费配音/);
    setLang('fr');
    expect(failureReason(x)).toMatch(/^Reelfold n’a pas de clé OpenAI.*voix gratuite/);
  });
  it('no free voice here (or another service): add the key, then try again', () => {
    expect(failureReason(f({ code: 'ai-key-missing', params: { service: 'Hedra', fix: 'add-key' } }))).toBe(
      'There’s no Hedra key in Reelfold, so this step couldn’t run. Add it in Settings › AI, then try again.',
    );
    expect(keyFocus(f({ params: { service: 'Hedra' } }))).toBe('hedra');
    expect(keyFocus(f({ params: { service: 'ElevenLabs' } }))).toBeUndefined();
    expect(failureReason(f({ code: 'ai-key-missing' }))).toMatch(/^There’s no API key/);
  });
});

describe('the voice question when the paid voice has no key', () => {
  it('offers the free voice this computer has', () => {
    expect(inboxTitle(voice('kokoro'))).toBe('No OpenAI key for the voice');
    expect(noKeyBody(voice('kokoro'))).toBe('The free voice on this computer reads the script (zf_xiaobei). It costs nothing; you can switch to OpenAI later.');
    setLang('zh-CN');
    expect(inboxTitle(voice('kokoro'))).toBe('配音缺少 OpenAI 密钥');
  });
  it('with no free voice here, adding the key is the way', () => {
    expect(noKeyBody(voice(null))).toBe('There’s no free voice on this computer either. Add your OpenAI key in Settings, then press Try again.');
    setLang('fr');
    expect(noKeyBody(voice(null))).toMatch(/Ajoutez votre clé OpenAI/);
  });
  it('the autopilot says it used the free voice', () => {
    const d: AutopilotDecision = { checkpoint: 'voice', item: 'ep1', kind: 'voice-pick', by: 'rules', reason_code: 'free-voice', params: { service: 'OpenAI' } } as AutopilotDecision;
    const w = decisionWords(d);
    expect(tk(w.key, w.params)).toBe('used the free voice — no OpenAI key');
    setLang('zh-CN');
    expect(tk(w.key, w.params)).toBe('用了免费配音——没有 OpenAI 密钥');
    expect(decisionWords({ ...d, reason_code: 'default' }).key).toBe('ap.d.default');
  });
  it('every new string exists in en, zh-CN and fr', () => {
    for (const k of Object.keys(sessionFixesEn).filter((k) => k.startsWith('voice.noKey') || k.includes('key-missing') || k.includes('Key') || k === 'ap.d.freeVoice')) {
      expect(sessionFixesZh[k as keyof typeof sessionFixesEn], k).toBeTruthy();
      expect(sessionFixesFr[k as keyof typeof sessionFixesEn], k).toBeTruthy();
    }
  });
});
