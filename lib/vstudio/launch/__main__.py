"""python -m vstudio.launch <step> CONFIG [options]  (see vstudio.launch and workflows/launch-kit/WORKFLOW.md)

  features CONFIG [--json]                 draft features: release.changelog / git / notes, else the brief's shot table
  capture CONFIG                           (capture.clips / capture.images: read her own recordings, record nothing)
  capture CONFIG                           run scripts/capture.mjs on capture.shot_list -> capture.shots
  build CONFIG [--only demo,loop,clip,<feature>,<name>]
  render CONFIG [--only ...] [--quality draft|looks|delivery] [--no-build]
  stills CONFIG                            Product Hunt gallery + OG image
  copy CONFIG                              post copy per platform x language -> copy/COPY.md
  schedule CONFIG [--apply]                proposal -> schedule/; --apply = planned posts on the publish calendar
  check CONFIG                             vstudio.firstpass on every video (exit 1 on a must-fix item)
  all CONFIG [--quality ...]               build, render, stills, copy, schedule, check
"""
import argparse
import json
import os
import subprocess
import sys

from . import config as C
from . import features as FE
from . import kit as K

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
CAPTURE = os.path.join(ROOT, "workflows", "launch-kit", "scripts", "capture.mjs")


def _brief_files(root):
    """Her brief / notes next to the config (the project links them into inputs/)."""
    out = []
    for d in (os.path.join(root, "inputs"), root):
        if os.path.isdir(d):
            out += sorted(os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith((".md", ".txt"))
                          and not f.startswith(".") and f.lower() not in ("changelog.md",))
    return out


