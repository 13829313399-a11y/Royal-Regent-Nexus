import { createPinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/auth'

const httpMock = vi.hoisted(() => {
  const state: {
    unauthorizedHandler?: (error?: unknown) => void
  } = {}
  return {
    state,
    setUnauthorizedHandler: vi.fn((handler) => {
      state.unauthorizedHandler = handler
    }),
  }
})

vi.mock('@/lib/http', () => ({
  http: {},
  setUnauthorizedHandler: httpMock.setUnauthorizedHandler,
}))

describe('installUnauthorizedSessionHandler', () => {
  const user = {
    id: 'user-engineer',
    username: 'engineer',
    display_name: '华兴工程师',
    roles: ['工程师'],
    permissions: ['molding_sample:read'],
    factory_scopes: ['huaxing'],
    department_scopes: ['engineering'],
    grants: [],
    force_password_change: false,
  }

  it('clears the auth session and redirects the current page to login on 401', async () => {
    const { installUnauthorizedSessionHandler } = await import('../sessionExpiryHandler')
    const pinia = createPinia()
    const authStore = useAuthStore(pinia)
    const router = {
      currentRoute: {
        value: {
          name: 'molding-sample',
          fullPath: '/modules/molding-sample?factory=huaxing',
          meta: { requiresAuth: true },
        },
      },
      replace: vi.fn(() => Promise.resolve()),
    }

    authStore.applySession(user)

    installUnauthorizedSessionHandler(router as never, pinia)
    httpMock.state.unauthorizedHandler?.({})

    expect(authStore.isAuthenticated).toBe(false)
    expect(authStore.currentUser).toBeNull()
    expect(router.replace).toHaveBeenCalledWith({
      name: 'login',
      query: { redirect: '/modules/molding-sample?factory=huaxing' },
    })
  })

  it('does not turn a public registration-page 401 into a login redirect back to registration', async () => {
    const { installUnauthorizedSessionHandler } = await import('../sessionExpiryHandler')
    const pinia = createPinia()
    const authStore = useAuthStore(pinia)
    const router = {
      currentRoute: {
        value: {
          name: 'register',
          fullPath: '/register',
          meta: { requiresAuth: false },
        },
      },
      replace: vi.fn(() => Promise.resolve()),
    }

    authStore.applySession(user)
    installUnauthorizedSessionHandler(router as never, pinia)
    httpMock.state.unauthorizedHandler?.({})

    expect(authStore.isAuthenticated).toBe(true)
    expect(router.replace).not.toHaveBeenCalled()
  })

  it('does not let a stale session probe clear a newer authenticated session', async () => {
    const { installUnauthorizedSessionHandler } = await import('../sessionExpiryHandler')
    const pinia = createPinia()
    const authStore = useAuthStore(pinia)
    const router = {
      currentRoute: {
        value: {
          name: 'dashboard',
          fullPath: '/',
          meta: { requiresAuth: true },
        },
      },
      replace: vi.fn(() => Promise.resolve()),
    }

    authStore.applySession(user)
    installUnauthorizedSessionHandler(router as never, pinia)
    httpMock.state.unauthorizedHandler?.({ config: { url: '/auth/me' } })

    expect(authStore.isAuthenticated).toBe(true)
    expect(router.replace).not.toHaveBeenCalled()
  })
})
