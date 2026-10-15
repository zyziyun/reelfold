"""Installed macOS speech voices, exported locally through the system's say tool."""
import os
import platform
import re
import subprocess

SAY = '/usr/bin/say'


def voices():
    """Only voices exposed by this Mac; never download or change system speech settings."""
    if platform.system() != 'Darwin' or not os.path.isfile(SAY):
        return []
    r = subprocess.run([SAY, '-v', '?'], capture_output=True, text=True, timeout=15, check=True)
    out = []
    for line in r.stdout.splitlines():
        m = re.match(r'^(.+?)\s+([a-z]{2,3}[_-][A-Za-z0-9_-]+)\s+#', line)
        if m:
            name, lang = m.groups()
            out.append(dict(id=name.strip(), name=name.strip(), lang=lang.replace('_', '-')))
    return out


def chinese_voices():
    return sorted([v for v in voices() if v['lang'].startswith(('zh-', 'yue-'))],
                  key=lambda v: ('Premium' not in v['name'], v['lang'] != 'zh-CN', v['name']))


def synth(text, voice, dst, tmp):
    if voice not in {v['id'] for v in voices()}:
        raise RuntimeError('The selected macOS voice is not installed. Choose an installed voice in Settings > Voice.')
    source = os.path.join(tmp, 'speech.txt')
    with open(source, 'w', encoding='utf-8') as f:
        f.write(text)
    # File input keeps punctuation, leading dashes and multiline user text out of command options.
    r = subprocess.run([SAY, '-v', voice, '-f', source, '-o', dst, '--file-format=AIFF'],
                       capture_output=True, text=True, timeout=max(60, min(900, len(text) * 0.5)))
    if r.returncode or not os.path.isfile(dst) or os.path.getsize(dst) < 128:
        raise RuntimeError('macOS could not export this voice. Choose another installed voice in Settings > Voice.')
