---
title: Contributing
description: Build Reelfold from source, run a packaged build locally, find your way around the repo, run the tests, add an effect or a platform, translate, edit these docs and open a pull request.
---

Reelfold is MIT-licensed and lives in one repository: the engine and Claude Code skill at the root, the Mac app, the website and these docs under `apps/`. Fixes, effects, platform profiles and translations are all welcome.

## Build from source

You need macOS on Apple Silicon for the app, Node 22+, Python 3.10+ and `ffmpeg`.

```bash
git clone https://github.com/zyziyun/reelfold && cd reelfold
./install.sh && npm install
npm run desk
```

`./install.sh` installs the Python dependencies and downloads the open-licensed fonts and MediaPipe models into `~/.cache/video-studio`. `npm install` is one workspace install for everything in `apps/`. `npm run desk` starts the app with its engine running from this checkout's `lib/`.

### Useful scripts

From the repo root:

| Command | What it does |
|---|---|
| `npm run desk` (or `npm run dev`) | The Mac app in development, engine from this checkout |
| `npm run site` / `npm run docs` | reelfold.com / these docs, with live reload |
| `npm run build:web` | Builds the site and the docs into one folder (`apps/site/dist`, docs under `/docs`) |
| `npm run build:docs` | The docs only |
| `npm run test` / `npm run lint` | The app's tests / eslint + tsc |
| `npm run check` | `scripts/check_skill.py`, the repo checks |

In `apps/desk` (`npm run <script> -w apps/desk` from the root):

| Command | What it does |
|---|---|
| `runtime` | Bundles Python, ffmpeg and the engine for this machine into `build/runtime/` (about 1 GB; downloads cached) |
| `build:mac` | A packaged `Reelfold.app` in `dist/mac-arm64/`, unsigned, using the bundled runtime if present |
| `dist:mac:unsigned` | A DMG and zip, unsigned |
| `test:packaged` | Checks the packaged app: the bundled engine starts and answers |
| `mas:local` | The Mac App Store build, signed ad hoc with the sandbox entitlements, then tested |
| `test:e2e` | Builds, then the Playwright smoke tests |

### Run a packaged build locally

There is no one-step install script. To try a packaged build of your checkout:

```bash
npm ci                                  # once, at the repo root
npm run runtime -w apps/desk            # bundled Python + ffmpeg + engine (first time, or after engine changes)
npm run build:mac -w apps/desk          # -> apps/desk/dist/mac-arm64/Reelfold.app
npm run test:packaged -w apps/desk      # optional: check the packaged app
open apps/desk/dist/mac-arm64/Reelfold.app
```

The build is unsigned, so the first time macOS may ask you to confirm (right-click › Open). It shares settings and projects with an installed Reelfold, so quit the installed app before you open the local build, and don't replace `/Applications/Reelfold.app` while it is running. Signed, notarized and App Store builds are covered in `apps/desk/docs/RELEASING.md` and `apps/desk/docs/MAS.md`.

## Repo layout

```
SKILL.md                  router: which workflow for which request
workflows/<name>/         WORKFLOW.md playbook, scripts/, references/, examples/
lib/vstudio/              shared engine library (media, audio, asr, cut, subs, platform, export, publish …)
references/               long-form engine notes (PLATFORMS, BATCH, EFFECTS, RETOUCH …)
tests/                    pytest on synthetic media
apps/desk/                the Mac app (Electron)
apps/site/                reelfold.com (Astro)
apps/docs/                these docs (Astro Starlight)
```

## Run the tests

```bash
python3 -m pytest tests -q          # engine tests, synthetic media only
npm run test                        # Mac app: vitest + the engine bridge tests
npm run lint                        # Mac app: eslint + tsc
python3 scripts/check_skill.py      # repo checks before a commit
```

`check_skill.py` checks the skill's frontmatter and every `WORKFLOW.md`, and fails on decorative emoji in the playbooks, absolute personal paths (`/Users/<name>/`) and anything shaped like a committed secret. Your `persona.local.yaml` is git-ignored, so your own settings never reach the repo.

## Add an effect

Effects live in one declarative registry, `lib/vstudio/effects.py`, and the catalogue in `references/EFFECTS.md` is generated from it. The steps, from the function to the registry entry and the checks, are in [Adding effects](/docs/reference/engine/adding-effects/).

## Add or fix a platform profile

1. Edit the profile in `lib/vstudio/platform.py`: canvas per orientation, safe zones, caption box, length, loudness, encode caps, cover size and crops, title, text and tag limits.
2. Record where each value comes from in `references/PLATFORMS.md`, tagged **[S]** sourced, **[3P]** third-party or **[C]** convention. Platforms change their UI often; say what you checked and when.
3. If the platform has an upload page, add its row to `references/PUBLISHING.md`.
4. Run the platform tests (`tests/test_platform*.py`) and print the result with `python -m vstudio.platform`.

## Translate

| What | Where |
|---|---|
| These docs | `apps/docs/src/content/docs/<locale>/` (`zh`, `fr`, `es`). English is the root. Use the same slug as the English page. |
| The website | `apps/site/src/i18n/` (`en.ts`, `zh.ts`, `fr.ts`) |
| The Mac app | `apps/desk/src/renderer/src/i18n/locales/` (English is the source and the fallback) |
| Engine messages | `lib/vstudio/messages.py`, then `python3 scripts/gen_messages_md.py` (a test fails if `references/MESSAGES.md` is out of date) |

A page that isn't translated yet falls back to English with a notice, so partial translations are fine.

## Edit these docs

The docs are an Astro Starlight site in `apps/docs`. Guides, concepts and help pages are plain Markdown in `apps/docs/src/content/docs/`.

The **reference** pages are generated from the repo's own sources, so they never drift from the engine: workflow pages from `workflows/<name>/WORKFLOW.md`, engine pages from `references/*.md`, platforms from `lib/vstudio/platform.py`, the CLI page from each module's `--help`. Edit the source, not the generated page, then regenerate:

```bash
npm run gen -w apps/docs
```

## Pull requests

- Keep a PR to one change, and say what you tested and on what footage (synthetic media in `tests/` for anything the engine does).
- Run the tests and `check_skill.py` before you push.
- For a platform value, link the source. For a visual change, attach a still or a contact sheet.
- Never commit API keys, personal paths or footage you don't have the rights to.

By contributing, you agree that your contribution is licensed under the MIT licence of the project.

## Related

- [Adding effects](/docs/reference/engine/adding-effects/)
- [Platforms reference](/docs/reference/platforms/)
- [CLI reference](/docs/reference/cli/)
- [Install the skill](/docs/start/install-skill/)
