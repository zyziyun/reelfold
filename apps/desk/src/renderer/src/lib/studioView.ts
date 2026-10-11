// Which Studio filter is on screen (the sidebar lights Inbox for Needs you, All projects otherwise). The Studio
// publishes it; nothing else writes it.
import { useSyncExternalStore } from 'react';

let current: string | null = null;
const subs = new Set<() => void>();

export function setStudioView(f: string | null) {
  if (f === current) return;
  current = f;
  for (const s of subs) s();
}

export function useStudioView(): string | null {
  return useSyncExternalStore(
    (f) => {
      subs.add(f);
      return () => subs.delete(f);
    },
    () => current,
  );
}
