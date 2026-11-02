import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises } from '@vue/test-utils'
import { useAssistantStore } from '@/stores/assistant'
import { assistantApi } from '../api'
import type { Conversation, Message, MessagePage, SendPayload } from '../types'

const session = { id: 's', title: 'PRIVATE-OLD-TITLE', revision: 1, deletion_state: 'active', created_at: 1, updated_at: 1 }
const publicMessage: Message = {
  id: 'public', run_id: 'public-run', seq: 4, role: 'assistant', status: 'completed',
  content_parts: [{ type: 'text', text: 'Public closure explanation' }],
  help_citations: [], context_descriptor: null, created_at: 1,
}
const privateMessage: Message = {
  id: 'private', run_id: 'old-run', seq: 2, role: 'assistant', status: 'completed',
  content_parts: [{ type: 'text', text: 'PRIVATE-OLD-ORDER-400' },
    { type: 'business_snapshot', result: { contract_version: 3, tool_name: 'get_customer_orders', run_id: 'old-run' } }],
  help_citations: [], context_descriptor: null, created_at: 1,
}

function delayed<T>() {
  let resolve!: (value: T) => void, reject!: (reason: Error) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
function oldPage(): MessagePage {
  return { session, items: [privateMessage], next_cursor: 1, active_run_id: 'old-active-run' }
}
function setup() {
  const store = useAssistantStore()
  store.bindIdentity('alice:1')
  return store
}

beforeEach(() => { vi.restoreAllMocks(); setActivePinia(createPinia()) })
afterEach(() => useAssistantStore().bindIdentity(''))

it('discards an initially loading history response after a known same-identity authorization change', async () => {
  const store = setup(), pending = delayed<MessagePage>()
  vi.spyOn(assistantApi, 'messages').mockReturnValue(pending.promise)
  const send = vi.spyOn(assistantApi, 'send')
  const loading = store.selectSession('s')
  expect(store.loading).toBe(true)
  // Nothing protected is cached yet: invalidation must also fence this read.
  store.invalidateAuthorization()
  pending.resolve(oldPage())
  await loading
  expect(store.messagesBySession.s).toBeUndefined()
  expect(store.cursors.s).toBeUndefined()
  expect(store.runs.s).toBeUndefined()
  expect(store.sessions).toEqual([])
  expect(store.loading).toBe(false)
  expect(send).not.toHaveBeenCalled()
})

it('does not append an older private page to an otherwise public cached conversation after invalidation', async () => {
  const store = setup(), pending = delayed<MessagePage>()
  store.messagesBySession.s = [publicMessage]
  store.cursors.s = 3
  vi.spyOn(assistantApi, 'messages').mockReturnValue(pending.promise)
  const loading = store.selectSession('s', true)
  store.invalidateAuthorization()
  pending.resolve(oldPage())
  await loading
  expect(store.messagesBySession.s).toEqual([publicMessage])
  expect(store.cursors.s).toBe(3)
  expect(store.sessions).toEqual([])
  expect(store.runs.s).toBeUndefined()
})

it('settles the stale loader and ignores its error while a fresh authorized read remains authoritative', async () => {
  const store = setup(), old = delayed<MessagePage>(), current = delayed<MessagePage>()
  vi.spyOn(assistantApi, 'messages').mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise)
  const stale = store.selectSession('s')
  store.invalidateAuthorization()
  expect(store.loading).toBe(false)
  const fresh = store.selectSession('s')
  old.reject(new Error('PRIVATE-STALE-ERROR'))
  await stale
  expect(store.loading).toBe(true)
  expect(store.error).not.toContain('PRIVATE-STALE-ERROR')
  current.resolve({ session: { ...session, title: 'Current permitted conversation' }, items: [publicMessage], next_cursor: null, active_run_id: null })
  await fresh
  expect(store.messagesBySession.s).toEqual([publicMessage])
  expect(store.sessions[0]?.title).toBe('Current permitted conversation')
  expect(store.loading).toBe(false)
  expect(store.error).toBe('')
})

it('keeps a context-free ongoing conversation and draft when only authorization changes', () => {
  const store = setup(), controller = new AbortController()
  const payload: SendPayload = { client_request_id: 'same-free-chat', text: 'Explain closures', attachment_ids: [], intent: 'chat', profile_id: 'default', thinking: 'auto', web_search: 'off', page_context: null }
  store.selectedId = 's'
  store.messagesBySession.s = [publicMessage]
  store.drafts.s = { text: 'My unsent follow-up', attachments: [], documents: [] }
  store.runs.s = { runId: 'public-run', sessionId: 's', state: 'answering', payload, controller, error: '', omittedTurns: 0, lastSeq: 0 }
  const cancel = vi.spyOn(assistantApi, 'cancel')
  store.invalidateAuthorization()
  expect(controller.signal.aborted).toBe(false)
  expect(store.runs.s?.state).toBe('answering')
  expect(store.messagesBySession.s).toEqual([publicMessage])
  expect(store.drafts.s?.text).toBe('My unsent follow-up')
  expect(cancel).not.toHaveBeenCalled()
})

it('keeps a new context-free chat selected when authorization changes while session creation is pending', async () => {
  const store = setup(), creation = delayed<Conversation>(), transport = delayed<Response>()
  const conversation = { ...session, title: 'New public chat' }
  vi.spyOn(assistantApi, 'create').mockReturnValueOnce(creation.promise)
  const send = vi.spyOn(assistantApi, 'send').mockReturnValueOnce(transport.promise)
  vi.spyOn(assistantApi, 'messages').mockResolvedValue({ session: conversation, items: [publicMessage], next_cursor: null, active_run_id: null })
  vi.spyOn(assistantApi, 'sessions').mockResolvedValue({ items: [conversation], next_cursor: null })
  store.drafts.new = { text: 'Explain closures', attachments: [], documents: [] }
  const submission = store.submit({ protocol_version: 2, text: 'Explain closures', attachment_ids: [], intent: 'chat', profile_id: 'default', thinking: 'auto', web_search: 'off', page_context: null })
  expect(store.creating).toBe(true)
  store.invalidateAuthorization()
  creation.resolve(conversation)
  await flushPromises()
  const visibleWhileConnecting = store.selectedId, visibleBusy = store.busy
  transport.resolve(new Response('event: run.completed\ndata: {}\n\n', { headers: { 'Content-Type': 'text/event-stream' } }))
  await submission
  expect(visibleWhileConnecting).toBe('s')
  expect(visibleBusy).toBe(true)
  expect(store.selectedId).toBe('s')
  expect(store.drafts.s?.text).toBe('Explain closures')
  expect(send).toHaveBeenCalledTimes(1)
  expect(store.creating).toBe(false)
})
