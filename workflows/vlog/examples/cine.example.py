"""Cine vlog project (synthetic clip names). Copy to <project>/work/project.py, rename the clips, then:

    python3 project.py stills 1 9 20 ...   # look at every effect before rendering
    python3 project.py video && python3 project.py audio && python3 project.py final

Shape that worked (a city day: an activity, then the city at night):
  hook   20 beats of 1-2 beat cuts UNDER her own hook sentence, big hook line on top, ends on a band closing
  title  Opening: 2.39 band opens on a wide shot, title around it, expands into the first chapter's clip
  ch 1   the activity, told in order of arrival (lift -> floor number -> view -> her -> the action);
         landscape takes stacked in Dual / Triptych bands, never cover-cropped
  ch 2   one memory-like transition chapter in Super8 (the single light leak lands here)
  ch 3   a beat montage of the landmark (hard cuts on beats), then a FilmStrip breather of photos
  ch 4   her on-camera line, then Slides of the second landmark, then match cuts (same shot, colour change)
  end    wide bands bookend the opening, the last photo settles into a Print, a quiet EndCard
Clip names refer to <work>/sdr/<name>.mp4, photo names to <work>/photos_full/<name>.jpg (scripts/cine_tools.py ingest).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib"))
from vstudio import cinefx  # noqa: E402
from vstudio.cinefx import (Clip, DoubleExp, Dual, EndCard, FilmStrip, Opening, Photo, Print, Project,  # noqa: E402
                            Slides, Strip, Super8, Triptych, sequence, shift)

# beat grid from the track itself (vstudio.beats); every B(n) below lands on the music
cinefx.configure(os.path.dirname(os.path.abspath(__file__)), "music/track.mp3")
B = cinefx.B
OFF = B(20)   # the hook runs before the title; everything after is shifted by it


def hook():
    """1 beat minimum per cut (half-beat cuts read as flicker), 2 beats for anything with text or a layout."""
    return sequence(0, [
        (2, lambda a, b: Photo(a, b, "pool_lesson", z=(1.0, 1.05))),           # the cover promise, sharp photo
        (2, lambda a, b: FilmStrip(a, b, ["tower_a", "tower_b"], edge="400T")),
        (1, lambda a, b: Clip(a, b, "tower_up", 0.3, look="bw")),
        (1, lambda a, b: DoubleExp(a, b, ("tower_up", 0.5), ("window_city", 4.0))),
        (2, lambda a, b: Triptych(a, b, [("pool_wide", 1.0, 0.55), ("pool_side", 0.5, 0.6),
                                         ("pool_end", 0.3, 0.6)], 0.14)),
        (1, lambda a, b: Photo(a, b, "pool_ladder", z=(1.08, 1.0))),
        (1, lambda a, b: Dual(a, b, ("swim_a", 3.0), ("swim_b", 3.0), 0.08)),
        (2, lambda a, b: Slides(a, b, [("pool_buoy", "85F pool")])),
        (1, lambda a, b: Clip(a, b, "selfie_pool", 0.6)),
        (2, lambda a, b: Print(a, b, "pool_deck", settle=B(1.2), fade_from=B(5), label="85F pool")),
        (1, lambda a, b: Clip(a, b, "landmark_pink", 0.5, look="night")),
        (1, lambda a, b: Clip(a, b, "selfie_tower", 6.0, look="night")),
        (1, lambda a, b: DoubleExp(a, b, ("tower_up", 2.0), ("river_walk", 0.2))),
        (2, lambda a, b: Strip(a, b, "river_pan", 14.0, close=B(1.2))),
    ])


def main_cut():
    S = [Opening(0, B(8), ("river_pan", 1.0), ("lift_panel", 0.3), "在85楼云上学游泳", "SWIMMING AT 85F", "2026 · 11 · 02")]
    S += [Clip(B(8), B(11), "lift_panel", 0.3 + B(2.5)),                 # continues the Opening's vertical clip
          Clip(B(11), B(15), "lift_selfie", 2.6),                        # the floor number lit in the mirror
          Photo(B(15), B(19), "window_view", z=(1.0, 1.06)),
          Clip(B(19), B(23), "pool_wave", 2.2),
          Dual(B(23), B(31), ("swim_a", 1.5), ("swim_b", 1.5), 0.25),    # two landscape swim takes, one shot
          Triptych(B(31), B(37), [("swim_a", 6.5, 0.5), ("swim_b", 5.5, 0.5), ("pool_wide", 0.5, 0.55)], B(1.5)),
          Photo(B(37), B(41), "pool_ladder", z=(1.0, 1.06))]
    S += [Super8(B(41), B(46), "corridor", 4.0, 1.2, date="11 2 '26"),
          Super8(B(46), B(53), "lobby_out", 8.0, 2.4, date="11 2 '26")]
    b = 53
    for clip, start, speed, n in [("tower_a_up", 4.5, 1.3, 2), ("tower_b_up", 0.3, 1.0, 2), ("tower_c", 0.4, 1.0, 1),
                                  ("tower_dusk", 3.0, 1.0, 2), ("tower_glass", 0.4, 1.3, 2)]:
        S.append(Clip(B(b), B(b + n), clip, start, speed=speed, look="night"))
        b += n
    S += [FilmStrip(B(62), B(70), ["tower_a", "tower_b", "tower_c"], edge="400T"),
          Clip(B(70), B(76), "talk_street", 0.0),                        # her on-camera line, lips in sync
          Slides(B(76), B(86), [("landmark_a", "the tower"), ("landmark_b", "from below")]),
          Clip(B(86), B(88), "landmark_blue", 2.0, look="night"),        # match cut: same framing,
          Clip(B(88), B(90), "landmark_pink", 0.5, look="night"),        # the colour changes on the beat
          Strip(B(90), B(98), "river_pan", 0.0, reveal=1.2),
          Dual(B(98), B(106), ("river_boat", 6.0), ("river_dock", 2.0), B(2)),
          Print(B(106), B(116), "river_photo", settle=B(4), fade_from=B(7.5), label="riverside  2026.11.02"),
          EndCard(B(116), B(122), "换个方式游上海", "SHANGHAI · 2026.11.02")]
    return S


def timeline():
    return hook() + [shift(s, OFF) for s in main_cut()]


# her own voice: (clip, src_a, src_b, timeline_at, [(src_t0, src_t1, caption)]); captions proofread, not raw ASR
VO = [("talk_hotel", 1.14, 4.12, 0.25, [(1.14, 4.12, "上海环球中心的85楼")]),
      ("talk_hotel", 6.52, 10.20, 3.50, [(6.52, 10.20, "这个酒店有一个云端游泳池")]),
      ("talk_hotel", 10.95, 16.40, OFF + B(19) + 0.25, [(10.95, 13.88, "我找了一个私教来教游泳"),
                                                         (13.88, 16.40, "感觉环境真的挺好的")]),
      ("talk_street", 0.0, 12.2, OFF + B(70), [(0.0, 2.6, "我现在觉得这里好好看"),
                                               (2.6, 12.2, "当年在这里两年都没好好逛过")])]

P = Project(
    timeline, vo=VO,
    labels=[(OFF + B(8) + 0.3, "云端", "85F · IN THE CLOUDS"), (OFF + B(41) + 0.3, "出发", "HEADING OUT"),
            (OFF + B(53) + 0.2, "仰望", "LOOKING UP"), (OFF + B(90) + 0.6, "江边", "BY THE RIVER")],
    hook=(0.15, B(7) - 0.05, "换个方式游上海"),       # the cover title, said in the first second
    leak=OFF + B(41),                                 # the one light leak: into the Super8 chapter
    dips=[OFF, OFF + B(70), OFF + B(90)],             # chapter breaks dip to black, never flash white
    sfx=[("shutter_b", B(13) + 0.02, 0.22), ("camera", B(17) + B(1.2) - 0.1, 0.22),
         *[("shutter_b", OFF + B(76) + k * B(5) + 0.02, 0.35) for k in range(2)],
         ("camera", OFF + B(106) + B(4) - 0.15, 0.3)],
    total=OFF + B(122), out="vlog.mp4")

if __name__ == "__main__":
    cinefx.cli(__file__)
