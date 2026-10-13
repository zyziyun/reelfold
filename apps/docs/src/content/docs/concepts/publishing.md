---
title: Publishing
description: How a post reaches each platform. YouTube goes through its official API; other platforms get assisted fill in the built-in browser, and you press publish. Nothing posts alone unless you turn on automatic posting.
---

Reelfold helps you post, but it never posts on its own unless you turn that on. Where a platform has an official upload API that Reelfold supports (YouTube today), it uses that API. Everywhere else, the Mac app opens the platform's own upload page in its built-in browser, sets the video file and types the title, text and tags. You check everything, make the choices only you should make, and press publish yourself.

## Why it matters

A post is public and goes out under your name. The last look should be yours: the right account, the right category, the AI-content label, the audience. Assisted publishing removes the tedious part (dragging files, pasting copy, retyping tags for each platform) and keeps the part that matters with you. It also works on platforms that have no public posting API at all, which includes most Chinese platforms.

## How it works

Each platform has one path, shown on it in **Settings › Publishing**: **Official API** (YouTube), or the built-in browser (every other platform). Every platform also has **Upload in your browser** (see below).

### Assisted fill in the built-in browser

1. **One persistent login per account.** You sign in to each platform once inside the app's browser. The app never stores your passwords or cookies itself, and when it detects a login page it stops filling. Some platforms offer "Continue with Google", "Continue with Facebook" or "Sign in with Apple"; those providers refuse sign-in inside an app's built-in browser, so Reelfold replaces their refusal page with a short explanation. Use the platform's own email, phone or QR code login instead.
2. **Fill.** For each post, the app opens the upload page, sets the video file and types the title, body and tags where the page allows it.
3. **You publish.** You review, set category, audience, AI label, subreddit or board as needed, and press the platform's publish button. The app may outline that button; it never clicks it. There is no way to express a click in an adapter.
4. **Posted.** Reelfold watches the page after your click; when the platform confirms, the post is marked posted, with its link when the page shows one. You can also mark it by hand.

Scheduled posts are not just calendar entries: at each post's time Reelfold sends a "Time to post" notification, and clicking it opens the filled upload page. Posts that came due while the app was closed wait at the top of Publish. See [How scheduling works](/docs/guides/scheduling-publishing/#how-scheduling-works).

Each platform's fill steps live in a small adapter file. You can add or override adapters without rebuilding the app, in `~/Library/Application Support/Reelfold/adapters/`. Adapters written without a live session are marked unverified until someone checks them against the real page.

### YouTube: the official YouTube Data API

YouTube is published only through Google's official YouTube Data API, never through the built-in browser (Google refuses sign-in inside embedded browsers).

1. **Sign in once** in **Settings › Publishing › YouTube** with **Sign in with Google in your browser**. Google's sign-in opens in your system browser; Reelfold never sees your password. Reelfold asks to upload videos to your channel and to see your channel's name and playlists; it cannot edit or delete your videos. Adding videos to playlists is a separate permission you can allow. Tokens are kept in the macOS keychain.
2. **Publish from the post.** A YouTube post shows a publish form instead of a web page: title, description, tags, category, visibility, **Now** or **At a time**, the audience (made for kids or not, which YouTube requires), the altered or synthetic content label, **Publish as a Short**, the cover as thumbnail, a playlist. Nothing goes out until you press **Publish** or **Schedule**.
3. **A scheduled post** is uploaded now as private with a publish time; YouTube makes it public at that time, even if your computer is asleep.

Google keeps uploads from a Google Cloud project that has not passed YouTube's API audit private. You then make them public in YouTube Studio. Sign-in uses Reelfold's Google app when your build includes it, or **My own Google Cloud client** (see [Scheduling and publishing](/docs/guides/scheduling-publishing/#youtube-sign-in-and-your-own-google-cloud-client)). The Mac App Store edition cannot sign in to YouTube; each YouTube post offers **Upload in your browser** instead.

### Upload in your browser

Every platform has **Upload in your browser**: the upload page opens in your default browser, where you are already signed in, and Reelfold hands you each piece. It shows the video file to drag in and copies the title, description and tags one at a time. You press publish there, then paste the post's link to mark it posted.

### Nothing posts on its own

An upload starts only from your click (Publish, Schedule, or your publish button on a filled page). The one exception is the **Post scheduled videos automatically** switch for YouTube in Settings › Publishing, which you turn on yourself (off by default): then scheduled YouTube posts are uploaded about an hour before their time. TikTok, X and Instagram are listed under **Post automatically (official APIs)** as **Not yet**; they use assisted fill until then.

With the skill, you turn an official API on explicitly in a series or project file (`uploader: <name>`), with credentials kept outside the repo, and each upload requires the confirm code of the exact package you reviewed.

### Video length per platform

Not every platform gets the same length. YouTube and Bilibili get a long cut with chapters; Shorts, TikTok, Xiaohongshu, Instagram and LinkedIn get a short cut. Set your own shortest and longest per platform in **Settings › Publishing › Video length**. See [One master, many platforms](/docs/guides/multi-platform/).

### Without the Mac app

With the skill alone, `uploader: manual` gives you the upload page, the steps, the caption text, the cover and a checklist for each post.

## Platform notes

- **YouTube:** official API only, long-form and Shorts. To publish as a Short from Reelfold, the video must be vertical or square and 60 seconds or less (`#Shorts` is added).
- **Reddit:** you type the subreddit; a title is required and can't be edited later. Read the community's rules on self-promotion first.
- **Pinterest:** the link goes in the destination-link field, never the description. You pick the board.
- **Snapchat Spotlight:** 5 to 60 seconds, 9:16, no watermarks.
- **Kwai:** no desktop web upload; you get a package to post from the phone app.
- **Xiaohongshu, Douyin, WeChat Channels, Bilibili, Kuaishou, Weibo, Zhihu:** assisted fill on the creator upload page. Each has an AI-content declaration toggle; tick it yourself when it applies.

## In the Mac app

Publish shows your week. Each approved clip has its post copy ready; open it, check the filled page (or the YouTube form), press publish, and the post is marked posted.

## With the Claude Code skill

Exports and packages come with covers, post copy and a schedule. Nothing is uploaded unless you have turned on an official API as described above; otherwise you post from the package yourself, or open the project in the Mac app to publish from there.

## Related

- [Scheduling and publishing guide](/docs/guides/scheduling-publishing/)
- [Platforms reference](/docs/reference/platforms/)
- [Publishing engine reference](/docs/reference/engine/publishing/)
- [Privacy](/docs/concepts/privacy/)
