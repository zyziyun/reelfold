"""Import finished videos (and their footage) for second-pass editing - the desk side of ``vstudio.project.imports``.

  POST /api/import/check {inputs[]}             what was dropped: finished videos (per clip, with versions, covers,
                                                post copy) vs footage -> {verdict, clips, sources, counts}
  POST /api/import {inputs[], sources?[], title?}   -> {job}; ``import`` events {job, state copying | done | failed,
                                                progress, item, clip, error}; GET /api/import/job/<job>
  GET  /api/import/<item>                       the import: clips, footage, shot matching / transcription state
  POST /api/import/<item>/match {clip?}         match the clip's shots to its footage again (``import-match`` events)
  POST /api/import/<item>/copy {clip}           its post copy written again for every platform (``import-copy``)
  GET  /api/import/<item>/takes?clip=&shot=     other takes of a shot from the footage, each with a still

After an import, in the background: every clip's first version is transcribed by the engine (its own transcript, so
the transcript editor and word cuts agree; the clip's post copy says the language) - a clip with speech opens on
its words, one without on its timeline - then its shots are matched to the footage. Nothing is written next to the
files she dropped: the engine copies (clones) the finished videos into a project of its own and only reads the
footage.
"""
import json
import os
import subprocess
import threading
import time
import uuid

from .common import batch_id, need, read_json
from .outputs import EngineMessage


