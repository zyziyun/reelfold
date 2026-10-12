# Reelfold website (apps/site)

Lives in `apps/site/` of the [Reelfold](https://github.com/zyziyun/reelfold) monorepo; MIT like the rest of
the repo (see `LICENSE`). `npm install` works here or at the repo root (one npm workspace for all apps).

Product site for Reelfold (千剪), the free, open-source (MIT) batch video app for macOS. Design: direction F
("Paper", editorial calm) from the 2026-10 redesign (`site-redesign/` in the design repo: README, IMPLEMENTATION.md,
reference HTML and PNGs). Static Astro build served by a Cloudflare Worker on reelfold.com. No cookies, no analytics,
no third-party requests: fonts are self-hosted (SIL OFL, licences in `public/fonts/`). About 1 KB of inline JS
(scrolled-nav hairline, fade-in on scroll, language switch keeps `#section`); everything works without it.

## Pages (every page in 4 languages)

| Page | en | 中文 | Français | Español |
|---|---|---|---|---|
| Home | `/` | `/zh/` | `/fr/` | `/es/` |
| Use cases | `/podcast-clips/`, `/interview-clips/`, `/course-slicing/`, `/course-from-notes/`, `/travel-vlog/`, `/talking-head/`, `/studios/` | `/zh/…` | `/fr/…` | `/es/…` |
| Platform specs | `/platforms/` (anchor per platform, e.g. `/platforms/#xiaohongshu`) | `/zh/platforms/` | … | … |
| Comparisons | `/compare/opus-clip/`, `/compare/descript/`, `/compare/capcut/` | `/zh/compare/…` | … | … |
| Legal drafts (noindex) | `/privacy/`, `/terms/` | 中文 | English text + note | English text + note |

`/docs/` (nav + footer) is the separate Starlight docs site (`apps/docs`), copied into `dist/docs` at deploy time;
this site never builds anything under `/docs`. Old `/en/*` URLs are static redirect pages.

## Run

```bash
npm install
npm run dev          # http://localhost:4321
npm run build        # static site in dist/ (+ sitemap-index.xml)
npm run check        # copy rules + site checks on dist/ (below)
npm run preview      # serve dist/
npm run screenshots  # node scripts/screenshot.mjs <baseUrl> [name-regex]: full-page PNGs into screenshots/
npm run deploy       # manual build + wrangler deploy (normally CI does this on every push to main: docs/CI_CD.md)
```

Generators (outputs are committed, so `npm run build` needs only Node):

| Command | Writes | When |
|---|---|---|
| `npm run fonts:zh` | `public/fonts/noto-serif-sc-600-{core,extra}.woff2`, `src/styles/zh-font.css`, `src/data/zh-font.json` | after changing 中文 headings (build first). Needs `pip install fonttools brotli` |
| `npm run og` | `public/og/{en,zh,fr,es}.png` (1200×630) | after changing the hero copy. Needs Playwright + Chrome, ImageMagick |
| `npm run platforms` | `src/data/platforms.json` from `lib/vstudio/platform.py` | after the engine's platform profiles change |
| `python3 scripts/fr-typo.py` | narrow no-break spaces in French strings (before `: ; ? !` and inside `« »`) | after editing French copy |
| `node scripts/brand.mjs` | favicons, app icons, `site.webmanifest` | after a logo change |

## Structure

```
src/config.ts               URL, GitHub / download URLs, docs paths, skill command, and `downloadReady` (below)
src/i18n/{en,zh,fr,es}.ts   home + shared UI copy; zh/fr/es are typed against en (a missing key fails the build)
src/i18n/index.ts           LANGS, HTML_LANG, HREFLANG (en, zh-Hans, fr, es), prefix(), pathFor()
src/content/usecases.ts     the 5 use-case pages, written per language
src/content/compare.ts      the 3 comparison pages: values, notes, sources, CHECKED date
src/content/platforms.ts    /platforms/ copy; numbers come from src/data/platforms.json
src/data/batch.ts           the real batch on the home page (72-min lecture, 24 clips, timecodes, QC result)
src/layouts/Base.astro      <html lang>, head (Seo), fonts preload, nav, footer, the inline script
src/components/             Seo, SiteNav, SiteFooter, Ctas, Print, Img (AVIF+WebP <picture>), Faq, Crumbs, Related,
                            Icon, Logo, home/* (Hero, PromoVideo, Steps, Makes, Audiences, Batch, Platforms, ThreeUp,
                            NextTeaser, OpenSource, FinalCta), Privacy, Terms
src/views/                  page templates (HomePage, UseCasePage, ComparePage, PlatformsPage, LegalPage)
src/pages/                  thin route files: / , /[slug]/, /compare/[tool]/, /platforms/, … and the same under zh/ fr/ es/
src/lib/                    zhHeading (中文 clause-safe line breaks), images (screenshot registry), schema (JSON-LD),
                            releaseStatus (build-time downloadReady from the GitHub API)
src/assets/                 app screenshots (re-rendered with the Reelfold name), batch covers, demo sheets
src/styles/global.css       tokens + all component styles (ported from the F prototype)
scripts/                    check-copy, check-site, subset-zh-font.py, og, export-platforms.py, fr-typo.py, screenshot, brand
docs/SEO_SUBMIT.md          Google Search Console, Bing Webmaster, 百度站长 steps
```

## Promo film and screenshot slots

- **Promo film**: put the film at `public/media/reelfold-promo.mp4` (H.264, 16:9) and a poster frame at
  `public/media/reelfold-promo.jpg`, then rebuild. `src/components/home/PromoVideo.astro` shows it under the hero on
  every language; with no mp4 there, nothing renders. To swap the film, replace the file (same name) and rebuild.
- **App screenshots** (`src/assets/app/*-{en,zh}.webp`, `src/lib/images.ts`): 2880×1800 (1440×900 at 2x), light
  theme, from a desk build of `main` on an isolated temp profile (own userData / VSTUDIO_HOME / cache), with real engine
  runs and Claude Code as the AI. Footage is CC0 / public domain only (see "Image credits"); never a creator's own
  footage, names or paths. `HOME_DASH` is the Home dashboard shot. Output sheets (`src/assets/demos/`) are frames of
  the clips those runs exported.

## Image credits

All footage in the screenshots and sheets is from Wikimedia Commons under CC0 (public domain dedication); no credit is
required, it is listed here as a courtesy:

- Talk: "The Research Stadium" (Daniel Mietchen) · classroom talk: "Interview with a Teacher - Glen Caruso"
  (Chase Bohannon, Glen Caruso)
- Australian coast: "Aerial view of sea and boats" (Wayne McKelvie), "Forster breakwater and beach", "Panoramic view of
  Stockton Beach", "Black Head Beach, New South Wales", "Southern Wallabi Beach surf conditions…", "Surf Life Saving NSW
  drone operation at a beach" (JaredMcKenzie), "Sunrise Glow Over Surf Beach…", "Federation Hut near Mt Feathertop"
  (Bracteantha)
- River surfing: "Die Ewige Welle und Surfers in Augsburg" (Sillerkiil)
- Okanagan: "After Sunset on the Sandbar at the Mouth of Mission Creek", "Autumn Cattails at Sunset in East Kelowna",
  "Aerial View of Crags of Kelowna Mountain in Early Winter", "Dying Light on Okanagan Mountain", "Glimpses of Lake
  Okanagan from the Fairlane trail…", "Forward View of CCGS McIntyre Bay" (Extemporalist)

Course episodes are rendered by the engine from lesson notes written for the demo (diagrams + offline Kokoro voice).

## The "coming soon" switch

`SITE.downloadReady` in `src/config.ts`, decided at build time by `src/lib/releaseStatus.ts`: `true` when
`https://github.com/zyziyun/reelfold/releases/latest` is a published release with a `.dmg` (GitHub API; drafts never
count). While `false`, every CTA on every page and language is **Star on GitHub** + **Build from source**, the fine
print says the macOS app is coming soon, the header button is "Star", and the JSON-LD has no `downloadUrl`; once `true`
everything switches to **Download for macOS**. The deploy workflow (`.github/workflows/deploy-web.yml`) deploys only on
`release: published`, so publishing a desk release turns the buttons on within minutes. `SITE_DOWNLOAD_READY=1` / `0`
forces it; `DOWNLOAD_READY_FALLBACK` in `config.ts` is used only when the API cannot be reached. The build logs
`[site] downloadReady=… (reason)`.

## SEO

- Per page and language: `<title>`, description, self canonical, hreflang `en` / `zh-Hans` / `fr` / `es` / `x-default`,
  `og:*` (locale + alternates, 1200×630 image per language), Twitter card.
- Titles ≤ 70 characters (中文 ≤ 40), descriptions ≤ 160 (中文 ≤ 100), checked by `npm run check`.
- JSON-LD: home = SoftwareApplication (price 0, MIT, operating systems, version, download URL once released, screenshot,
  features) + Organization + FAQPage; use-case, compare and platform
  pages = BreadcrumbList + FAQPage. FAQ JSON-LD is built from the same arrays as the visible `<details>`.
- `sitemap-index.xml` (`@astrojs/sitemap`, every indexable URL with `xhtml:link` alternates); `robots.txt` points to it.
  Legal drafts are `noindex` and not in the sitemap.
- `npm run check` (scripts/check-site.mjs) fails on: not exactly one h1, skipped heading levels, missing
  title/description, non-absolute or wrong canonical, incomplete or non-reciprocal hreflang, JSON-LD that does not
  parse, missing OG image, `<img>` without alt/width/height, broken internal links or `#anchors`, third-party
  resources, and 中文 heading characters missing from the font subset.

## Copy rules

Enforced by `npm run check:copy` on the built HTML: no em-dashes; no hype words (最, 第一, 100%, 首个, 唯一, 顶级, 极致,
颠覆, 爆款, 保证; best, ultimate, guaranteed, 10x, seamless …). Honest claims only: the numbers are one real batch
(72-minute lecture → 24 clips × 4 formats = 96 files, $0.73 AI cost, 21/24 passed the automatic checks); the
comparison tables say "Not verified" where a primary source did not confirm a fact, and show the date they were checked.
People in the images come only from CC0 footage (see "Image credits").

## Lighthouse (local builds)

Mobile and desktop for `/`, `/zh/`, `/fr/`, `/es/`: Performance 98–100, Accessibility 100, Best Practices 100, SEO 100
(mobile LCP 2.2–2.3 s, CLS 0, TBT 0). `/podcast-clips/`, `/compare/descript/`, `/zh/platforms/` mobile: 99–100 / 100 / 100 / 100.

2026-10-12, local build served without compression (`python3 -m http.server`), Lighthouse 12, simulated throttling:
mobile `/` 89 → 90, `/zh/` 82 → 87, `/podcast-clips/` 93 → 97, `/zh/course-slicing/` 83 → 93, `/fr/` 89 → 90;
desktop 99–100 → 100 everywhere; Accessibility, Best Practices and SEO 100 before and after.

## Before publishing

1. `SITE.contactEmail` (legal pages) is a placeholder.
2. Legal review of `/privacy` and `/terms`, then remove the draft banners and `noindex`.
3. First macOS release: publish it on GitHub; the site redeploys and `downloadReady` turns on by itself.
4. Enable GitHub Discussions (linked from the open-source section and footer).
5. Re-check `src/content/compare.ts` before changing `CHECKED`; prices and features of other tools change.
6. Submit the site to search engines: `docs/SEO_SUBMIT.md`.
