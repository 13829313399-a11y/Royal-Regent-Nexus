import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { useAssistantStore } from '@/stores/assistant'
import AssistantDataset from '../AssistantDataset.vue'
import AssistantArtifacts from '../AssistantArtifacts.vue'
import { assistantApi, AssistantApiError } from '../api'
import type { Artifact, ArtifactDataset } from '../types'

const dataset: ArtifactDataset = {
  dataset_id:'same-canonical-snapshot',title:'合成订单',scope:{label:'华康A / 当前筛选',filters:{view:'open'}},
  as_of:'2026-10-23T01:00:00Z',observed_at:null,retrieved_at:'2026-10-23T01:00:01Z',timezone:'Asia/Shanghai',status:'partial',historical:true,
  total_count:50,returned_count:41,truncated:true,columns:[{key:'reference_no',label:'订单编号'},{key:'quantity',label:'数量'}],
  rows:Array.from({length:41},(_,i)=>({reference_no:`合成订单${i}`,quantity:i === 0 ? '<script>secret()</script>' : i})),
  metrics:[{key:'remaining',label:'未走货数量',value:'900',unit:'件',status:'known',definition_id:'quantity'},
    {key:'orders',label:'订单数',value:2,unit:'订单行',status:'known',definition_id:'count'},
    {key:'unknown',label:'库存可用量',value:null,unit:'件',status:'unknown',definition_id:'unknown'}],
  definitions:{quantity:'同一筛选下的未走货数量',count:'订单行数',unknown:'原系统缺失'},unknown_fields:[{field:'stock',reason:'没有可用量来源'}],source_ids:['registered-source'],
  charts:[{type:'bar',dataset_id:'same-canonical-snapshot',unit:'件',metric_keys:['remaining']},
    {type:'bar',dataset_id:'same-canonical-snapshot',unit:'订单行',metric_keys:['orders']}],
}
const artifact = (revision=1, content='已保存说明'): Artifact => ({id:'a',title:'订单成果',kind:'chart',current_revision:revision,revision,content,source_refs:[],export_formats:['md','pdf','xlsx'],datasets:[dataset],edit_origin:revision > 1 ? 'manual_edit' : 'initial_save'})
const wrappers: Array<ReturnType<typeof mount>> = []
beforeEach(()=>{
  vi.restoreAllMocks()
  setActivePinia(createPinia())
  vi.spyOn(assistantApi,'artifacts').mockResolvedValue({items:[],next_cursor:null})
  vi.spyOn(assistantApi,'artifact').mockResolvedValue(artifact())
})
afterEach(()=>{wrappers.forEach(w=>w.unmount());wrappers.length=0;vi.clearAllTimers();vi.useRealTimers();vi.unstubAllGlobals()})

function deferred<T>() {
  let resolve!:(value:T)=>void
  const promise=new Promise<T>(done=>{resolve=done})
  return {promise,resolve}
}
function downloadSpies() {
  vi.useFakeTimers({toFake:['setTimeout','clearTimeout']})
  const create=vi.fn(()=>'blob:synthetic-export'),BaseURL=URL
  vi.stubGlobal('URL',class extends BaseURL {static createObjectURL=create;static revokeObjectURL=vi.fn()})
  const click=vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{})
  return {create,click}
}

it('uses the same original data for unit-separated plots, unknowns and paged detail without executing cells',async()=>{
  const w=mount(AssistantDataset,{props:{dataset,initialView:'chart'}});wrappers.push(w)
  expect(w.get('svg').text()).toContain('900')
  expect(w.get('svg').text()).not.toContain('库存可用量')
  expect(w.text()).toContain('未知')
  expect(w.text()).toContain('实际返回 41 / 50 条')
  expect(w.find('script').exists()).toBe(false)
  expect(w.text()).toContain('<script>secret()</script>')
  expect(w.findAll('tbody').at(-1)!.findAll('tr')).toHaveLength(20)
  await w.get('[aria-label="图表单位"]').setValue('1')
  expect(w.get('svg').text()).toContain('订单数')
  expect(w.get('svg').text()).not.toContain('900')
  await w.findAll('button').find(b=>b.text()==='下一页明细')!.trigger('click')
  expect(w.text()).toContain('合成订单20')
  expect(w.text()).not.toContain('<script>secret()</script>')
  expect(w.text()).toContain(dataset.dataset_id)
})

