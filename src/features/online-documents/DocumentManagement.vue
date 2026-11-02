<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { isAxiosError } from 'axios'
import { DialogContent, DialogDescription, DialogOverlay, DialogPortal, DialogRoot, DialogTitle } from 'reka-ui'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'
import { onlineDocuments as api, type OnlineDocument, type DocumentRevision, type DocumentEvent, type DocumentCommand } from '@/api/onlineDocuments'
import { downloadBlob } from './editor'

const props = defineProps<{ factoryId: string; document: OnlineDocument }>()
const emit = defineEmits<{ close: []; changed: [document: OnlineDocument, notice: string]; pending: [value: boolean]; denied: [] }>()
const current = ref({ ...props.document })
const tab = ref<'history' | 'protection' | 'events' | 'trash'>(props.document.deleted_at ? 'trash' : 'history')
const sectionTitle = computed(() => ({ history: '历史版本', protection: '公式区域保护', events: '操作记录', trash: current.value.deleted_at ? '恢复文件' : '移入回收站' })[tab.value])
const history = ref<DocumentRevision[]>([])
const events = ref<DocumentEvent[]>([])
const nextHistory = ref<number | null>(null)
const nextEvents = ref<string | null>(null)
const ranges = ref<{ name: string; formula_count: number; text: string }[]>([])
const error = ref('')
const loading = ref(false)
const busy = ref(false)
const heading = ref<HTMLElement>()
type Kind = 'restore' | 'trash' | 'recover' | 'protection'
const confirmation = ref<{ kind: Kind; description: string; payload: DocumentCommand } | null>(null)
const uncertain = ref(false)
const blocked = computed(() => current.value.editing || !!current.value.pending_save || !!current.value.save_error)
let generation = 0
let disposed = false
const active = (run: number) => !disposed && run === generation
function requestClose(open = false) { if (!open && !busy.value && !uncertain.value) emit('close') }
function guardDismiss(event: Event) { if (busy.value || uncertain.value) event.preventDefault() }
const date = (value: string) => new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })
const labels: Record<string, string> = { copy: '复制文档', move: '移动文件夹', create: '创建文档', rename: '重命名', share: '修改共享权限', save: '保存版本（最后编辑账号）', restore: '恢复历史版本', trash: '移入回收站', recover: '从回收站恢复', protection: '调整公式区域保护' }
function details(event: DocumentEvent) {
  if (event.kind === 'rename') return `${event.details.from} → ${event.details.to}`
  if (event.kind === 'restore') return `来源：版本 ${event.details.restored_revision}`
  if (event.kind === 'protection') return event.details.enabled ? '已启用保护' : '已解除保护'
  if (event.kind === 'share') {
    const grants = event.details.after as { name: string; access: string }[] | undefined
    return grants?.length ? grants.map(g => `${g.name}：${g.access === 'edit' ? '可编辑' : '只读'}`).join('；') : '仅自己可见'
  }
  if (event.kind === 'recover') return '恢复后仅自己可见，原共享已清除'
  return ''
}
function failed(e: unknown) {
  error.value = getApiErrorMessage(e)
  if (isAxiosError(e) && [401, 403, 404].includes(e.response?.status ?? 0)) {
    history.value = []; events.value = []; ranges.value = []; emit('denied')
  }
}
async function load(more = false) {
  if (busy.value || uncertain.value) return
  const run = ++generation
  loading.value = true; error.value = ''
  try {
    if (tab.value === 'history') {
      const result = await api.history(props.factoryId, current.value.id, more ? nextHistory.value ?? 0 : 0)
      if (active(run)) { history.value = more ? [...history.value, ...result.items] : result.items; nextHistory.value = result.next_before }
    } else if (tab.value === 'events') {
      const result = await api.events(props.factoryId, current.value.id, more ? nextEvents.value ?? '' : '')
      if (active(run)) { events.value = more ? [...events.value, ...result.items] : result.items; nextEvents.value = result.next_before }
    } else if (tab.value === 'protection') {
      const result = await api.protection(props.factoryId, current.value.id)
      if (active(run)) {
        current.value = result.document
        ranges.value = result.sheets.map(s => ({ ...s, text: result.rules.find(r => r.sheet === s.name)?.ranges.join(',') ?? '' }))
      }
    }
  } catch (e) { if (active(run)) failed(e) }
  finally { if (active(run)) loading.value = false }
}
function switchTab(value: typeof tab.value) {
  if (busy.value || uncertain.value) return
  confirmation.value = null; tab.value = value; void load()
}
function prepare(kind: Kind, revision?: number) {
  if (busy.value || loading.value || blocked.value || uncertain.value) return
  let description = ''
  const payload: DocumentCommand = { request_id: createRandomUuid(), expected_version: current.value.state_version }
  if (kind === 'restore') { payload.revision = revision; description = `将版本 ${revision} 恢复为一个新版本。现在的内容仍保留在历史记录中，共享权限保持不变。` }
  if (kind === 'trash') description = '移入回收站后，同事将无法打开该文件，现有共享会被清除。文件和历史版本仍保留，可由你恢复。'
  if (kind === 'recover') description = '文件将恢复到文档列表，默认仅自己可见。需要同事使用时，请重新设置共享。'
  if (kind === 'protection') {
    payload.enabled = !current.value.protected
    payload.rules = payload.enabled ? ranges.value.map(r => ({ sheet: r.name, ranges: r.text.split(/[,，;；\n]/).map(v => v.trim().toUpperCase()).filter(Boolean) })) : []
    description = payload.enabled ? '仅指定区域可填写，原有公式仍锁定。留空的工作表将整张只读，不能增删行列、工作表或新建公式。设置会生成新版本。' : '解除后，可编辑同事也能修改公式和其他区域。此操作会生成新版本。'
  }
  error.value = ''; confirmation.value = { kind, payload, description }
}
async function execute() {
  const action = confirmation.value
  if (!action || busy.value) return
  const run = generation
  busy.value = true; error.value = ''; emit('pending', true)
  try {
    const doc = await api.command(props.factoryId, current.value.id, action.kind, action.payload)
    if (!active(run)) return
    uncertain.value = false; confirmation.value = null; current.value = doc
    const notices = { restore: `已恢复为版本 ${doc.revision}，原有版本仍保留`, trash: '已移入回收站', recover: '已恢复文件，目前仅自己可见', protection: doc.protected ? '已启用公式区域保护' : '已解除公式区域保护' }
    emit('changed', doc, doc.operation_notice || notices[action.kind])
  } catch (e) {
    if (active(run)) {
      // Unknown network/5xx results may already be committed. Keep exactly the
      // same command until acknowledged; do not silently generate another ID.
      uncertain.value = !isAxiosError(e) || !e.response || e.response.status >= 500
      failed(e)
      if (uncertain.value) error.value = '操作结果尚未确认，请重试原操作；重试不会重复生成版本。' + error.value
      else confirmation.value = null
    }
  } finally {
    if (active(run)) { busy.value = false; emit('pending', uncertain.value) }
  }
}
async function download(version: DocumentRevision) {
  if (busy.value || uncertain.value) return
  const run = generation
  busy.value = true; error.value = ''
  try { const blob = await api.downloadRevision(props.factoryId, current.value.id, version.revision); if (active(run)) downloadBlob(blob, `${current.value.title}-版本${version.revision}.${current.value.format}`) }
  catch (e) { if (active(run)) failed(e) }
  finally { if (active(run)) busy.value = false }
}
onMounted(() => { void load() })
onBeforeUnmount(() => { disposed = true; generation++; emit('pending', false) })
</script>

