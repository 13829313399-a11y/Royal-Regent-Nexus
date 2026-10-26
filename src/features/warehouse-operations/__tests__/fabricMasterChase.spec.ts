import { pendingFabricImports, pendingFabricMasterSaves } from '../pendingFabricRequests'
import { reactive } from 'vue'
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
const session = reactive({ currentUser: { id: 'keeper' }, authorizationVersion: 0 })
vi.mock('@/stores/auth', () => ({ useAuthStore: () => session }))
let wrapper: VueWrapper | undefined
const body = () => new DOMWrapper(document.body)
const button = (text: string) => body().findAll('button').find(item => item.text() === text)!
async function router() { const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] }); await router.push('/'); await router.isReady(); return router }
beforeEach(() => { pendingFabricImports.clear(); pendingFabricMasterSaves.clear(); session.currentUser = { id: 'keeper' }; session.authorizationVersion = 0; vi.clearAllMocks(); api.list.mockResolvedValue({ items: [], total: 0, can_manage: true }); api.candidates.mockResolvedValue([{ key: 'C1', kind: 'MATERIAL', code: '001', name: '白色布', revision: 0, status: 'DRAFT', data: { unit: '码' }, source_count: 2, variants: [], conflict: false }]) })
afterEach(() => { wrapper?.unmount(); wrapper = undefined; document.body.innerHTML = ''; vi.restoreAllMocks() })
async function openMaster(view = 'items') { wrapper = mount(Master, { props: { view }, attachTo: document.body, global: { plugins: [await router()] } }); await flushPromises() }
describe('fabric master data and chase confirmation', () => {
  it('keeps the zone dialog during routine session refresh but closes it on changed authority', async () => {
    api.list.mockResolvedValue({ items: [{ id: 'A01', code: 'A01', name: 'A01', kind: 'LOCATION', status: 'ACTIVE', revision: 1, updated_at: '', data: { warehouse: '布料仓' } }], can_manage: true })
    await openMaster('locations'); await button('设置分料区').trigger('click'); await flushPromises()
    await body().get('[aria-label="分料区"]').setValue('THREAD')
    await body().get('[aria-label="选择 布料仓 A01"]').setValue(true)
    api.list.mockClear()
    session.currentUser = { id: 'keeper' }; await flushPromises()
    expect(api.list).not.toHaveBeenCalled()
    expect(body().get('[aria-label="分料区"]').element).toHaveProperty('value', 'THREAD')
    expect(body().get('[aria-label="选择 布料仓 A01"]').element).toHaveProperty('checked', true)
    session.authorizationVersion++; await flushPromises()
    expect(body().find('[role=dialog]').exists()).toBe(false)
  })
  it('permits login recovery and reloads master data after the original in-flight write completes', async () => {
    const navigation = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/master', component: Master, props: { view: 'partners' } },
      { path: '/login', name: 'login', component: { template: '<div>login page</div>' } },
    ] })
    await navigation.push('/master'); await navigation.isReady()
    wrapper = mount({ template: '<router-view />' }, { attachTo: document.body, global: { plugins: [navigation] } })
    await flushPromises(); await button('新增资料').trigger('click')
    await body().get('[aria-label="供应商编号"]').setValue('SUP1')
    await body().get('[aria-label="资料名称"]').setValue('保存的供应商')
    let finish!: (value: unknown) => void
    api.save.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    await body().get('form.fabric-master-form').trigger('submit')
    await navigation.push('/login'); await flushPromises()
    expect(navigation.currentRoute.value.name).toBe('login')
    await navigation.push('/master'); await flushPromises()
    api.list.mockClear()
    const saved = { id: 'SUP1', code: 'SUP1', name: '保存的供应商', kind: 'SUPPLIER', status: 'ACTIVE', data: {} }
    api.list.mockResolvedValueOnce({ items: [saved], can_manage: true })
    finish(saved); await flushPromises()
    expect(api.list).toHaveBeenCalledOnce()
    expect(body().text()).toContain('保存的供应商')
  })
  it('clears supplier data and rejects late reads when authorization changes', async () => {
    let finish!: (value: unknown) => void
    api.list.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    await openMaster('partners')
    api.list.mockResolvedValue({ items: [], can_manage: false })
    session.authorizationVersion++; await flushPromises()
    finish({ items: [{ id: 'S1', kind: 'SUPPLIER', code: 'PRIVATE', name: '旧账号供应商', status: 'ACTIVE', data: {} }], can_manage: true })
    await flushPromises()
    expect(body().text()).not.toContain('旧账号供应商')
    expect(button('新增资料')).toBeUndefined()
  })
  it('retains the original unknown save without exposing it to another account', async () => {
    await openMaster('partners')
    await button('新增资料').trigger('click')
    await body().get('[aria-label="供应商编号"]').setValue('SUP1')
    await body().get('[aria-label="资料名称"]').setValue('原账号供应商')
    api.save.mockRejectedValueOnce(new Error('连接中断'))
    await body().get('form.fabric-master-form').trigger('submit'); await flushPromises()
    const original = api.save.mock.calls[0]![0]
    await button('关闭').trigger('click'); await flushPromises()
    expect(body().find('[role=dialog]').exists()).toBe(false)
    expect(button('核对原保存结果')).toBeDefined()
    session.currentUser = { id: 'other' }; await flushPromises()
    expect(body().find('[role=dialog]').exists()).toBe(false)
    expect(button('核对原保存结果')).toBeUndefined()
    session.currentUser = { id: 'keeper' }; await flushPromises()
    api.save.mockResolvedValueOnce({})
    await button('核对原保存结果').trigger('click'); await flushPromises()
    expect(api.save.mock.calls[1]![0]).toEqual(original)
  })
  it('suggests a candidate category without saving and accepts the staff correction', async () => {
    await openMaster()
    expect(api.candidates).toHaveBeenCalledWith('MATERIAL')
    expect(body().text()).toContain('采购物料自动归集')
    expect(api.save).not.toHaveBeenCalled()
    await button('核对并建档').trigger('click'); await flushPromises()
    expect(body().get<HTMLInputElement>('[aria-label="资料编码"]').element.value).toBe('001')
    expect(body().get<HTMLSelectElement>('[aria-label="物料分类"]').element.value).toBe('FABRIC')
    await body().get('[aria-label="资料启用状态"]').setValue('ACTIVE')
    expect(body().get('[aria-label="物料分类"]').attributes('required')).toBeDefined()
    await body().get('[aria-label="物料分类"]').setValue('ACCESSORY')
    api.save.mockResolvedValue({}); await body().get('form.fabric-master-form').trigger('submit'); await flushPromises()
    expect(api.save).toHaveBeenCalledWith(expect.objectContaining({ kind: 'MATERIAL', code: '001', status: 'ACTIVE', data: expect.objectContaining({ category: 'ACCESSORY', unit: '码' }) }))
  })
  it('leaves ambiguous units and conflicting candidates unclassified', async () => {
    api.candidates.mockResolvedValueOnce([{ key: 'C1', kind: 'MATERIAL', code: '001', name: '物料', data: { unit: '公斤' }, conflict: false, variants: [] }])
    await openMaster(); await button('核对并建档').trigger('click'); await flushPromises()
    expect(body().get<HTMLSelectElement>('[aria-label="物料分类"]').element.value).toBe('')
    expect(api.save).not.toHaveBeenCalled()
    await button('关闭').trigger('click'); await flushPromises()
    api.candidates.mockResolvedValueOnce([{ key: 'C2', kind: 'MATERIAL', code: '002', name: '有冲突', data: { unit: '码' }, conflict: true, variants: [{ name: '有冲突', unit: '码' }, { name: '有冲突', unit: 'Pcs' }] }])
    await button('刷新归集').trigger('click'); await flushPromises()
    await button('核对并建档').trigger('click'); await flushPromises()
    expect(body().get<HTMLSelectElement>('[aria-label="物料分类"]').element.value).toBe('')
  })
  it('suggests on new unit input without overwriting a manual classification', async () => {
    await openMaster(); await button('新增资料').trigger('click'); await flushPromises()
    await body().get('[aria-label="库存单位"]').setValue(' PCS ')
    expect(body().get<HTMLSelectElement>('[aria-label="物料分类"]').element.value).toBe('ACCESSORY')
    await body().get('[aria-label="库存单位"]').setValue('公斤')
    expect(body().get<HTMLSelectElement>('[aria-label="物料分类"]').element.value).toBe('')
    await body().get('[aria-label="物料分类"]').setValue('THREAD')
    await body().get('[aria-label="库存单位"]').setValue('码')
    expect(body().get<HTMLSelectElement>('[aria-label="物料分类"]').element.value).toBe('THREAD')
    expect(api.save).not.toHaveBeenCalled()
  })
  it('reports a candidate read failure as unknown and allows a refresh without saving', async () => {
    api.candidates.mockRejectedValueOnce(new Error('连接失败'))
    await openMaster()
    expect(body().get('[role="alert"]').text()).toContain('自动归集读取失败')
    expect(body().text()).not.toContain('暂无未建档的导入候选')
    expect(body().get('.fabric-material-views').text()).toContain('—')
    await button('刷新归集').trigger('click'); await flushPromises()
    expect(body().find('[role="alert"]').exists()).toBe(false)
    expect(body().text()).toContain('白色布')
    expect(api.save).not.toHaveBeenCalled()
  })
  it('does not show an empty candidate queue when the master read failed', async () => {
    api.list.mockRejectedValueOnce(new Error('连接失败'))
    await openMaster()
    expect(body().find('[role="alert"]').exists()).toBe(true)
    expect(body().get('.fabric-material-views').text()).toContain('—')
    expect(body().text()).not.toContain('暂无未建档的导入候选')
    expect(api.candidates).not.toHaveBeenCalled()
  })
  it('resets candidate pagination when searching for a material', async () => {
    api.candidates.mockResolvedValue(Array.from({ length: 25 }, (_, index) => ({ key: String(index), code: `M-${index}`, name: `材料${index}`, data: { unit: '码' }, source_count: 1, variants: [] })))
    await openMaster()
    await button('下一页候选').trigger('click')
    expect(body().text()).toContain('M-24')
    await body().get('[aria-label="基础资料关键字"]').setValue('M-24')
    expect(body().findAll('.fabric-candidate-grid article')).toHaveLength(1)
    expect(body().get('.fabric-candidate-grid').text()).toContain('M-24')
    expect(api.save).not.toHaveBeenCalled()
  })
  it('discards late material candidates after moving to supplier data', async () => {
    let resolve!: (value: unknown[]) => void
    api.candidates.mockReturnValueOnce(new Promise(done => { resolve = done }))
    await openMaster()
    await wrapper!.setProps({ view: 'partners' }); await flushPromises()
    resolve([{ key: 'old', code: 'OLD', name: '迟到物料', data: {}, variants: [] }]); await flushPromises()
    expect(body().text()).not.toContain('迟到物料')
    expect(body().text()).toContain('供应商资料')
    expect(api.save).not.toHaveBeenCalled()
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
    wrapper!.unmount(); await openMaster('partners'); await button('新增资料').trigger('click'); await flushPromises()
    expect(body().get('[role=dialog]').text()).toContain('每家供应商一个固定编号')
    await body().get('[aria-label="供应商编号"]').setValue('GYS001')
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
