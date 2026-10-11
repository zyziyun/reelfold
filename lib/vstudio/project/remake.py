"""Remake one standing setting of a finished item without running its recipe again: the vertical framing of a vlog
(follow the subject / fill with blur) re-makes only the vertical exports, the post copy is written again and every
platform's post.md with it. Works for projects made before the recipe had the setting (no answer recorded, no
stage run): what the item has now is read from its exports (the checkpoint's ``current`` hook).

    python -m vstudio.project remake --dir P --item I --do framing=follow [--do copy] [--json | --json-events]

A checkpoint takes part when the recipe gives it a ``remake`` ref: ``fn(env, cp, choice) -> {answer, ...}`` with
``env`` the item as a finished run left it (``RemakeEnv``: params, the stages' outputs, the stage folder). The
answer is recorded as hers (``Project.answer``, no re-plan): the clip page and the next full run both follow it.
"""
import os
import time

from vstudio.batch.store import DB_NAME, Store
from vstudio.batch.util import now

from . import build as B
from . import manifests as M


class RemakeError(ValueError):
    pass


class RemakeEnv:
    """What a remake function gets: the shape of ``build.Env`` for an item that finished (no stage running)."""

    def __init__(self, project, item, stage):
        self.project = project
        rows = {r["id"]: r for r in project.jobs_rows()}
        if item not in rows:
            raise RemakeError(f"unknown item {item!r}; known: {', '.join(rows) or '-'}")
        row = rows[item]
        self.job = item
        self.m = project.manifest
        self.project_dir = project.dir
        self.state_dir = project.state_dir
        self.item_dir = os.path.join(project.dir, "items", row.get("_base_item") or item)
        self.params = dict(project.params(), **row)
        self.params.update(_project_dir=project.dir, _item_dir=self.item_dir, _item=item)
        self.spec, self.inputs = {}, {}
        if os.path.exists(os.path.join(project.state_dir, DB_NAME)):
            st = Store(project.state_dir)
            try:
                self.spec = st.spec or {}
                for name, r in st.stage_rows(item).items():
                    if r["state"] == "done" and isinstance(r.get("out"), dict):
                        self.inputs[name] = r["out"]
            finally:
                st.close()
        self.workflow_dir = os.path.join(M.WORKFLOWS, self.m["workflow"])
        self.at(stage)

    def at(self, stage):
        """The env pointed at ``stage``'s folder (state/jobs/<item>/<stage>)."""
        self.stage = stage
        self.dir = os.path.join(self.state_dir, "jobs", self.job, stage)
        os.makedirs(self.dir, exist_ok=True)
        return self

    def path(self, *names):
        return os.path.join(self.dir, *names)

    def item_path(self, *names):
        return os.path.join(self.item_dir, *names)

    def log(self, msg):
        with open(self.path("remake.log"), "a", encoding="utf-8") as f:
            f.write(f"{now()} {msg}\n")

    def tctx(self):
        t = B.static_tctx(self.m, self.params, self.job)
        t.update(stage_dir=self.dir, out=dict(self.inputs))
        return t

    def fmt(self, text):
        return M.fmt(text, self.tctx())

    def write_payload(self, cp, payload):
        """A checkpoint payload as its gate writes it (state/checkpoints/<item>/<id>.json) -> the payload."""
        from vstudio.batch.util import write_json
        pay = B.finalize_payload(self, cp, payload)
        write_json(os.path.join(B.checkpoint_dir(self.state_dir, self.job), f"{cp['id']}.json"), pay)
        return pay


def current(project, cp, item):
    """What a finished item has for checkpoint ``cp`` when nobody answered it (made before the recipe asked): the
    recipe's ``current`` hook -> {pick, choice, options} | None (nothing to show: not made yet / not applicable)."""
    if not cp.get("current"):
        return None
    try:
        return M.resolve_ref(cp["current"])(project, cp, item)
    except Exception:  # noqa: BLE001  (a setting that cannot be read is not shown)
        return None


def remakeable(project):
    """The checkpoints of this recipe a finished item can remake."""
    return [c for c in project.manifest["checkpoints"] if c.get("remake")]


def remake(project, item, todo, emit=None):
    """``todo`` {checkpoint id: choice (an option kind) | None (redo it as suggested)} for one finished ``item``, in
    recipe order -> {ok, item, done [{checkpoint, choice, ...}]}. Refused while the project runs."""
    from vstudio.batch import livestatus as LS
    from vstudio.batch.run import BatchBusy, runner_active
    emit = emit or (lambda ev: None)
    cps = {c["id"]: c for c in remakeable(project)}
    bad = [k for k in todo if k not in cps]
    if bad:
        raise RemakeError(f"{project.manifest['id']}: cannot remake {', '.join(bad)}; can: {', '.join(cps) or '-'}")
    if runner_active(project.state_dir):
        raise BatchBusy("the project is running; change this when it has finished")
    order = [c["id"] for c in project.manifest["checkpoints"] if c["id"] in todo]
    emit(dict(event="run-start", ts=now(), jobs=[item], remake=order))
    done, t0 = [], time.time()
    try:
        for cid in order:
            cp = cps[cid]
            LS.write(project.dir, "running", by="project", stage=f"cp_{cp['kind']}", message=f"remake: {cid}",
                     live_code="remake", live_params=dict(checkpoint=cid, item=item))
            emit(dict(event="stage-start", ts=now(), job=item, stage=cid))
            env = RemakeEnv(project, item, cp["after"])
            res = M.resolve_ref(cp["remake"])(env, cp, todo[cid]) or {}
            if res.get("answer") is not None:
                project.answer(cid, res["answer"], items=[item], replan=False)
            emit(dict(event="stage-done", ts=now(), job=item, stage=cid, state="done"))
            done.append(dict({k: v for k, v in res.items() if k != "answer"}, checkpoint=cid, choice=todo[cid]))
    except Exception as e:
        LS.write(project.dir, "failed", by="project", message=f"remake failed: {str(e)[:200]}")
        emit(dict(event="stage-fail", ts=now(), job=item, stage=(order + [""])[len(done)], error=str(e)[:400]))
        emit(dict(event="project-end", ts=now(), status="failed", exit_code=1))
        if isinstance(e, (RuntimeError, OSError)):
            raise RemakeError(str(e)) from e
        raise
    LS.write(project.dir, "done", by="project", message="done")
    emit(dict(event="project-end", ts=now(), status="done", exit_code=0, seconds=round(time.time() - t0, 1)))
    return dict(ok=True, item=item, done=done)
