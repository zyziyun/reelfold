// Goal mode's page (#/studio?goal=<id>): one request that asked for several videos. The hero says the goal, how far
// the group is ("4 of 6 made") and what it is doing; then, by state:
//   surveying  what it reads right now (clips, photos, stories, the AI's ideas)
//   planned    the plan card: one card per video - rename, change its kind or length, drop or keep, pick two and
//              merge them - and 「Make these N videos」 (on autopilot this step passes by itself)
//   running    one row per video with its own state, progress and reason; Drop / Try again / Open
//   done       what was made (each video's files per platform and its post) and what was dropped and why;
//              「Remove unfinished」
// The stories the footage fell into (time, place, light) are below, with their frames.
import { AiPickChip, AiTag } from './AiPick';
import { labelOf } from '../lib/projectAi';
import type { ProjectAi } from '../../../shared/projectAi';
import { Check, ChevronDown, ChevronRight, Copy, FolderOpen, GitMerge, Layers, Play, RotateCcw, Square, Trash2, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { GOAL_KINDS, type Goal, type GoalEditOp, type GoalKind, type GoalStory, type GoalVideo } from '../../../shared/goal';
import { EXPORT_PLATFORMS } from '../../../shared/chatEdit';
import type { Clip, EditOp } from '../../../shared/v04';
import { fmtDuration, parseSecs } from '../../../shared/platformLengths';
import { fmtLen, getLang, t } from '../i18n';
import { useEngine } from '../lib/engine';
import { countNote, dropReason, goalActive, goalHref, goalLine, goalPct, goalTitle, goalTone, groupVideos, surveyLine, versionLabel, versionLine, versionTone, videoHref, videoLine, videoTitle, videoTone, GOAL_POLL_MS } from '../lib/goals';
import { failureReason } from './Failure';
import { Thumb } from './kit';
import { errText } from './msg';
import { PlatformIcon } from './PlatformIcon';
import { platformName } from '../lib/platformName';
import { filePlatforms, missingTargets } from '../lib/versions';
import { useUi } from './ui';
import type { PilotFailure } from '../../../shared/v02';
import './goal.css';

const base = (p: string) => p.replace(/[\\/]+$/, '').split(/[\\/]/).pop() ?? p;

function useGoal(gid: string) {
  const { client, subscribe } = useEngine();
  const [g, setG] = useState<Goal | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!client) return;
    let alive = true;
    client
      .goal(gid)
      .then((x) => alive && (setG(x), setErr(null)))
      .catch((e: Error) => alive && setErr(e.message));
    return () => {
      alive = false;
    };
  }, [client, gid, n]);
  useEffect(() => subscribe((e) => void ((e.type === 'goals' || e.type === 'batches') && setN((x) => x + 1))), [subscribe]);
  const going = !!g && (g.state === 'surveying' || g.state === 'running');
  useEffect(() => {
    if (!going) return;
    const tm = window.setInterval(() => setN((x) => x + 1), GOAL_POLL_MS);
    return () => window.clearInterval(tm);
  }, [going]);
  return { g, setG, err, reload: () => setN((x) => x + 1) };
}

