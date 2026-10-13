# Third-party notices (Reelfold engine)

Code in this repository adapted from other open-source projects. Each keeps its own licence; the notice is
reproduced below as the licence asks. (Software bundled with the desktop app: apps/desk/THIRD_PARTY_LICENSES.md.)

## OpenFilm

https://github.com/openfilm/openfilm (MIT). Ported / adapted in:

- `lib/vstudio/project/nle.py`: the editing-program export (FCP7 XML for Premiere Pro / DaVinci Resolve after
  `packages/openfilm/studio/server/nle.mjs`; the 剪映 / CapCut draft after `packages/openfilm/studio/server/jianying.mjs`).
- `lib/vstudio/look.py`: the look check of HTML-rendered scenes (the idea of `packages/openfilm/src/look.mjs`: frames
  drawn twice in two shuffled orders and compared, failed fonts, text cut, missing sounds, a contact sheet).
- `lib/vstudio/project/outputs.py` (overrides): edits the person made that an agent keeps, after OpenFilm's
  `overrides` attribute (idea only, no code).

```
MIT License

Copyright (c) 2026 OpenFilm contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
