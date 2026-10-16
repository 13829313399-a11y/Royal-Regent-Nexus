import { afterEach,beforeEach,describe,expect,it,vi } from 'vitest'
import { mount,flushPromises,type VueWrapper } from '@vue/test-utils'
import CuttingCutover from '../CuttingCutover.vue'
import { cuttingApi,type Access } from '../api'
import { cutoverApi,type CutoverPreview } from '../cutoverApi'
import { advanceAuthenticationGeneration,announceSessionBoundary } from '@/lib/authenticationGeneration'

vi.mock('vue-router',async importOriginal=>({...await importOriginal<typeof import('vue-router')>(),onBeforeRouteLeave:vi.fn(),onBeforeRouteUpdate:vi.fn()}))
vi.mock('../api',()=>({cuttingApi:{access:vi.fn()},errorMessage:()=> '系统依据已变化，请重新读取'}))
vi.mock('../cutoverApi',async importOriginal=>({...await importOriginal<typeof import('../cutoverApi')>(),cutoverApi:{preview:vi.fn()}}))
const access:Access={enabled:true,schema_ready:true,permissions:['read','cost_read','settlement_read','payment_read']}
const info:CutoverPreview={month:'2026-10',start:'2026-10-01',cutoff:'2026-09-30',scope:'internal',generated_at:'2026-10-16',token:'basis-one',
  rows:[{key:'custody:one',category:'现场余料',label:'订单A 蓝布',value:'2.5',unit:'米',sources:['原实发1'],line_id:'order-a',note:'本厂',status:'未核对'}],
  notices:[],external:[],counts:{未核对:1},state:'preparation_only',can_post:false}
let wrapper:VueWrapper
beforeEach(()=>{vi.clearAllMocks();vi.mocked(cuttingApi.access).mockResolvedValue(access);vi.mocked(cutoverApi.preview).mockResolvedValue(structuredClone(info));vi.spyOn(window,'confirm').mockReturnValue(true)})
afterEach(()=>{wrapper?.unmount();vi.restoreAllMocks()})
async function open(){wrapper=mount(CuttingCutover,{props:{access}});await wrapper.get('input[type=month]').setValue('2026-10');await click('读取系统依据')}
async function click(label:string){if(label==='读取系统依据')await wrapper.get('form').trigger('submit');else await wrapper.findAll('button').find(b=>b.text()===label)!.trigger('click');await flushPromises()}
async function edit(){await wrapper.get('input[aria-label=现场余料对照值]').setValue('0');await wrapper.get('input[aria-label=现场余料原始资料依据]').setValue('盘点原表第3行')}

describe('P5a read-only cutover preparation',()=>{
  it('sends explicit zero and evidence without adding the system balance',async()=>{
    await open();await edit();expect(wrapper.text()).toContain('待重新核对')
    await click('核对差异')
    expect(cutoverApi.preview).toHaveBeenLastCalledWith('2026-10','internal',{batch:1,batch_size:50,query:'',token:'basis-one',comparisons:[{key:'custody:one',value:'0',unit:'米',evidence:'盘点原表第3行'}],external:[]},expect.any(AbortSignal))
    expect(wrapper.text()).toContain('不保存期初');expect(wrapper.text()).toContain('不增加库存或应付')
  })
  it('keeps inputs after conflict and refresh but never silently reuses a changed unit',async()=>{
    await open();await edit();vi.mocked(cutoverApi.preview).mockRejectedValueOnce({response:{status:409}})
    await click('核对差异');expect(wrapper.text()).toContain('系统依据已变化')
    vi.mocked(cutoverApi.preview).mockResolvedValue({...info,token:'basis-two',rows:[{...info.rows[0]!,unit:'码'}]})
    await click('读取系统依据');expect((wrapper.get('input[aria-label=现场余料对照值]').element as HTMLInputElement).value).toBe('0')
    await click('核对差异')
    expect(cutoverApi.preview).toHaveBeenLastCalledWith('2026-10','internal',expect.objectContaining({token:'basis-two',comparisons:[expect.objectContaining({unit:'米'})]}),expect.any(AbortSignal))
  })
  it('requires explicit discard on scope switch even after a failed request',async()=>{
    await open();await edit();vi.mocked(cutoverApi.preview).mockRejectedValueOnce({response:{status:409}});await click('核对差异')
    await wrapper.get('select').setValue('finance');vi.mocked(window.confirm).mockReturnValue(false)
    const count=vi.mocked(cutoverApi.preview).mock.calls.length
    await click('读取系统依据');expect(window.confirm).toHaveBeenCalled();expect(cutoverApi.preview).toHaveBeenCalledTimes(count)
  })
  it('retains the form during unrelated parent refresh and clears on revocation',async()=>{
    await open();await edit();await wrapper.setProps({accessLoading:true,access:undefined})
    await wrapper.setProps({accessLoading:false})
    expect(wrapper.text()).not.toContain('订单A 蓝布')
    await wrapper.setProps({access,accessLoading:false})
    expect((wrapper.get('input[aria-label=现场余料对照值]').element as HTMLInputElement).value).toBe('0')
    await wrapper.setProps({access:{...access,permissions:['read']}});await wrapper.setProps({access})
    expect(wrapper.text()).not.toContain('订单A 蓝布')
    await click('读取系统依据');expect((wrapper.get('input[aria-label=现场余料对照值]').element as HTMLInputElement).value).toBe('')
  })
  it('drops responses from an old session and rechecks permissions after preview',async()=>{
    let resolve!:(p:CutoverPreview)=>void
    vi.mocked(cutoverApi.preview).mockImplementationOnce(()=>new Promise(r=>{resolve=r}))
    await open();advanceAuthenticationGeneration();announceSessionBoundary();resolve(info);await flushPromises()
    expect(wrapper.text()).not.toContain('订单A 蓝布')
    vi.mocked(cuttingApi.access).mockResolvedValueOnce(access).mockResolvedValueOnce({...access,permissions:['read']})
    await click('读取系统依据');expect(wrapper.text()).toContain('权限已撤销');expect(wrapper.text()).not.toContain('订单A 蓝布')
  })
  it('never treats empty evidence as a verified zero opening',async()=>{
    vi.mocked(cutoverApi.preview).mockResolvedValue({...info,rows:[],counts:{}});await open()
    expect(wrapper.text()).toContain('不代表账外期初为零');expect(wrapper.text()).toContain('不代表可以正式入账')
  })
})


