"""Import finished videos (and their footage) for second-pass editing (导入成片二次编辑).

A video made elsewhere - another Reelfold run, CapCut / 剪映, Final Cut, Premiere, a phone app - becomes a work folder
of its own that every second-pass tool works on (vstudio.project.outputs: clip chat edits, cuts, captions, music,
framing, covers, post copy, new platform / language versions). Footage that came with it is LINKED, never copied: its
shots are matched to the finished video by their frames (vstudio.shotmatch), so a re-cut can pull another take from
the footage and a new aspect can be rebuilt from the full source frame.

    from vstudio.project import imports as IM
    IM.classify(["out/", "raw/"])                  # what was dropped: finished videos vs footage, per clip
    r = IM.import_(["out/01-x"], sources=["raw/01"])   # -> {dir, clips [...], first}
    IM.match_shots(r["dir"])                               # shots -> .vstudio/shots/<version>.json
    IM.rewrite_copy(r["dir"], clip, platforms)             # post copy per platform, written again

    python -m vstudio.project import PATH... [--sources DIR]... [--title T] [--check] [--match] --json

Layout (``$VSTUDIO_HOME/projects/import-<stamp>-<slug>/``; the originals are never written - each finished video is
an APFS clone / copy, covers and post copy are copied, footage stays where it is):

    final/<clip>/<platform>.mp4, <platform>.cover.jpg, <platform>.post.md
    .vstudio/import.json   {version, at, inputs, title, clips [{id, title, versions [{file, platform, orientation,
                            aspect, w, h, duration, original, cover, post {title, body, tags}, post_original?}],
                            sources [abs]}], sources [abs]}
    .vstudio/work.json     the work record (``imported: {at, clips}``) - the desk lists it like every work folder
    .vstudio/shots/<slug>.json   shot match of one version (``match_shots``)

Classification (``classify``) is cheap (names, folders, siblings, container tags; one ffprobe per video): a video is
finished when it is named for a platform / an export (``youtube.mp4``, ``final``, ``成片``, CapCut / 剪映 exports), sits
in an output folder (out / final / export / delivery), has a cover or post copy next to it, or is a platform canvas
(1080x1920, 1920x1080, 1080x1440 ...) written by an editor; it is footage when it has a camera's name (DJI_0001,
IMG_1234, GX010001, C0001, PXL_...), a camera's tags, or is a camera format (4K / 10-bit / HEVC log) with no export
signs. Every verdict carries its reasons.
"""
import os
import re
import shutil
import subprocess
import sys
import time

from vstudio.batch.util import read_json, write_json
from ..oscompat import relpath as _relpath

VERSION = 1
VIDEO = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}
IMAGE = {".jpg", ".jpeg", ".png", ".webp"}
SKIP_DIRS = {".git", ".vstudio", "node_modules", "__pycache__", "state", "work", "cache", "renders", "tts", "frames",
             "stills"}
MAX_DEPTH = 4
MAX_FILES = 3000

# platform words in file names -> (platform id, orientation) - international first (registry order)
PLATFORM_WORDS = [
    (r"youtube[-_ ]?shorts|shorts", ("youtube-shorts", "vertical")),
    (r"youtube|\byt\b", ("youtube", "horizontal")),
    (r"tiktok|\btt\b", ("tiktok", "vertical")),
    (r"instagram|reels?\b|\big\b", ("instagram", "vertical")),
    (r"facebook|\bfb\b", ("facebook", "vertical")),
    (r"linkedin", ("linkedin", "horizontal")),
    (r"\bx\b|twitter", ("x", "horizontal")),
    (r"xiaohongshu|\bxhs\b|rednote|小红书", ("xiaohongshu", "vertical")),
    (r"douyin|抖音", ("douyin", "vertical")),
    (r"bilibili|b站|\bbili\b", ("bilibili", "horizontal")),
    (r"shipinhao|channels|视频号|wechat", ("wechat-channels", "vertical")),
    (r"kuaishou|快手", ("kuaishou", "vertical")),
    (r"weibo|微博", ("weibo", "horizontal")),
]
INTL_FIRST = ["youtube", "youtube-shorts", "tiktok", "instagram", "facebook", "linkedin", "x", "xiaohongshu", "douyin",
              "bilibili", "wechat-channels", "kuaishou", "weibo"]
