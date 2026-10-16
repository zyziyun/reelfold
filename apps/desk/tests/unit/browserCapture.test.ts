import { createHash } from 'node:crypto';
import { describe, expect, it, vi } from 'vitest';
vi.mock('electron', () => ({ app: {}, shell: {} }));
import { openBrowserFile } from '../../src/main/openBrowserFile';
import { browserCapturePage, safeBrowserSource } from '../../src/main/browserCapture';
import { validateIpc } from '../../src/shared/ipc';

describe('local browser passage recording', () => {
  it('accepts only a regular HTTPS source and gives no arbitrary file-opening IPC', () => {
    expect(safeBrowserSource('https://www.youtube.com/watch?v=6WaeGfLnRvc')).toContain('youtube.com');
    for (const value of ['javascript:alert(1)', 'file:///etc/passwd', 'https://me:secret@example.com/', 'http://example.com/']) expect(safeBrowserSource(value)).toBeNull();
    expect(validateIpc('rec:browserCapture', { lang: 'zh' })).toEqual({ lang: 'zh' });
    expect(() => validateIpc('rec:browserCapture', { lang: 'zh', path: '/private/file.html' })).toThrow();
    expect(() => validateIpc('rec:browserCapture', { lang: 'ar' })).toThrow();
  });
  it('uses the normal browser without creating or reading a browser profile', async () => {
    const launch = vi.fn(async () => undefined), fallback = vi.fn(async () => undefined);
    const file = process.platform === 'win32' ? 'C:\\recordings\\capture.html' : '/tmp/recordings/capture.html';
    await openBrowserFile(file, { platform: 'darwin', resolve: async () => ({ path: '/Applications/Chrome.app/Contents/MacOS/Chrome' }), launch, fallback });
    expect(launch).toHaveBeenLastCalledWith('/usr/bin/open', ['-a', '/Applications/Chrome.app', expect.stringMatching(/^file:/)], true);
    await openBrowserFile(file, { platform: 'win32', resolve: async () => ({ path: 'C:\\Browser\\browser.exe' }), launch, fallback });
    expect(launch).toHaveBeenLastCalledWith('C:\\Browser\\browser.exe', [expect.stringMatching(/^file:/)], false);
    expect(fallback).not.toHaveBeenCalled();
    await openBrowserFile(file, { platform: 'darwin', resolve: async () => { throw new Error('No protocol registration'); }, launch, fallback });
    expect(fallback).toHaveBeenCalledOnce();
  });
  it('keeps capture offline, hash-limits the script, and renders source URLs as data', () => {
    const html = browserCapturePage('en', 'https://example.com/</script><img>');
    const script = html.match(/<script>([\s\S]*)<\/script>/)![1];
    expect(html.match(/<script>/g)).toHaveLength(1);
    expect(html).toContain(`script-src 'sha256-${createHash('sha256').update(script).digest('base64')}'`);
    expect(html).toContain("connect-src 'none'");
    expect(html).not.toContain('<img>');
    expect(script).toContain("systemAudio: 'exclude'");
    expect(script).toContain("selfBrowserSurface: 'exclude'");
    expect(script).toContain('getAudioTracks().length');
    expect(script).not.toMatch(/fetch\(|WebSocket|XMLHttpRequest/);
  });
});
