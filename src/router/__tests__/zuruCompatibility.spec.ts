import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, expect, it, vi } from 'vitest'
import type { AuthMeResponse } from '@/api/auth'
const api = vi.hoisted(() => ({ getMe: vi.fn() }))
vi.mock('@/api/auth', () => ({ authApi: api }))
vi.mock('vue-router', async (load) => {
  const actual = await load<typeof import('vue-router')>()
  return { ...actual, createWebHistory: actual.createMemoryHistory }
})
vi.mock('@/views/CustomerOrderCenterView.vue', () => ({ default: { template: '<div />' } }))
import { router } from '@/router'
import { useAuthStore } from '@/stores/auth'

beforeEach(async () => {
  vi.resetAllMocks()
  setActivePinia(createPinia())
  await router.replace('/login?logged_out=1')
})

it('replaces the old ZURU link with the existing A intake permissions', async () => {
  const permissions = ['customer_order:read']
  const user: AuthMeResponse = {
    id: 'sales-a', username: 'sales-a', display_name: 'A业务', roles: [], permissions,
    factory_scopes: ['huakang-a'], department_scopes: ['sales-business'], force_password_change: false,
    grants: [{ role_id: 'sales', role_name: '业务', factory_id: 'huakang-a', department: 'sales-business', permissions, data_scope: 'factory' }],
    effective_access: permissions.map(permission_code => ({ permission_code, factory_id: 'huakang-a', department: 'sales-business', effect: 'allow', allowed: true, source_type: 'user_override', source_ids: ['sales-a'] })),
    profile: { primary_factory_id: 'huakang-a', primary_department: 'sales-business', position: '', confirmation_status: 'confirmed' },
  }
  api.getMe.mockResolvedValue(user)
  useAuthStore().applySession(user)
  await router.replace('/modules/sales-business/zuru-intake')
  expect(router.currentRoute.value.name).toBe('customer-order-center')
  expect(router.currentRoute.value.query).toMatchObject({ factory: 'huakang-a', customer: 'zuru', section: 'import' })
  expect(router.currentRoute.value.meta).toMatchObject({ requiresAuth: true, enforcePermissions: true, permissions: ['customer_order:read'] })
})
