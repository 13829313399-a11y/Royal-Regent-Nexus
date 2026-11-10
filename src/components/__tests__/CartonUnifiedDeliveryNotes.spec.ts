import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Component from '../CartonUnifiedDeliveryNotes.vue'
import type { UnifiedDelivery } from '@/api/cartonUnifiedDeliveries'
const api = vi.hoisted(() => ({ receive: vi.fn(), reopenShortfall: vi.fn() }))
const portal = vi.hoisted(() => ({ receiptOptions: vi.fn() }))
vi.mock('@/api/cartonUnifiedDeliveries', async importOriginal => ({ ...await importOriginal<typeof import('@/api/cartonUnifiedDeliveries')>(), cartonUnifiedDeliveriesApi: api }))
vi.mock('@/api/cartonSupplierPortal', () => ({ cartonSupplierPortalApi: portal }))
vi.mock('@/api/cartonSpecialRequests', () => ({ cartonSpecialRequestsApi: { download: vi.fn() } }))
const allocations = defineComponent({ props: ['effective', 'modelValue'], emits: ['update:modelValue'], template: `<button type="button" aria-label="选择测试仓位" @click="$emit('update:modelValue', [{ location_id: 'B1', quantity: effective }])">测试仓位</button>` })
function group(): UnifiedDelivery {
  return { id: 'U1', factory_id: 'huaxing', delivery_note_no: 'DN-1', delivery_date: '2026-10-20', created_at: '2026-10-20', status: 'SENT', revision: 1, can_operate: true, requires_correction: false, formal: null, receipts: [],
    special: [{ id: 'R1', kind: 'SAMPLE', revision: 2, shipments: [{ id: 'S1' }], attachments: [], permissions: {} }] as unknown as UnifiedDelivery['special'],
    lines: [{ id: 'L1', source_kind: 'SPECIAL', source_type: 'SPECIAL_REQUEST', special_request_id: 'R1', special_shipment_id: 'S1', special_request_revision: 2, original_special_line_id: 'RL1', origin: 'INTERNAL', order_no: 'SP-1', order_line_id: null, contract_no: '', customer_po: '', item_no: '', customer_name: '', child_no: '1', packaging_type: '外箱', paper_quality: 'A=B', specification: '10*20*30', dimension_unit: 'cm', unit: '个', quantity: '10', received_quantity: '0', remaining_quantity: '10', delivery_unit_price: '0', free_confirmed: false, mark_mode: 'NONE' }] }
}
function setup(source = group(), props = {}) { return mount(Component, { props: { group: source, canReceive: true, locations: [{ id: 'B1', factory_id: 'huaxing', label: 'A01', warehouse: '仓库', bin_code: 'A01', status: 'ACTIVE' }], ...props }, global: { stubs: { CartonReceiptAllocations: allocations, CartonSplitReceiptReview: true, CartonSourceLinks: true } } }) }
async function open(wrapper: ReturnType<typeof setup>) { await wrapper.findAll('button').find(item => item.text() === '核实实际收到')!.trigger('click'); await flushPromises() }
beforeEach(() => { vi.clearAllMocks(); api.receive.mockResolvedValue(group()); api.reopenShortfall.mockResolvedValue(group()); portal.receiptOptions.mockResolvedValue([]) })
afterEach(() => { vi.unstubAllGlobals() })
describe('unified delivery receipt', () => {
  it('shows a whole mixed supplier note with visible formal history and no warehouse operation', () => {
    const source = group()
    Object.assign(source.lines[0]!, { customer_name: '样板客户', received_quantity: '0', effective_quantity: '0' })
    source.lines.push({ ...source.lines[0]!, id: 'FORMAL', source_kind: 'FORMAL', order_line_id: 'ORDER-LINE',
      customer_name: '正单客户', contract_no: 'CT-42', received_quantity: '4', remaining_quantity: '6', effective_quantity: '4' })
    source.formal = { id: 'SHIP-1', delivery_note_no: source.delivery_note_no, delivery_date: source.delivery_date, created_at: source.created_at,
      revision: 1, status: 'SENT', confirmed_at: '', acceptance_date: '2026-11-08', lines: [], acceptance_lines: [],
      acceptance_history: [{ confirmed_at: '', acceptance_date: '2026-11-08', status: 'POSTED', lines: [] }] }
    const wrapper = setup(source, { supplier: true, collapsible: true })
    try {
      const details = wrapper.get('details')
      expect(details.attributes('open')).toBeUndefined()
      expect(details.get('summary').text()).toBe('送货单明细')
      expect(wrapper.text()).toContain('部分已核实，余货待收')
      expect(details.text()).toContain('样板客户')
      expect(details.text()).toContain('正单客户')
      expect(details.text()).toContain('实际入库 待核实')
      expect(details.text()).toContain('2026-11-08 · 已入库')
      expect(wrapper.text()).not.toContain('冲销本次入库')
      expect(api.receive).not.toHaveBeenCalled()
    } finally { wrapper.unmount() }
  })
  it('keeps unrelated mixed-note papers waiting when opened from a selected order', async () => {
    const source = group()
    Object.assign(source.lines[0]!, { customer_name: '所选客户', contract_no: 'CT-1', item_no: 'SKU-1' })
    source.lines.push({ ...source.lines[0]!, id: 'OTHER', original_special_line_id: 'RL2', customer_name: '另一个客户' })
    const wrapper = setup(source, { autoOpen: true, receiptEntryPaperIds: ['L1'] })
    try {
      await flushPromises()
      expect(wrapper.get('form').text()).toContain('原送货单 DN-1')
      expect(wrapper.get('fieldset').text()).toContain('客户 所选客户 · 合同 CT-1 · 订单 SP-1 · 货号 SKU-1')
      expect(wrapper.get<HTMLInputElement>('[aria-label="L1实收"]').element.value).toBe('10')
      expect(wrapper.find('[aria-label="OTHER实收"]').exists()).toBe(false)
      expect(wrapper.find('[aria-label="统一未收余货处理"]').exists()).toBe(false)
      await wrapper.get('[aria-label="选择测试仓位"]').trigger('click')
      await wrapper.get('form').trigger('submit'); await flushPromises()
      expect(api.receive.mock.calls[0]![1].special).toMatchObject([{ remaining_action: 'WAIT',
        lines: [{ shipment_line_id: 'L1', received_quantity: '10' }] }])
      expect(api.receive.mock.calls[0]![1].special[0].lines).toHaveLength(1)
    } finally { wrapper.unmount() }
  })

  it('preserves the receipt draft through identical list refreshes and blocks writes while fresh inputs are unavailable', async () => {
    const wrapper = setup(group(), { autoOpen: true })
    try {
      await flushPromises()
      await wrapper.get('[aria-label="L1实收"]').setValue('7')
      await wrapper.setProps({ readBlocked: true, group: group() }); await flushPromises()
      expect(wrapper.get<HTMLInputElement>('[aria-label="L1实收"]').element.value).toBe('7')
      await wrapper.get('form').trigger('submit'); await flushPromises()
      expect(api.receive).not.toHaveBeenCalled()
      await wrapper.setProps({ readBlocked: false }); await flushPromises()
      expect(wrapper.get<HTMLInputElement>('[aria-label="L1实收"]').element.value).toBe('7')
      const changed = group(); changed.revision++
      await wrapper.setProps({ group: changed }); await flushPromises()
      expect(wrapper.find('[aria-label="L1实收"]').exists()).toBe(false)
    } finally { wrapper.unmount() }
  })
  it.each([
    { price: null, free: false, shown: '', hint: '原单未填写单价', action: 'PENDING' },
    { price: '0', free: false, shown: '0', hint: '原单单价为0，未确认免费', action: 'PENDING' },
    { price: '0', free: true, shown: '0', hint: '供应商已明确确认免费', action: 'FREE' },
  ])('shows and submits the actual unified original price: $hint', async ({ price, free, shown, hint, action }) => {
    const source = group(); source.lines[0]!.delivery_unit_price = price; source.lines[0]!.free_confirmed = free
    const wrapper = setup(source); await open(wrapper)
    const input = wrapper.get<HTMLInputElement>('[aria-label="L1供应商单价"]')
    expect(input.element.value).toBe(shown); expect(input.attributes('readonly')).toBeDefined(); expect(wrapper.text()).toContain(hint)
    await wrapper.get('[aria-label="选择测试仓位"]').trigger('click')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.receive.mock.calls[0]![1].special[0].lines[0]).toMatchObject({ unit_price: '0', price_action: action })
    wrapper.unmount()
  })
  it('displays an absent original price and submits pending instead of treating it as free', async () => {
    const source = group(); source.lines[0]!.delivery_unit_price = null; source.lines[0]!.free_confirmed = false
    const wrapper = setup(source)
    expect(wrapper.text()).toContain('供应商原价 未填写（待核价）')
    expect(wrapper.text()).not.toContain('供应商已明确本行免费')
    await open(wrapper)
    expect(wrapper.get<HTMLInputElement>('[aria-label="L1供应商单价"]').element.value).toBe('')
    await wrapper.get('[aria-label="选择测试仓位"]').trigger('click')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.receive.mock.calls[0]![1].special[0].lines[0]).toMatchObject({ price_action: 'PENDING', unit_price: '0' })
    wrapper.unmount()
  })
  it.each([false, true])('routes sources and exposes files according to resource access (allowed=%s)', allowed => {
    const source = group(); source.special[0]!.permissions.can_view_order_resources = allowed
    source.lines[0]!.mark_attachment_id = 'A1'
    const wrapper = setup(source)
    const link = wrapper.getComponent({ name: 'CartonSourceLinks' })
    expect(link.attributes('receiving')).toBe('true')
    expect(link.attributes('marks')).toBe(allowed ? 'true' : 'false')
    expect(wrapper.findAll('button').some(row => row.text() === '查看本批箱唛')).toBe(allowed)
    wrapper.unmount()
  })
  it('shows all rejected deliveries as zero inbound instead of received stock on both sides', () => {
    const source = group(); source.lines[0] = { ...source.lines[0]!, quantity: '2600', received_quantity: '2600',
      rejected_quantity: '2600', effective_quantity: '0', remaining_quantity: '0', receivable_quantity: '0' }
    for (const supplier of [false, true]) {
      const wrapper = setup(source, { supplier })
      expect(wrapper.text()).toContain('整单已拒收退回 · 入库 0')
      expect(wrapper.text()).toContain('到货 2,600 · 拒收退回 2,600')
      expect(wrapper.text()).toContain('实际入库 0')
      expect(wrapper.text()).not.toContain('实收 2600')
      wrapper.unmount()
    }
  })
  it('accepts supplier extras by selecting the type without collecting customer, requester or workshop', async () => {
    const source = group(); source.special[0]!.origin = 'SUPPLIER_EXTRA'; source.lines[0]!.origin = 'SUPPLIER_EXTRA'
    const wrapper = setup(source); await open(wrapper)
    await wrapper.get('[aria-label="R1额外用途"]').setValue('WORKSHOP_MISC')
    expect(wrapper.find('[aria-label="R1需求人"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="R1车间"]').exists()).toBe(false)
    await wrapper.get('[aria-label="选择测试仓位"]').trigger('click')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.receive).toHaveBeenCalledWith('U1', expect.objectContaining({ special: [expect.objectContaining({ received_kind: 'WORKSHOP_MISC', requester_name: '', workshop_id: '' })] }), expect.any(AbortSignal))
    wrapper.unmount()
  })
  it('supports both receive and compact reopen when HTTP crypto has no randomUUID', async () => {
    vi.stubGlobal('crypto', { getRandomValues: globalThis.crypto.getRandomValues.bind(globalThis.crypto) })
    const receipt = setup(); await open(receipt)
    await receipt.get('[aria-label="L1实收"]').setValue('0')
    await receipt.get('[aria-label="统一未收余货处理"]').setValue('CLOSE')
    await receipt.get('[aria-label="统一短送结束原因"]').setValue('本原单确认短送结束')
    await receipt.get('form').trigger('submit'); await flushPromises()
    expect(api.receive.mock.calls[0]![1].request_id).toMatch(/^[0-9a-f-]{36}$/)
    receipt.unmount()
    const source = group(); source.lines[0]!.closed_quantity = '2'; source.lines[0]!.remaining_quantity = '0'
    const wrapper = setup(source, { reopenOnly: true })
    expect(wrapper.text()).not.toContain('核实实际收到')
    await wrapper.findAll('button').find(item => item.text() === '更正短送结束')!.trigger('click')
    await wrapper.get('[aria-label="L1选择重开"]').setValue(true)
    await wrapper.get('[aria-label="重开短送原因"]').setValue('原短送结束操作有误')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.reopenShortfall.mock.calls[0]![1].request_id).toMatch(/^[0-9a-f-]{36}$/)
    wrapper.unmount()
  })
  it('reopens only selected closed papers with their exact source revisions and a reason', async () => {
    const source = group(); source.lines[0]!.remaining_quantity = '0'; source.lines[0]!.closed_quantity = '2'
    source.lines.push({ ...source.lines[0]!, id: 'L2' })
    const wrapper = setup(source)
    await wrapper.findAll('button').find(item => item.text() === '更正短送结束')!.trigger('click')
    await wrapper.get('form[aria-label="重开短送余量"]').trigger('submit'); await flushPromises()
    expect(api.reopenShortfall).not.toHaveBeenCalled()
    await wrapper.get('[aria-label="L1选择重开"]').setValue(true)
    await wrapper.get('[aria-label="L1重开数量"]').setValue('1')
    await wrapper.get('[aria-label="重开短送原因"]').setValue('核对原单误关闭')
    await wrapper.get('form[aria-label="重开短送余量"]').trigger('submit'); await flushPromises()
    expect(api.reopenShortfall).toHaveBeenCalledWith('U1', expect.objectContaining({ factory_id: 'huaxing', reason: '核对原单误关闭',
      special: [{ request_id: 'R1', shipment_id: 'S1', expected_revision: 2, lines: [{ shipment_line_id: 'L1', quantity: '1' }] }] }), expect.any(AbortSignal))
    expect(api.receive).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('未产生入库或应付')
    expect(wrapper.emitted('changed')).toHaveLength(1)
    wrapper.unmount()
  })
  it('retains the reopen request on uncertainty and rejects quantities above closed remainder', async () => {
    const source = group(); source.lines[0]!.closed_quantity = '2'
    api.reopenShortfall.mockRejectedValueOnce(new Error('保存结果未确认'))
    const wrapper = setup(source)
    await wrapper.findAll('button').find(item => item.text() === '更正短送结束')!.trigger('click')
    await wrapper.get('[aria-label="L1选择重开"]').setValue(true)
    await wrapper.get('[aria-label="L1重开数量"]').setValue('3')
    await wrapper.get('[aria-label="重开短送原因"]').setValue('原操作关闭有误')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.reopenShortfall).not.toHaveBeenCalled()
    await wrapper.get('[aria-label="L1重开数量"]').setValue('1')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    const first = api.reopenShortfall.mock.calls[0]![1]
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.reopenShortfall.mock.calls[1]![1].request_id).toBe(first.request_id)
    wrapper.unmount()
    const supplier = setup(source, { supplier: true })
    expect(supplier.text()).not.toContain('更正短送结束')
    supplier.unmount()
  })
  it('closes only the selected paper and preserves the other paper as zero-arrival WAIT', async () => {
    const source = group(); source.lines.push({ ...source.lines[0]!, id: 'L2' })
    const wrapper = setup(source); await open(wrapper)
    await wrapper.get('[aria-label="L1实收"]').setValue('0'); await wrapper.get('[aria-label="L2实收"]').setValue('0')
    await wrapper.get('[aria-label="L1关闭此纸品余量"]').setValue(true)
    await wrapper.get('[aria-label="统一短送结束原因"]').setValue('第一种纸品本单不再送')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    const payload = api.receive.mock.calls[0]![1]
    expect(payload.special[0].remaining_action).toBe('WAIT')
    expect(payload.special[0].lines[0]).toMatchObject({ received_quantity: '0', close_remaining: true })
    expect(payload.special[0].lines[1].close_remaining).toBeUndefined()
    wrapper.unmount()
  })
  it('records a reasoned zero-arrival closure without inventing quantities or locations', async () => {
    const wrapper = setup(); await open(wrapper)
    await wrapper.get('[aria-label="L1实收"]').setValue('0')
    await wrapper.get('[aria-label="统一未收余货处理"]').setValue('CLOSE')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.receive).not.toHaveBeenCalled()
    await wrapper.get('[aria-label="统一短送结束原因"]').setValue('供应商确认本单不再送')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.receive).toHaveBeenCalledWith('U1', expect.objectContaining({ special: [expect.objectContaining({ remaining_action: 'CLOSE', close_reason: '供应商确认本单不再送', lines: [expect.objectContaining({ received_quantity: '0', location_allocations: [] })] })] }), expect.any(AbortSignal))
    wrapper.unmount()
  })
  it('opens the precise pending original note from a source link without a second click', async () => {
    const wrapper = setup(group(), { autoOpen: true }); await flushPromises()
    expect(wrapper.find('form[aria-label="统一送货验收"]').exists()).toBe(true)
    await wrapper.setProps({ viewerKey: 'changed' }); await flushPromises()
    expect(wrapper.get<HTMLInputElement>('[aria-label="L1实收"]').element.value).toBe('10')
    wrapper.unmount()
  })
  it('keeps unexplained zero pending automatically without a warehouse price selector', async () => {
    const wrapper = setup(); await open(wrapper)
    expect(wrapper.find('[aria-label="L1价格核对"]').exists()).toBe(false)
    expect(wrapper.get('[aria-label="L1供应商单价"]').attributes('readonly')).toBeDefined()
    await wrapper.get('[aria-label="选择测试仓位"]').trigger('click')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.receive).toHaveBeenCalledWith('U1', expect.objectContaining({ special: [expect.objectContaining({ request_id: 'R1', shipment_id: 'S1', expected_revision: 2, lines: [expect.objectContaining({ price_action: 'PENDING', unit_price: '0', price_reason: '供应商原单缺价或零价未注明免费，待供应商补价', received_quantity: '10', location_allocations: [{ location_id: 'B1', quantity: 10 }] })] })] }), expect.any(AbortSignal))
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
  it('keeps the same idempotency key on uncertain retry and preserves the supplier original price', async () => {
    const source = group(); source.lines[0]!.delivery_unit_price = '2'
    api.receive.mockRejectedValueOnce(new Error('结果未确认'))
    const wrapper = setup(source); await open(wrapper); await wrapper.get('[aria-label="选择测试仓位"]').trigger('click')
    await wrapper.get('form').trigger('submit'); await flushPromises(); const first = api.receive.mock.calls[0]![1]
    await wrapper.get('form').trigger('submit'); await flushPromises(); expect(api.receive.mock.calls[1]![1].request_id).toBe(first.request_id)
    expect(first.special[0].lines[0]).toMatchObject({ price_action: 'MATCH', unit_price: '2', price_reason: '' }); expect(source.lines[0]!.delivery_unit_price).toBe('2')
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
    await wrapper.get('[aria-label="L1破损"]').setValue('0'); await wrapper.get('[aria-label="选择测试仓位"]').trigger('click'); await wrapper.get('form').trigger('submit'); await flushPromises(); expect(wrapper.text()).toContain('额外送货须核对用途'); expect(api.receive).not.toHaveBeenCalled(); wrapper.unmount()
  })
})
