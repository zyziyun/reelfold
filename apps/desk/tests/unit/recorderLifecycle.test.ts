import { describe, expect, it, vi } from 'vitest';
import { recorderLifecycle } from '../../src/renderer/src/create/record/recorderLifecycle';

function device() {
  const events = new EventTarget();
  const native = Object.assign(events, {
    state: 'inactive' as RecordingState,
    start: vi.fn(() => { native.state = 'recording'; }),
    stop: vi.fn(() => { native.state = 'inactive'; }),
  });
  return { native, lifecycle: recorderLifecycle(native as unknown as MediaRecorder) };
}

describe('native recorder completion', () => {
  it('waits for stop delivery even when the input already made it inactive', async () => {
    const { native, lifecycle } = device();
    lifecycle.start(1000);
    native.state = 'inactive';
    const done = vi.fn();
    const saving = lifecycle.stop().then(done);
    await Promise.resolve();
    expect(done).not.toHaveBeenCalled();
    native.dispatchEvent(new Event('stop'));
    await saving;
    expect(done).toHaveBeenCalledOnce();
    expect(native.stop).not.toHaveBeenCalled();
  });

  it('shares completion across repeated stops and remembers an earlier stop event', async () => {
    const { native, lifecycle } = device();
    lifecycle.start();
    const first = lifecycle.stop();
    expect(lifecycle.stop()).toBe(first);
    expect(native.stop).toHaveBeenCalledOnce();
    native.dispatchEvent(new Event('stop'));
    await first;
    await lifecycle.stop();
    expect(native.stop).toHaveBeenCalledOnce();
  });

  it('does not wait forever when start failed or was never called', async () => {
    const { native, lifecycle } = device();
    await lifecycle.stop();
    native.start.mockImplementation(() => { throw new Error('device lost'); });
    expect(() => lifecycle.start()).toThrow('device lost');
    await lifecycle.stop();
    expect(native.stop).not.toHaveBeenCalled();
  });
});
