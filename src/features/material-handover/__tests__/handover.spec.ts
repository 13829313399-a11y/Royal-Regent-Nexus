import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { reactive } from 'vue'
import { AxiosError } from 'axios'
import View from '../MaterialHandoverView.vue'
import type { HandoverDocument, HandoverWorkspace } from '@/api/materialHandover'

const api = vi.hoisted(() => ({ workspace: vi.fn(), list: vi.fn(), issuers: vi.fn(), detail: vi.fn(), post: vi.fn(), action: vi.fn(), save: vi.fn(), upload: vi.fn(), context: vi.fn(), file: vi.fn(), printFile: vi.fn() }))
vi.mock('../HandoverOriginalPrint.vue',async()=>{const {defineComponent,onMounted}=await import('vue');return{default:defineComponent({props:['file','token'],emits:['ready','failed'],setup(props,{emit}){onMounted(()=>emit('ready',props.token));return{}},template:'<section class="original-print-preview">原单加码打印预览</section>'})}})
vi.mock('@/api/materialHandover', () => ({ HANDOVER_FACTORY: 'huakang-c', handoverApi: () => api }))
const auth = reactive({ currentUser: { id: 'warehouse' }, authorizationVersion: 1 })
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))
let wrapper: VueWrapper | undefined
const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T
const fixture = (): HandoverDocument => ({ id: 'D1', factory_id: 'huakang-c', issuer_id: null, status: 'CONFIRMED', revision: 3,
  code_version: 1, code: 'MH1:D1:1', data: { kind: 'DELIVERY', source_no: 'DN-1', document_date: '2026-10-12', counterparty: '供应商',
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
  it('sends internal month reconciliation to the warehouse closing workspace', async () => {
    await open()
    expect(wrapper!.findAll('.handover-tabs button').map(button => button.text())).not.toContain('月度数量对账')
    expect(wrapper!.get('.handover-tabs a').attributes('href')).toBe('/modules/pmc-warehouse/fabric-warehouse/closing?factory=huakang-c&view=monthly')
  })
  it('posts only explicitly selected lines with the actual quantity and revisions', async () => {
    api.post.mockResolvedValue(fixture()); await open(); await select()
    expect(api.post).not.toHaveBeenCalled()
    await wrapper!.get('.posting-row input[type=checkbox]').setValue(true)
    await wrapper!.get('[aria-label="本次A数量"]').setValue('7.5')
    await wrapper!.get('.posting-row select').setValue('BIN')
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
    expect(wrapper!.text()).not.toContain('制单方与链接')
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
