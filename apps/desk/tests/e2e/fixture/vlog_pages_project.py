"""Test fixture for the project-page e2e: travel vlogs (her "Seattle red leaves" kind) on tiny synthetic drone-like
clips with NO audio stream (no speech, no transcript), made by the REAL engine with the vlog recipe on autopilot (the
rules draft the cut, pick a license-free bed and the cover; no AI account, no network):

    done    run to the end: exports + covers under items/<item>/exports (not the batch layout), so the desk must read
            them through the engine's collect to call it Ready, show its cover and open it in the editor
    fresh   created, not run: the desk starts it (Try again) and shows its pieces as they are made

    python vlog_pages_project.py ROOT [--fresh-secs N]   (VSTUDIO_HOME etc. from the environment) -> prints {done, fresh}
    (``fresh`` gets its own, longer clips so its run lasts long enough to watch and pause)
"""
import json
import os
import subprocess
import sys

ROOT = sys.argv[1]
FRESH_SECS = int(sys.argv[sys.argv.index("--fresh-secs") + 1]) if "--fresh-secs" in sys.argv else 6
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
sys.path[:0] = [os.path.join(REPO, "lib")]

from vstudio.project.core import Project  # noqa: E402


def footage(folder, secs):
    os.makedirs(folder, exist_ok=True)
    out = []
    for i in range(3):
        p = os.path.join(folder, f"DJI_000{i}_D.MP4")
        if not os.path.exists(p):
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                            f"testsrc2=size=480x270:rate=30:duration={secs}", "-vf", f"hue=h={i * 40}", "-c:v",
                            "libx264", "-pix_fmt", "yuv420p", p], check=True)
        out.append(p)
    return out


def make(name, title, clips):
    p = Project.create(os.path.join(ROOT, "projects", name), recipe="vlog", name=title, inputs=dict(footage=clips),
                       params=dict(platforms=["youtube", "tiktok"], preset="ultrafast", title=title))
    p.data["prompt"] = "Cut these into a calm red-leaves film with some music"
    p.data["autopilot"] = dict(on=True, spend_cap=0.0, judge=False, ask=[], lang="en")
    p.save()
    return p


out = {}
done = make("done", "Red leaves", footage(os.path.join(ROOT, "media"), 6))
r = done.run(autopilot=True)
out["done"] = dict(dir=done.dir, status=r["status"], exit=r.get("exit_code"), pending=[(x["item"], x["id"]) for x in r["pending"]])
fresh = make("fresh", "Maple road", footage(os.path.join(ROOT, "media-long"), FRESH_SECS))
out["fresh"] = dict(dir=fresh.dir)
print(json.dumps(out, ensure_ascii=False))
