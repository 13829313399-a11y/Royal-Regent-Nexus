import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import AssistantFeedback from '../AssistantFeedback.vue'
import AssistantMessage from '../AssistantMessage.vue'
import { assistantApi, AssistantApiError } from '../api'
import type { FeedbackData, FeedbackRecord, Message } from '../types'
import { createMemoryHistory, createRouter } from 'vue-router'

const source={source_id:'source-one',kind:'business',title:'合成原单的很长来源名称 <script>不执行()</script>',citation_eligible:true}
const empty:FeedbackData={run_id:'run',available:true,feedback:null,sources:[source]}
const saved=(comment='我的说明',revision=1):FeedbackRecord=>({run_id:'run',revision,categories:['factual'],source_ids:[source.source_id],comment,updated_at:1})
const wrappers:ReturnType<typeof mount>[]=[]
function form(){const w=mount(AssistantFeedback,{attachTo:document.body,props:{runId:'run',open:true,available:true}});wrappers.push(w);return w}
function button(w:ReturnType<typeof mount>,label:string){return w.findAll('button').find(b=>b.text()===label)!}
beforeEach(()=>{
  vi.restoreAllMocks()
  vi.spyOn(assistantApi,'feedback').mockResolvedValue(empty)
  vi.spyOn(assistantApi,'saveFeedback').mockResolvedValue(saved())
  vi.spyOn(assistantApi,'send')
})
afterEach(()=>{wrappers.forEach(w=>w.unmount());wrappers.length=0;document.body.innerHTML=''})

it('loads the original feedback, saves explicit categories and source IDs without changing or generating an answer',async()=>{
  const w=form();await flushPromises()
  expect(w.find('script').exists()).toBe(false);expect(w.text()).toContain(source.title)
  await w.get('input[value="factual"]').setValue(true)
  await w.get('input[value="source-one"]').setValue(true)
  await w.get('textarea').setValue('我的说明')
  await button(w,'保存反馈').trigger('click');await flushPromises()
  const payload=vi.mocked(assistantApi.saveFeedback).mock.calls[0]![1]
  expect(payload).toMatchObject({base_revision:0,categories:['factual'],source_ids:['source-one'],comment:'我的说明'})
  expect(payload.client_request_id).toMatch(/^[a-f0-9]{32}$/)
  expect(w.text()).toContain('反馈已保存');expect(assistantApi.send).not.toHaveBeenCalled()
})

it('freezes an uncertain save and uses the identical request only after an explicit retry',async()=>{
  vi.mocked(assistantApi.saveFeedback).mockRejectedValueOnce(new TypeError('network response lost')).mockResolvedValueOnce(saved())
  const w=form();await flushPromises();await w.get('textarea').setValue('我的说明')
  await button(w,'保存反馈').trigger('click');await flushPromises()
  expect(w.text()).toContain('保存结果待确认');expect(w.get('fieldset').attributes('disabled')).toBeDefined()
  expect(assistantApi.saveFeedback).toHaveBeenCalledTimes(1)
  await button(w,'按原请求重试保存').trigger('click');await flushPromises()
  const calls=vi.mocked(assistantApi.saveFeedback).mock.calls
  expect(calls[1]?.[1]).toEqual(calls[0]?.[1]);expect(w.text()).toContain('反馈已保存')
  expect(assistantApi.send).not.toHaveBeenCalled()
})

it('resolves a lost save response through a read without posting feedback or generation again',async()=>{
  vi.mocked(assistantApi.saveFeedback).mockRejectedValueOnce(new TypeError('response lost'))
  vi.mocked(assistantApi.feedback).mockResolvedValueOnce(empty).mockResolvedValueOnce({...empty,feedback:{...saved(),categories:[],source_ids:[]}})
  const w=form();await flushPromises();await w.get('textarea').setValue('我的说明')
  await button(w,'保存反馈').trigger('click');await flushPromises()
  await button(w,'查询已保存反馈').trigger('click');await flushPromises()
  expect(w.text()).toContain('反馈已保存');expect(w.text()).not.toContain('保存结果待确认')
  expect(assistantApi.saveFeedback).toHaveBeenCalledTimes(1);expect(assistantApi.send).not.toHaveBeenCalled()
})

