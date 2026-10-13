"""Voice casting (vstudio.voicecast + the photo-story ``voice`` step): the catalog matches the models' real speakers,
the rules cast per kind of video, the AI's pick is kept only when it is a real candidate, her own voice is never
re-cast, and the old ``voice: qwen`` projects still read. Catalog: lib/vstudio/voices.json."""
import json
import os
import types

import pytest
import yaml

from vstudio import qwen_synth, tts
from vstudio import voicecast as VC
from vstudio.project import autopilot as AP
from vstudio.project import manifests as M
from vstudio.project.adapters import photostory as PS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def _no_local_kokoro(monkeypatch):
    monkeypatch.delenv(tts.KOKORO_MODEL_ENV, raising=False)
    monkeypatch.setattr(VC, "_kokoro_dir", lambda: None)


def fake(reply, calls=None):
    def complete(task, system, prompt, **kw):
        if calls is not None:
            calls.append(dict(task=task, prompt=prompt))
        if isinstance(reply, Exception):
            raise reply
        return {"provider": "fake", "json": reply}
    return complete


# --------------------------------------------------------------------------- the catalog
def test_catalog_lists_every_qwen_speaker_and_only_valid_tags():
    cat = VC.catalog()
    ids = [v["id"] for v in cat["voices"]]
    assert len(ids) == len(set(ids))
    qwen = {v["speaker"] for v in VC.voices("qwen")}
    assert qwen == set(qwen_synth.SPEAKERS)                    # the model's own spk_id list
    assert {v["speaker"] for v in VC.voices("qwen", "zh")} == set(tts.QWEN_ZH_VOICES)
    for v in cat["voices"]:
        assert v["engine"] in ("qwen", "kokoro") and v["gender"] in ("male", "female")
        assert set(v["tone"]) <= set(cat["tones"]), v["id"]
        assert set(v["fit"]) <= set(cat["kinds"]), v["id"]
        assert v["label"]["en"] and v["label"]["zh"] and v["desc"] and v["native"]
        if v["engine"] == "kokoro":
            assert v["speaker"][:1] in tts.KOKORO_LANGS and v["speaker"][1] in "fm"
            assert (v["speaker"][1] == "m") == (v["gender"] == "male")
    for k in cat["kinds"]:
        assert cat["styles"][k]["zh"] and cat["styles"][k]["en"], k
    for lang, per in cat["rules"].items():
        if lang == "about":
            continue
        assert set(per) <= set(cat["kinds"]) | {"default"}
        for k, order in per.items():
            for i in order:
                assert i in ids and lang in next(v for v in cat["voices"] if v["id"] == i)["native"], (lang, k, i)


def test_qwen_speakers_match_the_downloaded_model_config_when_present():
    snap = os.path.expanduser("~/.cache/huggingface/hub/models--mlx-community--Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit/"
                              "snapshots")
    cfgs = [os.path.join(snap, d, "config.json") for d in (os.listdir(snap) if os.path.isdir(snap) else [])]
    cfgs = [c for c in cfgs if os.path.isfile(c)]
    if not cfgs:
        pytest.skip("the Qwen3-TTS CustomVoice model is not downloaded here")
    tc = json.load(open(cfgs[0]))["talker_config"]
    assert set(tc["spk_id"]) == {v["speaker"] for v in VC.voices("qwen")}
    dialects = {k for k, d in tc["spk_is_dialect"].items() if d}
    assert dialects == {v["speaker"] for v in VC.voices("qwen") if v.get("dialect")}


def test_bundled_kokoro_voices_are_the_apps_download():
    assets = json.load(open(os.path.join(ROOT, "apps", "desk", "packaging", "assets.json")))
    groups = assets.get("groups") or assets.get("assets") or []
    g = next(x for x in groups if x["id"] == "tts-kokoro")
    shipped = {os.path.basename(f["dest"]).split(".")[0] for f in g["files"] if "/voices/" in f["dest"]}
    bundled = {v["speaker"] for v in VC.voices("kokoro") if v.get("bundled")}
    assert bundled and bundled <= shipped


