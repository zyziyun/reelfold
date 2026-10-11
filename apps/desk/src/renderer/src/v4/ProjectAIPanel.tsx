// 「让 AI 改」 on the PROJECT page: one request for every clip of the project (or just the selected one). The
// engine plans per clip in one call and answers with grouped cards (apply per clip / apply to all), or — when the
// change is impossible on finished files (burned-in text, burned captions) — a re-render card within seconds with
// the real way to do it (the work-script lines, copy instructions for Claude Code, regenerate). While it works the
// panel shows the stages (读取 N 条片子 → 询问 Claude Code → 生成修改) with elapsed time, a fallback notice when
// the routed AI times out, and Cancel (the engine process is killed).
import { useEffect, useRef, useState } from 'react';
import { ArrowUp, Check, Clipboard, FileText, FolderOpen, PanelRightClose, RefreshCw, Undo2, X } from 'lucide-react';
import type { EngineMsg, ProjectAction, ProjectAskJob, ProjectAskResult, ProjectGroup, RerenderAction } from '../../../shared/v04';
import { providerName } from '../../../shared/aiRoutes';
import { t, type MessageKey } from '../i18n';
import { emsg, errText } from './msg';
import { useEngine } from '../lib/engine';
import { go } from '../lib/router';
import { useUi } from './ui';
import { AnsweredBy, FallbackNote, ProviderChip } from './AiChip';

interface Msg {
  id: number;
  me?: boolean;
  text: string;
  result?: ProjectAskResult;
  /** applied group -> the edit number it added (for undo) */
  applied?: Record<string, number>;
  /** project-level controls already used */
  done?: string[];
  tone?: 'muted' | 'error';
}

interface Clip {
  id: string;
  title: string;
}

let seq = 0;
/** each project's conversation while the app is open: the page under the chat changes as the run goes (the run page,
 * then the ready page) and the chat stays */
const KEPT = new Map<string, Msg[]>();

function stageText(s: ProjectAskJob['stages'][number]): string {
  if (s.stage === 'read') return t('pai.st.read', { n: s.n ?? 0 });
  if (s.stage === 'check') return t('pai.st.check');
  if (s.stage === 'ask') return !s.provider || s.provider === 'rules' ? t('pai.st.rules') : t('pai.st.ask', { name: providerName(s.provider) });
  return t('pai.st.plan');
}

function whyKey(code?: string): MessageKey {
  return code === 'timeout' ? 'pai.why.timeout' : code === 'auth-expired' || code === 'not-logged-in' ? 'pai.why.expired' : 'pai.why.failed';
}

