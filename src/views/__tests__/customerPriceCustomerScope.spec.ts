import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import QuoteCenterPanel from '@/components/modules/sales/QuoteCenterPanel.vue'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

vi.mock('@/api/customerPriceArtifact', () => ({
  customerPriceArtifactApi: {
    list: vi.fn(async () => []),
    consume: vi.fn(),
    download: vi.fn(),
  },
}))

const customerPricePermissions = [
  'customer_price:read',
  'customer_price:import_internal_quote',
  'customer_price:export_customer_quote',
  'customer_price:compare',
]

function mountPanel(
  username: string,
  deniedPermissions: string[] = [],
  factoryId = 'huaxing',
) {
  useAppStore().setActiveFactory(factoryId as 'huaxing' | 'huakang-c' | 'huakang-d')
  const effectiveAccess = customerPricePermissions.map((permissionCode) => ({
    permission_code: permissionCode,
    factory_id: factoryId,
    department: 'sales-business',
    effect: deniedPermissions.includes(permissionCode) ? 'deny' as const : 'allow' as const,
    allowed: !deniedPermissions.includes(permissionCode),
    source_type: deniedPermissions.includes(permissionCode) ? 'override' : 'role',
    source_ids: deniedPermissions.includes(permissionCode) ? ['override-1'] : ['sales_customer_owner'],
  }))

  useAuthStore().applySession({
    id: `user-${username}`,
    username,
    display_name: '普通业务',
    roles: ['车间业务跟客'],
    permissions: customerPricePermissions,
    grants: [{
      role_id: 'sales_customer_owner',
      role_code: 'sales_customer_owner',
      role_name: '车间业务跟客',
      factory_id: factoryId,
      department: 'sales-business',
      permissions: customerPricePermissions,
      data_scope: 'department',
    }],
    factory_scopes: [factoryId],
    department_scopes: ['sales-business'],
    authz_mode: 'enforce',
    effective_access: effectiveAccess,
    force_password_change: false,
  })

  return mount(QuoteCenterPanel)
}

function mountCrossFactoryPosition(scopeMode: 'cross_factory_read' | 'cross_factory_operate') {
  useAppStore().setActiveFactory('huadeng')
  useAuthStore().applySession({
    id: 'user-cross-factory-sales',
    username: 'cross-factory-sales',
    display_name: '跨厂业务',
    roles: ['业务'],
    permissions: customerPricePermissions,
    grants: [{
      role_id: 'position_sales_business',
      role_code: 'position_sales_business',
      role_name: '业务',
      factory_id: 'huaxing',
      department: 'sales-business',
      permissions: customerPricePermissions,
      data_scope: 'all',
      scope_mode: scopeMode,
      read_permission_codes: ['customer_price:read'],
      unrestricted_department: true,
    }],
    factory_scopes: ['*', 'huaxing'],
    department_scopes: ['*', 'sales-business'],
    authz_mode: 'enforce',
    effective_access: customerPricePermissions.map((permissionCode) => ({
      permission_code: permissionCode,
      factory_id: 'huaxing',
      department: 'sales-business',
      effect: 'allow' as const,
      allowed: true,
      source_type: 'role_binding',
      source_ids: ['position-sales-binding'],
    })),
    force_password_change: false,
  })

  return mount(QuoteCenterPanel)
}

describe('QuoteCenterPanel customer visibility', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    window.history.replaceState({}, '', '/')
  })
  afterEach(() => window.history.replaceState({}, '', '/'))

  it('lets an ordinary sales account see and switch every customer', async () => {
    const wrapper = mountPanel('ordinary-sales-user')
    const customerButtons = wrapper.findAll('button[aria-pressed]')

    expect(customerButtons.map((button) => button.text())).toEqual([
      'BuzzBee 1 单',
      '迪士尼 1 单',
      'Dickie 1 单',
      '彩星 2 单',
    ])

    for (const [selectedIndex, customerButton] of customerButtons.entries()) {
      await customerButton.trigger('click')

      expect(customerButton.attributes('aria-pressed')).toBe('true')
      expect(wrapper.get('input[type="file"]').attributes('disabled')).toBeUndefined()
      customerButtons.forEach((otherButton, otherIndex) => {
        expect(otherButton.attributes('aria-pressed')).toBe(String(otherIndex === selectedIndex))
      })
    }
  })

  it('lets an ordinary sales account import for every customer without an account binding', () => {
    const wrapper = mountPanel('ordinary-sales-user')

    expect(wrapper.get('input[type="file"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).toContain('全部客户按相同权限操作')
  })

  it('still honors an explicit user-level import deny', () => {
    const wrapper = mountPanel('ordinary-sales-user', ['customer_price:import_internal_quote'])

    expect(wrapper.get('input[type="file"]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('当前账号没有导入内部报价权限')
  })

  it('still honors an explicit user-level export deny', () => {
    const wrapper = mountPanel('ordinary-sales-user', ['customer_price:export_customer_quote'])

    expect(wrapper.get('input[type="file"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).toContain('仅可导入')
    expect(wrapper.text()).toContain('当前账号没有输出权限')
  })

  it('uses the selected factory when a position has cross-factory operation access', () => {
    const wrapper = mountCrossFactoryPosition('cross_factory_operate')

    expect(wrapper.get('input[type="file"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).toContain('可导入/输出')
  })

  it('keeps cross-factory read positions from importing in the selected factory', () => {
    const wrapper = mountCrossFactoryPosition('cross_factory_read')

    expect(wrapper.get('input[type="file"]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('仅查看')
  })

  it.each(['huakang-c', 'huakang-d'] as const)(
    'starts %s with an independent empty conversion state and no legacy factory mock',
    async (factoryId) => {
      const wrapper = mountPanel(`ordinary-sales-${factoryId}`, [], factoryId)
      const customerButtons = wrapper.findAll('button[aria-pressed]')

      expect(customerButtons.map((button) => button.text())).toEqual([
        'BuzzBee 0 单',
        '迪士尼 0 单',
        'Dickie 0 单',
        '彩星 0 单',
      ])

      for (const customerButton of customerButtons) {
        await customerButton.trigger('click')
        expect(wrapper.text()).not.toMatch(/QTC-(?:HKA|HKB|HD)-|CQ-HD-/)
      }
    },
  )
})
