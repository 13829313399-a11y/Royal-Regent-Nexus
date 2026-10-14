import { reactive } from 'vue'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { ChangeRecord, OrganizationCatalog, PersonIdentity } from '@/api/identity'
import IdentityChangeContent from '../IdentityChangeContent.vue'

const api = vi.hoisted(() => ({ person: vi.fn(), catalog: vi.fn(), listRoles: vi.fn() }))
const auth = reactive({ currentUser: { id: 'admin', display_name: '系统管理员', username: 'admin' }, authorizationVersion: 1, can: vi.fn(() => true) })
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))
vi.mock('@/api/identity', async (original) => ({ ...(await original<object>()), identityApi: api }))
vi.mock('@/api/iam', () => ({ iamApi: api }))
enableAutoUnmount(afterEach)

const catalog = { organizations: [
  { id: 'huaxing', name: '华兴', factory_id: 'huaxing', kind: 'factory', status: 'active', departments: [{ code: 'engineering', name: '工程部' }] },
  { id: 'huakang-a', name: '华康A', factory_id: 'huakang-a', kind: 'factory', status: 'active', departments: [{ code: 'sales-business', name: '业务部' }] },
] } as OrganizationCatalog
const target = { id: 'employee', display_name: '测试员工', assignments: [], role_bindings: [], overrides: [] } as unknown as PersonIdentity
function record(): ChangeRecord {
  return {
    id: 'change-one', revision: 1, target_user_id: 'employee', requester_user_id: 'admin',
    request_type: 'primary_assignment_transfer', state: 'draft', reason: '调厂调岗',
    effective_at: '', created_at: '2026-10-13T02:32:00Z',
    payload: { request_type: 'primary_assignment_transfer', target_user_id: 'employee', reason: '调厂调岗',
      base_identity_version: 1, base_authorization_version: 35, binding_dispositions: [], exception_decisions: [],
      new_assignment: { org_unit_id: 'huaxing', department_code: 'engineering', official_position_title: '技术员', assignment_type: 'regular', is_primary: true, role_bindings: [] },
    },
  }
}
const mountContent = (row = record(), withCatalog = true) => mount(IdentityChangeContent, { props: { record: row, catalog: withCatalog ? catalog : undefined } })
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(r => { resolve = r }); return { promise, resolve } }
beforeEach(() => {
  vi.resetAllMocks()
  auth.currentUser.id = 'admin'; auth.authorizationVersion = 1; auth.can.mockReturnValue(true)
  api.person.mockResolvedValue(target); api.catalog.mockResolvedValue(catalog)
  api.listRoles.mockResolvedValue([{ id: 'engineering-role', name: '工程技术岗位' }])
})

it('renders the reported transfer as readable Chinese without raw payload fields or internal identifiers', async () => {
  const wrapper = mountContent()
  await flushPromises()
  const text = wrapper.text()
  for (const value of ['办理人员', '测试员工', '申请人', '系统管理员', '华兴', '工程部', '技术员', '长期任职', '是，作为主要任职', '未设置结束时间', '本次未单独选择权限方案', '实际权限以“权限影响”中的核对结果为准']) expect(text).toContain(value)
  for (const code of ['base_authorization_version', 'new_assignment', 'org_unit_id', 'requester_user_id', 'huaxing', 'engineering', 'regular', 'employee']) expect(text).not.toContain(code)
  expect(wrapper.find('pre').exists()).toBe(false)
  expect(api.catalog).not.toHaveBeenCalled()
  expect(api.listRoles).not.toHaveBeenCalled()
})

it.each([['regular', '长期任职'], ['part_time', '兼任'], ['temporary', '临时支援'], ['acting', '临时代理']])('explains %s assignment type and an additional appointment', async (type, label) => {
  const row = record()
  row.payload.new_assignment!.assignment_type = type
  row.payload.new_assignment!.is_primary = false
  const wrapper = mountContent(row)
  await flushPromises()
  expect(wrapper.text()).toContain(label)
  expect(wrapper.text()).toContain('否，作为其他任职')
})

it.each([
  ['home', [], '本次任职所在厂区'],
  ['all_current', [], '办理时的全部生产厂区（固定范围）'],
  ['selected', ['huaxing', 'huakang-a'], '华兴、华康A'],
  ['selected', [], '未选择生产厂区'],
])('explains the %s package scope without exposing codes', async (kind, factoryIds, label) => {
  const row = record()
  row.payload.new_assignment!.role_bindings = [{ role_id: 'engineering-role', department: 'sales-business', factory_scope: { kind, factory_ids: factoryIds } }]
  const wrapper = mountContent(row)
  await flushPromises()
  expect(wrapper.text()).toContain('工程技术岗位')
  expect(wrapper.text()).toContain('业务部')
  expect(wrapper.text()).toContain(label)
  expect(wrapper.text()).not.toContain('engineering-role')
})

it('shows profile corrections and approved scheduling in Beijing time', async () => {
  const row = record()
  row.request_type = 'profile_correction'; delete row.payload.new_assignment
  row.payload.display_name = '更正姓名'; row.payload.official_position_title = '工程师'
  row.state = 'scheduled'; row.effective_at = '2026-10-15T01:30:00Z'
  const wrapper = mountContent(row)
  await flushPromises()
  expect(wrapper.text()).toContain('更正后的资料姓名更正姓名正式岗位工程师')
  expect(wrapper.text()).toContain('2026-10-15 09:30（北京时间）')
  expect(wrapper.text()).not.toContain('办理通过后生效')
  expect(wrapper.find('[aria-label="调整后的任职"]').exists()).toBe(false)
})