it('retains a conflicted draft, loads the latest comparison and saves only against that new revision',async()=>{
  const load=vi.mocked(assistantApi.artifact).mockResolvedValueOnce(artifact(2,'已保存第二版')).mockResolvedValueOnce(artifact(3,'另一窗口的第三版'))
  const save=vi.spyOn(assistantApi,'reviseArtifact').mockRejectedValueOnce(new AssistantApiError('版本冲突',409,'revision_conflict')).mockResolvedValueOnce(artifact(4,'我的合并稿'))
  const w=mount(AssistantArtifacts,{props:{selected:'a'}});wrappers.push(w);await flushPromises()
  await w.get('textarea').setValue('我的合并稿')
  await w.findAll('button').find(b=>b.text()==='保存为新版本')!.trigger('click');await flushPromises()
  expect(w.get('textarea').element.value).toBe('我的合并稿')
  await w.findAll('button').find(b=>b.text()==='读取最新版本并保留草稿')!.trigger('click');await flushPromises()
  expect(load).toHaveBeenCalledTimes(2)
  expect(w.get('textarea').element.value).toBe('我的合并稿')
  expect(w.text()).toContain('另一窗口的第三版')
  await w.findAll('button').find(b=>b.text()==='保存为新版本')!.trigger('click');await flushPromises()
  expect(save).toHaveBeenLastCalledWith('a',3,'我的合并稿')
  expect(w.text()).toContain('人工编辑')
  expect(w.findComponent(AssistantDataset).props('dataset')).toEqual(dataset)
})

it('requires an explicit discard before navigating away from an unsaved artifact',async()=>{
  const w=mount(AssistantArtifacts,{props:{selected:'a'}});wrappers.push(w);await flushPromises()
  await w.get('textarea').setValue('不能丢失的草稿')
  await w.findAll('button').find(b=>b.text()==='返回成果列表')!.trigger('click')
  expect(w.get('textarea').element.value).toBe('不能丢失的草稿')
  await w.findAll('button').find(b=>b.text()==='保留编辑')!.trigger('click')
  expect(w.get('textarea').element.value).toBe('不能丢失的草稿')
  await w.findAll('button').find(b=>b.text()==='返回成果列表')!.trigger('click')
  await w.findAll('button').find(b=>b.text()==='放弃草稿并继续')!.trigger('click')
  expect(w.find('textarea').exists()).toBe(false)
})

it('clears every private view when an export detects revoked sources',async()=>{
  vi.spyOn(assistantApi,'exportArtifact').mockRejectedValue(new AssistantApiError('来源已失效',410,'source_unavailable'))
  const w=mount(AssistantArtifacts,{props:{selected:'a'}});wrappers.push(w);await flushPromises()
  await w.findAll('button').find(b=>b.text()==='导出 PDF')!.trigger('click');await flushPromises()
  expect(w.text()).toContain('来源已失效')
  expect(w.find('textarea').exists()).toBe(false)
  expect(w.text()).not.toContain('900')
  expect(w.findComponent(AssistantDataset).exists()).toBe(false)
})

it('discards an export that finishes after an identity change',async()=>{
  let resolve!: (blob: Blob)=>void
  vi.spyOn(assistantApi,'exportArtifact').mockImplementation(()=>new Promise(done=>{resolve=done}))
  const click=vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{})
  const w=mount(AssistantArtifacts,{props:{selected:'a'}});wrappers.push(w);await flushPromises()
  await w.findAll('button').find(b=>b.text()==='导出 XLSX')!.trigger('click')
  window.dispatchEvent(new Event('auth-session-boundary-changed'));await nextTick()
  resolve(new Blob(['prior identity data']));await flushPromises()
  expect(click).not.toHaveBeenCalled()
  expect(w.text()).not.toContain('900')
})

