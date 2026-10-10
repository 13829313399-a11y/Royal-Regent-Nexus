import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView, type Router } from 'vue-router'
import { cuttingOperationsRoutes } from '../routes'
import { cuttingApi } from '../api'
import { ordersApi, type CuttingOrder } from '../ordersApi'
import { reportingApi, type ProductionView } from '../reportingApi'

vi.mock('@/components/layout/AccountMenu.vue',()=>({default:{template:'<span />'}}))
vi.mock('../api',async original=>({...await original<typeof import('../api')>(),cuttingApi:{access:vi.fn()}}))
vi.mock('../ordersApi',()=>({ordersApi:{list:vi.fn()}}))
vi.mock('../reportingApi',async original=>({...await original<typeof import('../reportingApi')>(),reportingApi:{read:vi.fn(),command:vi.fn(),recover:vi.fn()}}))
const path='/modules/production/cutting/reporting?factory=huakang-c'
const order:CuttingOrder={line_id:'line-1',dispatch_id:'dispatch-1',source_version:1,snapshot:{reference_no:'CUT-1',product_no:'001',customer_name:'合成洋行',status:'active'},received_at:'',needs_receipt:false,
  current:{version:7,actor_id:'a',created_at:'',reason:'接单',data:{order:{},dispatch_id:'dispatch-1',bom:null,requisition:null,batches:[],purchase_reconciliation_required:false}}}
const view:ProductionView={line_id:'line-1',version:7,as_of:'2026-10-10',tasks:[{task_id:'task-1',name:'本厂任务',execution:'internal',mode:null,plan_version:6,target_sets:50,parts:[{code:'P1',name:'前片',pieces_per_set:2},{code:'P2',name:'后片',pieces_per_set:1}],historical:false,balance:null}],documents:[],
  summary:{order_sets:50,completed:0,handed:0,actual_delivery:0,remaining:50,planned:10,plan_difference:-10,completed_unhanded:0,day_completed:0,day_handed:0,months:{}}}
let wrapper:VueWrapper,router:Router
const clone=<T,>(v:T):T=>JSON.parse(JSON.stringify(v))
function button(text:string){const b=wrapper.findAll('button').find(b=>b.text()===text);if(!b)throw Error('Missing '+text);return b}
function field(label:string){const l=wrapper.findAll('label').find(l=>l.text().startsWith(label));if(!l)throw Error('Missing field '+label);return l.find('input,select,textarea')}
async function open(permissions=['read','report_write','report_review','handover_write','acceptance_write'],data=view){
  vi.mocked(cuttingApi.access).mockResolvedValue({enabled:true,schema_ready:true,orders_schema_ready:true,reporting_schema_ready:true,permissions})
  vi.mocked(ordersApi.list).mockResolvedValue({data:[order],page:1,page_size:50,total:1})
  vi.mocked(reportingApi.read).mockResolvedValue(clone(data))
  router=createRouter({history:createMemoryHistory(),routes:[...cuttingOperationsRoutes,{path:'/modules/production',component:{template:'<div>生产部</div>'}}]})
  await router.push(path);await router.isReady();wrapper=mount(RouterView,{global:{plugins:[router]}});await flushPromises()
  await button('查看填数').trigger('click');await flushPromises()
}
async function form(){await button('填报此任务').trigger('click');await field('本次套数').setValue('10');await field('现场依据').setValue('现场核套人A确认10套');await field('本次提交').setValue('文员填回实际数')}
beforeEach(()=>{vi.resetAllMocks();vi.spyOn(window,'confirm').mockReturnValue(false)})
afterEach(()=>{wrapper?.unmount();vi.restoreAllMocks()})

