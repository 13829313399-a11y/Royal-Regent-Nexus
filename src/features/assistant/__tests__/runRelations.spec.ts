import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { useAssistantStore } from '@/stores/assistant'
import AssistantPanel from '../AssistantPanel.vue'
import AssistantMessage from '../AssistantMessage.vue'
import { assistantApi } from '../api'
import { relatedDraft } from '../relatedDraft'
import type { Capabilities, Message, SendPayload } from '../types'

vi.mock('vue-router',()=>({useRouter:()=>({push:vi.fn()})}))
const caps: Capabilities={enabled:true,configuration_status:'configured',schema_status:'ready',connection_status:'unverified',verified_at:null,provider:'synthetic',model:'synthetic',help_status:'ready',profiles:[{id:'default',label:'默认',thinking:'unknown',vision:false,web_search:false,function_calling:false}]}
const original: Omit<SendPayload,'client_request_id'>={protocol_version:2,text:'原筛选的订单有多少未走货？',attachment_ids:[],document_ids:[],intent:'my_work',profile_id:'default',thinking:'off',web_search:'off',page_context:{module_id:'customer-orders',route_name:'customer-order-center',factory_id:'huakang-a'},context_selection:{selection_id:'orders',resources:[],filters:{view:'unshipped'}}}
const messages: Message[]=[{id:'u',run_id:'parent',seq:1,role:'user',content_parts:[{type:'text',text:original.text}],status:'completed',help_citations:[],context_descriptor:original.page_context,created_at:1},{id:'a',run_id:'parent',seq:2,role:'assistant',content_parts:[{type:'text',text:'未走货900，历史时点。'}],status:'completed',help_citations:[],context_descriptor:original.page_context,created_at:2}]
let wrappers: ReturnType<typeof mount>[]=[]
beforeEach(()=>{
 vi.restoreAllMocks();setActivePinia(createPinia());document.body.innerHTML='<div id="app"></div>'
 Object.defineProperty(window,'innerWidth',{value:1280,configurable:true,writable:true})
 Object.defineProperty(window,'innerHeight',{value:900,configurable:true,writable:true})
 vi.spyOn(assistantApi,'capabilities').mockResolvedValue(caps)
 vi.spyOn(assistantApi,'sessions').mockResolvedValue({items:[],next_cursor:null})
 vi.spyOn(assistantApi,'question').mockResolvedValue({run_id:'parent',session_id:'s',payload:structuredClone(original)})
 const store=useAssistantStore();store.capabilities=caps;store.selectedId='s';store.messagesBySession.s=structuredClone(messages)
})
afterEach(()=>{wrappers.forEach(w=>w.unmount());wrappers=[];document.body.innerHTML='';vi.unstubAllGlobals()})
function panel(){const w=mount(AssistantPanel,{attachTo:document.body,props:{mode:'side',side:'right',width:460,page:{module_id:'portal',route_name:'dashboard',factory_id:'group'},pageTitle:'系统门户'}});wrappers.push(w);return w}
function button(w:ReturnType<typeof mount>,text:string){return w.findAll('button').find(b=>b.text()===text)!}
async function relatedAction(w:ReturnType<typeof mount>,kind:'revise'|'regenerate'){
 await w.get(`[aria-label="${kind==='revise'?'更多问题操作':'更多回答操作'}"]`).trigger('keydown',{key:'ArrowDown'});await flushPromises()
 const item=[...document.querySelectorAll<HTMLElement>('[role="menuitem"]')].find(el=>el.textContent===(kind==='revise'?'编辑重问':'重新生成新回答'))!
 item.click();await flushPromises()
}

it('restores original scope and relation after reload, then sends a new request without overwriting evidence',async()=>{
 const store=useAssistantStore(), submit=vi.spyOn(store,'submit').mockResolvedValue(undefined)
 const w=panel();await flushPromises()
 expect(w.find('.yl-tail-actions').exists()).toBe(false)
 await relatedAction(w,'revise')
 expect(store.draftFor().text).toBe(original.text)
 expect(store.draftFor().scope?.page).toEqual(original.page_context)
 expect(store.draftFor().scope?.selection).toEqual(original.context_selection)
 expect(store.draftFor().intent).toBe('my_work')
 await w.get('textarea[aria-label="给曜灵的问题"]').setValue('只说明原未走货口径。')
 await w.get('form.yl-composer').trigger('submit');await flushPromises()
 expect(submit).toHaveBeenCalledWith(expect.objectContaining({text:'只说明原未走货口径。',relation:{parent_run_id:'parent',kind:'revise'},page_context:original.page_context,context_selection:original.context_selection}))
 expect(store.messages).toEqual(messages)
})

