<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { DialogContent, DialogDescription, DialogOverlay, DialogPortal, DialogRoot, DialogTitle } from 'reka-ui'
import { Camera, Megaphone, MessageSquare, Paperclip, RefreshCw, X } from '@lucide/vue'
import { cartonFeedbackApi, type FeedbackDetail, type FeedbackState, type FeedbackWorkspace } from '@/api/cartonFeedback'
import { getApiErrorMessage } from '@/lib/http'
import { captureFeedbackScreenshot } from '@/lib/feedbackScreenshot'
import FeedbackScreenshotAnnotator from '@/components/FeedbackScreenshotAnnotator.vue'

const props = defineProps<{ factoryId: string; factoryName: string; viewerKey?: string }>()
type Tab = 'compose' | 'mine' | 'manage' | 'updates'
type Shot = { id: string; file: File; url: string; notes: string[] }
const open = ref(false), tab = ref<Tab>('compose'), busy = ref(false), loading = ref(false), capturing = ref(false)
const error = ref(''), success = ref(''), title = ref(''), description = ref('')
const data = ref<FeedbackWorkspace>({ can_manage: false, feedbacks: [], updates: [] })
const detail = ref<FeedbackDetail | null>(null), detailLoading = ref(false), imageUrls = ref<string[]>([])
const screenshots = ref<Shot[]>([]), editing = ref<File | null>(null), editingIndex = ref(-1)
const input = ref<HTMLInputElement | null>(null), replyBody = ref(''), replyState = ref<FeedbackState>('FIXED')
const updateTitle = ref(''), updateBody = ref('')
const search = ref(''), status = ref(''), from = ref(''), to = ref(''), sort = ref('DESC'), page = ref(1)
const queryTotal = computed(() => tab.value === 'updates' ? (data.value.updates_total ?? data.value.updates.length) : (data.value.total ?? data.value.feedbacks.length))
let queryTimer: ReturnType<typeof setTimeout> | undefined
function clearQueries() { search.value = ''; status.value = ''; from.value = ''; to.value = '' }
watch([search, status, from, to, sort], () => {
  page.value = 1; clearDetail(); data.value.feedbacks = []; data.value.updates = []
  listSequence++; if (queryTimer) clearTimeout(queryTimer)
  if (open.value) queryTimer = setTimeout(() => void refresh(), 200)
})
watch(page, () => { clearDetail(); if (open.value) void refresh() })
onBeforeUnmount(() => { if (queryTimer) clearTimeout(queryTimer) })
const states: Record<FeedbackState, string> = { OPEN: '待处理', FIXED: '已修改', DECLINED: '暂时无法修改' }
const tabs = computed(() => [{ id: 'compose' as Tab, label: '反馈问题' }, { id: 'mine' as Tab, label: '我的反馈' },
  ...(data.value.can_manage ? [{ id: 'manage' as Tab, label: '处理反馈' }] : []), { id: 'updates' as Tab, label: '功能变动' }])
