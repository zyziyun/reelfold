/* global process, console */
// Stands in for an old install (Daycut / video-studio desk) in tests/e2e/migration.spec.ts: under the old app name
// (= the old keychain key "<name> Safe Storage"), writes a profile with settings, an API key encrypted by
// safeStorage and a login cookie in a persistent publish partition, then quits.
//   electron legacyProfile.mjs <appData> <legacy name>
import { app, safeStorage, session } from 'electron';
import { Buffer } from 'node:buffer';
import fs from 'node:fs';
import path from 'node:path';

const [appData, name] = process.argv.slice(-2);
const checkSecret = process.argv.includes('--check-secret');
const dir = checkSecret ? appData : path.join(appData, name);
const secret = 'legacy-test-key-0123456789';
app.setName(name);
app.setPath('userData', dir);
app.whenReady().then(async () => {
  try {
    if (checkSecret) {
      const encrypted = JSON.parse(fs.readFileSync(path.join(dir, 'secrets.json'), 'utf8')).openai;
      let matches = false;
      try { matches = safeStorage.decryptString(Buffer.from(encrypted, 'base64')) === secret; } catch { /* wrong key */ }
      console.log(`LEGACY_SECRET_MATCH:${matches}`);
      return;
    }
    fs.mkdirSync(path.join(dir, 'assets', 'chromium', '1'), { recursive: true });
    fs.writeFileSync(path.join(dir, 'settings.json'), JSON.stringify({ lang: 'fr', accent: 'red', firstRunDone: true, accounts: [{ platform: 'douyin', name: 'main' }] }));
    fs.writeFileSync(path.join(dir, 'secrets.json'), JSON.stringify({ openai: safeStorage.encryptString(secret).toString('base64') }));
    fs.writeFileSync(path.join(dir, 'assets', 'installed.json'), JSON.stringify({ chromium: { root: path.join(dir, 'assets', 'chromium', '1'), sha256: [] } }));
    const ses = session.fromPartition('persist:douyin-main');
    await ses.cookies.set({ url: 'https://creator.douyin.com', name: 'sessionid', value: 'legacy-cookie-value', expirationDate: Date.now() / 1000 + 86400 });
    await ses.cookies.flushStore();
    console.log('LEGACY_PROFILE_OK');
  } catch (e) {
    console.error('LEGACY_PROFILE_FAIL', e);
    process.exitCode = 1;
  }
  finally { app.quit(); }
});
