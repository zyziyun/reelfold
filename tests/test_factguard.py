"""The fact check of told pieces (vstudio.factguard): the Elliott Bay film's drafted narration said "one of the West
Coast's largest grain terminals", "Seattle's busiest rail yard" and "among the West Coast's largest" (and 最大的…之一,
最繁忙的, 位列前列) although the drafter's prompt asked for verifiable facts only. The routed AI lists the claims;
the rules decide; only the spec's cue literals change; facts.md tells her what changed. A fake model throughout."""
import json
import os

from vstudio import factguard as FG
from vstudio.project import drafts as DR

PIER = ("At **Pier 86** stands one of the West Coast's largest grain terminals.",
        "86号码头坐落着西海岸最大的粮食码头之一。")
BALMER = ("Beside the pier stretches **Balmer Yard**, Seattle's busiest rail yard.",
          "码头旁是**巴尔默调车场**，西雅图最繁忙的调车场。")
MARINA = ("**Elliott Bay Marina**, with over a thousand berths, is among the West Coast's largest.",
          "**埃利奥特湾游艇码头**泊位逾千，位列西海岸前列。")
RAILS = ("The rails first reached this shore in **1893**, with the Great Northern.",
         "**1893年**，大北方铁路修到这片海岸。")
SILOS = ("Its white silos have watched over the bay since the late 1960s.", "白色筒仓自1960年代末守望海湾。")

SPEC = '''# Elliott Bay - a narrated history
MEDIA = dict(images=["frames", "../inputs"], videos="../inputs")
TITLE_EN = "Elliott Bay"
SCRIPT = [
    (1, [("At **Pier 86** stands one of the West Coast's largest grain terminals.",
          "86号码头坐落着西海岸最大的粮食码头之一。"),
         ("Its white silos have watched over the bay since the late 1960s.",
          "白色筒仓自1960年代末守望海湾。")], [
        ("vCLIP", 1.4, "still", dict(off=14.2, label="Pier 86 Grain Terminal")),
    ]),
    (2, [("Beside the pier stretches **Balmer Yard**, Seattle's busiest rail yard.",
          "码头旁是**巴尔默调车场**，西雅图最繁忙的调车场。")], [
        ("vCLIP", 1.4, "still", dict(off=8.9, label="Balmer Yard · Interbay")),
    ]),
    (2, [("The rails first reached this shore in **1893**, with the Great Northern.",
          "**1893年**，大北方铁路修到这片海岸。")], [
        ("vCLIP", 1.4, "still", dict(off=56.1, tl=1893)),
    ]),
    (3, [("The bay belongs to small boats, too.", "这片海湾也属于小型船只。"),
         ("**Elliott Bay Marina**, with over a thousand berths, is among the West Coast's largest.",
          "**埃利奥特湾游艇码头**泊位逾千，位列西海岸前列。")], [
        ("vCLIP", 1.4, "still", dict(off=50.7, label="Elliott Bay Marina")),
    ]),
]
COVER = dict(title="Elliott Bay", hero=dict(src="cover_a"))  # the cover: largest still
'''


def fake(claims, provider="claude-code", calls=None):
    def complete(task, system, body, **kw):
        if calls is not None:
            calls.append(body)
        return dict(json=dict(claims=claims), provider=provider, model="t")
    return complete


def none_complete(*a, **k):
    return dict(provider="none")


ELLIOTT_CLAIMS = [
    dict(cue=0, claim="one of the West Coast's largest grain terminals", kind="superlative", confidence=0.55,
         source_type="local-knowledge", softened_en="At **Pier 86** stands a grain terminal.",
         softened_zh="86号码头坐落着一座粮食码头。"),
    dict(cue=2, claim="Seattle's busiest rail yard", kind="ranking", confidence=0.4, source_type="unverifiable",
         softened_en="", softened_zh=""),                       # no model line: the word rules soften it
    dict(cue=3, claim="The Great Northern reached the shore in 1893", kind="date", confidence=0.95,
         source_type="encyclopedic", softened_en="", softened_zh=""),
    dict(cue=5, claim="among the West Coast's largest marinas", kind="superlative", confidence=0.6,
         source_type="well-known", softened_en="**Elliott Bay Marina** has over a thousand berths.",
         softened_zh="**埃利奥特湾游艇码头**泊位逾千。"),
]