let controller = new AbortController(), generation = 0, listSequence = 0, detailSequence = 0
let submitSignature = '', submitKey = '', publishSignature = '', publishKey = ''
function revokeImages() { imageUrls.value.forEach(url => URL.revokeObjectURL(url)); imageUrls.value = [] }
function clearDetail() { detailSequence++; detail.value = null; detailLoading.value = false; replyBody.value = ''; revokeImages() }
function reset() {
  if (queryTimer) clearTimeout(queryTimer)
  search.value = ''; status.value = ''; from.value = ''; to.value = ''; sort.value = 'DESC'; page.value = 1
  generation++; listSequence++; detailSequence++; controller.abort(); controller = new AbortController()
  screenshots.value.forEach(shot => URL.revokeObjectURL(shot.url)); screenshots.value = []; revokeImages()
  editing.value = null; editingIndex.value = -1; detail.value = null; replyBody.value = ''
  data.value = { can_manage: false, feedbacks: [], updates: [] }
  title.value = ''; description.value = ''; updateTitle.value = ''; updateBody.value = ''
  submitSignature = ''; submitKey = ''; publishSignature = ''; publishKey = ''
  busy.value = false; loading.value = false; detailLoading.value = false; capturing.value = false; error.value = ''; success.value = ''
}
watch(() => [props.factoryId, props.viewerKey], () => { open.value = false; reset() }, { flush: 'sync' })
function close() { open.value = false; reset() }
function show(destination: Tab) { reset(); tab.value = destination; open.value = true; void refresh() }
async function refresh() {
  const current = generation, sequence = ++listSequence, factory = props.factoryId
  loading.value = true; error.value = ''
  try {
    const result = await cartonFeedbackApi.workspace(factory, tab.value === 'manage', controller.signal, { search: search.value.trim(), status: status.value, date_from: from.value, date_to: to.value, sort: sort.value, limit: 25, offset: tab.value === 'updates' ? 0 : (page.value - 1) * 25, updates_offset: tab.value === 'updates' ? (page.value - 1) * 25 : 0 })
    if (current === generation && sequence === listSequence) {
      data.value = result
      if (detail.value && !result.feedbacks.some(row => row.id === detail.value!.id)) clearDetail()
    }
  } catch (cause) {
    if (current === generation && sequence === listSequence) { clearDetail(); data.value = { can_manage: false, feedbacks: [], updates: [] }; error.value = getApiErrorMessage(cause) }
  } finally { if (current === generation && sequence === listSequence) loading.value = false }
}
function changeTab(destination: Tab) {
  if (busy.value) return
  page.value = 1; clearQueries(); tab.value = destination; detailSequence++; detail.value = null; detailLoading.value = false; revokeImages(); error.value = ''; success.value = ''; void refresh()
}
async function selectDetail(id: string) {
  const current = generation, sequence = ++detailSequence, factory = props.factoryId
  detailLoading.value = true; detail.value = null; revokeImages(); error.value = ''; replyBody.value = ''; replyState.value = 'FIXED'
  try {
    const row = await cartonFeedbackApi.detail(factory, id, controller.signal)
    if (current !== generation || sequence !== detailSequence) return
    detail.value = row
    const blobs = await Promise.all(row.images.map(image => cartonFeedbackApi.image(factory, id, image, controller.signal)))
    if (current === generation && sequence === detailSequence) imageUrls.value = blobs.map(blob => URL.createObjectURL(blob))
  } catch (cause) { if (current === generation && sequence === detailSequence) { clearDetail(); error.value = getApiErrorMessage(cause) } }
  finally { if (current === generation && sequence === detailSequence) detailLoading.value = false }
}
function editFile(file: File, index = -1) {
  if (busy.value || capturing.value) return
  error.value = ''
  if (index < 0 && screenshots.value.length >= 3) { error.value = '每条反馈最多 3 张截图。'; return }
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) { error.value = '请选择不超过 5 MB 的 PNG、JPG 或 WebP 图片。'; return }
  editingIndex.value = index; editing.value = file
}
function fileSelected(event: Event) { const target = event.target as HTMLInputElement; if (target.files?.[0]) editFile(target.files[0]); target.value = '' }
function saveScreenshot(file: File, notes: string[]) {
  const shot = { id: crypto.randomUUID(), file, notes, url: URL.createObjectURL(file) }
  if (editingIndex.value >= 0) { URL.revokeObjectURL(screenshots.value[editingIndex.value]!.url); screenshots.value.splice(editingIndex.value, 1, shot) }
  else screenshots.value.push(shot)
  editing.value = null; editingIndex.value = -1
}
function removeScreenshot(index: number) { URL.revokeObjectURL(screenshots.value[index]!.url); screenshots.value.splice(index, 1) }
function paste(event: ClipboardEvent) {
  if (!open.value || tab.value !== 'compose' || editing.value || capturing.value || busy.value) return
  const file = Array.from(event.clipboardData?.items ?? []).find(item => item.kind === 'file' && item.type.startsWith('image/'))?.getAsFile()
  if (file) { event.preventDefault(); editFile(file) }
}
async function capture() {
  const current = generation, signal = controller.signal
  capturing.value = true; error.value = ''; await nextTick()
  if (current !== generation) return
  try {
    const file = await captureFeedbackScreenshot(signal)
    if (current !== generation) return
    capturing.value = false; editFile(file)
  } catch (cause) { if (current === generation) error.value = getApiErrorMessage(cause) }
  finally { if (current === generation) capturing.value = false }
}
async function submit() {
  if (busy.value || loading.value || !title.value.trim() || !description.value.trim()) return
  const current = generation, factory = props.factoryId
  const body = [description.value.trim(), ...screenshots.value.flatMap((shot, index) => shot.notes.length ? [`截图 ${index + 1} 批注：`, ...shot.notes] : [])].join('\n')
  const signature = JSON.stringify([title.value.trim(), body, screenshots.value.map(shot => shot.id)])
  if (signature !== submitSignature) { submitSignature = signature; submitKey = crypto.randomUUID() }
  busy.value = true; error.value = ''; success.value = ''
  try {
    const row = await cartonFeedbackApi.create(factory, title.value.trim(), body, '/modules/pmc-warehouse/carton-procurement', submitKey, screenshots.value.map(shot => shot.file), controller.signal)
    if (current !== generation) return
    title.value = ''; description.value = ''; screenshots.value.forEach(shot => URL.revokeObjectURL(shot.url)); screenshots.value = []
    submitSignature = ''; tab.value = 'mine'; success.value = '反馈已提交，可在这里查看管理员回复。'
    await refresh(); if (current === generation) await selectDetail(row.id)
  } catch (cause) { if (current === generation) error.value = getApiErrorMessage(cause) }
  finally { if (current === generation) busy.value = false }
}
async function reply() {
  if (busy.value || !detail.value || !replyBody.value.trim()) return
  const current = generation, row = detail.value, factory = props.factoryId
  busy.value = true; error.value = ''; success.value = ''
  try {
    const result = await cartonFeedbackApi.reply(factory, row, replyBody.value.trim(), replyState.value, controller.signal)
    if (current === generation) { detail.value = result; replyBody.value = ''; success.value = '处理结果和回复已保存，员工可以查看。'; await refresh() }
  } catch (cause) { if (current === generation) error.value = getApiErrorMessage(cause) }
  finally { if (current === generation) busy.value = false }
}
async function publish() {
  if (busy.value || !updateTitle.value.trim() || !updateBody.value.trim()) return
  const current = generation, factory = props.factoryId
  const signature = JSON.stringify([updateTitle.value.trim(), updateBody.value.trim()])
  if (signature !== publishSignature) { publishSignature = signature; publishKey = crypto.randomUUID() }
  busy.value = true; error.value = ''; success.value = ''
  try {
    await cartonFeedbackApi.publish(factory, updateTitle.value.trim(), updateBody.value.trim(), publishKey, controller.signal)
    if (current === generation) { updateTitle.value = ''; updateBody.value = ''; publishSignature = ''; success.value = `更新说明已发布到${props.factoryName}。`; await refresh() }
  } catch (cause) { if (current === generation) error.value = getApiErrorMessage(cause) }
  finally { if (current === generation) busy.value = false }
}
document.addEventListener('paste', paste)
onBeforeUnmount(() => { reset(); document.removeEventListener('paste', paste) })
defineExpose({ openFeedback: () => show('compose') })
</script>

