// A real null through the JS API: CLI -c.mas.identity=null becomes the string "null".
// Packaging errors must propagate; the presence of a partly written .app is insufficient.
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { Arch, Platform, build } from 'electron-builder';
const require = createRequire(import.meta.url);
const config = require('../../electron-builder.config.cjs');
await build({
  projectDir: fileURLToPath(new URL('../..', import.meta.url)),
  targets: Platform.MAC.createTarget('mas', Arch.arm64),
  publish: 'never',
  config: { ...config, mas: { ...config.mas, identity: null } },
});
