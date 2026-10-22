vi.mock('../workspaceApi',()=>import('./workspaceFixtures'))
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import CuttingClosingPage from '../CuttingClosingPage.vue'
import { CUTTING_WORKSPACES } from '../navigation'
import { cuttingApi, type Access } from '../api'
import { ordersApi, type CuttingOrder } from '../ordersApi'
import { closingApi, type ClosingPreview } from '../closingApi'
import { settlementApi, type FeeRecord } from '../settlementApi'
import { paymentApi, type PaymentRecord } from '../paymentApi'
import { periodApi } from '../periodApi'
vi.mock('../periodApi',()=>({periodApi:{read:vi.fn()}}))
vi.mock('../api',async original=>({...await original<typeof import('../api')>(),cuttingApi:{access:vi.fn()}}))
vi.mock('../ordersApi',()=>({ordersApi:{list:vi.fn(),read:vi.fn()}}))
vi.mock('../closingApi',()=>({closingApi:{read:vi.fn()}}))
vi.mock('../settlementApi',()=>({settlementApi:{read:vi.fn()}}))
vi.mock('../paymentApi',()=>({paymentApi:{read:vi.fn()}}))
const rights:Access={enabled:true,schema_ready:true,orders_schema_ready:true,reporting_schema_ready:true,usage_schema_ready:true,permissions:['read','cost_read']}
const order:CuttingOrder={line_id:'line',dispatch_id:'d',source_version:1,snapshot:{reference_no:'ORDER-1',product_no:'P1',customer_name:'合成客户'},received_at:'',needs_receipt:false,current:{version:1,actor_id:'a',created_at:'',reason:'',data:{order:{},dispatch_id:'d',bom:null,requisition:null,batches:[],purchase_reconciliation_required:false}}}
const snapshot:ClosingPreview={line_id:'line',month:'2026-10',start:'2026-10-01',end:'2026-10-31',through:'2026-10-15',generated_at:'2026-10-15T12:00:00+08:00',state:'preview',partial:true,basis:{order_version:1,plan_version:2,usage_revision:3,warehouse_revision:4},production:[],materials:[],issues:[],production_documents:[],usage_documents:[],warehouse_documents:[],costs:{CNY:{normal:'16.25',loss:'2.00'}},pending_pricing:0,wip_status:'not_frozen',current_allocation_review:[]}
let wrapper:VueWrapper
const button=(text:string)=>wrapper.findAll('button').find(b=>b.text()===text)!
async function open(path='/'){const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:CuttingClosingPage,props:{workspace:CUTTING_WORKSPACES.find(w=>w.path==='closing')}},{path:'/away',component:{template:'<div>其他工作区</div>'}}]});await router.push(path);await router.isReady();wrapper=mount(RouterView,{global:{plugins:[router]}});await flushPromises();return router}
beforeEach(()=>{vi.resetAllMocks();vi.mocked(cuttingApi.access).mockResolvedValue(rights);vi.mocked(ordersApi.list).mockResolvedValue({data:[order],total:1,page:1,page_size:50});vi.mocked(closingApi.read).mockResolvedValue(snapshot)})
afterEach(()=>{wrapper?.unmount();vi.restoreAllMocks()})
describe('P4a monthly reconciliation',()=>{
  it.each(['period','settlement','payment'] as const)('retries the exact failed historical %s target and separates a manual current read',async kind=>{
    vi.mocked(cuttingApi.access).mockResolvedValue({...rights,periods_schema_ready:true,settlements_schema_ready:true,payments_schema_ready:true,permissions:['read','cost_read','settlement_read','payment_read']})
    const api=kind==='period'?periodApi:kind==='settlement'?settlementApi:paymentApi
    if(kind==='period')vi.mocked(periodApi.read).mockResolvedValue({month:'2026-09',revision:0,state:'open',selected_state:'open',event_id:null,data:null,history:[],locked_months:[]})
    if(kind==='settlement')vi.mocked(settlementApi.read).mockResolvedValue({revision:0,document_id:null,state:'open',selected_state:'open',event_id:null,statements:[],data:null,history:[],price_history:[]})
    if(kind==='payment')vi.mocked(paymentApi.read).mockResolvedValue({month:'2026-09',revision:0,rows:[],totals:[],documents:[],document_id:null,state:'open',selected_state:'open',event_id:null,data:null,history:[],replacements:[]})
    vi.mocked(api.read).mockRejectedValueOnce(new Error('offline')).mockRejectedValueOnce(new Error('still offline'))
    await open(`/?factory=huakang-c&view=${kind}&month=2026-09&document_id=original-doc&event_id=original-event`)
    const retry=kind==='period'?'重试原月结记录':kind==='settlement'?'重试原结算记录':'重试原付款记录'
    const expected=kind==='period'?['2026-09','original-event']:['2026-09','original-doc','original-event']
    await button(retry).trigger('click');await flushPromises()
    expect(api.read).toHaveBeenLastCalledWith(...expected)
    expect(button(retry)).toBeDefined()
    await button(retry).trigger('click');await flushPromises()
    expect(api.read).toHaveBeenLastCalledWith(...expected)
    expect(button(retry)).toBeUndefined()
    const generic=kind==='period'?'读取月结记录':kind==='settlement'?'读取外发结算':'读取付款登记'
    await button(generic).trigger('click');await flushPromises()
    expect(vi.mocked(api.read).mock.calls.at(-1)).toEqual(kind==='period'?['2026-09',undefined]:['2026-09',undefined,undefined])
  })
  it.each(['period','settlement','payment'] as const)('clears the failed %s read target after an explicit authorization denial',async kind=>{
    vi.mocked(cuttingApi.access).mockResolvedValue({...rights,periods_schema_ready:true,settlements_schema_ready:true,payments_schema_ready:true,permissions:['read','cost_read','settlement_read','payment_read']})
    const api=kind==='period'?periodApi:kind==='settlement'?settlementApi:paymentApi
    vi.mocked(api.read).mockRejectedValueOnce(new Error('offline')).mockRejectedValueOnce({response:{status:403}})
    await open(`/?factory=huakang-c&view=${kind}&month=2026-09&document_id=private-doc&event_id=private-event`)
    const retry=kind==='period'?'重试原月结记录':kind==='settlement'?'重试原结算记录':'重试原付款记录'
    await button(retry).trigger('click');await flushPromises()
    expect(button(retry)).toBeUndefined()
  })
  it('does not replay a pending historical link after the user explicitly chooses another view',async()=>{
    let resolve!:(value:Access)=>void
    vi.mocked(cuttingApi.access).mockReturnValueOnce(new Promise(r=>resolve=r))
    await open('/?factory=huakang-c&view=period&month=2026-08')
    await button('冻结报表').trigger('click')
    resolve({...rights,periods_schema_ready:true});await flushPromises()
    expect(periodApi.read).not.toHaveBeenCalled()
    expect(button('冻结报表').attributes('aria-pressed')).toBe('true')
  })
  it('recovers a historical month and frozen event after a failed initial access read',async()=>{
    vi.mocked(cuttingApi.access).mockRejectedValueOnce(new Error('offline')).mockResolvedValue({...rights,periods_schema_ready:true})
    vi.mocked(periodApi.read).mockImplementation(async month=>({month,revision:0,state:'open',selected_state:'open',event_id:null,data:null,history:[],locked_months:[]}))
    await open('/?factory=huakang-c&view=period&month=2026-08&event_id=frozen-august')
    expect(periodApi.read).not.toHaveBeenCalled()
    await button('重新读取月结工作区').trigger('click');await flushPromises()
    expect(periodApi.read).toHaveBeenCalledWith('2026-08','frozen-august')
    expect(wrapper.findComponent({name:'CuttingMonthlyOverview'}).props('month')).toBe('2026-08')
  })
  it('retries failed order-list loading before restoring the exact historical payment document',async()=>{
    vi.mocked(cuttingApi.access).mockResolvedValue({...rights,payments_schema_ready:true,permissions:['read','payment_read']})
    vi.mocked(ordersApi.list).mockRejectedValueOnce(new Error('offline')).mockResolvedValue({data:[order],total:1,page:1,page_size:50})
    vi.mocked(paymentApi.read).mockResolvedValue({month:'2026-08',current_month:'2026-09',revision:1,rows:[],totals:[],documents:[],document_id:'payment-8',state:'open',selected_state:'open',event_id:null,data:null,history:[],replacements:[]})
    await open('/?factory=huakang-c&view=payment&month=2026-08&document_id=payment-8&event_id=old-payment-event')
    expect(paymentApi.read).not.toHaveBeenCalled()
    await button('重新读取月结工作区').trigger('click');await flushPromises()
    expect(paymentApi.read).toHaveBeenCalledWith('2026-08','payment-8','old-payment-event')
  })
  it('synchronizes a financial deep link without an order to overview, exports and tab reentry',async()=>{
    vi.mocked(cuttingApi.access).mockResolvedValue({...rights,periods_schema_ready:true})
    vi.mocked(periodApi.read).mockImplementation(async month=>({month,revision:0,state:'open',selected_state:'open',event_id:null,data:null,history:[],locked_months:[]}))
    await open('/?factory=huakang-c&view=period&month=2026-08')
    expect((wrapper.get('[aria-label="核对月份"]').element as HTMLInputElement).value).toBe('2026-08')
    await button('月结总览').trigger('click');await flushPromises()
    await button('冻结报表').trigger('click');await flushPromises()
    expect(wrapper.findComponent({name:'CuttingMonthlyOverview'}).props('month')).toBe('2026-08')
    await button('内部月结').trigger('click');await flushPromises()
    expect((wrapper.findComponent({name:'CuttingPeriodClosing'}).get('input[type=month]').element as HTMLInputElement).value).toBe('2026-08')
  })

  it('does not change overview month or discard a reason when an in-page historical switch is cancelled',async()=>{
    vi.mocked(cuttingApi.access).mockResolvedValue({...rights,periods_schema_ready:true})
    vi.mocked(periodApi.read).mockImplementation(async month=>({month,revision:0,state:'open',selected_state:'open',event_id:null,data:null,history:[],locked_months:[]}))
    await open('/?factory=huakang-c&view=period&month=2026-08')
    await wrapper.get('input[maxlength="500"]').setValue('八月尚未保存的依据')
    await button('月结总览').trigger('click');await flushPromises()
    vi.spyOn(window,'confirm').mockReturnValue(false)
    wrapper.findComponent({name:'CuttingMonthlyOverview'}).vm.$emit('open','period','2026-09','')
    await flushPromises()
    expect((wrapper.get('[aria-label="核对月份"]').element as HTMLInputElement).value).toBe('2026-08')
    expect(wrapper.get('input[maxlength="500"]').element.value).toBe('八月尚未保存的依据')
    expect(periodApi.read).not.toHaveBeenCalledWith('2026-09',undefined)
  })

  it('asks once for a committed same-route cross-month link and keeps cancelled navigation intact',async()=>{
    vi.mocked(cuttingApi.access).mockResolvedValue({...rights,periods_schema_ready:true})
    vi.mocked(periodApi.read).mockImplementation(async month=>({month,revision:0,state:'open',selected_state:'open',event_id:null,data:null,history:[],locked_months:[]}))
    const router=await open('/?factory=huakang-c&view=period&month=2026-08')
    await wrapper.get('input[maxlength="500"]').setValue('八月复核依据')
    const confirm=vi.spyOn(window,'confirm').mockReturnValue(false)
    await router.push('/?factory=huakang-c&view=period&month=2026-09');await flushPromises()
    expect(router.currentRoute.value.query.month).toBe('2026-08')
    expect(wrapper.get('input[maxlength="500"]').element.value).toBe('八月复核依据')
    confirm.mockReturnValue(true).mockClear()
    await router.push('/?factory=huakang-c&view=period&month=2026-09');await flushPromises()
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(periodApi.read).toHaveBeenLastCalledWith('2026-09',undefined)
    expect(wrapper.get('input[maxlength="500"]').element.value).toBe('')
  })

  it('awaits parent authorization before opening a same-route payment trace',async()=>{
    const granted={...rights,payments_schema_ready:true,permissions:['read','payment_read']}
    vi.mocked(cuttingApi.access).mockResolvedValue(granted)
    const router=await open()
    let resolve!:(value:Access)=>void
    vi.mocked(cuttingApi.access).mockReturnValueOnce(new Promise(r=>resolve=r))
    const payment:PaymentRecord={month:'2026-09',current_month:'2026-09',revision:1,rows:[],totals:[],documents:[],document_id:'payment-9',state:'open',selected_state:'open',event_id:null,data:null,history:[],replacements:[]}
    vi.mocked(paymentApi.read).mockResolvedValue(payment)
    await router.push('/?factory=huakang-c&view=payment&month=2026-09&document_id=payment-9')
    await flushPromises()
    expect(paymentApi.read).not.toHaveBeenCalled()
    resolve(granted);await flushPromises()
    expect(paymentApi.read).toHaveBeenCalledWith('2026-09','payment-9',undefined)
  })
  it('pages complete scoped traces without changing the parent totals and reports conflicts',async()=>{
    const data={...snapshot,history_pagination:{page:1,page_size:20,total:45,scope:'all' as const,token:'evidence'}}
    vi.mocked(closingApi.read).mockResolvedValue(data)
    await open();await button('月度核对').trigger('click');await flushPromises()
    await button('来源及更正追溯').trigger('click')
    vi.mocked(closingApi.read).mockResolvedValueOnce({...data,history_pagination:{...data.history_pagination,page:2}})
    await button('下一页历史').trigger('click');await flushPromises()
    expect(closingApi.read).toHaveBeenLastCalledWith('line','2026-10',true,2,'all','evidence')
    expect(wrapper.text()).toContain('第 2 页 · 共 45')
    vi.mocked(closingApi.read).mockRejectedValueOnce({response:{status:409,data:{detail:'核对依据已变化，请刷新'}}})
    await button('下一页历史').trigger('click');await flushPromises()
    expect(wrapper.text()).toContain('核对依据已变化')
    expect(wrapper.text()).toContain('第 2 页 · 共 45')
  })
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
    await wrapper.get('input[aria-label="核对月份"]').setValue('2026-09')
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

it('opens the actual payment panel from a settlement blocker in another month',async()=>{
  vi.mocked(cuttingApi.access).mockResolvedValue({...rights,settlements_schema_ready:true,payments_schema_ready:true,permissions:['read','settlement_read','payment_read']})
  const fee:FeeRecord={revision:1,document_id:'fee-1',state:'confirmed',selected_state:'confirmed',event_id:'fee-event',statements:[],history:[{id:'fee-event',action:'confirm',version:1,actor:'甲',actor_id:'a',date:'2026-10-16',reason:'核对'}],price_history:[],payment_dependencies:[{document_id:'payment-9',month:'2026-09',state:'confirmed',amount:'5.00',currency:'CNY',voucher_no:'PAY-09'}],data:{input:{factory_id:'huakang-c',operation_id:'o',expected_version:0,reason:'依据',document_id:'fee-1',month:'2026-10',basis_token:'b',selections:[],vendor_evidence:'已核对'},snapshot:{month:'2026-10',cutoff:'2026-10-16',resource_id:'v',resource_name:'外厂甲',currency:'CNY',rows:[],sets:1,total:'5.00',tax_basis:'inclusive',vendor_evidence:'已核对'},prepared_by:'a',submitted_by:'a',replaces_id:null}}
  const payment:PaymentRecord={month:'2026-09',current_month:'2026-09',revision:1,rows:[],totals:[],documents:[],document_id:'payment-9',state:'open',selected_state:'open',event_id:null,data:null,history:[],replacements:[]}
  vi.mocked(settlementApi.read).mockResolvedValue(fee);vi.mocked(paymentApi.read).mockResolvedValue(payment)
  await open();await button('读取外发结算').trigger('click');await flushPromises()
  await button('定位占用付款').trigger('click');await flushPromises()
  expect(paymentApi.read).toHaveBeenCalledWith('2026-09','payment-9',undefined)
  expect(wrapper.findAll('label').find(label=>label.text()==='付款月份')!.get('input').element.value).toBe('2026-09')
  expect(wrapper.findComponent({name:'CuttingMonthlyOverview'}).props('month')).toBe('2026-09')
})
