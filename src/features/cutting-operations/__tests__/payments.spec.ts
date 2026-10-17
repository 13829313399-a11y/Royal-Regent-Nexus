import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { defineComponent } from 'vue'
import CuttingPayments from '../CuttingPayments.vue'
import { cuttingApi, type Access } from '../api'
import { paymentApi, type PaymentRecord, type PaymentBasis, type PaymentSave } from '../paymentApi'

vi.mock('../api',()=>({cuttingApi:{access:vi.fn()},errorMessage:()=> '请求被拒绝或未完成'}))
vi.mock('../paymentApi',()=>({paymentApi:{read:vi.fn(),basis:vi.fn(),preview:vi.fn(),write:vi.fn(),recover:vi.fn()}}))
const access:Access={enabled:true,schema_ready:true,payments_schema_ready:true,permissions:['read','payment_read','payment_prepare','payment_confirm','payment_reverse']}
const basis:PaymentBasis={revision:0,basis_token:'fresh',rows:[{settlement_id:'statement-1',settlement_event_id:'confirmed-fee-event',month:'2026-10',resource_id:'vendor-1',resource_name:'外厂甲',currency:'CNY',payable:'20.00',paid:'0.00',pending:'0.00',unpaid:'20.00',available:'20.00',payments:[]}]}
const empty:PaymentRecord={revision:0,rows:basis.rows,totals:[{currency:'CNY',payable:'20.00',paid:'0.00',pending:'0.00',unpaid:'20.00',available:'20.00'}],documents:[],document_id:null,state:'open',selected_state:'open',event_id:null,data:null,history:[],replacements:[]}
const input:PaymentSave={factory_id:'huakang-c',operation_id:'op-1',expected_version:0,reason:'登记依据',document_id:'payment-1',day:'2026-10-16',voucher_no:'PAY-001',method:'bank',evidence:'实际银行回单',currency:'CNY',amount:'5.00',basis_token:'fresh',allocations:[{settlement_id:'statement-1',amount:'5.00'}],replaces_document_id:null}
function saved(state:PaymentRecord['state']='submitted'):PaymentRecord{return {...structuredClone(empty),document_id:'payment-1',event_id:'latest',state,selected_state:state,history:[{id:'latest',action:state==='confirmed'?'confirm':state==='reversed'?'reverse':'submit',actor:'会计',date:'2026-10-16',reason:'核对凭证'}],data:{input:structuredClone(input),prepared_by:'accountant-1',submitted_by:'accountant-1',snapshot:{day:input.day,voucher_no:input.voucher_no,method:'bank',evidence:input.evidence,resource_id:'vendor-1',resource_name:'外厂甲',currency:'CNY',amount:'5.00',allocations:[{...basis.rows[0]!,amount:'5.00'}],replaces_document_id:null}}}}
let wrapper:VueWrapper|undefined
beforeEach(()=>{vi.clearAllMocks();vi.spyOn(window,'confirm').mockReturnValue(true);vi.mocked(cuttingApi.access).mockResolvedValue(access);vi.mocked(paymentApi.basis).mockResolvedValue(structuredClone(basis));vi.mocked(paymentApi.read).mockResolvedValue(structuredClone(empty));vi.mocked(paymentApi.write).mockResolvedValue({document_id:'payment-1'});vi.mocked(paymentApi.preview).mockResolvedValue(saved().data!.snapshot);vi.mocked(paymentApi.recover).mockResolvedValue({state:'abandoned'})})
afterEach(()=>{wrapper?.unmount();wrapper=undefined;vi.restoreAllMocks()})
async function open(rights=access){const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:CuttingPayments},{path:'/next',component:{template:'<div />'}}]});await router.push('/');await router.isReady();const root=defineComponent({props:['access','accessLoading'],components:{RouterView},template:'<RouterView v-slot="{Component}"><component :is="Component" :access="access" :access-loading="accessLoading" /></RouterView>'});wrapper=mount(root,{props:{access:rights},global:{plugins:[router]}});return router}
async function click(text:string){const button=wrapper!.findAll('button').find(b=>b.text()===text);expect(button,text).toBeDefined();await button!.trigger('click');await flushPromises()}
function field(name:string){const label=wrapper!.findAll('label').find(l=>l.text()===name);expect(label,name).toBeDefined();return label!.find<HTMLInputElement|HTMLTextAreaElement|HTMLSelectElement>('input,textarea,select')}
async function edit(){await click('新建付款登记');await field('付款凭证号（本厂唯一）').setValue('PAY-001');await field('实际付款金额').setValue('5.00');await field('付款凭据／交易流水说明').setValue('实际银行回单');await field('登记／更正依据').setValue('登记依据');await wrapper!.get('input[aria-label="核销金额 statement-1"]').setValue('5.00')}
async function submit(){await wrapper!.get('form').trigger('submit');await flushPromises()}

