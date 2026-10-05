import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AuthMeResponse } from '@/api/auth'

const api = vi.hoisted(() => ({ getMe: vi.fn() }))
vi.mock('@/api/auth', () => ({ authApi: api }))
vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return { ...actual, createWebHistory: actual.createMemoryHistory }
})
import { router } from '@/router'
import { useAuthStore } from '@/stores/auth'

describe('supplier management route scope', () => {
  beforeEach(async () => {
    vi.resetAllMocks(); setActivePinia(createPinia())
    await router.replace('/login?logged_out=1')
  })
  it('opens supplier mark templates with supplier read permission without internal carton permissions', async () => {
    const user: AuthMeResponse = {
      id: 'supplier', username: 'supplier', display_name: '供应商', roles: [], permissions: ['carton_supplier:read'],
      factory_scopes: ['*'], department_scopes: ['*'], force_password_change: false,
      grants: [{ role_id: 'supplier-reader', role_name: '供应商查看', factory_id: '*', department: '*', permissions: ['carton_supplier:read'], data_scope: 'group' }],
      effective_access: [{ permission_code: 'carton_supplier:read', factory_id: '*', department: '*', effect: 'allow', allowed: true, source_type: 'user_override', source_ids: ['supplier-read'] }],
      profile: { primary_factory_id: 'huaxing', primary_department: 'carton', position: '', confirmation_status: 'confirmed' },
    }
    api.getMe.mockResolvedValue(user); useAuthStore().applySession(user)
    await router.replace('/carton-supplier/carton-mark?factory=huaxing')
    expect(router.currentRoute.value.name).toBe('carton-supplier-carton-mark')
    await router.replace('/carton-supplier?factory=huaxing')
    expect(router.currentRoute.value.name).toBe('carton-supplier')
    await router.replace('/modules/pmc-warehouse/carton-procurement?factory=huaxing')
    expect(router.currentRoute.value.name).toBe('dashboard')
  })
  it('rejects supplier pages when supplier read permission is absent', async () => {
    const user: AuthMeResponse = {
      id: 'viewer', username: 'viewer', display_name: '普通账号', roles: [], permissions: [],
      factory_scopes: [], department_scopes: [], force_password_change: false, grants: [],
    }
    api.getMe.mockResolvedValue(user); useAuthStore().applySession(user)
    await router.replace('/carton-supplier')
    expect(router.currentRoute.value.name).toBe('dashboard')
    await router.replace('/carton-supplier/carton-mark?factory=huaxing')
    expect(router.currentRoute.value.name).toBe('dashboard')
  })
  it.each(['carton', 'pmc-warehouse'])('allows a %s-only read grant through the real navigation guard', async department => {
    const user: AuthMeResponse = {
      id: 'warehouse', username: 'warehouse', display_name: '仓管', roles: [],
      permissions: ['carton_procurement:read'], factory_scopes: ['huaxing'], department_scopes: [department], force_password_change: false,
      grants: [{ role_id: 'custom-reader', role_name: '纸箱读取', factory_id: 'huaxing', department, permissions: ['carton_procurement:read'], data_scope: 'factory' }],
      profile: { primary_factory_id: 'huaxing', primary_department: department, position: '', confirmation_status: 'confirmed' },
    }
    api.getMe.mockResolvedValue(user); useAuthStore().applySession(user)
    await router.replace('/carton-supplier-management?factory=huaxing')
    expect(router.currentRoute.value.name).toBe('carton-supplier-management')
    expect(router.currentRoute.value.meta.permissionDepartment).toBeUndefined()
    expect(router.currentRoute.value.meta.strictPermissions).toBe(true)
    expect(useAuthStore().can('carton_procurement:read', 'huaxing', department)).toBe(true)
    expect(useAuthStore().can('carton_procurement:read', 'huadeng', department)).toBe(false)
  })
  it.each([false, true])('rejects missing effective read access even with a legacy grant: %s', async legacyGrant => {
    const user: AuthMeResponse = {
      id: 'denied', username: 'denied', display_name: '无权限', roles: [],
      permissions: legacyGrant ? ['carton_procurement:read'] : [], authz_mode: 'enforce', factory_scopes: ['huaxing'], department_scopes: ['carton'], force_password_change: false,
      grants: legacyGrant ? [{ role_id: 'custom-reader', role_name: '旧读取角色', factory_id: 'huaxing', department: 'carton', permissions: ['carton_procurement:read'], data_scope: 'factory' }] : [],
      // The server's effective snapshot is authoritative after explicit denies.
      effective_access: legacyGrant ? [{ permission_code: 'carton_procurement:read', factory_id: '*', department: '*', effect: 'deny', allowed: false, source_type: 'user_override', source_ids: ['deny'] }] : [],
      profile: { primary_factory_id: 'huaxing', primary_department: 'carton', position: '', confirmation_status: 'confirmed' },
    }
    api.getMe.mockResolvedValue(user); useAuthStore().applySession(user)
    await router.replace('/carton-supplier-management?factory=huaxing')
    // The application's forbidden-page policy redirects denied navigation home.
    expect(router.currentRoute.value.name).toBe('dashboard')
    expect(useAuthStore().can('carton_procurement:read', 'huaxing', 'carton')).toBe(false)
  })
})
