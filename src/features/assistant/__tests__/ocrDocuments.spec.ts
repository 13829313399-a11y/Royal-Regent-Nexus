import { beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { advanceAuthenticationGeneration, announceSessionBoundary } from '@/lib/authenticationGeneration'
import { assistantApi } from '../api'
import { documentLocation, formatDocument, type DocumentSegment } from '../documentFormat'
import AssistantOcrPreview from '../AssistantOcrPreview.vue'
import AssistantSources from '../AssistantSources.vue'
import type { EvidencePart } from '../v2'

const parts: DocumentSegment[] = [1,2].map(page => ({text:'Quantity 4?0',locator:{kind:'ocr_region',page,region:1,bbox:{x:.12,y:.32,width:.28,height:.06,coordinate_system:'normalized_0_1'}},metadata:{format:'ocr',signal_score:.98,uncertain:true,uncertainty_reasons:['ambiguous_characters']}}))
beforeEach(() => {
  vi.restoreAllMocks()
  Object.defineProperty(URL,'createObjectURL',{configurable:true,value:vi.fn(()=>'blob:synthetic-page')})
  Object.defineProperty(URL,'revokeObjectURL',{configurable:true,value:vi.fn()})
})

it('keeps an ambiguous high-score candidate uncertain with an exact page and region', () => {
  expect(documentLocation(parts[1]!.locator)).toBe('第 2 页 · 识别区域 1')
  const value=formatDocument(parts)
  expect(value).toContain('Quantity 4?0')
  expect(value).toContain('0.980（不是正确率）')
  expect(value).toContain('待核对原页')
  expect(value).not.toContain('400')
})

it('loads the selected real page API and positions its normalized region', async () => {
  const api=vi.spyOn(assistantApi,'documentPage').mockResolvedValue(new Blob(['png']))
  const w=mount(AssistantOcrPreview,{props:{id:'file',parts}})
  await flushPromises()
  expect(api).toHaveBeenLastCalledWith('file',1)
  expect(w.get('.yl-ocr-box').attributes('style')).toContain('left: 12%')
  await w.get('select').setValue(1); await flushPromises()
  expect(api).toHaveBeenLastCalledWith('file',2)
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:synthetic-page')
  expect(w.get('img').attributes('alt')).toContain('第 2 页')
  await w.get('button').trigger('click')
  expect(w.get('.yl-ocr-page').classes()).toContain('yl-ocr-zoomed')
  w.unmount()
})

it('clears failed page content and allows explicit retry', async () => {
  const api=vi.spyOn(assistantApi,'documentPage').mockRejectedValueOnce(new Error('文件已删除')).mockResolvedValue(new Blob(['png']))
  const w=mount(AssistantOcrPreview,{props:{id:'file',parts}})
  await flushPromises(); expect(w.find('img').exists()).toBe(false)
  expect(w.text()).toContain('文件已删除')
  await w.get('button').trigger('click'); await flushPromises()
  expect(api).toHaveBeenCalledTimes(2); expect(w.find('img').exists()).toBe(true)
  await w.get('img').trigger('error')
  expect(w.find('img').exists()).toBe(false); expect(w.text()).toContain('原页图片未能显示')
  w.unmount()
})

it('does not restore a previous file when its page fetch resolves late', async () => {
  let resolve!: (b:Blob)=>void
  vi.spyOn(assistantApi,'documentPage').mockReturnValueOnce(new Promise(r=>{resolve=r})).mockResolvedValue(new Blob(['new']))
  const w=mount(AssistantOcrPreview,{props:{id:'old',parts}})
  await w.setProps({id:'new'}); await flushPromises()
  resolve(new Blob(['old'])); await flushPromises()
  expect(URL.createObjectURL).toHaveBeenCalledTimes(1)
  w.unmount()
})

it('clears page blobs and blocks late callbacks at the authentication boundary', async () => {
  let resolve!: (b:Blob)=>void
  vi.spyOn(assistantApi,'documentPage').mockReturnValue(new Promise(r=>{resolve=r}))
  const w=mount(AssistantOcrPreview,{props:{id:'file',parts}})
  advanceAuthenticationGeneration(); announceSessionBoundary()
  resolve(new Blob(['old'])); await flushPromises()
  expect(URL.createObjectURL).not.toHaveBeenCalled(); expect(w.find('section').exists()).toBe(false)
  w.unmount()
})

it('opens only the cited OCR region through the actual source component', async () => {
  vi.spyOn(assistantApi,'documentContent').mockResolvedValue(parts)
  const api=vi.spyOn(assistantApi,'documentPage').mockResolvedValue(new Blob(['png']))
  const evidence:EvidencePart={type:'evidence',schema_version:2,run_id:'r',revision:1,search:{requested_mode:'off',execution:'not_requested',evidence_level:'none',search_count:null,reason_code:null},citations:[],activities:[],sources:[{kind:'file',source_id:'s',run_id:'r',title:'scan.pdf',file_ref:{kind:'document',id:'file'},extracted_at:'2026-10-25T00:00:00Z',locator:parts[1]!.locator}]}
  const w=mount(AssistantSources,{props:{evidence},attachTo:document.body})
  await w.get('article button').trigger('click'); await flushPromises()
  expect(api).toHaveBeenCalledWith('file',2)
  expect(w.find('select').exists()).toBe(false)
  expect(w.text()).toContain('第 2 页 · 识别区域 1')
  await w.get('.yl-file-preview').trigger('keydown',{key:'Escape'}); await flushPromises()
  expect(w.find('img').exists()).toBe(false)
  expect(document.activeElement).toBe(w.get('article button').element)
  w.unmount()
})
