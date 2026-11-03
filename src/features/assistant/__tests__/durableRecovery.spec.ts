import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { useAssistantStore } from '@/stores/assistant'
import { assistantApi } from '../api'
import type { Capabilities, SendPayload, Snapshot, RunState } from '../types'

const input: Omit<SendPayload, 'client_request_id'> = { protocol_version:2, text:'合成问题', attachment_ids:[], intent:'chat', profile_id:'default', thinking:'auto', web_search:'off', page_context:null }
const conversation = {id:'s',title:'私有标题',revision:1,deletion_state:'active',created_at:1,updated_at:1}
function snapshot(text: string, seq: number, state: RunState = 'answering'): Snapshot {
  return {run_id:'r',session_id:'s',state,usage:null,error_code:null,context_window:{},protocol_version:3,event_seq:seq,
    items:[{id:'q',run_id:'r',seq:1,role:'user',status:'completed',content_parts:[{type:'text',text:input.text}],help_citations:[],context_descriptor:null,created_at:1},
      {id:'a',run_id:'r',seq:2,role:'assistant',status:state,content_parts:[{type:'text',part_id:'chat-0:text',text}],help_citations:[],context_descriptor:null,created_at:1}]}
}
function event(event: string, seq: number, data: Record<string,unknown> = {}) { return `event: ${event}\ndata: ${JSON.stringify({run_id:'r',seq,...data})}\n\n` }
function response(...frames: string[]) { return new Response(frames.join(''),{headers:{'Content-Type':'text/event-stream'}}) }
function setup() {
  const store=useAssistantStore();store.bindIdentity('alice:1');store.selectedId='s';store.sessions=[conversation]
  store.capabilities={run_protocols:[1,2,3],durable_runs:{available:true,reason:null}} as Capabilities
  return store
}
beforeEach(()=>{
  vi.restoreAllMocks();setActivePinia(createPinia())
  vi.spyOn(assistantApi,'send').mockResolvedValue(new Response(JSON.stringify({run_id:'r',reused:false}),{status:202,headers:{'Content-Type':'application/json'}}))
  vi.spyOn(assistantApi,'sessions').mockResolvedValue({items:[conversation],next_cursor:null})
})
afterEach(()=>{useAssistantStore().bindIdentity('');vi.useRealTimers()})

it('promotes only advertised V3 and repairs a gap with the same run without another admission',async()=>{
  const store=setup()
  vi.spyOn(assistantApi,'snapshot').mockResolvedValueOnce(snapshot('第一段',3)).mockResolvedValueOnce(snapshot('第一段第二段补齐',6)).mockResolvedValueOnce(snapshot('第一段第二段补齐最后',8,'completed'))
  vi.spyOn(assistantApi,'events').mockResolvedValueOnce(response(event('response.delta',3,{channel:'answer',text:'重复'}),event('response.delta',4,{channel:'answer',part_id:'chat-0:text',text:'第二段'}),event('response.delta',6,{channel:'answer',text:'缺口后'})))
    .mockResolvedValueOnce(response(event('response.delta',6,{channel:'answer',text:'又重复'}),event('response.delta',7,{channel:'answer',part_id:'chat-0:text',text:'最后'}),event('run.completed',8)))
  await store.submit(input)
  expect(assistantApi.send).toHaveBeenCalledTimes(1)
  expect(vi.mocked(assistantApi.send).mock.calls[0]?.[1].protocol_version).toBe(3)
  expect(vi.mocked(assistantApi.events).mock.calls.map(c=>[c[0],c[1]])).toEqual([['r',3],['r',6]])
  expect(store.currentRun?.state).toBe('completed');expect(store.currentRun?.lastSeq).toBe(8)
  expect(store.messages.at(-1)?.content_parts[0]?.text).toBe('第一段第二段补齐最后')
})

