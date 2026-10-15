import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import { FillControl, FillRuns } from '../../src/main/publish/fillControl';
import { validateIpc } from '../../src/shared/ipc';
import { guardedSend, runFill, type Send } from '../../src/main/publish/cdpFill';
import { parseAdapter, type Adapter } from '../../src/shared/publish/adapterSchema';
import { planFill } from '../../src/shared/publish/fillPlan';
import { parsePostCopy } from '../../src/shared/publish/postCopy';

const load = (f: string): Adapter => {
  const r = parseAdapter(JSON.parse(fs.readFileSync(path.resolve(__dirname, '../../adapters', f), 'utf8')));
  if (!r.ok) throw new Error(r.error);
  return r.adapter;
};

const copy = parsePostCopy('第 1 集：批量剪口播\n\n第一行\n第二行\n\n#口播 #剪辑\n', '第 1 集：批量剪口播');

/** A fake page: selectors present in `dom` resolve to objectIds; records every CDP call. */
function fakePage(dom: Record<string, { file?: boolean }>, frames = 1) {
  const calls: { method: string; params?: Record<string, unknown> }[] = [];
  const objs = new Map<string, string>();
  const send: Send = async (method, params) => {
    calls.push({ method, params });
    switch (method) {
      case 'Page.getFrameTree': {
        const child = Array.from({ length: frames - 1 }, (_, i) => ({ frame: { id: `f${i + 1}` } }));
        return { frameTree: { frame: { id: 'f0' }, childFrames: child } };
      }
      case 'Page.createIsolatedWorld':
        return { executionContextId: 1 };
      case 'Runtime.evaluate': {
        const sels: string[] = (JSON.parse(/const SELS = (.*);\n/.exec(String(params!.expression))![1]) as { css: string }[]).map((p) => p.css);
        const hit = sels.find((s) => s in dom);
        if (!hit) return { result: { type: 'object', subtype: 'null' } };
        const id = `obj:${hit}`;
        objs.set(id, hit);
        return { result: { type: 'object', subtype: 'node', objectId: id } };
      }
      case 'Runtime.callFunctionOn': {
        const sel = objs.get(String(params!.objectId))!;
        if (String(params!.functionDeclaration).includes("this.type === 'file'")) return { result: { value: !!dom[sel].file } };
        return { result: { value: true } };
      }
      default:
        return {};
    }
  };
  return { send, calls };
}

describe('assisted fill plan', () => {
  it('parses post.md into title / description / tags', () => {
    expect(copy).toEqual({ title: '第 1 集：批量剪口播', description: '第一行\n第二行', tags: ['口播', '剪辑'] });
    expect(parsePostCopy('标题\n\n正文\n\n标签：a, b', '').tags).toEqual(['a', 'b']);
  });

  it('never contains a click step; publish is only highlighted', () => {
    for (const f of ['tiktok.json', 'youtube-studio.json']) {
      const steps = planFill(load(f), { videoPath: '/p/v.mp4', coverPath: '/p/c.jpg', copy });
      expect(steps.every((s) => ['files', 'text', 'highlight'].includes(s.kind))).toBe(true);
      expect(steps.filter((s) => s.kind === 'highlight').map((s) => s.field)).toEqual(['publish']);
      expect(steps[0]).toMatchObject({ kind: 'files', field: 'file', paths: ['/p/v.mp4'] });
    }
  });

  it('TikTok: caption = description + hashtags, no title, no cover', () => {
    const steps = planFill(load('tiktok.json'), { videoPath: '/p/v.mp4', coverPath: '/p/c.jpg', copy });
    const desc = steps.find((s) => s.field === 'description');
    expect(desc && desc.kind === 'text' && desc.text).toBe('第一行\n第二行\n\n#口播 #剪辑');
    expect(steps.some((s) => s.field === 'title' || s.field === 'cover')).toBe(false);
  });

  it('YouTube: title clipped to 100 chars, cover set when present', () => {
    const long = { ...copy, title: 'x'.repeat(150) };
    const steps = planFill(load('youtube-studio.json'), { videoPath: '/p/v.mp4', coverPath: '/p/c.jpg', copy: long });
    const title = steps.find((s) => s.field === 'title');
    expect(title && title.kind === 'text' && Array.from(title.text).length).toBe(100);
    expect(steps.find((s) => s.field === 'cover')).toMatchObject({ kind: 'files', paths: ['/p/c.jpg'] });
  });
});

