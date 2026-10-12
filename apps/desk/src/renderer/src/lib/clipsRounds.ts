// The Studio's clip loading, one round per change of the recent projects' versions: each project's clips are asked
// once per version, a few at a time. A new round (the list refreshed: a running job touches its project every few
// hundred ms) does not throw away what the last one is still asking - those answers land when they come; only what
// was not started yet moves on. Else a slow engine never gets one project's clips in and a link to its video waits on
// a skeleton for ever. The newest ask's answer per project wins.

export interface ClipsAsk {
  id: string;
  /** the project's version (its updated time, status, live state): a new version is asked again */
  v: string;
}

export class ClipsRounds<T> {
  /** project -> the version asked for (being asked or answered) */
  private seen: Record<string, string> = {};
  private asks = 0;
  /** project -> the number of the ask whose answer is shown */
  private shown: Record<string, number> = {};

  constructor(private atOnce: number) {}

  /** Ask that project again on the next round (its clips changed without a new version). */
  forget(id: string): void {
    delete this.seen[id];
  }

  /** Start a round: ``fetch`` what has a new version, ``put`` each answer (never one older than what is shown),
   * ``fail`` each project that could not be read (asked again on a later round). -> resolves when this round's asks
   * are done, and a cancel that stops it starting more (call it before the next round). */
  round(ids: ClipsAsk[], fetch: (id: string) => Promise<T>, put: (id: string, v: T) => void, fail: (id: string) => void): { done: Promise<{ failed: boolean }>; cancel: () => void } {
    let alive = true;
    const todo = ids.filter(({ id, v }) => this.seen[id] !== v);
    for (const { id, v } of todo) this.seen[id] = v;
    let failed = false;
    const next = async (): Promise<void> => {
      if (!alive) return;
      const x = todo.shift();
      if (!x) return;
      const ask = ++this.asks;
      try {
        const d = await fetch(x.id);
        if (ask >= (this.shown[x.id] ?? 0)) {
          this.shown[x.id] = ask;
          put(x.id, d);
        }
      } catch {
        if (this.seen[x.id] === x.v) delete this.seen[x.id];
        failed = true;
        fail(x.id);
      }
      return next();
    };
    const done = Promise.all(Array.from({ length: Math.min(this.atOnce, todo.length) }, next)).then(() => ({ failed }));
    return {
      done,
      cancel: () => {
        alive = false;
        for (const x of todo) if (this.seen[x.id] === x.v) delete this.seen[x.id];
      },
    };
  }
}