def test_elliott_bay_rankings_are_softened_in_both_languages_and_a_sourced_date_is_kept():
    res = FG.check([PIER, SILOS, BALMER, RAILS, ("The bay belongs to small boats, too.", "这片海湾也属于小型船只。"),
                    MARINA], "a history of the Elliott Bay waterfront", fake(ELLIOTT_CLAIMS),
                   units=[1, 1, 2, 2, 3, 3])
    cues = res["cues"]
    assert cues[0] == ("At **Pier 86** stands a grain terminal.", "86号码头坐落着一座粮食码头。")
    en, zh = cues[2]                                             # the word rules: still a sentence, no ranking
    assert en == "Beside the pier stretches **Balmer Yard**, a busy rail yard." and "最" not in zh and "调车场" in zh
    assert cues[3] == RAILS                                      # encyclopedic, 0.95: kept, with its 1893
    assert cues[5] == ("**Elliott Bay Marina** has over a thousand berths.", "**埃利奥特湾游艇码头**泊位逾千。")
    for c in cues:
        assert not FG.scan(c[0]) and not FG.scan(c[1])
    dec = {c["cue"]: c["decision"] for c in res["claims"]}
    assert dec == {0: "softened", 2: "softened", 3: "kept", 5: "softened"} and res["ai"] and res["dropped"] == 0


def test_a_superlative_is_kept_only_when_sure_and_sourced():
    line = ("Mount Rainier is the highest peak in Washington.", "雷尼尔山是华盛顿州最高的山峰。")
    keep = FG.check([line], "history", fake([dict(cue=0, claim="highest peak in Washington", kind="superlative",
                                                  confidence=0.97, source_type="encyclopedic")]))
    assert keep["cues"] == [line] and keep["kept"] == 1
    soft = FG.check([line], "history", fake([dict(cue=0, claim="highest peak in Washington", kind="superlative",
                                                  confidence=0.97, source_type="well-known")]))
    assert soft["cues"][0] != line and not FG.scan(soft["cues"][0][0]) and not FG.scan(soft["cues"][0][1])


def test_an_unverifiable_claim_drops_its_line_only_when_the_unit_keeps_another():
    a = ("Sailors say the pier is haunted by a captain.", "水手们说码头上有船长的幽灵。")
    b = ("The bay belongs to small boats, too.", "这片海湾也属于小型船只。")
    claim = [dict(cue=0, claim="the pier is haunted", kind="event", confidence=0.2, source_type="unverifiable",
                  softened_en="Sailors tell stories about the pier.", softened_zh="水手们讲着码头的故事。")]
    two = FG.check([a, b], "history", fake(claim), units=[0, 0])
    assert two["cues"] == [None, b] and two["dropped"] == 1
    one = FG.check([a, b], "history", fake(claim), units=[0, 1])
    assert one["cues"][0] == ("Sailors tell stories about the pier.", "水手们讲着码头的故事。") and one["dropped"] == 0
    # a weak date loses its number
    d = FG.check([SILOS], "history", fake([dict(cue=0, claim="since the late 1960s", kind="date", confidence=0.3,
                                                source_type="local-knowledge")]))
    en, zh = d["cues"][0]
    assert "1960" not in en and "1960" not in zh and en.startswith("Its white silos have watched over the bay")


def test_no_ai_the_word_rules_still_soften_and_facts_md_says_so(tmp_path):
    res = FG.check([PIER, BALMER, MARINA, RAILS], "history", none_complete)
    assert res["ai"] is False and res["ai_note"]
    assert res["cues"][0] == ("At **Pier 86** stands a large grain terminal.", "86号码头坐落着大型粮食码头。")
    assert res["cues"][2][1] == "**埃利奥特湾游艇码头**泊位逾千。" and res["cues"][3] == RAILS
    assert res["softened"] == 3 and all(c["by"] == "words" for c in res["claims"])
    p = FG.write_facts(str(tmp_path / "facts.md"), res, "en")
    md = open(p, encoding="utf-8").read()
    assert "The AI check did not run" in md and "softened" in md and "Seattle's busiest rail yard" in md
    assert "a busy rail yard" in md
    zh = FG.facts_markdown(res, "zh")
    assert "AI 核查没有运行" in zh and "已弱化" in zh
    # an error from the model is the same as no model
    def boom(*a, **k):
        raise RuntimeError("expired")
    assert FG.check([PIER], "history", boom)["cues"][0][0] == "At **Pier 86** stands a large grain terminal."


