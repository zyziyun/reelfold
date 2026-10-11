// ＋ New video (2026-10 review steps 6-7): Home's composer as one component - say it, drop files (anywhere on the
// window), pick the platforms, ⌘↵ - plus the other ways to start that used to live on their own pages: record
// yourself, a series / storyboard (Create), the sample. The request becomes a row of the Studio at once (planned and
// run on autopilot unless Settings says "Ask me first") and the box is free for the next one.
import { useEffect, useRef, useState } from 'react';
import { CalendarDays, ChevronDown, ChevronRight, Clapperboard, Circle, File as FileIcon, FileText, Folder, FolderOpen, Image as ImageIcon, MoreHorizontal, Music, Paperclip, Play, Plus, Sparkles, Video, X } from 'lucide-react';
import { WEEK_WORDS } from '../../../shared/weekPlan';
import { homePlatforms } from '../../../shared/platforms';
import { IS_LITE } from '../../../shared/edition';
import { getLang, t } from '../i18n';
import { CHIP_LIMIT, groupAttachments, removeItem, summarize, type AttachItem } from '../lib/attachments';
import { useEngine } from '../lib/engine';
import { useHistory } from '../lib/history';
import { keyHint } from '../lib/keys';
import { href } from '../lib/router';
import { useCreateEnabled } from '../create/flag';
import { useWeekPlan } from '../weekplan/useWeekPlan';
import { PlatformChip } from './Home';
import { errText } from './msg';
import { useUi } from './ui';

const base = (p: string) => p.replace(/[\\/]+$/, '').split(/[\\/]/).pop() ?? p;
const isImage = (p: string) => /\.(jpe?g|png|webp)$/i.test(p);

function kindIcon(p: string) {
  const e = p.toLowerCase().split('.').pop() ?? '';
  if (['mp4', 'mov', 'm4v', 'mkv', 'webm'].includes(e)) return <Video className="ico" />;
  if (['jpg', 'jpeg', 'png', 'webp', 'heic'].includes(e)) return <ImageIcon className="ico" />;
  if (['wav', 'mp3', 'm4a', 'aac', 'flac'].includes(e)) return <Music className="ico" />;
  if (['pdf', 'docx', 'pptx', 'md', 'txt', 'srt', 'vtt'].includes(e)) return <FileText className="ico" />;
  if (!p.includes('.') || p.endsWith('/')) return <Folder className="ico" />;
  return <FileIcon className="ico" />;
}

const DRAFT = 'v4.composer';

