# CI / CD

Everything ships from GitHub Actions; nobody deploys or builds a release by hand.

| Workflow | Runs on | Does |
|---|---|---|
| `deploy-web.yml` (Deploy web) | PRs and pushes to `main` touching the site, docs or the docs generator inputs; `release: published`; manual | Regenerates the docs reference pages from the engine, builds site + docs (`scripts/build-web.sh`), runs the site + docs checks and `check_skill`. On a published release or a manual run on `main` it then deploys (a push to `main` only builds and checks, so the live site never describes an unreleased app) to the Cloudflare Worker `reelfold-site` (reelfold.com) and smoke-tests `/`, `/zh/`, `/docs/`. PRs never deploy. |
| `desk-release.yml` (Desk release) | tag `v*`; manual (dry run by default) | Builds, signs, notarizes, staples and verifies the macOS arm64 app with `apps/desk/scripts/release-mac.sh`, then creates / updates a **draft** GitHub Release with the DMG, zip, blockmap, `latest-mac.yml` and release notes. Never publishes. |
| `site.yml` (Site) | PRs and pushes | Checks only (site build). |
| `desk-ci.yml` (Desk CI) | PRs; pushes to `main`, `release/**`; tags `v*`; nightly; manual (`tier`: full / quick) | Parallel jobs. `changes` decides whether desk files changed (if not, every job is skipped and `test` passes as a no-op) and, in the quick tier, which tests the change can affect (below). macOS: `checks` (lint + typecheck always; the picked unit, sidecar engine and scripts tests) and `e2e (i/n)` (the picked Electron e2e specs, 1-4 shards; the whole suite in 4 in the full tier), then the aggregator **`test`** (green only when all of them passed; the required check, and the release automation waits on this name). `e2e report (merged)` uploads one HTML report (`desk-e2e-report`). Windows: `Windows checks` on every run; the **full tier** adds the engine pytest on Windows and `Windows e2e (i/4)`; all rolled up in **`Windows`**, which fails the run but is not part of `test`. |
| `engine.yml` (Engine) | PRs; pushes to `main`, `release/**`; tags `v*`; nightly; manual (`tier`) | `changes` (with the picked test files, below), then `pytest`: `check_skill`, then the picked tests in parallel (`pytest -n auto`, pytest-xdist, slowest tests listed at the end), then the aggregator **`test`** (no-op when no engine file changed). A normal push / PR skips the tests marked `slow` (long real renders); the full tier runs them. |
| `deploy-telemetry.yml` (Deploy telemetry) | PRs and pushes to `main` touching `apps/telemetry`; manual | Unit tests + typecheck. On `main`: finds or creates the D1 database `reelfold-usage`, applies `apps/telemetry/migrations`, deploys the Worker `reelfold-telemetry` on `t.reelfold.com`, sets `STATS_TOKEN`, smoke-tests `/api/v1/health`. |
| `metrics-weekly.yml` (Weekly metrics) | Mondays 02:00 UTC; manual | `scripts/metrics/github_stats.py` + `scripts/metrics/usage.py` into the run summary, one CSV row each into the `metrics-history` artifact. Totals only. |

**Tiers.** A normal push or PR runs the quick tier: **only the tests the change can affect** (next section), and never
the Windows engine pytest, the Windows e2e suite or the engine tests marked `slow`. The **full tier** runs all of it: nightly, on tags `v*`, on `release/**`
branches, on manual runs (`tier=full`, the default) and when CI files, lockfiles, requirements, `pyproject.toml` or the
desk packaging change (`.github/scripts/ci-changes.sh` has the lists). Runs of `main` and `release/**` queue instead of
cancelling each other, so every `main` commit gets a result; a PR or feature-branch run is cancelled by a newer push to
the same ref; tag runs are never cancelled. Caches: npm, the Electron / electron-builder downloads (keyed on
`package-lock.json`), the Windows ffmpeg (per month); python deps go in with uv (no cache needed); the release workflow also
caches its runtime downloads (keyed on the runtime lock and requirement files). Locally, the e2e suite can be split the
same way: `npx playwright test --shard=1/4` in `apps/desk` (after `npm run build`); `pytest -n auto -m "not slow"` is
the engine's quick tier over every test.

