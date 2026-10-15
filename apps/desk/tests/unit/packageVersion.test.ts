import { createRequire } from 'node:module';
import { expect, it } from 'vitest';
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
