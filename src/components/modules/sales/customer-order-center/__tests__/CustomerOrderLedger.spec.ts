import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import CustomerOrderLedger from '../CustomerOrderLedger.vue'
import CustomerOrderHistoryImport from '../CustomerOrderHistoryImport.vue'

const api = vi.hoisted(() => ({
  capabilities: vi.fn(), list: vi.fn(), detail: vi.fn(), amend: vi.fn(), cancel: vi.fn(), dispatch: vi.fn(), confirmShipment: vi.fn(), reverseShipment: vi.fn(),
}))
const historyApi = vi.hoisted(() => ({ customers: vi.fn(), preview: vi.fn(), confirm: vi.fn(), correctOpening: vi.fn() }))
vi.mock('@/api/customerOrderLedger', () => ({ customerOrderLedgerApi: api, customerOrderLedgerSourceUrl: vi.fn(() => '/api/customer-order-ledger/sources/source-1?factory_id=huaxing') }))
vi.mock('@/api/customerOrderHistory', () => ({ customerOrderHistoryApi: historyApi }))

const line = {
  id: 'line-1', factory_id: 'huaxing', customer_code: 'buzzbee', customer_name: 'BuzzBee', reference_no: '0009382481', product_no: '00123', quantity: '0100', shipped_quantity: '0020', remaining_quantity: '0080', status: 'active' as const, version: 2, revision: 4, dispatch_status: 'unsent' as const, data: { requested_ship_date: '2026-10-01' }, created_at: '', updated_at: '',
}

function mountLedger() {
  api.capabilities.mockResolvedValue({ read: true, write: true, dispatch: true, shipment_confirm: true, inbox_read: false, inbox_receive: false })
  api.list.mockResolvedValue({ items: [line], total: 1, page: 1, page_size: 50, customers: [{ code: 'buzzbee', name: 'BuzzBee' }] })
  api.detail.mockResolvedValue({ line, versions: [], dispatches: [], shipments: [], sources: [] })
  return mount(CustomerOrderLedger, { props: { factoryId: 'huaxing', factoryName: '华兴厂' } })
}

