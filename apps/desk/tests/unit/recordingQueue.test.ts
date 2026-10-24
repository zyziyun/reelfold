import { describe, expect, it, vi } from 'vitest';
import { recordingQueue } from '../../src/renderer/src/create/record/recordingQueue';

describe('recording chunk queue', () => {
  it('retains failed and later chunks, then retries them in order', async () => {
    const errors = vi.fn();
    const queue = recordingQueue(errors);
    const saved: number[] = [];
    let diskFull = true;
    queue.add(async () => { saved.push(0); });
    queue.add(async () => { if (diskFull) throw new Error('disk full'); saved.push(1); });
    queue.add(async () => { saved.push(2); });
    await expect(queue.flush()).rejects.toThrow('disk full');
    expect(saved).toEqual([0]);
    expect(errors).toHaveBeenCalled();
    diskFull = false;
    await queue.flush();
    await queue.flush();
    expect(saved).toEqual([0, 1, 2]);
  });
  it('drains final data enqueued while a write is waiting', async () => {
    let release!: () => void;
    const held = new Promise<void>(resolve => { release = resolve; });
    const saved: number[] = [];
    const queue = recordingQueue(() => {});
    queue.add(async () => { await held; saved.push(0); });
    const done = queue.flush();
    queue.add(async () => { saved.push(1); });
    release();
    await done;
    expect(saved).toEqual([0, 1]);
  });
});
