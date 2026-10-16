// A local, offline capture page opened in the user's normal browser. No account, cookie or upload access.
import { createHash } from 'node:crypto';

type Language = 'en' | 'zh' | 'fr';
const words = {
  en: { title: 'Bring a video passage into Reelfold', intro: 'Keep watching in the browser where you signed in. Choose that video tab and include its audio.', original: 'Open the source video', start: 'Choose video tab and record', stop: 'Stop and save passage', ready: 'Ready when you are', recording: 'Recording the tab you chose', saved: 'Saved. Drag the downloaded video into your Reelfold material panel.', noAudio: 'No tab audio was shared. Try again: choose the video tab and enable Share tab audio. Chrome and Edge support this.', unsupported: 'This browser cannot record a tab with sound. Open this local page in Chrome or Edge.', failed: 'Recording could not start. You can try choosing the tab again.', cancelled: 'Sharing was cancelled. Nothing was recorded.', limit: 'Each passage is up to 5 minutes; it saves automatically at the limit. You can record another passage afterward.', limited: 'Saved the 5-minute passage. You can record another passage to continue.', saveAgain: 'Save this passage again', local: 'Recording stays in your browser and saves to your computer. Return to Reelfold to add your own explanation.', partial: 'Recording ended unexpectedly. The recorded part was saved; check it before using it.', empty: 'No video was recorded. Choose the tab again.' },
  zh: { title: '把看到的片段带回 Reelfold', intro: '在已登录的浏览器继续看视频。录制时选择那个视频标签页，并勾选共享声音。', original: '打开原视频', start: '选择视频标签页，开始录制', stop: '停止并保存片段', ready: '准备好后再开始', recording: '正在录制你选择的标签页', saved: '已保存。把下载的视频拖进 Reelfold 的材料区，再加上自己的讲解。', noAudio: '没有共享到标签页声音。请重新选择视频标签页，并勾选“共享标签页音频”。可使用 Chrome 或 Edge。', unsupported: '这个浏览器暂不支持录制带声音的标签页。请用 Chrome 或 Edge 打开这份本地页面。', failed: '录制没有开始，可以重新选择标签页再试。', cancelled: '已取消共享，没有开始录制。', limit: '每段最多 5 分钟，到时自动保存；需要更多内容可以再录一段。', limited: '已保存这段 5 分钟的视频，可以继续录下一段。', saveAgain: '再次保存这段视频', local: '录制内容只在浏览器里处理，保存到你的电脑。回到工作台后，继续加入自己的想法。', partial: '录制意外结束，已保存录到的部分；使用前请先检查。', empty: '没有录到视频，请重新选择标签页。' },
  fr: { title: 'Ajouter un passage vidéo à Reelfold', intro: 'Continuez dans le navigateur où vous êtes connecté. Choisissez l’onglet vidéo et partagez son audio.', original: 'Ouvrir la vidéo source', start: 'Choisir l’onglet et enregistrer', stop: 'Arrêter et sauvegarder', ready: 'Commencez quand vous voulez', recording: 'Enregistrement de l’onglet choisi', saved: 'Enregistré. Glissez la vidéo téléchargée dans les sources Reelfold, puis ajoutez votre explication.', noAudio: 'Aucun audio partagé. Réessayez avec l’onglet vidéo et activez le partage audio. Chrome et Edge le permettent.', unsupported: 'Ce navigateur ne permet pas cet enregistrement audio. Ouvrez cette page locale dans Chrome ou Edge.', failed: 'L’enregistrement n’a pas commencé. Réessayez de choisir l’onglet.', cancelled: 'Partage annulé. Aucun enregistrement.', limit: 'Chaque passage dure au plus 5 minutes, puis se sauvegarde automatiquement. Vous pouvez ensuite en enregistrer un autre.', limited: 'Passage de 5 minutes enregistré. Vous pouvez continuer avec un autre passage.', saveAgain: 'Sauvegarder à nouveau', local: 'Le contenu reste dans votre navigateur et se sauvegarde sur votre ordinateur. Revenez à Reelfold pour ajouter vos idées.', partial: 'Enregistrement interrompu. La partie enregistrée est sauvegardée ; vérifiez-la avant utilisation.', empty: 'Aucune vidéo enregistrée. Choisissez à nouveau l’onglet.' },
};

/** Only an HTTPS source can be opened by this page; no executable or local-file URL is embedded. */
export function safeBrowserSource(value?: string): string | null {
  if (!value) return null;
  try { const u = new URL(value); return u.protocol === 'https:' && !u.username && !u.password ? u.href : null; } catch { return null; }
}

