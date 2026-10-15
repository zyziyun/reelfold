// One assisted browser operation at a time. A pause gates every CDP command; takeover/navigation cancels it.
// Uses AbortController, with a monotonic active clock so waiting for the creator consumes no selector timeout.
export class FillControl {
  private abort = new AbortController();
  private pausedAt: number | null = null;
  private pausedMs = 0;
  private waiting: Promise<void> | null = null;
  private wake: (() => void) | null = null;
  get signal() { return this.abort.signal; }
  now = () => (this.pausedAt ?? performance.now()) - this.pausedMs;

  pause() {
    if (this.waiting || this.signal.aborted) return;
    this.pausedAt = performance.now();
    this.waiting = new Promise((resolve) => { this.wake = resolve; });
  }
  resume() {
    if (this.pausedAt !== null) this.pausedMs += performance.now() - this.pausedAt;
    this.pausedAt = null;
    const wake = this.wake;
    this.waiting = null;
    this.wake = null;
    wake?.();
  }
  cancel() { this.abort.abort(); this.resume(); }
  async checkpoint() {
    this.signal.throwIfAborted();
    while (this.waiting) await this.waiting;
    this.signal.throwIfAborted();
  }
}

export class FillRuns {
  private active: { id: string; control: FillControl } | null = null;
  private settled: Promise<void> = Promise.resolve();
  command(id: string, action: 'pause' | 'resume' | 'cancel'): boolean {
    if (this.active?.id !== id) return false;
    this.active.control[action]();
    return true;
  }
  cancel() { this.active?.control.cancel(); }
  async run<T>(id: string, work: (control: FillControl) => Promise<T>): Promise<T | { ok: false; reason: 'cancelled'; detail?: string }> {
    const previous = this.settled;
    let finish!: () => void;
    this.settled = new Promise((resolve) => { finish = resolve; });
    this.cancel();
    const control = new FillControl();
    this.active = { id, control };
    try {
      // The old run must detach its debugger before a replacement starts using the same browser view.
      await previous;
      await control.checkpoint();
      const result = await work(control);
      await control.checkpoint();
      return result;
    }
    catch (e) { if (control.signal.aborted) return { ok: false, reason: 'cancelled' }; throw e; }
    finally { if (this.active?.control === control) this.active = null; finish(); }
  }
}