def test_a_local_kokoro_folder_limits_the_candidates(tmp_path, monkeypatch):
    (tmp_path / "voices").mkdir()
    for s in ("af_heart", "am_michael", "bf_emma"):
        (tmp_path / "voices" / f"{s}.safetensors").write_bytes(b"")
    monkeypatch.setattr(VC, "_kokoro_dir", lambda: str(tmp_path))
    assert {v["speaker"] for v in VC.candidates("kokoro", "en")} == {"af_heart", "am_michael", "bf_emma"}
    assert VC.rule_cast("en", "kokoro", "history")["speaker"] == "am_michael"      # bm_george is not here
    assert VC.rule_cast("en", "kokoro", "vlog")["speaker"] == "af_heart"


# --------------------------------------------------------------------------- the rules
@pytest.mark.parametrize("kind,zh,en", [
    ("history", "uncle_fu", "bm_george"), ("documentary", "uncle_fu", "am_michael"), ("news", "uncle_fu", "am_michael"),
    ("course", "serena", "af_heart"), ("tutorial", "serena", "af_heart"), ("vlog", "vivian", "af_bella"),
    ("promo", "vivian", "am_puck"), ("kids", "serena", "bm_fable"), (None, "serena", "af_heart"),
])
def test_rules_cast_per_kind(kind, zh, en):
    c = VC.rule_cast("zh", "qwen", kind)
    assert c["speaker"] == zh and c["by"] == "rules" and c["engine"] == "qwen"
    assert c["style"] == VC.style_for(kind, "zh")             # Qwen3-TTS takes the delivery instruction
    e = VC.rule_cast("en", "kokoro", kind)
    assert e["speaker"] == en and e["style"] is None          # Kokoro takes none


def test_short_vertical_platforms_lean_lively_when_nothing_says_the_kind():
    assert VC.rule_cast("zh", "qwen", None, platforms=["douyin"])["speaker"] == "vivian"
    assert VC.rule_cast("zh", "qwen", "history", platforms=["douyin"])["speaker"] == "uncle_fu"


def test_kind_of_her_words():
    assert VC.kind_of("A 110-second Chinese-narrated night-drone history of Seattle Center, the 1962 World's Fair") == \
        "history"
    assert VC.kind_of("MCP 入门课程 第3讲") == "course"
    assert VC.kind_of("周末 vlog 日常") == "vlog"
    assert VC.kind_of("新品发布 launch trailer") == "promo"
    assert VC.kind_of("") is None


def test_her_words_change_the_voice_without_a_model():
    c = VC.rule_cast("zh", "qwen", "course", instruction="换个男声", current="serena")
    assert c["speaker"] == "uncle_fu" and c["speaker"] != "serena"
    c = VC.rule_cast("zh", "qwen", "history", instruction="换个女声", current="uncle_fu")
    assert VC.find(c["speaker"])["gender"] == "female"
    c = VC.rule_cast("zh", "qwen", "history", instruction="活泼一点的声音", current="uncle_fu")
    assert c["speaker"] == "vivian"
    calls = []
    c = VC.cast("zh", "qwen", "history", instruction="用 vivian 的声音", complete=fake({}, calls))
    assert c["speaker"] == "vivian" and c["by"] == "you" and not calls       # named: no model call


# --------------------------------------------------------------------------- the AI
def test_the_ais_pick_is_used_with_its_reason_and_style():
    calls = []
    c = VC.cast("zh", "qwen", title="夜色下的太空针塔", request="night history of the Space Needle",
                script="1962 年世博会……", complete=fake(dict(speaker="uncle_fu", style="沉稳庄重", reason="历史纪录片，沉稳的男声"),
                                                     calls))
    assert c == dict(engine="qwen", speaker="uncle_fu", style="沉稳庄重", reason="历史纪录片，沉稳的男声", by="ai",
                     kind="history", provider="fake")
    assert calls[0]["task"] == "planner"                  # the project's AI routing, like the other plan steps
    body = json.loads(calls[0]["prompt"].split("\nWrite the reason")[0])
    assert {x["speaker"] for x in body["candidates"]} == set(tts.QWEN_ZH_VOICES)
    assert body["kind"] == "history"


