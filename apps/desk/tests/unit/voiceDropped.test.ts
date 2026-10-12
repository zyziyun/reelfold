// Dogfood 2026-10-11: her Chinese course explainer stopped at the voice with "TTS dropped sentences after retries ...
// line 02: ['地基先打好：Tool Calling。']", and the project page only said "Something went wrong while making it".
// The engine now codes it stage-voice-dropped {line, sentence, fix: rephrase-line}: the page names the scene and the
// sentence, and what to do (reword or split it, then Try again). English, 简体中文, Français.
import { afterEach, describe, expect, it } from 'vitest';
import type { InboxItem } from '../../src/shared/v04';
import type { PilotFailure } from '../../src/shared/v02';
import { setLang } from '../../src/renderer/src/i18n';
import { sessionFixesEn, sessionFixesFr, sessionFixesZh } from '../../src/renderer/src/i18n/locales/sessionFixes';
import { inboxTitle } from '../../src/renderer/src/lib/inboxView';
import { failureReason } from '../../src/renderer/src/v4/Failure';

afterEach(() => setLang('en'));

const dropped: PilotFailure = {
  state: 'failed',
  code: 'stage-voice-dropped',
  provider: null,
  error: 'RuntimeError: tts.py exit 1',
  at: 1,
  stage: 'voice',
  params: { line: '2', sentence: '地基先打好：Tool Calling', lines: '1', fix: 'rephrase-line' },
};

describe('a voice that kept leaving out a sentence', () => {
  it('names the scene, the sentence and the fix', () => {
    expect(failureReason(dropped)).toBe(
      'The voice kept leaving out a sentence in scene 2: “地基先打好：Tool Calling”. Reword or split that sentence in the script, then press Try again.',
    );
    expect(failureReason(dropped)).not.toMatch(/Something went wrong|RuntimeError|tts\.py/);
    setLang('zh-CN');
    expect(failureReason(dropped)).toBe('配音几次都漏读了第 2 幕的一句：“地基先打好：Tool Calling”。 在脚本里把这句改个说法或拆成两句，再点「再试一次」。');
    setLang('fr');
    expect(failureReason(dropped)).toMatch(/^La voix a sauté plusieurs fois une phrase de la scène 2 : « 地基先打好：Tool Calling »\. Reformulez/);
  });
  it('the inbox card says what stopped the run', () => {
    const x = { key: 'a'.repeat(16), kind: 'failed', group: 'failed', project: { id: 'p', name: 'MCP 课', kind: 'project' }, code: 'inbox.failed.stage-voice-dropped', params: {}, options: [], source: 'engine' } as unknown as InboxItem;
    expect(inboxTitle(x)).toBe('The voice left out a sentence — the run stopped');
    setLang('zh-CN');
    expect(inboxTitle(x)).toBe('配音漏读了一句，运行停下了');
  });
  it('every new string exists in en, zh-CN and fr', () => {
    for (const k of Object.keys(sessionFixesEn).filter((k) => k.includes('voice-dropped') || k.includes('rephrase-line'))) {
      expect(sessionFixesZh[k as keyof typeof sessionFixesEn], k).toBeTruthy();
      expect(sessionFixesFr[k as keyof typeof sessionFixesEn], k).toBeTruthy();
    }
  });
});

// Demo 2026-10-11: the free voice errored on a line (a Kokoro length bug, now fixed) on every take; the voice stage now
// retries a failing line in two halves and, if that fails too, stops coded stage-voice-failed {line, sentence}.
describe('a voice that could not read a line, even split in two', () => {
  const failed: PilotFailure = { ...dropped, code: 'stage-voice-failed', params: { line: '3', sentence: 'The headphones use exactly that', lines: '1', fix: 'rephrase-line' } };
  it('names the scene, its words and the fix', () => {
    expect(failureReason(failed)).toBe(
      'The voice could not read scene 3, even in two halves: “The headphones use exactly that”. Reword or split that sentence in the script, then press Try again.',
    );
    setLang('zh-CN');
    expect(failureReason(failed)).toMatch(/^配音读不出第 3 幕，分成两半也不行：“The headphones use exactly that”。/);
    setLang('fr');
    expect(failureReason(failed)).toMatch(/^La voix n’a pas pu lire la scène 3, même en deux moitiés/);
  });
  it('the inbox card says what stopped the run', () => {
    const x = { key: 'b'.repeat(16), kind: 'failed', group: 'failed', project: { id: 'p', name: 'Noise', kind: 'project' }, code: 'inbox.failed.stage-voice-failed', params: {}, options: [], source: 'engine' } as unknown as InboxItem;
    expect(inboxTitle(x)).toBe('The voice could not read a scene — the run stopped');
  });
});