def draft_features(cfg_path):
    """The feature list to show -> (features [{id, title, kind, ...}], source, notes [plain lines]). Sources in
    order: the release the config names (changelog / git range / pasted notes; a changelog that is not there is
    skipped, said in ``notes``), the features already in the config (drafted from her brief), the shot table of
    her brief; else an empty list (never an error: the list is only a draft)."""
    import yaml
    with open(cfg_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise C.ConfigError("launch.config.yaml is not a mapping of settings")
    rel = dict(raw.get("release") or {})
    root = os.path.dirname(os.path.abspath(cfg_path))
    notes = []
    if rel.get("changelog"):
        rel["changelog"] = os.path.join(root, os.path.expanduser(rel["changelog"]))
    if (rel.get("git") or {}).get("repo"):
        rel["git"] = dict(rel["git"], repo=os.path.join(root, os.path.expanduser(rel["git"]["repo"])))
    if rel:
        try:
            feats = FE.load(rel)
            if feats:
                return feats, "release", notes
        except FE.SourceMissing as e:
            notes.append(f"{e}; drafting from the clips and the brief instead")
            rel.pop("changelog", None)
            if rel.get("git") or rel.get("notes"):
                feats = FE.load(rel)
                if feats:
                    return feats, "release", notes
    have = [f for f in raw.get("features") or [] if isinstance(f, dict) and f.get("id")]
    if have:
        return [dict(id=f["id"], title=C.plain(C.text(f.get("caption"))), kind="feat", scope=None,
                     shot=f.get("shot") or f["id"], caption=f.get("caption")) for f in have], "config", notes
    shots = [os.path.basename(c if isinstance(c, str) else c.get("file") or "")
             for c in ((raw.get("capture") or {}).get("clips") or [])]
    for b in _brief_files(root):
        with open(b, encoding="utf-8", errors="replace") as f:
            got = FE.from_brief(f.read(), shots or None)
        if got["features"]:
            return [dict(id=x["id"], title=x["caption"]["en"], kind="feat", scope=None,
                         shot=[os.path.splitext(s)[0] for s in x["shots"]], caption=x["caption"])
                    for x in got["features"]], os.path.basename(b), notes
    notes.append("no release notes, changelog or brief with on-screen lines: write the features in "
                 "launch.config.yaml")
    return [], None, notes


def _features(cfg_path, as_json):
    feats, source, notes = draft_features(cfg_path)
    for n in notes:
        print("note:", n, file=sys.stderr)
    if as_json:
        print(json.dumps(feats, ensure_ascii=False, indent=1))
        return 0
    print("# draft: pick 3-6, give each a shot id, write the on-screen caption (【term】 = highlighted word)")
    print(f"# from: {source or 'nothing yet'}")
    if not feats:
        print("features: []")
        return 0
    print("features:")
    for f in feats:
        sid = f.get("shot") or f["id"]
        print(f"  - id: {f['id']}            # {f['kind']}{'(' + f['scope'] + ')' if f.get('scope') else ''}")
        print(f"    shot: {json.dumps(sid, ensure_ascii=False)}")
        cap = f.get("caption") if isinstance(f.get("caption"), dict) else {"en": f["title"]}
        print(f"    caption: {json.dumps(cap, ensure_ascii=False)}")
    return 0


def capture(cfg):
    cap = cfg.get("capture") or {}
    if not cap.get("shot_list"):
        if cap.get("clips") or cap.get("images"):
            # her own recordings / screenshots: nothing to record; read them once (size, poster, where the action is)
            sh = C.load_shots(cfg)
            print(f"{len(sh)} supplied shot(s), nothing to record: {', '.join(sorted(sh))}", flush=True)
            return 0
        raise C.ConfigError("nothing to show: list your recordings under capture.clips (or screenshots under "
                            "capture.images), or a capture.shot_list to record the product")
    out = os.path.dirname(cap["shots"]) if cap.get("shots") else os.path.join(cfg["out"], "capture")
    cmd = ["node", CAPTURE, "--shots", cap["shot_list"], "--out", out]
    if cap.get("app"):
        cmd += ["--electron", cap["app"]]
    elif cap.get("url"):
        cmd += ["--url", cap["url"]]
    else:
        raise C.ConfigError("capture: set app (an Electron app dir) or url")
    for k, v in (cap.get("env") or {}).items():
        cmd += ["--env", f"{k}={v}"]
    if cap.get("env_json"):
        cmd += ["--env-json", cap["env_json"]]
    if cap.get("size"):
        cmd += ["--size", str(cap["size"])]
    if cap.get("scale"):
        cmd += ["--scale", str(cap["scale"])]
    print(" ".join(cmd), flush=True)
    return subprocess.run(cmd).returncode


def _main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m vstudio.launch", description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split("\n", 1)[1])
    ap.add_argument("step", choices=["features", "capture", "build", "render", "stills", "copy", "schedule", "check",
                                     "all"])
    ap.add_argument("config")
    ap.add_argument("--only", default="", help="comma list: demo, loop, clip, a feature id or a render name")
    ap.add_argument("--quality", default="delivery", choices=["draft", "looks", "delivery"])
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.step == "features":
        return _features(a.config, a.json)
    cfg = C.load(a.config)
    from . import brand as B
    for w in B.warnings(cfg):
        print("warning:", w, file=sys.stderr)
    only = [x for x in a.only.split(",") if x] or None
    if a.step == "capture":
        return capture(cfg)
    if a.step == "build":
        K.build(cfg, only)
    elif a.step == "render":
        K.render(cfg, only, a.quality, rebuild=not a.no_build)
    elif a.step == "stills":
        for p in K.stills(cfg):
            print(p)
    elif a.step == "copy":
        res = K.posts(cfg)
        for w in res["warnings"]:
            print("check:", w)
        print(os.path.join(cfg["out"], "copy", "COPY.md"))
    elif a.step == "schedule":
        res = K.schedule(cfg, apply=a.apply)
        print(f"{len(res['rows'])} posts proposed -> {os.path.join(cfg['out'], 'schedule', 'SCHEDULE.md')}")
        if a.apply:
            print(f"calendar: {len(res['added'])} planned, {len(res['skipped'])} without an account (schedule.accounts)")
    elif a.step == "check":
        return 0 if K.check(cfg)["ok"] else 1
    elif a.step == "all":
        K.render(cfg, only, a.quality)
        K.stills(cfg)
        K.posts(cfg)
        K.schedule(cfg)
        return 0 if K.check(cfg)["ok"] else 1
    return 0


def main(argv=None):
    """The CLI; a failure is one plain line on stderr ("launch-kit <kind>: <what to fix>", the project runner maps
    it to a failure code), never a Python traceback. VSTUDIO_DEBUG=1 shows the traceback too."""
    step = next((x for x in (argv if argv is not None else sys.argv[1:]) if not x.startswith("-")), "")
    try:
        return _main(argv)
    except C.ConfigError as e:
        print(f"launch-kit config: {e}", file=sys.stderr)
        return 2
    except (FE.SourceMissing, FileNotFoundError) as e:
        if os.environ.get("VSTUDIO_DEBUG"):
            raise
        what = e
        if isinstance(e, FileNotFoundError) and e.filename:
            what = f"{os.path.basename(e.filename)} is not there"
        print(f"launch-kit config: {step}: {what}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001  (a tool / render failure: its own words, no traceback)
        if os.environ.get("VSTUDIO_DEBUG"):
            raise
        print(f"launch-kit {step} failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
