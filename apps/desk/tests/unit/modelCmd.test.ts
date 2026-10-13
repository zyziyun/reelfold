// `/model <words>` (lib/modelCmd): her words resolve against the models known now (the built-in Claude list) without
// waiting on the full model lists - a slow probe of every provider (local servers, CLIs) once held `/model 5.5` up
// for 5+ s with nothing on screen; only words that match nothing wait for the lists and try again.
import { describe, expect, it, vi } from 'vitest';

// a fresh store per test (the lists are loaded once per app run)
const fresh = async () => {
  vi.resetModules();
  return (await import('../../src/renderer/src/lib/modelCmd')).soonOrListed;
};

describe('soonOrListed', () => {
  it('answers at once from what is known, never waiting on the lists', async () => {
    const w = globalThis as unknown as { window?: { desk?: unknown } };
    const had = w.window;
    w.window = { desk: { ai: { models: () => new Promise(() => undefined) } } }; // the lists never come
    try {
      const soonOrListed = await fresh();
      const find = vi.fn(() => 'opus-5-5');
      await expect(soonOrListed(find)).resolves.toBe('opus-5-5');
      expect(find).toHaveBeenCalledTimes(1);
    } finally {
      w.window = had;
    }
  });
  it('words that match nothing yet: waits for the lists, then tries again', async () => {
    const w = globalThis as unknown as { window?: { desk?: unknown } };
    const had = w.window;
    let listed = false;
    const models = () => new Promise((r) => setTimeout(() => ((listed = true), r({ providers: [] })), 10));
    w.window = { desk: { ai: { models } } };
    try {
      const soonOrListed = await fresh();
      const find = vi.fn(() => (listed ? 'gpt-6-luna' : null));
      await expect(soonOrListed(find)).resolves.toBe('gpt-6-luna');
      expect(find).toHaveBeenCalledTimes(2);
    } finally {
      w.window = had;
    }
  });
});
