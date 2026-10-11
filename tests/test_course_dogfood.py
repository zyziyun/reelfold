"""A course episode from her Notion lecture scripts (dogfood, 2026-10-10): Chinese narration in the explainer
(中文讲解), an exported Notion folder of 讲稿 planned as a course explainer (not a 剧本, not "add your recordings"),
the voice / script drafting fixes, and the Hedra AI presenter behind the spend gate (fake transport, no network).

    python3 -m pytest tests/test_course_dogfood.py -q
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXP = ROOT / "workflows" / "explainer" / "scripts"
sys.path.insert(0, str(ROOT / "lib"))

need_ff = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


def _imp(name):
    sys.path.insert(0, str(EXP))
    try:
        import importlib
        return importlib.import_module(name)
    finally:
        sys.path.pop(0)


ZH_SCRIPT = """# SCRIPT

## Line 1 — Hook (Frame 1)

    你有 3 个 AI 应用，要接 4 个工具。没有标准的话，就是 3 乘 4，
    12 份集成代码。它叫 MCP。

EN: Three apps, four tools, twelve integrations. It is called MCP.

## Line 2 — USB-C (Frame 2)

    MCP 是 AI 应用的 USB-C 接口。你写一个 MCP server，所有支持 MCP 的应用都能直接用它。
