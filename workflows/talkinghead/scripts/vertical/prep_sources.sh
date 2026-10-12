#!/usr/bin/env bash
# HDR -> SDR, audio, word-level whisper per clip - see prep_sources.py (the batch runs that one; this keeps the old
# CLI).   usage: bash prep_sources.sh WORK_DIR clip1.MOV clip2.MOV ...   (env PROMPT, TONEMAP, ORIENT, PLATFORM, ...)
exec "${VSTUDIO_PYTHON:-python3}" "$(dirname "$0")/prep_sources.py" "$@"
