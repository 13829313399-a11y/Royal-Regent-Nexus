import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import TaskBoard from '../CuttingTaskBoard.vue'
import Inventory from '../CuttingInventory.vue'
import Costs from '../CuttingCostOverview.vue'
import Activity from '../CuttingActivityPage.vue'
import Monthly from '../CuttingMonthlyOverview.vue'
import { workspaceApi, type TaskView, type ActivityRow } from '../workspaceApi'
import { readCuttingLocation } from '../location'
import { invalidateCuttingWorkspace } from '../workspaceRefresh'
vi.mock('../workspaceApi',()=>({
  businessDay:()=> '2026-10-20',
  workspaceApi:{tasks:vi.fn(),inventory:vi.fn(),activity:vi.fn(),monthly:vi.fn(),costs:vi.fn()},
}))
vi.mock('../CuttingReportExport.vue',()=>({default:{props:['selection','access'],template:'<pre class="export-selection">{{JSON.stringify(selection)}}</pre>'}}))
const empty={data:[],total:0,page:1,page_size:50}
const task:TaskView={...empty,day:'2026-10-10',total:51,stats:{tasks:51,reported:1,unreported:50,planned:60,completed:2,handed:1,abnormal:1,unplanned_facts:0},
  data:[{line_id:'line-1',order_no:'ORD-001',customer:'客户',item_no:'ITEM',task_id:'task-1',task_name:'任务',resource_name:'外厂',execution:'outsourced',planned:10,reported:false,has_fact:true,day_completed:2,day_handed:1,completed:2,target_sets:20,returned:3,accepted:2,historical:false,reasons:['外发收回待验收']}]}
