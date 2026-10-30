<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, onBeforeRouteLeave } from 'vue-router'
import { FileText, Sheet, Upload, ArrowLeft, Download, Save, Users, Folder, FolderPlus } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import PageHeader from '@/components/common/PageHeader.vue'
import { getApiErrorMessage } from '@/lib/http'
import { isAxiosError } from 'axios'
import { registerFactoryChangeGuard } from '@/lib/factoryChangeGuard'
import { useAuthStore } from '@/stores/auth'
import { onlineDocuments as api, type OnlineDocument, type DocumentGrant, type DocumentFolder, type MoveDocuments, type CopyDocument } from '@/api/onlineDocuments'
import { downloadBlob, loadEditor, type EditorEvent, type EditorInstance } from './editor'
import DocumentManagement from './DocumentManagement.vue'
import TrashDocuments from './TrashDocuments.vue'
import { readRecent, recentKey, rememberDocument } from './recentDocuments'
import type { DocumentSort } from '@/api/onlineDocuments'

import { createRandomUuid } from '@/lib/randomUuid'

const props = defineProps<{ factoryId: string }>()
const auth = useAuthStore()
const docs = ref<OnlineDocument[]>([])
const selected = ref<OnlineDocument | null>(null)
const shared = ref<OnlineDocument | null>(null)
const managed = ref<OnlineDocument | null>(null)
const documentPending = ref(false)
const folderPending = ref(false)
const copyPending = ref(false)
const trashing = ref<OnlineDocument[] | null>(null)
const trashOrigin = ref('')
const managementPending = computed(() => documentPending.value || folderPending.value || copyPending.value || !!trashing.value)
const copying = ref<OnlineDocument | null>(null)
const copyTitle = ref('')
const copyError = ref('')
const copyRequest = ref<CopyDocument | null>(null)
const copyInput = ref<HTMLInputElement>()
const recycleBin = ref(false)
const folders = ref<DocumentFolder[]>([])
const folder = ref('')
const checked = ref<string[]>([])
const moveTarget = ref('')
const folderName = ref('')
const showNewFolder = ref(false)
const renamingFolder = ref<DocumentFolder | null>(null)
const folderRenameTitle = ref('')
const folderRenameInput = ref<HTMLInputElement>()
const folderUncertain = ref(false)
type FolderRequest = { kind: 'create'; payload: { id: string; name: string } } | { kind: 'move'; payload: MoveDocuments } | { kind: 'remove'; id: string } | { kind: 'rename'; id: string; name: string; expectedName: string; expectedVersion: number }
const folderRequest = ref<FolderRequest | null>(null)
const currentFolder = computed(() => folders.value.find(f => f.id === folder.value))
const createInFolder = computed(() => currentFolder.value?.id)
const renaming = ref<OnlineDocument | null>(null)
const renameTitle = ref('')
const renameError = ref('')
const renameInput = ref<HTMLInputElement>()
const title = ref('')
const error = ref('')
const notice = ref('')
const loading = ref(true)
const busy = ref(false)
const saving = ref(false)
const ready = ref(false)
const dirty = ref(false)
const editorSynced = ref(true)
const connected = ref(false)
const fileInput = ref<HTMLInputElement>()
const grants = ref<DocumentGrant[]>([])
const people = ref<Awaited<ReturnType<typeof api.recipients>>>([])
const person = ref('')
const grantAccess = ref<'view' | 'edit'>('view')
const peopleSearch = ref('')
const availablePeople = computed(() => people.value.filter(p => p.id !== auth.currentUser?.id && !grants.value.some(g => g.user_id === p.id) &&
  [p.display_name, p.organization, p.department].filter(Boolean).join(' ').toLocaleLowerCase().includes(peopleSearch.value.trim().toLocaleLowerCase())))
const search = ref('')
const sort = ref<DocumentSort>('updated')
const recentScope = computed(() => recentKey(auth.currentUser?.id ?? '', auth.currentUser?.identity?.employment_epoch ?? 1, props.factoryId))
const recent = ref(readRecent(recentScope.value))
const visibleDocs = computed(() => docs.value.filter(d => d.title.toLocaleLowerCase().includes(search.value.toLocaleLowerCase())))
const selectableDocs = computed(() => visibleDocs.value.filter(d => d.access === 'owner'))
const allChecked = computed(() => selectableDocs.value.length > 0 && selectableDocs.value.every(d => checked.value.includes(d.id)))
const canEdit = computed(() => selected.value?.access !== 'view')
const state = computed(() => !ready.value ? '正在连接编辑器…' : saving.value ? '正在保存到系统…' : dirty.value ? '有修改待存入系统' : '已保存到系统')
let editor: EditorInstance | undefined
let generation = 0
let changeCounter = 0
let disposed = false
let timer: ReturnType<typeof setInterval> | undefined
let savePromise: Promise<boolean> | undefined
let pollBusy = false
const removeFactoryGuard = registerFactoryChangeGuard(() => {
  if (managementPending.value) { error.value = '文档操作结果尚未确认，请先完成原操作'; return false }
  if (!selected.value) return true
  error.value = '请先保存并返回文档列表，再切换厂区'
  return false
})
const active = (value: number) => !disposed && value === generation
const message = (value: unknown) => getApiErrorMessage(value)

async function refresh() {
  const run = generation
  const filter = folder.value
  const order = sort.value
  loading.value = true; error.value = ''
  const bin = recycleBin.value
  try {
    const listing = bin ? api.trash(props.factoryId) : order !== 'updated' ? api.list(props.factoryId, filter || undefined, { sort: order, ...(order === 'recent' ? { recent_ids: recent.value.map(v => v.id).join(',') } : {}) }) : filter ? api.list(props.factoryId, filter) : api.list(props.factoryId)
    const [items, directories] = await Promise.all([listing, api.folders(props.factoryId)])
    if (active(run) && bin === recycleBin.value && filter === folder.value && order === sort.value) { docs.value = items; folders.value = directories; checked.value = []; connected.value = true }
  }
  catch (e) { if (active(run)) { error.value = message(e); connected.value = false } }
  finally { if (active(run)) loading.value = false }
}

function destroy() {
  generation++; editor?.destroyEditor(); editor = undefined
  ready.value = false; selected.value = null; dirty.value = false
  busy.value = false; saving.value = false; savePromise = undefined
  closeSharing(); notice.value = ''
  renaming.value = null; renameTitle.value = ''; renameError.value = ''
  managed.value = null; documentPending.value = false; folderPending.value = false
  folderRequest.value = null; folderUncertain.value = false; checked.value = []; showNewFolder.value = false; folderName.value = ''
  renamingFolder.value = null; copying.value = null; copyPending.value = false; copyRequest.value = null; copyError.value = ''
  trashing.value = null
}

