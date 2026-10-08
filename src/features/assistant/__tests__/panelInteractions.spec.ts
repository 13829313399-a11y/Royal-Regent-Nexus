import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
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
 vi.spyOn(assistantApi,'sessions').mockResolvedValue({items:[],next_cursor:null})
 vi.spyOn(assistantApi,'capabilities').mockResolvedValue(caps)
 vi.spyOn(assistantApi,'help').mockResolvedValue({items:[article],status:'ready'})
 useAssistantStore().capabilities=caps
})
afterEach(()=>{wrappers.forEach(w=>w.unmount());wrappers=[];document.body.innerHTML=''})
function panel(mode:'side'|'focus'='side'){
 const w=mount(AssistantPanel,{attachTo:document.body,props:{mode,side:'right',width:432,page:{module_id:'portal',route_name:'dashboard',factory_id:'group'},pageTitle:'系统门户'}});wrappers.push(w);return w
}
describe('assistant panel boundaries',()=>{
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
