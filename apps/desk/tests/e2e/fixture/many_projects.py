"""Test fixture for the All projects scale e2e (real engine): N script projects (the preproduction recipe, a topic
each - no media, nothing run) registered the way the desk's own projects are, so the Studio lists N videos.

    python many_projects.py ROOT N   (VSTUDIO_HOME from the environment) -> prints {n, dirs[0]}
"""
import json
import os
import sys

ROOT, N = sys.argv[1], int(sys.argv[2])
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "lib"))

from vstudio.project.core import Project  # noqa: E402

TOPICS = ["Why the second request is faster", "Three ways to cut a long talk", "Captions that people read",
          "A calmer cover", "Posting at the right hour", "One recording, every platform"]
dirs = []
for k in range(N):
    p = Project.create(os.path.join(ROOT, "projects", f"s{k:03d}"), recipe="preproduction",
                       name=f"Script {k + 1:03d} · {TOPICS[k % len(TOPICS)]}",
                       items=[dict(id="001", inputs=dict(topic=TOPICS[k % len(TOPICS)]))])
    dirs.append(p.dir)
print(json.dumps(dict(n=len(dirs), first=dirs[0])))
