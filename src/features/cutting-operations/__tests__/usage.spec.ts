import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView, type Router } from 'vue-router'
import CuttingMaterialUsage from '../CuttingMaterialUsage.vue'
import { usageApi, type UsageLedger } from '../usageApi'
import { subtractQuantities } from '../quantityMath'
vi.mock('../usageApi',()=>({usageApi:{read:vi.fn(),post:vi.fn(),recover:vi.fn(),balance:vi.fn()}}))
const ledger:UsageLedger={revision:3,issues:[{issue_id:'i1',context:{order_no:'O1',task_id:'t1',task_name:'裁剪任务',resource_name:'本厂裁床',execution:'internal',plan_version:2,bom_version:1,row:0,mapping_basis:'规格对应',cutting_material:{code:'M1',name:'蓝布',unit:'米',category:'fabric',specification:'A',color:'蓝',source_reference:'工程'},warehouse_material:{id:'m',code:'M',name:'蓝布',revision:1,unit:'米',category:'FABRIC',spec:'A',color:'蓝'},root_batch_id:'b1',unit:'米',item_code:'M',item_name:'蓝布',lot:'LOT-1',roll_no:'1',location:'A01'},reversed:false,issued_quantity:'4',received_quantity:'4',returned_quantity:'0',consumed_quantity:'0',loss_quantity:'0',remaining_quantity:'4'}],documents:[],pending_pricing:0,amounts:{}}
let wrapper:VueWrapper,router:Router
const clone=<T,>(value:T):T=>JSON.parse(JSON.stringify(value))
function button(name:string){const element=wrapper.findAll('button').find(b=>b.text()===name);if(!element)throw new Error('Missing '+name);return element}
function field(name:string){return wrapper.findAll('label').find(l=>l.text().startsWith(name))!.get('input,select,textarea')}
async function open(withCosts=false,permissions=['read','usage_write','usage_review','cost_read','cost_write']){
  router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:CuttingMaterialUsage,props:{lineId:'l1',permissions,withCosts}},{path:'/away',component:{template:'<div>离开</div>'}}]})
  await router.push('/');await router.isReady();wrapper=mount(RouterView,{global:{plugins:[router]}});await flushPromises()
}
async function fill(){await button('登记耗用').trigger('click');await field('本次实际正常耗用').setValue('2');await field('本次裁剪损耗').setValue('0.5');await field('本次盘余').setValue('1.5');await field('耗用、损耗').setValue('实际裁剪及现场盘余核对')}
const hint={day:'2026-10-10',warehouse_cutoff:5,received_quantity:'4',returned_quantity:'0',consumed_quantity:'0',loss_quantity:'0',available_quantity:'4',same_day_document_ids:[],later_documents:[],revision:3}
beforeEach(()=>{vi.resetAllMocks();vi.spyOn(window,'confirm').mockReturnValue(false);vi.mocked(usageApi.read).mockResolvedValue(clone(ledger));vi.mocked(usageApi.post).mockResolvedValue({id:'u1'});vi.mocked(usageApi.balance).mockResolvedValue(hint)})
afterEach(()=>{wrapper?.unmount();vi.restoreAllMocks()})
describe('P3b custody and cost editor',()=>{
  it('shows a dated balance and exact count difference without changing loss',async()=>{
    await open();await fill();await flushPromises()
    expect(wrapper.get('[aria-label="业务日期余额提示"]').text()).toContain('账面应余 1.5')
    expect(wrapper.text()).toContain('盘余减账面差额 0')
    await field('本次盘余').setValue('1.4');expect(wrapper.text()).toContain('盘余减账面差额 -0.1')
    expect(field('本次裁剪损耗').element).toHaveProperty('value','0.5')
    expect(subtractQuantities('999999999999.999999','999999999999.999998')).toBe('0.000001')
  })
  it('ignores an older balance response after the business date changes',async()=>{
    await open();await fill();await flushPromises()
    let resolve!:(value:typeof hint)=>void
    vi.mocked(usageApi.balance).mockReturnValueOnce(new Promise(r=>resolve=r)).mockResolvedValueOnce({...hint,day:'2026-10-12',available_quantity:'2'})
    await field('业务日期').setValue('2026-10-11');await field('业务日期').setValue('2026-10-12');await flushPromises()
    resolve({...hint,day:'2026-10-11',available_quantity:'999'});await flushPromises()
    expect(wrapper.get('[aria-label="业务日期余额提示"]').text()).toContain('2026-10-12')
    expect(wrapper.get('[aria-label="业务日期余额提示"]').text()).not.toContain('999')
  })
  it('corrects with the original date and issue, preserving replacement links',async()=>{
    const value=clone(ledger)
    value.documents=[{id:'u-old',voided:false,reviewed:false,entry:{day:'2026-10-10',issue_id:'i1',consumed_quantity:'2',loss_quantity:'0.5',counted_remaining:'1.5'},context:value.issues[0]!.context,actor:'文员',created_at:'2026-10-10',reason:'原依据',history:[],replaces_document_id:'u-earlier',warehouse_cutoff:5}]
    vi.mocked(usageApi.read).mockResolvedValue(value)
    await open();expect(wrapper.text()).toContain('替代原单：u-earlier');await button('更正原耗用单').trigger('click');await flushPromises()
    expect(field('业务日期').attributes('readonly')).toBeDefined()
    expect(usageApi.balance).toHaveBeenLastCalledWith('l1','i1','2026-10-10','u-old')
    await field('本次实际正常耗用').setValue('2.25');await field('本次盘余').setValue('1.25');await field('操作原因').setValue('核对原耗用单更正')
    await wrapper.get('form').trigger('submit');await flushPromises()
    expect(usageApi.post).toHaveBeenCalledWith('l1','correct',expect.objectContaining({document_id:'u-old',issue_id:'i1',day:'2026-10-10',consumed_quantity:'2.25',counted_remaining:'1.25'}))
  })
  it('renders batch identity and business date for every historical cost',async()=>{
    const value=clone(ledger)
    value.price_history=[{version:7,actor:'采购',date:'2026-10-12',reason:'价格更正',data:{context:value.issues[0]!.context,entry:{day:'2026-10-11',unit_cost:'3',currency:'CNY',price_reference:'成本凭证',issue_id:'i1'}}}]
    vi.mocked(usageApi.read).mockResolvedValue(value);await open(true)
    expect(wrapper.text()).toContain('原批次 b1');expect(wrapper.text()).toContain('业务日期 2026-10-11');expect(wrapper.text()).toContain('关联实发 i1')
  })
  it('reloads the date balance after reauthentication without dropping the draft',async()=>{
    await open();vi.mocked(usageApi.balance).mockRejectedValueOnce({response:{status:401}})
    await button('登记耗用').trigger('click');await flushPromises();expect(wrapper.text()).toContain('登录已失效')
    await button('登录后继续读取').trigger('click');await flushPromises()
    expect(wrapper.find('form').exists()).toBe(true)
    expect(wrapper.find('[aria-label="业务日期余额提示"]').exists()).toBe(true)
  })
  it('posts real use/loss/count separately against the original issue without inventing price',async()=>{
    await open();await fill();await wrapper.get('form').trigger('submit');await flushPromises()
    expect(usageApi.read).toHaveBeenCalledWith('l1',false)
    expect(usageApi.post).toHaveBeenCalledWith('l1','post',expect.objectContaining({expected_version:3,issue_id:'i1',consumed_quantity:'2',loss_quantity:'0.5',counted_remaining:'1.5'}))
    expect(wrapper.text()).not.toContain('确认批次成本')
  })
  it('requires explicit currency and cost evidence for the original batch',async()=>{
    await open(true);await button('确认批次成本').trigger('click')
    expect(field('币种').element).toHaveProperty('value','')
    await field('原批次实际单位成本').setValue('0');await field('币种').setValue('HKD');await field('成本凭据').setValue('客户零成本供料核定');await field('操作原因').setValue('采购核对原批次凭证')
    await wrapper.get('form').trigger('submit');await flushPromises()
    expect(usageApi.post).toHaveBeenCalledWith('l1','price',expect.objectContaining({unit_cost:'0',currency:'HKD',price_reference:'客户零成本供料核定'}))
  })
  it.each([401,403,409])('preserves the original uncertain operation through retry %s',async status=>{
    await open();await fill();vi.mocked(usageApi.post).mockRejectedValueOnce(new Error('timeout')).mockRejectedValueOnce({response:{status}}).mockResolvedValueOnce({})
    await wrapper.get('form').trigger('submit');await flushPromises();const original=vi.mocked(usageApi.post).mock.calls[0]
    await button('重试耗用／成本原操作').trigger('click');await flushPromises();await router.push('/away');expect(router.currentRoute.value.path).toBe('/')
    await button('重试耗用／成本原操作').trigger('click');await flushPromises();expect(vi.mocked(usageApi.post).mock.calls[2]).toEqual(original)
  })
  it('refreshes a definitely rejected draft without dropping its use or count',async()=>{
    await open();await fill();vi.mocked(usageApi.post).mockRejectedValueOnce({response:{status:409}});await wrapper.get('form').trigger('submit');await flushPromises()
    vi.mocked(usageApi.read).mockResolvedValue({...clone(ledger),revision:7})
    await button('保留填写并刷新耗用版本').trigger('click');await flushPromises();expect(field('本次盘余').element).toHaveProperty('value','1.5')
    await wrapper.get('form').trigger('submit');await flushPromises();expect(vi.mocked(usageApi.post).mock.calls[1]?.[2].expected_version).toBe(7)
  })
  it('fences an abandoned operation while preserving the draft and unload guard',async()=>{
    await open();await fill();vi.mocked(usageApi.post).mockRejectedValueOnce(new Error('timeout'));await wrapper.get('form').trigger('submit');await flushPromises()
    vi.mocked(usageApi.recover).mockResolvedValue({state:'abandoned'});await button('核对耗用／成本保存结果').trigger('click');await flushPromises()
    expect(field('本次实际正常耗用').element).toHaveProperty('value','2')
    const event=new Event('beforeunload',{cancelable:true});window.dispatchEvent(event);expect(event.defaultPrevented).toBe(true)
  })
  it('hides write actions from read-only accounts and exposes unavailable service as an error',async()=>{
    await open(false,['read']);expect(wrapper.findAll('button').some(b=>b.text()==='登记耗用')).toBe(false)
    vi.mocked(usageApi.read).mockRejectedValueOnce({response:{status:503,data:{detail:'P3b迁移未完成'}}})
    await button('刷新耗用与余料').trigger('click');await flushPromises();expect(wrapper.get('[role="alert"]').text()).toContain('P3b迁移未完成')
  })
  it('never re-exposes cached costs after login expiry followed by a forbidden read',async()=>{
    const priced=clone(ledger);priced.issues[0]!.normal_cost='12345.67';priced.issues[0]!.loss_cost='0.00'
    vi.mocked(usageApi.read).mockResolvedValueOnce(priced).mockRejectedValueOnce({response:{status:401}}).mockRejectedValueOnce({response:{status:403}})
    await open(true);expect(wrapper.text()).toContain('12345.67')
    await button('刷新耗用与余料').trigger('click');await flushPromises();expect(wrapper.text()).not.toContain('12345.67')
    await button('登录后继续读取').trigger('click');await flushPromises();expect(wrapper.text()).not.toContain('12345.67');expect(wrapper.text()).not.toContain('确认批次成本')
  })
})
