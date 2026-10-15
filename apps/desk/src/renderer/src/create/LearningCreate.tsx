import { useCallback, useEffect, useRef, useState } from 'react';
import { BookOpen, Paperclip } from 'lucide-react';
import type { LearningCredit, LearningSource, LearningWorkspace } from '../../../shared/learning';
import { t, fmtClock } from '../i18n';
import { useEngine } from '../lib/engine';
import { selHref } from '../lib/nav';
import { getLang } from '../i18n';
import { useRouteQuery } from '../lib/router';
import { useUi } from '../v4/ui';
import { media } from '../v4/kit';
import { errText } from '../v4/msg';
import { SourcePlayer } from './learning/SourcePlayer';
import { CameraCapture } from './learning/CameraCapture';
import { VoiceNote } from './learning/VoiceNote';
import './learning/learning.css';
import { youtubeSource } from './learning/source';

/** Human-led creation: watch, stop, think, speak, collect, arrange; AI is never started by opening a workspace. */
export function LearningCreate() {
  const { client } = useEngine();
  const ui = useUi();
  const query = useRouteQuery();
  const [idea, setIdea] = useState('');
  const [files, setFiles] = useState<string[]>([]);
  const [doc, setDoc] = useState<LearningWorkspace | null>(null);
  const [recent, setRecent] = useState<{ id: string; title: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [source, setSource] = useState('');
  const [dropOver, setDropOver] = useState(false);
  const [time, setTime] = useState(0);
  const [timeKnown, setTimeKnown] = useState(false);
  const [pause, setPause] = useState(0);
  const [seek, setSeek] = useState<number | null>(null);
  const [mark, setMark] = useState<number | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [editingNote, setEditingNote] = useState<string | null>(null);
  const [thought, setThought] = useState('');
  const [kind, setKind] = useState<'thought' | 'quote'>('thought');
  const [link, setLink] = useState('');
  const [voiceAudio, setVoiceAudio] = useState<string | null>(null);
  const [pageVoice, setPageVoice] = useState('');
  const [latestTake, setLatestTake] = useState<string | null>(null);
  const [creditDrafts, setCreditDrafts] = useState<Record<string, LearningCredit>>({});
  const [creditOpen, setCreditOpen] = useState(false);
  const creditPanel = useRef<HTMLDetailsElement | null>(null);
  const [post, setPost] = useState('');
  const anchor = useRef<{ source: string | null; at: number | null } | null>(null);
  const onTime = useCallback((n: number) => { setTime(n); setTimeKnown(true); }, []);
  useEffect(() => {
    if (!client) return;
    let active = true;
    // A workspace owns its unsaved thought and material position. Never carry them into another one.
    setDoc(null); setSource(''); setTime(0); setTimeKnown(false); setMark(null); setSeek(null);
    setThought(''); setEditingNote(null); setVoiceAudio(null); setPicked([]); setPageVoice(''); setLatestTake(null); setCreditDrafts({}); setCreditOpen(false); setPost('');
    anchor.current = null;
    if (query.id) void client.learningWorkspace(query.id).then((d) => { if (active) { setDoc(d); setPost(d.post ?? ''); } }).catch((e) => ui.toast(errText(e), { error: true }));
    else { setDoc(null); void client.learningWorkspaces().then((r) => { if (active) setRecent(r.workspaces); }).catch(() => undefined); }
    return () => { active = false; };
  }, [client, query.id, ui]);
  useEffect(() => {
    if (!doc || source) return;
    const first = Object.keys(doc.sources)[0] ?? Object.keys(doc.readings ?? {})[0] ?? doc.links[0] ?? '';
    setSource(first); setTime(youtubeSource(first)?.start ?? 0);
  }, [doc, source]);
  const act = async (fn: () => Promise<void>) => {
    if (busy) return;
    setBusy(true);
    try { await fn(); } catch (e) { ui.toast(errText(e), { error: true }); } finally { setBusy(false); }
  };
  const change = async (data: Record<string, unknown>) => {
    if (client && doc) setDoc(await client.updateLearning(doc.id, data));
  };
  const pick = () => void act(async () => {
    const xs = await window.desk.openFiles('any');
    if (!xs.length) return;
    if (doc) await change({ action: 'files', files: xs });
    else setFiles((old) => [...new Set([...old, ...xs])]);
  });
  if (!doc) return <div className="cr cr-home" data-testid="learning-create">
    <div className="tag"><BookOpen className="ico" /> {t('learning.creation')}</div>
    <h1 className="hello">{t('learning.title')}</h1><p className="muted">{t('learning.humanFlow')}</p>
    <div className="cr-cmp" style={{ padding: 24, display: 'grid', gap: 16 }}>
      <label className="col" style={{ gap: 8 }}>{t('learning.idea')}<textarea value={idea} onChange={(e) => setIdea(e.target.value)} placeholder={t('learning.ideaHint')} data-testid="learning-idea" /></label>
      <button className="btn" disabled={busy} onClick={pick} data-testid="learning-sources"><Paperclip className="ico" />{t('learning.sources')}</button>
      {files.map((p) => <button className="btn ghost sm" key={p} onClick={() => setFiles((xs) => xs.filter((x) => x !== p))}>{p.split(/[\\/]/).pop()} ×</button>)}
      <button className="btn primary lg" disabled={busy || !idea.trim()} onClick={() => void act(async () => {
        if (!client) return;
        const made = await client.createLearning({ idea: idea.trim(), thoughts: '', files });
        setSource(''); setDoc(made); location.hash = `#/create/learning?id=${made.id}`;
      })} data-testid="learning-start">{t('learning.openWorkspace')}</button>
    </div>
    {!!recent.length && <div className="col" style={{ gap: 10, marginTop: 24 }}><h3>{t('learning.resume')}</h3>{recent.map((r) => <a className="btn ghost" key={r.id} href={`#/create/learning?id=${r.id}`}>{r.title}</a>)}</div>}
  </div>;
  const current = doc.sources[source];
  const reading = doc.readings?.[source];
  const takes = Object.values(doc.sources).filter((s) => s.role === 'commentary');
  const sourceName = (s: LearningSource) => s.role === 'commentary' ? `${t('learning.myTake')} ${takes.findIndex((x) => x.id === s.id) + 1} · ${fmtClock(s.duration ?? 0)}` : s.path.split(/[\\/]/).pop();
  const freshTake = latestTake ? doc.sources[latestTake] : undefined;
  const hasThoughts = doc.notes.some((n) => n.kind === 'thought');
  const missingCredit = doc.blocks.map((b) => doc.sources[b.source]).find((s) => s && s.role !== 'commentary' && ['title', 'creator', 'locator'].some((key) => !doc.credits[s.id]?.[key as keyof LearningCredit]?.trim()));
  const hasVoice = doc.blocks.some((b) => doc.sources[b.source]?.role === 'commentary' || (b.voice && doc.sources[b.voice]?.role === 'commentary'));
  const credit = creditDrafts[source] ?? doc.credits[source] ?? { title: current?.path.split(/[\\/]/).pop() ?? '', creator: '', locator: '' };
  const saveThought = () => void act(async () => {
    const pos = anchor.current ?? { source: source || null, at: source && !reading && !current?.image && timeKnown ? time : null };
    await change(editingNote ? { action: 'revise-note', note: editingNote, text: thought } : { action: 'note', text: thought, kind, ...pos, ...(voiceAudio ? { voice_audio: voiceAudio } : {}) });
    setThought(''); setEditingNote(null); setVoiceAudio(null); anchor.current = null;
  });
  const select = (value: string) => { setSource(value); setCreditOpen(false); setTime(youtubeSource(value)?.start ?? 0); setTimeKnown(false); setMark(null); setSeek(null); };
  return <div className="cr learning-workspace" data-testid="learning-workspace" onDragOver={(e) => { if (e.dataTransfer.types.includes('Files')) { e.preventDefault(); e.stopPropagation(); setDropOver(true); } }} onDragLeave={() => setDropOver(false)} onDrop={(e) => {
        e.preventDefault(); e.stopPropagation(); setDropOver(false);
        const paths = [...e.dataTransfer.files].map((file) => window.desk.pathForFile(file)).filter(Boolean);
        if (!paths.length) return;
        void act(async () => {
          const access = await window.desk.grantAccess?.(paths);
          if (access?.needed && !access.granted) return;
          if (!client) return;
          const saved = await client.updateLearning(doc.id, { action: 'files', files: paths });
          const added = Object.keys(saved.sources).find((id) => !doc.sources[id]) ?? Object.keys(saved.readings ?? {}).find((id) => !doc.readings?.[id]);
          setDoc(saved); if (added) select(added);
        });
      }}>
    <div className="row" style={{ justifyContent: 'space-between' }}><div><div className="tag">{t('learning.creation')}</div><h1>{doc.title}</h1></div><a className="btn ghost" href="#/create/learning">{t('learning.allWorkspaces')}</a></div>
    <p className="muted">{t('learning.humanFlow')}</p>
    <div className="learning-grid">
      <section className={`learning-panel ${dropOver ? 'learning-drop-over' : ''}`} data-testid="learning-material-panel">
        <h2>{t('learning.materials')}</h2>
        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
          <select value={source} onChange={(e) => select(e.target.value)} aria-label={t('learning.materials')} data-testid="learning-source-select"><option value="">{t('learning.pickSource')}</option>{Object.values(doc.sources).map((s) => <option value={s.id} key={s.id}>{sourceName(s)}</option>)} {Object.values(doc.readings ?? {}).map((r) => <option value={r.id} key={r.id}>{r.path.split(/[\\/]/).pop()}</option>)}{doc.links.map((u) => <option value={u} key={u}>{youtubeSource(u) ? `${t('learning.youtubePlayer')} · ${fmtClock(youtubeSource(u)!.start)}` : u}</option>)}</select>
          <button className="btn sm" disabled={busy} onClick={pick}>{t('learning.sources')}</button>
        </div>
        <details open={!source} className="learning-extra"><summary>{t('learning.addLink')}</summary><div className="row" style={{ gap: 8, margin: '12px 0' }}><input type="url" value={link} onChange={(e) => setLink(e.target.value)} placeholder={t('learning.linkHint')} aria-label={t('learning.linkHint')} data-testid="learning-link" /><button className="btn sm" disabled={busy || !link.trim()} onClick={() => void act(async () => { await change({ action: 'link', url: link.trim() }); select(link.trim()); setLink(''); })}>{t('learning.addLink')}</button></div></details>
        {dropOver && <p className="small">{t('learning.dropMaterial')}</p>}
        <SourcePlayer source={current} reading={reading} browserTime={timeKnown ? time : undefined} link={!current && !reading ? source : undefined} onTime={onTime} seek={seek} pause={pause} />
        {!reading && <div className="row" style={{ gap: 8, flexWrap: 'wrap', marginTop: 12 }}>
          <span className="small">{fmtClock(time)}</span><details><summary data-testid="learning-time-edit">{t('learning.timeEdit')}</summary><label className="small">{t('learning.sourceTime')} <input type="number" min={0} step={0.1} value={Math.round(time * 10) / 10} onChange={(e) => { setTime(Number(e.target.value)); setTimeKnown(true); }} style={{ width: 90 }} data-testid="learning-source-time" /></label></details>
          {current && !current.image && <details className="learning-extra"><summary data-testid="learning-excerpt-tools">{t('learning.choosePassage')}</summary><p className="small muted">{t('learning.passageHint')}</p><div className="row" style={{ gap: 8, flexWrap: 'wrap' }}><button className="btn sm" onClick={() => setMark(time)} data-testid="learning-mark-start">{mark === null ? t('learning.markStart') : fmtClock(mark)}</button><button className="btn sm" disabled={busy || mark === null || time <= mark} onClick={() => void act(async () => { await change({ action: 'block', block: { source, start: mark, end: time, point: thought.trim() || doc.title } }); setMark(null); })} data-testid="learning-keep-range">{t('learning.addPassage')}</button></div></details>}
          {current?.role === 'commentary' && <button className="btn sm" disabled={busy} onClick={() => void act(() => change({ action: 'block', block: { source, start: 0, end: current.duration, point: t('learning.myTake') } }))} data-testid="learning-use-take">{t('learning.useWholeTake')}</button>}
        </div>}
        {!current && youtubeSource(source) && !timeKnown && <p className="small muted">{t('learning.timeNotKnown')}</p>}
        {current?.image && <div className="row" style={{ gap: 8, marginTop: 12 }}>
          <select value={pageVoice} onChange={(e) => setPageVoice(e.target.value)} aria-label={t('learning.pageVoice')}><option value="">{t('learning.pageVoice')}</option>{Object.values(doc.sources).filter((s) => s.role === 'commentary').map((s) => <option key={s.id} value={s.id}>{sourceName(s)}</option>)}</select>
          <button className="btn sm" disabled={busy || !pageVoice} onClick={() => void act(() => change({ action: 'block', block: { source, start: 0, end: doc.sources[pageVoice]?.duration, voice: pageVoice, voice_start: 0, point: thought.trim() || doc.title } }))}>{t('learning.addPage')}</button>
        </div>}
        {current && current.role !== 'commentary' && <details ref={creditPanel} open={creditOpen} onToggle={(e) => setCreditOpen(e.currentTarget.open)} style={{ marginTop: 12 }}><summary>{t('learning.sourceCredit')}</summary>{(['title', 'creator', 'locator'] as const).map((key) => <label className="col" key={key}>{t(`learning.credit.${key}`)}<input value={credit[key]} onChange={(e) => setCreditDrafts((old) => ({ ...old, [source]: { ...credit, [key]: e.target.value } }))} /></label>)}<button className="btn sm" onClick={() => void act(async () => { await change({ action: 'credit', source, credit }); setCreditOpen(false); })}>{t('learning.saveCredit')}</button></details>}

      </section>
      <section className="learning-panel">
        <h2>{t('learning.thinking')}</h2><p className="muted small">{t('learning.dictationHint')}</p>
        <div className="row" style={{ gap: 8 }}><button className={`btn sm ${kind === 'thought' ? 'primary' : ''}`} onClick={() => setKind('thought')}>{t('learning.myThought')}</button><button className={`btn sm ${kind === 'quote' ? 'primary' : ''}`} onClick={() => setKind('quote')}>{t('learning.sourceQuote')}</button></div>
        <textarea value={thought} onFocus={() => { setPause((n) => n + 1); anchor.current ??= { source: source || null, at: source && !reading && !current?.image && timeKnown ? time : null }; }} onChange={(e) => setThought(e.target.value)} placeholder={t('learning.thoughtsHint')} style={{ width: '100%', minHeight: 140, margin: '12px 0' }} data-testid="learning-thought" />
        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}><VoiceNote id={doc.id} disabled={busy} onStart={() => { setPause((n) => n + 1); anchor.current = { source: source || null, at: source && !reading && !current?.image && timeKnown ? time : null }; }} onText={(text, audio) => { setThought((old) => old ? old + '\n' + text : text); setVoiceAudio(audio); }} /><button className="btn primary" disabled={busy || !thought.trim()} onClick={saveThought} data-testid="learning-save-thought">{t('learning.saveThought')}</button>{editingNote && <button className="btn ghost" onClick={() => { setEditingNote(null); setThought(''); anchor.current = null; }}>{t('learning.newThought')}</button>}</div>
        <CameraCapture id={doc.id} onSaved={(d) => {
          setDoc(d);
          const latest = Object.values(d.sources).filter((s) => s.role === 'commentary').at(-1);
          setLatestTake(latest?.id ?? null);
          if (current?.image && latest) setPageVoice(latest.id);
        }} script={doc.script} />
        {freshTake && <div className="ux-opt learning-fresh-take" data-testid="learning-fresh-take">
          <div className="row" style={{ gap: 12, justifyContent: 'space-between', flexWrap: 'wrap' }}><span>{t('learning.justRecorded')} · {fmtClock(freshTake.duration ?? 0)}</span>
            <button className="btn" disabled={busy || doc.blocks.some((b) => b.source === freshTake.id && b.start === 0 && b.end === freshTake.duration)} onClick={() => void act(() => change({ action: 'block', block: { source: freshTake.id, start: 0, end: freshTake.duration, point: t('learning.myTake') } }))} data-testid="learning-add-recorded-take">{doc.blocks.some((b) => b.source === freshTake.id && b.start === 0 && b.end === freshTake.duration) ? t('learning.takeInVideo') : t('learning.addMyTake')}</button>
          </div>
          <details><summary>{t('learning.watchTake')}</summary><video src={media(freshTake.path)} controls playsInline style={{ width: '100%', maxHeight: 220 }} /></details>
        </div>}
        <div className="col" style={{ gap: 10, marginTop: 16 }} data-testid="learning-notes">
          {doc.notes.map((n) => <article key={n.id} className="ux-opt">
            <div className="learning-notehead">
              <small>{n.kind === 'thought' ? t('learning.myThought') : t('learning.sourceQuote')} {n.at !== null && <button className="btn ghost sm" onClick={() => { if (n.source) select(n.source); setSeek(n.at); }}>{fmtClock(n.at)}</button>}{n.at === null && n.source && <button className="btn ghost sm" onClick={() => { if (n.source) select(n.source); }}>{t('learning.backToSource')}</button>}</small>
              <button className="btn ghost sm" onClick={() => { setThought(n.text); setKind(n.kind); setEditingNote(n.id); anchor.current = { source: n.source, at: n.at }; }}>{t('learning.reviseThought')}</button>
            </div>
            <p style={{ whiteSpace: 'pre-wrap' }}>{n.text}</p>
            {n.voice_audio && <audio src={media(n.voice_audio)} controls style={{ maxWidth: '100%' }} />}
          </article>)}
        </div>
      </section>
    </div>
    {(hasThoughts || doc.blocks.length > 0 || takes.length > 0) && <section className="learning-panel" style={{ marginTop: 20 }}><h2>{t('learning.finish')}</h2>{doc.blocks.length > 0 && <p className="muted small">{t('learning.draftHint')}</p>}
      <div className="col" style={{ gap: 8 }}>{doc.blocks.map((b, i) => <div className="ux-opt row" key={b.id} style={{ gap: 12 }} data-testid="learning-block"><span style={{ flex: 1 }}>{i + 1}. {doc.sources[b.source]?.role === 'commentary' ? t('learning.myTake') : t('learning.sourceQuote')} · {fmtClock(b.start)}–{fmtClock(b.end)} · {b.point}</span>{([-1, 1] as const).map((delta) => <button key={delta} className="btn ghost sm" disabled={busy || (delta < 0 ? i === 0 : i === doc.blocks.length - 1)} aria-label={t(delta < 0 ? 'learning.up' : 'learning.down')} onClick={() => void act(() => change({ action: 'move', block: b.id, delta }))}>{delta < 0 ? '↑' : '↓'}</button>)}<button className="btn ghost sm" disabled={busy} onClick={() => void act(() => change({ action: 'remove', block: b.id }))}>{t('learning.removeFromDraft')}</button></div>)}</div>
      {doc.blocks.length > 0 && !hasVoice && <p className="small muted">{t('learning.needMyVoice')}</p>}
      {missingCredit && <div className="row" style={{ gap: 12, flexWrap: 'wrap', marginTop: 12 }}><p className="small muted">{t('learning.needCredit')}</p><button className="btn sm" data-testid="learning-fill-credit" onClick={() => { select(missingCredit.id); setCreditOpen(true); requestAnimationFrame(() => creditPanel.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })); }}>{t('learning.fillCredit')}</button></div>}
      <div className="row" style={{ gap: 12, marginTop: 16 }}>{doc.blocks.length > 0 && <button className="btn primary" disabled={busy || !hasVoice || !!missingCredit} onClick={() => void act(async () => { if (client) { const result = await client.editLearning(doc.id); location.hash = selHref(result.id); } })} data-testid="learning-make-demo">{t('learning.makeDemo')}</button>}{hasThoughts && <button className={`btn ${doc.blocks.length ? '' : 'primary'}`} onClick={() => setPost(doc.notes.filter((n) => n.kind === 'thought').map((n) => n.text).join('\n\n'))} data-testid="learning-post">{t('learning.assemblePost')}</button>}</div>
      {hasThoughts && <details className="learning-extra"><summary data-testid="learning-tools">{t('learning.optionalTools')}</summary><p className="small muted">{t('learning.selectThoughts')}</p><div className="col" style={{ gap: 10 }}>{doc.notes.filter((n) => n.kind === 'thought').map((n) => <label className="small learning-note-tool" key={n.id}><input type="checkbox" checked={picked.includes(n.id)} onChange={(e) => setPicked((ids) => e.target.checked ? [...ids, n.id] : ids.filter((x) => x !== n.id))} aria-label={t('learning.useForDemo')} /><span>{n.text}</span></label>)}</div><button className="btn" disabled={busy || !picked.length} onClick={() => void act(async () => {
        if (!client) return;
        const thoughts = doc.notes.filter((n) => picked.includes(n.id) && n.kind === 'thought').map((n) => n.text).join('\n\n');
        if (thoughts.length > 1600) throw new Error(t('learning.demoTooLong'));
        const r = await client.startIntake(t('learning.demoRequest', { thoughts }), [], ['youtube'], getLang(), { mode: 'ask', recipe: 'explainer' });
        await change({ action: 'tool', job: r.id });
        location.hash = selHref(r.id);
      })} data-testid="learning-ai-demo">{t('learning.aiDemo')}</button></details>}
      {doc.tool_jobs?.map((job) => <a key={job.id} className="btn ghost sm" href={selHref(job.id)}>{t('learning.openToolDemo')}</a>)}
      {!!post && <div className="col" style={{ gap: 8, marginTop: 12 }}><textarea value={post} onChange={(e) => setPost(e.target.value)} aria-label={t('learning.postDraft')} style={{ minHeight: 160 }} /><button className="btn" disabled={busy} onClick={() => void act(() => change({ action: 'post', text: post }))}>{t('learning.savePost')}</button><button className="btn" onClick={() => void window.desk.copyText(post)}>{t('learning.copyPost')}</button></div>}
    </section>}
  </div>;
}
