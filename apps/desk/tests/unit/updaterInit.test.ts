import { expect, it, vi } from 'vitest';

const getter = vi.hoisted(() => vi.fn(() => { throw new Error('App version is not a valid semver version'); }));
vi.mock('electron', () => ({ app: { isPackaged: true, getVersion: () => '0.2.9-local.09004414' } }));
vi.mock('electron-updater', () => ({ default: { get autoUpdater() { return getter(); } } }));
import { initUpdater, updateState, checkForUpdates } from '../../src/main/updater';

it('an updater construction failure cannot crash import or startup', async () => {
  expect(getter).not.toHaveBeenCalled();
  const log = vi.fn();
  expect(() => initUpdater(undefined, log)).not.toThrow();
  expect(updateState()).toMatchObject({state: 'error', current: '0.2.9-local.09004414'});
  expect(log).toHaveBeenCalled();
  await expect(checkForUpdates()).resolves.toMatchObject({state: 'error'});
});
