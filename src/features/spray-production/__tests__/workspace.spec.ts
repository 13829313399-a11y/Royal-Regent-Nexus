import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { sprayProductionApi as api, type SpraySummary } from '@/api/sprayProduction'
import { useSprayWorkspace } from '../workspace'
import ReportsPage from '../pages/ReportsPage.vue'
import EntryForm from '../components/EntryForm.vue'

vi.mock('@/api/sprayProduction', () => ({sprayProductionApi:{summary:vi.fn(),collection:vi.fn(),balances:vi.fn(),command:vi.fn(),preferences:vi.fn()}}))
const snapshot = (factory:string):SpraySummary => ({factory_id:factory,revision:1,as_of:'2026-09-11T00:00:00Z',data_mode:'live',coverage:'no_data',counts:{},permissions:['read','report']})
beforeEach(() => {
  vi.resetAllMocks(); setActivePinia(createPinia())
  vi.mocked(api.summary).mockImplementation(async factory=>snapshot(factory))
  vi.mocked(api.collection).mockResolvedValue({items:[],total:0,page:1,page_size:1000})
  vi.mocked(api.balances).mockResolvedValue({})
  vi.mocked(api.preferences).mockResolvedValue([])
})
describe('spray factory workspace', () => {
  it('loads records beyond page one and keeps the final record searchable',async()=>{
    vi.mocked(api.collection).mockImplementation(async(_scope,kind,_signal,page=1)=>({items:kind==='orders'?(page===1?Array.from({length:1000},(_,i)=>({id:'order-'+i})):[{id:'last-order',document_no:'0000123'}]):[],total:kind==='orders'?1001:0,page,page_size:1000}))
    const s=useSprayWorkspace();await s.load('huaxing')
    expect(s.items('orders')).toHaveLength(1001);expect(s.find('orders','last-order')?.document_no).toBe('0000123');expect(s.truncated).toBe(false)
  })
  it('saves a draft without reloading production or restoring another factory preference',async()=>{
    const s=useSprayWorkspace();await s.load('huaxing');vi.mocked(api.summary).mockClear()
    vi.mocked(api.command).mockResolvedValue({id:'draft',revision:1})
    vi.mocked(api.preferences).mockResolvedValue([{id:'draft',kind:'report_draft',name:'现场快录',revision:1,payload:{lines:[]}}])
    await s.savePreference('report_draft','现场快录',{lines:[]})
    expect(api.summary).not.toHaveBeenCalled();expect(s.preferences).toHaveLength(1)
    await s.load('huadeng');expect(s.preferences).toHaveLength(0)
  })
  it('does not download payroll or costs for a production-only account', async () => {
    const s = useSprayWorkspace(); await s.load('huaxing')
    expect(vi.mocked(api.collection).mock.calls.map(c=>c[1])).not.toEqual(expect.arrayContaining(['rates','purchases','imports','settlements']))
    expect(s.can('cost_read')).toBe(false)
  })
  it('a late response cannot replace the newly selected factory', async () => {
    let resolveOld!:(value:SpraySummary)=>void
    vi.mocked(api.summary).mockImplementation(factory=>factory==='huaxing'?new Promise(resolve=>{resolveOld=resolve}):Promise.resolve(snapshot(factory)))
    const s=useSprayWorkspace(), old=s.load('huaxing')
    await s.load('huakang-b'); resolveOld(snapshot('huaxing')); await old
    expect(s.factory).toBe('huakang-b'); expect(s.summary?.factory_id).toBe('huakang-b')
  })
  it('reuses the receipt id after a lost response and leaves the draft with caller', async () => {
    const s=useSprayWorkspace(); await s.load('huaxing')
    vi.mocked(api.command).mockRejectedValueOnce(new Error('connection lost')).mockResolvedValueOnce({id:'saved',revision:2})
    const payload={lines:[{regular_qty:'12'}]}
    expect(await s.command('reports',payload)).toBeNull()
    expect(await s.command('reports',payload)).toMatchObject({id:'saved'})
    const calls=vi.mocked(api.command).mock.calls
    expect(calls[0]![2].operation_id).toBe(calls[1]![2].operation_id)
    expect(payload.lines[0]!.regular_qty).toBe('12')
  })
  it('group selection is neutral and makes no factory request',async()=>{
    const s=useSprayWorkspace();await s.load('group');expect(api.summary).not.toHaveBeenCalled();expect(s.summary).toBeNull()
  })
})
describe('spray entry',()=>{
  it('restores the persistent submission receipt before retrying after a refresh',async()=>{
    const s=useSprayWorkspace();await s.load('huaxing')
    vi.mocked(api.preferences).mockResolvedValue([{id:'draft',kind:'report_draft',name:'现场快录',revision:1,payload:{operation_id:'persisted-receipt',date:'2026-09-11',shift:'白班',team:'一组',people:'甲',lines:[{task_id:'',activity:'调机',regular_qty:'0',regular_hours:'3',overtime_qty:'0',overtime_hours:'0',good:'0',held:'0',rework:'0',scrap:'0',rate_id:''}]}}])
    vi.mocked(api.command).mockImplementation(async(_scope,action)=>{if(action==='reports')throw new Error('response lost');return {id:'draft',revision:2}})
    const wrapper=mount(ReportsPage);await flushPromises()
    expect(wrapper.get('[aria-label="第1行 正班小时"]').element).toHaveProperty('value','3')
    await wrapper.get('form').trigger('submit');await flushPromises()
    const report=vi.mocked(api.command).mock.calls.find(c=>c[1]==='reports')
    expect(report?.[2].operation_id).toBe('persisted-receipt');expect(wrapper.get('[aria-label="第1行 正班小时"]').element).toHaveProperty('value','3')
    wrapper.unmount()
  })
  it('pastes 20 complete rows, refuses one invalid row without partial replacement',async()=>{
    const s=useSprayWorkspace();await s.load('huaxing')
    const wrapper=mount(ReportsPage)
    await wrapper.get('textarea').setValue(Array(20).fill('10\t1\t0\t0\t10\t0\t0\t0').join('\n'))
    const check=wrapper.findAll('button').find(b=>b.text()==='检查粘贴')!
    await check.trigger('click');await flushPromises()
    expect(wrapper.findAll('[aria-label="报工任务"]')).toHaveLength(20)
    await wrapper.get('textarea').setValue('1\t1\t0\t0\t1\t0\t0\t0\nBAD')
    await check.trigger('click')
    expect(wrapper.findAll('[aria-label="报工任务"]')).toHaveLength(20)
    expect(wrapper.text()).toContain('不会跳过错误行');expect(api.command).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('gives selects an exact accessible name and submits the business selection',async()=>{
    const wrapper=mount(EntryForm,{props:{fields:[{key:'resource_id',label:'资源',options:[{value:'r-1',label:'手喷第一班'}]}]}})
    await wrapper.get('select[aria-label="资源"]').setValue('r-1')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]).toEqual([{resource_id:'r-1'}]);wrapper.unmount()
  })
})