describe('payment registration and allocation',()=>{
  it('requires separate payment permission and explicit migration',async()=>{await open({...access,permissions:['read','settlement_read','cost_read']});expect(wrapper!.find('form').exists()).toBe(false);expect(wrapper!.text()).toContain('仅限单独授权');expect(paymentApi.read).not.toHaveBeenCalled()})
  it('previews full allocation and saves monetary strings',async()=>{await open();await edit();expect(wrapper!.text()).toContain('分配合计 5.00 CNY');await click('预览核销分配');expect(wrapper!.text()).toContain('已全额分配 1 张结算单');await submit();expect(paymentApi.write).toHaveBeenCalledWith('save',expect.objectContaining({amount:'5.00',voucher_no:'PAY-001',allocations:[{settlement_id:'statement-1',amount:'5.00'}]}))})
  it('preserves drafts on loading and conflict refresh without silently dropping missing allocations',async()=>{await open();await edit();await wrapper!.setProps({access:undefined,accessLoading:true});expect(wrapper!.find('form').exists()).toBe(false);await wrapper!.setProps({access,accessLoading:false});expect(field('实际付款金额').element.value).toBe('5.00');vi.mocked(paymentApi.write).mockRejectedValueOnce({response:{status:409}});await submit();vi.mocked(paymentApi.basis).mockResolvedValue({...basis,revision:2,rows:[]});await click('保留填写，刷新付款依据');expect(wrapper!.text()).toContain('1 笔原分配');await click('取消失效分配');expect(wrapper!.text()).toContain('分配合计 0.00')})
  it('clears financial fields on actual revocation and does not restore them after reauthorization',async()=>{await open();await edit();await wrapper!.setProps({access:{...access,permissions:['read']}});expect(wrapper!.text()).not.toContain('实际银行回单');await wrapper!.setProps({access});await click('恢复付款填写');expect(field('实际付款金额').element.value).toBe('');expect(field('付款凭证号（本厂唯一）').element.value).toBe('');expect(wrapper!.text()).toContain('分配合计 0.00')})
  it('keeps unknown request identity through failed recovery and blocks leaving',async()=>{const router=await open();await edit();vi.mocked(paymentApi.write).mockRejectedValueOnce(new Error('lost response'));await submit();const body=vi.mocked(paymentApi.write).mock.calls[0]![1];await router.push('/next');expect(router.currentRoute.value.path).toBe('/');vi.mocked(paymentApi.recover).mockRejectedValueOnce({response:{status:403}});await click('核对原付款操作结果');await click('核对原付款操作结果');expect(paymentApi.recover).toHaveBeenLastCalledWith('save',body);expect(wrapper!.text()).toContain('原操作未执行')})
  it('shows current balances separately from selected month and source access',async()=>{await open();await click('读取付款登记');expect(wrapper!.text()).toContain('非历史月末余额');expect(wrapper!.text()).toContain('待复核占用');expect(wrapper!.text()).not.toContain('查看原结算版本')})
  it('requires explicit reason for review and preserves the frozen source version',async()=>{vi.mocked(paymentApi.read).mockResolvedValue(saved());await open();await click('读取付款登记');await click('独立复核付款生效');expect(paymentApi.write).not.toHaveBeenCalled();await field('操作依据').setValue('核对真实银行回单');await click('独立复核付款生效');expect(paymentApi.write).toHaveBeenCalledWith('confirm',expect.objectContaining({document_id:'payment-1',reason:'核对真实银行回单'}))})
  it('labels reversed history as ineffective and makes a linked new registration',async()=>{vi.mocked(paymentApi.read).mockResolvedValue({...saved('confirmed'),state:'reversed',event_id:'old'});await open();await click('读取付款登记');expect(wrapper!.text()).toContain('历史版本，不计入当前有效核销');expect(wrapper!.text()).not.toContain('整笔冲销登记及核销');vi.mocked(paymentApi.read).mockResolvedValue(saved('reversed'));await click('返回当前付款版本');await click('关联原凭证重新登记');expect(wrapper!.text()).toContain('关联原冲销登记：payment-1');await submit();expect(paymentApi.write).toHaveBeenCalledWith('save',expect.objectContaining({replaces_document_id:'payment-1',voucher_no:'PAY-001',amount:'5.00'}));expect((vi.mocked(paymentApi.write).mock.calls[0]![1] as PaymentSave).document_id).not.toBe('payment-1')})
  it('ignores late financial responses after access revocation',async()=>{let resolve!:(v:PaymentBasis)=>void;vi.mocked(paymentApi.basis).mockImplementation(()=>new Promise(r=>{resolve=r}));await open();await wrapper!.findAll('button').find(b=>b.text()==='新建付款登记')!.trigger('click');await flushPromises();await wrapper!.setProps({access:{...access,permissions:['read']}});resolve(basis);await flushPromises();expect(wrapper!.text()).not.toContain('外厂甲');expect(wrapper!.find('form').exists()).toBe(false)})
})

