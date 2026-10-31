import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CustomerOrderSchedule from '../CustomerOrderSchedule.vue'

vi.mock('@/components/CartonMaterialsSourceButton.vue', () => ({ default: { template: '<span>订单资料</span>' } }))

const api = vi.hoisted(() => ({ customers: vi.fn(), get: vi.fn(), organize360: vi.fn() }))
enableAutoUnmount(afterEach)
beforeEach(() => { vi.resetAllMocks() })
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals() })
vi.mock('@/api/customerOrderSchedule', () => ({ customerOrderScheduleApi: api }))
vi.mock('../CustomerOrderLedger.vue', () => ({
  default: {
    name: 'CustomerOrderLedger',
    props: ['factoryId', 'factoryName', 'detailOnly', 'focusLineId'],
    emits: ['changed', 'close-detail'],
    template: '<aside data-testid="ledger-detail"><button type="button" @click="$emit(\'changed\')">保存详情</button><button type="button" @click="$emit(\'close-detail\')">关闭详情</button></aside>',
  },
}))

const line = {
  id: 'line-1', factory_id: 'huaxing', customer_code: 'buzzbee', customer_name: 'BuzzBee', reference_no: 'REF-001', product_no: 'P-001', quantity: '100', shipped_quantity: '20', remaining_quantity: '80', status: 'active' as const, version: 2, revision: 1, dispatch_status: 'sent' as const,
  data: { contract_no: 'CT-9', po_no: 'PO-0007', product_name_zh: '小熊', product_name_en: 'Bear', requested_ship_date: '2026-10-10', packaging: '彩盒', label: true }, created_at: '', updated_at: '',
}

function result(overrides: Record<string, unknown> = {}) {
  return {
    factory_id: 'huaxing', customer_code: 'buzzbee', customer_name: 'BuzzBee',
    columns: [{ key: 'packaging', label: '包装' }, { key: 'label', label: '标签' }, { key: 'note', label: '备注' }, { key: 'carton_mark', label: '箱唛' }, { key: 'extra', label: '客户字段' }],
    summary: { order_count: 2, ordered_quantity: '200', shipped_quantity: '120', remaining_quantity: '80', unknown_quantity_count: 1, cancelled_count: 1 },
    sections: {
      unshipped: { items: [line], total: 51, page: 1, page_size: 50 },
      shipped: { items: [{ ...line, id: 'line-2', remaining_quantity: '0' }], total: 1, page: 1, page_size: 50 },
      cancelled: { items: [{ ...line, id: 'line-3', status: 'cancelled' as const, remaining_quantity: '99' }], total: 1, page: 1, page_size: 50 },
    },
    ...overrides,
  }
}

function mountSchedule() {
  api.customers.mockResolvedValue({ factory_id: 'huaxing', items: [{ code: 'buzzbee', name: 'BuzzBee' }] })
  api.get.mockResolvedValue(result())
  return mount(CustomerOrderSchedule, { props: { factoryId: 'huaxing', factoryName: '华兴厂' } })
}

async function chooseAndApply(wrapper: ReturnType<typeof mount>) {
  await flushPromises()
  await wrapper.get('select').setValue('buzzbee')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
}

function inspectionResult(asOfDate = '2026-10-16') {
  const scopedLine = { ...line, factory_id: 'huakang-a', customer_code: '360', customer_name: '360' }
  const pending = { ...scopedLine, id: 'pending', reference_no: 'PENDING-360', schedule_inspection_date: '', inspection_date_warning: '验货日期字段冲突' }
  const completed = { ...scopedLine, id: 'completed', reference_no: 'COMPLETED-360', schedule_inspection_date: '2026-10-15' }
  const section = (items: Array<typeof scopedLine>, total = items.length) => ({ items, total, page: 1, page_size: 50 })
  return {
    ...result(), factory_id: 'huakang-a', customer_code: '360', customer_name: '360', columns: [],
    inspection_grouping: { as_of_date: asOfDate, timezone: 'Asia/Shanghai' },
    sections: { unshipped: section([pending, completed]), inspection_pending: section([pending], 51), completed: section([completed], 51), shipped: section([completed]), cancelled: section([]) },
  }
}

async function mount360() {
  api.customers.mockResolvedValue({ factory_id: 'huakang-a', items: [{ code: '360', name: '360' }, { code: 'green-toys', name: 'Green Toys' }] })
  api.get.mockResolvedValue(inspectionResult())
  const wrapper = mount(CustomerOrderSchedule, { props: { factoryId: 'huakang-a', factoryName: '华康 A 厂' } })
  await flushPromises()
  await wrapper.get('select').setValue('360')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  return wrapper
}

async function chooseWorkbook(wrapper: ReturnType<typeof mount>, file = new File(['workbook'], '360.xlsx')) {
  const input = wrapper.get('input[type="file"]')
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  await input.trigger('change')
  return file
}

