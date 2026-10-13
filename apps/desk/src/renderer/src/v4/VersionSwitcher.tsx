// The clip page's Versions (2026-10-13, her "how do I see the video each platform will get - the sizes differ?" and
// "show the versions of every language"): one switcher of the video's versions - YouTube 16:9, Shorts · TikTok 9:16,
// and, for a goal video made in two languages, its 中文 sibling's 小红书 3:4 / B站 16:9 - grouped by language. A click
// plays that file in the big player at once (its shape, burned captions, watermark, cover): selecting never renders.
// Under the row: what the playing version is for (the platforms that post it, its post copy), Show in Finder, Export.
// A size this clip has not got is a separate, labelled "Make the 3:4 version" (rendered in the background).
import { ExternalLink, FolderOpen, Loader2, Play, Plus, Upload, X } from 'lucide-react';
import type { ClipFile, EditOp, OutputDoc } from '../../../shared/v04';
import { t, type MessageKey } from '../i18n';
import type { LangVersion } from '../lib/langVersions';
import { langName } from '../lib/langVersions';
import { clipHref } from '../lib/nav';
import { filePlatforms, versionFor } from '../lib/versions';
import { ASPECT_TARGET, VERSIONS, versionsFor } from './ClipInfo';
import { platformName } from './Home';
import { PlatformIcon } from './PlatformIcon';

const RATIO = /^\d+:\d+$/;

/** another language's version playing: its project, clip and file */
export interface OtherPick {
  v: LangVersion;
  file: ClipFile;
}

