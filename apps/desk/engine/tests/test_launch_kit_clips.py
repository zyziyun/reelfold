"""Dogfood 2026-10-11 (a 0.2.7 promo from 13 screen recordings + BRIEF.md): launch-kit failed at its 2nd step with a
raw traceback - the features step ran on the seeded example's CHANGELOG.md while the config was still being drafted.
A launch kit from her clips + a brief (no changelog) now drafts its config from the brief's shot table, the features
and capture steps run on it, and a step that fails says one plain line with a failure code, never a traceback."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import _isolate  # noqa: E402,F401

BRIEF = """# Quill Notes 2.0 - launch promo brief

Dark space, one teal accent.

| # | Take | Use | On screen (EN) | 中文 |
|---|---|---|---|---|
| 1 | `01-home.mp4` | 0:00-0:04 · Home lands | Quill Notes 2.0 | Quill Notes 2.0 |
| 2 | `02-tag.mp4` | 0:04-0:08 · tags | Tags itself. | 自己打标签。 |
| 3 | end card | 0:08-0:11 · logo | Quill Notes - free for Mac. quillnotes.app | 速记 Quill Notes —— 免费的 Mac 应用。quillnotes.app |
"""
REQUEST = ("Make an 11-second premium launch promo for Quill Notes 2.0 from the clips in this folder, following "
           "BRIEF.md: open on Home with no hook, tight cuts at 1.1× with fast smooth animated transitions, the "
           "built-in tech music bed, and export 16:9 and 9:16 in English and Chinese.")


def _clip(path):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x202020:s=640x400:r=30:d=6",
                    "-f", "lavfi", "-i", "color=c=white:s=40x40:r=30:d=6", "-filter_complex",
                    "[0][1]overlay=x='40+mod(t*60\\,300)':y=150", "-pix_fmt", "yuv420p", path], check=True)


class LaunchKitFromClipsAndABrief(unittest.TestCase):
    def test_brief_only_kit_drafts_runs_and_fails_in_plain_words(self):
        from desk_engine import pilot
        from vstudio.project.core import Project
        root = tempfile.mkdtemp()
        raw = os.path.join(root, "raw")
        os.makedirs(raw)
        shots = [os.path.join(raw, n) for n in ("01-home.mp4", "02-tag.mp4")]
        for s in shots:
            _clip(s)
        brief = os.path.join(root, "BRIEF.md")
        with open(brief, "w", encoding="utf-8") as f:
            f.write(BRIEF)
        p = Project.create(os.path.join(root, "promo"), recipe="launch-kit", inputs=dict(notes=[brief], shots=shots),
                           params=dict(languages=["en", "zh"]))
        p.data["prompt"] = REQUEST
        p.save()
        old = os.environ.get("VSTUDIO_HYPERFRAMES")
        os.environ["VSTUDIO_HYPERFRAMES"] = os.path.join(root, "no-hyperframes-here")   # the render fails, fast
        try:
            events = []
            p.run(autopilot=True, judge=lambda *a, **k: dict(provider="none"), on_event=events.append)
        finally:
            if old is None:
                os.environ.pop("VSTUDIO_HYPERFRAMES", None)
            else:
                os.environ["VSTUDIO_HYPERFRAMES"] = old
        item = os.path.join(p.dir, "items", "main")
        import yaml
        with open(os.path.join(item, "launch.config.yaml"), encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        self.assertEqual(cfg["product"]["name"], "Quill Notes")
        self.assertNotIn("release", cfg)
        self.assertEqual([x["caption"]["zh"] for x in cfg["features"]], ["Quill Notes 2.0", "自己打标签。"])
        done = {e["stage"] for e in events if e.get("event") == "stage-done"}
        self.assertTrue({"cp_config", "features", "capture"} <= done, events)
        with open(os.path.join(item, "work", "features.draft.yaml"), encoding="utf-8") as f:
            self.assertEqual([x["id"] for x in yaml.safe_load(f)["features"]], ["01-home", "02-tag"])
        fails = [e for e in events if e.get("event") == "stage-fail"]
        self.assertEqual([e["stage"] for e in fails], ["render"], fails)
        self.assertNotIn("Traceback", fails[0]["error"])
        self.assertIn("launch-kit render failed", fails[0]["error"])
        # a config the kit cannot use: its own code, so the app words it (never "a file couldn't be read")
        d = tempfile.mkdtemp()
        err = "RuntimeError: launch_kit.py exit 2:\nlaunch-kit config: launch.config.yaml:\n  - product.name is required"
        from vstudio import proctail
        code = proctail.tool_failure(err)
        with open(os.path.join(d, pilot.LOG), "w", encoding="utf-8") as f:
            f.write(json.dumps(dict(event="stage-fail", job="main", stage="features", error=err, **code)) + "\n")
        with open(os.path.join(d, pilot.REC), "w", encoding="utf-8") as f:
            json.dump(dict(pid=None, started=1.0, offset=0, exit=1, finished=2.0), f)
        fail = pilot.failure(d)
        self.assertEqual(fail["code"], "stage-launch-config")
        self.assertEqual(fail["params"]["fix"], "ask-fix-config")


if __name__ == "__main__":
    unittest.main()
