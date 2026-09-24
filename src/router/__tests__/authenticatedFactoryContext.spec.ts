import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AuthMeResponse } from '@/api/auth'

const api = vi.hoisted(() => ({ getMe: vi.fn(), login: vi.fn(), logout: vi.fn(), changePassword: vi.fn() }))
vi.mock('@/api/auth', () => ({ authApi: api }))
vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return { ...actual, createWebHistory: actual.createMemoryHistory }
})

import { router, refreshAndRevalidateAuthorization } from '@/router'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

function user(primaryFactoryId: string, id = 'a'): AuthMeResponse {
  return {
    id, username: id, display_name: id, roles: [], permissions: [], grants: [],
    factory_scopes: ['*'], department_scopes: ['*'], force_password_change: false,
    profile: { primary_factory_id: primaryFactoryId, primary_department: 'production', position: '', confirmation_status: 'confirmed' },
  }
}

describe('authenticated factory context with real navigation guards', () => {
  beforeEach(async () => {
    vi.resetAllMocks()
    setActivePinia(createPinia())
    api.getMe.mockImplementation(async () => useAuthStore().currentUser ?? user('huakang-a'))
    await router.replace('/login?logged_out=1')
  })

  it('initializes a login before the dashboard resolves, keeping the / route', async () => {
    api.login.mockResolvedValue(user('huakang-b'))
    await useAuthStore().login({ username: 'b', password: 'test-password' })
    const observed: string[] = []
    const remove = router.beforeResolve(() => { observed.push(useAppStore().activeFactoryId) })
    try {
      await router.replace('/')
      expect(router.currentRoute.value.fullPath).toBe('/')
      expect(observed).toEqual(['huakang-b'])
    } finally { remove() }
  })

  it('restores /auth/me before allowing the protected page', async () => {
    api.getMe.mockResolvedValue(user('huadeng'))
    expect(useAuthStore().currentUser).toBeNull()
    const observed: string[] = []
    const remove = router.beforeResolve(() => { observed.push(useAppStore().activeFactoryId) })
    try {
      await router.replace('/')
      expect(observed).toEqual(['huadeng'])
      expect(api.getMe).toHaveBeenCalled()
    } finally { remove() }
  })

  it('opens the rebuilt UV workspace only with an explicit A factory and current permission', async () => {
    await router.replace('/modules/production/production-plan?factory=huakang-a')
    expect(router.currentRoute.value.name).toBe('module-detail')
    useAuthStore().applySession({...user('huakang-a'),permissions:['uv_ops:read'],effective_access:[{permission_code:'uv_ops:read',factory_id:'huakang-a',department:'production',effect:'allow',allowed:true,source_type:'role_binding',source_ids:['uv']} ]})
    await router.push('/modules/production/uv-printing?factory=huakang-a')
    expect(router.currentRoute.value.fullPath).toBe('/modules/production/uv-printing/live?factory=huakang-a')
    await router.replace('/modules/production/uv-printing/live?factory=huakang-b')
    expect(router.currentRoute.value.fullPath).toBe('/modules/production?factory=huakang-b')
  })

  it('lets the explicit deep link win over the registered factory', async () => {
    await router.replace('/modules/pmc-warehouse?factory=huadeng')
    expect(useAppStore().activeFactoryId).toBe('huadeng')
    expect(router.currentRoute.value.query.factory).toBe('huadeng')
    api.getMe.mockResolvedValue(user('huakang-c'))
    await refreshAndRevalidateAuthorization(useAuthStore(), router)
    expect(useAppStore().activeFactoryId).toBe('huadeng')
  })

  it.each(['not-a-factory', '*', ''])( 'ignores invalid deep link %s', async (factory) => {
    await router.replace({ path: '/modules/pmc-warehouse', query: { factory } })
    expect(useAppStore().activeFactoryId).toBe('huakang-a')
  })

  it('restores a session on /login and resolves the protected deep-link redirect', async () => {
    await router.replace('/login?redirect=' + encodeURIComponent('/modules/pmc-warehouse?factory=huadeng'))
    expect(router.currentRoute.value.fullPath).toBe('/modules/pmc-warehouse?factory=huadeng')
    expect(useAppStore().activeFactoryId).toBe('huadeng')
  })

  it('keeps explicit logout on the login page without a session probe', async () => {
    useAuthStore().applySession(user('huakang-c'))
    await router.replace('/login?logged_out=1&redirect=/')
    expect(router.currentRoute.value.name).toBe('login')
    expect(api.getMe).not.toHaveBeenCalled()
  })

  it.each([undefined, '/modules/pmc-warehouse?factory=huadeng'])(
    'preserves factory through forced password change and redirect %s', async (redirect) => {
      useAuthStore().applySession({ ...user('huakang-c'), force_password_change: true })
      await router.replace(redirect ?? '/')
      expect(router.currentRoute.value.name).toBe('change-password')
      expect(useAppStore().activeFactoryId).toBe(redirect ? 'huadeng' : 'huakang-c')
      api.changePassword.mockResolvedValue(user('huakang-c'))
      await useAuthStore().changePassword({ current_password: 'old-pass', new_password: 'new-pass', confirm_password: 'new-pass' })
      await router.replace({ name: 'change-password', query: redirect ? { redirect } : {} , force: true })
      expect(router.currentRoute.value.fullPath).toBe(redirect ?? '/')
      expect(useAppStore().activeFactoryId).toBe(redirect ? 'huadeng' : 'huakang-c')
    },
  )

  it('preserves manual choice on navigation, focus refresh and avatar responses', async () => {
    await router.replace('/')
    useAppStore().setActiveFactory('huadeng')
    await router.replace('/people')
    await refreshAndRevalidateAuthorization(useAuthStore(), router)
    useAuthStore().applySession({ ...user('huakang-a'), avatar_url: '/avatar.png' })
    expect(useAppStore().activeFactoryId).toBe('huadeng')
  })

  it('syncs an official primary-factory change once during a direct permission refresh', async () => {
    await router.replace('/')
    useAppStore().setActiveFactory('huakang-b')
    api.getMe.mockResolvedValue(user('huadeng'))
    await useAuthStore().refreshSession()
    expect(useAppStore().activeFactoryId).toBe('huadeng')
    useAppStore().setActiveFactory('huakang-d')
    await refreshAndRevalidateAuthorization(useAuthStore(), router)
    expect(useAppStore().activeFactoryId).toBe('huakang-d')
  })

  it('clears expired-session selection and initializes the next account', async () => {
    await router.replace('/')
    useAppStore().setActiveFactory('huadeng')
    api.getMe.mockRejectedValue({ response: { status: 401 } })
    await refreshAndRevalidateAuthorization(useAuthStore(), router)
    expect(router.currentRoute.value.name).toBe('login')
    expect(useAppStore().authenticatedFactoryContext).toBeNull()
    api.login.mockResolvedValue(user('huaxing', 'b'))
    await useAuthStore().login({ username: 'b', password: 'test-password' })
    await router.replace('/')
    expect(useAppStore().activeFactoryId).toBe('huaxing')
  })

  it('does not turn factory context into a grant for a strictly protected page', async () => {
    await router.replace('/modules/production/three-d-printing?factory=huakang-a')
    expect(router.currentRoute.value.name).not.toBe('three-d-printing-management')
    expect(useAuthStore().can('three_d_printing:read', 'huakang-a', 'three-d-printing')).toBe(false)
  })

  it('does not let a late old navigation overwrite the new account factory', async () => {
    let finishProbe: (value: AuthMeResponse) => void = () => undefined
    let probeStarted: () => void = () => undefined
    const started = new Promise<void>((resolve) => { probeStarted = resolve })
    api.getMe.mockImplementationOnce(() => new Promise<AuthMeResponse>((resolve) => {
      finishProbe = resolve
      probeStarted()
    }))
    const oldNavigation = router.push('/modules/pmc-warehouse?factory=huadeng')
    await started
    api.login.mockResolvedValue(user('huakang-b', 'b'))
    await useAuthStore().login({ username: 'b', password: 'test-password' })
    await router.replace('/')
    finishProbe(user('huakang-a'))
    await oldNavigation
    expect(router.currentRoute.value.fullPath).toBe('/')
    expect(useAuthStore().currentUser?.id).toBe('b')
    expect(useAppStore().activeFactoryId).toBe('huakang-b')
  })
})