it('explains the source assignment, historical source decisions and personal exceptions', async () => {
  const row = record()
  row.payload.source_assignment_id = 'assignment-secret-id'
  row.payload.binding_dispositions = [{ binding_id: 'binding-secret-id', source: 'system_administration' }]
  row.payload.exception_decisions = [{ override_id: 'override-secret-id', decision: 'keep_original_scope' }]
  api.person.mockResolvedValue({ ...target,
    assignments: [{ id: 'assignment-secret-id', org_unit_id: 'huaxing', org_name: '华兴', department_code: 'engineering', official_position_title: '工程师' }],
    role_bindings: [{ id: 'binding-secret-id', role_name: '管理员方案', department: 'engineering', factory_id: 'huaxing' }],
    overrides: [{ id: 'override-secret-id', effect: 'deny', permission_code: 'internal_quote:create', factory_id: 'huaxing', department: 'engineering' }],
  })
  const wrapper = mountContent(row)
  await flushPromises()
  expect(wrapper.text()).toContain('华兴 · 工程部 · 工程师')
  expect(wrapper.text()).toContain('管理员方案 · 华兴 · 工程部')
  expect(wrapper.text()).toContain('保留为独立系统管理')
  expect(wrapper.text()).toContain('明确禁止')
  expect(wrapper.text()).toContain('按原范围保留')
  expect(wrapper.text()).not.toContain('secret-id')
})

it('uses scoped requester names and falls back honestly when readable names are unavailable', async () => {
  const row = record()
  row.requester_user_id = 'another-admin'
  api.person.mockImplementation((id: string) => Promise.resolve(id === 'another-admin' ? { ...target, id, display_name: '申请管理员' } : target))
  const wrapper = mountContent(row)
  await flushPromises()
  expect(wrapper.text()).toContain('申请管理员')
  api.person.mockRejectedValue({ response: { status: 403 } }); api.catalog.mockRejectedValue(new Error('目录暂不可读取'))
  const unavailable = record()
  unavailable.id = 'unreadable'
  unavailable.requester_user_id = 'hidden-user-id'
  unavailable.payload.new_assignment!.org_unit_id = 'unknown-org-id'
  unavailable.payload.new_assignment!.department_code = 'unknown-department-code'
  const fallback = mountContent(unavailable, false)
  await flushPromises()
  expect(fallback.text()).toContain('姓名暂不可读取')
  expect(fallback.text()).toContain('组织名称待核实')
  expect(fallback.text()).toContain('部门名称待核实')
  expect(fallback.text()).not.toMatch(/hidden-user-id|unknown-org-id|unknown-department-code/)
  expect(fallback.text()).toContain('技术员')
})

it('does not request the independent role catalog without its capability', async () => {
  auth.can.mockImplementation((permission?: string) => permission !== 'system:permission_catalog_read')
  const row = record()
  row.payload.new_assignment!.role_bindings = [{ role_id: 'unavailable-role-id', department: 'engineering', factory_scope: { kind: 'home', factory_ids: [] } }]
  const wrapper = mountContent(row)
  await flushPromises()
  expect(api.listRoles).not.toHaveBeenCalled()
  expect(wrapper.text()).toContain('权限方案名称待核实')
  expect(wrapper.text()).not.toContain('unavailable-role-id')
})

it('clears private resolved names and stops lookups when personnel access is removed', async () => {
  const wrapper = mountContent()
  await flushPromises()
  expect(wrapper.text()).toContain('测试员工')
  api.person.mockClear(); api.catalog.mockClear(); api.listRoles.mockClear()
  auth.can.mockReturnValue(false); auth.authorizationVersion++
  await flushPromises()
  expect(wrapper.text()).not.toContain('测试员工')
  expect(api.person).not.toHaveBeenCalled()
  expect(api.catalog).not.toHaveBeenCalled()
  expect(api.listRoles).not.toHaveBeenCalled()
})

it('ignores delayed names after selection changes', async () => {
  const late = deferred<PersonIdentity>()
  api.person.mockReturnValueOnce(late.promise)
  const wrapper = mountContent()
  const next = record(); next.id = 'change-two'; next.target_user_id = 'employee-two'
  api.person.mockResolvedValue({ ...target, id: 'employee-two', display_name: '第二位员工' })
  await wrapper.setProps({ record: next }); await flushPromises()
  late.resolve({ ...target, display_name: '旧人员姓名' }); await flushPromises()
  expect(wrapper.text()).toContain('第二位员工')
  expect(wrapper.text()).not.toContain('旧人员姓名')
})

it('clears resolved names immediately on an authorization refresh and ignores the previous lookup', async () => {
  const late = deferred<PersonIdentity>()
  api.person.mockReturnValueOnce(late.promise)
  const wrapper = mountContent()
  api.person.mockResolvedValue({ ...target, display_name: '新权限范围姓名' })
  auth.authorizationVersion++
  await flushPromises()
  late.resolve({ ...target, display_name: '旧权限范围姓名' }); await flushPromises()
  expect(wrapper.text()).toContain('新权限范围姓名')
  expect(wrapper.text()).not.toContain('旧权限范围姓名')
})
