// 「Edit the collection」 on a goal's page (2026-10-13, her words: "可以针对合集做二次编辑么，比如我希望除了这些多选几个片段"):
// one composer for the whole group, on the group's AI (the chip). What she says is routed by the engine
// (goaledit.py) to
//   more    new plan cards cut from the clips no video plays yet (the page shows them; Ask-me-first waits for her)
//   recut   one video's other shots: its shots now + the unused clips with their frames; she picks or lets the AI pick
//   fanout  one change to every made video, each clip through its own AI: per-video progress, what changed, Undo
// The quick chips say the common ones (「再做 3 条」「补够 12 条」「全部加旁白」「换一批镜头」).
import { ArrowUp, Check, Layers, RotateCcw, Sparkles, Undo2, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import type { FanRowState, Goal, GoalCandidates, GoalFanout } from '../../../shared/goal';
import { t } from '../i18n';
import { useEngine } from '../lib/engine';
import { groupVideos, videoHref, videoTitle } from '../lib/goals';
import { labelOf } from '../lib/projectAi';
import { AiPickChip } from './AiPick';
import { Thumb } from './kit';
import { emsg, errText } from './msg';
import { useUi } from './ui';

/** What the page asks the chat to open: one video's re-cut (``video`` null: which one? first). */
export interface RecutAsk {
  video: string | null;
  shot?: number | null;
  mode?: 'add' | 'replace' | 'swap';
}

interface Msg {
  id: number;
  me?: boolean;
  text: string;
  tone?: 'muted' | 'error';
}

let seq = 0;
/** each group's conversation while the app is open */
const KEPT = new Map<string, Msg[]>();

const FAN_TONE: Record<FanRowState, 'run' | 'you' | 'error' | 'done' | 'off'> = {
  waiting: 'off',
  asking: 'run',
  applying: 'run',
  rendering: 'run',
  proposed: 'you',
  done: 'done',
  nothing: 'off',
  failed: 'error',
  undone: 'off',
};

export function GoalChat({ g, onGoal, recut, setRecut }: { g: Goal; onGoal: (g: Goal) => void; recut: RecutAsk | null; setRecut: (r: RecutAsk | null) => void }) {
  const { client } = useEngine();
  const ui = useUi();
  const [msgs, setMsgsS] = useState<Msg[]>(() => KEPT.get(g.id) ?? []);
  const setMsgs = (f: (m: Msg[]) => Msg[]) =>
    setMsgsS((m) => {
      const n = f(m);
      KEPT.set(g.id, n);
      return n;
    });
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const log = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    log.current?.scrollTo({ top: 1e9, behavior: 'smooth' });
  }, [msgs.length, recut, g.fanouts?.length]);
  const made = groupVideos(g).filter((v) => v.state === 'made');
  const fill = g.fill && g.fill.need > 0 ? g.fill : null;
  const say = (m: Omit<Msg, 'id'>) => setMsgs((x) => [...x, { id: ++seq, ...m }]);

  const run = async (shown: string, fn: () => Promise<Goal | { intent: import('../../../shared/goal').GoalIntent; goal: Goal }>) => {
    if (!client || busy) return;
    say({ me: true, text: shown });
    setText('');
    setBusy(true);
    try {
      const r = await fn();
      const goal = 'goal' in r && 'intent' in r ? r.goal : (r as Goal);
      onGoal(goal);
      if ('intent' in r) {
        const it = r.intent;
        if (it.kind === 'more') say({ text: it.n ? t('ge.r.more', { n: it.n }) : t('ge.r.moreSome') });
        else if (it.kind === 'recut') {
          const v = it.video ? goal.videos.find((x) => x.id === it.video) : null;
          setRecut({ video: v ? v.id : null, shot: it.shot ?? null, mode: it.mode });
          say({ text: v ? t('ge.r.recut', { title: videoTitle(v) }) : t('ge.r.recutWhich') });
        } else if (it.kind === 'fanout') say({ text: t('ge.r.fanout', { n: goal.fanouts?.[goal.fanouts.length - 1]?.counts.total ?? made.length }) });
        else say({ text: t('ge.r.empty'), tone: 'muted' });
      } else if (goal.more?.state === 'planning') say({ text: t('ge.r.more', { n: goal.more.n }) });
      else if (goal.fanouts?.length) say({ text: t('ge.r.fanout', { n: goal.fanouts[goal.fanouts.length - 1].counts.total || made.length }) });
    } catch (e) {
      say({ text: errText(e), tone: 'error' });
    } finally {
      setBusy(false);
    }
  };
  const send = (words: string) => {
    if (!words.trim()) return;
    void run(words.trim(), () => client!.goalSay(g.id, words.trim()));
  };
  const chips: { key: string; label: string; go: () => void }[] = [
    { key: 'more3', label: t('ge.chip.more3'), go: () => void run(t('ge.chip.more3Say'), () => client!.goalMore(g.id, { n: 3 })) },
    ...(fill ? [{ key: 'fill', label: t('ge.chip.fill', { n: fill.target }), go: () => void run(t('ge.chip.fillSay', { n: fill.target }), () => client!.goalMore(g.id, { to: fill.target })) }] : []),
    { key: 'voice', label: t('ge.chip.voice'), go: () => void run(t('ge.chip.voiceSay'), () => client!.goalFanout(g.id, t('ge.chip.voiceSay'))) },
    {
      key: 'swap',
      label: t('ge.chip.swap'),
      go: () => {
        say({ me: true, text: t('ge.chip.swapSay') });
        say({ text: t('ge.r.recutWhich') });
        setRecut({ video: null, mode: 'swap' });
      },
    },
  ];
  const open = g.more && (g.more.state === 'planning' || g.more.state === 'ready');

  return (
    <section className="goalv-sec goalv-chat agent" data-testid="goal-chat">
      <div className="hd">
        <b style={{ whiteSpace: 'nowrap', flex: 'none' }}>
          <Sparkles className="ico" /> {t('ge.title')}
        </b>
        <AiPickChip value={g.ai ?? null} onChange={(v) => client && void client.setGoalAi(g.id, v).then((x) => (onGoal(x), ui.toast(t('tai.groupSwitched', { name: labelOf(v) }))))} testId="goal-chat-ai" title={t('tai.groupTip')} disabled={busy} />
        <span className="sp" />
      </div>
      <div className="alog goalv-chatlog" ref={log} data-testid="goal-chat-log">
        {!msgs.length && !g.more && !g.fanouts?.length && !recut && <div className="muted small">{t('ge.lead')}</div>}
        {msgs.map((m) => (
          <div key={m.id} className={`msg ${m.me ? 'me' : ''} ${m.tone === 'muted' ? 'muted' : ''}`} style={m.tone === 'error' ? { color: 'var(--danger)' } : undefined} data-testid={m.me ? 'goal-chat-me' : 'goal-chat-reply'}>
            {m.text}
          </div>
        ))}
        {g.more && <MoreLine g={g} onRetry={() => void run(t('ge.more.retry'), () => client!.goalMore(g.id, { n: g.more!.n, ...(g.more!.about ? { about: g.more!.about } : {}) }))} />}
        {(g.fanouts ?? []).map((f) => (
          <FanoutCard key={f.id} g={g} f={f} onGoal={onGoal} />
        ))}
        {recut && <RecutPanel g={g} ask={recut} onClose={() => setRecut(null)} onGoal={onGoal} onPick={(vid) => setRecut({ ...recut, video: vid })} />}
      </div>
      <div className="in">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t('ge.placeholder')}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              send(text);
            }
          }}
          disabled={!client}
          data-testid="goal-chat-input"
        />
        <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
          {chips.map((c) => (
            <button key={c.key} className="chip" onClick={c.go} disabled={busy || !client || (c.key !== 'swap' && c.key !== 'voice' && !!open) || ((c.key === 'voice' || c.key === 'swap') && !made.length)} data-testid="goal-chat-chip" data-chip={c.key}>
              {c.label}
            </button>
          ))}
          <span className="sp" />
          <button className="btn icon sm" onClick={() => send(text)} disabled={!text.trim() || busy || !client} aria-label={t('ge.send')} data-testid="goal-chat-send">
            <ArrowUp className="ico" />
          </button>
        </div>
      </div>
    </section>
  );
}

