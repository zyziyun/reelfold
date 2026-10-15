# Mac App Store ("Lite") build

Reelfold ships twice on macOS: the full app (Developer ID, notarized DMG, GitHub Releases, electron-updater) and a
sandboxed **Reelfold Lite** on the Mac App Store. Same code; the edition is chosen at build time:

```bash
BUILD_EDITION=mas npm run build          # the app itself (src/shared/edition.ts: __REELFOLD_EDITION__)
npm run mas:local                        # local check: build, package, ad-hoc sign with the MAS entitlements, test
npm run release:mas                      # store build: sign, .pkg, verify, App Store lint, validate (UPLOAD=1 to upload)
MAS_VERSION=0.2.1 npm run release:mas    # a new build for an App Store version that is still open (after a rejection)
npm run appstore:lint -- <Reelfold.app>  # the App Store lint alone (below)
```

App Store Connect: app "Reelfold", bundle id `app.reelfold.desk`, SKU `reelfold-mac`, Apple ID 6820016757, team
ZH47R7RVKB. Store texts, review notes and screenshots for the listing are kept outside the repository.

## What Lite leaves out (and why)

| | Full | Lite | Why |
|---|---|---|---|
| AI | Claude Code / Codex subscription (CLI sign-in in an in-app terminal), API keys, local models | API keys, local models (Ollama, LM Studio, vLLM) | A sandboxed app cannot run CLIs the user installed; no terminal (node-pty is not packaged) |
| Folders | any path; watched folders by path | only folders / files she picked; kept with security-scoped bookmarks | App Sandbox |
| Updates | electron-updater (GitHub Releases) | the Mac App Store | Guideline 2.4.5(vii) |
| First-run downloads | speech models, fonts, face models, optional Chromium | the same minus Chromium (data only) | Guideline 2.4.5(iv) / 2.5.2: no downloaded executables |
| HTML covers / slides | headless Chrome (installed or downloaded) | rendered by the app's own Chromium (offscreen window) | no second browser binary in the sandbox |
| Usage counts (opt-in) | yes | none | optional cloud AI content is disclosed separately |
| Publishing | built-in browser (assisted fill, she presses Publish), YouTube API | built-in browser for every platform, YouTube included | Google's desktop OAuth redirects to a loopback port: a listening socket, which Lite does not have (no `network.server`) |
| Local services | engine sidecar + (Lite) HTML renderer on Unix domain sockets | same | nothing listens on a network port in either edition (Windows: 127.0.0.1, CPython has no AF_UNIX there) |

Everything else (projects, ASR, cleanup, captions, renders, review, calendar, Create recorder) is the same code. The
Lite build says what it does once, neutrally (Settings › General, first run, Settings › AI: "This edition uses API keys
or local models"). It names no other download and links nowhere - no "get the full version", no reelfold.com
(Guidelines 3.1.1 / 2.3); `tests/unit/editionLite.test.ts` checks that in every language. The full build is unchanged.

## How it works

- `src/shared/edition.ts` - `EDITION`, `CAPS` (what the edition can do). Everything gates on
  `CAPS`, never on scattered checks.
- `src/main/access.ts` - every open panel (`pick()` in `main/index.ts`) asks for a security-scoped bookmark in the
  MAS build; bookmarks are kept in `<userData>/access.json` and started at launch, before the engine. Files dropped on
  the window are readable for this launch; the app asks once ("Allow") for their folder so they stay readable.
  Watched folders are limited to granted folders.
- Engine (the Python sidecar, a child process in the app's sandbox) gets `VSTUDIO_LLM_NO_CLI=1` (claude-code / codex
  report `unavailable` and are skipped in fallback chains), `VSTUDIO_NO_CHROME=1`, `DESK_HISTORY_WATCH=` (no default
  watched folder) and `VSTUDIO_HTML_RENDER_SOCKET` + token (`src/main/htmlRender.ts`: HTML -> PNG in an offscreen
  window, local files only, no network, a Unix socket in the container + per-launch token).
- Engine transport (both editions): the sidecar listens on a Unix domain socket in the app's temp folder (in Lite the
  sandbox container: `~/Library/Containers/app.reelfold.desk/Data/tmp/rf-engine-<random>.sock`, mode 0600,
  `DESK_SOCKET`); no TCP port, so no `network.server` entitlement. Main talks to it directly
  (`src/main/engineTransport.ts`); the UI calls `app://desk/api/*` (same origin as the page: no CORS, no engine port in
  the CSP), which main's `app://` protocol handler forwards to the socket, streaming the event stream. The per-launch
  bearer token still guards every request. Windows keeps 127.0.0.1 + a random port (no AF_UNIX in CPython there).
