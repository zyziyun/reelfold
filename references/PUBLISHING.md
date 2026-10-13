# Publishing: how a post reaches each platform

`vstudio.platform.publishing(name)` holds the same data as this page. The rules apply to every platform:

1. **Official API first.** When a platform has an official upload API the creator can use, Reelfold uses it: OAuth
   in her **system browser** (PKCE + a loopback redirect where the platform supports it), tokens encrypted in the OS
   keychain, never a sign-in inside an embedded browser. Google refuses sign-in in embedded browsers ("Couldn't sign
   you in - This browser or app may not be secure", `accounts.google.com/v3/signin/rejected`), so YouTube has **no**
   built-in-browser path at all. In the desk app the platform's path is `PUBLISH_PATH` in
   `apps/desk/src/shared/publish/apiPlatforms.ts` and is shown on every platform in Publishing accounts.
2. **Assisted publishing only where there is no usable official API** (and, until they are wired, for the platforms
   marked "API later" below). The desk opens the platform's own upload page in its built-in browser, with one
   persistent login per account (the app never stores passwords or cookies itself), sets the video file and types the
   title, text and tags where the page allows it. The creator checks everything, makes the choices only she should
   make (category, audience, AI label, subreddit, board ...), and **presses publish herself**. She then marks the post
   as posted, with its URL. The app outlines the publish button at most; it never clicks it. Login pages are detected
   (URL rules + a password / QR form on the page) and the fill stops there. A provider's refusal page inside the
   built-in browser (Google, Facebook Login, Sign in with Apple) is detected and replaced by a plain explanation:
   sign in with the platform's own login instead, or use "Upload in your browser".
3. **Upload in your browser** is always there, for every platform: the upload page opens in her default browser
   (her own sign-in there), the file is shown to drag in, the title / description / tags are copied one at a time.
   It is a manual helper, never a sign-in path.
4. **Nothing auto-posts.** An API upload starts only from her Publish / Schedule click (a scheduled YouTube post is
   uploaded private with `publishAt`, and YouTube publishes it at that time), or from the "post scheduled videos
   automatically" switch she turned on herself (off by default). `publishing(n)["auto_post"]` is always `False`.
5. Outside the desk: an official API is opt-in per platform (`uploader: <name>` in the series / project file, with
   credentials in `$VSTUDIO_SECRETS`, never in the repo), and each upload needs the **confirm code** of the exact
   package that was reviewed (`plan` -> code -> `upload --confirm`). `uploader: manual` prints the page, the steps,
   `caption.txt`, the cover and a `CHECKLIST.md`.

The selectors of every assisted-fill page are marked **unverified** until someone checks them against the live page
with a logged-in account. The desk keeps the adapter files.

## Length per platform

Not every platform gets the same video length. Each platform's version is cut to that platform's habits for the kind
of video (`references/platforms/<name>.md`, read by `vstudio.platform_habits`; table in references/PLATFORMS.md): a
long cut with chapters for YouTube and Bilibili, a short cut for Shorts, TikTok, 小红书, Instagram, LinkedIn. One
story is rendered twice from the same project (two items, each with its own length and platforms), not reframed.
She sets her own shortest / longest per platform in Settings › Publishing › Video length (`$VSTUDIO_HOME/
platforms.json`, also read by the CLI skill) or in persona.local.yaml (`platforms.<name>.limits: {min_s, max_s}`,
`platforms.<name>.lengths: {<kind>: [min, target, max]}`). The platform files are where a platform's habits (length,
chapters, captions, title / hook, hashtags, cover, posting times) evolve; a platform-specific playbook later reads
the same file.

## Audit: official upload APIs (checked 2026-10)

No platform below offers an official **MCP** server for uploading; where an API exists it is the one listed.
"Desk path": **API** = wired, the only path; **API later** = an official API exists but is not wired yet (assisted
fill until then); **assisted** = no official upload API she can use.

