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
          applicable_departments: ['engineering'],
          requires_global_factory: false,
          scope_guidance: '仅工程部门绑定。',
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

  it('disables role templates that do not apply to the selected department', async () => {
    const wrapper = mount(IamRoleBindings, {
      props: {
        bindings: [],
        roles: [
          {
            id: 'engineer', code: 'engineer', name: '工程师', description: '工程权限', version: 1,
            is_protected: false, binding_count: 0, permission_count: 6,
            applicable_departments: ['engineering'], requires_global_factory: false,
            scope_guidance: '绑定在用户所属厂区的工程部门。',
          },
          {
            id: 'molding-clerk', code: 'molding_clerk', name: '啤机部文员', description: '生产权限', version: 1,
            is_protected: false, binding_count: 0, permission_count: 8,
            applicable_departments: ['production', 'molding'], requires_global_factory: false,
            scope_guidance: '绑定在用户所属厂区的生产或啤机部门。',
          },
        ],
        factoryId: 'huaxing',
        department: 'engineering',
      },
    })

    const options = wrapper.get('select').findAll('option')
    const engineer = options.find((option) => option.text().includes('工程师'))
    const moldingClerk = options.find((option) => option.text().includes('啤机部文员'))
    expect(engineer?.attributes('disabled')).toBeUndefined()
    expect(moldingClerk?.attributes('disabled')).toBeDefined()
    expect(moldingClerk?.text()).toContain('当前范围不适用')

    await wrapper.get('select').setValue('engineer')
    expect(wrapper.text()).toContain('适用范围：绑定在用户所属厂区的工程部门。')
  })
})