function toggleChecked() {
  if (busy.value || loading.value || managementPending.value) return
  checked.value = allChecked.value ? [] : selectableDocs.value.map(d => d.id)
}
function startTrash(doc?: OnlineDocument) {
  if (busy.value || loading.value || managementPending.value || recycleBin.value) return
  const items = doc ? [doc] : selectableDocs.value.filter(d => checked.value.includes(d.id))
  if (!items.length || items.some(d => d.access !== 'owner')) return
  closeSharing(); managed.value = null; copying.value = null; renaming.value = null
  error.value = ''; notice.value = ''
  trashOrigin.value = doc ? `od-trash-${doc.id}` : 'od-trash-checked'
  trashing.value = items.map(d => ({ ...d }))
}
function trashed(doc: OnlineDocument) {
  if (doc.deleted_at) docs.value = docs.value.filter(d => d.id !== doc.id)
  else docs.value = docs.value.map(d => d.id === doc.id ? doc : d)
  checked.value = checked.value.filter(id => id !== doc.id)
}
async function closeTrash(count?: number) {
  trashing.value = null
  if (count !== undefined) notice.value = `已将 ${count} 份文档移入回收站，可在回收站恢复`
  await nextTick()
  const target = document.getElementById(trashOrigin.value) ?? document.getElementById('od-select-all')
  target?.focus()
}

async function switchFolder(value: string) {
  if (busy.value || loading.value || managementPending.value) return
  folder.value = value; checked.value = []; docs.value = []; closeSharing(); renaming.value = null; managed.value = null
  copying.value = null; renamingFolder.value = null
  await refresh()
}

async function changeSort(value: DocumentSort) {
  if (busy.value || loading.value || managementPending.value) return
  sort.value = value; copying.value = null; managed.value = null; renaming.value = null
  await refresh()
}

async function runFolderRequest() {
  const request = folderRequest.value
  if (!request || busy.value) return
  const run = generation
  busy.value = true; folderPending.value = true; error.value = ''; folderUncertain.value = false
  try {
    if (request.kind === 'create') await api.createFolder(props.factoryId, request.payload)
    else if (request.kind === 'move') await api.move(props.factoryId, request.payload)
    else if (request.kind === 'rename') await api.renameFolder(props.factoryId, request.id, request.name, request.expectedName, request.expectedVersion)
    else await api.removeFolder(props.factoryId, request.id)
    if (!active(run)) return
    folderRequest.value = null; folderPending.value = false
    notice.value = request.kind === 'create' ? '文件夹已创建，可以勾选文档移入' : request.kind === 'move' ? `已完成 ${request.payload.documents.length} 份文档的归类` : request.kind === 'rename' ? `文件夹已改名为「${request.name}」` : '空文件夹已删除'
    if (request.kind === 'rename') renamingFolder.value = null
    if (request.kind === 'create') { showNewFolder.value = false; folderName.value = ''; moveTarget.value = request.payload.id }
    if (request.kind === 'remove') folder.value = ''
    await refresh()
  } catch (e) {
    if (!active(run)) return
    const status = isAxiosError(e) ? e.response?.status : undefined
    const rejected = !!status && status >= 400 && status < 500 && status !== 408
    if (rejected) { folderRequest.value = null; folderPending.value = false }
    else folderUncertain.value = true
    error.value = (rejected ? '' : '归类操作结果尚未确认，请重试原操作。') + message(e)
  } finally { if (active(run)) busy.value = false }
}

function newFolder() {
  if (busy.value || managementPending.value || !folderName.value.trim()) return
  folderRequest.value = { kind: 'create', payload: { id: createRandomUuid(), name: folderName.value.trim() } }
  void runFolderRequest()
}

function moveChecked() {
  if (busy.value || managementPending.value || !checked.value.length) return
  const documents = docs.value.filter(d => checked.value.includes(d.id) && d.access === 'owner')
    .map(d => ({ id: d.id, expected_version: d.placement_version ?? 0 }))
  if (!documents.length) return
  folderRequest.value = { kind: 'move', payload: { request_id: createRandomUuid(), folder_id: moveTarget.value || null, documents } }
  void runFolderRequest()
}

function removeFolder() {
  if (busy.value || managementPending.value || !currentFolder.value || docs.value.length) return
  folderRequest.value = { kind: 'remove', id: currentFolder.value.id }
  void runFolderRequest()
}

async function startFolderRename() {
  if (busy.value || managementPending.value || !currentFolder.value) return
  renamingFolder.value = { ...currentFolder.value }; folderRenameTitle.value = currentFolder.value.name
  showNewFolder.value = false
  await nextTick(); folderRenameInput.value?.focus(); folderRenameInput.value?.select()
}
function saveFolderName() {
  if (busy.value || managementPending.value || !renamingFolder.value || !folderRenameTitle.value.trim()) return
  folderRequest.value = { kind: 'rename', id: renamingFolder.value.id, name: folderRenameTitle.value.trim(), expectedName: renamingFolder.value.name, expectedVersion: renamingFolder.value.version }
  void runFolderRequest()
}

async function startCopy(doc: OnlineDocument) {
  if (busy.value || managementPending.value || doc.access !== 'owner') return
  busy.value = true; error.value = ''; notice.value = ''; managed.value = null; renaming.value = null; closeSharing()
  const run = generation
  try {
    const current = await api.detail(props.factoryId, doc.id)
    if (!active(run)) return
    copying.value = { ...doc, ...current }; copyTitle.value = `${current.title.slice(0, 185)}-副本`; copyError.value = ''; copyRequest.value = null
    await nextTick(); if (active(run)) { copyInput.value?.focus(); copyInput.value?.select() }
  } catch (e) { if (active(run)) error.value = message(e) }
  finally { if (active(run)) busy.value = false }
}
async function copyDocument() {
  const doc = copying.value
  if (!doc || busy.value || !copyTitle.value.trim()) return
  const run = generation
  copyRequest.value ??= { request_id: createRandomUuid(), expected_revision: doc.revision, title: copyTitle.value.trim(), folder_id: doc.folder_id ?? null }
  busy.value = true; copyPending.value = true; copyError.value = ''
  try {
    const result = await api.copy(props.factoryId, doc.id, copyRequest.value)
    if (!active(run)) return
    copyPending.value = false; copyRequest.value = null; copying.value = null
    notice.value = result.deleted_at ? '副本已创建，之后已移入回收站，可在回收站查看' : `已创建「${result.title}.${result.format}」，仅自己可见`
    await refresh()
  } catch (e) {
    if (!active(run)) return
    const status = isAxiosError(e) ? e.response?.status : undefined
    const rejected = !!status && status >= 400 && status < 500 && status !== 408
    if (rejected) { copyRequest.value = null; copyPending.value = false }
    copyError.value = (rejected ? '' : '复制结果尚未确认，请重试原操作，不会重复创建。') + message(e)
  } finally { if (active(run)) busy.value = false }
}

