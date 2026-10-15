# AI providers: API keys, self-hosted models, or no key at all

Every AI step of video-studio goes through one of three small registries, so each step can run on

- **any API provider** (Anthropic, OpenAI, OpenRouter, Gemini, ElevenLabs, DeepSeek, Qwen, Kimi, GLM, Doubao),
- **self-hosted / local models** (Ollama, LM Studio, vLLM, llama.cpp server, local whisper, a whisper or TTS
  server on your own GPU box), or
- **no API key**, through a locally installed agent CLI that is already logged in with your own subscription
  (Claude Code, Codex), or any coding agent that speaks the Agent Client Protocol (Gemini CLI, Cursor CLI,
  GitHub Copilot CLI, OpenCode, Qwen Code, Kimi CLI, CodeBuddy, iFlow CLI; section 2a).

| registry | module | used by |
|---|---|---|
| text LLM | `vstudio.llm.complete()` | segment planning (`plan-segments`), caption proofreading, the per-source glossary, the claude planner (sync mode) |
| speech recognition | `vstudio.asr.transcribe(backend=...)` | every transcript (talkinghead, batch, longform, call-clips, explainer, photo-story) |
| speech synthesis | `vstudio.tts.synth(engine=...)` | explainer narration, pronunciation drills, photo-story voice |

See what works on this machine (keys present, CLIs installed, local servers reachable; nothing is sent):

```bash
cd $VSTUDIO/lib
python3 -m vstudio.llm providers            # LLM + ASR + TTS tables and the current route of each task
python3 -m vstudio.llm providers --json
python3 -m vstudio.llm route                # task -> provider / model / where that came from
python3 -m vstudio.llm test --provider ollama --model llama3.2:1b    # one tiny JSON round-trip, no secrets printed
```

Every step also works with **no model at all** (`none`): the rule-based planner, term fixes + glossary-free
proofreading, local whisper and local / free TTS engines.

## 1. Choosing the provider (routing)

Put an `llm:` section in `persona.local.yaml` (yours, gitignored) or in a client's `client.yaml`
(`python -m vstudio.batch client update --client acme --set '{"llm": {...}}'`):

```yaml
llm:
  default: {provider: claude-code}              # string shorthand works too: default: claude-code
  tasks:                                        # segment_plan | proofread | glossary | copy | script | planner | intake | output_edit
    segment_plan: {provider: anthropic, model: claude-opus-5-5, effort: medium}
    proofread:    {provider: ollama, model: "qwen3:8b"}
    glossary:     {provider: openai-compatible, base_url: "http://gpu-box:8000/v1", api_key_env: GPU_BOX_KEY,
                   model: Qwen/Qwen3-32B}
    copy:         {provider: deepseek}
  prices: {"Qwen/Qwen3-32B": [0, 0]}            # USD per million tokens (input, output); overrides the table
```

Keys never go into these files: name the environment variable (`api_key_env`); `client.yaml` rejects
`api_key` / `token` fields.

Precedence (first match wins):

1. an explicit provider / model (`--provider ollama`, spec `proofread.provider: kimi`, `complete(provider=...)`);
   `auto` means "not given"
2. env `VSTUDIO_LLM_<TASK>_PROVIDER` / `VSTUDIO_LLM_<TASK>_MODEL` (e.g. `VSTUDIO_LLM_PROOFREAD_PROVIDER=ollama`;
   `VSTUDIO_LLM_<TASK>_FALLBACK=codex,ollama` gives it a fallback chain). 1 and 2 are a step's own override
