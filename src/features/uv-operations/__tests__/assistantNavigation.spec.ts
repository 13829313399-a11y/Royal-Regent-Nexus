import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { assistantSelection } from '@/features/assistant/selection'
import { useUvAssistantContext, uvSelection } from '../assistantContext'
import { guardUvNavigation, sameUvPageScope, useUvNavigationGuard } from '../navigationGuard'
import { provideUvMotionPreference } from '../composables/useUvMotionPreference'
import TaskPassport from '../components/TaskPassport.vue'
import type { UvWorkspace } from '../workspace'

const request = vi.fn()
const w = { ready: ref(true), selectedTaskId: ref<string|null>(null), verifiedTaskId: ref<string|null>(null),
  assistantListReady: ref(false), contextVersion: ref(1), can: () => false, request, explain: (e: unknown) => (e as Error).message }
vi.mock('../workspace', () => ({ useUvWorkspace: () => w }))
const wrappers: VueWrapper[] = []
beforeEach(() => {
  w.ready.value=true; w.selectedTaskId.value=null; w.verifiedTaskId.value=null; w.assistantListReady.value=false
  request.mockReset(); request.mockImplementation(async (path: string) => ({ data: { id: decodeURIComponent(path.slice(6)), version: 1, code: '原任务', product_snapshot: '合成长产品', batches: [] } }))
  vi.stubGlobal('matchMedia', vi.fn(() => Object.assign(new EventTarget(), { matches: false })))
  vi.stubGlobal('ResizeObserver', class { observe(){} disconnect(){} })
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false)
  vi.spyOn(HTMLElement.prototype, 'getClientRects').mockReturnValue([{width:10,height:10}] as unknown as DOMRectList)
})
afterEach(() => { wrappers.splice(0).forEach(v => v.unmount()); vi.restoreAllMocks(); vi.unstubAllGlobals(); document.body.innerHTML=''; localStorage.clear() })

async function open(url='/uv?factory=huakang-a&uv_task=SYN-T1') {
  const source = defineComponent({ setup() {
    provideUvMotionPreference(() => 'synthetic').setPreference('off')
    const context = useUvAssistantContext(w as unknown as UvWorkspace)
    return () => h('main', { tabindex: -1, 'data-uv-focus-fallback': '' }, [h('p', context.sourceError.value), h(TaskPassport)])
  } })
  const router = createRouter({ history: createMemoryHistory(), routes: [
    {path:'/uv',name:'uv-planning',component:source}, {path:'/other',component:{template:'<p>其他页面</p>'}},
  ] })
  router.beforeEach(guardUvNavigation)
  await router.push(url)
  const view=mount(defineComponent({setup:()=>()=>h(RouterView)}), { attachTo:document.body, global:{plugins:[router]} })
  wrappers.push(view); await flushPromises()
  return {view,router}
}

it('opens a typed original task URL, binds only the verified selection, and closes without drafting a shift',async()=>{
  const {view,router}=await open()
  expect(request).toHaveBeenCalledWith('tasks/SYN-T1')
  expect(view.get('[aria-label="任务档案"]').text()).toContain('原任务')
  expect(w.verifiedTaskId.value).toBe('SYN-T1')
  const frozen=structuredClone(assistantSelection('uv-operations'))
  expect(frozen?.resources).toEqual([{module_id:'uv-operations',resource_type:'task',resource_id:'SYN-T1'}])
  expect(router.currentRoute.value.query.task).toBeUndefined()
  await view.get('[aria-label="关闭任务档案"]').trigger('click'); await flushPromises()
  expect(router.currentRoute.value.query.uv_task).toBeUndefined()
  expect(w.verifiedTaskId.value).toBeNull()
  expect(frozen?.resources[0]?.resource_id).toBe('SYN-T1')
  expect(assistantSelection('uv-operations')?.filters.scope_error).toBeTruthy()
})

it('does not admit a missing/mismatched task and retries the actual original request',async()=>{
  request.mockRejectedValueOnce(new Error('原任务不可用'))
  const {view}=await open()
  expect(view.text()).toContain('原任务不可用')
  expect(assistantSelection('uv-operations')?.resources).toEqual([])
  expect(assistantSelection('uv-operations')?.filters.scope_error).toBeTruthy()
  await view.get('.uv-state-actions button').trigger('click'); await flushPromises()
  expect(request).toHaveBeenCalledTimes(2)
  expect(w.verifiedTaskId.value).toBe('SYN-T1')
  expect(document.activeElement).toBe(view.get('[aria-label="任务档案"]').element)
  request.mockResolvedValueOnce({data:{id:'WRONG',version:1,code:'不可显示'}})
  w.selectedTaskId.value='SYN-T2';await flushPromises()
  expect(view.text()).toContain('返回的任务与所选来源不一致')
  expect(view.text()).not.toContain('不可显示')
  expect(w.verifiedTaskId.value).toBeNull()
})

it('rejects ambiguous URL identifiers without fetching and clears stale verified facts synchronously on context loss',async()=>{
  const {router}=await open('/uv?factory=huakang-a&uv_task=A&uv_task=B')
  expect(request).not.toHaveBeenCalled()
  expect(assistantSelection('uv-operations')?.filters.scope_error).toContain('编号无效')
  await router.replace('/uv?factory=huakang-a&uv_task=SYN-T1');await flushPromises()
  expect(w.verifiedTaskId.value).toBe('SYN-T1')
  w.ready.value=false;w.contextVersion.value++;await nextTick()
  expect(w.verifiedTaskId.value).toBeNull()
  expect(assistantSelection('uv-operations')?.resources).toEqual([])
})

it('requires a verified task or a native task-list scope and never defaults a different factory',()=>{
  expect(uvSelection('huakang-b',true,null,null,true).filters.scope_error).toBeTruthy()
  expect(uvSelection('huakang-a',true,'A',null,true).resources).toEqual([])
  expect(uvSelection('huakang-a',true,null,null,false).filters.scope_error).toBeTruthy()
  expect(uvSelection('huakang-a',true,null,null,true).filters).toMatchObject({factory_id:'huakang-a',view:'tasks'})
})

it('runs draft guards before factory mutation and preserves same-page source queries',async()=>{
  const dirty=ref(true), saving=ref(false), factory=ref('huakang-a')
  const confirm=vi.spyOn(window,'confirm').mockReturnValue(false)
  const page=defineComponent({setup(){useUvNavigationGuard((to,from)=>sameUvPageScope(to,from)||!saving.value&&(!dirty.value||confirm()));return()=>h('p','draft')}})
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/uv',component:page},{path:'/login',name:'login',component:{template:'login'}}]})
  router.beforeEach((to,from)=>{if(!guardUvNavigation(to,from))return false;factory.value=String(to.query.factory??'');return true})
  await router.push('/uv?factory=huakang-a')
  wrappers.push(mount(defineComponent({setup:()=>()=>h(RouterView)}),{global:{plugins:[router]}}));await flushPromises()
  await router.push('/uv?factory=huakang-b')
  expect(factory.value).toBe('huakang-a');expect(dirty.value).toBe(true)
  await router.push('/uv?factory=huakang-a&uv_task=A')
  expect(router.currentRoute.value.query.uv_task).toBe('A')
  saving.value=true;confirm.mockReturnValue(true);await router.push('/uv?factory=huakang-b')
  expect(factory.value).toBe('huakang-a')
  saving.value=false;await router.push('/uv?factory=huakang-b');expect(factory.value).toBe('huakang-b')
  saving.value=true;await router.push('/login');expect(router.currentRoute.value.name).toBe('login')
})
