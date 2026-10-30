import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CartonOrderSplitDialog from '../CartonOrderSplitDialog.vue'
import CartonSplitReceiptReview from '../CartonSplitReceiptReview.vue'
import type { CartonOrderResponse } from '@/api/cartonProcurement'
import type { SplitContext, SplitRecord } from '@/api/cartonOrderSplits'
import { allocateSplitTargets, type SplitDraftTarget } from '@/features/carton-procurement/splitAllocation'

const divisionApi = vi.hoisted(() => ({ context: vi.fn() }))
vi.mock('@/api/cartonOrderDivisions', () => ({ cartonOrderDivisionsApi: divisionApi }))
const api = vi.hoisted(() => ({ context: vi.fn(), create: vi.fn(), act: vi.fn(), receiptPreview: vi.fn() }))
vi.mock('@/api/cartonOrderSplits', () => ({ cartonOrderSplitsApi: api }))
const order: CartonOrderResponse = {
  id: 'ORDER1', factory_id: 'huaxing', order_no: 'CT-1', customer_code: 'BUZZ', customer_name: 'BUZZ', supplier_id: 'SUP1',
  supplier_name: '供应商', contract_no: 'OLD', customer_po: 'OLD-PO', item_no: '001', product_name: '产品', quantity_basis: 'CALCULATED',
  product_order_quantity: '100', order_date: '2026-09-01', due_date: '2026-09-30', status: 'PARTIALLY_RECEIVED', note: '', revision: 4,
  created_by: 'u1', created_by_name: '用户', updated_by: 'u1', updated_by_name: '用户', created_at: '', updated_at: '',
  lines: [{ id: 'PAPER1', line_no: 1, packaging_type: '外箱', paper_quality: 'A33', specification: '18*12*10', dimension_unit: 'cm',
    usage_quantity: '10', required_quantity: '10', received_quantity: '3', remaining_quantity: '7', unit: '个', unit_price: '1',
    currency: 'CNY', price_source: 'manual', note: '' }],
}
const plan: SplitRecord = {
  id: 'CS-1', factory_id: 'huaxing', order_id: 'ORDER1', order_no: 'CT-1', item_no: '001', customer_code: 'BUZZ',
  status: 'PENDING_WAREHOUSE', revision: 1, reason: '客户拆单', created_at: '2026-09-28', created_by_name: '用户',
  targets: [{ contract_no: 'NEW', customer_po: 'NEW-PO', product_quantity: '40', lines: [{ order_line_id: 'PAPER1', target_line_id: 'CSL-1',
    pending_quantity: '2', pending_remaining: '2', received_quantity: '0', packaging_type: '外箱', paper_quality: 'A33',
    specification: '18*12*10', unit: '个', stock: [{ location_id: 'A1', expected_position_revision: 6, quantity: '2' }] }] }],
}
const context: SplitContext = {
  factory_id: 'huaxing', order_no: 'CT-1', revision: 4, plans: [],
  lines: [{ order_line_id: 'PAPER1', packaging_type: '外箱', paper_quality: 'A33', specification: '18*12*10', unit: '个',
    usage_quantity: '10', required_quantity: '10', pending_available: '7', positions: [{ inventory_key: 'PAPER1', factory_id: 'huaxing',
      customer_code: 'BUZZ', customer_name: 'BUZZ', contract_no: 'OLD', item_no: '001', order_line_id: 'PAPER1', packaging_type: '外箱',
      paper_quality: 'A33', specification: '18*12*10', unit: '个', balance: '3', location_id: 'A1', position_revision: 6,
      latest_location: 'A车间／A1', location_revision: 0, latest_movement_id: 'IN1', latest_document_no: 'DN1', latest_movement_at: '',
      latest_inbound_at: '', position_key: '["PAPER1","A1"]' }] }],
}
const stubs = Object.fromEntries(['DialogRoot', 'DialogOverlay', 'DialogContent', 'DialogTitle', 'DialogDescription']
  .map(name => [name, { template: '<div><slot /></div>' }]))

beforeEach(() => {
  vi.clearAllMocks()
  api.context.mockResolvedValue(structuredClone(context))
  divisionApi.context.mockResolvedValue({ ...structuredClone(context), can_split: true, previous_proposals: [], order_split: null })
  api.create.mockResolvedValue(plan)
  api.act.mockResolvedValue({ ...plan, revision: 2, status: 'ACTIVE' })
})
afterEach(() => vi.unstubAllGlobals())

