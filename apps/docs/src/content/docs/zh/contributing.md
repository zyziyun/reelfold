---
title: 参与贡献
description: 从源码构建千剪，在本机跑打包版，了解仓库结构，跑测试，添加效果或平台配置，参与翻译，修改这份文档，以及提交 Pull Request 的约定。
---

千剪（Reelfold）以 MIT 协议开源，全部在一个仓库里：根目录是引擎和 Claude Code 技能，`apps/` 下是 Mac 应用、网站和这份文档。修 bug、加效果、补平台配置、做翻译都欢迎。

## 从源码构建

应用需要 Apple Silicon 的 macOS，另外要 Node 22+、Python 3.10+ 和 `ffmpeg`。

```bash
git clone https://github.com/zyziyun/reelfold && cd reelfold
./install.sh && npm install
npm run desk
```

`./install.sh` 会安装 Python 依赖，并把开源授权的字体和 MediaPipe 模型下载到 `~/.cache/video-studio`。`npm install` 一次装好 `apps/` 下所有工作区。`npm run desk` 启动应用，引擎直接用这份代码里的 `lib/`。

### 常用脚本

在仓库根目录：

| 命令 | 作用 |
|---|---|
| `npm run desk`（或 `npm run dev`） | 开发模式的 Mac 应用，引擎用这份代码 |
| `npm run site` / `npm run docs` | reelfold.com / 这份文档，改动实时刷新 |
| `npm run build:web` | 把网站和文档构建到一个文件夹（`apps/site/dist`，文档在 `/docs` 下） |
| `npm run build:docs` | 只构建文档 |
| `npm run test` / `npm run lint` | 应用的测试 / eslint + tsc |
| `npm run check` | `scripts/check_skill.py`，仓库检查 |

在 `apps/desk` 里（在根目录用 `npm run <脚本> -w apps/desk`）：

| 命令 | 作用 |
|---|---|
| `runtime` | 把这台机器用的 Python、ffmpeg 和引擎打包到 `build/runtime/`（约 1 GB；下载会缓存） |
| `build:mac` | 打包出 `dist/mac-arm64/Reelfold.app`，不签名，有打包好的 runtime 就用它 |
| `dist:mac:unsigned` | 不签名的 DMG 和 zip |
| `test:packaged` | 检查打包版：内置引擎能启动、能响应 |
| `mas:local` | Mac App Store 版，用沙盒权限做临时签名，然后测试 |
| `test:e2e` | 先构建，再跑 Playwright 冒烟测试 |

### 在本机跑打包版

没有一步到位的安装脚本。想试试你这份代码的打包版：

```bash
npm ci                                  # 在仓库根目录，只需一次
npm run runtime -w apps/desk            # 打包 Python + ffmpeg + 引擎（第一次，或改了引擎之后）
npm run build:mac -w apps/desk          # -> apps/desk/dist/mac-arm64/Reelfold.app
npm run test:packaged -w apps/desk      # 可选：检查打包版
open apps/desk/dist/mac-arm64/Reelfold.app
```

这个版本没有签名，第一次打开时 macOS 可能要你确认（右键 › 打开）。它和已安装的千剪共用设置和项目，所以打开本地版之前先退出已安装的应用，也不要在它运行时替换 `/Applications/Reelfold.app`。签名、公证和 App Store 版的构建见 `apps/desk/docs/RELEASING.md` 和 `apps/desk/docs/MAS.md`。

## 仓库结构

```
SKILL.md                  路由：什么需求走哪个工作流
workflows/<name>/         WORKFLOW.md 剧本、scripts/、references/、examples/
lib/vstudio/              共用引擎库（media、audio、asr、cut、subs、platform、export、publish 等）
references/               引擎长文档（PLATFORMS、BATCH、EFFECTS、RETOUCH 等）
tests/                    基于合成素材的 pytest
apps/desk/                Mac 应用（Electron）
apps/site/                reelfold.com（Astro）
apps/docs/                这份文档（Astro Starlight）
```

## 跑测试

```bash
python3 -m pytest tests -q          # 引擎测试，只用合成素材
npm run test                        # Mac 应用：vitest + 引擎桥接测试
npm run lint                        # Mac 应用：eslint + tsc
python3 scripts/check_skill.py      # 提交前的仓库检查
```

`check_skill.py` 会检查技能的 frontmatter 和每个 `WORKFLOW.md`，发现剧本里有装饰性 emoji、绝对的个人路径（`/Users/<名字>/`）或者像是提交了密钥的内容就会报错。你的 `persona.local.yaml` 被 git 忽略，个人设置不会进仓库。

## 添加效果

所有效果都登记在一个声明式的注册表 `lib/vstudio/effects.py` 里，`references/EFFECTS.md` 的目录由它生成。从写函数到登记再到检查的步骤，见[添加效果](/docs/zh/reference/engine/adding-effects/)。

## 添加或修正平台配置

1. 在 `lib/vstudio/platform.py` 里改配置：各方向的画布、安全区、字幕区、时长、响度、编码上限、封面尺寸和裁切，以及标题、正文、标签的限制。
2. 在 `references/PLATFORMS.md` 里写明每个值的来源，标上 **[S]** 官方来源、**[3P]** 第三方或 **[C]** 约定值。平台改版很频繁，写清楚你查了什么、什么时候查的。
3. 平台有网页上传页的话，在 `references/PUBLISHING.md` 里加一行。
4. 跑平台相关测试（`tests/test_platform*.py`），用 `python -m vstudio.platform` 打印出来核对。

## 翻译

| 内容 | 位置 |
|---|---|
| 这份文档 | `apps/docs/src/content/docs/<语言>/`（`zh`、`fr`、`es`），英文在根目录。文件名和英文页保持一致。 |
| 网站 | `apps/site/src/i18n/`（`en.ts`、`zh.ts`、`fr.ts`） |
| Mac 应用 | `apps/desk/src/renderer/src/i18n/locales/`（英文是源文本，也是兜底） |
| 引擎提示 | `lib/vstudio/messages.py`，然后运行 `python3 scripts/gen_messages_md.py`（`references/MESSAGES.md` 过期时测试会失败） |

还没翻译的页面会显示英文并附一条提示，所以只翻一部分也没关系。

## 修改这份文档

文档是 `apps/docs` 里的 Astro Starlight 站点。指南、概念和帮助页都是 `apps/docs/src/content/docs/` 下的普通 Markdown。

**参考** 页是从仓库源文件生成的，所以永远和引擎一致：工作流页来自 `workflows/<name>/WORKFLOW.md`，引擎页来自 `references/*.md`，平台页来自 `lib/vstudio/platform.py`，CLI 页来自各模块的 `--help`。要改就改源文件，不要改生成出来的页面，然后重新生成：

```bash
npm run gen -w apps/docs
```

## Pull Request

- 一个 PR 只做一件事，写清楚测了什么、用的什么素材（引擎相关的改动请用 `tests/` 里的合成素材）。
- push 之前跑一遍测试和 `check_skill.py`。
- 改平台参数请附上来源链接；改视觉效果请附一张截图或联系表。
- 不要提交 API key、个人路径，或者你没有版权的素材。

提交贡献即表示你同意它以本项目的 MIT 协议授权。

## 相关

- [添加效果](/docs/zh/reference/engine/adding-effects/)
- [平台参考](/docs/zh/reference/platforms/)
- [命令行参考](/docs/zh/reference/cli/)
- [安装技能](/docs/zh/start/install-skill/)