it('preserves the authorized draft when another scope is selected during parent refresh',async()=>{
  const limited:Access={...access,permissions:['read','cost_read']}
  vi.mocked(cuttingApi.access).mockResolvedValue(limited)
  wrapper=mount(CuttingCutover,{props:{access:limited}})
  await wrapper.get('input[type=month]').setValue('2026-10')
  await click('读取系统依据');await edit()
  expect(wrapper.get('option[value=finance]').attributes('disabled')).toBeDefined()
  await wrapper.get('select').setValue('finance')
  await wrapper.setProps({accessLoading:true,access:undefined})
  await wrapper.setProps({access:limited,accessLoading:false})
  await wrapper.get('select').setValue('internal')
  expect((wrapper.get('input[aria-label=现场余料对照值]').element as HTMLInputElement).value).toBe('0')
  expect(window.confirm).not.toHaveBeenCalled()
})

it('keeps inputs across batches and compares only the visible batch',async()=>{
  const batch={number:1,size:50,total:60,pages:2,unit:'订单',query:''}
  vi.mocked(cutoverApi.preview).mockResolvedValue({...info,batch})
  await open();await edit()
  vi.mocked(cutoverApi.preview).mockResolvedValue({...info,token:'second',batch:{...batch,number:2},rows:[{...info.rows[0]!,key:'custody:two',label:'订单B'}]})
  await click('下一批');await edit();await click('核对差异')
  expect(cutoverApi.preview).toHaveBeenLastCalledWith('2026-10','internal',expect.objectContaining({batch:2,comparisons:[expect.objectContaining({key:'custody:two'})]}),expect.any(AbortSignal))
  vi.mocked(cutoverApi.preview).mockResolvedValue({...info,batch})
  await click('上一批')
  expect((wrapper.get('input[aria-label=现场余料对照值]').element as HTMLInputElement).value).toBe('0')
  expect(wrapper.text()).toContain('不代表全量结论')
})

it('opens exact financial history versions without discarding comparison input',async()=>{
  const target={workspace:'payment',id:'payment-a',event_id:'reverse-a',month:'2026-09'}
  vi.mocked(cutoverApi.preview).mockResolvedValue({...info,history:[{key:'payment:a',document_id:'payment-a',kind:'payment',state:'冲销登记',effective:false,target,history:[{id:'reverse-a',action:'冲销登记',day:'2026-09-01',actor:'会计',actor_id:'acct',date:'2026-10-16',reason:'日期错误',amount:'5.00',currency:'CNY',target}]}]})
  await open();await edit();await click('定位此版本')
  expect(wrapper.emitted('payment')).toEqual([['2026-09','payment-a','reverse-a']])
  expect(wrapper.text()).toContain('日期错误')
  expect((wrapper.get('input[aria-label=现场余料对照值]').element as HTMLInputElement).value).toBe('0')
})


it('renders an exact original-issue link with the cutoff month',async()=>{
  const {createRouter,createMemoryHistory}=await import('vue-router')
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:{template:'<div />'}},{path:'/modules/production/cutting/materials',component:{template:'<div />'}}]})
  await router.push('/');await router.isReady()
  vi.mocked(cutoverApi.preview).mockResolvedValue({...info,rows:[{...info.rows[0]!,target:{workspace:'materials',line_id:'order-a',kind:'issue',id:'issue-1',month:'2026-09'}}]})
  wrapper=mount(CuttingCutover,{props:{access},global:{plugins:[router]}})
  await wrapper.get('input[type=month]').setValue('2026-10');await click('读取系统依据')
  const href=wrapper.get('a').attributes('href')
  expect(href).toContain('/modules/production/cutting/materials?')
  expect(href).toContain('line_id=order-a');expect(href).toContain('focus_id=issue-1');expect(href).toContain('month=2026-09')
})

it('can recover batch one after a stale high batch fails without clearing local input',async()=>{
  vi.mocked(cutoverApi.preview).mockResolvedValue({...info,batch:{number:1,size:50,total:60,pages:2,unit:'订单',query:''}})
  await open();await edit()
  vi.mocked(cutoverApi.preview).mockResolvedValue({...info,batch:{number:2,size:50,total:60,pages:2,unit:'订单',query:''}})
  await click('下一批')
  vi.mocked(cutoverApi.preview).mockRejectedValueOnce({response:{status:409}})
  await click('核对差异');await click('返回第一批重新读取')
  expect(cutoverApi.preview).toHaveBeenLastCalledWith('2026-10','internal',expect.objectContaining({batch:1}),expect.any(AbortSignal))
  expect((wrapper.get('input[aria-label=现场余料对照值]').element as HTMLInputElement).value).toBe('0')
})
