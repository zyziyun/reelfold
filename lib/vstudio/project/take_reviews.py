"""Refresh existing AIGC review evidence without running generation or the project graph."""
import os

from vstudio.batch.recipes import Ctx
from vstudio.batch.run import BatchBusy
from vstudio.batch.util import write_json
from vstudio.oscompat import try_lock, unlock

from . import build as B
from .adapters import aivideo


def refresh(project, item):
    """Recheck a waiting take-selection gate. Never approve, resume, or generate a take.

    Uses the runner's cross-process lock and the normal judge/card history logic. A
    current partial or rejected review is retained, rather than resampled for approval.
    """
    if project.manifest['id'] != 'ai-video':
        raise ValueError('take reviews are only available for AI video projects')
    cp = project.checkpoint('takes')
    if cp.get('kind') != 'take-selection' or cp.get('after') != 'judge':
        raise ValueError('unsupported take review checkpoint')
    # Validate membership before composing any filesystem paths from the item id.
    rows = {r['id']: r for r in project.jobs_rows()}
    if item not in rows:
        raise ValueError('unknown take review item')
    with open(os.path.join(project.state_dir, 'run.lock'), 'a') as lock:
        if not try_lock(lock):
            raise BatchBusy('wait for this project to stop before reviewing its takes')
        try:
            if not project.pending(cid='takes', item=item):
                raise ValueError('this item is not waiting for take review')
            params = dict(project.params(), **rows[item])
            params.update(_project_dir=project.dir, _item_dir=os.path.join(project.dir, 'items', item))
            directory = os.path.join(params['_item_dir'], 'work', 'ai', 'judge')
            os.makedirs(directory, exist_ok=True)
            entry = next(s for s in project.manifest['stages'] if s['id'] == 'judge')
            ctx = Ctx(dict(id=item, params=params), project.data.get('spec') or {}, directory, {}, project.state_dir)
            env = B.Env(ctx, project.manifest, entry)
            # Direct invocation is deliberate: Project.run(only=...) selects jobs, not
            # stages, and could run a paid generator when upstream inputs changed.
            output = aivideo.judge(env)
            env.inputs = {'judge': output}
            payload = B.finalize_payload(env, cp, aivideo.takes_payload(env, cp))
            write_json(os.path.join(B.checkpoint_dir(project.state_dir, item), 'takes.json'), payload)
            return dict(ok=True, digest=payload['digest'])
        finally:
            unlock(lock)


def current_payload(project, item, payload):
    """Read current bindings for a saved gate without writes or model calls."""
    from types import SimpleNamespace
    cp = project.checkpoint('takes')
    item_dir = os.path.join(project.dir, 'items', item)
    env = SimpleNamespace(inputs={'judge': {'takes': os.path.join(item_dir, 'work', 'ai', 'judge', 'takes.json')}},
                          job=item, m=project.manifest, project_dir=project.dir)
    current = B.finalize_payload(env, cp, aivideo.takes_payload(env, cp))
    return dict(payload, **current)