it('requires an explicit conflict choice after another accountant changes this draft',async()=>{
  const initial=saved('draft');vi.mocked(paymentApi.read).mockResolvedValue(initial)
  vi.mocked(paymentApi.basis).mockResolvedValue({...basis,document:{event_id:'latest',input:initial.data!.input,snapshot:initial.data!.snapshot,actor:'会计甲',date:'2026-10-16'}})
  await open();await click('读取付款登记');await click('修订付款草稿');await field('付款凭据／交易流水说明').setValue('我的未保存说明')
  const other=structuredClone(initial.data!);other.input.evidence='乙的已保存说明';other.input.amount='7.00';other.input.allocations[0]!.amount='7.00';other.snapshot.evidence=other.input.evidence;other.snapshot.amount='7.00';other.snapshot.allocations[0]!.amount='7.00'
  vi.mocked(paymentApi.basis).mockResolvedValue({...basis,revision:9,document:{event_id:'newer',input:other.input,snapshot:other.snapshot,actor:'会计乙',date:'2026-10-16'}})
  await click('保留填写，刷新付款依据')
  expect(wrapper!.text()).toContain('乙的已保存说明');expect(wrapper!.text()).toContain('我的未保存说明')
  await submit();expect(paymentApi.write).not.toHaveBeenCalled()
  await click('核对后保留我的填写');await field('登记／更正依据').setValue('确认采用我的更正')
  await submit();expect(paymentApi.write).toHaveBeenLastCalledWith('save',expect.objectContaining({base_event_id:'newer',expected_version:9,evidence:'我的未保存说明',amount:'5.00'}))
})

it('adopts latest server fields only after choice and clears comparison on revocation',async()=>{
  const initial=saved('draft');vi.mocked(paymentApi.read).mockResolvedValue(initial)
  const other=structuredClone(initial.data!);other.input.evidence='服务端新凭据';other.snapshot.evidence='服务端新凭据'
  vi.mocked(paymentApi.basis).mockResolvedValue({...basis,document:{event_id:'newer',input:other.input,snapshot:other.snapshot,actor:'会计乙',date:'2026-10-16'}})
  await open();await click('读取付款登记');await click('修订付款草稿');expect(wrapper!.text()).toContain('请先比较并选择')
  await click('采用服务器最新内容');expect(field('付款凭据／交易流水说明').element.value).toBe('服务端新凭据')
  await wrapper!.setProps({access:{...access,permissions:['read']}});expect(wrapper!.text()).not.toContain('服务端新凭据')
})

