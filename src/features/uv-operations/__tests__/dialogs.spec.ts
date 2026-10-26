import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, reactive, ref } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import UvActionDialog from '../components/UvActionDialog.vue'
import RunMatchDialog from '../components/RunMatchDialog.vue'
import TaskPassport from '../components/TaskPassport.vue'
import { provideUvMotionPreference } from '../composables/useUvMotionPreference'
import { UvError } from '../workspace'
import type { Entity } from '../contracts'

const command=vi.fn(),request=vi.fn(),load=vi.fn()
const w={contextVersion:ref(1),selectedTaskId:ref<string|null>(null),verifiedTaskId:ref<string|null>(null),notification:ref(''),can:()=>true,command,request,load,refresh:vi.fn(),explain:(cause:unknown)=>(cause as Error).message,items:()=>[],pagination:{}}
vi.mock('../workspace',()=>({useUvWorkspace:()=>w,UvError:class extends Error{constructor(message:string,public status=0,public code='',public fields:Record<string,string>={}){super(message)}}}))
const deferred=<T,>()=>{let resolve!:(value:T)=>void,reject!:(error:unknown)=>void;const promise=new Promise<T>((a,b)=>{resolve=a;reject=b});return{resolve,reject,promise}}
const run=(id='RUN'):Entity=>({id,version:7,native_job_id:'合成作业 '+id})
const wrappers:VueWrapper[]=[]
const keep=<T extends VueWrapper>(wrapper:T)=>{wrappers.push(wrapper);return wrapper}

beforeEach(()=>{
  command.mockReset();request.mockReset();load.mockReset();load.mockResolvedValue(undefined);command.mockResolvedValue({id:'saved',version:1})
  w.selectedTaskId.value=null;w.verifiedTaskId.value=null;w.contextVersion.value=1
  vi.stubGlobal('matchMedia',vi.fn(()=>Object.assign(new EventTarget(),{matches:false})))
  vi.stubGlobal('ResizeObserver',class{observe(){}disconnect(){}})
  vi.spyOn(document,'hidden','get').mockReturnValue(false)
  vi.spyOn(HTMLElement.prototype,'getClientRects').mockReturnValue([{width:20,height:20}] as unknown as DOMRectList)
  HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');this.querySelector<HTMLElement>('button,input,select')?.focus()}
  HTMLDialogElement.prototype.close=function(){this.removeAttribute('open')}
})
afterEach(()=>{wrappers.splice(0).forEach(wrapper=>wrapper.unmount());vi.restoreAllMocks();vi.unstubAllGlobals();vi.useRealTimers();document.body.innerHTML='';localStorage.clear()})