FINAL_WORDS = re.compile(r"final|export|成片|导出|定稿|发布|master|render|_v\d+\b|\bv\d+$|capcut|剪映|premiere|"
                         r"davinci|resolve|fcp|final ?cut|imovie|edit(ed)?\b|cut\b|剪辑", re.I)
CAMERA_NAME = re.compile(r"^(DJI_\d|DJI\d|IMG_\d|MVI_\d|GX\d|GH\d|GOPR\d|GP\d|C\d{4}|PXL_\d|VID_\d{8}|VID\d|"
                         r"\d{8}_\d{6}|A\d{3}_C\d|CLIP\d|MAH\d|DSC_?\d|P\d{7}|insta360|LRV_|DJI_20\d{6})", re.I)
OUT_DIRS = {"out", "final", "finals", "export", "exports", "output", "outputs", "delivery", "deliver", "成片", "导出",
            "publish", "renders"}
SRC_DIRS = {"raw", "src", "source", "sources", "footage", "素材", "原片", "clips", "dcim", "media", "card"}
CANVASES = {(1080, 1920), (1920, 1080), (1080, 1440), (1440, 1080), (1080, 1350), (1080, 1080), (720, 1280),
            (1280, 720), (2160, 3840), (3840, 2160), (1242, 2208), (1440, 1920)}
CAMERA_TAGS = re.compile(r"DJI|GoPro|Apple iPhone|com\.apple\.quicktime\.(make|model)|Sony|Canon|Panasonic|"
                         r"Insta360|Ambarella|Blackmagic|Pixel", re.I)
EDITOR_TAGS = re.compile(r"Lavf|CapCut|Jianying|剪映|Premiere|Final Cut|com\.apple\.proapps|DaVinci|Resolve|iMovie|"
                         r"HandBrake|Adobe|VN Video|InShot|Reelfold", re.I)


class ImportError_(ValueError):
    def __init__(self, code, message, message_zh=None, **params):
        super().__init__(message)
        self.info = dict(ok=False, error=message, code=code, params=params, message=message,
                         message_zh=message_zh or message)


# --------------------------------------------------------------------------- reading what was dropped
def _walk(inputs):
    """-> [(abs path, the input it came from)] - symlinked files count once per real file, symlinked folders and
    the folders a tool keeps its working files in are skipped."""
    out, seen = [], set()
    for raw in inputs:
        p = os.path.abspath(os.path.expanduser(str(raw)))
        if os.path.isfile(p):
            if p not in seen:
                seen.add(p)
                out.append((p, p))
            continue
        if not os.path.isdir(p):
            continue
        base = p.rstrip(os.sep).count(os.sep)
        for d, dirs, files in os.walk(p):
            depth = d.rstrip(os.sep).count(os.sep) - base
            dirs[:] = sorted(x for x in dirs if not x.startswith((".", "_")) and x.lower() not in SKIP_DIRS
                             and depth < MAX_DEPTH and not os.path.islink(os.path.join(d, x)))
            for fn in sorted(files):
                if fn.startswith("."):
                    continue
                fp = os.path.join(d, fn)
                real = os.path.realpath(fp)
                if fp in seen or real in seen or not os.path.isfile(real):
                    continue
                seen.update((fp, real))
                out.append((fp, p))
                if len(out) >= MAX_FILES:
                    return out
    return out


def _probe(path):
    """One ffprobe: size, duration, codec, bit depth, format / stream tags (as one string)."""
    from vstudio import media
    try:
        r = media.run(["ffprobe", "-v", "error", "-show_entries",
                       "format=duration:format_tags:stream=codec_type,codec_name,width,height,pix_fmt,"
                       "color_transfer:stream_tags:stream_side_data=rotation", "-of", "json", path], capture=True)
        import json
        d = json.loads(r.stdout_text)
    except Exception:  # noqa: BLE001  (an unreadable file: nothing known)
        return {}
    v = next((s for s in d.get("streams") or [] if s.get("codec_type") == "video"), {}) or {}
    a = next((s for s in d.get("streams") or [] if s.get("codec_type") == "audio"), None)
    w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    rot = 0
    for sd in v.get("side_data_list") or []:
        if "rotation" in sd:
            rot = int(sd["rotation"])
    if abs(rot) % 180 == 90:
        w, h = h, w
    tags = " ".join(f"{k}={val}" for src in ((d.get("format") or {}).get("tags") or {}, v.get("tags") or {})
                    for k, val in src.items())
    return dict(w=w, h=h, duration=float((d.get("format") or {}).get("duration") or 0), vcodec=v.get("codec_name"),
                pix_fmt=v.get("pix_fmt") or "", transfer=v.get("color_transfer") or "", has_audio=a is not None,
                tags=tags)