/** Her last ask for more videos, in one line (the new cards themselves are on the page). */
function MoreLine({ g, onRetry }: { g: Goal; onRetry: () => void }) {
  const m = g.more!;
  const n = m.ids?.length ?? 0;
  if (m.state === 'discarded') return null;
  return (
    <div className="msg col" data-testid="goal-more-line" data-state={m.state} style={{ gap: 6 }}>
      {m.state === 'planning' && (
        <span className="row" style={{ gap: 6 }}>
          <i className="dot run" />
          {t('ge.more.planning', { n: m.n })}
        </span>
      )}
      {m.state === 'ready' && (
        <span className="row" style={{ gap: 6 }}>
          <i className="dot you" />
          {t('ge.more.ready', { n })}
        </span>
      )}
      {m.state === 'made' && (
        <span className="row muted" style={{ gap: 6 }}>
          <Check className="ico" style={{ width: 12, height: 12 }} />
          {t('ge.more.made', { n })}
        </span>
      )}
      {m.state === 'empty' && <span className="muted">{t('ge.more.empty')}</span>}
      {m.state === 'failed' && (
        <>
          <span style={{ color: 'var(--danger)' }}>{t('ge.more.failed', { why: m.error || m.error_code || '' })}</span>
          <button className="btn sm" style={{ alignSelf: 'flex-start' }} onClick={onRetry} data-testid="goal-more-retry">
            <RotateCcw className="ico" />
            {t('ge.more.retry')}
          </button>
        </>
      )}
    </div>
  );
}