export function Composer({ compact = false, autoFocus = false, onSent, onClose }: { compact?: boolean; autoFocus?: boolean; onSent?: (id: string) => void; onClose?: () => void }) {
  const { client } = useEngine();
  const ui = useUi();
  const { reload: reloadHist } = useHistory();
  const createOn = useCreateEnabled();
  const wp = useWeekPlan();
  const draft = (() => {
    try {
      return JSON.parse(sessionStorage.getItem(DRAFT) ?? '{}') as { prompt?: string; files?: string[] };
    } catch {
      return {};
    }
  })();
  const [prompt, setPrompt] = useState(draft.prompt ?? '');
  const [files, setFiles] = useState<string[]>(draft.files ?? []);
  const [platforms, setPlatforms] = useState<string[] | null>(null);
  const [savedPf, setSavedPf] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);
  const ta = useRef<HTMLTextAreaElement | null>(null);
  useEffect(() => sessionStorage.setItem(DRAFT, JSON.stringify({ prompt, files })), [prompt, files]);
  useEffect(() => {
    // her choice, else her accounts' platforms, else the international pair - international first (as on Home)
    void window.desk.getSettings().then((s) => {
      setPlatforms(homePlatforms(s.defaultPlatforms, Object.keys(s.accounts ?? {}).filter((k) => (s.accounts[k] ?? []).length)));
      setSavedPf(s.defaultPlatforms ?? null);
    });
  }, []);
  useEffect(() => {
    if (autoFocus) window.setTimeout(() => ta.current?.focus(), 30);
  }, [autoFocus]);
  // files dropped anywhere on the window land here
  useEffect(() => {
    if (ui.dropped.length) setFiles((f) => [...new Set([...f, ...ui.takeDropped()])]);
  }, [ui.dropped, ui]);

  const ready = !!(prompt.trim() || files.length);
  const send = async (p: { prompt: string; files: string[]; sample?: boolean }) => {
    if (!client || busy || !(p.prompt || p.files.length)) return;
    if (!p.sample && p.files.length && WEEK_WORDS.test(p.prompt)) {
      if (await wp.actions.start(p.files, p.prompt)) {
        setPrompt('');
        setFiles([]);
      }
      return;
    }
    setBusy(true);
    try {
      const auto = (await window.desk.getSettings()).autopilot !== false;
      const r = await client.startIntake(p.prompt, p.files, platforms ?? undefined, getLang(), {
        mode: auto ? 'autopilot' : 'ask',
        sampleName: p.sample ? t('sample.projectName') : undefined,
        // a fixed intent (the sample): no planning call
        recipe: p.sample ? 'talkinghead' : undefined,
      });
      sessionStorage.removeItem(DRAFT);
      setPrompt('');
      setFiles([]);
      reloadHist();
      const name = p.prompt.trim() ? p.prompt.trim().slice(0, 40) + (p.prompt.trim().length > 40 ? '…' : '') : base(p.files[0] ?? '');
      ui.toast(t(auto ? 'home.sent' : 'home.sentAsk', { name }));
      onSent?.(r.id);
    } catch (e) {
      ui.toast(errText(e), { error: true });
    } finally {
      setBusy(false);
    }
  };
  const submit = () => void send({ prompt: prompt.trim(), files });
  const sample = async () => {
    if (!client) return;
    try {
      const s = await client.sample();
      if (!s.available || !s.path) return ui.toast(t('sample.unavailable'), { error: true });
      await send({ prompt: t('sample.prompt'), files: [s.path], sample: true });
    } catch (e) {
      ui.toast((e as Error).message, { error: true });
    }
  };
  const addFiles = async (kind: 'files' | 'folder') => {
    const got = kind === 'files' ? await window.desk.openFiles('any') : [await window.desk.openFolder()].filter((x): x is string => !!x);
    if (got.length) setFiles((f) => [...new Set([...f, ...got])]);
  };
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setOver(false);
    const paths = [...e.dataTransfer.files].map((f) => window.desk.pathForFile?.(f) ?? '').filter(Boolean);
    if (paths.length) setFiles((f) => [...new Set([...f, ...paths])]);
    if (paths.length && IS_LITE) void window.desk.grantAccess?.(paths).catch(() => undefined);
  };
  // the chip is this request's choice; her default changes only through "Make this my default"
  const savePlatforms = (v: string[]) => setPlatforms(v);
  const makeDefault = (v: string[]) => {
    if (!v.length) return;
    setSavedPf(v);
    void window.desk.setSettings({ defaultPlatforms: v.slice(0, 8) }).catch(() => undefined);
  };
  const more = (e: React.MouseEvent) => {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    ui.menu({ clientX: r.left, clientY: r.bottom + 6 }, [
      { label: t('home.addFiles'), icon: <Plus className="ico" />, run: () => addFiles('files'), testId: 'add-files' },
      { label: t('home.addFolder'), icon: <FolderOpen className="ico" />, run: () => addFiles('folder'), testId: 'add-folder' },
      ...(files.length ? [{ label: t('wp.make'), icon: <CalendarDays className="ico" />, run: () => void wp.actions.start(files, prompt.trim()).then((ok) => ok && (setPrompt(''), setFiles([]))), testId: 'composer-week' }] : []),
      ...(createOn ? [{ label: t('nav.create'), icon: <Clapperboard className="ico" />, run: () => (location.hash = href({ name: 'create', path: [] })), testId: 'composer-create' }] : []),
      { label: t('sample.try'), icon: <Play className="ico" />, run: () => void sample(), testId: 'composer-sample' },
    ]);
  };
  return (
    <div
      className={`ux-composer ${compact ? 'compact' : ''} ${over ? 'over' : ''} ${prompt ? 'typing' : ''}`}
      data-own-drop
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
      data-testid="composer"
    >
      <textarea
        ref={ta}
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder={t('home.placeholderDrop')}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            submit();
          }
          if (e.key === 'Escape' && onClose) {
            e.stopPropagation();
            onClose();
          }
        }}
        rows={2}
        data-testid="composer-input"
      />
      {files.length > 0 && <AttachedFiles files={files} onChange={setFiles} />}
      <div className="foot">
        <button className="btn icon ux-attach" onClick={() => void addFiles('files')} aria-label={t('home.attach')} data-tip={t('home.attachTip')} data-testid="composer-attach">
          <Paperclip className="ico" />
        </button>
        {createOn && (
          <a className="btn ghost sm ux-rec" href={href({ name: 'create', path: ['record'] })} data-tip={t('st.record')} data-testid="composer-record">
            <Circle className="ico rec" />
            {compact ? null : t('st.record')}
          </a>
        )}
        <PlatformChip value={platforms} onChange={savePlatforms} saved={savedPf} onMakeDefault={makeDefault} />
        <button className="btn ghost icon sm" onClick={more} aria-label={t('st.more')} data-tip={t('st.more')} data-testid="composer-more">
          <MoreHorizontal className="ico" />
        </button>
        <span className="sp" />
        <span className="ux-kbdhint" aria-hidden>
          {keyHint('⌘↵')}
        </span>
        <button className={`btn ux-make ${ready ? 'primary' : ''}`} disabled={busy || !ready} onClick={submit} data-testid="make-plan">
          <Sparkles className="ico" />
          {t('home.submitAuto')}
        </button>
      </div>
    </div>
  );
}

