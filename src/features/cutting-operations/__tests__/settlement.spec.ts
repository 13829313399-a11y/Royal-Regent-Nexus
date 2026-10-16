import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { defineComponent } from 'vue'
import CuttingSettlement from '../CuttingSettlement.vue'
import { cuttingApi, type Access } from '../api'
import { settlementApi, type FeeBasis, type FeeRecord, type FeeSave } from '../settlementApi'

vi.mock('../api',()=>({cuttingApi:{access:vi.fn()},errorMessage:()=> '请求被拒绝或未完成'}))
vi.mock('../settlementApi',()=>({settlementApi:{read:vi.fn(),basis:vi.fn(),write:vi.fn(),recover:vi.fn(),preview:vi.fn()}}))
const access:Access={enabled:true,schema_ready:true,settlements_schema_ready:true,permissions:['read','settlement_read','settlement_price','settlement_prepare','settlement_confirm','settlement_reopen']}
const record:FeeRecord={revision:1,document_id:null,state:'open',selected_state:'open',event_id:null,data:null,history:[],statements:[],price_history:[]}
const basis:FeeBasis={month:'2026-10',cutoff:'2026-10-16',revision:1,basis_token:'basis-1',rows:[{
  line_id:'line-1',task_id:'external',acceptance_id:'acceptance-1',acceptance_event_id:'event-1',day:'2026-10-15',accepted_sets:20,reserved_sets:5,available_sets:15,task_remaining_sets:20,
  correction_pending:false,context_token:'context-1',context:{task_name:'裁剪任务',resource_name:'外厂甲',resource_id:'resource-1',task_target:25,bom_id:'bom-1',bom_version:2,plan_version:3},
  order:{customer_name:'客户甲',reference_no:'ORDER-01',product_no:'P01'},acceptance_evidence:'验收凭据',acceptance_actor:'文员',acceptance_date:'2026-10-15',
  price:{id:'price-1',version:1,actor:'主管',actor_id:'supervisor',date:'2026-10-15',reason:'确认报价',unit_price:'1.25',currency:'CNY',evidence:'含税报价凭据',tax_basis:'inclusive'},
}]}
let wrapper:VueWrapper|undefined
beforeEach(()=>{vi.clearAllMocks();vi.spyOn(window,'confirm').mockReturnValue(true);vi.mocked(cuttingApi.access).mockResolvedValue(access);vi.mocked(settlementApi.read).mockResolvedValue(structuredClone(record));vi.mocked(settlementApi.basis).mockResolvedValue(structuredClone(basis));vi.mocked(settlementApi.write).mockResolvedValue({document_id:'statement-1'});vi.mocked(settlementApi.recover).mockResolvedValue({state:'abandoned'});vi.mocked(settlementApi.preview).mockResolvedValue({snapshot:saved().data!.snapshot,confirmation_token:'confirmed-preview'})})
afterEach(()=>{wrapper?.unmount();wrapper=undefined;vi.restoreAllMocks()})
async function open(rights=access){const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:CuttingSettlement},{path:'/next',component:{template:'<div />'}}]});await router.push('/');await router.isReady();const root=defineComponent({props:['access','accessLoading'],components:{RouterView},template:'<RouterView v-slot="{Component}"><component :is="Component" :access="access" :access-loading="accessLoading" /></RouterView>'});wrapper=mount(root,{props:{access:rights},global:{plugins:[router]}});return router}
async function click(label:string){const b=wrapper!.findAll('button').find(b=>b.text()===label);expect(b,label).toBeDefined();await b!.trigger('click');await flushPromises()}
async function edit(){await click('查询待结验收');await click('新建对账草稿');await wrapper!.get('input[type=number]').setValue('6');await wrapper!.findAll('textarea')[0]!.setValue('外厂核对凭据');await wrapper!.findAll('textarea')[1]!.setValue('核对依据')}
async function submit(){await wrapper!.get('form').trigger('submit');await flushPromises()}
function saved(state:FeeRecord['state']='submitted'):FeeRecord{return {...record,document_id:'statement-1',state,selected_state:state,event_id:'current',history:[{id:'current',action:state==='confirmed'?'confirm':'submit',version:2,actor:'主管',actor_id:'supervisor',date:'2026-10-16',reason:'核对'}],data:{input:{} as FeeSave,prepared_by:'supervisor',submitted_by:'supervisor',replaces_id:null,snapshot:{month:'2026-10',cutoff:'2026-10-16',resource_id:'resource-1',resource_name:'外厂甲',currency:'CNY',sets:6,total:'7.50',tax_basis:'inclusive',vendor_evidence:'外厂确认凭据',rows:[{...basis.rows[0]!,sets:6,amount:'7.50',prior_priced_sets:0}]}}}}

