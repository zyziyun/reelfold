"""Delete (「删除」): what Reelfold made goes - a project, a batch (a group of videos), an import, a work folder, one
made video, a request - and her footage never does.

  plan(sel)            what would go, per thing picked: the Reelfold-made paths (``targets``), their file count and
                       size, the recordings / footage it points at (``keep``: they stay), other files of hers in the
                       folder (``other``: they stay), or why it cannot go (``reason``: running | nothing-made |
                       unsafe | not-found). ``sig`` signs exactly the targets she was shown.
  stage(sel, sig)      Move to Trash, step 1: the things leave every list at once (pending) and the desk's main process
                       is told which paths to move to the macOS Trash / Windows Recycle Bin - after the Undo toast is
                       gone (``undo`` brings them back, nothing moved). ``commit(id, trashed, failed)``: step 2, the
                       paths now in the Trash -> their notes go (see ``_forget``); anything the Trash refused comes back.
  hard(sel, sig)       Delete permanently: the targets are removed from disk at once, then their notes go.

``sel`` = {dirs: [project / batch / work folders], clips: [{item, clip}], requests: [request ids]}.

What counts as Reelfold's own: a folder the app made (under ``$VSTUDIO_HOME/projects``) is all its own except the
footage it points at; in a folder of hers (a batch or work folder in a watched folder) only the names the engine
writes (``MADE``: batch.db, jobs/, state/, final/, exports/, review/, delivery/, cache/, .vstudio/ ...). A folder
whose entries are all made goes as a whole; otherwise only its made entries go and the rest stays. Nothing that is,
or holds, a path the project / batch / import names as its input is ever a target; every target lies inside the
thing's own folder, at least three levels deep, never the home folder, a top folder or the Reelfold home.

One video: its job folder (``jobs/<id>``, ``state/jobs/<id>``), its item folder (``items/<id>``), its export folder
(``final/<id>``) and its exported files / cover / post copy inside the folder; the folder's ``.vstudio/removed.json``
remembers the video is gone (the run store still lists the job), so no list shows it again.

The notes that go with a deleted thing (``_forget``): the archive / name / client notes and the desk list row
(``History.forget``), its posts not posted yet on the calendar (posted ones are her history), her own clip titles,
its videos in a goal (dropped: ``deleted``), and a request's record (``Intake.delete``).
"""
import hashlib
import json
import os
import shutil
import threading
import time
import uuid

from .common import need, read_json, write_json

MADE = {
    "batch.db", "batch.db-wal", "batch.db-shm", "batch.yaml", "segments.yaml", "SEGMENTS.md", "RED_TRIAGE.md",
    "V02_FIELD_TEST.md", "jobs", "review", "review-links", "delivery", "package", "cache", "state", ".vstudio",
    "exports", "export", "final", "out", "output", "outputs", "renders", "work", "items", "REPORT.md", "PICKS.md",
    "NOTES.md", "project.yaml", "timeline.yaml", "timeline.json", "timeline.auto.yaml", "titles.json",
    "manifest.json", "masters.json", "schedule.csv", "post.md", "run.lock", "status.json", "desk-pilot.json",
    "desk-pilot.log", "intake.json", ".DS_Store",
}
SOURCE_KEYS = ("inputs", "input", "sources", "source", "footage", "recordings", "video", "audio", "media")
MAX_SEL = 200
STALE_S = 120                    # a pending Trash older than this (the app quit before its toast was gone): moved now


def _abs_strings(v, out):
    if isinstance(v, str):
        if os.path.isabs(v) and "\0" not in v and len(v) < 4096:
            out.append(v)
    elif isinstance(v, dict):
        for x in v.values():
            _abs_strings(x, out)
    elif isinstance(v, list):
        for x in v:
            _abs_strings(x, out)
    return out


def _under_keys(v, out):
    """Absolute paths under an inputs / sources / footage key, at any depth (``clips[].sources`` of an import)."""
    if isinstance(v, dict):
        for k, x in v.items():
            if k in SOURCE_KEYS:
                _abs_strings(x, out)
            else:
                _under_keys(x, out)
    elif isinstance(v, list):
        for x in v:
            _under_keys(x, out)
    return out


