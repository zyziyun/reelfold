// Every automatic check the engine can fail (vstudio: _c("<name>", ...)) is named in plain words with what to do, in
// every UI language; a review never lists "An auto check failed" twice with no detail.
import fs from 'node:fs';
import path from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';
import { LANGS, LOCALES, setLang } from '../../src/renderer/src/i18n';
import { issueDo, issueText, reviewReasons } from '../../src/renderer/src/lib/inboxView';

const lib = path.resolve(__dirname, '../../../../lib/vstudio');

function engineChecks(): string[] {
  const names = new Set<string>();
  for (const f of fs.readdirSync(lib, { recursive: true, encoding: 'utf8' }).filter((x) => x.endsWith('.py'))) {
    for (const m of fs.readFileSync(path.join(lib, f), 'utf8').matchAll(/\b_c\(\s*"([a-z][a-z0-9-]+)"/g)) names.add(m[1]);
  }
  return [...names].sort();
}

describe('failed checks', () => {
  afterAll(() => setLang('en'));
  const checks = engineChecks();

  it('finds the engine’s checks', () => {
    expect(checks).toEqual(expect.arrayContaining(['loudness', 'safe-zone', 'av-sync', 'title', 'lost-words']));
  });

  it('each has a name and a what-to-do in every UI language', () => {
    for (const l of LANGS) {
      const m = LOCALES[l].messages as Record<string, string>;
      for (const c of checks) {
        expect(m[`issue.${c}`], `${l} issue.${c}`).toBeTruthy();
        expect(m[`issue.do.${c}`], `${l} issue.do.${c}`).toBeTruthy();
      }
    }
  });

  it('a check the app has no words for still says which one; two lines never read the same', () => {
    setLang('en');
    expect(issueText('new-check')).toBe('The “new check” check didn’t pass');
    expect(issueDo('new-check')).toMatch(/approve/i);
    const rs = reviewReasons([{ code: 'safe-zone', n: 2 }, { code: 'alpha', n: 1 }, { code: 'beta', n: 1 }, { code: 'safe-zone', n: 1 }]);
    expect(new Set(rs.map((r) => r.text)).size).toBe(rs.length);
    expect(rs.find((r) => r.code === 'safe-zone')).toMatchObject({ text: 'Captions sit under the platform’s buttons', n: 3 });
    expect(rs.map((r) => r.text)).not.toContain('An auto check failed');
  });
});
