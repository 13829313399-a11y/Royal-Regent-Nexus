import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { useAssistantStore } from '@/stores/assistant'
import { acquireBodyScrollLock } from '@/lib/bodyScrollLock'
import AssistantPanel from '../AssistantPanel.vue'
import { assistantApi } from '../api'
import type { Capabilities, HelpArticle } from '../types'

const caps: Capabilities={enabled:true,configuration_status:'unconfigured',schema_status:'ready',connection_status:'unverified',verified_at:null,provider:'qwen_openai_compatible',model:null,help_status:'ready',profiles:[{id:'default',label:'默认',thinking:'unknown',vision:false,web_search:false,function_calling:false}]}
const article: HelpArticle={id:'portal.overview',module_id:'portal',title:'门户说明',summary:'合成说明',content:'没有读取业务数据',anchor_id:'portal.overview',status:'verified',source_label:'测试来源',knowledge_version:'test',route_names:['dashboard'],steps:[]}
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
 useAssistantStore().capabilities=caps
})
afterEach(()=>{wrappers.forEach(w=>w.unmount());wrappers=[];document.body.innerHTML=''})
function panel(mode:'side'|'focus'='side'){
 const w=mount(AssistantPanel,{attachTo:document.body,props:{mode,side:'right',width:432,page:{module_id:'portal',route_name:'dashboard',factory_id:'group'},pageTitle:'系统门户'}});wrappers.push(w);return w
}
async function pointerEvent(target: { element: Element }, type: string, options: PointerEventInit) {
 target.element.dispatchEvent(new PointerEvent(type, { bubbles: true, ...options })); await nextTick()
}
describe('assistant panel boundaries',()=>{
 it('moves the existing about-panel dock action and saves the chosen side',async()=>{
  const w=panel();await flushPromises();await w.setProps({position:{x:500,y:80}})
  await w.get('[aria-label="关于与连接状态"]').trigger('click')
  await w.findAll('button').find(b=>b.text()==='移到左侧')!.trigger('click')
  expect(w.emitted('side')?.at(-1)).toEqual(['left'])
  expect(w.emitted('position')?.at(-1)).toEqual([{x:20,y:80}])
  expect(w.emitted('layout-end')).toHaveLength(1)
 })
 it('holds edge reveal for editing or keyboard focus, but not an ordinary mouse button click',async()=>{
  const w=panel();await flushPromises();const button=w.get('[aria-label="历史会话"]')
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
  for(const target of [w.get('[aria-label="历史会话"]'),w.get('.yl-scroll'),w.get('textarea')]){
   await pointerEvent(target,'pointerdown',{button:0,pointerId:1,clientX:900,clientY:100})
   await pointerEvent(w.get('.yl-header'),'pointermove',{pointerId:1,clientX:500,clientY:200})
  }
  expect(w.emitted('position')).toBeUndefined()
  await w.get('[aria-label="历史会话"]').trigger('click')
  expect(w.get('.yl-inner-layer h2').text()).toBe('你的对话')
 })
 it('resizes both dimensions from the corner and preserves the top-left anchor',async()=>{
  const w=panel();await flushPromises();const corner=w.get('[aria-label="调整曜灵大小"]')
  await pointerEvent(corner,'pointerdown',{button:0,pointerId:1,clientX:1250,clientY:650})
  await pointerEvent(corner,'pointermove',{pointerId:1,clientX:1190,clientY:480})
  expect(w.emitted('width')?.at(-1)).toEqual([372])
  expect(w.emitted('height')?.at(-1)).toEqual([470])
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
  expect(w.emitted('position')?.at(-1)).toEqual([{x:20,y:240}])
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
  await w.get('[aria-label="移动曜灵浮窗"]').trigger('keydown',{key:'ArrowDown'})
  expect(w.emitted('position')?.at(-1)).toEqual([{x:300,y:100}])
  await w.get('[aria-label="调整曜灵大小"]').trigger('keydown',{key:'ArrowDown',shiftKey:true})
  expect(w.emitted('height')?.at(-1)).toEqual([530])
  await w.get('[aria-label="恢复浮窗位置和大小"]').trigger('click')
  expect(w.emitted('position')?.at(-1)).toEqual([null]);expect(w.emitted('width')?.at(-1)).toEqual([432]);expect(w.emitted('height')?.at(-1)).toEqual([640])
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
