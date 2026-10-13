import { expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import AssistantMessage from '../AssistantMessage.vue'
import { assistantApi } from '../api'
import type { Message } from '../types'

it('authorized assistant navigation still respects the original router leave guard',async()=>{
 const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',name:'source',component:{}},{path:'/work',name:'work',component:{}}]})
 await router.push('/');await router.isReady()
 const guard=vi.fn(()=>false);router.beforeEach(guard)
 const action=vi.spyOn(assistantApi,'action').mockResolvedValue({type:'open_record',label:'打开事项',route_name:'work',params:{},query:{},resource:{module_id:'work-center',resource_type:'entry',resource_id:'synthetic'}})
 const message={id:'m',run_id:'r',role:'assistant',status:'completed',content_parts:[{type:'actions',items:[{type:'open_record',label:'打开事项'}]}],help_citations:[],context_descriptor:null} as unknown as Message
 const wrapper=mount(AssistantMessage,{props:{message},global:{plugins:[router]}})
 await wrapper.findAll('button').find(b=>b.text()==='打开事项')!.trigger('click');await flushPromises()
 expect(action).toHaveBeenCalledWith('r',0);expect(guard).toHaveBeenCalledOnce();expect(router.currentRoute.value.name).toBe('source')
 wrapper.unmount();vi.restoreAllMocks()
})
