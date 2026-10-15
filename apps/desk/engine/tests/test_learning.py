"""Human-led thought/material workspace: durable notes, local-only voice tools and explicit edit invocation."""
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _isolate  # noqa: E402,F401
from desk_engine.learning import Learning  # noqa: E402
from desk_engine.common import BadRequest  # noqa: E402
from vstudio import media  # noqa: E402
from vstudio.project.core import Project  # noqa: E402


class Workspace(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=self.temp.name
        self.env=mock.patch.dict(os.environ,{'VSTUDIO_HOME':os.path.join(self.root,'home'),'VSTUDIO_CACHE':os.path.join(self.root,'cache'),'VSTUDIO_DEFAULT_PERSONA':'1','VSTUDIO_LLM_PROVIDER':'none'})
        self.env.start()
        self.ib=SimpleNamespace(history=mock.Mock(),bus=mock.Mock(),runner=SimpleNamespace(python=sys.executable,env=dict(os.environ)),_forget_engine=mock.Mock())
        self.api=Learning(self.ib)
        self.source=os.path.join(self.root,'source.mp4')
        media.run(['ffmpeg','-y','-f','lavfi','-i','color=red:s=320x240:r=30:d=3','-f','lavfi','-i','sine=frequency=600:duration=3',*media.delivery_args(preset='ultrafast',audio=True,encoder='libx264'),self.source])

    def tearDown(self):
        self.env.stop();self.temp.cleanup()

    def create(self):
        return self.api.create(dict(idea='My own idea https://www.youtube.com/watch?v=6WaeGfLnRvc&t=3198s',thoughts='I need to think about this.',files=[self.source]))

    def test_creating_reading_and_writing_do_not_start_a_model_or_renderer(self):
        with mock.patch('vstudio.llm.complete',side_effect=AssertionError('No AI without a request')),mock.patch('desk_engine.pilot.spawn',side_effect=AssertionError('No auto render')):
            d=self.create();sid=next(iter(d['sources']))
            after=self.api.update(d['id'],dict(action='note',text='My own point, unchanged.',source=sid,at=1.25))
            self.assertEqual(after['notes'][-1]['text'],'My own point, unchanged.')
            self.assertEqual(after['notes'][-1]['at'],1.25)
            self.assertEqual(self.api.get(d['id'])['notes'],after['notes'])
            self.assertEqual(self.api.list()['workspaces'][0]['id'],d['id'])
            self.api.update(d['id'],dict(action='post',text='My final edited post.'))
            self.assertEqual(self.api.get(d['id'])['post'],'My final edited post.')
            revised=self.api.update(d['id'],dict(action='revise-note',note=after['notes'][-1]['id'],text='My revised thought.'))
            self.assertEqual(revised['notes'][-1]['text'],'My revised thought.')
            self.assertEqual(revised['notes'][-1]['revisions'][0]['text'],'My own point, unchanged.')
            tool=self.api.update(d['id'],dict(action='tool',job='aabbcc112233'))
            self.assertEqual(tool['tool_jobs'][0]['id'],'aabbcc112233')

    def test_quote_does_not_become_my_teleprompter(self):
        d=self.create();sid=next(iter(d['sources']))
        out=self.api.update(d['id'],dict(action='note',text='An original source quote',kind='quote',source=sid,at=1))
        self.assertNotIn('An original source quote',out['script'])
        self.assertIn('I need to think',out['script'])

    def test_bounds_missing_sources_and_unsafe_links_are_rejected(self):
        d=self.create();sid=next(iter(d['sources']))
        for body in [dict(action='note',text='x',source=sid,at=float('nan')),dict(action='note',text='x',source=sid,at=8),dict(action='link',url='javascript:alert(1)'),dict(action='files',files=['/no/such/file'])]:
            with self.assertRaises(BadRequest): self.api.update(d['id'],body)
        self.assertEqual(len(self.api.get(d['id'])['notes']),1)
        with self.assertRaises(BadRequest): self.api.get('../elsewhere')

    def test_user_orders_real_parts_then_requests_the_shared_edit_engine(self):
        d=self.create();sid=next(iter(d['sources']))
        d=self.api.update(d['id'],dict(action='credit',source=sid,credit=dict(title='A demo',creator='Author',locator='https://example.com/demo')))
        d=self.api.update(d['id'],dict(action='block',block=dict(source=sid,start=0,end=1,point='Original claim')))
        take=os.path.join(self.root,'my-take.mp4')
        import shutil
        shutil.copyfile(self.source,take)
        d=self.api.update(d['id'],dict(action='take',files=[take]))
        mine=next(k for k,s in d['sources'].items() if s['role']=='commentary')
        d=self.api.update(d['id'],dict(action='block',block=dict(source=mine,start=1,end=2,point='My interpretation')))
        first=d['blocks'][0]['id'];last=d['blocks'][1]['id']
        d=self.api.update(d['id'],dict(action='move',block=last,delta=-1))
        self.assertEqual(d['blocks'][0]['id'],last)
        d=self.api.update(d['id'],dict(action='move',block=last,delta=1))
        with mock.patch('desk_engine.pilot.spawn') as spawn:
            res=self.api.edit(d['id'])
            self.assertTrue(res['ok']);self.assertIn('outline,montage',spawn.call_args.kwargs['args'])
            from desk_engine.common import batch_id
            self.assertEqual(res['id'],batch_id(os.path.join(res['dir'],'state')))
        from desk_engine.common import read_json
        montage=read_json(os.path.join(res['dir'],'items/main/work/montage.json'))
        self.assertEqual([s['point'] for s in montage['segments']],['Original claim','My interpretation'])
        self.api.update(d['id'],dict(action='remove',block=first))
        self.assertTrue(os.path.isfile(self.source))

    def test_new_camera_materials_do_not_replace_old_takes(self):
        d=self.create()
        d=self.api.update(d['id'],dict(action='take',files=[self.source]))
        self.assertEqual([s['role'] for s in d['sources'].values()],['commentary'])
        self.assertEqual(len(d['blocks']),0)
        self.assertTrue(os.path.isfile(self.source))

    def test_source_text_is_readable_bounded_and_never_becomes_personal_testimony(self):
        path=os.path.join(self.root,'book-notes.md')
        text='\ufeff# Source passage\n原文观点。<img src=x onerror=alert(1)>\n'
        with open(path,'w',encoding='utf-8') as f:f.write(text)
        with mock.patch('vstudio.llm.complete',side_effect=AssertionError('No AI for reading')):
            d=self.api.create(dict(idea='Reading and thinking',files=[path]))
            self.assertFalse(d['sources'])
            sid=next(iter(d['readings']))
            self.assertEqual(d['readings'][sid]['text'],text.lstrip('\ufeff'))
            self.assertEqual(d['script'],'')
            quote=self.api.update(d['id'],dict(action='note',text='原文观点。',source=sid,at=None,kind='quote'))
            self.assertEqual(quote['notes'][0]['source'],sid)
            self.assertEqual(quote['script'],'')
            own=self.api.update(d['id'],dict(action='note',text='This is my interpretation.',source=sid,at=None))
            self.assertEqual(own['script'],'This is my interpretation.')
            self.assertEqual(self.api.get(d['id'])['readings'][sid]['text'],text.lstrip('\ufeff'))
            with self.assertRaises(BadRequest):self.api.update(d['id'],dict(action='note',text='x',source=sid,at=1))
            with self.assertRaises(BadRequest):self.api.update(d['id'],dict(action='block',block=dict(source=sid,start=0,end=1)))
        with open(path,'w',encoding='utf-8') as f:f.write('文'*100001)
        read=self.api.get(d['id'])['readings'][sid]
        self.assertEqual(len(read['text']),100000);self.assertTrue(read['truncated'])
        self.assertEqual(os.path.getsize(path),300003)
        os.rename(path,path+'.moved')
        self.assertTrue(self.api.get(d['id'])['readings'][sid]['unavailable'])
        self.assertEqual(len(self.api.get(d['id'])['notes']),2)

    def test_local_only_dictation_never_falls_through_to_cloud(self):
        from vstudio.create import store
        d=self.create();rec=os.path.join(store.recordings_root(),'thought');os.makedirs(rec)
        import json
        with open(os.path.join(rec,'session.json'),'w') as f:json.dump({'tracks':{'mic':{'file':'mic.webm'}}},f)
        with open(os.path.join(rec,'mic.webm'),'wb') as f:f.write(b'fixture')
        with mock.patch('vstudio.asr.providers',return_value=[dict(provider='openai',kind='api',ready=True)]),mock.patch('vstudio.asr.transcribe') as transcribe:
            with self.assertRaises(BadRequest):self.api.dictate(d['id'],rec)
            transcribe.assert_not_called()
        with mock.patch('vstudio.asr.providers',return_value=[dict(provider='faster',kind='local',ready=True)]),mock.patch('vstudio.asr.transcribe',return_value=dict(text='My exact words.')) as transcribe:
            out=self.api.dictate(d['id'],rec)
            self.assertEqual(out['text'],'My exact words.')
            self.assertEqual(transcribe.call_args.kwargs['backend'],'faster')

if __name__=='__main__':unittest.main()
