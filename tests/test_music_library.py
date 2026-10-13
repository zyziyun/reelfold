"""The CC0 music library (vstudio.music + music_library.json): only licences free for bundling and published videos,
every track pinned (sha256) in the desk's first-run assets; the pick fits the video (words, pace, tempo) and the
videos of one goal never share a track (her DJI goal: three beat shorts all got the same 108 BPM bed although she
asked for each its own theme, rhythm and music); her recent videos' tracks go down; favourites / bans; a CC BY track's
credit reaches the post copy. A tiny fake library of synthetic files - no network, no real audio."""
import json
import os

import numpy as np
import pytest

from vstudio import assets as AS
from vstudio import music as MU

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("VSTUDIO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VSTUDIO_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("VSTUDIO_MUSIC_DIRS", "")
    monkeypatch.setenv("HOME", str(tmp_path / "userhome"))
    monkeypatch.delenv(MU.LIBRARY_ENV, raising=False)


# --------------------------------------------------------------------------- the real manifest
def test_manifest_has_only_free_licences_and_covers_the_moods():
    doc = MU.library_doc()
    assert MU.validate_library(doc) == []
    tr = doc["tracks"]
    assert 40 <= len(tr) <= 60
    assert {t["licence"] for t in tr} <= {"CC0-1.0", "PDM-1.0"}          # nothing that needs a credit or forbids reuse
    assert not any(t["artist"].lower() in MU.FORBIDDEN_ARTISTS for t in tr)
    styles = {t["style"] for t in tr}
    assert {"piano", "ambient", "acoustic", "cinematic", "pop", "electronic", "lofi", "documentary",
            "chinese"} <= styles
    assert any("corporate" in t["tags"] for t in tr)
    beat = sorted({round(t["bpm"]) for t in tr if t["steady"] and t["bpm"]})
    assert len(beat) >= 10 and beat[0] <= 90 and beat[-1] >= 125           # beat tracks over a range of tempos
    for t in tr:                                                             # the metadata every pick relies on
        assert len(t["energy_curve"]) == 24 and 0 <= t["energy"] <= 1 and t["duration"] > 30
        assert t["licence_evidence"].startswith("https://") and t["source_url"].startswith("https://")
        if t["steady"]:
            assert t["downbeats"] and t["loop"] and t["loop"]["end"] - t["loop"]["start"] >= 16


def test_validation_refuses_licences_that_are_not_free():
    good = dict(MU.library_doc()["tracks"][0])
    bad = [dict(good, id="a", licence="CC-BY-NC-4.0"),
           dict(good, id="b", url="https://cdn.pixabay.com/audio/x.mp3"),
           dict(good, id="c", artist="Rafael Krux"),
           dict(good, id="d", sha256="abc"),
           dict(good, id="e", licence="CC-BY-ND-4.0", licence_url="https://creativecommons.org/licenses/by-nd/4.0/"),
           dict(good, id="f", licence="YouTube Audio Library")]
    errs = MU.validate_library(dict(tracks=bad))
    for k in "abcdef":
        assert any(e.startswith(f"{k}:") for e in errs), (k, errs)
    assert MU.validate_library(dict(tracks=[good])) == []
    assert MU.validate_library(dict(tracks=[dict(good, licence_url="https://example.org/anything")]))


def test_the_library_is_a_pinned_first_run_download():
    lib = {t["file"]: t for t in MU.library_doc()["tracks"]}
    with open(os.path.join(ROOT, "apps", "desk", "packaging", "assets.json"), encoding="utf-8") as f:
        g = next(x for x in json.load(f)["groups"] if x["id"] == "music-library")
    assert g["required"] and g["env"] == {MU.LIBRARY_ENV: ""} and "targets" not in g
    assert {f["dest"]: (f["url"], f["sha256"], f["size"]) for f in g["files"]} == \
        {k: (t["url"], t["sha256"], t["size"]) for k, t in lib.items()}
    cli = AS.GROUPS["music-library"]                                         # the CLI skill fetches the same files
    assert {f["dest"] for f in cli["files"]} == set(lib) and cli["env"] == MU.LIBRARY_ENV


# --------------------------------------------------------------------------- a fake installed library
def _track(tid, style, mood, bpm, energy, tags=(), licence="CC0-1.0", artist="Test Artist"):
    return dict(id=tid, title=tid.replace("-", " ").title(), artist=artist, licence=licence,
                licence_url="https://creativecommons.org/publicdomain/zero/1.0/", source="test",
                source_url="https://example.org/" + tid, licence_evidence="https://example.org/licence",
                original_url="https://example.org/" + tid, url=f"https://example.org/{tid}.mp3", file=f"{tid}.wav",
                sha256="0" * 64, size=0, duration=120.0, mood=mood, style=style, tags=list(tags), bpm=bpm,
                bpm_detected=bpm, steady=bpm is not None, first_beat=0.1, downbeats=[0.1, 2.3], energy=energy,
                energy_curve=[energy] * 24, loop=dict(start=4.0, end=100.0) if bpm else None)


LIB = [
    _track("sunny-pop", "pop", "bright", 104, 0.8, ["pop", "summer"]),
    _track("ukulele-day", "acoustic", "bright", 96, 0.75, ["ukulele", "acoustic"]),
    _track("funk-loop", "pop", "bright", 115, 0.65, ["funk"]),
    _track("drive-beat", "electronic", "tech", 128, 0.85, ["electronic", "corporate"]),
    _track("slow-piano", "piano", "calm", None, 0.25, ["piano", "classical"]),
    _track("old-castle", "documentary", "story", 70, 0.4, ["documentary", "history"]),
    _track("erhu-night", "chinese", "tech", 127.9, 0.8, ["chinese", "erhu"]),
]


@pytest.fixture
def lib(tmp_path, monkeypatch):
    d = tmp_path / "library"
    d.mkdir()
    tracks = []
    for t in LIB:
        p = d / t["file"]
        p.write_bytes(b"RIFF" + bytes(64))
        tracks.append(dict(t, size=p.stat().st_size))
    man = tmp_path / "music_library.json"
    man.write_text(json.dumps(dict(kind="vstudio.music.library", version=1, tracks=tracks)))
    monkeypatch.setattr(MU, "LIBRARY_JSON", str(man))
    MU._LIB.clear()
    monkeypatch.setenv(MU.LIBRARY_ENV, str(d))
    yield d
    MU._LIB.clear()


def test_installed_library_tracks_join_the_pool(lib):
    ids = [t["id"] for t in MU.tracks()]
    assert "lib:sunny-pop" in ids and "builtin:calm" in ids
    assert MU.resolve("lib:slow-piano").endswith("slow-piano.wav")
    assert MU.beat_grid("lib:drive-beat") == (round(60 / 128, 5), 0.1)
    assert all(t["installed"] for t in MU.library())


def test_rank_fits_words_pace_and_tempo(lib):
    assert MU.rank("钢琴 安静一点", style="calm")[0]["id"] == "lib:slow-piano"
    assert MU.rank("讲讲这座古堡的历史 documentary")[0]["id"] == "lib:old-castle"
    assert MU.rank("中国风 夜景")[0]["id"] == "lib:erhu-night"
    assert MU.rank("产品发布 promo", style="fun", need_beat=True)[0]["id"] == "lib:drive-beat"
    fast = MU.rank("summer 卡点", style="fun", need_beat=True, shot_s=1.15)
    assert fast[0]["id"] == "lib:sunny-pop" and "104 BPM" in " ".join(fast[0]["fit"])
    assert all(t.get("steady") for t in fast[:5])                            # a beat reel never gets free-time piano
    slow = MU.rank("", shot_s=6.0)                                           # long calm shots: a low-energy track
    assert slow[0]["energy"] <= 0.45


def test_a_goal_group_gets_a_track_and_a_tempo_each(lib, tmp_path):
    picks = []
    for i, title in enumerate(["Jet Ski Summer 卡点", "Streets of Red 卡点", "Spray on Coeur d'Alene 卡点 summer"]):
        r = MU.choose(title, style="fun", need_beat=True, shot_s=1.1, min_duration=40,
                      project=str(tmp_path / f"p{i}"), item="main", group="goal1")
        picks.append(r[0])
    assert len({p["id"] for p in picks}) == 3
    assert len({round(p["bpm"]) for p in picks}) == 3
    # asking again (a resumed run, her answer) gives each video the same track
    again = MU.rank("Jet Ski Summer 卡点", style="fun", need_beat=True, shot_s=1.1, min_duration=40,
                    project=str(tmp_path / "p0"), item="main", group="goal1")
    assert again[0]["id"] == picks[0]["id"]
    # another group may use them again (only her recent videos push them down a little)
    other = MU.rank("Jet Ski Summer 卡点", style="fun", need_beat=True, shot_s=1.1, project=str(tmp_path / "q"),
                    item="main", group="goal2")
    assert all("group" not in " ".join(t["fit"]) for t in other)


def test_an_exhausted_library_reuses_rather_than_failing(lib, tmp_path):
    for t in MU.tracks():                                     # ban everything but one beat track
        if t["id"] != "lib:sunny-pop":
            MU.set_pref(t["id"], banned=True)
    a = MU.choose("卡点", style="fun", need_beat=True, project=str(tmp_path / "a"), item="main", group="g")
    b = MU.choose("卡点", style="fun", need_beat=True, project=str(tmp_path / "b"), item="main", group="g")
    assert a[0]["id"] == b[0]["id"] == "lib:sunny-pop"
    assert "another video of this group has it" in b[0]["fit"]


def test_recent_videos_tracks_go_down(lib, tmp_path):
    first = MU.choose("summer 卡点", style="fun", need_beat=True, project=str(tmp_path / "a"), item="main")[0]
    second = MU.choose("summer 卡点", style="fun", need_beat=True, project=str(tmp_path / "b"), item="main")[0]
    assert first["id"] != second["id"]
    assert [r["track"] for r in MU.history()] == [first["id"], second["id"]]
    assert MU.pick_of(str(tmp_path / "a"), "main") == first["id"]


def test_favourites_go_up_and_bans_are_never_picked(lib):
    top = MU.rank("summer 卡点", style="fun", need_beat=True)[0]["id"]
    MU.set_pref(top, banned=True)
    assert top not in [t["id"] for t in MU.rank("summer 卡点", style="fun", need_beat=True)]
    MU.set_pref("lib:funk-loop", favourite=True)
    assert MU.rank("summer 卡点", style="fun", need_beat=True)[0]["id"] == "lib:funk-loop"
    assert MU.prefs() == dict(favourites=["lib:funk-loop"], banned=[top])
    MU.set_pref(top, favourite=True)                          # a favourite is no longer banned
    assert top in MU.prefs()["favourites"] and top not in MU.prefs()["banned"]


def test_cc_by_library_track_credit_reaches_the_post_copy(lib, monkeypatch, tmp_path):
    doc = json.loads(open(MU.LIBRARY_JSON).read())
    doc["tracks"].append(dict(_track("by-song", "acoustic", "warm", 90, 0.5, ["acoustic"], licence="CC-BY-4.0",
                                     artist="Some Artist"), size=68,
                              licence_url="https://creativecommons.org/licenses/by/4.0/"))
    (lib / "by-song.wav").write_bytes(b"RIFF" + bytes(64))
    open(MU.LIBRARY_JSON, "w").write(json.dumps(doc))
    MU._LIB.clear()
    t = next(x for x in MU.tracks() if x["id"] == "lib:by-song")
    assert t["credit"].startswith('Music: "By Song" by Some Artist') and "licenses/by/4.0" in t["credit"]
    assert not next(x for x in MU.tracks() if x["id"] == "lib:sunny-pop")["credit"]       # CC0: none needed
    assert "lib:by-song" not in [x["id"] for x in MU.rank("acoustic", no_credit=True)]   # nowhere to print it
    from vstudio.project.adapters import vlog as V

    class A:
        job = "main"
        params = {}
        value = dict(pick=0)
        payload = dict(options=[dict(id=0, kind="track", track=t["id"], title=t["title"], source="library",
                                     license=t["license"], credit=t["credit"], path=t["path"], mood=t["mood"])],
                       group="g")

        class project:
            dir = str(tmp_path / "proj")
    res = V.music_apply(A())
    assert res["params"]["music_pick"]["credit"] == t["credit"]     # the music stage writes it to music_post.json
    assert MU.pick_of(str(tmp_path / "proj"), "main") == "lib:by-song"


def test_target_energy_and_tempo_from_pace():
    assert MU.target_energy("卡点 快节奏") > 0.7 and MU.target_energy("舒缓 治愈") < 0.4
    assert MU.target_energy("") is None and MU.target_energy("", shot_s=1.0) > MU.target_energy("", shot_s=6.0)
    assert MU.target_bpm(1.0) == 120 and MU.target_bpm(0.5) == 135 and MU.target_bpm(None) is None
    assert np.isclose(MU.target_bpm(1.2), 100)
