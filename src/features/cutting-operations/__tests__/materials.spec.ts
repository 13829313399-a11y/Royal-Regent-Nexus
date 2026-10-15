import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createRouter, createMemoryHistory, RouterView, type Router } from 'vue-router'
import CuttingMaterialRequests from '../CuttingMaterialRequests.vue'
import CuttingPlanEditor from '../CuttingPlanEditor.vue'
import { materialApi, type MaterialLedger, type WarehouseMaterial } from '../materialsApi'
import { ordersApi } from '../ordersApi'
import { multiplyQuantity } from '../quantityMath'
import type { CuttingOrder } from '../ordersApi'
import type { MasterRecord } from '../api'
import type { ProductionPlan, PlanTask } from '../planning'
vi.mock('../materialsApi',()=>({materialApi:{read:vi.fn(),catalog:vi.fn(),post:vi.fn(),recover:vi.fn()}}))
vi.mock('../ordersApi',()=>({ordersApi:{read:vi.fn()}}))
const resource:MasterRecord={id:'r1',factory_id:'huakang-c',kind:'resource',code:'R1',version:1,status:'active',actor_id:'a',created_at:'',reason:'',data:{name:'本厂',execution:'internal',process:'cutting',contact:'',source_reference:'现场'}}
const bom:MasterRecord={...resource,id:'bom',kind:'bom',code:'B1',status:'published',version:2,data:{name:'测试BOM',item_no:'001',style:'',color:'蓝',source_reference:'工程',parts:[{code:'A',name:'裁片A',pieces_per_set:1}],requirements:[{material_id:'mat',material_version:1,part_codes:['A'],quantity_per_set:'0.5',unit:'米',required_for_cutting:true,stage:'裁剪',note:''}]},material_references:{'mat:1':{code:'M1',name:'蓝布'}}}
const task:PlanTask={task_id:'t1',name:'本厂任务',resource_id:'r1',resource_version:1,target_sets:20,materials:[],readiness_basis:'按交期',actual_issue_date:null,actual_issue_reference:'',prerequisite_date:null,prerequisite_basis:'',days:[],resource,planned_sets:0,unplanned_sets:20,first_supply_date:null,completion_date:null}
const plan:ProductionPlan={version:8,tasks:[task],allocated_sets:20,unallocated_sets:0,actor_id:'a',created_at:'',reason:''}
const order:CuttingOrder={line_id:'line-1',dispatch_id:'d1',source_version:1,snapshot:{reference_no:'O1',status:'active'},received_at:'',needs_receipt:false,current:{version:9,actor_id:'a',created_at:'',reason:'',data:{order:{},dispatch_id:'d1',bom,requisition:null,batches:[],purchase_reconciliation_required:false,planning:{published:plan}}}}
const material:WarehouseMaterial={id:'wm1',code:'FAB1',name:'蓝布',revision:2,unit:'米',category:'FABRIC',spec:'规格A',color:'蓝'}
const ledger:MaterialLedger={revision:7,requests:[{id:'req1',date:'2026-10-01',quantity:'6.50',issued_quantity:'6.5',unit:'米',item_code:'FAB1',item_name:'蓝布',closed:false,close_reason:'',reason:'任务用途',context:{order_no:'O1',plan_version:8,bom_version:2,task_id:'t1',task_name:'本厂任务',resource_name:'本厂',execution:'internal',row:0,mapping_basis:'双边身份核对',cutting_material:{code:'M1',name:'蓝布',category:'fabric',unit:'米',specification:'规格A',color:'蓝',source_reference:'工程'},warehouse_material:material},issues:[{id:'i1',date:'2026-10-02',quantity:'6.5',received_quantity:'1',returned_quantity:'0',reversed:false,lot:'LOT1',roll_no:'1',location:'A01'}],receipts:[{id:'rec1',original_id:'i1',date:'2026-10-03',quantity:'1',reason:'收妥凭证',actor:'文员',reversed:false}]}]}
const clone=<T,>(v:T):T=>JSON.parse(JSON.stringify(v))
let wrapper:VueWrapper,router:Router
function button(text:string){const b=wrapper.findAll('button').find(b=>b.text()===text);if(!b)throw Error('Missing '+text);return b}
function field(text:string){const l=wrapper.findAll('label').find(l=>l.text().startsWith(text));if(!l)throw Error('Missing '+text);return l.find('input,select,textarea')}
async function open(permissions=['read','material_request','material_receive']){
  router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:CuttingMaterialRequests,props:{order:clone(order),permissions}},{path:'/away',component:{template:'<div>离开</div>'}}]})
  await router.push('/');await router.isReady();wrapper=mount(RouterView,{global:{plugins:[router]}});await flushPromises()
}
async function receipt(){await button('分批签收').trigger('click');await field('本次签收数量').setValue('2.5');await field('收妥凭据').setValue('签收人A，实际收到2.5米')}
beforeEach(()=>{vi.resetAllMocks();vi.spyOn(window,'confirm').mockReturnValue(false);vi.mocked(materialApi.read).mockResolvedValue(clone(ledger));vi.mocked(materialApi.catalog).mockResolvedValue({items:[material],total:1,page:1});vi.mocked(materialApi.post).mockResolvedValue({})})
afterEach(()=>{wrapper?.unmount();vi.restoreAllMocks()})
describe('cutting material bridge',()=>{
  it('submits the frozen task/BOM row and explicitly selected material revision',async()=>{
    await open();await button('新建领料申请').trigger('click');await button('查询物料映射').trigger('click');await flushPromises();await field('仓库物料版本').setValue('wm1');await field('物料对应依据').setValue('规格A蓝色米一致');await field('本次申请数量').setValue('6.50');await field('申请数量').setValue('任务分批领料');await wrapper.get('form').trigger('submit');await flushPromises()
    expect(materialApi.post).toHaveBeenCalledWith('line-1','request',expect.objectContaining({factory_id:'huakang-c',expected_version:9,plan_version:8,task_id:'t1',row:0,material_id:'wm1',material_revision:2,quantity:'6.50'}))
    expect(wrapper.text()).toContain('申请不扣库存')
  })
  it('shows exact-unit quantities, frozen identities and the separate actual receipt date',async()=>{
    await open();expect(wrapper.text()).toContain('已全部发料');expect(wrapper.text()).toContain('规格A');expect(wrapper.text()).toContain('2026-10-03');expect(wrapper.text()).toContain('已签收')
    await receipt();await wrapper.get('form').trigger('submit');await flushPromises();expect(materialApi.post).toHaveBeenCalledWith('line-1','receive',expect.objectContaining({original_id:'i1',expected_version:7,quantity:'2.5'}))
  })
  it('protects dirty drafts on cancel, route leave and unload',async()=>{
    await open();await receipt();await button('取消领料编辑').trigger('click');expect(wrapper.find('form').exists()).toBe(true);await router.push('/away');expect(router.currentRoute.value.path).toBe('/');const e=new Event('beforeunload',{cancelable:true});window.dispatchEvent(e);expect(e.defaultPrevented).toBe(true)
  })
  it.each([401,403,409])('keeps the original uncertain command through retry %s',async status=>{
    await open();await receipt();vi.mocked(materialApi.post).mockRejectedValueOnce(new Error('timeout')).mockRejectedValueOnce({response:{status}}).mockResolvedValueOnce({});await wrapper.get('form').trigger('submit');await flushPromises();const original=vi.mocked(materialApi.post).mock.calls[0];await button('重试领料原操作').trigger('click');await flushPromises();await router.push('/away');expect(router.currentRoute.value.path).toBe('/');await button('重试领料原操作').trigger('click');await flushPromises();expect(vi.mocked(materialApi.post).mock.calls[2]).toEqual(original)
  })
  it('restores editing after initial 401 then definite rejection',async()=>{
    await open();await receipt();vi.mocked(materialApi.post).mockRejectedValueOnce({response:{status:401}}).mockRejectedValueOnce({response:{status:409}});await wrapper.get('form').trigger('submit');await flushPromises();expect(wrapper.find('form').exists()).toBe(false);await button('重试领料原操作').trigger('click');await flushPromises();expect(field('本次签收数量').element).toHaveProperty('value','2.5')
  })
  it('retains quantities while explicitly refreshing a stale warehouse revision',async()=>{
    await open();await receipt();vi.mocked(materialApi.post).mockRejectedValueOnce({response:{status:409}});await wrapper.get('form').trigger('submit');await flushPromises();vi.mocked(materialApi.read).mockResolvedValue({...clone(ledger),revision:10});await button('保留填写并刷新仓库版本').trigger('click');await flushPromises();expect(field('本次签收数量').element).toHaveProperty('value','2.5');await wrapper.get('form').trigger('submit');await flushPromises();expect(vi.mocked(materialApi.post).mock.calls[1]?.[2].expected_version).toBe(10);expect(vi.mocked(materialApi.post).mock.calls[1]?.[2].operation_id).not.toBe(vi.mocked(materialApi.post).mock.calls[0]?.[2].operation_id)
  })
  it('ignores a late draft-version refresh after cancelling the editor',async()=>{
    await open();await receipt();let resolve!:(v:MaterialLedger)=>void;vi.mocked(materialApi.read).mockReturnValueOnce(new Promise(r=>resolve=r));await button('保留填写并刷新仓库版本').trigger('click');vi.mocked(window.confirm).mockReturnValue(true);await button('取消领料编辑').trigger('click');resolve({...clone(ledger),revision:99});await flushPromises();expect(wrapper.find('form').exists()).toBe(false)
  })
  it('fences an uncertain operation without discarding the draft',async()=>{
    await open();await receipt();vi.mocked(materialApi.post).mockRejectedValueOnce(new Error('timeout'));await wrapper.get('form').trigger('submit');await flushPromises();vi.mocked(materialApi.recover).mockResolvedValue({state:'abandoned'});await button('核对领料保存结果／停止未执行操作').trigger('click');await flushPromises();expect(field('本次签收数量').element).toHaveProperty('value','2.5');expect(wrapper.text()).toContain('原操作已核实未执行')
  })
  it('does not expose request or signature writes to read-only users',async()=>{await open(['read']);expect(wrapper.findAll('button').some(b=>['新建领料申请','分批签收','撤销签收','关闭未发余量'].includes(b.text()))).toBe(false)})
  it('ignores material search results after the query changes',async()=>{
    await open();await button('新建领料申请').trigger('click');let resolve!:(v:{items:WarehouseMaterial[];total:number;page:number})=>void;vi.mocked(materialApi.catalog).mockReturnValueOnce(new Promise(r=>resolve=r));await button('查询物料映射').trigger('click');await field('查询仓库物料').setValue('新物料');resolve({items:[material],total:1,page:1});await flushPromises();expect(field('仓库物料版本').findAll('option')).toHaveLength(1)
  })
})


