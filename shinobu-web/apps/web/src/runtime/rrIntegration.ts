export const isRrIntegration = import.meta.env.VITE_RR_INTEGRATION === 'true';

let accountId: string | undefined;

export function rrToolsUrl(search = globalThis.location?.search ?? ''): string {
  const factory = new URLSearchParams(search).get('factory');
  return factory ? `/tools?${new URLSearchParams({ factory })}` : '/tools';
}

export function rrTranslationEntry(search = globalThis.location?.search ?? ''): string {
  const url = new URL(rrToolsUrl(search), 'http://localhost');
  url.searchParams.set('tool', 'image-translation');
  return `${url.pathname}${url.search}`;
}

/** These names separate local account workspaces; files remain on this device. */
export function accountStorageKey(key: string): string {
  if (!isRrIntegration) return key;
  if (!accountId) throw new Error('请先登录主站，再打开图片翻译。');
  return `rr-image-translation-${encodeURIComponent(accountId)}-${key}`;
}

type RrAccount = { id: string; force_password_change: boolean };

async function readAccount(): Promise<RrAccount | null> {
  const response = await fetch('/api/auth/me', {
    credentials: 'same-origin',
    cache: 'no-store',
  });
  if (response.status === 401 || response.status === 403) return null;
  if (!response.ok) throw new Error('暂时无法连接主站，请稍后重新打开图片翻译。');
  const value: unknown = await response.json();
  if (!value || typeof value !== 'object' || !('id' in value)
      || typeof value.id !== 'string' || !value.id
      || !('force_password_change' in value)
      || typeof value.force_password_change !== 'boolean') {
    throw new Error('无法确认主站登录状态，请重新登录。');
  }
  return { id: value.id, force_password_change: value.force_password_change };
}

function returnToLogin(): void {
  globalThis.location.replace(`/login?${new URLSearchParams({ redirect: rrTranslationEntry() })}`);
}

export async function prepareRrSession(): Promise<boolean> {
  if (!isRrIntegration) return true;
  const account = await readAccount();
  if (!account) { returnToLogin(); return false; }
  if (account.force_password_change) {
    globalThis.location.replace('/change-password');
    return false;
  }
  accountId = account.id;
  return true;
}

/** A tab opened before logout/account switching must not keep the old workspace. */
export function watchRrSession(onInvalid: () => void): () => void {
  if (!isRrIntegration) return () => undefined;
  let disposed = false;
  let checking = false;
  const check = async (): Promise<void> => {
    if (disposed || checking || document.visibilityState === 'hidden') return;
    checking = true;
    try {
      const account = await readAccount();
      if (!disposed && (!account || account.id !== accountId || account.force_password_change)) {
        onInvalid();
        returnToLogin();
      }
    } catch {
      // Network failure does not select a different account or erase local work.
    } finally {
      checking = false;
    }
  };
  const notify = (): void => { void check(); };
  const timer = window.setInterval(notify, 60_000);
  window.addEventListener('focus', notify);
  document.addEventListener('visibilitychange', notify);
  return () => {
    disposed = true;
    window.clearInterval(timer);
    window.removeEventListener('focus', notify);
    document.removeEventListener('visibilitychange', notify);
  };
}