2b. the project's AI: `ai: {provider, model}` in the `project.yaml` of env `VSTUDIO_PROJECT_DIR` (every
   `python -m vstudio.project ... --dir P` sets it; re-read on every call, so a switch mid-run applies from the next
   AI step), else env `VSTUDIO_LLM_PROJECT_AI` (JSON, a request not yet a project). It covers every task; its
   fallback is the global order (the default provider, then its fallback) without itself; no model -> the routes
   file's `models.<provider>`. Show / switch: `python -m vstudio.project model --dir P [--provider X [--model M] |
   --clear]` (recorded in `state/autopilot.jsonl` as `event: ai`)
3. the desk's routes file `tasks.<task>` (env `VSTUDIO_LLM_ROUTES_FILE`, JSON `{default, tasks}`, re-read on every
   call), then the client's `llm.tasks.<task>`, then the persona's `llm.tasks.<task>`
4. env `VSTUDIO_LLM_PROVIDER` / `VSTUDIO_LLM_MODEL` (+ `VSTUDIO_LLM_FALLBACK`)
5. the desk's routes file `default`, then the client's `llm.default`, then the persona's `llm.default`
6. legacy `auto`: `anthropic` when `ANTHROPIC_API_KEY` is set, else `none`. Nothing paid, remote or
   subscription-backed is ever picked implicitly beyond that.

When a provider is named explicitly and the config has an entry for the same provider, that entry's model and
options are used. The glossary follows task `glossary` (falls back to the proofread provider when the spec names
one); the batch spec key `proofread.glossary_provider` overrides it.

## 2. LLM providers

| provider | kind | setup | default model | JSON |
|---|---|---|---|---|
| `anthropic` (alias `claude`) | API | `pip install anthropic`, `ANTHROPIC_API_KEY` | `claude-opus-5-5` | `output_config.format` for a schema, else instruction |
| `openai` | API | `pip install openai`, `OPENAI_API_KEY` | `gpt-4.1-mini` (plan-segments: `gpt-4.1`) | `response_format` json_object / json_schema |
| `openrouter` | API | `OPENROUTER_API_KEY` | `openai/gpt-4.1-mini` | json_object |
| `deepseek` | API | `DEEPSEEK_API_KEY` | `deepseek-chat` | json_object |
| `qwen` (alias `dashscope`, `bailian`) | API | `DASHSCOPE_API_KEY` (Bailian / DashScope compatible mode) | `qwen-plus` | json_object |
| `kimi` (alias `moonshot`) | API | `MOONSHOT_API_KEY` | `kimi-k2-0905-preview` | json_object |
| `glm` (alias `zhipu`, `zai`) | API | `ZHIPUAI_API_KEY` (a Z.ai key with `region: intl`) | `glm-4.6` | json_object |
| `doubao` (alias `ark`, `volcengine`, `byteplus`) | API | `ARK_API_KEY` (Volcengine Ark; BytePlus ModelArk with `region: intl`) | `doubao-seed-1-6-250615` | json_object |
| `gemini` (optional) | API | `pip install google-genai`, `GEMINI_API_KEY` or `GOOGLE_API_KEY` | `gemini-2.5-flash` | `response_mime_type` |
| `ollama` | local | `ollama serve`; `ollama pull qwen3:8b` | `qwen3:8b` | json_object |
| `lmstudio` | local | LM Studio > Developer > Start server | (set `model`) | json_schema |
| `vllm` | local | `vllm serve <model>` (port 8000) | (set `model`) | json_object |
| `llamacpp` | local | `llama-server -m model.gguf` (port 8080) | (set `model`) | json_object |
| `openai-compatible` | any | `base_url` + optional `api_key_env` (or env `VSTUDIO_LLM_BASE_URL`, `VSTUDIO_LLM_API_KEY_ENV`) | (set `model`) | json_object |
| `claude-code` | subscription CLI | Claude Code installed and logged in (`claude`, then `/login`) | the CLI's default (`model: opus` / `sonnet` to pin) | `--json-schema` for a schema |
| `codex` | subscription CLI | Codex CLI installed and logged in with ChatGPT (`codex login`) | the CLI's default | `--output-schema` for a schema |
| `gemini-cli`, `cursor-agent`, `copilot`, `opencode`, `claude-acp`, `codex-acp`, `qwen-code`, `kimi-cli`, `codebuddy`, `iflow` | ACP agent | the agent installed and signed in (section 2a) | the agent's default (`model:` = an id it lists) | instruction + tolerant parse |
| `none` | - | nothing | - | callers use their rule-based path |

Mainland China and international endpoints: Qwen, Kimi, GLM and Doubao have one of each (a key works on the
endpoint of the site it came from). Pick one with the route option `region: cn | intl`, env
`VSTUDIO_<PRESET>_REGION`, persona `llm.regions: {qwen: intl}`, or Settings › AI › API keys in the desk (written to
the routes file as `regions`); default `cn`.

| preset | `cn` (default) | `intl` | get a key |
|---|---|---|---|
| `qwen` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` | bailian.console.aliyun.com / Model Studio (Alibaba Cloud international) |
| `kimi` | `https://api.moonshot.cn/v1` | `https://api.moonshot.ai/v1` | platform.moonshot.cn / platform.moonshot.ai |
| `glm` | `https://open.bigmodel.cn/api/paas/v4` | `https://api.z.ai/api/paas/v4` | open.bigmodel.cn / z.ai |
| `doubao` | `https://ark.cn-beijing.volces.com/api/v3` | `https://ark.ap-southeast.bytepluses.com/api/v3` | console.volcengine.com/ark / console.byteplus.com/ark |
| `deepseek` | `https://api.deepseek.com/v1` (one endpoint) | | platform.deepseek.com |

