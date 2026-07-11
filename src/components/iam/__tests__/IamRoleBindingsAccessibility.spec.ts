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
})