**Which tests a change runs (quick tier).** The `changes` job of each workflow runs
`.github/scripts/select_tests.py` over the changed files; its summary (the job's page on GitHub) lists every picked
test and why. The rules, and the lists to tune, are in `.github/test-map.yml`:

- **Desk e2e** (`apps/desk/tests/e2e`). The specs drive the built app, so their imports never reach the renderer
  (Playwright's `--only-changed` would find nothing); they find elements by `data-testid` instead. A changed renderer
  file brings its own test ids (a hook, stylesheet or helper without any: those of the nearest files importing it,
  type-only imports ignored), and the specs using one of them run. Ids most specs wait on (`home`, the Studio list, the
  composer: `e2e_landmark_specs`) count only when the file renders nothing more specific. Main process, preload, the
  engine sidecar and `lib/`: the `e2e:` globs, the specs named like the module (`updater.ts` → `update.spec.ts`), the
  specs whose python fixture imports it, else the smoke set (`e2e_smoke`, `e2e_real_smoke` for engine code the desk
  loads). A changed spec, or a helper / fixture it uses, runs that spec. The picked specs are split by their estimated
  time (`e2e_weights`): one shard up to ~5 min, at most 4.
- **Sidecar unittests** (`apps/desk/engine/tests`) and **engine pytest** (`tests/`): a static import scan. A test runs
  when its import closure holds a changed module (its own imports wherever they are, past that module-level imports
  only: the engine imports lazily inside functions everywhere, and following those would pick nearly every test). A
  module no test imports runs the tests that name it, else `sidecar_smoke` / `pytest_smoke`. A changed test runs itself.
- **Desk unit tests**: `vitest related` on the changed desk files.
- **Everything** (the quick tier's whole suite): a change to a `full` / `full_desk` / `full_engine` path (lockfiles,
  requirements, CI files, the e2e harness, the build config), or a run without a change list (a new branch, a manual
  `tier=quick` run). Docs (`ignore:`) run nothing, and `test` passes as a no-op.

Locally: `git diff --name-only origin/main | python3 .github/scripts/select_tests.py --suite desk --changed -`
(or `--suite engine`) prints the same selection; `tests/test_ci_select.py` checks the rules.

The website's download buttons follow the releases by themselves: the site build asks the GitHub API whether a
published release with a `.dmg` exists (`apps/site/src/lib/releaseStatus.ts`), and publishing a release triggers a
redeploy. Until the first release is published, the buttons say "Star on GitHub" / "Build from source".

## One-time setup (the maintainer, on her Mac)

Secrets are pasted at the `gh` prompt or piped from a file; they never go into a chat, a commit or a shell history.
`gh auth status` must show you logged in to github.com with the `repo` scope. Check what is set (names only) with
`gh secret list --repo zyziyun/reelfold`.

### 1. Cloudflare (website deploys)

1. dash.cloudflare.com → *My Profile* → *API Tokens* → **Create Token** → template **Edit Cloudflare Workers** →
   *Use template*.
   - Account Resources: *Include* → your account.
   - Zone Resources: *Include* → *Specific zone* → `reelfold.com`.
   - *Continue to summary* → *Create Token*, copy the token (shown once).
2. Account ID: dash.cloudflare.com → *Workers & Pages* → right column *Account ID* (or `npx wrangler whoami`).
3. Store both:
   ```bash
   gh secret set CLOUDFLARE_API_TOKEN --repo zyziyun/reelfold     # paste the token at the prompt
   gh secret set CLOUDFLARE_ACCOUNT_ID --repo zyziyun/reelfold    # paste the account ID
   ```
4. Test: GitHub → Actions → *Deploy web* → *Run workflow* (branch `main`). The *Deploy to Cloudflare* job should end
   with three `ok` smoke-test lines. If wrangler reports an authentication error about the custom domains, edit the
   token and add *Zone → DNS → Edit* for `reelfold.com`.

Until both secrets exist, the deploy job is skipped with a "Deploy skipped: missing secrets" warning; the build and
checks still run.

### 2. Apple (signed + notarized desk releases)

**Developer ID certificate (.p12)**

1. Keychain Access → *login* → *My Certificates* → right-click **Developer ID Application: <name> (<TEAMID>)** (the
   private key must be listed under it) → *Export…* → format *Personal Information Exchange (.p12)* → save as
   `cert.p12` → choose a strong password.
2. Store it:
   ```bash
   base64 -i cert.p12 | gh secret set MAC_CERT_P12_BASE64 --repo zyziyun/reelfold
   gh secret set MAC_CERT_PASSWORD --repo zyziyun/reelfold       # paste the .p12 password
   ```

**App Store Connect API key (notarization)**

1. appstoreconnect.apple.com → *Users and Access* → *Integrations* → *App Store Connect API* → *Team Keys* → **+**
   (the first time, the Account Holder has to click *Request Access*). Name `reelfold-notary`, access **Developer** →
   *Generate*.
2. Note the **Issuer ID** (above the table) and the **Key ID** (in the row), then *Download* the `AuthKey_<KEYID>.p8`
   (possible only once).
3. Store them:
   ```bash
   base64 -i AuthKey_XXXXXXXXXX.p8 | gh secret set APPLE_API_KEY_P8_BASE64 --repo zyziyun/reelfold
   gh secret set APPLE_API_KEY_ID --repo zyziyun/reelfold         # paste the Key ID
   gh secret set APPLE_API_ISSUER_ID --repo zyziyun/reelfold      # paste the Issuer ID
   ```

**Then delete the local copies**: `rm cert.p12 AuthKey_*.p8` (and empty the Trash if they went there). The
certificate stays in your keychain; a lost `.p8` is replaced by revoking the key and generating a new one.

Test without releasing: Actions → *Desk release* → *Run workflow* with *dry run* ticked. It builds, signs, notarizes
and verifies, and keeps the DMG as a workflow artifact (about 45 minutes, longer on the first run while the runtime
cache fills). Without the five secrets it stops in its first step and names the missing ones.

The local `npm run release:mac` keeps using the keychain identity and the `vstudio-notary` notarytool profile; it
switches to the API key only when `APPLE_API_KEY` (path to the `.p8`), `APPLE_API_KEY_ID` and `APPLE_API_ISSUER` are
all set (`DRY_RUN=1` checks either mode without building).

### 3. Optional: approve each website deploy

GitHub → *Settings* → *Environments* → `production` (created by the first deploy run) → *Required reviewers* → add
yourself. Every deploy then waits for a click on *Review deployments*. Leave it off for fully automatic deploys.

### 4. Usage counts (opt-in, anonymous; `apps/telemetry`)

The desk app's "Share anonymous usage counts" (off by default) posts to the Worker `reelfold-telemetry` on
`https://t.reelfold.com`, which stores rows in the D1 database `reelfold-usage` (what is stored:
`apps/telemetry/migrations/0001_init.sql`; the public page: `apps/docs/src/content/docs/concepts/usage-counts.md`).
It has its own custom domain because `reelfold.com` is a Custom Domain of the site Worker, and a Custom Domain
takes precedence over any route on the same hostname (a `reelfold.com/api/*` route would never run).

1. **D1 permission.** The "Edit Cloudflare Workers" token template has no D1 permission. dash.cloudflare.com →
   *My Profile* → *API Tokens* → the token behind `CLOUDFLARE_API_TOKEN` → *Edit* → *Add more* → **Account → D1 →
   Edit** → *Continue to summary* → *Update token* (the token value does not change; nothing to re-paste). Without
   it, *Deploy telemetry* stops with "The Cloudflare token cannot use D1".
2. **Stats token** (who may read the numbers): make a random secret, keep a copy on the Mac, store it in GitHub:
   ```bash
   mkdir -p ~/.config/reelfold && openssl rand -hex 32 > ~/.config/reelfold/stats_token && chmod 600 ~/.config/reelfold/stats_token
   gh secret set STATS_TOKEN --repo zyziyun/reelfold < ~/.config/reelfold/stats_token
   ```
   then GitHub → Actions → *Deploy telemetry* → *Run workflow* (it puts the secret on the Worker).
3. **Read the numbers:** `python3 scripts/metrics/usage.py` (reads `~/.config/reelfold/stats_token`).
4. **Leave your own Mac out:** Settings › General › Privacy shows the anonymous ID once sharing is on;
   `python3 scripts/metrics/usage.py mark-internal <that id> --note "my mac"`.

The Worker keeps no IP addresses (Workers Logs are off in `wrangler.jsonc`), drops unknown fields, rate-limits per
address (in memory) and per install (200 events a day), and a daily cron deletes raw rows after 13 months while
keeping per-day totals without ids. By hand (rarely needed): `cd apps/telemetry && npx wrangler d1 migrations apply
reelfold-usage --remote && npx wrangler deploy` with the database id in `wrangler.jsonc`.

### 5. Site visits and GitHub traffic (no code in the app)

- **Cloudflare Web Analytics** (cookieless): dash.cloudflare.com → *Analytics & Logs* → *Web Analytics* → *Add a
  site* → `reelfold.com` → keep **Automatic setup** on. Cloudflare then adds its beacon to the pages it serves for
  `reelfold.com` (site and `/docs`); numbers appear there after a few minutes. If automatic setup is not offered,
  copy the site's token (the 32-character `token` in the snippet it shows) into the repository secret
  `CF_BEACON_TOKEN`; the next *Deploy web* builds the beacon into every page (`apps/site/src/layouts/Base.astro`,
  `apps/docs/astro.config.mjs`). Without the secret, no script is added.
- **GitHub traffic** (views, clones, referrers) is kept by GitHub for 14 days only; *Weekly metrics* saves it every
  Monday. The workflow token cannot read traffic: add a fine-grained token (repository `zyziyun/reelfold`,
  permission *Administration: read-only*) as `METRICS_GH_TOKEN`, or run `python3 scripts/metrics/github_stats.py`
  locally (uses your `gh` login). Stars and release downloads work without it.
- The weekly run summary and the `metrics-history` artifact are visible to anyone who can see this public repo's
  Actions: they hold totals only, never ids.

## How to release a new desk version

```bash
npm run version:bump -- 0.2.1                  # repo root: sets apps/desk/package.json (+ lock) to 0.2.1, no tag
git commit -am "chore(desk): release v0.2.1"
git push origin main
git tag v0.2.1 && git push origin v0.2.1       # starts Desk release
```

1. Optional, before tagging: write the notes in `apps/desk/release-notes/v0.2.1.md` (or a `## 0.2.1` section in
   `apps/desk/CHANGELOG.md`). Otherwise they are generated from the `feat` / `fix` / `perf` commits since the last tag.
2. Wait for *Desk release* (~45 min). A tag that does not match `apps/desk/package.json` fails at once.
3. GitHub → *Releases* → the draft `v0.2.1`: download the DMG, try it, edit the notes, **Publish release**.
4. Publishing starts *Deploy web*: a few minutes later reelfold.com shows "Download for macOS" (first release), and
   installed apps pick the update up within 6 hours.

A failed run can be re-run from the Actions page; a re-run on the same tag replaces the files in the draft. A
published release is never modified: bump the version instead.

## Auto-publish later (optional)

To skip the manual Publish click, in `.github/workflows/desk-release.yml` → *Create / update the DRAFT GitHub Release*:
drop `--draft` from `gh release create` and add `gh release edit "$TAG" --draft=false` after the update branch.
A release published by the workflow's own token does **not** trigger other workflows, so also add `actions: write` to
the job's permissions and a final step `gh workflow run deploy-web.yml --ref main` to refresh the website.

## Windows

Full Desk CI runs core engine pytest in four independent Windows jobs, separate from desktop checks. Sorted
`tests/test_*.py` files are partitioned once across the jobs, with two pytest workers per job to bound media/model
memory. No slow tests are excluded. Each shard retains its verbose log and JUnit report as `windows-engine-N`;
native calls lasting four minutes emit a thread dump, and each test has a five-minute timeout so a stuck worker
fails with diagnostics before the runner is terminated. The `Windows` gate requires every engine and e2e shard.

The *windows* job in `desk-release.yml` builds the **unsigned** Windows x64 NSIS installer on every tag push (and on a
manual run with *windows* ticked). It does not block the macOS files: the mac job never waits for it. When both are
done, the *windows-release* job checks the files (`latest.yml` must point at the `.exe` with the right sha512) and
attaches `Reelfold-<v>-win-x64-setup.exe`, its `.blockmap` and `latest.yml` (the Windows update feed) to the same draft
release, creating the draft if it is somehow missing. If the Windows build fails the run turns red and its summary says
"Windows installer NOT attached"; the macOS draft is complete, and *Re-run failed jobs* attaches the installer later.
A dry run with *windows* ticked does the same checks and prints the upload it would do. Signing it later:
`apps/desk/docs/RELEASING.md` §3.
