import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { defineComponent } from 'vue'
import CuttingOrdersPage from '../CuttingOrdersPage.vue'
import CuttingReportingPage from '../CuttingReportingPage.vue'
import CuttingCostsPage from '../CuttingCostsPage.vue'
import CuttingLocationNotice from '../CuttingLocationNotice.vue'
import { cuttingApi } from '../api'
import { ordersApi, type CuttingOrder } from '../ordersApi'
import { reportingApi, type ProductionView } from '../reportingApi'
import { CUTTING_WORKSPACES } from '../navigation'
import { readCuttingLocation, cuttingDestination } from '../location'
vi.mock('../api',async original=>({...await original<typeof import('../api')>(),cuttingApi:{access:vi.fn()}}))
vi.mock('../ordersApi',()=>({ordersApi:{list:vi.fn(),read:vi.fn()}}))
vi.mock('../reportingApi',async original=>({...await original<typeof import('../reportingApi')>(),reportingApi:{read:vi.fn()}}))
const editorStub=defineComponent({setup(_, {expose}){expose({discard:()=>true});return{}},template:'<div />'})
const order:CuttingOrder={line_id:'beyond-page-one',dispatch_id:'d',source_version:1,snapshot:{reference_no:'TARGET-ORDER',product_no:'PRODUCT',status:'active'},received_at:'',needs_receipt:false,
  current:{version:1,actor_id:'a',created_at:'',reason:'',data:{order:{},dispatch_id:'d',bom:null,requisition:null,batches:[],purchase_reconciliation_required:false}}}
const view:ProductionView={line_id:order.line_id,version:1,as_of:'2026-10-15',tasks:[],documents:[],summary:{order_sets:10,completed:0,handed:0,actual_delivery:0,remaining:10,planned:0,plan_difference:0,completed_unhanded:0,day_completed:0,day_handed:0,months:{}}}
let wrapper:VueWrapper
beforeEach(()=>{
  vi.resetAllMocks()
  vi.mocked(cuttingApi.access).mockResolvedValue({enabled:true,schema_ready:true,orders_schema_ready:true,reporting_schema_ready:true,usage_schema_ready:true,permissions:['read','cost_read']})
  vi.mocked(ordersApi.list).mockResolvedValue({data:[],total:0,page:1,page_size:50})
  vi.mocked(ordersApi.read).mockResolvedValue(order)
  vi.mocked(reportingApi.read).mockResolvedValue(view)
})
afterEach(()=>wrapper?.unmount())
async function open(workspace:string){
  const path='/modules/production/cutting/'+workspace
  const component=workspace==='reporting'?CuttingReportingPage:workspace==='costs'?CuttingCostsPage:CuttingOrdersPage
  const router=createRouter({history:createMemoryHistory(),routes:[{path,component,props:{workspace:CUTTING_WORKSPACES.find(w=>w.path===workspace)}}]})
  await router.push(cuttingDestination(order.line_id,'2026-09',workspace));await router.isReady()
  wrapper=mount(RouterView,{global:{plugins:[router],stubs:{CuttingMaterialRequests:editorStub,CuttingMaterialUsage:editorStub,CuttingProductionSummary:true}}})
  await flushPromises();return router
}
describe('monthly reconciliation destinations',()=>{
  it.each(['planning','materials','reporting','costs'])('opens the exact %s order without relying on the first list page',async workspace=>{
    await open(workspace)
    expect(ordersApi.read).toHaveBeenCalledWith(order.line_id);expect(ordersApi.list).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('TARGET-ORDER');expect(wrapper.text()).toContain('核对月份 2026-09')
    expect(wrapper.findAll('a').find(a=>a.text()==='返回该月核对')!.attributes('href')).toContain('month=2026-09')
    if(workspace==='reporting')expect(reportingApi.read).toHaveBeenCalledWith(order.line_id,undefined,1,undefined,undefined)
  })
  it('locates the history page containing a linked production document',async()=>{
    const router=await open('reporting')
    await router.push(cuttingDestination(order.line_id,'2026-09','reporting','report','old-report'));await flushPromises()
    expect(reportingApi.read).toHaveBeenLastCalledWith(order.line_id,undefined,1,undefined,'old-report')
  })
  it('ignores an earlier order response after query navigation',async()=>{
    let resolve!:(v:CuttingOrder)=>void
    vi.mocked(ordersApi.read).mockReturnValueOnce(new Promise(r=>resolve=r))
    const router=await open('materials')
    vi.mocked(ordersApi.read).mockResolvedValue({...order,line_id:'new-order',snapshot:{reference_no:'NEW-ORDER'}})
    await router.push(cuttingDestination('new-order','2026-10','materials'));await flushPromises()
    resolve(order);await flushPromises()
    expect(wrapper.text()).toContain('NEW-ORDER');expect(wrapper.text()).not.toContain('TARGET-ORDER')
  })
  it('allows a manual search after opening a linked order',async()=>{
    await open('materials')
    const query=wrapper.findAll('input').find(input=>input.attributes('maxlength')==='80')!
    await query.setValue('ANOTHER-ORDER')
    await wrapper.get('form.order-toolbar').trigger('submit');await flushPromises()
    expect(ordersApi.list).toHaveBeenLastCalledWith(1,'ANOTHER-ORDER','','')
    expect(wrapper.text()).not.toContain('TARGET-ORDER')
  })
  it.each([403,404])('clears prior records when the linked order returns %i',async status=>{
    const router=await open('materials')
    vi.mocked(ordersApi.read).mockRejectedValueOnce({response:{status,data:{detail:'关联订单无法查看'}}})
    await router.push(cuttingDestination('unavailable','2026-10','materials'));await flushPromises()
    expect(wrapper.text()).not.toContain('TARGET-ORDER');expect(wrapper.text()).toContain('关联订单无法查看')
  })
  it('does not request cost order data without the independent cost permission',async()=>{
    vi.mocked(cuttingApi.access).mockResolvedValue({enabled:true,schema_ready:true,orders_schema_ready:true,usage_schema_ready:true,permissions:['read']})
    await open('costs');expect(ordersApi.read).not.toHaveBeenCalled();expect(wrapper.text()).toContain('单独授予成本查询权限')
  })
  it('rejects foreign or duplicate order parameters and encodes identifiers',()=>{
    expect(readCuttingLocation({factory:'huaxing',line_id:'line'})).toBeUndefined()
    expect(readCuttingLocation({factory:'huakang-c',line_id:['a','b']})).toBeUndefined()
    expect(readCuttingLocation({factory:'huakang-c',line_id:'line',focus_kind:'unknown',focus_id:'x'})).toEqual({lineId:'line',month:undefined})
  })
  it('opens and highlights a nested original document without opening an edit form',async()=>{
    const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:{template:'<div />'}}]});await router.push('/')
    wrapper=mount(defineComponent({components:{CuttingLocationNotice},template:'<section class="cutting-page"><CuttingLocationNotice :location="{lineId:\'line\',month:\'2026-09\',kind:\'warehouse\',id:\'doc\'}" selected-id="line"/><details><summary>历史</summary><p data-cutting-warehouse="doc">关联原单</p></details></section>'}),{attachTo:document.body,global:{plugins:[router]}})
    await flushPromises()
    expect(wrapper.get('details').element.open).toBe(true)
    expect(wrapper.get('[data-cutting-warehouse]').attributes('data-cutting-focused')).toBe('true')
    expect(wrapper.text()).toContain('已定位关联记录')
    expect(wrapper.find('form').exists()).toBe(false)
  })
})
