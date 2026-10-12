"""Home's suggestion chips from her own signals only (GET /api/home/suggestions): never a canned idea.

  * ``recurring``  - a request she has sent more than once (same words, spacing and case aside), newest first;
  * ``recordings`` - a recording that landed in one of her watched folders in the last few days and is not in any
                     project or request yet (a file directly in the folder or one level below; project folders and
                     Reelfold's own stores are skipped).

-> {recurring: [{prompt, n, at}], recordings: [{path, name, folder, at, size}]}
"""
import os
import re
import time

MEDIA = (".mp4", ".mov", ".m4v", ".mkv", ".webm", ".m4a", ".wav", ".mp3", ".aac", ".flac")
FRESH_S = 3 * 86400
MAX_RECURRING = 3
MAX_RECORDINGS = 3
MAX_SCAN = 400          # directory entries looked at per watched folder (a huge folder stays quick)


def _norm(p):
    return re.sub(r"\s+", " ", (p or "").strip().lower())


def recurring(jobs):
    """Requests sent at least twice: [{prompt (the newest wording), n, at}], the most repeated first."""
    seen = {}
    for j in jobs:
        p = j.get("prompt")
        if not isinstance(p, str) or not p.strip():
            continue
        k = _norm(p)
        at = j.get("created") or j.get("started") or 0
        cur = seen.get(k)
        if cur is None:
            seen[k] = dict(prompt=p.strip(), n=1, at=at)
        else:
            cur["n"] += 1
            if at >= cur["at"]:
                cur["at"], cur["prompt"] = at, p.strip()
    out = [x for x in seen.values() if x["n"] >= 2]
    out.sort(key=lambda x: (-x["n"], -(x["at"] or 0)))
    return out[:MAX_RECURRING]


def _yaml_paths(path):
    """Every absolute path a project.yaml names as an input (items[].inputs, inputs)."""
    from .history import _project_yaml        # parsed once per change of the file (200+ projects on each Home look)
    d = _project_yaml(os.path.dirname(path))
    if not isinstance(d, dict):
        return []
    out = []

    def take(v):
        if isinstance(v, str) and os.path.isabs(v):
            out.append(v)
        elif isinstance(v, list):
            for x in v:
                take(x)
        elif isinstance(v, dict):
            for x in v.values():
                take(x)
    take(d.get("inputs"))
    for it in d.get("items") or []:
        if isinstance(it, dict):
            take(it.get("inputs"))
    return out


def used_paths(jobs, project_dirs):
    """Real paths already in her work: every request's inputs and every project's inputs."""
    used = set()
    for j in jobs:
        for p in j.get("inputs") or []:
            if isinstance(p, str):
                used.add(os.path.realpath(p))
    for d in project_dirs:
        for p in _yaml_paths(os.path.join(d, "project.yaml")):
            used.add(os.path.realpath(p))
    return used


def _inside(path, folders):
    return any(path == f or path.startswith(f.rstrip(os.sep) + os.sep) for f in folders)


def new_recordings(watch, used, project_dirs, now=None):
    """Fresh recordings in the watched folders that no project / request uses yet, newest first."""
    now = time.time() if now is None else now
    skip = {os.path.realpath(d) for d in project_dirs}
    used_dirs = {p for p in used if os.path.isdir(p)}
    found = []
    for w in watch:
        root = os.path.realpath(os.path.expanduser(w))
        if not os.path.isdir(root):
            continue
        todo, n = [(root, 0)], 0
        while todo:
            d, level = todo.pop()
            if d in skip or os.path.exists(os.path.join(d, "project.yaml")) or os.path.exists(os.path.join(d, "batch.db")):
                continue
            try:
                names = sorted(os.listdir(d))
            except OSError:
                continue
            for name in names:
                n += 1
                if n > MAX_SCAN:
                    break
                if name.startswith("."):
                    continue
                p = os.path.join(d, name)
                if os.path.isdir(p) and not os.path.islink(p):
                    if level < 1:
                        todo.append((p, level + 1))
                    continue
                if not name.lower().endswith(MEDIA):
                    continue
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                if now - st.st_mtime > FRESH_S or st.st_size < 1024:
                    continue
                rp = os.path.realpath(p)
                if rp in used or _inside(rp, used_dirs):
                    continue
                found.append(dict(path=p, name=name, folder=os.path.basename(root) or root, at=st.st_mtime,
                                  size=st.st_size))
    found.sort(key=lambda x: -x["at"])
    return found[:MAX_RECORDINGS]


def suggestions(history, intake, now=None):
    jobs = [j for j in list(intake.jobs.values()) if not j.get("discarded")]
    try:
        items = history.list()["items"]
    except Exception:  # noqa: BLE001  (no history yet: nothing to leave out)
        items = []
    dirs = [i["dir"] for i in items if i.get("dir")]
    used = used_paths(jobs, [i["dir"] for i in items if i.get("kind") == "project" and i.get("dir")])
    return dict(recurring=recurring(jobs), recordings=new_recordings(history.watch(), used, dirs, now))
