import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, reactive, ref } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { assistantSelection } from '@/features/assistant/selection'
import { spraySelection, useSprayAssistantContext } from '../assistantContext'
import { guardSprayNavigation, registerSprayNavigationGuard } from '../navigationGuard'
import type { SprayWorkspace } from '../workspace'
import TaskPassport from '../components/TaskPassport.vue'
import OrderPassport from '../components/OrderPassport.vue'

const request=vi.fn()
const w={factory:ref('huaxing'),ready:ref(true),passportId:ref<string|null>(null),taskPassportId:ref<string|null>(null),
  verifiedDemandId:ref<string|null>(null),verifiedTaskId:ref<string|null>(null),contextVersion:ref(1),
  assistantRecord:ref<{id:string;kind:'demand'|'task';label:string}|null>(null),
  assistantView:ref<'demands'|'tasks'|null>(null),relatedDemand:ref(''),readScopes:reactive<Record<string,{ready:boolean;sequence:number;params:Record<string,unknown>;demandId:string}>>({}),
  items:vi.fn(()=>[]),can:(action:string)=>action==='read',query:request,explain:(e:unknown)=>(e as Error).message}
vi.mock('../workspace',()=>({useSprayWorkspace:()=>w}))
const wrappers:VueWrapper[]=[]
const dialogOriginals = ['show','showModal','close'].map(key=>[key,Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype,key)] as const)
const envelope=(data:unknown)=>({meta:{factory_id:'huaxing',as_of:'2026-10-25T12:00:00+08:00'},data})
const task=(id:string)=>({id,factory_id:'huaxing',version:1,updated_at:'2026-10-25T01:00:00Z',quantity:'200',reported:'160',status:'started',
  step:{name:'原喷油工序',input_unit:'件',output_unit:'件',output_ratio:'1'},resource:{name:'合成手喷机',code:'SYN-M'},
  allocations:[],reports:[{id:'R1',document_no:'SYN-日报',business_date:'2026-10-25',processed:'160',good:'150',hold:'0',scrap:'10'}],reports_total:1})
const demand=(id:string)=>({id,factory_id:'huaxing',version:1,document_no:'原喷油需求',counterparty:'合成委托方',lines:[],journey:[],updated_at:'2026-10-25T01:00:00Z'})
beforeEach(()=>{
  w.factory.value='huaxing';w.ready.value=true;w.contextVersion.value=1;w.passportId.value=null;w.taskPassportId.value=null
  w.verifiedDemandId.value=null;w.verifiedTaskId.value=null;w.assistantView.value=null;w.relatedDemand.value=''
  w.assistantRecord.value=null
  Object.keys(w.readScopes).forEach(key=>delete w.readScopes[key]);w.items.mockReturnValue([])
  request.mockReset();request.mockImplementation(async(path:string)=>envelope(path.startsWith('tasks/')?task(path.slice(6)):path.startsWith('demands/')?demand(path.slice(8)):[]))
  vi.stubGlobal('matchMedia',vi.fn(()=>Object.assign(new EventTarget(),{matches:false})))
  for(const key of ['show','showModal','close'])Object.defineProperty(HTMLDialogElement.prototype,key,{configurable:true,writable:true,value:function(this:HTMLDialogElement){if(key==='close')this.removeAttribute('open');else this.setAttribute('open','')}})
})
afterEach(()=>{wrappers.splice(0).forEach(view=>view.unmount());vi.restoreAllMocks();vi.unstubAllGlobals();document.body.innerHTML='';for(const[key,descriptor]of dialogOriginals){if(descriptor)Object.defineProperty(HTMLDialogElement.prototype,key,descriptor);else Reflect.deleteProperty(HTMLDialogElement.prototype,key)}})

