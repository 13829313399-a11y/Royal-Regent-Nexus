import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'
import Component from '../CartonSupplierReceiving.vue'
import type { PortalWorkspace, ShipmentLine } from '@/api/cartonSupplierPortal'
import { isSupplierOrderSource, supplierPaperCompatible, type SupplierOrderSource } from '@/features/carton-procurement/supplierOrderSource'

const api = vi.hoisted(() => ({ workspace: vi.fn(), receiptOptions: vi.fn(), linkShipmentLine: vi.fn(), receive: vi.fn(), linkReceipt: vi.fn(), changeNonArrival: vi.fn() }))
const can = vi.hoisted(() => vi.fn((_permission: string) => true))
const authState = reactive({ currentUser: { id: 'warehouse', identity: { employment_epoch: 1, effective_context_key: 'original' } }, authorizationVersion: 1, authzMode: 'enforce' })
vi.mock('@/api/cartonSupplierPortal', () => ({ cartonSupplierPortalApi: api }))
vi.mock('@/api/cartonPositions', () => ({ cartonPositionsApi: { locations: vi.fn(async () => [{ id: 'BIN', factory_id: 'huaxing', status: 'ACTIVE', warehouse: 'A', bin_code: '01' }]) } }))
vi.mock('@/api/cartonProcurement', () => ({ cartonProcurementApi: { listCustomers: vi.fn(async () => [{ customer_code: 'CUSTOMER', customer_name: '客户', status: 'ACTIVE' }]) } }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ can,
  get currentUser() { return authState.currentUser }, get authorizationVersion() { return authState.authorizationVersion }, get authzMode() { return authState.authzMode } }) }))
vi.mock('@/stores/app', () => ({ useAppStore: () => ({ activeProductionFactory: { id: 'huaxing' } }) }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }) }))

const options = { props: { factoryId: 'huaxing' }, global: { stubs: { CartonReceiptAllocations: true, CartonSplitReceiptReview: true } } }
function sourceLine(id = 'SOURCE', patch: Partial<ShipmentLine> = {}): ShipmentLine {
  return { id, source_type: 'AD_HOC_REVIEW', order_line_id: null, order_no: '', contract_no: 'CONTRACT', item_no: 'ITEM',
    customer_po: 'PO', customer_name: '', child_no: '', packaging_type: '普通箱', paper_quality: 'A=B', specification: '19.875X11.25X15.375inch',
    unit: '个', quantity: '836', unit_price: '3.22', currency: 'CNY', ...patch }
}
function fixture(): PortalWorkspace {
  return { factory_id: 'huaxing', supplier_name: '东康', orders: [{ id: 'ORDER', order_no: 'CT-ORDER', customer_code: 'CUSTOMER', customer_name: '客户', revision: 2,
    contract_no: 'CONTRACT', item_no: 'ITEM', customer_po: 'PO', product_name: '产品', status: 'PENDING_SUPPLIER', issue_id: 'ISSUE', document_no: 'CT-ORDER-P00',
    order_date: '2026-10-14', planned_date: '2026-10-20', awaiting_issue: false, attachments: [], lines: [{ id: 'PAPER', line_no: 1, child_no: 'CT-ORDER/01',
      packaging_type: '外箱', paper_quality: 'A=B', specification: '19.875*11.25*15.375', dimension_unit: 'inch', unit: '个', required_quantity: '2000', received_quantity: '0',
      in_transit_quantity: '0', remaining_to_ship: '2000', accepted: false, commitment_revision: 0, promised_date: '' }] }],
    shipments: [{ id: 'SHIPMENT', delivery_note_no: 'DN-1', delivery_date: '2026-10-12', revision: 3, status: 'SENT', created_at: '', confirmed_at: '', acceptance_date: null,
      acceptance_lines: [], lines: [sourceLine(), sourceLine('PARTITION', { packaging_type: '隔板', specification: '10*20cm', quantity: '1600' }),
        sourceLine('OTHER-ITEM', { contract_no: 'OTHER', item_no: 'OTHER' }), sourceLine('OTHER-PO', { customer_po: 'ANOTHER-PO' })] },
      { id: 'OTHER-SHIPMENT', delivery_note_no: 'DN-2', delivery_date: '2026-10-13', revision: 1, status: 'SENT', created_at: '', confirmed_at: '', acceptance_date: null, acceptance_lines: [],
        lines: [sourceLine('OTHER-NOTE')] }] }
}
const button = (wrapper: ReturnType<typeof mount>, text: string) => wrapper.get('[aria-label="送货单 DN-1 操作"]').findAll('button').find(row => row.text() === text)!
type Exposed = { resumeOrderSource(source: SupplierOrderSource, orderId?: string): Promise<boolean> }
const exposed = (wrapper: ReturnType<typeof mount>) => wrapper.vm as unknown as Exposed
const emittedSource = (wrapper: ReturnType<typeof mount>) => wrapper.emitted('create-order')![0]![0] as SupplierOrderSource

