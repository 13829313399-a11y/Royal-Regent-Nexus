import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, nextTick, defineComponent, h } from 'vue'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ImportsPage from '../pages/ImportsPage.vue'
import ShiftsPage from '../pages/ShiftsPage.vue'
import PlanningPage from '../pages/PlanningPage.vue'
import SettingsPage from '../pages/SettingsPage.vue'
import { UvError } from '../workspace'
import type { Entity } from '../contracts'
const request=vi.fn(),command=vi.fn(),load=vi.fn(),replace=vi.fn()
const data=ref<Record<string,Entity[]>>({})
const route={query:{} as Record<string,string>}
const w={contextVersion:ref(1),meta:ref({view_revision:1}),notification:ref(''),ready:ref(true),assistantListReady:ref(false),pagination:{},can:()=>true,items:(name:string)=>data.value[name]??[],request,command,load,explain:(e:unknown)=>(e as Error).message,selectedTaskId:ref(null)}
vi.mock('../workspace',()=>({useUvWorkspace:()=>w,UvError:class extends Error{constructor(message:string,public status=0){super(message)}}}))
vi.mock('vue-router',()=>({useRoute:()=>route,useRouter:()=>({replace}),onBeforeRouteLeave:vi.fn()}))
const deferred=<T,>()=>{let resolve!:(v:T)=>void,reject!:(e:unknown)=>void;const promise=new Promise<T>((a,b)=>{resolve=a;reject=b});return{promise,resolve,reject}}
const wrappers:VueWrapper[]=[]
const keep=<T extends VueWrapper>(v:T)=>{wrappers.push(v);return v}
const stubs={UvActionDialog:true,RunMatchDialog:true,CollectionFooter:true,RouterLink:true}
const button=(v:VueWrapper,label:string)=>v.findAll('button').find(b=>b.text()===label)!
const shift=()=>({id:'S',version:1,status:'open',name:'QA'})
const task=(id='T'):Entity=>({id,version:1,code:id,batches:[{id:'B',version:1,task_id:id,pass_index:1,remaining:100}],process_snapshot:{fixture_id:'F'},schedule:[]})
beforeEach(()=>{
 request.mockReset();command.mockReset();load.mockReset();replace.mockReset()
 command.mockResolvedValue({id:'OK',version:1});load.mockResolvedValue(undefined);replace.mockResolvedValue(undefined)
 route.query={shift:'S'};w.contextVersion.value=1;w.notification.value=''
 data.value={shifts:[shift()],tasks:[task(),task('T2')],batches:[{id:'B',version:1,task_id:'T',pass_index:1,remaining:100}],machines:[{id:'M',version:1,code:'M'}],fixtures:[{id:'F',version:1,code:'F'}]}
 request.mockImplementation(async(path:string)=>({data:path.endsWith('/gaps')?{totals:{},missing_participation:[],pending_quality:[],unmatched_runs:[]}:path==='imports/templates'?{'products-v1':{fields:['code'],permissions:[]}}:path.startsWith('tasks/')?task(path.slice(6)):[]}))
 vi.stubGlobal('ResizeObserver',class{observe(){}disconnect(){}})
 vi.spyOn(document,'hidden','get').mockReturnValue(false)
})
afterEach(()=>{wrappers.splice(0).forEach(v=>v.unmount());vi.restoreAllMocks();vi.unstubAllGlobals();vi.useRealTimers();document.body.innerHTML=''})
async function addRow(v:VueWrapper){
 await button(v,'添加核数行').trigger('click')
 const row=v.findAll('[data-row-state]').at(-1)!
 await row.findAll('select')[0]!.setValue('T');await row.findAll('select')[1]!.setValue('B')
 await row.findAll('input')[0]!.setValue(10);await row.findAll('input')[1]!.setValue(10);await row.findAll('input')[5]!.setValue('人工计数依据')
 return row
}
describe('UV reconciliation submission boundaries',()=>{
 it('stops queued rows on unmount while the first confirmation is pending',async()=>{
  const pending=deferred<Entity>();command.mockReturnValue(pending.promise)
  const v=keep(mount(ShiftsPage,{global:{stubs}}));await flushPromises();await addRow(v);await addRow(v)
  await button(v,'确认有效行').trigger('click');expect(command).toHaveBeenCalledTimes(1)
  v.unmount();pending.resolve({id:'OK',version:1});await flushPromises();expect(command).toHaveBeenCalledTimes(1)
 })
 it('retains confirmed state when post-command list refresh fails',async()=>{
  const v=keep(mount(ShiftsPage,{global:{stubs}}));await flushPromises();const row=await addRow(v)
  load.mockRejectedValueOnce(new UvError('refresh denied',422))
  await row.get('[data-confirm]').trigger('click');await flushPromises()
  expect(row.attributes('data-row-state')).toBe('saved');expect(v.text()).toContain('核数已确认，列表刷新失败')
  expect(command).toHaveBeenCalledTimes(1);expect(row.find('[data-confirm]').exists()).toBe(false)
 })
 it('retries the frozen uncertain submission even if the live shift closes',async()=>{
  command.mockRejectedValueOnce(new UvError('unknown',503))
  const v=keep(mount(ShiftsPage,{global:{stubs}}));await flushPromises();const row=await addRow(v)
  await row.get('[data-confirm]').trigger('click');await flushPromises();const first=command.mock.calls[0]!
  data.value={...data.value,shifts:[{...shift(),status:'closed'}]};await nextTick()
  await row.get('[data-confirm]').trigger('click');await flushPromises()
  expect(command.mock.calls[1]).toEqual(first);expect(row.attributes('data-row-state')).toBe('saved')
 })
 it('keeps draft DOM, caret and IME Enter through live revision updates',async()=>{
  const v=keep(mount(ShiftsPage,{attachTo:document.body,global:{stubs}}));await flushPromises();const row=await addRow(v)
  const input=row.findAll('input')[5]!.element as HTMLInputElement;input.focus();input.setSelectionRange(2,2)
  w.meta.value={view_revision:2};await flushPromises()
  expect(row.findAll('input')[5]!.element).toBe(input);expect(input.selectionStart).toBe(2)
  const event=new KeyboardEvent('keydown',{key:'Enter',isComposing:true,bubbles:true,cancelable:true});input.dispatchEvent(event)
  expect(event.defaultPrevented).toBe(false);expect(document.activeElement).toBe(input)
 })
})
describe('UV import/export asynchronous boundaries',()=>{
 it('ignores a late failed poll after the user uploads a replacement file',async()=>{
  vi.useFakeTimers();route.query={import_job:'I'};const pending=deferred<{data:Entity}>();let reads=0
  request.mockImplementation(async(path:string)=>path==='imports/templates'?{data:{'products-v1':{fields:['code'],permissions:[]}}}:path==='imports/I'?(++reads===1?{data:{id:'I',version:1,status:'processing'}}:pending.promise):path==='imports/preview'?{data:{id:'NEW',version:1,status:'preview',valid_count:1}}:{data:[]})
  const v=keep(mount(ImportsPage));await flushPromises();await vi.advanceTimersByTimeAsync(3000);await flushPromises()
  const input=v.get('input[type=file]');Object.defineProperty(input.element,'files',{value:[new File(['code\nQA'],'qa.csv')],configurable:true});await input.trigger('change')
  await v.findAll('form')[0]!.trigger('submit');await flushPromises();pending.reject(new Error('OLD-POLL'));await flushPromises()
  expect(v.text()).not.toContain('OLD-POLL');expect(v.text()).toContain('确认导入全部有效行')
 })
 it('does not lock export input for invalid local record selection',async()=>{
  route.query={};const v=keep(mount(ImportsPage));await flushPromises()
  const form=v.findAll('form')[1]!
  await form.findAll('select')[1]!.setValue('selected');await form.get('textarea').setValue(' , ， ')
  await form.trigger('submit');await flushPromises()
  expect(command).not.toHaveBeenCalled();expect(v.text()).toContain('至少一个记录 ID')
  expect(form.get('fieldset').attributes('disabled')).toBeUndefined()
 })
 it('does not overwrite a newly created export with an older list response',async()=>{
  const old=deferred<{data:Entity[]}>();let reads=0
  request.mockImplementation(async(path:string)=>path==='imports/templates'?{data:{}}:path==='exports'?(++reads===1?old.promise:{data:[{id:'E',version:1,kind:'production',status:'ready'}]}):{data:[]})
  route.query={};const v=keep(mount(ImportsPage));await flushPromises()
  await v.findAll('form')[1]!.trigger('submit');await flushPromises()
  expect(v.text()).toContain('下载 XLSX');old.resolve({data:[]});await flushPromises();expect(v.text()).toContain('下载 XLSX')
 })
 it('stops hidden polling, resumes once, and does not resurrect timers after unmount',async()=>{
  vi.useFakeTimers();route.query={import_job:'I'};const pending=deferred<{data:Entity}>();let reads=0
  request.mockImplementation(async(path:string)=>path==='imports/templates'?{data:{}}:path==='imports/I'?(++reads===1?{data:{id:'I',version:1,status:'processing'}}:pending.promise):{data:[]})
  const v=keep(mount(ImportsPage));await flushPromises()
  vi.spyOn(document,'hidden','get').mockReturnValue(true);document.dispatchEvent(new Event('visibilitychange'))
  await vi.advanceTimersByTimeAsync(10000);expect(reads).toBe(1)
  vi.spyOn(document,'hidden','get').mockReturnValue(false);document.dispatchEvent(new Event('visibilitychange'));await flushPromises();expect(reads).toBe(2)
  v.unmount();pending.resolve({data:{id:'I',version:1,status:'processing'}});await flushPromises();await vi.advanceTimersByTimeAsync(10000);expect(reads).toBe(2)
 })
 it('stops polling after an import reaches preview',async()=>{
  vi.useFakeTimers();route.query={import_job:'I'};let reads=0
  request.mockImplementation(async(path:string)=>path==='imports/templates'?{data:{}}:path==='imports/I'?{data:{id:'I',version:1,status:++reads===1?'processing':'preview'}}:{data:[]})
  keep(mount(ImportsPage));await flushPromises();await vi.advanceTimersByTimeAsync(3000);await flushPromises();expect(reads).toBe(2)
  await vi.advanceTimersByTimeAsync(9000);expect(reads).toBe(2)
 })
})
describe('UV file upload lifetime',()=>{
 it('does not post an old upload success notification after leaving during refresh',async()=>{
  data.value={...data.value,'process-versions':[{id:'P',version:1,name:'工艺',revision:1}]}
  const pending=deferred<void>();request.mockResolvedValue({data:{id:'FILE',version:1}})
  const v=keep(mount(SettingsPage,{global:{stubs}}));await flushPromises()
  await v.findAll('[role=tab]')[1]!.trigger('click');await button(v,'上传文件').trigger('click')
  await v.get('form select').setValue('P');const input=v.get('input[type=file]');Object.defineProperty(input.element,'files',{value:[new File(['qa'],'qa.prn')],configurable:true});await input.trigger('change')
  load.mockReturnValueOnce(pending.promise);await v.get('form').trigger('submit');await flushPromises();v.unmount()
  pending.resolve();await flushPromises();expect(w.notification.value).toBe('')
 })
})
describe('UV planning response identity',()=>{
 it.each([[208,'02:30'],[211,'02:45'],[95,'00:00'],[1105,'00:00']])('previews a snapped drag at x=%s without committing production or schedule',async(x,time)=>{
  const date='2026-10-21',start=date+'T10:00:00+08:00',end=date+'T12:00:00+08:00'
  const plan:Entity={id:'PLAN',version:1,task_id:'T',batch_id:'B',machine_id:'M',fixture_id:'F',start_at:start,end_at:end,status:'planned'}
  const details={...task(),process_snapshot:{fixture_id:'F',cycle_seconds:60},schedule:[plan]}
  data.value.machines=[{id:'M',version:1,code:'M'},{id:'M2',version:1,code:'M2'}]
  request.mockImplementation(async(path:string)=>({data:path==='schedule/window'?[plan]:path==='tasks/T'?details:path==='schedule/preview'?{id:'P',version:1,can_commit:true,conflicts:[],warnings:[]}:[]}))
  const v=keep(mount(PlanningPage,{global:{stubs}}));await flushPromises()
  await v.get('input[type="date"]').setValue(date);await flushPromises()
  const track=v.get('[data-machine="M2"]')
  vi.spyOn(track.element,'getBoundingClientRect').mockReturnValue({left:100,width:1000} as DOMRect)
  await v.get('[data-plan="PLAN"]').trigger('dragstart')
  await track.trigger('drop',{clientX:x});await flushPromises()
  const previews=request.mock.calls.filter(([path])=>path==='schedule/preview')
  expect(previews).toHaveLength(1)
  const block=JSON.parse(previews[0]![1].body).blocks[0]
  const targetDay=x>1100?'2026-10-22':date
  expect(new Date(block.start_at).valueOf()).toBe(new Date(targetDay+'T'+time+':00+08:00').valueOf())
  expect(new Date(block.end_at).valueOf()-new Date(block.start_at).valueOf()).toBe(7200000)
  expect(block.machine_id).toBe('M2');expect(command).not.toHaveBeenCalled()
 })
 it('ignores an old detail error from refresh after another task is selected',async()=>{
  const pending=deferred<{data:Entity}>();let reads=0
  request.mockImplementation(async(path:string)=>path==='tasks/T'?(++reads===1?{data:task()}:pending.promise):path==='tasks/T2'?{data:task('T2')}:{data:[]})
  const v=keep(mount(PlanningPage,{global:{stubs}}));await flushPromises()
  const select=v.get('.uv-plan-form select');await select.setValue('T');await flushPromises()
  await button(v,'刷新').trigger('click');await flushPromises()
  await select.setValue('T2');await flushPromises();pending.reject(new Error('STALE-T'));await flushPromises()
  expect(v.text()).not.toContain('STALE-T');expect((select.element as HTMLSelectElement).value).toBe('T2')
 })
})