<template>
  <DialogRoot :open="true" @update:open="requestClose">
    <DialogPortal>
      <DialogOverlay class="od-manage-overlay" />
      <DialogContent class="od-manage" aria-modal="true" @escape-key-down="guardDismiss" @interact-outside="guardDismiss" @open-auto-focus="event => { event.preventDefault(); nextTick(() => heading?.focus()) }">
    <header>
      <div class="od-manage-title">
        <p class="eyebrow">文件详情</p>
        <DialogTitle as-child><h2 ref="heading" tabindex="-1">{{ current.title }}.{{ current.format }} · {{ sectionTitle }}</h2></DialogTitle>
        <DialogDescription class="description">{{ current.owner_name }} · {{ current.deleted_at ? '回收站中的文件' : '我的文档' }} · 当前版本 {{ current.revision }}</DialogDescription>
      </div>
      <Button variant="ghost" size="sm" :disabled="busy || uncertain" @click="requestClose()">关闭详情</Button>
    </header>
    <div class="tabs" role="group" aria-label="管理功能">
      <Button v-if="!current.deleted_at" variant="ghost" :aria-pressed="tab === 'history'" :disabled="busy || uncertain" @click="switchTab('history')">历史版本</Button>
      <Button v-if="!current.deleted_at && current.format === 'xlsx'" variant="ghost" :aria-pressed="tab === 'protection'" :disabled="busy || uncertain" @click="switchTab('protection')">公式区域保护</Button>
      <Button variant="ghost" :aria-pressed="tab === 'events'" :disabled="busy || uncertain" @click="switchTab('events')">操作记录</Button>
      <Button variant="ghost" :aria-pressed="tab === 'trash'" :disabled="busy || uncertain" @click="switchTab('trash')">{{ current.deleted_at ? '恢复文件' : '移入回收站' }}</Button>
    </div>
    <p v-if="busy || uncertain" class="pending-note" role="status">{{ uncertain ? '操作结果尚未确认，请在此文件内重试原操作后关闭。' : '正在处理此文件，请稍候再关闭。' }}</p>
    <div class="od-manage-body">
    <p v-if="blocked" class="hint" role="status">还有编辑会话或保存待确认。请所有人保存并关闭文档后，关闭此面板并刷新列表。</p>
    <div v-if="error" role="alert" class="error">{{ error }} <Button v-if="!uncertain" variant="outline" size="sm" :disabled="busy || loading" @click="load()">重新读取</Button></div>
    <p v-if="loading" role="status">正在读取…</p>
    <template v-else>
      <div v-if="tab === 'history'">
        <p class="hint">这里只显示当前文件的历史版本，仅拥有者可见。可下载核对内容，再恢复为新版本；当前内容不会丢失。</p>
        <ul><li v-for="v in history" :key="v.revision"><div><strong>版本 {{ v.revision }}{{ v.current ? ' · 当前版本' : '' }}</strong><p>{{ date(v.created_at) }} · {{ (v.byte_size / 1024).toFixed(1) }} KB</p></div><div class="actions"><Button variant="outline" size="sm" :disabled="busy || uncertain" @click="download(v)">下载此版本</Button><Button v-if="!v.current" variant="outline" size="sm" :disabled="busy || uncertain || blocked || current.protected" @click="prepare('restore', v.revision)">恢复此版本</Button></div></li></ul>
        <p v-if="current.protected" class="hint">恢复历史版本前，请先解除公式区域保护。</p>
        <Button v-if="nextHistory" variant="ghost" :disabled="busy || uncertain" @click="load(true)">加载更早版本</Button>
      </div>
      <div v-if="tab === 'protection'">
        <p class="hint">{{ current.protected ? '已保护：只有下面的区域可以填写，原有公式保持锁定。' : '为每张工作表指定可填写区域，其余区域和原有公式锁定。留空表示整张只读。' }}</p>
        <p class="hint">例如 B2:D100,F2:F100。合计最多 50000 格；保护期间不能新增公式、增删行列或工作表。数组公式和原有密码保护需先处理。</p>
        <label v-for="r in ranges" :key="r.name">{{ r.name }} · {{ r.formula_count }} 个公式<input v-model="r.text" :aria-label="`${r.name}可填写区域`" placeholder="例如 B2:D100,F2:F100；留空整张只读" :disabled="busy || uncertain || current.protected || blocked || !!confirmation" /></label>
        <Button :variant="current.protected ? 'destructive' : 'default'" :disabled="busy || uncertain || blocked || !ranges.length" @click="prepare('protection')">{{ current.protected ? '解除保护' : '启用保护' }}</Button>
      </div>
      <div v-if="tab === 'events'">
        <p class="hint">记录从本功能启用后开始保留。多人共同编辑的保存记录显示最后编辑账号，不代表该账号修改了全部内容。</p>
        <ul><li v-for="e in events" :key="e.id"><div><strong>{{ labels[e.kind] ?? e.kind }}</strong><p>{{ e.actor_name }} · {{ date(e.created_at) }} · 版本 {{ e.revision }}</p><p v-if="details(e)">{{ details(e) }}</p></div></li></ul>
        <p v-if="!events.length && !error" class="hint">暂无操作记录；已有历史版本仍保留。</p>
        <Button v-if="nextEvents" variant="ghost" :disabled="busy || uncertain" @click="load(true)">加载更早记录</Button>
      </div>
      <div v-if="tab === 'trash'"><p class="hint">{{ current.deleted_at ? '文件和历史版本仍保留。恢复后默认仅自己可见，需要重新共享。' : '移入回收站会取消共享，同事无法继续访问。文件和历史版本可由你恢复，不会永久删除。' }}</p><Button :variant="current.deleted_at ? 'default' : 'destructive'" :disabled="busy || uncertain || blocked" @click="prepare(current.deleted_at ? 'recover' : 'trash')">{{ current.deleted_at ? '恢复到文档列表' : '将文件移入回收站' }}</Button></div>
    </template>
    </div>
    <div v-if="confirmation" class="confirmation" role="group" aria-label="确认文档操作"><strong>{{ current.title }}.{{ current.format }}</strong><p>{{ confirmation.description }}</p><div class="actions"><Button :variant="confirmation.kind === 'trash' || confirmation.kind === 'restore' ? 'destructive' : 'default'" :disabled="busy" @click="execute">{{ busy ? '正在处理…' : uncertain ? '重试原操作' : '确认操作' }}</Button><Button variant="outline" :disabled="busy || uncertain" @click="confirmation = null">取消</Button></div></div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style scoped>
