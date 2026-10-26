import { beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { useAssistantStore } from '@/stores/assistant'
import { assistantApi } from '../api'
import AssistantDocumentSearch from '../AssistantDocumentSearch.vue'
import AssistantDocumentReplacement from '../AssistantDocumentReplacement.vue'
import AssistantSources from '../AssistantSources.vue'
import type { DocumentFile, DocumentSearchResult } from '../types'
import type { EvidencePart, FileSource } from '../v2'

beforeEach(() => { vi.restoreAllMocks(); setActivePinia(createPinia()) })
const file: DocumentFile={id:'old',session_id:'s',name:'合成条款.txt',parse_status:'ready',document_version:'a'.repeat(64),indexed_segments:1000}
const replacement: DocumentFile={...file,id:'new',document_version:'b'.repeat(64)}
const result: DocumentSearchResult={materials:[{source_id:'chunk',name:file.name,text:'SYN-R0913 验收条款',locator:{kind:'paragraph',paragraph:914},document_version:file.document_version!,excerpt_range:{start:0,end:16,total:2000}}],report:{selected_chunks:1,total_chunks:1000,matched_chunks:1,coverage:'partial',notice:'未召回不代表不存在',unmatched_identifiers:[]}}

it('searches explicit input and shows bounded recall with original location and keyboard focus',async()=>{
  const api=vi.spyOn(assistantApi,'searchDocuments').mockResolvedValue(result)
  const w=mount(AssistantDocumentSearch,{props:{file},attachTo:document.body})
  expect(w.get('button').attributes('disabled')).toBeDefined()
  await w.get('input').setValue('SYN-R0913'); await w.get('input').trigger('keydown',{key:'Enter'}); await flushPromises()
  expect(api).toHaveBeenCalledWith('s',['old'],'SYN-R0913')
  expect(w.text()).toContain('选取 1 / 1000 个片段')
  expect(w.text()).toContain('第 914 段');expect(w.text()).toContain('部分文字')
  expect(document.activeElement).toBe(w.get('h4').element)
  await w.get('h4').trigger('keydown',{key:'Escape'}); expect(document.activeElement).toBe(w.get('input').element)
  w.unmount()
})

it('shows no-match and failure states without implying that a fact does not exist',async()=>{
  const api=vi.spyOn(assistantApi,'searchDocuments').mockResolvedValue({...result,materials:[],report:{...result.report,selected_chunks:0,coverage:'no_match',unmatched_identifiers:['syn-x0001']}})
  const w=mount(AssistantDocumentSearch,{props:{file}})
  await w.get('input').setValue('SYN-X0001');await w.get('button').trigger('click');await flushPromises()
  expect(w.text()).toContain('未命中所查内容');expect(w.text()).toContain('未召回不代表不存在')
  api.mockRejectedValue(new Error('文件版本已变化'))
  await w.get('button').trigger('click');await flushPromises()
  expect(w.find('h4').exists()).toBe(false);expect(w.text()).toContain('文件版本已变化');w.unmount()
})

it.each(['file','identity'] as const)('rejects late search results after %s changes',async(change)=>{
  let resolve!: (v:DocumentSearchResult)=>void
  vi.spyOn(assistantApi,'searchDocuments').mockReturnValue(new Promise(r=>{resolve=r}))
  const w=mount(AssistantDocumentSearch,{props:{file}})
  await w.get('input').setValue('SYN-R0913');await w.get('button').trigger('click')
  if(change==='file') await w.setProps({file:replacement})
  else useAssistantStore().identityGeneration++
  await flushPromises();resolve(result);await flushPromises()
  expect(w.find('h4').exists()).toBe(false);expect(w.get('input').element.value).toBe('');w.unmount()
})

it('retains the original on failed replacement and selects the independently parsed new version on success',async()=>{
  const store=useAssistantStore(); store.draftFor('s').documents=[file,replacement,{...file,id:'pending',parse_status:'parsing'}]
  const api=vi.spyOn(assistantApi,'replaceDocument').mockRejectedValueOnce(new Error('新文件版本已变化')).mockResolvedValue({replaced_file_id:'old',file:replacement})
  const w=mount(AssistantDocumentReplacement,{props:{file}})
  expect(w.findAll('option')).toHaveLength(2)
  await w.get('select').setValue('new');await w.get('button').trigger('click');await flushPromises()
  expect(w.text()).toContain('新文件版本已变化');expect(store.draftFor('s').documents.some(d=>d.id==='old')).toBe(true)
  await w.get('button').trigger('click');await flushPromises()
  expect(api).toHaveBeenLastCalledWith('old','new',file.document_version,replacement.document_version)
  expect(store.draftFor('s').documents.some(d=>d.id==='old')).toBe(false);expect(w.emitted('replaced')).toHaveLength(1);w.unmount()
})

it('does not mutate a changed identity draft when replacement returns late',async()=>{
  const store=useAssistantStore();store.draftFor('s').documents=[file,replacement]
  let resolve!: (v:{replaced_file_id:string;file:DocumentFile})=>void
  vi.spyOn(assistantApi,'replaceDocument').mockReturnValue(new Promise(r=>{resolve=r}))
  const w=mount(AssistantDocumentReplacement,{props:{file}})
  await w.get('select').setValue('new');await w.get('button').trigger('click')
  store.identityGeneration++;await flushPromises();resolve({replaced_file_id:'old',file:replacement});await flushPromises()
  expect(store.draftFor('s').documents).toHaveLength(2);expect(w.emitted('replaced')).toBeUndefined();w.unmount()
})

it('previews only a version-bound excerpt and rejects a mismatched range',async()=>{
  const source:FileSource={kind:'file',source_id:'chunk',run_id:'r',title:file.name,file_ref:{kind:'document',id:'old'},extracted_at:'2026-10-25T00:00:00Z',locator:{kind:'paragraph',paragraph:1},document_version:file.document_version,excerpt_range:{start:3,end:7,total:10}}
  const evidence:EvidencePart={type:'evidence',schema_version:2,run_id:'r',revision:1,search:{requested_mode:'off',execution:'not_requested',evidence_level:'none',search_count:null,reason_code:null},sources:[source],citations:[],activities:[]}
  const api=vi.spyOn(assistantApi,'documentContent').mockResolvedValue([{text:'0😀23456789',locator:source.locator}])
  const w=mount(AssistantSources,{props:{evidence}})
  await w.get('button').trigger('click');await flushPromises()
  expect(api).toHaveBeenCalledWith('old',file.document_version);expect(w.get('pre').text()).toContain('3456');expect(w.get('pre').text()).not.toContain('0123')
  await w.setProps({evidence:{...evidence,sources:[{...source,excerpt_range:{start:3,end:12,total:10}}]}})
  await w.get('button').trigger('click');await flushPromises();expect(w.find('pre').exists()).toBe(false);expect(w.text()).toContain('引用片段已变化');w.unmount()
})