describe('subcontract reconciliation and frozen payables',()=>{
  it('requires independent fee read rather than material cost read',async()=>{await open({...access,permissions:['read','cost_read']});expect(wrapper!.text()).toContain('加工费需单独');expect(wrapper!.find('input').exists()).toBe(false);expect(settlementApi.read).not.toHaveBeenCalled()})
  it('preserves quantities when refreshing basis and saves only selected rows',async()=>{await open();await edit();vi.mocked(settlementApi.basis).mockResolvedValue({...basis,revision:2,basis_token:'basis-2'});await click('保留数量，刷新待结依据');expect((wrapper!.get('input[type=number]').element as HTMLInputElement).value).toBe('6');await submit();expect(settlementApi.write).toHaveBeenCalledWith('save',expect.objectContaining({basis_token:'basis-2',expected_version:2,vendor_evidence:'外厂核对凭据',selections:[{line_id:'line-1',acceptance_id:'acceptance-1',sets:6}]}))})
  it('does not lose an independent draft during parent loading',async()=>{await open();await edit();await wrapper!.setProps({access:undefined,accessLoading:true});expect(wrapper!.find('form').exists()).toBe(false);await wrapper!.setProps({access,accessLoading:false});expect((wrapper!.get('input[type=number]').element as HTMLInputElement).value).toBe('6');expect(wrapper!.get('textarea').element.value).toBe('外厂核对凭据')})
  it('clears sensitive evidence after actual revocation but restores quantities against fresh evidence',async()=>{await open();await edit();await wrapper!.setProps({access:{...access,permissions:['read']}});expect(wrapper!.text()).not.toContain('外厂核对凭据');expect(wrapper!.text()).not.toContain('1.25');await wrapper!.setProps({access});await click('恢复对账填写');expect((wrapper!.get('input[type=number]').element as HTMLInputElement).value).toBe('6');expect(wrapper!.get('textarea').element.value).toBe('')})
  it('keeps the exact unknown command through denied recovery and blocks leaving',async()=>{const router=await open();await edit();vi.mocked(settlementApi.write).mockRejectedValue(new Error('connection lost'));await submit();const body=vi.mocked(settlementApi.write).mock.calls[0]![1];await router.push('/next');expect(router.currentRoute.value.path).toBe('/');vi.mocked(settlementApi.recover).mockRejectedValueOnce({response:{status:403}});await click('核对原外发结算操作结果');expect(wrapper!.text()).toContain('核对原外发结算操作结果');await click('核对原外发结算操作结果');expect(settlementApi.recover).toHaveBeenLastCalledWith('save',body);expect(wrapper!.text()).toContain('核实未执行')})
  it('preserves rejected draft and prevents silent dropping of missing acceptance rows',async()=>{await open();await edit();vi.mocked(settlementApi.write).mockRejectedValueOnce({response:{status:409}});await submit();expect(wrapper!.find('form').exists()).toBe(true);vi.mocked(settlementApi.basis).mockResolvedValue({...basis,rows:[]});await click('保留数量，刷新待结依据');expect(wrapper!.text()).toContain('1 笔已选验收');await click('取消缺失的验收选择');expect(wrapper!.text()).not.toContain('1 笔已选验收')})
  it('refreshes rejected quote without losing entered price or evidence',async()=>{await open();await click('查询待结验收');await click('确认／修订单价');await wrapper!.get('input[type=text]').setValue('2.345678');await wrapper!.findAll('textarea')[0]!.setValue('新含税报价');await wrapper!.findAll('textarea')[1]!.setValue('调价原因');vi.mocked(settlementApi.write).mockRejectedValueOnce({response:{status:409}});await submit();vi.mocked(settlementApi.basis).mockResolvedValue({...basis,revision:9});await click('保留填写，刷新报价依据');await submit();expect(settlementApi.write).toHaveBeenLastCalledWith('price',expect.objectContaining({expected_version:9,unit_price:'2.345678',evidence:'新含税报价'}))})
  it('shows frozen amounts, quoted evidence and independent confirmation controls',async()=>{vi.mocked(settlementApi.read).mockResolvedValue(saved());await open({...access,permissions:['read','settlement_read','settlement_confirm']});vi.mocked(cuttingApi.access).mockResolvedValue({...access,permissions:['read','settlement_read','settlement_confirm']});await click('读取外发结算');expect(wrapper!.text()).toContain('7.50 CNY');expect(wrapper!.text()).toContain('含税报价凭据');expect(wrapper!.text()).not.toContain('提交外发对账复核');await wrapper!.get('input[maxlength="500"]').setValue('会计独立复核凭据');await click('复核并确认应付');expect(settlementApi.write).toHaveBeenCalledWith('confirm',expect.objectContaining({document_id:'statement-1',reason:'会计独立复核凭据'}))})
  it('history is read only and labels inactive frozen amounts',async()=>{vi.mocked(settlementApi.read).mockResolvedValue({...saved('confirmed'),event_id:'old'});await open();await click('读取外发结算');expect(wrapper!.text()).toContain('历史版本');expect(wrapper!.text()).toContain('历史冻结金额（已失效，不计入当前有效应付）');expect(wrapper!.text()).not.toContain('反结外发结算')})
  it('does not resurrect stale prices after permission loss',async()=>{let resolve!:(value:FeeBasis)=>void;vi.mocked(settlementApi.basis).mockImplementation(()=>new Promise(r=>{resolve=r}));await open();const b=wrapper!.findAll('button').find(b=>b.text()==='查询待结验收')!;await b.trigger('click');await flushPromises();await wrapper!.setProps({access:{...access,permissions:['read']}});resolve(basis);await flushPromises();expect(wrapper!.text()).not.toContain('外厂甲');expect(wrapper!.find('table').exists()).toBe(false)})
  it('binds explicit vendor confirmation to the preview and resets on quantity changes',async()=>{
    await open();await edit();await click('预览本次对账金额')
    expect(wrapper!.text()).toContain('本次预览：6 套 · 7.50 CNY')
    await wrapper!.get('input[type=checkbox]').setValue(true)
    await wrapper!.get('input[type=number]').setValue('7')
    expect(wrapper!.find('input[type=checkbox]').exists()).toBe(false)
    await submit()
    expect(settlementApi.write).toHaveBeenLastCalledWith('save',expect.objectContaining({vendor_confirmation_token:''}))
  })
  it('sends acknowledged preview and never implicitly confirms on refresh',async()=>{
    await open();await edit();await click('预览本次对账金额');await wrapper!.get('input[type=checkbox]').setValue(true)
    vi.mocked(settlementApi.write).mockRejectedValueOnce({response:{status:409}})
    await submit();expect(settlementApi.write).toHaveBeenLastCalledWith('save',expect.objectContaining({vendor_confirmation_token:'confirmed-preview'}))
    await click('保留数量，刷新待结依据');expect(wrapper!.find('input[type=checkbox]').exists()).toBe(false)
    expect(wrapper!.get('textarea').element.value).toBe('外厂核对凭据')
    await submit();expect(settlementApi.write).toHaveBeenLastCalledWith('save',expect.objectContaining({vendor_confirmation_token:''}))
  })
  it('locates dependent statements across months and labels ineffective historical amounts',async()=>{
    const value={...saved('confirmed'),state:'reopened' as const,event_id:'old',dependencies:[{document_id:'later-document',month:'2026-09',state:'submitted' as const,sets:3,version:8}]}
    vi.mocked(settlementApi.read).mockResolvedValue(value);await open();await click('读取外发结算')
    expect(wrapper!.text()).toContain('当前结算单状态：已反结')
    expect(wrapper!.text()).toContain('历史冻结金额（已失效，不计入当前有效应付）')
    await click('定位后续结算单');expect(settlementApi.read).toHaveBeenLastCalledWith('2026-09','later-document',undefined)
  })
  it('compares revisions exactly and keeps currency totals separate from filters',async()=>{
    const value=saved();value.previous_snapshot=structuredClone(value.data!.snapshot)
    value.previous_snapshot.rows[0]!.sets=5;value.previous_snapshot.rows[0]!.amount='6.25'
    value.totals=[{state:'submitted',currency:'CNY',sets:6,total:'7.50'},{state:'confirmed',currency:'USD',sets:2,total:'3.00'}]
    vi.mocked(settlementApi.read).mockResolvedValue(value);await open();await click('读取外发结算')
    expect(wrapper!.text()).toContain('+1.25');expect(wrapper!.text()).toContain('3.00 USD')
    await wrapper!.get('input[placeholder="加工厂名称"]').setValue('其他加工厂')
    expect(wrapper!.text()).toContain('本月汇总（不受筛选影响）');expect(wrapper!.text()).toContain('7.50 CNY')
    value.previous_snapshot.currency='USD';vi.mocked(settlementApi.read).mockResolvedValue(value);await click('读取外发结算')
    expect(wrapper!.text()).toContain('币种变化，不计算差额')
  })

})