Model lists: with a key set, `python -m vstudio.llm models --provider qwen` asks the endpoint's own `/models`;
without one it shows a short maintained list (Qwen `qwen-plus`, `qwen3-max`, `qwen-flash`, `qwen-turbo`,
`qwen3-coder-plus`; Kimi `kimi-k2-0905-preview`, `kimi-k2-turbo-preview`, `kimi-k2-thinking`; GLM `glm-4.6`,
`glm-4.5`, `glm-4.5-air`, `glm-4.5-flash`; Doubao `doubao-seed-1-6-250615`, `doubao-seed-1-6-flash-250828`,
`doubao-seed-1-6-thinking-250715`, `doubao-1-5-pro-32k-250115`; DeepSeek `deepseek-chat`, `deepseek-reasoner`).
An Ark endpoint id (`ep-...`) works as the Doubao model too.

Other preset base URLs (override with `base_url:` or env `VSTUDIO_<PRESET>_BASE_URL`): OpenRouter
`https://openrouter.ai/api/v1`, Ollama
`http://localhost:11434/v1`, LM Studio `http://localhost:1234/v1`, vLLM `http://localhost:8000/v1`, llama.cpp
`http://localhost:8080/v1`. The default models of the presets are examples - providers rename models often; set
`model:` to what your account / server actually has (`python -m vstudio.llm providers` lists the models a local
server reports).

Notes per backend:

- **anthropic**: thinking is adaptive by default on Claude Opus 5.5 (no `budget_tokens` is ever sent; no
  assistant prefill). `effort` goes to `output_config.effort` (proofread uses `low`, the planner `medium`).
  The server-side refusal fallback (beta) is used when the installed SDK supports it; a refusal raises.
  The claude planner's **Message Batches** mode (`plan --planner claude` without `--sync`) is an Anthropic-only
  API and stays Anthropic-only; `--sync` goes through `vstudio.llm`.
- **openai / compatible**: Chat Completions. Reasoning models (`o*`, `gpt-5*`) get `max_completion_tokens` and no
  temperature. Small local models follow JSON instructions less reliably: the tolerant parser and the one repair
  retry catch most slips; the callers' own validators (proofread's audio-faithful check, plan-segments' range
  checks) reject the rest. 7-8B models are fine for `copy`; prefer 14B+ (or an API model) for `proofread`.
- **claude-code**: runs `claude -p --output-format json --tools "" --no-session-persistence --strict-mcp-config
  --system-prompt <system>` with the prompt on stdin, in an empty temp directory, with a timeout. No tools are
  available to it, nothing is written to your project, and `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` /
  `ANTHROPIC_BASE_URL` are removed from its environment so it uses your own login (set `inherit_env: true` in the
  route to keep them). Errors such as an expired login are reported as-is: run `claude` and `/login` again.
