// The run page (ux/run-view A, 2026-10-10): what the Studio shows for a request being planned and a project being
// made. One calm hero - the title, what it is doing right now in one plain sentence, a big number with the time left,
// the pipeline as a slim timeline - then "what happened" stage by stage (files read, minutes transcribed, what the AI
// answered and decided, clips past each step, with times and durations) and the live pane: the model CLIs' turns and
// the engine's log as they stream (LivePane), docked below or beside, resizable, foldable. Stop / Discard / the
// Autopilot switch stay where they were (the hero's top row). The plan card still answers a plan that waits for her.
import { Sparkles, Square, Trash2 } from 'lucide-react';
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import type { HistoryItem } from '../../../shared/v02';
import type { AutopilotDoc, CalendarPost, OpenRequest } from '../../../shared/v04';
import { fmtClock, fmtMinutes, fmtTime, t, tk, type MessageKey } from '../i18n';
import { providerName } from '../../../shared/aiRoutes';
import { useEngine, useLoad } from '../lib/engine';
import { useHistory } from '../lib/history';
import { planStory, runStory, useLive, type LiveState, type StoryEntry } from '../lib/live';
import { liveText } from '../lib/liveStatus';
import { useBox, usePane } from '../lib/panes';
import { STEPS, stepState, type Pipeline } from '../lib/pipeline';
import { planProgressView, PLAN_STEPS } from '../lib/planProgress';
import { useIntakeJob } from '../lib/useIntakeJob';
import { Decisions, stateLine } from './Hub';
import { LivePane } from './LivePane';
import { errText } from './msg';
import { PlanCard } from './PlanCard';
import { Splitter } from './Splitter';
import { newVideo, useUi } from './ui';
import './runview.css';

const LAYOUT_KEY = 'run.liveLayout';
/** beside: the story keeps at least this much width (narrower, the pane docks below) */
const SIDE_MAIN = 600;
type Layout = 'below' | 'side';

function loadLayout(): Layout {
  return localStorage.getItem(LAYOUT_KEY) === 'side' ? 'side' : 'below';
}

/** seconds -> "2 s" / "1:31" (a step's duration in the story) */
function dur(s: number): string {
  return s < 60 ? t('run.secs', { n: Math.max(1, Math.round(s)) }) : fmtClock(s);
}

function useNow(on: boolean) {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    if (!on) return;
    const tm = window.setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => window.clearInterval(tm);
  }, [on]);
  return now;
}

// ---------------------------------------------------------------- the shell: hero + story, the live pane docked
function RunShell({ live, hero, children, running, testId, attrs }: { live: LiveState; hero: ReactNode; children?: ReactNode; running: boolean; testId: string; attrs?: Record<string, string | undefined> }) {
  const [layout, setLayout] = useState<Layout>(loadLayout);
  const [boxRef, box] = useBox<HTMLDivElement>();
  const side = layout === 'side' && box.w >= SIDE_MAIN + 360;
  const below = usePane('run.live', box.h ? box.h - 220 : undefined);
  const beside = usePane('run.side', box.w ? box.w - SIDE_MAIN : undefined);
  const pane = side ? beside : below;
  const flip = () => {
    const n: Layout = layout === 'side' ? 'below' : 'side';
    localStorage.setItem(LAYOUT_KEY, n);
    setLayout(n);
  };
  return (
    <div className={`runv ${side ? 'runv-side' : 'runv-below'}`} data-testid={testId} ref={boxRef} {...attrs}>
      <div className="runv-main" data-testid="run-main">
        {hero}
        {children}
      </div>
      {pane.collapsed ? (
        <button className="runv-livebar" onClick={pane.toggle} data-testid="live-show" aria-expanded={false}>
          <span className={`lv-dot ${running ? 'on' : ''}`} aria-hidden />
          <b>{t('lp.title')}</b>
          <span className="muted">{live.lines.length ? t('run.liveLines', { n: live.lines.length }) : t('lp.none')}</span>
          <span className="sp" />
          <span className="muted">{t('lp.show')}</span>
        </button>
      ) : (
        <>
          <Splitter
            orient={side ? 'col' : 'row'}
            sign={-1}
            state={{ size: pane.size, collapsed: false }}
            spec={pane.spec}
            room={side ? (box.w ? box.w - SIDE_MAIN : undefined) : box.h ? box.h - 220 : undefined}
            onChange={pane.set}
            onReset={pane.reset}
            label={t('run.liveResize')}
            tip={t('lay.dragTip')}
            testId="live-split"
          />
          <div className="runv-live" style={side ? { width: pane.size } : { height: pane.size }}>
            <LivePane live={live} layout={side ? 'side' : 'below'} onLayout={box.w >= SIDE_MAIN + 360 ? flip : undefined} onCollapse={pane.toggle} />
          </div>
        </>
      )}
    </div>
  );
}