async function open(doc: OnlineDocument) {
  if (busy.value || managementPending.value) return
  managed.value = null
  copying.value = null
  busy.value = true; error.value = ''; closeSharing(); renaming.value = null; notice.value = ''
  const run = ++generation
  try {
    const response = await api.editor(props.factoryId, doc.id)
    if (!active(run)) return
    selected.value = response.document; dirty.value = false; editorSynced.value = true; ready.value = false
    const sdk = await loadEditor(response.script_url)
    await nextTick()
    if (!active(run)) return
    editor = new sdk.DocEditor('online-document-editor', { ...response.config, events: {
      onDocumentReady: () => { if (active(run)) { ready.value = true; recent.value = rememberDocument(recentScope.value, doc.id, recent.value) } },
      onDocumentStateChange: (event: EditorEvent) => {
        if (!active(run)) return
        if (event.data === true) { changeCounter++; dirty.value = true; editorSynced.value = false }
        else if (event.data === false) editorSynced.value = true
      },
      onError: () => { if (active(run)) error.value = '编辑器连接或保存发生错误，请保留窗口并重试' },
      onMetaChange: () => { if (active(run)) void refreshEditorTitle(run, doc.id) },
      onRequestClose: () => { if (active(run)) void close() },
    } })
  } catch (e) { if (active(run)) { error.value = message(e); editor?.destroyEditor(); editor = undefined } }
  finally { if (active(run)) busy.value = false }
}

async function refreshEditorTitle(run: number, id: string) {
  try {
    const current = await api.detail(props.factoryId, id)
    if (active(run) && selected.value?.id === id && current.state_version >= selected.value.state_version) {
      selected.value.title = current.title; selected.value.state_version = current.state_version
    }
  } catch { /* Keep editing; the next save/detail read also refreshes metadata. */ }
}

async function create(format: 'docx' | 'xlsx') {
  if (busy.value || managementPending.value) return
  busy.value = true; error.value = ''
  const run = generation
  try { const doc = await api.create(props.factoryId, title.value, format, createInFolder.value); if (active(run)) { busy.value = false; await open(doc) } }
  catch (e) { if (active(run)) error.value = message(e) }
  finally { if (!disposed) busy.value = false }
}

async function upload(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]; input.value = ''
  if (!file || busy.value || managementPending.value) return
  if (!/\.(docx|xlsx)$/i.test(file.name) || file.size > 100 * 1024 * 1024) { error.value = '请选择 100 MB 以内的 DOCX 或 XLSX 文件'; return }
  busy.value = true; error.value = ''
  const run = generation
  try { const doc = await api.upload(props.factoryId, file, createInFolder.value); if (active(run)) { busy.value = false; await open(doc) } }
  catch (e) { if (active(run)) error.value = message(e) }
  finally { if (!disposed) busy.value = false }
}

async function performSave() {
  const doc = selected.value
  if (!doc || !canEdit.value) return true
  if (!ready.value) { error.value = '请等待编辑器连接完成后再保存'; return false }
  const run = generation
  saving.value = true; error.value = ''
  try {
    const syncDeadline = Date.now() + 30000
    while (!editorSynced.value) {
      if (!active(run)) return false
      if (Date.now() >= syncDeadline) throw new Error('编辑器仍在同步修改，请保持窗口打开，稍后重试')
      await new Promise(resolve => setTimeout(resolve, 100))
    }
    if (!active(run)) return false
    const changes = changeCounter
    const request = await api.save(props.factoryId, doc.id)
    const deadline = Date.now() + 85000
    do {
      if (!active(run)) return false
      const current = await api.detail(props.factoryId, doc.id)
      if (!active(run)) return false
      if (current.save_error) throw new Error(current.save_error)
      if (!request.request_id || current.saved_request === request.request_id) {
        selected.value = selected.value && selected.value.state_version > current.state_version ? { ...current, title: selected.value.title, state_version: selected.value.state_version } : current
        if (changeCounter === changes) dirty.value = false
        return true
      }
      await new Promise(resolve => setTimeout(resolve, 1000))
    } while (Date.now() < deadline)
    throw new Error('保存仍未确认，请保持窗口打开并重试')
  } catch (e) { if (active(run)) error.value = message(e); return false }
  finally { if (active(run)) saving.value = false }
}

function save() {
  if (!savePromise) {
    const pending = performSave().finally(() => { if (savePromise === pending) savePromise = undefined })
    savePromise = pending
  }
  return savePromise
}

async function close() {
  if (busy.value || managementPending.value) return false
  if (selected.value && canEdit.value && !ready.value && !dirty.value) {
    try { await api.releaseUnopened(props.factoryId, selected.value.id) } catch { /* Retain the server session on an uncertain result. */ }
  }
  if (selected.value && canEdit.value && ready.value && !(await save())) return false
  if (dirty.value) { error.value = '仍有新的修改待保存，请保存后再返回'; return false }
  destroy(); busy.value = false
  await refresh()
  return true
}

async function download(doc: OnlineDocument) {
  error.value = ''
  if (selected.value && canEdit.value && !(await save())) return
  const run = generation
  try { const blob = await api.download(props.factoryId, doc.id); if (active(run)) downloadBlob(blob, `${doc.title}.${doc.format}`) }
  catch (e) { if (active(run)) error.value = message(e) }
}

async function sharing(doc: OnlineDocument) {
  if (busy.value || managementPending.value) return
  managed.value = null
  busy.value = true; error.value = ''; notice.value = ''; closeSharing()
  renaming.value = null
  const run = generation
  try {
    const [current, recipients] = await Promise.all([api.detail(props.factoryId, doc.id), api.recipients(props.factoryId)])
    if (!active(run)) return
    shared.value = current; grants.value = (current.grants ?? []).map(g => ({ ...g })); people.value = recipients; person.value = ''
    grantAccess.value = 'view'
  } catch (e) { if (active(run)) error.value = message(e) }
  finally { if (active(run)) busy.value = false }
}

