import { describe, expect, it, vi } from 'vitest'
import { refreshAndRevalidateAuthorization } from '@/router'

function route(overrides: Record<string, unknown> = {}) {
  return {
    name: 'molding-sample',
    fullPath: '/modules/molding-sample?factory=huaxing',
    meta: {
      requiresAuth: true,
      enforcePermissions: true,
      permissions: ['molding_sample:read'],
    },
    ...overrides,
  }
}

function routerFor(currentRoute = route()) {
  return {
    currentRoute: { value: currentRoute },
    replace: vi.fn(() => Promise.resolve()),
  }
}

describe('authorization snapshot route revalidation', () => {
  it('redirects to forbidden after a successful refresh removes the current route permission', async () => {
    const authStore = {
      isAuthenticated: true,
      refreshSession: vi.fn(async () => true),
      canAny: vi.fn(() => false),
    }
    const router = routerFor()

    await expect(refreshAndRevalidateAuthorization(authStore, router)).resolves.toBe('forbidden')
    expect(authStore.canAny).toHaveBeenCalledWith(['molding_sample:read'])
    expect(router.replace).toHaveBeenCalledWith({ name: 'forbidden' })
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