export function ProjectAIPanel({
  item,
  clips,
  selected,
  running,
  liveText,
  onApplied,
  onFold,
  testId = 'ai-panel',
}: {
  item: string;
  /** the finished clips of the page (what "all" means) */
  clips: Clip[];
  selected?: Clip | null;
  running?: boolean;
  liveText?: string | null;
  onApplied?: () => void;
  /** the page lets the chat fold to its edge: the header's fold button */
  onFold?: () => void;
  testId?: string;
}) {
  const { client } = useEngine();
  const ui = useUi();
  const [msgs, setMsgsS] = useState<Msg[]>(() => KEPT.get(item) ?? []);
  const setMsgs = (f: (m: Msg[]) => Msg[]) =>
    setMsgsS((m) => {
      const n = f(m);
      KEPT.set(item, n);
      return n;
    });
  const [text, setText] = useState('');
  const [scope, setScope] = useState<'all' | 'one'>('all');
  const [job, setJob] = useState<ProjectAskJob | null>(null);
  const [started, setStarted] = useState(0);
  const [now, setNow] = useState(0);
  const log = useRef<HTMLDivElement | null>(null);
  const input = useRef<HTMLTextAreaElement | null>(null);
  // "Ask AI about this" on a piece of the making: her words started, the cursor at the end
  useEffect(() => {
    const on = (e: Event) => {
      const d = (e as CustomEvent<{ item: string; text: string }>).detail;
      if (d?.item !== item) return;
      setText(d.text);
      window.setTimeout(() => {
        const el = input.current;
        el?.focus();
        el?.setSelectionRange(el.value.length, el.value.length);
      }, 40);
    };
    window.addEventListener('project-chat:prefill', on);
    return () => window.removeEventListener('project-chat:prefill', on);
  }, [item]);
  const busy = Boolean(job && job.state === 'running') || started > 0;
  useEffect(() => {
    log.current?.scrollTo({ top: 1e9, behavior: 'smooth' });
  }, [msgs, job?.stages.length]);
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    setMsgsS(KEPT.get(item) ?? []);
    setJob(null);
    setStarted(0);
  }, [item]);

  // poll the job while it runs (+ a local clock for the elapsed time)
  const jobId = job?.job;
  useEffect(() => {
    if (!client || !jobId || !started) return;
    let alive = true;
    const tick = setInterval(() => setNow(Date.now()), 250);
    const poll = setInterval(async () => {
      try {
        const j = await client.projectAskJob(jobId);
        if (!alive) return;
        setJob(j);
        if (j.state !== 'running') finish(j);
      } catch {
        /* the next poll retries */
      }
    }, 400);
    return () => {
      alive = false;
      clearInterval(tick);
      clearInterval(poll);
    };
  }, [client, jobId, started]); // eslint-disable-line react-hooks/exhaustive-deps

  const finish = (j: ProjectAskJob) => {
    setStarted(0);
    if (j.state === 'cancelled') {
      setMsgs((m) => [...m, { id: ++seq, text: t('pai.cancelled'), tone: 'muted' }]);
    } else if (j.state === 'failed') {
      const wd = j.notices.find((n) => n.kind === 'watchdog');
      setMsgs((m) => [...m, { id: ++seq, text: wd ? t('pai.watchdog', { s: Math.round(wd.seconds ?? 0) }) : emsg(j.error) || t('em.ask-failed'), tone: 'error' }]);
    } else if (j.result) {
      const r = j.result;
      const n = r.groups.filter((g) => g.proposals.length).length;
      const notes = (r.warnings ?? []).map((w: EngineMsg) => emsg(w)).filter(Boolean);
      const head = n ? t('pai.changes', { n }) : r.answer === 'nothing' ? t('ai.nothing') : '';
      setMsgs((m) => [...m, { id: ++seq, text: [head, r.summary ?? '', ...notes].filter(Boolean).join('\n'), result: r, applied: {} }]);
    }
    setJob(null);
  };

  const send = async (prompt: string) => {
    if (!client || !prompt.trim() || busy) return;
    const target = scope === 'one' && selected ? [selected.id] : clips.map((c) => c.id);
    // nothing finished yet (it is still being made): the engine still answers what the project can do now (pause,
    // pick the music or the cover again, cut it again)
    setMsgs((m) => [...m, { id: ++seq, me: true, text: prompt }]);
    setText('');
    const t0 = Date.now();
    setStarted(t0);
    setNow(t0);
    try {
      const r = await client.projectAsk(item, prompt, scope === 'one' && target.length ? target : null, selected ? { selected: selected.id } : null);
      setJob({ job: r.job, item, prompt, state: 'running', stages: [], notices: [], clips: r.clips, timeout: r.timeout, elapsed: 0, result: null, error: null, partial: null });
    } catch (e) {
      setStarted(0);
      setMsgs((m) => [...m, { id: ++seq, text: errText(e), tone: 'error' }]);
    }
  };

  const cancel = async () => {
    if (!client || !job) return;
    try {
      await client.stopProjectAsk(job.job);
    } catch (e) {
      ui.toast(errText(e), { error: true });
    }
  };

  const setApplied = (mid: number, clip: string, v: number | null) =>
    setMsgs((m) =>
      m.map((x) => {
        if (x.id !== mid) return x;
        const a = { ...(x.applied ?? {}) };
        if (v === null) delete a[clip];
        else a[clip] = v;
        return { ...x, applied: a };
      }),
    );

  const applyGroup = async (mid: number, g: ProjectGroup, quiet = false) => {
    if (!client || !g.proposals.length) return false;
    try {
      const before = await client.output(item, g.clip);
      await client.editOutput(item, g.clip, g.proposals.map((p) => p.op));
      setApplied(mid, g.clip, before.steps.length + 1);
      if (!quiet) onApplied?.();
      return true;
    } catch (e) {
      ui.toast(`${g.title}: ${errText(e)}`, { error: true });
      return false;
    }
  };
  const applyAll = async (m: Msg) => {
    let n = 0;
    for (const g of m.result?.groups ?? []) if (g.proposals.length && !m.applied?.[g.clip] && (await applyGroup(m.id, g, true))) n++;
    onApplied?.();
    if (n) ui.toast(t('pai.appliedAll', { n }));
  };
  const undoGroup = async (mid: number, g: ProjectGroup, at: number) => {
    if (!client) return;
    try {
      const cur = await client.output(item, g.clip);
      await client.undoOutput(item, g.clip, Math.max(1, cur.steps.length - at + 1));
      setApplied(mid, g.clip, null);
      onApplied?.();
      ui.toast(t('ai.undone'));
    } catch (e) {
      ui.toast(errText(e), { error: true });
    }
  };

  /** a project-level answer's control: pause / go on / take the decision back (the run asks her there) */
  const runAction = async (mid: number, a: ProjectAction) => {
    if (!client) return;
    try {
      if (a.kind === 'stop') await client.stopHistory(item);
      else if (a.kind === 'resume') await client.resumeHistory(item);
      else if (a.kind === 'reopen' && a.checkpoint) await client.autopilotReopen(item, a.checkpoint, a.item ?? '*');
      setMsgs((m) => [...m.map((x) => (x.id === mid ? { ...x, done: [...(x.done ?? []), actKey(a)] } : x)), { id: ++seq, text: t(a.kind === 'stop' ? 'pc.done.stop' : a.kind === 'resume' ? 'pc.done.resume' : 'pc.done.reopen'), tone: 'muted' }]);
      onApplied?.();
    } catch (e) {
      ui.toast(errText(e), { error: true });
    }
  };

  const act = async (a: RerenderAction) => {
    try {
      if (a.kind === 'copy-prompt' && a.prompt) {
        await window.desk.copyText(a.prompt);
        ui.toast(t('pai.copied'));
      } else if ((a.kind === 'open-file' || a.kind === 'reveal') && a.file) {
        await window.desk.showItem(a.file);
      } else if (a.kind === 'regenerate' && client && a.items?.length) {
        const r = await client.regenerate(item, a.items);
        ui.toast(r.started ? t('pai.regenStarted', { n: a.items.length }) : t('pai.regenSimulated'));
      }
    } catch (e) {
      ui.toast(errText(e), { error: true });
    }
  };

  const elapsed = started ? Math.max(0, Math.round((now - started) / 1000)) : 0;
  const stages = job?.stages ?? [];
  const asking = stages.length && stages[stages.length - 1].stage === 'ask';
  // nothing made yet (it is being made): what the project can do now; else the usual clip edits
  const chips: [MessageKey, string][] = clips.length
    ? [
        ['ai.chip.tighter', t('ai.chip.tighterPrompt')],
        ['ai.chip.douyin', t('ai.chip.douyinPrompt')],
      ]
    : [
        ['pc.chip.pause', t('pc.chip.pausePrompt')],
        ['pc.chip.music', t('pc.chip.musicPrompt')],
        ['pc.chip.recut', t('pc.chip.recutPrompt')],
      ];

  return (
    <aside className="agent" data-testid={testId} data-scope="project">
      <div className="hd">
        <b style={{ whiteSpace: 'nowrap', flex: 'none' }}>{t('ai.title')}</b>
        <ProviderChip task="edit" testId="ai-provider-chip" />
        <span className="sp" />
        {onFold && (
          <button className="btn ghost icon sm" onClick={onFold} aria-label={t('pc.fold')} data-tip={t('pc.fold')} data-testid="project-chat-fold">
            <PanelRightClose className="ico" />
          </button>
        )}
        {running ? (
          <span className="st run">
            <i className="dot run" />
            {t('ai.working')}
          </span>
        ) : clips.length === 0 ? null : (
          <select
            className="inp sm"
            style={{ width: 'auto', flex: '0 0 auto', maxWidth: 112, height: 26, textOverflow: 'ellipsis' }}
            value={scope}
            onChange={(e) => setScope(e.target.value as 'all' | 'one')}
            title={t('pai.scopeTip')}
            aria-label={t('pai.scopeTip')}
            data-testid="pai-scope"
            disabled={busy}
          >
            <option value="all">{t('pai.scopeAll', { n: clips.length })}</option>
            {selected && <option value="one">{t('pai.scopeOne', { title: selected.title })}</option>}
          </select>
        )}
      </div>
      <div className="alog" ref={log} data-testid="ai-log">
        {liveText && <div className="msg" lang="zh-CN">{liveText}</div>}
        {!msgs.length && !liveText && !busy && <div className="muted">{clips.length ? t('pai.empty') : t('em.pa-nothing-made')}</div>}
        {msgs.map((m) => (
          <div key={m.id} className="col" style={{ gap: 8 }}>
            {m.text && (
              <div className={`msg ${m.me ? 'me' : ''} ${m.tone === 'muted' ? 'muted' : ''}`} style={m.tone === 'error' ? { color: 'var(--danger)' } : undefined} data-testid={m.me ? undefined : 'pai-reply'}>
                {m.text}
              </div>
            )}
            {m.result && (
              <>
                {(m.result.actions ?? []).length > 0 && (
                  <div className="pa-acts" data-testid="pai-actions">
                    {m.result.actions!.map((a, k) => (
                      <button key={k} className={`btn sm ${k === 0 ? 'primary' : ''}`} disabled={m.done?.includes(actKey(a))} onClick={() => void runAction(m.id, a)} data-testid="pai-project-action" data-kind={a.kind} data-checkpoint={a.checkpoint}>
                        {emsg(a.label)}
                      </button>
                    ))}
                  </div>
                )}
                {m.result.needs_rerender && <RerenderCard nr={m.result.needs_rerender} seconds={m.result.model_called ? null : m.result.seconds} onAct={act} />}
                {m.result.groups.filter((g) => g.proposals.length).map((g) => {
                  const at = m.applied?.[g.clip];
                  return (
                    <div key={g.clip} className="change" data-testid="pai-group" data-clip={g.clip}>
                      <div className="row">
                        <b className="sp clamp1">{g.title}</b>
                        {at ? (
                          <span className="st done">
                            <Check className="ico" style={{ width: 12, height: 12 }} />
                            {t('ai.applied')}
                          </span>
                        ) : null}
                      </div>
                      {g.proposals.map((p) => (
                        <div key={p.id} className="col" style={{ gap: 2 }} data-testid="ai-proposal">
                          <span className="clamp2">{emsg(p.describe) || p.op.op}</span>
                          {p.why && <span className="muted small">{emsg(p.why)}</span>}
                        </div>
                      ))}
                      <div className="row">
                        {!at ? (
                          <button className="btn sm primary" onClick={() => void applyGroup(m.id, g)} data-testid="pai-apply">
                            {t('pai.applyClip')}
                          </button>
                        ) : (
                          <button className="btn sm" onClick={() => void undoGroup(m.id, g, at)} data-testid="pai-undo">
                            <Undo2 className="ico" />
                            {t('ai.undo')}
                          </button>
                        )}
                        <button className="btn sm ghost" onClick={() => go({ name: 'clip', id: item, clip: g.clip })} data-testid="pai-open-clip">
                          {t('pai.openClip')}
                        </button>
                      </div>
                    </div>
                  );
                })}
                {m.result.groups.filter((g) => g.proposals.length).length > 1 && (
                  <button
                    className="btn sm primary"
                    style={{ alignSelf: 'flex-start' }}
                    disabled={m.result.groups.every((g) => !g.proposals.length || m.applied?.[g.clip])}
                    onClick={() => void applyAll(m)}
                    data-testid="pai-apply-all"
                  >
                    {t('pai.applyAll', { n: m.result.groups.filter((g) => g.proposals.length).length })}
                  </button>
                )}
                <AnsweredBy provider={m.result.provider} fallback={m.result.fallback} testId="ai-answered-by" />
                {m.result.failed?.provider && !m.result.fallback && <FallbackNote rulesFrom={m.result.failed.provider} />}
              </>
            )}
          </div>
        ))}
        {busy && job?.partial && <RerenderCard nr={job.partial} onAct={act} />}
        {busy && (
          <div className="msg col" style={{ gap: 4 }} data-testid="pai-status" aria-live="polite">
            {!stages.length && (
              <span className="row" style={{ gap: 6 }}>
                <i className="dot run" />
                {t('pai.st.start')}
              </span>
            )}
            {stages.map((s, i) => {
              const last = i === stages.length - 1;
              return (
                <span key={`${s.stage}${i}`} className={`row ${last ? '' : 'muted'}`} style={{ gap: 6 }} data-testid="pai-stage" data-stage={s.stage}>
                  {last ? <i className="dot run" /> : <Check className="ico" style={{ width: 12, height: 12 }} />}
                  {stageText(s)}
                </span>
              );
            })}
            {(job?.notices ?? [])
              .filter((n) => n.kind === 'fallback')
              .map((n, i) => (
                <span key={i} className="notice small" data-testid="pai-fallback">
                  {t('pai.fbLive', { from: providerName(n.from), to: providerName(n.to), why: t(whyKey(n.code)) })}
                </span>
              ))}
            <span className="row" style={{ gap: 8 }}>
              <span className="faint small" data-testid="pai-elapsed">
                {t('pai.elapsed', { s: elapsed })}
              </span>
              <span className="sp" />
              <button className="btn sm ghost" onClick={() => void cancel()} disabled={!job} data-testid="pai-cancel">
                <X className="ico" />
                {t('pai.cancel')}
              </button>
            </span>
            {asking && elapsed >= 20 && job && <span className="faint small">{t('pai.slow', { s: Math.round(job.timeout) })}</span>}
          </div>
        )}
      </div>
      <div className="in">
        <textarea
          ref={input}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={running || !clips.length ? t('pc.placeholderRun') : t('pai.placeholder')}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              void send(text);
            }
          }}
          data-testid="ai-input"
        />
        <div className="row">
          {chips.map(([k, prompt]) => (
            <button key={k} className="chip" onClick={() => void send(prompt)} disabled={busy}>
              {t(k)}
            </button>
          ))}
          <span className="sp" />
          <button className="btn icon sm" onClick={() => void send(text)} disabled={!text.trim() || busy} aria-label={t('ai.send')} data-testid="ai-send">
            <ArrowUp className="ico" />
          </button>
        </div>
      </div>
    </aside>
  );
}

