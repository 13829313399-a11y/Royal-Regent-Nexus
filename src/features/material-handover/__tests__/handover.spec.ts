import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { reactive } from 'vue'
import { AxiosError } from 'axios'
import View from '../MaterialHandoverView.vue'
import type { HandoverDocument, HandoverWorkspace } from '@/api/materialHandover'

const api = vi.hoisted(() => ({ workspace: vi.fn(), list: vi.fn(), pendingDeliveries: vi.fn(), issuers: vi.fn(), detail: vi.fn(), purchaseSources: vi.fn(), post: vi.fn(), scan: vi.fn(), action: vi.fn(), save: vi.fn(), upload: vi.fn(), context: vi.fn(), file: vi.fn(), printFile: vi.fn() }))
vi.mock('../HandoverOriginalPrint.vue',async()=>{const {defineComponent,onMounted}=await import('vue');return{default:defineComponent({props:['file','token'],emits:['ready','failed'],setup(props,{emit}){onMounted(()=>emit('ready',props.token));return{}},template:'<section class="original-print-preview">原单加码打印预览</section>'})}})
vi.mock('@/api/materialHandover', () => ({ HANDOVER_FACTORY: 'huakang-c', handoverApi: () => api }))
const auth = reactive({ currentUser: { id: 'warehouse' }, authorizationVersion: 1 })
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))
let wrapper: VueWrapper | undefined
const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T
const fixture = (): HandoverDocument => ({ id: 'D1', factory_id: 'huakang-c', issuer_id: null, status: 'CONFIRMED', revision: 3,
  code_version: 1, code: 'MH1:D1:1', data: { kind: 'DELIVERY', supplier_id: 'SUP', source_no: 'DN-1', document_date: '2026-10-12', counterparty: '供应商',
    contract_no: '', production_no: '', product_no: '', note: '', lines: ['A','B'].map((id) => ({ id, source_line: '', item_code: id, item_name: '物料' + id, specification: '', color: '', quantity: '40', unit: '码', material_category: 'FABRIC', lot: 'LOT', roll_no: '', roll_quantities: '', contract_no: '', production_no: '', product_no: '', note: '' })) },
  warnings: [], evidence: {}, engine: 'xlsx', raw_text: '', file_name: '原件.xlsx', source_sha256: '', confirmed_at: '', created_at: '',
  progress: { A: { processed: '10', remaining: '30' }, B: { processed: '0', remaining: '40' } }, processing_status: 'PARTIAL', movements: [] })
const work = (): HandoverWorkspace => ({ factory_id: 'huakang-c', inventory: { revision: 8, locations: [{ id: 'BIN', warehouse: '一仓', code: 'A01', label: '一仓 A01', status: 'ACTIVE', revision: 1 }], stock: [], documents: [], permissions: { read: true, operate: true, correct: false, quality: false } }, materials: [], can_operate: true, can_manage: false })
async function open(external = false, path = '/?factory=huakang-c') {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: View, props: { external } }, { path: '/other', component: { template: '<div>其他页面</div>' } }, { path: '/modules/pmc-warehouse/fabric-warehouse/inventory', component: { template: '<div>台账</div>' } }] })
  await router.push(path); await router.isReady()
  wrapper = mount(RouterView, { global: { plugins: [router] } }); await flushPromises()
  return router
}
async function select() { await wrapper!.findAll('button').find(button => button.text().startsWith('DN-1'))!.trigger('click'); await flushPromises() }
async function click(text: string) { await wrapper!.findAll('button').find(button => button.text() === text)!.trigger('click'); await flushPromises() }
beforeEach(() => { vi.resetAllMocks(); auth.currentUser.id = 'warehouse'; auth.authorizationVersion = 1; api.workspace.mockResolvedValue(work()); api.list.mockResolvedValue({ items: [{ ...fixture(), line_count: 2 }], limit: 50, offset: 0 }); api.detail.mockResolvedValue(fixture()); api.issuers.mockResolvedValue([]); api.context.mockResolvedValue({ name: '供应商', kind: 'SUPPLIER', supplier_id: 'SUP' });api.file.mockResolvedValue(new Blob(['<svg/>'],{type:'image/svg+xml'}));vi.stubGlobal('URL',class extends URL { static createObjectURL(){return 'blob:test'};static revokeObjectURL(){} });vi.spyOn(window,'print').mockImplementation(()=>{}) })
afterEach(() => { wrapper?.unmount(); wrapper = undefined;vi.restoreAllMocks();vi.unstubAllGlobals() })