/** a dropped folder's chip says how many files it holds */
function FolderCount({ path }: { path: string }) {
  const [n, setN] = useState<number | null>(null);
  useEffect(() => {
    let alive = true;
    void window.desk
      .countFiles?.(path)
      .then((x) => alive && setN(x))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [path]);
  return n == null ? null : (
    <span className="pair" data-testid="composer-folder-count">
      {t('cf.files', { n })}
    </span>
  );
}

/** one attached item: a video and its same-named .srt are one chip (removing it removes both) */
function FileChip({ item, onRemove }: { item: AttachItem; onRemove: () => void }) {
  return (
    <span className="file" title={item.paths.join('\n')} data-testid="composer-file" data-kind={item.kind}>
      <span className="ic">{isImage(item.path) ? <img src={window.desk.mediaUrl(item.path)} alt="" loading="lazy" /> : kindIcon(item.path)}</span>
      <span className="clamp1">{item.name}</span>
      {item.sidecar && <span className="pair">{t('cf.plusSrt')}</span>}
      {item.kind === 'folder' && <FolderCount path={item.path} />}
      <button className="x" onClick={onRemove} aria-label={t('cf.removeOne', { name: item.name })} data-testid="composer-file-remove">
        <X className="ico" />
      </button>
    </span>
  );
}

/** a few files: their chips; many (a drone card): one plain line that opens into a scrollable list */
function AttachedFiles({ files, onChange }: { files: string[]; onChange: (f: string[]) => void }) {
  const [open, setOpen] = useState(false);
  const items = groupAttachments(files);
  const chips = (
    <>
      {items.map((it) => (
        <FileChip key={it.path} item={it} onRemove={() => onChange(removeItem(files, it))} />
      ))}
    </>
  );
  if (items.length <= CHIP_LIMIT) {
    return (
      <div className="files ux-files" data-testid="composer-files">
        {chips}
      </div>
    );
  }
  const s = summarize(files, items);
  const parts = [
    t('cf.files', { n: s.files }),
    s.videos ? t('cf.videos', { n: s.videos }) + (s.withSubs ? ` (${t('cf.withSubs', { n: s.withSubs })})` : '') : '',
    s.photos ? t('cf.photos', { n: s.photos }) : '',
    s.audio ? t('cf.audio', { n: s.audio }) : '',
    s.docs ? t('cf.docs', { n: s.docs }) : '',
    s.subs ? t('cf.subs', { n: s.subs }) : '',
    s.folders ? t('cf.folders', { n: s.folders }) : '',
    s.other ? t('cf.other', { n: s.other }) : '',
  ].filter(Boolean);
  return (
    <div className={`ux-files many ${open ? 'open' : ''}`} data-testid="composer-files">
      <div className="ux-files-sum">
        <button className="ux-files-toggle" onClick={() => setOpen((o) => !o)} aria-expanded={open} data-tip={t(open ? 'cf.hide' : 'cf.show')} data-testid="composer-files-toggle">
          {open ? <ChevronDown className="ico" /> : <ChevronRight className="ico" />}
          <span className="lines">
            {s.dir && (
              <span className="dir">
                <Folder className="ico" />
                <span className="clamp1">{s.dir}</span>
              </span>
            )}
            <span className="tx" data-testid="composer-files-summary">
              {parts.join(' · ')}
            </span>
          </span>
        </button>
        <button className="ux-files-clear" onClick={() => onChange([])} data-testid="composer-files-clear">
          {t('cf.removeAll')}
        </button>
      </div>
      {open && (
        <div className="files ux-files-list" data-testid="composer-files-list">
          {chips}
        </div>
      )}
    </div>
  );
}
