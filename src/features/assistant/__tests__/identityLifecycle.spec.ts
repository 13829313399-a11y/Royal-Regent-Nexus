import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAssistantStore } from '@/stores/assistant'
import { identityKey, eligible, pageContext } from '../context'
import { assistantApi } from '../api'
import type { AuthMeResponse } from '@/api/auth'
import type { Capabilities, SendPayload } from '../types'
const user = (id: string, epoch = 1) => ({ id, force_password_change:false, identity:{ employment_epoch:epoch } }) as AuthMeResponse
const cap = {enabled:true,configuration_status:'configured',schema_status:'ready',profiles:[]} as unknown as Capabilities
const input: Omit<SendPayload,'client_request_id'> = {text:'你好',attachment_ids:[],intent:'chat',profile_id:'default',thinking:'auto',web_search:'off',page_context:null}
beforeEach(() => { vi.restoreAllMocks(); setActivePinia(createPinia()) })
describe('identity and stream ownership', () => {
  it('freezes the actual full-page factory, including the fixed UV workspace', () => {
    expect(pageContext('injection-scheduling','group','huaxing')?.factory_id).toBe('huaxing')
    expect(pageContext('uv-live','huakang-b')?.factory_id).toBe('huakang-a')
    expect(pageContext('dashboard','group','forged')?.factory_id).toBe('group')
  })
  it('keeps same account/epoch through ordinary refresh but excludes public pages and forced change', () => {
    const store = useAssistantStore(); store.bindIdentity(identityKey(user('a'))); store.selectedId='keep'
    store.bindIdentity(identityKey({...user('a'), authorization_version:2})); expect(store.selectedId).toBe('keep')
    store.bindIdentity(identityKey(user('a',2))); expect(store.selectedId).toBe('')
    expect(eligible(user('supplier'),'carton-supplier')).toBe(true)
    expect(eligible(user('a'),'login')).toBe(false)
    expect(eligible({...user('a'),force_password_change:true},'dashboard')).toBe(false)
  })
  it('ignores late capability response after account switch', async () => {
    let resolve!: (value: Capabilities) => void
    vi.spyOn(assistantApi,'capabilities').mockImplementation(() => new Promise(r => { resolve=r }))
    const store=useAssistantStore(); store.bindIdentity('a:1'); const request=store.refreshCapabilities(); store.bindIdentity('b:1'); resolve(cap); await request
    expect(store.capabilities).toBeNull()
  })
  it('deduplicates event seq and does not let an old stream mutate another account', async () => {
    let stream!: ReadableStreamDefaultController<Uint8Array>
    const body=new ReadableStream<Uint8Array>({start(c){stream=c}})
    vi.spyOn(assistantApi,'send').mockResolvedValue(new Response(body,{headers:{'Content-Type':'text/event-stream'}}))
    const store=useAssistantStore(); store.bindIdentity('a:1'); store.selectedId='s1'; store.messagesBySession.s1=[]
    const running=store.submit(input); await Promise.resolve(); await Promise.resolve()
    const frame='event: response.delta\ndata: {"run_id":"r1","seq":1,"channel":"answer","text":"旧账号"}\n\n'
    stream.enqueue(new TextEncoder().encode(frame+frame))
    await new Promise(r=>setTimeout(r,10))
    expect(store.messages.at(-1)?.content_parts.map(p=>p.text).join('')).toBe('旧账号')
    store.bindIdentity('b:1'); stream.enqueue(new TextEncoder().encode('event: run.completed\ndata: {"run_id":"r1","seq":2}\n\n')); stream.close(); await running
    expect(store.messages).toEqual([]); expect(store.runs).toEqual({})
  })
  it('handles reused JSON using a snapshot without starting another provider request', async () => {
    vi.spyOn(assistantApi,'send').mockResolvedValue(Response.json({reused:true,run_id:'r1'}))
    vi.spyOn(assistantApi,'snapshot').mockResolvedValue({run_id:'r1',session_id:'s1',state:'completed',usage:null,error_code:null,context_window:{},items:[]})
    const store=useAssistantStore();store.bindIdentity('a:1');store.selectedId='s1'; await store.submit(input)
    expect(assistantApi.send).toHaveBeenCalledTimes(1);expect(assistantApi.snapshot).toHaveBeenCalledWith('r1');expect(store.currentRun?.state).toBe('completed')
  })
  it('looks up an early cancellation without replacing the stream message buffers', async () => {
    let stream!: ReadableStreamDefaultController<Uint8Array>
    const body=new ReadableStream<Uint8Array>({start(c){stream=c}})
    vi.spyOn(assistantApi,'send').mockResolvedValue(new Response(body,{headers:{'Content-Type':'text/event-stream'}}))
    vi.spyOn(assistantApi,'lookup').mockResolvedValue({run_id:'r1',session_id:'s1',state:'connecting',usage:null,error_code:null,context_window:{},items:[]})
    vi.spyOn(assistantApi,'cancel').mockResolvedValue({state:'connecting'})
    const store=useAssistantStore();store.bindIdentity('a:1');store.selectedId='s1'
    const running=store.submit(input);await Promise.resolve();await store.stop()
    expect(store.messages).toHaveLength(2)
    stream.enqueue(new TextEncoder().encode('event: response.delta\ndata: {"run_id":"r1","seq":1,"channel":"answer","text":"保存部分回答"}\n\n'))
    await new Promise(r=>setTimeout(r,10));expect(store.messages.at(-1)?.content_parts[0]?.text).toBe('保存部分回答')
    store.bindIdentity('');stream.close();await running
  })
})