function Hero({ eyebrow, actions, title, prompt, now, pct, left, timeline }: { eyebrow: ReactNode; actions: ReactNode; title: string; prompt?: string | null; now: ReactNode; pct: number | null; left: ReactNode; timeline: ReactNode }) {
  return (
    <header className="runv-hero">
      <div className="runv-top">
        <span className="runv-eyebrow" data-testid="run-eyebrow">
          {eyebrow}
        </span>
        <span className="sp" />
        {actions}
      </div>
      <h1 className="runv-title clamp2" data-testid="hub-title" lang="zh-CN">
        {title}
      </h1>
      {prompt ? <p className="runv-quote muted clamp2">“{prompt}”</p> : null}
      <p className="runv-now" data-testid="run-now">
        {now}
      </p>
      <div className="runv-big">
        <span className="runv-pct tnum" data-testid="run-pct">
          {pct == null ? '—' : `${pct}%`}
        </span>
        <span className="runv-left muted" data-testid="run-left">
          {left}
        </span>
      </div>
      <div className={`runv-track ${pct == null ? 'indet' : ''}`} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct ?? undefined} aria-label={t('run.progress')} data-testid="run-bar">
        <i style={{ width: `${pct ?? 30}%` }} />
      </div>
      {timeline}
    </header>
  );
}

