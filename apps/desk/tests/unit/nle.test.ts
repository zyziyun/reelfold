// "Export for editing software…" and her hand edits on the desk side: the engine calls (one clip / a whole project,
// format and media in the body), the formats international first (剪映 last), the override reset op, and every message
// in en / zh / fr with the same variables.
import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import { EngineClient } from '../../src/shared/engineClient';
import { nleEn, nleFr, nleZh } from '../../src/renderer/src/i18n/locales/nle';

const BASE = 'app://desk';
const TOKEN = 'tok'.repeat(20);
const ok = (body: unknown) => vi.fn(async (_url: string, _init?: RequestInit) => new Response(JSON.stringify(body), { status: 200 }));
const SRC = (p: string) => fs.readFileSync(path.join(import.meta.dirname, '../../src/renderer/src', p), 'utf8');

describe('engine calls', () => {
  it('one clip and a whole project go to output nle', async () => {
    const f = ok({ ok: true, format: 'capcut', dir: '/x', main: '/x/clip' });
    const c = new EngineClient(BASE, TOKEN, f);
    await c.exportNle('abcdefabcdef', 'clip a.mp4', 'capcut', { media: 'copy', to_app: true });
    let [url, init] = f.mock.calls[0];
    expect(url).toBe(`${BASE}/api/outputs/abcdefabcdef/${encodeURIComponent('clip a.mp4')}/nle`);
    expect(JSON.parse(String(init!.body))).toEqual({ format: 'capcut', media: 'copy', to_app: true });
    await c.exportNleAll('abcdefabcdef', 'xmeml');
    [url, init] = f.mock.calls[1];
    expect(url).toBe(`${BASE}/api/outputs/abcdefabcdef/nle`);
    expect(JSON.parse(String(init!.body))).toEqual({ format: 'xmeml' });
  });

  it('a hand edit goes back to the AI version with one op', async () => {
    const f = ok({ ok: true, step: { id: 's3', describe: [] } });
    const c = new EngineClient(BASE, TOKEN, f);
    await c.editOutput('abcdefabcdef', 'c1', [{ op: 'override_reset', key: 'caption_style:color' }]);
    expect(JSON.parse(String(f.mock.calls[0][1]!.body)).ops).toEqual([{ op: 'override_reset', key: 'caption_style:color' }]);
  });
});

describe('the dialog and its entry points', () => {
  it('lists the formats international first, 剪映 last', () => {
    const src = SRC('v4/NleDialog.tsx');
    expect(src).toContain("export const NLE_FORMATS: NleFormat[] = ['xmeml', 'capcut', 'otio', 'jianying'];");
  });
  it('is offered on the export card, the clip menu and Deliver; hand edits in the editor', () => {
    expect(SRC('v4/chat/cards.tsx')).toContain('data-testid="export-nle"');
    const proj = SRC('v4/Project.tsx');
    expect(proj).toContain("testId: 'menu-nle'");
    expect(proj).toContain('data-testid="deliver-nle"');
    expect(SRC('v4/OutputEditor.tsx')).toContain("{ op: 'override_reset', key: o.key }");
  });
});

describe('messages', () => {
  const vars = (s: string) => [...s.matchAll(/\{(\w+)[,}]/g)].map((m) => m[1]).sort();
  it('exist in en / zh / fr with the same variables', () => {
    for (const k of Object.keys(nleEn) as (keyof typeof nleEn)[]) {
      expect(nleZh[k], k).toBeTruthy();
      expect(nleFr[k], k).toBeTruthy();
      expect(vars(nleZh[k]), k).toEqual(vars(nleEn[k]));
      expect(vars(nleFr[k]), k).toEqual(vars(nleEn[k]));
    }
  });
  it('word every override label and refusal the engine sends', () => {
    for (const code of ['user-override', 'op-override-reset', 'theme-kept-yours', 'nle-needs-engine', 'override-title', 'override-caption', 'override-caption-style', 'override-effect']) {
      expect(nleEn[`em.${code}` as keyof typeof nleEn], code).toBeTruthy();
    }
  });
});
