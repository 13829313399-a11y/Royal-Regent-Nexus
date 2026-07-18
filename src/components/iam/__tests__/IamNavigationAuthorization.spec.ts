import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import type { AuthMeResponse } from '@/api/auth'
import IamNavigation from '@/components/iam/IamNavigation.vue'
import { navigationGroups } from '@/data/enterpriseMock'
import { useAuthStore } from '@/stores/auth'

function session(
  roleId: string,
  permissions: string[],
  overrides: Partial<AuthMeResponse> = {},
): AuthMeResponse {
  return {
    id: `user-${roleId}`,
    username: roleId,
    display_name: roleId === 'position_general_manager' ? '集团总经理' : '测试用户',
    roles: [roleId],
    permissions,
    factory_scopes: roleId === 'admin' ? ['*'] : ['huaxing', '*'],
    department_scopes: roleId === 'admin' ? ['*'] : ['management', '*'],
    grants: [{
      role_id: roleId,
      role_code: roleId,
      role_name: roleId,
      factory_id: roleId === 'admin' ? '*' : 'huaxing',
      department: roleId === 'admin' ? '*' : 'management',
      permissions,
      scope_mode: roleId === 'position_general_manager' ? 'cross_factory_operate' : 'own_factory',
      unrestricted_department: roleId === 'position_general_manager',
      data_scope: roleId === 'admin' ? 'all' : 'factory',
    }],
    authz_mode: 'enforce',
    effective_access: [],
    force_password_change: false,
    ...overrides,
  }
}

function mountNavigation(compact = false) {
  return mount(IamNavigation, {
    props: { title: '权限管理', compact },
    global: {
      stubs: {
        RouterLink: {
          props: ['to'],
          template: '<a :href="to"><slot /></a>',
        },
      },
    },
  })
}

describe('IAM navigation authorization', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('hides every account and permission-management entry from the general manager', () => {
    const authStore = useAuthStore()
    authStore.applySession(session('position_general_manager', [
      'molding_sample:read',
      'internal_quote:create',
      'customer_price:read',
    ]))

    const wrapper = mountNavigation()
    expect(wrapper.text()).not.toContain('用户与授权')
    expect(wrapper.text()).not.toContain('内置职位权限')

    const visibleSystemPaths = navigationGroups
      .flatMap((group) => group.items)
      .filter((item) => !item.permissions?.length
        || item.permissions.some((permission) => authStore.can(permission)))
      .map((item) => item.to)
      .filter((path) => path.startsWith('/system/'))
    expect(visibleSystemPaths).toEqual([])
  })

  it('keeps account and fixed-position navigation available to the wildcard administrator', () => {
    const authStore = useAuthStore()
    authStore.applySession(session('admin', [
      'system:user_manage',
      'system:access_manage',
      'system:permission_catalog_read',
    ]))

    const wrapper = mountNavigation()
    expect(wrapper.text()).toContain('用户与授权')
    expect(wrapper.text()).toContain('内置职位权限')

    const visibleSystemPaths = navigationGroups
      .flatMap((group) => group.items)
      .filter((item) => !item.permissions?.length
        || item.permissions.some((permission) => authStore.can(permission)))
      .map((item) => item.to)
      .filter((path) => path.startsWith('/system/'))
    expect(visibleSystemPaths).toEqual([
      '/system/users',
      '/system/iam/roles',
    ])
  })

  it('uses the compact workspace header without changing authorization visibility', () => {
    const authStore = useAuthStore()
    authStore.applySession(session('admin', ['system:user_manage', 'system:access_manage']))

    const wrapper = mountNavigation(true)
    expect(wrapper.get('header > div').classes()).toContain('py-2')
    expect(wrapper.get('header > div').classes()).toContain('gap-1')
    expect(wrapper.text()).toContain('用户与授权')
    expect(wrapper.text()).toContain('内置职位权限')
  })
})
