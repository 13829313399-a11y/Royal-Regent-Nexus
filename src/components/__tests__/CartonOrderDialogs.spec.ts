import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import Batch from '../CartonOrderBatchActionDialog.vue'
import Receipt from '../CartonOrderReceiptDialog.vue'
import Manual from '../CartonSpecialManualReceipt.vue'
import type { SpecialRequest } from '@/api/cartonSpecialRequests'

const api = vi.hoisted(() => ({ batchAction: vi.fn(), detail: vi.fn(), list: vi.fn() }))
vi.mock('@/api/cartonSpecialRequests', () => ({ cartonSpecialRequestsApi: api }))
const row: SpecialRequest = { id: 'REQ', request_no: 'SP-01', factory_id: 'huaxing', kind: 'SAMPLE', title: '', requester_name: '员工', customer_code: '', customer_name: '', workshop_id: '', purpose: '', required_date: '2026-10-25', status: 'SENT', revision: 4, current_version_id: 'V1', quote_version_id: '', pricing_kind: 'PENDING_QUOTE', promised_date: '', lines: [{ id: 'L1', packaging_type: '外箱', paper_quality: 'A33', specification: '10*20*30', quantity: '10', unit: '个', dimension_unit: 'cm', item_no: '', mark_mode: 'NONE', mark_ready: true }], shipments: [], attachments: [], messages: [], history: [], permissions: { can_manual_receive: true } }
beforeEach(() => { vi.clearAllMocks(); api.detail.mockResolvedValue(row); api.list.mockResolvedValue({ options: { locations: [{ id: 'BIN', label: '仓 / A1' }] } }) })
const button = (text: string) => [...document.querySelectorAll<HTMLButtonElement>('button')].find(element => element.textContent === text)!

it('keeps a failed mixed batch reason and request key and posts true source identities and revisions', async () => {
  api.batchAction.mockRejectedValueOnce(new Error('网络结果待确认')).mockResolvedValueOnce({ count: 2 })
  const wrapper = mount(Batch, { props: { open: true, factoryId: 'huaxing', viewerKey: 'u1', action: 'DELETE', entries: [{ kind: 'SAMPLE', special: row }, { kind: 'WORKSHOP_MISC', special: { ...row, id: 'MISC', kind: 'WORKSHOP_MISC', revision: 8 } }] } })
  await flushPromises()
  expect(button('删除订单').disabled).toBe(true)
  const reason = document.querySelector<HTMLTextAreaElement>('[aria-label="批量订单操作原因"]')!
  reason.value = '重复录入订单'; reason.dispatchEvent(new Event('input', { bubbles: true })); await flushPromises()
  button('删除订单').click(); await flushPromises()
  const first = api.batchAction.mock.calls[0]![0]
  expect(first).toMatchObject({ factory_id: 'huaxing', action: 'DELETE', reason: '重复录入订单', items: [{ kind: 'SAMPLE', id: 'REQ', expected_revision: 4 }, { kind: 'WORKSHOP_MISC', id: 'MISC', expected_revision: 8 }] })
  expect(reason.value).toBe('重复录入订单'); expect(document.body.textContent).toContain('网络结果待确认')
  button('删除订单').click(); await flushPromises()
  expect(api.batchAction.mock.calls[1]![0].request_id).toBe(first.request_id)
  expect(wrapper.emitted('saved')).toHaveLength(1); wrapper.unmount()
})

it('opens only the receiving form and preserves it when refreshing locations', async () => {
  const wrapper = mount(Receipt, { props: { open: true, factoryId: 'huaxing', requestId: 'REQ', viewerKey: 'u1' }, global: { stubs: { CartonSpecialManualReceipt: true } } })
  await flushPromises()
  expect(document.body.textContent).not.toContain('订单资料')
  const editor = wrapper.getComponent(Manual), original = editor.element
  editor.vm.$emit('locations-changed'); await flushPromises()
  expect(wrapper.getComponent(Manual).element).toBe(original)
  editor.vm.$emit('saved', row); await flushPromises()
  expect(wrapper.emitted('saved')).toHaveLength(1)
  expect(wrapper.emitted('update:open')).toEqual([[false]])
  wrapper.unmount()
})

it('routes pending shipments to the original note and never mounts a duplicate receipt form', async () => {
  api.detail.mockResolvedValue({ ...row, shipments: [{ id: 'SHIP', delivery_note_no: 'OLD-DN', lines: [{ remaining_quantity: '10' }] }] })
  const wrapper = mount(Receipt, { props: { open: true, factoryId: 'huaxing', requestId: 'REQ', viewerKey: 'u1' } })
  await flushPromises()
  expect(wrapper.findComponent(Manual).exists()).toBe(false)
  button('OLD-DN · 前往验收').click(); await flushPromises()
  expect(wrapper.emitted('open-delivery')).toEqual([['OLD-DN']]); wrapper.unmount()
})

it('discards old identity receipt reads before showing the new scope', async () => {
  let resolve!: (value: SpecialRequest) => void
  api.detail.mockReturnValueOnce(new Promise<SpecialRequest>(done => { resolve = done }))
  const wrapper = mount(Receipt, { props: { open: true, factoryId: 'huaxing', requestId: 'REQ', viewerKey: 'u1' }, global: { stubs: { CartonSpecialManualReceipt: true } } })
  await wrapper.setProps({ viewerKey: 'u2' }); await flushPromises()
  resolve({ ...row, request_no: 'OLD-PRIVATE' }); await flushPromises()
  expect(wrapper.getComponent(Manual).props('request').request_no).toBe('SP-01'); wrapper.unmount()
})