async function startRename(doc: OnlineDocument) {
  if (busy.value || managementPending.value || doc.access !== 'owner') return
  managed.value = null
  copying.value = null
  closeSharing(); notice.value = ''; error.value = ''; renameError.value = ''
  renaming.value = { ...doc }; renameTitle.value = doc.title
  const run = generation
  await nextTick()
  if (active(run)) { renameInput.value?.focus(); renameInput.value?.select() }
}

async function cancelRename() {
  if (busy.value) return
  const id = renaming.value?.id
  renaming.value = null; renameError.value = ''; renameTitle.value = ''
  await nextTick()
  if (id) document.getElementById(`od-rename-${id}`)?.focus()
}

async function saveName() {
  const doc = renaming.value
  if (!doc || busy.value) return
  if (!renameTitle.value.trim()) { renameError.value = '请输入文件名称'; return }
  const run = generation
  busy.value = true; renameError.value = ''
  try {
    const renamed = await api.rename(props.factoryId, doc.id, renameTitle.value.trim(), doc.title, doc.state_version)
    if (!active(run)) return
    docs.value = docs.value.map(d => d.id === renamed.id ? { ...d, ...renamed } : d)
    if (selected.value?.id === renamed.id && renamed.state_version >= selected.value.state_version) { selected.value.title = renamed.title; selected.value.state_version = renamed.state_version }
    if (renamed.title_sync_pending) { renaming.value = { ...doc, ...renamed }; renameTitle.value = renamed.title; renameError.value = renamed.operation_notice ?? '名称已保存，请重试同步名称' }
    else { renaming.value = null; renameTitle.value = ''; notice.value = `已重命名为「${renamed.title}.${renamed.format}」` }
  } catch (e) { if (active(run)) renameError.value = message(e) }
  finally { if (active(run)) busy.value = false }
}

function closeSharing() {
  shared.value = null; grants.value = []; people.value = []; person.value = ''; peopleSearch.value = ''
}

function addGrant() {
  if (busy.value || shared.value?.editing || grants.value.length >= 50) return
  const recipient = people.value.find(p => p.id === person.value)
  if (!recipient || grants.value.some(g => g.user_id === recipient.id)) return
  grants.value.push({ user_id: recipient.id, name: recipient.display_name, access: grantAccess.value, epoch: recipient.epoch }); person.value = ''
}

async function saveGrants() {
  if (!shared.value || busy.value || shared.value.editing) return
  busy.value = true; error.value = ''
  const run = generation
  try { await api.share(props.factoryId, shared.value.id, grants.value, shared.value.share_version ?? ''); if (active(run)) { closeSharing(); notice.value = '共享设置已保存'; await refresh() } }
  catch (e) { if (active(run)) error.value = message(e) }
  finally { if (active(run)) busy.value = false }
}

async function heartbeat() {
  if (!selected.value || pollBusy || saving.value) return
  pollBusy = true
  const run = generation
  try {
    const current = await api.detail(props.factoryId, selected.value.id)
    if (!active(run)) return
    if (current.save_error) error.value = current.save_error
    if (dirty.value && canEdit.value && ready.value) await save()
  } catch (e) {
    if (active(run)) {
      if (isAxiosError(e) && [401, 403, 404].includes(e.response?.status ?? 0)) destroy()
      error.value = '文档连接检查失败，请保持窗口打开。' + message(e)
    }
  } finally { pollBusy = false }
}

function beforeUnload(event: BeforeUnloadEvent) { if (dirty.value || saving.value || managementPending.value) { event.preventDefault(); event.returnValue = '' } }
async function manage(doc: OnlineDocument) {
  if (busy.value || managementPending.value || doc.access !== 'owner') return
  closeSharing(); renaming.value = null; managed.value = null
  const run = generation
  await nextTick(); if (active(run)) managed.value = { ...doc }
}
async function closeManagement() {
  if (managementPending.value) return
  const id = managed.value?.id; managed.value = null
  await nextTick(); if (id) document.getElementById(`od-manage-${id}`)?.focus()
}
async function managedChange(doc: OnlineDocument, text: string) {
  managed.value = null; documentPending.value = false; notice.value = text
  if (doc.deleted_at) recycleBin.value = true
  else if (recycleBin.value) recycleBin.value = false
  await refresh()
}
async function switchLibrary(bin: boolean) {
  if (managementPending.value || busy.value || loading.value) return
  managed.value = null; closeSharing(); renaming.value = null; docs.value = []; recycleBin.value = bin
  folder.value = ''; checked.value = []
  await refresh()
}
function sessionBoundary() { destroy(); docs.value = []; folders.value = []; folder.value = ''; shared.value = null; connected.value = false; recent.value = readRecent(recentScope.value) }
watch(search, () => { if (!managementPending.value) checked.value = [] })
watch([() => auth.currentUser?.id, () => auth.currentUser?.authorization_version, () => auth.currentUser?.identity?.employment_epoch], () => { sessionBoundary(); void refresh() })
onBeforeRouteLeave(async () => { if (managementPending.value) { error.value = '文档操作结果尚未确认，请先重试原操作'; return false }; if (!selected.value) return true; return close() })
onMounted(() => { void refresh(); timer = setInterval(() => void heartbeat(), 20000); window.addEventListener('beforeunload', beforeUnload); window.addEventListener('auth-session-boundary-changed', sessionBoundary) })
onBeforeUnmount(() => { disposed = true; destroy(); removeFactoryGuard(); if (timer) clearInterval(timer); window.removeEventListener('beforeunload', beforeUnload); window.removeEventListener('auth-session-boundary-changed', sessionBoundary) })
</script>