class Imports:
    def __init__(self, data_dir, history, outputs, strips, bus=None, runner=None):
        self.data_dir, self.history, self.outputs, self.strips, self.bus = data_dir, history, outputs, strips, bus
        self.runner = runner
        self.jobs = {}
        self.state = {}                    # item -> {clip: {transcribe, match {state, matched, shots, error}, copy}}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ helpers
    def _engine(self):
        if self.runner is None:
            raise EngineMessage(dict(code="needs-engine", params={}, message="importing needs the video engine, "
                                     "which is not running", message_zh="导入需要视频引擎，引擎没有在运行"))
        from vstudio.project import imports as IM
        return IM

    def _emit(self, kind, **kw):
        if self.bus:
            self.bus.publish(kind, **kw)

    def _proc(self, args, on_event, timeout=4 * 3600):
        """``python -m vstudio.project <args> --json-events`` -> its done result (events passed on)."""
        cmd = [self.runner.python, "-m", "vstudio.project", *args, "--json-events"]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self.runner.env,
                             stdin=subprocess.DEVNULL)
        done, err = None, None
        t0 = time.time()
        for line in p.stdout:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("event") == "done":
                done = ev.get("result")
            elif ev.get("ok") is False:
                err = ev
            else:
                on_event(ev)
            if time.time() - t0 > timeout:
                p.kill()
                break
        p.wait()
        tail = (p.stderr.read() or "").strip().splitlines()
        p.stdout.close()
        p.stderr.close()
        if done is None:
            if err:
                raise EngineMessage(err)
            raise RuntimeError((tail[-1] if tail else "the engine stopped")[:300])
        return done

    def _entry(self, item):
        e = self.history.find(item, max_age=0)
        need(e["kind"] == "work", "not an imported video")
        return e

    def _clip_state(self, item, clip):
        with self._lock:
            return self.state.setdefault(item, {}).setdefault(clip, {})

    # ------------------------------------------------------------------ check
    def check(self, inputs):
        IM = self._engine()
        r = IM.classify(inputs)
        clips = [dict(key=c["key"], title=c["title"], folder=c["folder"],
                      versions=[dict(file=v["file"], platform=v["platform"], aspect=v["aspect"], w=v["w"], h=v["h"],
                                     duration=v["duration"], cover=v["cover"], post=bool(v["post"]), why=v["why"])
                                for v in c["versions"]]) for c in r["clips"]]
        self.history.allow_media([v["cover"] for c in clips for v in c["versions"] if v.get("cover")])
        pairs = IM.pair_sources(r["clips"], r["sources"]) if r["clips"] else {}
        for c in clips:
            c["sources"] = len(pairs.get(c["key"]) or [])
        return dict(ok=True, verdict=r["verdict"], counts=r["counts"], clips=clips, sources=r["sources"][:500],
                    raw=[dict(path=f["path"], why=f["why"]) for f in r["files"] if f["role"] == "raw"][:50])

    # ------------------------------------------------------------------ import
    def start(self, inputs, sources=None, title=None):
        self._engine()
        jid = uuid.uuid4().hex[:12]
        job = dict(id=jid, state="copying", progress=0.0, inputs=inputs, sources=sources or [], at=time.time())
        self.jobs[jid] = job
        self._emit("import", job=jid, state="copying", progress=0.0)
        threading.Thread(target=self._run, args=(job, title), daemon=True).start()
        return dict(job=jid, state="copying")

    def get(self, jid):
        need(jid in self.jobs, "no such import")
        return {k: v for k, v in self.jobs[jid].items() if k != "inputs"}

    def _run(self, job, title):
        args = ["import", *job["inputs"]]
        for s in job["sources"]:
            args += ["--sources", s]
        if title:
            args += ["--title", title]

        def ev(e):
            if e.get("stage") == "copy" and e.get("n"):
                job["progress"] = round(e["i"] / e["n"], 3)
                self._emit("import", job=job["id"], state="copying", progress=job["progress"])
        try:
            r = self._proc(args, ev, timeout=6 * 3600)
        except Exception as e:  # noqa: BLE001
            job.update(state="failed", error=getattr(e, "doc", None) or dict(code="import-failed", params={},
                                                                             message=str(e)[:300]))
            self._emit("import", job=job["id"], state="failed", error=job["error"])
            return
        item = batch_id(r["dir"])
        job.update(state="done", progress=1.0, item=item, clip=r["first"]["clip"], dir=r["dir"],
                   clips=[c["id"] for c in r["clips"]])
        self.history.allow_media([r["dir"]])
        self._emit("batches")
        self._emit("import", job=job["id"], state="done", item=item, clip=job["clip"])
        self._after(item, r["dir"], r["clips"])

    def _after(self, item, d, clips):
        """Background, one clip after another: the engine's transcript of its first version, then its shot match."""
        for c in clips:                      # in line for their shot match: the page says it is coming
            if c.get("sources"):
                self._clip_state(item, c["id"])["match"] = dict(state="running", progress=0.0)
        for c in clips:
            self._transcribe(item, d, c)
        for c in clips:
            if c.get("sources"):
                self._match(item, d, c["id"])

    def _transcribe(self, item, d, c):
        oid = c["versions"][0]["file"]
        key = (item, c["id"])
        st = dict(state="running", at=time.time())
        self.strips._asr[key] = st
        self.strips._emit(item, c["id"], st)
        self._clip_state(item, c["id"])["transcribe"] = "running"
        code = ("import json,sys\nfrom vstudio.project import outputs as O\nrec,doc=O._load(sys.argv[1],sys.argv[2])\n"
                "W=O.words(doc,required=False)\ndoc.save()\nprint(json.dumps(dict(n=len(W))))")
        try:
            p = subprocess.run([self.runner.python, "-c", code, d, oid], capture_output=True, text=True,
                               timeout=3600, env=self.runner.env, stdin=subprocess.DEVNULL)
            if p.returncode != 0:
                raise RuntimeError(((p.stderr or "").strip().splitlines() or ["transcription failed"])[-1][:300])
            n = json.loads(p.stdout.strip().splitlines()[-1])["n"]
            st = dict(state="done", words=n, at=time.time())
        except Exception as e:  # noqa: BLE001  (no speech model: the clip still opens, on its timeline)
            st = dict(state="failed", error=str(e)[:300], at=time.time())
        self.strips._asr[key] = st
        self._clip_state(item, c["id"])["transcribe"] = st["state"]
        self.strips._emit(item, c["id"], st)
        self._emit("output-edit", item=item, clip=c["id"])

    def _match(self, item, d, clip):
        cs = self._clip_state(item, clip)
        cs["match"] = dict(state="running", progress=0.0)
        self._emit("import-match", item=item, clip=clip, state="running", progress=0.0)

        def ev(e):
            if e.get("stage") == "match" and e.get("n"):
                cs["match"]["progress"] = round(e["i"] / e["n"], 3)
                self._emit("import-match", item=item, clip=clip, state="running", progress=cs["match"]["progress"])
        try:
            r = self._proc(["import-match", "--dir", d, "--clip", clip], ev)
            m = (r.get("matched") or [{}])[0]
            cs["match"] = dict(state="done", matched=m.get("matched", 0), shots=m.get("shots", 0),
                               coverage=m.get("coverage"))
        except Exception as e:  # noqa: BLE001
            cs["match"] = dict(state="failed", error=str(e)[:300])
        self._emit("import-match", item=item, clip=clip, **cs["match"])
        self._emit("output-edit", item=item, clip=clip)

    # ------------------------------------------------------------------ an import
    def info(self, item):
        IM = self._engine()
        e = self._entry(item)
        m = IM.manifest(e["dir"])
        need(m, "not an imported video")
        st = self.state.get(item) or {}
        clips = []
        for c in m["clips"]:
            s = st.get(c["id"]) or {}
            sm = IM.shots(e["dir"], c["versions"][0]["file"])
            match = s.get("match") or (dict(state="done", matched=sum(1 for x in sm["shots"] if x["match"]),
                                            shots=len(sm["shots"]), coverage=sm.get("coverage")) if sm else
                                       dict(state="idle" if c.get("sources") else "none"))
            clips.append(dict(id=c["id"], title=c["title"], sources=c.get("sources") or [],
                              versions=[dict(file=os.path.join(e["dir"], v["file"]), platform=v["platform"],
                                             original=v.get("original"), post=v.get("post"),
                                             rewritten=bool(v.get("post_original"))) for v in c["versions"]],
                              match=match, transcribe=s.get("transcribe"), copy=s.get("copy")))
        return dict(ok=True, item=item, dir=e["dir"], title=m.get("title"), at=m.get("at"), inputs=m.get("inputs"),
                    clips=clips)

    def match(self, item, clip=None):
        IM = self._engine()
        e = self._entry(item)
        m = IM.manifest(e["dir"])
        need(m, "not an imported video")
        todo = [c["id"] for c in m["clips"] if (clip is None or c["id"] == clip) and c.get("sources")]
        need(todo, "no footage is linked to this video")

        def run():
            for cid in todo:
                self._match(item, e["dir"], cid)
        threading.Thread(target=run, daemon=True).start()
        return dict(ok=True, clips=todo, state="running")

    def link(self, item, clip, sources):
        """Footage linked afterwards (a folder picked on the clip page) -> matched right away."""
        IM = self._engine()
        e = self._entry(item)
        try:
            got = IM.link_sources(e["dir"], clip, sources)
        except IM.ImportError_ as ex:
            raise EngineMessage(ex.info) from ex
        threading.Thread(target=self._match, args=(item, e["dir"], clip), daemon=True).start()
        self._emit("output-edit", item=item, clip=clip)
        return dict(ok=True, sources=len(got))

    def copy(self, item, clip):
        IM = self._engine()
        e = self._entry(item)
        need(IM.manifest(e["dir"]), "not an imported video")
        cs = self._clip_state(item, clip)
        if cs.get("copy") == "running":
            return dict(ok=True, state="running")
        cs["copy"] = "running"
        self._emit("import-copy", item=item, clip=clip, state="running")

        def run():
            try:
                self._proc_copy(e["dir"], clip)
                cs["copy"] = "done"
                self._emit("import-copy", item=item, clip=clip, state="done")
            except Exception as ex:  # noqa: BLE001
                cs["copy"] = "failed"
                self._emit("import-copy", item=item, clip=clip, state="failed", error=str(ex)[:300])
            self._emit("output-edit", item=item, clip=clip)
            self._emit("calendar")
        threading.Thread(target=run, daemon=True).start()
        return dict(ok=True, state="running")

    def _proc_copy(self, d, clip):
        p = subprocess.run([self.runner.python, "-m", "vstudio.project", "import-copy", "--dir", d, "--clip", clip,
                            "--json"], capture_output=True, text=True, timeout=900, env=self.runner.env,
                           stdin=subprocess.DEVNULL)
        doc = None
        try:
            doc = json.loads(p.stdout)
        except ValueError:
            pass
        if p.returncode != 0 or not isinstance(doc, dict) or doc.get("ok") is False:
            raise RuntimeError((doc or {}).get("message") or ((p.stderr or "").strip().splitlines() or
                                                               ["the post copy was not written"])[-1])
        return doc

    def takes(self, item, clip, shot):
        """Other takes of one shot: [{source, name, t, dur, why, still}] (stills cached in the desk's data)."""
        IM = self._engine()
        from vstudio import shotmatch as SM
        e = self._entry(item)
        m = IM.manifest(e["dir"])
        need(m, "not an imported video")
        c = next((x for x in m["clips"] if x["id"] == clip), None)
        need(c, "no such clip")
        sm = IM.shots(e["dir"], c["versions"][0]["file"])
        need(sm, "the shots of this clip are not matched yet")
        need(isinstance(shot, int) and 0 <= shot < len(sm["shots"]), "shot: a shot number of this clip")
        out = []
        for a in SM.alternatives(sm, shot, n=6):
            out.append(dict(a, name=os.path.basename(a["source"]), still=self._still(a["source"], a["t"] + a["dur"] / 2)))
        cur = sm["shots"][shot].get("match")
        orig = dict(source=cur["source"], name=os.path.basename(cur["source"]), t=cur["t"],
                    still=self._still(cur["source"], (cur["t"] + cur["t_end"]) / 2)) if cur else None
        stills = [x["still"] for x in out if x.get("still")] + ([orig["still"]] if orig and orig.get("still") else [])
        self.history.allow_media(stills)
        return dict(ok=True, shot=shot, original=orig, takes=out)

    def _still(self, src, t):
        import hashlib
        d = os.path.join(self.data_dir, "import-stills")
        os.makedirs(d, exist_ok=True)
        k = hashlib.sha1(f"{os.path.realpath(src)}\0{round(t, 2)}".encode()).hexdigest()[:16]
        out = os.path.join(d, k + ".jpg")
        if os.path.exists(out):
            return out
        try:
            from vstudio import media
            media.run(["ffmpeg", "-y", "-ss", f"{max(0.0, t):.3f}", "-i", src, "-frames:v", "1", "-vf",
                       "scale=320:-2", "-q:v", "4", out])
        except Exception:  # noqa: BLE001
            return None
        return out if os.path.exists(out) else None


