import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

beforeEach(() => {
  vi.resetModules();
  vi.stubEnv('VITE_RR_INTEGRATION', 'true');
  vi.stubGlobal('isSecureContext', true);
  vi.stubGlobal('location', { search: '?factory=huaxing', replace: vi.fn() });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

const accountResponse = (id: string, changePassword = false) =>
  new Response(JSON.stringify({ id, force_password_change: changePassword }));

describe('rr translation integration', () => {
  it('does not open any account storage before the server identifies the user', async () => {
    const integration = await import('../../apps/web/src/runtime/rrIntegration');
    expect(() => integration.accountStorageKey('history')).toThrow('请先登录');
    const fetcher = vi.fn(async () => accountResponse('account-a'));
    vi.stubGlobal('fetch', fetcher);
    expect(await integration.prepareRrSession()).toBe(true);
    expect(fetcher).toHaveBeenCalledWith('/api/auth/me', {
      credentials: 'same-origin', cache: 'no-store',
    });
    expect(integration.accountStorageKey('history')).toContain('account-a');
  });

  it('uses different history and provider-key names after changing accounts', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => accountResponse('account-a')));
    const first = await import('../../apps/web/src/runtime/rrIntegration');
    await first.prepareRrSession();
    const firstHistory = first.accountStorageKey('shinobu-local-history');
    const firstKey = first.accountStorageKey('shinobu:provider-key:');
    vi.resetModules();
    vi.stubGlobal('fetch', vi.fn(async () => accountResponse('account-b')));
    const second = await import('../../apps/web/src/runtime/rrIntegration');
    await second.prepareRrSession();
    expect(second.accountStorageKey('shinobu-local-history')).not.toBe(firstHistory);
    expect(second.accountStorageKey('shinobu:provider-key:')).not.toBe(firstKey);
  });

  it('returns unauthenticated users through the protected tool entry', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('', { status: 401 })));
    const integration = await import('../../apps/web/src/runtime/rrIntegration');
    expect(await integration.prepareRrSession()).toBe(false);
    const target = vi.mocked(location.replace).mock.calls[0]![0] as string;
    expect(new URL(target, 'https://rr.test').searchParams.get('redirect'))
      .toBe('/tools?factory=huaxing&tool=image-translation');
    expect(() => integration.accountStorageKey('history')).toThrow();
  });

  it('honors the existing forced-password-change requirement', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => accountResponse('account-a', true)));
    const integration = await import('../../apps/web/src/runtime/rrIntegration');
    expect(await integration.prepareRrSession()).toBe(false);
    expect(location.replace).toHaveBeenCalledWith('/change-password');
    expect(() => integration.accountStorageKey('history')).toThrow();
  });

  it('supports the HTTP server UI but rejects failed account reads', async () => {
    vi.stubGlobal('isSecureContext', false);
    const fetcher = vi.fn(async () => new Response('', { status: 503 }));
    vi.stubGlobal('fetch', fetcher);
    const integration = await import('../../apps/web/src/runtime/rrIntegration');
    await expect(integration.prepareRrSession()).rejects.toThrow('暂时无法连接');
    expect(() => integration.accountStorageKey('history')).toThrow();
    fetcher.mockResolvedValueOnce(accountResponse('account-a'));
    expect(await integration.prepareRrSession()).toBe(true);
  });

  it('unmounts the previous account when a visible tab discovers a session change', async () => {
    vi.useFakeTimers();
    const browser = new EventTarget();
    Object.assign(browser, { setInterval, clearInterval });
    vi.stubGlobal('window', browser);
    vi.stubGlobal('document', Object.assign(new EventTarget(), { visibilityState: 'visible' }));
    const fetcher = vi.fn().mockResolvedValueOnce(accountResponse('account-a'))
      .mockResolvedValueOnce(accountResponse('account-b'));
    vi.stubGlobal('fetch', fetcher);
    const integration = await import('../../apps/web/src/runtime/rrIntegration');
    await integration.prepareRrSession();
    const unmount = vi.fn();
    const dispose = integration.watchRrSession(unmount);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(unmount).toHaveBeenCalledOnce();
    expect(location.replace).toHaveBeenCalledOnce();
    dispose();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('retains the standalone storage contract outside the rr build', async () => {
    vi.stubEnv('VITE_RR_INTEGRATION', 'false');
    const integration = await import('../../apps/web/src/runtime/rrIntegration');
    expect(await integration.prepareRrSession()).toBe(true);
    expect(integration.accountStorageKey('shinobu-local-history')).toBe('shinobu-local-history');
  });

  it('keeps return links local and retains only factory context', async () => {
    const integration = await import('../../apps/web/src/runtime/rrIntegration');
    expect(integration.rrToolsUrl('?factory=huaxing&redirect=https://example.com'))
      .toBe('/tools?factory=huaxing');
    expect(integration.rrToolsUrl('')).toBe('/tools');
  });
});