def platform_of(name):
    """A file name -> (platform, orientation) or None."""
    n = os.path.splitext(os.path.basename(name))[0].lower().replace(".", " ")
    for rx, pf in PLATFORM_WORDS:
        if re.search(rx, n, re.I):
            return pf
    return None


def aspect_of(w, h):
    if not w or not h:
        return None
    r = w / h
    for name, v in (("9:16", 9 / 16), ("3:4", 3 / 4), ("4:5", 4 / 5), ("1:1", 1.0), ("4:3", 4 / 3), ("16:9", 16 / 9)):
        if abs(r - v) < 0.04:
            return name
    return f"{w}:{h}"


def _orientation(w, h):
    return "vertical" if h > w else "horizontal"


def video_role(path, info=None, siblings=()):
    """-> (role finished | raw, score, reasons [codes]). Positive score = finished."""
    info = info if info is not None else _probe(path)
    name = os.path.basename(path)
    stem = os.path.splitext(name)[0]
    folder = os.path.basename(os.path.dirname(path)).lower()
    parents = [x.lower() for x in os.path.dirname(os.path.abspath(path)).split(os.sep)[-3:]]
    score, why = 0, []
    if platform_of(name):
        score += 3
        why.append("platform-name")
    if FINAL_WORDS.search(stem):
        score += 2
        why.append("export-name")
    if any(p in OUT_DIRS for p in parents):
        score += 2
        why.append("output-folder")
    sib = {os.path.basename(s).lower() for s in siblings}
    if any(re.search(r"cover|封面|post|文案", s) for s in sib):
        score += 2
        why.append("cover-or-post-beside")
    if CAMERA_NAME.match(stem):
        score -= 4
        why.append("camera-name")
    if any(p in SRC_DIRS for p in parents) or folder.startswith("dji_"):
        score -= 1
        why.append("footage-folder")
    if os.path.islink(path):
        score -= 1
        why.append("linked-footage")
    tags = info.get("tags") or ""
    if EDITOR_TAGS.search(tags):
        score += 1
        why.append("editor-tags")
    if CAMERA_TAGS.search(tags) and not EDITOR_TAGS.search(tags):
        score -= 2
        why.append("camera-tags")
    w, h = info.get("w") or 0, info.get("h") or 0
    if (w, h) in CANVASES and (w, h) not in ((3840, 2160), (2160, 3840)) and info.get("has_audio"):
        score += 1
        why.append("platform-canvas")
    if "10" in (info.get("pix_fmt") or "") or (info.get("transfer") or "") in ("arib-std-b67", "smpte2084"):
        score -= 1
        why.append("camera-format")
    if not info.get("has_audio") and info.get("w"):
        score -= 1
        why.append("no-audio")
    return ("finished" if score > 0 else "raw"), score, why


def _post_sections(text):
    """A post.md with one section per platform (``## youtube`` + title line + body + #tags) -> {platform: post}."""
    out = {}
    parts = re.split(r"^##\s+", text or "", flags=re.M)
    for part in parts[1:]:
        head, _, rest = part.partition("\n")
        pf = platform_of(head.strip().split()[0] if head.strip() else "")
        if not pf:
            continue
        out[pf[0]] = parse_post(rest)
    return out


def parse_post(text):
    """Post copy text -> {title, body, tags} (a title line, the body, #tag lines / 标签：a，b lines)."""
    lines = [ln.rstrip() for ln in (text or "").strip().splitlines()]
    title, body, tags = "", [], []
    for ln in lines:
        s = ln.strip()
        if not title and s:
            m = re.match(r"^(?:\*\*)?(?:标题|title)(?:\*\*)?\s*[:：]\s*(.+)$", s, re.I)
            title = (m.group(1) if m else s).strip().lstrip("# ").strip()
            continue
        if s and re.fullmatch(r"(#\S+\s*)+", s):
            tags += [x.lstrip("#") for x in s.split()]
            continue
        m = re.match(r"^(?:标签|tags)\s*[:：]\s*(.+)$", s, re.I)
        if m:
            tags += [x.strip().lstrip("#") for x in re.split(r"[,，、\s]+", m.group(1)) if x.strip()]
            continue
        body.append(ln)
    return dict(title=title[:300], body="\n".join(body).strip()[:5000], tags=[t for t in tags if t][:30])


