import { createPinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/auth'

const httpMock = vi.hoisted(() => {
  const state: {
    unauthorizedHandler?: () => void
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
  it('clears the auth session and redirects the current page to login on 401', async () => {
    const { installUnauthorizedSessionHandler } = await import('../sessionExpiryHandler')
    const pinia = createPinia()
    const authStore = useAuthStore(pinia)
    const router = {
      currentRoute: {
        value: {
          name: 'molding-sample',
          fullPath: '/modules/molding-sample?factory=huaxing',
        },
      },
      replace: vi.fn(() => Promise.resolve()),
    }

    authStore.applySession({
      id: 'user-engineer',
      username: 'engineer',
      display_name: '华兴工程师',
      roles: ['工程师'],
      permissions: ['molding_sample:read'],
      factory_scopes: ['huaxing'],
      department_scopes: ['engineering'],
      grants: [],
      force_password_change: false,
    })

    installUnauthorizedSessionHandler(router as never, pinia)
    httpMock.state.unauthorizedHandler?.()

    expect(authStore.isAuthenticated).toBe(false)
    expect(authStore.currentUser).toBeNull()
    expect(router.replace).toHaveBeenCalledWith({
      name: 'login',
      query: { redirect: '/modules/molding-sample?factory=huaxing' },
    })
  })
})
