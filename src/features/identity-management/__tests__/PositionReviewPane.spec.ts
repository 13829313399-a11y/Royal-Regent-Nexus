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