async function open(url='/spray?factory=huaxing&spray_task=SYN-T1') {
  const component=defineComponent({setup(){
    const context=useSprayAssistantContext(w as unknown as SprayWorkspace)
    return()=>h('main',{tabindex:-1,'data-spray-focus-fallback':''},[
      h('p',context.sourceError.value),h('button',{onClick:()=>w.taskPassportId.value='SYN-T2'},'原任务按钮'),
      h(TaskPassport),h(OrderPassport)])
  }})
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/spray',name:'spray-execution',component},{path:'/other',component:{template:'other'}}]})
  router.beforeEach(guardSprayNavigation)
  await router.push(url)
  const view=mount(defineComponent({setup:()=>()=>h(RouterView)}),{attachTo:document.body,global:{plugins:[router]}})
  wrappers.push(view);await flushPromises();return{view,router}
}

it('opens the actual read-only task and retains only a verified frozen selection',async()=>{
  const{view,router}=await open()
  expect(request).toHaveBeenCalledWith('tasks/SYN-T1',{},'task-passport')
  expect(view.get('[aria-label="喷油任务档案"]').text()).toContain('SYN-日报')
  expect(view.text()).toContain('合格 150')
  expect(w.verifiedTaskId.value).toBe('SYN-T1')
  const frozen=structuredClone(assistantSelection('spray-production'))
  expect(frozen?.resources).toEqual([{module_id:'spray-production',resource_type:'task',resource_id:'SYN-T1'}])
  await view.get('[aria-label="关闭喷油任务档案"]').trigger('click');await flushPromises()
  expect(router.currentRoute.value.query.spray_task).toBeUndefined()
  expect(w.verifiedTaskId.value).toBeNull()
  expect(assistantSelection('spray-production')?.resources[0]?.resource_id).toBe('SYN-T1')
  w.assistantRecord.value=null
  expect(assistantSelection('spray-production')?.filters.scope_error).toBeTruthy()
  expect(frozen?.resources[0]?.resource_id).toBe('SYN-T1')
})

it('resolves native overview task links and returns focus to the original native button',async()=>{
  const{view,router}=await open('/spray?factory=huaxing&task=SYN-T1')
  expect(w.verifiedTaskId.value).toBe('SYN-T1')
  await view.get('[aria-label="关闭喷油任务档案"]').trigger('click');await flushPromises()
  expect(router.currentRoute.value.query.task).toBeUndefined()
  const button=view.get('main > button');(button.element as HTMLElement).focus();await button.trigger('click');await flushPromises()
  expect(w.verifiedTaskId.value).toBe('SYN-T2')
  await view.get('[aria-label="喷油任务档案"]').trigger('cancel');await flushPromises()
  expect(document.activeElement).toBe(button.element)
})

it('retries original failures, refuses wrong records, and never exposes a late A→B→A response',async()=>{
  request.mockRejectedValueOnce(new Error('原任务暂不可用'))
  const{view}=await open()
  expect(view.text()).toContain('原任务暂不可用')
  expect(assistantSelection('spray-production')?.resources).toEqual([])
  await view.get('[aria-label="喷油任务档案"] .spray-secondary').trigger('click');await flushPromises()
  expect(w.verifiedTaskId.value).toBe('SYN-T1')
  expect(document.activeElement).toBe(view.get('[aria-label="喷油任务档案"]').element)
  let resolve!:(value:unknown)=>void
  request.mockImplementationOnce(()=>new Promise(value=>{resolve=value}))
  w.taskPassportId.value='A';await nextTick()
  w.taskPassportId.value='B';await flushPromises()
  w.taskPassportId.value='A';await flushPromises()
  resolve(envelope({...task('A'),step:{...task('A').step,name:'STALE-PRIVATE'}}));await flushPromises()
  expect(view.text()).not.toContain('STALE-PRIVATE');expect(w.verifiedTaskId.value).toBe('A')
  request.mockResolvedValueOnce(envelope(task('WRONG')));w.taskPassportId.value='C';await flushPromises()
  expect(view.text()).toContain('返回的任务与所选来源不一致')
  expect(w.verifiedTaskId.value).toBeNull()
  expect(w.assistantRecord.value).toBeNull()
})

