import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DOMWrapper, flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import Workspace from '../FabricProcurementWorkspace.vue'
import Dialog from '../FabricBatchReceiptDialog.vue'
import DateRangeFilter from '@/components/DateRangeFilter.vue'
import { purchaseSearchKey } from '../purchaseSearch'
import type { PurchaseDetail } from '@/api/fabricProcurement'

const api = vi.hoisted(() => ({ receiveBatch: vi.fn() }))
const sourceApi = vi.hoisted(() => ({ lines: vi.fn(), detail: vi.fn(), imports: vi.fn() }))
vi.mock('@/api/fabricReceiving', () => ({ fabricReceivingApi: api, materialCategoryLabels: { FABRIC: '布料', ACCESSORY: '辅料', THREAD: '线' } }))
vi.mock('@/api/fabricProcurement', () => ({ fabricProcurementApi: sourceApi }))
const source = (id: string, unit = '码', category: 'FABRIC' | 'ACCESSORY' = 'FABRIC'): PurchaseDetail => ({ id, revision: 2, receipt_count: 0, can_receive: true,
  material_category: category, warehouse_received_quantity: '0', warehouse_outstanding_quantity: id === 'L1' ? '5' : null,
  facts: { order_no: `PO-${id}`, material_code: id, material_name: `物料${id}`, supplier: '供应商', unit, source_category: 'PURCHASE', production_no: 'P1', style_no: 'ST1' }, evidence: [] } as PurchaseDetail)