- **codex**: runs `codex exec --json --sandbox read-only --skip-git-repo-check --cd <temp dir>
  --output-last-message <file> [--model M] [--output-schema F] -` (system + prompt on stdin), with
  `OPENAI_API_KEY` removed from its environment so it uses your ChatGPT login. The flags follow the Codex CLI's
  documented `exec` options; check `codex exec --help` on your machine if the CLI changed.
- **ACP agents**: see section 2a.
- Retries: rate limits, overload, 5xx and connection errors are retried twice with backoff; bad requests, auth
  errors, refusals and CLI timeouts are not. A broken JSON reply gets one repair round (the model sees its own
  reply and is asked for valid JSON); after that the caller gets `json=None` and falls back (proofread: glossary /
  term fixes only for that chunk; plan-segments: rule-based fill).

### Fallback chains

A route entry may name `fallback: [codex, ollama]`: when the routed provider fails (login expired, CLI missing,
outage), the next one runs. The result records it - `fallback_from` (the error texts) and
`fallback: {from, to, code, error, tried}` with `code` one of `auth-expired | not-logged-in | not-installed |
key-missing | rate-limited | timeout | model-unsupported | failed` - and `output ai` / the intake planner pass it on (`routed`,
`fallback`, `provider_fallback`), so an app can say "Claude's login expired, Codex answered this time". An explicit
provider (`--provider`) never falls back.

A fallback entry may carry its own model: `fallback: [{provider: codex, model: gpt-6-luna}]`.

### Choosing the model

