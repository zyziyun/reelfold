import { afterEach, describe, expect, it } from 'vitest';
import type { PilotFailure } from '../../src/shared/v02';
import { setLang } from '../../src/renderer/src/i18n';
import { failureDetails, failureReason } from '../../src/renderer/src/v4/Failure';

const promo: PilotFailure = { state: 'failed', code: 'stage', provider: null, stage: 'render', at: 1,
  error: 'render: RuntimeError: launch_kit.py exit 1: launch-kit render failed: TypeError: sequence item 5: expected str instance, NoneType found' };
afterEach(() => setLang('en'));
describe('failed render diagnostics', () => {
  it('keeps the cause that the generic stage reason cannot explain', () => {
    expect(failureReason(promo)).toContain('Render');
    expect(failureDetails(promo)).toContain('TypeError: sequence item 5: expected str instance, NoneType found');
  });
  it('copyable diagnostics hide credentials and private paths', () => {
    const privatePath = ['', 'Users', 'example', 'Customers', 'private', 'project.mp4'].join('/');
    const detail = failureDetails({ ...promo, error: `${promo.error}\n${privatePath}\ntoken=super-secret-value\nme@example.com` });
    expect(detail).toContain('TypeError:');
    for (const secret of ['example/Customers', 'private/project', 'super-secret-value', 'me@example.com']) expect(detail).not.toContain(secret);
  });
  it('does not produce details without an error and bounds long logs', () => {
    expect(failureDetails({ ...promo, error: '  ' })).toBe('');
    expect(failureDetails({ ...promo, error: 'Error\n'.repeat(1000) }).length).toBeLessThanOrEqual(4001);
  });
});
