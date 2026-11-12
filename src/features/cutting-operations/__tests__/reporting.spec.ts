vi.mock('../workspaceApi',()=>import('./workspaceFixtures'))
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView, type Router } from 'vue-router'
import { cuttingOperationsRoutes } from '../routes'
import { cuttingApi } from '../api'
import { ordersApi, type CuttingOrder } from '../ordersApi'
import { reportingApi, type ProductionView, type ReportKind, type ReportEvent } from '../reportingApi'

vi.mock('@/components/layout/AccountMenu.vue',()=>({default:{template:'<span />'}}))
vi.mock('../api',async original=>({...await original<typeof import('../api')>(),cuttingApi:{access:vi.fn()}}))
vi.mock('../ordersApi',()=>({ordersApi:{list:vi.fn(),read:vi.fn()}}))
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
async function open(permissions=['read','report_write','report_review','handover_write','return_write','acceptance_write'],data=view,orders=[order]){
  vi.mocked(cuttingApi.access).mockResolvedValue({enabled:true,schema_ready:true,orders_schema_ready:true,reporting_schema_ready:true,permissions})
  vi.mocked(ordersApi.list).mockResolvedValue({data:orders,page:1,page_size:50,total:orders.length})
  vi.mocked(reportingApi.read).mockResolvedValue(clone(data))
  router=createRouter({history:createMemoryHistory(),routes:[...cuttingOperationsRoutes,{path:'/modules/production',component:{template:'<div>生产部</div>'}}]})
  await router.push(path);await router.isReady();wrapper=mount(RouterView,{global:{plugins:[router]}});await flushPromises()
  expect(button('选择生产订单').attributes('aria-expanded')).toBe('false')
  expect(wrapper.text()).toContain('当日任务')
  expect(ordersApi.list).not.toHaveBeenCalled()
  await button('选择生产订单').trigger('click');await flushPromises()
  await button('查看记录').trigger('click');await flushPromises()
}
async function form(){await button('填报此任务').trigger('click');await field('本次套数').setValue('10');await field('现场依据').setValue('现场核套人A确认10套');await field('本次提交').setValue('文员填回实际数')}
beforeEach(()=>{vi.resetAllMocks();vi.spyOn(window,'confirm').mockReturnValue(false)})
afterEach(()=>{wrapper?.unmount();vi.restoreAllMocks()})

