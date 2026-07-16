import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { UserAccessResponse } from '@/api/iam'
import IamIdentitySummary from '../IamIdentitySummary.vue'

function accessForDepartment(department: string): UserAccessResponse {
  return {
    user: {
      id: 'user-1',
      username: 'employee-1',
      display_name: '测试员工',
      status: 'active',
      phone: '',
      email: '',
    },
    profile: {
      primary_factory_id: 'huaxing',
      primary_department: department,
      position: '自定义职位',
      confirmation_status: 'confirmed',
    },
    authorization_version: 1,
    role_bindings: [],
    overrides: [],
    effective_access: [],
    system_position_role_id: '',
    system_position_role_name: '',
    recommended_system_position_role_id: '',
    legacy_role_count: 0,
    active_override_count: 0,
    cleanup_role_count: 0,
    cleanup_override_count: 0,
  }
}

describe('IamIdentitySummary department labels', () => {
  it.each([
    ['management', '总务'],
    ['pmc-warehouse', '仓库'],
    ['qc', 'QC部'],
    ['carton', '纸箱部'],
  ])('uses the registration department catalog for %s', (department, label) => {
    const wrapper = mount(IamIdentitySummary, {
      props: { access: accessForDepartment(department) },
    })

    expect(wrapper.text()).toContain(`华兴 · ${label}`)
  })
})
