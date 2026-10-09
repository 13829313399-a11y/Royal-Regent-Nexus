import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CartonOrderSplitDialog from '../CartonOrderSplitDialog.vue'
import CartonSplitReceiptReview from '../CartonSplitReceiptReview.vue'
import type { CartonOrderResponse } from '@/api/cartonProcurement'
import type { SplitContext, SplitRecord } from '@/api/cartonOrderSplits'

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
const button = (wrapper: ReturnType<typeof mount>, label: string) => wrapper.findAll('button').find(item => item.text() === label)!

beforeEach(() => {
  vi.clearAllMocks()
  api.context.mockResolvedValue(structuredClone(context))
  api.create.mockResolvedValue(plan)
  api.act.mockResolvedValue({ ...plan, revision: 2, status: 'ACTIVE' })
})
afterEach(() => vi.unstubAllGlobals())

describe('订单拆分', () => {
  it('opens and retries on HTTP browsers without randomUUID, rotating the request only when inputs change', async () => {
    vi.stubGlobal('crypto', { getRandomValues: crypto.getRandomValues.bind(crypto) })
    const wrapper = mount(CartonOrderSplitDialog, { props: { order, canCreate: true, canConfirm: true }, global: { stubs } })
    try {
      await flushPromises()
      expect(api.context).toHaveBeenCalledWith('huaxing', 'CT-1')
      await wrapper.get('[aria-label="拆分 1 合同"]').setValue('NEW')
      await wrapper.get('[aria-label="拆分 1 产品数量"]').setValue(40)
      api.create.mockRejectedValue(new Error('连接中断'))
      await wrapper.get('form').trigger('submit'); await flushPromises()
      const firstRequest = api.create.mock.calls[0]![2]
      expect(firstRequest.request_id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
      expect(wrapper.get('[role="alert"]').text()).toContain('连接中断')

      await wrapper.get('form').trigger('submit'); await flushPromises()
      expect(api.create.mock.calls[1]![2]).toEqual(firstRequest)
      await wrapper.get('[aria-label="拆分 1 合同"]').setValue('CORRECTED')
      api.create.mockResolvedValue(plan)
      await wrapper.get('form').trigger('submit'); await flushPromises()
      expect(api.create.mock.calls[2]![2].request_id).not.toBe(firstRequest.request_id)
      expect(wrapper.text()).toContain('库存归属等待仓库确认')
      expect(wrapper.get('[aria-label="拆分 1 合同"]').element).toHaveProperty('value', '')
    } finally { wrapper.unmount() }
  })
  it('explains missing write permissions while keeping split records readable', async () => {
    const wrapper = mount(CartonOrderSplitDialog, { props: { order, canCreate: false, canConfirm: false }, global: { stubs } })
    await flushPromises()
    expect(wrapper.text()).toContain('当前账号可查看拆分记录')
    expect(wrapper.find('form').exists()).toBe(false)
    expect(api.create).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('分别提交待到量与指定仓位库存，使用最新上下文 revision', async () => {
    const wrapper = mount(CartonOrderSplitDialog, { props: { order, canCreate: true, canConfirm: true }, global: { stubs } })
    await flushPromises()
    await wrapper.get('[aria-label="拆分 1 合同"]').setValue('NEW')
    await wrapper.get('[aria-label="拆分 1 客户 PO"]').setValue('NEW-PO')
    await wrapper.get('[aria-label="拆分 1 产品数量"]').setValue(40)
    await wrapper.get('[aria-label="拆分 1 纸品 1 仓位 1 库存数量"]').setValue(2)
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(api.create).toHaveBeenCalledWith('huaxing', 'CT-1', expect.objectContaining({ expected_revision: 4,
      targets: [expect.objectContaining({ contract_no: 'NEW', customer_po: 'NEW-PO', product_quantity: 40,
        lines: [{ order_line_id: 'PAPER1', pending_quantity: 2, stock: [{ location_id: 'A1', expected_position_revision: 6, quantity: 2 }] }] })] }))
    expect(wrapper.text()).toContain('库存归属等待仓库确认')
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('已入库拆分必须由仓库勾选核对后确认', async () => {
    api.context.mockResolvedValue({ ...context, plans: [plan] })
    const wrapper = mount(CartonOrderSplitDialog, { props: { order, canCreate: false, canConfirm: true }, global: { stubs } })
    await flushPromises()
    const confirm = button(wrapper, '确认库存拆分')
    expect(confirm.attributes('disabled')).toBeDefined()
    await wrapper.get('input[type="checkbox"]').setValue(true)
    await confirm.trigger('click'); await flushPromises()
    expect(api.act).toHaveBeenCalledWith('huaxing', plan, 'confirm', '按客户要求拆分合同归属')
    expect(wrapper.find('form').exists()).toBe(false)
  })

  it('权限不足不显示确认或新增，版本冲突保留表单并提示', async () => {
    api.context.mockResolvedValue({ ...context, plans: [plan] })
    const read = mount(CartonOrderSplitDialog, { props: { order, canCreate: false, canConfirm: false }, global: { stubs } })
    await flushPromises()
    expect(read.text()).not.toContain('确认库存拆分')
    expect(read.find('form').exists()).toBe(false)
    api.create.mockRejectedValue(new Error('原库存已变化，请刷新'))
    const edit = mount(CartonOrderSplitDialog, { props: { order, canCreate: true, canConfirm: true }, global: { stubs } })
    await flushPromises()
    await edit.get('[aria-label="拆分 1 合同"]').setValue('NEW')
    await edit.get('form').trigger('submit'); await flushPromises()
    expect(edit.get('[role="alert"]').text()).toContain('原库存已变化')
    expect(edit.emitted('changed')).toBeUndefined()
    expect((edit.get('[aria-label="拆分 1 合同"]').element as HTMLInputElement).value).toBe('NEW')
  })
})

describe('拆单收货核对', () => {
  const allocation = { plan_id: 'CS-1', target_line_id: 'CSL-1', order_line_id: 'PAPER1', contract_no: 'NEW', customer_po: 'NEW-PO',
    item_no: '001', packaging_type: '外箱', quantity: '2', unit: '个' }
  it('必须勾选去向；有效实收变化会清除旧确认并重新预览', async () => {
    api.receiptPreview.mockResolvedValue({ confirmation: 'TOKEN1', blocked_plans: [], allocations: [allocation] })
    const wrapper = mount(CartonSplitReceiptReview, { props: { factory: 'huaxing', lines: [{ order_line_id: 'PAPER1', effective_quantity: 2 }] } })
    await flushPromises()
    expect(wrapper.text()).toContain('NEW-PO')
    expect(wrapper.emitted('update:confirmation')?.at(-1)).toEqual([''])
    await wrapper.get('input[type="checkbox"]').setValue(true)
    expect(wrapper.emitted('update:confirmation')?.at(-1)).toEqual(['TOKEN1'])
    api.receiptPreview.mockResolvedValue({ confirmation: 'TOKEN2', blocked_plans: [], allocations: [{ ...allocation, quantity: '1' }] })
    await wrapper.setProps({ lines: [{ order_line_id: 'PAPER1', effective_quantity: 1 }] }); await flushPromises()
    expect((wrapper.get('input').element as HTMLInputElement).checked).toBe(false)
    expect(wrapper.emitted('update:confirmation')?.at(-1)).toEqual([''])
  })

  it('待仓库处理的方案阻止确认，旧厂区的迟到预览不覆盖新厂区', async () => {
    let finish!: (value: unknown) => void
    api.receiptPreview.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const wrapper = mount(CartonSplitReceiptReview, { props: { factory: 'huaxing', lines: [{ order_line_id: 'PAPER1', effective_quantity: 2 }] } })
    api.receiptPreview.mockResolvedValue({ confirmation: '', blocked_plans: ['OTHER-PLAN'], allocations: [] })
    await wrapper.setProps({ factory: 'huakang-a' }); await flushPromises()
    finish({ confirmation: 'OLD', blocked_plans: [], allocations: [allocation] }); await flushPromises()
    expect(wrapper.text()).toContain('先在工作看板处理拆单')
    expect(wrapper.find('input[type="checkbox"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('NEW-PO')
  })
})