def import_clips(d, probe=None):
    """The clips of an imported folder from its manifest (every version kept, even two of one aspect: a Chinese and
    an English 16:9) -> the desk's clip rows, or None when ``d`` is not an import."""
    m = read_json(os.path.join(d, ".vstudio", "import.json"), None)
    if not isinstance(m, dict) or not isinstance(m.get("clips"), list):
        return None
    from . import works as WK
    names = {"youtube": "YouTube", "youtube-shorts": "Shorts", "tiktok": "TikTok", "instagram": "Instagram",
             "facebook": "Facebook", "linkedin": "LinkedIn", "x": "X", "xiaohongshu": "小红书", "douyin": "抖音",
             "bilibili": "B站", "wechat-channels": "视频号", "kuaishou": "快手", "weibo": "微博"}
    out = []
    for c in m["clips"]:
        files = []
        for v in c.get("versions") or []:
            p = os.path.join(d, v["file"])
            if not os.path.isfile(p):
                continue
            info = (probe or (lambda _p: {}))(p) or {}
            w, h = v.get("w") or info.get("w"), v.get("h") or info.get("h")
            files.append(dict(path=p, aspect=WK.aspect_of(w, h) or "原尺寸", w=w, h=h, fps=info.get("fps"),
                              duration=v.get("duration") or info.get("duration"),
                              platform=f"{v['platform']}:{v.get('orientation') or 'vertical'}" if v.get("platform")
                              else None, label=names.get(v.get("platform")) if v.get("platform") else None))
        first = (c.get("versions") or [{}])[0]
        cover = next((os.path.join(d, v["cover"]) for v in c.get("versions") or [] if v.get("cover")), None)
        posts = {v["platform"]: v["post"] for v in c.get("versions") or [] if v.get("platform") and v.get("post")}
        out.append(dict(id=c["id"], title=(first.get("post") or {}).get("title") or c.get("title") or c["id"],
                        state="done", files=files, cover=cover, post=first.get("post"), posts=posts,
                        duration=next((f["duration"] for f in files if f.get("duration")), None), extra=False,
                        imported=dict(sources=len(c.get("sources") or []))))
    return out