export function VersionSwitcher({
  doc,
  files,
  playing,
  platforms,
  onPlay,
  onExport,
  edit,
  lang = null,
  others = [],
  other = null,
  onPlayOther,
}: {
  doc: OutputDoc;
  /** what the player can play (an edit's fresh renders first, then the originals) */
  files: ClipFile[];
  /** the aspect playing now (this clip's) */
  playing: string | undefined;
  /** the platforms she posts this clip to (scheduled, else picked) */
  platforms: string[];
  onPlay: (aspect: string) => void;
  onExport: () => void;
  edit: (ops: EditOp[], undoToast?: boolean) => Promise<boolean>;
  /** this clip's language and its siblings' (a goal video made in several languages) */
  lang?: string | null;
  others?: LangVersion[];
  /** a sibling's version playing instead of this clip's */
  other?: OtherPick | null;
  onPlayOther?: (o: OtherPick) => void;
}) {
  const own = new Set(doc.files.map((f) => f.aspect));
  // the engine keeps an export by its platform target (3:4 -> xiaohongshu:vertical)
  const added = new Set(doc.exports.flatMap((e) => [e.target, ...Object.entries(ASPECT_TARGET).filter(([, x]) => x === e.target).map(([a]) => a)]));
  const flat = doc.mode === 'flattened';
  // the shapes of the platforms it is made for (a goal video's English cut: YouTube's 16:9), plus what it has
  const shapes = versionsFor(doc.targets);
  const sizes = [...new Set<string>([...VERSIONS.filter((v) => shapes.includes(v) || added.has(v)), ...files.map((f) => f.aspect)])];
  const name = (v: string) => ((VERSIONS as readonly string[]).includes(v) ? t(`ci.v.${v}` as MessageKey) : RATIO.test(v) ? v : t('c.original'));
  const cur = other ? null : (files.find((f) => f.aspect === playing) ?? null);
  // each platform posts one version (the publisher's pick); this one's platforms
  // nothing picked to post yet: the platforms the version was made for (a photo story's 3:4 is 小红书's)
  const picked = cur ? platforms.filter((pf) => versionFor(pf, files)?.aspect === cur.aspect) : [];
  const posts = picked.length || !cur ? picked : filePlatforms(cur);
  const remove = (v: string) => void edit([{ op: 'export_remove', target: v } as EditOp], true);
  const grouped = others.length > 0;
  return (
    <div className="vsw" data-testid="ci-versions">
      <div className="vsw-row" role="radiogroup" aria-label={t('ci.vPick')} data-testid="ci-versions-mine" data-lang={lang ?? ''}>
        {grouped && <span className="vsw-lang">{lang ? langName(lang) : t('ci.vThis')}</span>}
        {sizes.map((v) => {
          const f = files.find((x) => x.aspect === v);
          const removable = !own.has(v) && added.has(v);
          if (f) {
            const on = cur?.aspect === v;
            return (
              <span key={v} className={`vsw-it ${on ? 'on' : ''}`}>
                <button role="radio" aria-checked={on} className="vsw-b" onClick={() => onPlay(v)} title={t('ci.vPick')} data-testid={`ci-version-${v}`} data-made="1">
                  <Play className="ico" />
                  {name(v)}
                </button>
                {removable && (
                  <button className="vsw-x" onClick={() => remove(v)} aria-label={t('ci.vRemove')} data-tip={t('ci.vRemove')} data-testid={`ci-version-remove-${v}`}>
                    <X className="ico" />
                  </button>
                )}
              </span>
            );
          }
          if (added.has(v))
            return (
              <span key={v} className="vsw-it making">
                <span className="vsw-b" data-testid={`ci-version-${v}`} data-made="0">
                  <Loader2 className="ico spin" />
                  {t('ci.vMaking', { v: name(v) })}
                </span>
                <button className="vsw-x" onClick={() => remove(v)} aria-label={t('ci.vRemove')} data-tip={t('ci.vRemove')} data-testid={`ci-version-remove-${v}`}>
                  <X className="ico" />
                </button>
              </span>
            );
          // not made: making it is its own, labelled action (a background render), never a selection
          return (
            <button
              key={v}
              className="vsw-b vsw-add"
              disabled={doc.caps.export === false}
              onClick={() => void edit([{ op: 'export_add', target: v, layout: flat ? 'band' : 'auto' } as EditOp], true)}
              data-testid={`ci-version-${v}`}
              data-made="0"
            >
              <Plus className="ico" />
              {t('ci.vAdd', { v: name(v) })}
            </button>
          );
        })}
      </div>
      {others.map((o) => (
        <div key={o.item} className="vsw-row" role="radiogroup" aria-label={langName(o.lang)} data-testid="ci-versions-other" data-lang={o.lang}>
          <span className="vsw-lang">{langName(o.lang)}</span>
          {o.clip.files.map((f) => {
            const on = other?.v.item === o.item && other.file.path === f.path;
            const pf = f.platform ? f.platform.split(':')[0] : null;
            return (
              <span key={f.path} className={`vsw-it ${on ? 'on' : ''}`}>
                <button role="radio" aria-checked={on} className="vsw-b" onClick={() => onPlayOther?.({ v: o, file: f })} data-testid={`ci-version-${o.lang}-${f.aspect}`} data-made="1">
                  <Play className="ico" />
                  {[pf ? platformName(pf) : null, RATIO.test(f.aspect) ? f.aspect : null].filter(Boolean).join(' ') || t('c.original')}
                </button>
              </span>
            );
          })}
          <a className="vsw-open" href={clipHref(o.item, o.clip.id)} data-testid="ci-version-open">
            <ExternalLink className="ico" />
            {t('ci.vOpen')}
          </a>
        </div>
      ))}
      {cur && (
        <div className="vsw-d" data-testid="ci-version-detail" data-aspect={cur.aspect} data-lang={lang ?? ''}>
          <span className="muted">{t('ci.vPostsTo')}</span>
          {posts.length ? (
            posts.map((pf) => (
              <span key={pf} className="vsw-pf" data-testid="ci-version-pf" data-pf={pf}>
                <PlatformIcon id={pf} size={13} />
                {platformName(pf)}
              </span>
            ))
          ) : (
            <span className="faint">{t('ci.vPostsNone')}</span>
          )}
          <span className="sp" />
          <button className="btn ghost sm" onClick={() => void window.desk.showItem(cur.path)} data-testid="ci-version-reveal">
            <FolderOpen className="ico" />
            {t('ci.vReveal')}
          </button>
          <button className="btn ghost sm" onClick={onExport} data-testid="ci-version-export">
            <Upload className="ico" />
            {t('ci.vExport')}
          </button>
        </div>
      )}
      {other && <OtherDetail o={other} />}
    </div>
  );
}

/** a sibling's version playing: its language, the platform it is made for, its post copy, its folder */
function OtherDetail({ o }: { o: OtherPick }) {
  const pf = o.file.platform ? o.file.platform.split(':')[0] : null;
  const post = (pf && o.v.clip.posts?.[pf]) || o.v.clip.post;
  return (
    <div className="vsw-d vsw-other" data-testid="ci-version-detail" data-aspect={o.file.aspect} data-lang={o.v.lang}>
      <span className="muted">{t('ci.vPostsTo')}</span>
      {pf ? (
        <span className="vsw-pf" data-testid="ci-version-pf" data-pf={pf}>
          <PlatformIcon id={pf} size={13} />
          {platformName(pf)}
        </span>
      ) : null}
      <span className="sp" />
      <button className="btn ghost sm" onClick={() => void window.desk.showItem(o.file.path)} data-testid="ci-version-reveal">
        <FolderOpen className="ico" />
        {t('ci.vReveal')}
      </button>
      {post && (
        <div className="vsw-post" lang={o.v.lang === 'zh' ? 'zh-CN' : o.v.lang} data-testid="ci-version-post">
          {post.title && <b className="clamp1">{post.title}</b>}
          {post.body && <p className="clamp2">{post.body}</p>}
        </div>
      )}
    </div>
  );
}
