import { mount, flushPromises } from '@vue/test-utils'
import { expect, it, vi } from 'vitest'
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
