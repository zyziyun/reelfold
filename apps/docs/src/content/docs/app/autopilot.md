---
title: Autopilot and Ask me first
description: "How Reelfold's Autopilot plans, decides and finishes projects on its own, how Ask me first brings back the plan and the pilot, and how to see and change every decision."
---

Reelfold can work two ways. **Autopilot** (the default) takes your request to finished clips on its own and writes down every choice it made. **Ask me first** shows you the plan and one pilot clip before the rest is made, and asks you each question.

## Autopilot

When you press **Make it** on Home, the request becomes a project and runs:

1. The AI plans it: which recipe, how many clips, which platforms.
2. It runs every step. Where a person would normally decide (which unsure filler words to cut, which opening, which cover, which music, how vertical versions are framed, which post copy), the AI decides with its reasons, using the same rules you would see in the Inbox.
3. When the checks pass, the clips are approved and ready to post.

Only real blockers reach your Inbox: something only you can give (a missing file, a script you must write), paid AI work over your spend cap (0 unless you raise it), consent from a guest in the frame, or a step that stopped. Spending over the cap and consent are never answered for you.

Up to two projects run at the same time; the rest wait their turn ("Waiting for a free slot · #2 in line") and keep their place across a restart.

## Ask me first

With **Ask me first**:

- Home's button reads **Make a plan**. The plan shows what it will make, for which platforms, how long it takes and what it may cost. Change it in plain words ("only 3 clips", "no 9:16"), press **Update**, then **Start — make 1 to preview**.
- One clip is made first so you can check the look before the rest.
- Each decision waits for you in the Inbox, with the suggested answer ready.

## Switch between them

- **For new projects**: Settings › General › **New projects**: **Autopilot** or **Ask me first**.
- **For one project**: on its page, the line under the title says which mode it is in; switch it there. The next run follows it.

## What the AI decided

Every project page has **What the AI decided**: one line per decision, who made it (**AI** with the provider's name, or **Rules** when no model was used) and why. For example: "Cut 6 unsure filler words, kept 2", "Cover: frame 3", "Music: …", "Vertical versions follow the subject", "Post copy written by the AI".

### Change a decision

Press **Change** on any line. The question goes back to your Inbox with every option; answer it there, and only what depends on it is made again (the cover, the vertical versions, the cut). Everything else is kept. A project that is still running can be changed once it has finished.

## With the Claude Code skill or a terminal

```bash
python -m vstudio.project run --dir <project> --autopilot      # no pilot stop; decisions recorded in project.yaml
python -m vstudio.project run --dir <project> --ask-first      # turn autopilot off again for this project
python -m vstudio.project decisions --dir <project> [--history]  # what it decided, by whom, why
python -m vstudio.project reopen --dir <project> --id cover-pick [--item <item>]   # take one decision back
python -m vstudio.project autopilot --dir <project> --on|--off [--spend-cap N]
```

`--spend-cap N` lets autopilot approve paid steps up to N credits (default 0: every spend asks you). `--no-judge` decides by the rules only, with no model call; `--lang en|zh|fr` sets the language of its reasons. A `reopen`ed decision waits for you on the next run. Full flags: [CLI reference](/docs/reference/cli/).

## Related

- [Home](/docs/app/home/)
- [Batch and review](/docs/concepts/batch-review/)
- [Projects](/docs/concepts/projects/)
- [The live run page](/docs/app/live-run/)
