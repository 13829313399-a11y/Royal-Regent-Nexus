import { beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { useAssistantStore } from '@/stores/assistant'
import { assistantApi } from '../api'
import { renderMarkdown } from '../markdown'
import type { ContentPart, Conversation, SendPayload } from '../types'
import type { EvidencePart } from '../v2'

const fixtures = JSON.parse(readFileSync('backend/tests/fixtures/assistant_v2/app-streams.json', 'utf8')) as {cases: Array<{
  id: string; run_id: string; request: SendPayload; events: Array<Record<string, unknown>>;
  ignored_deliveries?: Array<{event: Record<string,unknown>}>;
  checkpoints?: Array<{after_seq: number; evidence_revision: number; source_ids: string[]}>;
  expected: {terminal_state: string; content_parts: ContentPart[]}
}>}
const session: Conversation = { id:'s',title:'fixture',revision:1,deletion_state:'active',created_at:1,updated_at:1 }
beforeEach(() => { vi.restoreAllMocks(); setActivePinia(createPinia()) })
it.each(fixtures.cases)('consumes handoff stream through the production store: $id', async sample => {
  const store=useAssistantStore();store.bindIdentity('synthetic:1');store.selectedId='s'
  let stream!: ReadableStreamDefaultController<Uint8Array>
  vi.spyOn(assistantApi,'send').mockResolvedValue(new Response(new ReadableStream({start(c){stream=c}}),{headers:{'Content-Type':'text/event-stream'}}))
  vi.spyOn(assistantApi,'messages').mockImplementation(async()=>({session,items:[...store.messages],next_cursor:null,active_run_id:null}))
  vi.spyOn(assistantApi,'sessions').mockResolvedValue({items:[session],next_cursor:null})
  const running=store.submit(sample.request)
  await flushPromises()
  for (const frame of sample.events) {
    stream.enqueue(new TextEncoder().encode(`event: ${frame.event}\ndata: ${JSON.stringify(frame)}\n\n`))
    await flushPromises()
    const checkpoint=sample.checkpoints?.find(c=>c.after_seq===frame.seq)
    if(checkpoint) {
      const evidence=store.messages.at(-1)?.content_parts.find(p=>p.type==='evidence') as unknown as EvidencePart
      expect(evidence.revision).toBe(checkpoint.evidence_revision)
      expect(evidence.sources.map(s=>s.source_id)).toEqual(checkpoint.source_ids)
    }
  }
  // Deliveries after a terminal event must never revive a finished run.
  for(const delivery of sample.ignored_deliveries || []) {
    try { stream.enqueue(new TextEncoder().encode(`event: ${delivery.event.event}\ndata: ${JSON.stringify(delivery.event)}\n\n`)) } catch { /* stream already consumed */ }
  }
  try {stream.close()} catch { /* closed */ }
  await running
  expect(store.currentRun?.state).toBe(sample.expected.terminal_state)
  const actual=store.messages.at(-1)!.content_parts
  for(const type of ['text','evidence']) expect(actual.filter(p=>p.type===type)).toEqual(sample.expected.content_parts.filter(p=>p.type===type))
  expect(actual.filter(p=>p.type==='evidence')).toHaveLength(sample.request.protocol_version === 2 ? 1 : 0)
})
it('keeps new/session/identity drafts separate and migrates first-upload text', async()=>{
  const store=useAssistantStore();store.bindIdentity('a:1');store.draftFor().text='未发送正文'
  vi.spyOn(assistantApi,'create').mockResolvedValue(session)
  await store.newSession(true)
  expect(store.draftFor().text).toBe('未发送正文')
  store.selectedId='b';store.draftFor().text='B draft';store.selectedId='s'
  expect(store.draftFor().text).toBe('未发送正文')
  store.bindIdentity('a:2');expect(store.draftFor().text).toBe('')
})
it('renders citations by part identity while leaving inline/fenced code literal',()=>{
  const sample=fixtures.cases.find(c=>c.id==='late-source-split-marker')!
  const evidence=sample.expected.content_parts.find(p=>p.type==='evidence') as unknown as EvidencePart
  const part=sample.expected.content_parts.find(p=>p.type==='text')!
  const html=renderMarkdown(part.text || '',evidence,String(part.part_id))
  expect((html.match(/data-yl-source=/g)||[])).toHaveLength(1)
  expect((html.match(/<code[^>]*>\[ref_1\]/g)||[])).toHaveLength(2)
})