def folder_sources(d):
    """Every path the folder's project / batch / import names as its input: her footage and recordings."""
    out = []
    from .history import _project_sources
    if os.path.isfile(os.path.join(d, "project.yaml")):
        out += _project_sources(d)
    for store in (d, os.path.join(d, "state")):
        db = os.path.join(store, "batch.db")
        if not os.path.isfile(db):
            continue
        try:
            from .common import read_db
            with read_db(db) as con:
                for (v,) in con.execute("SELECT v FROM meta WHERE k = 'spec'"):
                    _under_keys(json.loads(v or "{}"), out)
                for (p,) in con.execute("SELECT params FROM jobs"):
                    try:
                        doc = json.loads(p or "{}")
                    except ValueError:
                        continue
                    _under_keys(doc, out)
                    if isinstance(doc, dict):          # a job's own source file / folder
                        for k in ("src", "file", "path"):
                            if isinstance(doc.get(k), str) and os.path.isabs(doc[k]):
                                out.append(doc[k])
        except Exception:  # noqa: BLE001  (an unreadable store: the folder's own names still decide)
            pass
    for f in ("batch.yaml", "segments.yaml"):
        p = os.path.join(d, f)
        if os.path.isfile(p):
            try:
                import yaml
                with open(p, encoding="utf-8") as fh:
                    _under_keys(yaml.safe_load(fh) or {}, out)
            except Exception:  # noqa: BLE001
                pass
    for f in ("import.json", "work.json"):
        _under_keys(read_json(os.path.join(d, ".vstudio", f), None) or {}, out)
    return [p for p in dict.fromkeys(os.path.realpath(x) for x in out) if os.path.exists(p)]


def _inside(p, root):
    return p == root or p.startswith(root.rstrip(os.sep) + os.sep)


def _real(p):
    """A link is its own path (removing it never touches what it points at); anything else its real path."""
    return os.path.abspath(p) if os.path.islink(p) else os.path.realpath(p)


def _size(paths):
    n, size = 0, 0
    for t in paths:
        if os.path.islink(t) or os.path.isfile(t):
            n += 1
            try:
                size += os.lstat(t).st_size
            except OSError:
                pass
            continue
        for dp, _dn, fn in os.walk(t):
            for f in fn:
                n += 1
                try:
                    size += os.lstat(os.path.join(dp, f)).st_size
                except OSError:
                    pass
            if n > 200000:
                return n, size
    return n, size


def _minimal(paths):
    """Drop paths inside another one of the list (the folder goes, its files with it)."""
    out = []
    for p in sorted(dict.fromkeys(paths), key=len):
        if not any(_inside(p, q) for q in out):
            out.append(p)
    return out


def removed_clips(d):
    """The videos deleted from a folder (``.vstudio/removed.json``) - its run store still lists their jobs."""
    doc = read_json(os.path.join(d, ".vstudio", "removed.json"), None) or {}
    return set(doc.get("clips") or []) if isinstance(doc, dict) else set()


# videos waiting in a pending Trash (Undo still possible): {real folder: {clip ids}} - the lists leave them out
PENDING_CLIPS = {}


def hidden_clips(d):
    return removed_clips(d) | PENDING_CLIPS.get(os.path.realpath(d), set())


