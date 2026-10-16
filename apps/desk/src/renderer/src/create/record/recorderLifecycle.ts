/** MediaRecorder becomes inactive before its final data/stop events are delivered.
 * Register completion before starting, including for input loss and repeated Stop. */
export function recorderLifecycle(recorder: MediaRecorder) {
  let started = false;
  const completed = new Promise<void>((resolve) => recorder.addEventListener('stop', () => resolve(), { once: true }));
  return {
    start(timeslice?: number) {
      recorder.start(timeslice);
      started = true;
    },
    stop(): Promise<void> {
      if (!started) return Promise.resolve();
      if (recorder.state !== 'inactive') recorder.stop();
      return completed;
    },
  };
}
