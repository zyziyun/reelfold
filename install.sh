#!/usr/bin/env bash
# video-studio installer (the open-source engine behind Reelfold): Python deps + open-licensed fonts and models into ~/.cache/video-studio.
# Re-runnable; skips files that already exist. Override the location with VSTUDIO_CACHE.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CACHE="${VSTUDIO_CACHE:-$HOME/.cache/video-studio}"
mkdir -p "$CACHE/fonts" "$CACHE/models"

fetch() {  # url dest
  if [ -s "$2" ]; then echo "  ✓ $(basename "$2")"; return; fi
  echo "  ↓ $(basename "$2")"; curl -fsSL "$1" -o "$2.part" && mv "$2.part" "$2"
}

echo "fonts (OFL) -> $CACHE/fonts"
fetch https://github.com/notofonts/noto-cjk/raw/main/Sans/SubsetOTF/SC/NotoSansSC-Regular.otf "$CACHE/fonts/NotoSansSC-Regular.otf"
fetch https://github.com/notofonts/noto-cjk/raw/main/Sans/SubsetOTF/SC/NotoSansSC-Bold.otf "$CACHE/fonts/NotoSansSC-Bold.otf"
fetch https://github.com/notofonts/noto-cjk/raw/main/Sans/SubsetOTF/SC/NotoSansSC-Medium.otf "$CACHE/fonts/NotoSansSC-Medium.otf"
fetch https://github.com/notofonts/noto-cjk/raw/main/Serif/SubsetOTF/SC/NotoSerifSC-Regular.otf "$CACHE/fonts/NotoSerifSC-Regular.otf"
fetch https://github.com/notofonts/noto-cjk/raw/main/Serif/SubsetOTF/SC/NotoSerifSC-Bold.otf "$CACHE/fonts/NotoSerifSC-Bold.otf"
fetch "https://github.com/google/fonts/raw/main/ofl/stixtwotext/STIXTwoText%5Bwght%5D.ttf" "$CACHE/fonts/STIXTwoText-Regular.ttf"
fetch "https://github.com/google/fonts/raw/main/ofl/stixtwotext/STIXTwoText-Italic%5Bwght%5D.ttf" "$CACHE/fonts/STIXTwoText-Italic.ttf"
fetch https://github.com/JetBrains/JetBrainsMono/raw/master/fonts/ttf/JetBrainsMono-Regular.ttf "$CACHE/fonts/JetBrainsMono-Regular.ttf"
fetch https://github.com/JetBrains/JetBrainsMono/raw/master/fonts/ttf/JetBrainsMono-Bold.ttf "$CACHE/fonts/JetBrainsMono-Bold.ttf"
# typography kit (vstudio.config FONTS display-zh / zh-humanist / serif-display): Instrument Serif for English titles,
# LXGW WenKai 霞鹜文楷 for quotes, Smiley Sans 得意黑 for Chinese headlines (only published as a zip: sha256-checked,
# then just its two font files are unpacked)
fetch "https://github.com/google/fonts/raw/7085eb89a950e85db5b166b7a58d414544b4140c/ofl/instrumentserif/InstrumentSerif-Regular.ttf" "$CACHE/fonts/InstrumentSerif-Regular.ttf"
fetch https://github.com/lxgw/LxgwWenKai/releases/download/v1.522/LXGWWenKai-Regular.ttf "$CACHE/fonts/LXGWWenKai-Regular.ttf"
if [ -s "$CACHE/fonts/SmileySans-Oblique.otf" ]; then echo "  ✓ SmileySans-Oblique.otf"; else
  SMILEY_ZIP="$CACHE/fonts/smiley-sans-v2.0.1.zip"
  fetch https://github.com/atelier-anchor/smiley-sans/releases/download/v2.0.1/smiley-sans-v2.0.1.zip "$SMILEY_ZIP"
  if python3 -c 'import hashlib,sys; sys.exit(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest() != sys.argv[2])' \
      "$SMILEY_ZIP" 299c0be6c960ae37361762eca76f7d0cd516615435bb96c0d4b98a1e70178a07; then
    unzip -o -q -j "$SMILEY_ZIP" SmileySans-Oblique.otf SmileySans-Oblique.ttf -d "$CACHE/fonts" && rm -f "$SMILEY_ZIP"
  else
    echo "  !! smiley-sans-v2.0.1.zip checksum mismatch - skipped (headlines fall back to Noto Sans SC)"; rm -f "$SMILEY_ZIP"
  fi
fi

echo "models (Apache-2.0, MediaPipe) -> $CACHE/models"
fetch https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task "$CACHE/models/face_landmarker.task"
fetch https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter/float16/latest/selfie_segmenter.tflite "$CACHE/models/selfie_segmenter.tflite"
fetch https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_multiclass_256x256/float32/latest/selfie_multiclass_256x256.tflite "$CACHE/models/selfie_multiclass_256x256.tflite"
echo "models (MIT: Beat This! beat tracker, TransNet V2 shot detector) -> $CACHE/models"
mkdir -p "$CACHE/models/beat_this" "$CACHE/models/transnetv2"
# mirrored on Reelfold's GitHub (MIT); the original JKU host is the fallback
fetch https://github.com/zyziyun/reelfold/releases/download/models-beat-this-final0/final0.ckpt "$CACHE/models/beat_this/final0.ckpt" \
  || fetch https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp/final0.ckpt "$CACHE/models/beat_this/final0.ckpt"
TNV2=https://media.githubusercontent.com/media/soCzech/TransNetV2/85cef72af9a916bdfd7cc94a670c9cdfbf12d1ed/inference/transnetv2-weights/variables
fetch "$TNV2/variables.index" "$CACHE/models/transnetv2/variables.index"
fetch "$TNV2/variables.data-00000-of-00001" "$CACHE/models/transnetv2/variables.data-00000-of-00001"

if [ "${SKIP_PIP:-0}" != "1" ]; then
  echo "python deps"
  python3 -m pip install -q -r "$HERE/requirements.txt"
  # Apple Silicon gets the fast local whisper; elsewhere faster-whisper is used.
  if [ "$(uname -s)-$(uname -m)" = "Darwin-arm64" ]; then python3 -m pip install -q mlx-whisper; else python3 -m pip install -q faster-whisper; fi
fi

command -v ffmpeg >/dev/null || echo "!! ffmpeg not found - install it (brew install ffmpeg / apt install ffmpeg)"
command -v npx >/dev/null || echo "!! node/npx not found - HyperFrames workflows (explainer, promo-recut) need Node 18+"
[ -f "$HERE/persona.local.yaml" ] || echo "tip: cp persona.example.yaml persona.local.yaml and fill in your brand/voice"
echo "done. export PYTHONPATH=\"$HERE/lib:\$PYTHONPATH\"   (or: pip install -e $HERE)"
