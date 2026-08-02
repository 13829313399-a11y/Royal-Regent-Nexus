import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const authApiMock = vi.hoisted(() => ({
  getMe: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  changePassword: vi.fn(),
}))

vi.mock('@/api/auth', () => ({
  authApi: authApiMock,
}))

import { useAuthStore } from '../auth'

const user = {
  id: 'admin',
  username: 'admin',
  display_name: '系统管理员',
  roles: ['系统管理员'],
  permissions: ['system:user_manage'],
  grants: [],
  factory_scopes: ['*'],
  department_scopes: ['*'],
  force_password_change: false,
}

describe('auth session loading', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('does not let an older failed session probe clear a newer login', async () => {
    let rejectSessionProbe: (reason?: unknown) => void = () => undefined
    authApiMock.getMe.mockImplementationOnce(() => new Promise((_, reject) => {
      rejectSessionProbe = reject
    }))
    authApiMock.login.mockResolvedValue(user)

    const authStore = useAuthStore()
    const pendingSessionProbe = authStore.ensureSession()
    await Promise.resolve()

    await authStore.login({ username: 'admin', password: 'correct-password' })
    rejectSessionProbe(new Error('旧会话已失效'))

    await expect(pendingSessionProbe).resolves.toBe(true)
    expect(authStore.isAuthenticated).toBe(true)
    expect(authStore.currentUser?.username).toBe('admin')
  })

  it('applies the rotated session returned after changing a temporary password', async () => {
    const changedUser = { ...user, force_password_change: false }
    authApiMock.changePassword.mockResolvedValue(changedUser)
    const authStore = useAuthStore()
    authStore.applySession({ ...user, force_password_change: true })

    await authStore.changePassword({
      current_password: 'TemporaryPass1!',
      new_password: 'FormalPass456!',
      confirm_password: 'FormalPass456!',
    })

    expect(authStore.currentUser?.force_password_change).toBe(false)
    expect(authStore.isAuthenticated).toBe(true)
  })

  it('clears the current session when an explicit refresh receives 401', async () => {
    authApiMock.getMe.mockRejectedValueOnce({ response: { status: 401 } })
    const authStore = useAuthStore()
    authStore.applySession(user)

    await expect(authStore.refreshSession()).resolves.toBe(false)
    expect(authStore.isAuthenticated).toBe(false)
    expect(authStore.currentUser).toBeNull()
  })

  it.each([
    ['network error', new Error('network unavailable')],
    ['server error', { response: { status: 500 } }],
  ])('keeps the current session when an explicit refresh hits a %s', async (_label, error) => {
    authApiMock.getMe.mockRejectedValueOnce(error)
    const authStore = useAuthStore()
    authStore.applySession(user)

    await expect(authStore.refreshSession()).resolves.toBe(false)
    expect(authStore.isAuthenticated).toBe(true)
    expect(authStore.currentUser?.username).toBe('admin')
  })

  it('does not let a stale refresh 401 clear a newer login', async () => {
    let rejectRefresh: (reason?: unknown) => void = () => undefined
    authApiMock.getMe.mockImplementationOnce(() => new Promise((_, reject) => {
      rejectRefresh = reject
    }))
    authApiMock.login.mockResolvedValue(user)
    const authStore = useAuthStore()
    authStore.applySession(user)

    const pendingRefresh = authStore.refreshSession()
    await Promise.resolve()
    await authStore.login({ username: 'admin', password: 'new-session' })
    rejectRefresh({ response: { status: 401 } })

    await expect(pendingRefresh).resolves.toBe(true)
    expect(authStore.isAuthenticated).toBe(true)
    expect(authStore.currentUser?.username).toBe('admin')
  })
})
