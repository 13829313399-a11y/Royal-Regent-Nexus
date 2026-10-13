import { beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { useAssistantStore } from '@/stores/assistant'
import { assistantApi } from '../api'
import AssistantArtifacts from '../AssistantArtifacts.vue'
import type { Artifact, Conversation } from '../types'

function deferred<T>() { let resolve!: (value:T)=>void; const promise = new Promise<T>(r=>resolve=r); return {promise,resolve} }
const conversation=(id:string):Conversation=>({id,title:id,revision:1,deletion_state:'active',created_at:1,updated_at:1})
const artifact=(id:string):Artifact=>({id,title:id,kind:'note',current_revision:1,revision:1,content:id,source_refs:[],export_formats:['md']})
beforeEach(()=>{vi.restoreAllMocks();setActivePinia(createPinia())})

it('a failed replacement search cannot reuse the previous history or artifact cursor',async()=>{
 const store=useAssistantStore();store.bindIdentity('viewer')
 const sessions=vi.spyOn(assistantApi,'sessions').mockResolvedValueOnce({items:[conversation('old')],next_cursor:'1:old'}).mockRejectedValueOnce(new Error('offline'))
 await store.history();store.historyQuery='replacement';await store.history();await store.history(true)
 expect(sessions).toHaveBeenCalledTimes(2);expect(store.historyCursor).toBeNull();expect(store.sessions).toEqual([])
 const artifacts=vi.spyOn(assistantApi,'artifacts').mockResolvedValueOnce({items:[artifact('old')],next_cursor:'1:old'}).mockRejectedValueOnce(new Error('offline'))
 const wrapper=mount(AssistantArtifacts);await flushPromises()
 await wrapper.get('[aria-label="搜索私有成果"]').setValue('replacement');await wrapper.get('form').trigger('submit');await flushPromises()
 expect(artifacts).toHaveBeenCalledTimes(2);expect(wrapper.text()).not.toContain('更多成果');expect(wrapper.text()).toContain('offline');wrapper.unmount()
})

it('older history searches cannot replace newer results or mix late pages',async()=>{
 const store=useAssistantStore();store.bindIdentity('viewer')
 const old=deferred<Awaited<ReturnType<typeof assistantApi.sessions>>>(), page=deferred<Awaited<ReturnType<typeof assistantApi.sessions>>>()
 const api=vi.spyOn(assistantApi,'sessions').mockReturnValueOnce(old.promise).mockResolvedValueOnce({items:[conversation('new')],next_cursor:'1:new'}).mockReturnValueOnce(page.promise).mockResolvedValueOnce({items:[conversation('final')],next_cursor:null})
 store.historyQuery='old';const pending=store.history();store.historyQuery='new';await store.history()
 old.resolve({items:[conversation('old')],next_cursor:null});await pending;expect(store.sessions.map(s=>s.id)).toEqual(['new'])
 store.historyQuery='not submitted';const more=store.history(true);await store.history(true)
 expect(api).toHaveBeenCalledTimes(3);expect(api).toHaveBeenLastCalledWith('1:new','new',false)
 store.historyQuery='final';await store.history();page.resolve({items:[conversation('late')],next_cursor:'1:late'});await more
 expect(store.sessions.map(s=>s.id)).toEqual(['final']);expect(store.historyCursor).toBeNull();expect(store.historyBusy).toBe(false)
})

it('artifact searches bind pages to the submitted query and ignore late responses',async()=>{
 const late=deferred<Awaited<ReturnType<typeof assistantApi.artifacts>>>()
 const api=vi.spyOn(assistantApi,'artifacts').mockResolvedValueOnce({items:[artifact('initial')],next_cursor:'1:initial'}).mockReturnValueOnce(late.promise).mockResolvedValueOnce({items:[artifact('wanted')],next_cursor:null})
 const wrapper=mount(AssistantArtifacts);await flushPromises()
 await wrapper.get('[aria-label="搜索私有成果"]').setValue('wanted')
 await wrapper.findAll('button').find(b=>b.text()==='更多成果')!.trigger('click')
 expect(api).toHaveBeenLastCalledWith('1:initial','')
 expect(wrapper.findAll('button').find(b=>b.text()==='更多成果')!.attributes('disabled')).toBeDefined()
 await wrapper.get('form').trigger('submit');await flushPromises()
 late.resolve({items:[artifact('late')],next_cursor:'1:late'});await flushPromises()
 expect(wrapper.text()).toContain('wanted');expect(wrapper.text()).not.toContain('late');expect(wrapper.text()).not.toContain('更多成果')
 wrapper.unmount()
})

it('late artifact opens cannot replace a newer selection or reopen after returning',async()=>{
 vi.spyOn(assistantApi,'artifacts').mockResolvedValue({items:[],next_cursor:null})
 const first=deferred<Artifact>(),second=deferred<Artifact>()
 vi.spyOn(assistantApi,'artifact').mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
 const wrapper=mount(AssistantArtifacts,{props:{selected:'first'}});await wrapper.setProps({selected:'second'})
 second.resolve(artifact('second'));await flushPromises();first.resolve(artifact('first'));await flushPromises()
 expect(wrapper.get('h3').text()).toBe('second')
 const third=deferred<Artifact>();vi.mocked(assistantApi.artifact).mockReturnValueOnce(third.promise)
 await wrapper.setProps({selected:'third'});await wrapper.findAll('button').find(b=>b.text()==='返回成果列表')!.trigger('click')
 third.resolve(artifact('third'));await flushPromises();expect(wrapper.find('h3').exists()).toBe(false)
 wrapper.unmount()
})