let wrapper:VueWrapper
const router=createRouter({history:createMemoryHistory(),routes:[{path:'/:pathMatch(.*)*',component:{template:'<div />'}}]})
const button=(name:string)=>wrapper.findAll('button').find(b=>b.text()===name)!
beforeEach(()=>{vi.resetAllMocks()})
afterEach(()=>wrapper?.unmount())
describe('cutting read-only workspaces',()=>{
  it('opens and updates an explicit sample business day without changing the default-today contract',async()=>{
    vi.mocked(workspaceApi.tasks).mockResolvedValue(task)
    const sampleRouter=createRouter({history:createMemoryHistory(),routes:[{path:'/:pathMatch(.*)*',component:{template:'<div />'}}]})
    await sampleRouter.push('/dashboard?factory=huakang-c&day=2026-09-10')
    wrapper=mount(TaskBoard,{global:{plugins:[sampleRouter]}});await flushPromises()
    expect(workspaceApi.tasks).toHaveBeenLastCalledWith(expect.objectContaining({day:'2026-09-10',page:1}))
    await sampleRouter.push('/dashboard?factory=huakang-c&day=2026-10-21');await flushPromises()
    expect(workspaceApi.tasks).toHaveBeenLastCalledWith(expect.objectContaining({day:'2026-10-21',page:1}))
    await sampleRouter.push('/dashboard?factory=huakang-c&day=2026-02-30');await flushPromises()
    expect(workspaceApi.tasks).toHaveBeenLastCalledWith(expect.objectContaining({day:'2026-10-20'}))
  })
  it('keeps inventory paging and write refresh on applied filters, and distinguishes no matches',async()=>{
    vi.mocked(workspaceApi.inventory).mockResolvedValue({...empty,total:51,units:{}})
    wrapper=mount(Inventory);await flushPromises()
    await wrapper.get('input').setValue('NEW-ORDER')
    await button('下一页').trigger('click');await flushPromises()
    expect(workspaceApi.inventory).toHaveBeenLastCalledWith(expect.objectContaining({q:'',page:2}))
    invalidateCuttingWorkspace();await flushPromises()
    expect(workspaceApi.inventory).toHaveBeenLastCalledWith(expect.objectContaining({q:'',page:1}))
    expect((wrapper.get('input').element as HTMLInputElement).value).toBe('NEW-ORDER')
    vi.mocked(workspaceApi.inventory).mockResolvedValue({...empty,units:{}})
    await wrapper.get('form').trigger('submit');await flushPromises()
    expect(workspaceApi.inventory).toHaveBeenLastCalledWith(expect.objectContaining({q:'NEW-ORDER',page:1}))
    expect(wrapper.text()).toContain('当前筛选无匹配库存记录')
    expect(wrapper.text()).not.toContain('先在“领料申请”')
    await button('清除筛选').trigger('click');await flushPromises()
    expect(wrapper.text()).toContain('暂无关联实发记录')
  })
  it('keeps task date, text and executor on applied filters when paging back to page one',async()=>{
    vi.mocked(workspaceApi.tasks).mockImplementation(async params=>({...task,page:params.page??1}))
    wrapper=mount(TaskBoard,{global:{plugins:[router]}});await flushPromises()
    await wrapper.get('input[type=date]').setValue('2026-09-01')
    await wrapper.get('input[maxlength]').setValue('NEW')
    await wrapper.get('select').setValue('internal')
    await button('下一页').trigger('click');await flushPromises()
    expect(workspaceApi.tasks).toHaveBeenLastCalledWith(expect.objectContaining({day:'2026-10-20',q:'',execution:'',page:2}))
    await button('上一页').trigger('click');await flushPromises()
    expect(workspaceApi.tasks).toHaveBeenLastCalledWith(expect.objectContaining({day:'2026-10-20',q:'',page:1}))
    await wrapper.get('form').trigger('submit');await flushPromises()
    expect(workspaceApi.tasks).toHaveBeenLastCalledWith(expect.objectContaining({day:'2026-09-01',q:'NEW',execution:'internal',page:1}))
  })
  it('does not pair a log page fence with newly typed filters and links the exact master version',async()=>{
    const row={source:'master',document_id:'master-1',version:1,id:'revision-1',occurred_at:'2026-10-10T00:00:00Z',action:'revision',actor:'operator',reason:'原依据'} as ActivityRow
    vi.mocked(workspaceApi.activity).mockResolvedValue({...empty,data:[row],total:51,token:'original-fence'})
    wrapper=mount(Activity,{global:{plugins:[router]}});await flushPromises()
    expect(wrapper.get('a').attributes('href')).toContain('master_version=1')
    await wrapper.get('select').setValue('order')
    await wrapper.get('input[type=month]').setValue('2026-09')
    await wrapper.findAll('input')[0]!.setValue('NEW-ORDER')
    await button('下一页').trigger('click');await flushPromises()
    expect(workspaceApi.activity).toHaveBeenLastCalledWith(expect.objectContaining({source:'',order_q:'',month:undefined,page:2,expected_token:'original-fence'}))
    await wrapper.get('form').trigger('submit');await flushPromises()
    expect(workspaceApi.activity).toHaveBeenLastCalledWith(expect.objectContaining({source:'order',order_q:'NEW-ORDER',month:'2026-09',page:1,expected_token:undefined}))
  })
  it('keeps cost paging on the queried scope and explains filtered empty results',async()=>{
    vi.mocked(workspaceApi.costs).mockResolvedValue({...empty,total:51,currencies:{},pending_pricing:0})
    wrapper=mount(Costs);await flushPromises()
    await wrapper.get('input').setValue('NOT-FOUND');await button('下一页').trigger('click');await flushPromises()
    expect(workspaceApi.costs).toHaveBeenLastCalledWith({q:'',page:2})
    vi.mocked(workspaceApi.costs).mockResolvedValue({...empty,currencies:{},pending_pricing:0})
    await wrapper.get('form').trigger('submit');await flushPromises()
    expect(wrapper.text()).toContain('当前筛选无匹配费用记录')
  })

  it('splits exception actions and retains the result day and correct reporting view',async()=>{
    vi.mocked(workspaceApi.tasks).mockResolvedValue({...task,data:task.data.map(r=>({...r,reasons:['外发收回待验收','已结束业务日未填报','计划依据已变更']}))})
    wrapper=mount(TaskBoard,{global:{plugins:[router]}});await flushPromises()
    await wrapper.get('input[type=date]').setValue('2026-10-19')
    const link=(name:string)=>wrapper.findAll('a').find(a=>a.text()===name)!.attributes('href')
    expect(link('收回与验收')).toContain('reporting_view=external')
    expect(link('补填当日日报')).toContain('/reporting?')
    expect(link('补填当日日报')).toContain('day=2026-10-10')
    expect(link('复核计划')).toContain('/planning?')
  })
  it('refreshes inventory after a write without clearing its filters',async()=>{
    vi.mocked(workspaceApi.inventory).mockResolvedValue({...empty,units:{}})
    wrapper=mount(Inventory);await flushPromises()
    await wrapper.get('input').setValue('ORDER-42')
    await wrapper.get('form').trigger('submit');await flushPromises()
    invalidateCuttingWorkspace();await flushPromises()
    expect(workspaceApi.inventory).toHaveBeenLastCalledWith(expect.objectContaining({q:'ORDER-42',page:1}))
    expect((wrapper.get('input').element as HTMLInputElement).value).toBe('ORDER-42')
  })
  it('uses the parent month for query and exports and reacts to a new period',async()=>{
    vi.mocked(workspaceApi.monthly).mockImplementation(async month=>({month,domains:[],frozen:[]}))
    wrapper=mount(Monthly,{props:{month:'2026-09'}});await flushPromises()
    expect(workspaceApi.monthly).toHaveBeenLastCalledWith('2026-09')
    await wrapper.setProps({month:'2026-08'});await flushPromises()
    expect(workspaceApi.monthly).toHaveBeenLastCalledWith('2026-08')
    await wrapper.get('input[type=month]').setValue('2026-07')
    expect(wrapper.emitted('update:month')?.at(-1)).toEqual(['2026-07'])
  })
  it('queries logs by order and business month before pagination',async()=>{
    vi.mocked(workspaceApi.activity).mockResolvedValue({...empty,total:51,token:'scoped'})
    wrapper=mount(Activity,{global:{plugins:[router]}});await flushPromises()
    await wrapper.get('input[type=month]').setValue('2026-09')
    await wrapper.findAll('input')[0]!.setValue('ORD-001')
    await wrapper.get('form').trigger('submit');await flushPromises()
    await button('下一页').trigger('click');await flushPromises()
    expect(workspaceApi.activity).toHaveBeenLastCalledWith(expect.objectContaining({order_q:'ORD-001',month:'2026-09',page:2,expected_token:'scoped'}))
  })
  it('shows full-scope metrics and links the queried business day even after editing the filter',async()=>{
    vi.mocked(workspaceApi.tasks).mockResolvedValue(task)
    wrapper=mount(TaskBoard,{global:{plugins:[router]}});await flushPromises()
    expect(wrapper.text()).toContain('51')
    await wrapper.get('input[type=date]').setValue('2026-10-19')
    const link=wrapper.findAll('a').find(a=>a.text()==='填数／查看')!
    expect(link.attributes('href')).toContain('day=2026-10-10')
    await button('下一页').trigger('click');await flushPromises()
    expect(workspaceApi.tasks).toHaveBeenLastCalledWith(expect.objectContaining({page:2}))
  })
  it('does not replace the newest task query with an older response',async()=>{
    let resolve!:(value:TaskView)=>void
    vi.mocked(workspaceApi.tasks).mockReturnValueOnce(new Promise(r=>resolve=r)).mockResolvedValueOnce({...task,data:[],total:0,stats:{...task.stats,tasks:7}})
    wrapper=mount(TaskBoard,{global:{plugins:[router]}})
    await button('异常任务').trigger('click');await flushPromises()
    resolve(task);await flushPromises()
    expect(wrapper.text()).not.toContain('ORD-001')
    expect(wrapper.text()).toContain('7')
  })
  it('shows unknown metrics instead of zero after a failed query',async()=>{
    vi.mocked(workspaceApi.tasks).mockRejectedValue(new Error('离线'))
    wrapper=mount(TaskBoard,{global:{plugins:[router]}});await flushPromises()
    expect(wrapper.get('[role=alert]').exists()).toBe(true)
    expect(wrapper.findAll('.cutting-metrics strong').map(e=>e.text()).join('')).toContain('—')
    expect(wrapper.text()).not.toContain('当前筛选范围暂无任务')
  })
  it('requests distinct order summaries when changing inventory view',async()=>{
    vi.mocked(workspaceApi.inventory).mockResolvedValue({...empty,units:{米:{remaining_quantity:'8.5',unsigned_quantity:'2',returned_quantity:'1'}}})
    wrapper=mount(Inventory);await flushPromises()
    expect(workspaceApi.inventory).toHaveBeenLastCalledWith(expect.objectContaining({view:'issues'}))
    await wrapper.setProps({summary:true});await flushPromises()
    expect(workspaceApi.inventory).toHaveBeenLastCalledWith(expect.objectContaining({view:'orders',page:1}))
    expect(wrapper.text()).toContain('8.5')
  })
  it('preserves the page fence for logs and resets it on a fresh query',async()=>{
    vi.mocked(workspaceApi.activity).mockResolvedValue({...empty,total:51,token:'basis'})
    wrapper=mount(Activity,{global:{plugins:[router]}});await flushPromises()
    await button('下一页').trigger('click');await flushPromises()
    expect(workspaceApi.activity).toHaveBeenLastCalledWith(expect.objectContaining({page:2,expected_token:'basis'}))
    await wrapper.get('form').trigger('submit');await flushPromises()
    expect(workspaceApi.activity).toHaveBeenLastCalledWith(expect.objectContaining({page:1,expected_token:undefined}))
  })
  it('routes cost confirmation to its event anchor and keeps settlement prices as original evidence',async()=>{
    const row:ActivityRow={source:'material',id:'price-1',line_id:'line-1',version:3,action:'price',occurred_at:'2026-10-10T10:00:00Z',business_day:'2026-10-10',document_id:'batch-1',actor:'采购',reason:'确认',related_id:null,month:null}
    vi.mocked(workspaceApi.activity).mockResolvedValue({...empty,total:2,data:[row,{...row,source:'settlement',id:'fee-price',price_evidence:{line_id:'line-1',task_id:'external',unit_price:'2.50',currency:'CNY',evidence:'QUOTE-001'}}]})
    wrapper=mount(Activity,{global:{plugins:[router]}});await flushPromises()
    expect(wrapper.get('a').attributes('href')).toContain('focus_kind=cost_event')
    expect(wrapper.get('a').attributes('href')).toContain('cost_view=history')
    expect(wrapper.text()).toContain('QUOTE-001')
    expect(wrapper.findAll('a')).toHaveLength(1)
  })
  it('clears protected log rows after losing permission',async()=>{
    vi.mocked(workspaceApi.activity).mockResolvedValueOnce({...empty,total:1,data:[{source:'period',id:'freeze',document_id:'2026-10',version:1,occurred_at:'2026-10-10T00:00:00Z',action:'lock',actor:'会计',reason:'机密依据',line_id:'',business_day:null,related_id:null,month:'2026-10'}]}).mockRejectedValueOnce({response:{status:403}})
    wrapper=mount(Activity,{global:{plugins:[router]}});await flushPromises()
    expect(wrapper.text()).toContain('机密依据')
    await wrapper.get('form').trigger('submit');await flushPromises()
    expect(wrapper.text()).not.toContain('机密依据')
  })
  it('exports payment balances with the current payments contract, not a fake frozen payment selection',async()=>{
    vi.mocked(workspaceApi.monthly).mockResolvedValue({month:'2026-10',domains:[],frozen:[{kind:'payment',event_id:'payment-event',document_id:'payment',version:1,month:'2026-10',valid:false,actor:'会计',date:'2026-10-10'}]})
    wrapper=mount(Monthly,{props:{exportsOnly:true,access:{enabled:true,schema_ready:true,permissions:['payment_read']}}});await flushPromises()
    expect(wrapper.findAll('.export-selection').map(p=>JSON.parse(p.text()))).toEqual([{kind:'payments',month:'2026-10'}])
    await button('查看冻结依据').trigger('click')
    expect(wrapper.emitted('open')?.[0]).toEqual(['payment','2026-10','payment','payment-event'])
  })
  it('validates calendar dates and cost anchor targets',()=>{
    expect(readCuttingLocation({factory:'huakang-c',line_id:'line-1',day:'2026-02-30'})?.day).toBeUndefined()
    expect(readCuttingLocation({factory:'huakang-c',line_id:'line-1',day:'2026-10-10',focus_kind:'cost_event',focus_id:'p1',cost_view:'allocation'})).toMatchObject({day:'2026-10-10',kind:'cost_event',id:'p1',costView:'allocation'})
  })
})