describe('CustomerOrderSchedule', () => {
  it('requires a customer, shows persisted section totals, mapped fields and cancellation rules', async () => {
    const wrapper = mountSchedule()
    await flushPromises()
    await wrapper.get('form').trigger('submit')
    expect(api.get).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('请先选择客户')

    await chooseAndApply(wrapper)
    expect(api.get).toHaveBeenCalledWith('huaxing', expect.objectContaining({ customerCode: 'buzzbee', unshippedPage: 1, shippedPage: 1, cancelledPage: 1, pageSize: 50 }))
    expect(wrapper.text()).toContain('订单数')
    expect(wrapper.text()).toContain('数量汇总按订单只计算一次')
    expect(wrapper.text()).toContain('有 1 条订单数量无法汇总')
    expect(wrapper.text()).toContain('REF-001')
    expect(wrapper.text()).toContain('PO-0007')
    expect(wrapper.text()).toContain('部分走货的订单仍会在这里显示剩余数量')
    expect(wrapper.text()).toContain('已取消订单的未走货数量为 0')
    expect(wrapper.text()).toContain('包装')
    expect(wrapper.findAll('th').map((header) => header.text())).not.toContain('客户字段')
  })

  it('keeps applied filters while paging each section independently', async () => {
    const wrapper = mountSchedule()
    await chooseAndApply(wrapper)
    await wrapper.get('input[type="search"]').setValue('draft-only')
    api.get.mockResolvedValue(result({ sections: { ...result().sections, unshipped: { items: [], total: 51, page: 2, page_size: 50 } } }))
    const sections = wrapper.findAll('.customer-schedule__section')
    await sections[0]!.findAll('button').find((button) => button.text() === '下一页')!.trigger('click')
    await flushPromises()
    expect(api.get).toHaveBeenLastCalledWith('huaxing', expect.objectContaining({ q: '', unshippedPage: 2, shippedPage: 1, cancelledPage: 1 }))
  })

  it('does not apply an old response and clears rows if the returned scope is wrong', async () => {
    let resolveFirst: ((value: ReturnType<typeof result>) => void) | undefined
    api.get.mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve }))
    const wrapper = mountSchedule()
    await flushPromises()
    await wrapper.get('select').setValue('buzzbee')
    await wrapper.get('form').trigger('submit')
    await wrapper.get('input[type="search"]').setValue('new')
    api.get.mockResolvedValueOnce(result({ customer_code: 'other' }))
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('返回数据与当前厂区或客户不一致')
    expect(wrapper.text()).not.toContain('REF-001')
    resolveFirst?.(result())
    await flushPromises()
    expect(wrapper.text()).not.toContain('REF-001')
  })

  it('refreshes all schedule sections after a saved detail and closes its detail view', async () => {
    const wrapper = mountSchedule()
    await chooseAndApply(wrapper)
    await wrapper.findAll('.customer-schedule__link')[0]!.trigger('click')
    expect(wrapper.get('[data-testid="ledger-detail"]').exists()).toBe(true)
    await wrapper.get('[data-testid="ledger-detail"] button').trigger('click')
    await flushPromises()
    expect(api.get).toHaveBeenLastCalledWith('huaxing', expect.objectContaining({ unshippedPage: 1, shippedPage: 1, cancelledPage: 1 }))
    await wrapper.get('[data-testid="ledger-detail"] button:last-child').trigger('click')
    expect(wrapper.find('[data-testid="ledger-detail"]').exists()).toBe(false)
  })

  it('rejects a cross-customer row even when the response envelope matches', async () => {
    const wrapper = mountSchedule()
    api.get.mockResolvedValueOnce(result({ sections: { ...result().sections, shipped: { items: [{ ...line, customer_code: 'disney' }], total: 1, page: 1, page_size: 50 } } }))
    await chooseAndApply(wrapper)
    expect(wrapper.text()).toContain('返回数据与当前厂区或客户不一致')
    expect(wrapper.text()).not.toContain('REF-001')
  })

  it('uses the returned page after a page is clamped by the server', async () => {
    const wrapper = mountSchedule()
    await chooseAndApply(wrapper)
    api.get.mockResolvedValueOnce(result({ sections: { ...result().sections, unshipped: { items: [line], total: 1, page: 1, page_size: 50 } } }))
    await wrapper.findAll('.customer-schedule__section')[0]!.findAll('button').find((button) => button.text() === '下一页')!.trigger('click')
    await flushPromises()
    await wrapper.findAll('.customer-schedule__link')[0]!.trigger('click')
    await wrapper.get('[data-testid="ledger-detail"] button').trigger('click')
    await flushPromises()
    expect(api.get).toHaveBeenLastCalledWith('huaxing', expect.objectContaining({ unshippedPage: 1 }))
  })

  it('shows inspection groups and their warnings while retaining independent shipment quantities', async () => {
    const wrapper = await mount360()
    expect(wrapper.findAll('.customer-schedule__section h3').map((heading) => heading.text())).toEqual([
      '未完成（按验货日期） 51 条', '已完成（按验货日期） 51 条', '已走货订单 1 条',
    ])
    expect(wrapper.get('[data-testid="inspection-rule"]').text()).toContain('上海日期 2026-10-16')
    expect(wrapper.text()).toContain('今天、未来或无有效日期归入未完成')
    expect(wrapper.get('[data-section="inspection_pending"]').text()).toContain('待核对：验货日期字段冲突')
    const completed = wrapper.get('[data-section="completed"]')
    expect(completed.text()).toContain('2026-10-15')
    expect(completed.findAll('tbody tr')[0]!.findAll('td').map((cell) => cell.text()).slice(6, 11)).toEqual(['100', '2026-10-10', '2026-10-15', '20', '80'])
    expect(wrapper.get('[data-section="shipped"]').text()).toContain('COMPLETED-360')
    expect(wrapper.get('.customer-schedule__organize').text()).toContain('选择 360 统一排期（ITEM表、接单表、正单评审表）')
    expect(api.organize360).not.toHaveBeenCalled()
  })

  it('keeps the two inspection pages independent and applies server-clamped pages', async () => {
    const wrapper = await mount360()
    const response = inspectionResult()
    response.sections.inspection_pending.page = 2
    api.get.mockResolvedValueOnce(response)
    await wrapper.get('[data-section="inspection_pending"]').findAll('button').find((button) => button.text() === '下一页')!.trigger('click')
    await flushPromises()
    expect(api.get).toHaveBeenLastCalledWith('huakang-a', expect.objectContaining({ inspectionPendingPage: 2, completedPage: 1, shippedPage: 1 }))
    api.get.mockResolvedValueOnce({ ...response, sections: { ...response.sections, completed: { ...response.sections.completed, total: 1, page: 1 } } })
    await wrapper.get('[data-section="completed"]').findAll('button').find((button) => button.text() === '下一页')!.trigger('click')
    await flushPromises()
    expect(api.get).toHaveBeenLastCalledWith('huakang-a', expect.objectContaining({ inspectionPendingPage: 2, completedPage: 2 }))
    await wrapper.get('[data-section="completed"] .customer-schedule__link').trigger('click')
    await wrapper.get('[data-testid="ledger-detail"] button').trigger('click')
    await flushPromises()
    expect(api.get).toHaveBeenLastCalledWith('huakang-a', expect.objectContaining({ inspectionPendingPage: 2, completedPage: 1 }))
  })

  it('rejects mismatched rows in the added inspection section', async () => {
    const wrapper = await mount360()
    const response = inspectionResult()
    response.sections.completed.items[0]!.factory_id = 'huaxing'
    api.get.mockResolvedValueOnce(response)
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('返回数据与当前厂区或客户不一致')
    expect(wrapper.find('[data-section="completed"]').exists()).toBe(false)
  })

  it('refreshes on a visible Shanghai day change and when returning from a hidden page', async () => {
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] })
    vi.setSystemTime(new Date('2026-10-16T15:59:45Z'))
    const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
    const wrapper = await mount360()
    expect(api.get).toHaveBeenCalledTimes(1)
    api.get.mockResolvedValue(inspectionResult('2026-10-17'))
    await vi.advanceTimersByTimeAsync(30_000)
    await flushPromises()
    expect(api.get).toHaveBeenCalledTimes(2)
    expect(wrapper.get('[data-testid="inspection-rule"]').text()).toContain('2026-10-17')
    visibility.mockReturnValue('hidden')
    vi.setSystemTime(new Date('2026-10-17T16:00:00Z'))
    await vi.advanceTimersByTimeAsync(30_000)
    expect(api.get).toHaveBeenCalledTimes(2)
    visibility.mockReturnValue('visible')
    api.get.mockResolvedValue(inspectionResult('2026-10-18'))
    window.dispatchEvent(new Event('focus'))
    await flushPromises()
    expect(api.get).toHaveBeenCalledTimes(3)
    expect(wrapper.get('[data-testid="inspection-rule"]').text()).toContain('2026-10-18')
    wrapper.unmount()
    await vi.advanceTimersByTimeAsync(30_000)
    window.dispatchEvent(new Event('focus'))
    expect(api.get).toHaveBeenCalledTimes(3)
  })

  it('ignores a delayed cross-day refresh after the customer changes', async () => {
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] })
    vi.setSystemTime(new Date('2026-10-17T00:00:00Z'))
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
    const wrapper = await mount360()
    let finish: ((value: ReturnType<typeof inspectionResult>) => void) | undefined
    api.get.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    document.dispatchEvent(new Event('visibilitychange'))
    await flushPromises()
    await wrapper.get('select').setValue('green-toys')
    finish?.(inspectionResult('2026-10-17'))
    await flushPromises()
    expect(wrapper.find('[data-testid="inspection-rule"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('COMPLETED-360')
    expect(wrapper.find('input[type="file"]').exists()).toBe(false)
  })

  it('downloads an explicitly selected workbook and clears it when the customer changes', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    const wrapper = await mount360()
    const file = await chooseWorkbook(wrapper)
    expect(api.organize360).not.toHaveBeenCalled()
    const createObjectURL = vi.fn().mockReturnValue('blob:360')
    vi.stubGlobal('URL', class extends URL { static createObjectURL = createObjectURL; static revokeObjectURL = vi.fn() })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    api.organize360.mockResolvedValue({ blob: new Blob(['excel']), fileName: '整理后的360.xlsx', report: {
      as_of_date: '2026-10-16', warning_count: 5, warnings: ['ITEM表第 8 行日期缺失', '接单表第 9 行日期冲突', '正单评审表第 10 行日期无效'],
      sheets: { ITEM表: { moved_to_completed: 7, moved_to_pending: 1 }, 接单表: { moved_to_completed: 7, moved_to_pending: 1 }, 正单评审表: { moved_to_completed: 6, moved_to_pending: 2 } },
    } })
    await wrapper.get('.customer-schedule__organize button').trigger('click')
    await flushPromises()
    expect(api.organize360).toHaveBeenCalledWith('huakang-a', file)
    expect(click).toHaveBeenCalledOnce()
    await vi.advanceTimersByTimeAsync(1000)
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:360')
    expect(wrapper.text()).toContain('已下载整理后的 Excel 副本')
    const report = wrapper.get('[data-testid="organize-report"]')
    expect(report.text()).toContain('本次整理按上海日期 2026-10-16 判断')
    expect(report.text()).toContain('ITEM表：移入已完成 7 条，移回未完成 1 条')
    expect(report.text()).toContain('正单评审表：移入已完成 6 条，移回未完成 2 条')
    expect(report.text()).toContain('日期提醒 5 条（最多展示前 3 条')
    expect(report.findAll('.customer-schedule__organize-warnings li').map((item) => item.text())).toEqual(['ITEM表第 8 行日期缺失', '接单表第 9 行日期冲突', '正单评审表第 10 行日期无效'])
    await wrapper.get('select').setValue('green-toys')
    await wrapper.get('select').setValue('360')
    expect(wrapper.get('.customer-schedule__organize button').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).not.toContain(file.name)
    expect(wrapper.find('[data-testid="organize-report"]').exists()).toBe(false)
  })

  it('downloads successfully when the optional organize report is unavailable', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    const wrapper = await mount360()
    await chooseWorkbook(wrapper)
    vi.stubGlobal('URL', class extends URL { static createObjectURL = vi.fn().mockReturnValue('blob:360'); static revokeObjectURL = vi.fn() })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    api.organize360.mockResolvedValueOnce({ blob: new Blob(['excel']), fileName: '360.xlsx' })
    await wrapper.get('.customer-schedule__organize button').trigger('click')
    await flushPromises()
    expect(click).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('已下载整理后的 Excel 副本')
    expect(wrapper.find('[data-testid="organize-report"]').exists()).toBe(false)
    await vi.advanceTimersByTimeAsync(1000)
  })

  it('does not download an old file response after a factory switch', async () => {
    const wrapper = await mount360()
    await chooseWorkbook(wrapper)
    let finish: ((value: { blob: Blob; fileName: string }) => void) | undefined
    api.organize360.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    await wrapper.get('.customer-schedule__organize button').trigger('click')
    api.customers.mockResolvedValue({ factory_id: 'huaxing', items: [{ code: '360', name: '360' }] })
    await wrapper.setProps({ factoryId: 'huaxing' })
    await flushPromises()
    await wrapper.get('select').setValue('360')
    finish?.({ blob: new Blob(['excel']), fileName: 'old.xlsx' })
    await flushPromises()
    expect(click).not.toHaveBeenCalled()
    expect(wrapper.find('.customer-schedule__organize').exists()).toBe(false)
  })

  it('rejects non-XLSX selections and displays server download errors', async () => {
    const wrapper = await mount360()
    await chooseWorkbook(wrapper, new File(['bad'], '360.xls'))
    expect(wrapper.text()).toContain('请选择 .xlsx 排期文件')
    expect(wrapper.get('.customer-schedule__organize button').attributes('disabled')).toBeDefined()
    await chooseWorkbook(wrapper)
    api.organize360.mockRejectedValueOnce(new Error('原排期含无效日期，请核对'))
    await wrapper.get('.customer-schedule__organize button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('无法整理排期：原排期含无效日期，请核对')
  })
})
