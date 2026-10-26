"""Compatibility imports for existing talking-head configurations.

The implementation lives in vstudio.broll so native export and workflow
compositors share decoding, screenshot scrolling and card drawing.
"""
from vstudio.broll import (  # noqa: F401 - legacy config imports
    IMG_EXT, Item, Source, active, badge_layer, blur_fill, cover_fit,
    ease, exists, load, paste_card, round_mask,
)
