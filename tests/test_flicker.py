"""Flicker QC (vstudio.flicker): a render with a white flash, a dip through black or a blinking subtitle fails;
hard cuts, crossfades, slow fades and real motion pass.

2026-10-12: she found every DJI film "屏闪有点厉害" (white flash hits, a light-leak transition, subtitles cut out for
a frame before the next one, a timeline box popping in)."""
import shutil
import subprocess

import numpy as np
import pytest

from vstudio import flicker as FL

FPS = 30


def _grid(levels):
    """(n,) mean levels -> an (n, 8, 8) luma grid with a little texture."""
    r = np.random.default_rng(1)
    return np.asarray(levels, np.float32)[:, None, None] + r.normal(0, 0.3, (len(levels), 8, 8)).astype(np.float32)


def test_hard_cut_and_crossfade_pass():
    y = np.r_[np.full(90, 60.0), np.full(90, 140.0)]                 # a hard cut: one step
    assert FL.measure(_grid(y), FPS)["ok"]
    y = np.r_[np.full(90, 60.0), np.linspace(60, 140, 24), np.full(90, 140.0)]   # 0.8 s crossfade
    rep = FL.measure(_grid(y), FPS)
    assert rep["ok"] and rep["max_jump"] < 5


def test_white_flash_and_dip_fail():
    y = np.full(240, 80.0)
    y[100:115] = np.r_[np.linspace(80, 250, 8), np.linspace(250, 80, 7)]    # 0.5 s flash to white
    rep = FL.measure(_grid(y), FPS)
    assert not rep["ok"] and any(e["kind"] == "flash" for e in rep["events"])
    assert 3.2 < rep["events"][0]["t"] < 3.9
    y = np.full(240, 120.0)
    y[100:118] = np.r_[np.linspace(120, 0, 9), np.linspace(0, 120, 9)]     # dip to black between shots
    assert not FL.measure(_grid(y), FPS)["ok"]


def test_subtitle_blink_fails_and_eased_change_passes():
    F = _grid(np.full(240, 50.0))
    F[:, 6:8, 1:7] += 40                                    # a subtitle in the bottom band
    blink = F.copy()
    blink[120:123, 6:8, 1:7] -= 40                          # cut out for 3 frames before the next cue
    rep = FL.measure(blink, FPS)
    assert not rep["ok"] and rep["events"][0]["kind"] == "blink"
    eased = F.copy()                                        # the next cue crossfades: a shallow 0.4 s dip
    eased[114:126, 6:8, 1:7] -= 40 * np.r_[np.linspace(0, .15, 6), np.linspace(.15, 0, 6)][:, None, None]
    assert FL.measure(eased, FPS)["ok"]


def test_busy_activity_reduces_transient_scores_without_exempting_the_tail():
    r = np.random.default_rng(3)
    y = 100 + np.cumsum(r.normal(0, 6, 300))                # spray / glitter: busy everywhere
    y[150:156] += r.normal(0, 8, 6)
    grid = _grid(np.clip(y, 0, 255))
    report = FL.measure(grid, FPS, "energetic")
    raw = FL.transients(grid.mean((1, 2)), FPS).max()
    assert report["flash"] < raw  # local activity still suppresses busy changes
    # This random walk has a broad dip near 8 s; the old last-two-second
    # exemption hid it. Uniform frame brightness is not evidence of object motion.
    assert any(e["kind"] == "flash" and 8 <= e["t"] < 8.2 for e in report["events"])
    assert not any(e["t"] < 8 for e in report["events"])


def test_monotonic_opening_and_closing_fades_pass():
    y = np.r_[np.linspace(0, 100, 12), np.full(200, 100.0), np.linspace(100, 0, 45)]
    assert FL.measure(_grid(y), FPS)["ok"]


def test_mode_from_config():
    assert FL.mode_for({"qc": {"flicker": "warn"}}) == "warn"
    assert FL.mode_for({"qc": {"flicker": False}}) == "off"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_check_raises_on_a_rendered_flash(tmp_path):
    out = tmp_path / "flash.mp4"
    graph = ("color=c=0x404040:s=160x90:r=30:d=8,format=yuv420p,"
             "geq=lum='if(between(T,4,4.4),235,64)':cb=128:cr=128")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", graph, "-c:v", "libx264", "-crf", "18",
                    str(out)], check=True)
    with pytest.raises(FL.FlickerError) as e:
        FL.check(str(out), mode="fail", log=None)
    assert "flash" in str(e.value)
    assert (tmp_path / "flash.flicker.json").exists()
    assert FL.check(str(out), mode="warn", log=None)["ok"] is False