def test_a_pick_outside_the_candidates_or_a_failed_model_falls_back_to_the_rules():
    c = VC.cast("zh", "qwen", "history", complete=fake(dict(speaker="ryan", reason="x")))     # English speaker
    assert c["speaker"] == "uncle_fu" and c["by"] == "rules"
    c = VC.cast("zh", "qwen", "history", complete=fake(RuntimeError("no provider")))
    assert c["by"] == "rules" and "no provider" in c["ai_error"]
    c = VC.cast("en", "kokoro", "course", complete=fake(dict(speaker="af_heart", style="slow", reason="clear")))
    assert c["by"] == "ai" and c["style"] is None
    assert VC.cast("zh", "openai", "history", complete=False) is None      # no catalog for OpenAI: its own voice


def test_a_change_never_returns_the_same_voice():
    c = VC.cast("zh", "qwen", "course", instruction="换个声音", current={"speaker": "serena"},
                complete=fake(dict(speaker="serena", reason="same")))
    assert c["speaker"] != "serena" and c["by"] == "rules"


# --------------------------------------------------------------------------- values in projects
def test_back_compat_values():
    for v in ("qwen", "auto", "marin", "", None, "{'engine': 'x'}"):
        assert VC.parse(v) is None and VC.explicit(v) is None
    assert VC.explicit("vivian")["speaker"] == "vivian"
    assert VC.explicit("傅叔")["speaker"] == "uncle_fu"
    assert VC.explicit("qwen:dylan")["speaker"] == "dylan"
    assert VC.explicit(dict(engine="qwen", speaker="serena", by="ai")) is None
    assert VC.is_cast(dict(engine="qwen", speaker="serena", by="rules"))
    assert VC.explicit(dict(speaker="eric"))["by"] == "you"
    assert VC.record(dict(engine="qwen", speaker="eric", style=None, reason="r", by="ai", x=1)) == \
        dict(engine="qwen", speaker="eric", reason="r", by="ai")


# --------------------------------------------------------------------------- the photo-story step
SPEC = """TITLE_ZH = "夜色下的太空针塔"
TTS = dict(language="zh")
SCRIPT = [("intro", [("In 1962 the World's Fair came to Seattle.", "1962 年，世博会来到西雅图。")], [])]
"""


def env_for(tmp_path, voice=None, raw=None, item="needle"):
    pdir = tmp_path / "proj"
    idir = pdir / "items" / item
    (idir / "work").mkdir(parents=True)
    (idir / "work" / "spec.py").write_text(SPEC, encoding="utf-8")
    (pdir / "state").mkdir()
    doc = dict(version=1, name="The Needle After Dark (中文)", recipe="photo-story",
               params=dict(mode="narration", voice=raw if raw is not None else "qwen", platforms=["bilibili"]),
               items=[dict(id=item, params=dict(title="夜色下的太空针塔"))])
    (pdir / "project.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    params = dict(voice=voice if voice is not None else doc["params"]["voice"], tts_engine="auto",
                  platforms=["bilibili"], title="夜色下的太空针塔", _project_dir=str(pdir), _item=item,
                  _item_dir=str(idir))
    logs = []
    return types.SimpleNamespace(params=params, item_dir=str(idir), project_dir=str(pdir),
                                 state_dir=str(pdir / "state"), job=item, log=logs.append, logs=logs)


@pytest.fixture
def qwen_here(monkeypatch):
    monkeypatch.setattr(VC, "narration_engine", lambda lang, engine="auto": "qwen" if lang == "zh" else "kokoro")