it('retries a failed GET subscription while preserving the last server state and never repeats POST',async()=>{
  vi.useFakeTimers()
  const store=setup()
  vi.spyOn(assistantApi,'snapshot').mockResolvedValueOnce(snapshot('部分',3)).mockResolvedValueOnce(snapshot('部分完成',5,'completed'))
  vi.spyOn(assistantApi,'events').mockRejectedValueOnce(new TypeError('network failed')).mockResolvedValueOnce(response(event('response.delta',4,{channel:'answer',part_id:'chat-0:text',text:'完成'}),event('run.completed',5)))
  const running=store.submit(input);await flushPromises()
  expect(store.currentRun?.state).toBe('answering');expect(store.currentRun?.subscriptionState).toBe('retrying');expect(store.busy).toBe(true)
  await vi.advanceTimersByTimeAsync(400);await running
  expect(assistantApi.send).toHaveBeenCalledTimes(1);expect(assistantApi.events).toHaveBeenCalledTimes(2)
  expect(store.messages.at(-1)?.content_parts[0]?.text).toBe('部分完成')
})

it('recovers a lost admission response only through the original lookup key',async()=>{
  const store=setup()
  vi.mocked(assistantApi.send).mockRejectedValueOnce(new TypeError('response lost after commit'))
  vi.spyOn(assistantApi,'lookup').mockResolvedValue(snapshot('部分',3))
  vi.spyOn(assistantApi,'snapshot').mockResolvedValue(snapshot('部分完成',4,'completed'))
  vi.spyOn(assistantApi,'events').mockResolvedValue(response(event('run.completed',4)))
  await store.submit(input)
  const sent=vi.mocked(assistantApi.send).mock.calls[0]![1]
  expect(assistantApi.lookup).toHaveBeenCalledWith('s',sent.client_request_id)
  expect(assistantApi.send).toHaveBeenCalledTimes(1);expect(store.messages).toHaveLength(2)
  expect(store.currentRun?.state).toBe('completed')
})

it('refresh restores active saved content and subscribes after its atomic snapshot sequence',async()=>{
  const store=setup()
  vi.spyOn(assistantApi,'messages').mockResolvedValue({session:conversation,items:snapshot('刷新前部分',3).items,next_cursor:null,active_run_id:'r',active_run_protocol_version:3,active_run_state:'answering',active_event_seq:3})
  vi.spyOn(assistantApi,'events').mockResolvedValue(response(event('response.delta',4,{channel:'answer',part_id:'chat-0:text',text:'刷新后完成'}),event('run.completed',5)))
  vi.spyOn(assistantApi,'snapshot').mockResolvedValue(snapshot('刷新前部分刷新后完成',5,'completed'))
  await store.selectSession('s');await flushPromises()
  expect(assistantApi.send).not.toHaveBeenCalled();expect(assistantApi.events).toHaveBeenCalledWith('r',3,expect.any(AbortSignal))
  expect(store.messages.at(-1)?.content_parts[0]?.text).toBe('刷新前部分刷新后完成')
})

it('revoked replay clears body title draft layers generation and rejects a late history response',async()=>{
  const store=setup()
  let finishHistory!:(v:{items:typeof conversation[];next_cursor:null})=>void
  vi.mocked(assistantApi.sessions).mockReturnValueOnce(new Promise(resolve=>{finishHistory=resolve}))
  const stale=store.history()
  store.sessions=[conversation];store.draftFor('s').text='私有草稿'
  vi.spyOn(assistantApi,'snapshot').mockResolvedValue(snapshot('私有正文400',3))
  vi.spyOn(assistantApi,'events').mockResolvedValue(response('event: run.unavailable\ndata: {"run_id":"r","code":"sources_unavailable"}\n\n'))
  await store.submit(input)
  finishHistory({items:[conversation],next_cursor:null});await stale
  expect(store.messagesBySession.s).toBeUndefined();expect(store.drafts.s).toBeUndefined();expect(store.runs.s).toBeUndefined()
  expect(store.sessions).toEqual([]);expect(store.selectedId).toBe('');expect(store.visibilityGeneration).toBe(1)
  expect(store.error).toContain('权限已改变');expect(assistantApi.send).toHaveBeenCalledTimes(1)
})

