import { computed, reactive, ref } from 'vue'
import { defineStore } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { collaborationApi as api, type Capabilities, type Conversation, type Message, type MessagePayload, type MessagePage, type Draft, type Bootstrap, type SyncBatch, type Page, type MemberProfile, type Preferences, type Reference, type Attachment } from '@/api/collaboration'
import { getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'
import { consumeStream } from '@/features/collaboration/stream'
import { requestSurface, releaseSurface } from '@/features/collaboration/panelCoordinator'

interface Composer extends Draft { revision: number; savedRevision: number; error: string; saving: boolean; reference: Reference | null }
interface Pending { payload: MessagePayload; state: 'sending' | 'failed'; error: string; revision: number }

export const useMessagingStore = defineStore('messaging', () => {
  const auth = useAuthStore()
  const identityKey = computed(() => auth.currentUser ? `${auth.currentUser.id}:${auth.currentUser.identity?.employment_epoch ?? 1}` : '')
  const bound = ref(''), capabilities = ref<Capabilities | null>(null), conversations = ref<Conversation[]>([])
  const history = reactive<Record<string, Message[]>>({}), drafts = reactive<Record<string, Composer>>({}), pending = reactive<Record<string, Pending[]>>({})
  const hasMore = reactive<Record<string, boolean>>({}), loading = reactive<Record<string, boolean>>({})
  const selectedId = ref(''), opened = ref(false), unread = ref(0), cursor = ref(''), status = ref('正在连接'), error = ref('')
  const profile = ref<MemberProfile | null>(null), preferences = ref<Preferences | null>(null), nextConversationCursor = ref<string | null>(null)
  const ready = computed(() => Boolean(capabilities.value?.enabled && capabilities.value.eligible))
  const selected = computed(() => conversations.value.find(c => c.id === selectedId.value))
  const visibleMessages = computed(() => history[selectedId.value] ?? [])
  let controller = new AbortController(), streamController: AbortController | undefined
  let timer: ReturnType<typeof setTimeout> | undefined, networkVersion = 0
  let refreshVersion = 0, applying: Promise<void> = Promise.resolve()
  const cursorSeq = (value: string) => { try { return Number(JSON.parse(atob(value.replace(/-/g, '+').replace(/_/g, '/')))[3]) } catch { return 0 } }
  const draftTimers = new Map<string, ReturnType<typeof setTimeout>>()
  const draftFlights = new Map<string, Promise<void>>()
  const current = (key: string) => bound.value === key && identityKey.value === key && !controller.signal.aborted

  function stopNetwork() { networkVersion += 1; clearTimeout(timer); timer = undefined; streamController?.abort(); streamController = undefined }
  function bind(key: string) {
    if (bound.value === key) return
    stopNetwork(); refreshVersion++; controller.abort(); controller = new AbortController(); bound.value = key
    draftTimers.forEach(clearTimeout); draftTimers.clear(); draftFlights.clear()
    for (const record of [history, drafts, pending, hasMore, loading]) for (const id of Object.keys(record)) delete record[id]
    capabilities.value = null; conversations.value = []; selectedId.value = ''; opened.value = false; unread.value = 0; cursor.value = ''; profile.value = null; preferences.value = null; error.value = ''
    releaseSurface('messages')
  }
  async function refreshCapabilities() {
    const key = bound.value, version = ++refreshVersion
    if (!key) return
    try {
      const result = await api.get<Capabilities>('/capabilities', controller.signal)
      if (!current(key) || version !== refreshVersion) return
      capabilities.value = result
      if (!ready.value) { bind(''); return }
      if (cursor.value) {
        try {
          let batch: SyncBatch
          do {
            batch = await api.get<SyncBatch>('/sync', controller.signal, { cursor: cursor.value })
            if (!current(key) || version !== refreshVersion) return
            await applyBatch(batch)
          } while (batch.has_more)
          if (selectedId.value) {
            const conv = await api.get<Conversation>(`/conversations/${selectedId.value}`, controller.signal)
            if (!current(key) || version !== refreshVersion) return
            conversations.value = [conv, ...conversations.value.filter(c => c.id !== conv.id)]
            await loadMessages(conv.id)
          }
          return
        } catch (caught) {
          const code = (caught as { response?: { data?: { detail?: { code?: string } } } }).response?.data?.detail?.code
          if (code !== 'RESET_REQUIRED') throw caught
          if (!current(key) || version !== refreshVersion) return
          cursor.value = ''; for (const id of Object.keys(history)) delete history[id]
        }
      }
      const [boot, self] = await Promise.all([api.get<Bootstrap>('/bootstrap', controller.signal), api.get<MemberProfile>('/me/profile', controller.signal)])
      if (!current(key) || version !== refreshVersion || cursorSeq(boot.cursor) < cursorSeq(cursor.value)) return
      conversations.value = boot.conversations.items; nextConversationCursor.value = boot.conversations.next_cursor
      unread.value = boot.unread; preferences.value = boot.preferences; profile.value = self; cursor.value = boot.cursor; error.value = ''
      if (selectedId.value) await select(selectedId.value)
    } catch (caught) { if (current(key)) error.value = getApiErrorMessage(caught) }
  }
  function merge(items: Message[]) {
    for (const message of items) {
      if (message.client_message_id && message.sender_user_id === capabilities.value?.owner.user_id) pending[message.conversation_id] = (pending[message.conversation_id] ?? []).filter(entry => entry.payload.client_message_id !== message.client_message_id)
      const rows = history[message.conversation_id] ??= []
      const index = rows.findIndex(old => old.id === message.id || old.message_seq === message.message_seq)
      if (index < 0) rows.push(message)
      else if (rows[index]!.version <= message.version) rows[index] = message
      rows.sort((a, b) => a.message_seq - b.message_seq)
      if (message.retracted_at) for (const row of rows) if (row.reply_to_id === message.id) row.reply = { id: message.id, message_seq: message.message_seq, body: '消息已撤回', retracted: true }
    }
  }
  function applyBatch(batch: SyncBatch, notify = false): Promise<void> {
    const next = applying.catch(() => {}).then(() => applyOrderedBatch(batch, notify)); applying = next; return next
  }
  async function applyOrderedBatch(batch: SyncBatch, notify = false) {
    const key = bound.value
    if (`${batch.owner.user_id}:${batch.owner.employment_epoch}` !== key || !current(key)) throw new Error('身份已变化')
    if (cursorSeq(batch.cursor) < cursorSeq(cursor.value)) return
    // Hydrate dirty entities before advancing the applied cursor.
    if (batch.events.some(e => e.conversation_id)) {
      const page = await api.get<Page<Conversation>>('/conversations', controller.signal, { include_archived: true })
      if (!current(key)) throw new Error('身份已变化')
      conversations.value = [...page.items, ...conversations.value.filter(c => !page.items.some(x => x.id === c.id))]
      nextConversationCursor.value = page.next_cursor
      for (const cid of new Set(batch.events.map(e => e.conversation_id).filter((id): id is string => !!id && !page.items.some(c => c.id === id)))) {
        const conv = await api.get<Conversation>(`/conversations/${cid}`, controller.signal)
        if (!current(key)) throw new Error('身份已变化')
        conversations.value = [conv, ...conversations.value.filter(c => c.id !== cid)]
      }
    }
    if (batch.events.some(e => e.type === 'preferences.updated' || e.type === 'profile.changed')) {
      const [p, pref] = await Promise.all([api.get<MemberProfile>('/me/profile', controller.signal), api.get<Preferences>('/me/preferences', controller.signal)])
      if (!current(key)) throw new Error('身份已变化')
      profile.value = p; preferences.value = pref
    }
    for (const event of batch.events) {
      if (event.message) merge([event.message])
      if (event.type === 'draft.updated' && event.conversation_id) {
        const draft = drafts[event.conversation_id]
        if (draft && draft.revision === draft.savedRevision && !draft.saving) await loadDraft(event.conversation_id)
      }
      if (event.type.startsWith('appreciation.')) window.dispatchEvent(new Event('collaboration-appreciations-changed'))
    }
    if (!current(key)) throw new Error('身份已变化')
    if (cursorSeq(batch.cursor) < cursorSeq(cursor.value)) return
    unread.value = batch.unread; cursor.value = batch.cursor
    if (notify && !batch.has_more) for (const event of batch.events) {
      if ((event.type === 'message.created' && event.message?.sender_user_id !== capabilities.value?.owner.user_id && !event.message?.retracted_at) || (event.type === 'appreciation.created' && event.notify_receiver)) {
        window.dispatchEvent(new CustomEvent('collaboration-notification', { detail: { type: event.type, id: event.entity_id, conversation_id: event.conversation_id } }))
      }
    }
  }
  function resume() {
    stopNetwork()
    if (!ready.value || !cursor.value || document.hidden || navigator.onLine === false) { status.value = navigator.onLine === false ? '离线，消息待恢复' : '同步已暂停'; return }
    const key = bound.value, version = networkVersion
    streamController = new AbortController(); const signal = streamController.signal
    status.value = '已连接'
    let recovered = false
    void consumeStream(cursor.value, signal, async batch => { await applyBatch(batch, recovered); if (!batch.has_more) recovered = true }).catch(caught => {
      if (!current(key) || signal.aborted || version !== networkVersion) return
      if (String(caught).includes('401')) { stopNetwork(); status.value = '登录已失效'; return }
      if (String(caught).includes('reset')) { void refreshCapabilities().then(resume); return }
      status.value = '正在使用定时同步'
      const poll = async () => {
        if (!current(key) || version !== networkVersion || document.hidden || navigator.onLine === false) return
        try { let batch: SyncBatch; do { batch = await api.get<SyncBatch>('/sync', controller.signal, { cursor: cursor.value }); await applyBatch(batch, recovered) } while (batch.has_more && current(key)); recovered = true }
        catch (err) {
          if (current(key)) {
            if ((err as { response?: { data?: { detail?: { code?: string } } } }).response?.data?.detail?.code === 'RESET_REQUIRED') {
              await refreshCapabilities(); if (current(key) && version === networkVersion) resume(); return
            }
            error.value = getApiErrorMessage(err)
          }
        }
        if (current(key) && version === networkVersion) timer = setTimeout(() => void poll(), opened.value ? 3000 : 15000)
      }
      void poll()
    })
  }
  async function loadMessages(cid: string, older = false) {
    if (loading[cid]) return
    const key = bound.value; loading[cid] = true
    try {
      const loaded = history[cid] ?? []
      let gap: Message | undefined
      for (let i = loaded.length - 1; i > 0; i--) if (loaded[i]!.message_seq > loaded[i - 1]!.message_seq + 1) { gap = loaded[i]; break }
      const params = older && loaded.length ? { before_seq: (gap ?? loaded[0]!).message_seq } : {}
      const page = await api.get<MessagePage>(`/conversations/${cid}/messages`, controller.signal, params)
      if (!current(key)) return
      merge(page.items); updateHistoryAvailability(cid)
    } catch (caught) { if (current(key)) error.value = getApiErrorMessage(caught) }
    finally { if (current(key)) loading[cid] = false }
  }
  function updateHistoryAvailability(cid: string) {
    const rows = history[cid] ?? []
    hasMore[cid] = !!rows.length && (rows[0]!.message_seq > 1 || rows.some((row, i) => i > 0 && row.message_seq > rows[i - 1]!.message_seq + 1))
  }
  async function loadDraft(cid: string) {
    const key = bound.value, revision = drafts[cid]?.revision
    const result = await api.get<Draft>(`/conversations/${cid}/draft`, controller.signal)
    if (!current(key) || drafts[cid]?.revision !== revision) return
    drafts[cid] = { ...result, revision: 0, savedRevision: 0, error: '', saving: false, reference: null }
  }
  async function select(cid: string) {
    const key = bound.value
    selectedId.value = cid; error.value = ''
    if (!conversations.value.some(c => c.id === cid)) { try { const conv = await api.get<Conversation>(`/conversations/${cid}`, controller.signal); if (!current(key)) return; conversations.value.push(conv) } catch (caught) { if (current(key)) error.value = getApiErrorMessage(caught); return } }
    await Promise.all([loadMessages(cid), !drafts[cid] ? loadDraft(cid).catch(caught => { if (current(key)) error.value = getApiErrorMessage(caught) }) : Promise.resolve()])
    if (!current(key)) return
    drafts[cid] ??= { text: '', reply_to_id: null, attachment_ids: [], version: 0, revision: 0, savedRevision: 0, error: '', saving: false, reference: null }
  }
  async function openPeer(peer: string) {
    const key = bound.value
    if (!ready.value) return
    try {
      const conv = await api.post<Conversation>('/conversations/direct', { peer_user_id: peer }, controller.signal)
      if (!current(key)) return
      conversations.value = [conv, ...conversations.value.filter(c => c.id !== conv.id)]
      if (requestSurface('messages')) opened.value = true
      await select(conv.id)
      return conv.id
    } catch (caught) { if (current(key)) error.value = getApiErrorMessage(caught) }
  }
  function openPanel() { if (requestSurface('messages')) opened.value = true }
  function closePanel() { opened.value = false; releaseSurface('messages') }
  function edit(cid: string, patch: Partial<Pick<Composer, 'text' | 'reply_to_id' | 'attachment_ids' | 'reference'>>) {
    const draft = drafts[cid]; if (!draft) return
    Object.assign(draft, patch); draft.revision += 1
    clearTimeout(draftTimers.get(cid)); draftTimers.set(cid, setTimeout(() => void saveDraft(cid), 800))
  }
  function saveDraft(cid: string): Promise<void> {
    const existing = draftFlights.get(cid); if (existing) return existing
    const key = bound.value
    const flight = (async () => {
      const draft = drafts[cid]; if (!draft) return
      draft.saving = true
      while (current(key) && draft.savedRevision !== draft.revision) {
        const revision = draft.revision
        const saved = { text: draft.text, reply_to_id: draft.reply_to_id, attachment_ids: [...draft.attachment_ids] }
        try {
          const result = await api.patch<Draft>(`/conversations/${cid}/draft`, { expected_version: draft.version, ...saved }, controller.signal)
          if (!current(key)) return
          draft.version = result.version; draft.savedRevision = revision; draft.error = ''
        } catch (caught) {
          if (!current(key)) return
          draft.error = getApiErrorMessage(caught)
          // A dropped PATCH response may still have committed. Resolve its
          // version before freezing a message's draft CAS token.
          try {
            const cloud = await api.get<Draft>(`/conversations/${cid}/draft`, controller.signal)
            if (!current(key)) return
            if (cloud.text === saved.text && cloud.reply_to_id === saved.reply_to_id && JSON.stringify(cloud.attachment_ids) === JSON.stringify(saved.attachment_ids)) {
              draft.version = cloud.version; draft.savedRevision = revision; draft.error = ''; continue
            }
          } catch { /* Keep the original save error and all local input. */ }
          break
        }
      }
      if (current(key)) draft.saving = false
    })().finally(() => { if (current(key)) draftFlights.delete(cid) })
    draftFlights.set(cid, flight); return flight
  }
  async function keepLocalDraft(cid: string) {
    const key = bound.value, draft = drafts[cid]; if (!draft) return
    await draftFlights.get(cid)
    const cloud = await api.get<Draft>(`/conversations/${cid}/draft`, controller.signal)
    if (!current(key)) return
    draft.version = cloud.version; draft.revision += 1; await saveDraft(cid)
  }
  async function transmit(cid: string, entry: Pending) {
    const key = bound.value; entry.state = 'sending'; entry.error = ''
    try {
      const result = await api.post<Message>(`/conversations/${cid}/messages`, entry.payload, controller.signal)
      if (!current(key)) return
      merge([result]); pending[cid] = (pending[cid] ?? []).filter(p => p.payload.client_message_id !== entry.payload.client_message_id)
      const draft = drafts[cid]
      if (draft && draft.revision === entry.revision) {
        draft.text = ''; draft.reply_to_id = null; draft.attachment_ids = []; draft.reference = null; draft.revision += 1
        // Keep reconciliation dirty from the first await so a draft.updated
        // event cannot replace the composer with a stale cloud draft.
        draft.savedRevision = draft.revision - 1
        const revision = draft.revision
        try {
          const cloud = await api.get<Draft>(`/conversations/${cid}/draft`, controller.signal)
          if (current(key) && drafts[cid] === draft && draft.revision === revision) {
            draft.version = cloud.version
            if (cloud.text || cloud.attachment_ids.length || cloud.reply_to_id) {
              draft.error = '消息已发送，云端仍有另一份草稿，请选择采用云端或保留本机。'
              // Prevent a later draft event from silently restoring sent text.
              draft.savedRevision = revision - 1
            } else { draft.error = ''; draft.savedRevision = revision }
          }
        } catch { if (current(key) && drafts[cid] === draft && draft.revision === revision) { draft.error = '消息已发送，草稿状态待核对。'; draft.savedRevision = revision - 1 } }
      }
      // Server result is canonical; no optimistic decrement or delivery claim.
      const batch = await api.get<SyncBatch>('/sync', controller.signal, { cursor: cursor.value }); await applyBatch(batch)
    } catch (caught) { if (current(key)) { entry.state = 'failed'; entry.error = getApiErrorMessage(caught) } }
  }
  async function send(cid: string) {
    const draft = drafts[cid]; if (!draft || (!draft.text.trim() && !draft.attachment_ids.length && !draft.reference)) return
    if ((pending[cid] ?? []).some(entry => entry.revision === draft.revision)) return
    const key = bound.value, revision = draft.revision
    const payload: MessagePayload = { client_message_id: createRandomUuid(), kind: draft.reference ? 'business_reference' : draft.attachment_ids.length ? 'attachment' : 'text', body: draft.text, reply_to_id: draft.reply_to_id, attachment_ids: [...draft.attachment_ids], reference: draft.reference, draft_version: null }
    clearTimeout(draftTimers.get(cid)); await saveDraft(cid)
    if (!current(key)) return
    payload.draft_version = draft.revision === revision ? draft.version : null
    if ((pending[cid] ?? []).some(entry => entry.revision === revision)) return
    const entry: Pending = { payload, state: 'sending', error: '', revision }; (pending[cid] ??= []).push(entry)
    await transmit(cid, entry)
    if (!current(key)) return
  }
  async function markRead(cid: string, seq: number) {
    const key = bound.value
    try { const result = await api.post<Conversation>(`/conversations/${cid}/read`, { through_message_seq: seq }, controller.signal); if (current(key)) { conversations.value = conversations.value.map(c => c.id === cid ? result : c); const batch = await api.get<SyncBatch>('/sync', controller.signal, { cursor: cursor.value }); await applyBatch(batch) } }
    catch (caught) { if (current(key)) error.value = getApiErrorMessage(caught) }
  }
  async function retract(message: Message) { const key = bound.value; try { const result = await api.post<Message>(`/messages/${message.id}/retract`, {}, controller.signal); if (current(key)) merge([result]) } catch (caught) { if (current(key)) error.value = getApiErrorMessage(caught) } }
  async function locate(cid: string, seq: number) { const key = bound.value; const result = await api.get<MessagePage>(`/conversations/${cid}/messages`, controller.signal, { before_seq: seq + 1 }); if (current(key)) { merge(result.items); updateHistoryAvailability(cid) } }
  async function firstUnread(cid: string) { const key = bound.value, conv = conversations.value.find(c => c.id === cid); if (!conv) return; const result = await api.get<MessagePage>(`/conversations/${cid}/messages`, controller.signal, { after_seq: conv.last_read_seq }); if (current(key)) { merge(result.items); updateHistoryAvailability(cid) } }
  async function changeConversation(value: Conversation, patch: { mute_until?: string | null; pin_order?: number; archived?: boolean }) { const key = bound.value; const result = await api.patch<Conversation>(`/conversations/${value.id}/preferences`, { expected_version: value.version, mute_until: value.mute_until, pin_order: value.pin_order, archived: !!value.archived_at, ...patch }, controller.signal); if (current(key)) conversations.value = conversations.value.map(c => c.id === result.id ? result : c) }
  async function moreConversations() { const key = bound.value; if (!nextConversationCursor.value) return; const page = await api.get<Page<Conversation>>('/conversations', controller.signal, { cursor: nextConversationCursor.value, include_archived: true }); if (current(key)) { conversations.value.push(...page.items.filter(c => !conversations.value.some(x => x.id === c.id))); nextConversationCursor.value = page.next_cursor } }
  async function saveProfile(value: MemberProfile) { const key = bound.value; const { version, ...body } = value; const result = await api.patch<MemberProfile>('/me/profile', { ...body, expected_version: version }, controller.signal); if (current(key)) profile.value = result; return current(key) ? result : null }
  async function savePreferences(value: Preferences) { const key = bound.value; const { version, ...body } = value; const result = await api.patch<Preferences>('/me/preferences', { ...body, expected_version: version }, controller.signal); if (current(key)) preferences.value = result }
  async function upload(cid: string, file: File, clientId: string, progress: (n: number) => void): Promise<Attachment | null> { const key = bound.value; const result = await api.upload(cid, file, clientId, n => { if (current(key)) progress(n) }, controller.signal); if (!current(key)) return null; edit(cid, { attachment_ids: [...(drafts[cid]?.attachment_ids ?? []), result.id] }); return result }
  return { identityKey, bound, capabilities, ready, conversations, history, drafts, pending, hasMore, loading, selectedId, selected, visibleMessages, opened, unread, cursor, status, error, profile, preferences, nextConversationCursor,
    bind, refreshCapabilities, resume, stopNetwork, select, openPeer, openPanel, closePanel, loadMessages, loadDraft, edit, saveDraft, keepLocalDraft, send, transmit, markRead, retract, saveProfile, savePreferences, upload, applyBatch, locate, firstUnread, changeConversation, moreConversations }
})
