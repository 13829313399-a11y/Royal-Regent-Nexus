import { beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { advanceAuthenticationGeneration, announceSessionBoundary } from '@/lib/authenticationGeneration'
import { assistantApi } from '../api'
import { formatDocument, type DocumentSegment } from '../documentFormat'
import AssistantDocument from '../AssistantDocument.vue'
import AssistantSources from '../AssistantSources.vue'
import type { EvidencePart, FileSource } from '../v2'

beforeEach(() => { vi.restoreAllMocks(); setActivePinia(createPinia()) })
const parts: DocumentSegment[] = [
  {text:'400',locator:{kind:'sheet',sheet:'采购',cells:'C7'},metadata:{format:'xlsx',formula:'=A7-B7',cache_status:'available',coverage:'只读已保存缓存'}},
  {text:'未知（公式未保存可用缓存）',locator:{kind:'sheet',sheet:'采购',cells:'D7'},metadata:{formula:'=EXTERNAL_REF',cache_status:'missing',coverage:'只读已保存缓存'}},
  {text:'合成表头',locator:{kind:'sheet',sheet:'采购',cells:'A1'},metadata:{merged_range:'A1:D1',merged_anchor:'A1'}},
]
const source: FileSource = {kind:'file',source_id:'cell',run_id:'r',title:'合成采购.xlsx',file_ref:{kind:'document',id:'f'},extracted_at:'2026-10-25T00:00:00Z',locator:parts[1]!.locator}
const evidence: EvidencePart = {type:'evidence',schema_version:2,run_id:'r',revision:1,search:{requested_mode:'off',execution:'not_requested',evidence_level:'none',search_count:null,reason_code:null},sources:[source],citations:[],activities:[]}

it('shows truthful formula cache, unknown, merged-header and paragraph locations', () => {
  const text = formatDocument([...parts,{text:'合成条款',locator:{kind:'paragraph',paragraph:8},metadata:{heading:'验收条件',in_table:true}}])
  expect(text).toContain('采购!C7\n400\n公式（未执行）：=A7-B7')
  expect(text).toContain('缓存：未保存可用值，不能按 0 处理')
  expect(text).toContain('合并区域：A1:D1；值来自 A1')
  expect(text).toContain('第 8 段 · 验收条件')
  expect(text.match(/只读已保存缓存/g)).toHaveLength(1)
})

it('renders Office metadata through the actual document component', async () => {
  vi.spyOn(assistantApi,'document').mockResolvedValue({id:'f',name:'合成采购.xlsx',parse_status:'ready'})
  vi.spyOn(assistantApi,'documentContent').mockResolvedValue(parts)
  const w = mount(AssistantDocument,{props:{id:'f'},attachTo:document.body}); await flushPromises()
  await w.findAll('button').find(b=>b.text()==='查看文件原文')!.trigger('click'); await flushPromises()
  expect(w.get('pre').text()).toContain('采购!D7')
  expect(w.get('pre').text()).toContain('不能按 0 处理')
  expect(document.activeElement?.textContent).toBe('关闭文件原文')
  await w.get('.yl-file-preview').trigger('keydown',{key:'Escape'}); await flushPromises()
  expect(w.find('pre').exists()).toBe(false)
  expect(document.activeElement?.textContent).toBe('查看文件原文'); w.unmount()
})

it('refreshes the material card when the parent observes parser completion', async () => {
  vi.spyOn(assistantApi,'document')
    .mockResolvedValueOnce({id:'f',name:'合成采购.xlsx',parse_status:'parsing'})
    .mockResolvedValueOnce({id:'f',name:'合成采购.xlsx',parse_status:'ready'})
  const w=mount(AssistantDocument,{props:{id:'f',status:'parsing'}}); await flushPromises()
  expect(w.text()).toContain('解析中')
  expect(w.text()).not.toContain('查看文件原文')
  await w.setProps({status:'ready'}); await flushPromises()
  expect(w.text()).toContain('可分析'); expect(w.text()).toContain('查看文件原文'); w.unmount()
})

it('shows only the cited cell and refuses a missing locator', async () => {
  const read = vi.spyOn(assistantApi,'documentContent').mockResolvedValue(parts)
  const w = mount(AssistantSources,{props:{evidence}})
  await w.get('button').trigger('click'); await flushPromises()
  expect(w.get('pre').text()).toContain('=EXTERNAL_REF')
  expect(w.get('pre').text()).not.toContain('=A7-B7')
  read.mockResolvedValue([parts[0]!])
  await w.findAll('button').find(b=>b.text()==='关闭引用原文')!.trigger('click')
  await w.get('button').trigger('click'); await flushPromises()
  expect(w.find('pre').exists()).toBe(false)
  expect(w.text()).toContain('引用位置当前不可用'); w.unmount()
})

it.each(['evidence','identity'] as const)('discards a late private preview after %s changes', async (change) => {
  let resolve!: (value:DocumentSegment[])=>void
  vi.spyOn(assistantApi,'documentContent').mockReturnValue(new Promise(r=>{resolve=r}))
  const w = mount(AssistantSources,{props:{evidence}})
  await w.get('button').trigger('click')
  if (change==='evidence') await w.setProps({evidence:null})
  else { advanceAuthenticationGeneration(); announceSessionBoundary() }
  resolve(parts); await flushPromises()
  expect(w.find('pre').exists()).toBe(false); w.unmount()
})

it('explains Office parse failures without leaking an internal error code', async () => {
  vi.spyOn(assistantApi,'document').mockResolvedValue({id:'f',name:'fake.xlsx',parse_status:'failed',error_code:'office_signature'})
  const w=mount(AssistantDocument,{props:{id:'f'}});await flushPromises()
  expect(w.text()).toContain('文件内容与 Office 格式不符')
  expect(w.text()).not.toContain('office_signature'); w.unmount()
})
