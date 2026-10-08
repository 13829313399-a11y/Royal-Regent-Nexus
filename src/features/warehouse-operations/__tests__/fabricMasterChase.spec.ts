import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DOMWrapper, flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import Master from '../FabricMasterWorkspace.vue'
import Chase from '../FabricChaseDialog.vue'
import Filters from '../FabricPurchaseFilters.vue'
import type { PurchaseDetail } from '@/api/fabricProcurement'
import type { PurchaseFilters } from '@/api/fabricProcurement'
const api = vi.hoisted(() => ({ list: vi.fn(), candidates: vi.fn(), save: vi.fn(), history: vi.fn() }))
const procurement = vi.hoisted(() => ({ resolveChase: vi.fn() }))
vi.mock('@/api/fabricMaster', () => ({ fabricMasterApi: api }))
vi.mock('@/api/fabricProcurement', () => ({ fabricProcurementApi: procurement }))
let wrapper: VueWrapper | undefined
const body = () => new DOMWrapper(document.body)
const button = (text: string) => body().findAll('button').find(item => item.text() === text)!
async function router() { const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] }); await router.push('/'); await router.isReady(); return router }
beforeEach(() => { vi.clearAllMocks(); api.list.mockResolvedValue({ items: [], total: 0, can_manage: true }); api.candidates.mockResolvedValue([{ key: 'C1', kind: 'MATERIAL', code: '001', name: '白色布', revision: 0, status: 'DRAFT', data: { unit: '码' }, source_count: 2, variants: [], conflict: false }]) })
afterEach(() => { wrapper?.unmount(); wrapper = undefined; document.body.innerHTML = ''; vi.restoreAllMocks() })
async function openMaster() { wrapper = mount(Master, { props: { view: 'items' }, attachTo: document.body, global: { plugins: [await router()] } }); await flushPromises() }
describe('fabric master data and chase confirmation', () => {
  it('opens an imported candidate without guessing category or saving until explicitly completed', async () => {
    await openMaster(); await button('查看导入候选').trigger('click'); await flushPromises()
    expect(api.save).not.toHaveBeenCalled()
    await button('补齐资料').trigger('click'); await flushPromises()
    expect(body().get<HTMLInputElement>('[aria-label="资料编码"]').element.value).toBe('001')
    expect(body().get<HTMLSelectElement>('[aria-label="物料分类"]').element.value).toBe('')
    await body().get('[aria-label="资料启用状态"]').setValue('ACTIVE')
    expect(body().get('[aria-label="物料分类"]').attributes('required')).toBeDefined()
    await body().get('[aria-label="物料分类"]').setValue('FABRIC')
    api.save.mockResolvedValue({}); await body().get('form.fabric-master-form').trigger('submit'); await flushPromises()
    expect(api.save).toHaveBeenCalledWith(expect.objectContaining({ kind: 'MATERIAL', code: '001', status: 'ACTIVE', data: expect.objectContaining({ category: 'FABRIC', unit: '码' }) }))
  })
  it('freezes master payload after unknown network result and keeps the same UUID on retry', async () => {
    await openMaster(); await button('新增资料').trigger('click'); await flushPromises()
    await body().get('[aria-label="资料编码"]').setValue('001'); await body().get('[aria-label="资料名称"]').setValue('白色布')
    api.save.mockRejectedValueOnce({ isAxiosError: true, message: 'network' }).mockResolvedValueOnce({})
    await body().get('form.fabric-master-form').trigger('submit'); await flushPromises()
    const payload = JSON.parse(JSON.stringify(api.save.mock.calls[0]![0]))
    expect(body().find('fieldset[disabled]').exists()).toBe(true)
    await button('重试保存').trigger('click'); await flushPromises()
    expect(api.save.mock.calls[1]![0]).toEqual(payload)
  })
  it('hides master creation from read-only accounts and protects unsaved edits', async () => {
    api.list.mockResolvedValueOnce({ items: [], total: 0, can_manage: false }); await openMaster()
    expect(body().findAll('button').some(item => item.text() === '新增资料')).toBe(false)
    wrapper!.unmount(); await openMaster(); await button('新增资料').trigger('click'); await flushPromises()
    await body().get('[aria-label="资料编码"]').setValue('001')
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    await button('关闭').trigger('click'); expect(confirm).toHaveBeenCalled(); expect(body().find('[role=dialog]').exists()).toBe(true)
  })
  it('shows the original chase equation and confirms only the start quantity, without posting stock', async () => {
    const source = { id: 'L1', revision: 2, receipt_count: 1, warehouse_received_quantity: '10', can_review: true, facts: { order_no: 'PO1', material_name: '白色布', supplier: '供应商', unit: '码' } } as PurchaseDetail
    wrapper = mount(Chase, { props: { source }, attachTo: document.body, global: { plugins: [await router()] } }); await flushPromises()
    await body().get('[aria-label="起始待收数量"]').setValue('37'); await body().get('[aria-label="起始待收核对依据"]').setValue('采购确认原始欠37')
    expect(body().get('.fabric-chase-equation').text()).toContain('37 − 10 = 27 码')
    procurement.resolveChase.mockResolvedValue({ stock_posted: false }); await body().get('form').trigger('submit'); await flushPromises()
    expect(procurement.resolveChase).toHaveBeenCalledWith('L1', expect.objectContaining({ expected_source_revision: 2, expected_receipt_count: 1, expected_resolution_revision: 0, starting_quantity: '37', confirmed_start: true }))
    expect(wrapper.emitted('saved')).toHaveLength(1)
  })
  it('offers quantity sorting only after selecting a unit and resets it when unit clears', async () => {
    wrapper = mount(Filters, { props: { modelValue: { unit: '', sort: 'OVERDUE' }, view: 'OUTSTANDING', search: '', busy: false, pending: true, options: { suppliers: ['供应商'], units: ['码'] }, 'onUpdate:modelValue': value => wrapper!.setProps({ modelValue: value }) } })
    expect(wrapper.get('option[value="QUANTITY_DESC"]').attributes('disabled')).toBeDefined()
    await wrapper.setProps({ modelValue: { unit: '码', sort: 'QUANTITY_DESC' } })
    expect(wrapper.get('option[value="QUANTITY_DESC"]').attributes('disabled')).toBeUndefined()
    const model = (wrapper.props() as { modelValue: PurchaseFilters }).modelValue
    await wrapper.setProps({ modelValue: { ...model, unit: '' } }); await flushPromises()
    expect((wrapper.props() as { modelValue: PurchaseFilters }).modelValue.sort).toBe('OVERDUE')
  })
})
