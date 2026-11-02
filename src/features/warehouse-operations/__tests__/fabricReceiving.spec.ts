import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DOMWrapper, flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia } from 'pinia'
import Dialog from '../FabricReceiptDialog.vue'
import Detail from '../FabricReceiptDetail.vue'
import type { FabricReceipt } from '@/api/fabricReceiving'
import Records from '../FabricReceivingRecords.vue'
import Workspace from '../FabricProcurementWorkspace.vue'
import { receiptQuantity, receiptTotal, receiptAmount, receiptAmountTotals } from '../receiptQuantities'
import type { PurchaseDetail } from '@/api/fabricProcurement'

const api = vi.hoisted(() => ({ receive: vi.fn(), receipts: vi.fn(), stock: vi.fn() }))
const sourceApi = vi.hoisted(() => ({ groups: vi.fn(), lines: vi.fn(), detail: vi.fn(), imports: vi.fn() }))
vi.mock('@/api/fabricReceiving', () => ({ fabricReceivingApi: api, materialCategoryLabels: { FABRIC: '布料', ACCESSORY: '辅料', THREAD: '线' } }))
vi.mock('@/api/fabricProcurement', () => ({ fabricProcurementApi: sourceApi }))
const source: PurchaseDetail = { id: 'L1', revision: 2, receipt_count: 0, prior_received_quantity: '50', warehouse_received_quantity: '0', can_receive: true,
  facts: { order_no: 'PO1', supplier: '供应商', material_code: '001', material_name: '白色布', unit: '码', ordered_quantity: '100', reported_received_quantity: '50', source_category: 'SUPPLEMENT',
    status: 'PENDING', source_line_id: '', production_no: 'P1', plan_no: '', old_material_code: '', contract_no: '', unit_price: '0',
    order_date: null, order_date_raw: '', delivery_detail: '', delivery_note_no: '', delivery_note_date: null, delivery_note_date_raw: '',
    reported_receipt_date: null, reported_receipt_date_raw: '', supplier_reply: '', supplier_reply_date: null, second_reply: '', second_reply_date: null,
    note: '', warehouse_note: '' }, available_locations: ['A01','A02'].map(code => ({ id: code, code, name: code, warehouse: '一仓', category: 'FABRIC', label: `一仓／${code}` })), evidence: [] }