- Runtime (both editions, one runtime): no tkinter / Tcl / Tk, no scipy (the engine is scipy-free; mlx-whisper's one
  scipy call, `signal.medfilt` for word timestamps, is patched at bundle time by `scripts/runtime/patch_mlx_whisper.py`,
  tested to give identical word timestamps), and urllib.parse without the "itms-services" scheme.
- The workflow scripts' `python3` / `ffmpeg` resolve to the bundled ones (`runtime.ts` puts both bin folders first
  on PATH): `/usr/bin/python3` is an xcrun shim that refuses to run in a sandbox.
- `electron-builder.config.cjs` `mas`: `hardenedRuntime: false`, entitlements in `packaging/mac/`:
  `entitlements.mas.plist` (app), `entitlements.mas.inherit.plist` (every nested executable: exactly app-sandbox +
  inherit), `entitlements.mas.loginhelper.plist`; `PrivacyInfo.xcprivacy`; `ITSAppUsesNonExemptEncryption = NO`;
  node-pty excluded. @electron/osx-sign adds `com.apple.application-identifier` / `team-identifier` from the profile.

## Sandbox checks (2026-10-07, macOS 26, Apple silicon, Electron 44.5.1 MAS build)

Run with `npm run mas:local` (ad-hoc signature, real MAS entitlements, real App Sandbox):