def test_only_the_cue_literals_change_in_the_spec():
    new, res = FG.check_spec(SPEC, "a history of the waterfront", fake(ELLIOTT_CLAIMS[:1] + [
        dict(cue=1, claim="since the late 1960s", kind="date", confidence=0.85, source_type="encyclopedic"),
        dict(cue=4, claim="boats", kind="general", confidence=0.1, source_type="unverifiable")]))
    assert DR.data_module_ok(new)
    assert '"At **Pier 86** stands a grain terminal."' in new and '"86号码头坐落着一座粮食码头。"' in new
    assert "西雅图最繁忙" not in new and "前列" not in new and "busiest" not in new
    assert "The bay belongs to small boats, too." not in new           # dropped: its unit keeps the marina line
    assert res["dropped"] == 1
    # everything outside the cue literals is byte-identical
    old_lines, new_lines = SPEC.splitlines(), new.splitlines()
    for ln in old_lines:
        if not any(x in ln for x in ("Pier 86** stands", "86号码头坐落", "Balmer Yard**, Seattle", "西雅图最繁忙",
                                     "small boats", "小型船只", "Elliott Bay Marina**, with", "位列西海岸")):
            assert ln in new_lines, ln
    assert new.startswith(SPEC[:SPEC.index("SCRIPT")]) and new.endswith(SPEC[SPEC.index("]\nCOVER"):])
    assert "# the cover: largest still" in new                         # a comment is not narration
    js = {k: v for k, v in res.items() if k != "cues"}
    json.dumps(js, ensure_ascii=False)                                  # the record is plain data


def test_the_explainer_script_is_checked_line_by_line():
    text = ("# SCRIPT\n\n## Line 1 — Pier (Frame 1)\n\n    At Pier 86 stands one of the West Coast's largest grain "
            "terminals.\n    It still works at night.\n\nZH: 86号码头坐落着西海岸最大的粮食码头之一。\n\n"
            "## Line 2 — Rails (Frame 2)\n\n    The rails came in 1893.\n\nZH: 1893年铁路修到这里。\n")
    new, res = FG.check_script(text, "history", none_complete)
    assert "    At Pier 86 stands a large grain terminal. It still works at night.\n" in new
    assert "ZH: 86号码头坐落着大型粮食码头。" in new and "## Line 2 — Rails (Frame 2)\n\n    The rails came in 1893." in new
    assert res["softened"] == 1 and res["dropped"] == 0


class Ctx:
    def __init__(self, project, item_dir, request, lang="en"):
        self.project_dir, self.item_dir, self._r, self._l = str(project), str(item_dir), request, lang
        self.params = dict(title="Elliott Bay")

    def request(self):
        return self._r

    def lang(self):
        return self._l


def test_facts_md_goes_to_the_project_root_or_the_items_work_folder(tmp_path):
    proj = tmp_path / "proj"
    item = proj / "items" / "en"
    (item / "work").mkdir(parents=True)
    (proj / "project.yaml").write_text("name: x\n")
    new, rec, note = FG.run(Ctx(proj, item, "a history of the bay"), "spec", SPEC, str(item / "work"), none_complete)
    assert rec["where"] == "project" and rec["file"] == str(proj / "facts.md") and os.path.isfile(rec["file"])
    assert rec["softened"] == 3 and not rec["ai"] and "word rules only" in note and "facts.md" in note
    (proj / "items" / "zh").mkdir()                                     # two versions: each keeps its own record
    _, rec, note = FG.run(Ctx(proj, item, "a history of the bay", "zh"), "spec", SPEC, str(item / "work"),
                          none_complete)
    assert rec["where"] == "item" and rec["file"] == str(item / "work" / "facts.md") and "事实核查" in note


def _ps_ctx(tmp_path, request, **params):
    proj = tmp_path / "proj"
    proj.mkdir(exist_ok=True)
    (proj / "project.yaml").write_text(f"name: Elliott Bay\nprompt: {request}\n")
    ctx = DR.Ctx(str(proj), "en", dict(_inputs={}, platforms=["youtube"], **params), "photo-story")
    os.makedirs(os.path.join(ctx.item_dir, "work", "frames"))
    for n in ("cover_a", "vCLIP"):           # the stills the spec names exist (no clips in these tests)
        with open(os.path.join(ctx.item_dir, "work", "frames", f"{n}.jpg"), "wb") as f:
            f.write(b"jpg")
    return ctx, proj