let wrapper: VueWrapper | undefined
const body = () => new DOMWrapper(document.body)
const button = (label: string) => body().findAll('button').find(item => item.text().startsWith(label))!
async function router() {
  const instance = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] })
  await instance.push('/'); await instance.isReady(); return instance
}
beforeEach(() => { vi.clearAllMocks(); sourceApi.lines.mockResolvedValue({ total: 100, items: [source('L1')], can_receive: true }); sourceApi.detail.mockImplementation(async id => source(id)) })
afterEach(() => { wrapper?.unmount(); wrapper = undefined; document.body.innerHTML = ''; vi.restoreAllMocks() })
async function openDialog(sources = [source('L1'), source('L2', '个', 'ACCESSORY')]) {
  wrapper = mount(Dialog, { props: { sources }, attachTo: document.body, global: { plugins: [await router()] } }); await flushPromises()
}
async function fill() {
  await body().get('[aria-label="批量送货依据编号"]').setValue('DN-ALL')
  for (const index of [1, 2]) {
    await body().get(`[aria-label="物料${index}明细1实收数量"]`).setValue('0.125')
    await body().get(`[aria-label="物料${index}明细1仓位"]`).setValue(`A0${index}`)
  }
  await body().get('[aria-label="物料1明细1缸号"]').setValue('0001')
}
describe('carton-style fabric selection and batch receiving', () => {
  it('uses the header keyword across all purchase text, without lower duplicate search fields', async () => {
    const search = ref(''), submitted = ref(0)
    wrapper = mount(Workspace, { props: { mode: 'pending' }, attachTo: document.body, global: { plugins: [await router()], provide: { [purchaseSearchKey as symbol]: { search, submitted } } } })
    await flushPromises()
    expect(body().find('input[type="search"]').exists()).toBe(false)
    expect(body().find('[aria-label="款号筛选"]').exists()).toBe(false)
    expect(body().find('[aria-label="采购单号筛选"]').exists()).toBe(false)
    search.value = 'ST1'; submitted.value++; await flushPromises()
    expect(sourceApi.lines).toHaveBeenLastCalledWith('PENDING', 'ST1', 0, 'OUTSTANDING', expect.any(Object))
    expect(body().find('[aria-label="选择供应商复期范围"]').exists()).toBe(true)
    await button('来源 / 核对').trigger('click'); await flushPromises()
    await new Promise(resolve => setTimeout(resolve, 450))
    expect(sourceApi.lines).toHaveBeenCalledTimes(2)
    expect(body().get('[role="dialog"]').text()).toContain('采购来源详情')
  })
  it('queries the selected promise date range and clears both request dates and calendar display once', async () => {
    wrapper = mount(Workspace, { props: { mode: 'pending' }, attachTo: document.body, global: { plugins: [await router()] } }); await flushPromises()
    wrapper.getComponent(DateRangeFilter).vm.$emit('update:modelValue', { start: { toString: () => '2026-09-01' }, end: { toString: () => '2026-09-30' } })
    await flushPromises()
    expect(sourceApi.lines).toHaveBeenLastCalledWith('PENDING', '', 0, 'OUTSTANDING', expect.objectContaining({ promise_from: '2026-09-01', promise_to: '2026-09-30' }))
    const before = sourceApi.lines.mock.calls.length
    await button('清空筛选').trigger('click'); await flushPromises()
    expect(sourceApi.lines).toHaveBeenCalledTimes(before + 1)
    expect(sourceApi.lines).toHaveBeenLastCalledWith('PENDING', '', 0, 'OUTSTANDING', expect.objectContaining({ promise_from: '', promise_to: '' }))
    expect(wrapper.getComponent(DateRangeFilter).props('modelValue')).toEqual({ start: undefined, end: undefined })
  })
  it('preserves selected sources across pages and filters and rechecks every source before opening', async () => {
    wrapper = mount(Workspace, { props: { mode: 'pending' }, attachTo: document.body, global: { plugins: [await router()] } }); await flushPromises()
    await body().get('[aria-label="选择 PO-L1 · L1"]').setValue(true)
    sourceApi.lines.mockResolvedValue({ total: 100, items: [source('L2')], can_receive: true })
    await button('下一页').trigger('click'); await flushPromises()
    expect(body().text()).toContain('其中 1 项不在当前筛选内')
    await body().get('[aria-label="全选当前页可入库物料"]').setValue(true)
    expect(button('登记所选订单入库').text()).toContain('2')
    await body().get('[aria-label="采购类型筛选"]').setValue('SUPPLEMENT'); await flushPromises()
    expect(button('登记所选订单入库').text()).toContain('2')
    await button('登记所选订单入库').trigger('click'); await flushPromises()
    expect(sourceApi.detail.mock.calls.map(call => call[0])).toEqual(['L1', 'L2'])
    expect(body().text()).toContain('批量登记入库 · 2 项物料')
  })
  it('blocks the whole selection when a freshly checked source cannot receive', async () => {
    sourceApi.lines.mockResolvedValue({ total: 2, items: [source('L1'), source('L2')], can_receive: true })
    sourceApi.detail.mockImplementation(async id => ({ ...source(id), can_receive: id === 'L1' }))
    wrapper = mount(Workspace, { props: { mode: 'pending' }, attachTo: document.body, global: { plugins: [await router()] } }); await flushPromises()
    await body().get('[aria-label="全选当前页可入库物料"]').setValue(true)
    await button('登记所选订单入库').trigger('click'); await flushPromises()
    expect(body().find('[role="dialog"]').exists()).toBe(false)
    expect(body().get('[role="alert"]').text()).toContain('PO-L2')
  })
  it('caps selection at 50, keeps hidden selections removable, and hides checkboxes for read-only users', async () => {
    const many = Array.from({ length: 50 }, (_, index) => source(`L${index + 1}`))
    sourceApi.lines.mockResolvedValueOnce({ total: 51, items: many, can_receive: true }).mockResolvedValueOnce({ total: 51, items: [source('L51')], can_receive: true })
    wrapper = mount(Workspace, { props: { mode: 'pending' }, attachTo: document.body, global: { plugins: [await router()] } }); await flushPromises()
    await body().get('[aria-label="全选当前页可入库物料"]').setValue(true)
    await button('下一页').trigger('click'); await flushPromises()
    await body().get('[aria-label="选择 PO-L51 · L51"]').setValue(true)
    expect(body().get('[role="alert"]').text()).toContain('最多选择 50')
    expect(button('登记所选订单入库').text()).toContain('50')
    await body().get('[aria-label="取消选择 PO-L1 · L1 · 物料L1"]').trigger('click'); await flushPromises()
    expect(button('登记所选订单入库').text()).toContain('49')
    sourceApi.lines.mockResolvedValue({ total: 1, items: [source('L51')], can_receive: false })
    await button('刷新').trigger('click'); await flushPromises()
    expect(body().find('input[type="checkbox"]').exists()).toBe(false)
    expect(body().find('[aria-label="批量已选范围"]').exists()).toBe(false)
  })
  it('never fills actual quantities from chase; requires each bin and fabric dye, and posts unlike units separately', async () => {
    await openDialog()
    expect(body().get<HTMLInputElement>('[aria-label="物料1明细1实收数量"]').element.value).toBe('')
    expect(body().find('[aria-label="物料2明细1缸号"]').exists()).toBe(false)
    await fill()
    await body().get('[aria-label="物料1明细1缸号"]').setValue('')
    expect(button('保存全部并入库').attributes('disabled')).toBeDefined()
    await body().get('[aria-label="物料1明细1缸号"]').setValue('0001')
    await body().get('[aria-label="物料2明细1仓位"]').setValue('')
    expect(button('保存全部并入库').attributes('disabled')).toBeDefined()
    await body().get('[aria-label="物料2明细1仓位"]').setValue('A02')
    api.receiveBatch.mockResolvedValue({ request_id: 'R', receipts: [{ id: 'R1' }, { id: 'R2' }] })
    await body().get('form').trigger('submit'); await flushPromises()
    expect(api.receiveBatch).toHaveBeenCalledWith(expect.objectContaining({ delivery_reference: 'DN-ALL', confirmed: true, items: [
      expect.objectContaining({ source_line_id: 'L1', material_category: 'FABRIC', batches: [{ quantity: '0.125', location: 'A01', dye_lot: '0001', roll_no: '' }] }),
      expect.objectContaining({ source_line_id: 'L2', material_category: 'ACCESSORY', batches: [{ quantity: '0.125', location: 'A02', dye_lot: '', roll_no: '' }] }),
    ] }))
    expect(wrapper!.emitted('saved')).toHaveLength(1)
  })
  it('requires an explanation only for known per-item overage, and leaves unknown chase receivable', async () => {
    await openDialog(); await fill()
    await body().get('[aria-label="物料1明细1实收数量"]').setValue('6')
    await body().get('[aria-label="物料2明细1实收数量"]').setValue('600')
    expect(body().find('[aria-label="第2项超收说明"]').exists()).toBe(false)
    expect(button('保存全部并入库').attributes('disabled')).toBeDefined()
    await body().get('[aria-label="第1项超收说明"]').setValue('供应商多送1码')
    expect(button('保存全部并入库').attributes('disabled')).toBeUndefined()
  })
  it.each([undefined, 408, 500])('freezes the complete payload after unknown outcome %s and replays the same UUID', async status => {
    await openDialog(); await fill()
    api.receiveBatch.mockRejectedValueOnce({ isAxiosError: true, message: 'network', ...(status ? { response: { status, data: { detail: 'timeout' } } } : {}) }).mockResolvedValueOnce({ request_id: 'R', receipts: [] })
    await body().get('form').trigger('submit'); await flushPromises()
    const sent = JSON.parse(JSON.stringify(api.receiveBatch.mock.calls[0]![0]))
    expect(body().find('fieldset[disabled]').exists()).toBe(true)
    await button('重试本次入库').trigger('click'); await flushPromises()
    expect(api.receiveBatch.mock.calls[1]![0]).toEqual(sent)
  })
  it('keeps drafts editable after a validation rejection and protects dirty dismissal', async () => {
    await openDialog(); await fill()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    await button('关闭').trigger('click'); expect(confirm).toHaveBeenCalled(); expect(wrapper!.emitted('close')).toBeUndefined()
    api.receiveBatch.mockRejectedValueOnce({ isAxiosError: true, response: { status: 422, data: { detail: '仓位资料已停用' } } })
    await body().get('form').trigger('submit'); await flushPromises()
    expect(body().find('fieldset[disabled]').exists()).toBe(false)
    expect(body().get<HTMLInputElement>('[aria-label="物料1明细1实收数量"]').element.value).toBe('0.125')
  })
})
