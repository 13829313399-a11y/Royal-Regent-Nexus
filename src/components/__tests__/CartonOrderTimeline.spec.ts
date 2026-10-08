import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import CartonOrderTimeline from '../CartonOrderTimeline.vue'
import type { OrderTimelineEvent } from '@/api/cartonOrderTimeline'

const api = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/api/cartonOrderTimeline', () => ({ cartonOrderTimelineApi: api }))
const base: OrderTimelineEvent = { id: 'create', occurred_at: '2026-09-01T09:00:00+08:00', event_type: 'ORDER_CREATED', event_label: '落单', order_id: 'O1', customer_code: 'C1', customer_name: '360', contract_no: 'CONTRACT', item_no: 'ITEM', product_name: '消防车', document_no: '', material_label: '', quantity_change: null, quantity_before: null, quantity_after: null, quantity_basis: 'NONE', unit: '', reason: '', actor_name: '文员', description: '历史记录未保存当时数量' }
function data() { return { events: [base,
  { ...base, id: 'append', event_type: 'ORDER_APPENDED', event_label: '追加', quantity_change: '20', quantity_before: '100', quantity_after: '120', quantity_basis: 'ORDER_PRODUCT', unit: '件', description: '', reason: '客户追加' },
  { ...base, id: 'reduce', event_type: 'ORDER_REDUCED', event_label: '减单', quantity_change: '-10', quantity_before: '120', quantity_after: '110', quantity_basis: 'ORDER_PRODUCT', unit: '件', description: '' },
  { ...base, id: 'in', event_type: 'INBOUND', event_label: '确认入库', quantity_change: '2', quantity_basis: 'INVENTORY', unit: '个', material_label: '外箱 A33', document_no: 'DN-1', description: '' },
] } }
function open(orderId = 'O1') { return mount(CartonOrderTimeline, { props: { factoryId: 'huaxing', customerCode: 'C1', dateFrom: '', dateTo: '', search: '', orderId, inventoryKey: '', targetLabel: 'CONTRACT · ITEM', refreshKey: 0 } }) }
beforeEach(() => { vi.clearAllMocks(); api.get.mockResolvedValue(data()) })
describe('订单流水明细', () => {
  it('shows business changes once and omits procedural steps from rows, filters and counts', async () => {
    const procedural = [
      ['RECEIPT_DRAFT_CREATED', '保存收料单'], ['ORDER_SUBMITTED_SUPPLIER', '确认订单并锁定'],
      ['PURCHASE_ORDER_ISSUED', '生成供应商采购单'], ['RECEIPT_CONFIRMED', '确认收料（无有效入库）'],
      ['INVENTORY_PRICE_CONFIRMED', '入库核价'], ['ORDER_UPDATED', '修改订单'],
    ].map(([event_type, event_label], index) => ({ ...base, id: `process-${index}`, event_type, event_label }))
    const changes = [
      { ...base, id: 'out', event_type: 'OUTBOUND', event_label: '出库', quantity_basis: 'INVENTORY', quantity_change: '-1', unit: '个' },
      { ...base, id: 'reverse', event_type: 'REVERSAL', event_label: '出库冲销', quantity_basis: 'INVENTORY', quantity_change: '1', unit: '个' },
      { ...base, id: 'adjust', event_type: 'ADJUSTMENT', event_label: '盘点调整', quantity_basis: 'INVENTORY', quantity_change: '-2', unit: '个' },
      { ...base, id: 'move', event_type: 'INVENTORY_LOCATION_CHANGED', event_label: '调仓', description: '仓位：A01 → B02；数量不变。' },
      { ...base, id: 'cancel', event_type: 'ORDER_CANCELLED', event_label: '取消订单' },
      { ...base, id: 'return', event_type: 'ORDER_RETURNED', event_label: '退单' },
    ]
    api.get.mockResolvedValue({ events: [...data().events, ...procedural, ...changes] })
    const wrapper = open(); await flushPromises()
    expect(wrapper.get('tbody').findAll('tr')).toHaveLength(10)
    expect(wrapper.text()).toContain('10 条记录')
    for (const event of procedural) {
      expect(wrapper.get('tbody').text()).not.toContain(event.event_label)
      expect(wrapper.get('select').text()).not.toContain(event.event_label)
    }
    for (const event of changes) expect(wrapper.get('tbody').text()).toContain(event.event_label)
    expect(wrapper.get('[aria-label="订单基本信息"]').text()).toContain('360')
    expect(wrapper.get('[aria-label="订单基本信息"]').text()).toContain('消防车')
    expect(wrapper.get('tbody').text()).not.toContain('CONTRACT')
    expect(wrapper.get('tbody').text()).not.toContain('消防车')
    expect(wrapper.get('thead').findAll('th').map(cell => cell.text())).toEqual(['时间', '事项', '纸品 / 单据', '数量变动', '备注', '经手人'])
  })
  it('never loads an unscoped all-orders timeline', async () => {
    const wrapper = open(''); await flushPromises()
    expect(api.get).not.toHaveBeenCalled()
    expect(wrapper.find('tbody').text()).toContain('没有订单流水记录')
  })
  it('shows frozen order quantities separately from inventory quantities and preserves missing history', async () => {
    const wrapper = open(); await flushPromises()
    const rows = wrapper.get('tbody').findAll('tr')
    expect(rows[0]!.text()).toContain('历史记录未保存当时数量')
    expect(rows[1]!.text()).toContain('订单产品')
    expect(rows[1]!.text()).toContain('+20 件')
    expect(rows[1]!.text()).toContain('100 → 120 件')
    expect(rows[2]!.text()).toContain('-10 件')
    expect(rows[3]!.text()).toContain('库存纸品')
    expect(rows[3]!.text()).toContain('+2 个')
    expect(wrapper.get('table').findAll('button')).toHaveLength(0)
  })
  it('filters event kinds and reverses complete sequence without dropping records', async () => {
    const wrapper = open(); await flushPromises()
    await wrapper.get('[aria-label="订单流水操作筛选"]').setValue('ORDER_REDUCED|减单')
    expect(wrapper.get('tbody').findAll('tr')).toHaveLength(1)
    expect(wrapper.get('tbody').text()).toContain('减单')
    await wrapper.get('[aria-label="订单流水操作筛选"]').setValue('')
    await wrapper.get('[aria-label="订单流水排序"]').setValue('DESC')
    expect(wrapper.get('tbody').findAll('tr')[0]!.text()).toContain('确认入库')
  })
  it('passes exact order and date scope without an all-orders entry', async () => {
    const wrapper = open(); await flushPromises()
    await wrapper.setProps({ dateFrom: '2026-09-01', dateTo: '2026-09-07' }); await flushPromises()
    expect(api.get.mock.lastCall).toEqual(['huaxing', { customer_code: 'C1', date_from: '2026-09-01', date_to: '2026-09-07', search: '', order_id: 'O1', inventory_key: '' }])
    expect(wrapper.text()).not.toContain('查看全部订单')
  })
  it('does not restore records from an earlier factory request and clears data on failure', async () => {
    let finish!: (data: unknown) => void
    api.get.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const wrapper = open(); await flushPromises()
    api.get.mockResolvedValue({ events: [] })
    await wrapper.setProps({ factoryId: 'huakang_a', orderId: 'O2' }); await flushPromises()
    finish(data()); await flushPromises()
    expect(wrapper.text()).not.toContain('客户追加')
    api.get.mockRejectedValueOnce(new Error('failed'))
    await wrapper.setProps({ refreshKey: 1 }); await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(wrapper.find('table').exists()).toBe(false)
  })
})
