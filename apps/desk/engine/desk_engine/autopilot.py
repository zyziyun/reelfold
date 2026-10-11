"""Autopilot in the desk: what the engine decided for a project, taking one decision back, and switching a project
between autopilot and "ask me first" (``python -m vstudio.project decisions | reopen | autopilot``, the engine's
references/PROJECTS.md section 3).

  GET  /api/autopilot/<item>              {supported, autopilot {on, spend_cap, judge, lang, ask}, decisions [...],
                                           running, queued}
  POST /api/autopilot/<item>/reopen {checkpoint, item}   the decision goes back to her: the project runs on to that
                                           checkpoint and stops there (the Inbox asks) -> {ok, rerun}
  POST /api/autopilot/<item>/mode {on}    switch; turning autopilot on also continues a project that waits (its
                                           questions are then decided by the engine) -> {ok, autopilot, resumed}
  POST /api/autopilot/<item>/change {checkpoint, item, answer {approve, keep}}   she changes one taste call in place
                                           (the clip editor's Undo / Change on a decision): her answer replaces the
                                           engine's, the affected stages re-run -> {ok, resumed, rerun}
  POST /api/autopilot/<item>/remake {item, do {checkpoint: choice | null}}   a standing setting of a finished clip
                                           made again in the background, only what it changes (the vlog's vertical
                                           framing: the vertical exports; its post copy: the copy + every post.md),
                                           also on a project made before the recipe had it
                                           (``python -m vstudio.project remake``) -> {ok, started, do}

The taste calls (the unsure filler cuts, the opening) come with their options in the inbox's plain-language shape,
each ``checked`` as decided, so the editor can show them as made decisions with Undo / Change per option.

Only recipe projects (``project.yaml``) have checkpoints to decide; other folders answer ``supported: false``.
"""
import json
import os

from . import inbox_labels as L
from . import pilot
from .common import BadRequest, need, read_json


def _m(code, en, zh, **params):
    return dict(code=code, message=en, message_zh=zh, params=params)


# her words for the standing settings a finished clip can make again (zh / en / fr): the clip chat and the project
# chat run them (``Autopilot.remake_asked``) instead of an edit the model would guess (a 9:16 version)
_FOLLOW = (r"跟随主体|跟随画面|跟着主体|跟拍主体|主体裁切|跟随.{0,4}裁切|不要模糊|别用模糊|不用模糊|去掉模糊|取消模糊|"
           r"不要.{0,6}模糊|follow(?:s|ing)? the (?:subject|action)|subject[- ]follow|\bno blur|without (?:the |a )?blur|"
           r"(?:don'?t|do not) (?:use (?:a |the )?)?blur|remove the blur|suivre le sujet|suit le sujet|sans flou|"
           r"pas de flou|enlever le flou")
_BLUR = (r"模糊(?:背景|填充|底)|用模糊|fill(?:ed)? with (?:a )?blur|blur(?:red)? (?:background|fill|pad)|fond flou|"
         r"remplir (?:avec du|de) flou")
_COPY = (r"(?:重写|重新写|改写|重新生成|重做|再写|写一?下?|更新|换).{0,10}(?<!封面)(?:发布)?文案|发布文案|"
         r"(?<!封面)文案.{0,6}(?:重写|重新写|重新生成|重做)|\bpost (?:copy|text|captions?)\b|"
         r"\b(?:re-?write|regenerate|redo|re-?do|write)\b.{0,30}\b(?:posts?|copy|descriptions?)\b|"
         r"\bcaptions?\b.{0,24}\bplatforms?\b|"
         r"texte de publication|(?:r[ée]{1,2}cri\w*|refai\w*|r[ée]g[ée]n[ée]r\w*).{0,30}(?:textes?|l[ée]gendes?|"
         r"descriptions?)")


def remake_intent(text):
    """A chat request -> {framing: follow | blur, copy: True} for what it asks to make again, or None."""
    import re
    t = (text or "").strip()
    out = {}
    if re.search(_FOLLOW, t, re.I):
        out["framing"] = "follow"
    elif re.search(_BLUR, t, re.I):
        out["framing"] = "blur"
    if re.search(_COPY, t, re.I):
        out["copy"] = True
    return out or None

# decisions the editor lists per clip, with their options (the others are listed on the project page as before)
TASTE = ("filler-confirm", "hook-pick")


