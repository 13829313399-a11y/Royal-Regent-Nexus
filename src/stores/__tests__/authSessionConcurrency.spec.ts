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
import { useAppStore } from '../app'

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
  profile: { primary_factory_id: 'huakang-a', primary_department: 'engineering', position: '', confirmation_status: 'confirmed' },
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
    expect(useAppStore().activeFactoryId).toBe('huakang-a')
  })

  it('does not let a stale successful probe restore a logged-out factory binding', async () => {
    let resolveProbe: (value: typeof user) => void = () => undefined
    authApiMock.getMe.mockImplementationOnce(() => new Promise((resolve) => { resolveProbe = resolve }))
    const store = useAuthStore()
    const pending = store.ensureSession()
    store.clearSession()
    resolveProbe(user)
    await expect(pending).resolves.toBe(false)
    expect(useAppStore().authenticatedFactoryContext).toBeNull()
    expect(useAppStore().activeFactoryId).toBe('group')
  })

  it('does not let an old successful refresh replace a different account factory', async () => {
    let resolveRefresh: (value: typeof user) => void = () => undefined
    const store = useAuthStore()
    store.applySession(user)
    authApiMock.getMe.mockImplementationOnce(() => new Promise((resolve) => { resolveRefresh = resolve }))
    const pending = store.refreshSession()
    authApiMock.login.mockResolvedValue({ ...user, id: 'b', profile: { ...user.profile, primary_factory_id: 'huakang-d' } })
    await store.login({ username: 'b', password: 'test-password' })
    resolveRefresh(user)
    await pending
    expect(store.currentUser?.id).toBe('b')
    expect(useAppStore().activeFactoryId).toBe('huakang-d')
  })

  it('starts a new factory selection when the same account logs in again', async () => {
    const store = useAuthStore()
    store.applySession(user)
    useAppStore().setActiveFactory('huadeng')
    authApiMock.login.mockResolvedValue(user)
    await store.login({ username: 'admin', password: 'test-password' })
    expect(useAppStore().activeFactoryId).toBe('huakang-a')
  })

  it('clears the factory binding on logout even when the logout request fails', async () => {
    const store = useAuthStore()
    store.applySession(user)
    authApiMock.logout.mockRejectedValueOnce(new Error('network unavailable'))
    await expect(store.logout()).rejects.toThrow('network unavailable')
    expect(useAppStore().authenticatedFactoryContext).toBeNull()
    expect(useAppStore().activeFactoryId).toBe('group')
  })
})
