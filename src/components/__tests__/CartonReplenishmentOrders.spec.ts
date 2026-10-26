import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import Component from '../CartonReplenishmentOrders.vue'
import type { PortalOrder } from '@/api/cartonSupplierPortal'
const api = vi.hoisted(() => ({ acceptBatch: vi.fn() }))
vi.mock('@/api/cartonSupplierPortal', () => ({ cartonSupplierPortalApi: api }))
beforeEach(() => { vi.clearAllMocks(); api.acceptBatch.mockResolvedValue({}) })
const orders = [{ id: 'O1', factory_id: 'huaxing', status: 'PARTIALLY_RECEIVED', replenishment_sources: [
  { issue_id: 'B1', document_no: 'PO-B01', responsibility: 'SUPPLIER', planned_date: '2026-10-20', lines: [{ id: 'L1', packaging_type: '外箱', specification: '10*20*30', unit: '个', accepted: false, commitment_revision: 2, remaining_to_ship: '2' }] },
  { issue_id: 'B2', document_no: 'PO-B02', responsibility: 'OWN', planned_date: '2026-10-21', lines: [{ id: 'L1', packaging_type: '外箱', specification: '10*20*30', unit: '个', accepted: false, commitment_revision: 0, remaining_to_ship: '3' }] },
] }] as unknown as (PortalOrder & { factory_id: string })[]
it('accepts the exact B version and independent promise while showing responsibility', async () => {
  const wrapper = mount(Component, { props: { orders, canApprove: true, viewerKey: 'supplier-1' } })
  expect(wrapper.text()).toContain('供应商责任 · 免费换补')
  expect(wrapper.text()).toContain('我方责任 · 按实际收货计费')
  await wrapper.get('[aria-label="PO-B01 补单承诺交期"]').setValue('2026-10-23')
  await wrapper.get('[aria-label="PO-B01 确认补单接单"]').trigger('click'); await flushPromises()
  expect(api.acceptBatch).toHaveBeenCalledWith('huaxing', [{ order_line_id: 'L1', issue_id: 'B1', expected_revision: 2, promised_date: '2026-10-23' }])
  expect(wrapper.emitted('changed')).toHaveLength(1)
  wrapper.unmount()
})
it('keeps read-only viewers from accepting a replacement', () => {
  const wrapper = mount(Component, { props: { orders, canApprove: false, viewerKey: 'reader' } })
  expect(wrapper.find('input').exists()).toBe(false)
  expect(api.acceptBatch).not.toHaveBeenCalled(); wrapper.unmount()
})
it('shows a disputed accepted B as blocked and routes agreement back to changes', () => {
  const disputed = structuredClone(orders)
  disputed[0]!.replenishment_sources = [disputed[0]!.replenishment_sources![0]!]
  disputed[0]!.replenishment_sources![0]!.lines[0]!.accepted = false
  disputed[0]!.replenishment_sources![0]!.lines[0]!.shipping_blocked_reason = '供应商有异议，请在变更待办重新确认'
  const wrapper = mount(Component, { props: { orders: disputed, canApprove: true, viewerKey: 'supplier-1' } })
  expect(wrapper.text()).toContain('供应商有异议，请在变更待办重新确认')
  expect(wrapper.text()).not.toContain('补单已接单')
  expect(wrapper.find('button').exists()).toBe(false)
  expect(api.acceptBatch).not.toHaveBeenCalled()
  wrapper.unmount()
})
it('embeds only fully accepted B sources for promise maintenance and preserves standalone acceptance', async () => {
  const mixed = structuredClone(orders)
  mixed[0]!.replenishment_sources![1]!.lines[0]!.accepted = true
  const wrapper = mount(Component, { props: { orders: mixed, canApprove: true, viewerKey: 'supplier-1', acceptedOnly: true, embedded: true } })
  expect(wrapper.text()).not.toContain('PO-B01')
  expect(wrapper.text()).toContain('PO-B02')
  expect(wrapper.find('[aria-label="PO-B02 确认补单接单"]').exists()).toBe(false)
  await wrapper.get('[aria-label="PO-B02 补单承诺交期"]').setValue('2026-10-26')
  await wrapper.get('[aria-label="PO-B02 保存补单承诺"]').trigger('click'); await flushPromises()
  expect(api.acceptBatch).toHaveBeenCalledWith('huaxing', [{ order_line_id: 'L1', issue_id: 'B2', expected_revision: 0, promised_date: '2026-10-26' }])
  await wrapper.setProps({ viewerKey: 'supplier-2' })
  expect((wrapper.get('[aria-label="PO-B02 补单承诺交期"]').element as HTMLInputElement).value).toBe('')
  wrapper.unmount()
})
it('does not expose an accepted-only promise action for closed or blocked B sources', () => {
  const closed = structuredClone(orders)
  closed[0]!.status = 'COMPLETED'
  for (const source of closed[0]!.replenishment_sources!) source.lines[0]!.accepted = true
  const wrapper = mount(Component, { props: { orders: closed, canApprove: true, viewerKey: 'supplier-1', acceptedOnly: true } })
  expect(wrapper.text()).toContain('补单已接单')
  expect(wrapper.find('button').exists()).toBe(false)
  expect(api.acceptBatch).not.toHaveBeenCalled(); wrapper.unmount()
})
