"""vstudio.brain: template classifier, per-shot treatment planner, generation proposals, the project store.

No media work: analyses, tiles and projects are built by hand; prices come from the real rate card."""
import pytest

from vstudio.brain import genplan as G
from vstudio.brain import presets as P
from vstudio.brain import store as ST
from vstudio.brain import template as T
from vstudio.brain import treat as TR


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("VSTUDIO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "VSTUDIO_LLM_PROVIDER"):
        monkeypatch.delenv(k, raising=False)


# --------------------------------------------------------------------------- analyses
def _vid(i, dur=40, speech=False, name=None, **kw):
    return dict(id=f"f{i}", path=f"/x/{name or f'DJI_2026062220590{i}_000{i}_D.MP4'}", rel=name or f"c{i}.mp4",
                kind="video", duration=dur, speech=speech, speech_s=dur * 0.9 if speech else 0.0,
                orientation="horizontal", talking_head=False, multi_person=False, screen_share=False, **kw)


def _an(*files):
    return dict(files=list(files))


def _drone(n=6, dur=40):
    fs = [_vid(i, dur) for i in range(1, n + 1)]
    fs.append(dict(id="t1", path="/x/DJI_0001.SRT", kind="text", shape="telemetry"))
    return _an(*fs)


def test_drone_footage_no_words_is_a_calm_film_by_the_rules():
    d = T.classify(T.signals(_drone(), ""))
    assert d["template"] == "travel-calm" and d["recipe"] == "vlog" and d["by"] == "rules"
    assert "drone" in d["reason"]["en"] and "无人机" in d["reason"]["zh"]
    assert d["alternatives"] and all(a["id"] != "travel-calm" for a in d["alternatives"])


@pytest.mark.parametrize("prompt,want", [
    ("Make a 35-second upbeat summer short: fast cuts on the beat, energetic music, no voice.", "beat-short"),
    ("做一条卡点快剪", "beat-short"),
    ("Make a 90-second history explainer over these night drone shots; state only verifiable facts.",
     "history-explainer"),
    ("A 45-second vertical autumn essay: a calm, high-end reflective voice-over about letting go.", "essay"),
    ("Make a 75-second road-trip vlog with place and time captions.", "trip-vlog"),
])
def test_her_words_pick_the_template(prompt, want):
    d = T.classify(T.signals(_drone(), prompt))
    assert d["template"] == want and d["by"] == "her"


def test_speech_materials():
    th = _an(_vid(1, 300, speech=True, name="talk.mp4", ))
    th["files"][0]["talking_head"] = True
    assert T.classify(T.signals(th, ""))["template"] == "th-refined"
    call = _an(_vid(1, 1800, speech=True, name="zoom.mp4"))
    call["files"][0]["multi_person"] = True
    assert T.classify(T.signals(call, ""))["template"] == "conversation-clips"
    lec = _an(_vid(1, 3600, speech=True, name="lesson.mp4"))
    lec["files"][0]["screen_share"] = True
    assert T.classify(T.signals(lec, ""))["template"] == "lecture-shorts"
    docs = _an(dict(id="d1", path="/x/notes.md", kind="text", shape="article"))
    assert T.classify(T.signals(docs, ""))["template"] == "concept-explainer"


def test_words_never_pick_what_the_materials_cannot_make():
    # "口播" over silent drone footage: no speech to cut, so it stays a footage film
    d = T.classify(T.signals(_drone(), "口播精剪"))
    assert d["recipe"] == "vlog"


def test_fixed_recipe_and_keep():
    d = T.classify(T.signals(_drone(), "fast cuts on the beat"), fixed_recipe="photo-story")
    assert d["recipe"] == "photo-story"
    k = T.classify(T.signals(_drone(), ""), keep="beat-short")
    assert k["template"] == "beat-short" and k["by"] == "her" and k["confidence"] == 1.0
    assert T.classify(T.signals(_drone(), ""), fixed_recipe="polish") is None


def test_close_call_goes_to_the_judge_and_a_bad_judge_is_ignored():
    s = T.signals(_drone(), "")
    s["aerial"] = False                                   # travel-calm 1.0 vs trip-vlog 0.6 ... make it close
    sc = T.scores(s)
    assert sc["travel-calm"][0] > sc["trip-vlog"][0]
    seen = []
    T.AMBIGUOUS, old = 0.9, T.AMBIGUOUS
    try:
        d = T.classify(s, judge=lambda s_, c: seen.append(c) or dict(pick="trip-vlog", reason="a trip in time order"))
        assert seen and d["template"] == "trip-vlog" and d["by"] == "ai" and "trip" in d["reason"]["en"]
        d = T.classify(s, judge=lambda s_, c: dict(pick="not-a-template"))
        assert d["template"] == "travel-calm" and d["by"] == "rules"

        def boom(s_, c):
            raise RuntimeError("no model")
        assert T.classify(s, judge=boom)["by"] == "rules"
    finally:
        T.AMBIGUOUS = old


def test_ai_judge_reads_the_routed_model():
    calls = []

    def complete(task, system, prompt, **kw):
        calls.append((task, prompt))
        return dict(provider="fake", json=dict(pick="trip-vlog", reason="ok"))
    j = T.ai_judge(complete=complete)
    assert j(T.signals(_drone(), ""), ["travel-calm", "trip-vlog"])["pick"] == "trip-vlog"
    assert calls[0][0] == "planner"
    assert T.ai_judge(complete=lambda *a, **k: dict(provider="none"))(T.signals(_drone(), ""), ["x"]) is None


def test_goal_kinds_map_to_templates():
    from vstudio.intake import goal
    for k in P.GOAL_KINDS:
        assert goal.RECIPE[k] == P.for_goal_kind(k)["recipe"]
    assert P.for_goal_kind("reel")["id"] == "beat-short"


# --------------------------------------------------------------------------- intake: the plan carries the template
def test_plan_project_gets_template_and_english_style(tmp_path):
    from vstudio.intake import plan as PL
    an = _drone(4)
    for f in an["files"]:
        p = tmp_path / f["path"].lstrip("/").replace("/", "_")
        p.write_bytes(b"x")
        f["path"] = str(p)
        f.setdefault("rel", p.name)
    p = dict(recipe="vlog", materials=[f["id"] for f in an["files"]], params={})
    PL.attach_template(p, an, "Make a 35-second upbeat summer short: fast cuts on the beat, no voice.")
    assert p["template"]["id"] == "beat-short" and p["template"]["by"] == "her"
    assert p["params"]["style"] == "fun" and p["param_sources"]["style"] == "template"
    q = dict(recipe="vlog", materials=[], params={"style": "calm"})
    PL.attach_template(q, an, "fast cuts on the beat")
    assert q["params"]["style"] == "calm"                # a style already set is never replaced
    r = dict(recipe="polish", materials=[], params={})
    PL.attach_template(r, an, "")
    assert "template" not in r


def test_history_explainer_over_footage_is_a_photo_story():
    from vstudio.intake import rules as R
    intent = R.parse_prompt("Make a 90-second history explainer over these drone shots")
    an = dict(files=[dict(id="f1", path="/x/a.mp4", kind="video", duration=60, speech=False)])
    assert [r for r, _ in R.choose_recipes(intent, an)] == ["photo-story"]


# --------------------------------------------------------------------------- treatment
def _tile(i, clip="a", t0=0.0, dur=12.0, **kw):
    base = dict(id=f"C{i}.S1", clip=f"/x/{clip}.mp4", file=f"{clip}.mp4", start=t0, end=t0 + dur,
                best=[t0 + 2, t0 + 6], t=t0 + 4, score=0.8, sharp=0.8, steady=0.85, exposure=0.8, jitter_px=0.3,
                pan_px_s=20.0, motion=3.0, bright=0.45, lab=[120.0, 128.0, 130.0], faces=0, subject_frac=0.5,
                subject_xy=[0.5, 0.5], src_fps=30.0, w=3840, h=2160, time_of_day="evening", city="Seattle")
    base.update(kw)
    return base


def test_calm_film_dissolves_where_the_light_changes_and_cuts_where_it_does_not():
    ts = [_tile(1, "a"), _tile(2, "b"), _tile(3, "c", bright=0.12, exposure=0.5, lab=[60.0, 128, 140],
                                              time_of_day="night", score=0.7)]
    pl = TR.plan(ts, "travel-calm")
    rows = {r["id"]: r for r in pl["shots"]}
    assert rows["C1.S1"]["transition"]["kind"] == "open"
    assert rows["C2.S1"]["transition"]["kind"] in ("cut", "match-cut")
    assert rows["C3.S1"]["transition"]["kind"] == "dissolve" and rows["C3.S1"]["transition"]["s"] == 0.8
    assert any("evening → night" in w["en"] for w in rows["C3.S1"]["why"])
    assert pl["summary"]["checks"]["no_flash"]
    lo, hi = P.get("travel-calm")["policy"]["hold"]
    assert all(lo <= r["hold_s"] <= hi or r["hold_s"] == r["end"] - r["start"] for r in pl["shots"] if not r["skip"])


def test_slow_motion_only_with_an_even_cadence():
    moving = dict(motion=12.0, steady=0.9)
    p30 = TR.plan([_tile(1, **moving, dur=5.0)], "travel-calm", rife=False)
    assert p30["shots"][0]["speed"] == "normal"            # 30p at 0.5x judders: no
    p60 = TR.plan([_tile(1, src_fps=59.94, dur=5.0, **moving)], "travel-calm", rife=False)
    assert p60["shots"][0]["speed"] == "slowmo" and p60["shots"][0]["speed_x"] == 0.5
    prife = TR.plan([_tile(1, dur=5.0, **moving)], "travel-calm", rife=True)
    assert prife["shots"][0]["speed"] == "slowmo" and "RIFE" in prife["shots"][0]["why"][2]["en"]
    shaky = TR.plan([_tile(1, src_fps=60.0, motion=12.0, steady=0.4, dur=5.0)], "travel-calm")
    assert shaky["shots"][0]["speed"] == "normal"


def test_beat_short_ramps_once_and_cuts_on_the_beat():
    ts = [_tile(i, f"c{i}", motion=4.0 + i, src_fps=60.0) for i in range(1, 7)]
    pl = TR.plan(ts, "beat-short", beats=True)
    used = [r for r in pl["shots"] if not r["skip"]]
    assert sum(r["speed"] == "ramp" for r in used) == 1
    assert {r["transition"]["kind"] for r in used[1:]} <= {"beat-cut", "match-cut"}


def test_bad_shots_are_skipped_and_say_why():
    ts = [_tile(1), _tile(2, "b", score=0.2, sharp=0.1, steady=0.1),
          _tile(3, "c", bright=0.08, exposure=0.2, score=0.4)]
    rows = {r["id"]: r for r in TR.plan(ts, "travel-calm")["shots"]}
    assert rows["C2.S1"]["skip"] and rows["C2.S1"]["why"][0]["code"] == "low-quality"
    assert rows["C3.S1"]["skip"] and rows["C3.S1"]["why"][0]["code"] == "too-dark"


def test_a_night_film_keeps_its_dark_shots():
    ts = [_tile(i, f"c{i}", bright=0.12, exposure=0.3, score=0.62) for i in range(1, 5)] + [_tile(5, "dusk", bright=0.45)]
    rows = {r["id"]: r for r in TR.plan(ts, "history-explainer", target_s=30)["shots"]}
    assert not any(w["code"] == "too-dark" for r in rows.values() for w in r["why"])
    assert sum(not r["skip"] for k, r in rows.items() if k != "C5.S1") >= 2


def test_target_length_keeps_the_best_shots():
    ts = [_tile(i, f"c{i}", score=0.5 + i * 0.05, sharp=0.3 + i * 0.08) for i in range(1, 9)]
    pl = TR.plan(ts, "travel-calm", target_s=30)
    used = [r for r in pl["shots"] if not r["skip"]]
    assert 25 <= pl["summary"]["seconds"] <= 45 and len(used) < 8
    assert all(r["id"] in {u["id"] for u in used} for r in pl["shots"] if r["score"] >= 0.9)


def test_reframe_follows_faces_or_subjects_for_a_vertical_output():
    ts = [_tile(1, faces=1), _tile(2, "b", subject_spread=0.1, subject_xy=[0.7, 0.5]), _tile(3, "c", subject_spread=0.35)]
    rows = [r for r in TR.plan(ts, "travel-calm", out_aspect="9:16")["shots"]]
    assert [r["reframe"] for r in rows] == ["follow-face", "follow-subject", "centre"]
    assert all(r["reframe"] == "none" for r in TR.plan(ts, "travel-calm")["shots"])


def test_talking_head_jump_cuts_morph_with_rife_else_punch_in():
    ts = [_tile(1, "talk", 0, 20, faces=1, face_area=0.08, speech=1.0), _tile(2, "talk", 22, 15, faces=1, face_area=0.082, speech=1.0)]
    ts[1]["id"] = "C1.S2"
    cont = [dict(ts[0], id="C1.S1.1"), dict(ts[1], id="C1.S1.2", start=20.0)]      # one shot played on
    cut_in_source = [dict(ts[0]), dict(ts[1], start=20.0)]                          # the recording cuts there
    assert TR.plan(cut_in_source, "th-refined", rife=True)["shots"][1]["transition"]["kind"] == "morph"
    assert TR.plan(cont, "th-refined", rife=True)["shots"][1]["transition"]["kind"] == "continuous"
    with_rife = TR.plan(ts, "th-refined", rife=True)["shots"][1]
    assert with_rife["transition"]["kind"] == "morph" and with_rife["hold_s"] == 15
    without = TR.plan(ts, "th-refined", rife=False)["shots"][1]
    assert without["transition"]["kind"] == "morph-fallback" and without["punch_in"] == "jump-cover"
    calm = TR.plan(ts, "travel-calm", rife=True)["shots"]
    assert all(r.get("punch_in") in (None, "none") for r in calm)        # no punch-ins in a footage film


def test_close_calls_go_to_the_judge_and_her_changes_win():
    ts = [_tile(1), _tile(2, "b", bright=0.35, lab=[112.0, 128, 131])]
    seen = []

    def judge(rows):
        seen.extend(r["id"] for r in rows)
        return {r["id"]: dict(transition="dissolve", reason="the mood shifts") for r in rows}
    pl = TR.plan(ts, "travel-calm", judge=judge)
    if seen:
        r = next(x for x in pl["shots"] if x["id"] == seen[0])
        assert r["by"] == "ai" and r["transition"]["kind"] == "dissolve"
    pl = TR.plan(ts, "travel-calm", overrides={"C2.S1": dict(transition="cut", speed="normal")})
    r = pl["shots"][1]
    assert r["by"] == "her" and r["transition"]["kind"] == "cut"


# --------------------------------------------------------------------------- generation proposals
def test_weak_only_shot_short_footage_and_cover():
    ts = [_tile(1), _tile(2, "b", score=0.2, bright=0.1, sharp=0.1, steady=0.2, exposure=0.2)]
    pl = TR.plan(ts, "travel-calm", target_s=60)
    props = G.propose("travel-calm", pl, dict(videos=2, aerial=True), stage="cut", target_s=60, tiles=ts)
    kinds = [x["kind"] for x in props]
    assert kinds[0] == "weak" and "short" in kinds
    weak = props[0]
    assert weak["mode"] == "image-to-video" and weak["source"]["clip"] == "/x/b.mp4"
    assert weak["status"] == "proposed" and weak["ai_label"] is True
    assert weak["provider"] == "kling-mcp" and weak["estimate"]["cny"] and weak["estimate"]["cny"] > 0
    assert G.total(props)["cny"] > 0
    assert props[0]["id"] == G.propose("travel-calm", pl, dict(videos=2, aerial=True), "cut", target_s=60,
                                       tiles=ts)[0]["id"]       # stable ids: her answers stick


def test_establishing_shot_when_the_film_opens_close():
    ts = [_tile(1, faces=1), _tile(2, "b", faces=2)]
    pl = TR.plan(ts, "trip-vlog")
    props = G.propose("trip-vlog", pl, dict(videos=2, aerial=False), stage="planned", place="Kyoto", tiles=ts)
    est = [x for x in props if x["kind"] == "establishing"]
    assert est and "Kyoto" in est[0]["prompt"] and est[0]["mode"] == "text-to-video"
    assert not [x for x in G.propose("trip-vlog", pl, dict(videos=2, aerial=True), "planned", tiles=ts)
                if x["kind"] == "establishing"]


def test_bridge_only_in_a_narrated_piece_across_a_place_change():
    ts = [_tile(1), _tile(2, "b", city="Kyoto", time_of_day="night", bright=0.15, exposure=0.5, lab=[60.0, 128, 140])]
    pl = TR.plan(ts, "history-explainer")
    assert [x["kind"] for x in G.propose("history-explainer", pl, {}, "cut", tiles=ts)].count("bridge") == 1
    pl2 = TR.plan(ts, "travel-calm")
    assert "bridge" not in [x["kind"] for x in G.propose("travel-calm", pl2, {}, "cut", tiles=ts)]


def test_broll_for_a_long_talking_head_stretch():
    sents = [dict(start=k * 6.0, end=k * 6.0 + 5.5, text=f"sentence {k} about attention heads") for k in range(40)]
    props = G.propose("th-refined", dict(shots=[dict(_tile(1, "talk", 0, 60, faces=1), skip=False, why=[],
                                                     transition=dict(kind="open"), hold_s=60)]),
                      {}, stage="cut", sentences=sents)
    b = [x for x in props if x["kind"] == "broll"]
    assert len(b) == 3 and "attention heads" in b[0]["prompt"] and "sentence" in b[0]["prompt"]


def test_confirm_code_follows_the_price():
    x = dict(id="g1", provider="kling-mcp", model="m", seconds=5, estimate=dict(cny=5.0))
    y = dict(x, estimate=dict(cny=7.5))
    assert G.confirm_code(x) != G.confirm_code(y)


# --------------------------------------------------------------------------- the project store
@pytest.fixture
def project(tmp_path, monkeypatch):
    from vstudio.project.core import Project
    clips = []
    for k in range(2):
        c = tmp_path / f"DJI_2026062220590{k}_000{k}_D.MP4"
        c.write_bytes(b"x")
        clips.append(str(c))
    pr = Project.create(str(tmp_path / "proj"), recipe="vlog", inputs=dict(footage=clips))
    pr.data["prompt"] = "Make a 30-second calm film from these drone shots."
    pr.save()
    an = _drone(2)
    for f, c in zip([f for f in an["files"] if f["kind"] == "video"], clips):
        f["path"] = c
    ts = [_tile(1, clip=clips[0].rsplit("/", 1)[1][:-4]), _tile(2, clip="x", score=0.2, bright=0.1)]
    ts[0]["clip"], ts[1]["clip"] = clips[0], clips[1]
    monkeypatch.setattr(ST, "_signals", lambda project, paths, refresh=False, light=False: (T.signals(an, project.data["prompt"]), []))
    monkeypatch.setattr(ST, "_tiles", lambda project, paths, refresh=False, echo=None: ts)
    return pr


def test_store_show_change_and_decide(project):
    from vstudio.project.core import Project
    doc = ST.show(project)
    assert doc["template"]["template"] == "travel-calm" and doc["stage"] == "cut"
    assert all(a["recipe"] == "vlog" for a in doc["template"]["alternatives"])
    assert doc["plan"]["summary"]["used"] >= 1 and doc["decisions"][0]["kind"] == "template"
    assert doc["proposals"] and doc["cost"]["cny"] > 0
    with pytest.raises(ST.BrainError):
        ST.set_template(project, "th-refined")              # another recipe: a new project, not a switch
    ST.set_template(project, "beat-short")
    pr = Project(project.dir)
    assert pr.data["brain"]["template"]["by"] == "her" and pr.data["params"]["style"] == "fun"
    doc = ST.show(pr)
    assert doc["template"]["template"] == "beat-short" and doc["template"]["by"] == "her"
    sid = next(r["id"] for r in doc["plan"]["shots"] if not r["skip"])
    ST.set_shot(pr, sid, transition="cut")
    with pytest.raises(ST.BrainError):
        ST.set_shot(pr, sid, transition="glitch")
    doc = ST.show(Project(project.dir))
    assert next(r for r in doc["plan"]["shots"] if r["id"] == sid)["by"] == "her"
    g = doc["proposals"][0]
    with pytest.raises(ST.BrainError):
        ST.decide_gen(Project(project.dir), g["id"], "approve", code="nope")
    r = ST.decide_gen(Project(project.dir), g["id"], "approve", code=g["code"])
    assert r["status"] == "approved"
    doc = ST.show(Project(project.dir))
    got = next(x for x in doc["proposals"] if x["id"] == g["id"])
    assert got["status"] == "approved" and got["by"] == "her"
    assert doc["cost"]["n"] == len([x for x in doc["proposals"] if x["status"] == "proposed"])
    ST.decide_gen(Project(project.dir), g["id"], "skip")
    assert next(x for x in ST.show(Project(project.dir))["proposals"] if x["id"] == g["id"])["status"] == "skipped"


def test_plan_template_carries_into_the_project(project):
    from vstudio.project.core import Project
    project.data["brain"] = dict(template=dict(id="trip-vlog", by="rules", reason=dict(en="planned", zh="计划")))
    project.save()
    doc = ST.show(Project(project.dir))
    assert doc["template"]["template"] == "trip-vlog" and doc["template"]["reason"]["en"] == "planned"
    assert doc["template"]["alternatives"][0]["id"] == "travel-calm"


def test_autopilot_never_approves_generation():
    import inspect
    from vstudio.project import autopilot
    assert "decide_gen" not in inspect.getsource(autopilot) and "brain" not in inspect.getsource(autopilot)


def test_target_seconds():
    assert ST.target_seconds("Make a 90-second film") == 90
    assert ST.target_seconds("a 2-minute history explainer") == 120
    assert ST.target_seconds("做一条 45 秒的") == 45
    assert ST.target_seconds("两分钟的片子") == 120
    assert ST.target_seconds("no length") is None


def test_cli_presets_and_shot_validation(project, capsys):
    from vstudio.brain import cli
    assert cli.main(["presets", "--json"]) == 0
    assert "travel-calm" in capsys.readouterr().out
    assert cli.main(["shot", "--dir", project.dir, "--id", "C1.S1", "--set", "speed=warp", "--json"]) == 2


def test_calm_vlog_drafter_reads_the_shot_plan(tmp_path, monkeypatch):
    from vstudio.project.adapters import vlog as V
    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    a.write_bytes(b"x")
    b.write_bytes(b"x")
    doc = dict(template=dict(label="Calm travel film"), plan=dict(shots=[
        dict(id="C1.S1", clip=str(a), skip=False, use=[3.0, 13.0], speed="normal", transition=dict(kind="open"),
             why=[dict(code="open", en="opens the film")]),
        dict(id="C2.S1", clip=str(b), skip=True, why=[]),
        dict(id="C2.S2", clip=str(b), skip=False, use=[20.0, 25.0], speed="slowmo", transition=dict(kind="dissolve"),
             why=[dict(code="dissolve", en="the light changes")])]))
    monkeypatch.setattr(ST, "show", lambda project, light=False: doc)
    monkeypatch.setattr("vstudio.project.core.Project", lambda d: object())

    class Ctx:
        project_dir = str(tmp_path)
    line, picks = V.brain_plan(Ctx(), {"c1": str(a), "c2": str(b)})
    assert picks == [dict(clip="c1", start=3.0, dur=10.0), dict(clip="c2", start=20.0, dur=5.0)]
    assert "c2 20.0-25.0s (dissolve, slow motion: the light changes)" in line and "Calm travel film" in line
    monkeypatch.setattr(ST, "show", lambda project, light=False: (_ for _ in ()).throw(RuntimeError("no shots")))
    assert V.brain_plan(Ctx(), {"c1": str(a)}) == ("", [])


def test_calm_aerials_join_with_dissolves_and_a_beat_short_never_does():
    ts = [_tile(1, "a", aerial=True), _tile(2, "b", aerial=True)]
    assert TR.plan(ts, "travel-calm")["shots"][1]["transition"]["kind"] == "dissolve"
    assert TR.plan(ts, "trip-vlog")["shots"][1]["transition"]["kind"] in ("cut", "match-cut")
    assert TR.plan(ts, "beat-short", beats=True)["shots"][1]["transition"]["kind"] in ("beat-cut", "match-cut")


def test_a_change_of_framing_stays_a_clean_cut():
    ts = [_tile(1, "talk", 0, 20, faces=1, face_area=0.05, speech=1.0),
          _tile(2, "talk", 20, 15, faces=1, face_area=0.11, speech=1.0)]
    ts[1]["id"] = "C1.S2"
    r = TR.plan(ts, "th-refined", rife=True)["shots"][1]
    assert r["transition"]["kind"] == "cut" and r["punch_in"] == "none"
