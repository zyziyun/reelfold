// Generate packaging/assets.json: the large assets the app downloads on first run (not shipped in the installer),
// each with a pinned URL, size and sha256. Small files are downloaded and hashed here; Hugging Face LFS files use
// the LFS sha256 from the API (no 1.6 GB download needed). The headless browser zips are downloaded once to hash them.
//   node scripts/runtime/assets-lock.mjs [--skip-chromium]
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { CACHE, download, log, ROOT, sha256File } from './common.mjs';

const PINS = {
  notoCjk: 'f8d157532fbfaeda587e826d4cd5b21a49186f7c',
  googleFonts: '7085eb89a950e85db5b166b7a58d414544b4140c',
  jetbrainsMono: '19371302b95d218af43299bce79ddbddd0bc364d',
  // the typography kit (vstudio.config FONTS display-zh / zh-humanist / serif-display; theme.type_scale pairs), all
  // SIL OFL 1.1: LXGW WenKai (霞鹜文楷) is a plain release file; Smiley Sans (得意黑) is only published as a zip, so it
  // is its own extract group (font-smiley); Instrument Serif comes from google/fonts at the googleFonts pin above
  lxgwWenKai: 'https://github.com/lxgw/LxgwWenKai/releases/download/v1.522/LXGWWenKai-Regular.ttf',
  smileySans: { version: '2.0.1', url: 'https://github.com/atelier-anchor/smiley-sans/releases/download/v2.0.1/smiley-sans-v2.0.1.zip' },
  mlxWhisper: { repo: 'mlx-community/whisper-large-v3-turbo', rev: 'a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb' },
  // 4-bit turbo: ~460 MB instead of 1.6 GB, near-identical captions; the first-run default (the full one is optional)
  mlxWhisperFast: { repo: 'mlx-community/whisper-large-v3-turbo-q4', rev: '660c343bbf4e52ac257f0b7d952e5388e6f93bef' },
  fasterWhisper: { repo: 'dropbox-dash/faster-whisper-large-v3-turbo', rev: '0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf' },
  // the free offline voice (Apple silicon, mlx-audio): Kokoro-82M v1.0 weights + the voices the engine defaults to
  // (zf_xiaobei = vstudio.tts.ZH_VOICE, af_heart = DEFAULT_VOICE) and two more English ones
  kokoro: { repo: 'mlx-community/Kokoro-82M-bf16', rev: 'a71e4d38b236d968966a2002c4c895dbd12b1c3c',
    voices: ['zf_xiaobei', 'af_heart', 'am_michael', 'bf_emma'] },
  // the free Chinese voice (Apple silicon, mlx-audio): Qwen3-TTS 1.7B CustomVoice, 8-bit MLX - native Mandarin
  // speakers (serena = vstudio.tts.ZH_VOICE["qwen"], vivian, uncle_fu, dylan, eric); ux/zh-voice has the A/B
  qwenTts: { repo: 'mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit', rev: '41d3337e8b7f2843a75841595fc14e4b9a7a4b96' },
  // frame interpolation (Apple silicon, MLX - no torch): RIFE 4.25 for morph-cut bridges and smooth slow motion
  // (vstudio.rife / vstudio.morphcut); the same pins as vstudio.rife.FILES
  rife: { repo: 'mlx-community/RIFE-4.25', rev: '6b650eaa5664aab280119511fe944861491aa15e' },
  // the headless browser for HTML covers / slides and HyperFrames: chrome-headless-shell from Chrome for Testing, not a
  // Chromium.app snapshot - a bare executable with no app bundle, so macOS never sees an app that could ask for
  // notifications. The version is the one HyperFrames manages itself (CHROME_VERSION in the hyperframes CLI), so its
  // renders run on the browser it is tested with and it does not download a second copy.
  // cover engine 2.0 (vstudio.cover_engine): subject cutout, upscale, frame aesthetics - all MIT / BSD / Apache
  birefnet: { repo: 'onnx-community/BiRefNet_lite-ONNX', rev: 'de15b22ba131738a16dff04aab8bdf8dc32e3ac1' },
  clipL14: { repo: 'Xenova/clip-vit-large-patch14', rev: 'c307790166907339eed5a9a53a249af534102536' },
  aesthetic: { repo: 'christophschuhmann/improved-aesthetic-predictor', sha: '6934dd81792f086e613a121dbce43082cb8be85e' },
  esrgan: 'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth',
  headlessShell: { version: '152.0.7977.30', platforms: { 'darwin-arm64': 'mac-arm64', 'darwin-x64': 'mac-x64', 'win32-x64': 'win64' } },
};
const skipChromium = process.argv.includes('--skip-chromium');
const prev = (() => {
  try {
    return JSON.parse(fs.readFileSync(path.join(ROOT, 'packaging', 'assets.json'), 'utf8'));
  } catch {
    return null;
  }
})();