class Purge:
    def __init__(self, data_dir, history, intake=None, calendar=None, outputs=None, goals=None, bus=None):
        self.data_dir, self.history, self.intake, self.calendar = data_dir, history, intake, calendar
        self.outputs, self.goals, self.bus = outputs, goals, bus
        self.path = os.path.join(data_dir, "purge.json")
        self._lock = threading.RLock()
        self._apply_hidden()

    # ------------------------------------------------------------------ pending (Move to Trash, before it moved)
    def _pending(self):
        doc = read_json(self.path, None)
        return doc if isinstance(doc, dict) else {}

    def _apply_hidden(self):
        dirs, reqs, clips, goals = set(), set(), {}, set()
        for p in self._pending().values():
            entries = []
            for it in p.get("items") or []:
                if it["kind"] == "goal":
                    goals.add(it["id"])
                    entries.extend(it.get("members") or [])
                else:
                    entries.append(it)
            for it in entries:
                if it["kind"] == "clip":
                    clips.setdefault(os.path.realpath(it["dir"]), set()).add(it["clip"])
                elif it["kind"] == "request":
                    reqs.add(it["id"])
                else:
                    dirs.add(os.path.realpath(it["dir"]))
        if self.goals is not None:
            self.goals.hidden = goals
        self.history.gone = dirs
        self.history._last = self.history._last_archived = None
        if self.intake is not None:
            self.intake.hidden = reqs
        PENDING_CLIPS.clear()
        PENDING_CLIPS.update(clips)

    def _publish(self, items=()):
        if self.bus:
            for t in ("batches", "inbox", "calendar", "goals"):
                self.bus.publish(t)
            for x in items:
                if x.get("kind") == "clip":
                    self.bus.publish("output-edit", item=x["item"], clip=x["clip"])

    # ------------------------------------------------------------------ the plan
    def _busy(self, d):
        try:
            return self.history._busy(d)
        except Exception:  # noqa: BLE001
            return None

    def _row(self, d):
        rp = os.path.realpath(d)
        for archived in (False, True):
            for r in self.history.list(archived=archived)["items"]:
                if os.path.realpath(r.get("real") or r["dir"]) == rp:
                    return r
        return None

    def _folder(self, d):
        from .history import _trashable, vstudio_home
        home = os.path.realpath(os.path.expanduser("~"))
        rp = os.path.realpath(d)
        row = self._row(d)
        kind = (row or {}).get("kind") or ("project" if os.path.isfile(os.path.join(rp, "project.yaml")) else
                                           "batch" if os.path.isfile(os.path.join(rp, "batch.db")) else "work")
        if kind == "work" and os.path.isfile(os.path.join(rp, ".vstudio", "import.json")):
            kind = "import"
        res = dict(key=f"d:{rp}", kind=kind, dir=d, id=(row or {}).get("id"), ok=False,
                   name=(row or {}).get("name") or os.path.basename(rp), targets=[], files=0, bytes=0, keep=[], other=[])
        if not row or not os.path.isdir(rp):
            res["reason"] = "not-found"
            return res
        if self._busy(rp):
            res["reason"] = "running"
            return res
        if not _trashable(rp, home):
            res["reason"] = "unsafe"
            return res
        mine = os.path.realpath(os.path.join(vstudio_home(), "projects"))
        owned = _inside(rp, mine) and rp != mine
        srcs = folder_sources(rp)
        made, kept = [], []
        try:
            names = sorted(os.listdir(rp))
        except OSError:
            names = []
        for name in names:
            p = os.path.join(rp, name)
            q = _real(p)
            if any(_inside(s, q) for s in srcs) or not _inside(q, rp):
                kept.append(name)                     # holds her footage / points outside: stays
            elif owned or name in MADE:
                made.append(p)
            else:
                kept.append(name)
        if not made:
            res["reason"] = "nothing-made"
            res["keep"] = srcs[:20]
            return res
        targets = made
        if not kept:
            targets = [rp]
            parent = os.path.dirname(rp)
            if os.path.dirname(parent) == mine:      # an app-made project's projects/<id> (its intake note only)
                try:
                    rest = set(os.listdir(parent)) - {os.path.basename(rp), "intake.json", ".DS_Store"}
                except OSError:
                    rest = {"?"}
                if not rest:
                    targets = [parent]
        if not all(_trashable(t, home) for t in targets):
            res["reason"] = "unsafe"
            return res
        n, size = _size(targets)
        res.update(ok=True, targets=targets, whole=not kept, files=n, bytes=size, keep=srcs[:20],
                   other=[k for k in kept if not any(_inside(s, os.path.join(rp, k)) for s in srcs)][:20])
        return res

    def _clip(self, item, clip):
        from .history import _trashable
        from .outputs import list_clips
        home = os.path.realpath(os.path.expanduser("~"))
        res = dict(key=f"c:{item}/{clip}", kind="clip", item=item, clip=clip, ok=False, name=clip, targets=[],
                   files=0, bytes=0, keep=[], other=[])
        try:
            e = self.history.find(item)
        except KeyError:
            res["reason"] = "not-found"
            return res
        d = os.path.realpath(e["dir"])
        res.update(dir=d, project=e.get("name"))
        c = next((x for x in list_clips(e) if x["id"] == clip), None)
        if c is None:
            res["reason"] = "not-found"
            return res
        res["name"] = c.get("title") or clip
        try:
            own = (self.outputs and read_json(self.outputs._titles_path(), None)) or {}
            t = own.get(self.outputs._title_key(e, clip)) if isinstance(own, dict) else None
            if isinstance(t, str) and t.strip():
                res["name"] = t.strip()
        except Exception:  # noqa: BLE001
            pass
        if self._busy(d):
            res["reason"] = "running"
            return res
        srcs = folder_sources(d)
        store = os.path.join(d, "state") if e["kind"] == "project" else d
        cand = [c.get("jobdir"), os.path.join(store, "jobs", clip), os.path.join(d, "items", clip),
                os.path.join(d, "final", clip)]
        for f in c.get("files") or []:
            cand.append(f.get("path"))
        cand.append(c.get("cover"))
        targets = []
        for p in cand:
            if not isinstance(p, str) or not p or not os.path.lexists(p):
                continue
            q = _real(p)
            if not _inside(q, d) or q == d or any(_inside(s, q) or _inside(q, s) for s in srcs):
                continue
            if not _trashable(q, home):
                continue
            targets.append(q)
        targets = _minimal(targets)
        n, size = _size(targets)
        res.update(ok=True, targets=targets, files=n, bytes=size, keep=srcs[:20])
        return res

    def _request(self, rid):
        res = dict(key=f"r:{rid}", kind="request", id=rid, ok=False, name=rid, targets=[], files=0, bytes=0, keep=[],
                   other=[])
        if self.intake is None:
            res["reason"] = "not-found"
            return res
        try:
            j = self.intake.get(rid)
        except (KeyError, ValueError):
            res["reason"] = "not-found"
            return res
        plan = j.get("plan") or {}
        names = [p.get("name") for p in plan.get("projects") or [] if p.get("name")]
        res["name"] = j.get("name") or (names[0] if names else None) or (j.get("prompt") or rid)[:80]
        if j.get("applied"):
            res["reason"] = "made"
            return res
        res.update(ok=True, keep=[p for p in (j.get("inputs") or []) if isinstance(p, str)][:20])
        return res

    def _goal(self, gid):
        res = dict(key=f"g:{gid}", kind="goal", id=gid, name=gid, ok=False,
                   targets=[], files=0, bytes=0, keep=[], other=[], members=[])
        try:
            g = self.goals._get(gid)
        except (AttributeError, KeyError):
            return dict(res, reason="not-found")
        res["name"] = g.get("goal") or g.get("prompt") or gid
        if g.get("state") in ("surveying", "running") or (g.get("more") or {}).get("state") in ("planning", "ready"):
            return dict(res, reason="running")
        dirs, reqs = set(), set()
        for v in g.get("videos") or []:
            dirs.update(p["dir"] for p in v.get("projects") or [] if p.get("dir"))
            dirs.update(p["dir"] for p in (v.get("prev") or {}).get("projects") or [] if p.get("dir"))
            dirs.update((v.get("past") or {}).get("dirs") or [])
            reqs.update((v.get("past") or {}).get("intakes") or [])
            if v.get("intake"):
                reqs.add(v["intake"])
        # A project shared by another visible collection is not exclusively owned by this deletion.
        for other in self.goals._all():
            if other["id"] == gid or other.get("dismissed_at"):
                continue
            for v in other.get("videos") or []:
                linked = [p.get("dir") for p in v.get("projects") or []]
                linked += [p.get("dir") for p in (v.get("prev") or {}).get("projects") or []]
                linked += (v.get("past") or {}).get("dirs") or []
                if {os.path.realpath(d) for d in dirs} & {os.path.realpath(d) for d in linked if d}:
                    return dict(res, reason="unsafe")
        members = [self._folder(d) for d in sorted(dirs) if os.path.lexists(d)]
        for rid in sorted(reqs):
            r = self._request(rid)
            if r.get("reason") == "made":
                # Applied requests are retained as history; their project files are handled above.
                continue
            members.append(r)
        members = [m for m in members if not (m["kind"] == "request" and m.get("reason") == "not-found")]
        if any(not m["ok"] for m in members):
            return dict(res, reason=next(m["reason"] for m in members if not m["ok"]))
        targets = sorted(set(t for m in members for t in m["targets"]))
        targets = [t for t in targets if not any(t != parent and _inside(t, parent) for parent in targets)]
        keep = list(dict.fromkeys([*(g.get("inputs") or []), *[p for m in members for p in m["keep"]]]))
        if any(_inside(os.path.realpath(src), os.path.realpath(target)) for src in keep for target in targets):
            return dict(res, reason="unsafe")
        return dict(res, ok=True, members=members, targets=targets,
                    files=sum(m["files"] for m in members), bytes=sum(m["bytes"] for m in members),
                    keep=keep,
                    other=list(dict.fromkeys(p for m in members for p in m["other"])))

    @staticmethod
    def _sel(sel):
        need(isinstance(sel, dict), "body must be an object")
        dirs, clips, reqs = sel.get("dirs") or [], sel.get("clips") or [], sel.get("requests") or []
        need(isinstance(dirs, list) and isinstance(clips, list) and isinstance(reqs, list), "dirs / clips / requests: lists")
        need(0 < len(dirs) + len(clips) + len(reqs) <= MAX_SEL, f"pick 1-{MAX_SEL} things to delete")
        for d in dirs:
            need(isinstance(d, str) and os.path.isabs(d) and "\0" not in d and len(d) < 4096, "dirs: absolute paths")
        for c in clips:
            need(isinstance(c, dict) and isinstance(c.get("item"), str) and isinstance(c.get("clip"), str) and
                 0 < len(c["clip"]) <= 200 and ".." not in c["clip"] and "/" not in c["clip"], "clips: {item, clip}")
        for r in reqs:
            need(isinstance(r, str) and len(r) == 12, "requests: request ids")
        return list(dict.fromkeys(os.path.normpath(d) for d in dirs)), clips, list(dict.fromkeys(reqs))

    def plan(self, sel):
        gids = sel.get("goals") or [] if isinstance(sel, dict) else []
        if gids:
            need(isinstance(gids, list) and len(gids) == 1 and isinstance(gids[0], str) and len(gids[0]) == 12, "pick one series")
            need(not any(sel.get(k) for k in ("dirs", "clips", "requests")), "delete a series separately")
            item = self._goal(gids[0])
            return dict(items=[item], keep=item["keep"], files=item["files"], bytes=item["bytes"],
                        sig=self._sig([item] if item["ok"] else []))
        dirs, clips, reqs = self._sel(sel)
        items = [self._folder(d) for d in dirs]
        whole = {os.path.realpath(d) for d in dirs}
        seen = set()
        for c in clips:
            k = (c["item"], c["clip"])
            if k in seen:
                continue
            seen.add(k)
            it = self._clip(*k)
            if it.get("dir") and it["dir"] in whole:
                continue                             # its whole folder goes already
            items.append(it)
        items += [self._request(r) for r in reqs]
        ok = [x for x in items if x["ok"]]
        keep = list(dict.fromkeys(p for x in ok for p in x["keep"]))[:40]
        return dict(items=items, keep=keep, files=sum(x["files"] for x in ok), bytes=sum(x["bytes"] for x in ok),
                    sig=self._sig(ok))

    @staticmethod
    def _sig(ok):
        return hashlib.sha1(json.dumps(sorted([x["key"], sorted(x["targets"]), sorted(m["key"] for m in x.get("members") or [])] for x in ok)).encode()).hexdigest()[:16]

    def _checked(self, sel, sig):
        doc = self.plan(sel)
        ok = [x for x in doc["items"] if x["ok"]]
        need(ok, "nothing here can be deleted")
        need(isinstance(sig, str) and sig == doc["sig"], "what would be deleted changed since you looked - look again")
        return doc, ok

    # ------------------------------------------------------------------ Move to Trash (soft)
    def stage(self, sel, sig):
        doc, ok = self._checked(sel, sig)
        pid = uuid.uuid4().hex[:12]
        rec = dict(id=pid, at=time.time(), items=[{k: x.get(k) for k in ("key", "kind", "dir", "id", "item", "clip",
                                                                          "name", "targets", "members")} for x in ok])
        with self._lock:
            p = self._pending()
            p[pid] = rec
            write_json(self.path, p)
            self._apply_hidden()
        self._publish(rec["items"])
        return dict(id=pid, items=rec["items"], targets=[t for x in ok for t in x["targets"]],
                    refused=[x for x in doc["items"] if not x["ok"]])

    def pending(self, now=None):
        now = now or time.time()
        return dict(items=[dict(id=p["id"], at=p["at"], stale=now - p["at"] > STALE_S,
                                targets=[t for x in p["items"] for t in x["targets"]])
                           for p in self._pending().values()])

    def pending_one(self, pid):
        p = self._pending().get(pid)
        if not p:
            raise KeyError(f"no pending delete {pid}")
        return dict(id=pid, at=p["at"], targets=[t for x in p["items"] for t in x["targets"]])

    def undo(self, pid):
        with self._lock:
            p = self._pending()
            rec = p.pop(pid, None)
            if rec is None:
                raise KeyError(f"no pending delete {pid}")
            write_json(self.path, p)
            self._apply_hidden()
        self._publish(rec["items"])
        return dict(ok=True, restored=[x["key"] for x in rec["items"]])

    def commit(self, pid, trashed, failed=()):
        """The desk moved ``trashed`` to the Trash (``failed``: the Trash refused): the things whose every target is
        gone from where it was lose their notes; the others come back in the lists."""
        need(isinstance(trashed, list) and isinstance(failed, list), "trashed / failed: lists")
        with self._lock:
            p = self._pending()
            rec = p.pop(pid, None)
            if rec is None:
                raise KeyError(f"no pending delete {pid}")
            bad = {os.path.realpath(f) for f in failed if isinstance(f, str)}
            done, back = [], []
            for it in rec["items"]:
                gone = all(not os.path.lexists(t) and t not in bad for t in it["targets"])
                (done if gone else back).append(it)
            self._forget(done)
            write_json(self.path, p)
            self._apply_hidden()
        self._publish(rec["items"])
        return dict(ok=True, deleted=[x["key"] for x in done], back=[dict(key=x["key"], name=x["name"]) for x in back])

    # ------------------------------------------------------------------ Delete permanently (hard)
    def hard(self, sel, sig):
        doc, ok = self._checked(sel, sig)
        from .history import _trashable
        home = os.path.realpath(os.path.expanduser("~"))
        done, failed = [], []
        for it in ok:
            try:
                for t in it["targets"]:
                    if not _trashable(t, home):
                        raise OSError("unsafe")
                    if os.path.islink(t) or os.path.isfile(t):
                        os.remove(t)
                    elif os.path.isdir(t):
                        shutil.rmtree(t)
                done.append(it)
            except OSError:
                failed.append(dict(key=it["key"], name=it["name"]))
        with self._lock:
            self._forget(done)
        self._publish(done)
        return dict(ok=True, deleted=[x["key"] for x in done], failed=failed, files=sum(x["files"] for x in done),
                    bytes=sum(x["bytes"] for x in done), refused=[x for x in doc["items"] if not x["ok"]])

    # ------------------------------------------------------------------ the notes that go with them
    def _forget(self, items):
        from .common import batch_id
        groups = [x for x in items if x["kind"] == "goal"]
        for group in groups:
            self._forget(group.get("members") or [])
            self.goals.dismiss(group["id"])
        items = [x for x in items if x["kind"] != "goal"]
        dirs = [x["dir"] for x in items if x["kind"] not in ("clip", "request")]
        clips = [x for x in items if x["kind"] == "clip"]
        reqs = [x["id"] for x in items if x["kind"] == "request"]
        if dirs:
            self.history.forget(dirs)
        for x in clips:                               # the folder remembers the video is gone
            d = x["dir"]
            if not os.path.isdir(d):
                continue
            gone = sorted(removed_clips(d) | {x["clip"]})
            try:
                write_json(os.path.join(d, ".vstudio", "removed.json"), dict(clips=gone))
            except OSError:
                pass
        if reqs and self.intake is not None:
            try:
                self.intake.delete(reqs)
            except Exception:  # noqa: BLE001  (already gone)
                pass
        # posts not posted yet of the deleted projects / videos (posted ones are her history)
        if self.calendar is not None and (dirs or clips):
            items_ = {batch_id(x) for d in dirs for x in (d, os.path.join(d, "state"), os.path.realpath(d),
                                                           os.path.join(os.path.realpath(d), "state"))}
            pairs = {(x["item"], x["clip"]) for x in clips}
            try:
                drop = [r["id"] for r in self.calendar._rows() if r.get("state") != "posted" and
                        (r.get("item") in items_ or (r.get("item"), r.get("clip")) in pairs)]
                for i in range(0, len(drop), 1000):
                    self.calendar.remove_many(drop[i:i + 1000])
            except Exception:  # noqa: BLE001
                pass
        if self.outputs is not None and clips:        # her own titles of the deleted videos
            try:
                path = self.outputs._titles_path()
                own = read_json(path, None)
                if isinstance(own, dict):
                    keys = set()
                    for x in clips:
                        keys.add(self.outputs._title_key(dict(dir=x["dir"]), x["clip"]))
                    if keys & set(own):
                        write_json(path, {k: v for k, v in own.items() if k not in keys})
            except Exception:  # noqa: BLE001
                pass
        if self.goals is not None and (dirs or reqs):
            try:
                self.goals.forget(dirs, reqs)
            except Exception:  # noqa: BLE001
                pass