- The MAS Electron starts sandboxed (no V8 crash, cf. electron#51351). Without the `TEAMID.app.reelfold.desk`
  application group it aborts at launch (`bootstrap_check_in ...MachPortRendezvousServer: Permission denied`), so
  the group stays even in the ad-hoc test build.
- The real engine starts from the bundle; VideoToolbox H.264 works; ASR (MLX Whisper + numba) runs without the
  hardened-runtime JIT entitlements; downloads (models, fonts) work; a local Ollama on localhost answers.
- **Grants reach the running engine.** A child started before the parent consumes a security-scoped bookmark can
  read the file afterwards (tested with a minimal sandboxed app: child denied before
  `startAccessingSecurityScopedResource`, allowed after). Apple's forum answers describe `inherit` as passing only
  static rights, so this was checked rather than assumed; the engine is restarted anyway whenever assets change.
- The built-in sample, end to end (download, ASR, glossary, cleanup, face, compose, cover frames, export, QC,
  preview), finished inside the sandbox with no sandbox violations in the unified log.
- Found and fixed on the way: scripts calling `python3` hit the xcrun shim; the bundled LGPL ffmpeg has no `hqdn3d` /
  `eq` (GPL), which failed every talking-head render in **both** editions - `vstudio.media` now passes those two
  polish filters through when the ffmpeg lacks them; the Anthropic provider needed the `anthropic` package, which the
  bundled runtime lacks - it now falls back to the Messages API over plain HTTPS; with no usable AI at all (no key
  yet - the reviewer's case) the glossary step failed the whole job - it now falls back to rules and logs why.
- Known: the MAS Chromium keeps its single-instance socket in `<container>/tmp/S`. After a force-quit / crash the
  next launch can quit at once (`Failed to create .../S/SingletonCookie: File exists`); the launch after that works.
  The packaged tests clear it between launches.
- `tests/packaged/mas.spec.ts` (run by `npm run mas:local`): entitlements of every executable (no `network.server`),
  Info.plist / privacy manifest / no Squirrel / no node-pty, the sandboxed engine on its Unix socket (no listening TCP
  socket in the app or any child: `lsof`), Lite AI rows and routes, no Chromium group, updater and usage off, Lite
  copy in Settings and first run (no upsell text, no link out); `DESK_TEST_SAMPLE=1` adds the sample run. The app is
  driven over `--remote-debugging-pipe` (`tests/packaged/cdpPipe.ts`): without `network.server` the sandbox refuses
  a debugging port.

## App Store lint

`scripts/appstore/appstore_lint.py` checks a build for what App Review rejected (Reelfold 0.2.1: Guideline 2.4.5
`network.server` without matching functionality; Guideline 2.5.1 Tcl_* symbols from CPython's `_tkinter` and
unprefixed BLAS symbols scipy's SuperLU imported from Accelerate) or is known to reject:

| Check | Fails on |
|---|---|
| symbols | any Mach-O whose undefined symbols (`nm -m -u`) hit `scripts/appstore/denylist.txt` (Tcl/Tk, Apple's BLAS list, Electron's private QuartzCore classes; every entry with its source), or a BLAS/LAPACK-shaped Accelerate import that is neither `$NEWLAPACK` nor a documented legacy entry point (`cblas_*`, `name_`); `_tkinter*.so` / libtcl / libtk files |
| strings | "itms-services" in a bundled `.py` / `.pyc` |
| entitlements | signed app: every executable and architecture slice sandboxed; the app only allow-listed keys, never `network.server`; nested executables exactly app-sandbox + inherit. `--unsigned`: the same rules on `packaging/mac/entitlements.mas*.plist` |
| quarantine | any `com.apple.quarantine` attribute (ITMS-91109) |
| asar | `app.asar` holding more than `out/`, `package.json`, `node_modules/` (0.2.1's carried `build/` - a second runtime and the download cache, Mach-O files the other checks cannot see inside the archive - plus `src/`, `tests/`, `scripts/`, `packaging/`: the `mas.files` list had only an exclusion, which electron-builder reads as "everything") |

Where it runs: `bundle.mjs` (runtime symbols + strings, every mac runtime build), `npm run mas:local` (ad-hoc build),
`scripts/release-mas.sh` (signed store build, before the pkg is validated; it also greps the app's entitlements for
`network.server`), and CI: `.github/workflows/appstore-lint.yml` builds the runtime + an unsigned `--mac mas` app on
every PR touching the app, engine or requirements and runs it with `--unsigned`; its manual "validate" run signs the
pkg and runs `altool --validate-app` when the MAS certificate / profile / API key secrets exist (optional). Unit tests:
`npm run test:scripts` (a real Mach-O built in the test imports denylisted symbols; signed ad hoc with and without
`network.server`).

Kept on purpose (reported as notes, not failures): OpenCV's `cv2` imports the documented legacy LAPACK / cblas
interface (`_dgesv_`, `_cblas_sgemm`, ...), public since macOS 10 and not named in the 0.2.1 rejection; the MAS Electron
imports `fileport_makeport` / `fileport_makefd` (`sys/fileport.h` is in the public SDK; not named either).

Not checkable without her certificates: TestFlight / store signature, the provisioning profile, `altool` validation,
and the open panel itself (a real click; the bookmark path is unit-tested and the grant mechanism was tested above).

## October 15 rejection and resubmission gate

Reviewed against Apple's live [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/)
on October 15, 2026. Automated lint covers observable bundle facts, not an approval guarantee.

- **2.4.5(i), camera/microphone:** the rejected binary was 0.2.3 (20261008.2350.0).
  Newer source has Home → Record (`composer-record`, route `#/create/record`), enabled by default.
  The camera records the presenter; the microphone records speech. Both are opt-in in the recorder,
  and the recording is saved locally. Confirm this in the exact new signed MAS build before citing it
  to App Review. `recordEdit.spec.ts` checks permission denial and actual recording with synthetic
  browser tracks; it does not prove hardware permission prompts in a distribution-signed MAS app.
  Keep sandbox `device.camera` + `device.microphone`. Remove redundant hardened-runtime
  `device.audio-input` from MAS (MAS has hardenedRuntime=false); full-download entitlements are separate.
- **Guideline 4, window lifecycle:** Window → Open Reelfold (⌘0) is always enabled, recreates a closed
  main window and restores/focuses an existing one. English, Chinese and French labels are provided.
  `windowMenu.spec.ts` closes the actual test window and invokes the native menu entry, then verifies
  the new Home window and that repeated use creates no duplicates. Repeat with the signed store app.
- **2.1/2.3:** review notes must describe the new build's actual functionality, first-run downloads,
  hardware/OS requirements and a working path without an AI key. Check all listing/support URLs,
  screenshots and age/privacy answers against this exact candidate. Do not copy old claims blindly.
- **5.1.1/5.1.2(i):** Help → Privacy Policy opens the policy in the system browser. Verify this link and the App Store Connect Privacy Policy URL,
  and explicit permission before personal data is shared with third-party AI. A configured API key or
  a general privacy paragraph alone is not evidence of explicit sharing consent. Audit text, contact
  sheets/images, cloud ASR audio, provider fallback and custom endpoints, plus the privacy label.
  A no-tracking manifest does not establish that no user data ever reaches a provider.
- **2.4.5(iv)/2.5.2:** verify model/asset downloads contain data only, not Python/JavaScript/plugins or
  executables that add features. **2.4.5(iii):** verify engine/render processes stop on ordinary Quit.
- **5.2:** review rights for bundled voices/models/music/fonts and terms of publishing integrations.
  The automated symbol denylist is not a complete private-API or licensing audit.

Unsigned packaging uses `node scripts/appstore/package-unsigned.mjs`: a real JavaScript `null` signing
identity. The CLI spelling `-c.mas.identity=null` becomes the string "null" in the installed builder,
which causes an expected signing failure. No build error is now swallowed with `|| true`.
`beforePack` reads `context.packager.appInfo.version`, the real hook context; `context.appInfo` does not exist.

The `bundle` lint check requires valid store Info.plist/version/team/export metadata, purpose strings
for enabled hardware permissions, the privacy manifest, complete built app entries inside app.asar,
no Squirrel updater framework and no node-pty (including unpacked files). It runs on signed and unsigned
apps; runtime-only scans skip bundle metadata. Failed symbol/quarantine scans also fail closed.
Unknown `--only` check names are errors rather than silent clean reports.

Before upload: run the expanded signed-bundle lint and strict signature/pkg checks, exercise window
reopening and recorder access in the exact MAS candidate, and complete the manual privacy/metadata
checks above. Apple server validation requires an App Store Connect API key; local checks are not a
substitute. Upload and Submit for Review remain separate actions.

## Review risks

- **Built-in publishing browser** (Guidelines 2.5.6, 5.1.1, 5.2): it loads platform sites in embedded Chromium
  sessions and fills the upload form; she presses Publish. Say so in the review notes; no credentials pass through
  the app. Navigation is limited to each adapter's `allowedHosts`, but the platforms show user content - answer the
  age-rating "Unrestricted Web Access" question **Yes** unless the browser is locked further (see age rating notes).
- **Local services** (resolved after the 0.2.1 rejection, 2.4.5): the engine and HTML renderer listen on Unix domain
  sockets inside the container, not on a network port; the app has no `network.server` entitlement. Review notes,
  TECHNICAL NOTES:

  ```
  - Reelfold runs its video engine as a helper process inside the app's sandbox. The app talks to it over a
    Unix domain socket in the app's own container (per-launch token); it does not listen on any network port and
    has no network.server entitlement.
  - Outgoing connections only (network.client): AI providers the user configures with their own API key, a local
    model server on the same Mac if the user sets one up (e.g. Ollama), first-run downloads of speech-recognition
    models and fonts (data only, no code), and the built-in publishing browser (platform websites the user signs
    in to).
  ```
- **AI**: needs her own API key or a local model; give the reviewer a path that works without one (the sample uses
  rules when no AI is connected).
- **Size**: ~3.4 GB installed (Python + MLX + ffmpeg). Allowed; mention first-run downloads (~0.5 GB, data only).

## Research (sources)

- Electron MAS guide: app-sandbox + `application-groups` TEAMID.bundleid; use the `mas` Electron build; Transporter
  upload - https://www.electronjs.org/docs/latest/tutorial/mac-app-store-submission-guide
- Helper tools: sign with exactly app-sandbox + inherit -
  https://developer.apple.com/documentation/xcode/embedding-a-helper-tool-in-a-sandboxed-app ;
  `inherit` and dynamic (PowerBox) rights - https://developer.apple.com/forums/thread/111125
- `network.server` for listening sockets (Lite has none: Unix sockets in the container need no entitlement; a TCP
  listen without it fails with EPERM, checked 2026-10-08) -
  https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.network.server
- Microphone key in the sandbox: `device.microphone` (hardened runtime: `device.audio-input`) -
  https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.device.microphone
- Hardened runtime not required for MAS - https://developer.apple.com/forums/thread/111145
- electron-builder `mas` options (entitlements, entitlementsInherit, entitlementsLoginHelper, provisioningProfile,
  hardenedRuntime default true in v26) - https://www.electron.build/docs/mas/ ,
  https://www.electron.build/v26/docs/api/app-builder-lib.interface.masconfiguration/
- Certificates: Apple Distribution (or 3rd Party Mac Developer Application) for the app, 3rd Party Mac Developer
  Installer for the pkg - https://www.electron.build/docs/features/code-signing/code-signing-mac/
- altool: `--validate-app`, `--upload-package` (replaces `--upload-app`), API key in `private_keys` /
  `API_PRIVATE_KEYS_DIR` - https://keith.github.io/xcode-man-pages/altool.7.html
- App Review Guidelines 2.4.5 (sandbox, self-contained, no downloaded code, updates only through the store) and 2.5.2
  - https://developer.apple.com/app-store/review/guidelines/ ; ML models as data -
  https://developer.apple.com/forums/thread/793131
- Required-reason APIs (privacy manifest enforcement names iOS/iPadOS/tvOS/visionOS/watchOS; the manifest is shipped
  anyway) - https://developer.apple.com/documentation/bundleresources/describing-use-of-required-reason-api ;
  Electron has none of its own yet - https://github.com/electron/electron/issues/54617
- Export compliance (`ITSAppUsesNonExemptEncryption`) -
  https://developer.apple.com/documentation/security/complying-with-encryption-export-regulations
- Quarantine flags block uploads (ITMS-91109): `xattr -cr` before signing - https://developer.apple.com/forums/thread/772398
- TestFlight entitlements (application-identifier / team-identifier in the main app only) -
  https://developer.apple.com/forums/thread/733942
- Screenshots: 16:10, 1280×800 / 1440×900 / 2560×1600 / 2880×1800, 1-10 -
  https://developer.apple.com/help/app-store-connect/reference/app-information/screenshot-specifications
- Age ratings (4+/9+/13+/16+/18+, Unrestricted Web Access) - https://developer.apple.com/news/?id=ks775ehf ,
  https://developer.apple.com/help/app-store-connect/reference/app-information/age-ratings-values-and-definitions

### Explicit AI sharing permission (5.1.2(i))

The MAS build gates outgoing AI content through main-process native permission dialogs. Each dialog identifies the actual HTTP(S) origin and one use: analysis (text/transcripts/reference images), transcription (audio), speech (narration text), or generation (prompts/reference media). Allow is explicit; cancel/default is denial. Grants are remembered per origin and use in the app container. Help > Reset AI Sharing Permissions clears them and invalidates an open dialog. Already transmitted requests cannot be recalled. Local loopback models require no remote-sharing grant; private LAN/custom endpoints do. API key storage, paid-generation approval and OS device permissions remain separate decisions.

A per-launch authenticated Unix socket carries only the origin and fixed use, never content or keys. Missing/broken permission service denies remote content requests. AI permission refusal is terminal through LLM retries/fallback. HTTP/SDK content calls refuse redirects in MAS, so an approved service cannot forward user content to an unapproved destination. Edge's unofficial voice transport is unavailable in MAS; use local/system voices or API voice services. Full/CLI editions retain their existing behavior.

Manual checks before submission: launch the exact sandbox candidate with a fresh temporary profile; verify native Allow/Don’t Allow, new-origin/new-use prompts, persistence and Help reset. Do not use private footage to test remote AI without the creator's express approval. Reconcile the live privacy policy and App Store Connect privacy disclosures with optional cloud audio, reference images and generation input sharing; a no-telemetry flag is not proof of “Data Not Collected”. The website policy source is prepared locally; deployment requires the creator's confirmation.

The privacy manifest conservatively declares Photos or Videos, Audio Data and Other User Content, linked to the user (provider API accounts), for App Functionality, without tracking. This covers optional cloud AI input; local-only usage does not transmit these inputs. Before uploading, update App Store Connect's privacy label to match and review the configured providers' retention terms. Do not keep the historical “Data Not Collected” response. Apple defines collection as off-device access beyond real-time servicing: https://developer.apple.com/app-store/app-privacy-details/ . The manifest is not a replacement for the App Store Connect questionnaire.

### Vision SDK metrics audit

The Mac ARM runtime pins the official MediaPipe 0.10.21 wheel. Newer upstream wheels include a Clearcut uploader for performance/API-use metrics without an opt-out; Google confirms no input images/video are uploaded, but the metrics conflict with the Store build’s no-usage-counts behavior. Source: https://github.com/google-ai-edge/mediapipe/issues/6291 and https://developers.google.com/edge/mediapipe/solutions/tasks#mediapipe_tasks_privacy_notice .

The lock keeps NumPy 2 and uses OpenCV’s contrib wheel as the sole cv2 provider. Per-target overrides exclude unused JAX dependencies, keeping SciPy out. Real 478-point face detection and 6-class segmentation were verified with NumPy 2.5.3 and Protobuf 4.25.9; the runtime verifier also checks the NumPy image-buffer bridge. App Store lint requires the audited SDK version and rejects its known uploader/endpoint fingerprints in native binaries. This is a guard against this specific SDK regression, not proof that arbitrary dependencies never make network requests. Windows dependencies are unchanged by this Mac-specific repair.