it('clears an already loaded persistent artifact view on same-identity authorization invalidation',async()=>{
  const store=useAssistantStore();store.bindIdentity('alice:1')
  const w=mount(AssistantArtifacts,{props:{selected:'a'}});wrappers.push(w);await flushPromises()
  await w.get('textarea').setValue('PRIVATE-UNSAVED-REMARK')
  expect(w.text()).toContain('900')
  store.invalidateAuthorization();await nextTick()
  expect(w.find('textarea').exists()).toBe(false)
  expect(w.findComponent(AssistantDataset).exists()).toBe(false)
  expect(w.text()).not.toContain('订单成果')
  expect(w.text()).not.toContain('900')
  expect(w.text()).not.toContain('PRIVATE-UNSAVED-REMARK')
})

it('does not install an artifact opening response that arrives after authorization invalidation',async()=>{
  const store=useAssistantStore();store.bindIdentity('alice:1')
  const pending=deferred<Artifact>()
  vi.mocked(assistantApi.artifact).mockReturnValueOnce(pending.promise)
  const w=mount(AssistantArtifacts,{props:{selected:'a'}});wrappers.push(w);await flushPromises()
  store.invalidateAuthorization()
  pending.resolve(artifact(1,'PRIVATE-LATE-OPEN'));await flushPromises()
  expect(w.find('textarea').exists()).toBe(false)
  expect(w.findComponent(AssistantDataset).exists()).toBe(false)
  expect(w.text()).not.toContain('PRIVATE-LATE-OPEN')
})

it('does not create a download from an old export that resolves after authorization invalidation',async()=>{
  const {create,click}=downloadSpies(),store=useAssistantStore();store.bindIdentity('alice:1')
  const pending=deferred<Blob>()
  vi.spyOn(assistantApi,'exportArtifact').mockReturnValueOnce(pending.promise)
  const w=mount(AssistantArtifacts,{props:{selected:'a'}});wrappers.push(w);await flushPromises()
  await w.findAll('button').find(b=>b.text()==='导出 PDF')!.trigger('click')
  store.invalidateAuthorization()
  pending.resolve(new Blob(['PRIVATE-OLD-DOWNLOAD']));await flushPromises()
  expect(create).not.toHaveBeenCalled()
  expect(click).not.toHaveBeenCalled()
  expect(w.find('textarea').exists()).toBe(false)
})

it('keeps a new authorized download busy when an old export settles and still permits the new download',async()=>{
  const {create,click}=downloadSpies(),store=useAssistantStore();store.bindIdentity('alice:1')
  const old=deferred<Blob>(),current=deferred<Blob>()
  vi.spyOn(assistantApi,'exportArtifact').mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise)
  const w=mount(AssistantArtifacts,{props:{selected:'a'}});wrappers.push(w);await flushPromises()
  await w.findAll('button').find(b=>b.text()==='导出 PDF')!.trigger('click')
  store.invalidateAuthorization();await nextTick()
  vi.mocked(assistantApi.artifact).mockResolvedValueOnce({...artifact(1,'CURRENT-PERMITTED-B'),id:'b'})
  await w.setProps({selected:'b'});await flushPromises()
  expect(w.get('textarea').element.value).toBe('CURRENT-PERMITTED-B')
  await w.findAll('button').find(b=>b.text()==='导出 XLSX')!.trigger('click')
  old.resolve(new Blob(['PRIVATE-OLD-DOWNLOAD']));await flushPromises()
  expect(create).not.toHaveBeenCalled()
  expect(w.findAll('button').find(b=>b.text()==='导出 XLSX')!.attributes('disabled')).toBeDefined()
  current.resolve(new Blob(['CURRENT-PERMITTED-DOWNLOAD']));await flushPromises()
  expect(create).toHaveBeenCalledTimes(1)
  expect(click).toHaveBeenCalledTimes(1)
})
