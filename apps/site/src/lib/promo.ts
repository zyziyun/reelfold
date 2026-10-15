// Shared by the visible player, watch pages and video sitemap.
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import type { Lang } from '../i18n';
export const demoCopy = {
  en: { title: 'Reelfold app demo: create, edit and prepare to publish', description: 'Watch Reelfold turn a request into videos, edit clips and prepare a publishing calendar. Free, open-source video editing on your Mac.', heading: 'See the workflow in 44 seconds.', note: 'Recorded in a demo workspace. Publishing screens show preparation and scheduling; they do not demonstrate a live upload.', link: 'Watch the app demo', language: 'English on-screen titles', steps: ['Describe a video with your footage or notes.', 'Review and edit a clip, its captions and platform versions.', 'Turn notes into an animated explanation.', 'Prepare post copy and a publishing calendar.'], guide: 'Try the workflow', next: 'Make several videos from a folder' },
  zh: { title: '千剪 Reelfold 演示：创作、剪辑与发布准备', description: '用 44 秒了解千剪：描述需求、编辑成片、制作讲解视频，再准备文案和发布日历。免费开源，在 Mac 上剪辑。', heading: '44 秒，看看工作流程。', note: '在演示工作区录制。发布画面展示文案准备和排期，不代表实际账号上传。', link: '观看应用演示', language: '中文画面标题', steps: ['带上素材或笔记，描述想做的视频。', '检查成片、字幕和各平台版本，继续修改。', '把笔记做成动画讲解。', '准备发布文案和日历排期。'], guide: '试试这个流程', next: '从文件夹做一组视频' },
  fr: { title: 'Démo Reelfold : créer, monter et préparer la publication', description: 'Découvrez Reelfold en 44 secondes : demande, montage, explication animée et calendrier. Montage local gratuit et open source sur Mac.', heading: 'Le workflow en 44 secondes.', note: 'Enregistré dans un espace de démonstration. La publication montre la préparation et le calendrier, sans envoi réel.', link: 'Voir la démo', language: 'Titres à l’écran en anglais', steps: ['Décrivez la vidéo avec vos fichiers ou vos notes.', 'Vérifiez le montage, les sous-titres et les formats.', 'Transformez des notes en explication animée.', 'Préparez les textes et le calendrier de publication.'], guide: 'Essayer le workflow', next: 'Créer plusieurs vidéos depuis un dossier' },
  es: { title: 'Demo de Reelfold: crear, editar y preparar la publicación', description: 'Conoce Reelfold en 44 segundos: petición, edición, explicación animada y calendario. Edición local gratuita y de código abierto en Mac.', heading: 'El flujo en 44 segundos.', note: 'Grabado en un espacio de demostración. La publicación muestra preparación y calendario, sin una subida real.', link: 'Ver la demo', language: 'Títulos en pantalla en inglés', steps: ['Describe el vídeo con tus archivos o notas.', 'Revisa el montaje, los subtítulos y los formatos.', 'Convierte notas en una explicación animada.', 'Prepara los textos y el calendario de publicación.'], guide: 'Probar el flujo', next: 'Crear varios vídeos desde una carpeta' },
} as const;
export function promo(lang: Lang) {
  const mediaLang = lang === 'zh' ? 'zh' : 'en';
  const src = `/media/reelfold-demo-${mediaLang}.mp4`;
  const poster = `/media/reelfold-demo-${mediaLang}.jpg`;
  const available = [src, poster].every(p => existsSync(join(process.cwd(), 'public', p)));
  return { src, poster, available, mediaLang, duration: 'PT43.834S', uploadDate: '2026-10-15', ...demoCopy[lang] };
}