it('preserves a conflicting draft and replaces server content only through an explicit choice',async()=>{
  vi.mocked(assistantApi.saveFeedback).mockRejectedValueOnce(new AssistantApiError('已保存反馈已更新，草稿保留。',409,'feedback_conflict')).mockResolvedValueOnce(saved('当前草稿',3))
  vi.mocked(assistantApi.feedback).mockResolvedValueOnce(empty).mockResolvedValueOnce({...empty,feedback:saved('另一版本',2)})
  const w=form();await flushPromises();await w.get('textarea').setValue('当前草稿')
  await button(w,'保存反馈').trigger('click');await flushPromises()
  await button(w,'查询已保存反馈').trigger('click');await flushPromises()
  expect((w.get('textarea').element as HTMLTextAreaElement).value).toBe('当前草稿')
  expect(w.text()).toContain('另一版本');expect(assistantApi.saveFeedback).toHaveBeenCalledTimes(1)
  await button(w,'以当前草稿替换已保存反馈').trigger('click');await flushPromises()
  expect(vi.mocked(assistantApi.saveFeedback).mock.calls[1]?.[1]).toMatchObject({base_revision:2,comment:'当前草稿'})
})

it('clears private feedback when source access fails and emits the parent invalidation signal',async()=>{
  vi.mocked(assistantApi.feedback).mockResolvedValue({...empty,feedback:saved('私有说明')})
  vi.mocked(assistantApi.saveFeedback).mockRejectedValue(new AssistantApiError('来源已失效',410,'sources_unavailable'))
  const w=form();await flushPromises();await button(w,'保存反馈').trigger('click');await flushPromises()
  expect(w.emitted('unavailable')).toHaveLength(1)
  expect((w.get('textarea').element as HTMLTextAreaElement).value).toBe('');expect(w.text()).not.toContain('私有说明')
})

it('ignores a previous run read and never steals focus from another control after loading',async()=>{
  let finish!:(v:FeedbackData)=>void
  vi.mocked(assistantApi.feedback).mockReturnValueOnce(new Promise(resolve=>{finish=resolve})).mockResolvedValueOnce({...empty,run_id:'new-run',sources:[]})
  const w=form();await flushPromises()
  await w.setProps({runId:'new-run'});await flushPromises()
  const outside=document.createElement('button');outside.textContent='其他控件';document.body.append(outside);outside.focus()
  finish({...empty,feedback:saved('旧运行私有文字')});await flushPromises()
  expect((w.get('textarea').element as HTMLTextAreaElement).value).toBe('')
  expect(document.activeElement).toBe(outside)
})

it('gives an accurate disabled reason on an older backend and does not call missing APIs',async()=>{
  const w=mount(AssistantFeedback,{props:{runId:'run',open:true,available:false}});wrappers.push(w);await flushPromises()
  expect(w.text()).toContain('反馈功能尚未准备完成');expect(button(w,'保存反馈').attributes('disabled')).toBeDefined()
  expect(assistantApi.feedback).not.toHaveBeenCalled()
})

it('puts feedback and regeneration in the keyboard menu and prepares edits without a generation request',async()=>{
  const router=createRouter({history:createMemoryHistory(),routes:[]})
  const message:Message={id:'saved',run_id:'run',seq:2,role:'assistant',status:'completed',content_parts:[{type:'text',text:'原回答'}],help_citations:[],context_descriptor:null,created_at:1}
  const w=mount(AssistantMessage,{attachTo:document.body,props:{message,feedbackAvailable:true},global:{plugins:[router]}});wrappers.push(w)
  await w.get('[aria-label="更多回答操作"]').trigger('keydown',{key:'ArrowDown'});await flushPromises()
  const item=[...document.querySelectorAll<HTMLElement>('[role="menuitem"]')].find(el=>el.textContent==='重新生成新回答')!
  item.click();await flushPromises()
  expect(w.emitted('related')?.[0]).toEqual(['run','regenerate']);expect(assistantApi.send).not.toHaveBeenCalled()
  await w.get('[aria-label="更多回答操作"]').trigger('keydown',{key:'ArrowDown'});await flushPromises()
  const feedbackItem=[...document.querySelectorAll<HTMLElement>('[role="menuitem"]')].find(el=>el.textContent==='反馈')!
  feedbackItem.click();await flushPromises()
  expect(w.text()).toContain('反馈这次回答');expect(assistantApi.feedback).toHaveBeenCalledWith('run',expect.any(AbortSignal))
})
