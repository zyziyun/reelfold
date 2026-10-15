import type { APIRoute } from 'astro';
import { LANGS, pathFor } from '../i18n';
import { site } from '../config';
import { promo } from '../lib/promo';
const xml = (s: string) => s.replace(/[<>&"']/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&apos;' }[c]!));
export const GET: APIRoute = () => new Response(`<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:video="http://www.google.com/schemas/sitemap-video/1.1">${LANGS.filter(l => promo(l).available).map(l => {
  const f = promo(l);
  return `<url><loc>${site}${pathFor(l, 'demo')}</loc><video:video><video:thumbnail_loc>${site}${f.poster}</video:thumbnail_loc><video:title>${xml(f.title)}</video:title><video:description>${xml(f.description)}</video:description><video:content_loc>${site}${f.src}</video:content_loc><video:duration>44</video:duration><video:publication_date>${f.uploadDate}</video:publication_date></video:video></url>`;
}).join('')}</urlset>`, { headers: { 'Content-Type': 'application/xml; charset=utf-8' } });
