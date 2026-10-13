import { beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import { assistantApi, AssistantApiError } from '../api'
import AssistantArtifacts from '../AssistantArtifacts.vue'
import AssistantDocument from '../AssistantDocument.vue'
import { useAssistantStore } from '@/stores/assistant'
import type { Artifact, DocumentFile } from '../types'

beforeEach(() => { vi.restoreAllMocks(); setActivePinia(createPinia()) })
const artifact = (content = '已保存正文', version = 1): Artifact => ({ id:'a', title:'合成成果', kind:'markdown', content, revision:version, current_revision:version, source_refs:[], export_formats:['md'] })
const file: DocumentFile = { id:'f', name:'合成资料.txt', parse_status:'ready' }

it('requires saving visible edits before export and then exports the newly saved revision', async () => {
  vi.spyOn(assistantApi,'artifacts').mockResolvedValue({items:[],next_cursor:null})
  vi.spyOn(assistantApi,'artifact').mockResolvedValue(artifact())
  vi.spyOn(assistantApi,'reviseArtifact').mockResolvedValue(artifact('新正文',2))
  const exportFile = vi.spyOn(assistantApi,'exportArtifact').mockResolvedValue(new Blob(['新正文']))
  vi.stubGlobal('URL', Object.assign(URL, {createObjectURL:vi.fn(()=>'blob:synthetic'),revokeObjectURL:vi.fn()}))
  vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{})
  const w=mount(AssistantArtifacts,{props:{selected:'a'}}); await flushPromises()
  await w.get('textarea').setValue('新正文')
  const download=()=>w.findAll('button').find(b=>b.text()==='导出 MD')!
  expect(download().attributes('disabled')).toBeDefined()
  expect(w.text()).toContain('有未保存的修改')
  await download().trigger('click'); expect(exportFile).not.toHaveBeenCalled()
  await w.findAll('button').find(b=>b.text()==='保存为新版本')!.trigger('click'); await flushPromises()
  expect(download().attributes('disabled')).toBeUndefined()
  await download().trigger('click'); await flushPromises()
  expect(exportFile).toHaveBeenCalledWith('a','md',2)
  expect(w.get('textarea').element.value).toBe('新正文'); w.unmount()
})

it('keeps a conflicting draft and prevents downloading a misleading old version',async()=>{
  vi.spyOn(assistantApi,'artifacts').mockResolvedValue({items:[],next_cursor:null})
  vi.spyOn(assistantApi,'artifact').mockResolvedValue(artifact())
  vi.spyOn(assistantApi,'reviseArtifact').mockRejectedValue(new AssistantApiError('版本冲突',409,'revision_conflict'))
  const w=mount(AssistantArtifacts,{props:{selected:'a'}}); await flushPromises()
  await w.get('textarea').setValue('我的修改')
  await w.findAll('button').find(b=>b.text()==='保存为新版本')!.trigger('click'); await flushPromises()
  expect(w.get('textarea').element.value).toBe('我的修改')
  expect(w.text()).toContain('版本冲突')
  expect(w.findAll('button').find(b=>b.text()==='导出 MD')!.attributes('disabled')).toBeDefined(); w.unmount()
})

it('blocks export while a selected revision loads and retains the visible revision on failure',async()=>{
  vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{})
  vi.spyOn(assistantApi,'artifacts').mockResolvedValue({items:[],next_cursor:null})
  let reject!: (reason:Error)=>void
  vi.spyOn(assistantApi,'artifact').mockResolvedValueOnce(artifact('第二版正文',2)).mockReturnValueOnce(new Promise((_,r)=>{reject=r}))
  const exportFile=vi.spyOn(assistantApi,'exportArtifact').mockResolvedValue(new Blob(['第二版正文']))
  const w=mount(AssistantArtifacts,{props:{selected:'a'}}); await flushPromises()
  await w.get('select').setValue('1')
  expect(w.get('textarea').element.value).toBe('第二版正文')
  const download=()=>w.findAll('button').find(b=>b.text()==='导出 MD')!
  expect(download().attributes('disabled')).toBeDefined()
  await download().trigger('click'); expect(exportFile).not.toHaveBeenCalled()
  reject(new Error('合成读取失败')); await flushPromises()
  expect(w.get('select').element.value).toBe('2')
  expect(w.get('textarea').element.value).toBe('第二版正文')
  await download().trigger('click'); await flushPromises()
  expect(exportFile).toHaveBeenCalledWith('a','md',2); w.unmount()
})

it('reads historical file metadata and indexed content, and deletes only after confirmation',async()=>{
  vi.spyOn(assistantApi,'document').mockResolvedValue(file)
  vi.spyOn(assistantApi,'documentContent').mockResolvedValue([{text:'合成原文',locator:{kind:'lines',start:1,end:2}}])
  const remove=vi.spyOn(assistantApi,'removeDocument').mockResolvedValue(new Response(null,{status:204}))
  const w=mount(AssistantDocument,{props:{id:'f'}}); await flushPromises()
  expect(w.text()).toContain('合成资料.txt'); expect(w.text()).toContain('可分析')
  await w.findAll('button').find(b=>b.text()==='查看文件原文')!.trigger('click'); await flushPromises()
  expect(w.text()).toContain('第 1–2 行'); expect(w.text()).toContain('合成原文')
  await w.findAll('button').find(b=>b.text()==='删除文件')!.trigger('click')
  expect(remove).not.toHaveBeenCalled(); expect(w.text()).toContain('全部版本将不可读取或导出')
  await w.findAll('button').find(b=>b.text()==='确认删除文件')!.trigger('click'); await flushPromises()
  expect(remove).toHaveBeenCalledWith('f'); expect(w.emitted('deleted')).toHaveLength(1)
  expect(w.text()).toContain('文件已删除'); expect(w.text()).not.toContain('合成原文'); w.unmount()
})

it('does not restore private metadata after an identity switch or show controls for a deleted file',async()=>{
  let resolve!: (value:DocumentFile)=>void
  vi.spyOn(assistantApi,'document').mockReturnValueOnce(new Promise(r=>{resolve=r})).mockRejectedValueOnce(new AssistantApiError('文件已删除',410,'source_unavailable'))
  const store=useAssistantStore(); store.bindIdentity('first')
  const w=mount(AssistantDocument,{props:{id:'f'}})
  store.bindIdentity('second'); await flushPromises()
  resolve(file); await flushPromises()
  expect(w.text()).toContain('文件已删除'); expect(w.text()).not.toContain('合成资料.txt')
  expect(w.findAll('button')).toHaveLength(0); w.unmount()
})

it('explains a historical parse failure and withholds content preview',async()=>{
  vi.spyOn(assistantApi,'document').mockResolvedValue({...file,parse_status:'failed',error_code:'parse_memory_limit'})
  const w=mount(AssistantDocument,{props:{id:'f'}});await flushPromises()
  expect(w.text()).toContain('解析超出内存限制，请拆分后重新上传')
  expect(w.text()).not.toContain('parse_memory_limit')
  expect(w.findAll('button').some(b=>b.text()==='查看文件原文')).toBe(false);w.unmount()
})