let wrapper: VueWrapper | undefined
const body = () => new DOMWrapper(document.body)
const button = (label: string) => body().findAll('button').find(item => item.text() === label)!
async function router() {
  const instance = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] })
  await instance.push('/'); await instance.isReady(); return instance
}
beforeEach(() => { vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-10-05T18:00:00Z')); vi.clearAllMocks(); sourceApi.groups.mockResolvedValue({ total: 0, line_total: 0, groups: [] }); api.receipts.mockResolvedValue({ total: 0, items: [] }); api.stock.mockResolvedValue({ total: 0, items: [] }); sourceApi.lines.mockResolvedValue({ total: 1, items: [source], can_receive: true }); sourceApi.detail.mockResolvedValue(source) })
afterEach(() => { wrapper?.unmount(); wrapper = undefined; document.body.innerHTML = ''; vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })
async function open(receiptSource = source) { wrapper = mount(Dialog, { props: { source: receiptSource }, attachTo: document.body, global: { plugins: [await router(), createPinia()] } }); await flushPromises() }
async function fill() {
  await body().get('[aria-label="送货依据编号"]').setValue('DN-001')
  await body().get('[aria-label="本单到货量"]').setValue('1000')
  await body().get('[aria-label="入库物料分类"]').setValue('FABRIC')
  await body().get('[aria-label="第1项实点数量"]').setValue('0.1')
  await body().get('[aria-label="第1项仓位"]').setValue('一仓／A01')
  await body().get('[aria-label="第1项缸号"]').setValue('0001')
}
describe('fabric actual receiving', () => {
  it.each([
    [' PＣＳ ', undefined, 'ACCESSORY'], ['米', undefined, 'FABRIC'], ['卷', undefined, 'ACCESSORY'],
    ['公斤', undefined, ''], ['千克(转算专用)', undefined, ''], ['片', undefined, ''],
    ['码', 'THREAD', 'THREAD'], ['Pcs', 'FABRIC', 'FABRIC'],
  ] as const)('suggests from %s while preserving confirmed category %s', async (unit, material_category, expected) => {
    await open({ ...source, material_category, facts: { ...source.facts, unit } })
    expect(body().get<HTMLSelectElement>('[aria-label="入库物料分类"]').element.value).toBe(expected)
    expect(api.receive).not.toHaveBeenCalled()
  })
  it('blocks split totals above the delivery quantity even with an overage reason', async () => {
    await open(); await fill()
    await body().get('[aria-label="本单到货量"]').setValue('0.3')
    await button('＋ 增加明细').trigger('click')
    await body().get('[aria-label="第2项实点数量"]').setValue('0.200001')
    await body().get('[aria-label="第2项仓位"]').setValue('一仓／A02')
    await body().get('[aria-label="第2项缸号"]').setValue('0001')
    expect(body().text()).toContain('实点合计超过本单到货量')
    expect(button('保存并入库').attributes('disabled')).toBeDefined()
    expect(api.receive).not.toHaveBeenCalled()
    await body().get('[aria-label="第2项实点数量"]').setValue('0.2')
    expect(button('保存并入库').attributes('disabled')).toBeUndefined()
    api.receive.mockResolvedValue({ id: 'split' })
    await button('保存并入库').trigger('click'); await flushPromises()
    expect(api.receive.mock.calls[0]![1]).toEqual(expect.objectContaining({ delivery_quantity: '0.3', batches: expect.arrayContaining([expect.objectContaining({ quantity: '0.2' })]) }))
  })
  it('calculates amounts exactly with whole-receipt rounding, without floating-point or missing-price zeroes', () => {
    expect(receiptAmount('0.125', '0.04')).toBe('0.01')
    expect(receiptAmount('0.1', '0.2')).toBe('0.02')
    expect(receiptAmount('50', '0')).toBe('0.00')
    expect(receiptAmount('50', '')).toBeUndefined()
    expect(receiptAmount('50', '-1')).toBeUndefined()
    expect(receiptAmount('999999999999.999999', '999999999999.999999')).toBe('999999999999999998000000.00')
    expect(receiptAmountTotals([{ amount: '0.01', currency: 'CNY' }, { amount: '1.25', currency: 'CNY' }, { amount: '2.00', currency: 'HKD' }, { amount: undefined, currency: 'CNY' }])).toEqual([{ currency: 'CNY', amount: '1.26' }, { currency: 'HKD', amount: '2.00' }])
  })
  it('adds optional price and currency, previews amount and submits frozen receipt evidence', async () => {
    await open(); await fill()
    expect(body().get<HTMLSelectElement>('[aria-label="入库币种"]').element.value).toBe('CNY')
    await body().get('[aria-label="入库单价"]').setValue('0.05')
    expect(button('保存并入库').attributes('disabled')).toBeUndefined()
    expect(body().get('.receipt-price-amount').text()).toContain('0.01 CNY')
    await body().get('[aria-label="入库币种"]').setValue('')
    expect(button('保存并入库').attributes('disabled')).toBeDefined()
    await body().get('[aria-label="入库币种"]').setValue('CNY')
    expect(body().get('.receipt-price-amount').text()).toContain('0.01 CNY')
    await body().get('[aria-label="入库单价"]').setValue('-1')
    expect(button('保存并入库').attributes('disabled')).toBeDefined()
    await body().get('[aria-label="入库单价"]').setValue('0')
    expect(body().get('.receipt-price-amount').text()).toContain('0.00 CNY')
    api.receive.mockResolvedValue({ id: 'R-PRICE' })
    await button('保存并入库').trigger('click'); await flushPromises()
    expect(api.receive.mock.calls[0]![1]).toEqual(expect.objectContaining({ unit_price: '0', price_unit: '码', currency: 'CNY' }))
    expect(api.receive.mock.calls[0]![1]).not.toHaveProperty('amount')
  })
  it('defaults dates to Shanghai today, suggests category and closes untouched defaults', async () => {
    await open()
    expect(body().get<HTMLSelectElement>('[aria-label="入库币种"]').element.value).toBe('CNY')
    expect(body().get<HTMLInputElement>('[aria-label="实际收货日期"]').element.value).toBe('2026-10-06')
    expect(body().get<HTMLInputElement>('[aria-label="送货单日期"]').element.value).toBe('2026-10-06')
    expect(body().get<HTMLSelectElement>('[aria-label="入库物料分类"]').element.value).toBe('FABRIC')
    expect(body().find('[aria-label="记账月份"]').exists()).toBe(false)
    expect(body().find('[aria-label="此前实收基数"]').exists()).toBe(false)
    expect(body().find('[aria-label="此前没收过"]').exists()).toBe(false)
    expect(body().find('[aria-label="确认实际入库"]').exists()).toBe(false)
    expect(body().get<HTMLDetailsElement>('.fabric-receipt-more').element.open).toBe(false)
    const confirm = vi.spyOn(window, 'confirm')
    await button('返回待收料').trigger('click')
    expect(confirm).not.toHaveBeenCalled(); expect(wrapper!.emitted('close')).toHaveLength(1)
  })
  it('requires manual category, every location and dye lot for fabric, with no first-receipt question', async () => {
    await open()
    await body().get('[aria-label="送货依据编号"]').setValue('DN-001')
  await body().get('[aria-label="本单到货量"]').setValue('1000')
    await body().get('[aria-label="第1项实点数量"]').setValue('29')
    await body().get('[aria-label="第1项仓位"]').setValue('一仓／A01')
    expect(button('保存并入库').attributes('disabled')).toBeDefined()
    await body().get('[aria-label="入库物料分类"]').setValue('FABRIC')
    expect(button('保存并入库').attributes('disabled')).toBeDefined()
    expect(body().get('[aria-label="第1项缸号"]').attributes('required')).toBeDefined()
    await body().get('[aria-label="第1项仓位"]').setValue('一仓／A01')
    await body().get('[aria-label="第1项缸号"]').setValue('0001')
    expect(button('保存并入库').attributes('disabled')).toBeUndefined()
    await body().get('[aria-label="第1项仓位"]').setValue('  ')
    expect(button('保存并入库').attributes('disabled')).toBeDefined()
  })
  it('does not submit manually editable month or a prior receipt quantity', async () => {
    await open(); await fill()
    api.receive.mockResolvedValue({ id: 'R1' })
    await button('保存并入库').trigger('click'); await flushPromises()
    const payload = api.receive.mock.calls[0]![1]
    expect(payload).not.toHaveProperty('accounting_month')
    expect(payload).not.toHaveProperty('prior_received_quantity')
    expect(payload).not.toHaveProperty('unit_price')
    expect(payload).not.toHaveProperty('price_unit')
    expect(payload).not.toHaveProperty('currency')
    expect(payload).toEqual(expect.objectContaining({ confirmed: true, delivery_note_date: '2026-10-06' }))
  })
  it('shows the remaining quantity after recorded receipts without repeating historical questions', async () => {
    await open({ ...source, receipt_count: 1, warehouse_received_quantity: '20' }); await fill()
    expect(body().get('.fabric-intake-progress').text()).toContain('30 码')
    await body().get('[aria-label="第1项实点数量"]').setValue('30')
    expect(body().find('[aria-label="超收说明"]').exists()).toBe(false)
    api.receive.mockResolvedValue({ id: 'R2' })
    await button('保存并入库').trigger('click'); await flushPromises()
    expect(api.receive.mock.calls[0]![1].expected_receipt_count).toBe(1)
  })
  it.each(['ACCESSORY', 'THREAD'])('hides fabric identifiers for %s and clears them in the submitted payload', async category => {
    await open({ ...source, available_locations: [...source.available_locations!, { id: 'NEW', code: 'NEW', name: 'NEW', warehouse: '分类仓', label: '分类仓／NEW', category }] } as PurchaseDetail); await fill()
    await body().get('[aria-label="第1项卷号"]').setValue('0002')
    await body().get('[aria-label="入库物料分类"]').setValue(category)
    expect(button('保存并入库').attributes('disabled')).toBeDefined()
    await body().get('[aria-label="第1项仓位"]').setValue('分类仓／NEW')
    expect(body().find('[aria-label="第1项缸号"]').exists()).toBe(false)
    expect(body().find('[aria-label="第1项卷号"]').exists()).toBe(false)
    expect(button('保存并入库').attributes('disabled')).toBeUndefined()
    api.receive.mockResolvedValue({ id: 'R1' })
    await button('保存并入库').trigger('click'); await flushPromises()
    expect(api.receive.mock.calls[0]![1]).toEqual(expect.objectContaining({ material_category: category, batches: [{ quantity: '0.1', counted_quantity: '0.1', damaged_quantity: '0', rejected_quantity: '0', other_unusable_quantity: '0', location_id: 'NEW', location: '分类仓／NEW', dye_lot: '', roll_no: '' }] }))
  })
  it('only requires an explanation for exact overage and clears stale explanations for normal partial receipts', async () => {
    await open(); await fill()
    expect(body().find('[aria-label="超收说明"]').exists()).toBe(false)
    await body().get('[aria-label="第1项实点数量"]').setValue('50.000001')
    expect(body().get('.fabric-receipt-overage').text()).toContain('超出待收数量 0.000001 码')
    expect(button('保存并入库').attributes('disabled')).toBeDefined()
    await body().get('[aria-label="超收说明"]').setValue('实物多到')
    expect(button('保存并入库').attributes('disabled')).toBeUndefined()
    await body().get('[aria-label="第1项实点数量"]').setValue('30')
    expect(body().find('[aria-label="超收说明"]').exists()).toBe(false)
    api.receive.mockResolvedValue({ id: 'R1' })
    await button('保存并入库').trigger('click'); await flushPromises()
    expect(api.receive.mock.calls[0]![1].difference_reason).toBe('')
  })
  it('keeps backdated receipt and delivery dates without an independent accounting month', async () => {
    await open(); await fill()
    await body().get('[aria-label="实际收货日期"]').setValue('2026-09-29')
    await body().get('[aria-label="送货单日期"]').setValue('2026-09-28')
    await body().get('[aria-label="第1项缸号"]').setValue('0002')
    await body().get('[aria-label="第1项卷号"]').setValue('0003')
    api.receive.mockResolvedValue({ id: 'R1' })
    await button('保存并入库').trigger('click'); await flushPromises()
    expect(api.receive.mock.calls[0]![1]).toEqual(expect.objectContaining({ receipt_date: '2026-09-29', delivery_note_date: '2026-09-28', batches: [{ quantity: '0.1', counted_quantity: '0.1', damaged_quantity: '0', rejected_quantity: '0', other_unusable_quantity: '0', location_id: 'A01', location: '一仓／A01', dye_lot: '0002', roll_no: '0003' }] }))
  })
  it('does not turn unknown source quantities into zero', async () => {
    await open({ ...source, prior_received_quantity: null, receipt_quantity_review_required: true, can_receive: true }); await fill()
    expect(body().text()).toContain('起始待收量待负责人核对')
    expect(button('保存并入库').attributes('disabled')).toBeUndefined()
    expect(body().text()).toContain('待收数量待核对')
  })
  it('can open and post from HTTP browsers without crypto.randomUUID', async () => {
    vi.stubGlobal('crypto', { getRandomValues: crypto.getRandomValues.bind(crypto) })
    await open(); await fill()
    api.receive.mockResolvedValue({ id: 'R1' })
    await button('保存并入库').trigger('click'); await flushPromises()
    expect(api.receive.mock.calls[0]![1].request_id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
  })
  it('uses exact decimals and distinguishes empty, explicit zero and invalid splits', () => {
    expect(receiptTotal(['0.1', '0.2'])).toBe('0.3')
    expect(receiptTotal(['1.000001', '2.999999'])).toBe('4')
    expect(receiptQuantity('0')).toBe(0n)
    expect(receiptQuantity('')).toBeUndefined()
    expect(receiptQuantity('0.0000001')).toBeUndefined()
    expect(receiptTotal(['0', '1'])).toBeUndefined()
    expect(receiptQuantity('1000000000000')).toBeUndefined()
  })
  it('submits only actual splits with source and receipt versions', async () => {
    await open()
    expect(body().find('[aria-label="此前实收基数"]').exists()).toBe(false)
    expect(button('保存并入库').attributes('disabled')).toBeDefined()
    await fill()
    await button('＋ 增加明细').trigger('click')
    await body().get('[aria-label="第2项实点数量"]').setValue('0.2')
    await body().get('[aria-label="第2项仓位"]').setValue('一仓／A02')
    await body().get('[aria-label="第2项缸号"]').setValue('0002')
    await body().get('[aria-label="第1项卷号"]').setValue('00001')
    expect(body().text()).toContain('本次入库合计：0.3 码')
    api.receive.mockResolvedValue({ id: 'R1', quantity: '0.3', unit: '码', stock_posted: true })
    await button('保存并入库').trigger('click'); await flushPromises()
    expect(api.receive).toHaveBeenCalledWith('L1', expect.objectContaining({ expected_source_revision: 2, expected_receipt_count: 0, confirmed: true,
      batches: [{ quantity: '0.1', counted_quantity: '0.1', damaged_quantity: '0', rejected_quantity: '0', other_unusable_quantity: '0', location_id: 'A01', location: '一仓／A01', dye_lot: '0001', roll_no: '00001' }, { quantity: '0.2', counted_quantity: '0.2', damaged_quantity: '0', rejected_quantity: '0', other_unusable_quantity: '0', location_id: 'A02', location: '一仓／A02', dye_lot: '0002', roll_no: '' }] }))
    expect(wrapper!.emitted('saved')?.[0]?.[0]).toEqual(expect.objectContaining({ id: 'R1' }))
  })
  it('freezes the exact payload and reuses its request after an unknown save outcome', async () => {
    await open(); await fill()
    api.receive.mockRejectedValueOnce(new Error('连接中断'))
    await button('保存并入库').trigger('click'); await flushPromises()
    const first = api.receive.mock.calls[0]![1]
    expect(body().get('fieldset').attributes('disabled')).toBeDefined()
    expect(body().text()).toContain('填写内容已锁定')
    api.receive.mockResolvedValueOnce({ id: 'R1' })
    await button('重试本次入库').trigger('click'); await flushPromises()
    expect(api.receive.mock.calls[1]![1]).toEqual(first)
  })
  it('guards a date-only change and keeps an HTTP timeout outcome frozen for retry', async () => {
    await open()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    await body().get('[aria-label="送货单日期"]').setValue('2026-09-16')
    await button('返回待收料').trigger('click')
    expect(confirm).toHaveBeenCalledOnce(); expect(wrapper!.emitted('close')).toBeUndefined()
    await fill(); api.receive.mockRejectedValueOnce({ response: { status: 408 }, isAxiosError: true })
    await button('保存并入库').trigger('click'); await flushPromises()
    expect(body().get('fieldset').attributes('disabled')).toBeDefined()
    expect(button('重试本次入库').exists()).toBe(true)
  })
  it('guards losing filled rows, permits correcting rejected input and closes a stale source', async () => {
    await open(); await fill()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    await button('返回待收料').trigger('click')
    expect(confirm).toHaveBeenCalledOnce(); expect(wrapper!.emitted('close')).toBeUndefined()
    api.receive.mockRejectedValueOnce({ response: { status: 422, data: { detail: '请输入差异原因' } }, isAxiosError: true })
    await button('保存并入库').trigger('click'); await flushPromises()
    expect(body().get('fieldset').attributes('disabled')).toBeUndefined()
    api.receive.mockRejectedValueOnce({ response: { status: 409, data: { detail: '来源已变化' } }, isAxiosError: true })
    await button('保存并入库').trigger('click'); await flushPromises()
    expect(wrapper!.emitted('stale')?.[0]?.[0]).toContain('来源已变化')
  })
  it('opens receiving from a freshly read source, refreshes the list after posting, and respects read-only accounts', async () => {
    wrapper = mount(Workspace, { props: { mode: 'pending' }, attachTo: document.body, global: { plugins: [await router(), createPinia()] } }); await flushPromises()
    await button('按采购明细').trigger('click'); await flushPromises()
    await button('登记入库').trigger('click'); await flushPromises()
    expect(sourceApi.detail).toHaveBeenCalledWith('L1')
    await fill(); api.receive.mockResolvedValue({ id: 'R1', quantity: '0.1', unit: '码' })
    await button('保存并入库').trigger('click'); await flushPromises()
    expect(wrapper!.text()).toContain('本次实收 0.1 码 已计入待检库存')
    expect(sourceApi.lines).toHaveBeenCalledTimes(2)
    sourceApi.lines.mockResolvedValue({ total: 1, items: [source], can_receive: false })
    await wrapper!.get('form').trigger('submit'); await flushPromises()
    expect(wrapper!.findAll('button').some(item => item.text() === '登记入库')).toBe(false)
  })
  it('loads posted receipt/stock views and clears protected records on a denied query', async () => {
    api.stock.mockResolvedValue({ total: 1, items: [{ id: 'B1', receipt_id: 'R1', movement_id: 'M1', facts: source.facts, quantity: '0.3', unit: '码', material_category: 'FABRIC', location_id: 'A01', location: '一仓／A01', dye_lot: '', roll_no: '', receipt_date: '2026-09-16', accounting_month: '2026-09', delivery_reference: 'DN1' }] })
    wrapper = mount(Records, { props: { mode: 'stock' }, global: { plugins: [await router(), createPinia()] } }); await flushPromises()
    expect(wrapper!.text()).toContain('0.3 码')
    expect(wrapper!.text()).toContain('期初、退料、调仓和盘点不计入本页')
    api.stock.mockRejectedValue({ response: { status: 403, data: { detail: '无权限' } }, isAxiosError: true })
    await wrapper!.get('form').trigger('submit'); await flushPromises()
    expect(wrapper!.findAll('tbody tr')).toHaveLength(0)
    expect(wrapper!.text()).toContain('无权限')
    await wrapper!.setProps({ mode: 'receipts' }); await flushPromises()
    expect(api.receipts).toHaveBeenCalledWith('', 0, expect.objectContaining({ sort: 'RECEIPT_DESC' }))
  })
})


describe('purchase receipt v2 differences', () => {
  it('calculates accepted quantity and keeps shortage and returned quantities separate', async () => {
    await open({ ...source, warehouse_outstanding_quantity: '1000' }); await fill()
    await body().get('[aria-label="第1项实点数量"]').setValue('980')
    await body().get('[aria-label="第1项拒收数量"]').setValue('20')
    expect(body().get('[aria-label="第1项入库数量"]').text()).toBe('960')
    expect(body().get('[aria-label="本次数量汇总"]').text()).toContain('送货量1000 码实点合计980 码破损合计0 码拒收合计20 码其他不可用合计0 码入库合计960 码短少20 码退供应商合计20 码')
    api.receive.mockResolvedValue({ id: 'V2', quantity: '960', stock_posted: true })
    await button('保存并入库').trigger('click'); await flushPromises()
    expect(api.receive).toHaveBeenCalledWith('L1', expect.objectContaining({
      expected_source_revision: 2, expected_receipt_count: 0, delivery_quantity: '1000',
      batches: [expect.objectContaining({ quantity: '960', counted_quantity: '980', damaged_quantity: '0', rejected_quantity: '20', other_unusable_quantity: '0' })],
    }))
  })
  it.each([
    ['实点数量', ''], ['实点数量', '-1'], ['实点数量', '1e2'], ['实点数量', '0.0000001'],
    ['破损数量', '-1'], ['拒收数量', '0.2'], ['其他不可用', ''],
  ])('blocks invalid %s = %s', async (field, value) => {
    await open(); await fill()
    await body().get(`[aria-label="第1项${field}"]`).setValue(value)
    expect(button('保存并入库').attributes('disabled')).toBeDefined()
    await body().get('form').trigger('submit'); expect(api.receive).not.toHaveBeenCalled()
  })
  it('uses counted for the delivery limit even when accepted is below it', async () => {
    await open(); await fill()
    await body().get('[aria-label="本单到货量"]').setValue('10')
    await body().get('[aria-label="第1项实点数量"]').setValue('11')
    await body().get('[aria-label="第1项拒收数量"]').setValue('10')
    expect(body().get('[aria-label="第1项入库数量"]').text()).toBe('1')
    expect(button('保存并入库').attributes('disabled')).toBeDefined()
    expect(body().text()).toContain('实点合计超过本单到货量')
  })
  it('accepts zero stock with separate damage and other evidence and zero price amount', async () => {
    await open(); await fill()
    await body().get('[aria-label="第1项实点数量"]').setValue('10')
    await body().get('[aria-label="第1项破损数量"]').setValue('2')
    await body().get('[aria-label="第1项拒收数量"]').setValue('5')
    await body().get('[aria-label="第1项其他不可用"]').setValue('3')
    await body().get('[aria-label="入库单价"]').setValue('5')
    expect(body().text()).toContain('本次全部不可用，只登记差异，不增加库存')
    expect(body().get('.receipt-price-amount').text()).toContain('0.00 CNY')
    expect(button('保存并入库').attributes('disabled')).toBeUndefined()
    api.receive.mockResolvedValue({ id: 'ZERO', quantity: '0', stock_posted: false })
    await button('保存并入库').trigger('click'); await flushPromises()
    expect(api.receive.mock.calls[0]![1].batches[0]).toMatchObject({ quantity: '0', counted_quantity: '10', damaged_quantity: '2', rejected_quantity: '5', other_unusable_quantity: '3' })
  })
  it('adds a same-dye roll without copying physical quantities and rejects duplicate roll/bin', async () => {
    await open(); await fill()
    await body().get('[aria-label="第1项卷号"]').setValue('0002')
    await body().get('[aria-label="第1项破损数量"]').setValue('0.01')
    await body().get('[aria-label="第1项同缸新增一卷"]').trigger('click')
    for (const [field, value] of [['缸号','0001'], ['卷号',''], ['实点数量',''], ['破损数量','0'], ['拒收数量','0'], ['其他不可用','0']]) {
      expect(body().get<HTMLInputElement>(`[aria-label="第2项${field}"]`).element.value).toBe(value)
    }
    expect(body().get<HTMLInputElement>('[aria-label="第2项仓位"]').element.value).toBe('一仓／A01')
    expect(button('保存并入库').attributes('disabled')).toBeDefined()
    await body().get('[aria-label="第2项实点数量"]').setValue('1')
    await body().get('[aria-label="第2项卷号"]').setValue('0002')
    expect(body().text()).toContain('同缸号、卷号和仓位重复')
    expect(button('保存并入库').attributes('disabled')).toBeDefined()
    await body().get('[aria-label="第2项仓位"]').setValue('一仓／A02')
    expect(button('保存并入库').attributes('disabled')).toBeUndefined()
  })
  it('requires overage reason only for accepted, not counted', async () => {
    await open(); await fill()
    await body().get('[aria-label="第1项实点数量"]').setValue('60')
    await body().get('[aria-label="第1项拒收数量"]').setValue('10')
    expect(body().find('[aria-label="超收说明"]').exists()).toBe(false)
    expect(button('保存并入库').attributes('disabled')).toBeUndefined()
    await body().get('[aria-label="第1项拒收数量"]').setValue('9')
    expect(button('保存并入库').attributes('disabled')).toBeDefined()
  })
  it('shows a zero-stock success notice after saving from the purchase workspace', async () => {
    wrapper = mount(Workspace, { props: { mode: 'pending' }, attachTo: document.body, global: { plugins: [await router(), createPinia()] } }); await flushPromises()
    await button('按采购明细').trigger('click'); await flushPromises()
    await button('登记入库').trigger('click'); await flushPromises(); await fill()
    await body().get('[aria-label="第1项拒收数量"]').setValue('0.1')
    api.receive.mockResolvedValue({ id: 'ZERO', quantity: '0', unit: '码', stock_posted: false })
    await button('保存并入库').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('本次入库 0，全部为差异/退供应商；未增加库存')
    expect(wrapper.text()).not.toContain('已计入待检库存')
  })
  it('renders difference evidence and zero-stock status without an empty stock table', async () => {
    const record = { id: 'R0', source_line_id: 'L1', source_revision: 2, facts: source.facts, quantity: '0', unit: '码',
      material_category: 'FABRIC', stock_posted: false, receipt_date: '2026-10-06', accounting_month: '2026-10',
      occurred_at: '2026-10-06T10:00:00+08:00', batches: [], delivered_quantity: '1000', counted_quantity: '980',
      accepted_quantity: '0', damaged_quantity: '10', rejected_quantity: '960', other_unusable_quantity: '10', shortage_quantity: '20', returned_to_supplier: '980',
      receipt_lines: [{ batch_id: null, location: '一仓／A01', dye_lot: '0001', roll_no: '0002', counted_quantity: '980',
        damaged_quantity: '10', rejected_quantity: '960', other_unusable_quantity: '10', accepted_quantity: '0', returned_to_supplier: '980',
        shortage_quantity: '20', shortage_scope: 'RECEIPT', disposition: 'RETURNED_TO_SUPPLIER' }],
    } as FabricReceipt
    wrapper = mount(Detail, { props: { record }, attachTo: document.body, global: { plugins: [await router()] } }); await flushPromises()
    expect(body().text()).toContain('本次入库 0，全部为差异/退供应商')
    expect(body().get('.receipt-differences').text()).toContain('退供应商合计980 码')
    expect(body().get('[aria-label="逐卷差异"]').text()).toContain('不可用量当场退供应商')
    expect(body().find('[aria-label="入库批次明细"]').exists()).toBe(false)
    await wrapper.setProps({ record: { ...record, quantity: '1000', accepted_quantity: '1000', counted_quantity: '1000', shortage_quantity: '0', returned_to_supplier: '0', stock_posted: true } })
    expect(body().find('.receipt-differences').exists()).toBe(false)
    await wrapper.setProps({ record: { ...record, quantity: '10', stock_posted: true, receipt_lines: undefined } })
    expect(body().find('.receipt-differences').exists()).toBe(false)
  })
})
