import { beforeEach,afterEach,it,expect,vi } from 'vitest'
import { mount,flushPromises,type VueWrapper } from '@vue/test-utils'
import { createRouter,createMemoryHistory,RouterView } from 'vue-router'
import Closing from '../CuttingClosingPage.vue'
import { CUTTING_WORKSPACES } from '../navigation'
import { cuttingApi,type Access } from '../api'
import { ordersApi } from '../ordersApi'
import { periodApi } from '../periodApi'
import { settlementApi } from '../settlementApi'
import { paymentApi } from '../paymentApi'
vi.mock('../api',()=>({cuttingApi:{access:vi.fn()},errorMessage:()=> '读取失败'}))
vi.mock('../ordersApi',()=>({ordersApi:{list:vi.fn(),read:vi.fn()}}))
vi.mock('../closingApi',()=>({closingApi:{read:vi.fn()}}))
vi.mock('../periodApi',()=>({periodApi:{read:vi.fn()}}))
vi.mock('../settlementApi',()=>({settlementApi:{read:vi.fn()}}))
vi.mock('../paymentApi',()=>({paymentApi:{read:vi.fn()}}))
type Kind='period'|'settlement'|'payment'
const rights:Access={enabled:true,schema_ready:true,orders_schema_ready:true,reporting_schema_ready:true,usage_schema_ready:true,periods_schema_ready:true,settlements_schema_ready:true,payments_schema_ready:true,permissions:['read','cost_read','settlement_read','payment_read']}
const tabs={period:'内部月结',settlement:'外发对账与结算',payment:'付款与核销'}
const retries={period:'重试原月结记录',settlement:'重试原结算记录',payment:'重试原付款记录'}
const apis={period:periodApi,settlement:settlementApi,payment:paymentApi}
const records={
 period:{month:'2026-09',revision:0,state:'open',selected_state:'open',event_id:'chosen-event',data:null,history:[],locked_months:[]},
 settlement:{revision:0,document_id:'chosen-doc',state:'open',selected_state:'open',event_id:'chosen-event',statements:[],data:null,history:[],price_history:[]},
 payment:{month:'2026-09',revision:0,rows:[],totals:[],documents:[],document_id:'chosen-doc',state:'open',selected_state:'open',event_id:'chosen-event',data:null,history:[],replacements:[]},
}
let wrapper:VueWrapper|undefined
const button=(text:string)=>wrapper!.findAll('button').find(b=>b.text()===text)!
const parentMonth=()=>wrapper!.get('[aria-label="核对月份"]')
beforeEach(()=>{vi.resetAllMocks();vi.mocked(cuttingApi.access).mockResolvedValue(rights);vi.mocked(ordersApi.list).mockResolvedValue({data:[],total:0,page:1,page_size:50})})
afterEach(()=>wrapper?.unmount())
async function interrupted(kind:Kind){
 let reject!:(value:unknown)=>void
 vi.mocked(apis[kind].read).mockImplementationOnce(()=>new Promise((_resolve,r)=>reject=r)).mockResolvedValue(records[kind] as never)
 const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:Closing,props:{workspace:CUTTING_WORKSPACES.find(w=>w.path==='closing')!}}]})
 await router.push(`/?factory=huakang-c&view=${kind}&month=2026-09&document_id=chosen-doc&event_id=chosen-event`);await router.isReady()
 wrapper=mount(RouterView,{global:{plugins:[router],stubs:{CuttingMonthlyOverview:true,CuttingCutover:true,CuttingReportExport:true,CuttingPeriodReview:true}}});await flushPromises()
 await button('月结总览').trigger('click')
 await wrapper.findAll('form').find(f=>f.findAll('button').some(b=>b.text()==='查询订单'))!.trigger('submit');await flushPromises()
 reject(new Error('late failure'));await flushPromises()
 await button(tabs[kind]).trigger('click');await flushPromises()
}
it.each(['period','settlement','payment'] as Kind[])('synchronizes exact %s retry and retains selection across repeated overview/export reentry',async kind=>{
 await interrupted(kind);await button(retries[kind]).trigger('click');await flushPromises()
 expect((parentMonth().element as HTMLInputElement).value).toBe('2026-09')
 const reader=wrapper!.findAll('input[type=month]').find(e=>e.element.closest('section')?.textContent?.includes(kind==='period'?'内部月结与锁月':kind==='settlement'?'外发加工费对账与结算':'外发加工费付款登记与核销'))!
 for(const next of ['月结总览','冻结报表','月结总览']){await button(next).trigger('click');await button(tabs[kind]).trigger('click');await flushPromises();expect((reader.element as HTMLInputElement).value).toBe('2026-09')}
 expect(apis[kind].read).toHaveBeenCalledTimes(2)
 expect(apis[kind].read).toHaveBeenLastCalledWith(...(kind==='period'?['2026-09','chosen-event']:['2026-09','chosen-doc','chosen-event']))
})
it.each(['period','settlement','payment'] as Kind[])('never overrides a newer overview month after %s retry starts',async kind=>{
 await interrupted(kind)
 let resolve!:(value:never)=>void
 vi.mocked(apis[kind].read).mockImplementationOnce(()=>new Promise(r=>resolve=r))
 await button(retries[kind]).trigger('click');await flushPromises()
 await button('月结总览').trigger('click');await parentMonth().setValue('2026-08');await button(tabs[kind]).trigger('click');await flushPromises()
 resolve(records[kind] as never);await flushPromises()
 expect((parentMonth().element as HTMLInputElement).value).toBe('2026-08')
})
