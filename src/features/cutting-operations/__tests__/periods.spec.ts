import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { defineComponent } from 'vue'
import CuttingPeriodClosing from '../CuttingPeriodClosing.vue'
import { cuttingApi, type Access } from '../api'
import { periodApi, type PeriodBasis, type PeriodRecord } from '../periodApi'

vi.mock('../api',()=>({cuttingApi:{access:vi.fn()},errorMessage:()=> '请求被拒绝或未完成'}))
vi.mock('../periodApi',()=>({periodApi:{read:vi.fn(),basis:vi.fn(),write:vi.fn(),recover:vi.fn()}}))
const access:Access={enabled:true,schema_ready:true,periods_schema_ready:true,permissions:['read','cost_read','period_prepare','period_lock','period_reopen']}
const record:PeriodRecord={month:'2026-10',revision:0,state:'open',selected_state:'open',event_id:null,data:null,history:[],locked_months:[]}
const basis:PeriodBasis={month:'2026-10',revision:0,state:'open',basis_token:'basis-1',previous_month:null,blockers:[],notices:[],rows:[{
  issue_id:'issue-1',line_id:'line-1',context:{task_name:'本厂任务',resource_name:'车间',item_name:'蓝布',unit:'米',root_batch_id:'batch-1'},
  opening_normal_quantity:'0',ending_normal_quantity:'2',opening_loss_quantity:'0',ending_loss_quantity:'0.5',opening_custody:'0',ending_custody:'1.5',opening_sets:0,ending_sets:10,carried_completed_quantity:null,price:null,
}]}
let wrapper:VueWrapper|undefined
beforeEach(()=>{vi.clearAllMocks();vi.spyOn(window,'confirm').mockReturnValue(true);vi.mocked(cuttingApi.access).mockResolvedValue(access);vi.mocked(periodApi.read).mockResolvedValue(structuredClone(record));vi.mocked(periodApi.basis).mockResolvedValue(structuredClone(basis));vi.mocked(periodApi.write).mockResolvedValue({});vi.mocked(periodApi.recover).mockResolvedValue({state:'abandoned'})})
afterEach(()=>{wrapper?.unmount();wrapper=undefined;vi.restoreAllMocks()})
async function open(rights=access){const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:CuttingPeriodClosing},{path:'/next',component:{template:'<div />'}}]});await router.push('/');await router.isReady();const root=defineComponent({props:['access','accessLoading'],components:{RouterView},template:'<RouterView v-slot="{Component}"><component :is="Component" :access="access" :access-loading="accessLoading" /></RouterView>'});wrapper=mount(root,{props:{access:rights},global:{plugins:[router]}});return router}
async function click(label:string){const target=wrapper!.findAll('button').find(b=>b.text()===label);expect(target,label).toBeDefined();await target!.trigger('click');await flushPromises()}
async function edit(){await click('读取月结记录');await click('编制／重新核对月结')}

