vi.mock('../workspaceApi',()=>import('./workspaceFixtures'))
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import CuttingMasterPage from '../CuttingMasterPage.vue'
import { createRouter, createMemoryHistory, RouterView } from 'vue-router'
import { cuttingApi, type MasterRecord } from '../api'

vi.mock('../api', async importOriginal => {
  const actual = await importOriginal<typeof import('../api')>()
  return { ...actual, cuttingApi: { access: vi.fn(), list: vi.fn(), save: vi.fn(), state: vi.fn(), versions: vi.fn() } }
})
const record: MasterRecord = { id: 'material-1', kind: 'material', factory_id: 'huakang-c', code: '001', version: 1, status: 'active', data: { name: '测试布', category: 'fabric', unit: '米', color: '蓝', specification: '', source_reference: '工程-M1' }, actor_id: 'synthetic', created_at: '2026-10-07T00:00:00Z', reason: '测试来源' }
let wrapper: VueWrapper
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(cuttingApi.access).mockResolvedValue({ enabled: true, schema_ready: true, permissions: ['read', 'master_write', 'bom_write', 'bom_publish'] })
  vi.mocked(cuttingApi.list).mockResolvedValue({ data: [], total: 0, page: 1, page_size: 50 })
})
afterEach(() => wrapper?.unmount())
async function open() { wrapper = mount(CuttingMasterPage); await flushPromises() }
function button(text: string) { const found = wrapper.findAll('button').find(b => b.text() === text); if (!found) throw new Error('Missing button: ' + text); return found }
async function input(label: string, value: string) {
  const found = wrapper.get('form.cutting-master-form').findAll('label').find(l => l.text() === label)
  if (!found) throw new Error('Missing field: ' + label)
  await found.get('input').setValue(value)
}
async function materialForm() {
  await button('物料与单位').trigger('click'); await flushPromises()
  await button('新增资料').trigger('click')
  await input('资料编码', '001'); await input('物料名称', '测试布'); await input('基本单位', '米')
  await input('权威物料编码／资料来源', '工程-M1'); await input('登记／修订原因', '核对资料')
}

