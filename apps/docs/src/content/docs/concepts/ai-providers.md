---
title: AI providers
description: Bring your own AI to Reelfold, from your Claude Code or Codex login, an API key, or a local model. Route each task, set fallbacks and see what each step costs.
---

Reelfold doesn't come with its own AI. It uses one you already have: your logged-in Claude Code or Codex CLI, an API key from a provider you choose, or a model running on your own machine. You can pick a different one for each task.

## Why it matters

You stay in control of cost, quality and where your text goes. A subscription you already pay for can do the planning at no extra cost. A local model keeps everything on your Mac. And when one provider is down or your login expires, a fallback can take over and you are told which one answered.

## Which steps use AI

| Step | What the AI does |
|---|---|
| Intake | Turns your request and files into a plan |
| Segment planning | Picks the segments of a long recording, with titles and hooks |
| Caption proofreading and glossary | Fixes names and terms the speech recognizer got wrong |
| Post copy and scripts | Writes titles, post text and scripts |
| Output edits and chat | Turns a plain-language edit into edit steps; runs the project and clip chat |
| Autopilot decisions | Judges the unsure choices (filler cuts, opening, cover, music) and gives its reason |
| Explainer scenes | Drafts the script from your notes and draws each scene as a diagram or animation |

Speech recognition and voice are separate: transcription runs locally by default (whisper on Apple Silicon), and narration can use the free local voice, your cloned voice, or a hosted one (see [Voices](/docs/guides/voices/)). Most text steps also work with no model at all, through a rule-based path. Drawing an explainer's scenes is the exception: it needs a model, and without one the project waits in Needs you instead of making a text-only video.

## Three ways to connect

| Way | Providers | Notes |
|---|---|---|
| CLI login, no API key | Claude Code, Codex | Uses the plan you are logged into. Runs with no tools, in an empty temporary folder; nothing is written to your project |
| API key | Anthropic, OpenAI, DeepSeek, Qwen, Kimi, GLM, OpenRouter, Gemini; ElevenLabs for voice | Keys are referenced by environment variable name, never written into config files |
| Local | Ollama, LM Studio, vLLM, llama.cpp; local whisper; your own whisper or TTS server | Nothing leaves your machine |

:::note[Subscription CLIs are for your own use]
Claude Code and Codex logins come with their own usage limits and terms. Before using one to produce paid client work at volume, check the provider's current terms, and use an API key or a local model where they call for it.
:::

## Routing and fallbacks

Each task (intake, segment planning, proofreading, glossary, copy, script, output edits) can have its own provider, with a default for the rest. Each route can list fallbacks in order: if the first fails, the next is tried. A provider you name explicitly for one run never falls back.

When a fallback runs you see a message rather than a silent switch:

- `llm-fallback`: "Claude Code failed (login expired); Codex answered instead." The job continued.
- `llm-all-failed`: every provider in the chain failed. The step stops and lists them. Where a rule-based path exists (segment planning, intake), it fills in and says so.

Failure reasons include an expired login, not logged in, not installed, a missing key, rate limiting and timeouts.

## Cost

API calls are costed per token and reported with each step. Subscription CLIs and local models count as zero. In an internal test, a 72-minute lecture became 24 clips for 4 platforms (96 files) for $0.73 in API cost, about $0.03 per clip.

## Time limits and effort

- **Time limits.** A CLI model (Claude Code, Codex) gets a time limit per attempt, so an expired login can't hang a step. The clip chat gives it 180 s; a slow answer is better than none. When it runs out, the next provider in the chain is tried and you are told ("Claude Code didn't answer within 120 s, so Codex was used this time"); a CLI that just timed out is skipped for a while. Set your own limit per route (`timeout: 300`) or for every CLI call (`VSTUDIO_LLM_CLI_TIMEOUT=300`).
- **Effort.** Big generations, such as drawing an explainer scene, ask Claude Code for a medium reasoning effort (`--effort medium`): about a minute per scene instead of five. Set `effort:` (`low`, `medium`, `high`) on a route to change it. An older Claude Code without `--effort` is called without it.
- **Model.** Leave the model empty to use the CLI's own default. If you set one for Codex, it must be a model your ChatGPT account can use; a model the account doesn't support fails every call ("didn't answer").

## In the Mac app

Settings › **AI** shows the AI that is working and when it was checked, with **Switch AI…**. From there you sign in to Claude Code or Codex (your browser opens), **Test** a provider, add **API keys** (kept in the system keychain), find **Models on this computer**, **Change order** of the backups, and set **Different AI for specific jobs**. A changed key needs an engine restart; the page offers it. The [Mac App Store edition](/docs/help/editions/) offers API keys and local models only.

## Troubleshooting

| You see | Meaning | Fix |
|---|---|---|
| **No model** / "No AI model connected" | Nothing is connected, or every provider is unavailable | Settings › AI: sign in, add a key or start a local model, then **Test** |
| "The model didn't answer this time" / "Claude Code didn't answer" | A model is connected but did not reply in time, or failed | **Try again** (it gets more time); check the login; add a backup in **Change order** |
| "… login expired, so … was used this time" | The first provider's login expired; a backup answered | Sign in again in Settings › AI |
| "… hit its usage limit" | Your plan's limit was reached; a backup answered | Wait for the limit to reset, or route heavy jobs to an API key or local model |
| Every Codex call fails right away | The Codex model set for the route isn't available to your account | Clear the model, or pick one your account supports |
| "The visuals need an AI model" | An explainer's scenes can't be drawn without a model | Connect one, then **Try again** |

More: [Troubleshooting](/docs/help/troubleshooting/#ai-providers).

## With the Claude Code skill

Put an `llm:` section in your `persona.local.yaml`:

```yaml
llm:
  default: {provider: claude-code, timeout: 300, fallback: [codex, ollama]}
  tasks:
    copy:      {provider: codex}                     # no model: the CLI's own default
    proofread: {provider: ollama, model: "qwen3:8b"}
```

Then check it from the `lib/` folder:

```bash
python3 -m vstudio.llm providers   # what works on this machine; nothing is sent
python3 -m vstudio.llm route       # which provider each task uses, and why
python3 -m vstudio.llm test --provider ollama --model llama3.2:1b   # one tiny round-trip
```

## Related

- [Privacy](/docs/concepts/privacy/)
- [Settings](/docs/app/settings/)
- [Persona reference](/docs/reference/persona/)
- [Providers engine reference](/docs/reference/engine/providers/)
- [Engine messages](/docs/reference/messages/)