.od-manage-overlay { position:fixed; inset:0; z-index:70; background:rgb(15 23 42 / 40%); }
.od-manage { position:fixed; inset:0 0 0 auto; z-index:71; width:min(680px,100%); height:100dvh; display:flex; flex-direction:column; overflow:hidden; background:var(--color-card); color:var(--color-foreground); border-left:1px solid var(--color-border); box-shadow:-8px 0 28px rgb(15 23 42 / 10%); }
header,.tabs,.actions,li { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
header { flex-shrink:0; align-items:flex-start; flex-wrap:nowrap; padding:20px 24px 0; }
.od-manage-title { min-width:0; flex:1; }
.eyebrow,.description { font-size:12px; color:var(--color-muted-foreground); line-height:1.6; }
.eyebrow { margin-bottom:6px; } .description { margin-top:8px; overflow-wrap:anywhere; }
h2 { font-size:18px; line-height:1.5; font-weight:600; overflow-wrap:anywhere; }
.tabs { flex-shrink:0; margin:0; padding:16px 24px 12px; border-bottom:1px solid var(--color-border); }
.tabs [aria-pressed=true] { color:var(--color-primary); background:var(--color-muted); }
.od-manage-body { min-height:0; flex:1; overflow-y:auto; overscroll-behavior:contain; padding:12px 24px 24px; }
.pending-note { flex-shrink:0; padding:10px 24px; font-size:13px; color:var(--color-muted-foreground); background:var(--color-muted); }
.hint,li p,.confirmation p { color:var(--color-muted-foreground); font-size:13px; line-height:1.7; margin:10px 0; overflow-wrap:anywhere; } li { padding:12px 0; border-top:1px solid var(--color-border); justify-content:space-between; } li>div { min-width:0; } li strong { font-size:14px; } li p { margin:4px 0; } .error { color:var(--color-destructive); margin:12px 0; overflow-wrap:anywhere; } label { display:flex; flex-direction:column; gap:6px; margin:14px 0; font-size:14px; overflow-wrap:anywhere; } input { min-height:38px; border:1px solid var(--color-input); border-radius:var(--radius-md); padding:6px 10px; background:var(--color-background); width:100%; max-width:680px; }
.confirmation { flex-shrink:0; max-height:45dvh; overflow-y:auto; padding:16px 24px; border-top:1px solid var(--color-border); background:var(--color-muted); overflow-wrap:anywhere; }
@media(max-width:700px) { header { padding:16px 12px 0; } h2 { font-size:16px; } .tabs { padding:12px; gap:6px; } .od-manage-body { padding:10px 12px 16px; } .confirmation,.pending-note { padding:12px; } .actions { width:100%; } }
</style>
