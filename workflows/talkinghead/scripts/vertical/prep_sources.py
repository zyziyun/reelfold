#!/usr/bin/env python3
"""Convert phone clips (iPhone HLG / Dolby Vision HDR, or plain SDR) to SDR 1080p H.264, extract audio,
transcribe with word timestamps.
usage: python3 prep_sources.py WORK_DIR clip1.MOV clip2.MOV ...   (clips are numbered 1..N in order)
env PROMPT="术语 列表 ..."   whisper initial_prompt (fixes English terms in Chinese speech)
env TONEMAP=avconvert|ffmpeg  force a tone-map backend (default: avconvert for HDR clips when present, else ffmpeg)
env ORIENT=vertical|horizontal   body orientation to build (default vertical). A landscape clip (webcam, camera,
                               Zoom) for a vertical body is reframed to 9:16 with vstudio.reframe face mode: the
                               face is tracked (One Euro smoothed virtual camera, dead zone, eased pans, cut-aware),
                               kept in the platform safe box; no face -> pad-blur. ORIENT=horizontal keeps 16:9
                               (for compose --platform youtube / bilibili; vertical clips are then left as they are).
env KEEP_LANDSCAPE=1           same as ORIENT=horizontal (old flag)
env PLATFORM=douyin            safe box used by the reframe (default persona platforms.default, 9:16)
env REFRAME_MODE=face|pad-blur|center   override the reframe mode

Outputs per clip i: sdr$i.mp4 (picture + sound cut_pass1 cuts from), a$i.wav (16k mono), a$i.json (whisper),
sdr$i.crop.json (reframe plan, landscape -> vertical only); prep.json collects per clip: size, mode, face hit
rate and the picture UPSCALE factor (compose.py caps the punch-in with it so an upscaled crop doesn't go soft).
Built on vstudio.media.to_sdr (avconvert, else ffmpeg zscale/tonemap=hable, else libplacebo, else a warned
approximation), vstudio.reframe, media.extract_wav and vstudio.asr (via ../asr.py). Plain Python (no bash) so it
runs on Windows too; prep_sources.sh forwards here.
"""
import json
import os
import pathlib
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4] / "lib"))
sys.path.insert(0, HERE)
from vstudio import media  # noqa: E402

# fit inside 1080x1920 (portrait) or 1920x1080 (landscape); ffmpeg auto-applies the rotation tag first
FIT = ("scale='if(gt(iw,ih),1920,1080)':'if(gt(iw,ih),1080,1920)':force_original_aspect_ratio=decrease:"
       "force_divisible_by=2")


def prep(src, sdr, a16, backend):
    media.to_sdr(src, sdr, backend=backend, fit=FIT, crf=14)
    info = media.probe(sdr)
    try:
        si = media.probe(src)
        up0 = max(1.0, info["w"] / max(1, min(si["display_w"], si["display_h"]) if info["w"] < info["h"]
                                      else si["display_w"]))
    except Exception:  # noqa: BLE001
        up0 = 1.0                                    # the fit step may already have enlarged a small source
    orient = "horizontal" if os.environ.get("KEEP_LANDSCAPE") == "1" else os.environ.get("ORIENT", "vertical")
    rec = dict(src=os.path.basename(src), w=info["w"], h=info["h"], mode="as-is", upscale=round(up0, 3))
    if info["w"] > info["h"] and orient != "horizontal":
        # Landscape clip -> 9:16 body: face-tracked virtual camera (vstudio.reframe), pad-blur when no face.
        from layout import resolve_profile
        from vstudio import platform as P
        from vstudio import reframe as R
        prof = resolve_profile(os.environ.get("PLATFORM") or None)
        if prof.h < prof.w or (prof.w, prof.h) != (1080, 1920):
            prof = resolve_profile(None)             # the body is always 1080x1920; 3:4 is derived in compose
        tmp = sdr[:-4] + ".land.mp4"
        os.replace(sdr, tmp)
        pl = R.plan(tmp, 1080, 1920, mode=os.environ.get("REFRAME_MODE", "face"), safe=P.safe_box(prof),
                    fallback="pad-blur")
        R.render(tmp, sdr, pl, encode_args=["-c:v", "libx264", "-crf", "14", "-preset", "medium", "-pix_fmt",
                                            "yuv420p", *media.BT709, "-c:a", "aac", "-b:a", "256k"])
        with open(sdr[:-4] + ".crop.json", "w") as f:
            json.dump(pl, f)
        os.remove(tmp)
        cw = pl.get("crop_w") if pl["mode_used"] in ("face", "center") else None
        up = (1080 / cw if cw else 1.0) * up0
        rec.update(mode=pl["mode_used"], hit_rate=pl.get("hit_rate"), upscale=round(up, 3), stats=pl.get("stats"))
        print(f"landscape source -> 9:16 via reframe {pl['mode_used']} (face hit rate {pl.get('hit_rate')}, "
              f"crop {cw and round(cw)}px wide, x{up:.2f} upscale"
              f"{': soft, compose caps the punch-in' if up > 1.3 else ''}); ORIENT=horizontal keeps it 16:9")
    elif info["w"] < info["h"] and orient == "horizontal":
        print("vertical source kept vertical; compose --platform youtube puts it on a blurred 16:9 fill")
    pj = os.path.join(os.path.dirname(os.path.abspath(sdr)), "prep.json")
    allp = {}
    if os.path.exists(pj):
        with open(pj) as f:
            allp = json.load(f)
    allp[os.path.basename(sdr)] = rec
    with open(pj, "w") as f:
        json.dump(allp, f, indent=1)
    media.extract_wav(sdr, a16, sr=16000, channels=1)
    info = media.probe(sdr)
    print(f"{os.path.basename(sdr)}: {info['w']}x{info['h']} {info['fps']:.3f} fps {info['duration']:.1f}s",
          flush=True)


def main(argv):
    if len(argv) < 2 or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv[:1] in (["-h"], ["--help"]) else 1
    work, clips = argv[0], argv[1:]
    os.makedirs(work, exist_ok=True)
    prompt = os.environ.get("PROMPT")
    for i, src in enumerate(clips, 1):
        sdr, wav = os.path.join(work, f"sdr{i}.mp4"), os.path.join(work, f"a{i}.wav")
        prep(src, sdr, wav, os.environ.get("TONEMAP") or "auto")
        subprocess.run([sys.executable, os.path.join(HERE, "..", "asr.py"), wav, os.path.join(work, f"a{i}.json"),
                        *(["--prompt", prompt] if prompt else [])], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
