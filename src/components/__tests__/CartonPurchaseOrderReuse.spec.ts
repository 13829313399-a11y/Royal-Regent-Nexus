import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import SpecialPurchase from '../CartonSpecialPurchaseOrders.vue'
import SupplierPurchase from '../CartonSupplierPurchaseOrders.vue'
import PurchaseDialog from '../CartonPurchaseOrderDialog.vue'
import type { CartonPurchaseOrderContextResponse } from '@/api/cartonProcurement'
const api = vi.hoisted(() => ({ purchaseContext: vi.fn(), purchaseExport: vi.fn() }))
const supplier = vi.hoisted(() => ({ documents: vi.fn(), exportDocuments: vi.fn() }))
vi.mock('@/api/cartonSpecialRequests', () => ({ cartonSpecialRequestsApi: api }))
vi.mock('@/api/cartonSupplierPortal', () => ({ cartonSupplierPortalApi: supplier }))
const context: CartonPurchaseOrderContextResponse = { factory_id: 'huaxing', order_no: 'SP-1', order_revision: 7, pending_type: 'NONE', pending_product_quantity: null, pending_line_count: 0, can_generate: false, historical_baseline: false, latest_document_no: 'SP-1-V7', issues: [{ id: 'VERSION-7', factory_id: 'huaxing', order_no: 'SP-1', document_no: 'SP-1-V7', document_type: 'APPEND', issue_sequence: 2, source_order_revision: 7, before_product_quantity: null, after_product_quantity: null, product_quantity_delta: null, generated_by: 'u1', generated_by_name: '同事', generated_at: '2026-10-21T12:00:00' }] }
beforeEach(() => { vi.resetAllMocks(); api.purchaseContext.mockResolvedValue(context) })
it('uses the same purchase viewer and retries the exact frozen special version after a failed download', async () => {
  api.purchaseExport.mockRejectedValue(new Error('下载失败，请重试'))
  const wrapper = mount(SpecialPurchase, { props: { factoryId: 'huaxing', requestId: 'REQ', orderNo: 'SP-1', supplier: true } })
  await flushPromises(); expect(wrapper.findComponent(PurchaseDialog).exists()).toBe(true)
  for (let i = 0; i < 2; i++) {
    await wrapper.findAll('button').find(button => button.text() === '重新下载原版本')!.trigger('click'); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('下载失败')
  }
  expect(api.purchaseExport).toHaveBeenCalledTimes(2)
  expect(api.purchaseExport).toHaveBeenLastCalledWith('huaxing', 'REQ', 'VERSION-7', true, expect.any(AbortSignal))
  expect(wrapper.text()).not.toContain('生成并下载'); wrapper.unmount()
})
it('discards an old factory response before displaying purchase history', async () => {
  let resolve!: (value: CartonPurchaseOrderContextResponse) => void
  api.purchaseContext.mockReturnValueOnce(new Promise<CartonPurchaseOrderContextResponse>(r => { resolve = r })).mockResolvedValueOnce({ ...context, order_no: 'NEW', issues: [] })
  const wrapper = mount(SpecialPurchase, { props: { factoryId: 'huaxing', requestId: 'REQ', orderNo: 'SP-1' } })
  await wrapper.setProps({ factoryId: 'huakang-b', requestId: 'OTHER', orderNo: 'NEW' }); await flushPromises()
  resolve(context); await flushPromises()
  expect(wrapper.text()).not.toContain('SP-1-V7'); expect(wrapper.text()).toContain('NEW'); wrapper.unmount()
})
it('uses the same supplier purchase history and filters unrelated orders and deliveries', async () => {
  const doc = { id: 'DOC', kind: 'PURCHASE', factory_id: 'huaxing', document_no: 'PO-1', document_type: 'INITIAL', created_at: '2026-10-21T12:00:00', orders: [{ order_no: 'ORDER' }], lines: [] }
  supplier.documents.mockResolvedValue([doc, { ...doc, id: 'OTHER', document_no: 'PRIVATE', orders: [{ order_no: 'OTHER' }] }, { ...doc, id: 'DEL', kind: 'DELIVERY' }])
  const wrapper = mount(SupplierPurchase, { props: { factoryId: 'huaxing', orderNo: 'ORDER' } }); await flushPromises()
  expect(wrapper.findComponent(PurchaseDialog).exists()).toBe(true)
  expect(wrapper.text()).not.toContain('PRIVATE')
  await wrapper.findAll('button').find(button => button.text() === '重新下载原版本')!.trigger('click'); await flushPromises()
  expect(supplier.exportDocuments).toHaveBeenCalledWith([doc]); wrapper.unmount()
})
