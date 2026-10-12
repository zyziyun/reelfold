"""Test fixture for the Home chips / Studio empty states e2e (real engine, tiny synthetic talks, no AI account):

  u/  "Office hours"   two recordings run as the desk starts a project (a pilot of one): the first clip made (its
                       filler cut and its review answered), the second not made yet          -> "Finish … 1 clip left"
                                                                                                and a video "not made yet"
  s/  "Workshop talk"  a made project from one request ("Cut this week's recordings into clips"): registered in the
                       request's series (``intake-…``, named after the request's words)       -> the series chip
  c/  "Failed script"  a script project whose lint stage failed: a question about the whole project, no video
  a/  "Short talk"     a talk parked at a filler question, newer than c (first in Needs you)

    python home_scale.py ROOT   (VSTUDIO_HOME etc. from the environment) -> prints {u, s, c, a, series}
"""
import json
import os
import subprocess
import sys

ROOT = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", ".."))
sys.path[:0] = [os.path.join(REPO, "lib"), os.path.join(REPO, "tests")]


def run(script, root, *args):
    out = subprocess.run([sys.executable, os.path.join(HERE, script), root, *args], check=True, capture_output=True,
                         text=True, env=os.environ).stdout
    return json.loads(out.strip().splitlines()[-1])


c = run("failed_project.py", os.path.join(ROOT, "c"))
s = run("real_project.py", os.path.join(ROOT, "s"), "--autopilot", "--name", "Workshop talk")
u = run("real_project.py", os.path.join(ROOT, "u"), "--pilot", "--name", "Office hours")
a = run("real_project.py", os.path.join(ROOT, "a"))

os.environ["VSTUDIO_TEST_TRUTH"] = u["truth"]
from vstudio.project import home as H  # noqa: E402
from vstudio.project.core import Project  # noqa: E402

# the first clip made: its filler question and its review answered the way the Inbox does, the pilot run on
p = Project(u["dir"])
p.answer("filler", {"approve": [3], "keep": []})
Project(p.dir).run(pilot=1, resume=True)
p = Project(u["dir"])
p.answer("publish", {"approve": True})
r = Project(p.dir).run(pilot=1, resume=True)

# "Workshop talk" is one of a request's projects: the request's series (as intake apply makes it)
sid = "intake-Cut-this-week-s-reco-10111539"
H.new_series(sid, "talkinghead", name="Cut this week's recordings int", notes="intake: Cut this week's recordings into clips")
H.register(s["dir"], name="Workshop talk", recipe="talkinghead", series=sid)

print(json.dumps(dict(u=u["dir"], s=s["dir"], c=c["dir"], a=a["dir"], series=sid, status=r["status"])))