class Autopilot:
    def __init__(self, history, runner, bus=None, intake=None):
        self.history, self.runner, self.bus = history, runner, bus

    def _project(self, item):
        e = self.history.find(item)
        d = e.get("dir") or ""
        return e, d, e.get("kind") == "project" and os.path.isfile(os.path.join(d, "project.yaml"))

    def _cli(self):
        need(self.runner is not None, "the engine is not available")
        return self.runner.sibling("vstudio.project")

    def get(self, item):
        e, d, ok = self._project(item)
        base = dict(item=item, running=bool(pilot.running(d)) if d else False, queued=pilot.queued(d) if d else None)
        if not ok:
            return dict(base, supported=False, autopilot=None, decisions=[])
        doc = self._cli().json(["decisions", "--dir", d, "--json"], timeout=60)
        decs = [dict(x, options=options(x)) if x.get("kind") in TASTE else x for x in doc.get("decisions") or []]
        return dict(base, supported=True, autopilot=doc.get("autopilot"), decisions=decs, choices=doc.get("choices") or [])

    def _resume(self, d, autopilot=None):
        """Continue the project in the background (unless it runs / waits in line already)."""
        if pilot.running(d) or pilot.queued(d):
            return False
        py = self.runner.python
        args = [py, "-m", "vstudio.project", "resume", "--dir", d, "--json-events"]
        if autopilot is True:
            args.insert(-1, "--autopilot")
        pilot.spawn(py, self.runner.env, d, bus=self.bus, args=args)
        return True

    def reopen(self, item, checkpoint, sub="*"):
        need(isinstance(checkpoint, str) and 0 < len(checkpoint) <= 60, "checkpoint: the decision's checkpoint id")
        need(isinstance(sub, str) and 0 < len(sub) <= 120, "item: the clip's item id (or *)")
        _e, d, ok = self._project(item)
        need(ok, "only a recipe project has decisions to take back")
        if pilot.running(d):
            raise BadRequest("the project is running; take this back when it has finished")
        r = self._cli().json(["reopen", "--dir", d, "--id", checkpoint, "--item", sub, "--json"], timeout=120)
        resumed = self._resume(d)
        if self.bus:
            self.bus.publish("batches")
            self.bus.publish("inbox")
        return dict(r if isinstance(r, dict) else {}, ok=True, resumed=resumed)

    def change(self, item, checkpoint, sub, answer):
        """Her answer to one taste call the engine made (keep a cut it made, make one it kept, another opening): it
        replaces the auto-answer (the decision is hers from now on, the log keeps the engine's) and the project runs
        the stages it affects again in the background."""
        need(isinstance(checkpoint, str) and 0 < len(checkpoint) <= 60, "checkpoint: the decision's checkpoint id")
        need(isinstance(sub, str) and 0 < len(sub) <= 120, "item: the clip's item id")
        need(isinstance(answer, dict) and isinstance(answer.get("approve"), list) and len(answer["approve"]) <= 200,
             "answer: {approve: [option ids], keep: [option ids]}")
        _e, d, ok = self._project(item)
        need(ok, "only a recipe project has decisions to change")
        if pilot.running(d):
            raise BadRequest("the project is running; change this when it has finished")
        doc = self._cli().json(["decisions", "--dir", d, "--json"], timeout=60)
        dec = next((x for x in doc.get("decisions") or [] if x.get("checkpoint") == checkpoint and
                    x.get("item") == sub and not x.get("asked")), None)
        if dec is None:                            # a standing setting she already chose (framing): she switches it
            dec = next((x for x in doc.get("choices") or [] if x.get("checkpoint") == checkpoint and
                        x.get("item") == sub), None)
        need(dec is not None, f"no decision {checkpoint} for {sub}")
        from .inbox import engine_answer
        value = engine_answer(dec.get("kind"), answer)
        need(value is not None, "answer: pick one option")
        r = self._cli().json(["checkpoint", "--dir", d, "--id", checkpoint, "--item", sub, "--answer",
                              json.dumps(value), "--json"], timeout=120)
        resumed = self._resume(d)
        if self.bus:
            self.bus.publish("batches")
            self.bus.publish("inbox")
        return dict(ok=True, resumed=resumed, rerun=(r or {}).get("rerun") if isinstance(r, dict) else None)

    def remake(self, item, sub, do):
        """Make one standing setting of a finished clip again (``choices``: the framing, the post copy - whoever set
        it, or what an older project has), in the background like a run: the project shows as running and the
        clip page / chat follow it on the bus."""
        need(isinstance(sub, str) and 0 < len(sub) <= 600, "item: the clip's item id (or a,b)")
        need(isinstance(do, dict) and 0 < len(do) <= 4, "do: {checkpoint: choice | null}")
        subs = [x for x in sub.split(",") if x]
        need(0 < len(subs) <= 20, "item: the clip's item id (or a,b)")
        _e, d, ok = self._project(item)
        need(ok, "only a recipe project has settings to make again")
        if pilot.running(d) or pilot.queued(d):
            raise BadRequest("the project is running; change this when it has finished")
        doc = self._cli().json(["decisions", "--dir", d, "--json"], timeout=60)
        args = []
        for cp, choice in do.items():
            for one in subs:
                c = next((x for x in doc.get("choices") or [] if x.get("checkpoint") == cp and x.get("item") == one),
                         None)
                need(c is not None, f"{cp}: not a setting of {one}")
                need(choice is None or (isinstance(choice, str) and choice in (c.get("options") or [])),
                     f"{cp}: one of {', '.join(c.get('options') or [])}")
            args += ["--do", f"{cp}={choice}" if choice else cp]
        py = self.runner.python
        pilot.spawn(py, self.runner.env, d, bus=self.bus,
                    args=[py, "-m", "vstudio.project", "remake", "--dir", d, "--item", sub, *args, "--json-events"])
        if self.bus:
            self.bus.publish("batches")
        return dict(ok=True, started=True, do=do)

    def remake_asked(self, item, want, clip=None):
        """A chat request (``remake_intent``) on project ``item`` - one clip of it, or the whole project: the settings
        it names that the clip has are made again in the background -> the reply messages, or None when it names
        none this project has (the chat answers as before)."""
        if not want:
            return None
        _e, d, ok = self._project(item)
        if not ok or self.runner is None:
            return None
        doc = self.get(item)
        mine = [c for c in doc.get("choices") or [] if clip is None or c.get("item") == clip or
                str(clip).startswith(f"{c.get('item')}/")]
        frs = [c for c in mine if c.get("kind") == "reframe-pick"]
        cps = [c for c in mine if c.get("kind") == "copy-pick"]
        do, msgs, subs = {}, [], set()
        if want.get("framing") and frs:
            todo = [c for c in frs if c.get("choice") != want["framing"]]
            if todo:
                do[todo[0]["checkpoint"]] = want["framing"]
                subs |= {c["item"] for c in todo}
            else:
                msgs.append(_m(f"remake-already-{want['framing']}", "The vertical versions already " +
                               ("follow the subject." if want["framing"] == "follow" else "fill with blur."),
                               "竖屏版本已经是" + ("跟随主体裁切" if want["framing"] == "follow" else "模糊填充") + "了。"))
        if want.get("copy") and cps:
            do[cps[0]["checkpoint"]] = None
            subs |= {c["item"] for c in cps}
        if not do:
            return msgs or None
        if doc.get("running") or doc.get("queued"):
            return msgs + [_m("remake-busy", "It is making something right now; ask again when it has finished.",
                              "现在正在制作，做完后再说一次。")]
        self.remake(item, ",".join(sorted(subs)), do)
        if want.get("framing") in [v for v in do.values()]:
            msgs.append(_m(f"remake-{want['framing']}",
                           "Making the vertical versions again: " + ("the camera follows the subject, no blurred "
                                                                    "background." if want["framing"] == "follow" else
                                                                    "the whole frame on a blurred fill."),
                           "正在重新导出竖屏版本：" + ("镜头跟随画面主体裁切，不用模糊背景。" if want["framing"] == "follow"
                                              else "整幅画面放在模糊背景上。")))
        if want.get("copy") and cps:
            msgs.append(_m("remake-copy", "Writing the post copy again for every platform (title, text and hashtags in "
                                          "its language); each version's post text is replaced when it is done.",
                           "正在为每个平台重写发布文案（标题、正文和话题，按平台语言），写好后替换各版本的发布文字。"))
        return msgs

    def mode(self, item, on):
        need(isinstance(on, bool), "on: true (autopilot) or false (ask me first)")
        _e, d, ok = self._project(item)
        need(ok, "only a recipe project can switch to autopilot")
        doc = self._cli().json(["autopilot", "--dir", d, "--on" if on else "--off", "--json"], timeout=60)
        resumed = False
        if on:                                     # her questions waiting in it are now the engine's to decide
            st = self._cli().json(["status", "--dir", d, "--brief", "--json"], timeout=120)
            if isinstance(st, dict) and st.get("state") in ("needs-you", "planned", "paused", "interrupted", "new"):
                resumed = self._resume(d, autopilot=True)
        if self.bus:
            self.bus.publish("batches")
            self.bus.publish("inbox")
        return dict(ok=True, autopilot=(doc or {}).get("autopilot"), resumed=resumed)


def options(dec):
    """A taste decision's options (from the checkpoint payload the engine showed its judge) in the inbox's shape,
    ``checked`` = what the engine decided: a filler cut it made, the opening it picked (none: no cold open). A filler
    option carries the words around it (``ctx``, inbox_labels.engine_option) so the editor finds it in the clip."""
    pay = read_json(dec.get("payload"), None) if dec.get("payload") else None
    if not isinstance(pay, dict):
        return []
    v = dec.get("value") if isinstance(dec.get("value"), dict) else {}
    cut = {str(x) for x in v.get("approve") or []}
    out = []
    for i, o in enumerate([o for o in pay.get("options") or [] if isinstance(o, dict)][:60]):
        opt = L.engine_option(o, pay.get("default"), i)
        if dec.get("kind") == "filler-confirm":
            opt["checked"] = opt["id"] in cut
        else:
            opt["checked"] = str(i) == str(v.get("pick"))
            opt["kind"] = "opening"
        out.append(opt)
    return out
