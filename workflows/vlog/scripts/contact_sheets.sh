#!/usr/bin/env bash
# Contact sheets per clip - see contact_sheets.py (the recipe runs that one; this keeps the old CLI).
#   contact_sheets.sh OUT_DIR EVERY_SEC CLIP1 [CLIP2 ...]
exec "${VSTUDIO_PYTHON:-python3}" "$(dirname "$0")/contact_sheets.py" "$@"
