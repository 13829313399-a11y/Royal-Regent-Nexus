import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import CuttingScheduleImport from '../CuttingScheduleImport.vue'
const api=vi.hoisted(()=>({preview:vi.fn(),confirm:vi.fn(),recover:vi.fn(),template:vi.fn()}))
vi.mock('../scheduleImportApi',()=>({scheduleImportApi:api}))
const parsed={file_name:'排期.xlsx',file_sha256:'a'.repeat(64),fingerprint:'b'.repeat(64),can_confirm:true,new_count:1,duplicate_count:0,sheets:[{sheet:'排期',status:'ready',header_row:1,row_count:1,message:'已识别七列表头'}],rows:[{sheet:'排期',row:2,data:{customer_name:'INDEX',reference_no:'TEST-01',product_no:'0012',product_name_zh:'测试产品',quantity:'480',unit:'PCS',requested_ship_date:'2026-11-03'},errors:[],status:'new',line_id:null}]}
const result={batch_id:'batch-1',file_name:'排期.xlsx',file_sha256:'a'.repeat(64),created:1,skipped:0,rows:[{line_id:'line-1',sheet:'排期',row:2,reference_no:'TEST-01',product_no:'0012',status:'new',version:1}]}
function button(w:ReturnType<typeof mount>,text:string){return w.findAll('button').find(b=>b.text()===text)!}
async function setup(){
  const w=mount(CuttingScheduleImport,{global:{stubs:{RouterLink:RouterLinkStub}}})
  await button(w,'排期 Excel 导入').trigger('click')
  const input=w.find<HTMLInputElement>('input[type=file]'),file=new File(['test'],'排期.xlsx')
  Object.defineProperty(input.element,'files',{value:[file],configurable:true});await input.trigger('change')
  await button(w,'读取导入预览').trigger('click');await flushPromises()
  return w
}
async function confirm(w:ReturnType<typeof mount>){await w.find('textarea').setValue('合成排期已核对');await w.find('input[type=checkbox]').setValue(true);await button(w,'确认导入并送裁床待接单').trigger('click');await flushPromises()}
beforeEach(()=>{vi.clearAllMocks();api.preview.mockResolvedValue(parsed);api.confirm.mockResolvedValue(result);api.recover.mockResolvedValue({state:'committed',result})})
describe('controlled schedule intake',()=>{
  it('requires preview and acknowledgement, exposes source rows and a result order link',async()=>{
    const w=await setup();expect(w.text()).toContain('480 PCS');expect(button(w,'确认导入并送裁床待接单').attributes('disabled')).toBeDefined()
    await confirm(w);expect(api.confirm).toHaveBeenCalledTimes(1);expect(w.text()).toContain('新增 1 条')
    expect(w.findComponent(RouterLinkStub).props('to').query.line_id).toBe('line-1');expect(w.emitted('imported')).toHaveLength(1);w.unmount()
  })
  it('does not enable confirmation for file conflicts',async()=>{
    api.preview.mockResolvedValue({...parsed,can_confirm:false,rows:[{...parsed.rows[0],status:'conflict',errors:['已有订单冲突']}]})
    const w=await setup();await w.find('textarea').setValue('仍需核对原单');await w.find('input[type=checkbox]').setValue(true)
    expect(button(w,'确认导入并送裁床待接单').attributes('disabled')).toBeDefined();expect(w.text()).toContain('不会覆盖原订单');w.unmount()
  })
  it('requires a fresh preview and acknowledgement after a known conflict, preserving file and reason',async()=>{
    api.confirm.mockRejectedValueOnce({response:{status:409,data:{detail:'订单来源冲突，请重新预览'}}})
    const w=await setup();await confirm(w)
    expect(w.text()).toContain('原预览已失效')
    expect(w.find('input[type=checkbox]').exists()).toBe(false)
    expect(w.findAll('button').some(b=>b.text()==='确认导入并送裁床待接单')).toBe(false)
    expect(w.find('input[type=file]').attributes('disabled')).toBeUndefined()
    expect(button(w,'读取导入预览').attributes('disabled')).toBeUndefined()
    await button(w,'读取导入预览').trigger('click');await flushPromises()
    expect(api.preview.mock.calls[1]?.[0]).toBe(api.preview.mock.calls[0]?.[0])
    expect(w.find<HTMLTextAreaElement>('textarea').element.value).toBe('合成排期已核对')
    expect(w.find<HTMLInputElement>('input[type=checkbox]').element.checked).toBe(false)
    expect(button(w,'确认导入并送裁床待接单').attributes('disabled')).toBeDefined()
    await confirm(w)
    expect(api.confirm.mock.calls[1]?.[1].operation_id).not.toBe(api.confirm.mock.calls[0]?.[1].operation_id)
    expect(w.text()).toContain('导入完成');w.unmount()
  })
  it('shows every worksheet and refuses a blocked sheet even if can_confirm is inconsistent',async()=>{
    api.preview.mockResolvedValue({...parsed,sheets:[...parsed.sheets,{sheet:'缺列排期',status:'blocked',header_row:null,row_count:0,message:'缺少：单位，请整理完整七列'}]})
    const w=await setup();await w.find('textarea').setValue('合成排期已核对');await w.find('input[type=checkbox]').setValue(true)
    expect(w.text()).toContain('缺列排期');expect(w.text()).toContain('缺少：单位')
    expect(button(w,'确认导入并送裁床待接单').attributes('disabled')).toBeDefined()
    expect(api.confirm).not.toHaveBeenCalled();w.unmount()
  })
  it('fails closed when an old server provides no worksheet coverage',async()=>{
    api.preview.mockResolvedValue({...parsed,sheets:undefined})
    const w=await setup();await w.find('textarea').setValue('合成排期已核对');await w.find('input[type=checkbox]').setValue(true)
    expect(w.text()).toContain('未提供工作表核对结果')
    expect(button(w,'确认导入并送裁床待接单').attributes('disabled')).toBeDefined();w.unmount()
  })
  it('keeps the exact file and operation after unknown response and later rejection until recovery',async()=>{
    api.confirm.mockRejectedValueOnce(new Error('offline')).mockRejectedValueOnce({response:{status:409,data:{detail:'版本冲突'}}})
    const w=await setup();await confirm(w);expect(w.text()).toContain('结果尚未确认')
    expect(w.find('input[type=file]').attributes('disabled')).toBeDefined()
    await button(w,'重试原导入').trigger('click');await flushPromises()
    expect(api.confirm.mock.calls[1]?.[0]).toBe(api.confirm.mock.calls[0]?.[0]);expect(api.confirm.mock.calls[1]?.[1]).toBe(api.confirm.mock.calls[0]?.[1])
    expect(w.find('input[type=file]').attributes('disabled')).toBeDefined()
    await button(w,'恢复核对原操作').trigger('click');await flushPromises();expect(w.text()).toContain('导入完成');expect(w.emitted('imported')).toHaveLength(1);w.unmount()
  })
  it('fenced unexecuted recovery restores input instead of silently submitting again',async()=>{
    api.confirm.mockRejectedValueOnce(new Error('offline'));api.recover.mockResolvedValue({state:'abandoned'})
    const w=await setup();await confirm(w);await button(w,'恢复核对原操作').trigger('click');await flushPromises()
    expect(w.text()).toContain('已安全终止');expect(api.confirm).toHaveBeenCalledTimes(1);expect(w.find('input[type=file]').attributes('disabled')).toBeUndefined()
    expect(w.find('input[type=checkbox]').exists()).toBe(false)
    expect(w.findAll('button').some(b=>b.text()==='确认导入并送裁床待接单')).toBe(false);w.unmount()
  })
})