def test_photostory_casts_once_and_keeps_the_cast(tmp_path, monkeypatch, qwen_here):
    calls = []
    import vstudio.llm as L
    monkeypatch.setattr(L, "complete", fake(dict(speaker="uncle_fu", style="沉稳", reason="历史题材"), calls))
    env = env_for(tmp_path)
    pay = PS.voice_payload(env, {})
    assert pay["default"] == dict(engine="qwen", speaker="uncle_fu", style="沉稳", reason="历史题材", by="ai",
                                  kind="history", provider="fake")
    assert pay["default_meta"]["by"] == "ai" and pay["default_meta"]["params"]["speaker"] == "uncle_fu"
    assert [o["speaker"] for o in pay["options"] if o["checked"]] == ["uncle_fu"]
    assert len(calls) == 1
    # the autopilot / auto answer takes it with its reason -> project.yaml voice {engine, speaker, style, reason, by}
    d = AP.rules(dict(kind="voice-cast"), pay)
    assert d["value"] == pay["default"] and d["by"] == "ai" and d["reason"] == "历史题材"
    res = PS.voice_apply(types.SimpleNamespace(value=d["value"], payload=pay, params=env.params))
    assert res["params"]["voice"]["speaker"] == "uncle_fu" and res["digest"] == pay["digest"]
    # the next run reads the recorded cast: no new model call, same digest (the answer stands)
    env.params["voice"] = res["params"]["voice"]
    again = PS.voice_payload(env, {})
    assert again["default"]["speaker"] == "uncle_fu" and again["digest"] == pay["digest"] and len(calls) == 1


def test_photostory_never_recasts_her_voice(tmp_path, monkeypatch, qwen_here):
    calls = []
    import vstudio.llm as L
    monkeypatch.setattr(L, "complete", fake(dict(speaker="uncle_fu", reason="x"), calls))
    env = env_for(tmp_path, voice="vivian")                       # she named a speaker
    pay = PS.voice_payload(env, {})
    assert pay["default"]["speaker"] == "vivian" and pay["default"]["by"] == "you" and not calls
    # her hand edit in project.yaml wins over the cast the engine stored in overrides
    env = env_for(tmp_path / "b", voice=dict(engine="qwen", speaker="uncle_fu", by="ai"), raw="dylan")
    pay = PS.voice_payload(env, {})
    assert pay["default"]["speaker"] == "dylan" and not calls
    assert PS.voice_recheck(env.params) == dict(speaker="dylan", style=None)


def test_photostory_her_words_recast_and_stay_hers(tmp_path, monkeypatch, qwen_here):
    import vstudio.llm as L
    monkeypatch.setattr(L, "complete", fake(dict(speaker="uncle_fu", style="沉稳", reason="沉稳的男声")))
    env = env_for(tmp_path, voice=dict(engine="qwen", speaker="serena", by="ai"))
    pay = PS.voice_payload(env, {})
    assert pay["default"]["speaker"] == "serena"
    res = PS.voice_apply(types.SimpleNamespace(value=dict(ask="换个男声"), payload=pay, params=env.params))
    v = res["params"]["voice"]
    assert v["speaker"] == "uncle_fu" and v["by"] == "you" and v["ask"] == "换个男声"
    env.params["voice"] = v
    after = PS.voice_payload(env, {})                             # hers now: kept, and the answer's digest holds
    assert after["default"]["speaker"] == "uncle_fu" and after["digest"] == res["digest"]
    # an Inbox pick (one tick) is hers too
    k = next(o["id"] for o in pay["options"] if o["speaker"] == "vivian")
    res = PS.voice_apply(types.SimpleNamespace(value=dict(pick=k), payload=pay, params=env.params))
    assert res["params"]["voice"]["speaker"] == "vivian" and res["params"]["voice"]["by"] == "you"


