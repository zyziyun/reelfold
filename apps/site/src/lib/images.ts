// Image registry: per-language app screenshots and output sheets. zh shows the app in Chinese with Chinese projects;
// en / fr / es show the English app. Every screenshot comes from a desk build on an isolated demo profile: real engine
// runs (Claude Code as the AI) on CC0 / public-domain footage (credits: README "Image credits"), never a creator's own
// footage. Sources are 2x (2880x1800) WebP; astro:assets makes the AVIF / WebP sizes.
import type { ImageMetadata } from 'astro';
import makingEn from '../assets/app/making-en.webp';
import makingZh from '../assets/app/making-zh.webp';
import editorEn from '../assets/app/editor-en.webp';
import editorZh from '../assets/app/editor-zh.webp';
import publishEn from '../assets/app/publish-en.webp';
import publishZh from '../assets/app/publish-zh.webp';
import texteditEn from '../assets/app/textedit-en.webp';
import texteditZh from '../assets/app/textedit-zh.webp';
import reviewEn from '../assets/app/review-en.webp';
import reviewZh from '../assets/app/review-zh.webp';
import projectsEn from '../assets/app/projects-en.webp';
import projectsZh from '../assets/app/projects-zh.webp';
import courseEn from '../assets/app/course-en.webp';
import courseZh from '../assets/app/course-zh.webp';
import homeDashEn from '../assets/app/home-dash-en.webp';
import homeDashZh from '../assets/app/home-dash-zh.webp';
import follow from '../assets/demos/follow.webp';
import talkinghead from '../assets/demos/talkinghead.jpg';
import longform from '../assets/demos/longform.jpg';
import type { Lang } from '../i18n';

const SETS = {
  making: { en: makingEn, zh: makingZh },
  editor: { en: editorEn, zh: editorZh },
  review: { en: reviewEn, zh: reviewZh },
  publish: { en: publishEn, zh: publishZh },
  textedit: { en: texteditEn, zh: texteditZh },
  projects: { en: projectsEn, zh: projectsZh },
  course: { en: courseEn, zh: courseZh },
  follow: { en: follow, zh: follow },
  longform: { en: longform, zh: longform },
  talkinghead: { en: talkinghead, zh: talkinghead },
} satisfies Record<string, { en: ImageMetadata; zh: ImageMetadata }>;

// The Home dashboard (Inbox / Running / Going out today), shown in the "New: Home" section of the home page.
export const HOME_DASH: { en: ImageMetadata; zh: ImageMetadata } | null = { en: homeDashEn, zh: homeDashZh };
export const homeDash = (lang: Lang): ImageMetadata | null => (HOME_DASH ? (lang === 'zh' ? HOME_DASH.zh : HOME_DASH.en) : null);

export type ImgKey = keyof typeof SETS;
export const img = (key: ImgKey, lang: Lang): ImageMetadata => (lang === 'zh' ? SETS[key].zh : SETS[key].en);

const clips = import.meta.glob<{ default: ImageMetadata }>('../assets/clips/*.jpg', { eager: true });
export const clipImg = (id: string) => clips[`../assets/clips/${id}.jpg`].default;