async function hashUrl(url) {
  const f = path.join(CACHE, 'assets', crypto.createHash('sha1').update(url).digest('hex'));
  await download(url, f);
  return { sha256: sha256File(f), size: fs.statSync(f).size };
}

async function file(url, dest) {
  return { url, dest, ...(await hashUrl(url)) };
}

async function hf({ repo, rev }, dir, names) {
  const tree = await (await fetch(`https://huggingface.co/api/models/${repo}/tree/${rev}?recursive=true`)).json();
  const out = [];
  for (const name of names) {
    const ent = tree.find((x) => x.path === name);
    if (!ent) throw new Error(`${repo}@${rev} has no ${name}`);
    const url = `https://huggingface.co/${repo}/resolve/${rev}/${name}`;
    out.push(ent.lfs ? { url, dest: `${dir}/${name}`, sha256: ent.lfs.oid, size: ent.size } : await file(url, `${dir}/${name}`));
  }
  return out;
}

const raw = (repo, sha, p) => `https://raw.githubusercontent.com/${repo}/${sha}/${p}`;
const fonts = [
  ['notofonts/noto-cjk', PINS.notoCjk, 'Sans/SubsetOTF/SC/NotoSansSC-Regular.otf', 'NotoSansSC-Regular.otf'],
  ['notofonts/noto-cjk', PINS.notoCjk, 'Sans/SubsetOTF/SC/NotoSansSC-Bold.otf', 'NotoSansSC-Bold.otf'],
  // the heavy Chinese titles (vstudio.launch.brand ZH_HEAVY): a real Black instead of Bold thickened with a stroke
  ['notofonts/noto-cjk', PINS.notoCjk, 'Sans/SubsetOTF/SC/NotoSansSC-Black.otf', 'NotoSansSC-Black.otf'],
  ['notofonts/noto-cjk', PINS.notoCjk, 'Serif/SubsetOTF/SC/NotoSerifSC-Regular.otf', 'NotoSerifSC-Regular.otf'],
  ['notofonts/noto-cjk', PINS.notoCjk, 'Serif/SubsetOTF/SC/NotoSerifSC-Bold.otf', 'NotoSerifSC-Bold.otf'],
  ['google/fonts', PINS.googleFonts, 'ofl/stixtwotext/STIXTwoText%5Bwght%5D.ttf', 'STIXTwoText-Regular.ttf'],
  ['google/fonts', PINS.googleFonts, 'ofl/stixtwotext/STIXTwoText-Italic%5Bwght%5D.ttf', 'STIXTwoText-Italic.ttf'],
  ['JetBrains/JetBrainsMono', PINS.jetbrainsMono, 'fonts/ttf/JetBrainsMono-Regular.ttf', 'JetBrainsMono-Regular.ttf'],
  ['JetBrains/JetBrainsMono', PINS.jetbrainsMono, 'fonts/ttf/JetBrainsMono-Bold.ttf', 'JetBrainsMono-Bold.ttf'],
  ['google/fonts', PINS.googleFonts, 'ofl/instrumentserif/InstrumentSerif-Regular.ttf', 'InstrumentSerif-Regular.ttf'],
];
const MP = 'https://storage.googleapis.com/mediapipe-models';
const models = [
  [`${MP}/face_landmarker/face_landmarker/float16/1/face_landmarker.task`, 'face_landmarker.task'],
  [`${MP}/image_segmenter/selfie_segmenter/float16/1/selfie_segmenter.tflite`, 'selfie_segmenter.tflite'],
  [`${MP}/image_segmenter/selfie_multiclass_256x256/float32/1/selfie_multiclass_256x256.tflite`, 'selfie_multiclass_256x256.tflite'],
];