export function GoalPage({ gid, vid }: { gid: string; vid?: string }) {
  const { client } = useEngine();
  const ui = useUi();
  const { g, setG, err } = useGoal(gid);
  const [busy, setBusy] = useState(false);
  const act = async <G extends Goal>(fn: () => Promise<G | null | void>, done?: (x: G) => void) => {
    if (!client || busy) return;
    setBusy(true);
    try {
      const x = await fn();
      if (x) {
        setG(x);
        done?.(x);
      }
    } catch (e) {
      ui.toast(errText(e), { error: true });
    } finally {
      setBusy(false);
    }
  };
  if (err && !g) return <div className="st-detail muted" data-testid="goal-missing">{t('goal.failed')}</div>;
  if (!g) return <div className="st-detail" aria-busy="true" data-testid="goal-loading" />;
  const pct = Math.round(goalPct(g) * 100);
  const from = g.inputs.map(base).join(', ');
  const vs = groupVideos(g);
  const unfinished = vs.some((v) => v.state === 'dropped' && !v.cleared);
  return (
    <div className="goalv" data-testid="goal-page" data-goal={g.id} data-state={g.state}>
      <header className="runv-hero goalv-hero">
        <div className="runv-top">
          <span className="runv-eyebrow" data-testid="goal-eyebrow">
            <Layers className="ico" /> {t('goal.kicker')} · {t('goal.from', { where: from })}
          </span>
          <span className="sp" />
          {g.state !== 'done' && g.state !== 'failed' && (
            <AiPickChip
              value={g.ai ?? null}
              onChange={(v) => void act(() => client!.setGoalAi(g.id, v), () => ui.toast(t('tai.groupSwitched', { name: labelOf(v) })))}
              testId="goal-ai"
              title={t('tai.groupTip')}
              disabled={busy}
            />
          )}
          {(g.state === 'surveying' || g.state === 'running') && (
            <button className="btn sm" disabled={busy} onClick={() => void act(() => client!.goalAct(g.id, 'stop'))} data-testid="goal-stop">
              <Square className="ico" />
              {t('goal.stop')}
            </button>
          )}
          {(g.state === 'failed' || (g.state === 'stopped' && !vs.length)) && (
            <button className="btn sm primary" disabled={busy} onClick={() => void act(() => client!.goalAct(g.id, 'retry'))} data-testid="goal-retry">
              <RotateCcw className="ico" />
              {t('goal.tryAgain')}
            </button>
          )}
          {(g.state === 'done' || g.state === 'stopped') && unfinished && (
            <button className="btn sm" disabled={busy} data-tip={t('goal.clearTip')} onClick={() => void act(() => client!.goalAct(g.id, 'clear'), (x) => ui.toast(t('goal.cleared', { n: (x.cleared?.requests ?? 0) + (x.cleared?.projects ?? 0) })))} data-testid="goal-clear">
              <Trash2 className="ico" />
              {t('goal.clear')}
            </button>
          )}
          {!goalActive(g) && (
            <button className="btn sm ghost" disabled={busy} onClick={() => void act(async () => (await client!.goalAct(g.id, 'dismiss'), (location.hash = '#/studio'), null))} data-testid="goal-dismiss">
              <X className="ico" />
              {t('goal.dismiss')}
            </button>
          )}
        </div>
        <h1 className="runv-title clamp2" data-testid="goal-title">
          {goalTitle(g)}
        </h1>
        {g.goal && g.prompt && <p className="runv-quote muted clamp2">“{g.prompt}”</p>}
        <p className="runv-now" data-testid="goal-now">
          <i className={`dot ${goalTone(g)}`} /> {goalLine(g)}
        </p>
        {g.state !== 'planned' && countNote(g) && (
          <p className={`small ${g.count?.short ? 'goalv-note' : 'muted'}`} data-testid="goal-count">
            {countNote(g)}
          </p>
        )}
        {g.state !== 'planned' && g.state !== 'failed' && (
          <>
            <div className="runv-big">
              <span className="runv-pct tnum" data-testid="goal-pct">
                {g.state === 'surveying' ? '—' : `${pct}%`}
              </span>
            </div>
            <div className={`runv-track ${g.state === 'surveying' ? 'indet' : ''}`} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={g.state === 'surveying' ? undefined : pct} aria-label={t('run.progress')} data-testid="goal-bar">
              <i style={{ width: `${g.state === 'surveying' ? 30 : Math.max(2, pct)}%` }} />
            </div>
          </>
        )}
      </header>
      {g.state === 'surveying' && <SurveySteps g={g} />}
      {g.state === 'failed' && (
        <p className="goalv-err" role="alert" data-testid="goal-error">
          {g.error_code === 'plan-empty' ? t('goal.noneMade') : failureReason({ code: g.error_code || 'unknown', state: 'failed' } as unknown as PilotFailure)}
        </p>
      )}
      {g.state === 'planned' && <GoalPlan g={g} busy={busy} onOps={(ops) => void act(() => client!.editGoal(g.id, ops))} onApprove={() => void act(() => client!.goalAct(g.id, 'approve'))} />}
      {(g.state === 'running' || g.state === 'done' || g.state === 'stopped') && (
        <>
          {g.state === 'done' && <GoalSummary g={g} />}
          <section className="goalv-sec" data-testid="goal-videos">
            <h2 className="runv-h">{t('goal.videos')}</h2>
            {vs.map((v) => (
              <VideoRow
                key={v.id}
                gid={g.id}
                v={v}
                on={vid === v.id}
                busy={busy}
                onAct={(a) => void act(() => client!.goalVideo(g.id, v.id, a))}
                onAi={(x) => void act(() => client!.setGoalAi(g.id, x, v.id), () => ui.toast(t('tai.switched', { name: labelOf(x) })))}
              />
            ))}
          </section>
        </>
      )}
      {g.survey?.stories?.length ? <Stories g={g} /> : null}
    </div>
  );
}