describe('CDP executor', () => {
  it('blocks every CDP method assisted fill does not need', async () => {
    const send = guardedSend(async () => ({}));
    await expect(send('Input.dispatchMouseEvent', { type: 'mousePressed' })).rejects.toThrow(/not allowed/);
    await expect(send('Network.getCookies')).rejects.toThrow(/not allowed/);
    await expect(send('Storage.getCookies')).rejects.toThrow(/not allowed/);
    await expect(send('Input.dispatchKeyEvent', { key: 'Tab' })).rejects.toThrow(/Enter/);
    await expect(send('DOM.setFileInputFiles', {})).resolves.toEqual({});
  });

  it('sets the file, types the caption, highlights publish, clicks nothing', async () => {
    const a = load('tiktok.json');
    const page = fakePage({
      'input[type="file"][accept*="video"]': { file: true },
      'div.public-DraftEditor-content[contenteditable="true"]': {},
      'button[data-e2e="post_video_button"]': {},
    });
    const steps = planFill(a, { videoPath: '/p/v.mp4', copy });
    const res = await runFill(page.send, steps, { sleep: async () => undefined });
    expect(res.map((r) => [r.field, r.status])).toEqual([
      ['file', 'ok'],
      ['description', 'ok'],
      ['publish', 'ok'],
    ]);
    const files = page.calls.find((c) => c.method === 'DOM.setFileInputFiles');
    expect(files?.params).toMatchObject({ files: ['/p/v.mp4'] });
    const typed = page.calls.filter((c) => c.method === 'Input.insertText').map((c) => c.params!.text);
    expect(typed).toEqual(['第一行', '第二行', '#口播 #剪辑']);
    expect(page.calls.some((c) => c.method === 'Input.dispatchMouseEvent')).toBe(false);
    expect(page.calls.filter((c) => c.method === 'Runtime.callFunctionOn').some((c) => /\.click\(/.test(String(c.params!.functionDeclaration)))).toBe(false);
  });

  it('stops when the file input is missing (not logged in / page changed)', async () => {
    const page = fakePage({});
    const steps = planFill(load('tiktok.json'), { videoPath: '/p/v.mp4', copy }).map((s) => ({ ...s, timeoutMs: 0 }));
    const res = await runFill(page.send, steps, { sleep: async () => undefined });
    expect(res).toEqual([{ field: 'file', kind: 'files', status: 'not-found', detail: steps[0].selectors[0] }]);
  });

  it('refuses to set files on something that is not a file input', async () => {
    const page = fakePage({ 'input[type="file"][accept*="video"]': { file: false } });
    const steps = planFill(load('tiktok.json'), { videoPath: '/p/v.mp4', copy }).map((s) => ({ ...s, timeoutMs: 0 }));
    const res = await runFill(page.send, steps, { sleep: async () => undefined });
    expect(res[0]).toMatchObject({ status: 'error' });
    expect(page.calls.some((c) => c.method === 'DOM.setFileInputFiles')).toBe(false);
  });

  it('looks in child frames too', async () => {
    const page = fakePage({ 'input[type="file"]': { file: true } }, 3);
    const steps = planFill(load('tiktok.json'), { videoPath: '/p/v.mp4', copy }).slice(0, 1);
    const res = await runFill(page.send, steps, { sleep: async () => undefined });
    expect(res[0].status).toBe('ok');
  });
});

describe('assisted browser takeover', () => {
  it('accepts only a real post identifier and a defined control action', () => {
    expect(validateIpc('publish:controlFill', { postId: 'a'.repeat(12), action: 'pause' })).toEqual({ postId: 'a'.repeat(12), action: 'pause' });
    expect(() => validateIpc('publish:controlFill', { postId: '*', action: 'cancel' })).toThrow();
    expect(() => validateIpc('publish:controlFill', { postId: 'a'.repeat(12), action: 'execute' })).toThrow();
  });
  const readyPage = () => fakePage({
    'input[type="file"][accept*="video"]': { file: true },
    'div.public-DraftEditor-content[contenteditable="true"]': {},
    'button[data-e2e="post_video_button"]': {},
  });
  it('pauses after the file, issues no further commands, resumes without repeating the file', async () => {
    const page = readyPage();
    const control = new FillControl();
    let reached!: () => void;
    const paused = new Promise<void>((resolve) => { reached = resolve; });
    const events: string[] = [];
    const job = runFill(page.send, planFill(load('tiktok.json'), { videoPath: '/p/v.mp4', copy }), {
      control, sleep: async () => undefined, onStep: (r) => {
        events.push(`${r.field}:${r.status}`);
        if (r.field === 'file' && r.status === 'ok') { control.pause(); reached(); }
      },
    });
    await paused;
    const count = page.calls.length;
    await new Promise((r) => setTimeout(r, 15));
    expect(page.calls).toHaveLength(count);
    expect(page.calls.some((c) => c.method === 'Input.insertText')).toBe(false);
    control.resume();
    expect((await job).every((r) => r.status === 'ok')).toBe(true);
    expect(page.calls.filter((c) => c.method === 'DOM.setFileInputFiles')).toHaveLength(1);
    expect(events.slice(0, 4)).toEqual(['file:running', 'file:ok', 'description:running', 'description:ok']);
  });
  it('cancels a paused run without writing text, and rejects a different post’s control request', async () => {
    const runs = new FillRuns();
    const page = readyPage();
    let reached!: () => void;
    const paused = new Promise<void>((resolve) => { reached = resolve; });
    const job = runs.run('post-a', (control) => runFill(page.send, planFill(load('tiktok.json'), { videoPath: '/p/v.mp4', copy }), {
      control, onStep: (r) => { if (r.field === 'file' && r.status === 'ok') { control.pause(); reached(); } },
    }));
    await paused;
    expect(runs.command('post-b', 'cancel')).toBe(false);
    expect(runs.command('post-a', 'cancel')).toBe(true);
    expect(await job).toEqual({ ok: false, reason: 'cancelled' });
    expect(page.calls.some((c) => c.method === 'Input.insertText')).toBe(false);
    expect(page.calls.at(-1)).toEqual({ method: 'Emulation.setFocusEmulationEnabled', params: { enabled: false } });
  });
  it('a superseded run cannot clear the newer run’s controls', async () => {
    const runs = new FillRuns();
    const old = runs.run('old', async (c) => { c.pause(); await c.checkpoint(); return 'old'; });
    let reached!: () => void;
    const nextPaused = new Promise<void>((r) => { reached = r; });
    const next = runs.run('next', async (c) => { c.pause(); reached(); await c.checkpoint(); return 'next'; });
    expect(await old).toEqual({ ok: false, reason: 'cancelled' });
    await nextPaused;
    expect(runs.command('next', 'resume')).toBe(true);
    expect(await next).toBe('next');
    expect(runs.command('next', 'pause')).toBe(false);
  });
  it('time spent checking the page while paused consumes no selector timeout', () => {
    let now = 100;
    const clock = vi.spyOn(performance, 'now').mockImplementation(() => now);
    try {
      const c = new FillControl();
      c.pause(); now += 60_000;
      expect(c.now()).toBe(100);
      c.resume(); now += 10;
      expect(c.now()).toBe(110);
    } finally { clock.mockRestore(); }
  });
  it('a late completion after takeover cannot report a successful automatic fill', async () => {
    const runs = new FillRuns();
    let entered!: () => void, finish!: () => void;
    const started = new Promise<void>((r) => { entered = r; });
    const pending = new Promise<void>((r) => { finish = r; });
    const job = runs.run('post', async () => { entered(); await pending; return { ok: true }; });
    await started;
    runs.command('post', 'cancel');
    finish();
    expect(await job).toEqual({ ok: false, reason: 'cancelled' });
  });
});

it('waits for a cancelled browser run to detach before starting its replacement', async () => {
  const runs = new FillRuns();
  let entered!: () => void;
  const started = new Promise<void>((r) => { entered = r; });
  let detached!: () => void;
  const cleanup = new Promise<void>((r) => { detached = r; });
  const old = runs.run('old', async (c) => {
    c.pause(); entered();
    try { await c.checkpoint(); } finally { await cleanup; }
  });
  await started;
  let replacementStarted = false;
  const next = runs.run('next', async () => { replacementStarted = true; return 'ready'; });
  await new Promise((r) => setTimeout(r, 10));
  expect(replacementStarted).toBe(false);
  detached();
  expect(await old).toEqual({ ok: false, reason: 'cancelled' });
  expect(await next).toBe('ready');
});
