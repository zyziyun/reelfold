// Source-engine CI uses the same pinned, hash-checked font files as the App.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { download, ROOT } from './common.mjs';

const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, 'packaging', 'assets.json'), 'utf8'));
const core = manifest.groups.find((g) => g.id === 'core');
const cache = process.env.VSTUDIO_CACHE || path.join(os.homedir(), '.cache', 'video-studio');
for (const file of core.files.filter((f) => f.dest.startsWith('fonts/') && /\.(?:otf|ttf)$/.test(f.dest))) {
  await download(file.url, path.join(cache, file.dest), file.sha256);
}
