// Engine connection for the renderer: EngineClient (token from the preload bridge) + the SSE stream.
import { createContext, useCallback, useContext, useEffect, useRef, useState, type Dispatch, type ReactNode, type SetStateAction } from 'react';
import { EngineClient } from '../../../shared/engineClient';
import type { EngineInfo, StreamEvent } from '../../../shared/types';
import { t } from '../i18n';

interface Ctx {
  client: EngineClient | null;
  info: EngineInfo | null;
  error: string | null;
  connected: boolean;
  subscribe(fn: (e: StreamEvent) => void): () => void;
  reconnect(): void;
}

const EngineCtx = createContext<Ctx | null>(null);

export function EngineProvider({ children }: { children: ReactNode }) {
  const [info, setInfo] = useState<EngineInfo | null>(null);
  const [client, setClient] = useState<EngineClient | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const subs = useRef(new Set<(e: StreamEvent) => void>());
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let alive = true;
    window.desk
      .engineInfo()
      .then((i) => {
        if (!alive) return;
        setInfo(i);
        setClient(new EngineClient(i.baseUrl, i.token));
        setError(null);
      })
      .catch((e: Error) => alive && setError(e.message));
    const off = window.desk.on('engine:status', (d) => {
      const s = d as { ok: boolean; error?: string; restarting?: boolean };
      // a crash the main process is already restarting from: say so instead of the raw exit log
      if (!s.ok) setError(s.restarting ? t('engine.restarting') : (s.error ?? t('engine.stopped')));
      else setNonce((n) => n + 1);
    });
    return () => {
      alive = false;
      off();
    };
  }, [nonce]);

  useEffect(() => {
    if (!client) return;
    const ac = new AbortController();
    let stop = false;
    (async () => {
      while (!stop) {
        try {
          setConnected(true);
          await client.stream((e) => subs.current.forEach((fn) => fn(e)), ac.signal);
        } catch {
          /* reconnect below */
        }
        setConnected(false);
        if (stop) break;
        await new Promise((r) => setTimeout(r, 1500));
      }
    })();
    return () => {
      stop = true;
      ac.abort();
    };
  }, [client]);

  const subscribe = useCallback((fn: (e: StreamEvent) => void) => {
    subs.current.add(fn);
    return () => {
      subs.current.delete(fn);
    };
  }, []);

  return (
    <EngineCtx.Provider value={{ client, info, error, connected, subscribe, reconnect: () => setNonce((n) => n + 1) }}>
      {children}
    </EngineCtx.Provider>
  );
}

export function useEngine(): Ctx {
  const c = useContext(EngineCtx);
  if (!c) throw new Error('EngineProvider missing');
  return c;
}

/** Load data with the engine client; reload() re-fetches.
 *
 * One request in flight at a time: a reload() asked while one runs is folded into one more request after it, and the
 * answer in flight is still shown (unless setData changed the data after it was asked). Before, every reload dropped
 * the answer in flight and sent another at once: an Archive / Undo of 220 projects reloads the list several times
 * within a second (her click, the engine's event, the registry stamp), so the engine listed every project three to
 * seven times over, concurrently, and only the last answer counted - on a slow Windows machine the list stayed as it
 * was for over a minute. A change of `deps` (or the client) is a new question: answers to the old one are dropped. */
export function useLoad<T>(fn: (c: EngineClient) => Promise<T>, deps: unknown[]) {
  const { client } = useEngine();
  const [data, setDataRaw] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  // gen: which question (deps) is current; tick orders requests asked and local edits (setData)
  const q = useRef({ gen: 0, go: null as (() => void) | null, busy: false, again: false, tick: 0, edited: 0 });
  useEffect(() => {
    if (!client) return;
    const s = q.current;
    const gen = ++s.gen;
    const go = () => {
      s.busy = true;
      s.again = false;
      const asked = ++s.tick;
      setLoading(true);
      fnRef
        .current(client)
        .then(
          (d) => {
            if (s.gen !== gen || asked <= s.edited) return;
            setDataRaw(d);
            setError(null);
          },
          (e: Error) => {
            if (s.gen === gen) setError(e.message);
          },
        )
        .finally(() => {
          if (s.gen !== gen) return;
          s.busy = false;
          if (s.again) go();
          else setLoading(false);
        });
    };
    s.go = go;
    go();
    return () => {
      s.gen++;
      s.go = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, ...deps]);
  const setData = useCallback<Dispatch<SetStateAction<T | null>>>((v) => {
    q.current.edited = ++q.current.tick;
    setDataRaw(v);
  }, []);
  const reload = useCallback(() => {
    const s = q.current;
    if (!s.go) return;
    if (s.busy) s.again = true;
    else s.go();
  }, []);
  return { data, setData, error, loading, reload };
}
