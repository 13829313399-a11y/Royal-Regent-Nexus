import { afterEach,beforeEach,describe,expect,it,vi } from 'vitest'
import { mount,flushPromises,type VueWrapper } from '@vue/test-utils'
import Monthly from '../CuttingMonthlyOverview.vue'
import { workspaceApi } from '../workspaceApi'
vi.mock('../workspaceApi',()=>({businessDay:()=> '2026-10-28',workspaceApi:{monthly:vi.fn()}}))
const result=(month:string)=>({month,domains:[],frozen:[]})
let wrapper:VueWrapper
const retry=()=>wrapper.findAll('button').find(b=>b.text()==='按原月份重试')
beforeEach(()=>{vi.resetAllMocks()})
afterEach(()=>wrapper?.unmount())
describe('frozen month list recovery',()=>{
  it('keeps a keyboard retry available after repeated failure and hands success to the result',async()=>{
    vi.mocked(workspaceApi.monthly).mockRejectedValueOnce(new Error('offline')).mockRejectedValueOnce(new Error('offline again')).mockResolvedValueOnce(result('2026-09'))
    wrapper=mount(Monthly,{attachTo:document.body,props:{month:'2026-09',exportsOnly:true}});await flushPromises()
    retry()!.element.focus();retry()!.element.dispatchEvent(new MouseEvent('click',{bubbles:true,detail:0}));await flushPromises()
    expect(document.activeElement).toBe(retry()!.element)
    retry()!.element.dispatchEvent(new MouseEvent('click',{bubbles:true,detail:0}));await flushPromises()
    expect(document.activeElement).toBe(wrapper.get('[aria-label="冻结报表读取结果"]').element)
  })
  it.each([401,403])('does not restore private retry focus after status %i',async status=>{
    vi.mocked(workspaceApi.monthly).mockRejectedValueOnce(new Error('offline')).mockRejectedValueOnce({response:{status}})
    wrapper=mount(Monthly,{attachTo:document.body,props:{month:'2026-09',exportsOnly:true}});await flushPromises()
    retry()!.element.focus();retry()!.element.dispatchEvent(new MouseEvent('click',{bubbles:true,detail:0}));await flushPromises()
    expect(retry()).toBeUndefined();expect(document.activeElement).toBe(document.body)
  })
  it.each(['input','tab','pointer','month','refresh','unmount','mouse'] as const)('does not reclaim retry focus after user intent or newer read: %s',async action=>{
    let fail!:(e:Error)=>void
    vi.mocked(workspaceApi.monthly).mockRejectedValueOnce(new Error('offline')).mockImplementationOnce(()=>new Promise((_r,reject)=>fail=reject)).mockRejectedValueOnce(new Error('new target'))
    wrapper=mount(Monthly,{attachTo:document.body,props:{month:'2026-09',exportsOnly:true}});await flushPromises()
    retry()!.element.focus();retry()!.element.dispatchEvent(new MouseEvent('click',{bubbles:true,detail:action==='mouse'?1:0}));await flushPromises()
    const input=wrapper.get<HTMLInputElement>('input[type=month]').element
    if(action==='input')input.focus()
    if(action==='tab')document.dispatchEvent(new KeyboardEvent('keydown',{key:'Tab',bubbles:true}))
    if(action==='pointer')document.dispatchEvent(new Event('pointerdown',{bubbles:true}))
    if(action==='month')await wrapper.setProps({month:'2026-08'})
    if(action==='refresh')await wrapper.get('form').trigger('submit')
    if(action==='unmount')wrapper.unmount()
    fail(new Error('late failure'));await flushPromises()
    if(action!=='unmount'&&retry())expect(document.activeElement).not.toBe(retry()!.element)
    if(action==='input')expect(document.activeElement).toBe(input)
    if(action==='month')expect(wrapper.text()).toContain('读取未完成：2026-08')
  })
  it('retries the captured month after repeated failures and reports its loading target',async()=>{
    let finish!:(v:ReturnType<typeof result>)=>void
    vi.mocked(workspaceApi.monthly).mockRejectedValueOnce(new Error('offline')).mockRejectedValueOnce(new Error('offline again')).mockImplementationOnce(()=>new Promise(r=>finish=r))
    wrapper=mount(Monthly,{props:{month:'2026-09',exportsOnly:true}});await flushPromises()
    expect(wrapper.text()).toContain('读取未完成：2026-09 · 冻结报表列表')
    await retry()!.trigger('click');await flushPromises();expect(retry()).toBeDefined()
    await retry()!.trigger('click');await flushPromises()
    expect(workspaceApi.monthly).toHaveBeenLastCalledWith('2026-09')
    expect(wrapper.text()).toContain('正在读取 2026-09 月结进度')
    finish(result('2026-09'));await flushPromises()
    expect(retry()).toBeUndefined();expect(wrapper.emitted('loaded')).toEqual([['2026-09']])
  })
  it('does not let an older month success overwrite a newer failure target',async()=>{
    let finish!:(v:ReturnType<typeof result>)=>void
    vi.mocked(workspaceApi.monthly).mockImplementationOnce(()=>new Promise(r=>finish=r)).mockRejectedValueOnce(new Error('offline'))
    wrapper=mount(Monthly,{props:{month:'2026-09',exportsOnly:true}});await flushPromises()
    await wrapper.setProps({month:'2026-08'});await flushPromises();finish(result('2026-09'));await flushPromises()
    expect(wrapper.text()).toContain('读取未完成：2026-08')
    expect(wrapper.emitted('loaded')).toBeUndefined()
  })
  it.each([401,403])('does not offer a private retry target after authorization status %i',async status=>{
    vi.mocked(workspaceApi.monthly).mockRejectedValue({response:{status}})
    wrapper=mount(Monthly,{props:{month:'2026-09',exportsOnly:true}});await flushPromises()
    expect(retry()).toBeUndefined();expect(wrapper.find('[aria-label="冻结报表列表读取目标"]').exists()).toBe(false)
  })
  it('submits only a month value and ignores completion after unmount',async()=>{
    let finish!:(v:ReturnType<typeof result>)=>void
    const loaded=vi.fn()
    vi.mocked(workspaceApi.monthly).mockResolvedValueOnce(result('2026-09')).mockImplementationOnce(()=>new Promise(r=>finish=r))
    wrapper=mount(Monthly,{props:{month:'2026-09'},attrs:{onLoaded:loaded}});await flushPromises()
    await wrapper.get('form').trigger('submit');expect(workspaceApi.monthly).toHaveBeenLastCalledWith('2026-09')
    wrapper.unmount();finish(result('2026-09'));await flushPromises()
    expect(loaded).toHaveBeenCalledTimes(1);expect(loaded).toHaveBeenCalledWith('2026-09')
  })
})