def _read(path, n=200000):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read(n)
    except OSError:
        return ""


def _clip_title(folder, posts):
    for pf in INTL_FIRST:
        if posts.get(pf, {}).get("title"):
            return posts[pf]["title"]
    for p in posts.values():
        if p.get("title"):
            return p["title"]
    return re.sub(r"^\d+[-_ ]+", "", os.path.basename(folder)).replace("-", " ").replace("_", " ").strip() or \
        os.path.basename(folder)


def _key_of(stem):
    """``A_title_9x16`` / ``ep1_youtube`` -> the clip key its versions share; a bare platform name -> ''."""
    s = re.sub(r"[_\-. ]?(\d{3,4}x\d{3,4}|9x16|16x9|3x4|4x3|1x1|4x5|vertical|horizontal|portrait|landscape)$", "",
               stem, flags=re.I)
    for rx, _pf in PLATFORM_WORDS:
        s = re.sub(rf"[_\-. ]?({rx})$", "", s, flags=re.I)
        s = re.sub(rf"^({rx})[_\-. ]?", "", s, flags=re.I)
    s = re.sub(r"[_\-. ]?(final|export|master|v\d+)$", "", s, flags=re.I)
    return s.strip("_-. ")


def classify(inputs, probe=None):
    """What was dropped -> {ok, verdict finished | raw | mixed | none, clips [{key, folder, title, versions [{file,
    platform, orientation, aspect, w, h, duration, cover, post, role, score, why}]}], sources [abs], files [{path,
    role, score, why}], counts {finished, raw, covers, posts}}. Nothing is written."""
    probe = probe or _probe
    files = _walk(inputs)
    by_dir = {}
    for p, _root in files:
        by_dir.setdefault(os.path.dirname(p), []).append(p)
    vids, rows = [], []
    for p, _root in files:
        if os.path.splitext(p)[1].lower() not in VIDEO:
            continue
        info = probe(p)
        role, score, why = video_role(p, info, by_dir.get(os.path.dirname(p), []))
        rows.append(dict(path=p, role=role, score=score, why=why))
        vids.append((p, info, role, score, why))
    finished = [v for v in vids if v[2] == "finished"]
    raw = [v for v in vids if v[2] == "raw"]
    clips = []
    groups = {}
    for p, info, role, score, why in finished:
        d = os.path.dirname(p)
        stem = os.path.splitext(os.path.basename(p))[0]
        k = _key_of(stem)
        groups.setdefault((d, k), []).append((p, info, score, why))
    # a folder whose videos are only platform names (youtube.mp4, xhs.mp4): one clip with versions
    for (d, k), vs in sorted(groups.items()):
        sibs = by_dir.get(d, [])
        post_all = {}
        for s_ in sibs:
            if os.path.basename(s_).lower() in ("post.md", "posts.md", "文案.md", "发布文案.md"):
                post_all.update(_post_sections(_read(s_)))
        versions = []
        for p, info, score, why in vs:
            stem = os.path.splitext(os.path.basename(p))[0]
            pf = platform_of(stem)
            w, h = info.get("w") or 0, info.get("h") or 0
            pfid, ori = (pf if pf else (None, _orientation(w, h)))
            cover = next((s_ for s_ in sibs if os.path.splitext(s_)[1].lower() in IMAGE and
                          re.match(rf"^{re.escape(stem)}[._ -]?(cover|封面)", os.path.basename(s_), re.I)), None)
            if not cover and len(vs) == 1:
                cover = next((s_ for s_ in sibs if os.path.splitext(s_)[1].lower() in IMAGE and
                              re.match(r"^(cover|封面)", os.path.basename(s_), re.I)), None)
            post = None
            pp = next((s_ for s_ in sibs if re.match(rf"^{re.escape(stem)}[._ -](post|文案)\.(md|txt)$",
                                                     os.path.basename(s_), re.I)), None)
            if pp:
                post = parse_post(_read(pp))
            elif pfid and pfid in post_all:
                post = post_all[pfid]
            elif len(vs) == 1 and not post_all:
                single = next((s_ for s_ in sibs if os.path.basename(s_).lower() in ("post.md", "post.txt",
                                                                                     "文案.md", "文案.txt")), None)
                if single:
                    post = parse_post(_read(single))
            versions.append(dict(file=p, platform=pfid, orientation=ori, aspect=aspect_of(w, h), w=w, h=h,
                                 duration=round(info.get("duration") or 0.0, 3), has_audio=bool(info.get("has_audio")),
                                 cover=cover, post=post, score=score, why=why))
        versions.sort(key=lambda v: (INTL_FIRST.index(v["platform"]) if v["platform"] in INTL_FIRST else 50,
                                     -(v["duration"] or 0)))
        posts = {v["platform"]: v["post"] for v in versions if v["post"] and v["platform"]}
        folder_named = not k
        title = _clip_title(d, posts) if folder_named or posts else k.replace("_", " ")
        key = _slug(os.path.basename(d) if folder_named else k) or "clip"
        clips.append(dict(key=key, folder=d, title=title, versions=versions))
    seen = {}
    for c in clips:                                  # unique keys (two folders named "final")
        n = seen.get(c["key"], 0)
        seen[c["key"]] = n + 1
        if n:
            c["key"] = f"{c['key']}-{n + 1}"
    covers = sum(1 for c in clips for v in c["versions"] if v["cover"])
    posts = sum(1 for c in clips for v in c["versions"] if v["post"])
    verdict = "none" if not vids else "finished" if finished and not raw else "raw" if not finished else "mixed"
    return dict(ok=True, verdict=verdict, clips=clips, sources=[v[0] for v in raw], files=rows,
                counts=dict(finished=len(finished), raw=len(raw), covers=covers, posts=posts, clips=len(clips)))


