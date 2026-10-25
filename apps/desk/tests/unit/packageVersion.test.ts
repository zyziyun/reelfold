import { createRequire } from 'node:module';
import { expect, it } from 'vitest';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
const require = createRequire(import.meta.url);
const config = require('../../electron-builder.config.cjs');
const pack = (version: string) => config.beforePack({ packager: { appInfo: { version } } });
it('rejects a numeric hash with leading zero before packaging', async () => {
  await expect(pack('0.2.9-local.09004414')).rejects.toThrow('Invalid app version');
  await expect(pack('0.2.9-local.g09004414')).resolves.toBeUndefined();
  await expect(pack('0.2.9')).resolves.toBeUndefined();
});

it('validates the real hook context when extraMetadata is absent', async () => {
  await expect(config.beforePack({ packager: { appInfo: { version: '0.2.8' }, config: {} } })).resolves.toBeUndefined();
  await expect(config.beforePack({ packager: { appInfo: { version: '0.2.9-local.01' }, config: {} } })).rejects.toThrow('Invalid app version');
});

it('writes the resolved update feed for local directory installs before signing', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'reelfold-feed-'));
  const { load } = require('js-yaml');
  const packager = {
    config, platformSpecificBuildOptions: {},
    appInfo: { updaterCacheDirName: 'video-studio-desk-updater' },
    info: { config, appInfo: { channel: 'local' } },
    expandMacro: (value: string) => value,
    getResourcesDir: () => dir,
  };
  try {
    await config.afterPack({ electronPlatformName: 'darwin', targets: [{ name: 'dir' }], packager, appOutDir: dir, arch: 3 });
    expect(load(await fs.readFile(path.join(dir, 'app-update.yml'), 'utf8'))).toMatchObject({
      provider: 'github', owner: 'zyziyun', repo: 'reelfold', updaterCacheDirName: 'video-studio-desk-updater',
    });
    await fs.unlink(path.join(dir, 'app-update.yml'));
    // Store builds and release artifacts retain their own packaging behavior.
    for (const [platform, target] of [['mas', 'dir'], ['win32', 'dir'], ['darwin', 'dmg'], ['darwin', 'zip']]) {
      await config.afterPack({ electronPlatformName: platform, targets: [{ name: target }], packager, appOutDir: dir });
      expect(await fs.readdir(dir)).toEqual([]);
    }
    packager.platformSpecificBuildOptions = { publish: null };
    await config.afterPack({ electronPlatformName: 'darwin', targets: [{ name: 'dir' }], packager, appOutDir: dir });
    expect(await fs.readdir(dir)).toEqual([]);
  } finally {
    await fs.rm(dir, { recursive: true, force: true });
  }
});
