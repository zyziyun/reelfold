"""Take selection preserves nested candidates and grants the playback paths to the media bridge."""
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _isolate  # noqa: E402,F401
from desk_engine.inbox import Inbox, engine_answer  # noqa: E402


class TakeInboxTest(unittest.TestCase):
    def test_candidates_and_media_survive_real_inbox_mapping(self):
        with tempfile.TemporaryDirectory() as root:
            history = Mock()
            history.list.return_value = {"items": []}
            history.archived_dirs.return_value = []
            inbox = Inbox(root, history)
            units = [{"unit": "shot", "takes": [{"file": root + "/take.mp4", "sheet": root + "/sheet.jpg",
                       "revision": "review-rev", "scorecard": {"references": [{"path": root + "/ref.png"}]}}]}]
            doc = {"entries": [{"project": root, "id": "takes", "kind": "take-selection", "options": units}]}
            with patch.object(inbox, "real", return_value=True), patch.object(inbox, "_engine_inbox", return_value=doc):
                items = inbox.list()["items"]
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["take_units"], units)
            self.assertEqual(items[0]["options"], [])
            allowed = history.allow_media.call_args.args[0]
            for file in ("take.mp4", "sheet.jpg", "ref.png"):
                self.assertIn(root + "/" + file, allowed)
            answer = {"picks": {"shot": root + "/take.mp4"}, "reviews": {"shot": {"revision": "review-rev"}}}
            self.assertEqual(engine_answer("take-selection", answer), answer)

    def test_review_runs_separately_and_reports_failure_without_resume(self):
        from desk_engine.inbox import background
        with tempfile.TemporaryDirectory() as root:
            inbox = Inbox(root, Mock())
            item = dict(key='a'*16,kind='take-selection',engine=dict(dir=root,id='takes',item='one'))
            class InlineThread:
                def __init__(self, target, **kw): self.target = target
                def start(self): self.target()
            with patch.object(inbox,'list',return_value=dict(items=[item])), \
                 patch('desk_engine.inbox.threading.Thread',InlineThread), \
                 patch('vstudio.project.core.Project'), \
                 patch('vstudio.project.take_reviews.refresh',side_effect=ValueError('test failure')), \
                 patch.object(inbox,'resume') as resume:
                before = background()
                self.assertEqual(inbox.review_takes(item['key']),dict(ok=True))
                self.assertEqual(background(),before)
                self.assertEqual(next(iter(inbox._take_review.values()))['state'],'failed')
                resume.assert_not_called()
