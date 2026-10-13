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

## Music library (first-run download, `music-library`)

The music every video is given is picked from ~50 real tracks that Reelfold downloads on first run
(`lib/vstudio/music_library.json`: each file pinned by sha256 to its original URL, archived by the Internet Archive).
Every track is **CC0 1.0 / public domain**: it may be redistributed by this MIT app and used in published, monetised
videos with no fee and no credit. Licence evidence per track: the archived FreePD.com category page ("100% Free Music -
Creative Commons 0", each track "available for commercial and non-commercial purposes") or the Musopen collection's
licence (`archive.org/details/musopen-chopin`, CC0). Not taken, on purpose: Rafael Krux's FreePD tracks (also sold on
Envato as Orchestralis and registered with YouTube Content ID), tracks whose files say they came from a CC BY / unknown
source (Jason Shaw, Phase Shift, statusq, dogsounds), YouTube Audio Library, Pixabay / Mixkit / Uppbeat (no
redistribution in another product), NC / ND licences (`vstudio.music.validate_library` refuses them). No credit is
needed; a courtesy credit is welcome: `Music: "<title>" by <artist> (FreePD.com, CC0)`. Public domain music can still
be wrongly claimed by a third party on YouTube: dispute it with the track's licence page above.

| Title | Artist | Style / mood | BPM | Licence | Source |
|---|---|---|---|---|---|
| Piano Magic Motive | Kevin MacLeod | piano / story | free | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/romantic.php) |
| Infinite Wonder | Kevin MacLeod | ambient / calm | free | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/misc.php) |
| Mana Two - Part 1 | Kevin MacLeod | ambient / calm | free | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/misc.php) |
| Painting Room | Kevin MacLeod | ambient / calm | 63 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/misc.php) |
| Connecting Rainbows | Kevin MacLeod | ambient / calm | free | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/world.php) |
| Champ de tournesol | Komiku | acoustic / warm | 80 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/romantic.php) |
| La Citadelle | Komiku | acoustic / warm | 130 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/romantic.php) |
| Patience Party | Kevin MacLeod | acoustic / warm | 70 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/romantic.php) |
| Wisdom in the Sun | Kevin MacLeod | acoustic / warm | free | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/misc.php) |
| Trip Up North | Bryan Teoh | acoustic / warm | 95 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/misc.php) |
| Pickled Pink | Kevin MacLeod | acoustic / warm | 103 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/upbeat.php) |
| Go On Without Me | Bryan Teoh | cinematic / story | 89 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/epic.php) |
| Fresh Focus | Kevin MacLeod | pop / bright | 104 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/upbeat.php) |
| Natural Vibes | Kevin MacLeod | pop / bright | 101 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/upbeat.php) |
| City Sunshine | Kevin MacLeod | pop / bright | 85 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/upbeat.php) |
| From Page to Practice | Bryan Teoh | pop / bright | 160 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/upbeat.php) |
| Inventing Flight | Bryan Teoh | pop / bright | free | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/upbeat.php) |
| Adding the Sun | Kevin MacLeod | pop / bright | 90 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/misc.php) |
| Backbeat | Kevin MacLeod | electronic / tech | 130 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/electronic.php) |
| Arpent | Kevin MacLeod | electronic / tech | 121 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/electronic.php) |
| Beat One | Kevin MacLeod | electronic / tech | 120 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/electronic.php) |
| Goodnightmare | Kevin MacLeod | electronic / tech | 130 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/electronic.php) |
| Meditating Beat | Kevin MacLeod | electronic / tech | 95 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/electronic.php) |
| Funky Energy Loop | Kevin MacLeod | pop / bright | 115 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/scoring.php) |
| Fake It Til You Fake It | Kevin MacLeod | lofi / warm | 140 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/misc.php) |
| Study and Relax | Kevin MacLeod | lofi / warm | 72 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/featured.php) |
| Bass Meant Jazz | Kevin MacLeod | lofi / warm | 96 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/misc.php) |
| Driving Concern | Kevin MacLeod | documentary / story | 112 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/scoring.php) |
| Ancient Rite | Kevin MacLeod | documentary / story | 70 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/epic.php) |
| Think About It | Bryan Teoh | documentary / story | 100 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/epic.php) |
| The Britons | Kevin MacLeod | documentary / story | 90 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/misc.php) |
| Shenzhen Nightlife | Kevin MacLeod | chinese / tech | 128 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/world.php) |
| Coy Koi | Anonymous | chinese / calm | 80 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/world.php) |
| Midnight in the Green House | Kevin MacLeod | world / calm | free | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/world.php) |
| Infinite Peace | Kevin MacLeod | world / calm | free | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/misc.php) |
| New Hero in Town | Kevin MacLeod | cinematic / story | free | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/epic.php) |
| Night Vigil | Kevin MacLeod | cinematic / story | free | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/epic.php) |
| Honor Bound | Bryan Teoh | cinematic / story | 125 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/epic.php) |
| Royal Coupling | Kevin MacLeod | cinematic / story | 120 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/misc.php) |
| Joey's Song | Kevin MacLeod | acoustic / warm | 122 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/comedy.php) |
| Icicles Melting | Kevin MacLeod | pop / bright | free | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/misc.php) |
| Painful Disorientation | Kevin MacLeod | piano / story | free | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/misc.php) |
| Energizing | Kevin MacLeod | pop / bright | 91 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/misc.php) |
| Screen Saver | Kevin MacLeod | electronic / tech | free | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/upbeat.php) |
| Gothamlicious | Kevin MacLeod | cinematic / story | free | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/epic.php) |
| Funshine | Kevin MacLeod | acoustic / bright | 96 | CC0 1.0 | [FreePD](https://web.archive.org/web/2024/https://freepd.com/upbeat.php) |
| Chopin: Nocturne Op. 9 No. 2 | Frédéric Chopin (perf. Musopen) | piano / calm | free | CC0 1.0 | [Musopen / Internet Archive](https://archive.org/details/musopen-chopin) |
| Chopin: Prelude Op. 28 No. 15 "Raindrop" | Frédéric Chopin (perf. Musopen) | piano / calm | free | CC0 1.0 | [Musopen / Internet Archive](https://archive.org/details/musopen-chopin) |
| Chopin: Prelude Op. 28 No. 13 | Frédéric Chopin (perf. Musopen) | piano / calm | free | CC0 1.0 | [Musopen / Internet Archive](https://archive.org/details/musopen-chopin) |
| Chopin: Nocturne Op. 72 No. 1 in E minor | Frédéric Chopin (perf. Musopen) | piano / story | free | CC0 1.0 | [Musopen / Internet Archive](https://archive.org/details/musopen-chopin) |
| Chopin: Waltz Op. 64 No. 2 | Frédéric Chopin (perf. Musopen) | piano / calm | free | CC0 1.0 | [Musopen / Internet Archive](https://archive.org/details/musopen-chopin) |
| Chopin: Waltz in A minor (op. posth.) | Frédéric Chopin (perf. Musopen) | piano / story | free | CC0 1.0 | [Musopen / Internet Archive](https://archive.org/details/musopen-chopin) |
