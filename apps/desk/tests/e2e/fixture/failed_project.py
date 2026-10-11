"""Test fixture for the Try again e2e: a small script project (preproduction recipe) made on autopilot whose ``lint``
stage fails while ``ROOT/FAIL`` exists. Writes a test-only ``sitecustomize`` hook to ``ROOT/hook`` (put that folder on
the desk's PYTHONPATH, with ``TRYAGAIN_FAIL_WHILE=ROOT/FAIL``), then runs the project once the way the desk does
(``run --autopilot --json-events`` into ``desk-pilot.log`` + its ``desk-pilot.json`` record), so it is failed.

    python failed_project.py ROOT   (VSTUDIO_HOME etc. from the environment) -> prints {dir, hook, marker}
"""
import json
import os
import subprocess
import sys
import time

ROOT = sys.argv[1]
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "lib"))

HOOK = '''import os
_m = os.environ.get("TRYAGAIN_FAIL_WHILE")
if _m:
    from vstudio.project.adapters import preproduction as _pp
    _lint = _pp.lint

    def lint(*a, **k):
        if os.path.exists(_m):
            raise RuntimeError("No such filter: 'nope' (test failure)")
        return _lint(*a, **k)
    _pp.lint = lint
'''

hook = os.path.join(ROOT, "hook")
os.makedirs(hook, exist_ok=True)
with open(os.path.join(hook, "sitecustomize.py"), "w", encoding="utf-8") as f:
    f.write(HOOK)
marker = os.path.join(ROOT, "FAIL")
open(marker, "w").close()

from vstudio.project import autopilot as AP  # noqa: E402
from vstudio.project.core import Project  # noqa: E402

p = Project.create(os.path.join(ROOT, "projects", "script"), recipe="preproduction", name="Failed script",
                   items=[dict(id="001", inputs=dict(topic="Why the second request is faster"))])
AP.configure(p, on=True, judge=False)
args = ["-m", "vstudio.project", "run", "--dir", p.dir, "--autopilot", "--json-events"]
env = dict(os.environ, PYTHONPATH=os.pathsep.join([hook, os.path.join(REPO, "lib")]), TRYAGAIN_FAIL_WHILE=marker)
with open(os.path.join(p.dir, "desk-pilot.log"), "ab") as log:
    started = time.time()
    code = subprocess.run([sys.executable, *args], stdout=log, stderr=log, env=env).returncode
with open(os.path.join(p.dir, "desk-pilot.json"), "w", encoding="utf-8") as f:
    json.dump(dict(pid=None, started=started, offset=0, agent_offset=0, exit=code, finished=time.time(), provider=None,
                   args=args), f)
print(json.dumps(dict(dir=p.dir, hook=hook, marker=marker, exit=code)))