function Story({ entries, label, now, empty }: { entries: StoryEntry[]; label: (s: string) => string; now: number; empty: string }) {
  return (
    <section className="runv-story" data-testid="run-story" aria-label={t('run.happened')}>
      <h2 className="runv-h">{t('run.happened')}</h2>
      {!entries.length && <p className="muted small" data-testid="run-story-empty">{empty}</p>}
      <ol>
        {entries.map((e, k) => (
          <li key={`${e.step}-${k}`} className={`runv-st ${e.state}`} data-testid="run-story-step" data-step={e.step} data-state={e.state}>
            <span className="runv-t tnum">{fmtTime(e.start * 1000)}</span>
            <span className="runv-mk" aria-hidden />
            <div className="runv-body">
              <b>{label(e.step)}</b>
              {e.facts.length > 0 && (
                <p className="muted" data-testid="run-facts">
                  {e.facts.map((f) => tk(f.key, f.params)).join(' · ')}
                </p>
              )}
              {e.files.length > 0 && (
                <div className="runv-files" data-testid="run-files">
                  {e.files.slice(-12).map((f) => (
                    <span key={f.name} className={`runv-f ${f.state}`} data-testid="run-file" data-state={f.state} title={f.name}>
                      <span className="nm clamp1">{f.name}</span>
                      <i />
                    </span>
                  ))}
                  {e.files.length > 12 && <span className="muted small">{t('run.moreFiles', { n: e.files.length - 12 })}</span>}
                </div>
              )}
              {e.decided.map((d, i) => (
                <div key={`d${i}`} className="runv-dec" data-testid="run-decided">
                  <Sparkles className="ico" />
                  <span>
                    {d.job ? `${d.job} · ` : ''}
                    {t(d.by === 'ai' ? 'run.decidedAi' : 'run.decidedRules', { what: d.kind ? tk(`checkpoint.${d.kind}`) : t('hub.decisionOther') })}
                  </span>
                </div>
              ))}
              {e.ai.slice(-2).map((a, i) => (
                <div key={`a${i}`} className="runv-dec ai" data-testid="run-ai">
                  <Sparkles className="ico" />
                  <span>
                    <b>{providerName(a.provider) || t('run.ai')}</b> · {a.text}
                  </span>
                </div>
              ))}
            </div>
            <span className="runv-d tnum muted">{dur((e.end ?? now) - e.start)}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

// ---------------------------------------------------------------- a request being planned
export function RequestRun({ r }: { r: OpenRequest }) {
  const { client } = useEngine();
  const { reload } = useHistory();
  const ui = useUi();
  const { job, revise, retry } = useIntakeJob(r.id);
  const running = (job?.state ?? r.state) === 'running' && !job?.plan;
  const live = useLive('request', r.id);
  const now = useNow(running);
  const discard = async () => {
    if (!client) return;
    try {
      await client.discardIntake(r.id);
      ui.toast(t('hub.discarded'));
      reload();
    } catch (e) {
      ui.toast(errText(e), { error: true });
    }
  };
  /** Stop / Start over: the request goes (nothing was made) and the composer has her words and files back */
  const startOver = async () => {
    if (!client) return;
    try {
      await client.discardIntake(r.id);
    } catch {
      // already gone
    }
    sessionStorage.setItem('v4.composer', JSON.stringify({ prompt: r.prompt ?? '', files: r.inputs ?? [] }));
    sessionStorage.removeItem('v4.hubSel');
    reload();
    newVideo();
  };
  const stop = async () => {
    try {
      await client?.stopIntake(r.id);
    } catch {
      // already finished: going back to the composer is still right
    }
    void startOver();
  };
  const view = planProgressView(job?.progress ?? r.progress);
  const story = useMemo(() => planStory(live.lines, now), [live.lines, now]);
  const at = view ? PLAN_STEPS.indexOf(view.steps.find((s) => s.state === 'current')?.id ?? 'scan') : 0;
  const pct = running ? Math.min(99, Math.round(((Math.max(0, at) + (view?.fraction ?? 0.35)) / PLAN_STEPS.length) * 100)) : job?.plan ? 100 : null;
  const started = job?.started ?? r.started ?? null;
  const p: Pipeline = { state: r.state === 'error' ? 'failed' : r.state === 'needs' ? 'you' : running ? 'planning' : 'plan-ready', current: 'plan', progress: null, eta: null };
  const sentence = running ? (view ? [view.label, view.detail].filter(Boolean).join(' — ') : job?.step === 'revise' ? t('plan.revising') : t('plan.reading')) : stateLine(p, undefined, r);
  const stepNote = (id: string) => {
    const e = story.find((x) => x.step === id);
    if (!e) return view?.steps.find((s) => s.id === id)?.note ?? null;
    return e.state === 'now' ? (e.facts[0] ? tk(e.facts[0].key, e.facts[0].params) : null) : dur((e.end ?? now) - e.start);
  };
  const hero = (
    <Hero
      eyebrow={
        <>
          <span>{running ? t('run.planning') : stateLine(p, undefined, r)}</span>
          {started ? <span className="tnum">· {t('run.startedAt', { at: fmtTime(started * 1000) })}</span> : null}
          {running && started ? (
            <span className="tnum" data-testid="plan-elapsed">
              · {fmtClock(Math.max(0, now - started))}
            </span>
          ) : null}
        </>
      }
      actions={
        <>
          <span className={`hub-mode ${r.mode === 'autopilot' ? 'on' : ''}`} data-testid="hub-request-mode">
            {r.mode === 'autopilot' ? <Sparkles className="ico" /> : null}
            {t(r.mode === 'autopilot' ? 'ap.auto' : 'ap.ask')}
          </span>
          {running && (
            <button className="btn" onClick={() => void stop()} data-testid="plan-stop">
              <Square className="ico" />
              {t('plan.stop')}
            </button>
          )}
          <button className="btn ghost" onClick={() => void discard()} data-testid="hub-discard">
            <Trash2 className="ico" />
            {t('hub.discard')}
          </button>
        </>
      }
      title={r.name || r.prompt || t('home.planningRow')}
      prompt={r.name ? r.prompt : null}
      now={sentence}
      pct={pct}
      left={running ? t('run.soFar', { t: fmtClock(Math.max(0, now - (started ?? now))) }) : job?.seconds ? t('run.took', { t: fmtClock(job.seconds) }) : ''}
      timeline={
        <ol className="runv-tl" data-testid="run-timeline">
          {(view?.steps ?? PLAN_STEPS.map((id) => ({ id, label: t(`plan.step.${id}` as MessageKey), state: running ? ('pending' as const) : ('done' as const), note: null }))).map((s) => (
            <li key={s.id} className={s.state} data-testid={`plan-step-${s.id}`} data-state={s.state}>
              <span>{s.label}</span>
              <small className="tnum">{stepNote(s.id) ?? ' '}</small>
            </li>
          ))}
        </ol>
      }
    />
  );
  return (
    <RunShell live={live} hero={hero} running={running} testId="hub-request" attrs={{ 'data-mode': r.mode, 'data-run': 'request' }}>
      {running ? (
        <Story entries={story} label={(s) => t(`plan.step.${s}` as MessageKey)} now={now} empty={t('run.storyNone')} />
      ) : (
        <div className="runv-plan">
          <PlanCard
            job={job}
            jobId={r.id}
            onRevise={(s) => void revise(s).catch((e) => ui.toast(errText(e), { error: true }))}
            onRetry={() => void retry().catch((e) => ui.toast(errText(e), { error: true }))}
            onReset={() => void startOver()}
            onStarted={() => reload()}
            onApplied={() => undefined}
          />
          {story.length > 0 && <Story entries={story} label={(s) => t(`plan.step.${s}` as MessageKey)} now={now} empty="" />}
        </div>
      )}
    </RunShell>
  );
}

// ---------------------------------------------------------------- a project being made
export function ProjectRun({ i, p }: { i: HistoryItem; p: Pipeline; posts: CalendarPost[] }) {
  const { client } = useEngine();
  const { reload: reloadHist } = useHistory();
  const ui = useUi();
  const running = p.state === 'run' || p.state === 'queued';
  const live = useLive('project', i.id);
  const now = useNow(running);
  const { data: ap, reload: reloadAp } = useLoad((c) => c.autopilot(i.id).catch(() => null as AutopilotDoc | null), [i.id, i.updated]);
  useEffect(() => {
    if (!running) return;
    const tm = setInterval(reloadAp, 4000);
    return () => clearInterval(tm);
  }, [running]); // eslint-disable-line react-hooks/exhaustive-deps
  const on = ap?.supported ? !!ap.autopilot?.on : !!i.autopilot;
  const setMode = async (v: boolean) => {
    if (!client || v === on) return;
    try {
      await client.autopilotMode(i.id, v);
      ui.toast(t('hub.modeSwitched', { mode: t(v ? 'ap.auto' : 'ap.ask') }));
      reloadAp();
      reloadHist();
    } catch (e) {
      ui.toast(errText(e), { error: true });
    }
  };
  const clipsTotal = i.live?.jobs_total ?? (typeof i.live?.params?.total === 'number' ? (i.live.params.total as number) : 0);
  const story = useMemo(() => runStory(live.lines, now, clipsTotal), [live.lines, now, clipsTotal]);
  const pct = p.progress == null ? null : Math.round(p.progress * 100);
  const started = i.live?.started ?? null;
  const step = t(`hub.step.${p.current}` as MessageKey);
  const msg = liveText(i.live);
  const sentence = p.state === 'queued' ? t('hub.queuedLong') : msg ? t('run.nowRun', { step, what: msg }) : step;
  const hero = (
    <Hero
      eyebrow={
        <>
          <span>{p.state === 'queued' ? t('hub.s.queued', { n: i.queued ?? 1 }) : t('run.making')}</span>
          {started ? <span className="tnum">· {t('run.startedAt', { at: fmtTime(started * 1000) })}</span> : null}
          {started && p.state === 'run' ? <span className="tnum" data-testid="run-elapsed">· {fmtClock(Math.max(0, now - started))}</span> : null}
        </>
      }
      actions={
        (ap?.supported || i.autopilot !== undefined) && (
          <div className="seg hub-modeseg" role="radiogroup" aria-label={t('ap.setting')} data-testid="hub-mode" data-on={on ? '1' : '0'}>
            <button role="radio" aria-checked={on} className={on ? 'on' : ''} onClick={() => void setMode(true)} title={t('hub.modeOn')} data-testid="hub-mode-auto">
              <Sparkles className="ico" />
              {t('ap.auto')}
            </button>
            <button role="radio" aria-checked={!on} className={!on ? 'on' : ''} onClick={() => void setMode(false)} title={t('hub.modeOff')} data-testid="hub-mode-ask">
              {t('ap.ask')}
            </button>
          </div>
        )
      }
      title={i.name}
      prompt={i.prompt}
      now={<span data-testid="hub-state-line">{sentence}</span>}
      pct={pct}
      left={p.eta ? t('hub.left', { t: fmtMinutes(Math.max(1, Math.round(p.eta / 60))) }) : started ? t('run.soFar', { t: fmtClock(Math.max(0, now - started)) }) : ''}
      timeline={
        <ol className="runv-tl" data-testid="hub-steps" data-current={p.current}>
          {STEPS.map((s) => {
            const st = stepState(s, p);
            const e = story.find((x) => x.step === s);
            const f = e?.facts.find((x) => x.key === 'run.f.clips');
            const note = f ? t('run.f.clipsShort', { done: Number(f.params.done), n: Number(f.params.n) }) : null;
            return (
              <li key={s} className={st === 'todo' ? 'pending' : st} data-step={s} data-state={st}>
                <span>{t(`hub.step.${s}` as MessageKey)}</span>
                <small className="tnum">{note ?? ' '}</small>
              </li>
            );
          })}
        </ol>
      }
    />
  );
  return (
    <RunShell live={live} hero={hero} running={running} testId="hub-project" attrs={{ 'data-id': i.id, 'data-state': p.state, 'data-run': 'project' }}>
      <Story entries={story} label={(s) => t(`hub.step.${s}` as MessageKey)} now={now} empty={p.state === 'queued' ? t('hub.queuedLong') : t('run.storyNone')} />
      {ap?.supported !== false && (ap?.decisions?.length ?? 0) > 0 && (
        <div className="runv-decs">
          <Decisions item={i.id} doc={ap} clips={[]} busy={p.state === 'run'} onChanged={() => (reloadAp(), reloadHist())} />
        </div>
      )}
    </RunShell>
  );
}