it('retains an existing draft until explicit replacement and never generates while preparing',async()=>{
 const store=useAssistantStore(), submit=vi.spyOn(store,'submit').mockResolvedValue(undefined)
 store.draftFor().text='未发送的原草稿'
 const w=panel();await flushPromises();await relatedAction(w,'regenerate')
 expect(store.draftFor().text).toBe('未发送的原草稿');expect(w.text()).toContain('替换并关联')
 await button(w,'保留原草稿').trigger('click');expect(store.draftFor().text).toBe('未发送的原草稿')
 await relatedAction(w,'regenerate');await button(w,'替换并关联').trigger('click')
 expect(store.draftFor().relation).toEqual({parent_run_id:'parent',kind:'regenerate'});expect(submit).not.toHaveBeenCalled()
 await button(w,'清除此草稿').trigger('click');await flushPromises();expect(store.draftFor().text).toBe('');expect(store.draftFor().relation).toBeUndefined()
 expect(document.activeElement).toBe(w.get('textarea[aria-label="给曜灵的问题"]').element)
})

it('discards a late frozen question when identity changes',async()=>{
 let resolve!: (value:Awaited<ReturnType<typeof assistantApi.question>>)=>void
 vi.mocked(assistantApi.question).mockImplementation(()=>new Promise(done=>{resolve=done}))
 const w=panel();await flushPromises();await relatedAction(w,'revise')
 const store=useAssistantStore();store.bindIdentity('other-person')
 resolve({run_id:'parent',session_id:'s',payload:original});await flushPromises()
 expect(store.draftFor().text).toBe('');expect(w.text()).not.toContain('发送后创建新回答')
})

it('opens an explicit excerpt editor and carries only the confirmed excerpt into the unsent input',async()=>{
 const w=panel();await flushPromises();await button(w,'继续追问').trigger('click');await flushPromises()
 expect(useAssistantStore().draftFor().text).toBe('')
 await w.get('textarea[aria-label="原回答摘录"]').setValue('未走货900')
 await button(w,'带入输入区').trigger('click');await flushPromises()
 expect(useAssistantStore().draftFor().text).toBe('【原回答摘录】\n未走货900\n\n我的问题：')
 expect(useAssistantStore().draftFor().relation).toEqual({parent_run_id:'parent',kind:'excerpt'})
 expect(useAssistantStore().draftFor().scope?.selection).toBeNull()
 expect(useAssistantStore().draftFor().intent).toBe('chat')
 expect(useAssistantStore().draftFor().search).toBe('off')
})

it('does not use text selected outside the answer as an implicit excerpt',async()=>{
 const outside=document.createElement('p');outside.textContent='其他页面中的私有文字';document.body.append(outside)
 const range=document.createRange();range.selectNodeContents(outside);window.getSelection()!.removeAllRanges();window.getSelection()!.addRange(range)
 const w=mount(AssistantMessage,{props:{message:messages[1]!}});wrappers.push(w)
 await button(w,'继续追问').trigger('click');expect((w.get('textarea[aria-label="原回答摘录"]').element as HTMLTextAreaElement).value).toBe('')
})

it('releases every created image URL when restoring one historical image fails',async()=>{
 vi.stubGlobal('URL',class extends URL {static createObjectURL=vi.fn(()=> 'blob:synthetic');static revokeObjectURL=vi.fn()})
 vi.mocked(assistantApi.question).mockResolvedValue({run_id:'parent',session_id:'s',payload:{...original,attachment_ids:['good','bad']}})
 vi.spyOn(assistantApi,'attachment').mockImplementation(async id=>{if(id==='bad') throw new Error('资料已删除');return new Blob(['image'])})
 await expect(relatedDraft('parent','revise')).rejects.toThrow('资料已删除')
 expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:synthetic')
})
