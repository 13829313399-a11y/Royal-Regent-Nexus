import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import StudioPeople from '../studio/StudioPeople.vue'
import type { Person } from '@/api/identity'

const employee: Person = {
  id: 'employee',
  username: 'staff',
  display_name: '工程员工',
  status: 'active',
  position: '工程师',
  primary_factory_id: 'factory',
  primary_department: 'engineering',
  identity_mode: 'v2',
  employment_status: 'active',
  identity_version: 2,
}
function directory() {
  return mount(StudioPeople, {
    props: {
      people: [employee],
      org: '',
      department: '',
      page: 1,
      total: 1,
      loading: false,
      failed: false,
      locked: false,
      editable: true,
      viewerId: 'reviewer',
      catalog: {
        writes_enabled: true,
        authz_mode: 'enforce',
        scheduling_enabled: false,
        organizations: [
          {
            id: 'factory',
            name: '甲厂',
            factory_id: 'factory',
            kind: 'factory',
            status: 'active',
            departments: [{ code: 'engineering', name: '工程部' }],
          },
          {
            id: 'group-management',
            name: '集团总务',
            factory_id: '',
            kind: 'functional_unit',
            status: 'active',
            departments: [],
          },
        ],
      },
    },
  })
}
it('keeps reading and configuring separate and offers reading to self or read-only viewers', async () => {
  const w = directory()
  await w.get('tbody tr').trigger('click')
  expect(w.emitted('select')).toHaveLength(1)
  await w.get('.personnel-open').trigger('click')
  expect(w.emitted('manage')).toEqual([[employee]])
  expect(w.emitted('select')).toHaveLength(1)
  await w.setProps({ viewerId: employee.id })
  expect(w.get('.personnel-open').text()).toBe('查看权限')
  await w.setProps({ viewerId: 'reviewer', editable: false })
  expect(w.get('.personnel-open').text()).toBe('查看权限')
  expect(w.text()).toContain('暂不可用')
  expect(w.text()).not.toContain('未配置权限包')
})
it('binds the organizational tree and mobile controls to the same directory filters', async () => {
  const w = directory()
  const nodes = w.findAll('.personnel-tree button')
  await nodes.find((b) => b.text().startsWith('甲厂'))!.trigger('click')
  expect(w.emitted('filter')?.at(-1)).toEqual(['factory', ''])
  await w.setProps({ org: 'factory' })
  await w.get('.iam2-departments button').trigger('click')
  expect(w.emitted('filter')?.at(-1)).toEqual(['factory', 'engineering'])
  await w.get('select[aria-label="筛选组织"]').setValue('group-management')
  expect(w.emitted('filter')?.at(-1)).toEqual(['group-management', ''])
  expect(w.get('.personnel-result').text()).toBe('共 1 人')
})

it('uses scoped server totals independently of the current page and preserves filters when collapsed', async () => {
  const w = directory()
  expect(w.get('.personnel-count').text()).toBe('—')
  await w.setProps({ org: 'factory', department: 'engineering', orgCounts: [
    { org_unit_id: 'factory', department: 'engineering', count: 32 },
    { org_unit_id: 'group-management', department: 'management', count: 4 },
  ] })
  expect(w.get('.personnel-count').text()).toBe('36 人')
  expect(w.get('.iam2-departments button').text()).toContain('32 人')
  const button = w.get('.personnel-tree-toggle')
  await button.trigger('click')
  expect(button.attributes('aria-expanded')).toBe('false')
  await button.trigger('click')
  expect(w.get('.iam2-departments button').attributes('aria-pressed')).toBe('true')
  expect(w.emitted('filter')).toBeUndefined()
})