it('account change stops subscription and discards a late snapshot before it can restore private content',async()=>{
  const store=setup()
  let finish!:(v:Snapshot)=>void
  vi.spyOn(assistantApi,'snapshot').mockReturnValueOnce(new Promise(resolve=>{finish=resolve}))
  const running=store.submit(input);await flushPromises()
  store.bindIdentity('bob:2');finish(snapshot('旧身份私有正文',3));await running
  expect(store.messagesBySession).toEqual({});expect(store.sessions).toEqual([]);expect(assistantApi.send).toHaveBeenCalledTimes(1)
})

it('does not request V3 when the worker capability is unavailable',async()=>{
  const store=setup();store.capabilities={run_protocols:[1,2],durable_runs:{available:false,reason:'disabled'}} as Capabilities
  vi.mocked(assistantApi.send).mockResolvedValue(response(event('run.completed',1)))
  vi.spyOn(assistantApi,'messages').mockResolvedValue({session:conversation,items:[],next_cursor:null,active_run_id:null})
  await store.submit(input)
  expect(vi.mocked(assistantApi.send).mock.calls[0]?.[1].protocol_version).toBe(2)
})

it('known native authorization change clears cached private evidence immediately and preserves context-free text',()=>{
  const store=setup()
  store.messagesBySession.s=snapshot('私有400',3).items
  store.messagesBySession.s[1]!.content_parts.push({type:'business_snapshot',result:{}})
  store.messagesBySession.public=snapshot('普通JavaScript说明',3).items.map(m=>({...m,run_id:'public-run'}))
  store.invalidateAuthorization()
  expect(store.messagesBySession.s).toBeUndefined();expect(store.sessions).toEqual([])
  expect(store.messagesBySession.public?.[1]?.content_parts[0]?.text).toBe('普通JavaScript说明')
  expect(store.visibilityGeneration).toBeGreaterThan(0);expect(assistantApi.send).not.toHaveBeenCalled()
})

it('acknowledges only actually applied events and keeps a gap snapshot out of the old subscription receipt',async()=>{
 const store=setup();store.capabilities!.operational_metrics={available:true,reason:null}
 vi.spyOn(assistantApi,'receipt').mockResolvedValue({applied_seq:7})
 vi.spyOn(assistantApi,'snapshot').mockResolvedValueOnce(snapshot('一',3)).mockResolvedValueOnce(snapshot('一二补齐',6)).mockResolvedValueOnce(snapshot('一二补齐',7,'completed'))
 vi.spyOn(assistantApi,'events').mockResolvedValueOnce(response(event('response.delta',4,{channel:'answer',part_id:'chat-0:text',text:'二'}),event('response.delta',6,{channel:'answer',part_id:'chat-0:text',text:'跳过一段'})))
   .mockResolvedValueOnce(response(event('run.completed',7)))
 await store.submit(input);await flushPromises()
 const requests=vi.mocked(assistantApi.events).mock.calls,receipts=vi.mocked(assistantApi.receipt).mock.calls
 expect(receipts.map(c=>c[2])).toEqual([4,7]);expect(receipts.map(c=>c[1])).toEqual(requests.map(c=>c[3]))
 expect(assistantApi.send).toHaveBeenCalledTimes(1)
})

it('shows an immediate stop request without inferring a terminal state or sending duplicate cancellation',async()=>{
 const store=setup();let finish!:(value:{state:string})=>void
 vi.spyOn(assistantApi,'cancel').mockReturnValue(new Promise(resolve=>{finish=resolve}))
 store.runs.s={runId:'r',sessionId:'s',state:'answering',payload:{...input,protocol_version:2,client_request_id:'same-request'},lastSeq:3,error:'',controller:new AbortController(),omittedTurns:0}
 const stopped=store.stop();expect(store.currentRun?.stopping).toBe(true);expect(store.currentRun?.error).toBe('正在停止…')
 expect(store.currentRun?.state).toBe('answering');await store.stop();expect(assistantApi.cancel).toHaveBeenCalledTimes(1)
 finish({state:'cancelled'});await stopped;expect(store.currentRun?.stopping).toBe(false);expect(store.currentRun?.state).toBe('answering')
})
