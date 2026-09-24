import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CartonSupplierView from '../CartonSupplierView.vue'
import CartonSupplierManagementView from '../CartonSupplierManagementView.vue'
import CartonSupplierMarkTemplatesView from '../CartonSupplierMarkTemplatesView.vue'
import CartonReceiptAllocations from '@/components/CartonReceiptAllocations.vue'
import type { PortalWorkspace } from '@/api/cartonSupplierPortal'
const api = vi.hoisted(() => ({ memberships: vi.fn(), workspace: vi.fn(), accept: vi.fn(), acceptBatch: vi.fn(), ship: vi.fn(), receive: vi.fn(), members: vi.fn(), member: vi.fn(), upload: vi.fn(), download: vi.fn(), markTemplates: vi.fn(), downloadMarkDocument: vi.fn(), previewMarkPdfUrl: vi.fn(), documents: vi.fn(), activity: vi.fn(), exportDocuments: vi.fn() }))
const router = vi.hoisted(() => ({ replace: vi.fn() }))
const can = vi.hoisted(() => vi.fn((_permission: string) => true))
vi.mock('@/api/cartonSupplierPortal', () => ({ cartonSupplierPortalApi: api }))
vi.mock('@/api/cartonPositions', () => ({ cartonPositionsApi: { locations: vi.fn(async () => [{ id: 'BIN-A', factory_id: 'huaxing', warehouse: 'A', bin_code: '01', label: 'A / 01', status: 'ACTIVE' }]) } }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ can }) }))
vi.mock('@/stores/app', () => ({ useAppStore: () => ({ activeProductionFactory: { id: 'huaxing' } }) }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: { factory: 'huaxing' } }), useRouter: () => router, RouterLink: { name: 'RouterLink', props: ['to'], template: '<a><slot /></a>' } }))
function fixture(): PortalWorkspace {
  return { factory_id: 'huaxing', supplier_name: '河源东康', orders: [{ id: 'ORDER-A', order_no: 'ORDER-A', customer_name: 'Dickie', contract_no: 'SC-A', customer_po: 'PO-A', item_no: 'ITEM-A', product_name: '产品', status: 'PENDING_SUPPLIER', issue_id: 'ISSUE-A', document_no: 'ORDER-A-P00', order_date: '2026-09-10', planned_date: '2026-09-25', awaiting_issue: false, attachments: [], lines: ['外箱', '平卡'].map((name, index) => ({ id: `LINE-${index}`, line_no: index+1, child_no: `ORDER-A/0${index+1}`, packaging_type: name, paper_quality: 'A33', specification: '10*20', dimension_unit: 'cm', unit: index ? '张' : '个', required_quantity: '100', received_quantity: '0', in_transit_quantity: '0', remaining_to_ship: '100', accepted: true, commitment_revision: 1, promised_date: '2026-09-25' })) }], shipments: [{ id: 'SHIP-A', delivery_note_no: 'DN-A', delivery_date: '2026-09-21', status: 'SENT', revision: 1, created_at: '', confirmed_at: '', acceptance_date: null, acceptance_lines: [], lines: [0,1].map(index => ({ id: `SL-${index}`, order_line_id: `LINE-${index}`, order_no: 'ORDER-A', contract_no: 'SC-A', customer_po: 'PO-A', item_no: 'ITEM-A', customer_name: 'Dickie', child_no: `ORDER-A/0${index+1}`, packaging_type: index ? '平卡' : '外箱', paper_quality: 'A33', specification: '10*20', unit: '个', quantity: '10', unit_price: '2', currency: 'CNY' })) }] }
}
const options = { global: { stubs: { AccountMenu: true, RouterLink: { template: '<a><slot /></a>' }, CartonReceiptAllocations: true } } }
beforeEach(() => { vi.resetAllMocks(); can.mockReturnValue(true); api.memberships.mockResolvedValue([{ factory_id: 'huaxing', supplier_name: '河源东康' }]); api.workspace.mockResolvedValue(fixture()); api.members.mockResolvedValue([]); api.ship.mockResolvedValue({ id: 'NEW' }); api.acceptBatch.mockResolvedValue({ order_ids: [] }); api.documents.mockResolvedValue([]); api.activity.mockResolvedValue([]); api.exportDocuments.mockResolvedValue(undefined); api.receive.mockResolvedValue({ id: 'SHIP-A' }); api.markTemplates.mockResolvedValue([]); api.previewMarkPdfUrl.mockReturnValue('/api/preview.pdf') })

