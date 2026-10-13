"""Her hand edits survive the AI (vstudio.project.outputs overrides): what she changes in the clip editor is an
override an AI chat edit / the project AI never changes unless she points at it, the model is told about, a new
file of the output (a re-run, Redo the visuals) re-applies, and that goes back to the AI version one key at a time.
Synthetic media, mocked model."""
import os
import shutil

import pytest

from test_output_edit import _iso, _work, synth  # noqa: F401  (fixtures)
from vstudio import llm
from vstudio.project import outputs as O
from vstudio.project import projai as PA

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


def _fake(monkeypatch, ops, seen=None):
    monkeypatch.setenv("VSTUDIO_LLM_OUTPUT_EDIT_PROVIDER", "claude-code")

    def complete(task, system, prompt, schema=None, provider=None, model=None, **kw):
        if seen is not None:
            seen.update(system=system, prompt=prompt)
        return dict(text="", json=dict(summary="ok", ops=ops), usage={}, cost_usd=0.0, provider="claude-code",
                    model="m")
    monkeypatch.setattr(llm, "complete", complete)


def _keys(w, oid):
    return {o["key"] for o in O.show(w, oid)["overrides"]}


def test_hand_edits_are_overrides_the_ai_keeps(tmp_path, synth, monkeypatch):  # noqa: F811
    w, oid = _work(tmp_path, synth)
    # the AI made a title first; she then edits by hand
    O.edit(w, oid, [dict(op="title", text="AI title")], by="ai")
    assert _keys(w, oid) == set()
    O.edit(w, oid, [dict(op="title", text="My title"),
                    dict(op="effect_add", effect="pop-words", start=1.0, params=dict(text="重点")),
                    dict(op="caption_add", start=0.5, end=1.5, text="新的字幕"),
                    dict(op="caption_style", style=dict(color="#FFD60A"))])
    s = O.show(w, oid)
    fx = s["state"]["effects"][0]["id"]
    cue = s["state"]["captions"]["added"][0]["id"]
    ov = {o["key"]: o for o in s["overrides"]}
    assert set(ov) == {"title", f"effect:{fx}", f"caption:{cue}", "caption_style:color"}
    assert ov[f"effect:{fx}"]["added"] and not ov["title"]["added"]
    assert all(o["label"]["code"].startswith("override-") for o in ov.values())

    seen = {}
    _fake(monkeypatch, [dict(op="title", text="Punchier"),                       # hers: dropped
                        dict(op="effect_update", id=fx, params=dict(text="别的")),  # hers: dropped
                        dict(op="caption_style", style=dict(size=1.3)),           # a field she did not touch: kept
                        dict(op="speed", value=1.2),                              # not hers: kept
                        dict(op="reset")], seen)                                  # would wipe hers: dropped
    r = O.ai(w, oid, "make it punchier")
    assert [p["normalized"]["op"] for p in r["proposed"]] == ["caption_style", "speed"]
    assert [d["error"]["code"] for d in r["dropped"]] == ["user-override"] * 3
    # the model is told what she changed
    assert "her_edits" in seen["prompt"] and "caption_style:color" in seen["prompt"] and "her_edits" in seen["system"]

    # she points at the effect: then the AI may change that one
    _fake(monkeypatch, [dict(op="effect_update", id=fx, params=dict(text="别的"))])
    r = O.ai(w, oid, "change this word", context=dict(effect=fx))
    assert [p["normalized"]["op"] for p in r["proposed"]] == ["effect_update"]

    # a theme keeps her colours
    _fake(monkeypatch, [dict(op="theme", theme="mono")])
    r = O.ai(w, oid, "more premium")
    assert r["proposed"][0]["normalized"]["restyle"] is False
    assert any(x and x["code"] == "theme-kept-yours" for x in r["proposed"][0]["warnings"])

    # the project AI drops the same ops
    rec, doc = O._load(w, oid)
    prop, drop = PA._validate(doc, doc.state(), [dict(op="title", text="x"), dict(op="speed", value=1.1)])
    assert [p["normalized"]["op"] for p in prop] == ["speed"] and drop[0]["error"]["code"] == "user-override"
    assert PA._summary(rec, doc, doc.state())["her_edits"]


