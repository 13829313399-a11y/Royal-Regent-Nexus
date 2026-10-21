import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import type { Action, Data, MaterialRecord } from '@/api/indonesiaMaterials'
import { copyDraft, type DraftKind } from './draftPersistence'
import { useMaterials } from './workspace'

interface DraftEditor {
  id: DraftKind
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
  const baseline = ref(fingerprint(value())), durable = ref(''), opened = ref(false)
  let paused = false, submitting = false, alive = true
  const permitted = (data: Data) => editor.allowed ? editor.allowed(data) : ws.canWrite
  const state = computed(() => { const data = editor.capture(); return data && permitted(data) ? data : null })
  const signature = computed(() => fingerprint(state.value))
  const recoveryWaiting = computed(() => !!ws.localDrafts.bucket.drafts[editor.id] && !opened.value)
  const dirty = computed(() => value() != null && fingerprint(value()) !== baseline.value)
  const unregister = ws.registerDraft(() => !!state.value && signature.value !== durable.value)
  async function persist() {
    const snapshot = state.value, stamp = signature.value
    if (!alive || paused || epoch !== ws.scopeEpoch || !ws.localDrafts.ready || !snapshot || !permitted(snapshot) || ws.pending) return false
    if (recoveryWaiting.value) { ws.error = '此处已有本机草稿，请先继续填写或明确新建替换，原内容仍保留。'; return false }
    opened.value = true
    const success = await ws.localDrafts.save(editor.id, snapshot)
    if (success && alive && epoch === ws.scopeEpoch) durable.value = stamp
    return success
  }
  watch(signature, () => { if (!paused) void persist() }, { flush: 'post' })
  const accept = (revision?: string) => { baseline.value = fingerprint(value()); if (revision !== undefined) ws.localDrafts.adopt(editor.id, revision) }
  const safelySaved = () => {
    if (state.value && signature.value !== durable.value) { ws.error = '当前输入尚未完成自动保存，请保留表单，待保存完成后再切换；如提示存储异常，请先核对。'; return false }
    return true
  }
  const permitDiscard = () => safelySaved() && (!dirty.value || window.confirm('当前填写内容尚未正式提交。关闭或切换分类后，本机草稿仍保留，确定继续吗？'))
  const beforeOpen = (editable = ws.canWrite) => {
    if (ws.busy || ws.pending || !ws.localDrafts.ready) return false
    if (!editable) return true
    if (!safelySaved()) return false
    if ((state.value || ws.localDrafts.bucket.drafts[editor.id]) && !window.confirm('此处已有填写草稿。打开另一份表单将覆盖这份本机草稿，确定放弃原填写内容并替换吗？')) return false
    ws.localDrafts.adopt(editor.id)
    opened.value = true
    return true
  }
  const reset = () => { paused = true; opened.value = false; editor.reset(); baseline.value = fingerprint(value()); durable.value = ''; void nextTick(() => { paused = false }) }
  const unregisterOwner = ws.registerDraftOwner(editor.id, {
    reset, flush: persist,
    async restore(saved, revision) {
      if (!permitted(saved)) throw new Error('当前账号没有恢复此类表单的权限，草稿仍保留。')
      if (state.value && signature.value !== fingerprint(saved) && !permitDiscard()) return false
      paused = true
      try {
        await editor.restore(copyDraft(saved))
        if (epoch !== ws.scopeEpoch || !alive) return false
        await nextTick()
        accept(revision); opened.value = true; durable.value = signature.value
        return true
      } finally { paused = false }
    },
  })
  async function run(action: Action, data: Data, target?: MaterialRecord, committed?: () => void) {
    if (submitting || ws.locked || epoch !== ws.scopeEpoch) return false
    submitting = true
    try {
      await nextTick(); await ws.localDrafts.flush()
      if (epoch !== ws.scopeEpoch || !await persist()) return false
      if (epoch !== ws.scopeEpoch || ws.locked) return false
      paused = true
      return await ws.run(action, data, target, () => { committed?.(); baseline.value = fingerprint(value()); durable.value = signature.value }, editor.id)
    } finally { await nextTick(); paused = false; submitting = false }
  }
  onBeforeUnmount(() => { alive = false; unregister(); unregisterOwner() })
  return { accept, permitDiscard, beforeOpen, run, recoveryWaiting }
}
