"""Isolated failed photo-story with real encoded flash and real QC evidence."""
import json
import os
import subprocess
import sys
import time
from vstudio import flicker
from vstudio.batch.store import Store
from vstudio.project.core import Project

p = Project.create(os.path.join(sys.argv[1], 'project'), recipe='photo-story',
                   name='Flicker review fixture', inputs={}, params={})
p.plan()
started = time.time()
folder = os.path.join(p.dir, 'items', 'main', 'out')
os.makedirs(folder, exist_ok=True)
video = os.path.join(folder, 'story.mp4')
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                "color=c=0x404040:s=320x180:r=30:d=4,geq=lum='if(between(T,2,2.2),235,64)':cb=128:cr=128",
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', video], check=True)
try:
    flicker.check(video, mode='fail', log=None)
except flicker.FlickerError as exc:
    error = str(exc)
else:
    raise AssertionError('fixture must fail flicker QC')
store = Store(p.state_dir)
try:
    store.set_stage('main', 'render', state='failed', started=started, error=error)
    store.set_job('main', state='failed')
finally:
    store.close()
print(json.dumps(dict(dir=p.dir)))