<template>
  <main class="od-workspace" :class="{ 'od-editing': selected }">
    <nav class="od-nav"><RouterLink :to="{ path: '/tools', query: { factory: factoryId } }"><ArrowLeft :size="15" />公共工具</RouterLink><span>{{ auth.currentUser?.display_name }}</span></nav>
    <div v-if="error" class="od-error" role="alert">{{ error }}</div>
    <div v-if="notice" class="od-notice" role="status">{{ notice }}</div>
    <div v-if="folderUncertain" class="od-notice"><span>请重试以确认原操作结果。</span><Button variant="outline" :disabled="busy" @click="runFolderRequest">重试归类操作</Button></div>
      <form v-if="renaming" class="od-sharing od-rename" aria-label="重命名文件" @submit.prevent="saveName" @keydown.esc.prevent="cancelRename">
        <div class="od-section-heading"><h2>重命名「{{ renaming.title }}」</h2></div>
        <label for="od-rename-title">文件名称</label>
        <div class="od-rename-input"><input id="od-rename-title" ref="renameInput" v-model="renameTitle" maxlength="190" :disabled="busy" :aria-invalid="!!renameError" :aria-describedby="renameError ? 'od-rename-error' : 'od-rename-help'" /><span>.{{ renaming.format }}</span></div>
        <p id="od-rename-help">只修改文件名称，文件内容和共享权限保持不变。</p>
        <p v-if="renameError" id="od-rename-error" class="od-rename-error" role="alert">{{ renameError }}</p>
        <div class="od-file-actions"><Button type="submit" :disabled="busy || !renameTitle.trim()">{{ busy ? '保存中…' : renaming.title_sync_pending ? '重试同步名称' : '保存名称' }}</Button><Button type="button" variant="outline" :disabled="busy" @click="cancelRename">取消</Button></div>
      </form>
    <template v-if="selected">
      <header class="od-editor-bar">
        <Button variant="outline" size="sm" :disabled="saving || busy" @click="close"><ArrowLeft :size="15" />文档列表</Button>
        <div class="od-editor-title"><strong :title="selected.title">{{ selected.title }}.{{ selected.format }}</strong><span role="status">{{ selected.access === 'view' ? '只读 · 已保存版本可下载' : state }}</span></div>
        <Button v-if="selected.access === 'owner'" :id="`od-rename-${selected.id}`" variant="ghost" size="sm" :disabled="busy || saving || !ready" @click="startRename(selected)">重命名</Button>
        <Button v-if="canEdit" size="sm" :disabled="!ready || saving" @click="save"><Save :size="15" />{{ saving ? '保存中…' : '保存到系统' }}</Button>
        <Button variant="outline" size="sm" :disabled="saving || !ready" @click="download(selected)"><Download :size="15" />下载</Button>
      </header>
      <div v-if="!ready" class="od-loading" role="status">正在连接文档编辑服务…</div>
      <div class="od-editor"><div id="online-document-editor" /></div>
    </template>
    <template v-else>
      <PageHeader title="在线文档" description="编辑 Word 和 Excel，支持表格公式；文件默认仅自己可见，可按同事设置只读或可编辑。">
        <template #actions><Button :disabled="busy || managementPending || !connected" @click="fileInput?.click()"><Upload :size="16" />上传文档</Button></template>
      </PageHeader>
      <input ref="fileInput" type="file" accept=".docx,.xlsx" class="sr-only" aria-label="选择 Word 或 Excel 文件" @change="upload" />
      <section v-if="!recycleBin" class="od-create" aria-label="新建文档">
        <label for="od-title">新建文档</label><input id="od-title" v-model="title" maxlength="190" placeholder="文档名称（选填）" />
        <Button variant="outline" :disabled="busy || managementPending || !connected" @click="create('docx')"><FileText :size="17" />Word 文档</Button>
        <Button variant="outline" :disabled="busy || managementPending || !connected" @click="create('xlsx')"><Sheet :size="17" />Excel 表格</Button>
        <span>支持 DOCX / XLSX，最大 100 MB</span>
      </section>
      <section v-if="shared" class="od-sharing" aria-label="共享设置">
        <div class="od-section-heading"><h2>共享「{{ shared.title }}」</h2><Button variant="ghost" size="sm" :disabled="busy" @click="closeSharing">关闭</Button></div>
        <p>只读：查看和下载；可编辑：修改内容并保存。仅拥有者能管理共享，保存设置后生效。</p>
        <div class="od-share-add">
          <label>查找同事<input v-model="peopleSearch" placeholder="姓名、组织或部门" :disabled="busy || shared.editing" @input="person = ''" /></label>
          <label>{{ factoryId === 'group' ? '公司同事' : '本厂同事' }}<select v-model="person" aria-label="选择共享同事" :disabled="busy || shared.editing"><option value="">选择同事</option><option v-for="p in availablePeople" :key="p.id" :value="p.id">{{ [p.display_name, p.organization, p.department].filter(Boolean).join(' · ') }}</option></select></label>
          <label>权限<select v-model="grantAccess" aria-label="新增共享权限" :disabled="busy || shared.editing"><option value="view">只读</option><option value="edit">可编辑</option></select></label>
          <Button variant="outline" :disabled="busy || !person || shared.editing || grants.length >= 50" @click="addGrant">添加</Button>
        </div>
        <p v-if="!availablePeople.length" class="od-share-hint">{{ peopleSearch ? '没有匹配的同事，请换个关键词。' : '暂无其他可添加的同事。' }}</p>
        <ul class="od-grants"><li v-for="g in grants" :key="g.user_id"><span>{{ g.name }}</span><label><span class="sr-only">{{ g.name }}的权限</span><select v-model="g.access" :disabled="busy || shared.editing"><option value="view">只读</option><option value="edit">可编辑</option></select></label><Button variant="ghost" size="sm" :aria-label="`移除${g.name}的共享`" :disabled="busy || shared.editing" @click="grants = grants.filter(item => item.user_id !== g.user_id)">移除</Button></li></ul>
        <p v-if="!grants.length">未选择共享同事；保存后仅自己可见。</p><p v-if="shared.editing" role="status">还有编辑窗口未关闭，请所有人保存并关闭后稍等约 10 秒，再重新打开共享设置。</p>
        <Button :disabled="busy || shared.editing" @click="saveGrants">保存共享设置</Button>
      </section>
      <form v-if="copying" class="od-sharing od-rename" aria-label="复制文档" @submit.prevent="copyDocument">
        <div class="od-section-heading"><h2>复制「{{ copying.title }}.{{ copying.format }}」</h2></div>
        <label for="od-copy-title">副本名称</label><div class="od-rename-input"><input id="od-copy-title" ref="copyInput" v-model="copyTitle" maxlength="190" :disabled="busy || copyPending" aria-describedby="od-copy-help" /><span>.{{ copying.format }}</span></div>
        <p id="od-copy-help">复制已保存的版本 {{ copying.revision }}，不包含编辑器中尚未保存的修改。副本仅自己可见，保留公式与保护设置，历史版本独立记录，副本位置：{{ folders.find(f => f.id === copying?.folder_id)?.name ?? '未分类' }}。</p>
        <p v-if="copyError" class="od-rename-error" role="alert">{{ copyError }}</p>
        <div class="od-file-actions"><Button type="submit" :disabled="busy || !copyTitle.trim()">{{ busy ? '复制中…' : copyPending ? '重试复制' : '创建副本' }}</Button><Button type="button" variant="outline" :disabled="busy || copyPending" @click="copying = null">取消</Button></div>
      </form>
      <DocumentManagement v-if="managed" :key="`${managed.id}:${managed.state_version}`" :factory-id="factoryId" :document="managed" @close="closeManagement" @changed="managedChange" @pending="documentPending = $event" @denied="managed = null; documentPending = false; refresh()" />
      <div class="od-library-tabs" role="group" aria-label="文档范围"><Button variant="ghost" :aria-pressed="!recycleBin" :disabled="busy || loading || managementPending" @click="switchLibrary(false)">文档</Button><Button variant="ghost" :aria-pressed="recycleBin" :disabled="busy || loading || managementPending" @click="switchLibrary(true)">回收站</Button></div>
      <div class="od-browser" :class="{ 'od-browser-bin': recycleBin }">
      <aside v-if="!recycleBin" class="od-folders" aria-label="我的文件夹">
        <div class="od-folder-heading"><strong><Folder :size="18" aria-hidden="true" />我的文件夹</strong><Button variant="ghost" size="icon-sm" aria-label="新建文件夹" title="新建文件夹" :disabled="busy || managementPending || !connected" @click="showNewFolder = !showNewFolder"><FolderPlus :size="16" /><span class="sr-only">新建文件夹</span></Button></div>
        <p>文件夹仅自己可见，文档按各自权限共享。</p>
        <form v-if="showNewFolder" class="od-folder-form" aria-label="新建文件夹" @submit.prevent="newFolder">
          <label for="od-folder-name">文件夹名称</label><input id="od-folder-name" v-model="folderName" maxlength="100" placeholder="例如：成品进出、每月报表" :disabled="busy || managementPending" />
          <Button type="submit" :disabled="busy || managementPending || !folderName.trim()">创建文件夹</Button><Button type="button" variant="ghost" :disabled="busy || managementPending" @click="showNewFolder = false">取消</Button>
        </form>
        <form v-if="renamingFolder" class="od-folder-form" aria-label="重命名文件夹" @submit.prevent="saveFolderName">
          <label for="od-folder-rename">新文件夹名称</label><input id="od-folder-rename" ref="folderRenameInput" v-model="folderRenameTitle" maxlength="100" :disabled="busy || managementPending" />
          <Button type="submit" :disabled="busy || managementPending || !folderRenameTitle.trim()">保存文件夹名称</Button><Button type="button" variant="ghost" :disabled="busy || managementPending" @click="renamingFolder = null">取消</Button>
        </form>
        <nav class="od-folder-navigation" aria-label="文件夹导航">
          <Button variant="ghost" class="od-folder-link" :aria-current="folder === '' ? 'page' : undefined" :disabled="busy || loading || managementPending" @click="switchFolder('')"><FileText :size="16" aria-hidden="true" /><span>全部文档（含共享）</span></Button>
          <Button variant="ghost" class="od-folder-link" :aria-current="folder === 'uncategorized' ? 'page' : undefined" :disabled="busy || loading || managementPending" @click="switchFolder('uncategorized')"><Folder :size="16" aria-hidden="true" /><span>我的未分类文档</span></Button>
          <div class="od-folder-items">
            <Button v-for="item in folders" :key="item.id" variant="ghost" class="od-folder-link" :aria-current="folder === item.id ? 'page' : undefined" :disabled="busy || loading || managementPending" @click="switchFolder(item.id)"><Folder :size="16" aria-hidden="true" /><span>{{ item.name }}</span></Button>
          </div>
        </nav>
        <div class="od-folder-filter"><div class="od-folder-mobile"><label for="od-folder-filter">查看范围</label><select id="od-folder-filter" :value="folder" :disabled="busy || loading || managementPending" @change="switchFolder(($event.target as HTMLSelectElement).value)"><option value="">全部文档（含共享）</option><option value="uncategorized">我的未分类文档</option><option v-for="item in folders" :key="item.id" :value="item.id">{{ item.name }}</option></select></div><Button v-if="currentFolder" variant="ghost" :disabled="busy || managementPending || loading" @click="startFolderRename">文件夹改名</Button><Button v-if="currentFolder && !docs.length && connected && !loading" variant="ghost" :disabled="busy || managementPending" @click="removeFolder">删除空文件夹</Button></div>
        <p v-if="currentFolder">当前文件夹：{{ currentFolder.name }}。新建或上传的文档会直接放入这里。</p>
      </aside>
      <section class="od-library" aria-label="文档列表">
        <div class="od-section-heading"><h2>{{ recycleBin ? "回收站（仅自己可见）" : currentFolder ? currentFolder.name : folder === "uncategorized" ? "我的未分类文档" : "我的文档与共享文档" }} <span>{{ docs.length }}</span></h2><div class="od-filter"><select v-if="!recycleBin" aria-label="文档排序" :value="sort" :disabled="busy || loading || managementPending" @change="changeSort(($event.target as HTMLSelectElement).value as DocumentSort)"><option value="updated">更新时间（最新优先）</option><option value="name">名称（升序）</option><option value="name_desc">名称（降序）</option><option value="recent">最近使用（本机）</option></select><input v-model="search" :disabled="busy || managementPending" aria-label="搜索文档" placeholder="搜索文档名称" /><Button variant="ghost" size="sm" :disabled="loading || busy || managementPending" @click="refresh">刷新</Button></div></div>
        <TrashDocuments v-if="trashing" :factory-id="factoryId" :documents="trashing" @changed="trashed" @close="closeTrash()" @complete="closeTrash" />
        <div v-if="!recycleBin && selectableDocs.length" class="od-selection" role="group" aria-label="文档批量操作">
          <Button id="od-select-all" variant="ghost" size="sm" :disabled="busy || loading || managementPending" @click="toggleChecked">{{ allChecked ? '取消全选' : '全选当前结果' }}</Button>
          <span role="status">已选 {{ checked.length }} 份</span>
          <Button id="od-trash-checked" variant="destructive" size="sm" :disabled="!checked.length || busy || loading || managementPending" @click="startTrash()">批量移入回收站</Button>
        </div>
        <form v-if="checked.length" class="od-folder-form od-move" aria-label="文档归类" @submit.prevent="moveChecked">
          <strong>已选 {{ checked.length }} 份</strong><label for="od-move-target">移入</label><select id="od-move-target" v-model="moveTarget" :disabled="busy || managementPending"><option value="">未分类（移出文件夹）</option><option v-for="item in folders" :key="item.id" :value="item.id">{{ item.name }}</option></select>
          <Button type="submit" :disabled="busy || managementPending">确认移动</Button><Button type="button" variant="ghost" :disabled="busy || managementPending" @click="checked = []">取消选择</Button>
        </form>
        <p v-if="sort === 'recent' && !recycleBin" class="od-recent-hint">显示此账号在本机最近打开的文档，仅包含当前仍有访问权限的文件。</p>
        <p v-if="loading" class="od-empty" role="status">正在加载文档…</p>
        <div v-else-if="!connected" class="od-empty"><h3>暂时无法打开在线文档</h3><p>请检查上方提示后重试。</p><Button variant="outline" @click="refresh">重试</Button></div>
        <div v-else-if="!visibleDocs.length" class="od-empty"><FileText :size="32" /><h3>{{ search ? '没有匹配的文档' : recycleBin ? '回收站为空' : currentFolder ? '文件夹为空' : sort === 'recent' ? '暂无最近使用的文档' : '从一份文档开始' }}</h3><p>{{ search ? '试试其他名称。' : recycleBin ? '移入回收站的文件和历史版本会保留在这里。' : currentFolder ? '在这里新建或上传文档，也可回到全部文档勾选文件移入。' : sort === 'recent' ? '切换到更新时间排序，打开文档后会记录在这里。' : '新建空白文档，或上传已有 Word / Excel 文件。' }}</p></div>
        <ul v-else class="od-documents"><li v-for="doc in visibleDocs" :key="doc.id"><input v-if="!recycleBin && doc.access === 'owner'" v-model="checked" type="checkbox" class="od-check" :value="doc.id" :aria-label="`选择 ${doc.title}.${doc.format}`" :disabled="busy || managementPending || loading" /><div class="od-file-icon" :class="doc.format"><Sheet v-if="doc.format === 'xlsx'" :size="23" /><FileText v-else :size="23" /></div><div class="od-file-info"><button :disabled="busy || managementPending" class="od-file-name" @click="recycleBin ? manage(doc) : open(doc)">{{ doc.title }}.{{ doc.format }}</button><p>{{ doc.owner_name }} · {{ doc.access === 'owner' ? (doc.grants?.length ? `已共享给 ${doc.grants.length} 人` : '仅自己可见') : doc.access === 'edit' ? '共享 · 可编辑' : '共享 · 只读' }} · {{ doc.protected ? '公式区域已保护 · ' : '' }}{{ new Date(doc.updated_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) }}</p></div><div class="od-file-actions"><Button v-if="doc.access === 'owner'" :id="`od-manage-${doc.id}`" variant="ghost" size="sm" :disabled="busy || managementPending" @click="manage(doc)">{{ recycleBin ? '恢复 / 记录' : '详情' }}</Button><template v-if="!recycleBin"><Button v-if="doc.access === 'owner'" variant="ghost" size="sm" :disabled="busy || managementPending" @click="startCopy(doc)">复制</Button><Button v-if="doc.access === 'owner'" :id="`od-rename-${doc.id}`" variant="ghost" size="sm" :disabled="busy || managementPending" @click="startRename(doc)">重命名</Button><Button v-if="doc.access === 'owner'" variant="ghost" size="sm" :disabled="busy || managementPending" @click="sharing(doc)"><Users :size="15" />共享</Button><Button v-if="doc.access === 'owner'" :id="`od-trash-${doc.id}`" variant="ghost" size="sm" class="od-trash-action" :disabled="busy || loading || managementPending" @click="startTrash(doc)">移入回收站</Button><Button variant="ghost" size="sm" :disabled="busy || managementPending" @click="download(doc)"><Download :size="15" />下载</Button><Button variant="outline" size="sm" :disabled="busy || managementPending" @click="open(doc)">打开</Button></template></div></li></ul>
      </section>
      </div>
    </template>
  </main>