<template>
  <div class="flex shrink-0 items-center gap-1.5">
    <button type="button" aria-label="打开问题反馈" title="问题反馈" class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 sm:px-3" @click="show('compose')"><MessageSquare class="size-4" aria-hidden="true" /><span class="hidden lg:inline">问题反馈</span></button>
    <button type="button" aria-label="查看功能变动" title="功能变动" class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 sm:px-3" @click="show('updates')"><Megaphone class="size-4" aria-hidden="true" /><span class="hidden lg:inline">功能变动</span></button>
  </div>
  <DialogRoot :open="open && !capturing && !editing" @update:open="value => { if (!value && !capturing && !editing) close() }">
    <DialogPortal>
    <DialogOverlay class="fixed inset-0 z-[70] bg-slate-950/40" />
    <DialogContent class="fixed left-1/2 top-1/2 z-[71] flex max-h-[92dvh] w-[calc(100%_-_1.5rem)] max-w-4xl -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl bg-white shadow-xl">
      <div class="flex items-start justify-between border-b px-5 py-4">
        <div><DialogTitle class="text-lg font-bold text-slate-950">问题反馈与功能变动</DialogTitle><DialogDescription class="mt-1 text-xs text-slate-500">{{ factoryName }} · 反馈仅本人和有权限的管理员可见，更新说明供本厂区员工查看。</DialogDescription></div>
        <button type="button" aria-label="关闭反馈窗口" class="rounded-lg border p-2" @click="close"><X class="size-4" /></button>
      </div>
      <nav aria-label="问题反馈子页面" class="flex flex-wrap gap-1 border-b bg-slate-50 px-4 py-2"><button v-for="entry in tabs" :key="entry.id" type="button" :disabled="busy" :aria-pressed="tab === entry.id" :class="tab === entry.id ? 'bg-teal-100 text-teal-800' : 'text-slate-600'" class="rounded-lg px-3 py-2 text-sm font-semibold disabled:opacity-50" @click="changeTab(entry.id)">{{ entry.label }}</button></nav>
      <div class="overflow-y-auto p-4 sm:p-5">
        <p v-if="error" role="alert" class="mb-4 whitespace-pre-wrap rounded-lg bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
        <p v-if="success" role="status" class="mb-4 rounded-lg bg-teal-50 p-3 text-sm text-teal-800">{{ success }}</p>
        <p v-if="loading" role="status" class="mb-3 text-sm text-slate-500">正在读取反馈与更新说明…</p>
        <div v-if="tab !== 'compose'" class="mb-4 flex flex-wrap items-end gap-2 rounded-lg bg-slate-50 p-3 text-xs" aria-label="反馈与更新查询">
          <label class="min-w-44 flex-1">关键字<input v-model="search" :disabled="busy" aria-label="反馈更新关键字" placeholder="标题 / 内容 / 提交人" class="mt-1 h-9 w-full rounded-lg border px-3"></label>
          <label v-if="tab !== 'updates'">状态<select v-model="status" :disabled="busy" aria-label="反馈状态筛选" class="mt-1 block h-9 rounded-lg border px-2"><option value="">全部状态</option><option v-for="(name, state) in states" :key="state" :value="state">{{ name }}</option></select></label>
          <label>{{ tab === 'updates' ? '发布日期从' : '提交日期从' }}<input v-model="from" :disabled="busy" type="date" aria-label="反馈更新起始日期" class="mt-1 block h-9 rounded-lg border px-2"></label><label>至<input v-model="to" :disabled="busy" type="date" aria-label="反馈更新结束日期" class="mt-1 block h-9 rounded-lg border px-2"></label>
          <select v-model="sort" :disabled="busy" aria-label="反馈更新排序" class="h-9 rounded-lg border px-2"><option value="DESC">最近更新优先</option><option value="ASC">最早更新优先</option></select><button type="button" :disabled="busy" class="h-9 rounded-lg border px-3" @click="clearQueries">清除筛选</button><button type="button" :disabled="busy" class="h-9 rounded-lg border px-3" @click="sort = 'DESC'">恢复默认排序</button>
        </div>
        <form v-if="tab === 'compose'" class="space-y-4" @submit.prevent="submit">
          <label class="block text-sm font-semibold">问题标题<input v-model="title" required maxlength="120" :disabled="busy" placeholder="例如：订单页面的数量显示不正确" class="mt-2 block w-full rounded-lg border p-2.5 font-normal"></label>
          <label class="block text-sm font-semibold">问题说明<textarea v-model="description" required maxlength="4000" rows="4" :disabled="busy" placeholder="请说明操作步骤、出现的问题，以及你希望的结果。" class="mt-2 block w-full resize-y rounded-lg border p-2.5 font-normal" /></label>
          <div class="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-3">
            <div class="flex flex-wrap items-center gap-2"><button type="button" :disabled="busy || screenshots.length >= 3" class="inline-flex items-center gap-1.5 rounded-lg border bg-white px-3 py-2 text-sm disabled:opacity-50" @click="capture"><Camera class="size-4" />截取当前页面</button><button type="button" :disabled="busy || screenshots.length >= 3" class="inline-flex items-center gap-1.5 rounded-lg border bg-white px-3 py-2 text-sm disabled:opacity-50" @click="input?.click()"><Paperclip class="size-4" />选择截图</button><span class="text-xs text-slate-500">也可 Ctrl+V 粘贴 · 最多 3 张，每张 5 MB</span></div>
            <p class="mt-2 text-xs leading-5 text-slate-500">截图时选择当前标签页，随后框选并编号；提交前可删除截图，请检查是否包含不需要分享的内容。</p>
            <input ref="input" type="file" accept="image/png,image/jpeg,image/webp" class="sr-only" aria-label="选择反馈截图文件" @change="fileSelected">
            <div v-if="screenshots.length" class="mt-3 grid gap-3 sm:grid-cols-3"><div v-for="(shot, index) in screenshots" :key="shot.id" class="rounded-lg border bg-white p-2"><img :src="shot.url" :alt="`反馈截图 ${index + 1}`" class="h-28 w-full rounded object-contain"><div class="mt-2 flex items-center justify-between text-xs"><span>截图 {{ index + 1 }} · {{ shot.notes.length }} 个批注</span><button type="button" :disabled="busy" :aria-label="`删除截图 ${index + 1}`" class="text-red-700" @click="removeScreenshot(index)">删除</button></div></div></div>
          </div>
          <div class="flex justify-end"><button type="submit" :disabled="busy || loading || !title.trim() || !description.trim()" class="rounded-lg bg-teal-700 px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-50">{{ busy ? '正在提交…' : '提交反馈' }}</button></div>
        </form>
        <template v-else-if="tab === 'mine' || tab === 'manage'">
          <div class="mb-3 flex items-center justify-between"><p class="text-xs text-slate-500">{{ tab === 'manage' ? '本厂区员工反馈' : '我的反馈' }} · 共 {{ queryTotal }} 条</p><button type="button" :disabled="loading || busy" class="inline-flex items-center gap-1 rounded-lg border px-3 py-1.5 text-xs" @click="refresh"><RefreshCw class="size-3" />刷新列表</button></div>
          <p v-if="!loading && !error && !data.feedbacks.length" class="rounded-xl bg-slate-50 p-6 text-center text-sm text-slate-500">暂无反馈</p>
          <div class="grid items-start gap-4" :class="detail || detailLoading ? 'md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]' : ''">
            <div class="space-y-2"><button v-for="row in data.feedbacks" :key="row.id" type="button" :disabled="busy" :aria-label="`查看反馈：${row.title}`" :class="detail?.id === row.id ? 'border-teal-400 bg-teal-50' : 'border-slate-200 bg-white'" class="w-full rounded-xl border p-3 text-left hover:border-teal-300" @click="selectDetail(row.id)"><div class="flex items-start justify-between gap-3"><span class="break-words text-sm font-semibold">{{ row.title }}</span><span class="shrink-0 rounded-full bg-slate-100 px-2 py-1 text-xs">{{ states[row.status] }}</span></div><p class="mt-2 text-xs text-slate-500">{{ row.author_name }} · {{ row.created_at.replace('T', ' ').slice(0, 16) }}</p></button></div>
            <p v-if="detailLoading" class="text-sm text-slate-500">正在读取反馈详情…</p>
            <article v-else-if="detail" class="min-w-0 space-y-4 rounded-xl border p-4">
              <div class="flex items-start justify-between gap-2"><h3 class="break-words font-bold">{{ detail.title }}</h3><button type="button" :disabled="busy" class="shrink-0 text-xs text-teal-700" @click="selectDetail(detail.id)">刷新详情</button></div>
              <p class="whitespace-pre-wrap break-words text-sm leading-6 text-slate-700">{{ detail.description }}</p>
              <div v-if="imageUrls.length" class="space-y-2"><a v-for="(url, index) in imageUrls" :key="url" :href="url" target="_blank" rel="noopener" :aria-label="`放大反馈截图 ${index + 1}`"><img :src="url" :alt="`反馈截图 ${index + 1}`" class="mb-2 max-h-56 w-full rounded-lg border object-contain"></a></div>
              <div class="space-y-3 border-t pt-3"><h4 class="text-sm font-semibold">管理员回复 <span class="font-normal text-slate-400">（最近 100 条）</span></h4><p v-if="!detail.replies.length" class="text-xs text-slate-500">等待管理员处理。</p><div v-for="entry in detail.replies" :key="entry.id" class="rounded-lg bg-slate-50 p-3"><p class="text-xs font-semibold text-teal-800">{{ states[entry.status] }} · {{ entry.author_name }}</p><p class="mt-2 whitespace-pre-wrap break-words text-sm leading-6">{{ entry.body }}</p><p class="mt-2 text-xs text-slate-400">{{ entry.created_at.replace('T', ' ').slice(0, 16) }}</p></div></div>
              <form v-if="tab === 'manage' && data.can_manage" class="space-y-3 border-t pt-3" @submit.prevent="reply"><label class="block text-sm font-semibold">处理结果<select v-model="replyState" :disabled="busy" aria-label="选择反馈处理结果" class="mt-2 block w-full rounded-lg border p-2"><option value="FIXED">已修改</option><option value="DECLINED">暂时无法修改</option><option value="OPEN">继续处理</option></select></label><label class="block text-sm font-semibold">回复员工<textarea v-model="replyBody" required maxlength="3000" rows="3" :disabled="busy" placeholder="说明改动内容，或暂时无法修改的原因。" class="mt-2 block w-full rounded-lg border p-2 font-normal" /></label><button type="submit" :disabled="busy || !replyBody.trim()" class="rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{{ busy ? '正在保存…' : '保存处理结果并回复' }}</button></form>
            </article>
          </div>
        </template>
        <template v-else>
          <form v-if="data.can_manage" class="mb-5 space-y-3 rounded-xl border border-teal-200 bg-teal-50/50 p-4" @submit.prevent="publish"><h3 class="font-semibold">发布更新说明到{{ factoryName }}</h3><label class="block text-sm">更新标题<input v-model="updateTitle" required maxlength="120" :disabled="busy" class="mt-1 block w-full rounded-lg border bg-white p-2"></label><label class="block text-sm">更新内容<textarea v-model="updateBody" required maxlength="6000" rows="3" :disabled="busy" placeholder="说明哪些功能有变化，员工应该如何使用。" class="mt-1 block w-full rounded-lg border bg-white p-2" /></label><button type="submit" :disabled="busy || !updateTitle.trim() || !updateBody.trim()" class="rounded-lg bg-teal-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{{ busy ? '正在发布…' : '发布更新说明' }}</button></form>
          <div class="mb-3 flex items-center justify-between"><p class="text-xs text-slate-500">本厂区已发布的更新 · 共 {{ queryTotal }} 条</p><button type="button" :disabled="loading || busy" class="rounded-lg border px-3 py-1.5 text-xs" @click="refresh">刷新更新</button></div>
          <p v-if="!loading && !error && !data.updates.length" class="rounded-xl bg-slate-50 p-6 text-center text-sm text-slate-500">管理员尚未发布更新说明。</p>
          <article v-for="entry in data.updates" :key="entry.id" class="mb-3 rounded-xl border p-4"><h3 class="break-words font-bold">{{ entry.title }}</h3><p class="mt-1 text-xs text-slate-400">{{ entry.created_at.replace('T', ' ').slice(0, 16) }} · {{ entry.author_name }}</p><p class="mt-3 whitespace-pre-wrap break-words text-sm leading-6 text-slate-700">{{ entry.body }}</p></article>
        </template>
        <div v-if="tab !== 'compose'" class="mt-4 flex items-center justify-end gap-3 border-t pt-3 text-xs"><button type="button" :disabled="busy || loading || page <= 1" class="rounded-lg border px-3 py-2 disabled:opacity-40" @click="page--">上一页</button><span>第 {{ page }} / {{ Math.max(1, Math.ceil(queryTotal / 25)) }} 页</span><button type="button" :disabled="busy || loading || page * 25 >= queryTotal" class="rounded-lg border px-3 py-2 disabled:opacity-40" @click="page++">下一页</button></div>
      </div>
    </DialogContent>
    </DialogPortal>
  </DialogRoot>
  <Teleport to="body"><div v-if="capturing" class="fixed bottom-5 left-1/2 z-[72] flex -translate-x-1/2 items-center gap-3 rounded-xl bg-slate-950 px-4 py-3 text-sm text-white"><span>请选择当前标签页进行截图</span><button type="button" class="shrink-0 rounded border border-white/40 px-2 py-1" @click="close">取消</button></div></Teleport>
  <FeedbackScreenshotAnnotator v-if="editing" :file="editing" @save="saveScreenshot" @cancel="editing = null; editingIndex = -1" />
</template>
