import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import type { Action, Data, MaterialRecord } from '@/api/indonesiaMaterials'
import { copyDraft, draftKind, draftIdentity, newDraftId, type DraftKind, type DraftId } from './draftPersistence'
import { useMaterials } from './workspace'

interface DraftEditor {
  id: DraftKind
  multiple?: boolean
  capture: () => Data | null
  restore: (state: Data) => void | Promise<void>
  reset: () => void
  allowed?: (state: Data) => boolean
}
const fileIds = new WeakMap<File, number>()
let nextFileId = 0
const fingerprint = (value: unknown) => JSON.stringify(value, (_key, entry) => {
  if (!(entry instanceof File)) return entry
  if (!fileIds.has(entry)) fileIds.set(entry, ++nextFileId)
  return { name: entry.name, size: entry.size, type: entry.type, lastModified: entry.lastModified, fileId: fileIds.get(entry) }
})

/** The component owns live inputs; IndexedDB owns recovery across page lifetimes. */
export function useMaterialDraft(value: () => unknown, editor: DraftEditor) {
  const ws = useMaterials(), epoch = ws.scopeEpoch
  const activeId = ref<DraftId>(editor.id), switching = ref(false)
  const baseline = ref(fingerprint(value())), durable = ref(''), opened = ref(false)
  let paused = false, submitting = false, alive = true
  const permitted = (data: Data) => editor.allowed ? editor.allowed(data) : ws.canWrite
  const state = computed(() => { const data = editor.capture(); return data && permitted(data) ? data : null })
  const signature = computed(() => fingerprint(state.value))
  const recoveryWaiting = computed(() => !!ws.localDrafts.bucket.drafts[activeId.value] && !opened.value)
  const dirty = computed(() => value() != null && fingerprint(value()) !== baseline.value)
  const unregister = ws.registerDraft(() => !!state.value && signature.value !== durable.value)
  async function persist() {
    const snapshot = state.value, stamp = signature.value
    let id = activeId.value
    if (!alive || paused || epoch !== ws.scopeEpoch || !ws.localDrafts.ready || !snapshot || !permitted(snapshot) || ws.pending) return false
    if (recoveryWaiting.value) { ws.error = '此处已有本机草稿，请继续填写原草稿，或新建另一份表单，原内容仍保留。'; return false }
    if (editor.multiple && id === editor.id && !opened.value) { activeId.value = id = newDraftId(editor.id); ws.localDrafts.adopt(id) }
    opened.value = true
    const success = await ws.localDrafts.save(id, snapshot)
    if (success && alive && epoch === ws.scopeEpoch && activeId.value === id) durable.value = stamp
    return success
  }
  watch([signature, activeId], () => { if (!paused) void persist() }, { flush: 'post' })
  const accept = (revision?: string) => { baseline.value = fingerprint(value()); if (revision !== undefined) ws.localDrafts.adopt(activeId.value, revision) }
  const safelySaved = () => {
    if (state.value && signature.value !== durable.value) { ws.error = '当前输入尚未完成自动保存，请保留表单，待保存完成后再切换；如提示存储异常，请先核对。'; return false }
    return true
  }
  const permitDiscard = () => safelySaved() && (editor.multiple || !dirty.value || window.confirm('当前填写内容尚未正式提交。关闭或切换分类后，本机草稿仍保留，确定继续吗？'))
  const reset = (id?: DraftId) => { if (id && id !== activeId.value) return; paused = true; opened.value = false; editor.reset(); baseline.value = fingerprint(value()); durable.value = ''; void nextTick(() => { paused = false }) }
  const current = () => alive && epoch === ws.scopeEpoch
  async function recover(saved: Data, revision: string, id: DraftId, preserved = false) {
    if (!current() || draftKind(id) !== editor.id) return false
    if (!permitted(saved)) throw new Error('当前账号没有恢复此类表单的权限，草稿仍保留。')
    if (editor.multiple && id !== activeId.value) {
      if (!preserved && state.value && !await persist()) return false
      await ws.localDrafts.flush()
      if (!current()) return false
    } else if (state.value && signature.value !== fingerprint(saved) && !permitDiscard()) return false
    paused = true
    try {
      await editor.restore(copyDraft(saved))
      if (!current()) return false
      activeId.value = id
      await nextTick()
      accept(revision); opened.value = true; durable.value = signature.value
      return true
    } finally { paused = false }
  }
  const unregisterOwner = ws.registerDraftOwner(editor.id, {
    reset, flush: persist,
    async restore(saved, revision, id) {
      if (switching.value || submitting) return false
      switching.value = true
      try { return await recover(saved, revision, id) }
      finally { switching.value = false }
    },
  })
  /** Switch records only after the old record is durable; a target draft is resumed, never replaced. */
  async function openRecord(id: DraftId, initialize: () => void, editable = ws.canWrite) {
    if (!editor.multiple || draftKind(id) !== editor.id || switching.value || submitting || ws.locked || !current()) return false
    switching.value = true
    try {
      if (state.value) {
        await nextTick()
        if (!await persist()) return false
        await ws.localDrafts.flush()
      } else if (ws.localDrafts.saving) await ws.localDrafts.flush()
      if (!current() || ws.locked) return false
      const matches = Object.values(ws.localDrafts.bucket.drafts).filter(item => item && draftKind(item.id) === editor.id && draftIdentity(editor.id, item.state) === id)
      const saved = matches.find(item => item!.id === activeId.value) ?? ws.localDrafts.bucket.drafts[id] ?? matches.sort((left, right) => right!.savedAt.localeCompare(left!.savedAt))[0]
      if (saved && editable) return await recover(saved.state, saved.revision, saved.id, true)
      paused = true
      activeId.value = id; opened.value = editable; durable.value = ''
      initialize()
      if (!current()) return false
      baseline.value = fingerprint(value())
      if (editable) ws.localDrafts.adopt(id)
      paused = false
      if (editable) void persist()
      return true
    } catch (cause) {
      if (current()) ws.error = cause instanceof Error ? cause.message : '记录草稿暂时无法读取，原内容仍保留。'
      return false
    } finally { paused = false; switching.value = false }
  }
  async function run(action: Action, data: Data, target?: MaterialRecord, committed?: () => void) {
    if (submitting || switching.value || ws.locked || epoch !== ws.scopeEpoch) return false
    submitting = true
    const owner = activeId.value
    try {
      await nextTick(); await ws.localDrafts.flush()
      if (epoch !== ws.scopeEpoch || !await persist()) return false
      if (epoch !== ws.scopeEpoch || ws.locked || activeId.value !== owner) return false
      paused = true
      return await ws.run(action, data, target, () => { if (activeId.value !== owner) return; committed?.(); baseline.value = fingerprint(value()); durable.value = signature.value }, owner)
    } finally { await nextTick(); paused = false; submitting = false }
  }
  onBeforeUnmount(() => { alive = false; unregister(); unregisterOwner() })
  return { accept, permitDiscard, openRecord, activeId, switching, run, recoveryWaiting }
}
