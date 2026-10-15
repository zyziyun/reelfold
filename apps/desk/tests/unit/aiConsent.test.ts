import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AiConsentService, parseConsent } from '../../src/main/aiConsent';
const dirs: string[] = [];
const services: AiConsentService[] = [];
function service(ask = vi.fn(async () => true)) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'rf-permission-test-')); dirs.push(dir);
  const file = path.join(dir, 'permissions.json');
  const s = new AiConsentService({ file, ask }); services.push(s);
  return { s, file, ask };
}
afterEach(() => { services.splice(0).forEach((s) => s.stop()); dirs.splice(0).forEach((d) => fs.rmSync(d, { recursive: true, force: true })); });
const request = { origin: 'https://api.example', purpose: 'analysis' as const };
describe('AI sharing permission', () => {
  it('accepts exact origins and fixed purposes, refuses secret/path/unknown fields', () => {
    expect(parseConsent(request)).toEqual(request);
    for (const origin of ['https://api.example/key', 'https://key@api.example', 'https://api.example?secret=x', 'file:///x', 'https://api.example/']) expect(parseConsent({ ...request, origin })).toBeNull();
    expect(parseConsent({ ...request, purpose: '__proto__' })).toBeNull();
  });
  it('serializes concurrent requests and remembers only explicitly allowed scopes', async () => {
    const { s, ask, file } = service();
    expect(await Promise.all([s.authorize(request), s.authorize(request)])).toEqual([true, true]);
    expect(ask).toHaveBeenCalledTimes(1);
    expect(await s.authorize({ ...request, origin: 'https://other.example' })).toBe(true);
    expect(await s.authorize({ ...request, purpose: 'transcription' })).toBe(true);
    expect(ask).toHaveBeenCalledTimes(3);
    const reopened = new AiConsentService({ file, ask }); services.push(reopened);
    expect(await reopened.authorize(request)).toBe(true);
    expect(ask).toHaveBeenCalledTimes(3);
    s.reset();
    expect(await s.authorize(request)).toBe(true);
    expect(ask).toHaveBeenCalledTimes(4);
  });
  it('never remembers a denial or a grant revoked while its dialog is open', async () => {
    const { s, file } = service(vi.fn(async () => false));
    expect(await s.authorize(request)).toBe(false);
    expect(fs.existsSync(file)).toBe(false);
    let resolve!: (v: boolean) => void;
    const pending = service(vi.fn(() => new Promise<boolean>((r) => { resolve = r; })));
    const granted = pending.s.authorize(request);
    await Promise.resolve(); pending.s.reset(); resolve(true);
    expect(await granted).toBe(false);
    expect(JSON.parse(fs.readFileSync(pending.file, 'utf8')).grants).toEqual([]);
  });
  it.skipIf(process.platform === 'win32')('authenticates real socket calls and refuses browser origins / invalid payloads', async () => {
    const { s, ask } = service(); await s.start();
    const post = (token: string, body: unknown, origin?: string) => new Promise<number>((resolve, reject) => {
      const req = http.request({ socketPath: s.socketPath!, path: '/consent', method: 'POST', headers: { authorization: `Bearer ${token}`, ...(origin ? { origin } : {}) } }, (res) => { res.resume(); res.on('end', () => resolve(res.statusCode!)); });
      req.on('error', reject); req.end(JSON.stringify(body));
    });
    expect(await post('wrong', request)).toBe(401);
    expect(await post(s.token, request, 'https://evil.example')).toBe(404);
    expect(await post(s.token, { ...request, purpose: 'secret' })).toBe(400);
    expect(ask).not.toHaveBeenCalled();
    expect(await post(s.token, request)).toBe(200);
    expect(ask).toHaveBeenCalledExactlyOnceWith(request);
  });
});
