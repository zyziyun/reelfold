"""Human-led creation workspace. Reading, notes and material ordering never invoke an AI planner."""
import hashlib
import math
import os
import re
import threading
import time
import uuid
from urllib.parse import urlsplit

from .common import need, read_json, write_json
from . import pilot

_LOCK = threading.RLock()
VIDEO = {'.mp4', '.mov', '.m4v', '.webm', '.mkv'}
PAGE = {'.png', '.jpg', '.jpeg', '.webp'}


class Learning:
    def __init__(self, inbox):
        self.inbox = inbox

    def _project(self, ident):
        from vstudio.batch.clients import home
        from vstudio.project.core import Project
        need(isinstance(ident, str) and re.fullmatch('[0-9a-f]{12}', ident), 'select a creation workspace')
        d = os.path.join(home(), 'projects', 'learning-' + ident)
        need(os.path.isfile(os.path.join(d, 'learning.json')), 'this workspace is unavailable')
        return Project(d)

    def _save(self, p, doc):
        doc['updated'] = time.time()
        write_json(os.path.join(p.dir, 'learning.json'), doc)
        if self.inbox.bus:
            self.inbox.bus.publish('history')
        return doc

    def _files(self, inputs, paths, role=None):
        need(isinstance(paths, list) and len(paths) <= 100, 'attach up to 100 files')
        for path in paths:
            need(isinstance(path, str) and os.path.isabs(path) and os.path.isfile(path), 'select an existing material')
            ext = os.path.splitext(path)[1].lower()
            key = role or ('references' if ext in VIDEO else 'pages' if ext in PAGE else 'notes' if ext in ('.md', '.txt') else None)
            need(key and (not role or ext in VIDEO), 'select video, page images or text notes')
            old = inputs.get(key) or []
            inputs[key] = list(dict.fromkeys((old if isinstance(old, list) else [old]) + [path]))
        return inputs

    def _readings(self, inputs):
        """Local source notes are readable material, never silently promoted to the creator's ideas."""
        rows = {}
        paths = inputs.get('notes') or []
        for path in paths if isinstance(paths, list) else [paths]:
            ident = 'reading-' + hashlib.sha256(os.fsencode(os.path.abspath(path))).hexdigest()[:12]
            row = dict(id=ident, path=path, text='', truncated=False)
            try:
                with open(path, encoding='utf-8-sig') as f:
                    text = f.read(100001)
                row.update(text=text[:100000], truncated=len(text) > 100000)
            except (OSError, UnicodeError):
                row['unavailable'] = True
            rows[ident] = row
        return rows

    def list(self):
        from vstudio.batch.clients import home
        import glob
        rows=[]
        for f in glob.glob(os.path.join(home(),'projects','learning-*','learning.json')):
            d=read_json(f,{})
            if re.fullmatch('[0-9a-f]{12}',str(d.get('id',''))):
                rows.append({k:d[k] for k in ('id','title','updated')})
        return dict(workspaces=sorted(rows,key=lambda r:r['updated'],reverse=True))

    def capture(self, ident, session_dir):
        from vstudio.create import record, store
        p=self._project(ident)
        need(not (pilot.running(p.dir) or pilot.queued(p.dir)),'wait for the current render')
        need(isinstance(session_dir,str) and os.path.isabs(session_dir),'select a saved recording')
        d=record.need_session(session_dir)
        need(os.path.dirname(os.path.realpath(d))==os.path.realpath(store.recordings_root()),'choose a recording made here')
        need(not os.path.exists(os.path.join(d,'recording.lock')),'finish the recording first')
        sess=read_json(os.path.join(d,'session.json'),{})
        out=os.path.join(d,'work','learning-take.mp4')
        os.makedirs(os.path.dirname(out),exist_ok=True)
        record.mux(d,sess,out)
        # Preserve the camera, microphone and screen tracks; the mux is a convenient editable derivative.
        return self.update(ident,dict(action='take',files=[out]))

    def create(self, b):
        from vstudio.batch.clients import home
        from vstudio.project.core import Project
        idea, thoughts = b.get('idea'), b.get('thoughts') or ''
        need(isinstance(idea, str) and 0 < len(idea.strip()) <= 6000, 'name your creation or describe an idea')
        need(isinstance(thoughts, str) and len(thoughts) <= 20000, 'thoughts: up to 20000 characters')
        ins = self._files(dict(brief=idea.strip()), b.get('files') or [])
        ident = uuid.uuid4().hex[:12]
        p = Project.create(os.path.join(home(), 'projects', 'learning-' + ident), recipe='learning-commentary',
                           name=idea.strip().splitlines()[0][:70], inputs=ins)
        p.data['prompt'] = idea.strip(); p.save()
        from vstudio.intake.sources import urls_in
        links = [u for u in urls_in(idea) if urlsplit(u).scheme == 'https']
        doc = dict(id=ident, title=p.data['name'], links=links, notes=[], blocks=[], credits={}, created=time.time())
        if thoughts.strip():
            doc['notes'].append(dict(id=uuid.uuid4().hex[:10], text=thoughts.strip(), source=None, at=None, kind='thought'))
        self._save(p, doc)
        return self.get(ident)

    def get(self, ident):
        from vstudio import learning
        p = self._project(ident)
        doc = read_json(os.path.join(p.dir, 'learning.json'), {})
        sources = learning.catalog(p.data.get('inputs') or {})
        self.inbox.history.allow_media([s['path'] for s in sources.values()] + [v['audio'] for v in doc.get('voice_notes',[])])
        return dict(doc, sources=sources, readings=self._readings(p.data.get('inputs') or {}), script='\n\n'.join(n['text'] for n in doc['notes'] if n.get('kind') == 'thought'))

    def update(self, ident, b):
        from vstudio import learning, media
        with _LOCK:
            p = self._project(ident)
            need(not (pilot.running(p.dir) or pilot.queued(p.dir)), 'wait for this workspace render to finish')
            doc = read_json(os.path.join(p.dir, 'learning.json'), {})
            sources = learning.catalog(p.data.get('inputs') or {})
            action = b.get('action')
            if action in ('files', 'take'):
                ins = dict(p.data.get('inputs') or {})
                self._files(ins, b.get('files') or [], 'takes' if action == 'take' else None)
                if action == 'take':
                    for path in b.get('files') or []:
                        info = media.probe(path)
                        need(info['has_video'] and info['has_audio'], 'your camera take needs both video and voice')
                        refs = ins.get('references') or []
                        ins['references'] = [x for x in (refs if isinstance(refs,list) else [refs]) if os.path.realpath(x) != os.path.realpath(path)]
                p.data['inputs'] = ins; p.save(); p.plan()
            elif action == 'note':
                text, source, at = b.get('text'), b.get('source'), b.get('at')
                need(isinstance(text, str) and 0 < len(text.strip()) <= 20000, 'say or write your thought')
                readings = self._readings(p.data.get('inputs') or {})
                need(source is None or source in sources or source in readings or source in doc['links'], 'choose an attached source')
                need(source not in readings or at is None, 'text notes do not have a playback time')
                need(at is None or (isinstance(at, (int,float)) and not isinstance(at,bool) and math.isfinite(at) and at >= 0), 'choose a valid source time')
                if source in sources and at is not None:
                    duration = sources[source].get('duration')
                    need(duration is not None and at <= duration, 'note time is outside the source')
                kind = b.get('kind', 'thought')
                need(kind in ('thought','quote'), 'note kind: thought or quote')
                note=dict(id=uuid.uuid4().hex[:10], text=text.strip(), source=source, at=at, kind=kind)
                voice=b.get('voice_audio')
                if voice is not None:
                    need(any(v.get('audio')==voice for v in doc.get('voice_notes',[])),'choose a voice input from this workspace')
                    note['voice_audio']=voice
                doc['notes'].append(note)
            elif action == 'revise-note':
                note=next((n for n in doc['notes'] if n['id']==b.get('note')),None)
                text=b.get('text')
                need(note is not None and isinstance(text,str) and 0<len(text.strip())<=20000,'select and edit your note')
                note.setdefault('revisions',[]).append(dict(text=note['text'],at=time.time()))
                note['text']=text.strip()
            elif action == 'credit':
                source = b.get('source'); credit = b.get('credit')
                need(source in sources, 'choose a source')
                need(isinstance(credit, dict) and all(isinstance(credit.get(k),str) and len(credit[k]) <= 2000 for k in ('title','creator','locator')), 'add source title, author and link or page')
                doc['credits'][source] = {k:credit[k].strip() for k in ('title','creator','locator')}
            elif action == 'block':
                block = b.get('block')
                need(isinstance(block,dict) and block.get('source') in sources, 'choose attached material')
                a, z = block.get('start'), block.get('end')
                need(all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in (a,z)) and 0 <= a < z, 'mark the start and end of this passage')
                src = sources[block['source']]
                need(src['image'] or z <= src['duration']+.04, 'the selected range exceeds the source')
                point = block.get('point') or doc['title']
                need(isinstance(point,str) and len(point)<=2000, 'name this part')
                clean = dict(id=uuid.uuid4().hex[:10],source=block['source'],start=a,end=z,point=point)
                for key in ('voice','voice_start'):
                    if key in block: clean[key] = block[key]
                doc['blocks'].append(clean)
            elif action in ('remove','move'):
                idx = next((i for i,x in enumerate(doc['blocks']) if x['id']==b.get('block')), None)
                need(idx is not None, 'select a draft part')
                if action=='remove': doc['blocks'].pop(idx)
                else:
                    delta=b.get('delta'); need(type(delta) is int and delta in (-1,1), 'move up or down')
                    target=max(0,min(len(doc['blocks'])-1,idx+delta))
                    doc['blocks'].insert(target,doc['blocks'].pop(idx))
            elif action == 'tool':
                job=b.get('job'); need(isinstance(job,str) and re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',job),'select a tool request')
                doc.setdefault('tool_jobs',[]).append(dict(id=job,kind='explainer-demo'))
            elif action == 'post':
                text=b.get('text'); need(isinstance(text,str) and len(text)<=100000,'post: up to 100000 characters')
                doc['post']=text
            elif action == 'link':
                url=b.get('url'); need(isinstance(url,str) and len(url)<=2000 and urlsplit(url).scheme=='https' and urlsplit(url).hostname, 'add an HTTPS website or video link')
                if url not in doc['links']: doc['links'].append(url)
            else:
                need(False, 'choose a workspace action')
            self._save(p,doc)
            return self.get(ident)

    def edit(self, ident):
        """The user's ordered blocks become the real edit list; no AI decides what they meant."""
        from vstudio import learning
        with _LOCK:
            p=self._project(ident); doc=self.get(ident)
            need(self.inbox.runner is not None, 'the local engine is required')
            need(not (pilot.running(p.dir) or pilot.queued(p.dir)), 'this workspace is already rendering')
            sources=doc['sources']; segments=[]
            for row in doc['blocks']:
                s={k:v for k,v in row.items() if k!='id'}
                if sources[s['source']]['role'] in ('reference','page'):
                    s['citation']=doc['credits'].get(s['source'])
                segments.append(s)
            montage=dict(title=doc['title'],segments=segments,purpose='creator-workspace')
            learning.validate(montage,sources)
            item=os.path.join(p.dir,'items','main')
            os.makedirs(os.path.join(item,'work'),exist_ok=True)
            with open(os.path.join(item,'SCRIPT.md'),'w',encoding='utf-8') as f:
                f.write('# '+doc['title']+'\n\n## RECORD\n'+doc['script'])
            write_json(os.path.join(item,'work','sources.json'),sources)
            write_json(os.path.join(item,'work','montage.json'),montage)
            p.plan()
            r=self.inbox.runner
            pilot.spawn(r.python,r.env,p.dir,bus=self.inbox.bus,args=[r.python,'-m','vstudio.project','run','--dir',p.dir,
                        '--auto','outline,montage','--json-events'])
            self.inbox._forget_engine()
            from .common import batch_id
            return dict(ok=True,dir=p.dir,id=batch_id(os.path.join(p.dir,'state')))

    def dictate(self, ident, session_dir):
        """Local ASR only, on the mic session the user explicitly recorded; no rewrite of their words."""
        self._project(ident)
        from vstudio import asr
        from vstudio.create import record, store
        need(isinstance(session_dir,str) and os.path.isabs(session_dir),'select a saved recording')
        d=record.need_session(session_dir)
        need(os.path.dirname(os.path.realpath(d))==os.path.realpath(store.recordings_root()), 'select this app\'s saved voice note')
        path=os.path.join(d,'mic.webm')
        need(os.path.isfile(path) and not os.path.exists(os.path.join(d,'recording.lock')), 'finish the voice note first')
        ready={r['provider'] for r in asr.providers() if r['kind']=='local' and r['ready']}
        backend=next((k for k in ('mlx','faster') if k in ready),None)
        self.inbox.history.allow_media([path])
        with _LOCK:
            p=self._project(ident)
            doc=read_json(os.path.join(p.dir,'learning.json'),{})
            doc.setdefault('voice_notes',[]).append(dict(audio=path,status='recorded'))
            self._save(p,doc)
        need(backend,'install a local speech model in Settings to dictate here')
        got=asr.transcribe(path,language='auto',backend=backend,cache=False)
        with _LOCK:
            doc=read_json(os.path.join(p.dir,'learning.json'),{})
            for v in doc.get('voice_notes',[]):
                if v.get('audio')==path: v.update(text=got.get('text') or '',status='transcribed')
            self._save(p,doc)
        self.inbox.history.allow_media([path])
        return dict(text=got.get('text') or '',audio=path)
