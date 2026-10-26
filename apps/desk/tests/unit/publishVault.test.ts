import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { ApiVault } from '../../src/main/publish/api/vault';

const dirs: string[] = [];
const crypto = {
  isEncryptionAvailable: () => true,
  encryptString: (s: string) => Buffer.from(s),
  decryptString: (b: Buffer) => b.toString(),
};
function setup() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'reelfold-vault-'));
  dirs.push(dir);
  return { vault: new ApiVault(dir, crypto, 'darwin'), file: path.join(dir, 'publish-api.json') };
}
afterEach(() => dirs.splice(0).forEach(d => fs.rmSync(d, { recursive: true, force: true })));

describe('publishing credential persistence', () => {
  it.each(['{"youtube/main":', 'null', '[]', '{"youtube/main":42}'])('preserves unreadable store %s on updates and removals', raw => {
    const { vault, file } = setup();
    fs.writeFileSync(file, raw);
    expect(() => vault.set('youtube/new', { refreshToken: 'replacement' })).toThrow(/could not be read/i);
    expect(fs.readFileSync(file, 'utf8')).toBe(raw);
    expect(() => vault.set('youtube/main', null)).toThrow(/could not be read/i);
    expect(fs.readFileSync(file, 'utf8')).toBe(raw);
  });

  it('creates a new store and retains other accounts when editing one', () => {
    const { vault } = setup();
    vault.set('youtube/main', { refreshToken: 'original', connectedAt: 'today' });
    vault.set('youtube/second', { refreshToken: 'second' });
    vault.set('youtube/main', { refreshToken: 'refreshed' });
    expect(vault.get('youtube/main')).toEqual({ refreshToken: 'refreshed', connectedAt: 'today' });
    vault.set('youtube/main', null);
    expect(vault.get('youtube/second').refreshToken).toBe('second');
  });
});