describe('UV task passport request identity',()=>{
  it('returns narrow-modal keyboard focus to the original task after background inert cleanup',async()=>{
    vi.stubGlobal('matchMedia',vi.fn(()=>Object.assign(new EventTarget(),{matches:true})))
    request.mockResolvedValue({data:{id:'A',version:1,code:'TASK-A',batches:[]}})
    const wrapper=keep(mount(defineComponent({setup(){
      provideUvMotionPreference(()=>'USER').setPreference('off')
      return()=>h('main',{'data-uv-focus-fallback':'',tabindex:-1},[
        h('button',{onClick:()=>{w.selectedTaskId.value='A'}},'原任务入口'),h(TaskPassport),
      ])
    }}),{attachTo:document.body,global:{stubs:{RouterLink:true}}}))
    const opener=wrapper.get('button');(opener.element as HTMLButtonElement).focus()
    await opener.trigger('click');await flushPromises()
    const panel=document.querySelector<HTMLElement>('[aria-label="任务档案"]')!
    expect(panel.getAttribute('aria-modal')).toBe('true')
    expect(document.activeElement).toBe(panel)
    panel.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));await flushPromises()
    expect(document.querySelector('[aria-label="任务档案"]')).toBeNull()
    expect(document.activeElement).toBe(opener.element)
  })
  it('keeps reopened B and its quality tab when the interrupted A exit deadline passes',async()=>{
    vi.useFakeTimers({toFake:['setTimeout','clearTimeout']})
    request.mockImplementation(async(path:string)=>({data:{id:path.slice(6),version:1,code:path.slice(6),batches:[]}}))
    const wrapper=keep(mount(defineComponent({setup(){provideUvMotionPreference(()=>'USER');return()=>h(TaskPassport)}}),{attachTo:document.body,global:{stubs:{RouterLink:true}}}))
    w.selectedTaskId.value='A';await flushPromises()
    const panel=wrapper.get('.uv-passport').element as HTMLElement
    panel.style.setProperty('--uv-motion-leave','180ms')
    w.selectedTaskId.value=null;await flushPromises()
    expect(wrapper.get('.uv-passport').attributes('data-phase')).toBe('closing')
    expect(wrapper.text()).toContain('A')
    await vi.advanceTimersByTimeAsync(60)
    w.selectedTaskId.value='B';await flushPromises()
    await wrapper.findAll('[role="tab"]').find(t=>t.text()==='品质')!.trigger('click')
    await vi.advanceTimersByTimeAsync(250);await flushPromises()
    expect(wrapper.get('.uv-passport h2').text()).toBe('B')
    expect(wrapper.get('[role="tab"][aria-selected="true"]').text()).toBe('品质')
    expect(wrapper.get('.uv-passport').attributes('data-phase')).toBe('open')
  })
  it('ignores a late successful A response after B has populated the passport',async()=>{
    const a=deferred<{data:Entity}>(),b=deferred<{data:Entity}>()
    request.mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise)
    const wrapper=keep(mount(TaskPassport,{attachTo:document.body,global:{stubs:{RouterLink:true}}}))
    w.selectedTaskId.value='A';await flushPromises();w.selectedTaskId.value='B';await flushPromises()
    b.resolve({data:{id:'B',version:2,code:'CURRENT-B',quantity:'25',batches:[]}});await flushPromises()
    a.resolve({data:{id:'A',version:99,code:'STALE-A',quantity:'999',batches:[]}});await flushPromises()
    expect(wrapper.text()).toContain('CURRENT-B');expect(wrapper.text()).toContain('25 pcs')
    expect(wrapper.text()).not.toContain('STALE-A');expect(wrapper.text()).not.toContain('999 pcs')
    expect(wrapper.find('[aria-busy="true"]').exists()).toBe(false)
  })
  it('ignores late A errors while B succeeds and ignores detail responses after close',async()=>{
    const a=deferred<{data:Entity}>(),b=deferred<{data:Entity}>(),c=deferred<{data:Entity}>()
    request.mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise).mockReturnValueOnce(c.promise)
    const wrapper=keep(mount(TaskPassport,{attachTo:document.body,global:{stubs:{RouterLink:true}}}))
    w.selectedTaskId.value='A';await flushPromises();w.selectedTaskId.value='B';await flushPromises()
    b.resolve({data:{id:'B',version:1,code:'TASK-B',batches:[]}});await flushPromises()
    a.reject(new Error('STALE-A'));await flushPromises()
    expect(wrapper.text()).toContain('TASK-B');expect(wrapper.text()).not.toContain('STALE-A')
    w.selectedTaskId.value='C';await flushPromises();w.selectedTaskId.value=null;await flushPromises()
    c.resolve({data:{id:'C',version:1,code:'LATE-C'}});await flushPromises()
    expect(wrapper.find('.uv-passport').exists()).toBe(false)
  })
  it('clears visible details immediately on authorization context changes',async()=>{
    request.mockResolvedValue({data:{id:'A',version:1,code:'SENSITIVE',batches:[]}})
    const wrapper=keep(mount(TaskPassport,{global:{stubs:{RouterLink:true}}}))
    w.selectedTaskId.value='A';await flushPromises();expect(wrapper.text()).toContain('SENSITIVE')
    w.contextVersion.value++;await nextTick();expect(wrapper.text()).not.toContain('SENSITIVE');expect(w.selectedTaskId.value).toBeNull()
  })
})

