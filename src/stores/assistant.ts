import { computed, markRaw, ref, shallowRef } from 'vue'
import { defineStore } from 'pinia'
import { assistantApi, AssistantApiError, newRequestId } from '@/features/assistant/api'
import { parseSSE } from '@/features/assistant/stream'
import { activeStates, type Capabilities, type Conversation, type Draft, type LocalRun, type Message, type SendPayload, type Snapshot } from '@/features/assistant/types'
import type { EvidencePart } from '@/features/assistant/v2'
import { EventGapError, RunUnavailableError, readDurableEvents, subscriptionDelay } from '@/features/assistant/durableStream'

export const useAssistantStore = defineStore('assistant', () => {
  const capabilities = shallowRef<Capabilities | null>(null), sessions = ref<Conversation[]>([])
  const selectedId = ref(''), messagesBySession = ref<Record<string, Message[]>>({}), cursors = ref<Record<string, number | null>>({})
  const runs = ref<Record<string, LocalRun>>({}), error = ref(''), historyCursor = ref<string | null>(null)
  const loading = ref(false), creating = ref(false), historyBusy = ref(false), historyError = ref('')
  const drafts = ref<Record<string, Draft>>({})
  const historyQuery = ref(''), favoritesOnly = ref(false), identityGeneration = ref(0)
  const visibilityGeneration = ref(0)
  const historyAuthorizationChanged = '资料权限已更新，请重新打开对话以核对当前可读内容。'
  function draftFor(id = selectedId.value) { return drafts.value[id || 'new'] ||= { text: '', attachments: [], documents: [] } }
  let generation = 0, selection = 0, identity = ''
  let historyGeneration = 0, messageScopeGeneration = 0, appliedHistory = { query: '', favorites: false }
  const subscriptions = new Map<string, { controller: AbortController; promise: Promise<void> }>()
  const messages = computed(() => messagesBySession.value[selectedId.value] || [])
  const currentRun = computed(() => runs.value[selectedId.value])
  const busy = computed(() => !!currentRun.value && activeStates.includes(currentRun.value.state))
  const anyBusy = computed(() => Object.values(runs.value).some(r => activeStates.includes(r.state)))
  const currentSession = computed(() => sessions.value.find(s => s.id === selectedId.value))
  function bindIdentity(key: string) {
    if (key === identity) return
    identity = key; generation++; selection++
    historyGeneration++; historyBusy.value = false; historyError.value = ''
    identityGeneration.value = generation
    Object.values(drafts.value).forEach(d => d.attachments.forEach(a => URL.revokeObjectURL(a.url)))
    drafts.value = {}; historyQuery.value = ''; favoritesOnly.value = false
    Object.values(runs.value).forEach(r => r.controller.abort())
    subscriptions.clear()
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
    if (more && (historyBusy.value || !historyCursor.value)) return
    const g = generation
    const h = ++historyGeneration
    if (!more) { appliedHistory = { query: historyQuery.value, favorites: favoritesOnly.value }; historyCursor.value = null; sessions.value = [] }
    const filters = { ...appliedHistory }, cursor = more ? historyCursor.value || '' : ''
    historyBusy.value = true; historyError.value = ''
    try {
      const value = await assistantApi.sessions(cursor, filters.query, filters.favorites)
      if (g !== generation || h !== historyGeneration) return
      sessions.value = more ? [...sessions.value, ...value.items.filter(s => !sessions.value.some(v => v.id === s.id))] : value.items
      historyCursor.value = value.next_cursor
    } catch (e) {
      if (g === generation && h === historyGeneration) historyError.value = e instanceof TypeError
        ? '暂时无法读取历史，请检查网络后重试。' : String(e instanceof Error ? e.message : e)
    }
    finally { if (g === generation && h === historyGeneration) historyBusy.value = false }
  }
  async function newSession(migrateDraft = false) {
    if (creating.value) return
    const g = generation, view = ++selection
    creating.value = true
    try {
      const row = await assistantApi.create(newRequestId())
      if (g !== generation) return
      replaceSession(row); messagesBySession.value[row.id] = []
      if (migrateDraft && drafts.value.new) { drafts.value[row.id] = drafts.value.new; delete drafts.value.new }
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
      if (snapshot.protocol_version === 3) {
        run.payload.protocol_version = 3; run.lastSeq = snapshot.event_seq || 0
      }
    }
  }
  async function selectSession(id: string, older = false) {
    const g = generation, view = ++selection, scope = messageScopeGeneration
    if (!older) selectedId.value = id
    if (error.value === historyAuthorizationChanged) error.value = ''
    loading.value = true
    try {
      const result = await assistantApi.messages(id, older ? cursors.value[id] || 0 : 0)
      if (g !== generation || view !== selection || scope !== messageScopeGeneration) return
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
        const durable = result.active_run_protocol_version === 3
        runs.value[id] = { runId: result.active_run_id, sessionId: id, state: durable ? result.active_run_state || 'connecting' : 'interrupted', payload: {protocol_version: durable ? 3 : 2} as SendPayload, lastSeq: durable ? result.active_event_seq || 0 : 0, error: durable ? '' : '这是保存的生成进度，可查询最新结果。', controller: markRaw(new AbortController()), omittedTurns: 0 }
        if (durable) void followDurable(id)
      }
    } catch (e) { if (g === generation && view === selection && scope === messageScopeGeneration) error.value = String(e instanceof Error ? e.message : e) }
    finally { if (g === generation && view === selection && scope === messageScopeGeneration) loading.value = false }
  }
  async function recover(sid = selectedId.value) {
    const g = generation, run = runs.value[sid]
    if (!run) return
    if (run.payload.protocol_version === 3) {
      run.controller.abort(); run.controller = markRaw(new AbortController())
    }
    try {
      const snapshot = run.runId ? await assistantApi.snapshot(run.runId) : await assistantApi.lookup(sid, run.payload.client_request_id)
      if (g === generation && runs.value[sid] === run) {
        if (snapshot.protocol_version === 3 && snapshot.items.some(m => m.unavailable)) { clearPrivateSession(sid); return }
        applySnapshot(snapshot); run.error = activeStates.includes(snapshot.state) ? snapshot.protocol_version === 3 ? '' : '请求仍在处理中，可稍后查询。' : ''
        if (snapshot.protocol_version === 3 && activeStates.includes(snapshot.state)) void followDurable(sid)
      }
    } catch (e) { if (g === generation) { run.retryable = e instanceof AssistantApiError && e.status === 404; run.error = run.retryable ? '尚未找到已接收的请求。重试会保留原请求编号，避免重复生成。' : String(e instanceof Error ? e.message : e) } }
  }
  function clearPrivateSession(sid: string) {
    runs.value[sid]?.controller.abort()
    const draft = drafts.value[sid]
    draft?.attachments.forEach(a => URL.revokeObjectURL(a.url))
    delete drafts.value[sid]; delete messagesBySession.value[sid]; delete runs.value[sid]; delete cursors.value[sid]
    visibilityGeneration.value++; historyGeneration++; historyBusy.value = false
    historyQuery.value = ''; favoritesOnly.value = false
    sessions.value = sessions.value.filter(s => s.id !== sid)
    if (selectedId.value === sid) { selectedId.value = ''; selection++ }
    error.value = '登录或相关资料权限已改变，当前对话内容已清除，请重新选择可用资料。'
  }
  function invalidateAuthorization() {
    // A first/older history page may contain protected data not cached yet.
    // Fence its success, error and finally without cancelling ordinary runs.
    messageScopeGeneration++
    if (loading.value) { loading.value = false; error.value = historyAuthorizationChanged }
    const protectedMessage = (message: Message) => {
      if (message.help_citations?.length) return true
      return message.content_parts.some(part => {
        if (['document_ref','image_ref','business_snapshot','business_failure','source_dependencies'].includes(part.type)) return true
        if (part.type !== 'evidence') return false
        const sources = (part as unknown as EvidencePart).sources
        return !Array.isArray(sources) || sources.some(s => ['business','file','help'].includes(s.kind))
      })
    }
    const affected = new Set(Object.entries(messagesBySession.value).filter(([, rows]) => rows.some(protectedMessage)).map(([sid]) => sid))
    for (const [sid, run] of Object.entries(runs.value)) {
      if (run.payload.page_context || run.payload.document_ids?.length || run.payload.attachment_ids?.length) affected.add(sid)
    }
    for (const sid of affected) {
      if (runs.value[sid] && activeStates.includes(runs.value[sid].state)) void stop(sid)
      clearPrivateSession(sid)
    }
    // Titles and source drawers may also have been derived from old scope.
    visibilityGeneration.value++; historyGeneration++; historyBusy.value=false; sessions.value=[]
  }
  function followDurable(sid: string): Promise<void> {
    const own = runs.value[sid]
    if (!own?.runId) return Promise.resolve()
    const controller = own.controller, g = generation
    const existing = subscriptions.get(sid)
    if (existing?.controller === controller) return existing.promise
    const valid = () => g === generation && runs.value[sid] === own && own.controller === controller && !controller.signal.aborted
    const work = async () => {
      let failures = 0
      while (valid()) {
        const began = performance.now()
        try {
          if (!activeStates.includes(own.state)) {
            const snapshot = await assistantApi.snapshot(own.runId)
            if (!valid()) return
            if (snapshot.items.some(m => m.unavailable)) { clearPrivateSession(sid); return }
            applySnapshot(snapshot)
            if (activeStates.includes(own.state)) continue
            await history()
            return
          }
          const subscriberId = capabilities.value?.operational_metrics?.available ? newRequestId() : undefined
          const initialSeq = own.lastSeq
          const response = subscriberId ? await assistantApi.events(own.runId,own.lastSeq,controller.signal,subscriberId)
            : await assistantApi.events(own.runId, own.lastSeq, controller.signal)
          if (!valid()) { await response.body?.cancel(); return }
          own.subscriptionState = 'live'; own.error = own.stopping?'正在停止…':''; own.retryable = false
          let count = 0
          try { count = await readDurableEvents(response, () => own.lastSeq, (event, data) => {
            if (!valid()) return
            if (data.run_id !== own.runId) throw new EventGapError('运行标识不一致。')
            const answer = messagesBySession.value[sid]?.find(m => m.run_id === own.runId && m.role === 'assistant')
            if (!answer) throw new EventGapError('本地保存进度缺失。')
            own.lastSeq = Number(data.seq)
            if (event === 'response.delta') {
              const type = data.channel === 'reasoning' ? 'reasoning' : 'text', partId = String(data.part_id || '')
              const part = answer.content_parts.find(p => p.type === type && p.part_id === partId)
              if (part) part.text = (part.text || '') + String(data.text)
              else answer.content_parts.push({type, text:String(data.text), part_id:partId})
              own.state = type === 'reasoning' ? 'thinking' : 'answering'
            } else if (event === 'response.phase') own.state = data.phase as LocalRun['state']
            else if (event === 'help.citations') answer.help_citations = data.items as Message['help_citations']
            else if (event === 'evidence.updated') {
              const evidence = data.evidence as EvidencePart, old = answer.content_parts.find(p => p.type === 'evidence')
              if (evidence?.run_id === own.runId && evidence.schema_version === 2 && Number.isInteger(evidence.revision) && evidence.revision > Number(old?.revision ?? -1)) {
                answer.content_parts = answer.content_parts.filter(p => p.type !== 'evidence'); answer.content_parts.push({...evidence})
              }
            } else if (event === 'ui.actions') {
              answer.content_parts = answer.content_parts.filter(p => p.type !== 'actions'); answer.content_parts.push({type:'actions',schema_version:2,items:data.items})
            } else if (event === 'context.window') own.omittedTurns = Number(data.omitted_turns) || 0
            else if (/^run\.(completed|cancelled|interrupted|failed)$/.test(event)) {
              own.state = event.slice(4) as LocalRun['state']; own.error = String(data.message || ''); own.retryable = data.retryable === true
            }
            answer.status = own.state
          }, controller.signal) }
          finally {
            if (subscriberId && valid() && own.lastSeq > initialSeq) {
              // Receipt failure never admits/retries a run or blocks rendering.
              void assistantApi.receipt(own.runId,subscriberId,own.lastSeq,controller.signal).catch(()=>undefined)
            }
          }
          if (!valid()) return
          if (!activeStates.includes(own.state)) continue
          if (!count && performance.now() - began < 1000) throw new Error('订阅连接提前结束。')
          failures = 0
        } catch (e) {
          if (!valid()) return
          if (e instanceof RunUnavailableError || e instanceof AssistantApiError && [401,403,404,410].includes(e.status)) { clearPrivateSession(sid); return }
          if (e instanceof EventGapError || e instanceof AssistantApiError && e.code === 'event_cursor_ahead') {
            try {
              const snapshot = await assistantApi.snapshot(own.runId)
              if (!valid()) return
              if (snapshot.items.some(m => m.unavailable)) { clearPrivateSession(sid); return }
              applySnapshot(snapshot)
            } catch (readError) {
              if (readError instanceof AssistantApiError && [401,403,404,410].includes(readError.status)) { clearPrivateSession(sid); return }
            }
          }
          if (++failures > 5) {
            own.subscriptionState = 'disconnected'; own.retryable = false
            own.error = activeStates.includes(own.state) ? '暂时无法恢复订阅，后台状态待查询。已显示内容保留，请查询保存结果。' : '暂时无法读取完整保存结果，已显示内容保留，请查询保存结果。'
            return
          }
          own.subscriptionState = 'retrying'; own.error = '正在恢复连接，已生成内容会保留。'; own.retryable = false
          await subscriptionDelay(Math.min(400 * 2 ** (failures - 1), 4000), controller.signal)
        }
      }
    }
    const promise = work().finally(() => { if (subscriptions.get(sid)?.controller === controller) subscriptions.delete(sid) })
    subscriptions.set(sid, {controller, promise})
    return promise
  }
  async function submit(input: Omit<SendPayload, 'client_request_id'>, reuse?: SendPayload) {
    if (busy.value || creating.value) return
    const g = generation
    let sid = selectedId.value
    if (!sid) sid = await newSession(true) || ''
    if (!sid || g !== generation) return
    const payload: SendPayload = reuse || { ...input, protocol_version: capabilities.value?.durable_runs?.available && capabilities.value.run_protocols?.includes(3) ? 3 : input.protocol_version, client_request_id: newRequestId() }
    const run: LocalRun = { runId: '', sessionId: sid, state: 'connecting', payload, lastSeq: 0, error: '', controller: markRaw(new AbortController()), omittedTurns: 0 }
    runs.value[sid] = run
    // Use the reactive proxy consistently when checking ownership.
    const own = runs.value[sid]!
    const valid = () => g === generation && runs.value[sid] === own
    error.value = ''
    const list = messagesBySession.value[sid] ||= []
    const index = (list.at(-1)?.seq || 0) + 1
    const uid = `pending-${payload.client_request_id}`, aid = `answer-${payload.client_request_id}`
    list.push({ id: uid, run_id: '', seq: index, role: 'user', content_parts: [{ type: 'text', text: payload.text }, ...payload.attachment_ids.map(id => ({type: 'image_ref', attachment_id: id})), ...(payload.document_ids || []).map(id => ({type: 'document_ref', file_id: id})), ...(payload.relation ? [{type:'run_relation',...payload.relation}] : [])], status: 'completed', help_citations: [], context_descriptor: payload.page_context, created_at: Date.now()/1000 })
    list.push({ id: aid, run_id: '', seq: index+1, role: 'assistant', content_parts: [], status: 'connecting', help_citations: [], context_descriptor: payload.page_context, created_at: Date.now()/1000 })
    let queued: { channel: string; text: string; part_id?: string }[] = [], lastFlush = 0, ended = false
    function flush() {
      if (!valid()) { queued = []; return }
      const answer = messagesBySession.value[sid]?.find(m => m.id === aid)
      if (answer) for (const delta of queued) {
        const type = delta.channel === 'reasoning' ? 'reasoning' : 'text'
        const part = delta.part_id ? answer.content_parts.find(p => p.type === type && p.part_id === delta.part_id) : answer.content_parts.at(-1)
        if (part?.type === type && part.part_id === delta.part_id) part.text = (part.text || '') + delta.text
        else answer.content_parts.push({ type, text: delta.text, ...(delta.part_id ? {part_id: delta.part_id} : {}) })
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
        if (payload.protocol_version === 3) {
          const snapshot = await assistantApi.snapshot(own.runId)
          if (!valid()) return
          if (snapshot.items.some(m => m.unavailable)) { clearPrivateSession(sid); return }
          messagesBySession.value[sid] = messagesBySession.value[sid]!.filter(m => m.id !== uid && m.id !== aid)
          applySnapshot(snapshot)
          await followDurable(sid)
          return
        }
        messagesBySession.value[sid] = messagesBySession.value[sid]!.filter(m => m.id !== uid && m.id !== aid)
        await recover(sid); return
      }
      if (!response.body) throw new Error('未收到回答流。')
      for await (const frame of parseSSE(response.body)) {
        if (!valid() || ended) break
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
          queued.push({ channel: String(data.channel), text: String(data.text), part_id: typeof data.part_id === 'string' ? data.part_id : undefined })
          own.state = data.channel === 'reasoning' ? 'thinking' : 'answering'
          if (performance.now()-lastFlush >= 40) flush()
        } else if (frame.event === 'response.phase') own.state = data.phase as LocalRun['state']
        else if (frame.event === 'help.citations' && answer) answer.help_citations = data.items as Message['help_citations']
        else if (frame.event === 'evidence.updated' && answer) {
          flush()
          const evidence = data.evidence as EvidencePart
          const old = answer.content_parts.find(p => p.type === 'evidence')
          if (evidence?.run_id === own.runId && evidence.schema_version === 2 && Number.isInteger(evidence.revision) && evidence.revision > Number(old?.revision ?? -1)) {
            answer.content_parts = answer.content_parts.filter(p => p.type !== 'evidence')
            answer.content_parts.push({...evidence})
          }
        }
        else if (frame.event === 'ui.actions' && answer) {
          flush(); answer.content_parts = answer.content_parts.filter(p => p.type !== 'actions')
          answer.content_parts.push({type:'actions', schema_version:2, items:data.items})
        }
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
        if (payload.protocol_version === 3) {
          if (e instanceof AssistantApiError && [401,403,410].includes(e.status)) { clearPrivateSession(sid); return }
          try {
            // Admission transport may be lost after commit. Only query its
            // original key; never automatically repeat the POST.
            const snapshot = own.runId ? await assistantApi.snapshot(own.runId) : await assistantApi.lookup(sid, payload.client_request_id)
            if (!valid()) return
            if (snapshot.items.some(m => m.unavailable)) { clearPrivateSession(sid); return }
            messagesBySession.value[sid] = messagesBySession.value[sid]!.filter(m => m.id !== uid && m.id !== aid)
            applySnapshot(snapshot)
            await followDurable(sid)
            return
          } catch (readError) {
            if (!valid()) return
            if (readError instanceof AssistantApiError && [401,403,410].includes(readError.status)) { clearPrivateSession(sid); return }
            if (own.runId) {
              own.error = '请求已接收，暂时无法读取后台进度；请查询保存结果。'; own.retryable = false
              return
            }
          }
        }
        own.state = e instanceof AssistantApiError ? 'failed' : 'interrupted'
        own.error = e instanceof Error ? e.message : '连接中断，已保留内容。'
        own.retryable = e instanceof AssistantApiError ? e.retryable : true
        const answer = messagesBySession.value[sid]?.find(m => m.id === aid)
        if (answer) answer.status = own.state
      }
    }
  }
  async function selectSessionIfVisible(sid: string) { if (selectedId.value === sid) await selectSession(sid) }
  function invalidateRun(runId:string) {
    for (const [sid, rows] of Object.entries(messagesBySession.value)) if(rows.some(m=>m.run_id===runId)) clearPrivateSession(sid)
  }
  async function stop(sid = selectedId.value) {
    const g = generation, own = runs.value[sid]
    if (!own || own.stopping) return
    own.stopping=true;own.error='正在停止…';own.retryable=false
    try {
      if (!own.runId) {
        const snapshot = await assistantApi.lookup(sid, own.payload.client_request_id)
        if (g !== generation || runs.value[sid] !== own) return
        own.runId = snapshot.run_id
      }
      if (g !== generation || !own.runId) return
      const result = await assistantApi.cancel(own.runId)
      if (g === generation && runs.value[sid] === own) {
        own.error = '正在停止…'
        if (own.payload.protocol_version === 3 && !activeStates.includes(result.state as LocalRun['state'])) await recover(sid)
      }
    }
    catch (e) { if (g === generation) own.error = String(e instanceof Error ? e.message : e) }
    finally { if (g === generation && runs.value[sid] === own) own.stopping=false }
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
  return { capabilities, sessions, selectedId, messages, messagesBySession, cursors, currentRun, runs, busy, anyBusy, currentSession, error, loading, creating, historyCursor, historyBusy, historyError,
    drafts, draftFor, historyQuery, favoritesOnly, identityGeneration, visibilityGeneration, invalidateAuthorization, invalidateRun, bindIdentity, refreshCapabilities, history, newSession, selectSession, submit, stop, recover, remove, rename }
})
