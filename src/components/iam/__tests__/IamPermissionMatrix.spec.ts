import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import IamPermissionMatrix from '@/components/iam/IamPermissionMatrix.vue'

describe('IamPermissionMatrix', () => {
  it('shows the current source and emits a three-state draft change', async () => {
    const wrapper = mount(IamPermissionMatrix, {
      props: {
        permissions: [{
          code: 'maintenance:update',
          name: 'maintenance:update',
          module_code: 'maintenance',
          module_name: '设备维修',
          action: 'update',
          risk_level: 'normal',
          scope_type: 'department',
          status: 'active',
          sort_order: 1,
          applicable_departments: ['engineering'],
          requires_global_factory: false,
          scope_guidance: '仅工程部门可配置。',
        }],
        states: { 'maintenance:update': 'inherit' },
        resolutions: { 'maintenance:update': { allowed: true, source_label: '工程主管角色' } },
        factoryId: 'huaxing',
        department: 'engineering',
      },
    })

    expect(wrapper.text()).toContain('设备维修')
    expect(wrapper.text()).toContain('设备维修 · 修改')
    expect(wrapper.text()).toContain('maintenance:update')
    expect(wrapper.text()).toContain('工程主管角色')
    expect(wrapper.text()).toContain('继承')
    expect(wrapper.text()).toContain('允许')
    expect(wrapper.text()).toContain('禁止')
    expect(wrapper.get('[data-testid="mobile-permission-list"]').classes()).toContain('md:hidden')
    expect(wrapper.get('[data-testid="desktop-permission-table"]').classes()).toContain('hidden')
    expect(wrapper.get('legend').text()).toBe('设备维修 · 修改用户级调整')

    const allowButton = wrapper
      .get('[data-testid="mobile-permission-list"]')
      .findAll('button')
      .find((button) => button.text().includes('允许'))
    await allowButton?.trigger('click')
    expect(wrapper.emitted('change')).toEqual([['maintenance:update', 'allow']])
  })

  it('blocks an inapplicable grant while keeping inherit available to clean a stale override', async () => {
    const wrapper = mount(IamPermissionMatrix, {
      props: {
        permissions: [{
          code: 'molding_sample:audit_read',
          name: 'molding_sample:audit_read',
          module_code: 'molding_sample',
          module_name: '啤办管理',
          action: 'audit_read',
          risk_level: 'normal',
          scope_type: 'department',
          status: 'active',
          sort_order: 1,
          applicable_departments: ['management'],
          requires_global_factory: false,
          scope_guidance: '仅管理部门可查看敏感操作审计。',
        }],
        states: { 'molding_sample:audit_read': 'allow' },
        resolutions: { 'molding_sample:audit_read': { allowed: true, source_label: '用户级覆盖' } },
        factoryId: 'huaxing',
        department: 'engineering',
      },
    })

    const mobileList = wrapper.get('[data-testid="mobile-permission-list"]')
    expect(mobileList.text()).toContain('当前范围不适用')
    expect(mobileList.text()).toContain('现有用户级允许配置不生效')
    expect(mobileList.text()).toContain('选择“继承”清理')

    const buttons = mobileList.findAll('button')
    const inheritButton = buttons.find((button) => button.text().includes('继承'))
    const allowButton = buttons.find((button) => button.text().includes('允许'))
    const denyButton = buttons.find((button) => button.text().includes('禁止'))
    expect(inheritButton?.attributes('disabled')).toBeUndefined()
    expect(allowButton?.attributes('disabled')).toBeDefined()
    expect(denyButton?.attributes('disabled')).toBeDefined()

    await inheritButton?.trigger('click')
    expect(wrapper.emitted('change')).toEqual([['molding_sample:audit_read', 'inherit']])
  })

  it('explains that a matching global role remains effective while local overrides stay disabled', () => {
    const wrapper = mount(IamPermissionMatrix, {
      props: {
        permissions: [{
          code: 'molding_sample:cross_factory_read',
          name: 'molding_sample:cross_factory_read',
          module_code: 'molding_sample',
          module_name: '啤办管理',
          action: 'cross_factory_read',
          risk_level: 'high',
          scope_type: 'factory_department',
          status: 'active',
          sort_order: 1,
          applicable_departments: ['*'],
          requires_global_factory: true,
          scope_guidance: '必须配置在全部厂区 / 全部部门范围。',
        }],
        states: { 'molding_sample:cross_factory_read': 'inherit' },
        resolutions: {
          'molding_sample:cross_factory_read': { allowed: true, source_label: '集团啤办只读' },
        },
        factoryId: 'huakang-b',
        department: 'engineering',
      },
    })

    const mobileList = wrapper.get('[data-testid="mobile-permission-list"]')
    expect(mobileList.text()).toContain('当前允许来自“集团啤办只读”的全局授权')
    expect(mobileList.text()).toContain('本地范围只展示结果')
    expect(mobileList.text()).not.toContain('授权来源在业务接口中不生效')
    for (const button of mobileList.findAll('button')) {
      expect(button.attributes('disabled')).toBeDefined()
    }
  })
})
