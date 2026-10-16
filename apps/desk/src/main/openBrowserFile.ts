// An HTML document handler may differ from the browser used for sign-in. Use the HTTPS handler explicitly.
import { app, shell } from 'electron';
import { execFile, spawn } from 'node:child_process';
import { promisify } from 'node:util';
import { pathToFileURL } from 'node:url';

interface BrowserFileDeps {
  platform: string;
  resolve: () => Promise<{ path: string }>;
  launch: (command: string, args: string[], wait: boolean) => Promise<void>;
  fallback: (url: string) => Promise<void>;
}
const run = promisify(execFile);
const launch: BrowserFileDeps['launch'] = async (command, args, wait) => {
  if (wait) { await run(command, args); return; }
  await new Promise<void>((resolve, reject) => {
    const child = spawn(command, args, { detached: true, stdio: 'ignore', windowsHide: false });
    child.once('error', reject); child.once('spawn', () => { child.unref(); resolve(); });
  });
};
export async function openBrowserFile(file: string, deps: BrowserFileDeps = {
  platform: process.platform,
  resolve: () => app.getApplicationInfoForProtocol('https://'),
  launch,
  fallback: (url) => shell.openExternal(url),
}): Promise<void> {
  const url = pathToFileURL(file).href;
  try {
    const browser = await deps.resolve();
    if (!browser.path) throw new Error('No default browser');
    if (deps.platform === 'darwin') {
      const bundle = browser.path.match(/^(.+\.app)(?:\/|$)/)?.[1] ?? browser.path;
      await deps.launch('/usr/bin/open', ['-a', bundle, url], true);
    } else if (deps.platform === 'win32') await deps.launch(browser.path, [url], false);
    else throw new Error('Use the OS file handler');
  } catch { await deps.fallback(url); }
}
