import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import CuttingClosingPage from '../CuttingClosingPage.vue'
import { CUTTING_WORKSPACES } from '../navigation'
import { cuttingApi, type Access } from '../api'
import { ordersApi, type CuttingOrder } from '../ordersApi'
import { closingApi, type ClosingPreview } from '../closingApi'
vi.mock('../api',async original=>({...await original<typeof import('../api')>(),cuttingApi:{access:vi.fn()}}))
vi.mock('../ordersApi',()=>({ordersApi:{list:vi.fn(),read:vi.fn()}}))
vi.mock('../closingApi',()=>({closingApi:{read:vi.fn()}}))
const rights:Access={enabled:true,schema_ready:true,orders_schema_ready:true,reporting_schema_ready:true,usage_schema_ready:true,permissions:['read','cost_read']}
const order:CuttingOrder={line_id:'line',dispatch_id:'d',source_version:1,snapshot:{reference_no:'ORDER-1',product_no:'P1',customer_name:'合成客户'},received_at:'',needs_receipt:false,current:{version:1,actor_id:'a',created_at:'',reason:'',data:{order:{},dispatch_id:'d',bom:null,requisition:null,batches:[],purchase_reconciliation_required:false}}}
const snapshot:ClosingPreview={line_id:'line',month:'2026-10',start:'2026-10-01',end:'2026-10-31',through:'2026-10-15',generated_at:'2026-10-15T12:00:00+08:00',state:'preview',partial:true,basis:{order_version:1,plan_version:2,usage_revision:3,warehouse_revision:4},production:[],materials:[],issues:[],production_documents:[],usage_documents:[],warehouse_documents:[],costs:{CNY:{normal:'16.25',loss:'2.00'}},pending_pricing:0,wip_status:'not_frozen',current_allocation_review:[]}
let wrapper:VueWrapper
const button=(text:string)=>wrapper.findAll('button').find(b=>b.text()===text)!
async function open(path='/'){const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:CuttingClosingPage,props:{workspace:CUTTING_WORKSPACES.find(w=>w.path==='closing')}},{path:'/away',component:{template:'<div>其他工作区</div>'}}]});await router.push(path);await router.isReady();wrapper=mount(RouterView,{global:{plugins:[router]}});await flushPromises();return router}
beforeEach(()=>{vi.resetAllMocks();vi.mocked(cuttingApi.access).mockResolvedValue(rights);vi.mocked(ordersApi.list).mockResolvedValue({data:[order],total:1,page:1,page_size:50});vi.mocked(closingApi.read).mockResolvedValue(snapshot)})
afterEach(()=>wrapper?.unmount())
describe('P4a monthly reconciliation',()=>{
  it('returns directly to the linked order and month beyond the list page',async()=>{
    vi.mocked(ordersApi.read).mockResolvedValue(order)
    await open('/?factory=huakang-c&line_id=line&month=2026-09')
    expect(ordersApi.read).toHaveBeenCalledWith('line');expect(ordersApi.list).not.toHaveBeenCalled()
    expect(closingApi.read).toHaveBeenCalledWith('line','2026-09',true)
  })
  it('shows stale-plan warning and links to the exact task',async()=>{
    vi.mocked(closingApi.read).mockResolvedValue({...snapshot,plan_stale:true,issues:[{code:'outsourced_unreturned',message:'尚未收回10套',workspace:'reporting',document_id:'',task_id:'task-1'}]})
    await open();await button('月度核对').trigger('click');await flushPromises()
    expect(wrapper.get('[role=alert]').text()).toContain('计划依据已变化')
    const link=wrapper.findAll('a').find(a=>a.text()==='前往处理工作区')!
    expect(link.attributes('href')).toContain('line_id=line');expect(link.attributes('href')).toContain('focus_kind=task');expect(link.attributes('href')).toContain('focus_id=task-1')
  })
  it('separates opening evidence and renders voids without empty usage amounts',async()=>{
    vi.mocked(closingApi.read).mockResolvedValue({...snapshot,usage_documents:[{
      document_id:'old-use',effective:false,scope:{opening:false,period:false,earlier_history:true,period_history:false},
      context:{task_name:'任务A',resource_name:'车间A',item_name:'蓝布',unit:'米',issue_id:'issue-A'},history:[
        {id:'post',action:'post',version:1,day:'2026-09-30',actor:'文员',date:'2026-09-30',reason:'实际耗用',entry:{consumed_quantity:'2',loss_quantity:'0.5',counted_remaining:'1.5'}},
        {id:'void',action:'void',version:2,day:'2026-11-01',actor:'文员',date:'2026-11-01',reason:'更正',entry:{},replaced_by_document_id:'replacement'},
      ]
    }]})
    await open();await button('月度核对').trigger('click');await flushPromises();await button('来源及更正追溯').trigger('click')
    await button('期初形成依据').trigger('click')
    expect(wrapper.text()).toContain('蓝布');expect(wrapper.text()).toContain('原实发 issue-A');expect(wrapper.text()).toContain('原单位 米')
    const events=wrapper.findAll('.closing-trace article')
    expect(events[1]!.text()).toContain('作废操作，不新增耗用或盘余');expect(events[1]!.text()).not.toContain('正常耗用')
    expect(wrapper.findAll('a').find(a=>a.text()==='replacement')!.attributes('href')).toContain('focus_id=replacement')
    await button('本期发生及更正').trigger('click');expect(wrapper.text()).not.toContain('old-use')
  })
  it('shows live period and price basis without presenting a closed period',async()=>{
    await open();await button('月度核对').trigger('click');await flushPromises()
    expect(wrapper.text()).toContain('2026-10-01 至 2026-10-15')
    expect(wrapper.text()).toContain('尚未冻结或锁月')
    await button('材料费用试算').trigger('click')
    expect(wrapper.text()).toContain('16.25');expect(wrapper.text()).toContain('当前已确认的原批次价格试算')
    expect(wrapper.text()).toContain('不是所选月末余额')
    expect(wrapper.findAll('button').some(b=>b.text()==='确认月结')).toBe(false)
  })
  it('clears the old month immediately and ignores a stale preview response',async()=>{
    await open();let resolve!:(v:ClosingPreview)=>void
    vi.mocked(closingApi.read).mockReturnValueOnce(new Promise(r=>resolve=r))
    await button('月度核对').trigger('click');await flushPromises()
    await wrapper.get('input[type=month]').setValue('2026-09')
    resolve(snapshot);await flushPromises()
    expect(wrapper.text()).not.toContain('取数时间：')
    await button('刷新所选订单核对').trigger('click');await flushPromises()
    expect(closingApi.read).toHaveBeenLastCalledWith('line','2026-09',true)
  })
  it('requests quantities only for a reader with no cost grant',async()=>{
    vi.mocked(cuttingApi.access).mockResolvedValue({...rights,permissions:['read']})
    const physical={...snapshot};delete physical.costs;delete physical.pending_pricing;delete physical.current_allocation_review
    vi.mocked(closingApi.read).mockResolvedValue(physical)
    await open();await button('月度核对').trigger('click');await flushPromises()
    expect(closingApi.read).toHaveBeenLastCalledWith('line',expect.any(String),false)
    await button('材料费用试算').trigger('click')
    expect(wrapper.text()).toContain('单独授予成本查询权限');expect(wrapper.text()).not.toContain('16.25')
  })
  it.each([401,403])('removes quantities and cost caches after %i',async status=>{
    await open();await button('月度核对').trigger('click');await flushPromises();await button('材料费用试算').trigger('click')
    expect(wrapper.text()).toContain('16.25')
    vi.mocked(closingApi.read).mockRejectedValueOnce({response:{status,data:{detail:'权限已变更'}}})
    await button('刷新所选订单核对').trigger('click');await flushPromises()
    expect(wrapper.text()).not.toContain('16.25');expect(wrapper.text()).not.toContain('ORDER-1')
    expect(wrapper.text()).toContain('权限已变更')
  })
  it('does not load orders before schema readiness',async()=>{
    vi.mocked(cuttingApi.access).mockResolvedValue({...rights,reporting_schema_ready:false})
    await open();expect(ordersApi.list).not.toHaveBeenCalled();expect(wrapper.text()).toContain('显式迁移')
  })
  it('discards responses after navigation away',async()=>{
    const router=await open();let resolve!:(v:ClosingPreview)=>void
    vi.mocked(closingApi.read).mockReturnValueOnce(new Promise(r=>resolve=r))
    await button('月度核对').trigger('click');await flushPromises();await router.push('/away');resolve(snapshot);await flushPromises()
    expect(wrapper.text()).toBe('其他工作区')
  })
})
