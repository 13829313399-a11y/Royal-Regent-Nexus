import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { useAssistantStore } from '@/stores/assistant'
import { acquireBodyScrollLock } from '@/lib/bodyScrollLock'
import AssistantPanel from '../AssistantPanel.vue'
import AssistantDocument from '../AssistantDocument.vue'
import { assistantApi } from '../api'
import type { Capabilities, HelpArticle } from '../types'

const caps: Capabilities={enabled:true,configuration_status:'unconfigured',schema_status:'ready',connection_status:'unverified',verified_at:null,provider:'qwen_openai_compatible',model:null,help_status:'ready',profiles:[{id:'default',label:'默认',thinking:'unknown',vision:false,web_search:false,function_calling:false}]}
const article: HelpArticle={id:'portal.overview',module_id:'portal',title:'门户说明',summary:'合成说明',content:'没有读取业务数据',anchor_id:'portal.overview',status:'verified',source_label:'测试来源',knowledge_version:'test',route_names:['dashboard'],steps:[],verification:{fingerprint:'a'.repeat(64),verified_commit:'synthetic',sources:[{path:'synthetic.ts',symbol:'field',expected_sha256:'a'.repeat(64),current_sha256:'a'.repeat(64),matches:true}]}}
let wrappers: ReturnType<typeof mount>[]=[]
beforeEach(()=>{
 vi.restoreAllMocks();setActivePinia(createPinia());document.body.innerHTML='<div id="app"></div>'
 Object.defineProperty(window,'innerWidth',{value:1280,writable:true,configurable:true})
 Object.defineProperty(window,'innerHeight',{value:900,writable:true,configurable:true})
 HTMLElement.prototype.setPointerCapture=vi.fn()
 HTMLElement.prototype.hasPointerCapture=vi.fn().mockReturnValue(true)
 HTMLElement.prototype.releasePointerCapture=vi.fn()
 vi.spyOn(assistantApi,'sessions').mockResolvedValue({items:[],next_cursor:null})
 vi.spyOn(assistantApi,'capabilities').mockResolvedValue(caps)
 vi.spyOn(assistantApi,'help').mockResolvedValue({items:[article],status:'ready'})
 vi.spyOn(assistantApi,'article').mockResolvedValue(article)
 useAssistantStore().capabilities=caps
})
afterEach(()=>{wrappers.forEach(w=>w.unmount());wrappers=[];document.body.innerHTML='';vi.unstubAllGlobals()})
function panel(mode:'side'|'focus'='side'){
 const w=mount(AssistantPanel,{attachTo:document.body,props:{mode,side:'right',width:432,page:{module_id:'portal',route_name:'dashboard',factory_id:'group'},pageTitle:'系统门户'}});wrappers.push(w);return w
}
async function pointerEvent(target: { element: Element }, type: string, options: PointerEventInit) {
 target.element.dispatchEvent(new PointerEvent(type, { bubbles: true, ...options })); await nextTick()
}
async function chooseMore(w: ReturnType<typeof mount>, label: string) {
  await w.get('[aria-label="更多操作"]').trigger('keydown',{key:'ArrowDown'}); await flushPromises()
  const item=[...document.querySelectorAll<HTMLElement>('[role="menuitem"]')].find(el=>el.textContent===label)
  expect(item).toBeTruthy(); item!.click(); await flushPromises()
}
describe('assistant panel boundaries',()=>{
 it.each([false,true])('repositions a target after responsive layout, unless the guide was cancelled (%s)',async cancel=>{
  const frames=new Map<number,FrameRequestCallback>();let sequence=0
  vi.stubGlobal('requestAnimationFrame',(callback:FrameRequestCallback)=>{frames.set(++sequence,callback);return sequence})
  vi.stubGlobal('cancelAnimationFrame',(id:number)=>{frames.delete(id)})
  const frame=async()=>{const pending=[...frames.values()];frames.clear();pending.forEach(callback=>callback(0));await nextTick()}
  const walkthrough={...article,steps:[{title:'核对',description:'合成步骤',anchor_id:article.anchor_id,precondition:'可见',completion:'显示'}]}
  vi.mocked(assistantApi.help).mockResolvedValue({items:[walkthrough],status:'ready'});vi.mocked(assistantApi.article).mockResolvedValue(walkthrough)
  const target=document.createElement('div');target.dataset.ylHelp=article.anchor_id;target.getClientRects=()=>({length:1}) as DOMRectList;target.scrollIntoView=vi.fn();document.body.append(target)
  vi.stubGlobal('matchMedia',()=>({matches:true}))
  const w=panel();await flushPromises()
  await w.findAll('button').find(b=>b.text()==='讲解本页')!.trigger('click');await flushPromises()
  await w.findAll('button').find(b=>b.text()==='带我看一遍')!.trigger('click');await flushPromises()
  await w.setProps({mode:'edge'});await flushPromises()
  expect(target.scrollIntoView).toHaveBeenCalledOnce()
  Object.defineProperty(window,'innerWidth',{value:390});window.dispatchEvent(new Event('resize'));await nextTick();await frame()
  expect(target.scrollIntoView).toHaveBeenCalledOnce()
  if(cancel) {window.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}));await flushPromises()}
  await frame()
  expect(target.scrollIntoView).toHaveBeenCalledTimes(cancel ? 1 : 2)
  if(!cancel) expect(target.scrollIntoView).toHaveBeenLastCalledWith({behavior:'instant',block:'center',inline:'nearest'})
 })
 it('returns narrow-screen guide focus after the reopened panel finishes refreshing capabilities',async()=>{
  Object.defineProperty(window,'innerWidth',{value:390})
  const walkthrough={...article,steps:[{title:'核对',description:'合成步骤',anchor_id:article.anchor_id,precondition:'可见',completion:'显示'}]}
  vi.mocked(assistantApi.help).mockResolvedValue({items:[walkthrough],status:'ready'});vi.mocked(assistantApi.article).mockResolvedValue(walkthrough)
  const target=document.createElement('div');target.dataset.ylHelp=article.anchor_id;target.getClientRects=()=>({length:1}) as DOMRectList;target.scrollIntoView=vi.fn();document.getElementById('app')!.append(target)
  vi.stubGlobal('matchMedia',()=>({matches:true}))
  const w=panel();await flushPromises()
  await w.findAll('button').find(b=>b.text()==='讲解本页')!.trigger('click');await flushPromises()
  const start=w.findAll('button').find(b=>b.text()==='带我看一遍')!;(start.element as HTMLElement).focus();await start.trigger('click');await flushPromises()
  // Reflect the parent's mode event, then allow the pending reveal to finish.
  await w.setProps({mode:'edge'});await flushPromises()
  await w.get('.yl-guide').findAll('button').find(b=>b.text()==='退出')!.trigger('click')
  await w.setProps({mode:'side'});await flushPromises()
  expect(document.activeElement).toBe(start.element);expect(w.find('.yl-guide').exists()).toBe(false)
 })
 it('disables stale guidance and exposes the mismatched source fingerprint',async()=>{
  const stale={...article,status:'needs_review',verification:{...article.verification!,sources:[{...article.verification!.sources[0]!,current_sha256:'changed',matches:false}]}}
  vi.mocked(assistantApi.help).mockResolvedValue({items:[stale],status:'partial'})
  const w=panel();await flushPromises();await w.findAll('button').find(b=>b.text()==='讲解本页')!.trigger('click');await flushPromises()
  expect(w.text()).toContain('已停止定位');expect(w.text()).toContain('changed')
  expect(w.findAll('button').find(b=>b.text()==='定位')!.attributes('disabled')).toBeDefined()
  expect(assistantApi.article).not.toHaveBeenCalled()
 })
 it('refreshes changed help but stops the old guide before touching the page',async()=>{
  vi.mocked(assistantApi.article).mockResolvedValue({...article,verification:{...article.verification!,fingerprint:'new-version'}})
  const w=panel();await flushPromises();await w.findAll('button').find(b=>b.text()==='讲解本页')!.trigger('click');await flushPromises()
  await w.findAll('button').find(b=>b.text()==='定位')!.trigger('click');await flushPromises()
  expect(w.text()).toContain('已停止旧引导');expect(w.text()).toContain('new-version');expect(w.find('.yl-target-outline').exists()).toBe(false)
  await w.findAll('button').find(b=>b.text()==='讲解本页')!.trigger('click');await flushPromises()
  expect(w.text()).not.toContain('已停止旧引导')
 })
 it('explains a missing target without submitting another page button',async()=>{
  const button=document.createElement('button'), click=vi.fn();button.textContent='提交';button.onclick=click;document.body.append(button)
  const w=panel();await flushPromises();await w.findAll('button').find(b=>b.text()==='讲解本页')!.trigger('click');await flushPromises()
  const locate=w.findAll('button').find(b=>b.text()==='定位')!;(locate.element as HTMLElement).focus();await locate.trigger('click');await flushPromises()
  expect(w.text()).toContain('没有可见且唯一');expect(w.find('.yl-guide').exists()).toBe(false);expect(click).not.toHaveBeenCalled()
  expect(document.activeElement).toBe(locate.element)
 })
 it.each(['route','identity','escape','unmount'] as const)('discards a pending guide after %s changes',async change=>{
  let resolve!: (value:HelpArticle)=>void
  vi.mocked(assistantApi.article).mockImplementation(()=>new Promise(done=>{resolve=done}))
  const target=document.createElement('div');target.dataset.ylHelp=article.anchor_id;target.getClientRects=()=>({length:1}) as DOMRectList;target.scrollIntoView=vi.fn();document.body.append(target)
  const w=panel();await flushPromises();await w.findAll('button').find(b=>b.text()==='讲解本页')!.trigger('click');await flushPromises()
  await w.findAll('button').find(b=>b.text()==='定位')!.trigger('click');await flushPromises()
  expect(w.text()).toContain('正在核对说明版本')
  if(change==='route') await w.setProps({page:null})
  else if(change==='identity') {useAssistantStore().identityGeneration++;await nextTick()}
  else if(change==='escape') await w.get('.yl-panel').trigger('keydown',{key:'Escape'})
  else {w.unmount();wrappers=wrappers.filter(item=>item!==w)}
  resolve(article);await flushPromises();expect(target.scrollIntoView).not.toHaveBeenCalled()
  if(change!=='unmount') expect(w.find('.yl-target-outline').exists()).toBe(false)
 })
 it('restores focus when source invalidation closes the material drawer',async()=>{
  const store=useAssistantStore();store.selectedId='s';store.draftFor('s').documents=[{id:'f',name:'file.txt',parse_status:'ready'}]
  vi.spyOn(assistantApi,'document').mockResolvedValue({id:'f',name:'file.txt',parse_status:'ready'})
  vi.spyOn(store,'selectSession').mockResolvedValue(undefined)
  const w=panel();await flushPromises();await chooseMore(w,'资料与来源')
  await w.get('.yl-source-layer').findAll('button').find(b=>b.text()==='资料')!.trigger('click');await flushPromises()
  w.findComponent(AssistantDocument).vm.$emit('deleted');await flushPromises()
  expect(w.find('.yl-source-layer').exists()).toBe(false)
  expect(document.activeElement).toBe(w.get('[aria-label="更多操作"]').element)
 })
 it('keeps successful batch uploads after one failure and clears errors on reselection',async()=>{
  const store=useAssistantStore();store.selectedId='synthetic-session'
  const upload=vi.spyOn(assistantApi,'uploadDocument').mockRejectedValueOnce(new Error('文件格式不支持')).mockResolvedValueOnce({id:'good',name:'good.docx',parse_status:'ready'}).mockResolvedValueOnce({id:'retry',name:'bad.docx',parse_status:'ready'})
  vi.spyOn(assistantApi,'document').mockImplementation(async id=>({id,name:id+'.docx',parse_status:'ready'}))
  const w=panel();await flushPromises()
  const input=w.findAll('input[type="file"]')[0]!
  Object.defineProperty(input.element,'files',{configurable:true,value:[new File(['bad'],'bad.docx'),new File(['good'],'good.docx')]})
  await input.trigger('change');await flushPromises()
  expect(upload).toHaveBeenCalledTimes(2)
  expect(store.draftFor().documents.map(d=>d.id)).toEqual(['good'])
  expect(w.text()).toContain('bad.docx：文件格式不支持')
  Object.defineProperty(input.element,'files',{configurable:true,value:[new File(['fixed'],'bad.docx')]})
  await input.trigger('change');await flushPromises()
  expect(upload).toHaveBeenCalledTimes(3)
  expect(store.draftFor().documents.map(d=>d.id)).toEqual(['good','retry'])
  expect(w.text()).not.toContain('文件格式不支持')
  expect((input.element as HTMLInputElement).value).toBe('')
 })
 it('does not create a session or change a draft after cancelling file selection',async()=>{
  const store=useAssistantStore(), create=vi.spyOn(store,'newSession')
  store.draftFor().text='保留草稿'
  const w=panel();await flushPromises()
  const input=w.findAll('input[type="file"]')[0]!
  Object.defineProperty(input.element,'files',{configurable:true,value:[]})
  await input.trigger('change');await flushPromises()
  expect(create).not.toHaveBeenCalled();expect(store.draftFor().text).toBe('保留草稿')
 })
 it('opens real coverage for the current page without changing the frozen draft and restores focus on Escape',async()=>{
  const api=vi.spyOn(assistantApi,'coverage').mockResolvedValue({factory_id:'group',checked_at:'2026-10-25T00:00:00Z',catalog_scope:'registered_modules',items:[]})
  const w=panel();await flushPromises();await w.get('textarea').setValue('保留问题')
  await chooseMore(w,'模块覆盖')
  expect(api).toHaveBeenCalledWith('group','portal',expect.any(AbortSignal))
  expect(w.get('.yl-conversation').attributes('inert')).toBeDefined()
  expect(document.activeElement).toBe(w.get('[aria-label="关闭模块覆盖"]').element)
  await w.get('[aria-label="关闭模块覆盖"]').trigger('keydown',{key:'Escape'});await flushPromises()
  expect(w.find('.yl-inner-layer').exists()).toBe(false)
  expect(document.activeElement).toBe(w.get('[aria-label="更多操作"]').element)
  expect(w.get('textarea').element.value).toBe('保留问题')
 })
 it('offers current work only for callable server connectors and submits the frozen order scope',async()=>{
  const store=useAssistantStore()
  store.capabilities={...caps,configuration_status:'configured',business_modules:[{module_id:'customer-orders',label:'客户订单',coverage_state:'planned',tools:[],read_only:true,reason:null}]}
  const send=vi.spyOn(store,'submit').mockResolvedValue(undefined), w=panel();await flushPromises()
  await w.setProps({page:{module_id:'customer-orders',route_name:'customer-order-center',factory_id:'huakang-a'},pageTitle:'客户订单中心'})
  expect(w.text()).not.toContain('查当前工作')
  store.capabilities={...store.capabilities,business_modules:[{...store.capabilities.business_modules![0]!,coverage_state:'implemented_unverified',tools:['list_customer_orders']}]};await nextTick()
  await w.findAll('button').find(b=>b.text().includes('查当前工作'))!.trigger('click')
  await w.get('textarea').trigger('keydown',{key:'Enter'})
  expect(send).toHaveBeenCalledWith(expect.objectContaining({intent:'my_work',page_context:{module_id:'customer-orders',route_name:'customer-order-center',factory_id:'huakang-a'}}))
 })
 it('reveals an anchor hidden beneath the side panel and offers a return to the explanation',async()=>{
  vi.stubGlobal('matchMedia',()=>({matches:true}))
  vi.spyOn(assistantApi,'help').mockResolvedValue({items:[{...article,anchor_id:'test.occluded'}],status:'ready'})
  vi.mocked(assistantApi.article).mockResolvedValue({...article,anchor_id:'test.occluded'})
  const target=document.createElement('div');target.dataset.ylHelp='test.occluded'
  target.getClientRects=()=>({length:1}) as DOMRectList;target.scrollIntoView=vi.fn()
  target.getBoundingClientRect=()=>({left:950,right:1050,top:150,bottom:190,width:100,height:40}) as DOMRect
  document.body.append(target)
  const w=panel();await flushPromises()
  w.get('.yl-panel').element.getBoundingClientRect=()=>({left:828,right:1260,top:20,bottom:740,width:432,height:720}) as DOMRect
  await w.findAll('button').find(b=>b.text()==='讲解本页')!.trigger('click');await flushPromises()
  await w.findAll('button').find(b=>b.text()==='定位')!.trigger('click');await flushPromises()
  expect(w.emitted('mode')?.at(-1)).toEqual(['edge'])
  await w.setProps({mode:'edge'});await flushPromises()
  expect(w.text()).toContain('返回说明');expect(w.find('.yl-target-outline').exists()).toBe(true)
  await w.setProps({mode:'side'});await flushPromises()
  expect(w.find('.yl-target-outline').exists()).toBe(false);expect(w.text()).toContain('门户说明')
  target.remove()
 })
 it('returns file-picker focus to the editor and retains the current draft',async()=>{
  const store=useAssistantStore();store.capabilities={...caps,materials:{available:true,extensions:['.txt']} as Capabilities['materials']}
  const w=panel();await flushPromises();await w.get('textarea').setValue('保留的草稿')
  await w.get('[aria-label="添加资料与更多选项"]').trigger('keydown',{key:'ArrowDown'});await flushPromises()
  const item=[...document.querySelectorAll<HTMLElement>('[role="menuitem"]')].find(el=>el.textContent==='上传文件')!
  item.click();await flushPromises()
  expect(document.activeElement).toBe(w.get('textarea').element)
  expect(store.draftFor().text).toBe('保留的草稿')
  expect(w.emitted('focus-change')?.at(-1)).toEqual([true])
 })
 it('keeps draft-bound page intent after navigation and supports explicit adoption and free chat',async()=>{
  const store=useAssistantStore();store.capabilities={...caps,configuration_status:'configured'}
  const send=vi.spyOn(store,'submit').mockResolvedValue(undefined), w=panel();await flushPromises()
  await w.get('textarea').setValue('原问题')
  await w.setProps({page:{module_id:'injection-scheduling',route_name:'injection-scheduling',factory_id:'huakang-a'},pageTitle:'注塑排产'})
  expect(w.text()).toContain('仍使用原问题范围')
  await w.get('textarea').trigger('keydown',{key:'Enter'})
  expect(send).toHaveBeenLastCalledWith(expect.objectContaining({page_context:{module_id:'portal',route_name:'dashboard',factory_id:'group'}}))
  await w.get('textarea').setValue('新范围问题')
  await w.findAll('button').find(b=>b.text()==='改用 华康A · 注塑排产')!.trigger('click')
  expect(store.draftFor().scope?.page?.factory_id).toBe('huakang-a')
  await w.get('[aria-label="移除页面上下文"]').trigger('click')
  await w.get('textarea').trigger('keydown',{key:'Enter'})
  expect(send).toHaveBeenLastCalledWith(expect.objectContaining({page_context:null,context_selection:null}))
 })
 it('keeps hidden conversation inert only while the single overlay is open and restores its menu trigger',async()=>{
  const w=panel();await flushPromises()
  expect(w.get('.yl-conversation').attributes('inert')).toBeUndefined()
  await chooseMore(w,'历史会话')
  expect(w.get('.yl-conversation').attributes('inert')).toBeDefined()
  expect(w.findAll('.yl-inner-layer')).toHaveLength(1)
  await w.get('[aria-label="关闭历史"]').trigger('click');await flushPromises()
  expect(w.get('.yl-conversation').attributes('inert')).toBeUndefined()
  expect(document.activeElement).toBe(w.get('[aria-label="更多操作"]').element)
 })
 it('keeps keyboard focus inside the panel while Send is replaced by Stop',async()=>{
  const store=useAssistantStore();store.capabilities={...caps,configuration_status:'configured'}
  const submit=vi.spyOn(store,'submit').mockResolvedValue()
  const w=panel();await flushPromises();await w.get('[aria-label="给曜灵的问题"]').setValue('question')
  ;(w.get('[aria-label="发送问题"]').element as HTMLElement).focus();await w.get('[aria-label="发送问题"]').trigger('click');await flushPromises()
  expect(submit).toHaveBeenCalledOnce();expect(document.activeElement).toBe(w.get('[aria-label="给曜灵的问题"]').element)
 })
 it('polls queued documents to readiness and stops after completion or unmount',async()=>{
  vi.useFakeTimers()
  try {
   const store=useAssistantStore();store.draftFor().documents=[{id:'doc',name:'test.txt',parse_status:'queued'}]
   const api=vi.spyOn(assistantApi,'document').mockResolvedValueOnce({id:'doc',name:'test.txt',parse_status:'parsing'}).mockResolvedValueOnce({id:'doc',name:'test.txt',parse_status:'ready'})
   const w=panel();await flushPromises();await vi.advanceTimersByTimeAsync(1000);await flushPromises()
   expect(w.text()).toContain('解析中');await vi.advanceTimersByTimeAsync(1000);await flushPromises();expect(w.text()).toContain('可分析')
   await vi.advanceTimersByTimeAsync(3000);expect(api).toHaveBeenCalledTimes(2)
   store.draftFor().documents.push({id:'second',name:'second.txt',parse_status:'queued'});await nextTick();w.unmount();wrappers=[]
   await vi.advanceTimersByTimeAsync(2000);expect(api).toHaveBeenCalledTimes(2)
  } finally {vi.useRealTimers()}
 })
 it('ignores a pending document response after the viewer identity changes',async()=>{
  vi.useFakeTimers()
  try {
   const store=useAssistantStore();store.bindIdentity('first');const old=store.draftFor();old.documents=[{id:'doc',name:'private.txt',parse_status:'queued'}]
   let resolve!: (v: Awaited<ReturnType<typeof assistantApi.document>>) => void
   vi.spyOn(assistantApi,'document').mockReturnValue(new Promise(r=>{resolve=r}))
   const w=panel();await flushPromises();await vi.advanceTimersByTimeAsync(1000)
   store.bindIdentity('second');await nextTick();resolve({id:'doc',name:'private.txt',parse_status:'ready'});await flushPromises()
   expect(store.draftFor().documents).toEqual([]);expect(old.documents[0].parse_status).toBe('queued');expect(w.text()).not.toContain('private.txt')
  } finally {vi.useRealTimers()}
 })
 it('follows a background answer after reveal but preserves an older reading position',async()=>{
  const w=panel();await flushPromises()
  const scroller=w.get('.yl-scroll').element as HTMLElement
  Object.defineProperty(scroller,'scrollHeight',{configurable:true,value:900})
  Object.defineProperty(scroller,'clientHeight',{configurable:true,value:200})
  await w.setProps({mode:'edge'});scroller.scrollTop=0
  await w.setProps({mode:'side'});await flushPromises()
  expect(scroller.scrollTop).toBe(900)
  scroller.scrollTop=100;await w.get('.yl-scroll').trigger('scroll')
  await w.setProps({mode:'edge'});await w.setProps({mode:'side'});await flushPromises()
  expect(scroller.scrollTop).toBe(100)
 })
 it('moves the existing about-panel dock action and saves the chosen side',async()=>{
  const w=panel();await flushPromises();await w.setProps({position:{x:500,y:80}})
  await chooseMore(w, '关于与连接状态')
  await w.findAll('button').find(b=>b.text()==='移到左侧')!.trigger('click')
  expect(w.emitted('side')?.at(-1)).toEqual(['left'])
  expect(w.emitted('position')?.at(-1)).toEqual([{x:20,y:80}])
  expect(w.emitted('layout-end')).toHaveLength(1)
 })
 it('holds edge reveal for editing or keyboard focus, but not an ordinary mouse button click',async()=>{
  const w=panel();await flushPromises();const button=w.get('[aria-label="更多操作"]')
  await pointerEvent(button,'pointerdown',{button:0,pointerId:1})
  ;(button.element as HTMLElement).focus();await nextTick()
  expect(w.emitted('focus-change')?.at(-1)).toEqual([false])
  ;(w.get('textarea').element as HTMLElement).focus();await nextTick()
  expect(w.emitted('focus-change')?.at(-1)).toEqual([true])
  window.dispatchEvent(new KeyboardEvent('keydown',{key:'Tab'}))
  ;(button.element as HTMLElement).focus();await nextTick()
  expect(w.emitted('focus-change')?.at(-1)).toEqual([true])
 })
 it('moves from the whole title bar in both axes without requiring a dock-side change',async()=>{
  const w=panel();await flushPromises()
  const header=w.get('.yl-header')
  await pointerEvent(header,'pointerdown',{button:0,pointerId:1,clientX:1000,clientY:60})
  await pointerEvent(header,'pointermove',{pointerId:1,clientX:800,clientY:170})
  expect(w.emitted('position')?.at(-1)).toEqual([{x:628,y:130}])
  await w.setProps({position:{x:628,y:130}})
  await pointerEvent(header,'pointerup',{pointerId:1})
  expect(w.get('.yl-panel').attributes('style')).toContain('left: 628px')
  expect(w.get('.yl-panel').attributes('style')).toContain('top: 130px')
  expect(w.emitted('layout-end')).toHaveLength(1)
  expect(document.getElementById('app')!.inert).not.toBe(true)
 })
 it('ignores other pointers and releases a cancelled gesture without continued movement',async()=>{
  const w=panel();await flushPromises();const header=w.get('.yl-header')
  await pointerEvent(header,'pointerdown',{button:0,pointerId:1,clientX:900,clientY:60})
  await pointerEvent(header,'pointermove',{pointerId:2,clientX:100,clientY:100})
  expect(w.emitted('position')).toBeUndefined()
  await pointerEvent(header,'pointercancel',{pointerId:1})
  await pointerEvent(header,'pointermove',{pointerId:1,clientX:100,clientY:100})
  expect(w.emitted('position')).toBeUndefined()
  expect(HTMLElement.prototype.releasePointerCapture).toHaveBeenCalledWith(1)
 })
 it('keeps header actions, body selection and the composer out of the drag gesture',async()=>{
  const w=panel();await flushPromises()
  for(const target of [w.get('[aria-label="更多操作"]'),w.get('.yl-scroll'),w.get('textarea')]){
   await pointerEvent(target,'pointerdown',{button:0,pointerId:1,clientX:900,clientY:100})
   await pointerEvent(w.get('.yl-header'),'pointermove',{pointerId:1,clientX:500,clientY:200})
  }
  expect(w.emitted('position')).toBeUndefined()
  await chooseMore(w, '历史会话')
  expect(w.get('.yl-inner-layer h2').text()).toBe('你的对话')
 })
 it('resizes both dimensions from the corner and preserves the top-left anchor',async()=>{
  const w=panel();await flushPromises();const corner=w.get('[aria-label="调整曜灵大小"]')
  await pointerEvent(corner,'pointerdown',{button:0,pointerId:1,clientX:1250,clientY:650})
  await pointerEvent(corner,'pointermove',{pointerId:1,clientX:1190,clientY:480})
  expect(w.emitted('width')?.at(-1)).toEqual([372])
  expect(w.emitted('height')?.at(-1)).toEqual([550])
  expect(w.emitted('position')?.at(-1)).toEqual([{x:828,y:20}])
 })
 it('keeps an edge resize anchored and clamps a drag within the visible viewport',async()=>{
  const w=panel();await flushPromises();const edge=w.get('[aria-label="调整曜灵宽度"]')
  await pointerEvent(edge,'pointerdown',{button:0,pointerId:1,clientX:828,clientY:200})
  await pointerEvent(edge,'pointermove',{pointerId:1,clientX:700,clientY:200})
  expect(w.emitted('width')?.at(-1)).toEqual([560])
  expect(w.emitted('position')?.at(-1)).toEqual([{x:700,y:20}])
  await w.setProps({width:560,position:{x:700,y:20}})
  await pointerEvent(edge,'pointerup',{pointerId:1})
  const header=w.get('.yl-header')
  await pointerEvent(header,'pointerdown',{button:0,pointerId:2,clientX:850,clientY:60})
  await pointerEvent(header,'pointermove',{pointerId:2,clientX:-2000,clientY:3000})
  expect(w.emitted('position')?.at(-1)).toEqual([{x:20,y:160}])
 })
 it('clamps stored geometry after viewport shrink and restores it when space returns',async()=>{
  const w=panel();await flushPromises();await w.setProps({position:{x:1000,y:700},width:600,height:820})
  Object.defineProperty(window,'innerWidth',{value:800});Object.defineProperty(window,'innerHeight',{value:500})
  window.dispatchEvent(new Event('resize'));await flushPromises()
  const style=w.get('.yl-panel').attributes('style')
  expect(style).toContain('left: 180px');expect(style).toContain('top: 20px');expect(style).toContain('--yl-height: 460px')
  Object.defineProperty(window,'innerWidth',{value:1920});Object.defineProperty(window,'innerHeight',{value:1600})
  window.dispatchEvent(new Event('resize'));await flushPromises()
  expect(w.get('.yl-panel').attributes('style')).toContain('left: 1000px')
  expect(w.get('.yl-panel').attributes('style')).toContain('top: 700px')
 })
 it('supports keyboard movement, resizing and resetting the layout',async()=>{
  const w=panel();await flushPromises();await w.setProps({position:{x:300,y:80},height:480})
  await chooseMore(w, '关于与连接状态')
  await w.get('[aria-label="移动曜灵浮窗"]').trigger('keydown',{key:'ArrowDown'})
  expect(w.emitted('position')?.at(-1)).toEqual([{x:300,y:100}])
  await w.get('[aria-label="关闭关于"]').trigger('click'); await flushPromises()
  await w.get('[aria-label="调整曜灵大小"]').trigger('keydown',{key:'ArrowDown',shiftKey:true})
  expect(w.emitted('height')?.at(-1)).toEqual([530])
  await chooseMore(w, '关于与连接状态')
  await w.get('[aria-label="恢复浮窗位置和大小"]').trigger('click')
  expect(w.emitted('position')?.at(-1)).toEqual([null]);expect(w.emitted('width')?.at(-1)).toEqual([460]);expect(w.emitted('height')?.at(-1)).toEqual([720])
 })
 it('preserves floating geometry through focus mode and hides drag controls on small screens',async()=>{
  const w=panel();await flushPromises();await w.setProps({position:{x:300,y:80},height:480,mode:'focus'})
  expect(w.find('[aria-label="移动曜灵浮窗"]').exists()).toBe(false)
  expect(w.get('.yl-panel').attributes('style')).not.toContain('left:')
  await w.setProps({mode:'side'})
  expect(w.get('.yl-panel').attributes('style')).toContain('left: 300px')
  Object.defineProperty(window,'innerWidth',{value:390});window.dispatchEvent(new Event('resize'));await flushPromises()
  expect(w.find('[aria-label="调整曜灵大小"]').exists()).toBe(false)
  expect(w.get('.yl-panel').attributes('aria-modal')).toBe('true')
 })
 it('keeps verified page help available with no model and hides unsupported controls',async()=>{
  const w=panel();await flushPromises();await w.get('textarea').setValue('自由问题')
  expect(w.get('[aria-label="发送问题"]').attributes('disabled')).toBeDefined()
  expect(w.find('[aria-label="上传图片"]').exists()).toBe(false)
  expect(w.find('[aria-label="思考模式"]').exists()).toBe(false)
  await w.findAll('button').find(b=>b.text()==='讲解本页')!.trigger('click');await flushPromises()
  expect(w.text()).toContain('门户说明');expect(w.text()).toContain('没有读取业务数据')
 })
 it('keeps a walkthrough alive while its source check waits after the hover surface closes',async()=>{
  const walkthrough={...article,steps:[{title:'读取同步状态',anchor_id:article.anchor_id,description:'只读',precondition:'可见',completion:'已核对'}]}
  vi.mocked(assistantApi.help).mockResolvedValue({items:[walkthrough],status:'ready'})
  let resolve!:(value:HelpArticle)=>void
  vi.mocked(assistantApi.article).mockImplementation(()=>new Promise(r=>{resolve=r}))
  const target=document.createElement('div');target.dataset.ylHelp=article.anchor_id
  target.getClientRects=()=>({length:1}) as DOMRectList;target.scrollIntoView=vi.fn();document.body.append(target)
  vi.stubGlobal('matchMedia',()=>({matches:true}))
  try {
   const w=panel();await flushPromises();await w.findAll('button').find(b=>b.text()==='讲解本页')!.trigger('click');await flushPromises()
   await w.findAll('button').find(b=>b.text()==='带我看一遍')!.trigger('click');await flushPromises()
   expect(w.emitted('mode')?.at(-1)).toEqual(['edge'])
   await w.setProps({mode:'edge'});await flushPromises()
   resolve(walkthrough);await flushPromises()
   expect(w.get('.yl-guide strong').text()).toBe('1 · 读取同步状态')
   expect(target.scrollIntoView).toHaveBeenCalledOnce()
  } finally {target.remove()}
 })
 it('keeps an overview walkthrough when its next anchor is also a standalone field article',async()=>{
  const step=(title:string,anchor_id:string)=>({title,anchor_id,description:'合成步骤',precondition:'可见',completion:'已核对'})
  const field={...article,id:'field',title:'字段说明',anchor_id:'test.field',steps:[step('字段独立引导','test.field')]}
  const overview={...article,steps:[step('第一步','test.first'),step('第二步','test.field')]}
  vi.spyOn(assistantApi,'help').mockResolvedValue({items:[field,overview],status:'ready'})
  vi.mocked(assistantApi.article).mockImplementation(async id => id === field.id ? field : overview)
  const targets=['test.first','test.field'].map(id=>{
   const el=document.createElement('div');el.dataset.ylHelp=id;el.getClientRects=()=>({length:1}) as DOMRectList;el.scrollIntoView=vi.fn();document.body.append(el);return el
  })
  vi.stubGlobal('matchMedia',()=>({matches:true}))
  try {
   const w=panel();await flushPromises();await w.findAll('button').find(b=>b.text()==='讲解本页')!.trigger('click');await flushPromises()
   const start=w.findAll('.yl-help-card').find(c=>c.text().includes('门户说明'))!.findAll('button').find(b=>b.text()==='带我看一遍')!;(start.element as HTMLElement).focus();await start.trigger('click');await flushPromises()
   expect(w.emitted('mode')?.at(-1)).toEqual(['edge'])
   await w.setProps({mode:'edge'});await flushPromises()
   expect(w.get('.yl-guide strong').text()).toBe('1 · 第一步')
   await w.get('.yl-guide').findAll('button').find(b=>b.text()==='下一步 / 跳过')!.trigger('click');await flushPromises()
   expect(w.get('.yl-guide strong').text()).toBe('2 · 第二步')
   expect(w.get('.yl-guide').text()).toContain('完成引导')
   await w.get('.yl-guide').findAll('button').find(b=>b.text()==='完成引导')!.trigger('click');await flushPromises()
   expect(w.emitted('mode')?.at(-1)).toEqual(['side'])
   await w.setProps({mode:'side'});await flushPromises()
   expect(w.find('.yl-guide').exists()).toBe(false);expect(document.activeElement).toBe(start.element)
  } finally {targets.forEach(el=>el.remove());vi.unstubAllGlobals()}
 })
 it('uses the shared scroll lock and restores the prior inert state on focus exit',async()=>{
  const release=acquireBodyScrollLock();const root=document.getElementById('app')!;root.inert=false
  const w=panel('focus');await flushPromises();expect(root.inert).toBe(true)
  await w.setProps({mode:'side'});expect(root.inert).toBe(false);expect(document.body.style.overflow).toBe('hidden')
  release();expect(document.body.style.overflow).not.toBe('hidden')
 })
 it('does not send IME confirmation or Shift+Enter, and Enter sends original text',async()=>{
  const store=useAssistantStore();store.capabilities={...caps,configuration_status:'configured'}
  const send=vi.spyOn(store,'submit').mockResolvedValue(undefined);const w=panel();await flushPromises();const input=w.get('textarea')
  await input.setValue('原始问题');await input.trigger('keydown',{key:'Enter',isComposing:true});await input.trigger('keydown',{key:'Enter',shiftKey:true});expect(send).not.toHaveBeenCalled()
  await input.trigger('keydown',{key:'Enter'});expect(send).toHaveBeenCalledWith(expect.objectContaining({text:'原始问题'}))
 })
})