const actKey = (a: ProjectAction) => `${a.kind}:${a.checkpoint ?? ''}:${a.item ?? ''}`;

const ACT_ICON = { 'copy-prompt': Clipboard, 'open-file': FileText, regenerate: RefreshCw, reveal: FolderOpen } as const;

function RerenderCard({ nr, seconds, onAct }: { nr: NonNullable<ProjectAskResult['needs_rerender']>; seconds?: number | null; onAct: (a: RerenderAction) => void }) {
  const files = nr.paths.flatMap((p) => p.files ?? []).slice(0, 4);
  return (
    <div className="change" data-testid="pai-needs-rerender" data-code={nr.code} style={{ borderColor: 'var(--warn, #c9a227)' }}>
      <b>{t('pai.rerenderTitle')}</b>
      <span>{emsg(nr.reason)}</span>
      <span className="muted small clamp2">{t('pai.rerenderClips', { n: nr.titles.length, list: nr.titles.join('、') })}</span>
      {nr.paths.map((p, i) => (
        <div key={i} className="col" style={{ gap: 6 }} data-testid="pai-path" data-kind={p.kind}>
          <span className="small">{emsg(p.message)}</span>
          <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
            {p.actions.map((a, k) => {
              const Icon = ACT_ICON[a.kind] ?? FileText;
              return (
                <button key={k} className={`btn sm ${k === 0 ? 'primary' : ''}`} onClick={() => onAct(a)} data-testid="pai-action" data-kind={a.kind}>
                  <Icon className="ico" />
                  {emsg(a.label)}
                </button>
              );
            })}
          </div>
        </div>
      ))}
      {files.length > 0 && (
        <details className="small">
          <summary className="muted">{t('pai.whereText')}</summary>
          {files.map((f, i) => (
            <div key={i} className="faint clamp1" title={f.text}>
              {f.file}:{f.line} {f.text}
            </div>
          ))}
        </details>
      )}
      {seconds != null && <span className="faint small">{t('pai.fast', { s: seconds < 1 ? '<1' : Math.round(seconds) })}</span>}
    </div>
  );
}
