import { computed, markRaw, ref, shallowRef } from 'vue'
import { defineStore } from 'pinia'
import { assistantApi, AssistantApiError, newRequestId } from '@/features/assistant/api'
import { parseSSE } from '@/features/assistant/stream'
import { activeStates, type Capabilities, type Conversation, type LocalRun, type Message, type SendPayload, type Snapshot } from '@/features/assistant/types'

export const useAssistantStore = defineStore('assistant', () => {
  const capabilities = shallowRef<Capabilities | null>(null), sessions = ref<Conversation[]>([])
  const selectedId = ref(''), messagesBySession = ref<Record<string, Message[]>>({}), cursors = ref<Record<string, number | null>>({})
  const runs = ref<Record<string, LocalRun>>({}), error = ref(''), historyCursor = ref<string | null>(null)
  const loading = ref(false), creating = ref(false)
  let generation = 0, selection = 0, identity = ''
  const messages = computed(() => messagesBySession.value[selectedId.value] || [])
  const currentRun = computed(() => runs.value[selectedId.value])
  const busy = computed(() => !!currentRun.value && activeStates.includes(currentRun.value.state))
  const anyBusy = computed(() => Object.values(runs.value).some(r => activeStates.includes(r.state)))
  const currentSession = computed(() => sessions.value.find(s => s.id === selectedId.value))
  function bindIdentity(key: string) {
    if (key === identity) return
    identity = key; generation++; selection++
    Object.values(runs.value).forEach(r => r.controller.abort())
    capabilities.value = null; sessions.value = []; selectedId.value = ''; messagesBySession.value = {}; runs.value = {}; cursors.value = {}
    error.value = ''; loading.value = false; creating.value = false; historyCursor.value = null
  }
  async function refreshCapabilities() {
    const g = generation
    try { const value = await assistantApi.capabilities(); if (g === generation) capabilities.value = value }
    catch (e) { if (g === generation) error.value = e instanceof Error ? e.message : '连接状态暂不可用。' }
  }
  function replaceSession(row: Conversation) {
    const at = sessions.value.findIndex(s => s.id === row.id)
    if (at >= 0) sessions.value[at] = row; else sessions.value.unshift(row)
  }
  async function history(more = false) {
    const g = generation
    try {
      const value = await assistantApi.sessions(more ? historyCursor.value || '' : '')
      if (g !== generation) return
      sessions.value = more ? [...sessions.value, ...value.items.filter(s => !sessions.value.some(v => v.id === s.id))] : value.items
      historyCursor.value = value.next_cursor
    } catch (e) { if (g === generation) error.value = String(e instanceof Error ? e.message : e) }
  }
  async function newSession() {
    if (creating.value) return
    const g = generation, view = ++selection
    creating.value = true
    try {
      const row = await assistantApi.create(newRequestId())
      if (g !== generation) return
      replaceSession(row); messagesBySession.value[row.id] = []
      if (view === selection) selectedId.value = row.id
      return row.id
    } catch (e) { if (g === generation) error.value = String(e instanceof Error ? e.message : e) }
    finally { if (g === generation) creating.value = false }
  }
  function applySnapshot(snapshot: Snapshot) {
    const sid = snapshot.session_id
    const current = messagesBySession.value[sid] || []
    messagesBySession.value[sid] = [...current.filter(m => m.run_id !== snapshot.run_id), ...snapshot.items].sort((a,b) => a.seq-b.seq)
    const run = runs.value[sid]
    if (run && (!run.runId || run.runId === snapshot.run_id)) {
      run.runId = snapshot.run_id; run.state = snapshot.state; run.omittedTurns = snapshot.context_window?.omitted_turns || 0
    }
  }
  async function selectSession(id: string, older = false) {
    const g = generation, view = ++selection
    if (!older) selectedId.value = id
    loading.value = true
    try {
      const result = await assistantApi.messages(id, older ? cursors.value[id] || 0 : 0)
      if (g !== generation || view !== selection) return
      const live = runs.value[id]
      // A live stream is authoritative for its own in-memory messages.
      const streaming = live && activeStates.includes(live.state)
      if (streaming && !live.runId && result.active_run_id) live.runId = result.active_run_id
      const liveItems = streaming ? (messagesBySession.value[id] || []).filter(m => m.run_id === live.runId || m.id.endsWith(live.payload.client_request_id)) : []
      const saved = liveItems.length ? result.items.filter(m => m.run_id !== live?.runId) : result.items
      const combined = older ? [...saved, ...(messagesBySession.value[id] || [])] : [...saved, ...liveItems]
      messagesBySession.value[id] = [...new Map(combined.map(m => [m.id, m])).values()].sort((a,b) => a.seq-b.seq)
      cursors.value[id] = result.next_cursor; replaceSession(result.session)
      if (result.active_run_id && !live) {
        runs.value[id] = { runId: result.active_run_id, sessionId: id, state: 'interrupted', payload: {} as SendPayload, lastSeq: 0, error: '这是保存的生成进度，可查询最新结果。', controller: markRaw(new AbortController()), omittedTurns: 0 }
      }
    } catch (e) { if (g === generation && view === selection) error.value = String(e instanceof Error ? e.message : e) }
    finally { if (g === generation && view === selection) loading.value = false }
  }
  async function recover(sid = selectedId.value) {
    const g = generation, run = runs.value[sid]
    if (!run) return
    try {
      const snapshot = run.runId ? await assistantApi.snapshot(run.runId) : await assistantApi.lookup(sid, run.payload.client_request_id)
      if (g === generation && runs.value[sid] === run) { applySnapshot(snapshot); run.error = activeStates.includes(snapshot.state) ? '请求仍在处理中，可稍后查询。' : '' }
    } catch (e) { if (g === generation) { run.retryable = e instanceof AssistantApiError && e.status === 404; run.error = run.retryable ? '尚未找到已接收的请求。重试会保留原请求编号，避免重复生成。' : String(e instanceof Error ? e.message : e) } }
  }
  async function submit(input: Omit<SendPayload, 'client_request_id'>, reuse?: SendPayload) {
    if (busy.value || creating.value) return
    const g = generation
    let sid = selectedId.value
    if (!sid) sid = await newSession() || ''
    if (!sid || g !== generation) return
    const payload = reuse || { ...input, client_request_id: newRequestId() }
    const run: LocalRun = { runId: '', sessionId: sid, state: 'connecting', payload, lastSeq: 0, error: '', controller: markRaw(new AbortController()), omittedTurns: 0 }
    runs.value[sid] = run
    // Use the reactive proxy consistently when checking ownership.
    const own = runs.value[sid]!
    const valid = () => g === generation && runs.value[sid] === own
    error.value = ''
    const list = messagesBySession.value[sid] ||= []
    const index = (list.at(-1)?.seq || 0) + 1
    const uid = `pending-${payload.client_request_id}`, aid = `answer-${payload.client_request_id}`
    list.push({ id: uid, run_id: '', seq: index, role: 'user', content_parts: [{ type: 'text', text: payload.text }], status: 'completed', help_citations: [], context_descriptor: payload.page_context, created_at: Date.now()/1000 })
    list.push({ id: aid, run_id: '', seq: index+1, role: 'assistant', content_parts: [], status: 'connecting', help_citations: [], context_descriptor: payload.page_context, created_at: Date.now()/1000 })
    let queued: { channel: string; text: string }[] = [], lastFlush = 0, ended = false
    function flush() {
      if (!valid()) { queued = []; return }
      const answer = messagesBySession.value[sid]?.find(m => m.id === aid)
      if (answer) for (const delta of queued) {
        const type = delta.channel === 'reasoning' ? 'reasoning' : 'text'
        const part = answer.content_parts.at(-1)
        if (part?.type === type) part.text = (part.text || '') + delta.text
        else answer.content_parts.push({ type, text: delta.text })
      }
      queued = []; lastFlush = performance.now()
    }
    try {
      const response = await assistantApi.send(sid, payload, own.controller.signal)
      if (!valid()) { await response.body?.cancel(); return }
      if (response.headers.get('content-type')?.includes('application/json')) {
        const reused = await response.json() as { run_id: string }
        if (!valid()) return
        own.runId = reused.run_id
        messagesBySession.value[sid] = messagesBySession.value[sid]!.filter(m => m.id !== uid && m.id !== aid)
        await recover(sid); return
      }
      if (!response.body) throw new Error('未收到回答流。')
      for await (const frame of parseSSE(response.body)) {
        if (!valid()) break
        const data = JSON.parse(frame.data) as Record<string, unknown>
        const seq = Number(data.seq)
        if (!Number.isInteger(seq) || seq <= own.lastSeq) continue
        if (own.runId && data.run_id !== own.runId) continue
        own.lastSeq = seq; own.runId = String(data.run_id)
        const answer = messagesBySession.value[sid]?.find(m => m.id === aid)
        const question = messagesBySession.value[sid]?.find(m => m.id === uid)
        if (answer) answer.run_id = own.runId
        if (question) question.run_id = own.runId
        if (frame.event === 'response.delta') {
          queued.push({ channel: String(data.channel), text: String(data.text) })
          own.state = data.channel === 'reasoning' ? 'thinking' : 'answering'
          if (performance.now()-lastFlush >= 40) flush()
        } else if (frame.event === 'response.phase') own.state = data.phase as LocalRun['state']
        else if (frame.event === 'help.citations' && answer) answer.help_citations = data.items as Message['help_citations']
        else if (frame.event === 'context.window') own.omittedTurns = Number(data.omitted_turns) || 0
        else if (/^run\.(completed|cancelled|interrupted|failed)$/.test(frame.event)) {
          flush(); ended = true; own.state = frame.event.slice(4) as LocalRun['state']
          own.error = String(data.message || (data.finish_reason === 'length' ? '回答达到模型输出预算，可能尚未完整。' : ''))
          own.retryable = data.retryable === true
        }
        if (answer) answer.status = own.state
      }
      flush()
      if (valid() && !ended) throw new Error('连接中断，已保留部分回答。请查询保存结果后决定是否重试。')
      if (valid()) { await selectSessionIfVisible(sid); await history() }
    } catch (e) {
      flush()
      if (valid()) {
        own.state = e instanceof AssistantApiError ? 'failed' : 'interrupted'
        own.error = e instanceof Error ? e.message : '连接中断，已保留内容。'
        own.retryable = e instanceof AssistantApiError ? e.retryable : true
        const answer = messagesBySession.value[sid]?.find(m => m.id === aid)
        if (answer) answer.status = own.state
      }
    }
  }
  async function selectSessionIfVisible(sid: string) { if (selectedId.value === sid) await selectSession(sid) }
  async function stop(sid = selectedId.value) {
    const g = generation, own = runs.value[sid]
    if (!own) return
    try {
      if (!own.runId) {
        const snapshot = await assistantApi.lookup(sid, own.payload.client_request_id)
        if (g !== generation || runs.value[sid] !== own) return
        own.runId = snapshot.run_id
      }
      if (g !== generation || !own.runId) return
      await assistantApi.cancel(own.runId); if (g === generation) own.error = '正在停止…'
    }
    catch (e) { if (g === generation) own.error = String(e instanceof Error ? e.message : e) }
  }
  async function remove(row: Conversation) {
    const g = generation
    const result = await assistantApi.remove(row.id)
    if (g !== generation) return
    delete messagesBySession.value[row.id]
    const r = runs.value[row.id]; r?.controller.abort(); delete runs.value[row.id]
    if (selectedId.value === row.id) { selectedId.value = ''; selection++ }
    if (result.deletion_state === 'pending') row.deletion_state = 'pending'
    else sessions.value = sessions.value.filter(s => s.id !== row.id)
  }
  async function rename(row: Conversation, title: string) {
    const g = generation, updated = await assistantApi.rename(row, title)
    if (g === generation) replaceSession(updated)
  }
  return { capabilities, sessions, selectedId, messages, messagesBySession, cursors, currentRun, runs, busy, anyBusy, currentSession, error, loading, creating, historyCursor,
    bindIdentity, refreshCapabilities, history, newSession, selectSession, submit, stop, recover, remove, rename }
})