describe('UV native form submission sessions',()=>{
  it('does not let a prior native dialog exit close a newly opened action',async()=>{
    vi.useFakeTimers({toFake:['setTimeout','clearTimeout']})
    const props=reactive<{action:string|null}>({action:'product'})
    const wrapper=keep(mount(defineComponent({setup(){provideUvMotionPreference(()=>'USER');return()=>h(UvActionDialog,props)}}),{attachTo:document.body,global:{stubs:{CollectionFooter:true}}}))
    await flushPromises();(wrapper.get('dialog').element as HTMLElement).style.setProperty('--uv-motion-leave','180ms')
    await wrapper.findAll('input')[0]!.setValue('OLD')
    props.action=null;await flushPromises();expect(wrapper.get('dialog').attributes('data-phase')).toBe('closing')
    await vi.advanceTimersByTimeAsync(60);props.action='fixture';await flushPromises()
    await wrapper.findAll('input')[0]!.setValue('NEW-FIXTURE')
    await vi.advanceTimersByTimeAsync(250);await flushPromises()
    expect(wrapper.get('dialog').attributes('open')).toBeDefined()
    expect((wrapper.findAll('input')[0]!.element as HTMLInputElement).value).toBe('NEW-FIXTURE')
    expect(wrapper.text()).not.toContain('新建产品');expect(command).not.toHaveBeenCalled()
  })
  it('blocks duplicate submit and saving Escape, then discards a late result after forced context clear',async()=>{
    const pending=deferred<Entity>();command.mockReturnValue(pending.promise)
    const wrapper=keep(mount(UvActionDialog,{props:{action:'product'},global:{stubs:{CollectionFooter:true}}}));await flushPromises()
    await wrapper.get('form').trigger('submit');await wrapper.get('form').trigger('submit');await wrapper.get('dialog').trigger('cancel')
    expect(command).toHaveBeenCalledTimes(1);expect(wrapper.emitted('close')).toBeUndefined()
    w.contextVersion.value++;await nextTick();pending.resolve({id:'LATE',version:1});await flushPromises()
    expect(wrapper.emitted('saved')).toBeUndefined();expect(wrapper.find('form').exists()).toBe(false)
  })
  it('keeps 409 inputs, connects field errors and focuses the invalid control',async()=>{
    command.mockRejectedValue(new UvError('编号冲突',409,'conflict',{'body.code':'此编号已存在'}))
    const wrapper=keep(mount(UvActionDialog,{attachTo:document.body,props:{action:'product'},global:{stubs:{CollectionFooter:true}}}));await flushPromises()
    await wrapper.findAll('input')[0]!.setValue('KEEP-CODE');await wrapper.get('form').trigger('submit');await flushPromises()
    const input=wrapper.findAll('input')[0]!
    expect((input.element as HTMLInputElement).value).toBe('KEEP-CODE');expect(input.attributes('aria-invalid')).toBe('true')
    expect(wrapper.text()).toContain('输入已保留');expect(document.activeElement).toBe(input.element)
    expect(document.getElementById(input.attributes('aria-describedby')!)).not.toBeNull()
  })
  it('keeps pairing code results in the open native dialog',async()=>{
    command.mockResolvedValue({id:'AGENT',version:1,pairing_code:'SYNTHETIC-CODE'})
    const wrapper=keep(mount(UvActionDialog,{props:{action:'agent'},global:{stubs:{CollectionFooter:true}}}));await flushPromises()
    await wrapper.get('form').trigger('submit');await flushPromises()
    expect(wrapper.text()).toContain('SYNTHETIC-CODE');expect(wrapper.get('dialog').attributes('open')).toBeDefined();expect(wrapper.emitted('close')).toBeUndefined()
  })
  it('preserves operation id, payload and version when an uncertain form close is cancelled',async()=>{
    command.mockRejectedValue(new UvError('unknown',503))
    const props=reactive({action:'machineEdit' as string|null,target:{id:'M',version:4},preset:{code:'M',name:'Original'}})
    const wrapper=keep(mount(defineComponent({setup(){provideUvMotionPreference(()=>'USER');return()=>h(UvActionDialog,props)}}),{attachTo:document.body,global:{stubs:{CollectionFooter:true}}}))
    await flushPromises();const dialog=wrapper.get('dialog').element as HTMLElement;dialog.style.setProperty('--uv-motion-leave','180ms')
    await wrapper.get('form').trigger('submit');await flushPromises();const first=command.mock.calls[0]!
    props.action=null;await nextTick();props.target={id:'M',version:99};props.action='machineEdit';await flushPromises()
    await wrapper.get('form').trigger('submit');await flushPromises()
    expect(command.mock.calls[1]![1]).toEqual(first[1]);expect(command.mock.calls[1]![2]).toBe(first[2]);expect(command.mock.calls[1]![1].expected_version).toBe(4)
  })
  it('keeps the same receipt operation and prevents concurrent receipt requests',async()=>{
    command.mockRejectedValue(new UvError('unknown',503));const receipt=deferred<{data:Entity}>();request.mockReturnValue(receipt.promise)
    const wrapper=keep(mount(UvActionDialog,{props:{action:'product'},global:{stubs:{CollectionFooter:true}}}));await flushPromises()
    await wrapper.get('form').trigger('submit');await flushPromises()
    const check=wrapper.findAll('button').find(button=>button.text()==='核对上次回执')!
    await check.trigger('click');await check.trigger('click')
    expect(request).toHaveBeenCalledTimes(1);expect(request.mock.calls[0]![0]).toBe('receipts/'+command.mock.calls[0]![2])
    receipt.reject(new UvError('none',404));await flushPromises();expect(wrapper.text()).toContain('回执尚未生成')
  })
})

