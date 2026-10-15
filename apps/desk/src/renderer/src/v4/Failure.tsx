// A failed pilot (P0-3): the reason in her words (from the engine's failure code, never the raw error) and what
// to do next — 去登录 / 换 Codex 重试 / 重试. Used on the project page and in the inbox.
import { useState } from 'react';
import type { PilotFailure } from '../../../shared/v02';
import { KEY_NAMES, providerName } from '../../../shared/aiRoutes';
import { has, t, tk, type MessageKey } from '../i18n';
import { stepOfStage } from '../lib/pipeline';
import { useEngine } from '../lib/engine';
import { useHistory } from '../lib/history';
import { useInbox } from '../lib/inbox';
import { go } from '../lib/router';
import { errText } from './msg';
import { CHINESE_VOICE_GROUP, ensureFreeVoice } from '../lib/freeVoice';
import { openReport } from '../support/Support';
import { useUi } from './ui';
import { redactClip } from '../../../shared/redact';

const AI = new Set(['ai-login', 'ai-quota', 'ai-timeout', 'ai-missing', 'ai-region', 'ai-needs-model']);

const TOOL_NAMES: Record<string, string> = { node: 'Node.js', ffmpeg: 'ffmpeg', ffprobe: 'ffprobe', npx: 'Node.js (npx)' };

/** The reason in her words: the failure code from the engine, never the raw error. A step that failed on an external
 * tool names the tool and the fix; "Part of Reelfold didn't start" is only for the engine itself not starting. */
export function failureReason(f: PilotFailure): string {
  const provider = f.provider ? providerName(f.provider) : t('fail.providerAny');
  const p = f.params ?? {};
  const toolId = String(p.tool ?? f.tool ?? '');
  const tool = TOOL_NAMES[toolId] ?? toolId;
  const path = typeof p.path === 'string' && p.path ? tk('fail.at', { path: p.path }) : '';
  const key = `fail.reason.${f.code}`;
  let reason: string;
  const step = stepOfStage(f.stage);
  // the step in her words (「转写」), never the engine's stage id (「asr」)
  if (f.code === 'stage') reason = step ? tk(key, { stage: t(`hub.step.${step}` as MessageKey) }) : tk('fail.reason.unknown');
  else if ((f.code === 'tool-missing' || f.code === 'tool-broken') && !tool) reason = tk('fail.reason.unknown');
  // a file that couldn't be read is named (and its drive when that isn't connected); without a name: the general words
  else if (f.code === 'media-unmounted' && !(p.file && p.volume)) reason = tk(p.file ? 'fail.reason.media-unreadable' : 'fail.reason.media', { file: String(p.file ?? '') });
  else if (f.code === 'media-unreadable' && !p.file) reason = tk('fail.reason.media');
  else if (f.code === 'ai-key-missing') reason = tk(key, { service: String(p.service ?? '') || t('fail.keyService') });
  // the voice kept leaving out a sentence / errored on a line: which scene and its words (without them: general words)
  else if (f.code === 'stage-voice-dropped' || f.code === 'stage-voice-failed') reason = p.sentence ? tk(key, { line: String(p.line ?? ''), sentence: String(p.sentence) }) : tk('fail.reason.unknown');
  // a redo of the visuals that drew no scene: which scene (or how many), why in plain words - the video stands
  else if (f.code === 'stage-visuals-failed') {
    const why = has(`fail.why.${p.why}`) ? tk(`fail.why.${p.why}`) : t('fail.why.other');
    const n = Number(p.n ?? 1);
    reason = n > 1 ? tk('fail.reason.stage-visuals-failed.many', { n, total: String(p.total ?? ''), why }) : tk(key, { scene: String(p.scene ?? ''), total: String(p.total ?? ''), why });
  }
  else if (has(key)) reason = tk(key, { provider, tool, at: path, path: String(p.path ?? ''), file: String(p.file ?? ''), volume: String(p.volume ?? '') });
  else reason = tk('fail.reason.unknown'); // a code this desk has no words for yet
  const fix = String(p.fix ?? f.fix ?? '');
  if (!fix) return reason;
  const how = has(`fail.fix.${fix}`) ? tk(`fail.fix.${fix}`) : /\s/.test(fix) || fix.includes('/') ? tk('fail.fix.cmd', { fix }) : '';
  return how ? `${reason} ${how}` : reason;
}

/** Diagnostic text stays behind an explicit disclosure and is safe to copy into a report. */
export function failureDetails(f: PilotFailure): string {
  return redactClip(f.error?.trim() ?? '', 4000);
}

