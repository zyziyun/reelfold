"""Dictionary word boundaries from the ICU libraries already in our native stack."""
from functools import lru_cache
from pathlib import Path
import ctypes.util
import os
import re
import sys


@lru_cache(maxsize=1)
def _english_parser():
    # This model already ships with the speech runtime. Never download a model
    # while laying out captions; source-only installations may omit speech extras.
    try:
        import spacy
        return spacy.load('en_core_web_sm', exclude=['ner', 'lemmatizer'])
    except (ImportError, OSError):
        return None


@lru_cache(maxsize=512)
def phrase_spans(text, language=None):
    """Protected noun-phrase character spans for explicitly English captions.

    Unknown/other languages retain their existing Unicode/dictionary layout.
    Offsets refer to plain text, not highlight markup. No text is rewritten.
    """
    if str(language or '').lower().replace('_', '-').split('-')[0] != 'en':
        return ()
    parser = _english_parser()
    if parser is None:
        return ()
    return tuple((s.start_char, s.end_char) for s in parser(text).noun_chunks)


def dictionary_script(char):
    value = ord(char)
    return (0x0E00 <= value <= 0x0EFF or 0x1000 <= value <= 0x109F or
            0x1780 <= value <= 0x17FF or 0xA9E0 <= value <= 0xA9FF or 0xAA60 <= value <= 0xAA7F)


@lru_cache(maxsize=1)
def _icu():
    from .textlayout import _libraries, _library_directory
    ffi, *_ = _libraries()  # also retains the bundled Windows DLL directory
    root = _library_directory()
    if root is not None:
        pattern = 'icuuc*.dll' if sys.platform == 'win32' else 'libicuuc.*.dylib' if sys.platform == 'darwin' else 'libicuuc.so.*'
        files = sorted(root.glob(pattern))
        file = str(files[0]) if files else None
    else:
        file = ctypes.util.find_library('icuuc')
    bundled = Path(sys.prefix).resolve().parent / 'ffmpeg'
    if not file and sys.platform == 'darwin' and not bundled.is_dir() and not os.environ.get('VSTUDIO_TEXT_LAYOUT_DIR'):
        # Homebrew keeps this keg-only library outside its normal lib folder.
        file = next((str(p) for base in ('/opt/homebrew/opt/icu4c/lib', '/usr/local/opt/icu4c/lib')
                     for p in Path(base).glob('libicuuc.*.dylib')), None)
    if not file:
        raise RuntimeError('Dictionary text wrapping requires ICU; repair the engine runtime or install ICU')
    lib = ffi.dlopen(file)
    match = re.search(r'(?:icuuc\.|icuuc|\.so\.)(\d+)', file)
    suffix = '_' + match[1] if match else ''
    ffi.cdef(f'''
        void *ubrk_open{suffix}(int type, const char *locale, const unsigned short *text, int length, int *status);
        int ubrk_first{suffix}(void *iterator);
        int ubrk_next{suffix}(void *iterator);
        void ubrk_close{suffix}(void *iterator);
    ''')
    return ffi, lib, tuple(getattr(lib, name + suffix) for name in ('ubrk_open', 'ubrk_first', 'ubrk_next', 'ubrk_close'))


def dictionary_words(text):
    """Return start -> end Python indexes only for dictionary-script runs.

    ICU's indexes count UTF-16 units. Translate them back without splitting
    surrogate pairs or changing the original string, markup, or punctuation.
    """
    if not any(dictionary_script(c) for c in text):
        return {}
    ffi, _, (open_, first, next_, close) = _icu()
    data = text.encode('utf-16-le')
    units = [int.from_bytes(data[i:i+2], 'little') for i in range(0, len(data), 2)]
    source = ffi.new('unsigned short[]', units)
    status = ffi.new('int *', 0)
    iterator = open_(1, b'', source, len(units), status)  # UBRK_WORD, automatic script dictionaries
    if status[0] > 0 or iterator == ffi.NULL:
        if iterator != ffi.NULL:
            close(iterator)
        raise RuntimeError(f'Dictionary text wrapping could not load ICU data (error {status[0]})')
    positions, offset = {0: 0}, 0
    for i, char in enumerate(text):
        offset += 2 if ord(char) > 0xFFFF else 1
        positions[offset] = i + 1
    result = {}
    try:
        start = first(iterator)
        while (end := next_(iterator)) != -1:
            a, b = positions[start], positions[end]
            if a < b and dictionary_script(text[a]):
                result[a] = b
            start = end
    finally:
        close(iterator)
    return result