function scopeLabel(f: GoalFanout): string {
  const l = f.scope?.lang;
  return l === 'en' ? t('ge.fan.scopeEn') : l === 'zh' ? t('ge.fan.scopeZh') : t('ge.fan.scopeAll');
}

/** One change across the group: per video its state, what its AI changed, Undo (its own steps only). */
function FanoutCard({ g, f, onGoal }: { g: Goal; f: GoalFanout; onGoal: (g: Goal) => void }) {
  const { client } = useEngine();
  const ui = useUi();
  const act = async (action: 'apply' | 'undo', video?: string) => {
    if (!client) return;
    try {
      onGoal(await client.goalFanoutAct(g.id, f.id, action, video));
    } catch (e) {
      ui.toast(errText(e), { error: true });
    }
  };
  const c = f.counts;
  const tail = [c.nothing ? t('ge.fan.nothingN', { n: c.nothing }) : null, c.failed ? t('ge.fan.failedN', { n: c.failed }) : null, c.undone ? t('ge.fan.undoneN', { n: c.undone }) : null].filter(Boolean);
  return (
    <div className="change goalv-fan" data-testid="goal-fanout" data-state={f.state} data-fanout={f.id}>
      <div className="row">
        <b className="sp clamp1">{t('ge.fan.title', { prompt: f.prompt })}</b>
        <span className="faint small">{scopeLabel(f)}</span>
      </div>
      {f.videos.map((x) => {
        const v = g.videos.find((y) => y.id === x.video);
        const lines = x.rows.flatMap((r) => (r.describe ?? []).map((d) => emsg(d as never)).filter(Boolean));
        const held = x.rows.find((r) => r.hold);
        const err = x.rows.find((r) => r.state === 'failed' && r.error)?.error;
        return (
          <div key={x.video} className="goalv-fanrow" data-testid="goal-fan-video" data-video={x.video} data-state={x.state}>
            <span className="row" style={{ gap: 8 }}>
              <i className={`dot ${FAN_TONE[x.state]}`} />
              <b className="clamp1 sp">{v ? videoTitle(v) : (x.title ?? x.video)}</b>
              <span className="muted small">{t(`ge.fan.${x.state}` as never)}</span>
              {x.state === 'proposed' && (
                <button className="btn sm primary" onClick={() => void act('apply', x.video)} data-testid="goal-fan-apply">
                  {t('ge.fan.apply')}
                </button>
              )}
              {x.state === 'done' && f.state !== 'running' && (
                <button className="btn sm" onClick={() => void act('undo', x.video)} data-testid="goal-fan-undo">
                  <Undo2 className="ico" />
                  {t('ge.fan.undo')}
                </button>
              )}
              {v?.projects?.length ? (
                <a className="btn sm ghost" href={videoHref(g.id, v)}>
                  {t('goal.open')}
                </a>
              ) : null}
            </span>
            {[...new Set(lines)].slice(0, 3).map((l, i) => (
              <span key={i} className="muted small clamp1" data-testid="goal-fan-change">
                {l}
              </span>
            ))}
            {held && <span className="small goalv-warn">{t('ge.fan.held')}</span>}
            {err && x.state === 'failed' && <span className="small" style={{ color: 'var(--danger)' }}>{err}</span>}
          </div>
        );
      })}
      <div className="row">
        <span className="small muted sp" data-testid="goal-fan-summary">
          {[t('ge.fan.summary', { done: c.done, total: c.total }), ...tail].join(' · ')}
        </span>
        {c.proposed > 0 && f.state !== 'running' && (
          <button className="btn sm primary" onClick={() => void act('apply')} data-testid="goal-fan-apply-all">
            {t('ge.fan.applyAll', { n: c.proposed })}
          </button>
        )}
      </div>
    </div>
  );
}

/** One video's other shots: its shots now (click to leave one out) and the clips no video plays (click to add),
 * then 「Re-cut」 - or 「Let the AI pick」. Only this video and its versions are made again. */
