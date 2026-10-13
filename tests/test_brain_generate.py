"""An approved "Could be generated" proposal through the Create spend gate (vstudio.create.oneoff via
vstudio.brain.generate): priced first, nothing sent without the estimate's code; ONE submit after her confirm; the
take placed in the edit at the proposed spot and taken out again (Undo). The providers are the Create test stand-ins
(tests/create_fake.py) - never a paid call; without them the real Kling adapter is refused by the gate (no key)."""
import json
import os
import shutil
import subprocess

import pytest

import create_fake as fake
from vstudio.brain import generate as GN
from vstudio.brain import store as ST
from vstudio.brain import template as T
from vstudio.create.i18n import CreateError

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


def _clip(path, src="testsrc2", secs=6):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"{src}=size=320x180:rate=30", "-t", str(secs),
                    "-pix_fmt", "yuv420p", path], check=True)


def _tile(i, clip, **kw):
    base = dict(id=f"C{i}.S1", clip=clip, file=os.path.basename(clip), start=0.0, end=6.0, best=[1, 4], t=2.0,
                score=0.8, sharp=0.8, steady=0.85, exposure=0.8, jitter_px=0.3, pan_px_s=20.0, motion=3.0, bright=0.45,
                lab=[120.0, 128.0, 130.0], faces=1, face_area=0.02, subject_frac=0.5, subject_xy=[0.5, 0.5],
                src_fps=30.0, w=320, h=180)
    base.update(kw)
    return base