beforeEach(() => {
  vi.resetAllMocks(); can.mockReturnValue(true)
  authState.currentUser = { id: 'warehouse', identity: { employment_epoch: 1, effective_context_key: 'original' } }
  authState.authorizationVersion = 1; authState.authzMode = 'enforce'
  api.workspace.mockResolvedValue(fixture()); api.receiptOptions.mockResolvedValue([])
})

describe('supplier-origin ordinary order entry', () => {
  it('continues the original delivery using only its remaining quantity and preserves the chosen remainder action', async () => {
    const data = fixture()
    data.shipments = [{ ...data.shipments[0]!, receipt_id: 'FIRST', receipt_status: 'POSTED', partially_received: true,
      lines: [sourceLine('SOURCE', { source_type: 'FORMAL_ORDER', order_line_id: 'PAPER', quantity: '100',
        received_quantity: '60', remaining_quantity: '40', receivable_quantity: '40' })],
      acceptance_history: [{ receipt_id: 'FIRST', status: 'POSTED', acceptance_date: '2026-09-30', confirmed_at: '', lines: [] }] }]
    api.workspace.mockResolvedValue(data)
    api.receive.mockResolvedValue({ ...data.shipments[0]!, status: 'RECEIVED' })
    const wrapper = mount(Component, options); await flushPromises()
    expect(wrapper.text()).toContain('累计实收 60 · 待收 40')
    expect(button(wrapper, '关联已入库记录')).toBeUndefined()
    await button(wrapper, '继续收余货').trigger('click'); await flushPromises()
    expect(wrapper.get<HTMLInputElement>('[aria-label="SOURCE 实收"]').element.value).toBe('40')
    expect(wrapper.get('[aria-label="SOURCE 实收"]').attributes('max')).toBe('40')
    expect(wrapper.get<HTMLSelectElement>('[aria-label="未收余货处理"]').element.value).toBe('WAIT')
    await wrapper.get('[aria-label="未收余货处理"]').setValue('CLOSE')
    await wrapper.get('[aria-label="SOURCE 实收"]').setValue(30)
    expect(wrapper.get('[aria-label="SOURCE 差异原因"]').attributes('required')).toBeDefined()
    await wrapper.get('[aria-label="未收余货处理"]').setValue('WAIT')
    expect(wrapper.get('[aria-label="SOURCE 差异原因"]').attributes('required')).toBeUndefined()
    await wrapper.get('[aria-label="SOURCE 实收"]').setValue(40)
    wrapper.findComponent({ name: 'CartonReceiptAllocations' }).vm.$emit('update:modelValue', [{ location_id: 'BIN', quantity: 40 }])
    await wrapper.get('[aria-label="发货验收日期"]').setValue('2026-10-01')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.receive).toHaveBeenCalledWith('SHIPMENT', expect.objectContaining({ remaining_action: 'WAIT', acceptance_date: '2026-10-01',
      lines: [expect.objectContaining({ received_quantity: 40 })] }))
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    await wrapper.findAll('button').find(row => row.text() === '冲销本次入库')!.trigger('click')
    expect(wrapper.emitted('reverse')?.[0]).toEqual(['FIRST'])
    wrapper.unmount()
  })
  it('groups only this note and contract/item/PO without creating orders or inferring product quantities', async () => {
    const wrapper = mount(Component, options); await flushPromises()
    expect(wrapper.text()).toContain('已有 1 张兼容正式订单')
    await wrapper.get('[aria-label="SOURCE 待核补建正式订单"]').trigger('click')
    const source = emittedSource(wrapper)
    expect(source).toMatchObject({ factoryId: 'huaxing', shipmentId: 'SHIPMENT', sourceLineId: 'SOURCE', deliveryNoteNo: 'DN-1', contractNo: 'CONTRACT', itemNo: 'ITEM', customerPo: 'PO', supplierId: '' })
    expect(source.customerCode).toBeUndefined()
    expect(source.papers.map(line => line.id)).toEqual(['SOURCE', 'PARTITION'])
    expect(source.papers.map(line => line.quantity)).toEqual(['836', '1600'])
    expect(isSupplierOrderSource(source)).toBe(true)
    expect(api.linkShipmentLine).not.toHaveBeenCalled(); expect(api.receive).not.toHaveBeenCalled()
    source.papers[0]!.quantity = '123'
    expect(wrapper.text()).toContain('发货 836 个')
    wrapper.unmount()
  })

  it.each(['carton_procurement:read', 'carton_procurement:receipt_write', 'carton_procurement:inventory_write', 'carton_procurement:order_write'])('requires %s before offering source creation', async permission => {
    can.mockImplementation(value => value !== permission)
    const wrapper = mount(Component, options); await flushPromises()
    expect(wrapper.find('[aria-label="SOURCE 待核补建正式订单"]').exists()).toBe(false)
    expect(wrapper.emitted('create-order')).toBeUndefined()
    wrapper.unmount()
  })

  it('does not offer creation for a shipment outside current customer operation scope', async () => {
    const data = fixture(); data.shipments[0]!.can_operate = false; api.workspace.mockResolvedValue(data)
    const wrapper = mount(Component, options); await flushPromises()
    expect(wrapper.find('[aria-label="SOURCE 待核补建正式订单"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('places receipt association and actual acceptance in one right-side action group', async () => {
    const wrapper = mount(Component, options); await flushPromises()
    const actions = wrapper.get('[aria-label="送货单 DN-1 操作"]')
    expect(actions.findAll('button').map(row => row.text())).toEqual(['关联已入库记录', '核实实际收到'])
    wrapper.unmount()
  })

  it('restores the entire receipt draft on return and only preselects a unique paper after locking', async () => {
    const wrapper = mount(Component, options); await flushPromises()
    await button(wrapper, '核实实际收到').trigger('click'); await flushPromises()
    const dialog = wrapper.get('[role="dialog"]')
    await dialog.get('[aria-label="SOURCE 实收"]').setValue(800)
    await dialog.get('[aria-label="SOURCE 差异原因"]').setValue('核对实物短收')
    await dialog.get('[aria-label="发货验收日期"]').setValue('2026-10-13')
    await dialog.get('[aria-label="SOURCE 入库单价"]').setValue(7.5)
    const allocations = wrapper.findAllComponents({ name: 'CartonReceiptAllocations' })
    allocations[0]!.vm.$emit('update:modelValue', [{ location_id: 'BIN', quantity: 800 }]); await flushPromises()
    await dialog.get('[aria-label="SOURCE 补建正式订单"]').trigger('click')
    const source = emittedSource(wrapper)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(await exposed(wrapper).resumeOrderSource(source)).toBe(true); await flushPromises()
    expect(wrapper.get('[aria-label="SOURCE 实收"]').element).toHaveProperty('value', '800')
    expect(wrapper.get('[aria-label="SOURCE 差异原因"]').element).toHaveProperty('value', '核对实物短收')
    expect(wrapper.get('[aria-label="发货验收日期"]').element).toHaveProperty('value', '2026-10-13')
    expect(wrapper.findAllComponents({ name: 'CartonReceiptAllocations' })[0]!.props('modelValue')).toEqual([{ location_id: 'BIN', quantity: 800 }])
    await wrapper.get('[role="dialog"]').get('[aria-label="SOURCE 补建正式订单"]').trigger('click')
    expect(await exposed(wrapper).resumeOrderSource(source, 'ORDER')).toBe(true); await flushPromises()
    expect(wrapper.get('[aria-label="SOURCE 验收关联订单"]').element).toHaveProperty('value', 'PAPER')
    expect(wrapper.get('[aria-label="PARTITION 验收关联订单"]').element).toHaveProperty('value', '')
    expect(api.linkShipmentLine).not.toHaveBeenCalled(); expect(api.receive).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('never copies a paused receipt into another note or factory and discards it on identity change', async () => {
    const wrapper = mount(Component, options); await flushPromises()
    await button(wrapper, '核实实际收到').trigger('click'); await flushPromises()
    await wrapper.get('[aria-label="SOURCE 实收"]').setValue(700)
    await wrapper.get('[role="dialog"]').get('[aria-label="SOURCE 补建正式订单"]').trigger('click')
    const source = emittedSource(wrapper)
    expect(await exposed(wrapper).resumeOrderSource({ ...source, factoryId: 'huakang-a' })).toBe(false)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(await exposed(wrapper).resumeOrderSource({ ...source, sourceLineId: 'PARTITION' })).toBe(false)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(await exposed(wrapper).resumeOrderSource({ ...source, shipmentId: 'OTHER-SHIPMENT', sourceLineId: 'OTHER-NOTE', papers: [sourceLine('OTHER-NOTE')] })).toBe(true)
    expect(wrapper.get('[aria-label="OTHER-NOTE 实收"]').element).toHaveProperty('value', '836')
    await wrapper.get('[aria-label="OTHER-NOTE 实收"]').setValue(123)
    await wrapper.get('[role="dialog"]').get('[aria-label="OTHER-NOTE 补建正式订单"]').trigger('click')
    const otherSource = wrapper.emitted('create-order')![1]![0] as SupplierOrderSource
    authState.currentUser = { id: 'new-operator', identity: { employment_epoch: 1, effective_context_key: 'new' } }; await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(await exposed(wrapper).resumeOrderSource(otherSource)).toBe(true); await flushPromises()
    expect(wrapper.get('[aria-label="OTHER-NOTE 实收"]').element).toHaveProperty('value', '836')
    wrapper.unmount()
  })

  it('keeps unresolved source and acceptance drafts when workspace refresh fails', async () => {
    const wrapper = mount(Component, options); await flushPromises()
    await button(wrapper, '核实实际收到').trigger('click'); await flushPromises()
    await wrapper.get('[aria-label="SOURCE 实收"]').setValue(700)
    await wrapper.get('[role="dialog"]').get('[aria-label="SOURCE 补建正式订单"]').trigger('click')
    const source = emittedSource(wrapper); api.workspace.mockRejectedValueOnce(new Error('暂时读取失败'))
    expect(await exposed(wrapper).resumeOrderSource(source, 'ORDER')).toBe(false); await flushPromises()
    expect(wrapper.text()).toContain('暂时读取失败')
    expect(await exposed(wrapper).resumeOrderSource(source)).toBe(true); await flushPromises()
    expect(wrapper.get('[aria-label="SOURCE 实收"]').element).toHaveProperty('value', '700')
    wrapper.unmount()
  })

  it('does not guess a paper when the newly locked order has duplicate compatible lines', async () => {
    const data = fixture()
    data.orders[0]!.lines.push({ ...data.orders[0]!.lines[0]!, id: 'DUPLICATE', child_no: 'CT-ORDER/02', line_no: 2 })
    api.workspace.mockResolvedValue(data)
    const wrapper = mount(Component, options); await flushPromises()
    await wrapper.get('[aria-label="SOURCE 待核补建正式订单"]').trigger('click')
    const source = emittedSource(wrapper)
    expect(await exposed(wrapper).resumeOrderSource(source, 'ORDER')).toBe(true); await flushPromises()
    const target = wrapper.get<HTMLSelectElement>('[aria-label="SOURCE 验收关联订单"]')
    expect(target.findAll('option').map(row => row.attributes('value'))).toEqual(['', 'PAPER', 'DUPLICATE'])
    expect(target.element.value).toBe('')
    expect(api.linkShipmentLine).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('does not report restoration success for an unissued, unavailable or unrelated created order', async () => {
    const data = fixture(); api.workspace.mockResolvedValue(data)
    const wrapper = mount(Component, options); await flushPromises()
    await wrapper.get('[aria-label="SOURCE 待核补建正式订单"]').trigger('click')
    const source = emittedSource(wrapper)
    expect(await exposed(wrapper).resumeOrderSource(source, 'NOT-VISIBLE')).toBe(false)
    data.orders[0]!.awaiting_issue = true
    expect(await exposed(wrapper).resumeOrderSource(source, 'ORDER')).toBe(false)
    data.orders[0]!.awaiting_issue = false; data.orders[0]!.item_no = 'ANOTHER-ITEM'
    expect(await exposed(wrapper).resumeOrderSource(source, 'ORDER')).toBe(false)
    expect(api.linkShipmentLine).not.toHaveBeenCalled()
    expect(wrapper.emitted('create-order')).toHaveLength(1)
    expect(await exposed(wrapper).resumeOrderSource(source)).toBe(true)
    wrapper.unmount()
  })

  it('links only the selected original row and restores quantities, bins and price across changed line IDs and ordering', async () => {
    const data = fixture(); data.shipments[0]!.lines = [sourceLine(), sourceLine('SECOND')]; api.workspace.mockResolvedValue(data)
    const wrapper = mount(Component, options); await flushPromises()
    await button(wrapper, '核实实际收到').trigger('click'); await flushPromises()
    const dialog = wrapper.get('[role="dialog"]')
    await dialog.get('[aria-label="SOURCE 无单处理结论"]').setValue('SAMPLE')
    await dialog.get('[aria-label="SOURCE 样板箱客户"]').setValue('CUSTOMER')
    await dialog.get('[aria-label="SOURCE 样板箱需求人"]').setValue('旧样板需求人')
    await dialog.get('[aria-label="SOURCE 实收"]').setValue(800)
    await dialog.get('[aria-label="SECOND 实收"]').setValue(600)
    await dialog.get('[aria-label="SOURCE 差异原因"]').setValue('纸箱短收核实')
    await dialog.get('[aria-label="SOURCE 破损"]').setValue(2)
    await dialog.get('[aria-label="SOURCE 拒收"]').setValue(3)
    await dialog.get('[aria-label="SOURCE 其他不可用"]').setValue(4)
    await dialog.get('[aria-label="SOURCE 入库单价"]').setValue(7.5)
    wrapper.findAllComponents({ name: 'CartonReceiptAllocations' })[0]!.vm.$emit('update:modelValue', [{ location_id: 'BIN', quantity: 791 }])
    await dialog.get('[aria-label="SOURCE 验收关联客户"]').setValue('CUSTOMER')
    await dialog.get('[aria-label="SOURCE 验收关联订单"]').setValue('PAPER')
    await dialog.get('[aria-label="SOURCE 验收关联原因"]').setValue('核对补建正式订单')
    const linked = { ...data.shipments[0]!, revision: 4, lines: [sourceLine('SECOND'), { ...sourceLine('SERVER-NEW-ID'), source_type: 'FORMAL_ORDER' as const,
      original_unmatched_line_id: 'SOURCE', order_line_id: 'PAPER', packaging_type: '外箱', child_no: 'CT-ORDER/01' }] }
    api.linkShipmentLine.mockResolvedValue(linked); api.workspace.mockResolvedValue({ ...data, shipments: [linked] })
    await dialog.get('[aria-label="SOURCE 验收确认关联"]').trigger('click'); await flushPromises()
    expect(api.linkShipmentLine).toHaveBeenCalledTimes(1)
    expect(api.linkShipmentLine).toHaveBeenCalledWith('SHIPMENT', 'SOURCE', expect.objectContaining({ order_line_id: 'PAPER', expected_revision: 3, expected_order_revision: 2 }))
    expect(wrapper.get('[aria-label="SERVER-NEW-ID 实收"]').element).toHaveProperty('value', '800')
    expect(wrapper.get('[aria-label="SECOND 实收"]').element).toHaveProperty('value', '600')
    expect(wrapper.get('[aria-label="SERVER-NEW-ID 差异原因"]').element).toHaveProperty('value', '纸箱短收核实')
    expect(wrapper.findAllComponents({ name: 'CartonReceiptAllocations' })[1]!.props('modelValue')).toEqual([{ location_id: 'BIN', quantity: 791 }])
    expect(wrapper.get('[aria-label="SERVER-NEW-ID 入库单价"]').element).toHaveProperty('value', '7.5')
    expect(wrapper.get('[aria-label="SERVER-NEW-ID 破损"]').element).toHaveProperty('value', '2')
    expect(wrapper.get('[aria-label="SERVER-NEW-ID 拒收"]').element).toHaveProperty('value', '3')
    expect(wrapper.get('[aria-label="SERVER-NEW-ID 其他不可用"]').element).toHaveProperty('value', '4')
    expect(api.receive).not.toHaveBeenCalled()
    expect(api.receiptOptions).toHaveBeenCalledTimes(2)
    const restored = wrapper.get('[role="dialog"]')
    await restored.findAll('article')[0]!.findAll('button').find(row => row.text() === '此项未到')!.trigger('click')
    api.receive.mockResolvedValue({ ...linked, receipt_id: 'RECEIPT' })
    await restored.trigger('submit'); await flushPromises()
    expect(api.receive).toHaveBeenCalledTimes(1)
    expect(api.receive).toHaveBeenCalledWith('SHIPMENT', expect.objectContaining({ expected_revision: 4,
      lines: [expect.objectContaining({ shipment_line_id: 'SECOND', received_quantity: 0 }),
        expect.objectContaining({ shipment_line_id: 'SERVER-NEW-ID', received_quantity: 800, unit_price: 7.5, damaged_quantity: 2, rejected_quantity: 3, unusable_quantity: 4,
          no_order_decision: '', requested_by: '', customer_code: '', location_allocations: [{ location_id: 'BIN', quantity: 791 }] })] }))
    wrapper.unmount()
  })

  it('retains the acceptance dialog and all fields after an association rejection', async () => {
    const wrapper = mount(Component, options); await flushPromises()
    await button(wrapper, '核实实际收到').trigger('click'); await flushPromises()
    const dialog = wrapper.get('[role="dialog"]')
    await dialog.get('[aria-label="SOURCE 实收"]').setValue(700)
    await dialog.get('[aria-label="SOURCE 验收关联客户"]').setValue('CUSTOMER')
    await dialog.get('[aria-label="SOURCE 验收关联订单"]').setValue('PAPER')
    await dialog.get('[aria-label="SOURCE 验收关联原因"]').setValue('核对补建正式订单')
    api.linkShipmentLine.mockRejectedValue(new Error('本次送货数量超过正式订单需求'))
    await dialog.get('[aria-label="SOURCE 验收确认关联"]').trigger('click'); await flushPromises()
    expect(wrapper.get('[aria-label="SOURCE 实收"]').element).toHaveProperty('value', '700')
    expect(wrapper.get('[aria-label="SOURCE 验收关联订单"]').element).toHaveProperty('value', 'PAPER')
    expect(wrapper.text()).toContain('本次送货数量超过正式订单需求')
    expect(api.receive).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})

describe('supplier-origin material and draft guards', () => {
  it('accepts the approved one-way outer-carton alias while excluding real type and dimension-unit conflicts', () => {
    const source = sourceLine(), paper = fixture().orders[0]!.lines[0]!
    expect(supplierPaperCompatible(source, paper)).toBe(true)
    expect(supplierPaperCompatible({ ...source, packaging_type: '外箱' }, { ...paper, packaging_type: '普通箱' })).toBe(false)
    expect(supplierPaperCompatible(source, { ...paper, packaging_type: '内箱' })).toBe(false)
    expect(supplierPaperCompatible(source, { ...paper, dimension_unit: 'cm' })).toBe(false)
    expect(supplierPaperCompatible({ ...source, dimension_unit: 'cm' }, paper)).toBe(false)
    expect(supplierPaperCompatible({ ...source, specification: '19.875*11.25*15.375' }, { ...paper, dimension_unit: 'cm' })).toBe(true)
    expect(supplierPaperCompatible({ ...source, packaging_type: '隔板', unit: '个', specification: '10*20cm' }, { ...paper, packaging_type: '隔板', unit: '张', dimension_unit: 'cm', specification: '10*20' })).toBe(true)
  })

  it('requires intact bounded source identity and prevents draft papers from mixing another order or source', () => {
    const source: SupplierOrderSource = { factoryId: 'huaxing', shipmentId: 'S', sourceLineId: 'SOURCE', deliveryNoteNo: 'DN', supplierId: '', contractNo: 'CONTRACT', itemNo: 'ITEM', customerPo: 'PO', papers: [sourceLine()] }
    expect(isSupplierOrderSource({ ...source, createdOrderNo: 'CT-SAVED' })).toBe(true)
    expect(isSupplierOrderSource({ ...source, createdOrderNo: 3 })).toBe(false)
    expect(isSupplierOrderSource({ ...source, sourceLineId: 'MISSING' })).toBe(false)
    expect(isSupplierOrderSource({ ...source, papers: [sourceLine('SOURCE', { contract_no: 'OTHER' })] })).toBe(false)
    expect(isSupplierOrderSource({ ...source, papers: [sourceLine('SOURCE', { order_line_id: 'PAPER' })] })).toBe(false)
    expect(isSupplierOrderSource({ ...source, papers: [sourceLine('SOURCE', { quantity: 'NaN' })] })).toBe(false)
  })
})

it.each(['FREE', 'PENDING'] as const)('preserves default actual quantity and submits explicit zero-price %s', async kind => {
  const data = fixture(); data.shipments = [data.shipments[0]!]; data.shipments[0]!.lines = [sourceLine('SOURCE', { contract_no: 'GIFT-ONLY', item_no: 'GIFT-ONLY' })]
  api.workspace.mockResolvedValue(data)
  api.receive.mockResolvedValue({ ...data.shipments[0]!, receipt_id: 'RECEIPT' })
  const wrapper = mount(Component, options); await flushPromises()
  await button(wrapper, '核实实际收到').trigger('click'); await flushPromises()
  const dialog = wrapper.get('[role="dialog"]')
  expect(dialog.get('[aria-label="SOURCE 实收"]').element).toHaveProperty('value', '836')
  await dialog.get('[aria-label="SOURCE 无单处理结论"]').setValue(kind === 'FREE' ? 'GIFT' : 'SAMPLE')
  await dialog.get('[aria-label="SOURCE 样板箱客户"]').setValue('CUSTOMER')
  if (kind === 'PENDING') await dialog.get('[aria-label="SOURCE 样板箱需求人"]').setValue('纸箱部')
  else expect(dialog.get('[aria-label="SOURCE 样板箱需求人"]').attributes('required')).toBeUndefined()
  await dialog.get('[aria-label="SOURCE 入库单价"]').setValue(0)
  wrapper.findComponent({ name: 'CartonReceiptAllocations' }).vm.$emit('update:modelValue', [{ location_id: 'BIN', quantity: 836 }])
  await dialog.trigger('submit'); await flushPromises()
  expect(api.receive).toHaveBeenCalledWith('SHIPMENT', expect.objectContaining({ lines: [expect.objectContaining({ received_quantity: 836, unit_price: 0, zero_price_kind: kind })] }))
  wrapper.unmount()
})
