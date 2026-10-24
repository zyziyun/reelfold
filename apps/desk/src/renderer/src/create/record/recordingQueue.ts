/** Retain unacknowledged chunks in order. A failed write stops automatic draining;
 * the owner's explicit save retry resumes at the failed chunk. */
export function recordingQueue(onError: (error: unknown) => void) {
  const pending: (() => Promise<unknown>)[] = [];
  let running: Promise<void> | undefined;
  let failed = false;
  let failure: unknown;
  function drain(): Promise<void> {
    if (running) return running;
    running = (async () => {
      while (pending.length && !failed) {
        try {
          await pending[0]();
          pending.shift();
        } catch (error) {
          failed = true;
          failure = error;
          onError(error);
        }
      }
    })().finally(() => { running = undefined; });
    return running;
  }
  return {
    add(write: () => Promise<unknown>) {
      pending.push(write);
      if (!failed) void drain();
    },
    async flush() {
      await running;
      failed = false;
      await drain();
      if (failed) throw failure;
    },
  };
}
