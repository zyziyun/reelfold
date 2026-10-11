"""A music-only clip (her Seattle drone vlog) whose transcript is whisper's "Thank you." at 0:00 and 0:33: the clip page
reads no words, so it opens on its timeline and nothing is captioned from it. Real speech keeps every word."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import _isolate  # noqa: E402,F401

from desk_engine import outputs as OU  # noqa: E402

HALLUCINATED = [dict(w="Thank", t=0.0, te=2.02, p=0.227), dict(w="you.", t=2.02, te=2.76, p=0.997),
                dict(w="Thank", t=33.92, te=35.32, p=0.215), dict(w="you.", t=35.32, te=36.22, p=0.998)]


class NoSpeechWords(unittest.TestCase):
    def test_hallucinated_words_are_no_words(self):
        self.assertEqual(OU._heard(HALLUCINATED, 59.0), [])
        self.assertEqual(OU._heard([], 59.0), [])

    def test_real_speech_is_kept(self):
        real = [dict(w=w, t=0.3 + k * 0.4, te=0.6 + k * 0.4, p=0.92) for k, w in enumerate(
            "so this is the lake we hiked to this morning and it was worth it".split())]
        real += [dict(w="Thank", t=6.0, te=6.3, p=0.95), dict(w="you.", t=6.3, te=6.6, p=0.97)]
        self.assertEqual(OU._heard(real, 7.0), real)

    def test_an_asr_sidecar_of_music_reads_no_words(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "vlog.mp4")
            open(f, "wb").close()
            seg = lambda a, b, p0: dict(start=a, end=b, text=" Thank you.", no_speech_prob=0.1, avg_logprob=-0.3,  # noqa: E731
                                        words=[dict(word=" Thank", start=a, end=a + 1.4, probability=p0),
                                               dict(word=" you.", start=a + 1.4, end=b, probability=0.99)])
            with open(f + ".asr.json", "w") as fh:
                json.dump({"k": dict(segments=[seg(0.0, 2.76, 0.23), seg(33.9, 36.2, 0.21)])}, fh)
            self.assertEqual(OU._asr_for(f), [])


if __name__ == "__main__":
    unittest.main()
