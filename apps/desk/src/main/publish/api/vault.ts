// OAuth clients and tokens for the official posting APIs, encrypted with Electron safeStorage (the key lives in the
// OS keychain, like the AI API keys in secrets.ts). Only ciphertext is written, to <userData>/publish-api.json;
// nothing here ever goes to the renderer, a log or the engine. No keychain (Linux without a keyring) = refused.
import fs from 'node:fs';
import path from 'node:path';
import type { CaptionArtifact, YtPublishResult } from '../../../shared/publish/apiPlatforms';
import type { Crypto } from '../../secrets';

export interface ApiSecret {
  captionTracks?: CaptionArtifact[];
  /** Resumable URI stays encrypted alongside credentials, never in the scheduler journal. */
  uploadSession?: { file?: string; sha256?: string; url: string; size: number; account: string; privacy: string; publishAt: string | null; followups: boolean };
  uploadReceipt?: { account: string; result: YtPublishResult };
  clientId?: string;
  clientSecret?: string;
  refreshToken?: string;
  scope?: string;
  connectedAt?: string;
  /** YouTube: which OAuth client signs in (Reelfold's, built in at build time, or hers) */
  source?: 'reelfold' | 'own';
  /** the channel the token belongs to (shown, never a secret) */
  channel?: { id: string; title: string };
}

export class ApiVault {
  private file: string;

  constructor(
    dir: string,
    private crypto: Crypto,
    private platform: NodeJS.Platform = process.platform,
  ) {
    this.file = path.join(dir, 'publish-api.json');
  }

  keychain(): boolean {
    if (!this.crypto.isEncryptionAvailable()) return false;
    return !(this.platform === 'linux' && this.crypto.getSelectedStorageBackend?.() === 'basic_text');
  }

  private readAll(forWrite = false): Record<string, string> {
    try {
      const raw = JSON.parse(fs.readFileSync(this.file, 'utf8'));
      if (!raw || typeof raw !== 'object' || Array.isArray(raw) ||
          Object.values(raw).some(value => typeof value !== 'string')) throw new Error('invalid credential store');
      return raw;
    } catch (error) {
      // Only a genuinely absent store can be initialized. A parse/read failure
      // must not erase other accounts or durable upload recovery information.
      if (forWrite && (error as NodeJS.ErrnoException).code !== 'ENOENT') {
        throw new Error('Publishing credentials could not be read. Existing saved accounts were not changed.', { cause: error });
      }
      return {};
    }
  }

  /** the stored entries (names only) */
  ids(): string[] {
    return Object.keys(this.readAll());
  }

  get(id: string, strict = false): ApiSecret {
    const v = this.readAll(strict)[id];
    if (v === undefined) return {};
    try {
      if (!this.keychain()) throw new Error('keychain unavailable');
      const value = JSON.parse(this.crypto.decryptString(Buffer.from(v, 'base64')));
      if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('invalid saved entry');
      return value as ApiSecret;
    } catch (error) {
      if (strict) throw new Error('Saved publishing information could not be decrypted. It was not changed.', { cause: error });
      return {}; // Account status remains readable when the keychain is unavailable.
    }
  }

  set(id: string, patch: ApiSecret | null) {
    if (patch && !this.keychain()) throw new Error('the OS keychain is not available: nothing is stored');
    const all = this.readAll(true);
    if (patch === null) delete all[id];
    else all[id] = this.crypto.encryptString(JSON.stringify({ ...this.get(id, true), ...patch })).toString('base64');
    fs.mkdirSync(path.dirname(this.file), { recursive: true });
    const tmp = this.file + '.tmp';
    fs.writeFileSync(tmp, JSON.stringify(all), { mode: 0o600 });
    fs.renameSync(tmp, this.file);
  }
}