@pytest.fixture
def home(tmp_path, monkeypatch):
    from vstudio.create import costs, store
    monkeypatch.setenv("VSTUDIO_HOME", str(tmp_path / "vhome"))
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))
    monkeypatch.delenv("KLING_MCP_TOKEN", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    store.configure(str(tmp_path / "vhome"))
    fake.install()
    fake.reset()
    costs.set_cap(300)
    yield tmp_path / "vhome"
    fake.uninstall()
    store.configure(None)


@pytest.fixture
def project(tmp_path, monkeypatch, home):
    """A drafted calm vlog whose film opens close (faces in every shot): the brain proposes an establishing shot."""
    from vstudio.project.core import Project
    clips = [str(tmp_path / "a.mp4"), str(tmp_path / "b.mp4")]
    _clip(clips[0], "testsrc2")
    _clip(clips[1], "mandelbrot")
    pr = Project.create(str(tmp_path / "proj"), recipe="vlog", inputs=dict(footage=clips))
    pr.data["prompt"] = "Make a 12-second calm film."
    pr.data["items"] = [dict(id="v1")]
    pr.save()
    an = dict(files=[dict(id=f"f{k}", path=c, kind="video", duration=6, speech=False, orientation="horizontal",
                          talking_head=False, multi_person=False, screen_share=False) for k, c in enumerate(clips)])
    ts = [_tile(1, clips[0]), _tile(2, clips[1])]
    monkeypatch.setattr(ST, "_signals", lambda project, paths, refresh=False, light=False:
                        (T.signals(an, project.data["prompt"]), []))
    monkeypatch.setattr(ST, "_tiles", lambda project, paths, refresh=False, echo=None: ts)
    doc = ST.show(pr)
    work = os.path.join(pr.dir, "items", "v1", "work")
    os.makedirs(work)
    from vstudio.brain import steer
    with open(os.path.join(work, "edit.json"), "w") as f:
        json.dump(dict(src_dir=".", clips={"a": clips[0], "b": clips[1]},
                       segments=steer.calm(doc, {"a": clips[0], "b": clips[1]})), f)
    return Project(pr.dir), doc


def _edit(pr):
    return json.load(open(os.path.join(pr.dir, "items", "v1", "work", "edit.json")))


def test_gate_then_one_submit_then_placed_and_undo(project):
    from vstudio.project.core import Project
    pr, doc = project
    prop = next(p for p in doc["proposals"] if p["kind"] == "establishing")
    assert prop["provider"] == "kling-mcp" and prop["status"] == "proposed"
    est = GN.estimate(pr, prop["id"])
    assert est["codes"] == [] and est["max_cny"] == prop["estimate"]["cny"] > 0
    assert len(est["confirm_code"]) == 8 and est["month"]["cap"] == 300
    assert fake.SUBMITS == []                                           # pricing sends nothing
    with pytest.raises(CreateError) as e:                               # a wrong code: refused, nothing recorded
        GN.generate(pr, prop["id"], est["id"], "0" * 8, est["max_cny"], code=prop["code"])
    assert e.value.code == "create.confirm-mismatch" and fake.SUBMITS == []
    assert next(x for x in ST.show(Project(pr.dir))["proposals"] if x["id"] == prop["id"])["status"] == "proposed"
    with pytest.raises(CreateError) as e:                               # less than the price: refused
        GN.generate(pr, prop["id"], est["id"], est["confirm_code"], est["max_cny"] - 1, code=prop["code"])
    assert e.value.code == "create.max-too-low" and fake.SUBMITS == []
    r = GN.generate(Project(pr.dir), prop["id"], est["id"], est["confirm_code"], est["max_cny"], code=prop["code"])
    assert r["ok"] and r["status"] == "placed" and os.path.exists(r["file"])
    assert fake.SUBMITS == [("kling-mcp", prop["id"])]                  # exactly one paid submit
    segs = _edit(pr)["segments"]
    assert segs[0]["clip"] == f"ai_{prop['id']}" and segs[0]["ai"] and segs[0]["brain"] == prop["id"]
    assert _edit(pr)["clips"][f"ai_{prop['id']}"] == os.path.realpath(r["file"])
    led = [json.loads(x) for x in open(os.path.join(pr.dir, "state", "brain", "gen", "spend.jsonl"))]
    assert [x["status"] for x in led] == ["submitted"]
    got = next(x for x in ST.show(Project(pr.dir))["proposals"] if x["id"] == prop["id"])
    assert got["status"] == "placed" and got["placed"]["items"][0]["item"] == "v1"
    with pytest.raises((CreateError, ST.BrainError)):                   # the same OK never submits twice
        GN.generate(Project(pr.dir), prop["id"], est["id"], est["confirm_code"], est["max_cny"], code=prop["code"])
    with pytest.raises(ST.BrainError):                                  # paid: not "undone" like an idea
        ST.decide_gen(Project(pr.dir), prop["id"], "undo")
    assert fake.SUBMITS == [("kling-mcp", prop["id"])]
    GN.unplace(Project(pr.dir), prop["id"])                             # Undo: out of the edit, the take kept
    assert all(s["clip"] != f"ai_{prop['id']}" for s in _edit(pr)["segments"])
    assert f"ai_{prop['id']}" not in _edit(pr)["clips"] and os.path.exists(r["file"])
    GN.place(Project(pr.dir), prop["id"])                               # put it back
    assert _edit(pr)["segments"][0]["clip"] == f"ai_{prop['id']}"
    assert fake.SUBMITS == [("kling-mcp", prop["id"])]


def test_a_timeout_after_the_request_left_is_an_unknown_charge_never_retried(project):
    from vstudio.create import providers as PR
    pr, doc = project
    prop = next(p for p in doc["proposals"] if p["kind"] == "establishing")
    PR.set_fake(fake.FakeProvider, **{"kling-mcp": dict(timeout={prop["id"]})})
    est = GN.estimate(pr, prop["id"])
    r = GN.generate(pr, prop["id"], est["id"], est["confirm_code"], est["max_cny"], code=prop["code"])
    assert r["status"] == "unknown-charge" and len(fake.SUBMITS) == 1
    led = [json.loads(x) for x in open(os.path.join(pr.dir, "state", "brain", "gen", "spend.jsonl"))]
    assert led[-1]["status"] == "unknown-charge"
    assert "ai_" not in json.dumps(_edit(pr)["segments"])


def test_without_the_stand_ins_the_real_service_is_refused_by_the_gate(project):
    """No KLING_MCP_TOKEN: the real Kling adapter is not ready - the gate says so and nothing is sent."""
    from vstudio.create import providers as PR
    pr, doc = project
    prop = next(p for p in doc["proposals"] if p["kind"] == "establishing")
    PR.set_fake(None)
    est = GN.estimate(pr, prop["id"])
    assert [c["code"] for c in est["codes"]] == ["create.provider-not-ready"]
    with pytest.raises(CreateError) as e:
        GN.generate(pr, prop["id"], est["id"], est["confirm_code"], est["max_cny"], code=prop["code"])
    assert e.value.code == "create.provider-not-ready"
    assert not os.path.exists(os.path.join(pr.dir, "state", "brain", "gen", "spend.jsonl"))


def test_the_month_cap_refuses(project):
    from vstudio.create import costs
    pr, doc = project
    prop = next(p for p in doc["proposals"] if p["kind"] == "establishing")
    costs.set_cap(1)
    est = GN.estimate(pr, prop["id"])
    assert est["codes"][0]["code"] == "create.over-cap"
    with pytest.raises(CreateError):
        GN.generate(pr, prop["id"], est["id"], est["confirm_code"], est["max_cny"], code=prop["code"])
    assert fake.SUBMITS == []


def test_the_job_starts_from_her_footage(project):
    pr, doc = project
    prop = dict(next(p for p in doc["proposals"] if p["kind"] == "establishing"), mode="image-to-video",
                source=dict(clip=doc["plan"]["shots"][0]["clip"], t=2.0))
    job = GN.job_of(pr, prop)
    assert os.path.exists(job["refs"]["image_1"]) and job["prompt"].startswith("Start exactly on 图片1")
    assert job["aspect"] == "16:9" and job["kind"] == "video"


def test_cli_estimate_and_refusal_shape(project, capsys):
    from vstudio.brain import cli
    pr, doc = project
    prop = next(p for p in doc["proposals"] if p["kind"] == "establishing")
    assert cli.main(["estimate", "--dir", pr.dir, "--id", prop["id"], "--json"]) == 0
    est = json.loads(capsys.readouterr().out)
    assert est["ok"] and est["confirm_code"]
    assert cli.main(["generate", "--dir", pr.dir, "--id", prop["id"], "--estimate", est["id"], "--confirm",
                     "deadbeef", "--max-cny", str(est["max_cny"]), "--code", prop["code"], "--json"]) == 2
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["code"] == "create.confirm-mismatch"


def test_edl_joins_the_plan(project):
    from vstudio.brain import edl
    pr, doc = project
    out = os.path.join(pr.dir, "items", "v1", "work", "vlog_master.edl.json")
    rows = doc["plan"]["shots"]
    with open(out, "w") as f:
        json.dump(dict(builder="calm", duration=10, shots=[
            dict(i=0, t0=0, t1=5, src=rows[0]["clip"], src_in=1.0, src_out=6.0, brain=rows[0]["id"]),
            dict(i=1, t0=5, t1=10, src=rows[1]["clip"], src_in=1.0, src_out=6.0)]), f)
    d = edl.shots(pr, item="v1")
    assert d["shots"][0]["brain"]["id"] == rows[0]["id"]
    assert d["shots"][1]["brain"]["id"] == rows[1]["id"]                # matched by its source window
    assert d["shots"][0]["brain"]["why"] and d["shots"][0]["file"] == "a.mp4"