describe('cutting production facts and save protection',()=>{
  it('posts complete sets immediately without a supervisor approval action',async()=>{
    await open();await form();vi.mocked(reportingApi.command).mockResolvedValue(clone(view))
    await wrapper.get('form.report-form').trigger('submit');await flushPromises()
    expect(reportingApi.command).toHaveBeenCalledWith('line-1','post',expect.objectContaining({expected_version:7,entry:expect.objectContaining({sets:10,mode:'sets',kind:'daily'})}))
    expect(wrapper.text()).toContain('操作已保存')
  })
  it('sends part quantities without pretending they are sets',async()=>{
    await open();await form();await field('报数方式').setValue('parts')
    await wrapper.get('[aria-label="P1合格片数"]').setValue('19');await wrapper.get('[aria-label="P2合格片数"]').setValue('12')
    vi.mocked(reportingApi.command).mockResolvedValue(clone(view));await button('保存草稿').trigger('click');await flushPromises()
    expect(reportingApi.command).toHaveBeenCalledWith('line-1','save',expect.objectContaining({entry:expect.objectContaining({sets:0,mode:'parts',parts:[{code:'P1',good:19,rejected:0,scrap:0},{code:'P2',good:12,rejected:0,scrap:0}]})}))
  })
  it('protects a dirty form from route changes and discard',async()=>{
    await open();await form();await button('取消编辑').trigger('click');expect(wrapper.find('form.report-form').exists()).toBe(true)
    await router.push('/modules/production?factory=huakang-c');expect(router.currentRoute.value.fullPath).toBe(path)
    const e=new Event('beforeunload',{cancelable:true});window.dispatchEvent(e);expect(e.defaultPrevented).toBe(true)
    vi.mocked(window.confirm).mockReturnValue(true);await button('取消编辑').trigger('click');expect(wrapper.find('form.report-form').exists()).toBe(false)
  })
  it.each([401,403,409])('retains unknown results through retry rejection %s',async status=>{
    await open();await form();vi.mocked(reportingApi.command).mockRejectedValueOnce(new Error('timeout')).mockRejectedValueOnce({response:{status}}).mockResolvedValueOnce(clone(view))
    await wrapper.get('form.report-form').trigger('submit');await flushPromises();const original=vi.mocked(reportingApi.command).mock.calls[0]
    await button('重试原操作').trigger('click');await flushPromises();await router.push('/modules/production?factory=huakang-c');expect(router.currentRoute.value.fullPath).toBe(path)
    await button('重试原操作').trigger('click');await flushPromises();expect(vi.mocked(reportingApi.command).mock.calls[2]).toEqual(original)
  })
  it('restores editing after initial 401 followed by definitive business rejection',async()=>{
    await open();await form();vi.mocked(reportingApi.command).mockRejectedValueOnce({response:{status:401}}).mockRejectedValueOnce({response:{status:422,data:{detail:'数量须核对'}}})
    await wrapper.get('form.report-form').trigger('submit');await flushPromises();expect(wrapper.find('form.report-form').exists()).toBe(false)
    await button('重试原操作').trigger('click');await flushPromises();expect(wrapper.find('form.report-form').exists()).toBe(true)
    expect(field('本次套数').element).toHaveProperty('value','10');expect(wrapper.text()).toContain('数量须核对')
  })
  it('fences an unexecuted operation and retains editable draft',async()=>{
    await open();await form();vi.mocked(reportingApi.command).mockRejectedValueOnce(new Error('timeout'))
    await wrapper.get('form.report-form').trigger('submit');await flushPromises()
    vi.mocked(reportingApi.recover).mockResolvedValue({state:'abandoned'});await button('核对保存结果／停止未执行操作').trigger('click');await flushPromises()
    expect(wrapper.text()).toContain('已确认原操作未执行');expect(field('本次套数').element).toHaveProperty('value','10')
  })
  it('keeps read-only users away from write controls',async()=>{
    await open(['read']);expect(wrapper.text()).toContain('未完成套数');expect(wrapper.findAll('button').some(b=>b.text()==='填报此任务')).toBe(false)
  })
  it('uses frozen historical context for remaining handover',async()=>{
    const data=clone(view),t=data.tasks[0]!;t.historical=true;t.mode='sets';t.settlement_context={plan_version:3,dispatch_id:'old',bom_id:'bom',bom_version:2,parts:t.parts,task_name:t.name,task_target:50,resource_id:'r',resource_name:'本厂',execution:'internal',actual_review_pending:false}
    await open(undefined,data);await button('办理历史余额').trigger('click');expect(field('业务类型').element).toHaveProperty('value','handover')
    expect(field('业务类型').findAll('option').some(o=>o.attributes('value')==='daily')).toBe(false)
    await field('本次套数').setValue('3');await field('现场依据').setValue('已交接凭据');await field('本次提交').setValue('历史余额交接')
    vi.mocked(reportingApi.command).mockResolvedValue(data);await wrapper.get('form.report-form').trigger('submit');await flushPromises()
    expect(reportingApi.command).toHaveBeenCalledWith('line-1','post',expect.objectContaining({entry:expect.objectContaining({kind:'handover',plan_version:3})}))
  })
  it('ignores a late order response after a newer selection',async()=>{
    await open();let resolve!: (data:ProductionView)=>void
    vi.mocked(reportingApi.read).mockReturnValueOnce(new Promise(r=>{resolve=r})).mockResolvedValueOnce({...clone(view),version:99})
    await button('查看填数').trigger('click');await button('查看填数').trigger('click');await flushPromises();resolve({...clone(view),version:8});await flushPromises()
    await form();vi.mocked(reportingApi.command).mockResolvedValue(clone(view));await wrapper.get('form.report-form').trigger('submit');await flushPromises()
    expect(reportingApi.command).toHaveBeenCalledWith('line-1','post',expect.objectContaining({expected_version:99}))
  })
  it('shows frozen part identity when a source re-receipt clears the current BOM',async()=>{
    const data=clone(view),t=data.tasks[0]!;t.mode='parts'
    t.settlement_context={plan_version:3,dispatch_id:'old',bom_id:'bom',bom_version:2,parts:clone(t.parts),task_name:t.name,task_target:50,resource_id:'r',resource_name:'原裁剪车间',execution:'internal',actual_review_pending:false}
    t.parts=[]
    await open(undefined,data)
    expect(wrapper.text()).toContain('以下实绩余额归属：原裁剪车间')
    expect(wrapper.text()).toContain('前片 0 片')
    expect(wrapper.text()).toContain('冻结 BOM V2')
  })
})