describe('supplier carton mark templates', () => {
  it('discovers a newly ordering service factory when refreshed', async () => {
    const factories = [
      { factory_id: 'huaxing', supplier_name: '河源东康' },
      { factory_id: 'huakang-a', supplier_name: '河源东康' },
    ]
    api.memberships.mockResolvedValueOnce([factories[0]]).mockResolvedValue(factories)
    const wrapper = mount(CartonSupplierMarkTemplatesView, options); await flushPromises()
    expect(wrapper.get('select[aria-label="箱唛资料厂区"]').findAll('option')).toHaveLength(1)
    await wrapper.findAll('button').find(button => button.text() === '刷新')!.trigger('click'); await flushPromises()
    expect(wrapper.get('select[aria-label="箱唛资料厂区"]').findAll('option').map(option => option.attributes('value'))).toEqual(['huaxing', 'huakang-a'])
    wrapper.unmount()
  })
  it('lists only the scoped read-only template response and offers PDF viewing plus both downloads', async () => {
    api.markTemplates.mockResolvedValue([{ id: 'mark-1', customer_name: 'Dickie', po: 'PO-A', item: 'ITEM-A', contract_number: 'SC-A', version: 2, check_status: '核对通过', manual_released: false, excel_file_name: 'customer.xlsx', pdf_file_name: 'print.pdf', created_at: '2026-09-21' }])
    const wrapper = mount(CartonSupplierMarkTemplatesView, options); await flushPromises()
    expect(api.markTemplates).toHaveBeenCalledWith('huaxing')
    expect(wrapper.text()).toContain('Dickie · ITEM-A · 第 2 版')
    expect(wrapper.get('a[aria-label="查看 mark-1 印刷 PDF"]').attributes('href')).toBe('/api/preview.pdf')
    await wrapper.get('button[aria-label="下载 mark-1 客人 Excel"]').trigger('click'); await flushPromises()
    expect(api.downloadMarkDocument).toHaveBeenCalledWith('mark-1', 'source_excel', 'huaxing', 'customer.xlsx')
    await wrapper.get('button[aria-label="下载 mark-1 印刷 PDF"]').trigger('click'); await flushPromises()
    expect(api.downloadMarkDocument).toHaveBeenCalledWith('mark-1', 'print_pdf', 'huaxing', 'print.pdf')
    expect(wrapper.find('input[type="file"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('does not request templates when the account has no supplier membership', async () => {
    api.memberships.mockResolvedValue([])
    const wrapper = mount(CartonSupplierMarkTemplatesView, options); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('暂无可查看的已下单厂区')
    expect(api.markTemplates).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})

describe('supplier batches and document desk', () => {
  it('shows business-date delivery reminders without NaN for invalid dates or completed orders', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-09-23T04:00:00Z'))
    try {
      const data = fixture()
      const source = data.orders[0]!
      const variant = (id: string, plannedDate: string, status = source.status) => {
        const order = structuredClone(source)
        order.id = id
        order.order_no = id
        order.planned_date = plannedDate
        order.status = status
        order.lines.forEach((line, index) => { line.id = `${id}-${index}`; line.child_no = `${id}/0${index + 1}` })
        return order
      }
      data.orders = [
        variant('OVERDUE', '2026-09-20'), variant('TODAY', '2026-09-23'),
        variant('TOMORROW', '2026-09-24'), variant('SOON', '2026-09-26'),
        variant('LATER', '2026-09-27'), variant('INVALID', '2026-02-30'),
        variant('COMPLETED', '2026-09-20', 'COMPLETED'),
      ]
      api.workspace.mockResolvedValue(data)
      const wrapper = mount(CartonSupplierView, options); await flushPromises()
      expect(wrapper.findAll('table')[0]!.find('thead').text()).toContain('交期提醒')
      const rowText = (id: string) => wrapper.findAll('table')[0]!.findAll('tbody tr')
        .find(row => row.find(`button[aria-label="查看订单 ${id} 明细"]`).exists())!.text()
      expect(rowText('OVERDUE')).toContain('已逾期 3 天')
      expect(rowText('TODAY')).toContain('今日交期')
      expect(rowText('TOMORROW')).toContain('明日交期')
      expect(rowText('SOON')).toContain('剩 3 天')
      expect(rowText('LATER')).toContain('距交期 4 天')
      expect(rowText('INVALID')).toContain('交期待确认')
      expect(rowText('COMPLETED')).toContain('交付已完成')
      expect(wrapper.text()).not.toContain('NaN')
      wrapper.unmount()
    } finally {
      vi.useRealTimers()
    }
  })

  it('shows selected orders even when the current filters hide them', async () => {
    const data = fixture()
    const second = structuredClone(data.orders[0]!)
    second.id = 'ORDER-B'
    second.order_no = 'ORDER-B'
    second.customer_name = 'BUZZ'
    second.lines.forEach((line, index) => { line.id = `B-LINE-${index}`; line.child_no = `ORDER-B/0${index + 1}` })
    data.orders.push(second)
    api.workspace.mockResolvedValue(data)
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.get('input[aria-label="选择订单 ORDER-A"]').setValue(true)
    await wrapper.get('select[aria-label="供应商订单客户筛选"]').setValue('BUZZ')
    expect(wrapper.find('input[aria-label="选择订单 ORDER-A"]').exists()).toBe(false)
    await wrapper.findAll('button').find(button => button.text() === '查看已选')!.trigger('click')
    expect(wrapper.get('input[aria-label="选择订单 ORDER-A"]').exists()).toBe(true)
    await wrapper.get('input[aria-label="选择订单 ORDER-A"]').setValue(false)
    expect(wrapper.text()).toContain('已选 0 张订单')
    wrapper.unmount()
  })

  it('keeps another paper\'s unsaved promised date after one paper is accepted', async () => {
    const data = fixture()
    data.orders[0]!.lines.forEach(line => { line.accepted = false; line.commitment_revision = 0 })
    api.workspace.mockImplementation(async () => structuredClone(data))
    api.accept.mockImplementation(async () => { data.orders[0]!.lines[0]!.accepted = true })
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.get('button[aria-label="确认订单 ORDER-A 接单"]').trigger('click')
    await wrapper.get('input[aria-label="ORDER-A/02 承诺交期"]').setValue('2026-10-05')
    await wrapper.get('input[aria-label="ORDER-A/01 承诺交期"]').setValue('2026-10-01')
    await wrapper.get('[role="dialog"]').findAll('button').find(button => button.text() === '确认接单')!.trigger('click'); await flushPromises()
    expect(wrapper.get<HTMLInputElement>('input[aria-label="ORDER-A/02 承诺交期"]').element.value).toBe('2026-10-05')
    wrapper.unmount()
  })

  it('reports the completed factory if a later factory rejects a batch', async () => {
    const first = fixture()
    first.orders[0]!.lines.forEach(line => { line.accepted = false; line.commitment_revision = 0 })
    const second = structuredClone(first)
    second.factory_id = 'huakang-a'
    second.orders[0]!.id = 'ORDER-K'
    second.orders[0]!.order_no = 'ORDER-K'
    second.orders[0]!.lines.forEach((line, index) => { line.id = `K-LINE-${index}`; line.child_no = `ORDER-K/0${index + 1}` })
    api.memberships.mockResolvedValue([
      { factory_id: 'huaxing', supplier_name: '河源东康' },
      { factory_id: 'huakang-a', supplier_name: '河源东康' },
    ])
    api.workspace.mockImplementation(async (scope: string) => structuredClone(scope === 'huaxing' ? first : second))
    api.acceptBatch.mockImplementation(async (scope: string) => {
      if (scope === 'huakang-a') throw new Error('版本已变更')
      first.orders[0]!.lines.forEach(line => { line.accepted = true })
      return { order_ids: ['ORDER-A'] }
    })
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.get('input[aria-label="全选当前筛选订单"]').setValue(true)
    await wrapper.findAll('button').find(button => button.text() === '批量确认接单')!.trigger('click')
    await wrapper.findAll('button').find(button => button.text() === '确认所选订单接单')!.trigger('click'); await flushPromises()
    expect(api.acceptBatch.mock.calls.map(call => call[0])).toEqual(['huaxing', 'huakang-a'])
    expect(wrapper.get('[role="alert"]').text()).toContain('已完成 华兴')
    expect(wrapper.get('[role="alert"]').text()).toContain('版本已变更')
    expect(wrapper.get('[role="dialog"]').text()).toContain('ORDER-K')
    wrapper.unmount()
  })

  it('confirms multiple selected orders before allowing a shipment', async () => {
    const data = fixture()
    const first = data.orders[0]!
    first.lines.forEach(line => { line.accepted = false; line.commitment_revision = 0 })
    const second = structuredClone(first)
    second.id = 'ORDER-B'
    second.order_no = 'ORDER-B'
    second.lines.forEach((line, index) => { line.id = `B-LINE-${index}`; line.child_no = `ORDER-B/0${index + 1}` })
    data.orders.push(second)
    api.workspace.mockImplementation(async () => structuredClone(data))
    api.acceptBatch.mockImplementation(async (_factory: string, lines: { order_line_id: string }[]) => {
      for (const order of data.orders) for (const line of order.lines) {
        if (lines.some(item => item.order_line_id === line.id)) line.accepted = true
      }
      return { order_ids: data.orders.map(order => order.id) }
    })
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(wrapper.findAll('table')[0]!.find('thead').text()).toContain('送货进度')
    await wrapper.get('input[aria-label="全选当前筛选订单"]').setValue(true)
    await wrapper.findAll('button').find(button => button.text() === '将所选订单加入发货')!.trigger('click')
    expect(wrapper.get('[role="alert"]').text()).toContain('尚未完成接单')
    expect(api.ship).not.toHaveBeenCalled()
    await wrapper.findAll('button').find(button => button.text() === '批量确认接单')!.trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('2 张订单')
    await wrapper.findAll('button').find(button => button.text() === '确认所选订单接单')!.trigger('click')
    await flushPromises()
    expect(api.acceptBatch).toHaveBeenCalledTimes(1)
    expect(api.acceptBatch.mock.calls[0]?.[0]).toBe('huaxing')
    expect(api.acceptBatch.mock.calls[0]?.[1]).toHaveLength(4)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    await wrapper.findAll('button').find(button => button.text() === '将所选订单加入发货')!.trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('登记本次发货')
    wrapper.unmount()
  })

  it('filters, inspects and exports selected purchase and delivery documents', async () => {
    const rows = [
      { id: 'I-1', kind: 'PURCHASE', factory_id: 'huaxing', document_no: 'PO-1', document_type: 'INITIAL', date: '2026-09-21', created_at: '2026-09-21T10:00:00', status: '已发行', replenishment: false,
        orders: [{ order_no: 'ORDER-A', customer_name: 'Dickie', contract_no: 'SC-A', customer_po: 'PO-A', item_no: 'ITEM-A', product_name: '产品', order_date: '2026-09-10', planned_date: '2026-09-25' }],
        lines: [{ order_no: 'ORDER-A', child_no: 'ORDER-A/01', packaging_type: '外箱', paper_quality: 'A33', specification: '10*20', unit: '个', before_quantity: '0', change_quantity: '100', quantity: '100' }] },
      { id: 'S-1', kind: 'DELIVERY', factory_id: 'huaxing', document_no: 'DN-1', document_type: 'DELIVERY', date: '2026-09-22', created_at: '2026-09-22T10:00:00', status: 'SENT', replenishment: false,
        orders: [{ order_no: 'ORDER-A', customer_name: 'Dickie', contract_no: 'SC-A', customer_po: 'PO-A', item_no: 'ITEM-A', product_name: '', order_date: '', planned_date: '' }],
        lines: [{ order_no: 'ORDER-A', child_no: 'ORDER-A/01', packaging_type: '外箱', paper_quality: 'A33', specification: '10*20', unit: '个', quantity: '10', received_quantity: '0' }] },
    ]
    api.documents.mockResolvedValue(rows)
    api.activity.mockResolvedValue([{ id: 'LOG-1', factory_id: 'huaxing', created_at: '2026-09-22T10:00:00', action: '送货单已登记', reference_no: 'DN-1', actor_name: '供应商' }])
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(wrapper.findAll('a').some(link => link.text().includes('箱唛资料模板'))).toBe(true)
    await wrapper.findAll('button').find(button => button.text().includes('采购单与送货单'))!.trigger('click'); await flushPromises()
    expect(api.documents).toHaveBeenCalledWith('huaxing')
    expect(wrapper.text()).toContain('PO-1')
    expect(wrapper.text()).toContain('DN-1')
    await wrapper.get('select[aria-label="单据类型筛选"]').setValue('PURCHASE')
    expect(wrapper.text()).toContain('PO-1')
    expect(wrapper.text()).not.toContain('DN-1')
    await wrapper.get('select[aria-label="单据类型筛选"]').setValue('')
    await wrapper.get('input[aria-label="全选当前筛选单据"]').setValue(true)
    await wrapper.findAll('button').find(button => button.text().includes('导出所选'))!.trigger('click'); await flushPromises()
    expect(api.exportDocuments).toHaveBeenCalledWith(expect.arrayContaining(rows))
    await wrapper.findAll('button').filter(button => button.text() === '明细')[0]!.trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('SC-A')
    expect(wrapper.get('[role="dialog"]').text()).toContain('外箱')
    await wrapper.get('button[aria-label="关闭单据明细"]').trigger('click')
    await wrapper.findAll('button').find(button => button.text() === '操作日志')!.trigger('click'); await flushPromises()
    expect(api.activity).toHaveBeenCalledWith('huaxing')
    expect(wrapper.text()).toContain('送货单已登记')
    wrapper.unmount()
  })
})
describe('supplier collaboration entry', () => {
  it('shows the business order date without the order number and previews details before pinning them', async () => {
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    const ledger = wrapper.findAll('table')[0]!
    expect(ledger.find('thead').text()).toContain('下单日期')
    expect(ledger.find('thead').text()).not.toContain('客户 / 订单')
    expect(ledger.find('tbody').text()).toContain('2026-09-10')
    expect(ledger.find('tbody').text()).not.toContain('ORDER-A')
    const button = wrapper.get('button[aria-label="查看订单 ORDER-A 明细"]')
    await button.trigger('mouseenter')
    expect(wrapper.get('[role="dialog"]').text()).toContain('悬停预览')
    expect(wrapper.get('[role="dialog"]').attributes('inert')).toBeDefined()
    await button.trigger('mouseleave')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    await button.trigger('click')
    expect(wrapper.get('[role="dialog"]').attributes('aria-modal')).toBe('true')
    expect(wrapper.get('[role="dialog"]').attributes('inert')).toBeUndefined()
    await button.trigger('mouseleave')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })); await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('filters issued orders by acceptance, warehouse confirmation, completion and cancellation stage', async () => {
    const data = fixture()
    const source = data.orders[0]!
    const variant = (id: string) => {
      const order = structuredClone(source)
      order.id = id
      order.order_no = id
      order.lines = order.lines.map((line, index) => ({ ...line, id: `${id}-${index}`, child_no: `${id}/0${index + 1}` }))
      return order
    }
    const pending = variant('ORDER-PENDING'); pending.lines[0]!.accepted = false
    const accepted = variant('ORDER-ACCEPTED')
    const waiting = variant('ORDER-WAITING'); waiting.status = 'PARTIALLY_RECEIVED'; waiting.lines[0]!.received_quantity = '5'; waiting.lines[0]!.remaining_to_ship = '95'
    const inTransit = variant('ORDER-TRANSIT'); inTransit.status = 'PARTIALLY_RECEIVED'; inTransit.lines[0]!.in_transit_quantity = '5'; inTransit.lines[0]!.remaining_to_ship = '95'
    const completed = variant('ORDER-COMPLETE'); completed.status = 'COMPLETED'
    const cancelled = variant('ORDER-CANCEL'); cancelled.status = 'CANCELLED'
    const unissued = variant('ORDER-UNISSUED'); unissued.awaiting_issue = true
    data.orders = [cancelled, completed, inTransit, accepted, waiting, pending, unissued]
    api.workspace.mockResolvedValue(data)
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    const rows = () => wrapper.findAll('table')[0]!.findAll('tbody tr')
    const filter = wrapper.get('select[aria-label="供应商订单状态筛选"]')
    expect(rows()[0]!.find('button[aria-label="查看订单 ORDER-PENDING 明细"]').exists()).toBe(true)
    expect(rows()[1]!.find('button[aria-label="查看订单 ORDER-WAITING 明细"]').exists()).toBe(true)
    for (const [value, id, label] of [
      ['PENDING_ACCEPTANCE', 'ORDER-PENDING', '待接单'],
      ['WAITING_SHIPMENT', 'ORDER-WAITING', '待送货'],
      ['ACCEPTED', 'ORDER-ACCEPTED', '已确认接单'],
      ['RECEIPT_PENDING', 'ORDER-TRANSIT', '送货待确定'],
      ['COMPLETED', 'ORDER-COMPLETE', '已完成'],
      ['CANCELLED', 'ORDER-CANCEL', '已取消'],
      ['PENDING_ISSUE', 'ORDER-UNISSUED', '变更待发行'],
    ]) {
      await filter.setValue(value)
      expect(rows()).toHaveLength(1)
      expect(rows()[0]!.get(`button[aria-label="查看订单 ${id} 明细"]`)).toBeDefined()
      expect(rows()[0]!.text()).toContain(label)
      if (value === 'COMPLETED' || value === 'CANCELLED') {
        expect(rows()[0]!.get(`input[aria-label="选择订单 ${id}"]`).attributes('disabled')).toBeDefined()
      }
    }
    wrapper.unmount()
  })
  it('shows all authorized factories together while filtering locally and dispatching to each target factory', async () => {
    const serviceFactories = [
      { factory_id: 'huaxing', supplier_name: '河源东康' },
      { factory_id: 'huakang-a', supplier_name: '河源东康' },
    ]
    api.memberships.mockResolvedValue(serviceFactories)
    const other = fixture()
    other.factory_id = 'huakang-a'
    other.orders[0]!.id = 'ORDER-K'
    other.orders[0]!.order_no = 'ORDER-K'
    other.orders[0]!.lines = other.orders[0]!.lines.map((line, index) => ({ ...line, id: `K-LINE-${index}`, child_no: `ORDER-K/0${index + 1}` }))
    other.shipments[0]!.id = 'SHIP-K'
    other.shipments[0]!.delivery_note_no = 'DN-K'
    api.workspace.mockImplementation(async (scope: string) => scope === 'huakang-a' ? other : fixture())
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    const factoryFilter = wrapper.get('select[aria-label="供应商订单厂区筛选"]')
    expect(factoryFilter.findAll('option').map(option => option.attributes('value'))).toEqual(['', 'huaxing', 'huakang-a'])
    expect(wrapper.text()).toContain('服务厂区：2 个 · 订单合并展示')
    expect(wrapper.get('input[aria-label="选择订单 ORDER-K"]')).toBeDefined()
    expect(wrapper.get('input[aria-label="选择订单 ORDER-A"]')).toBeDefined()
    await wrapper.get('input[aria-label="选择订单 ORDER-A"]').setValue(true)
    await wrapper.get('button[aria-label="查看订单 ORDER-A 明细"]').trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('A33 · 10*20 cm')
    expect(wrapper.find('input[aria-label="选择发货 ORDER-A/01"]').exists()).toBe(false)
    await wrapper.get('button[aria-label="关闭供应商订单明细"]').trigger('click')
    await wrapper.get('button[aria-label="登记订单 ORDER-A 发货"]').trigger('click')
    await wrapper.get('input[aria-label="选择发货 ORDER-A/02"]').setValue(false)
    await wrapper.get('input[aria-label="发货数量 ORDER-A/01"]').setValue(7)
    await wrapper.get('input[aria-label="供应商送货单号 华兴"]').setValue('DN-OLD')
    await factoryFilter.setValue('huakang-a'); await flushPromises()
    expect(api.workspace).toHaveBeenCalledWith('huaxing')
    expect(api.workspace).toHaveBeenCalledWith('huakang-a')
    expect(router.replace).not.toHaveBeenCalled()
    expect(wrapper.get('input[aria-label="供应商送货单号 华兴"]').element).toHaveProperty('value', 'DN-OLD')
    expect(wrapper.text()).toContain('已选 1 张订单 · 1 条发货纸品')
    expect(wrapper.get('input[aria-label="选择订单 ORDER-K"]')).toBeDefined()
    expect(wrapper.find('input[aria-label="选择订单 ORDER-A"]').exists()).toBe(false)
    await factoryFilter.setValue(''); await flushPromises()
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.ship).toHaveBeenCalledWith(expect.objectContaining({ factory_id: 'huaxing', delivery_note_no: 'DN-OLD', lines: [{ order_line_id: 'LINE-0', issue_id: 'ISSUE-A', quantity: 7 }] }))
    await wrapper.get('button[aria-label="登记订单 ORDER-K 发货"]').trigger('click')
    await wrapper.get('input[aria-label="选择发货 ORDER-K/02"]').setValue(false)
    await wrapper.get('input[aria-label="发货数量 ORDER-K/01"]').setValue(3)
    await wrapper.get('input[aria-label="供应商送货单号 华康A"]').setValue('DN-K-NEW')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.ship).toHaveBeenCalledWith(expect.objectContaining({ factory_id: 'huakang-a', delivery_note_no: 'DN-K-NEW', lines: [{ order_line_id: 'K-LINE-0', issue_id: 'ISSUE-A', quantity: 3 }] }))
    await wrapper.findAll('button').find(button => button.text().includes('发货与仓库反馈'))!.trigger('click')
    expect(wrapper.get('select[aria-label="供应商发货厂区筛选"]').element).toHaveProperty('value', '')
    expect(wrapper.text()).toContain('DN-K')
    expect(wrapper.text()).toContain('DN-A')
    wrapper.unmount()
  })
  it('keeps completed orders visible but excludes them from individual and bulk selection', async () => {
    const data = fixture()
    const second = structuredClone(data.orders[0]!)
    second.id = 'ORDER-B'
    second.order_no = 'ORDER-B'
    second.customer_name = 'BUZZ'
    second.contract_no = 'SC-B'
    second.item_no = 'ITEM-B'
    second.status = 'COMPLETED'
    second.lines = second.lines.map((line, index) => ({ ...line, id: `B-LINE-${index}`, child_no: `ORDER-B/0${index + 1}`, remaining_to_ship: '0' }))
    data.orders.push(second)
    api.workspace.mockResolvedValue(data)
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    const ledgerRows = () => wrapper.findAll('table')[0]!.findAll('tbody tr')

    await wrapper.get('input[aria-label="搜索供应商订单"]').setValue('SC-A')
    expect(ledgerRows()).toHaveLength(1)
    await wrapper.get('input[aria-label="全选当前筛选订单"]').setValue(true)
    await wrapper.get('input[aria-label="搜索供应商订单"]').setValue('SC-B')
    expect(ledgerRows()).toHaveLength(1)
    expect(wrapper.get('input[aria-label="选择订单 ORDER-B"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('input[aria-label="全选当前筛选订单"]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('已选 1 张订单')
    await wrapper.get('select[aria-label="供应商订单状态筛选"]').setValue('COMPLETED')
    expect(ledgerRows()).toHaveLength(1)
    await wrapper.findAll('button').find(button => button.text() === '清空筛选')!.trigger('click')
    expect(ledgerRows()).toHaveLength(2)
    await wrapper.get('input[aria-label="全选当前筛选订单"]').setValue(true)
    expect(wrapper.text()).toContain('已选 1 张订单')
    expect((wrapper.get('input[aria-label="全选当前筛选订单"]').element as HTMLInputElement).checked).toBe(true)
    await wrapper.findAll('button').find(button => button.text() === '查看已选')!.trigger('click')
    expect(ledgerRows()).toHaveLength(1)
    expect(ledgerRows()[0]!.get('button[aria-label="查看订单 ORDER-A 明细"]')).toBeDefined()
    data.orders[0]!.status = 'COMPLETED'
    await wrapper.findAll('button').find(button => button.text() === '刷新')!.trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('已选 0 张订单')
    expect(wrapper.get('input[aria-label="全选当前筛选订单"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
  it('filters by inclusive carton order dates and keeps the issued customer PO value', async () => {
    const data = fixture()
    const later = structuredClone(data.orders[0]!)
    later.id = 'ORDER-LATER'
    later.order_no = 'ORDER-LATER'
    later.order_date = '2026-09-20'
    later.customer_po = ''
    later.lines = later.lines.map((line, index) => ({ ...line, id: `LATER-${index}` }))
    data.orders.push(later)
    api.workspace.mockResolvedValue(data)
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    const rows = () => wrapper.findAll('table')[0]!.findAll('tbody tr')
    expect(rows()).toHaveLength(2)
    expect(rows()[0]!.text()).toContain('客户 PO PO-A')
    expect(rows()[1]!.text()).toContain('客户 PO 纸箱订单未填写')
    await wrapper.get('input[aria-label="下单日期开始"]').setValue('2026-09-20')
    expect(rows()).toHaveLength(1)
    expect(rows()[0]!.text()).toContain('2026-09-20')
    await wrapper.get('input[aria-label="下单日期结束"]').setValue('2026-09-20')
    expect(rows()).toHaveLength(1)
    await wrapper.findAll('button').find(button => button.text() === '清空筛选')!.trigger('click')
    expect(rows()).toHaveLength(2)
    expect(wrapper.get<HTMLInputElement>('input[aria-label="下单日期开始"]').element.value).toBe('')
    wrapper.unmount()
  })
  it('moves from the separate acceptance action to the shipment action after the last paper is accepted', async () => {
    const data = fixture()
    data.orders[0]!.lines[0]!.accepted = false
    api.workspace.mockImplementation(async () => structuredClone(data))
    api.accept.mockImplementation(async () => { data.orders[0]!.lines[0]!.accepted = true })
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(wrapper.find('button[aria-label="登记订单 ORDER-A 发货"]').exists()).toBe(false)
    await wrapper.get('button[aria-label="确认订单 ORDER-A 接单"]').trigger('click')
    await wrapper.get('input[aria-label="ORDER-A/01 承诺交期"]').setValue('2026-09-28')
    await wrapper.get('[role="dialog"]').findAll('button').find(button => button.text() === '确认接单')!.trigger('click'); await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('button[aria-label="登记订单 ORDER-A 发货"]')).toBeDefined()
    await wrapper.get('button[aria-label="登记订单 ORDER-A 发货"]').trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('登记本次发货')
    wrapper.unmount()
  })
  it('does not strand reduced zero-demand paper in the pending-acceptance stage', async () => {
    const data = fixture()
    data.orders[0]!.lines[0]!.required_quantity = '0'
    data.orders[0]!.lines[0]!.remaining_to_ship = '0'
    data.orders[0]!.lines[0]!.accepted = false
    api.workspace.mockResolvedValue(data)
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(wrapper.find('button[aria-label="确认订单 ORDER-A 接单"]').exists()).toBe(false)
    expect(wrapper.get('button[aria-label="登记订单 ORDER-A 发货"]')).toBeDefined()
    await wrapper.get('button[aria-label="查看订单 ORDER-A 明细"]').trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('需求已归零')
    await wrapper.get('button[aria-label="关闭供应商订单明细"]').trigger('click')
    await wrapper.get('button[aria-label="登记订单 ORDER-A 发货"]').trigger('click')
    expect(wrapper.find('input[aria-label="选择发货 ORDER-A/01"]').exists()).toBe(false)
    expect(wrapper.get('input[aria-label="选择发货 ORDER-A/02"]')).toBeDefined()
    wrapper.unmount()
  })
  it('closes acceptance when the last positive-demand paper is confirmed beside a zero-demand row', async () => {
    const data = fixture()
    data.orders[0]!.lines[0]!.required_quantity = '0'
    data.orders[0]!.lines[0]!.remaining_to_ship = '0'
    data.orders[0]!.lines[0]!.accepted = false
    data.orders[0]!.lines[1]!.accepted = false
    api.workspace.mockImplementation(async () => structuredClone(data))
    api.accept.mockImplementation(async () => { data.orders[0]!.lines[1]!.accepted = true })
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.get('button[aria-label="确认订单 ORDER-A 接单"]').trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('需求已归零 · 无需接单')
    expect(wrapper.get('[role="dialog"]').findAll('button').filter(button => button.text() === '确认接单')).toHaveLength(1)
    await wrapper.get('[role="dialog"]').findAll('button').find(button => button.text() === '确认接单')!.trigger('click'); await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('button[aria-label="登记订单 ORDER-A 发货"]')).toBeDefined()
    wrapper.unmount()
  })
  it('keeps shipment feedback searchable on its own tab', async () => {
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text().includes('发货与仓库反馈'))!.trigger('click')
    expect(wrapper.text()).toContain('DN-A')
    await wrapper.get('input[aria-label="搜索供应商发货单"]').setValue('UNMATCHED')
    expect(wrapper.text()).toContain('暂无符合条件的发货单')
    expect(wrapper.text()).not.toContain('DN-A')
    wrapper.unmount()
  })
  it('shows an unbound account message without requesting an arbitrary factory workspace', async () => {
    api.memberships.mockResolvedValue([])
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('暂无可查看的已下单厂区')
    expect(api.workspace).not.toHaveBeenCalled(); wrapper.unmount()
  })
  it('submits separately selected paper identities and actual shipment quantities', async () => {
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.get('button[aria-label="登记订单 ORDER-A 发货"]').trigger('click')
    await wrapper.get('input[aria-label="发货数量 ORDER-A/01"]').setValue(4)
    await wrapper.get('input[aria-label="发货数量 ORDER-A/02"]').setValue(8)
    await wrapper.get('input[aria-label="供应商送货单号 华兴"]').setValue('DN-NEW')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(api.ship).toHaveBeenCalledWith(expect.objectContaining({ factory_id: 'huaxing', delivery_note_no: 'DN-NEW', lines: [{ order_line_id: 'LINE-0', issue_id: 'ISSUE-A', quantity: 4 }, { order_line_id: 'LINE-1', issue_id: 'ISSUE-A', quantity: 8 }] }))
    expect(wrapper.find('input[aria-label="供应商送货单号 华兴"]').exists()).toBe(false)
    expect(wrapper.get('[role="status"]').text()).toContain('尚未计入库存'); wrapper.unmount()
  })
  it('blocks stale unissued commitments and retains values on a shipment error', async () => {
    const data = fixture(); data.orders[0]!.awaiting_issue = true
    api.workspace.mockResolvedValue(data)
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.get('button[aria-label="查看订单 ORDER-A 明细"]').trigger('click')
    expect(wrapper.text()).toContain('旧承诺暂停执行')
    expect(wrapper.find('button[aria-label="登记订单 ORDER-A 发货"]').exists()).toBe(false)
    await wrapper.get('button[aria-label="关闭供应商订单明细"]').trigger('click')
    data.orders[0]!.awaiting_issue = false; api.workspace.mockResolvedValue(structuredClone(data))
    await wrapper.findAll('button').find(button => button.text() === '刷新')!.trigger('click'); await flushPromises()
    api.ship.mockRejectedValue(new Error('当前剩余未送不足'))
    await wrapper.get('button[aria-label="登记订单 ORDER-A 发货"]').trigger('click')
    await wrapper.get('input[aria-label="选择发货 ORDER-A/02"]').setValue(false)
    await wrapper.get('input[aria-label="发货数量 ORDER-A/01"]').setValue(7)
    await wrapper.get('input[aria-label="供应商送货单号 华兴"]').setValue('DN-RETRY')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('当前剩余未送不足')
    expect(wrapper.get('[role="dialog"]').text()).toContain('当前剩余未送不足')
    expect(wrapper.get<HTMLInputElement>('input[aria-label="发货数量 ORDER-A/01"]').element.value).toBe('7'); wrapper.unmount()
  })
  it('requires a commitment before dispatch and sends the issued version and expected revision', async () => {
    const data = fixture(); data.orders[0]!.lines[0]!.accepted = false
    api.workspace.mockResolvedValue(data)
    const wrapper = mount(CartonSupplierView, options); await flushPromises()
    await wrapper.get('button[aria-label="查看订单 ORDER-A 明细"]').trigger('click')
    expect(wrapper.find('input[aria-label="选择发货 ORDER-A/01"]').exists()).toBe(false)
    await wrapper.get('button[aria-label="关闭供应商订单明细"]').trigger('click')
    expect(wrapper.find('button[aria-label="登记订单 ORDER-A 发货"]').exists()).toBe(false)
    await wrapper.get('button[aria-label="确认订单 ORDER-A 接单"]').trigger('click')
    await wrapper.get('input[aria-label="ORDER-A/01 承诺交期"]').setValue('2026-09-28')
    await wrapper.get('[role="dialog"]').findAll('button').find(button => button.text() === '确认接单')!.trigger('click'); await flushPromises()
    expect(api.accept).toHaveBeenCalledWith(expect.objectContaining({ id: 'LINE-0', commitment_revision: 1 }), expect.objectContaining({ issue_id: 'ISSUE-A' }), 'huaxing', '2026-09-28'); wrapper.unmount()
  })
})
describe('internal supplier collaboration', () => {
  it('hides privileged member and attachment controls for a receipt-only warehouse operator', async () => {
    can.mockImplementation(permission => ['carton_procurement:read', 'carton_procurement:receipt_write', 'carton_procurement:inventory_write'].includes(permission))
    const wrapper = mount(CartonSupplierManagementView, options); await flushPromises()
    expect(wrapper.text()).not.toContain('供应商外部账号授权')
    expect(wrapper.find('input[type="file"]').exists()).toBe(false)
    expect(api.members).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('核实实际收到'); wrapper.unmount()
  })
  it('allows explicit all-zero non-arrival with reasons and closes a successful confirmation before refresh', async () => {
    const wrapper = mount(CartonSupplierManagementView, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '核实实际收到')!.trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('确认整单未收到并退回')
    for (const input of wrapper.findAll('input[aria-label$="差异原因"]')) await input.setValue('货物尚未实际送到')
    api.workspace.mockRejectedValueOnce(new Error('台账刷新失败'))
    await wrapper.get('[role="dialog"]').trigger('submit'); await flushPromises()
    expect(api.receive).toHaveBeenCalledWith('SHIP-A', expect.objectContaining({ expected_revision: 1, lines: [expect.objectContaining({ shipment_line_id: 'SL-0', received_quantity: 0, difference_reason: '货物尚未实际送到' }), expect.objectContaining({ shipment_line_id: 'SL-1', received_quantity: 0 })] }))
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('[role="status"]').text()).toContain('仓库核实已保存'); wrapper.unmount()
  })
  it('retains partial quantities and differences on atomic receipt failure', async () => {
    api.receive.mockRejectedValue(new Error('单价或仓位无效，本次未入库'))
    const wrapper = mount(CartonSupplierManagementView, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '核实实际收到')!.trigger('click')
    await wrapper.get('input[aria-label="SL-0 实收"]').setValue(6)
    await wrapper.get('input[aria-label="SL-0 差异原因"]').setValue('短收四件待核实')
    wrapper.findAllComponents(CartonReceiptAllocations)[0]!.vm.$emit('update:modelValue', [{ location_id: 'BIN-A', quantity: 6 }])
    await wrapper.get('[role="dialog"]').trigger('submit'); await flushPromises()
    expect(wrapper.get<HTMLInputElement>('input[aria-label="SL-0 实收"]').element.value).toBe('6')
    expect(wrapper.get('[role="dialog"]').text()).toContain('本次未入库'); wrapper.unmount()
  })
  it('requires complete valid allocations for positive effective receipts before sending', async () => {
    const wrapper = mount(CartonSupplierManagementView, options); await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '核实实际收到')!.trigger('click')
    await wrapper.get('input[aria-label="SL-0 实收"]').setValue(6)
    for (const input of wrapper.findAll('input[aria-label$="差异原因"]')) await input.setValue('本次到货差异待核实')
    await wrapper.get('[role="dialog"]').trigger('submit'); await flushPromises()
    expect(api.receive).not.toHaveBeenCalled()
    expect(wrapper.get('[role="dialog"]').text()).toContain('必须选择有效仓位')
    const allocations = wrapper.findAllComponents(CartonReceiptAllocations)[0]!
    allocations.vm.$emit('update:modelValue', [{ location_id: 'BIN-A', quantity: 5 }])
    await wrapper.get('[role="dialog"]').trigger('submit'); await flushPromises()
    expect(api.receive).not.toHaveBeenCalled()
    expect(wrapper.get('[role="dialog"]').text()).toContain('合计必须等于')
    allocations.vm.$emit('update:modelValue', [{ location_id: 'unknown-bin', quantity: 6 }])
    await wrapper.get('[role="dialog"]').trigger('submit'); await flushPromises()
    expect(api.receive).not.toHaveBeenCalled()
    allocations.vm.$emit('update:modelValue', [{ location_id: 'BIN-A', quantity: 6 }])
    await wrapper.get('[role="dialog"]').trigger('submit'); await flushPromises()
    expect(api.receive).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false); wrapper.unmount()
  })
})