describe('UV run allocation presentation',()=>{
  it('keeps row DOM identity after deleting the middle allocation and strips UI keys from payload',async()=>{
    const wrapper=keep(mount(RunMatchDialog,{props:{run:run()},global:{stubs:{CollectionFooter:true}}}));await flushPromises()
    const add=()=>wrapper.findAll('button').find(button=>button.text()==='追加拼版任务')!
    await add().trigger('click');await add().trigger('click')
    const third=wrapper.findAll('.uv-allocation-row')[2]!.findAll('input')[1]!
    await third.setValue('7,8');await wrapper.findAll('.uv-allocation-row')[1]!.get('button').trigger('click')
    expect(wrapper.findAll('.uv-allocation-row')[1]!.findAll('input')[1]!.element).toBe(third.element)
    await wrapper.get('form').trigger('submit');await flushPromises()
    expect(command.mock.calls[0]![1].allocations).toHaveLength(2)
    expect(command.mock.calls[0]![1].allocations.every((row:Record<string,unknown>)=>!('key' in row))).toBe(true)
  })
  it('preserves the original run version and operation on uncertain close/reopen and retry',async()=>{
    command.mockRejectedValue(new UvError('unknown',503))
    const props=reactive<{run:Entity|null}>({run:run()})
    const wrapper=keep(mount(defineComponent({setup(){provideUvMotionPreference(()=>'USER');return()=>h(RunMatchDialog,props)}}),{attachTo:document.body,global:{stubs:{CollectionFooter:true}}}));await flushPromises()
    const dialog=wrapper.get('dialog').element as HTMLElement;dialog.style.setProperty('--uv-motion-leave','180ms')
    await wrapper.get('textarea').setValue('不可变核对依据');await wrapper.get('form').trigger('submit');await flushPromises();const first=command.mock.calls[0]!
    props.run=null;await nextTick();props.run={...run(),version:55};await flushPromises()
    await wrapper.get('form').trigger('submit');await flushPromises()
    expect(command.mock.calls[1]![1]).toEqual(first[1]);expect(command.mock.calls[1]![2]).toBe(first[2]);expect(first[1].expected_version).toBe(7)
  })
})