def _slug(s, n=40):
    s = re.sub(r"[^\w一-鿿]+", "-", str(s or "")).strip("-").lower()
    return s[:n].strip("-")


def pair_sources(clips, sources):
    """Footage -> the clips it belongs to: a clip folder and a footage folder sharing a number prefix (``01-x`` and
    ``01-y``) or a word pair; otherwise every clip gets all the footage (the shot match sorts it out)."""
    if not sources:
        return {c["key"]: [] for c in clips}
    if len(clips) == 1:
        return {clips[0]["key"]: list(sources)}
    byfolder = {}
    for s in sources:
        byfolder.setdefault(os.path.dirname(s), []).append(s)

    def num(name):
        m = re.match(r"^(\d{1,3})[-_ ]", os.path.basename(name))
        return int(m.group(1)) if m else None

    def words(name):
        return {w for w in re.split(r"[^a-z0-9一-鿿]+", os.path.basename(name).lower()) if len(w) > 2 and not w.isdigit()}

    out = {}
    for c in clips:
        cn, cw = num(c["folder"]), words(c["folder"]) | words(c["title"])
        hits = [s for f, ss in byfolder.items() if cn is not None and num(f) == cn for s in ss]
        if not hits:                            # no shared number: the folder sharing the most words (2 at least)
            best = max(byfolder, key=lambda f: len(cw & words(f)), default=None)
            if best is not None and len(cw & words(best)) >= 2:
                hits = list(byfolder[best])
        out[c["key"]] = hits or list(sources)
    return out


