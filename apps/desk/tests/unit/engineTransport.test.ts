// The engine is reached over a Unix domain socket (no TCP port: the Mac App Store build has no network.server
// entitlement); the UI's app://desk/api requests are forwarded by main. Windows keeps 127.0.0.1 (no AF_UNIX in CPython).
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { engineFetch, engineSocketPath, forwardToEngine, MAX_SOCKET_PATH, type EngineTarget } from '../../src/main/engineTransport';
import { ENGINE_BASE, EngineClient } from '../../src/shared/engineClient';

const posix = process.platform !== 'win32';
let dir = '';
let target: EngineTarget;
let server: http.Server;
const seen: { method?: string; url?: string; headers: http.IncomingHttpHeaders; body: string }[] = [];
let streamClosed = false;

beforeAll(async () => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'rft-'));
  server = http.createServer((req, res) => {
    let body = '';
    req.on('data', (c) => (body += c));
    req.on('end', () => {
      seen.push({ method: req.method, url: req.url, headers: req.headers, body });
      if (req.url === '/api/stream') {
        res.writeHead(200, { 'content-type': 'text/event-stream' });
        res.write(': connected\n\n');
        res.write('event: status\ndata: {"type":"status","n":1}\n\n');
        res.on('close', () => (streamClosed = true));
        return;
      }
      if (req.url === '/api/none') return void res.writeHead(204).end();
      res.writeHead(req.headers.authorization === 'Bearer tok' ? 200 : 401, { 'content-type': 'application/json', 'set-cookie': ['a=1', 'b=2'] });
      res.end(JSON.stringify({ ok: req.headers.authorization === 'Bearer tok', method: req.method, url: req.url, body }));
    });
  });
  if (posix) {
    const sock = engineSocketPath('t', dir)!;
    await new Promise<void>((r) => server.listen(sock, r));
    target = { socketPath: sock };
  } else {
    await new Promise<void>((r) => server.listen(0, '127.0.0.1', r));
    target = { port: (server.address() as { port: number }).port };
  }
});

afterAll(() => {
  server.close();
  fs.rmSync(dir, { recursive: true, force: true });
});

describe('engine socket path', () => {
  it('is a fresh file in the temp folder on macOS / Linux, short enough for sun_path; Windows uses TCP', () => {
    const a = engineSocketPath('rf-engine', '/tmp', 'darwin')!;
    expect(a).toMatch(/^\/tmp\/rf-engine-[0-9a-f]{8}\.sock$/);
    expect(engineSocketPath('rf-engine', '/tmp', 'darwin')).not.toBe(a);
    expect(engineSocketPath('rf-engine', 'C:\\Temp', 'win32')).toBeNull();
    // a sandbox container's tmp with a long user name still fits; an absurd one is refused with a clear error
    expect(Buffer.byteLength(engineSocketPath('rf-engine', '/Users/me/Library/Containers/app.reelfold.desk/Data/tmp/' + 'x'.repeat(20), 'darwin')!)).toBeLessThanOrEqual(MAX_SOCKET_PATH);
    expect(() => engineSocketPath('rf-engine', '/x'.repeat(60), 'darwin')).toThrow(/too long/);
  });
});

describe("main's own client", () => {
  it('talks to the engine over the socket with the token, JSON in and out', async () => {
    const c = new EngineClient(ENGINE_BASE, 'tok', engineFetch(() => target));
    const r = await c.applyReview('abcdefabcdef', { decisions: {} } as never);
    expect(r).toMatchObject({ ok: true, method: 'POST', url: '/api/batches/abcdefabcdef/review/apply' });
    const last = seen.at(-1)!;
    expect(JSON.parse(last.body)).toEqual({ decisions: {} });
    expect(last.headers.authorization).toBe('Bearer tok');
    expect(last.headers.host).toBe(posix ? 'engine' : `127.0.0.1:${(target as { port: number }).port}`);
  });

  it('refuses other URLs and a stopped engine', async () => {
    await expect(engineFetch(() => target)('http://127.0.0.1:1/api/x')).rejects.toThrow(/not an engine URL/);
    await expect(engineFetch(() => null)(`${ENGINE_BASE}/api/health`)).rejects.toThrow(/not running/);
  });
});