def test_reset_to_the_ai_version_one_key_at_a_time(tmp_path, synth):  # noqa: F811
    w, oid = _work(tmp_path, synth)
    O.edit(w, oid, [dict(op="title", text="AI title"), dict(op="caption_add", start=0.5, end=1.5, text="字幕"),
                    dict(op="caption_style", style=dict(size=1.0, color="#FFFFFF"))], by="ai")
    O.edit(w, oid, [dict(op="title", text="My title"), dict(op="caption_style", style=dict(size=1.4, color="#FF0000"))])
    O.edit(w, oid, [dict(op="cover", t=1.0, text="封面")])
    assert _keys(w, oid) == {"title", "caption_style:size", "caption_style:color", "cover"}

    with pytest.raises(O.OutputError) as ei:
        O.edit(w, oid, dict(op="override_reset", key="speed"))
    assert ei.value.info["code"] == "unknown-override"

    r = O.edit(w, oid, dict(op="override_reset", key="caption_style:color"))
    st = r["state"]
    assert st["captions"]["style"]["color"] == "#FFFFFF" and st["captions"]["style"]["size"] == 1.4
    assert st["title"]["text"] == "My title"
    assert r["step"]["describe"][0]["code"] == "op-override-reset"
    assert {o["key"] for o in r["overrides"]} == {"title", "caption_style:size", "cover"}

    r = O.edit(w, oid, dict(op="override_reset", key="title"))
    assert r["state"]["title"]["text"] == "AI title"
    r = O.edit(w, oid, dict(op="override_reset", key="cover"))
    assert r["state"]["cover"] is None                  # no AI version: back to none
    # undo brings her edit back
    r = O.undo(w, oid)
    assert r["state"]["cover"]["text"] == "封面" and "cover" in {o["key"] for o in r["overrides"]}
    # a later AI step she applied takes the key over
    O.edit(w, oid, [dict(op="cover", t=2.0, text="AI 封面")], by="ai")
    assert "cover" not in _keys(w, oid)


def test_overrides_survive_a_new_file(tmp_path, synth):  # noqa: F811
    """A re-run / Redo the visuals writes a new file at the same output: her edits are re-applied to it."""
    w, oid = _work(tmp_path, synth)
    O.edit(w, oid, [dict(op="title", text="Mine"), dict(op="caption_add", start=0.5, end=1.5, text="字幕")])
    f = O.show(w, oid)["output"]["file"]
    import subprocess
    tmp = f + ".new.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", f, "-vf", "eq=brightness=0.05", "-c:a", "copy", tmp],
                   check=True)
    os.replace(tmp, f)
    O._PROBES.clear()
    s = O.show(w, oid)
    assert any(x["code"] == "source-changed" for x in s["warnings"])
    assert s["state"]["title"]["text"] == "Mine" and {o["key"] for o in s["overrides"]} >= {"title"}


def test_override_keys_and_strip():
    assert O.override_keys(dict(op="caption_style", style=dict(color="#fff", size=1.2))) == \
        ["caption_style:color", "caption_style:size"]
    assert O.override_keys(dict(op="cut", start=1, end=2)) == []
    assert O._without_keys(dict(op="caption_style", style=dict(color="#fff", size=1.2)), ["caption_style:color"]) == \
        dict(op="caption_style", style=dict(size=1.2))
    assert O._without_keys(dict(op="title", title=dict(text="x")), ["title"]) is None
    assert O.override_conflict(["effect:fx1"], {"effect:fx1"}, dict(effect="fx1")) == []
    assert O.override_conflict(["caption:c2"], {"caption:c2"}, dict(cues=["c3"])) == ["caption:c2"]
    assert "title" in O.overrides_note({"title"})


def test_item_overrides_reads_the_edit_documents(tmp_path, monkeypatch):
    ed = tmp_path / "e1"
    ed.mkdir()
    from vstudio.batch.util import write_json
    write_json(str(ed / "edit.json"), dict(steps=[
        dict(id="s1", by="ai", ops=[dict(op="title", title=dict(text="a"))]),
        dict(id="s2", by="user", ops=[dict(op="cover", cover=dict(t=1)), dict(op="caption_text", cue="c1", text="x",
                                                                               derived=True)])]))
    monkeypatch.setattr(O, "list_outputs", lambda d: dict(outputs=[
        dict(id="ep1/xhs", item="ep1", steps=2, edit_dir=str(ed)), dict(id="ep2/xhs", item="ep2", steps=0)]))
    assert O.item_overrides("P", "ep1") == {"ep1/xhs": ["cover"]}
    assert O.item_overrides("P", "ep2") == {}


def test_naming_the_part_lets_the_ai_change_it():
    st = dict(title=dict(text="副业复盘 01"), effects=[dict(id="fx1", effect="pop-words", params=dict(text="重点"))])
    assert O.named_in("把标题去掉", "title", st) and O.named_in("remove 副业复盘 from all", "title", st)
    assert not O.named_in("make it punchier", "title", st)
    assert O.named_in("把「重点」这个字换成别的", "effect:fx1", st) and O.named_in("fx1 bigger", "effect:fx1", st)
    assert O.named_in("字幕颜色换成白色", "caption_style:color", st)
    n = dict(op="title", title=None)
    assert O.guard_ai_op(n, {"title"}, instruction="make it punchier", st=st)[0] is None
    assert O.guard_ai_op(n, {"title"}, instruction="去掉标题", st=st)[0] is n
    assert O.guard_ai_op(dict(op="reset"), {"title"}, instruction="start over")[0] is not None