def test_draft_spec_checks_a_told_piece_and_records_the_counts(tmp_path, monkeypatch):
    monkeypatch.setenv("VSTUDIO_HOME", str(tmp_path / "home"))
    from vstudio.project.adapters import photostory as PS
    monkeypatch.setattr(PS, "add_respellings", lambda text, complete: text)
    ctx, proj = _ps_ctx(tmp_path, "a 60-second history of the Elliott Bay waterfront, narrated in English")
    calls = []

    def complete(task, system, body, **kw):
        calls.append(system)
        if system is FG.SYSTEM:
            return dict(json=dict(claims=ELLIOTT_CLAIMS[:1]), provider="claude-code", model="t")
        return dict(json=dict(content=SPEC, summary="A short history."), provider="claude-code", model="t")
    path = os.path.join(ctx.item_dir, "work", "spec.py")
    rec = PS.draft_spec(ctx, dict(id="story", author={}), path, complete=complete)
    text = open(path, encoding="utf-8").read()
    assert rec and FG.SYSTEM in calls and DR.data_module_ok(text)
    assert '"At **Pier 86** stands a grain terminal."' in text and "busiest" not in text and "前列" not in text
    f = rec["facts"]
    assert f["ai"] and f["softened"] == 3 and f["dropped"] == 0 and f["where"] == "project"
    assert os.path.isfile(proj / "facts.md") and f["file"] == str(proj / "facts.md")
    assert "Fact check: 3 unverifiable claims softened" in rec["review"]["summary"]["params"]["text"]


def test_draft_spec_never_checks_a_music_mode_piece(tmp_path, monkeypatch):
    monkeypatch.setenv("VSTUDIO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("VSTUDIO_MUSIC_DIRS", "")
    from vstudio.project.adapters import photostory as PS
    ctx, proj = _ps_ctx(tmp_path, "a 6-second history piece of the waterfront, no voice", mode="music")
    monkeypatch.setattr(PS, "music_bed", lambda *a, **k: "music_calm.wav")
    calls = []

    def complete(task, system, body, **kw):
        calls.append(system)
        return dict(json=dict(content=SPEC, summary="ok"), provider="claude-code", model="t")
    path = os.path.join(ctx.item_dir, "work", "spec.py")
    rec = PS.draft_spec(ctx, dict(id="story", author={}), path, complete=complete)
    assert rec and rec["facts"] is None and FG.SYSTEM not in calls and not os.path.exists(proj / "facts.md")
    assert "Seattle's busiest rail yard" in open(path, encoding="utf-8").read()


def test_explainer_draft_record_gets_the_fact_check(tmp_path):
    from vstudio.project.adapters import explainer as EX
    item = tmp_path / "item"
    item.mkdir()
    path = item / "SCRIPT.md"
    path.write_text("# SCRIPT\n\n## Line 1 — Yard (Frame 1)\n\n    Balmer Yard is Seattle's busiest rail yard.\n\n"
                    "ZH: 巴尔默调车场是西雅图最繁忙的调车场。\n", encoding="utf-8")
    rec = EX.fact_check(Ctx(tmp_path / "noproj", item, "explain the waterfront"), str(path),
                        dict(by="ai", review=dict(kind="text", lines=[], summary=dict(code="draft.generic",
                                                                                     params=dict(text="ok")))),
                        none_complete)
    text = path.read_text(encoding="utf-8")
    assert "    Balmer Yard is a busy rail yard." in text and "最繁忙" not in text and EX.script_format_ok(str(path))
    assert rec["facts"]["softened"] == 1 and rec["facts"]["where"] == "item" and os.path.isfile(rec["facts"]["file"])
    assert rec["review"]["summary"]["params"]["text"] == "ok"
    assert "Fact check" in rec["review"]["lines"][0]["params"]["label"]
def test_plan_card_warns_only_for_told_projects():
    from vstudio.intake import plan as PL
    hist = dict(recipe="photo-story", name="Elliott Bay waterfront history", params=dict(mode="narration"))
    mood = dict(recipe="photo-story", name="Autumn essay", params=dict(mode="music"))
    vlog = dict(recipe="vlog", name="Seattle history trip", params={})
    expl = dict(recipe="explainer", name="Quantization", params={})
    assert PL.fact_risks([mood, vlog]) == []
    assert PL.fact_risks([dict(mood, name="Elliott Bay history")]) == []          # music mode: no voice, no check
    en = PL.fact_risks([mood, hist])
    assert len(en) == 1 and "fact-checked" in en[0] and "facts.md" in en[0]
    assert "事实核查" in PL.fact_risks([expl], "zh")[0] and PL.fact_risks([expl], "fr")[0].startswith("La narration")
    assert PL.fact_risks([dict(recipe="photo-story", name="Bay", params={},
                               template=dict(id="history-explainer"))]) == [PL.FACT_RISK["en"]]