describe('app://desk/api from the UI', () => {
  it('forwards method, path, query, body and the token; the answer keeps status and headers', async () => {
    const req = new Request(`${ENGINE_BASE}/api/events?n=5`, { method: 'POST', headers: { Authorization: 'Bearer tok', 'Content-Type': 'application/json', Origin: 'app://desk', Cookie: 'x=1' }, body: '{"a":1}' });
    const r = await forwardToEngine(target, req);
    expect(r.status).toBe(200);
    expect(await r.json()).toEqual({ ok: true, method: 'POST', url: '/api/events?n=5', body: '{"a":1}' });
    const last = seen.at(-1)!;
    expect(last.headers.origin).toBe('app://desk');
    expect(last.headers.cookie).toBeUndefined(); // only what the engine needs is passed on
    expect(r.headers.get('set-cookie')).toContain('a=1');
    const no = await forwardToEngine(target, new Request(`${ENGINE_BASE}/api/health`));
    expect(no.status).toBe(401);
    expect((await forwardToEngine(target, new Request(`${ENGINE_BASE}/api/none`, { headers: { Authorization: 'Bearer tok' } }))).status).toBe(204);
  });

  it('streams the event stream as it arrives, and closes the engine side when the UI stops reading', async () => {
    const r = await forwardToEngine(target, new Request(`${ENGINE_BASE}/api/stream`, { headers: { Authorization: 'Bearer tok' } }));
    const reader = r.body!.getReader();
    let text = '';
    while (!text.includes('"n":1')) text += new TextDecoder().decode((await reader.read()).value);
    expect(text).toContain(': connected');
    await reader.cancel();
    for (let i = 0; i < 50 && !streamClosed; i++) await new Promise((res) => setTimeout(res, 20));
    expect(streamClosed).toBe(true);
  });

  it('answers 503 / 502 when the engine is not there', async () => {
    expect((await forwardToEngine(null, new Request(`${ENGINE_BASE}/api/health`))).status).toBe(503);
    const gone = posix ? { socketPath: path.join(dir, 'gone.sock') } : { port: 9 };
    const r = await forwardToEngine(gone, new Request(`${ENGINE_BASE}/api/health`));
    expect(r.status).toBe(502);
    expect((await r.json()).error).toMatch(/engine unreachable/);
  });
});

describe('a burst of requests (All projects with 200+ projects)', () => {
  it.skipIf(!posix)('tries a connect the socket refused (backlog full) again instead of failing it', async () => {
    const { spawn } = await import('node:child_process');
    const sock = engineSocketPath('b', dir)!;
    // a socket that is bound but not listening refuses every connect at once (ECONNREFUSED), like a full backlog
    const py = spawn('python3', ['-c', `import socket,sys,time\ns=socket.socket(socket.AF_UNIX)\ns.bind(sys.argv[1])\nprint('bound',flush=True)\ntime.sleep(0.4)`, sock]);
    await new Promise<void>((r) => py.stdout.once('data', () => r()));
    const late = http.createServer((_q, res) => res.writeHead(200, { 'content-type': 'application/json' }).end('{"ok":true}'));
    py.once('exit', () => {
      fs.rmSync(sock, { force: true });
      late.listen(sock);
    });
    const t0 = Date.now();
    const r = await engineFetch(() => ({ socketPath: sock }))(`${ENGINE_BASE}/api/health`);
    expect(r.status).toBe(200);
    expect(await r.json()).toEqual({ ok: true });
    expect(Date.now() - t0).toBeGreaterThanOrEqual(300);
    late.close();
  });

  it('tries a refused connect again over 127.0.0.1 too (Windows: a full backlog refuses there as well)', async () => {
    // a free port with nothing listening refuses every connect (ECONNREFUSED); the engine starts listening a beat later
    const probe = http.createServer();
    await new Promise<void>((r) => probe.listen(0, '127.0.0.1', r));
    const port = (probe.address() as { port: number }).port;
    await new Promise<void>((r) => probe.close(() => r()));
    const late = http.createServer((_q, res) => res.writeHead(200, { 'content-type': 'application/json' }).end('{"ok":true}'));
    setTimeout(() => late.listen(port, '127.0.0.1'), 400);
    const r = await forwardToEngine({ port }, new Request(`${ENGINE_BASE}/api/health`));
    expect(r.status).toBe(200);
    expect(await r.json()).toEqual({ ok: true });
    late.close();
  });
});