describe('cutting master data', () => {
  it('does not let a slow linked-history request close a newly edited form',async()=>{
    let resolve!:(value:import('../api').MasterPage)=>void
    vi.mocked(cuttingApi.versions).mockReturnValueOnce(new Promise(r=>resolve=r))
    const router=createRouter({history:createMemoryHistory(),routes:[{path:'/master',component:CuttingMasterPage}]})
    await router.push('/master?master_id=material-1&master_version=1');await router.isReady()
    wrapper=mount(RouterView,{global:{plugins:[router]}});await flushPromises()
    await button('新增资料').trigger('click');await input('资料编码','DRAFT-KEEP')
    resolve({data:[record],total:1,page:1,page_size:50});await flushPromises()
    expect(wrapper.find('form.cutting-master-form').exists()).toBe(true)
    expect(wrapper.get('form.cutting-master-form').findAll('input').some(i=>(i.element as HTMLInputElement).value==='DRAFT-KEEP')).toBe(true)
    expect(cuttingApi.versions).toHaveBeenCalledTimes(1)
  })

  it('opens the requested older version page and responds to version-only links',async()=>{
    const latest={...record,version:101,reason:'当前资料'}
    vi.mocked(cuttingApi.versions).mockImplementation(async(_id,_page,focus)=>({data:[focus?{...record,version:focus,reason:`原始依据${focus}`} :latest],total:101,page:focus===1?3:focus?2:1,page_size:50}))
    const router=createRouter({history:createMemoryHistory(),routes:[{path:'/master',component:CuttingMasterPage}]})
    await router.push('/master?master_id=material-1&master_version=1');await router.isReady()
    wrapper=mount(RouterView,{global:{plugins:[router]}});await flushPromises()
    expect(cuttingApi.versions).toHaveBeenLastCalledWith('material-1',1,1)
    expect(wrapper.get('#cutting-master-version-1').attributes('open')).toBeDefined()
    expect(wrapper.text()).toContain('原始依据1')
    await router.push('/master?master_id=material-1&master_version=51');await flushPromises()
    expect(cuttingApi.versions).toHaveBeenLastCalledWith('material-1',1,51)
    expect(wrapper.get('#cutting-master-version-51').attributes('open')).toBeDefined()
    expect(wrapper.find('#cutting-master-version-1').exists()).toBe(false)
  })
  it('does not silently open current history when the requested version is invalid',async()=>{
    const router=createRouter({history:createMemoryHistory(),routes:[{path:'/master',component:CuttingMasterPage}]})
    await router.push('/master?master_id=material-1&master_version=bad');await router.isReady()
    wrapper=mount(RouterView,{global:{plugins:[router]}});await flushPromises()
    expect(wrapper.text()).toContain('指定资料版本无效')
    expect(cuttingApi.versions).not.toHaveBeenCalled()
  })
  it('pages only applied master filters and resets a submitted search to page one',async()=>{
    vi.mocked(cuttingApi.list).mockResolvedValue({data:[record],total:51,page:1,page_size:50})
    await open();await wrapper.get('input[maxlength="80"]').setValue('NEW')
    await button('下一页').trigger('click');await flushPromises()
    expect(cuttingApi.list).toHaveBeenLastCalledWith('bom',2,'')
    await wrapper.get('form').trigger('submit');await flushPromises()
    expect(cuttingApi.list).toHaveBeenLastCalledWith('bom',1,'NEW')
  })

  it('does not let a late linked-master response overwrite a newer route target',async()=>{
    let resolve!:(v:{data:MasterRecord[];total:number;page:number;page_size:number})=>void
    const newer={...record,id:'material-2',code:'NEW-002'}
    vi.mocked(cuttingApi.versions).mockReturnValueOnce(new Promise(r=>resolve=r)).mockResolvedValue({data:[newer],total:1,page:1,page_size:50})
    const router=createRouter({history:createMemoryHistory(),routes:[{path:'/master',component:CuttingMasterPage}]})
    await router.push('/master?master_id=material-1');await router.isReady()
    wrapper=mount(RouterView,{global:{plugins:[router]}});await flushPromises()
    await router.push('/master?master_id=material-2');await flushPromises()
    resolve({data:[record],total:1,page:1,page_size:50});await flushPromises()
    expect(wrapper.text()).toContain('NEW-002')
    expect(wrapper.text()).not.toContain('001 · 版本记录')
  })
  it('ignores old history success and failure after a newer request or close', async () => {
    vi.mocked(cuttingApi.list).mockResolvedValue({data:[record],total:1,page:1,page_size:50})
    await open()
    let oldResolve!: (value: import('../api').MasterPage)=>void
    let latestResolve!: (value: import('../api').MasterPage)=>void
    vi.mocked(cuttingApi.versions).mockImplementationOnce(()=>new Promise(r=>{oldResolve=r})).mockImplementationOnce(()=>new Promise(r=>{latestResolve=r}))
    await button('版本记录').trigger('click');await button('版本记录').trigger('click')
    oldResolve({data:[record],total:1,page:1,page_size:50});await flushPromises()
    expect(wrapper.text()).toContain('正在读取版本')
    const latest={...record,version:2,reason:'新的历史依据'}
    latestResolve({data:[latest],total:2,page:1,page_size:50});await flushPromises()
    expect(wrapper.text()).toContain('新的历史依据')
    let reject!: (error: unknown)=>void
    vi.mocked(cuttingApi.versions).mockImplementationOnce(()=>new Promise((_,r)=>{reject=r}))
    await button('版本记录').trigger('click');await button('关闭记录').trigger('click')
    reject({response:{data:{detail:'迟到的失败'}}});await flushPromises()
    expect(wrapper.text()).not.toContain('迟到的失败')
    expect(wrapper.text()).not.toContain('正在读取版本')
  })
  it('does not expose writes or fake empty data when disabled', async () => {
    vi.mocked(cuttingApi.access).mockResolvedValue({ enabled: false, schema_ready: false, permissions: ['master_write'] })
    await open()
    expect(wrapper.text()).toContain('基础资料尚未启用')
    expect(wrapper.text()).not.toContain('新增资料')
    expect(cuttingApi.list).not.toHaveBeenCalled()
  })
  it('denied access clears tables and write controls', async () => {
    vi.mocked(cuttingApi.access).mockRejectedValue({ response: { status: 403, data: { detail: '没有权限' } } })
    await open()
    expect(wrapper.get('[role="alert"]').text()).toContain('没有权限')
    expect(wrapper.find('table').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('新增资料')
  })
  it('read only user can inspect but cannot write or publish', async () => {
    vi.mocked(cuttingApi.access).mockResolvedValue({ enabled: true, schema_ready: true, permissions: ['read'] })
    vi.mocked(cuttingApi.list).mockResolvedValue({ data: [record], total: 1, page: 1, page_size: 50 })
    await open()
    expect(wrapper.text()).toContain('当前为只读')
    expect(wrapper.text()).toContain('版本记录')
    expect(wrapper.text()).not.toContain('新增资料')
    expect(wrapper.text()).not.toContain('修订草稿')
  })
  it('saves actual server data with explicit factory and source', async () => {
    vi.mocked(cuttingApi.save).mockResolvedValue(record)
    await open(); await materialForm()
    await wrapper.get('form.cutting-master-form').trigger('submit'); await flushPromises()
    expect(cuttingApi.save).toHaveBeenCalledWith(expect.objectContaining({ factory_id: 'huakang-c', expected_version: 0, code: '001', kind: 'material', data: expect.objectContaining({ unit: '米', source_reference: '工程-M1' }) }), undefined)
    expect(wrapper.text()).toContain('已保存 001，版本 V1')
    expect(wrapper.find('form.cutting-master-form').exists()).toBe(false)
  })
  it('freezes uncertain save and retries the exact original operation', async () => {
    vi.mocked(cuttingApi.save).mockRejectedValueOnce(new Error('timeout')).mockResolvedValueOnce(record)
    await open(); await materialForm()
    await wrapper.get('form.cutting-master-form').trigger('submit'); await flushPromises()
    expect(wrapper.text()).toContain('保存结果尚未确认')
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
    const original = vi.mocked(cuttingApi.save).mock.calls[0]![0]
    await button('重试原操作').trigger('click'); await flushPromises()
    expect(vi.mocked(cuttingApi.save).mock.calls[1]![0]).toEqual(original)
    expect(wrapper.text()).toContain('已保存 001')
  })
  it('keeps edits on version conflict without displaying success', async () => {
    vi.mocked(cuttingApi.save).mockRejectedValue({ response: { status: 409, data: { detail: '资料已更新，请重新读取后再保存' } } })
    await open(); await materialForm()
    await wrapper.get('form.cutting-master-form').trigger('submit'); await flushPromises()
    expect(wrapper.text()).toContain('资料已更新')
    expect(wrapper.find('form.cutting-master-form').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('已保存 001')
    expect(wrapper.text()).not.toContain('重试原操作')
  })
  it('BOM required-material setting remains independently editable', async () => {
    vi.mocked(cuttingApi.list).mockImplementation(async kind => ({ data: kind === 'material' ? [record] : [], total: kind === 'material' ? 1 : 0, page: 1, page_size: 50 }))
    await open(); await button('新增资料').trigger('click')
    await button('添加部件').trigger('click')
    await input('部件编码', 'P01'); await input('部件名称', '前片')
    await button('查询物料').trigger('click'); await flushPromises()
    await wrapper.get('select[aria-label="选择物料版本"]').setValue('material-1')
    await button('加入 BOM').trigger('click')
    expect(wrapper.text()).toContain('001 · 测试布 / V1')
    await wrapper.get('input[type="checkbox"]').setValue(false)
    await wrapper.get('form.cutting-master-form').trigger('submit'); await flushPromises()
    const sent = vi.mocked(cuttingApi.save).mock.calls[0]![0]
    expect(sent.kind).toBe('bom')
    expect(sent.data).toMatchObject({ requirements: [expect.objectContaining({ material_id: 'material-1', material_version: 1, required_for_cutting: false })] })
  })
  it('historical BOM labels use pinned material versions after a newer material search', async () => {
    const bom: MasterRecord = { ...record, id: 'bom-1', code: 'B01', kind: 'bom', status: 'published', material_references: { 'material-1:1': { code: '001', name: '原版蓝布' } }, data: { name: '产品', item_no: '0001', style: 'S1', color: '蓝', source_reference: '工程BOM', parts: [{ code: 'P1', name: '前片', pieces_per_set: 2 }], requirements: [{ material_id: 'material-1', material_version: 1, part_codes: ['P1'], quantity_per_set: '0.1', unit: '米', required_for_cutting: true, stage: '裁剪', note: '' }] } }
    vi.mocked(cuttingApi.list).mockImplementation(async kind => ({ data: kind === 'bom' ? [bom] : [{ ...record, version: 2, data: { ...record.data, name: '新版红布' } }], total: 1, page: 1, page_size: 50 }))
    vi.mocked(cuttingApi.versions).mockResolvedValue({ data: [bom], total: 1, page: 1, page_size: 50 })
    await open(); await button('修订草稿').trigger('click')
    expect(wrapper.text()).toContain('001 · 原版蓝布 / V1')
    await button('查询物料').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('001 · 原版蓝布 / V1')
    expect(wrapper.text()).not.toContain('新版红布 / V1')
    await button('版本记录').trigger('click'); await flushPromises()
    expect(wrapper.get('details').text()).toContain('原版蓝布 / V1')
  })
})
