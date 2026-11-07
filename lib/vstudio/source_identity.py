"""Stable source names shared by staging, visual evidence and rendering."""
import hashlib
import os
from collections import Counter


def names(paths):
    """Keep unique basenames; disambiguate colliding stems (including case) by path.

    Stem uniqueness matters because video references commonly omit extensions.
    Reserving all original stems prevents generated names stealing another input's ID.
    """
    paths = list(dict.fromkeys(os.path.abspath(p) for p in paths))
    stems = [os.path.splitext(os.path.basename(p))[0] for p in paths]
    counts = Counter(s.casefold() for s in stems)
    used = set(counts)
    result = {}
    for path, stem in zip(paths, stems):
        ext = os.path.splitext(path)[1]
        if counts[stem.casefold()] > 1:
            digest = hashlib.sha256(path.encode()).hexdigest()
            candidate = stem + '-' + digest[:16]
            while candidate.casefold() in used:
                candidate += '-src'
            stem = candidate
            used.add(stem.casefold())
        result[path] = stem + ext
    return result


def stage(paths, folder):
    """Link exact sources under unambiguous names without replacing existing files."""
    import filecmp
    import shutil
    os.makedirs(folder, exist_ok=True)
    result = {}
    for source, name in names(paths).items():
        dest = os.path.join(folder, name)
        if os.path.lexists(dest):
            if not os.path.isfile(dest) or not (os.path.samefile(source, dest) or filecmp.cmp(source, dest, shallow=False)):
                raise ValueError(f'Source name already belongs to another file: {dest}')
        else:
            try:
                os.symlink(source, dest)
            except OSError:
                shutil.copy2(source, dest)
        result[source] = dest
    return result