describe('统一拆单入口与历史记录', () => {
  it('默认打开真实拆单面板，不再提供旧数量分配表单', async () => {
    const wrapper = mount(CartonOrderSplitDialog, { props: { order, canCreate: true, canConfirm: true }, global: { stubs: { ...stubs, CartonIndependentSplitPanel: { template: '<div data-testid="real-split">真实拆单</div>' } } } })
    await flushPromises()
    expect(wrapper.find('[data-testid="real-split"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="拆单用途"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('子单独立送货、收料及库存核算')
    expect(api.create).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('历史库存记录只允许查看和显式撤销，不再新增库存分配', async () => {
    divisionApi.context.mockResolvedValue({ ...context, plans: [plan], can_split: false, previous_proposals: [], order_split: null })
    const wrapper = mount(CartonOrderSplitDialog, { props: { order, canCreate: false, canConfirm: true }, global: { stubs: { ...stubs, CartonIndependentSplitPanel: true } } })
    await flushPromises()
    expect(wrapper.text()).toContain('旧数量分配记录')
    expect(wrapper.text()).toContain('当前账号可查看记录')
    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('确认库存拆分')
    wrapper.unmount()
  })
})

describe('单数量拆分分配', () => {
  const draft = (products: string | number | null, quantity: string | number = ''): SplitDraftTarget => ({
    contract_no: 'NEW', customer_po: '', product_quantity: products, lines: [{ order_line_id: 'PAPER1', quantity }],
  })
  it('已全部收货时自动从可用库存分配', () => {
    const result = allocateSplitTargets(order, { ...context, lines: [{ ...context.lines[0]!, pending_available: '0' }] }, [draft(20)])
    expect(result.errors).toEqual([])
    expect(result.targets[0]!.lines[0]).toEqual({ order_line_id: 'PAPER1', pending_quantity: '0', stock: [{ location_id: 'A1', expected_position_revision: 6, quantity: '2' }] })
  })
  it('多个目标共享待到及各仓位余额，修改或移除前项会重新分配', () => {
    const next = { ...context, lines: [{ ...context.lines[0]!, pending_available: '2', positions: [context.lines[0]!.positions[0]!, { ...context.lines[0]!.positions[0]!, location_id: 'A2', balance: '3', position_revision: 8 }] }] }
    const result = allocateSplitTargets(order, next, [draft(40), draft(40)])
    expect(result.errors).toEqual([])
    expect(result.targets[0]!.lines[0]).toMatchObject({ pending_quantity: '2', stock: [{ location_id: 'A1', quantity: '2' }] })
    expect(result.targets[1]!.lines[0]).toMatchObject({ pending_quantity: '0', stock: [{ location_id: 'A1', quantity: '1' }, { location_id: 'A2', quantity: '3' }] })
    expect(allocateSplitTargets(order, next, [draft(40)]).targets[0]!.lines[0]).toEqual(result.targets[0]!.lines[0])
    expect(allocateSplitTargets(order, next, [draft(40), draft(50)]).errors.join()).toContain('超过剩余可分配 4')
    expect(next.lines[0]!.positions[0]!.balance).toBe('3')
  })
  it('只扣待仓库确认的库存预占，不重复扣已由context扣除的待到或已生效库存', () => {
    const next = { ...context, plans: [plan, { ...plan, id: 'ACTIVE', status: 'ACTIVE' as const }], lines: [{ ...context.lines[0]!, pending_available: '2' }] }
    const result = allocateSplitTargets({ ...order, product_order_quantity: '200' }, next, [draft(30)])
    expect(result.errors).toEqual([])
    expect(result.targets[0]!.lines[0]).toMatchObject({ pending_quantity: '2', stock: [{ location_id: 'A1', quantity: '1' }] })
    expect(allocateSplitTargets({ ...order, product_order_quantity: '200' }, next, [draft(40)]).errors.join()).toContain('超过剩余可分配 3')
  })
  it('四位小数通过定点分配，拒绝过多精度与计数单位小数', () => {
    const explicit = { ...order, quantity_basis: 'EXPLICIT' as const, product_order_quantity: null }
    const next = { ...context, lines: [{ ...context.lines[0]!, unit: '米', pending_available: '0.1', positions: [{ ...context.lines[0]!.positions[0]!, balance: '0.2001' }] }] }
    const result = allocateSplitTargets(explicit, next, [draft(null, '0.3001')])
    expect(result.errors).toEqual([])
    expect(result.targets[0]!.lines[0]).toMatchObject({ pending_quantity: '0.1', stock: [{ quantity: '0.2001' }] })
    expect(allocateSplitTargets(explicit, next, [draft(null, '0.30001')]).errors.join()).toContain('最多四位小数')
    expect(allocateSplitTargets(explicit, context, [draft(null, '0.5')]).errors.join()).toContain('必须为整数')
  })
  it('手动纸品拆分数作为配套纸品计算基数，不沿用原单手动总量', () => {
    const paired = { ...order, lines: [{ ...order.lines[0]!, quantity_rule: { mode: 'PACKING' as const, manual_quantity: '10' } },
      { ...order.lines[0]!, id: 'CARD', line_no: 2, quantity_rule: { mode: 'PER_CARTON' as const, carton_line_no: 1, per_carton_quantity: '2' } }] }
    const next = { ...context, lines: [...context.lines, { ...context.lines[0]!, order_line_id: 'CARD', pending_available: '20', positions: [] }] }
    const target = draft(20, '3'); target.lines.push({ order_line_id: 'CARD', quantity: '' })
    const result = allocateSplitTargets(paired, next, [target])
    expect(result.errors).toEqual([])
    expect(result.targets[0]!.lines.map(line => line.pending_quantity)).toEqual(['3', '6'])
    expect(allocateSplitTargets(order, context, [draft(60), draft(50)]).errors.join()).toContain('产品数量超过')
  })
})

describe('旧拆单收货保护', () => {
  it('不再提供分配确认，明确要求转换后按各订单收料', async () => {
    const wrapper = mount(CartonSplitReceiptReview, { props: { factory: 'huaxing', lines: [{ order_line_id: 'PAPER1', effective_quantity: 2 }] } })
    await flushPromises()
    expect(wrapper.text()).toContain('转为独立订单后分别收料')
    expect(wrapper.find('input').exists()).toBe(false)
    expect(api.receiptPreview).not.toHaveBeenCalled()
    expect(wrapper.emitted('update:confirmation')?.at(-1)).toEqual([''])
    wrapper.unmount()
  })
})
