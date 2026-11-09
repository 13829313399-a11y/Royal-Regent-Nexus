import { mount, flushPromises, enableAutoUnmount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest'
import CasdonWorkbookTools from '../CasdonWorkbookTools.vue'
const api=vi.hoisted(()=>({preview:vi.fn(),export:vi.fn()}))
vi.mock('@/api/casdonWorkbook',()=>({casdonWorkbookApi:api}))
enableAutoUnmount(afterEach)
const row={id:'4',row:4,section:'active',contract:'8996',reference:'8996',product:'30050',customer:'NTI',quantity:'1000'}
const data={factory_id:'huadeng',customer_code:'casdon',fingerprint:'hash',rows:[row,{...row,id:'14',row:14,section:'shipped',reference:'OLD'}]}
beforeEach(()=>{vi.resetAllMocks();api.preview.mockResolvedValue(data)})
afterEach(()=>{vi.restoreAllMocks();vi.unstubAllGlobals()})
async function upload(w:ReturnType<typeof mount>,name='casdon.xlsx') {
  const input=w.get('input[type=file]')
  Object.defineProperty(input.element,'files',{value:[new File(['data'],name)],configurable:true})
  await input.trigger('change');await flushPromises()
}
function button(w:ReturnType<typeof mount>,label:string){return w.findAll('button').find(b=>b.text()===label)!}
describe('Casdon Excel tool',()=>{
  it('requires explicit row and reason confirmation; refreshes exported copy',async()=>{
    const create=vi.fn(()=> 'blob:casdon');vi.stubGlobal('URL',Object.assign(URL,{createObjectURL:create,revokeObjectURL:vi.fn()}))
    vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{})
    api.export.mockResolvedValue({blob:new Blob(['output']),name:'副本.xlsx',warningCount:1,auditId:'audit'})
    const w=mount(CasdonWorkbookTools,{props:{factoryId:'huadeng'}});await upload(w)
    expect(w.text()).not.toContain('OLD /')
    expect(button(w,'标记已走货').attributes('disabled')).toBeDefined()
    await w.get('input[type=checkbox]').setValue(true);await button(w,'标记已走货').trigger('click')
    expect(api.export).not.toHaveBeenCalled()
    expect(button(w,'确认并下载副本').attributes('disabled')).toBeDefined()
    await w.get('fieldset input').setValue('已核对出货');await button(w,'确认并下载副本').trigger('click');await flushPromises()
    expect(api.export).toHaveBeenCalledWith('huadeng',expect.any(File),'hash','ship',['4'],'已核对出货')
    expect(create).toHaveBeenCalledOnce();expect(api.preview).toHaveBeenCalledTimes(2)
    expect(w.text()).toContain('台账未改动');expect(w.text()).toContain('1行未找到唯一价格来源')
  })
  it('can cancel and switch to restore without retaining prior selections',async()=>{
    const w=mount(CasdonWorkbookTools,{props:{factoryId:'huadeng'}});await upload(w)
    await w.get('input[type=checkbox]').setValue(true);await button(w,'标记已走货').trigger('click')
    await button(w,'取消').trigger('click');expect(api.export).not.toHaveBeenCalled()
    await w.get('select').setValue('shipped')
    expect(button(w,'恢复未走货').attributes('disabled')).toBeDefined()
    expect(w.text()).toContain('OLD');expect(w.find('fieldset').exists()).toBe(false)
  })
  it('ignores stale previews when factory changes',async()=>{
    let resolve!:(value:typeof data)=>void
    api.preview.mockReturnValueOnce(new Promise(r=>{resolve=r}))
    const w=mount(CasdonWorkbookTools,{props:{factoryId:'huadeng'}})
    await upload(w);await w.setProps({factoryId:'huaxing'});resolve(data);await flushPromises()
    expect(w.find('table').exists()).toBe(false)
  })
  it('does not download an export after unmount',async()=>{
    let resolve!:(value:unknown)=>void
    api.export.mockReturnValueOnce(new Promise(r=>{resolve=r}))
    const create=vi.fn();vi.stubGlobal('URL',Object.assign(URL,{createObjectURL:create,revokeObjectURL:vi.fn()}))
    const w=mount(CasdonWorkbookTools,{props:{factoryId:'huadeng'}});await upload(w)
    await button(w,'补充金额栏并下载').trigger('click');w.unmount()
    resolve({blob:new Blob(['result']),name:'out.xlsx',warningCount:0,auditId:''});await flushPromises()
    expect(create).not.toHaveBeenCalled()
  })
  it('rejects wrong input and shows empty result',async()=>{
    const w=mount(CasdonWorkbookTools,{props:{factoryId:'huadeng'}});await upload(w,'bad.pdf')
    expect(api.preview).not.toHaveBeenCalled();expect(w.text()).toContain('请选择')
    api.preview.mockResolvedValue({...data,rows:[]});await upload(w)
    expect(w.text()).toContain('没有符合条件的订单')
  })
  it('rejects a preview from another factory',async()=>{
    api.preview.mockResolvedValue({...data,factory_id:'huaxing'})
    const w=mount(CasdonWorkbookTools,{props:{factoryId:'huadeng'}});await upload(w)
    expect(w.find('table').exists()).toBe(false)
    expect(w.text()).toContain('厂区或客户不一致')
  })
})
