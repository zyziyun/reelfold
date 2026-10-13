// The Create spend gate for one "Could be generated" idea: the engine prices it (python -m vstudio.brain estimate:
// Create's rate card, the month's cap, the service ready and its credits), the sheet says what it costs, the most it
// can cost and what is left of the month, and every reason it would be refused - and nothing is sent until she
// presses "Generate ≈ ¥X". That click carries the estimate id + its confirm code + the max she saw; the engine checks
// all of it again and submits once (never retried). The autopilot never opens this.
import { useEffect, useState } from 'react';
import type { BrainEstimate, BrainProposal } from '../../../shared/v04';
import { yuan } from '../../../shared/create';
import { msgText } from '../create/api';
import { createHref } from '../create/routes';
import { t } from '../i18n';
import { useEngine } from '../lib/engine';
import { errText as engineErr } from './msg';
import { EngineError } from '../../../shared/engineClient';
import { said } from './brainText';

const PROVIDERS: Record<string, string> = {
  'kling-mcp': 'Kling',
  minimax: 'MiniMax',
  veo: 'Veo',
  'seedance-ark': 'Seedance',
};

/** A gate refusal in her words, the service named the way the card names it. */
export function gateText(m: { code: string; params?: Record<string, unknown> }, label?: string): string {
  const params = { ...(m.params ?? {}) };
  if (typeof params.provider === 'string') params.provider = label || PROVIDERS[params.provider] || params.provider;
  if (params.shots === undefined && m.code === 'create.unknown-charge') params.shots = '';
  return msgText({ code: m.code, params } as Parameters<typeof msgText>[0]);
}

function errOf(e: unknown, label: string): string {
  if (e instanceof EngineError && e.code && e.code.startsWith('create.'))
    return gateText({ code: e.code, params: (e.params ?? {}) as Record<string, unknown> }, label);
  return engineErr(e);
}

export function BrainGate({ item, p, onClose, onStarted }: { item: string; p: BrainProposal; onClose: () => void; onStarted: () => void }) {
  const { client } = useEngine();
  const [est, setEst] = useState<BrainEstimate | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const label = p.estimate.label || PROVIDERS[p.provider] || p.provider;
  useEffect(() => {
    if (!client) return;
    client
      .brainEstimate(item, p.id)
      .then(setEst)
      .catch((e) => setErr(errOf(e, label)));
  }, [client, item, p.id, label]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', k);
    return () => window.removeEventListener('keydown', k);
  }, [onClose]);
  const ln = est?.lines[0];
  const blocked = (est?.codes ?? []).map((c) => gateText(c, label));
  const notReady = (est?.codes ?? []).some((c) => c.code === 'create.provider-not-ready' || c.code === 'create.low-credits');
  const go = async () => {
    if (!client || !est || busy) return;
    setBusy(true);
    setErr(null);
    try {
      await client.brainGenerate(item, p.id, est, est.proposal.code || p.code);
      onStarted();
    } catch (e) {
      setErr(errOf(e, label));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="brain-scrim" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="brain-gate" role="dialog" aria-modal="true" aria-label={t('brain.gate.title', { what: said(p.title) })} data-testid="brain-gate">
        <h2>{t('brain.gate.title', { what: said(p.title) })}</h2>
        <p className="sub">{t('brain.gate.sub')}</p>
        {!est && !err && <div className="muted">{t('brain.gate.loading')}</div>}
        {est && ln && (
          <>
            <div className="gl" data-testid="brain-gate-line">
              <div>
                <div className="l1">
                  {t('brain.gate.line', {
                    who: label,
                    mode: p.mode === 'text-to-image' ? t('brain.mode.t2i') : t('brain.gate.clip'),
                  })}
                </div>
                <div className="l2">
                  {[
                    ln.seconds_billed
                      ? t('brain.gate.secs', {
                          s: Math.round(ln.seconds_billed),
                        })
                      : null,
                    ln.resolution,
                    ln.native_units ? t('create.sheet.credits', { n: ln.native_units }) : null,
                    ln.verified ? null : t('brain.gate.rateSeen'),
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </div>
              </div>
              <span className="amt">{yuan(ln.cny)}</span>
            </div>
            <div className="gsum" data-testid="brain-gate-total">
              <span className="big">≈ {yuan(est.subtotal_cny)}</span>
              <span className="muted">
                {t('brain.gate.max', { max: yuan(est.max_cny) })}
                {est.month.left_after !== null && (
                  <>
                    {' '}
                    ·{' '}
                    {t('create.sheet.monthLeft', {
                      n: yuan(est.month.left_after),
                    })}
                  </>
                )}
              </span>
            </div>
            <p className="muted gnote">{t('brain.gate.after')}</p>
          </>
        )}
        {(blocked.length > 0 || err) && (
          <div className="gblock" data-testid="brain-gate-blocked">
            <b>{t('create.sheet.blocked')}</b>
            {[...blocked, ...(err ? [err] : [])].map((x, i) => (
              <div key={i}>{x}</div>
            ))}
            {notReady && (
              <a className="link" href={createHref({ screen: 'settings' })}>
                {t('create.sheet.connect')}
              </a>
            )}
          </div>
        )}
        <div className="acts">
          <span className="sp" />
          <button className="btn" onClick={onClose} data-testid="brain-gate-cancel">
            {t('create.sheet.cancel')}
          </button>
          <button className="btn primary" disabled={!est || blocked.length > 0 || busy} onClick={() => void go()} data-testid="brain-gate-confirm">
            {est ? t('brain.gate.go', { n: yuan(est.subtotal_cny) }) : t('brain.gate.goPlain')}
          </button>
        </div>
      </div>
    </div>
  );
}
