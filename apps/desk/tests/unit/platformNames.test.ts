// No platform id renders as a raw `pf.*` key: every id the engine can hand the UI (platforms, package keys like
// "instagram-reels", "x:square") resolves to a name in every UI language.
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';
import { PLATFORMS } from '../../src/shared/platforms';
import { LANGS, setLang } from '../../src/renderer/src/i18n';
import { platformName } from '../../src/renderer/src/lib/platformName';

const root = path.resolve(__dirname, '../../../..');

/** The engine's platforms and every package key it writes ("<platform>-<orientation>"). */
function engineIds(): string[] {
  const out = execFileSync('python3', ['-I', '-c', [
    'import json, sys',
    `sys.path.insert(0, ${JSON.stringify(path.join(root, 'lib'))})`,
    'from vstudio import platform as p',
    'print(json.dumps({k: list(v.get("orientations", {})) for k, v in p.PLATFORMS.items()}))',
  ].join('\n')], { encoding: 'utf8' });
  const m = JSON.parse(out) as Record<string, string[]>;
  return Object.entries(m).flatMap(([k, os]) => [k, ...os.map((o) => `${k}-${o}`), ...os.map((o) => `${k}:${o}`)]);
}

describe('platform names', () => {
  afterAll(() => setLang('en'));
  const ids = [...new Set([...engineIds(), ...PLATFORMS.map((p) => p.id), 'x-web', 'shipinhao'])];

  it('cover every engine platform and package key in every UI language', () => {
    expect(ids).toContain('instagram-reels');
    for (const l of LANGS) {
      setLang(l);
      for (const id of ids) {
        const n = platformName(id);
        expect(n, `${l} ${id}`).not.toMatch(/^pf\./);
        expect(n, `${l} ${id}`).not.toBe('');
      }
    }
  });

  it('name Instagram Reels on its own (the inbox review card)', () => {
    setLang('en');
    expect(platformName('instagram-reels')).toBe('Instagram Reels');
    expect(platformName('tiktok-vertical')).toBe('TikTok');
    setLang('fr');
    expect(platformName('instagram-reels')).toBe('Reels Instagram');
    setLang('zh-CN');
    expect(platformName('instagram-reels')).toBe('Instagram Reels');
  });

  it('are only looked up through platformName (no hand-built pf.${id} keys)', () => {
    const src = path.resolve(__dirname, '../../src/renderer/src');
    const files = fs.readdirSync(src, { recursive: true, encoding: 'utf8' }).filter((f) => /\.tsx?$/.test(f) && !f.includes('i18n'));
    const bad = files.filter((f) => !f.endsWith('platformName.ts') && /`pf\.\$\{/.test(fs.readFileSync(path.join(src, f), 'utf8')));
    expect(bad).toEqual([]);
  });
});
