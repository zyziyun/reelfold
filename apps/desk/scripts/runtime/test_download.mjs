import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { download } from './common.mjs';

function fixture(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'runtime-download-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  return path.join(dir, 'asset');
}
function fastRetries(t) {
  const timer = globalThis.setTimeout;
  t.mock.method(globalThis, 'setTimeout', (fn, ms, ...args) =>
    timer(fn, ms === 5000 || ms === 10000 ? 0 : ms, ...args));
}
const digest = (value) => crypto.createHash('sha256').update(value).digest('hex');

test('writes and verifies bytes, then reuses the verified file offline', async (t) => {
  const dest = fixture(t);
  const bytes = Buffer.alloc(2 * 1024 * 1024, 71);
  let requests = 0;
  t.mock.method(globalThis, 'fetch', async () => { requests++; return new Response(bytes); });
  await download('https://fixture.invalid/asset', dest, digest(bytes));
  assert.deepEqual(fs.readFileSync(dest), bytes);
  assert.equal(fs.existsSync(`${dest}.part`), false);
  await download('https://fixture.invalid/asset', dest, digest(bytes));
  assert.equal(requests, 1);
});

test('rejects disk errors through the download promise without crashing', async (t) => {
  const dest = fixture(t);
  fs.mkdirSync(`${dest}.part`);
  fastRetries(t);
  let requests = 0;
  t.mock.method(globalThis, 'fetch', async () => { requests++; return new Response('asset'); });
  await assert.rejects(download('https://fixture.invalid/asset', dest), { code: 'EISDIR' });
  assert.equal(requests, 3);
  assert.equal(fs.existsSync(dest), false);
});

test('retries an interrupted body without keeping partial bytes', async (t) => {
  const dest = fixture(t);
  fastRetries(t);
  let requests = 0;
  t.mock.method(globalThis, 'fetch', async () => {
    if (++requests > 1) return new Response('complete');
    return new Response(new ReadableStream({ start(controller) {
      controller.enqueue(new TextEncoder().encode('partial'));
      controller.error(new Error('connection lost'));
    } }));
  });
  await download('https://fixture.invalid/asset', dest, digest('complete'));
  assert.equal(fs.readFileSync(dest, 'utf8'), 'complete');
  assert.equal(requests, 2);
});

test('checksum mismatch is terminal and never promotes the partial file', async (t) => {
  const dest = fixture(t);
  let requests = 0;
  t.mock.method(globalThis, 'fetch', async () => { requests++; return new Response('wrong'); });
  await assert.rejects(download('https://fixture.invalid/asset', dest, digest('right')), /checksum mismatch/);
  assert.equal(requests, 1);
  assert.equal(fs.existsSync(dest), false);
  assert.equal(fs.existsSync(`${dest}.part`), false);
});