| platform | official upload API | auth model | review / approval | cost | limits | desk path |
|---|---|---|---|---|---|---|
| YouTube (long-form + Shorts) | Data API v3 `videos.insert` (resumable), `thumbnails.set`, `playlistItems.insert` [S: https://developers.google.com/youtube/v3/docs/videos/insert] | OAuth 2.0 for installed apps, PKCE + loopback, system browser [S: https://developers.google.com/identity/protocols/oauth2/native-app] | YouTube scopes are sensitive: an app used by others needs **Google OAuth verification** (until then: "unverified app" screen, 100-user cap). Uploads from projects that have not passed the **YouTube API audit** are locked to private [S] | free | 10,000 quota units / day per project; an upload costs ~1,600 units [S: https://developers.google.com/youtube/v3/determine_quota_cost] | **API** |
| TikTok | Content Posting API (direct post / upload to inbox) [S: https://developers.tiktok.com/doc/content-posting-api-get-started] | OAuth 2.0 (Login Kit), PKCE for desktop | app review per product; unaudited clients post only `SELF_ONLY` from a private account [S] | free | per-creator daily post cap; file or verified-domain URL | API later |
| Instagram (Reels / feed) | Graph API Content Publishing [S: https://developers.facebook.com/docs/instagram-platform/content-publishing] | Instagram Login or Facebook Login (OAuth, registered redirect, app secret) | Professional (Business / Creator) account + Meta **App Review** for `instagram_business_content_publish` | free | rolling 24 h publishing cap; the video must be at a **public URL** | API later |
| Facebook | Graph API Reels / video publishing, **Pages only** [S: https://developers.facebook.com/docs/video-api/guides/reels-publishing] | Facebook Login, Page access token | App Review (`pages_manage_posts`); personal profiles: no API | free | 30 API Reels / 24 h per Page | API later (Pages) |
| Threads | Threads API `threads_content_publish` [S: https://developers.facebook.com/docs/threads/posts/] | Threads OAuth (registered redirect, app secret) | App Review to post for accounts other than the app's testers | free | 250 posts / 24 h; video at a public URL | API later |
| LinkedIn | Posts API + Videos API [S: https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/videos-api] | 3-legged OAuth, registered redirect URLs, client secret | members: "Share on LinkedIn" (`w_member_social`, self-serve); Company Pages: Community Management API approval | free | per-member daily throttles | API later |
| X | API v2 chunked media upload + `POST /2/tweets` [3P: https://docs.x.com/x-api/media/upload-media] | OAuth 2.0 with PKCE | developer account | **paid** access (see the X developer portal) | per tier | API later |
| Pinterest | API v5 `media` + `pins` [S: https://developers.pinterest.com/docs/key-concepts/access-tiers/] | OAuth 2.0 (registered redirect, app secret) | Trial tier: pins private; Standard tier needs review | free | per tier | API later |
| Dailymotion | Data API v2 upload sessions [S: https://developers.dailymotion.com/docs/upload-videos] | OAuth 2.0, `video.manage`, API key from Studio | self-serve API key | free | per key | API later |
| Reddit | Data API (OAuth); the **video** upload flow is undocumented (media asset lease + websocket) [3P: PRAW] | OAuth 2.0 | app pre-approval for many uses [3P] | free at low volume | 100 QPM | assisted (undocumented upload) |
| Snapchat Spotlight | Public Profile API, **allowlisted partners only** [S: https://developers.snap.com/marketing-api/Public-Profile-API/Introduction] | - | partner allowlist | - | - | assisted |
| B站 | 开放平台 视频稿件投递 [S: https://openhome.bilibili.com/doc/4] | OAuth 2.0 | developer application + review | free | per app | API later |
| 快手 | 开放平台 `photo/start_upload` -> `photo/publish` [S: https://open.kuaishou.com/platformDocs/openAbility/contentManagement/createAVideo.html] | OAuth 2.0, `user_video_publish` | approved app | free | per app | API later |
| 抖音 | 开放平台: posting for the user is limited to government / media tools; mobile share SDK needs an enterprise app [S: developer.open-douyin.com] | - | enterprise + review | - | - | assisted |
| 视频号 | none for publishing [S: WeChat community replies] | - | - | - | - | assisted |
| 小红书 | no public posting API | - | - | - | - | assisted |
| 微博 | video upload API only for government / media / institution accounts [S: https://open.weibo.com/wiki/Video/api] | - | - | - | - | assisted |
| 知乎 | none (the 2026 open platform is read-only) [S: https://developer.zhihu.com/] | - | - | - | - | assisted |
| Kwai | none for third parties; no desktop web upload | - | - | - | - | phone app (package + manual) |

Webview-sign-in risk in the built-in browser (`WEBVIEW_RISK` in `apps/desk/src/shared/publish/embedBlock.ts`):
YouTube is itself a Google sign-in (never opened there). TikTok, X, Pinterest, Reddit, LinkedIn and Dailymotion offer
"Continue with Google / Apple" buttons that fail there; Instagram and Threads offer "Continue with Facebook", which
fails there. Their **own** login (username / email / phone / QR code) works in the built-in browser. The desk detects
the refusal pages (also inside sign-in popups), hides them and says so.

## YouTube: the official Data API in the desk

- Sign in: Settings › Publishing accounts › YouTube › "Sign in with Google in your browser". Scopes asked:
  `youtube.upload` (upload) and `youtube.readonly` (the channel name, the playlists); `youtube` only when she turns
  playlists on (`playlistItems.insert` accepts no narrower scope). Tokens: one refresh token per publishing account,
  encrypted with Electron safeStorage (macOS Keychain); nothing reaches the renderer, the engine or a log.
- Publish: on a YouTube post, the form takes title, description, tags, category, visibility, now or a time
  (private + `publishAt`), Made for kids (she must answer), altered / synthetic content, Short (vertical or square,
  60 s or less; `#Shorts` added), the cover as thumbnail, a playlist. The upload is resumable, in 8 MiB chunks; a
  dropped connection or a 5xx asks the session how much arrived and resumes (exponential backoff, 6 tries per chunk).
  A refused thumbnail (channel not verified) or playlist is reported as a note; the video stays up.
- The Mac App Store (Lite) build has no loopback port (no `network.server` entitlement), so it cannot sign in:
  YouTube posts there use "Upload in your browser".

### Which Google OAuth client signs in

1. **Reelfold's client**: built into release builds from `REELFOLD_GOOGLE_CLIENT_ID` / `REELFOLD_GOOGLE_CLIENT_SECRET`
   in the release environment (`apps/desk/scripts/build.mjs`); **never committed**. A desktop client's secret is not
   confidential by Google's own rules, PKCE protects the code. Until the maintainer completes Google's OAuth app
   verification for the YouTube scopes (privacy policy + homepage on a verified domain, a demo video of the consent
   flow, the scope justification) and the YouTube API Services audit, users see the "unverified app" screen, at
   most 100 users can sign in, and uploads stay private.
2. **Her own Google Cloud client** (no shared caps; her uploads stay private until her own project passes the audit,
   which matters only for public uploads). The same steps are in the app (Settings › Publishing accounts › My own
   Google Cloud client):

**English**
1. Open https://console.cloud.google.com and create a project (any name, e.g. "Reelfold").
2. APIs & Services › Library: enable **YouTube Data API v3**.
3. Google Auth Platform (OAuth consent screen): User type **External**, app name, your email. Under Audience, add your
   own Google account as a test user.
4. Data Access: add the scopes `youtube.upload` and `youtube.readonly` (and `youtube` only for playlists).
5. Clients › Create client › Application type **Desktop app**. Copy the Client ID and the Client secret.
6. Paste both in Reelfold and press "Sign in with Google in your browser". While the app is in "Testing", Google asks
   you to sign in again every 7 days; publish it (no review is needed for your own use) to stay signed in.

**中文**
1. 打开 https://console.cloud.google.com ，新建一个项目（名字随意，比如「Reelfold」）。
2. 「API 和服务」›「库」：启用 **YouTube Data API v3**。
3. Google Auth Platform（OAuth 同意屏幕）：用户类型选 **外部**，填应用名和你的邮箱；在「受众群体」里把你自己的 Google 账号加为测试用户。
4. 「数据访问」：添加范围 `youtube.upload` 和 `youtube.readonly`（需要播放列表时再加 `youtube`）。
5. 「客户端」›「创建客户端」› 应用类型选 **桌面应用**，复制客户端 ID 和客户端密钥。
6. 粘贴到千剪，点「在浏览器中用 Google 登录」。应用处于「测试」状态时 Google 每 7 天要求重新登录一次；把它发布（自用无需审核）即可保持登录。

**Français**
1. Ouvrez https://console.cloud.google.com et créez un projet (n’importe quel nom, par ex. « Reelfold »).
2. API et services › Bibliothèque : activez **YouTube Data API v3**.
3. Google Auth Platform (écran de consentement OAuth) : type d’utilisateur **Externe**, nom de l’application, votre
   e-mail. Dans Audience, ajoutez votre propre compte Google comme utilisateur test.
4. Accès aux données : ajoutez les champs d’application `youtube.upload` et `youtube.readonly` (et `youtube`
   seulement pour les playlists).
5. Clients › Créer un client › Type d’application **Application de bureau**. Copiez l’ID client et le code secret.
6. Collez-les dans Reelfold et appuyez sur « Se connecter avec Google dans votre navigateur ». Tant que l’application
   est « En test », Google redemande la connexion tous les 7 jours ; publiez-la (aucun examen pour votre propre
   usage) pour rester connecté.

## Assisted-fill pages

| platform | assisted fill (web upload page) | wired here |
|---|---|---|
| YouTube | none: official API only (Upload in your browser opens https://studio.youtube.com/) | Data API (desk); `uploader: youtube` (ai-video workflow) |
| TikTok | https://www.tiktok.com/tiktokstudio/upload | assisted |
| Instagram | https://www.instagram.com/ (Create → Post) | assisted; `uploader: instagram-api` (ai-video) |
| X | https://x.com/compose/post | assisted; `uploader: x-api` (ai-video) |
| Facebook | https://www.facebook.com/ (Reel / Photo-video). Pages: Meta Business Suite | assisted |
| LinkedIn | https://www.linkedin.com/feed/ (Start a post → Video) | assisted |
| Threads | https://www.threads.com/ (composer → media) | assisted |
| Reddit | https://www.reddit.com/r/<subreddit>/submit (the creator types the subreddit) | assisted |
| Pinterest | https://www.pinterest.com/pin-creation-tool/ | assisted |
| Snapchat Spotlight | https://profile.snapchat.com/ (tick "Spotlight", accept the Creator Terms) | assisted |
| 小红书 | https://creator.xiaohongshu.com/publish/publish | assisted |
| 抖音 | https://creator.douyin.com/creator-micro/content/upload | assisted; `sau` (external browser tool, see ai-video) |
| 视频号 | https://channels.weixin.qq.com/platform/post/create | assisted |
| B站 | https://member.bilibili.com/platform/upload/video/frame | assisted |
| 快手 | https://cp.kuaishou.com/article/publish/video | assisted |
| 微博 | https://weibo.com/upload/channel (投稿), or the home composer | assisted |
| 知乎 | https://www.zhihu.com/zvideo/upload-video (or 创作中心 → 上传视频) | assisted |
| Dailymotion | Studio → Media → Upload video (https://www.dailymotion.com/partner/; the exact Studio host is unverified) | assisted |
| Kwai | **none**: no desktop web upload (Kwai Studio is for live streaming) | phone app (package + manual) |

URLs not confirmed by a source are written as the convention and are checked by the desk's login / upload-page
detection on first use. Platform-specific notes:

- **Reddit**: a title is required (300 characters, cannot be edited after posting) and Reddit has no hashtags. The
  creator types the subreddit, and flair / NSFW / spoiler are left to her. Read the community's rules before posting:
  many limit or ban self-promotion. See the norms in `references/PLATFORMS.md`.
- **Pinterest**: the link goes into the destination-link field, never into the description. The creator picks the
  board and the topics.
- **Snapchat**: 5-60 s, 9:16, no watermarks. Story and Spotlight cannot be posted together from the web.
- **YouTube**: one channel, two formats. The desk marks an upload as a Short (`#Shorts`) only when it is vertical or
  square and ≤ 60 s; YouTube itself accepts Shorts up to 3 min. Long-form from a vertical-only clip is flagged at
  packaging time.
- **AI label**: every Chinese platform has a 内容由 AI 生成 / 作者声明 toggle (labeling rules in force since
  2025-09-01). YouTube has "Altered or synthetic content", TikTok "AI-generated content", Meta "AI info". The creator
  ticks it herself; the checklist reminds her.

The ai-video workflow's own notes (series packages, the API audit rules, the confirm step) are in
`workflows/ai-video/references/PUBLISHING.md`.
