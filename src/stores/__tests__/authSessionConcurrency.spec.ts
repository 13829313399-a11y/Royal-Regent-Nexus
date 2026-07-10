import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const authApiMock = vi.hoisted(() => ({
  getMe: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
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
})