"""


# --------------------------------------------------------------------------- Chinese narration
def test_script_md_reads_chinese_narration(tmp_path):
    S = _imp("script_md")
    p = tmp_path / "SCRIPT.md"
    p.write_text(ZH_SCRIPT, encoding="utf-8")
    L = S.parse_script(p)
    assert [x["lang"] for x in L] == ["zh", "zh"] and S.narration_lang(L) == "zh"
    # wrapped Chinese lines join without a space; the narration is also the caption
    assert L[0]["spoken"] == "你有 3 个 AI 应用，要接 4 个工具。没有标准的话，就是 3 乘 4，12 份集成代码。它叫 MCP。"
    assert L[0]["zh"] == L[0]["spoken"] and L[0]["en"].startswith("Three apps")
    assert L[1]["en"] == ""
    en = tmp_path / "EN.md"
    en.write_text("## Line 1 — a\n\n    One chip.\n    Many cores.\n\nZH: 一块芯片。\n", encoding="utf-8")
    E = S.parse_script(en)
    assert E[0]["lang"] == "en" and E[0]["en"] == E[0]["spoken"] == "One chip. Many cores." and E[0]["zh"] == "一块芯片。"


def test_zh_tokens_match_asr_spelling():
    Z = _imp("zhtext")
    script = "MCP 是 AI 应用的 USB-C 接口，今天用七分钟、二十五个例子、零点五秒，二零二五年"
    heard = "MCPServer是AI应用的USB-C接口,今天用7分钟25个例子0.5秒2025年"
    a, b = Z.tokens(script), Z.tokens(heard)
    assert "7" in a and "25" in a and "0.5" in a and "2025" in a
    assert [t for t in b if t != "server"] == a
    assert Z.cn_number("一百零五") == "105" and Z.cn_number("两千") == "2000" and Z.cn_number("三万五千") == "35000"


def test_vo_check_finds_a_dropped_chinese_sentence():
    C = _imp("vo_check")
    script = "MCP 是 AI 应用的 USB-C 接口。它把 3 乘 4 变成 3 加 4。最后，它不是银弹。"
    ok = C.check(script, "MCP是AI应用的USB C接口它把三乘四变成三加四最后它不是银弹")
    assert ok["missing"] == []
    bad = C.check(script, "MCP是AI应用的USB C接口它把三乘四变成三加四")
    assert bad["missing"] == ["最后，它不是银弹。"]


def test_pair_cues_chinese_only_and_with_english(tmp_path):
    P = _imp("pair_cues")
    rows = P.zh_only("MCP 是 AI 应用的 USB-C 接口。它在 AI 应用和工具、数据、服务之间，插了一个标准化的接口层，"
                     "你写一个 MCP server，所有支持 MCP 的 AI 应用都能用它；这就是网络效应。", 26)
    assert "".join(z for z, *_ in rows).startswith("MCP 是 AI")
    assert all(P.zh_len(z) <= 26 for z, *_ in rows) and len(rows) >= 3
    (tmp_path / "SCRIPT.md").write_text(ZH_SCRIPT, encoding="utf-8")
    subprocess.run([sys.executable, str(EXP / "pair_cues.py"), "-C", str(tmp_path)], check=True, capture_output=True)
    txt = (tmp_path / "subtitles" / "cues.draft.txt").read_text(encoding="utf-8")
    assert "中文 || English" in txt
    block2 = txt.split("## 2", 1)[1]
    assert all(ln.rstrip().endswith("||") for ln in block2.strip().splitlines())   # no EN: line -> 中文 only


def test_align_cues_chinese_narration(tmp_path):
    (tmp_path / "SCRIPT.md").write_text(ZH_SCRIPT, encoding="utf-8")
    (tmp_path / "subtitles").mkdir()
    (tmp_path / "audio" / "vo").mkdir(parents=True)
    (tmp_path / "subtitles" / "cues.txt").write_text(
        "## 1\n你有 3 个 AI 应用，要接 4 个工具。|| Three apps, four tools.\n"
        "没有标准的话，就是 3 乘 4，12 份集成代码。它叫 MCP。|| It is called MCP.\n"
        "## 2\nMCP 是 AI 应用的 USB-C 接口。||\n你写一个 MCP server，所有支持 MCP 的应用都能直接用它。||\n",
        encoding="utf-8")
    json.dump([[1, 0.4, 8.0], [2, 9.1, 7.0]], open(tmp_path / "audio/vo/offsets.json", "w"))
    words, t = [], 0.4
    for w in ["你有", "三个", "AI", "应用", "要接", "四个", "工具", "没有", "标准的话", "就是", "三乘四", "十二份", "集成",
              "代码", "它叫", "MCP"]:
        words.append(dict(text=w, start=round(t, 2), end=round(t + 0.45, 2))); t += 0.48
    t = 9.1
    for w in ["MCP", "是", "AI", "应用的", "USB-C", "接口", "你写", "一个", "MCPServer", "所有", "支持", "MCP", "的",
              "应用", "都能", "直接", "用它"]:
        words.append(dict(text=w, start=round(t, 2), end=round(t + 0.38, 2))); t += 0.4
    json.dump(words, open(tmp_path / "audio/transcript.json", "w"), ensure_ascii=False)
    r = subprocess.run([sys.executable, str(EXP / "align_cues.py"), "-C", str(tmp_path)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    cues = json.load(open(tmp_path / "subtitles/cues.json", encoding="utf-8"))
    assert [c["line"] for c in cues] == [1, 1, 2, 2]
    assert cues[0]["zh"] == "你有 3 个 AI 应用，要接 4 个工具" and cues[0]["en"] == "Three apps, four tools."
    assert cues[1]["start"] > cues[0]["start"] and 3.0 < cues[1]["start"] < 4.5      # "没有" is the 8th word
    assert cues[3]["start"] > 11 and cues[2]["en"] == ""
    assert (tmp_path / "subtitles/zh.srt").exists() and (tmp_path / "subtitles/en.srt").exists()


def test_tts_kokoro_language_and_zh_voice():
    from vstudio import tts
    assert tts.kokoro_lang("zf_xiaobei") == "z" and tts.kokoro_lang("af_heart") == "a" and tts.kokoro_lang("ref") is None
    assert tts.zh_voice("kokoro") == "zf_xiaobei" and tts.zh_voice("edge").startswith("zh-CN")


def test_voice_checkpoint_is_free_for_a_local_chinese_voice(tmp_path):
    from types import SimpleNamespace
    from vstudio.project.adapters import explainer as X
    (tmp_path / "SCRIPT.md").write_text(ZH_SCRIPT, encoding="utf-8")
    env = SimpleNamespace(item_dir=str(tmp_path), params={"tts_engine": "clone", "voice": "cedar", "speed": 1.0})
    pay = X.voice_payload(env, {})
    assert pay["language"] == "zh" and pay["paid"] is False and pay["estimate_usd"] == 0.0 and pay["minutes"] > 0
    assert pay["default"]["voice"] == "clone"
    env.params = {"voice": "cedar"}
    assert X.voice_payload(env, {})["paid"] is True


# --------------------------------------------------------------------------- intake: an exported Notion 讲稿 folder
LECTURE = """# Lab MCP - 讲稿