it('closes a wide nonmodal passport with Escape and keeps its verified query scope',async()=>{
  vi.stubGlobal('matchMedia',vi.fn(()=>Object.assign(new EventTarget(),{matches:true})))
  const {view}=await open()
  await view.get('[aria-label="喷油任务档案"]').trigger('keydown',{key:'Escape'})
  await flushPromises()
  expect(w.taskPassportId.value).toBeNull()
  expect(assistantSelection('spray-production')?.resources[0]?.resource_id).toBe('SYN-T1')
})

it('opens demand source, retries a missing source and clears private details synchronously',async()=>{
  request.mockRejectedValueOnce(new Error('需求未找到'))
  const{view}=await open('/spray?factory=huaxing&spray_demand=SYN-D1')
  expect(w.verifiedDemandId.value).toBeNull()
  await view.get('[aria-label="订单追踪"] .spray-secondary').trigger('click');await flushPromises()
  expect(w.verifiedDemandId.value).toBe('SYN-D1')
  expect(assistantSelection('spray-production')?.resources[0]?.resource_type).toBe('demand')
  w.ready.value=false;w.contextVersion.value++
  expect(w.verifiedDemandId.value).toBeNull()
  await nextTick();expect(view.text()).not.toContain('原喷油需求')
})

it.each(['spray_task=A&spray_task=B','spray_task=A&spray_demand=B','spray_task=A&task=B'])('rejects ambiguous source parameters %s without a read',async(query)=>{
  const{view}=await open('/spray?factory=huaxing&'+query)
  expect(view.text()).toContain('来源编号无效')
  expect(request).not.toHaveBeenCalled()
  expect(assistantSelection('spray-production')?.filters.scope_error).toBeTruthy()
})

it('freezes successful native filters, excludes pagination and refuses unverified or changed scope',()=>{
  w.assistantView.value='tasks'
  w.readScopes.tasks={ready:true,sequence:1,params:{task_scope:'active',page:2,page_size:200},demandId:''}
  const first=spraySelection(w as unknown as SprayWorkspace)
  expect(first.filters).toMatchObject({factory_id:'huaxing',view:'tasks',task_scope:'active'})
  expect(first.filters.page).toBeUndefined()
  w.relatedDemand.value='D1'
  expect(spraySelection(w as unknown as SprayWorkspace).filters.scope_error).toBeTruthy()
  w.relatedDemand.value='';w.readScopes.tasks!.ready=false
  expect(spraySelection(w as unknown as SprayWorkspace).filters.scope_error).toBeTruthy()
  w.assistantView.value='demands';w.readScopes.demands={ready:true,sequence:2,params:{search:'原单_%'},demandId:''}
  expect(spraySelection(w as unknown as SprayWorkspace).filters.q).toBe('原单_%')
  expect(first.filters.task_scope).toBe('active')
})

it('protects real scope changes before factory mutation but permits readonly source changes',async()=>{
  let dirty=true,pending=false,factory='huaxing'
  const confirm=vi.fn(()=>false)
  const unregister=registerSprayNavigationGuard(()=>!pending&&(!dirty||confirm()))
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/spray',component:{template:'spray'}},{path:'/login',name:'login',component:{template:'login'}}]})
  router.beforeEach(async(to,from)=>{if(!await guardSprayNavigation(to,from))return false;factory=String(to.query.factory??'');return true})
  dirty=false;await router.push('/spray?factory=huaxing');dirty=true
  await router.push('/spray?factory=huakang-a');expect(factory).toBe('huaxing')
  await router.push('/spray?factory=huaxing&spray_task=T1');expect(router.currentRoute.value.query.spray_task).toBe('T1')
  pending=true;confirm.mockReturnValue(true);await router.push('/spray?factory=huakang-a');expect(factory).toBe('huaxing')
  pending=false;await router.push('/spray?factory=huakang-a');expect(factory).toBe('huakang-a')
  pending=true;await router.push('/login');expect(router.currentRoute.value.name).toBe('login');unregister()
})