def test_photostory_skips_an_engine_without_a_catalog(tmp_path, monkeypatch):
    monkeypatch.setattr(VC, "narration_engine", lambda lang, engine="auto": "openai")
    pay = PS.voice_payload(env_for(tmp_path), {})
    assert pay["skip"] and not pay["options"]


def test_the_recipe_has_the_voice_step_before_tts():
    m = M.get("photo-story")
    assert M.validate(m) == []
    cp = next(c for c in m["checkpoints"] if c["id"] == "voice")
    assert cp["kind"] == "voice-cast" and cp["blocks"] == ["tts"] and cp["auto"] == "always"
    tts_stage = next(s for s in m["stages"] if s["id"] == "tts")
    argv = M.fmt_args(tts_stage["run"]["argv"], dict(python="py", workflow_dir="w", item_dir="i", tts_engine="auto",
                                                      voice=dict(engine="qwen", speaker="uncle_fu", style="沉稳")))
    assert argv[argv.index("--speaker") + 1] == "uncle_fu" and argv[argv.index("--style") + 1] == "沉稳"
    old = M.fmt_args(tts_stage["run"]["argv"], dict(python="py", workflow_dir="w", item_dir="i", tts_engine="auto",
                                                     voice="qwen"))
    assert "--speaker" not in old and old[old.index("--voice") + 1] == "qwen"      # voice: qwen reads as before


def test_in_the_app_only_installed_kokoro_voices_are_cast_and_the_reason_says_so(tmp_path, monkeypatch):
    """Her app's tts-kokoro root is a shared Hugging Face snapshot with every voice in it, but the app installs four:
    the cast never picks af_bella / bm_george there, and says the best fit is not installed."""
    (tmp_path / "voices").mkdir()
    for s in ("af_heart", "am_michael", "bf_emma", "af_bella", "bm_george", "zf_xiaobei"):
        (tmp_path / "voices" / f"{s}.safetensors").write_bytes(b"")
    monkeypatch.setattr(VC, "_kokoro_dir", lambda: str(tmp_path))
    monkeypatch.setenv("VSTUDIO_TTS_MODELS_MANAGED", "1")
    assert {v["speaker"] for v in VC.candidates("kokoro", "en")} == {"af_heart", "am_michael", "bf_emma"}
    c = VC.rule_cast("en", "kokoro", "vlog")
    assert c["speaker"] == "af_heart" and "af_bella would fit best but is not installed" in c["reason"]
    c = VC.rule_cast("en", "kokoro", "history")
    assert c["speaker"] == "am_michael" and "bm_george" in c["reason"]
    assert VC.rule_cast("en", "kokoro", "course")["reason"].endswith("voice")          # the best one is installed
    c = VC.cast("en", "kokoro", "vlog", complete=fake(dict(speaker="af_bella", reason="x")))      # not a candidate
    assert c["speaker"] == "af_heart" and c["by"] == "rules"
    assert not VC.usable(dict(engine="kokoro", speaker="af_bella")) and VC.usable(dict(engine="kokoro", speaker="af_heart"))
    monkeypatch.delenv("VSTUDIO_TTS_MODELS_MANAGED")                # a dev engine: the folder decides
    assert "af_bella" in {v["speaker"] for v in VC.candidates("kokoro", "en")}


def test_photostory_her_voice_not_installed_falls_back_with_the_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(VC, "narration_engine", lambda lang, engine="auto": "kokoro")
    monkeypatch.setenv("VSTUDIO_TTS_MODELS_MANAGED", "1")
    env = env_for(tmp_path, voice="bm_george")
    (tmp_path / "proj" / "items" / "needle" / "work" / "spec.py").write_text(SPEC.replace('language="zh"', 'language="en"'))
    pay = PS.voice_payload(env, {})
    assert pay["default"]["speaker"] == "am_michael" and "bm_george is not installed" in pay["default"]["reason"]