# Part 5 — Notebook 04: FastMCP Server（约 14 分钟）
[切到 notebook 04]
我先讲一句话定义。**MCP 是 AI 应用的 USB-C 接口。**
## 5.1 时间线
Phase 1: Initialize
注意：Step 1 先连上，Step 2 再列工具，Step 3 调用。
面试 tip：senior 经常问这个。
Step 4: 看 History。
"""


@pytest.fixture
def iso(tmp_path, monkeypatch):
    monkeypatch.setenv("VSTUDIO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr("vstudio.intake.inventory.cache_root", lambda: str(tmp_path / "cache"))
    monkeypatch.setenv("VSTUDIO_LLM_PROVIDER", "none")
    monkeypatch.setenv("VSTUDIO_LLM_INTAKE_PROVIDER", "none")
    (tmp_path / "cache").mkdir()
    return tmp_path


def test_steps_are_not_episodes_and_a_lecture_is_not_a_screenplay():
    from vstudio.intake import docs as D
    assert [m.group(0) for m in D.EPISODE_RE.finditer("Step 1, Step 2, deep 3")] == []
    assert len(list(D.EPISODE_RE.finditer("第 2 集 / Episode 3 / EP 4"))) == 3
    assert D.shape_of(LECTURE, ".md", {}) != "script"


def test_a_course_video_from_lecture_notes_is_an_explainer(iso):
    from vstudio.intake import plan as PL
    d = iso / "notion-export"
    d.mkdir()
    (d / "Lab MCP - 讲稿 359f94dabb5d80898517c07f739c0a6e.md").write_text(LECTURE, encoding="utf-8")
    p = PL.make_plan("把这节讲稿做成一集有丰富交互感的科普课程视频（画面：图解动画、代码片段、对比表、要点卡），中文讲解，适合 YouTube 和 B站",
                     [str(d)], provider="none", asr="off")
    assert not p.get("needs"), p.get("needs")
    assert [x["recipe"] for x in p["projects"]] == ["explainer"]
    assert p["projects"][0]["params"]["platforms"] == ["youtube", "bilibili"]


def test_her_voice_engine_reaches_the_explainer_plan(iso, monkeypatch):
    from vstudio.intake import plan as PL
    (iso / "persona.yaml").write_text("tts:\n  engine: clone\n", encoding="utf-8")
    monkeypatch.setenv("VSTUDIO_PERSONA", str(iso / "persona.yaml"))
    from vstudio import config
    config.persona.cache_clear()
    try:
        p = PL.make_plan("做一条讲解 transformer 的视频", [], provider="none", asr="off")
        pr = p["projects"][0]
        assert pr["recipe"] == "explainer" and pr["params"]["tts_engine"] == "clone"
        assert pr["param_sources"]["tts_engine"] == "persona" and p["estimate"]["api_usd"] == 0
    finally:
        config.persona.cache_clear()


def test_lecture_notes_are_materials_not_the_script(tmp_path):
    from vstudio.project import build as B
    notes = tmp_path / "notes.md"
    notes.write_text(LECTURE, encoding="utf-8")
    ready = tmp_path / "ready.md"
    ready.write_text(ZH_SCRIPT, encoding="utf-8")
    tpl = ROOT / "lib/vstudio/project/templates/explainer_SCRIPT.md"
    assert not B._same_shape(str(notes), str(tpl)) and B._same_shape(str(ready), str(tpl))


def test_drafts_read_far_into_long_materials(tmp_path):
    from types import SimpleNamespace
    from vstudio.project import drafts as DR
    doc = tmp_path / "lecture.md"
    doc.write_text("开场。" * 3000 + "\n# Part 5 — FastMCP\nMCP 是 AI 应用的 USB-C 接口。", encoding="utf-8")
    text = DR._materials_text(SimpleNamespace(inputs={"script": [str(doc)]}))
    assert "USB-C 接口" in text


# --------------------------------------------------------------------------- Hedra presenter (fake transport)
class FakeHedra:
    def __init__(self, fail_submit=False):
        self.calls, self.fail_submit, self.polls = [], fail_submit, 0

    def __call__(self, url, data=None, headers=None, method=None, timeout=120):
        from vstudio.create.providers import hedra as H
        assert headers is not None and (url.startswith("https://cdn") or headers.get("X-API-Key") == "k-test")
        self.calls.append((method, url.split("/public", 1)[-1]))
        if url.endswith("/models"):
            return json.dumps({"data": [{"id": "m-img", "name": "Image"}, {"id": "m-c3", "name": "Character-3"}]}).encode(), {}
        if url.endswith("/assets") and method == "POST":
            return json.dumps({"id": f"a{len(self.calls)}"}).encode(), {}
        if "/upload" in url:
            assert headers["Content-Type"].startswith("multipart/form-data")
            return b"{}", {}
        if url.endswith("/generations") and method == "POST":
            body = json.loads(data)
            assert body["ai_model_id"] == "m-c3" and body["generated_video_inputs"]["resolution"] == "540p"
            if self.fail_submit:
                raise H.TransportError("timed out")
            return json.dumps({"id": "g1"}).encode(), {}
        if url.endswith("/generations/g1/status"):
            self.polls += 1
            done = self.polls > 1
            return json.dumps({"status": "complete" if done else "processing", "progress": 1 if done else 0.4,
                               "url": "https://cdn.example/v.mp4" if done else None}).encode(), {}
        if url.startswith("https://cdn"):
            return b"MP4", {}
        raise AssertionError(url)


@pytest.fixture
def pres(tmp_path, monkeypatch):
    monkeypatch.setenv("VSTUDIO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("HEDRA_API_KEY", "k-test")
    monkeypatch.delenv("HEDRA_MODEL_ID", raising=False)
    from vstudio.create import providers as PR, store
    store.configure(str(tmp_path / "home"))
    img, vo = tmp_path / "me.jpg", tmp_path / "vo.wav"
    img.write_bytes(b"jpg")
    vo.write_bytes(b"wav")
    monkeypatch.setattr("vstudio.media.duration", lambda p: 12.0)
    yield tmp_path, img, vo
    PR._instances.clear()
    store.configure(None)


def _install(fake):
    from vstudio.create import providers as PR
    from vstudio.create.providers.hedra import Hedra
    PR.install("hedra", Hedra(transport=fake))


def test_presenter_estimate_then_one_paid_run(pres):
    from vstudio.create import presenter as PS
    tmp, img, vo = pres
    fake = FakeHedra()
    _install(fake)
    est = PS.estimate(str(img), str(vo), out=str(tmp / "out"))
    assert est["credits"] == 36 and est["seconds_billed"] == 12 and est["checks"]["ok"] and len(est["confirm_code"]) == 8
    assert not fake.calls                                            # an estimate never touches the network
    from vstudio.create.i18n import CreateError
    with pytest.raises(CreateError) as e:
        PS.run(est["id"], "deadbeef", 99)
    assert e.value.code == "create.confirm-mismatch"
    with pytest.raises(CreateError) as e:
        PS.run(est["id"], est["confirm_code"], 0.1)
    assert e.value.code == "create.max-too-low"
    r = PS.run(est["id"], est["confirm_code"], est["max_cny"], sleep=lambda s: None)
    assert r["ok"] and open(r["file"], "rb").read() == b"MP4"
    assert [c for c in fake.calls if c[1] == "/generations"] == [("POST", "/generations")]
    led = PS.show()["ledger"]
    assert [x["status"] for x in led] == ["submitted"] and "k-test" not in json.dumps(led)
    with pytest.raises(CreateError) as e:                            # one OK = one submission
        PS.run(est["id"], est["confirm_code"], est["max_cny"], sleep=lambda s: None)
    assert e.value.code == "create.confirm-used"


def test_presenter_refuses_changed_files_expiry_and_records_unknown_charge(pres):
    from vstudio.create import presenter as PS, store
    from vstudio.create.i18n import CreateError
    tmp, img, vo = pres
    _install(FakeHedra())
    est = PS.estimate(str(img), str(vo))
    vo.write_bytes(b"another take")
    with pytest.raises(CreateError) as e:
        PS.run(est["id"], est["confirm_code"], est["max_cny"])
    assert e.value.code == "create.plan-changed"
    est = PS.estimate(str(img), str(vo))
    doc = store.read_json(PS._path(est["id"]))
    doc["expires_at"] = time.time() - 1
    store.write_json(PS._path(est["id"]), doc)
    with pytest.raises(CreateError) as e:
        PS.run(est["id"], est["confirm_code"], est["max_cny"])
    assert e.value.code == "create.confirm-expired"
    _install(FakeHedra(fail_submit=True))
    est = PS.estimate(str(img), str(vo))
    with pytest.raises(CreateError) as e:
        PS.run(est["id"], est["confirm_code"], est["max_cny"])
    assert e.value.code == "create.unknown-charge"
    assert PS.show()["ledger"][-1]["status"] == "unknown-charge"


def test_presenter_needs_her_key(pres, monkeypatch):
    from vstudio.create import presenter as PS
    tmp, img, vo = pres
    monkeypatch.delenv("HEDRA_API_KEY")
    est = PS.estimate(str(img), str(vo))
    assert not est["checks"]["ok"]
    assert est["checks"]["codes"][0]["code"] == "create.provider-not-ready"


def test_shot_routing_never_picks_the_presenter_service():
    from vstudio.create import routing
    src, _ = routing.cheapest(5, ["hedra", "veo"])
    assert src is None or "hedra" not in src


def test_long_chinese_cues_never_split_an_english_term_or_a_word_pair():
    P = _imp("pair_cues")
    cues = [z for z, *_ in P.zh_only("第一个要拆掉的混淆：MCP 不是 function calling 的替代品。", 16)]
    assert not any(z.rstrip().endswith("function") for z in cues)
    cues = [z for z, *_ in P.zh_only("MCP 是协议层——工具怎么被发现、被维护、被跨应用复用。", 16)]
    assert all(not z.startswith("护") for z in cues) and cues[0].endswith("、")


def test_an_edited_scene_rerenders():
    import yaml
    m = yaml.safe_load(open(ROOT / "workflows/explainer/recipe.yaml", encoding="utf-8"))
    render = next(s for s in m["stages"] if s["id"] == "render")
    assert any("compositions" in w for w in render.get("watch") or [])