function SurveySteps({ g }: { g: Goal }) {
  const steps = ['scan', 'probe', 'cluster', 'model', 'write'];
  const seen = g.progress?.seen ?? [];
  const cur = g.progress?.stage ?? 'scan';
  return (
    <section className="goalv-sec" data-testid="goal-survey">
      <ol className="goalv-steps">
        {steps.map((s) => {
          const state = s === cur ? 'now' : seen.includes(s) ? 'done' : 'todo';
          return (
            <li key={s} className={state} data-testid="goal-step" data-step={s} data-state={state}>
              <span className="mk" aria-hidden>{state === 'done' ? <Check className="ico" /> : null}</span>
              {s === cur ? surveyLine(g) : surveyLine({ progress: { stage: s } })}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function storyThumbs(g: Goal, v: Pick<GoalVideo, 'stories'>): string[] {
  const by = new Map((g.survey?.stories ?? []).map((s) => [s.id, s]));
  return v.stories.flatMap((s) => by.get(s)?.thumbs ?? []).slice(0, 3);
}

function storyWhere(g: Goal, v: Pick<GoalVideo, 'stories'>): string {
  const zh = getLang() === 'zh-CN';
  const by = new Map((g.survey?.stories ?? []).map((s) => [s.id, s]));
  const bits = v.stories.map((s) => {
    const x = by.get(s);
    if (!x) return null;
    const place = x.place ? (zh ? x.place.zh : x.place.en) : null;
    return [place, x.date].filter(Boolean).join(' ');
  });
  return [...new Set(bits.filter(Boolean))].slice(0, 3).join(' · ');
}

function GoalPlan({ g, busy, onOps, onApprove }: { g: Goal; busy: boolean; onOps: (ops: GoalEditOp[]) => void; onApprove: () => void }) {
  const [picked, setPicked] = useState<string[]>([]);
  const keep = g.videos.filter((v) => !v.planned_out);
  const tot = g.survey?.totals;
  return (
    <section className="goalv-sec goalv-plan" data-testid="goal-plan">
      <h2 className="runv-h">{t('goal.planTitle', { n: keep.length })}</h2>
      <p className="muted small">{t('goal.planLead')}</p>
      {countNote(g) && (
        <p className={`small ${g.count?.short ? 'goalv-note' : 'muted'}`} data-testid="goal-count">
          {countNote(g)}
        </p>
      )}
      {tot && (
        <p className="muted small" data-testid="goal-found">
          {t('goal.found', { clips: tot.videos, photos: tot.photos, days: tot.days.length })}
          {tot.panoramas ? ` · ${t('goal.panos', { n: tot.panoramas })}` : ''} · {t('goal.stories', { n: g.survey?.stories.length ?? 0 })}
        </p>
      )}
      {(g.survey?.unused?.photos ?? 0) + (g.survey?.unused?.panoramas ?? 0) > 0 && (
        <p className="muted small" data-testid="goal-unused">
          {t('goal.unusedNote', {
            what: [g.survey?.unused?.photos ? t('goal.photosN', { n: g.survey.unused.photos }) : null, g.survey?.unused?.panoramas ? t('goal.panos', { n: g.survey.unused.panoramas }) : null].filter(Boolean).join(getLang() === 'zh-CN' ? '、' : ', '),
          })}
        </p>
      )}
      {g.planner?.fallback && (
        <p className="goalv-note small" data-testid="goal-rules-note">
          {t('goal.rulesNote')}
        </p>
      )}
      <div className="goalv-cards">
        {g.videos.map((v) => (
          <PlanCard
            key={v.id}
            g={g}
            v={v}
            picked={picked.includes(v.id)}
            onPick={() => setPicked((p) => (p.includes(v.id) ? p.filter((x) => x !== v.id) : [...p, v.id]))}
            onOps={onOps}
            busy={busy}
          />
        ))}
      </div>
      <div className="goalv-foot">
        {picked.length >= 2 && (
          <button className="btn" disabled={busy} onClick={() => (onOps([{ op: 'merge', videos: picked }]), setPicked([]))} data-testid="goal-merge">
            <GitMerge className="ico" />
            {t('goal.merge')}
          </button>
        )}
        <span className="sp" />
        <button className="btn primary lg" disabled={busy || !keep.length} onClick={onApprove} data-testid="goal-approve">
          <Play className="ico" />
          {t('goal.approve', { n: keep.length })}
        </button>
      </div>
    </section>
  );
}

function PlanCard({ g, v, picked, onPick, onOps, busy }: { g: Goal; v: GoalVideo; picked: boolean; onPick: () => void; onOps: (ops: GoalEditOp[]) => void; busy: boolean }) {
  const [title, setTitle] = useState(videoTitle(v));
  useEffect(() => setTitle(videoTitle(v)), [v.title, v.title_zh]); // eslint-disable-line react-hooks/exhaustive-deps
  const [len, setLen] = useState(String(v.length_s));
  useEffect(() => setLen(String(v.length_s)), [v.length_s]);
  const out = !!v.planned_out;
  const merged = v.merged_into ? g.videos.find((x) => x.id === v.merged_into) : null;
  const thumbs = storyThumbs(g, v);
  const rename = () => {
    const s = title.trim();
    if (s && s !== videoTitle(v)) onOps([{ op: 'rename', video: v.id, title: s }]);
  };
  const setLength = () => {
    const n = Math.round(Number(len));
    if (Number.isFinite(n) && n >= 10 && n <= 600 && n !== v.length_s) onOps([{ op: 'length', video: v.id, length_s: n }]);
    else setLen(String(v.length_s));
  };
  return (
    <article className={`goalv-card ${out ? 'out' : ''} ${picked ? 'picked' : ''}`} data-testid="goal-plan-video" data-video={v.id} data-out={out ? 'true' : undefined}>
      <div className="goalv-thumbs" style={{ gridTemplateColumns: `repeat(${Math.max(1, thumbs.length)}, 1fr)` }}>
        {thumbs.length ? thumbs.map((p) => <Thumb key={p} src={p} ratio="16/9" className="goalv-th" />) : <div className="goalv-th empty" />}
      </div>
      <div className="goalv-cardbody">
        <input
          className="goalv-titlein"
          value={title}
          disabled={out || busy}
          onChange={(e) => setTitle(e.target.value)}
          onBlur={rename}
          onKeyDown={(e) => e.key === 'Enter' && (e.currentTarget as HTMLInputElement).blur()}
          aria-label={t('goal.rename')}
          maxLength={80}
          data-testid="goal-plan-title"
        />
        <p className="muted small clamp2">{[v.theme, v.why].filter(Boolean).join(' — ')}</p>
        <p className="faint small clamp1" data-testid="goal-plan-where">
          {[storyWhere(g, v), v.clips || !v.stills ? t('goal.clips', { n: v.clips }) : t('goal.photosN', { n: v.stills })].filter(Boolean).join(' · ')}
        </p>
        {out ? (
          <p className="small muted" data-testid="goal-plan-out">
            {merged ? t('goal.mergedInto', { name: videoTitle(merged) }) : t('goal.droppedOnPlan')}
          </p>
        ) : (
          <div className="goalv-fields">
            <label>
              <span className="faint small">{t('goal.kind')}</span>
              <select value={v.kind} disabled={busy} onChange={(e) => onOps([{ op: 'kind', video: v.id, kind: e.target.value as GoalKind }])} data-testid="goal-plan-kind">
                {GOAL_KINDS.filter((k) => k !== 'photos' || v.kind === 'photos').map((k) => (
                  <option key={k} value={k}>
                    {t(`goal.kind.${k}`)}
                  </option>
                ))}
              </select>
            </label>
            {v.lengths ? null : (
              <label>
                <span className="faint small">{t('goal.length')}</span>
                <input type="number" min={10} max={600} step={5} value={len} disabled={busy} onChange={(e) => setLen(e.target.value)} onBlur={setLength} onKeyDown={(e) => e.key === 'Enter' && (e.currentTarget as HTMLInputElement).blur()} data-testid="goal-plan-length" />
              </label>
            )}
            {v.lengths ? null : (
              <span className="goalv-plats" aria-label={v.platforms.map(platformName).join(', ')}>
                {v.platforms.map((p) => (
                  <PlatformIcon key={p} id={p} size={14} title={platformName(p)} />
                ))}
              </span>
            )}
          </div>
        )}
        {!out && v.lengths && <PlatformLengths v={v} busy={busy} onOps={onOps} />}
        <div className="goalv-cardacts">
          {!out && (
            <label className="goalv-pick small">
              <input type="checkbox" checked={picked} onChange={onPick} data-testid="goal-plan-pick" />
              {t('goal.pick')}
            </label>
          )}
          <span className="sp" />
          {out && !merged ? (
            <button className="btn sm" disabled={busy} onClick={() => onOps([{ op: 'restore', video: v.id }])} data-testid="goal-plan-keep">
              {t('goal.keep')}
            </button>
          ) : !out ? (
            <button className="btn sm ghost" disabled={busy} onClick={() => onOps([{ op: 'drop', video: v.id }])} data-testid="goal-plan-drop">
              <X className="ico" />
              {t('goal.drop')}
            </button>
          ) : null}
        </div>
      </div>
    </article>
  );
}

/** The plan card's lengths: one box per platform (each platform's habit for this kind, capped by the footage; hers
 * win), the cuts they make (a long cut with chapters, a short one) and how much the footage can carry. */
function PlatformLengths({ v, busy, onOps }: { v: GoalVideo; busy: boolean; onOps: (ops: GoalEditOp[]) => void }) {
  const lang = getLang();
  const lens = v.lengths ?? {};
  return (
    <div className="goalv-lens" data-testid="goal-plan-lengths">
      <span className="faint small">{t('goal.lengths')}</span>
      <div className="goalv-lenrow">
        {v.platforms.map((p) => (
          <LengthBox key={p} p={p} value={lens[p] ?? v.length_s} own={v.lengths_own?.[p] != null} busy={busy} onSet={(n) => onOps([{ op: 'length', video: v.id, platform: p, length_s: n }])} />
        ))}
      </div>
      {(v.cuts?.length ?? 0) > 1 && (
        <span className="faint small" data-testid="goal-plan-cuts">
          {v.cuts!.map((c) => t(c.form === 'long' ? 'goal.cutLong' : 'goal.cutShort', { len: fmtDuration(c.length_s, lang) })).join(' · ')}
        </span>
      )}
      {v.possible_s ? (
        <span className={`small ${v.over_footage ? 'goalv-warn' : 'faint'}`} data-testid="goal-plan-possible">
          {t('goal.possible', { len: fmtDuration(v.possible_s, lang) })}
          {v.over_footage ? ` · ${t('goal.overFootage')}` : ''}
        </span>
      ) : null}
    </div>
  );
}

function LengthBox({ p, value, own, busy, onSet }: { p: string; value: number; own: boolean; busy: boolean; onSet: (n: number) => void }) {
  const [txt, setTxt] = useState(String(value));
  useEffect(() => setTxt(String(value)), [value]);
  const commit = () => {
    const n = parseSecs(txt, 10, 3600);
    if (n != null && n !== value) onSet(n);
    else setTxt(String(value));
  };
  const name = platformName(p);
  return (
    <label className={`goalv-len ${own ? 'own' : ''}`} title={own ? `${name} · ${t('goal.ownLength')}` : name} data-testid="goal-plan-platform-length" data-platform={p}>
      <PlatformIcon id={p} size={14} />
      <input type="number" min={10} max={3600} step={5} value={txt} disabled={busy} aria-label={t('goal.lengthFor', { name })} onChange={(e) => setTxt(e.target.value)} onBlur={commit} onKeyDown={(e) => e.key === 'Enter' && (e.currentTarget as HTMLInputElement).blur()} />
      <span className="faint small">{t('pls.secs')}</span>
    </label>
  );
}

/** One video of the group while it is made / once it is settled. */
export function VideoRow({ gid, v, on, busy, onAct, onAi }: { gid: string; v: GoalVideo; on?: boolean; busy?: boolean; onAct?: (a: 'drop' | 'retry') => void; onAi?: (ai: ProjectAi | null) => void }) {
  const tone = videoTone(v);
  const pct = v.state === 'making' && v.progress != null ? Math.round(v.progress * 100) : null;
  return (
    <div className={`goalv-row ${on ? 'on' : ''}`} data-testid="goal-video" data-video={v.id} data-state={v.state}>
      <span className={`dot ${tone}`} aria-hidden />
      <span className="tx">
        <b className="clamp1">{videoTitle(v)}</b>
        <span className="s muted clamp1" data-testid="goal-video-line">
          {t(`goal.kind.${v.kind}`)} · {videoLine(v)}
        </span>
        {(v.state === 'making' || v.state === 'planning') && (
          <span className={`bar ${pct == null ? 'indet' : ''}`}>
            <i style={{ width: `${Math.max(4, pct ?? 30)}%` }} />
          </span>
        )}
        <Versions v={v} />
      </span>
      {onAi && (v.state === 'waiting' || v.state === 'planning' || v.state === 'making' || v.state === 'you') ? (
        <AiPickChip value={v.ai ?? null} onChange={onAi} testId="goal-video-ai" title={t('tai.videoTip')} compact disabled={busy} />
      ) : (
        <AiTag ai={v.own_ai ? v.ai : null} testId="goal-video-ai-tag" />
      )}
      {v.projects?.length ? (
        <a className="btn sm ghost" href={videoHref(gid, v)} data-testid="goal-video-open">
          {t('goal.open')}
        </a>
      ) : null}
      {onAct && (v.state === 'waiting' || v.state === 'planning' || v.state === 'making' || v.state === 'you') && (
        <button className="btn sm ghost" disabled={busy} onClick={() => window.confirm(t('goal.dropAsk', { title: videoTitle(v) })) && onAct('drop')} data-testid="goal-video-drop">
          {t('goal.dropVideo')}
        </button>
      )}
      {onAct && v.state === 'dropped' && !v.cleared && (
        <button className="btn sm" disabled={busy} onClick={() => onAct('retry')} data-testid="goal-video-retry">
          <RotateCcw className="ico" />
          {t('goal.retryVideo')}
        </button>
      )}
    </div>
  );
}

/** A video's language versions (one project each): one line per version inside the video, each opening its own
 * page - the English and the Chinese cut are one video, never two loose rows. */
export function Versions({ v, item }: { v: GoalVideo; item?: string }) {
  const xs = v.versions ?? [];
  if (xs.length < 2 || v.state === 'made' || v.state === 'dropped') return null;
  return (
    <span className="goalv-vers" data-testid="goal-versions">
      {xs.map((x, k) => (
        // a span (the group's row around it is a link already): it opens the version's own page
        <span
          key={x.item ?? k}
          role="link"
          tabIndex={0}
          className={`goalv-ver ${item && x.item === item ? 'on' : ''}`}
          data-testid="goal-version"
          data-lang={x.lang ?? ''}
          data-state={x.state}
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            if (x.item) location.hash = `#/studio/${x.item}`;
          }}
          onKeyDown={(e) => {
            if (e.key !== 'Enter' || !x.item) return;
            e.preventDefault();
            e.stopPropagation();
            location.hash = `#/studio/${x.item}`;
          }}
        >
          <i className={`dot ${versionTone(x)}`} />
          <b>{versionLabel(x)}</b> <span className="muted">{versionLine(x)}</span>
        </span>
      ))}
    </span>
  );
}

/** What was made: each video's files per platform and its post; then what was dropped and why. */
function GoalSummary({ g }: { g: Goal }) {
  const vs = groupVideos(g);
  const made = vs.filter((v) => v.state === 'made');
  const dropped = vs.filter((v) => v.state === 'dropped');
  return (
    <section className="goalv-sec goalv-summary" data-testid="goal-summary">
      <h2 className="runv-h">{made.length === vs.length ? t('goal.allMade', { n: made.length }) : t('goal.doneSome', { made: made.length, total: vs.length, dropped: dropped.length })}</h2>
      {made.length ? <p className="muted small">{t('goal.summaryLead')}</p> : <p className="muted">{t('goal.noneMade')}</p>}
      {made.map((v) => (
        <MadeVideo key={v.id} gid={g.id} v={v} />
      ))}
      {dropped.length > 0 && (
        <div className="goalv-dropped" data-testid="goal-summary-dropped">
          <h3 className="small">{t('goal.droppedList')}</h3>
          <ul>
            {dropped.map((v) => (
              <li key={v.id} className="small">
                <b>{videoTitle(v)}</b> — <span className="muted">{dropReason(v)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

const WIDE = new Set(['youtube', 'x', 'facebook', 'linkedin', 'reddit', 'bilibili', 'weibo', 'zhihu', 'dailymotion']);

/** The platforms one file is for: the made file of a canvas stands for every platform of the video on that canvas
 * (YouTube and Bilibili share the 16:9 file's folder, its exports sit side by side). */
export function platformsFor(f: Pick<Clip['files'][number], 'platform' | 'platforms' | 'w' | 'h' | 'aspect'>, platforms: string[]): string[] {
  const wide = f.w && f.h ? f.w > f.h : f.aspect === '16:9';
  const mine = platforms.map((p) => p.split(':')[0]).filter((p) => WIDE.has(p) === wide);
  return [...new Set([...filePlatforms(f), ...mine])];
}

/** one made clip of the video and the project item it belongs to */
interface MadeClip {
  item: string;
  clip: Clip;
}

function MadeVideo({ gid, v }: { gid: string; v: GoalVideo }) {
  const { client } = useEngine();
  const ui = useUi();
  const [made, setMade] = useState<MadeClip[] | null>(null);
  const [making, setMaking] = useState<Record<string, boolean>>({});
  const [n, setN] = useState(0);
  const items = useMemo(() => (v.projects ?? []).map((p) => p.item), [v.projects]);
  useEffect(() => {
    if (!client || !items.length) return;
    let alive = true;
    void Promise.all(
      items.map((id) =>
        client
          .clips(id)
          .then((d) => d.clips.map((clip) => ({ item: id, clip })))
          .catch(() => [] as MadeClip[]),
      ),
    ).then((xs) => alive && setMade(xs.flat().filter((x) => !x.clip.extra && x.clip.files.length)));
    return () => {
      alive = false;
    };
  }, [client, items.join(), n]); // eslint-disable-line react-hooks/exhaustive-deps
  const clips = made?.map((x) => x.clip) ?? null;
  // a planned platform with no version: made from this clip in the background (an export of its own size)
  const make = async (m: MadeClip, pf: string) => {
    if (!client) return;
    const key = `${m.item}/${m.clip.id}/${pf}`;
    const target = EXPORT_PLATFORMS.find((x) => x.id === pf)?.target ?? pf;
    setMaking((x) => ({ ...x, [key]: true }));
    try {
      await client.editOutput(m.item, m.clip.id, [{ op: 'export_add', target, layout: 'auto' } as EditOp]);
      // every target: what goes out is the edit's fresh renders, the clip itself with its new version (_as_published)
      await client.renderOutput(m.item, m.clip.id, { quality: 'final', targets: 'all' });
      setN((x) => x + 1);
    } catch (e) {
      ui.toast(errText(e), { error: true });
    } finally {
      setMaking((x) => ({ ...x, [key]: false }));
    }
  };
  const copy = async (c: Clip) => {
    if (!c.post) return;
    await window.desk.copyText(`${c.post.title}\n\n${c.post.body}\n\n${c.post.tags.map((x) => `#${x}`).join(' ')}`.trim());
    ui.toast(t('goal.copied'));
  };
  return (
    <article className="goalv-made" data-testid="goal-made" data-video={v.id}>
      <header>
        <b>{videoTitle(v)}</b>
        <span className="muted small"> · {t(`goal.kind.${v.kind}`)}</span>
        <span className="sp" />
        <a className="btn sm ghost" href={videoHref(gid, v)} data-testid="goal-made-open">
          {t('goal.open')}
        </a>
      </header>
      {(made ?? []).map((m) => {
        const c = m.clip;
        const missing = missingTargets(c.targets, c.files);
        return (
        <div key={`${m.item}/${c.id}`} className="goalv-clip">
          <Thumb src={c.cover} ratio="16/9" className="goalv-th" />
          <div className="goalv-clipbody">
            <div className="goalv-files" data-testid="goal-made-files">
              {c.files.map((f) => {
                // one version (one clip): its file of a canvas is for every platform on that canvas; several versions
                // (a language each): each file is its own platform's
                const pls = platformsFor(f, (clips ?? []).length > 1 ? [] : v.platforms);
                return (
                <button key={f.path} className="goalv-file" onClick={() => void window.desk.showItem(f.path)} data-tip={t('goal.showFile')} data-testid="goal-made-file">
                  {pls.length ? pls.map((p) => <PlatformIcon key={p} id={p} size={14} />) : <FolderOpen className="ico" />}
                  <span>{pls.length ? pls.map(platformName).join(' · ') : base(f.path)}</span>
                  <span className="faint">
                    {f.w && f.h ? `${f.w}×${f.h}` : f.aspect}
                    {f.duration ? ` · ${fmtLen(f.duration)}` : ''}
                  </span>
                </button>
                );
              })}
              {missing.map((pf) => {
                const busy = making[`${m.item}/${c.id}/${pf}`];
                return (
                  <span key={pf} className="goalv-file goalv-missing" data-testid="goal-made-missing" data-pf={pf}>
                    <PlatformIcon id={pf} size={14} />
                    <span>{platformName(pf)}</span>
                    <span className="faint">{busy ? t('goal.makingOne') : t('goal.notMade')}</span>
                    <button className="btn sm ghost" disabled={busy || !client} onClick={() => void make(m, pf)} data-testid="goal-made-make">
                      {t('goal.make')}
                    </button>
                  </span>
                );
              })}
            </div>
            {c.post && (
              <div className="goalv-post" data-testid="goal-made-post">
                <b className="clamp1">{c.post.title}</b>
                <p className="muted small clamp2">{c.post.body}</p>
                <button className="btn sm ghost" onClick={() => void copy(c)} data-testid="goal-made-copy">
                  <Copy className="ico" />
                  {t('goal.copy')}
                </button>
              </div>
            )}
          </div>
        </div>
        );
      })}
    </article>
  );
}

function Stories({ g }: { g: Goal }) {
  const zh = getLang() === 'zh-CN';
  const st = g.survey?.stories ?? [];
  return (
    <details className="goalv-sec goalv-stories" data-testid="goal-stories" open={g.state === 'planned'}>
      <summary className="runv-h">
        {t('goal.stories', { n: st.length })} <span className="muted small">— {t('goal.storiesHint')}</span>
      </summary>
      <div className="goalv-storygrid">
        {st.map((s: GoalStory) => (
          <div key={s.id} className="goalv-story" data-testid="goal-story">
            <Thumb src={s.thumbs[0] ?? null} ratio="16/9" className="goalv-th" />
            <b className="small clamp1">{[s.place ? (zh ? s.place.zh : s.place.en) : null, s.date].filter(Boolean).join(' · ') || s.folder || s.id}</b>
            <span className="faint small clamp1">
              {[s.start ? s.start.slice(11, 16) : null, s.videos ? t('goal.clips', { n: s.videos }) : null, s.photos ? t('goal.photosN', { n: s.photos }) : null, s.panoramas ? t('goal.panos', { n: s.panoramas }) : null, s.seconds ? fmtLen(s.seconds) : null].filter(Boolean).join(' · ')}
            </span>
          </div>
        ))}
      </div>
    </details>
  );
}

const FOLD_KEY = 'studio.goalFolded';

function loadFolded(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(FOLD_KEY) ?? '[]') as unknown;
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : [];
  } catch {
    return [];
  }
}

/** The group in the Studio list: the goal's header (its overall progress, opens the goal's page) and one row per
 * video with its own state, each opening its project once it has one. */
export function GoalGroup({ g, on, vid, item }: { g: Goal; on: boolean; vid?: string; item?: string }) {
  const [folded, setFolded] = useState(() => loadFolded().includes(g.id));
  const fold = () => {
    const now = !folded;
    setFolded(now);
    const xs = loadFolded().filter((x) => x !== g.id);
    localStorage.setItem(FOLD_KEY, JSON.stringify(now ? [...xs, g.id] : xs));
  };
  const vs = groupVideos(g);
  const pct = Math.round(goalPct(g) * 100);
  const thumbs = (v: GoalVideo) => storyThumbs(g, v)[0] ?? null;
  return (
    <section className="st-goal" data-testid="studio-goal" data-goal={g.id} data-state={g.state}>
      <div className="st-goalheadwrap" style={{ display: 'flex', alignItems: 'center' }}>
        <button className="btn ghost icon sm st-goalfold" onClick={fold} aria-expanded={!folded} aria-label={goalTitle(g)} data-testid="studio-goal-fold">
          {folded ? <ChevronRight className="ico" /> : <ChevronDown className="ico" />}
        </button>
        <a className={`st-goalhead ${on ? 'on' : ''}`} href={goalHref(g.id)} aria-current={on ? 'true' : undefined} data-testid="studio-goal-head" style={{ flex: 1 }}>
          <Layers className="ico" />
          <span className="tx">
            <b className="clamp1">{goalTitle(g)}</b>
            <span className="s clamp1" data-testid="studio-goal-line">
              <i className={`dot ${goalTone(g)}`} />
              {goalLine(g)}
            </span>
            {(g.state === 'running' || g.state === 'surveying') && (
              <span className={`bar ${g.state === 'surveying' ? 'indet' : ''}`}>
                <i style={{ width: `${Math.max(4, g.state === 'surveying' ? 30 : pct)}%` }} />
              </span>
            )}
          </span>
        </a>
      </div>
      {!folded &&
        g.state !== 'surveying' &&
        vs.map((v) => {
          const sel = (!!vid && vid === v.id) || (!!item && !!v.projects?.some((p) => p.item === item));
          const tone = videoTone(v);
          return (
            <a key={v.id} className={`st-goalrow ${sel ? 'on' : ''}`} href={videoHref(g.id, v)} aria-current={sel ? 'true' : undefined} data-testid="studio-goal-row" data-video={v.id} data-state={v.state}>
              <Thumb src={thumbs(v)} ratio="16/9" className="st-th" />
              <span className="tx">
                <b className="clamp1">{videoTitle(v)}</b>
                <span className="s clamp1">
                  <i className={`dot ${tone}`} />
                  {videoLine(v)}
                </span>
                {(v.state === 'making' || v.state === 'planning') && !v.queued && (
                  <span className={`bar ${v.progress == null || v.state === 'planning' ? 'indet' : ''}`}>
                    <i style={{ width: `${Math.max(4, Math.round((v.progress ?? 0.3) * 100))}%` }} />
                  </span>
                )}
                <Versions v={v} item={item} />
              </span>
            </a>
          );
        })}
    </section>
  );
}