describe('internal monthly closing',()=>{
  it('protects reasons on direct period links, historical reads, month input and route exit',async()=>{
    const router=await open();await click('读取月结记录')
    const panel=wrapper!.findComponent(CuttingPeriodClosing),oldMonth=(wrapper!.get('input[type=month]').element as HTMLInputElement).value
    await wrapper!.get('input[maxlength="500"]').setValue('仅属于原月的复核依据')
    vi.mocked(window.confirm).mockReturnValue(false)
    vi.mocked(periodApi.read).mockClear()
    await panel.vm.openPeriod('2025-01');await flushPromises()
    expect(periodApi.read).not.toHaveBeenCalled()
    await click('读取月结记录')
    await wrapper!.get('input[type=month]').setValue('2025-01')
    expect((wrapper!.get('input[type=month]').element as HTMLInputElement).value).toBe(oldMonth)
    await router.push('/next');expect(router.currentRoute.value.path).toBe('/')
    const event=new Event('beforeunload',{cancelable:true});window.dispatchEvent(event);expect(event.defaultPrevented).toBe(true)
    expect((wrapper!.get('input[maxlength="500"]').element as HTMLInputElement).value).toBe('仅属于原月的复核依据')
    vi.mocked(window.confirm).mockReturnValue(true).mockClear()
    await panel.vm.openPeriod('2025-01','old-event');await flushPromises()
    expect(window.confirm).toHaveBeenCalledTimes(1)
    expect(periodApi.read).toHaveBeenLastCalledWith('2025-01','old-event')
    expect((wrapper!.get('input[maxlength="500"]').element as HTMLInputElement).value).toBe('')
  })

  it('keeps the active month and unsaved reason when overview requests another month',async()=>{
    await open();await click('读取月结记录')
    const field=wrapper!.get('input[type=month]'),original=(field.element as HTMLInputElement).value
    await wrapper!.get('input[maxlength="500"]').setValue('当前月的独立复核依据')
    wrapper!.findComponent(CuttingPeriodClosing).vm.activateMonth('2025-01')
    await flushPromises()
    expect((field.element as HTMLInputElement).value).toBe(original)
    expect((wrapper!.get('input[maxlength="500"]').element as HTMLInputElement).value).toBe('当前月的独立复核依据')
    expect(wrapper!.text()).toContain('请先处理当前内容再切换期间')
  })
  it('filters displayed rows without losing hidden allocations on save',async()=>{
    await open();await edit();await wrapper!.findAll('input[type=number]')[1]!.setValue('1.2')
    await wrapper!.get('input[type=search]').setValue('不存在的客户')
    expect(wrapper!.get('tbody tr').isVisible()).toBe(false)
    await wrapper!.get('textarea').setValue('全月核对')
    await wrapper!.get('form').trigger('submit');await flushPromises()
    expect(periodApi.write).toHaveBeenCalledWith('save',expect.objectContaining({allocations:[expect.objectContaining({issue_id:'issue-1',completed_quantity:1.2})]}))
  })
  it('preserves an independent monthly form while the parent searches orders',async()=>{
    await open();await edit();await wrapper!.findAll('input[type=number]')[1]!.setValue('1.2')
    await wrapper!.get('textarea').setValue('保留月末归属依据')
    await wrapper!.setProps({access:undefined,accessLoading:true})
    expect(wrapper!.find('form').exists()).toBe(false)
    await wrapper!.setProps({access:{...access},accessLoading:false})
    expect((wrapper!.findAll('input[type=number]')[1]!.element as HTMLInputElement).value).toBe('1.2')
    expect(wrapper!.get('textarea').element.value).toBe('保留月末归属依据')
    expect(wrapper!.text()).toContain('保留数量，刷新依据')
  })
  it('requires fresh evidence but can resume quantities after actual revocation and regrant',async()=>{
    await open();await edit();await wrapper!.findAll('input[type=number]')[1]!.setValue('1.2')
    await wrapper!.setProps({access:{...access,permissions:['read']}})
    expect(wrapper!.find('form').exists()).toBe(false)
    await wrapper!.setProps({access:{...access}})
    await click('恢复填写并重新核对')
    expect((wrapper!.findAll('input[type=number]')[1]!.element as HTMLInputElement).value).toBe('1.2')
    expect((wrapper!.findAll('input[type=checkbox]')[0]!.element as HTMLInputElement).checked).toBe(false)
  })
  it('keeps uncertain-operation recovery accessible after cost permission is revoked',async()=>{
    const router=await open();await edit();await wrapper!.get('textarea').setValue('待核对操作')
    vi.mocked(periodApi.write).mockRejectedValueOnce(new Error('offline'))
    await wrapper!.get('form').trigger('submit');await flushPromises()
    const denied={...access,permissions:['read']}
    await wrapper!.setProps({access:denied});vi.mocked(cuttingApi.access).mockResolvedValue(denied)
    expect(wrapper!.find('textarea').exists()).toBe(false)
    await click('核对原操作结果');expect(periodApi.recover).toHaveBeenCalled()
    await router.push('/next');expect(router.currentRoute.value.path).toBe('/next')
  })
  it('requires migration and separate cost reading before exposing the workspace',async()=>{await open({...access,periods_schema_ready:false});expect(wrapper!.text()).toContain('0163');expect(wrapper!.find('input[type=month]').exists()).toBe(false);expect(periodApi.read).not.toHaveBeenCalled();await wrapper!.setProps({access:{...access,permissions:['read']}});expect(wrapper!.text()).toContain('单独授予成本查询');expect(wrapper!.find('input[type=month]').exists()).toBe(false)})
  it('saves explicit month-end allocations and completeness declarations',async()=>{await open();await edit();await wrapper!.get('textarea').setValue('月末实物和在制逐项核对');const quantity=wrapper!.findAll('input[type=number]');await quantity[1]!.setValue('1.2');await wrapper!.get('form').trigger('submit');await flushPromises();expect(periodApi.write).toHaveBeenCalledWith('save',expect.objectContaining({basis_token:'basis-1',reason:'月末实物和在制逐项核对',public_material_pending:true,unrecorded_opening:true,allocations:[expect.objectContaining({issue_id:'issue-1',completed_quantity:1.2})]}))})
  it('refreshes evidence while preserving quantities and resetting declarations',async()=>{await open();await edit();await wrapper!.findAll('input[type=number]')[1]!.setValue('1.2');await wrapper!.findAll('input[type=checkbox]')[0]!.setValue(true);await click('保留数量，刷新依据');expect((wrapper!.findAll('input[type=number]')[1]!.element as HTMLInputElement).value).toBe('1.2');expect((wrapper!.findAll('input[type=checkbox]')[0]!.element as HTMLInputElement).checked).toBe(false)})
  it('retains an unknown command and fences it before another operation or navigation',async()=>{const router=await open();await edit();await wrapper!.get('textarea').setValue('核对依据');vi.mocked(periodApi.write).mockRejectedValueOnce(new Error('offline'));await wrapper!.get('form').trigger('submit');await flushPromises();const original=vi.mocked(periodApi.write).mock.calls[0]![1];expect(wrapper!.text()).toContain('核对原操作结果');await router.push('/next');expect(router.currentRoute.value.path).toBe('/');await click('核对原操作结果');expect(periodApi.recover).toHaveBeenCalledWith('save',original);expect(wrapper!.text()).toContain('填写保留');expect(wrapper!.get('textarea').element.value).toBe('核对依据')})
  it('clears denied costs and ignores a late response after access changes',async()=>{await open();let resolve!:(value:PeriodRecord)=>void;vi.mocked(periodApi.read).mockImplementationOnce(()=>new Promise(r=>{resolve=r}));await click('读取月结记录');await wrapper!.setProps({access:{...access,permissions:['read']}});resolve({...record,state:'locked',locked_months:['2026-10']});await flushPromises();expect(wrapper!.text()).not.toContain('已锁月份');expect(wrapper!.text()).toContain('单独授予成本查询')})
  it('shows lock controls only for a submitted current version with lock rights',async()=>{vi.mocked(periodApi.read).mockResolvedValue({...record,state:'submitted',selected_state:'submitted'});await open({...access,permissions:['read','cost_read','period_lock']});vi.mocked(cuttingApi.access).mockResolvedValue({...access,permissions:['read','cost_read','period_lock']});await click('读取月结记录');expect(wrapper!.text()).toContain('复核并锁月');expect(wrapper!.text()).not.toContain('提交会计复核');await wrapper!.get('input[maxlength="500"]').setValue('会计独立复核');await click('复核并锁月');expect(window.confirm).toHaveBeenCalled();expect(periodApi.write).toHaveBeenCalledWith('lock',expect.objectContaining({reason:'会计独立复核'}))})
})