Every route entry takes `model:` (passed as `claude --model <id>` / `codex exec --model <id>` / the API's model).
Without one, the CLIs use their own default (Claude Code's, or `model` in `~/.codex/config.toml`).

```bash
python3 -m vstudio.llm models --json                           # the models each provider can use here
python3 -m vstudio.llm models --provider claude-code --resolve 5.5   # her words -> claude-opus-5-5
```

- **claude-code / anthropic**: the CLI has no "list models" command, so this is a maintained list of the current
  Claude models (`vstudio.llm_models.CLAUDE_MODELS`: Opus 5.5, Sonnet 5.5, Haiku 5.5, Fable 5.1, plus older ones);
  with an Anthropic key the API's own list is added.
- **codex**: `codex debug models`, the catalog of the models *your login* can use. A ChatGPT login cannot use every
  API model: when `~/.codex/config.toml` names one it cannot use, `models` reports `problem.code =
  codex-model-unsupported` with the fix, and a call that hits it fails with code `model-unsupported` and says so
  plainly ("the model 'gpt-6-astra' is not available for your ChatGPT login. Fix: pick a Codex model in Settings > AI,
  or change `model` in ~/.codex/config.toml").
- **API providers**: the provider's `/models` when its key is set, else a short maintained list.
- `--resolve` matches like the app's `/model`: "5.5" -> Opus 5.5 (opus before sonnet, haiku, fable), "sonnet" -> the
  newest Sonnet, "default" -> no model (the CLI's own).

The desk app writes the choice into its routes file: the model picked for a provider applies to every job using
that provider (and to that provider as a fallback); a job may still have its own.

### Login status and login commands

```bash
python3 -m vstudio.llm auth status --json         # every provider: state, account (email / plan), key present?, server up?
python3 -m vstudio.llm auth status --no-probe     # skip the tiny claude round-trip (faster, but cannot see expiry)
python3 -m vstudio.llm auth status --deep         # also a tiny codex round-trip
python3 -m vstudio.llm auth login --provider claude-code --json    # the command to run yourself (nothing is run)
python3 -m vstudio.llm auth logout --provider codex --json
```

States: `logged-in`, `expired`, `not-logged-in`, `not-installed` (CLIs); `configured`, `not-configured` (API keys:
only whether the variable is set, never its value); `ready`, `server-down`, `no-models` (local servers). Each row has
a `message` `{code, params, message, message_zh}`. claude-code is checked with `claude auth status --json` (plan,
email, auth method) **and** a one-line `claude -p` on the cheapest model, because `auth status` still says
`loggedIn: true` after the OAuth token expired (the round-trip then answers 401). codex uses `codex login status`.
Every CLI call (status, probe, the real work) runs with `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` /
`ANTHROPIC_BASE_URL` (claude) or `OPENAI_*` / `CODEX_API_KEY` (codex) removed from its environment. The CLIs are
found on `PATH`, then in `~/.local/bin`, `~/.claude/local`, `/opt/homebrew/bin`, `/usr/local/bin`, ... (env
`VSTUDIO_CLI_EXTRA_DIRS` replaces that list). `auth login` prints `claude auth login` / `codex login` (variants:
`--console`, `--sso`, `--device-auth`) and the variables to remove; the engine never sees a password or token.

### Subscription CLIs: your own local use

`claude-code` and `codex` reuse the plan you are logged into. They are meant for **your own local use** of this
tool. Subscription plans come with their own usage limits and terms; before using a subscription CLI to produce
paid work for clients (an agency pipeline, `deliver` packages, many batch jobs), check the provider's current
consumer / subscription terms and usage policies, and use an API key (or a self-hosted model) where the terms call
for it. `python -m vstudio.llm providers` never sends anything through them; `test` sends one tiny prompt.


## 2a. Coding agents over the Agent Client Protocol (ACP)

`vstudio.acp` is one client for every agent that speaks [ACP](https://agentclientprotocol.com) (JSON-RPC 2.0 over the
agent's stdin / stdout): `initialize` -> `session/new` in an empty temp folder with no MCP servers -> the model, if one
is asked for (`session/set_config_option`, or the older `session/set_model`) -> `session/prompt`; the reply is the
agent's streamed message. The client offers no file system and no terminal, and refuses every tool permission the
agent asks for. It runs **your own installed, unmodified program with its own sign-in**: Reelfold never reads a
credential, and the Anthropic / OpenAI variables the desk or engine may carry are removed from the agent's
environment (route option `inherit_env: true` keeps them; `cli:` names the program; `acp_args:` replaces the
arguments that start ACP mode).

| provider | agent | maker | started as | sign in | works in mainland China | install |
|---|---|---|---|---|---|---|
| `gemini-cli` | Gemini CLI | Google | `gemini --acp` (older: `--experimental-acp`) | Google account, on first run | no (needs access outside China) | `npm install -g @google/gemini-cli` |
| `cursor-agent` (alias `cursor`) | Cursor CLI | Cursor | `cursor-agent acp` | `cursor-agent login` | partly (some models are not offered in China) | `curl https://cursor.com/install -fsS \| bash` |
| `copilot` | GitHub Copilot CLI | GitHub | `copilot --acp` | `copilot login` (GitHub account with Copilot) | partly | `npm install -g @github/copilot` |
| `opencode` | OpenCode | SST | `opencode acp` | `opencode auth login` (any provider: DeepSeek, Kimi, GLM, Qwen keys work in China) | yes, with a China provider | `npm install -g opencode-ai` |
| `claude-acp` | Claude Code via its ACP adapter | Anthropic | `claude-agent-acp` (takes your `claude` as `CLAUDE_CODE_EXECUTABLE`) | your Claude Code sign-in | no | `npm install -g @agentclientprotocol/claude-agent-acp` |
| `codex-acp` | Codex via its ACP adapter | OpenAI | `codex-acp` (takes your `codex` as `CODEX_PATH`) | your Codex sign-in | no | `npm install -g @zed-industries/codex-acp` |
| `qwen-code` | Qwen Code | Alibaba | `qwen --acp` (older: `--experimental-acp`) | Qwen OAuth (qwen.ai, free daily quota) or a Bailian key, on first run | yes | `npm install -g @qwen-code/qwen-code@latest` |
| `kimi-cli` | Kimi CLI | Moonshot AI | `kimi acp` | `kimi login` | yes | `uv tool install kimi-cli` |
| `codebuddy` | CodeBuddy | Tencent | `codebuddy --acp` | CodeBuddy account (codebuddy.cn or codebuddy.ai), on first run | yes | `npm install -g @tencent-ai/codebuddy-code` |
| `iflow` | iFlow CLI | Alibaba iFlow | `iflow --experimental-acp` | iFlow account, on first run | yes | `npm install -g @iflow-ai/iflow-cli` |

```bash
python3 -m vstudio.llm auth status --provider qwen-code --json   # installed? signed in? its models (opens a session, no prompt)
python3 -m vstudio.llm auth login --provider kimi-cli --json     # the command to sign in (the desk runs it in its terminal)
python3 -m vstudio.llm models --provider qwen-code --json        # the models the agent offers this sign-in
python3 -m vstudio.llm test --provider qwen-code                 # one tiny JSON round-trip
```

Routing and fallbacks work as for every other provider, e.g. Claude Code first, then Qwen Code, then a DeepSeek key:

```yaml
llm:
  default: {provider: claude-code, fallback: [qwen-code, deepseek]}
  regions: {qwen: intl}                         # a Qwen key from Alibaba Cloud international
```

Failures come back as codes the desk words plainly: `not-installed`, `not-logged-in` (the agent's `auth_required`),
`region-blocked` ("not available in your region", "User location is not supported"), `model-unsupported` (an id the
agent does not list), `timeout`. An agent counts as a subscription CLI for the desk's Mac App Store build: like
Claude Code and Codex it is not available there (`VSTUDIO_LLM_NO_CLI=1`). Pictures (`images=`) go in as ACP image
blocks when the agent says it takes them.

## 3. Speech recognition (ASR)

| backend | kind | setup |
|---|---|---|
| `mlx` | local (Apple Silicon) | `pip install mlx-whisper` (model `VSTUDIO_WHISPER_MLX`, default whisper-large-v3-turbo) |
| `faster` | local (any OS) | `pip install faster-whisper` (model `VSTUDIO_WHISPER_FW`) |
| `openai` | API | `OPENAI_API_KEY` (whisper-1, about $0.006 / min) |
| `openai-compatible` | self-hosted | a `/v1/audio/transcriptions` server: `VSTUDIO_ASR_BASE_URL` (or persona `asr.base_url`), optional `asr.api_key_env`, `asr.model` |

`auto` = persona `asr.backend` / env `VSTUDIO_ASR_BACKEND`, else mlx -> faster -> openai (a server is only used
when named). Self-hosted servers that speak this API: faster-whisper-server / speaches (port 8000, model e.g.
`Systran/faster-whisper-large-v3`), whisper.cpp `whisper-server --inference-path /v1/audio/transcriptions`,
LocalAI. Word timestamps come from the server when it returns them (`verbose_json` + word granularity); a server
that returns only segments gets evenly spread words per segment (marked `approx_words`; cuts on those are less
exact - prefer local mlx / faster for tight edits). Results are cached per backend (+ server URL).

FunASR / SenseVoice (strong for Chinese) are not built in: the FunASR toolkit is MIT, but the SenseVoice /
Paraformer model weights ship under the FunASR model license, not Apache / MIT. If you run them yourself behind an
OpenAI-compatible transcription server, use the `openai-compatible` backend.

## 4. Speech synthesis (TTS)

| engine | kind | setup |
|---|---|---|
| `openai` | API | `OPENAI_API_KEY`; `gpt-4o-mini-tts` with per-line `instructions` (delivery direction) |
| `kokoro` | local (Apple Silicon), offline | `pip install mlx-audio "misaki[en,zh]"`; model `VSTUDIO_KOKORO_MODEL` (a local folder) or the HF repo `mlx-community/Kokoro-82M-bf16`. Bundled in the Mac app (Apple silicon) |
| `qwen` | local (Apple Silicon), offline | the free Chinese voice: Qwen3-TTS 1.7B CustomVoice (Apache-2.0) via `mlx-audio`; model `VSTUDIO_QWEN_TTS_MODEL` (a local folder) or the HF repo `mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit`; voices `serena` (default), `vivian`, `uncle_fu`, `dylan` (Beijing), `eric` (Sichuan). In the Mac app: the optional download `tts-qwen-zh` (~3 GB, Settings > Voice) |
| `edge` | online, no key, opt-in | `pip install edge-tts` (Microsoft's Edge read-aloud voices; unofficial, not a public API, has been down for days at a time; LGPL, not in the app) |
| `clone` | local (Apple Silicon) | `mlx-audio` + persona `tts.clone.ref_wav` / `ref_text` (your own voice only) |
| `openai-compatible` | self-hosted | a `/v1/audio/speech` server (Kokoro-FastAPI on port 8880, openedai-speech, LocalAI): `VSTUDIO_TTS_BASE_URL` or persona `tts.server.{base_url, api_key_env, model, voice}` |
| `elevenlabs` | API (optional) | `ELEVENLABS_API_KEY`; voice = a voice id (persona `tts.elevenlabs_voice`), model `eleven_multilingual_v2`, speed 0.7-1.2 |

`auto` = persona `tts.engine` / env `VSTUDIO_TTS_ENGINE`, else kokoro (Apple Silicon) -> edge -> openai. The
explainer's default (`tts_engine: auto`, `tts.available_engine()`) is the voice this machine has: persona
`tts.engine`, else OpenAI only when `OPENAI_API_KEY` is set, else the free voice installed (kokoro -> edge) - never
a paid engine without its key. A plan that chose OpenAI without a key: autopilot takes the free voice and records it
("used the free local voice — no OpenAI key"); Ask-me-first asks (use the free voice / add the key); with no free
voice installed either (the app on an Intel Mac or Windows: no free voice is bundled there), adding the key is the way.
A paid engine without its key raises `tts.MissingKey` (the service and the fix, in plain words). The
explainer narration takes `--engine`; drills take `--engine`. Takes are cached by engine + model (+ server URL) +
voice + speed + direction + text.

Chinese narration (中文讲解): the free voice says Chinese lines with `qwen` (`tts.zh_engine("kokoro")`) once it is
on this machine (`tts.qwen_ready()`; env `VSTUDIO_QWEN_TTS=off` switches it off): natural tones and polyphones (行长,
重新, 划船), English terms (MCP, Tool Calling, Space Needle) read as English, about 1x real time on an M-series Mac. A/B
(2026-10, six lines, Whisper round trip): Kokoro v1.0 zf_xiaobei CER 3.3%, Kokoro v1.1-zh 0.8-2.5% (same tone slips,
划 read as 画), Qwen3-TTS 1.7B serena 1.2%, MeloTTS 15.6%. Without it, Kokoro's Mandarin voices (`zf_xiaobei`, `zm_yunjian`, ...; the voice prefix is passed
as Kokoro's `lang_code`, `pip install "misaki[zh]"`) read Chinese only - English terms inside a Chinese sentence
(MCP, JSON-RPC) come out garbled. For a course full of English terms use `clone` (Qwen3-TTS reads both). Without a
recording of your own voice, a free local reference works: a 10-15 s Kokoro `zf_xiaobei` sample of plain Chinese
sentences as `tts.clone.ref_wav` + its text as `ref_text` (a synthetic voice, no real person's). Measured on an M5
Mac: about 3.3 x real time (a 6-minute narration in 20 minutes), sentence check by ASR included.

**The free voice in the desktop app (Apple silicon).** The app's runtime bundles Kokoro (mlx-audio + misaki, MIT /
Apache-2.0); the weights (Kokoro-82M v1.0, Apache-2.0, ~330 MB with the voices `zf_xiaobei`, `af_heart`,
`am_michael`, `bf_emma`) are not in the installer: they are the optional first-run download `tts-kokoro`
(`apps/desk/packaging/assets.json`: pinned Hugging Face revision, sha256 per file, resumable, Settings > Downloads),
fetched the first time a video takes the free voice. The app passes the folder as `VSTUDIO_KOKORO_MODEL` and sets
`VSTUDIO_TTS_MODELS_MANAGED=1`, so the engine never fetches a model itself (Mac App Store sandbox: everything stays in
the app's container, no `network.server`); before the download the voice step stops with `tts.VoiceNotDownloaded`
(failure code `tool-voice`) and the app offers the download. Takes run through `vstudio.kokoro_synth` (mlx-audio's
Python API, offline for a local folder). English without espeak-ng: misaki's GPL fallback (espeakng-loader /
phonemizer) is not bundled, so a word missing from misaki's English dictionaries (~180k words) is skipped instead of
guessed - spell out rare names or acronyms in the script; numbers are read through `vstudio.numwords_en` (the app
ships no LGPL num2words; same words). Intel Macs and Windows bundle no free voice (MLX is Apple-silicon only, and
kokoro-onnx's default phonemizer is espeak-ng, GPL): they keep the key path (OpenAI / ElevenLabs / your own
`openai-compatible` server, e.g. Kokoro-FastAPI).

The AI presenter (a talking head from your photo + the narration) is a paid video service, not TTS: Hedra, key
`HEDRA_API_KEY` (desk: Settings > Video generation > Hedra), behind the Create spend gate -
`python -m vstudio.create presenter estimate|run` (references/CREATE.md).

## 5. What each step sends

| step | task / registry | sent to the provider | not sent |
|---|---|---|---|
| plan-segments | `segment_plan` | the whole transcript as numbered sentences with times (chunks of ~150k chars), platform title rules, the client's style text and preferred tags | audio, video, file paths |
| intake plan / revise | `intake` | the request, the material summary (file names, durations, roles, short excerpts, document headings), the recipe catalog; when the request selects content from a recording, its time-coded transcript (up to 60k chars) | audio, video, full documents |
| output edit `ai` | `output_edit` | the instruction, the output's duration / canvas / mode / capability flags, the current edit state (trim, cuts, effect instances), the op list and the effect catalogue, the caption cues or a time-coded transcript of the output (up to 400 lines) | audio, video, file paths of the media |
| glossary | `glossary` | the whole transcript text of one source, the series / topic, the creator's term list; then the latin tokens with short contexts; then each proposed fix with up to 5 contexts | audio, video |
| proofread | `proofread` | the captions of one job (chunks of 120 cues), a second ASR hearing of the same span, low-confidence words, topic / title / chapter / notes, the glossary | audio, video |
| claude planner | `planner` (Anthropic) | the transcript in ~15 min chunks with times | audio, video |
| ASR `openai` / `openai-compatible` | asr | the audio track (mono 16 kHz, 32 kbps mp3), language, the ASR prompt (term list) | video |
| TTS `openai` / `elevenlabs` / `edge` / server | tts | the narration text, voice, speed, delivery direction | anything else |
| `clone` TTS, `mlx` / `faster` ASR, local LLM servers on localhost | - | nothing leaves the machine | |

Transcripts can hold names and private details of the people recorded: for client work prefer a local or
self-hosted model, or a provider whose data terms (retention, training use, region) your client accepts.

## 6. Cost

API calls are costed from `vstudio.llm.PRICES` (USD per million tokens; persona `llm.prices`, a call's `prices=`,
or the batch spec `prices.proofread_in / proofread_out` override it; unknown API models are estimated at 2.5 / 10
and flagged `cost_estimated`). Local servers and subscription CLIs are booked at 0 (the CLI's own notional figure
is kept in `usage.notional_cost_usd`). Whisper API minutes use `prices.openai_whisper_min`.

### macOS system Chinese narration

Settings → Voice → Chinese narration uses → macOS system voices selects an installed Chinese voice for new narration. The preference is shared by intake planning, second edits, photo stories and explainers; it is not a prompt instruction. Read the installed list with `vstudio.system_voice.chinese_voices()`; refresh after installing more voices in macOS Accessibility → Read & Speak. Only voices returned by `/usr/bin/say -v ?` are offered, including installed Premium voices. No automatic voice downloads or system preference changes. Siri voices not exposed by macOS for file synthesis are not promised.

`tts.synth(text, engine="system", voice=<installed name>)` exports through macOS, then uses the shared 48 kHz mono WAV/cache pipeline. The chosen voice is recorded in `VSTUDIO_TTS_PREFS` (`zh_engine: system`, `system_voice`). No API key or extra model is needed. An unavailable chosen voice fails explicitly instead of switching language or silently choosing a different speaker. Existing rendered audio remains unchanged.
