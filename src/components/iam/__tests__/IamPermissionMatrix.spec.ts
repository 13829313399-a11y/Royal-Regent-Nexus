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
        }],
        states: { 'maintenance:update': 'inherit' },
        resolutions: { 'maintenance:update': { allowed: true, source_label: '工程主管角色' } },
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
})
