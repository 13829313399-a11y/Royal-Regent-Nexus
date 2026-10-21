import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Component from '../CartonUnifiedDeliveryNotes.vue'
import type { UnifiedDelivery } from '@/api/cartonUnifiedDeliveries'
const api = vi.hoisted(() => ({ receive: vi.fn() }))
const portal = vi.hoisted(() => ({ receiptOptions: vi.fn() }))
vi.mock('@/api/cartonUnifiedDeliveries', async importOriginal => ({ ...await importOriginal<typeof import('@/api/cartonUnifiedDeliveries')>(), cartonUnifiedDeliveriesApi: api }))
vi.mock('@/api/cartonSupplierPortal', () => ({ cartonSupplierPortalApi: portal }))
vi.mock('@/api/cartonSpecialRequests', () => ({ cartonSpecialRequestsApi: { download: vi.fn() } }))
const allocations = defineComponent({ props: ['effective', 'modelValue'], emits: ['update:modelValue'], template: `<button type="button" aria-label="选择测试仓位" @click="$emit('update:modelValue', [{ location_id: 'B1', quantity: effective }])">测试仓位</button>` })
function group(): UnifiedDelivery {
  return { id: 'U1', factory_id: 'huaxing', delivery_note_no: 'DN-1', delivery_date: '2026-10-20', created_at: '2026-10-20', status: 'SENT', revision: 1, can_operate: true, requires_correction: false, formal: null, receipts: [],
    special: [{ id: 'R1', kind: 'SAMPLE', revision: 2, shipments: [{ id: 'S1' }], attachments: [] }] as unknown as UnifiedDelivery['special'],
    lines: [{ id: 'L1', source_kind: 'SPECIAL', source_type: 'SPECIAL_REQUEST', special_request_id: 'R1', special_shipment_id: 'S1', special_request_revision: 2, original_special_line_id: 'RL1', origin: 'INTERNAL', order_no: 'SP-1', order_line_id: null, contract_no: '', customer_po: '', item_no: '', customer_name: '', child_no: '1', packaging_type: '外箱', paper_quality: 'A=B', specification: '10*20*30', dimension_unit: 'cm', unit: '个', quantity: '10', received_quantity: '0', remaining_quantity: '10', delivery_unit_price: '0', free_confirmed: false, mark_mode: 'NONE' }] }
}
function setup(source = group(), props = {}) { return mount(Component, { props: { group: source, canReceive: true, locations: [{ id: 'B1', factory_id: 'huaxing', label: 'A01', warehouse: '仓库', bin_code: 'A01', status: 'ACTIVE' }], ...props }, global: { stubs: { CartonReceiptAllocations: allocations, CartonSplitReceiptReview: true, CartonSourceLinks: true } } }) }
async function open(wrapper: ReturnType<typeof setup>) { await wrapper.findAll('button').find(item => item.text() === '核实实际收到')!.trigger('click'); await flushPromises() }
beforeEach(() => { vi.clearAllMocks(); api.receive.mockResolvedValue(group()); portal.receiptOptions.mockResolvedValue([]) })
describe('unified delivery receipt', () => {
  it('opens the precise pending original note from a source link without a second click', async () => {
    const wrapper = setup(group(), { autoOpen: true }); await flushPromises()
    expect(wrapper.find('form[aria-label="统一送货验收"]').exists()).toBe(true)
    await wrapper.setProps({ viewerKey: 'changed' }); await flushPromises()
    expect(wrapper.get<HTMLInputElement>('[aria-label="L1实收"]').element.value).toBe('10')
    wrapper.unmount()
  })
  it('does not infer free from an unexplained zero, requires a reason, and preserves sample identity', async () => {
    const wrapper = setup(); await open(wrapper)
    expect(wrapper.get<HTMLSelectElement>('[aria-label="L1价格核对"]').element.value).toBe('PENDING')
    expect(wrapper.text()).toContain('原单价为 0，但未明确声明免费，默认待核价')
    await wrapper.get('[aria-label="选择测试仓位"]').trigger('click')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.receive).not.toHaveBeenCalled(); expect(wrapper.text()).toContain('待核价或更正价格须填写原因')
    await wrapper.get('[aria-label="L1价格核对"]').setValue('FREE'); await wrapper.get('[aria-label="L1价格说明"]').setValue('核对本批免费赠送')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.receive).toHaveBeenCalledWith('U1', expect.objectContaining({ special: [expect.objectContaining({ request_id: 'R1', shipment_id: 'S1', expected_revision: 2, lines: [expect.objectContaining({ price_action: 'FREE', unit_price: '0', zero_price_kind: 'FREE', received_quantity: '10', location_allocations: [{ location_id: 'B1', quantity: 10 }] })] })] }), expect.any(AbortSignal))
    wrapper.unmount()
  })
  it('submits every formal paper including zero-received rows when receiving part of a mixed note', async () => {
    const source = group()
    const formalLines = ['F1', 'F2'].map(id => ({ ...source.lines[0]!, id, source_kind: 'FORMAL' as const, source_type: 'FORMAL_ORDER', special_request_id: undefined, special_shipment_id: undefined, delivery_unit_price: '2' }))
    source.lines.push(...formalLines)
    source.formal = { id: 'FORMAL-1', revision: 3, lines: formalLines } as unknown as NonNullable<UnifiedDelivery['formal']>
    const wrapper = setup(source); await open(wrapper)
    await wrapper.get('[aria-label="L1实收"]').setValue('0')
    await wrapper.get('[aria-label="F2实收"]').setValue('0')
    await wrapper.findAll('[aria-label="选择测试仓位"]')[1]!.trigger('click')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.receive).toHaveBeenCalledWith('U1', expect.objectContaining({ special: [], formal: expect.objectContaining({ expected_revision: 3, lines: [expect.objectContaining({ shipment_line_id: 'F1', received_quantity: '10' }), expect.objectContaining({ shipment_line_id: 'F2', received_quantity: '0', location_allocations: [] })] }) }), expect.any(AbortSignal))
    wrapper.unmount()
  })
  it('keeps the same idempotency key on uncertain retry and does not silently write the suggested price as original', async () => {
    const source = group(); source.lines[0]!.delivery_unit_price = '2'
    api.receive.mockRejectedValueOnce(new Error('结果未确认'))
    const wrapper = setup(source); await open(wrapper); await wrapper.get('[aria-label="选择测试仓位"]').trigger('click')
    await wrapper.get('[aria-label="L1价格核对"]').setValue('PROPOSE'); await wrapper.get('[aria-label="L1建议单价"]').setValue('1.5'); await wrapper.get('[aria-label="L1价格说明"]').setValue('与商定价格不符')
    await wrapper.get('form').trigger('submit'); await flushPromises(); const first = api.receive.mock.calls[0]![1]
    await wrapper.get('form').trigger('submit'); await flushPromises(); expect(api.receive.mock.calls[1]![1].request_id).toBe(first.request_id)
    expect(first.special[0].lines[0]).toMatchObject({ price_action: 'PROPOSE', unit_price: '1.5', price_reason: '与商定价格不符' }); expect(source.lines[0]!.delivery_unit_price).toBe('2')
    wrapper.unmount()
  })
  it('keeps supplier read-only and resets receipt drafts on viewer changes', async () => {
    const source = group(); source.lines[0]!.currency = 'USD'
    const supplier = setup(source, { supplier: true }); expect(supplier.text()).toContain('USD 0'); expect(supplier.text()).not.toContain('核实实际收到'); expect(portal.receiptOptions).not.toHaveBeenCalled(); supplier.unmount()
    const wrapper = setup(); await open(wrapper); await wrapper.setProps({ viewerKey: 'different-actor' }); expect(wrapper.find('form').exists()).toBe(false); expect(api.receive).not.toHaveBeenCalled(); wrapper.unmount()
  })
  it('rejects invalid effective quantities and requires classification of supplier extras', async () => {
    const source = group(); source.special[0]!.origin = 'SUPPLIER_EXTRA'; source.lines[0]!.origin = 'SUPPLIER_EXTRA'
    const wrapper = setup(source); await open(wrapper); await wrapper.get('[aria-label="L1破损"]').setValue('11'); await wrapper.get('form').trigger('submit'); await flushPromises(); expect(api.receive).not.toHaveBeenCalled()
    await wrapper.get('[aria-label="L1破损"]').setValue('0'); await wrapper.get('[aria-label="选择测试仓位"]').trigger('click'); await wrapper.get('[aria-label="L1价格核对"]').setValue('FREE'); await wrapper.get('[aria-label="L1价格说明"]').setValue('核对本批免费赠送'); await wrapper.get('form').trigger('submit'); await flushPromises(); expect(wrapper.text()).toContain('额外送货须核对用途'); expect(api.receive).not.toHaveBeenCalled(); wrapper.unmount()
  })
})
