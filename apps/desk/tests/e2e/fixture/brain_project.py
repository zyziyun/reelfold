"""Test fixture for the editor-brain screens (brainScreens.spec.ts): a calm travel film made by the REAL engine on
autopilot (no AI account, no network) from four synthetic drone-like clips - an evening pair, a dusk shot and a dark
night shot at 60p - so the brain plans holds, a hard cut, a dissolve where the light changes, slow motion on the 60p
shot; her change of one shot; the rules draft cut from that plan (the builder's edit list carries the shot ids).

Then one "Could be generated" idea is generated through the Create spend gate with the Create TEST STAND-IN provider
(tests/create_fake.py: no network, nothing paid - it writes a flat coloured clip) and placed in the edit, and the
project re-renders with it, so the screens show an idea, a take in the edit and the timeline's AI shot.

    python brain_project.py ROOT        (VSTUDIO_HOME etc. from the environment) -> prints {dir, item, placed, ideas}
"""
import json
import os
import subprocess
import sys

ROOT = sys.argv[1]
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
sys.path[:0] = [os.path.join(REPO, "lib"), os.path.join(REPO, "tests")]

from vstudio.project.core import Project  # noqa: E402

PAN = "drawgrid=w=48:h=48:t=2:c=white@0.22,noise=alls=10:allf=u,crop=640:360:x='t*22':y=80"
CLIPS = (  # name, lavfi source, filters, fps - each a different light, so the plan has something to decide
    ("DJI_20261012174001_0001_D.MP4", "gradients=size=960x540:rate=30:c0=0xf2a65a:c1=0x6b8fb8:speed=0.004:duration=12",
     PAN + ",eq=brightness=0.02", 30),
    ("DJI_20261012174512_0002_D.MP4", "gradients=size=960x540:rate=30:c0=0xe89a52:c1=0x5f86b0:speed=0.005:duration=12",
     PAN + ",eq=brightness=0.0", 30),
    ("DJI_20261012181530_0003_D.MP4", "mandelbrot=size=640x360:rate=60", "hue=h=200,eq=brightness=-0.05", 60),
    ("DJI_20261012195021_0004_D.MP4", "gradients=size=640x360:rate=30:c0=0x080b12:c1=0x030407:speed=0.002:duration=12",
     "noise=alls=3:allf=u", 30),                       # too dark to use: the brain proposes a steady take of it
)


def footage(folder):
    os.makedirs(folder, exist_ok=True)
    out = []
    for name, src, vf, fps in CLIPS:
        p = os.path.join(folder, name)
        if not os.path.exists(p):
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", src, "-t", "12", "-vf", vf,
                            "-r", str(fps), "-c:v", "libx264", "-pix_fmt", "yuv420p", p], check=True)
        out.append(p)
    return out


def main():
    clips = footage(os.path.join(ROOT, "media-brain"))
    p = Project.create(os.path.join(ROOT, "projects", "brain"), recipe="vlog", name="Evening to night",
                       inputs=dict(footage=clips),
                       params=dict(platforms=["youtube"], preset="ultrafast", title="Evening to night"))
    p.data["prompt"] = "Make a 60-second calm travel film from these drone shots, from the evening light into the night"
    p.data["autopilot"] = dict(on=True, spend_cap=0.0, judge=False, ask=[], lang="en")
    p.save()
    from vstudio.brain import store as ST
    doc = ST.show(Project(p.dir))                      # the real shot tiles (vstudio.shots / five-frame fallback)
    used = [r for r in doc["plan"]["shots"] if not r["skip"]]
    if len(used) >= 2:                                 # her change of one shot: "a hard cut here"
        ST.set_shot(Project(p.dir), used[1]["id"], transition="cut")
    r = Project(p.dir).run(autopilot=True)
    out = dict(dir=p.dir, status=r["status"], ideas=[x["kind"] for x in ST.show(Project(p.dir))["proposals"]])
    # one idea generated with the Create test stand-in (no network, nothing paid) and placed in the edit
    import create_fake as fake
    from vstudio.brain import generate as GN
    from vstudio.create import costs
    fake.install()
    try:
        costs.set_cap(300)
        doc = ST.show(Project(p.dir))
        props = [x for x in doc["proposals"] if x["kind"] in GN.PLACEABLE]
        prop = next((x for x in props if x["kind"] == "short"), props[0] if props else None)
        if prop:
            est = GN.estimate(Project(p.dir), prop["id"])
            res = GN.generate(Project(p.dir), prop["id"], est["id"], est["confirm_code"], est["max_cny"],
                              code=prop["code"])
            out["placed"] = dict(id=prop["id"], kind=prop["kind"], status=res["status"])
    finally:
        fake.uninstall()
    r = Project(p.dir).run(autopilot=True)              # the edit changed: the render runs again with the take in it
    out["status2"] = r["status"]
    out["item"] = Project(p.dir).data["items"][0]["id"]
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
