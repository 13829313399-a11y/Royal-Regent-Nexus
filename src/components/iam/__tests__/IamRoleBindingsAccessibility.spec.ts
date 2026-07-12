import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import IamRoleBindings from '@/components/iam/IamRoleBindings.vue'

describe('IamRoleBindings accessibility', () => {
  it('gives the role template selector an accessible name', () => {
    const wrapper = mount(IamRoleBindings, {
      props: {
        bindings: [],
        roles: [{
          id: 'engineer',
          code: 'engineer',
          name: '工程师',
          description: '工程权限',
          version: 1,
          is_protected: false,
          binding_count: 0,
          permission_count: 2,
        }],
        factoryId: 'huaxing',
        department: 'engineering',
      },
    })

    expect(wrapper.get('select').attributes('aria-label')).toBe('新增角色模板')
  })

  it('only shows role sources that apply to the selected scope, including global bindings', () => {
    const wrapper = mount(IamRoleBindings, {
      props: {
        factoryId: 'huaxing',
        department: 'engineering',
        bindings: [
          {
            id: 'engineer-huaxing', role_id: 'engineer', role_code: 'engineer', role_name: '华兴工程师',
            factory_id: 'huaxing', department: 'engineering', state: 'active', source_type: 'role_template',
          },
          {
            id: 'global-admin', role_id: 'admin', role_code: 'admin', role_name: '集团管理员',
            factory_id: '*', department: '*', state: 'active', source_type: 'role_template',
          },
          {
            id: 'qa-huakang', role_id: 'qa', role_code: 'qa', role_name: '华康 QA 检验员',
            factory_id: 'huakang-a', department: 'qa', state: 'active', source_type: 'role_template',
          },
        ],
      },
    })

    expect(wrapper.text()).toContain('华兴工程师')
    expect(wrapper.text()).toContain('集团管理员')
    expect(wrapper.text()).not.toContain('华康 QA 检验员')
    expect(wrapper.text()).toContain('2 条')
  })
})