export function browserCapturePage(lang: Language, source?: string): string {
  const copy = words[lang];
  const config = JSON.stringify({ copy, source: safeBrowserSource(source), limit: 300 }).replace(/</g, '\\u003c');
  const script = `
    const config = ${config};
    const el = id => document.getElementById(id);
    for (const node of document.querySelectorAll('[data-copy]')) node.textContent = config.copy[node.dataset.copy];
    let recorder = null, stream = null, chunks = [], downloadUrl = '', timer = null, started = 0, limited = false, recordingFailed = false;
    el('source').hidden = !config.source;
    el('source').onclick = () => window.open(config.source, '_blank', 'noopener,noreferrer');
    const message = text => { el('status').textContent = text; };
    const stopTracks = () => { if (stream) stream.getTracks().forEach(track => track.stop()); stream = null; };
    const download = () => { const link = document.createElement('a'); link.href = downloadUrl; link.download = 'Reelfold-passage-' + new Date().toISOString().replace(/[:.]/g, '-') + '.webm'; link.click(); };
    const stop = () => { if (recorder && recorder.state !== 'inactive') recorder.stop(); };
    el('stop').onclick = stop;
    el('download').onclick = download;
    el('start').onclick = async () => {
      el('start').disabled = true; el('download').hidden = true; limited = false; recordingFailed = false; el('clock').textContent = '';
      if (!navigator.mediaDevices?.getDisplayMedia || typeof MediaRecorder === 'undefined') { message(config.copy.unsupported); el('start').disabled = false; return; }
      try {
        stream = await navigator.mediaDevices.getDisplayMedia({ video: { displaySurface: 'browser', frameRate: { ideal: 30, max: 30 } }, audio: true, selfBrowserSurface: 'exclude', systemAudio: 'exclude', preferCurrentTab: false });
        if (!stream.getAudioTracks().length) { stopTracks(); message(config.copy.noAudio); el('start').disabled = false; return; }
        chunks = [];
        const mimeType = ['video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus', 'video/webm'].find(type => MediaRecorder.isTypeSupported(type));
        if (!mimeType) { stopTracks(); message(config.copy.unsupported); el('start').disabled = false; return; }
        recorder = new MediaRecorder(stream, { mimeType, videoBitsPerSecond: 2500000, audioBitsPerSecond: 128000 });
        recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
        recorder.onerror = () => { recordingFailed = true; stop(); };
        recorder.onstop = () => {
          clearInterval(timer); timer = null; stopTracks(); el('stop').hidden = true; el('start').disabled = false;
          const blob = new Blob(chunks, { type: mimeType }); chunks = [];
          if (!blob.size) { message(config.copy.empty); return; }
          if (downloadUrl) URL.revokeObjectURL(downloadUrl);
          downloadUrl = URL.createObjectURL(blob); el('download').hidden = false; download();
          message(recordingFailed ? config.copy.partial : limited ? config.copy.limited + ' ' + config.copy.saved : config.copy.saved);
        };
        stream.getVideoTracks()[0].addEventListener('ended', stop, { once: true });
        recorder.start(1000); started = Date.now(); el('stop').hidden = false; message(config.copy.recording);
        timer = setInterval(() => { const seconds = Math.floor((Date.now() - started) / 1000); el('clock').textContent = Math.floor(seconds / 60) + ':' + String(seconds % 60).padStart(2, '0'); if (seconds >= config.limit) { limited = true; stop(); } }, 250);
      } catch (error) { stopTracks(); el('start').disabled = false; message(error?.name === 'NotAllowedError' ? config.copy.cancelled : config.copy.failed); }
    };
    window.addEventListener('beforeunload', event => { if (recorder && recorder.state !== 'inactive') { event.preventDefault(); event.returnValue = ''; } });
  `;
  const hash = createHash('sha256').update(script).digest('base64');
  return `<!doctype html><html lang="${lang}"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'sha256-${hash}'; style-src 'unsafe-inline'; media-src blob:; connect-src 'none'"><title>Reelfold · Browser passage</title><style>body{font:18px/1.65 system-ui;background:#18231d;color:#eff5f1;max-width:760px;margin:8vh auto;padding:24px}button{font:inherit;border:1px solid #658172;border-radius:12px;background:transparent;color:inherit;padding:12px 20px;cursor:pointer;margin:8px 8px 8px 0}button:disabled{opacity:.45;cursor:default}#start{background:#79d0ae;color:#13241b;border-color:transparent}p{color:#b5c8bc}h1{font-size:34px}#status{color:#eff5f1;min-height:3em}small{display:block;color:#a5bcad}#clock{font-variant-numeric:tabular-nums}button[hidden]{display:none}</style><small>REELFOLD</small><h1 data-copy="title"></h1><p data-copy="intro"></p><button id="source" data-copy="original"></button><div><button id="start" data-copy="start"></button><button id="stop" data-copy="stop" hidden></button><span id="clock" role="timer"></span></div><p id="status" role="status" data-copy="ready"></p><button id="download" data-copy="saveAgain" hidden></button><small data-copy="limit"></small><p data-copy="local"></p><script>${script}</script></html>`;
}