def test_retime_keeps_an_even_cadence():
    """59.94p at 1x / 0.5x and 29.97p at 1x decimate cleanly; 1.2x / 1.3x (the old calm defaults) blend instead of
    dropping every 4th-6th frame (the judder of the DJI films)."""
    from vstudio import ffmpeg_filters as F
    assert F.retime(59.94, 1.0, 30) == "fps=30"
    assert F.retime(59.94, 0.5, 30) == "setpts=PTS/0.5,fps=30"
    assert F.retime(29.97, 1.0, 30) == "fps=30"
    assert F.retime(119.88, 1.0, 30) == "fps=30"
    for src, sp in ((59.94, 1.2), (29.97, 1.3)):
        assert "framerate=fps=30" in F.retime(src, sp, 30)
    # slow motion past the source's frames: motion-compensated in-betweens (RIFE's ffmpeg fallback), or the old blend
    assert "minterpolate=fps=30" in F.retime(29.97, 0.5, 30)
    assert "minterpolate=fps=30" in F.retime(59.94, 0.25, 30)
    assert "framerate=fps=30" in F.retime(29.97, 0.5, 30, slowmo="blend")


def test_colour_flash_is_caught():
    """A warm light leak barely moves the luma but swings the colour cast for half a second."""
    F = _grid(np.full(240, 90.0))
    C = np.zeros((240, 2), np.float32)
    C[110:125, 1] = np.r_[np.linspace(0, 14, 8), np.linspace(14, 0, 7)]      # Cr up: an orange wash
    rep = FL.measure(F, FPS, "calm", C)
    assert not rep["ok"] and rep["events"][0]["kind"] == "colour" and rep["colour"] > 5
    C2 = np.zeros((240, 2), np.float32)
    C2[120:, 1] = 10.0                                                     # a cut to a warmer shot: a step
    assert FL.measure(F, FPS, "calm", C2)["ok"]


@pytest.mark.parametrize("region,expected", [(slice(None),1.0), (slice(0,2),.25)])
def test_flash_report_exposes_spatial_support_without_waiving_gate(region, expected):
    grid = np.full((240,8,8), 50, dtype=np.float32)
    grid[100:115, region, :] += 100
    report = FL.measure(grid, FPS, "energetic")
    event = next(e for e in report["events"] if e["kind"] == "flash")
    assert not report["ok"]
    assert event["active_cell_fraction"] == expected
    assert 100/FPS <= event["peak_t"] <= 115/FPS


@pytest.mark.parametrize("kind,span", [("flash_region", 15), ("blink", 3)])
def test_local_event_reports_grid_bounds_without_clearing_failure(kind, span):
    grid = np.full((240, 8, 8), 50, dtype=np.float32)
    grid[100:100 + span, 4:6, 2:4] += 180
    report = FL.measure(grid, FPS, "calm")
    event = next(e for e in report["events"] if e["kind"] == kind)
    assert not report["ok"]
    assert event["active_bounds"] == [.25, .5, .5, .75]
    assert event["active_cell_fraction"] == .062
    assert round(100/FPS, 3) <= event["peak_t"] < (100 + span)/FPS


def test_editorial_profile_defaults_to_calm_and_requires_explicit_energy():
    assert FL.profile_for() == 'calm'
    assert FL.profile_for({'mode': 'music'}) == 'calm'
    assert FL.profile_for({'qc': {'flicker_profile': 'energetic'}}) == 'energetic'
    with pytest.raises(ValueError, match='Unknown flicker profile'):
        FL.profile_for({'qc': {'flicker_profile': 'typo'}})


def test_cut_context_explains_comparison_window_without_waiving_failure(tmp_path, monkeypatch):
    report = dict(ok=False, limits=FL.LIMITS['calm'], events=[dict(kind='blink', t=3., end=3.03, peak_t=3.033, level=8.2)])
    monkeypatch.setattr(FL, 'analyze', lambda *a: report)
    path = tmp_path / 'qc.json'
    with pytest.raises(FL.FlickerError):
        FL.check('render.mp4', mode='fail', report_path=path, log=None, cuts=[3.1, 7.6])
    import json
    saved = json.loads(path.read_text())
    assert saved['ok'] is False
    assert saved['events'][0]['nearby_cuts'] == [3.1]
    assert saved['events'][0]['level'] == 8.2
    assert 'cuts at 3.10s' in FL.describe(saved)


def test_cut_context_uses_each_detectors_window():
    events = [dict(kind=kind, t=3, peak_t=3) for kind in ('blink', 'flash', 'colour')]
    report = FL.add_cut_context(dict(ok=False, events=events), [3.5])
    assert 'nearby_cuts' not in report['events'][0]
    assert report['events'][1]['nearby_cuts'] == [3.5]
    assert report['events'][2]['nearby_cuts'] == [3.5]


@pytest.mark.parametrize('duration', [4, 8])
def test_flash_near_end_is_not_hidden_by_a_closing_fade_exemption(duration):
    y = np.full(duration * FPS, 80.0)
    start = len(y) - 45  # 1.5 seconds before the end; enough context on both sides
    y[start:start + 6] = 230
    report = FL.measure(_grid(y), FPS)
    assert not report['ok']
    assert any(e['kind'] == 'flash' and e['t'] >= duration - 1.6 for e in report['events'])
