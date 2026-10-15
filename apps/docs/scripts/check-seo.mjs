// Check the generated multilingual SEO contract, including English fallback pages.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
const dist = fileURLToPath(new URL('../dist/', import.meta.url));
const pages = new Map();
function walk(dir) { for (const name of readdirSync(dir)) {
  const p = join(dir, name);
  if (statSync(p).isDirectory()) walk(p);
  else if (p.endsWith('index.html')) pages.set('https://reelfold.com/docs/' + relative(dist, p).replace(/index.html$/, ''), readFileSync(p, 'utf8'));
} }
walk(dist);
const errors = [];
const attr = (tag, name) => tag.match(new RegExp(`\\b${name}="([^"]*)"`))?.[1];
const sitemap = readdirSync(dist).filter(f => /^sitemap-\d+\.xml$/.test(f)).map(f => readFileSync(join(dist, f), 'utf8')).join('');
for (const [url, html] of pages) {
  const tags = [...html.matchAll(/<link\b[^>]*>/g)].map(m => m[0]);
  const canonical = tags.filter(t => attr(t, 'rel') === 'canonical').map(t => attr(t, 'href'));
  const noindex = /<meta[^>]*name="robots"[^>]*content="[^"]*noindex/.test(html);
  if (canonical.length !== 1 || !pages.has(canonical[0])) errors.push(`${url}: missing or invalid canonical`);
  if (!noindex && canonical[0] !== url) errors.push(`${url}: canonical is not self`);
  if (noindex && sitemap.includes(`<loc>${url}</loc>`)) errors.push(`${url}: fallback in sitemap`);
  const alternates = tags.filter(t => attr(t, 'rel') === 'alternate' && attr(t, 'hreflang'));
  if (noindex && alternates.length) errors.push(`${url}: noindex fallback has hreflang`);
  for (const tag of alternates) {
    const target = attr(tag, 'href');
    const other = pages.get(target);
    if (!other || /name="robots"[^>]*content="[^"]*noindex/.test(other)) errors.push(`${url}: hreflang targets a missing or noindex page ${target}`);
    else if (!other.includes(`href="${url}"`)) errors.push(`${url}: hreflang not reciprocal from ${target}`);
  }
  if (!noindex && !alternates.some(t => attr(t, 'href') === url)) errors.push(`${url}: no self hreflang`);
  for (const m of html.matchAll(/<script[^>]*type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/g)) {
    try { JSON.parse(m[1]); } catch { errors.push(`${url}: invalid JSON-LD`); }
  }
}
if (errors.length) { console.error(errors.join('\n')); process.exit(1); }
console.log(`docs SEO check ok (${pages.size} pages; canonicals, translations, fallback exclusions and structured data)`);
