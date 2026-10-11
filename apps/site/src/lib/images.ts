// Image registry: per-language app screenshots and demo sheets (zh has its own UI language and the Chinese
// material; en/fr/es use the English app and the English demo batch).
import type { ImageMetadata } from 'astro';
import makingEn from '../assets/app/making-en.png';
import makingZh from '../assets/app/making-zh.png';
import editorEn from '../assets/app/editor-en.png';
import editorZh from '../assets/app/editor-zh.png';
import review from '../assets/app/review.webp';
import publishEn from '../assets/app/publish-en.webp';
import publishZh from '../assets/app/publish-zh.webp';
import texteditEn from '../assets/app/textedit-en.png';
import texteditZh from '../assets/app/textedit-zh.png';
import typing from '../assets/app/typing.png';
import longform from '../assets/demos/longform-slices.jpg';
import talkinghead from '../assets/demos/talkinghead.jpg';
import longformEn from '../assets/demos/longform-slices-en.jpg';
import talkingheadEn from '../assets/demos/talkinghead-en.jpg';
import type { Lang } from '../i18n';

const SETS = {
  making: { en: makingEn, zh: makingZh },
  editor: { en: editorEn, zh: editorZh },
  review: { en: review, zh: review },
  publish: { en: publishEn, zh: publishZh },
  textedit: { en: texteditEn, zh: texteditZh },
  typing: { en: typing, zh: typing },
  longform: { en: longformEn, zh: longform },
  talkinghead: { en: talkingheadEn, zh: talkinghead },
} satisfies Record<string, { en: ImageMetadata; zh: ImageMetadata }>;
// ┌─ HOME DASHBOARD SCREENSHOT SLOT ───────────────────────────────────────────────────────────────────────────┐
// │ The Home dashboard (Inbox / Running / Going out today) is in development. When it ships:                     │
// │  1. capture it at 1440×900, light theme, from a built app with an isolated profile and the e2e fixtures      │
// │     (never a real profile), save as src/assets/app/home-dash-en.png and home-dash-zh.png;                    │
// │  2. import both here and set HOME_DASH = { en: …, zh: … };                                                    │
// │  3. update `next.*` in src/i18n/{en,zh,fr,es}.ts (it then reads as shipped, not "Coming next").              │
// │ While HOME_DASH is null, the "Coming next: Home" section on the home page shows its text only.               │
// └──────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
export const HOME_DASH: { en: ImageMetadata; zh: ImageMetadata } | null = null;
export const homeDash = (lang: Lang): ImageMetadata | null => (HOME_DASH ? (lang === 'zh' ? HOME_DASH.zh : HOME_DASH.en) : null);

export type ImgKey = keyof typeof SETS;
export const img = (key: ImgKey, lang: Lang): ImageMetadata => (lang === 'zh' ? SETS[key].zh : SETS[key].en);

const clips = import.meta.glob<{ default: ImageMetadata }>('../assets/clips/*.jpg', { eager: true });
export const clipImg = (id: string) => clips[`../assets/clips/${id}.jpg`].default;