describe('material handover workflow', () => {
  it('lists exact missing fields while allowing an unchanged incomplete supplier draft to be handed to the warehouse', async () => {
    const row = fixture(); row.status = 'DRAFT'; row.code = ''; row.code_version = 0
    row.data.lines[0]!.item_code = ''; row.data.lines[0]!.quantity = ''; row.data.lines[1]!.unit = ''
    row.warnings = ['请核对印刷文字与手写内容']
    api.detail.mockResolvedValue(row)
    api.save.mockRejectedValueOnce(new AxiosError('连接断开')).mockResolvedValueOnce({ ...row, revision: 4 })
    await open(true, '/#key=public-test-key'); await select()
    expect(wrapper!.get('.draft-review').text()).toContain('第 1 行（物料A）：缺少物料编码；缺少数量')
    expect(wrapper!.get('.draft-review').text()).toContain('第 2 行（物料B）：缺少单位')
    expect(wrapper!.get('[aria-label="第1行物料编码"]').attributes('aria-invalid')).toBe('true')
    expect(wrapper!.findAll('button').find(b => b.text() === '确认并打印原单')!.attributes('disabled')).toBeDefined()
    expect(wrapper!.get('.recognition-notes').attributes('open')).toBeUndefined()
    await click('保存，交仓库补全')
    const frozen = clone(api.save.mock.calls[0]![1])
    await click('重试原提交')
    expect(api.save.mock.calls[1]![1]).toEqual(frozen)
    expect(frozen.data.lines[0].item_code).toBe('')
    expect(wrapper!.text()).toContain('已保存为待核对单据')
    expect(api.action).not.toHaveBeenCalled(); expect(api.printFile).not.toHaveBeenCalled(); expect(api.post).not.toHaveBeenCalled()
  })
  it('updates confirmation readiness as missing fields are filled and retains optional supplier data', async () => {
    const row = fixture(); row.status = 'DRAFT'; row.data.lines[0]!.quantity = '0'; row.data.lines[0]!.unit_price = '0'
    row.warnings = ['请核对印刷文字与手写内容']
    api.detail.mockResolvedValue(row)
    api.action.mockImplementation((_id, _kind, body) => Promise.resolve({ ...fixture(), data: body.data }))
    api.printFile.mockResolvedValue(new Blob(['pdf'], { type: 'application/pdf' }))
    await open(true, '/#key=public-test-key'); await select()
    expect(wrapper!.get('.draft-review').text()).toContain('数量须大于 0')
    expect(wrapper!.get('.lines').classes()).toContain('compact')
    await click('展开选填信息'); expect(wrapper!.get('.lines').classes()).not.toContain('compact')
    await click('收起选填信息')
    await wrapper!.get('[aria-label="第1行单据数量"]').setValue('0.000001')
    expect(wrapper!.get('.draft-review').text()).toContain('资料已齐全')
    expect(wrapper!.find('.document-confirmation input[type="checkbox"]').exists()).toBe(false)
    await click('确认并打印原单')
    expect(api.action.mock.calls[0]![2]).toMatchObject({ acknowledge_warnings: true, data: { lines: [expect.objectContaining({ quantity: '0.000001', unit_price: '0', lot: 'LOT' }), expect.anything()] } })
    expect(api.post).not.toHaveBeenCalled()
  })
  it('saves a cleared document date as an incomplete draft instead of an invalid date string', async () => {
    const row = fixture(); row.status = 'DRAFT'; api.detail.mockResolvedValue(row)
    api.save.mockImplementation((_id, body) => Promise.resolve({ ...row, revision: 4, data: body.data }))
    await open(true, '/#key=public-test-key'); await select()
    await wrapper!.get('[aria-label="单据日期"]').setValue('')
    await click('保存，交仓库补全')
    expect(api.save.mock.calls[0]![1].data.document_date).toBeNull()
    expect(wrapper!.get('.draft-review').text()).toContain('缺少单据日期')
  })
  it('locks the original supplier and purpose when warehouse staff complete a portal draft', async () => {
    const row = fixture(); row.status = 'DRAFT'; row.issuer_id = 'ISSUER-A'; api.detail.mockResolvedValue(row)
    await open(); await select()
    expect(wrapper!.get('.document-fields select').attributes('disabled')).toBeDefined()
    expect(wrapper!.find('[aria-label="制单供应商"]').exists()).toBe(false)
    expect(wrapper!.get('[aria-label="制单方"]').attributes('readonly')).toBeDefined()
    expect(wrapper!.get('[aria-label="第1行物料编码"]').attributes('disabled')).toBeUndefined()
  })
  it('opens the exact confirmed delivery from the dashboard without posting or scanning', async () => {
    api.pendingDeliveries.mockResolvedValue({ total: 1, items: [{ ...fixture(), line_count: 2 }], offset: 0, limit: 50 })
    await open(false, '/?factory=huakang-c&deliveries=pending&document=D1')
    expect(api.pendingDeliveries).toHaveBeenCalledWith(0)
    expect(api.list).not.toHaveBeenCalled()
    expect(api.detail).toHaveBeenCalledWith('D1')
    expect(wrapper!.text()).toContain('待入库送货单')
    expect(wrapper!.find('.posting-card').exists()).toBe(true)
    expect(api.post).not.toHaveBeenCalled()
  })
  beforeEach(() => { api.purchaseSources.mockResolvedValue({ document_revision: 3, lines: {} }) })
  const purchase = (id: string, revision = 4, count = 2) => ({ id, revision, receipt_count: count, remaining: '30', received: '70',
    order_no: 'PO-' + id, production_no: 'P001', plan_no: '', contract_no: 'MA-001', supplier: '供应商',
    item_code: 'A', item_name: '物料A', unit: '码', can_receive: true, suggested: true })
  it('links actual delivery quantity and freezes purchase progress versions on an unknown result', async () => {
    api.purchaseSources.mockResolvedValue({ document_revision: 3, lines: { A: [purchase('P1')] } })
    api.post.mockRejectedValueOnce(new AxiosError('网络断开')).mockResolvedValueOnce(fixture())
    await open(); await select()
    expect(wrapper!.get<HTMLSelectElement>('[aria-label="A采购待收明细"]').element.value).toBe('P1')
    expect(wrapper!.get('.posting-card').text()).toContain('采购尚欠 30 码')
    await wrapper!.get('.posting-row input[type=checkbox]').setValue(true)
    await wrapper!.get('[aria-label="本次A数量"]').setValue('7.5')
    await wrapper!.findAll('.posting-row label').find(label => label.text().startsWith('入库仓位'))!.get('input').setValue('一仓 A01')
    await click('确认本次实物收发')
    const frozen = clone(api.post.mock.calls[0]![1])
    expect(frozen.lines[0]).toMatchObject({ purchase_source_id: 'P1', expected_source_revision: 4, expected_receipt_count: 2, quantity: '7.5' })
    expect(wrapper!.get('.posting-card fieldset').attributes('disabled')).toBeDefined()
    await click('重试原提交')
    expect(api.post.mock.calls[1]![1]).toEqual(frozen)
  })
  it('requires a warehouse choice when multiple purchase lines match the same material', async () => {
    api.purchaseSources.mockResolvedValue({ document_revision: 3, lines: { A: [purchase('P1'), purchase('P2', 5, 3)] } })
    api.post.mockResolvedValue(fixture())
    await open(); await select(); await wrapper!.get('.posting-row input[type=checkbox]').setValue(true)
    await click('确认本次实物收发')
    expect(api.post).not.toHaveBeenCalled()
    expect(wrapper!.text()).toContain('请为本次实收选择对应采购待收明细')
    await wrapper!.get('[aria-label="A采购待收明细"]').setValue('P2')
    await click('确认本次实物收发')
    expect(api.post.mock.calls[0]![1].lines[0]).toMatchObject({ purchase_source_id: 'P2', expected_source_revision: 5, expected_receipt_count: 3 })
  })
  it('blocks posting until purchase progress is read and ignores a late response after authorization changes', async () => {
    let resolve!: (value: { document_revision: number; lines: { A: ReturnType<typeof purchase>[] } }) => void
    api.purchaseSources.mockReturnValue(new Promise(done => { resolve = done }))
    await open(); await select()
    expect(wrapper!.findAll('button').find(button => button.text() === '确认本次实物收发')!.attributes('disabled')).toBeDefined()
    auth.authorizationVersion++; await flushPromises()
    resolve({ document_revision: 3, lines: { A: [purchase('private')] } }); await flushPromises()
    expect(wrapper!.find('.posting-card').exists()).toBe(false)
    expect(wrapper!.text()).not.toContain('PO-private')
    expect(api.post).not.toHaveBeenCalled()
  })
  it('keeps actual receiving disabled after a purchase read failure until explicitly refreshed', async () => {
    api.purchaseSources.mockRejectedValueOnce(new AxiosError('网络断开')).mockResolvedValueOnce({ document_revision: 3, lines: { A: [purchase('P1')] } })
    await open(); await select()
    expect(wrapper!.findAll('button').find(button => button.text() === '确认本次实物收发')!.attributes('disabled')).toBeDefined()
    api.workspace.mockResolvedValue({ ...work(), inventory: { ...work().inventory, revision: 12 } })
    await click('刷新采购与库存进度'); await flushPromises()
    expect(wrapper!.findAll('button').find(button => button.text() === '确认本次实物收发')!.attributes('disabled')).toBeUndefined()
    expect(wrapper!.get<HTMLSelectElement>('[aria-label="A采购待收明细"]').element.value).toBe('P1')
    api.post.mockResolvedValue(fixture())
    await wrapper!.get('.posting-row input[type=checkbox]').setValue(true)
    await click('确认本次实物收发')
    expect(api.post.mock.calls[0]![1].expected_inventory_revision).toBe(12)
  })
  it('keeps a boxed return on the left and removes duplicate warehouse navigation', async () => {
    await open()
    expect(wrapper!.findAll('.handover-tabs button').map(button => button.text())).toEqual(['单据管理', '扫码收发'])
    expect(wrapper!.find('.handover-tabs a').exists()).toBe(false)
    expect(wrapper!.get('.handover-header > :first-child').classes()).toContain('handover-back')
    expect(wrapper!.get('.handover-back').attributes('href')).toBe('/modules/pmc-warehouse/fabric-warehouse/receipts?factory=huakang-c&view=pending')
    expect(wrapper!.text()).not.toContain('查看库存台账')
  })
  it('queries all matching documents and keeps the applied filters when loading more and refreshing', async () => {
    api.workspace.mockResolvedValue({ ...work(), suppliers: [{ id: 'SUP', kind: 'SUPPLIER', code: 'S1', name: '供应商', status: 'ACTIVE', revision: 1, data: {}, updated_at: '' }] })
    await open(); await select()
    await wrapper!.get('[aria-label="本次A数量"]').setValue('7')
    await wrapper!.get('[aria-label="搜索交接单据"]').setValue('  布A  ')
    api.list.mockResolvedValue({ items: [{ ...fixture(), line_count: 2 }], total: 2, limit: 1, offset: 0 })
    await wrapper!.get('[aria-label="筛选供应商"]').setValue('SUP'); await flushPromises()
    await wrapper!.get('[aria-label="筛选单据状态"]').setValue('CONFIRMED'); await flushPromises()
    expect(api.list).toHaveBeenLastCalledWith(0, { search: '布A', supplier_id: 'SUP', kind: 'ALL', status: 'CONFIRMED' })
    expect(wrapper!.get<HTMLInputElement>('[aria-label="本次A数量"]').element.value).toBe('7')
    api.list.mockResolvedValue({ items: [{ ...fixture(), id: 'D2', line_count: 2 }], total: 2, limit: 1, offset: 1 })
    await click('加载更早单据')
    expect(api.list).toHaveBeenLastCalledWith(1, { search: '布A', supplier_id: 'SUP', kind: 'ALL', status: 'CONFIRMED' })
    expect(wrapper!.findAll('.document-item')).toHaveLength(2)
    await click('刷新')
    expect(api.list).toHaveBeenLastCalledWith(0, expect.objectContaining({ supplier_id: 'SUP', status: 'CONFIRMED' }))
    await click('重置')
    expect(api.list).toHaveBeenLastCalledWith(0, { search: '', supplier_id: '', kind: 'ALL', status: 'ALL' })
  })
  it('clears the supplier filter for issue documents and gives a useful empty result', async () => {
    await open()
    api.list.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 })
    await wrapper!.get('[aria-label="筛选单据用途"]').setValue('ISSUE'); await flushPromises()
    expect(api.list).toHaveBeenLastCalledWith(0, expect.objectContaining({ supplier_id: '', kind: 'ISSUE' }))
    expect(wrapper!.get('[aria-label="筛选供应商"]').attributes('disabled')).toBeDefined()
    expect(wrapper!.text()).toContain('没有符合条件的单据')
  })
  it('opens a scanned document on submit without posting stock', async () => {
    api.scan.mockResolvedValue(fixture())
    await open(false, '/?factory=huakang-c&tab=scan')
    await wrapper!.get('[aria-label="扫描单据二维码"]').setValue(' MH1:D1:1 ')
    await wrapper!.get('.scan-card form').trigger('submit'); await flushPromises()
    expect(api.scan).toHaveBeenCalledWith('MH1:D1:1')
    expect(wrapper!.find('.posting-card').exists()).toBe(true)
    expect(api.post).not.toHaveBeenCalled()
  })
  it('posts only explicitly selected lines with the actual quantity and revisions', async () => {
    api.post.mockResolvedValue(fixture()); await open(); await select()
    expect(api.post).not.toHaveBeenCalled()
    await wrapper!.get('.posting-row input[type=checkbox]').setValue(true)
    await wrapper!.get('[aria-label="本次A数量"]').setValue('7.5')
    await wrapper!.get('[aria-label="A入库仓位"]').setValue('一仓 A01')
    await click('确认本次实物收发')
    const body = api.post.mock.calls[0]![1]
    expect(body.expected_revision).toBe(3); expect(body.expected_inventory_revision).toBe(8)
    expect(body.lines).toEqual([{ line_id: 'A', quantity: '7.5', batch_id: '', location_id: 'BIN', lot: 'LOT', roll_no: '' }])
  })
  it('freezes an unknown write outcome and retries exactly the same request', async () => {
    api.post.mockRejectedValueOnce(new AxiosError('网络断开')); api.post.mockResolvedValueOnce(fixture())
    await open(); await select(); await wrapper!.get('.posting-row input[type=checkbox]').setValue(true)
    await click('确认本次实物收发'); const first = clone(api.post.mock.calls[0]![1])
    expect(wrapper!.get('[aria-label="本次A数量"]').attributes('disabled')).toBeUndefined() // parent fieldset enforces locking
    expect(wrapper!.get('.posting-card fieldset').attributes('disabled')).toBeDefined()
    await click('重试原提交'); expect(api.post.mock.calls[1]![1]).toEqual(first)
  })
  it('saves reactive draft edits and guards unsaved navigation', async () => {
    const row = fixture(); row.status = 'DRAFT'; api.detail.mockResolvedValue(row)
    api.save.mockImplementation((_id, body) => Promise.resolve({ ...row, revision: 4, data: body.data }))
    const router = await open(); await select(); await wrapper!.get('[aria-label="第1行单据数量"]').setValue('19')
    expect(wrapper!.findAll('button').find(b => b.text() === '确认并打印原单')!.attributes('disabled')).toBeUndefined()
    await router.push('/other'); expect(router.currentRoute.value.path).toBe('/')
    await click('保存核对内容'); expect(api.save.mock.calls[0]![1].data.lines[0].quantity).toBe('19')
    await router.push('/other'); expect(router.currentRoute.value.path).toBe('/other')
  })
  it('clears private documents on authorization changes and ignores late responses', async () => {
    let resolve: (row: HandoverDocument) => void = () => {}
    api.detail.mockReturnValue(new Promise<HandoverDocument>(r => { resolve = r }))
    await open(); await wrapper!.findAll('button').find(button => button.text().startsWith('DN-1'))!.trigger('click')
    api.list.mockResolvedValue({ items: [], limit: 50, offset: 0 }); auth.authorizationVersion++; await flushPromises()
    resolve(fixture()); await flushPromises(); expect(wrapper!.find('.posting-card').exists()).toBe(false)
  })
  it('public preparation never requests stock or exposes posting controls', async () => {
    await open(true, '/#key=public-test-key'); await select()
    expect(api.workspace).not.toHaveBeenCalled(); expect(wrapper!.find('.posting-card').exists()).toBe(false)
    expect(api.purchaseSources).not.toHaveBeenCalled()
    expect(wrapper!.text()).not.toContain('制单方与链接')
    expect(wrapper!.find('[aria-label="筛选供应商"]').exists()).toBe(false)
    expect(wrapper!.find('.handover-back').exists()).toBe(false)
  })
  it('confirms edited supplier data and prepares printing in a single submission',async()=>{
    const row=fixture();row.status='DRAFT';api.detail.mockResolvedValue(row)
    api.action.mockImplementation((_id,_kind,body)=>Promise.resolve({...fixture(),data:body.data}))
    await open(true,'/#key=public-test-key');await select();await wrapper!.get('[aria-label="第1行单据数量"]').setValue('9')
    api.printFile.mockResolvedValue(new Blob(['pdf'],{type:'application/pdf'}))
    await wrapper!.get('[aria-label="第1行参考单价"]').setValue('2.3');await click('确认并打印原单')
    expect(api.save).not.toHaveBeenCalled();expect(api.action.mock.calls[0]![2].data.lines[0].quantity).toBe('9')
    expect(api.action.mock.calls[0]![2].data.lines[0].unit_price).toBe('2.3');expect(window.print).toHaveBeenCalledOnce()
    expect(api.printFile).toHaveBeenCalledWith('D1',3,'right')
    expect(wrapper!.get('.original-print-preview').text()).toContain('原单加码打印预览')
    expect(api.post).not.toHaveBeenCalled()
  })
  it('prepares the chosen corner and clears print copies when authorization changes',async()=>{
    api.printFile.mockResolvedValue(new Blob(['pdf'],{type:'application/pdf'}))
    await open();await select();await wrapper!.get('[aria-label="原单二维码位置"]').setValue('left')
    await click('原单加码打印');expect(api.printFile).toHaveBeenCalledWith('D1',3,'left')
    expect(wrapper!.find('.original-print-preview').exists()).toBe(true)
    auth.authorizationVersion++;await flushPromises()
    expect(wrapper!.find('.original-print-preview').exists()).toBe(false)
    expect(wrapper!.find('a[download$="-原单加码.pdf"]').exists()).toBe(false)
  })
  it('does not print a late PDF for a cleared account context',async()=>{
    let resolve!:(file:Blob)=>void
    api.printFile.mockReturnValue(new Promise<Blob>(done=>{resolve=done}))
    await open();await select();await wrapper!.findAll('button').find(b=>b.text()==='原单加码打印')!.trigger('click')
    auth.authorizationVersion++;await flushPromises();resolve(new Blob(['pdf'],{type:'application/pdf'}));await flushPromises()
    expect(window.print).not.toHaveBeenCalled();expect(wrapper!.find('.original-print-preview').exists()).toBe(false)
  })
})