export function FailureDetails({ failure }: { failure: PilotFailure }) {
  const ui = useUi();
  const detail = failureDetails(failure);
  if (!detail) return null;
  const copy = async () => {
    try {
      await window.desk.copyText(detail);
      ui.toast(t('c.copied'));
    } catch (e) {
      ui.toast(errText(e), { error: true });
    }
  };
  return (
    <details className="muted small" data-testid="failure-details" style={{ minWidth: 0, maxWidth: '100%' }}>
      <summary>{t('plan.details')}</summary>
      <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', userSelect: 'text' }}>{detail}</pre>
      <button className="btn" onClick={() => void copy()} data-testid="failure-copy">{t('c.copy')}</button>
    </details>
  );
}

/** Where Settings › AI shows the key a failure needs (the OpenAI row for "No OpenAI key"). */
export function keyFocus(f: Pick<PilotFailure, 'params'>): string | undefined {
  const s = String(f.params?.service ?? '').toLowerCase();
  return (KEY_NAMES as readonly string[]).includes(s) ? s : undefined;
}

/** The provider to offer for 「换 … 重试」: the other subscription CLI. */
export function otherProvider(f: PilotFailure): string {
  return f.provider === 'codex' ? 'claude-code' : 'codex';
}

/** ``only``: just the one button that fixes it (connect a model / add a key / Sign in / Try again) - Home's rows
 * offer one action each. */
export function FailureActions({ item, failure, primary = true, onDone, only = false }: { item: string; failure: PilotFailure; primary?: boolean; onDone?: () => void; only?: boolean }) {
  const { client } = useEngine();
  const hist = useHistory();
  const inbox = useInbox();
  const ui = useUi();
  const [busy, setBusy] = useState(false);
  const ai = AI.has(failure.code);
  const other = otherProvider(failure);
  // the free Chinese voice (tts-qwen-zh) is its own download
  const zhVoice = failure.params?.fix === 'download-zh-voice';
  const retry = async (provider?: string) => {
    if (!client) return;
    setBusy(true);
    try {
      await client.retryPilot(item, provider ?? null);
      ui.toast(t('fail.retrying'));
      hist.reload();
      inbox.reload();
      onDone?.();
    } catch (e) {
      ui.toast(errText(e), { error: true });
    } finally {
      setBusy(false);
    }
  };
  const p = primary ? 'btn primary' : 'btn';
  const settings = (
    <button className={only ? p : 'btn'} onClick={() => go({ name: 'aiAccounts', focus: failure.provider ?? undefined })} data-testid="fail-ai-settings">
      {t('draft.needsModel.ai')}
    </button>
  );
  const addKey = (
    <button className={only ? p : 'btn'} onClick={() => go({ name: 'aiAccounts', focus: keyFocus(failure) })} data-testid="fail-add-key">
      {t('fail.addKey', { service: String(failure.params?.service ?? '') || t('fail.keyService') })}
    </button>
  );
  // one button: the step that fixes it (a model to connect, a key to add), else Sign in / Try again
  if (only && (failure.code === 'ai-needs-model' || failure.code === 'ai-region')) return settings;
  if (only && failure.code === 'ai-key-missing') return addKey;
  return (
    <>
      {failure.code === 'ai-login' || failure.code === 'ai-missing' ? (
        <button className={p} onClick={() => go({ name: 'aiAccounts', focus: failure.provider ?? undefined })} data-testid="fail-login">
          {t('fail.login')}
        </button>
      ) : (
        <button className={p} disabled={busy} onClick={() => void retry(failure.provider ?? undefined)} data-testid="fail-retry">
          {t('fail.retry')}
        </button>
      )}
      {!only && failure.code === 'tool-voice' && (
        <button
          className="btn"
          onClick={() =>
            void ensureFreeVoice(undefined, zhVoice ? CHINESE_VOICE_GROUP : undefined)
              .then((st) => ui.toast(t(st === 'installed' ? 'fail.voiceReady' : 'fail.voiceDownloading')))
              .catch((e) => ui.toast(errText(e), { error: true }))
          }
          data-testid="fail-download-voice"
        >
          {t(zhVoice ? 'fail.downloadZhVoice' : 'fail.downloadVoice')}
        </button>
      )}
      {!only && failure.code === 'ai-needs-model' && settings}
      {!only && failure.code === 'ai-key-missing' && addKey}
      {!only && ai && (
        <button className="btn" disabled={busy} onClick={() => void retry(other)} data-testid="fail-retry-other">
          {t('fail.retryWith', { provider: providerName(other) })}
        </button>
      )}
      {!only && (
        <button className="btn ghost" onClick={() => openReport({ kind: 'job', code: failure.code, message: failure.error || failure.code })} data-testid="fail-report">
          {t('sup.rp.report')}
        </button>
      )}
    </>
  );
}