describe('material bridge recovery and audit',()=>{
  it('keeps scientific-notation BOM quantities exact in cumulative request previews',()=>{
    expect(multiplyQuantity('1E+3',20)).toBe('20000')
    expect(multiplyQuantity('0.000001',1000000000)).toBe('1000.000000')
    expect(multiplyQuantity('1E-6',20)).toBe('0.000020')
    expect(multiplyQuantity('NaN',20)).toBeUndefined()
  })
  it('shows exact cumulative quantities and warns about additional requests above the task BOM amount',async()=>{
    const value=clone(ledger);value.totals=[{dispatch_id:'d1',bom_id:'bom',bom_version:2,task_id:'t1',resource_id:'r1',resource_version:1,row:0,task_name:'本厂任务',material_name:'蓝布',unit:'米',theoretical_quantity:'10',requested_quantity:'6.5',effective_requested_quantity:'6.5',issued_quantity:'6.5',received_quantity:'1',returned_quantity:'0',net_received_quantity:'1',outstanding_quantity:'0',exceeds_theoretical:false}]
    vi.mocked(materialApi.read).mockResolvedValue(value)
    await open();expect(wrapper.text()).toContain('历史／有效申请')
    await button('新建领料申请').trigger('click');await field('本次申请数量').setValue('4.000001')
    expect(wrapper.text()).toContain('有效申请合计 10.500001 米');expect(wrapper.text()).toContain('超过理论用量')
  })
  it('selects only current-task receipts and fills the latest selected actual receipt date',async()=>{
    const value=clone(ledger);value.requests[0]!.context={...value.requests[0]!.context,dispatch_id:'d1',bom_id:'bom',resource_id:'r1',resource_version:1}
    value.requests[0]!.receipts.push({...value.requests[0]!.receipts[0]!,id:'rec2',date:'2026-10-05'})
    value.requests[0]!.issues[0]!.received_quantity='999999999999.999999';value.requests[0]!.issues[0]!.returned_quantity='999999999999.999998'
    vi.mocked(materialApi.read).mockResolvedValue(value)
    const tasks=[clone(task)], editor=mount(CuttingPlanEditor,{props:{data:clone(order.current!.data),lineId:'line-1',modelValue:tasks}})
    await flushPromises()
    const receipts=editor.findAll('label').filter(l=>l.text().includes('· rec'))
    expect(receipts).toHaveLength(2)
    await receipts[0]!.get('input').setValue(true);await receipts[1]!.get('input').setValue(true)
    expect(tasks[0]!.material_receipt_ids).toEqual(['rec1','rec2']);expect(tasks[0]!.actual_issue_date).toBe('2026-10-05')
    await receipts[1]!.get('input').setValue(false);expect(tasks[0]!.actual_issue_date).toBe('2026-10-03')
    editor.unmount()
  })
  it('keeps a rejected request draft while refreshing and reconfirming its new plan version',async()=>{
    await open();await button('新建领料申请').trigger('click');await button('查询物料映射').trigger('click');await flushPromises()
    await field('仓库物料版本').setValue('wm1');await field('物料对应依据').setValue('规格A蓝色米一致');await field('本次申请数量').setValue('6.50');await field('申请数量').setValue('保留批次用途')
    vi.mocked(materialApi.post).mockRejectedValueOnce({response:{status:409}})
    await wrapper.get('form').trigger('submit');await flushPromises()
    const latest=clone(order);latest.current!.version=12;latest.current!.data.planning!.published!.version=11
    vi.mocked(ordersApi.read).mockResolvedValue(latest)
    await button('保留填写并刷新订单／计划').trigger('click');await flushPromises()
    expect(field('本次申请数量').element).toHaveProperty('value','6.50');expect(field('申请数量').element).toHaveProperty('value','保留批次用途');expect(field('仓库物料版本').element).toHaveProperty('value','wm1')
    expect(wrapper.text()).toContain('订单 V9 → V12');expect(wrapper.text()).toContain('发布计划 V8 → V11')
    await wrapper.get('form').trigger('submit');await flushPromises();expect(materialApi.post).toHaveBeenCalledTimes(1)
    await wrapper.get('input[type="checkbox"]').setValue(true)
    await wrapper.get('form').trigger('submit');await flushPromises()
    expect(vi.mocked(materialApi.post).mock.calls[1]?.[2]).toEqual(expect.objectContaining({expected_version:12,plan_version:11,quantity:'6.50',material_id:'wm1',mapping_basis:'规格A蓝色米一致'}))
    expect(vi.mocked(materialApi.post).mock.calls[1]?.[2].operation_id).not.toBe(vi.mocked(materialApi.post).mock.calls[0]?.[2].operation_id)
  })
  it('does not apply a late request refresh after its draft is discarded',async()=>{
    await open();await button('新建领料申请').trigger('click')
    let resolve!:(v:CuttingOrder)=>void;vi.mocked(ordersApi.read).mockReturnValueOnce(new Promise(r=>resolve=r))
    await button('保留填写并刷新订单／计划').trigger('click')
    const component=wrapper.findComponent(CuttingMaterialRequests);(component.vm as unknown as {discard:()=>boolean}).discard()
    resolve(clone(order));await flushPromises();expect(wrapper.find('form').exists()).toBe(false);expect(component.emitted('refreshed')).toBeUndefined()
  })
  it('restores a dirty request after catalog authentication expires',async()=>{
    await open();await button('新建领料申请').trigger('click');await field('申请数量').setValue('保留用途说明')
    vi.mocked(materialApi.catalog).mockRejectedValueOnce({response:{status:401}})
    await button('查询物料映射').trigger('click');await flushPromises()
    expect(wrapper.find('form').exists()).toBe(false)
    await button('重新登录后继续／刷新').trigger('click');await flushPromises()
    expect(field('申请数量').element).toHaveProperty('value','保留用途说明')
    expect(materialApi.post).not.toHaveBeenCalled()
  })
  it('shows dated audit details and explicitly confirms the new published plan',async()=>{
    const updated=clone(ledger);const row=updated.requests[0]!
    row.issued_quantity='2';row.accepted_plan_version=6;row.due_date='2026-10-09';row.history=[{id:'void1',original_id:'rec1',kind:'CUTTING_RECEIPT_VOID',date:'2026-10-08',occurred_at:'2026-10-10T12:00:00',actor:'核对主管',reason:'签收日期录错',quantity:'1',reversed:false}]
    vi.mocked(materialApi.read).mockResolvedValue(updated)
    await open();expect(wrapper.text()).toContain('2026-10-09');expect(wrapper.text()).toContain('核对主管');expect(wrapper.text()).toContain('签收日期录错')
    await button('核对计划续用').trigger('click');await field('操作原因').setValue('纯日期调整，物料与数量不变')
    await wrapper.get('form').trigger('submit');await flushPromises()
    expect(materialApi.post).toHaveBeenCalledWith('line-1','reuse',expect.objectContaining({original_id:'req1',plan_version:8,expected_version:7,reason:'纯日期调整，物料与数量不变'}))
  })
})
