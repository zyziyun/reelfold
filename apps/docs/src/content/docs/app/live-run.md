---
title: The live run page
description: "Watch a Reelfold project while it is made: what it is doing in one sentence, time left, each step's files and decisions, the pieces as they appear, the live Claude Code or Codex stream, and Watch all."
---

Open a project that is planning or running and its page shows the work as it happens. You can follow it closely, or leave and come back; nothing here is required.

<!-- SCREENSHOT PLACEHOLDER: a running project's page with the Live pane docked below (re-captured in apps/site). -->

## At the top

- **One sentence** saying what it is doing now, for example "Captions — clip 4 of 8".
- **Progress** in % and the time left, from the engine's real stages (plan, transcribe, cut, captions, render, check, copy).
- The mode, [Autopilot or Ask me first](/docs/app/autopilot/), which you can switch here.

To pause, say "pause it" in the [project chat](/docs/app/chat/) or press **Pause** on a piece (below). It stops at a safe point; **Try again** or "go on" continues from there.

## What happened

One entry per step, in order, with its time: the files it found or read, the minutes of speech it transcribed (or "from an earlier transcript"), which AI it asked and the tokens it used, how many clips are past the step, and each decision it made ("AI decided: …", "Decided by the rules: …").

## How it is being made

The pieces appear as soon as they exist: graded segments, contact sheets, the master, cover options, drawn scenes, the voice. When the project is done the panel is called **How it was made**. Click a piece to open it big, then:

- **Ask AI about this**: starts a chat message about that piece ("About 'Contact sheet 2': …").
- **Pause**: stops the run at a safe point.
- **Show in Finder**.

## Live

The **Live** pane is a terminal-style view of the real output: the Claude Code or Codex stream (its thinking, tool calls and replies) and the engine's log, line by line.

- **Show**: **All**, **AI** or **Engine**.
- **Search the log** (with previous / next match), **Copy the log**.
- **Dock below** or **Dock beside**, resize it, or hide it.
- Scrolled up? **Jump to live** returns to the newest line.

API keys, tokens and passwords are removed from the log before it is shown or saved.

## Watch all

**Watch all** (on Home's Running list, or **Watch all running** on a run page) tiles every running job on one screen, each with its sentence, progress and live log. **Back to the page** returns.

## Related

- [Project chat and clip chat](/docs/app/chat/)
- [Autopilot and Ask me first](/docs/app/autopilot/)
- [All projects](/docs/app/all-projects/)
- [Troubleshooting](/docs/help/troubleshooting/)