function RecutPanel({ g, ask, onClose, onGoal, onPick }: { g: Goal; ask: RecutAsk; onClose: () => void; onGoal: (g: Goal) => void; onPick: (vid: string) => void }) {
  const { client } = useEngine();
  const ui = useUi();
  const made = groupVideos(g).filter((v) => v.state === 'made');
  const v = ask.video ? g.videos.find((x) => x.id === ask.video) : null;
  const [c, setC] = useState<GoalCandidates | null>(null);
  const [add, setAdd] = useState<string[]>([]);
  const [drop, setDrop] = useState<number[]>(ask.shot ? [ask.shot] : []);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setC(null);
    setAdd([]);
    setDrop(ask.shot ? [ask.shot] : []);
    if (!client || !ask.video) return;
    let alive = true;
    client
      .goalCandidates(g.id, ask.video)
      .then((x) => alive && setC(x))
      .catch((e) => alive && ui.toast(errText(e), { error: true }));
    return () => {
      alive = false;
    };
  }, [client, g.id, ask.video, ask.shot]); // eslint-disable-line react-hooks/exhaustive-deps
  const go = async (pick?: 'ai') => {
    if (!client || !v) return;
    setBusy(true);
    try {
      const x = await client.goalRecut(g.id, v.id, pick ? { pick, shots: drop } : { add, shots: drop });
      onGoal(x);
      ui.toast(t('ge.recut.started', { title: videoTitle(v) }));
      onClose();
    } catch (e) {
      ui.toast(errText(e), { error: true });
    } finally {
      setBusy(false);
    }
  };
  if (!v)
    return (
      <div className="change goalv-recut" data-testid="goal-recut" data-video="">
        <div className="row">
          <b className="sp">{t('ge.recut.which')}</b>
          <button className="btn icon sm ghost" onClick={onClose} aria-label={t('ge.recut.cancel')}>
            <X className="ico" />
          </button>
        </div>
        <div className="row" style={{ flexWrap: 'wrap', gap: 6 }}>
          {made.map((x) => (
            <button key={x.id} className="btn sm" onClick={() => onPick(x.id)} data-testid="goal-recut-which" data-video={x.id}>
              <Layers className="ico" />
              {videoTitle(x)}
            </button>
          ))}
        </div>
      </div>
    );
  const n = add.length + drop.length;
  return (
    <div className="change goalv-recut" data-testid="goal-recut" data-video={v.id}>
      <div className="row">
        <b className="sp clamp1">{t('ge.recut.title', { title: videoTitle(v) })}</b>
        <button className="btn icon sm ghost" onClick={onClose} aria-label={t('ge.recut.cancel')} data-testid="goal-recut-close">
          <X className="ico" />
        </button>
      </div>
      {!c ? (
        <span className="muted small">{t('ge.recut.loading')}</span>
      ) : (
        <>
          {c.shots.length > 0 && (
            <>
              <span className="faint small">{t('ge.recut.now')}</span>
              <div className="goalv-shots">
                {c.shots.map((s) => {
                  const out = drop.includes(s.i);
                  return (
                    <button key={s.i} className={`goalv-shot ${out ? 'out' : ''}`} onClick={() => setDrop((d) => (out ? d.filter((x) => x !== s.i) : [...d, s.i]))} title={s.name} data-testid="goal-recut-shot" data-shot={s.i} data-out={out ? '1' : undefined}>
                      <Thumb src={s.thumb ?? null} ratio="16/9" className="goalv-th" />
                      <span className="small">{t('ge.recut.shot', { n: s.i })}</span>
                      {out && <X className="ico goalv-shotx" />}
                    </button>
                  );
                })}
              </div>
            </>
          )}
          <span className="faint small" data-testid="goal-recut-free-n">
            {c.free.length ? t('ge.recut.free', { n: c.free.length }) : t('ge.recut.none')}
          </span>
          <div className="goalv-shots">
            {c.free.map((x) => {
              const on = add.includes(x.path);
              return (
                <button key={x.path} className={`goalv-shot ${on ? 'on' : ''}`} onClick={() => setAdd((a) => (on ? a.filter((p) => p !== x.path) : [...a, x.path]))} title={x.name} data-testid="goal-recut-clip" data-on={on ? '1' : undefined}>
                  <Thumb src={x.thumb ?? null} ratio="16/9" className="goalv-th" />
                  <span className="small clamp1">
                    {x.same ? t('ge.recut.same') : [x.place?.en, x.date].filter(Boolean).join(' · ') || x.name}
                    {x.dur ? ` · ${Math.round(x.dur)}s` : ''}
                  </span>
                  {on && <Check className="ico goalv-shotx" />}
                </button>
              );
            })}
          </div>
          <div className="row" style={{ gap: 8 }}>
            <button className="btn sm primary" disabled={busy || !n} onClick={() => void go()} data-testid="goal-recut-go">
              {t('ge.recut.go', { n })}
            </button>
            <button className="btn sm" disabled={busy || !c.free.length} onClick={() => void go('ai')} data-testid="goal-recut-ai">
              <Sparkles className="ico" />
              {t('ge.recut.ai')}
            </button>
            <span className="sp" />
            <button className="btn sm ghost" onClick={onClose}>
              {t('ge.recut.cancel')}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
