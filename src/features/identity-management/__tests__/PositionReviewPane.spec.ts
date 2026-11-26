import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import PositionReviewPane from '../PositionReviewPane.vue'
import type { WorkItemDetail } from '@/api/positionReviews'

const api = vi.hoisted(() => ({ detail: vi.fn(), packages: vi.fn(), preview: vi.fn() }))
vi.mock('@/api/positionReviews', () => ({ positionReviewsApi: api, positionStatus: { pending: '待处理' } }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ currentUser: { id: 'admin', identity: { employment_epoch: 1 } }, authorizationVersion: 1 }) }))
const detail = (id: string): WorkItemDetail => ({ item_key: `position:${id}`, kind: 'position', origin: 'employee',
  user: { id, display_name: id, username: id }, source_revision: 'position:1', status: 'pending', before: null,
  declaration: { org_unit_id: 'f', department_code: 'd', position: '主管', note: '' }, created_at: '', updated_at: '',
  available_actions: ['preview', 'commit', 'return_position'], current_official: null,
  identity_mode: 'v2', identity_version: 1, authorization_version: 1, primary_assignment_id: 'a', current_bindings: [],
  independent_allows: [], explicit_denials: [], registration_details: null, can_keep_permissions: false, blocked_reasons: [] })

beforeEach(() => {
  vi.resetAllMocks()
  api.packages.mockResolvedValue({ items: [], catalog_revision: 'fixed' })
})

it('uses the incremental editor for pending studio positions without creating an old workbench preview', async () => {
  vi.useFakeTimers()
  try {
    api.detail.mockResolvedValue({...detail('r'), can_keep_permissions:true})
    const wrapper = mount(PositionReviewPane,{props:{itemKey:'position:r',studio:true},global:{stubs:{StudioPerson:{props:['review'],template:'<div>逐项办理 {{ review.item_key }}</div>'}}}})
    await flushPromises(); await vi.advanceTimersByTimeAsync(350)
    expect(wrapper.text()).toContain('逐项办理 position:r')
    expect(wrapper.text()).not.toContain('选择并分配内置方案')
    expect(api.preview).not.toHaveBeenCalled()
    wrapper.unmount()
  } finally { vi.useRealTimers() }
})