describe('cutting production facts and save protection',()=>{
  it('restores the chooser selection and applied cutoff from its saved URL',async()=>{
    await open()
    expect(router.currentRoute.value.query).toMatchObject({line_id:order.line_id,day:view.as_of})
    expect(reportingApi.read).toHaveBeenCalledTimes(1)
    const saved=router.currentRoute.value.fullPath
    wrapper.unmount()
    vi.mocked(ordersApi.read).mockResolvedValue(order)
    router=createRouter({history:createMemoryHistory(),routes:cuttingOperationsRoutes})
    await router.push(saved);await router.isReady()
    wrapper=mount(RouterView,{global:{plugins:[router]}});await flushPromises()
    expect(ordersApi.read).toHaveBeenCalledWith(order.line_id)
    expect(reportingApi.read).toHaveBeenLastCalledWith(order.line_id,view.as_of,1,undefined,undefined)
    expect(field('统计截至日期').element).toHaveProperty('value',view.as_of)
    await wrapper.findAll('a').find(link=>link.text()==='返回当日任务')!.trigger('click');await flushPromises()
    expect(router.currentRoute.value.query).toEqual({factory:'huakang-c'})
    expect(wrapper.text()).toContain('当日任务')
  })
  it('returns an out-of-range chooser page to page one using the applied query',async()=>{
    await open()
    await button('选择生产订单').trigger('click');await flushPromises()
    const filter=wrapper.get('form:has([name="order_query"])')
    const input=filter.get('input')
    await input.setValue('CUT')
    const first={data:[order],page:1,page_size:50,total:51}
    vi.mocked(ordersApi.list).mockResolvedValueOnce(first)
    await filter.trigger('submit');await flushPromises()
    await input.setValue('未应用')
    vi.mocked(ordersApi.list).mockResolvedValueOnce({data:[],page:2,page_size:50,total:1})
      .mockResolvedValueOnce({...first,total:1})
    await button('下一页').trigger('click');await flushPromises()
    expect(vi.mocked(ordersApi.list).mock.calls.slice(-2)).toEqual([[2,'CUT','','',false],[1,'CUT','','',false]])
    expect(wrapper.text()).toContain('原第 2 页超出范围，已按原条件返回第 1 页')
    expect(wrapper.text()).toContain('第 1 页 · 共 1 条')
    expect(input.element).toHaveProperty('value','未应用')
    expect(field('统计截至日期').element).toHaveProperty('value',view.as_of)
  })
  it('re-reads the chooser on reopen and separates pending changes from new reporting',async()=>{
    await open()
    const pending=clone(order)
    pending.needs_receipt=true
    pending.source_version=2
    pending.snapshot.quantity='150'
    pending.current!.data.order={version:1,quantity:'120'}
    pending.current!.data.receipt={mode:'automatic',source_version:1,received_at:'2026-11-12T00:32:00Z'}
    vi.mocked(ordersApi.list).mockResolvedValueOnce({data:[pending],page:1,page_size:50,total:1})
    await button('选择生产订单').trigger('click');await flushPromises()
    expect(ordersApi.list).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('变更待确认')
    expect(wrapper.text()).toContain('120 → 150')
    expect(wrapper.text()).toContain('首次下发自动接单 · 下发 V1')
    expect(wrapper.findAll('a').some(link=>link.text()==='前往排期确认')).toBe(true)
    await button('查看原记录').trigger('click');await flushPromises()
    expect(wrapper.text()).toContain('请先在生产排期确认新版本')
    expect(wrapper.findAll('button').some(item=>item.text()==='填报此任务')).toBe(false)
  })
  it('keeps the order and active form when switching record views', async () => {
    await open()
    expect(button('查看记录').attributes('aria-current')).toBe('true')
    await form()
    await button('裁片配套').trigger('click')
    expect(button('裁片配套').attributes('aria-pressed')).toBe('true')
    expect(field('本次套数').element).toHaveProperty('value','10')
    expect(button('查看记录').attributes('aria-current')).toBe('true')
    expect(reportingApi.read).toHaveBeenCalledTimes(1)
  })
  it('uses the successfully applied date for new reports, even after a failed statistics refresh',async()=>{
    await open()
    await field('统计截至日期').setValue('2026-10-09')
    expect(wrapper.text()).toContain('日期尚未应用')
    vi.mocked(reportingApi.read).mockRejectedValueOnce({response:{status:503,data:{detail:'暂时无法读取统计'}}})
    await wrapper.get('form:has([name="statistics_date"])').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('暂时无法读取统计')
    await button('填报此任务').trigger('click')
    expect(field('生产／业务日期').element).toHaveProperty('value','2026-10-10')
    await button('取消编辑').trigger('click')
    vi.mocked(reportingApi.read).mockResolvedValueOnce({...clone(view),as_of:'2026-10-09'})
    await wrapper.get('form:has([name="statistics_date"])').trigger('submit')
    await flushPromises()
    expect(router.currentRoute.value.query.day).toBe('2026-10-09')
    expect(wrapper.text()).not.toContain('日期尚未应用')
    await button('填报此任务').trigger('click')
    expect(field('生产／业务日期').element).toHaveProperty('value','2026-10-09')
  })
  it('starts a different order with its own default statistics date',async()=>{
    const second={...order,line_id:'line-2',snapshot:{...order.snapshot,reference_no:'CUT-2'}}
    await open(undefined,view,[order,second])
    await button('选择生产订单').trigger('click');await flushPromises()
    await field('统计截至日期').setValue('2026-10-09')
    vi.mocked(reportingApi.read).mockResolvedValueOnce({...clone(view),line_id:'line-2',as_of:'2026-10-11'})
    await wrapper.findAll('button').filter(b=>b.text()==='查看记录')[1]!.trigger('click');await flushPromises()
    expect(reportingApi.read).toHaveBeenLastCalledWith('line-2',undefined,1,undefined,undefined)
    expect(field('统计截至日期').element).toHaveProperty('value','2026-10-11')
    await button('填报此任务').trigger('click')
    expect(field('生产／业务日期').element).toHaveProperty('value','2026-10-11')
  })
  it.each(['save','recover'])('keeps the applied cutoff and unapplied date after %s',async(operation)=>{
    await open()
    await wrapper.get('form:has([name="statistics_date"])').trigger('submit');await flushPromises()
    await field('统计截至日期').setValue('2026-10-09')
    await form()
    await field('生产／业务日期').setValue('2026-10-08')
    const saved={...clone(view),version:8}
    if(operation==='recover'){
      vi.mocked(reportingApi.command).mockRejectedValueOnce(new Error('timeout'))
      vi.mocked(reportingApi.recover).mockResolvedValue({state:'committed',result:{...saved,as_of:'2026-10-11'}})
      vi.mocked(reportingApi.read).mockResolvedValueOnce(saved)
    }else vi.mocked(reportingApi.command).mockResolvedValueOnce(saved)
    await button('保存草稿').trigger('click');await flushPromises()
    expect(reportingApi.command).toHaveBeenCalledWith('line-1','save',expect.objectContaining({entry:expect.objectContaining({day:'2026-10-08'})}),'2026-10-10')
    if(operation==='recover'){
      await button('核对保存结果／停止未执行操作').trigger('click');await flushPromises()
      expect(reportingApi.read).toHaveBeenLastCalledWith('line-1','2026-10-10',1,undefined,undefined)
    }
    expect(router.currentRoute.value.query.day).toBe('2026-10-10')
    expect(field('统计截至日期').element).toHaveProperty('value','2026-10-09')
    expect(wrapper.text()).toContain('日期尚未应用')
    expect(wrapper.find('form.report-form').exists()).toBe(false)
  })
  it('preserves draft fields across history pages and rejects late history after a successful post',async()=>{
    const first=clone(view);first.history_pagination={page:1,page_size:20,total:45}
    await open(undefined,first);await form()
    let resolve!:(v:ProductionView)=>void
    vi.mocked(reportingApi.read).mockReturnValueOnce(new Promise(r=>resolve=r))
    await button('下一页历史').trigger('click');await flushPromises()
    expect(field('本次套数').element).toHaveProperty('value','10')
    expect(reportingApi.read).toHaveBeenLastCalledWith('line-1',first.as_of,2,7)
    const committed=clone(first);committed.version=8;committed.summary.completed=10
    vi.mocked(reportingApi.command).mockResolvedValue(committed)
    await wrapper.get('form.report-form').trigger('submit');await flushPromises()
    resolve({...first,history_pagination:{page:2,page_size:20,total:45}});await flushPromises()
    expect(wrapper.text()).toContain('第 1 页 · 共 45')
    expect(wrapper.text()).not.toContain('正在读取生产记录')
    expect(wrapper.text()).toContain('操作已保存')
  })
  it('retains current page and input after a history version conflict',async()=>{
    const data=clone(view);data.history_pagination={page:1,page_size:20,total:45}
    await open(undefined,data);await form()
    vi.mocked(reportingApi.read).mockRejectedValueOnce({response:{status:409,data:{detail:'生产记录已变化，请刷新'}}})
    await button('下一页历史').trigger('click');await flushPromises()
    expect(wrapper.text()).toContain('生产记录已变化')
    expect(field('本次套数').element).toHaveProperty('value','10')
    expect(wrapper.text()).toContain('第 1 页 · 共 45')
  })
  it.each([['return_write','return'],['acceptance_write','accept']] as const)('limits %s to its own external flow and selects it by default',async(permission,kind)=>{
    const data=clone(view);data.tasks[0]!.execution='outsourced'
    await open(['read',permission],data)
    await button('填报此任务').trigger('click')
    expect(field('业务类型').findAll('option').map(o=>o.attributes('value'))).toEqual([kind])
    expect(field('业务类型').element).toHaveProperty('value',kind)
    await field(kind==='accept'?'验收合格套数':'本次套数').setValue('5')
    await field('现场依据').setValue('外发凭据');await field('本次提交').setValue('独立岗位登记')
    vi.mocked(reportingApi.command).mockResolvedValue(data)
    await wrapper.get('form.report-form').trigger('submit');await flushPromises()
    expect(reportingApi.command).toHaveBeenCalledWith('line-1','post',expect.objectContaining({entry:expect.objectContaining({kind,sets:5})}),'2026-10-10')
  })
  it.each(['return_write','acceptance_write'])('does not offer internal tasks to a %s-only operator',async permission=>{
    await open(['read',permission])
    expect(wrapper.findAll('button').some(b=>b.text()==='填报此任务')).toBe(false)
  })
  it.each([['return_write','return'],['acceptance_write','accept']] as const)('gates historical corrections, void and draft discard by %s',async(permission,kind)=>{
    const data=clone(view),t=data.tasks[0]!;t.execution='outsourced';t.historical=true
    t.settlement_context={plan_version:3,dispatch_id:'old',bom_id:'bom',bom_version:2,parts:t.parts,task_name:t.name,task_target:50,resource_id:'r',resource_name:'外厂',execution:'outsourced',actual_review_pending:false}
    data.documents=(['return','accept'] as ReportKind[]).map((k,i)=>{
      const event:ReportEvent={id:k,version:i+1,document_id:k,action:'post',actor_id:'old-user',created_at:'',reason:'历史记录',data:{context:t.settlement_context!,entry:{task_id:t.task_id,plan_version:3,day:'2026-10-10',mode:'sets',kind:k,sets:5,rejected:0,scrap:0,parts:[],evidence:'原凭据',exception_reason:''}}}
      return {document_id:k,posted:event,draft:{...event,action:'save'},review:null,voided:false,history:[event],first_version:i+1}
    })
    await open(['read',permission],data)
    const own=wrapper.get(`[data-cutting-report="${kind}"]`),other=wrapper.get(`[data-cutting-report="${kind==='return'?'accept':'return'}"]`)
    expect(own.findAll('button').map(b=>b.text())).toEqual(['编辑／更正','放弃草稿','作废'])
    expect(other.findAll('button')).toHaveLength(0)
    await button('办理历史余额').trigger('click')
    expect(field('业务类型').element).toHaveProperty('value',kind)
    await button('取消编辑').trigger('click')
    await own.findAll('button')[0]!.trigger('click')
    await field(kind==='accept'?'验收合格套数':'本次套数').setValue('4')
    await field('本次提交').setValue('更正凭据')
    vi.mocked(reportingApi.command).mockResolvedValue(data)
    await wrapper.get('form.report-form').trigger('submit');await flushPromises()
    expect(reportingApi.command).toHaveBeenCalledWith('line-1','post',expect.objectContaining({document_id:kind,entry:expect.objectContaining({kind,sets:4,plan_version:3})}),'2026-10-10')
  })
  it('keeps an unsaved report when query navigation to a monthly target is rejected',async()=>{
    await open();await form()
    await router.push(path+'&line_id=another-order&month=2026-09&focus_kind=task&focus_id=other')
    await flushPromises()
    expect(window.confirm).toHaveBeenCalled()
    expect(router.currentRoute.value.query).toMatchObject({line_id:order.line_id,day:view.as_of})
    expect((field('本次套数').element as HTMLInputElement).value).toBe('10')
    expect(reportingApi.read).toHaveBeenCalledTimes(1)
  })
  it('posts complete sets immediately without a supervisor approval action',async()=>{
    await open();await form();vi.mocked(reportingApi.command).mockResolvedValue(clone(view))
    await wrapper.get('form.report-form').trigger('submit');await flushPromises()
    expect(reportingApi.command).toHaveBeenCalledWith('line-1','post',expect.objectContaining({expected_version:7,entry:expect.objectContaining({sets:10,mode:'sets',kind:'daily'})}),'2026-10-10')
    expect(wrapper.text()).toContain('操作已保存')
  })
  it('sends part quantities without pretending they are sets',async()=>{
    await open();await form();await field('报数方式').setValue('parts')
    await wrapper.get('[aria-label="P1合格片数"]').setValue('19');await wrapper.get('[aria-label="P2合格片数"]').setValue('12')
    vi.mocked(reportingApi.command).mockResolvedValue(clone(view));await button('保存草稿').trigger('click');await flushPromises()
    expect(reportingApi.command).toHaveBeenCalledWith('line-1','save',expect.objectContaining({entry:expect.objectContaining({sets:0,mode:'parts',parts:[{code:'P1',good:19,rejected:0,scrap:0},{code:'P2',good:12,rejected:0,scrap:0}]})}),'2026-10-10')
  })
  it('validates a pasted batch before applying it to the current parts form',async()=>{
    await open()
    await button('填报此任务').trigger('click')
    await field('报数方式').setValue('parts')
    const controls=wrapper.findAll('input, select, textarea').map(({element})=>element as HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement)
    expect(controls.length).toBeGreaterThan(6)
    expect(controls.every(control=>control.id && control.name && (control.labels?.length || control.getAttribute('aria-label')))).toBe(true)
    expect(new Set(controls.map(control=>control.id)).size).toBe(controls.length)
    const good=wrapper.get('[aria-label="P1合格片数"]')
    expect(good.attributes('name')).toBe('part_good_P1')
    await good.setValue('7')
    await field('粘贴裁片明细').setValue('P1\t19\t0\t0\nP1\t12\t0\t0')
    await button('校验并预览').trigger('click')
    expect(wrapper.text()).toContain('第 2 行部件编码「P1」重复')
    expect(button('保存草稿').attributes('disabled')).toBeDefined()
    expect(good.element).toHaveProperty('value','7')
    await field('粘贴裁片明细').setValue('部件编码\t合格新增片数\t不良片数\t报废片数\r\nP2\t12\t1\t0')
    await button('校验并预览').trigger('click')
    expect(wrapper.get('[aria-label="裁片粘贴预览"]').text()).toContain('P21210')
    await field('生产／业务日期').setValue('2026-10-09')
    expect(wrapper.find('[aria-label="裁片粘贴预览"]').exists()).toBe(false)
    await button('校验并预览').trigger('click')
    await button('应用到当前填报').trigger('click')
    expect(wrapper.get('[aria-label="P2合格片数"]').element).toHaveProperty('value','12')
    expect(good.element).toHaveProperty('value','7')
    expect(button('保存草稿').attributes('disabled')).toBeUndefined()
    expect(reportingApi.command).not.toHaveBeenCalled()
  })
  it('protects a dirty form from route changes and discard',async()=>{
    await open();await form();await button('取消编辑').trigger('click');expect(wrapper.find('form.report-form').exists()).toBe(true)
    const selectedPath=router.currentRoute.value.fullPath
    await router.push('/modules/production?factory=huakang-c');expect(router.currentRoute.value.fullPath).toBe(selectedPath)
    const e=new Event('beforeunload',{cancelable:true});window.dispatchEvent(e);expect(e.defaultPrevented).toBe(true)
    vi.mocked(window.confirm).mockReturnValue(true);await button('取消编辑').trigger('click');expect(wrapper.find('form.report-form').exists()).toBe(false)
  })
  it.each([401,403,409])('retains unknown results through retry rejection %s',async status=>{
    await open();await form();vi.mocked(reportingApi.command).mockRejectedValueOnce(new Error('timeout')).mockRejectedValueOnce({response:{status}}).mockResolvedValueOnce(clone(view))
    const selectedPath=router.currentRoute.value.fullPath
    await wrapper.get('form.report-form').trigger('submit');await flushPromises();const original=vi.mocked(reportingApi.command).mock.calls[0]
    await button('重试原操作').trigger('click');await flushPromises();await router.push('/modules/production?factory=huakang-c');expect(router.currentRoute.value.fullPath).toBe(selectedPath)
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
    await open(['read']);expect(wrapper.get('.report-totals').text()).toContain('未完成');expect(wrapper.findAll('button').some(b=>b.text()==='填报此任务')).toBe(false)
  })
  it('uses frozen historical context for remaining handover',async()=>{
    const data=clone(view),t=data.tasks[0]!;t.historical=true;t.mode='sets';t.settlement_context={plan_version:3,dispatch_id:'old',bom_id:'bom',bom_version:2,parts:t.parts,task_name:t.name,task_target:50,resource_id:'r',resource_name:'本厂',execution:'internal',actual_review_pending:false}
    await open(undefined,data);await button('办理历史余额').trigger('click');expect(field('业务类型').element).toHaveProperty('value','handover')
    expect(field('业务类型').findAll('option').some(o=>o.attributes('value')==='daily')).toBe(false)
    await field('本次套数').setValue('3');await field('现场依据').setValue('已交接凭据');await field('本次提交').setValue('历史余额交接')
    vi.mocked(reportingApi.command).mockResolvedValue(data);await wrapper.get('form.report-form').trigger('submit');await flushPromises()
    expect(reportingApi.command).toHaveBeenCalledWith('line-1','post',expect.objectContaining({entry:expect.objectContaining({kind:'handover',plan_version:3})}),'2026-10-10')
  })
  it('ignores a late order response after a newer selection',async()=>{
    await open();let resolve!: (data:ProductionView)=>void
    vi.mocked(reportingApi.read).mockReturnValueOnce(new Promise(r=>{resolve=r})).mockResolvedValueOnce({...clone(view),version:99})
    await button('查看记录').trigger('click');await button('查看记录').trigger('click');await flushPromises();resolve({...clone(view),version:8});await flushPromises()
    await form();vi.mocked(reportingApi.command).mockResolvedValue(clone(view));await wrapper.get('form.report-form').trigger('submit');await flushPromises()
    expect(reportingApi.command).toHaveBeenCalledWith('line-1','post',expect.objectContaining({expected_version:99}),'2026-10-10')
  })
  it('shows frozen part identity when a source re-receipt clears the current BOM',async()=>{
    const data=clone(view),t=data.tasks[0]!;t.mode='parts'
    t.settlement_context={plan_version:3,dispatch_id:'old',bom_id:'bom',bom_version:2,parts:clone(t.parts),task_name:t.name,task_target:50,resource_id:'r',resource_name:'原裁剪车间',execution:'internal',actual_review_pending:false}
    t.parts=[]
    await open(undefined,data)
    expect(wrapper.text()).toContain('以下实绩余额归属：原裁剪车间')
    expect(wrapper.text()).toContain('前片余 0 片')
    expect(wrapper.text()).toContain('冻结 BOM V2')
  })
})