# --------------------------------------------------------------------------- import
def _clone(src, dst):
    """APFS clone (instant, no extra space, a separate file) when possible, else a copy. Never a hard link: the copy
    must not be the original."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    real = os.path.realpath(src)
    if sys.platform == "darwin":
        r = subprocess.run(["/bin/cp", "-c", real, dst], capture_output=True)
        if r.returncode == 0:
            return "clone"
    shutil.copy2(real, dst)
    return "copy"


def projects_root():
    from vstudio.batch.clients import home
    return os.path.join(home(), "projects")


def manifest_path(d):
    return os.path.join(d, ".vstudio", "import.json")


def manifest(d):
    m = read_json(manifest_path(d), None)
    return m if isinstance(m, dict) and m.get("clips") is not None else None


def import_(inputs, sources=None, title=None, dest=None, plan=None, on_event=None, register=True):
    """Finished videos (``inputs``; footage among them is linked as sources) + optional footage folders / files
    (``sources``) -> a new work folder. -> {ok, dir, title, clips [{id, title, versions, sources}], first {clip,
    file}, sources}. ``plan``: a ``classify`` answer to use as it is."""
    emit = on_event or (lambda ev: None)
    plan = plan or classify(list(inputs) + list(sources or []))
    clips = plan["clips"]
    if not clips:
        raise ImportError_("no-finished-video", "no finished video among the files (only footage: start a new "
                           "video from it instead)", "这些文件里没有成片（只有素材：请用它新建视频）",
                           files=len(plan["files"]))
    src_all = sorted(set(plan["sources"]))
    if sources:
        extra = classify(list(sources))
        src_all = sorted(set(src_all) | set(extra["sources"]) |
                         {v["file"] for c in extra["clips"] for v in c["versions"]} -
                         {v["file"] for c in clips for v in c["versions"]})
    src_all = [os.path.realpath(s) for s in src_all]
    pairs = pair_sources(clips, src_all)
    name = title or (clips[0]["title"] if len(clips) == 1 else
                     os.path.basename(os.path.commonpath([c["folder"] for c in clips])) or clips[0]["title"])
    stamp = time.strftime("%Y%m%d-%H%M%S")
    d = os.path.abspath(dest or os.path.join(projects_root(), f"import-{stamp}-{_slug(name, 30) or 'video'}"))
    if os.path.exists(d) and os.listdir(d):
        raise ImportError_("dest-exists", f"{d} is not empty", f"{d} 不是空文件夹", dir=d)
    os.makedirs(d, exist_ok=True)
    out_clips, outputs = [], []
    n_files = sum(len(c["versions"]) for c in clips)
    k = 0
    for c in clips:
        cid = c["key"]
        cdir = os.path.join(d, "final", cid)
        vers = []
        used = set()
        for v in c["versions"]:
            k += 1
            emit(dict(event="progress", stage="copy", file=os.path.basename(v["file"]), i=k, n=n_files))
            base = v["platform"] or _slug(os.path.splitext(os.path.basename(v["file"]))[0], 30) or "video"
            nm, j = base, 2
            while nm in used:
                nm, j = f"{base}-{j}", j + 1
            used.add(nm)
            ext = os.path.splitext(v["file"])[1].lower()
            dst = os.path.join(cdir, nm + ext)
            how = _clone(v["file"], dst)
            row = dict(file=_relpath(dst, d), platform=v["platform"], orientation=v["orientation"],
                       aspect=v["aspect"], w=v["w"], h=v["h"], duration=v["duration"], has_audio=v.get("has_audio"),
                       original=os.path.abspath(v["file"]), how=how, cover=None, post=None)
            if v.get("cover"):
                cext = os.path.splitext(v["cover"])[1].lower()
                cdst = os.path.join(cdir, f"{nm}.cover{cext}")
                _clone(v["cover"], cdst)
                row["cover"] = _relpath(cdst, d)
            if v.get("post"):
                row["post"] = dict(v["post"])
                _write_post(os.path.join(cdir, f"{nm}.post.md"), v["post"])
            vers.append(row)
            outputs.append(row["file"])
        out_clips.append(dict(id=cid, title=c["title"], folder=c["folder"], versions=vers,
                              sources=pairs.get(cid) or []))
    man = dict(version=VERSION, at=time.strftime("%Y-%m-%dT%H:%M:%S"), inputs=[os.path.abspath(os.path.expanduser(x))
                                                                                for x in inputs],
               title=name, clips=out_clips, sources=src_all)
    write_json(manifest_path(d), man)
    from . import works as W
    rec_path = W.record_path(d)
    write_json(rec_path, dict(kind="work", imported=dict(at=man["at"], clips=len(out_clips),
                                                         sources=len(src_all))))
    W.touch(d, title=name, outputs=outputs, sources=src_all, register=register)
    emit(dict(event="stage", stage="done", clips=len(out_clips)))
    first = out_clips[0]
    return dict(ok=True, dir=d, title=name, clips=out_clips, sources=src_all,
                first=dict(clip=first["id"], file=os.path.join(d, first["versions"][0]["file"])))


def _write_post(path, post):
    lines = [post.get("title") or "", ""]
    if post.get("body"):
        lines += [post["body"], ""]
    if post.get("tags"):
        lines.append(" ".join("#" + t for t in post["tags"]))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).strip() + "\n")


# --------------------------------------------------------------------------- per-output facts (the editor)
def version_of(d, rel):
    """The imported version behind a work-folder output (``final/<clip>/<platform>.mp4``) -> {clip, title,
    version, sources, shots_path} or None."""
    m = manifest(d)
    if not m:
        return None
    rel = rel.replace(os.sep, "/")
    for c in m["clips"]:
        for v in c["versions"]:
            if v["file"] == rel:
                return dict(clip=c["id"], title=c["title"], version=v, sources=c.get("sources") or [],
                            shots_path=shots_path(d, rel))
    return None


def shots_path(d, rel):
    return os.path.join(d, ".vstudio", "shots", re.sub(r"[^\w.-]+", "_", rel.replace("/", "__")) + ".json")


def shots(d, rel):
    m = read_json(shots_path(d, rel), None)
    return m if isinstance(m, dict) and m.get("shots") is not None else None


def match_shots(d, clip=None, versions="primary", on_event=None):
    """Match the shots of each clip's versions to its footage (vstudio.shotmatch) -> {ok, matched [{clip, file,
    shots, matched, coverage}]}. ``versions``: primary | all. A clip without footage is skipped."""
    from vstudio import shotmatch as SM
    emit = on_event or (lambda ev: None)
    m = manifest(d)
    if not m:
        raise ImportError_("not-imported", f"{d} was not made by an import", "这个文件夹不是导入的", dir=d)
    out = []
    for c in m["clips"]:
        if clip and c["id"] != clip:
            continue
        srcs = [s for s in c.get("sources") or [] if os.path.isfile(s)]
        if not srcs:
            continue
        vs = c["versions"][:1] if versions == "primary" else c["versions"]
        for v in vs:
            emit(dict(event="stage", stage="match", clip=c["id"], file=v["file"]))
            r = SM.match(os.path.join(d, v["file"]), srcs, on_event=lambda ev, c_=c: emit(dict(ev, clip=c_["id"])))
            r["file"] = v["file"]
            p = shots_path(d, v["file"])
            write_json(p, r)
            out.append(dict(clip=c["id"], file=v["file"], shots=len(r["shots"]),
                            matched=sum(1 for s in r["shots"] if s["match"]), coverage=r["coverage"], path=p))
    return dict(ok=True, matched=out)


# --------------------------------------------------------------------------- post copy, written again
def rewrite_copy(d, clip, platforms=None, transcript=None, provider="auto", complete=None):
    """Every version's post copy written again (vstudio.postcopy: the routed AI, else the rules), each platform in
    its language, from the clip's title, the copy it came with and what is said in it. The copy it came with is
    kept as ``post_original``. -> {ok, clip, posts {platform: {title, body, tags, lang}}, source ai | rules, notes}"""
    from vstudio import postcopy as PC
    m = manifest(d)
    if not m:
        raise ImportError_("not-imported", f"{d} was not made by an import", "这个文件夹不是导入的", dir=d)
    c = next((x for x in m["clips"] if x["id"] == clip), None)
    if not c:
        raise ImportError_("unknown-clip", f"no clip {clip!r}", f"没有片段 {clip!r}", clip=clip)
    pfs = [p for p in (platforms or [v["platform"] for v in c["versions"] if v["platform"]]) if p] or ["youtube"]
    said = (transcript or "").strip()
    before = " ".join(filter(None, [(v.get("post_original") or v.get("post") or {}).get("body") for v in c["versions"]]))
    # the old title goes in as words, not as her title (a title of hers is kept as it is; this is a rewrite)
    ctx = PC.context(request=" ".join(filter(None, [c["title"], said[:1500], before[:800]])), title=None,
                     duration=next((v["duration"] for v in c["versions"] if v.get("duration")), None))
    dr = PC.draft(ctx, pfs, provider=provider, complete=complete)
    per = dr.get("per_platform") or {}
    posts = {}
    for v in c["versions"]:
        pf = v["platform"] or pfs[0]
        p = per.get(pf) or per.get(PC.platform_key(pf))
        if not p:
            continue
        v.setdefault("post_original", v.get("post"))
        v["post"] = dict(title=p.get("title") or "", body=p.get("body") or "", tags=list(p.get("tags") or []))
        _write_post(os.path.join(d, os.path.dirname(v["file"]), os.path.splitext(os.path.basename(v["file"]))[0]
                                 + ".post.md"), v["post"])
        posts[pf] = dict(v["post"], lang=p.get("lang"))
    for pf in pfs:
        if pf not in posts and per.get(pf):
            posts[pf] = dict(per[pf])
    write_json(manifest_path(d), m)
    return dict(ok=True, clip=clip, posts=posts, source=dr.get("source"), notes=dr.get("notes") or [])
