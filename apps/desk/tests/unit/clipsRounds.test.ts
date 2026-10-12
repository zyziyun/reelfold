import { describe, expect, it } from 'vitest';
import { ClipsRounds } from '../../src/renderer/src/lib/clipsRounds';

/** a fetch whose answers she releases by hand (a slow engine) */
function slowFetch() {
  const calls: { id: string; ok: (v: string) => void; no: (e: Error) => void }[] = [];
  const fetch = (id: string) => new Promise<string>((ok, no) => calls.push({ id, ok, no }));
  return { calls, fetch };
}
const tick = () => new Promise((r) => setTimeout(r, 0));

describe('the Studio clip rounds', () => {
  it('a new round while answers are coming (a running job refreshes the list) keeps them; unchanged projects are not asked again', async () => {
    const r = new ClipsRounds<string>(6);
    const { calls, fetch } = slowFetch();
    const got: Record<string, string> = {};
    const put = (id: string, v: string) => void (got[id] = v);
    const one = r.round([{ id: 'fuye', v: '1' }, { id: 'live', v: '1' }], fetch, put, () => undefined);
    // the running project moved on before the engine answered
    one.cancel();
    const two = r.round([{ id: 'fuye', v: '1' }, { id: 'live', v: '2' }], fetch, put, () => undefined);
    expect(calls.map((c) => c.id)).toEqual(['fuye', 'live', 'live']);
    calls[0].ok('fuye clips');
    calls[1].ok('live v1');
    calls[2].ok('live v2');
    await one.done;
    await two.done;
    expect(got).toEqual({ fuye: 'fuye clips', live: 'live v2' });
  });

  it('an older ask answering after a newer one is not shown', async () => {
    const r = new ClipsRounds<string>(6);
    const { calls, fetch } = slowFetch();
    const got: Record<string, string> = {};
    const one = r.round([{ id: 'live', v: '1' }], fetch, (id, v) => void (got[id] = v), () => undefined);
    one.cancel();
    const two = r.round([{ id: 'live', v: '2' }], fetch, (id, v) => void (got[id] = v), () => undefined);
    calls[1].ok('live v2');
    await two.done;
    calls[0].ok('live v1');
    await one.done;
    expect(got.live).toBe('live v2');
  });

  it('what a cancelled round had not started is the next round’s; a failure is asked again later', async () => {
    const r = new ClipsRounds<string>(1);
    const { calls, fetch } = slowFetch();
    const failed: string[] = [];
    const one = r.round([{ id: 'a', v: '1' }, { id: 'b', v: '1' }], fetch, () => undefined, (id) => failed.push(id));
    one.cancel();
    calls[0].no(new Error('busy'));
    expect(await one.done).toEqual({ failed: true });
    expect(failed).toEqual(['a']);
    expect(calls.map((c) => c.id)).toEqual(['a']); // b was never started by the cancelled round
    r.round([{ id: 'a', v: '1' }, { id: 'b', v: '1' }], fetch, () => undefined, () => undefined);
    await tick();
    expect(calls.map((c) => c.id)).toEqual(['a', 'a']);
    calls[1].ok('a');
    await tick();
    expect(calls.map((c) => c.id)).toEqual(['a', 'a', 'b']);
  });

  it('forget: a project edited without a new version is asked again', async () => {
    const r = new ClipsRounds<string>(6);
    const { calls, fetch } = slowFetch();
    r.round([{ id: 'a', v: '1' }], fetch, () => undefined, () => undefined);
    calls[0].ok('x');
    await tick();
    r.round([{ id: 'a', v: '1' }], fetch, () => undefined, () => undefined);
    expect(calls).toHaveLength(1);
    r.forget('a');
    r.round([{ id: 'a', v: '1' }], fetch, () => undefined, () => undefined);
    expect(calls).toHaveLength(2);
  });
});