it('shows an uncomputed registration impact until an explicitly staged package has a server preview', async () => {
  vi.useFakeTimers()
  try {
    api.detail.mockResolvedValue({ ...detail('r'), item_key: 'registration:r', kind: 'registration', studio_writes_enabled: true })
    api.packages.mockResolvedValue({ items: [{
      role_id: 'engineer', name: '工程岗位包', department: 'd', assignable: true, scope_mode: 'own_factory',
      capability_summary: [], description: '工程数据', definition_hash: 'hash', role_version_id: 'v1',
    }] })
    const tuple = { permission_code: 'engineering:view', permission_name: '查看工程数据', factory_id: 'f', factory_name: '测试厂', department: 'd', department_name: '工程' }
    api.preview.mockResolvedValue({
      server_now: '2026-11-19T08:00:00Z', expires_at: '2026-11-19T08:05:00Z', allowed_to_commit: true,
      permission_diffs: { added: [tuple], removed: [], retained: [], source_changed: [] },
      explicit_denials: [], high_risk: true, blocked_reasons: [],
    })
    const wrapper = mount(PositionReviewPane, { props: { itemKey: 'registration:r', studio: true, catalog: {
      organizations: [{ id: 'f', kind: 'factory', name: '测试厂', status: 'active', departments: [] }],
      writes_enabled: true, scheduling_enabled: false, authz_mode: 'v2',
    } } })
    await flushPromises()
    const counts = () => wrapper.findAll('.iam2-impact-totals strong').map(node => node.text())
    expect(counts()).toEqual(['—', '—', '—', '—'])
    expect(wrapper.findAll('input:checked')).toHaveLength(0)
    await wrapper.get('.pw-disclosure input[type="checkbox"]').setValue(true)
    await flushPromises()
    await wrapper.get('.pw-package input[type="radio"]').setValue(true)
    expect(api.preview).not.toHaveBeenCalled()
    await wrapper.findAll('button').find(node => node.text().includes('加入本单'))!.trigger('click')
    await flushPromises(); await vi.advanceTimersByTimeAsync(350)
    expect(api.preview).toHaveBeenCalledOnce()
    expect(counts()).toEqual(['1', '0', '0', '0'])
    expect(wrapper.get('.iam2-registration-impact').text()).toContain('测试厂 · 工程')
    const commit = wrapper.findAll('button').find(node => node.text() === '通过并分配权限')!
    expect(commit.attributes('disabled')).toBeDefined()
    await wrapper.get('.pw-actionbar .pw-risk input').setValue(true)
    expect(commit.attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  } finally { vi.useRealTimers() }
})
it.each(['pending', 'approved', 'rejected'])('shows registration contact details without opening a correction form for %s records', async status => {
  api.detail.mockResolvedValue({ ...detail('registrant'), item_key: 'registration:R', kind: 'registration', status,
    user: { id: 'registrant', display_name: '当前姓名', username: 'registered.account' },
    created_at: '2026-10-15T01:30:00Z', registration_details: { display_name: '申请姓名', phone: '13800000000', email: 'registered@example.com' },
    available_actions: status === 'pending' ? ['preview', 'commit'] : [] })
  const wrapper = mount(PositionReviewPane, { props: { itemKey: 'registration:R', compact: true } })
  await flushPromises()
  const info = wrapper.get('[aria-label="注册申请资料"]')
  expect(info.element.closest('details')).toBeNull()
  expect(info.element.closest('fieldset')).toBeNull()
  expect(info.text()).toContain('registered.account')
  expect(info.text()).toContain('申请姓名')
  expect(info.text()).toContain('13800000000')
  expect(info.text()).toContain('registered@example.com')
  expect(info.text()).not.toContain('当前姓名')
  wrapper.unmount()
})

it('distinguishes blank contacts from missing records and clears them when selecting a position review', async () => {
  api.detail.mockResolvedValueOnce({ ...detail('registrant'), kind: 'registration', item_key: 'registration:R',
    registration_details: { display_name: '申请姓名', phone: '', email: '  ' } })
    .mockResolvedValueOnce({ ...detail('registrant'), kind: 'registration', item_key: 'registration:old', registration_details: null })
    .mockResolvedValueOnce(detail('next'))
  const wrapper = mount(PositionReviewPane, { props: { itemKey: 'registration:R' } })
  await flushPromises()
  expect(wrapper.get('[aria-label="注册申请资料"]').findAll('dd').map(node => node.text())).toEqual(['registrant', '申请姓名', '未填写', '未填写'])
  await wrapper.setProps({ itemKey: 'registration:old' }); await flushPromises()
  expect(wrapper.get('[aria-label="注册申请资料"]').findAll('dd').map(node => node.text())).toEqual(['registrant', '未记录', '未记录', '未记录'])
  await wrapper.setProps({ itemKey: 'position:next' }); await flushPromises()
  expect(wrapper.find('[aria-label="注册申请资料"]').exists()).toBe(false)
  wrapper.unmount()
})

it('does not steal the current person input focus when an older selection resolves late', async () => {
  let resolve!: (value: WorkItemDetail) => void
  api.detail.mockReturnValueOnce(new Promise(r => { resolve = r })).mockResolvedValue(detail('B'))
  api.packages.mockResolvedValue({ items: [], catalog_revision: 'fixed' })
  const wrapper = mount(PositionReviewPane, { attachTo: document.body, props: { itemKey: 'position:A' } })
  await wrapper.setProps({ itemKey: 'position:B' }); await flushPromises()
  const search = wrapper.get('input[type="search"]').element as HTMLInputElement
  search.focus()
  await wrapper.get('input[type="search"]').setValue('正在搜索B的方案')
  resolve(detail('A')); await flushPromises()
  expect(wrapper.text()).toContain('B')
  expect(document.activeElement).toBe(search)
  expect(search.value).toBe('正在搜索B的方案')
  wrapper.unmount()
})

it.each([true, false])('opens an audit original as a read-only record with workspace UI %s', async studio => {
  vi.useFakeTimers()
  try {
    api.detail.mockResolvedValue({ ...detail('r'), can_keep_permissions: true })
    const wrapper = mount(PositionReviewPane, { props: { itemKey: 'position:r', readonly: true, studio },
      global: { stubs: { RouterLink: { name: 'RouterLink', props: ['to'], template: '<a><slot /></a>' } } } })
    await flushPromises()
    await vi.advanceTimersByTimeAsync(400)
    expect(wrapper.getComponent({ name: 'RouterLink' }).props('to')).toEqual({
      path: '/system/users', query: { view: studio ? 'inbox' : 'todo', task: 'position:r' },
    })
    expect(wrapper.find('fieldset').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('退回补充')
    expect(api.packages).not.toHaveBeenCalled()
    expect(api.preview).not.toHaveBeenCalled()
    wrapper.unmount()
  } finally { vi.useRealTimers() }
})
