import { describe, expect, it, vi } from 'vitest'
import { refreshAndRevalidateAuthorization } from '@/router'

function route(overrides: Record<string, unknown> = {}) {
  return {
    name: 'molding-sample',
    fullPath: '/modules/molding-sample?factory=huaxing',
    meta: {
      requiresAuth: true,
      enforcePermissions: true,
      permissions: ['molding_sample:read', 'molding_sample:cross_factory_read'],
    },
    ...overrides,
  }
}

type ProtectedSystemPath =
  | '/system/users'
  | '/system/users/user-1/access'
  | '/system/iam/roles'

function systemRoute(path: ProtectedSystemPath) {
  const permission = path === '/system/users'
    ? 'system:user_manage'
    : path.includes('/access')
      ? 'system:access_manage'
      : 'system:permission_catalog_read'
  return route({
    name: path === '/system/users'
      ? 'system-users'
      : path.includes('/access')
        ? 'user-access-management'
        : 'iam-role-templates',
    fullPath: path,
    meta: {
      requiresAuth: true,
      enforcePermissions: true,
      permissions: [permission],
    },
  })
}

function routerFor(currentRoute = route()) {
  return {
    currentRoute: { value: currentRoute },
    replace: vi.fn(() => Promise.resolve()),
  }
}

describe('authorization snapshot route revalidation', () => {
  it.each([
    '/system/users',
    '/system/users/user-1/access',
    '/system/iam/roles',
  ] as const)(
    'keeps %s directly accessible to a logged-in general manager without page permission',
    async (path) => {
      const generalManagerStore = {
        isAuthenticated: true,
        refreshSession: vi.fn(async () => true),
        canAny: vi.fn(() => false),
      }
      const router = routerFor(systemRoute(path))

      await expect(
        refreshAndRevalidateAuthorization(generalManagerStore, router),
      ).resolves.toBe('refreshed')
      expect(generalManagerStore.canAny).not.toHaveBeenCalled()
      expect(router.replace).not.toHaveBeenCalled()
    },
  )

  it.each([
    '/system/users',
    '/system/users/user-1/access',
    '/system/iam/roles',
  ] as const)(
    'keeps the wildcard administrator on the authorized %s route',
    async (path) => {
      const administratorStore = {
        isAuthenticated: true,
        refreshSession: vi.fn(async () => true),
        canAny: vi.fn(() => true),
      }
      const router = routerFor(systemRoute(path))

      await expect(
        refreshAndRevalidateAuthorization(administratorStore, router),
      ).resolves.toBe('refreshed')
      expect(router.replace).not.toHaveBeenCalled()
    },
  )

  it('keeps the current page after refresh even when the account lacks its page permission', async () => {
    const authStore = {
      isAuthenticated: true,
      refreshSession: vi.fn(async () => true),
      canAny: vi.fn(() => false),
    }
    const router = routerFor()

    await expect(refreshAndRevalidateAuthorization(authStore, router)).resolves.toBe('refreshed')
    expect(authStore.canAny).not.toHaveBeenCalled()
    expect(router.replace).not.toHaveBeenCalled()
  })

  it('redirects to login after refresh confirms the session expired', async () => {
    const authStore = {
      isAuthenticated: true,
      refreshSession: vi.fn(async () => {
        authStore.isAuthenticated = false
        return false
      }),
      canAny: vi.fn(() => true),
    }
    const router = routerFor()

    await expect(refreshAndRevalidateAuthorization(authStore, router)).resolves.toBe('login')
    expect(router.replace).toHaveBeenCalledWith({
      name: 'login',
      query: { redirect: '/modules/molding-sample?factory=huaxing' },
    })
  })

  it('keeps the current page on a transient refresh failure', async () => {
    const authStore = {
      isAuthenticated: true,
      refreshSession: vi.fn(async () => false),
      canAny: vi.fn(() => false),
    }
    const router = routerFor()

    await expect(refreshAndRevalidateAuthorization(authStore, router)).resolves.toBe('unchanged')
    expect(authStore.canAny).not.toHaveBeenCalled()
    expect(router.replace).not.toHaveBeenCalled()
  })

  it('does not redirect again when already on a public route', async () => {
    const authStore = {
      isAuthenticated: false,
      refreshSession: vi.fn(async () => false),
      canAny: vi.fn(() => false),
    }
    const router = routerFor(route({ name: 'login', fullPath: '/login', meta: { requiresAuth: false } }))

    await expect(refreshAndRevalidateAuthorization(authStore, router)).resolves.toBe('unchanged')
    expect(router.replace).not.toHaveBeenCalled()
  })
})