it('refreshes unrelated balance changes without resetting own input or document base',async()=>{
  const initial=saved('draft');vi.mocked(paymentApi.read).mockResolvedValue(initial)
  vi.mocked(paymentApi.basis).mockResolvedValue({...basis,document:{event_id:'latest',input:initial.data!.input,snapshot:initial.data!.snapshot,actor:'甲',date:'2026-10-16'}})
  await open();await click('读取付款登记');await click('修订付款草稿');await field('付款凭据／交易流水说明').setValue('保留说明')
  vi.mocked(paymentApi.basis).mockResolvedValue({...basis,revision:4,document:{event_id:'latest',input:initial.data!.input,snapshot:initial.data!.snapshot,actor:'甲',date:'2026-10-16'}})
  await click('保留填写，刷新付款依据');expect(wrapper!.text()).not.toContain('请先比较并选择');await submit()
  expect(paymentApi.write).toHaveBeenLastCalledWith('save',expect.objectContaining({expected_version:4,base_event_id:'latest',evidence:'保留说明'}))
})

it('recovers a previous-month save to the exact saved event and keeps a retry target if reading fails',async()=>{
  await open();await edit();await field('实际付款日期').setValue('2026-09-30')
  vi.mocked(paymentApi.write).mockRejectedValueOnce(new Error('lost'));await submit()
  vi.mocked(paymentApi.recover).mockResolvedValueOnce({state:'committed',result:{document_id:'payment-1',id:'saved-event',month:'2026-09'}})
  vi.mocked(paymentApi.read).mockRejectedValueOnce(new Error('temporarily unavailable'))
  await click('核对原付款操作结果')
  expect(paymentApi.read).toHaveBeenLastCalledWith('2026-09','payment-1','saved-event')
  expect(wrapper!.text()).toContain('打开已保存付款记录');expect(wrapper!.find('form').exists()).toBe(false)
  vi.mocked(paymentApi.read).mockResolvedValue({...saved('draft'),month:'2026-09',current_month:'2026-09'})
  await click('打开已保存付款记录');expect(field('付款月份').element.value).toBe('2026-09')
  expect(paymentApi.write).toHaveBeenCalledTimes(1)
})

it('follows original and current months when navigating date-corrected history',async()=>{
  const current={...saved('draft'),month:'2026-09',current_month:'2026-09',history:[{id:'old',action:'save' as const,actor:'甲',date:'2026-10-16',reason:'原登记',month:'2026-10'},{id:'latest',action:'save' as const,actor:'甲',date:'2026-10-16',reason:'纠正日期',month:'2026-09'}]}
  vi.mocked(paymentApi.read).mockResolvedValue(current);await open();await click('读取付款登记')
  vi.mocked(paymentApi.read).mockResolvedValue({...current,event_id:'old',month:'2026-10'})
  await wrapper!.findAll('button').find(b=>b.text()==='查看付款历史版本')!.trigger('click');await flushPromises()
  expect(paymentApi.read).toHaveBeenLastCalledWith('2026-10','payment-1','old')
  await click('返回当前付款版本');expect(paymentApi.read).toHaveBeenLastCalledWith('2026-09','payment-1',undefined)
})

it('shows precise review differences and never subtracts across currencies',async()=>{
  const value=saved();const previous=structuredClone(value.data!.snapshot);previous.amount='0.01';previous.allocations=[{...previous.allocations[0]!,settlement_id:'removed',amount:'0.01'}]
  value.previous_compilation={event_id:'before',snapshot:previous,actor:'甲',date:'2026-10-15'}
  vi.mocked(paymentApi.read).mockResolvedValue(value);await open();await click('读取付款登记')
  expect(wrapper!.text()).toContain('与上一编制版本比较');expect(wrapper!.text()).toContain('+4.99');expect(wrapper!.text()).toContain('新增分配');expect(wrapper!.text()).toContain('取消分配')
  previous.currency='HKD';await click('读取付款登记');expect(wrapper!.text()).toContain('币种变化，不计算差额')
})
