"""Make the voice samples Settings > Voice plays (src/renderer/src/settings/voice-samples/*.mp3): one line per free
voice, said by the real engine (vstudio.tts) - the Chinese voices by Qwen3-TTS, the English one by Kokoro.

    VSTUDIO_QWEN_TTS_MODEL=<tts-qwen-zh folder> VSTUDIO_KOKORO_MODEL=<tts-kokoro folder> \
        python scripts/voice-samples/make_voice_samples.py          # PYTHONPATH=<repo>/lib, mlx-audio installed

Re-run when a voice's model or the default line changes; the files are small (about 50 KB each).
"""
import os
import subprocess
import sys

from vstudio import tts

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src", "renderer", "src", "settings",
                   "voice-samples")
ZH_LINE = "大家好，欢迎回来。今天我们用五分钟，讲清楚 MCP 到底是什么。"
EN_LINE = "Welcome back. In the next five minutes, we'll see what MCP really is."


def mp3(wav, dst):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-ac", "1", "-ar", "24000", "-c:a", "libmp3lame",
                    "-b:a", "48k", dst], check=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    for v in tts.QWEN_ZH_VOICES:
        mp3(tts.synth(ZH_LINE, engine="qwen", voice=v), os.path.join(OUT, f"zh-{v}.mp3"))
        print("zh", v)
    mp3(tts.synth(EN_LINE, engine="kokoro", voice=tts.DEFAULT_VOICE["kokoro"]), os.path.join(OUT, "en-kokoro.mp3"))
    print("en kokoro")


if __name__ == "__main__":
    sys.exit(main())
