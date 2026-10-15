"""Source/edited-clock provenance, real multi-canvas graphics and second-edit preservation."""
import shutil
import subprocess
import json

import numpy as np
import pytest

from vstudio import spoken
from vstudio.project import outfx


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("VSTUDIO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VSTUDIO_DEFAULT_PERSONA", "1")


CUES = [dict(start=i, end=i + 1, text=t) for i, t in enumerate([
    "这是我的经历。", "副业改变了我的想法。", "不只是收入。", "认识不同圈子的人。", "交流更深入。", "思路也更开阔。",
    "这对我很重要。", "这是新的可能。", "保持好奇。", "谢谢。", "结束。", "再见。"])]
BEAT = dict(**{"from": 3, "to": 5}, kind="chain", title="副业带来的变化",
            items=["认识新圈子", "交流更深入", "思路更开阔"], evidence="认识不同圈子的人。")


def test_plan_uses_actual_edited_cue_indices():
    seen = []
    def model(task, system, prompt, **kw):
        seen.append((task, prompt))
        return dict(provider="test", json=dict(beats=[BEAT]))
    plan = spoken.plan(CUES, 12, complete=model)
    assert seen[0][0] == "edit" and "[3] 3.000–4.000" in seen[0][1]
    assert plan["effects"][0]["start"] == 3 and plan["effects"][0]["end"] == 6
    assert plan["effects"][0]["params"]["kind"] == "chain"


@pytest.mark.parametrize("change", [{"from": -1}, {"from": True}, {"from": 0}, {"to": 100},
                                     {"evidence": "我赚了十万美元"}, {"title": "赚了100万元"},
                                     {"kind": "made-up"}, {"kind": "contrast"}, {"items": []}])
def test_rejects_unsupported_or_ungrounded_beats(change):
    with pytest.raises(ValueError):
        spoken.validate(dict(beats=[dict(BEAT, **change)]), CUES, 12)


@pytest.mark.parametrize("size", [(640, 360), (360, 640), (450, 600)])
def test_card_is_readable_seek_safe_and_animated_on_each_canvas(size):
    w, h = size
    inst = spoken.validate(dict(beats=[BEAT]), CUES, 12)[0]
    safe = (w * .07, h * .07, w * .92, h * .9)
    layer = outfx.make_layer(inst, w, h, safe)
    base = np.full((h, w, 3), 80, np.uint8)
    frames = []
    for t in (0, .6, 1.5, .6, 2.5):
        frame = base.copy(); layer.draw(frame, t, 3); frames.append(frame)
    assert np.array_equal(frames[0], base)
    assert np.array_equal(frames[1], frames[3])  # seeking backwards does not accumulate transforms
    assert not np.array_equal(frames[1], frames[2])
    assert np.mean(np.abs(frames[2].astype(float) - base)) > 30
    assert all(x >= 0 and y >= 0 and x + bw <= w and y + bh <= h * .76
               for x, y, bw, bh in layer.boxes)


def test_pipeline_second_edits_keep_and_can_remove_recipe_graphics(tmp_path):
    from vstudio.project.outputs import Doc
    source = tmp_path / "video.mp4"; source.write_bytes(b"source signature")
    effect = spoken.validate(dict(beats=[BEAT]), CUES, 12)[0]
    rec = dict(file=str(source), id="x", owner=str(tmp_path), kind="project", mode="pipeline",
               edit_dir=str(tmp_path / "edits"), baseline_effects=[effect])
    doc = Doc(rec)
    assert doc.state()["effects"] == [effect]
    doc.d["steps"] = [dict(id="s1", ops=[dict(op="effect_remove", id=effect["id"])])]
    assert doc.state()["effects"] == []
    assert rec["baseline_effects"] == [effect]
    doc.d["steps"].append(dict(id="s2", ops=[dict(op="reset")]))
    assert doc.state()["effects"] == [effect]
    rec["mode"] = "flattened"
    assert Doc(rec).state()["effects"] == []  # a flattened file already contains its graphics


