"""Test fixture for the Home dashboard e2e (real engine): a small but full day of work, every piece made by the real
engine on tiny synthetic media (tone-burst talks + the engine tests' fake transcriber, no ASR model, no AI account):

  a/  "Short talk"     a talking-head project the engine parked at a filler question      -> Inbox (needs you)
  b/  "Weekly tips"    the same talk run on autopilot to the end: one made clip            -> ready / posts today
  c/  "Failed script"  a script project whose lint stage failed (failed_project.py)        -> Inbox (Try again)
  d/  "Q&A cut"        a project an agent is working in right now (``vstudio.project touch --status running``:
                       "Cutting clip 3 of 8", 4 min left)                                     -> Running
  watch/monday-qa.mp4  a fresh recording in a watched folder that no project uses yet      -> a chip
  PROFILE/engine-data/intake: the request "Cut my weekly Q&A into clips" sent twice (as the desk writes it)
                                                                                           -> a chip

    python home_projects.py ROOT PROFILE   (VSTUDIO_HOME etc. from the environment) -> prints {a, b, c, d, watch, ...}
"""
import json
import os
import subprocess
import sys
import time
import uuid

ROOT, PROFILE = sys.argv[1], sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", ".."))
sys.path[:0] = [os.path.join(REPO, "lib"), os.path.join(REPO, "tests")]


def run(script, root, *args):
    out = subprocess.run([sys.executable, os.path.join(HERE, script), root, *args], check=True, capture_output=True,
                         text=True, env=os.environ).stdout
    return json.loads(out.strip().splitlines()[-1])


a = run("real_project.py", os.path.join(ROOT, "a"))
b = run("real_project.py", os.path.join(ROOT, "b"), "--autopilot", "--name", "Weekly tips")
c = run("failed_project.py", os.path.join(ROOT, "c"))

from vstudio.project import works as W  # noqa: E402
from vstudio.project.core import Project  # noqa: E402

d = Project.create(os.path.join(ROOT, "d", "projects", "qa"), recipe="talkinghead", folder=os.path.join(ROOT, "a", "media"),
                   name="Q&A cut", params=dict(pipeline="fast", platforms=["tiktok"], preset="ultrafast"))
W.touch(d.dir, status="running", stage="cut", progress=0.375, message="Cutting clip 3 of 8", eta=240)

watch = os.path.join(ROOT, "watch")
os.makedirs(watch, exist_ok=True)
rec = os.path.join(watch, "monday-qa.mp4")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=180x320:rate=30:duration=2", "-an",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", rec], check=True)

intake = os.path.join(PROFILE, "engine-data", "intake")
os.makedirs(intake, exist_ok=True)
now = time.time()
for k, (prompt, ago) in enumerate((("Cut my weekly Q&A into clips", 2), ("cut my weekly Q&A into clips", 1))):
    pid = uuid.uuid4().hex[:12]
    job = dict(id=pid, state="done", step="applied", prompt=prompt, inputs=[], started=now - ago * 86400, seconds=4,
               platforms=["tiktok", "youtube-shorts"], lang="en", mode="autopilot",
               applied=[dict(dir=b["dir"], name="Weekly tips", recipe="talkinghead")])
    with open(os.path.join(intake, f"{pid}.job.json"), "w", encoding="utf-8") as f:
        json.dump(job, f)

print(json.dumps(dict(a=a["dir"], b=b["dir"], c=c["dir"], d=d.dir, watch=watch, recording=rec, hook=c["hook"],
                      marker=c["marker"], pending=a["pending"], b_status=b["status"])))