</template>

<style scoped>
.od-browser { display:grid; grid-template-columns:minmax(0,1fr); gap:18px; align-items:start; margin-top:18px; }
.od-folders { padding:16px; background:var(--color-card); border:1px solid var(--color-border); border-radius:var(--radius-xl); min-width:0; }
.od-folder-heading,.od-folder-heading strong,.od-folder-filter,.od-folder-form { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.od-folder-heading { justify-content:space-between; }.od-folder-heading strong { font-size:14px; }.od-folders p { font-size:12px; color:var(--color-muted-foreground); margin:10px 0; overflow-wrap:anywhere; line-height:1.6; }
.od-folder-navigation { display:none; }.od-folder-mobile { display:flex; flex-wrap:wrap; gap:8px; align-items:center; width:100%; }
.od-folder-filter select,.od-folder-form select { min-width:0; max-width:100%; width:280px; }.od-folder-form input { min-width:0; flex:1; }
.od-folder-form { margin:12px 0; }.od-folders .od-folder-form input { flex-basis:100%; }.od-folder-form label,.od-folder-filter label { font-size:13px; }
.od-library .od-move { margin:0 18px 16px; padding:12px 0; border-top:1px solid var(--color-border); border-bottom:1px solid var(--color-border); }
.od-browser .od-library { margin-top:0; min-width:0; }.od-browser .od-documents li { flex-wrap:wrap; }.od-browser .od-file-info { flex:1 1 200px; }.od-browser .od-file-actions { margin-left:auto; }
@media(min-width:1024px) {
  .od-browser { grid-template-columns:240px minmax(0,1fr); }.od-browser-bin { grid-template-columns:minmax(0,1fr); }
  .od-folder-mobile { display:none; }.od-folder-navigation { display:flex; flex-direction:column; gap:4px; margin-top:14px; }
  .od-folder-items { display:flex; flex-direction:column; gap:4px; max-height:55vh; overflow:auto; border-top:1px solid var(--color-border); margin-top:8px; padding-top:10px; }
  .od-folder-items:empty { display:none; }.od-folder-navigation .od-folder-link { justify-content:flex-start; align-items:flex-start; width:100%; height:auto; min-height:36px; padding:9px 10px; text-align:left; white-space:normal; }
  .od-folder-link span { min-width:0; overflow-wrap:anywhere; }.od-folder-link svg { margin-top:2px; }
  .od-folder-navigation .od-folder-link[aria-current=page] { background:var(--color-accent); color:var(--color-primary); }
  .od-folder-filter { margin-top:14px; }.od-folders .od-folder-form label { width:100%; }
}
input.od-check { width:18px; height:18px; min-height:18px; padding:0; accent-color:var(--color-primary); flex-shrink:0; }.od-documents li:has(.od-check:checked) { background:var(--color-muted); }
@media(max-width:700px) { .od-folder-form label { width:100%; }.od-folder-filter select,.od-folder-form select { width:100%; }.od-folder-form input { flex-basis:100%; }.od-folders { padding:14px 12px; } }

.od-selection { display:flex; flex-wrap:wrap; align-items:center; gap:12px; padding:0 18px 16px; font-size:13px; }.od-selection span { color:var(--color-muted-foreground); }.od-trash-action { color:var(--color-destructive); }
.od-workspace { min-height: 100dvh; padding: 16px 24px 28px; color: var(--color-foreground); background: var(--color-background); }
.od-nav,.od-nav a,.od-section-heading,.od-filter,.od-editor-bar,.od-file-actions { display:flex; align-items:center; gap:12px; }
.od-file-actions { flex-wrap:wrap; }.od-library-tabs { display:flex; gap:8px; margin-top:18px; }.od-library-tabs [aria-pressed=true] { background:var(--color-card); color:var(--color-primary); }
.od-nav { justify-content:space-between; margin-bottom:16px; font-size:13px; color:var(--color-muted-foreground); }.od-nav a { color:var(--color-primary); gap:6px; }
.od-notice { padding:10px 16px; color:var(--color-primary); background:var(--color-card); border:1px solid var(--color-border); border-radius:var(--radius-lg); margin-bottom:12px; }
.od-error { padding:12px 16px; border:1px solid var(--color-destructive); color:var(--color-destructive); background:var(--color-card); border-radius:var(--radius-lg); margin-bottom:12px; }
.od-create,.od-sharing,.od-library { background:var(--color-card); border:1px solid var(--color-border); border-radius:var(--radius-xl); margin-top:18px; }
.od-create { display:flex; align-items:center; flex-wrap:wrap; gap:12px; padding:18px; }.od-create label { font-weight:600; }.od-create span { margin-left:auto; font-size:12px; color:var(--color-muted-foreground); }
input,select { min-height:36px; border:1px solid var(--color-input); border-radius:var(--radius-md); padding:6px 10px; background:var(--color-background); font-size:14px; max-width:100%; }
.od-section-heading { padding:18px; justify-content:space-between; flex-wrap:wrap; gap:12px; }.od-section-heading h2 { font-weight:600; font-size:16px; min-width:0; overflow-wrap:anywhere; }.od-section-heading h2 span { color:var(--color-muted-foreground); margin-left:8px; font-size:13px; }
.od-recent-hint { padding:0 18px 12px; color:var(--color-muted-foreground); font-size:13px; }.od-filter select { max-width:100%; min-width:0; }.od-empty { min-height:250px; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:10px; text-align:center; padding:24px; color:var(--color-muted-foreground); }.od-empty h3 { font-size:17px; color:var(--color-foreground); }.od-empty p { font-size:14px; }
.od-documents li { display:flex; gap:16px; align-items:center; border-top:1px solid var(--color-border); padding:16px 18px; }.od-file-icon { flex-shrink:0; padding:12px; border-radius:var(--radius-lg); background:var(--color-muted); color:var(--color-primary); }.od-file-info { flex:1; min-width:0; }.od-file-name { display:block; max-width:100%; text-align:left; font-weight:600; overflow-wrap:anywhere; }.od-file-name:hover { color:var(--color-primary); text-decoration:underline; }.od-file-info p { font-size:12px; color:var(--color-muted-foreground); margin-top:6px; }
.od-sharing { padding:0 18px 18px; }.od-sharing .od-section-heading { padding-left:0; padding-right:0; }.od-sharing p { font-size:13px; color:var(--color-muted-foreground); margin-bottom:12px; }.od-share-add { display:flex; gap:12px; flex-wrap:wrap; align-items:end; }.od-share-add label { display:flex; flex-direction:column; gap:6px; font-size:13px; }.od-share-hint { margin-top:10px; }.od-share-add label { min-width:0; }.od-grants { margin:12px 0; }.od-grants li { display:flex; align-items:center; gap:12px; padding:8px 0; }.od-grants li>span { flex:1; min-width:0; overflow-wrap:anywhere; }
.od-rename>label { display:block; font-size:13px; margin-bottom:6px; }.od-rename-input { display:flex; align-items:center; gap:8px; max-width:560px; margin-bottom:10px; }.od-rename-input input { flex:1; min-width:0; }.od-rename-input span { color:var(--color-muted-foreground); font-size:13px; }.od-rename .od-rename-error { color:var(--color-destructive); }
.od-editing { height:100dvh; display:flex; flex-direction:column; padding-bottom:12px; }.od-editing .od-rename { flex-shrink:0; margin:0 0 12px; }.od-editing .od-nav { margin-bottom:10px; }.od-editor-bar { flex-wrap:wrap; margin-bottom:10px; }.od-editor-title { flex:1; min-width:120px; }.od-editor-title strong { display:block; overflow-wrap:anywhere; font-size:15px; }.od-editor-title span { display:block; font-size:12px; color:var(--color-muted-foreground); margin-top:3px; }.od-editor { flex:1; min-height:350px; background:var(--color-card); border:1px solid var(--color-border); }.od-editor>div { height:100%; }.od-loading { font-size:13px; padding:10px; color:var(--color-muted-foreground); }
@media(max-width:700px) { .od-workspace { padding:12px 10px; }.od-create { align-items:stretch; }.od-create input { flex:1; min-width:150px; }.od-create span { margin-left:0; width:100%; }.od-documents li { flex-wrap:wrap; gap:10px; padding:14px 12px; }.od-file-actions { width:100%; justify-content:flex-end; }.od-filter { width:100%; flex-wrap:wrap; }.od-filter select { width:100%; }.od-filter input { flex:1; min-width:0; }.od-editor-title { order:-1; width:100%; flex-basis:100%; }.od-share-add label { max-width:100%; } }
</style>