def test_finishing_stage_uses_proofread_captions_and_routes_into_export(tmp_path, monkeypatch):
    from vstudio.batch import stages
    from vstudio.batch.recipes import Ctx
    raw = tmp_path / "raw.json"; raw.write_text(json.dumps(dict(cues=[dict(start=0, end=1, text="wrong")])))
    proof = tmp_path / "proof.json"; proof.write_text(json.dumps(dict(cues=CUES), ensure_ascii=False))
    params = dict(finishing="editorial", title="我的经历")
    ctx = Ctx(dict(params=params), {}, str(tmp_path),
              dict(compose=dict(cues=str(raw), duration=12), proofread=dict(cues=str(proof))), str(tmp_path))
    got = []
    real_plan = spoken.plan
    def local_plan(cues, duration, title):
        got.extend(cues)
        return real_plan(cues, duration, title, complete=lambda *a, **kw: dict(json=dict(beats=[BEAT])))
    monkeypatch.setattr(spoken, "plan", local_plan)
    # The stage uses the same planner implementation; only the external text-model boundary is replaced.
    result = stages.run_finish(ctx)
    assert got == CUES
    assert result["effects"][0]["params"]["items"] == BEAT["items"]
    assert json.loads((tmp_path / "editorial-plan.json").read_text())["effects"] == result["effects"]
    dag = {s.name: s for s in stages.speech_stages()}
    assert "finish" in dag["export"].deps and dag["finish"].enabled(ctx.job, {})
    assert not dag["finish"].enabled(dict(params={}), {})


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_real_export_draws_graphics_even_with_captions_off_and_watermark_on(tmp_path, monkeypatch):
    import cv2
    from vstudio import export, platform, watermark
    source = tmp_path / "source.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x304050:s=640x360:r=15:d=8",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=8", "-c:v", "libx264", "-preset", "ultrafast",
                    "-c:a", "aac", "-shortest", str(source)], check=True)
    # Real watermark callback with a tiny test image; this previously eligible fast path must still draw effects.
    from PIL import Image
    mark = tmp_path / "mark.png"; Image.new("RGBA", (30, 10), (30, 180, 140, 255)).save(mark)
    monkeypatch.setattr(watermark, "resolve", lambda *a, **k: dict(kind="image", image=str(mark)))
    prof = platform.profile("youtube", "horizontal", overrides=dict(w=640, h=360, safe=dict(left=25, right=25, top=20, bottom=20)))
    effect = spoken.validate(dict(beats=[BEAT]), CUES, 12)[0]
    out = tmp_path / "out"; out.mkdir()
    result = export.export_one(str(source), prof, str(out), captions=False, watermark=True,
                               effects=[effect], encoder="libx264", preset="ultrafast", mode="letterbox")
    cap = cv2.VideoCapture(str(out / result["file"]))
    cap.set(cv2.CAP_PROP_POS_MSEC, 1000); ok1, before = cap.read()
    cap.set(cv2.CAP_PROP_POS_MSEC, 4500); ok2, during = cap.read(); cap.release()
    assert ok1 and ok2 and during.mean() > before.mean() + 50
    from vstudio import media
    assert media.probe(str(out / result["file"]))["has_audio"]
    from vstudio.batch.qc import run_gates
    man = tmp_path / "manifest.json"; man.write_text(json.dumps(dict(exports=[result])))
    cues = tmp_path / "cues.json"; cues.write_text(json.dumps(dict(cues=[])))
    report = run_gates(dict(id="sample", recipe="longform-slices", params=dict(finishing="editorial")),
                       dict(qc=dict(verify=False)), dict(compose=dict(cues=str(cues)),
                       export=dict(manifest=str(man), exports=[dict(result, file=str(out / result["file"]))])))
    assert next(c for c in report["checks"] if c["name"] == "flicker")["ok"]


def test_invalid_external_plan_is_repaired_with_original_caption_context():
    calls = []
    def model(task, system, prompt, **kw):
        calls.append(prompt)
        return dict(json=dict(beats=[dict(BEAT, **({"from": 0} if len(calls) == 1 else {}))]),
                    provider="test", model="test")
    result = spoken.plan(CUES, 12, complete=model)
    assert result["effects"][0]["start"] == 3
    assert len(calls) == 2 and result["repairs"]
    assert "VALIDATION ERROR" in calls[1] and "[3] 3.000–4.000" in calls[1]


def test_invalid_plan_never_counts_as_applied_after_repair_limit():
    calls = []
    def model(*a, **kw):
        calls.append(a)
        return dict(json=dict(beats=["bad beat"]))
    with pytest.raises(ValueError, match="still invalid after one repair"):
        spoken.plan(CUES, 12, complete=model)
    assert len(calls) == 2


@pytest.mark.parametrize("texts,kind,title,items", [
    (["Start with the request.", "Then the server responds."], "chain", "Request / response", ["Request", "Response"]),
    (["录课先讲输入", "再演示输出"], "chain", "输入与输出", ["输入", "输出"]),
    (["The demo shows a saved draft.", "It does not show a published post."], "contrast", "What is demonstrated", ["Saved draft", "Publishing unverified"]),
    (["这是我的面试经历", "不代表每个人都一样"], "takeaway", "个人经历", ["结果因人而异"]),
])
def test_same_contract_accepts_different_topics_and_supplied_qualifiers(texts, kind, title, items):
    cues = [dict(start=0, end=3, text="Opening"), dict(start=3, end=5, text=texts[0]),
            dict(start=5, end=7, text=texts[1]), dict(start=7, end=10, text="Ending")]
    beat = dict(**{"from": 1, "to": 2}, kind=kind, title=title, items=items, evidence=texts[0])
    result = spoken.plan(cues, 10, complete=lambda *a, **kw: dict(json=dict(beats=[beat])))
    assert result["effects"][0]["params"]["items"] == items
    assert result["repairs"] == []


def test_provider_failure_does_not_trigger_a_plan_repair():
    calls = []
    def model(*a, **kw):
        calls.append(a)
        raise RuntimeError("AI login expired")
    with pytest.raises(RuntimeError, match="AI login expired"):
        spoken.plan(CUES, 12, complete=model)
    assert len(calls) == 1