// beat / downbeat tracker (vstudio.beatthis) and shot boundaries (vstudio.transnet): read without torch / TensorFlow
// Mirrored on Reelfold's GitHub (MIT; original: https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp/final0.ckpt)
const BEAT_THIS = 'https://github.com/zyziyun/reelfold/releases/download/models-beat-this-final0/final0.ckpt';
const TRANSNET = 'https://media.githubusercontent.com/media/soCzech/TransNetV2/85cef72af9a916bdfd7cc94a670c9cdfbf12d1ed/inference/transnetv2-weights/variables';
const engineModels = [
  [BEAT_THIS, 'models/beat_this/final0.ckpt'],
  [`${TRANSNET}/variables.index`, 'models/transnetv2/variables.index'],
  [`${TRANSNET}/variables.data-00000-of-00001`, 'models/transnetv2/variables.data-00000-of-00001'],
];

const CORE_LICENCE = 'Fonts: SIL OFL 1.1 (Noto CJK, STIX Two, JetBrains Mono, Instrument Serif, LXGW WenKai). Models: Apache-2.0 (Google MediaPipe); MIT (Beat This! final0, CPJKU; TransNet V2, Soucek).';
const groups = [];
log('fonts + models');
groups.push({
  id: 'core',
  required: true,
  root: 'vstudio-cache',
  licence: CORE_LICENCE,
  files: [
    ...(await Promise.all(fonts.map(([r, s, p, n]) => file(raw(r, s, p), `fonts/${n}`)))),
    await file(PINS.lxgwWenKai, 'fonts/LXGWWenKai-Regular.ttf'),
    ...(await Promise.all(models.map(([u, n]) => file(u, `models/${n}`)))),
    ...(await Promise.all(engineModels.map(([u, d]) => file(u, d)))),
  ],
});
log('smiley sans');
// required (5.8 MB): the modern Chinese display face for headlines; the zip holds SmileySans-Oblique.otf/.ttf at its
// top level. Its own private root (an extract root is replaced as a whole, never the shared engine cache); the engine
// finds it through VSTUDIO_FONT_DISPLAY_ZH (CLI installs put it in <cache>/fonts instead)
groups.push({
  id: 'font-smiley',
  required: true,
  root: `fonts/smiley-sans-${PINS.smileySans.version}`,
  extract: true,
  env: { VSTUDIO_FONT_DISPLAY_ZH: 'SmileySans-Oblique.otf' },
  licence: 'Smiley Sans (得意黑), SIL OFL 1.1 (atelier-anchor). Chinese display headlines.',
  files: [await file(PINS.smileySans.url, `smiley-sans-v${PINS.smileySans.version}.zip`)],
});
log('whisper');
// asr-mlx-fast comes first: both set VSTUDIO_WHISPER_MLX and a later installed group wins, so the full model takes
// over once she downloads it
groups.push({
  id: 'asr-mlx-fast',
  required: true,
  targets: ['darwin-arm64'],
  root: 'models/whisper-large-v3-turbo-q4-mlx',
  env: { VSTUDIO_WHISPER_MLX: '' },
  licence: 'OpenAI Whisper large-v3-turbo weights, MIT (4-bit MLX conversion by mlx-community).',
  files: await hf(PINS.mlxWhisperFast, '.', ['config.json', 'weights.npz']),
});
groups.push({
  id: 'asr-mlx',
  required: false,
  targets: ['darwin-arm64'],
  root: 'models/whisper-large-v3-turbo-mlx',
  env: { VSTUDIO_WHISPER_MLX: '' },
  licence: 'OpenAI Whisper large-v3-turbo weights, MIT (MLX conversion by mlx-community).',
  files: await hf(PINS.mlxWhisper, '.', ['config.json', 'weights.safetensors']),
});
groups.push({
  id: 'asr-ct2',
  required: true,
  targets: ['darwin-x64', 'win32-x64'],
  root: 'models/whisper-large-v3-turbo-ct2',
  env: { VSTUDIO_WHISPER_FW: '' },
  licence: 'OpenAI Whisper large-v3-turbo weights, MIT (CTranslate2 conversion).',
  files: await hf(PINS.fasterWhisper, '.', ['config.json', 'model.bin', 'preprocessor_config.json', 'tokenizer.json', 'vocabulary.json']),
});
log('kokoro');
// optional: downloaded the first time a video needs the free voice (the desk offers it), or from Settings > Downloads
groups.push({
  id: 'tts-kokoro',
  required: false,
  targets: ['darwin-arm64'],
  root: 'models/kokoro-82m-mlx',
  env: { VSTUDIO_KOKORO_MODEL: '' },
  licence: 'Kokoro-82M v1.0 weights and voices, Apache-2.0 (hexgrad; MLX conversion by mlx-community).',
  files: await hf(PINS.kokoro, '.', ['config.json', 'kokoro-v1_0.safetensors', ...PINS.kokoro.voices.map((v) => `voices/${v}.safetensors`)]),
});
log('cover models');
// first run: the subject cutout every cover uses (onnxruntime on every target) and, on Apple silicon (MLX), the
// upscaler for small cover crops; optional: the frame-aesthetics model (covers rank frames without it)
groups.push({
  id: 'matte-birefnet',
  required: true,
  root: 'models/birefnet-lite',
  env: { VSTUDIO_BIREFNET_MODEL: 'model.onnx' },
  licence: 'BiRefNet-lite, MIT (ZhengPeng7/BiRefNet; ONNX export by onnx-community, MIT). Cover subject cutout.',
  files: await hf(PINS.birefnet, '.', ['onnx/model.onnx']).then((fs) => fs.map((f) => ({ ...f, dest: './model.onnx' }))),
});
groups.push({
  id: 'upscale-esrgan',
  required: true,
  targets: ['darwin-arm64'],
  root: 'models/realesrgan',
  env: { VSTUDIO_ESRGAN_WEIGHTS: 'realesr-general-x4v3.pth' },
  licence: 'Real-ESRGAN realesr-general-x4v3 weights, BSD-3-Clause (xinntao). Upscales small cover crops (MLX).',
  files: [await file(PINS.esrgan, './realesr-general-x4v3.pth')],
});
groups.push({
  id: 'cover-aesthetic',
  required: false,
  root: 'models/aesthetic',
  env: { VSTUDIO_AESTHETIC_MODEL: '' },
  licence: 'LAION aesthetic predictor v2, Apache-2.0 (christophschuhmann/improved-aesthetic-predictor) on OpenAI CLIP ViT-L/14, MIT (q4f16 ONNX by Xenova). Ranks cover frames.',
  files: [
    ...(await hf(PINS.clipL14, '.', ['onnx/vision_model_q4f16.onnx'])).map((f) => ({ ...f, dest: './vision_model.onnx' })),
    await file(raw(PINS.aesthetic.repo, PINS.aesthetic.sha, 'sac%2Blogos%2Bava1-l14-linearMSE.pth'), './sac+logos+ava1-l14-linearMSE.pth'),
  ],
});
log('qwen3-tts');
// optional: the Chinese voice (about 3 GB), from Settings > Voice or the voice step's "Download the Chinese voice"
groups.push({
  id: 'tts-qwen-zh',
  required: false,
  targets: ['darwin-arm64'],
  root: 'models/qwen3-tts-1.7b-customvoice-8bit',
  env: { VSTUDIO_QWEN_TTS_MODEL: '' },
  licence: 'Qwen3-TTS-12Hz-1.7B-CustomVoice weights and speech tokenizer, Apache-2.0 (Alibaba Qwen; 8-bit MLX conversion by mlx-community).',
  files: await hf(PINS.qwenTts, '.', ['config.json', 'generation_config.json', 'preprocessor_config.json', 'tokenizer_config.json',
    'vocab.json', 'merges.txt', 'model.safetensors', 'model.safetensors.index.json', 'speech_tokenizer/config.json',
    'speech_tokenizer/configuration.json', 'speech_tokenizer/preprocessor_config.json', 'speech_tokenizer/model.safetensors']),
});
log('rife');
// required on Apple silicon: 23 MB, and talking heads smooth their jump cuts by default (formats smooth_cuts)
groups.push({
  id: 'rife-mlx',
  required: true,
  targets: ['darwin-arm64'],
  root: 'models/rife-4.25-mlx',
  env: { VSTUDIO_RIFE_MODEL: '' },
  licence: 'RIFE 4.25 (Practical-RIFE, hzwer) weights, MIT (MLX conversion by mlx-community).',
  files: await hf(PINS.rife, '.', ['config.json', 'model.safetensors']),
});
log('music library');
// required: the CC0 music library every video's music is picked from (vstudio.music; ~290 MB). The track list, each
// file's pinned mirror URL, size and sha256 live in the engine's music_library.json (built and
// licence-checked by curation; vstudio.music.validate_library) - copied here, not re-downloaded.
const musicLib = JSON.parse(fs.readFileSync(path.join(ROOT, '..', '..', 'lib', 'vstudio', 'music_library.json'), 'utf8'));
groups.push({
  id: 'music-library',
  required: true,
  root: `music/library-v${musicLib.version}`,
  env: { VSTUDIO_MUSIC_LIBRARY: '' },
  licence: 'Music library: CC0 1.0 / public domain tracks (FreePD.com: Kevin MacLeod, Bryan Teoh, Komiku; Musopen: Chopin). Free to use in published videos, no credit needed (THIRD_PARTY_NOTICES.md).',
  files: musicLib.tracks.map((t) => ({ url: t.url, dest: t.file, sha256: t.sha256, size: t.size })),
});
const CFT = 'https://storage.googleapis.com/chrome-for-testing-public';
for (const [target, plat] of Object.entries(PINS.headlessShell.platforms)) {
  const { version } = PINS.headlessShell;
  const name = `chrome-headless-shell-${plat}`;
  const url = `${CFT}/${version}/${plat}/${name}.zip`;
  const old = prev?.groups.find((g) => g.id === `chromium-${target}`)?.files[0];
  let f;
  if (old?.url === url) f = old;
  else if (skipChromium) continue;
  else {
    log('chrome-headless-shell', target, url);
    f = { url, dest: `${name}.zip`, ...(await hashUrl(url)) };
  }
  const exe = `${name}/chrome-headless-shell${target.startsWith('win32') ? '.exe' : ''}`;
  groups.push({
    // the id stays chromium-<target> (the Settings row, the Lite filter); a new root + sha256 makes an older install
    // an upgrade the desk downloads by itself, then removes the old folder (AssetManager.upgrades)
    id: `chromium-${target}`,
    required: false,
    targets: [target],
    root: `chrome-headless-shell/${version}`,
    extract: true,
    // HYPERFRAMES_BROWSER_PATH: HyperFrames renders / checks use the same binary instead of downloading their own
    env: { CHROME: exe, HYPERFRAMES_BROWSER_PATH: exe },
    licence: 'chrome-headless-shell (Chromium), BSD-3-Clause and third-party licences (LICENSE.headless_shell in the download). Used for HTML covers/slides and HyperFrames.',
    files: [f],
  });
}

const out = { $comment: 'Generated by scripts/runtime/assets-lock.mjs. Downloaded on first run into the app data dir; every file is sha256-checked.', groups };
fs.writeFileSync(path.join(ROOT, 'packaging', 'assets.json'), JSON.stringify(out, null, 1) + '\n');
log('wrote packaging/assets.json', groups.map((g) => `${g.id}:${(g.files.reduce((a, f) => a + f.size, 0) / 1e6).toFixed(0)}MB`).join(' '));