describe('CustomerOrderLedger', () => {
  it('opens only the focused order and notifies its schedule after saving', async () => {
    const wrapper = mountLedger()
    await flushPromises()
    api.list.mockClear()
    await wrapper.setProps({ detailOnly: true, focusLineId: 'line-1' })
    await flushPromises()
    expect(api.list).not.toHaveBeenCalled()
    expect(api.detail).toHaveBeenLastCalledWith('line-1', 'huaxing')
    let finishShipment: (() => void) | undefined
    api.confirmShipment.mockImplementationOnce(() => new Promise<void>((resolve) => { finishShipment = resolve }))
    await wrapper.findAll('.ledger__form input')[4]!.setValue('DN-FOCUSED-1')
    await wrapper.findAll('button').find((button) => button.text() === '确认走货')!.trigger('click')
    expect(wrapper.get<HTMLButtonElement>('[aria-label="关闭详情"]').element.disabled).toBe(true)
    finishShipment?.()
    await flushPromises()
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(api.list).not.toHaveBeenCalled()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('keeps a closed focused detail closed while permissions are still loading', async () => {
    let resolveCapabilities: ((value: Record<string, boolean>) => void) | undefined
    api.capabilities.mockImplementationOnce(() => new Promise((resolve) => { resolveCapabilities = resolve }))
    api.detail.mockClear()
    const wrapper = mount(CustomerOrderLedger, { props: { factoryId: 'huaxing', factoryName: '华兴厂', detailOnly: true, focusLineId: 'line-1' } })
    await wrapper.get('[aria-label="关闭详情"]').trigger('click')
    resolveCapabilities?.({ read: true })
    await flushPromises()
    expect(api.detail).not.toHaveBeenCalled()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.emitted('close-detail')).toHaveLength(1)
    wrapper.unmount()
  })

  it('rejects a detail that does not match the selected order', async () => {
    api.capabilities.mockResolvedValue({ read: true })
    api.detail.mockResolvedValue({ line: { ...line, id: 'wrong-line' }, versions: [], dispatches: [], shipments: [], sources: [] })
    const wrapper = mount(CustomerOrderLedger, { props: { factoryId: 'huaxing', factoryName: '华兴厂', detailOnly: true, focusLineId: 'line-1' } })
    await flushPromises()
    expect(wrapper.text()).toContain('返回的订单与当前选择不一致')
    expect(wrapper.text()).not.toContain('0009382481')
    wrapper.unmount()
  })

  it('loads only the active factory and opens persisted line detail', async () => {
    const wrapper = mountLedger()
    await flushPromises()
    expect(api.list).toHaveBeenCalledWith('huaxing', expect.objectContaining({ view: 'all' }))
    expect(wrapper.text()).toContain('0009382481')
    expect(wrapper.text()).toContain('00123')
    await wrapper.get('button.ledger__link').trigger('click')
    await flushPromises()
    expect(api.detail).toHaveBeenCalledWith('line-1', 'huaxing')
    expect(wrapper.text()).toContain('修订 4')
  })

  it('keeps PO identifiers as strings when confirming shipment', async () => {
    const wrapper = mountLedger()
    await flushPromises()
    await wrapper.get('button.ledger__link').trigger('click')
    await flushPromises()
    api.confirmShipment.mockResolvedValue(line)
    const inputs = wrapper.findAll('.ledger__form input')
    await inputs[2]!.setValue('0007')
    await inputs[3]!.setValue('2026-10-02')
    await inputs[4]!.setValue('DN-0009')
    const shipmentButton = wrapper.findAll('button').find((button) => button.text() === '确认走货')
    await shipmentButton!.trigger('click')
    await flushPromises()
    expect(api.confirmShipment).toHaveBeenCalledWith('line-1', 'huaxing', expect.objectContaining({ quantity: '0007', document_no: 'DN-0009', expected_revision: 4, idempotency_key: expect.any(String) }))
  })

  it('shows customer fields, source lineage, versions and recipients in business language', async () => {
    const detailedLine = {
      ...line,
      data: {
        requested_ship_date: '2026-10-01', packaging: '彩盒', carton_mark: '外箱唛头', barcode: '6900000000012',
        source_kind: 'formal', import_controls: { preview_fingerprint: 'hidden' }, issues: [{ code: 'hidden' }],
        lineage: { carton_mark: '客户 PO 第 2 页', barcode: '客户条码资料' },
        history_migration: { cutoff_date: '2026-09-30', opening_shipped_quantity: '0020', sheet: 'ITEM表', row: 8, section: 'shipped', reason: '历史排期迁入', actor: '业务员', confirmed_at: '2026-10-01' },
        history_fields: [{ column: 'AZ', header: '客户自定义包装说明', value: '请使用蓝色内托' }], history_review: { sheet: '正单评审表', row: 18 },
      },
    }
    const wrapper = mountLedger()
    api.detail.mockResolvedValue({
      line: detailedLine,
      versions: [{ version: 1, data: { quantity: '0100', requested_ship_date: '2026-10-01', carton_mark: '旧箱唛', lineage: { carton_mark: '初始 PO' } }, reason: '初始确认', actor: '业务员', created_at: '2026-09-14' }],
      dispatches: [{ id: 'dispatch-1', recipient: 'pmc', version: 1, status: 'received', created_at: '2026-09-14', received_at: '2026-09-15', received_by: '王工' }],
      shipments: [], sources: [{ id: 'source-1', file_name: '正式订单.pdf', kind: 'formal' }],
    })
    await flushPromises()
    await wrapper.get('button.ledger__link').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('包装')
    expect(wrapper.text()).toContain('彩盒')
    expect(wrapper.text()).toContain('箱唛')
    expect(wrapper.text()).toContain('条码')
    expect(wrapper.text()).toContain('正式 PO')
    expect(wrapper.text()).toContain('字段来源说明')
    expect(wrapper.text()).toContain('PMC')
    expect(wrapper.text()).toContain('历史排期迁入期初')
    expect(wrapper.text()).toContain('期初已走货数量')
    expect(wrapper.text()).toContain('0020')
    expect(wrapper.text()).toContain('历史排期原始字段')
    const originalFields = wrapper.findAll('details').find((details) => details.text().includes('展开原排期字段'))!
    await originalFields.trigger('toggle')
    expect(originalFields.text()).toContain('客户自定义包装说明（AZ列）')
    expect(originalFields.text()).toContain('请使用蓝色内托')
    expect(originalFields.text()).toContain('ITEM表 · 第 8 行')
    expect(originalFields.text()).not.toContain('正单评审表')
    expect(wrapper.text()).toContain('V1 · 初始确认')
    expect(wrapper.text()).not.toContain('[object Object]')
    expect(wrapper.text()).not.toContain('import_controls')
  })

  it('paginates persisted lines and closes a stale detail before requesting the next page', async () => {
    api.capabilities.mockResolvedValue({ read: true, write: true, dispatch: true, shipment_confirm: true, inbox_read: false, inbox_receive: false })
    api.list
      .mockResolvedValueOnce({ items: [line], total: 51, page: 1, page_size: 50, customers: [] })
      .mockResolvedValueOnce({ items: [], total: 51, page: 2, page_size: 50, customers: [] })
    api.detail.mockResolvedValue({ line, versions: [], dispatches: [], shipments: [], sources: [] })
    const wrapper = mount(CustomerOrderLedger, { props: { factoryId: 'huaxing', factoryName: '华兴厂' } })
    await flushPromises()
    await wrapper.get('button.ledger__link').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    await wrapper.get('.ledger__pagination button:last-child').trigger('click')
    await flushPromises()
    expect(api.list).toHaveBeenLastCalledWith('huaxing', expect.objectContaining({ page: 2 }))
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })

  it('clears an in-flight old-factory detail when the active factory changes', async () => {
    api.capabilities.mockResolvedValue({ read: true, write: true, dispatch: true, shipment_confirm: true, inbox_read: false, inbox_receive: false })
    api.list.mockResolvedValue({ items: [line], total: 1, page: 1, page_size: 50, customers: [] })
    let resolveDetail: ((value: { line: typeof line; versions: never[]; dispatches: never[]; shipments: never[]; sources: never[] }) => void) | undefined
    api.detail.mockImplementationOnce(() => new Promise((resolve) => { resolveDetail = resolve }))
    const wrapper = mount(CustomerOrderLedger, { props: { factoryId: 'huaxing', factoryName: '华兴厂' } })
    await flushPromises()
    await wrapper.get('button.ledger__link').trigger('click')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    await wrapper.setProps({ factoryId: 'huakang-a', factoryName: '华康A厂' })
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    resolveDetail?.({ line, versions: [], dispatches: [], shipments: [], sources: [] })
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(api.list).toHaveBeenLastCalledWith('huakang-a', expect.any(Object))
  })

  it('opens the independent history migration flow and refreshes the ledger after it saves', async () => {
    const wrapper = mountLedger()
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === '历史排期迁入')!.trigger('click')
    const historyImport = wrapper.findComponent(CustomerOrderHistoryImport)
    expect(historyImport.exists()).toBe(true)
    api.list.mockClear()
    historyImport.vm.$emit('saved')
    await flushPromises()
    expect(api.list).toHaveBeenCalledWith('huaxing', expect.objectContaining({ page: 1 }))
    expect(wrapper.findComponent(CustomerOrderHistoryImport).exists()).toBe(false)
  })

  it('corrects a historical opening with the current revision, then refreshes persisted detail and list', async () => {
    const wrapper = mountLedger()
    await flushPromises()
    const historicalLine = {
      ...line,
      data: { ...line.data, history_migration: { cutoff_date: '2026-09-30', opening_shipped_quantity: '0020', sheet: '已走货', row: 8, section: 'shipped', reason: '历史排期迁入', actor: '业务员', confirmed_at: '2026-10-01' } },
    }
    api.detail.mockResolvedValue({ line: historicalLine, versions: [], dispatches: [], shipments: [], sources: [] })
    await wrapper.get('button.ledger__link').trigger('click')
    await flushPromises()
    const correction = wrapper.get('.ledger__history-correction')
    await correction.get('input').setValue('0015')
    await correction.get('textarea').setValue('核对原排期')
    historyApi.correctOpening.mockResolvedValue(historicalLine)
    await correction.get('button').trigger('click')
    await flushPromises()
    expect(historyApi.correctOpening).toHaveBeenCalledWith('line-1', 'huaxing', {
      expected_revision: 4, opening_shipped_quantity: '0015', reason: '核对原排期',
    })
    expect(api.list).toHaveBeenLastCalledWith('huaxing', expect.objectContaining({ page: 1 }))
    expect(api.detail).toHaveBeenLastCalledWith('line-1', 'huaxing')
  })

  it('ignores an in-flight historical-opening correction after the active factory changes', async () => {
    const wrapper = mountLedger()
    await flushPromises()
    const historicalLine = {
      ...line,
      data: { ...line.data, history_migration: { cutoff_date: '2026-09-30', opening_shipped_quantity: '0020', sheet: '已走货', row: 8, section: 'shipped', reason: '历史排期迁入', actor: '业务员', confirmed_at: '2026-10-01' } },
    }
    api.detail.mockResolvedValue({ line: historicalLine, versions: [], dispatches: [], shipments: [], sources: [] })
    await wrapper.get('button.ledger__link').trigger('click')
    await flushPromises()
    const correction = wrapper.get('.ledger__history-correction')
    await correction.get('input').setValue('0015')
    await correction.get('textarea').setValue('核对原排期')
    let resolveCorrection: ((value: typeof historicalLine) => void) | undefined
    historyApi.correctOpening.mockImplementationOnce(() => new Promise((resolve) => { resolveCorrection = resolve }))
    await correction.get('button').trigger('click')
    await wrapper.setProps({ factoryId: 'huakang-a', factoryName: '华康A厂' })
    resolveCorrection?.(historicalLine)
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(api.list).toHaveBeenLastCalledWith('huakang-a', expect.any(Object))
  })
})
