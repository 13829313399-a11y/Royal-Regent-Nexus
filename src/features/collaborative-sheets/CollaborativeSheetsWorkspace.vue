<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { Download, Plus, RefreshCw, Save, Upload, X } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import SectionPanel from '@/components/common/SectionPanel.vue'
import { collaborativeSheetsApi as api, type FillCell, type FillChange, type FillGrant, type FillRecipients, type FillTask, type FillTaskDetail, type FillParticipant, type SheetValue } from '@/api/collaborativeSheets'
import { getApiErrorMessage } from '@/lib/http'
import { departments } from '@/data/enterpriseMock'
import { registerFactoryChangeGuard } from '@/lib/factoryChangeGuard'
import { canFill, clipboardRows, columnName, parseInput, rangeBounds } from './grid'
import FillGrid from './FillGrid.vue'
import './workspace.css'

const props = defineProps<{ factoryId: string }>()
const tasks = ref<FillTask[]>([]), task = ref<FillTaskDetail>()
const recipients = ref<FillRecipients>({ users: [], departments: [] })
const busy = ref(false), loading = ref(false), error = ref(''), notice = ref('')
const title = ref(''), file = ref<File>(), showUpload = ref(false), filter = ref('all')
const activeSheet = ref(0), selected = ref<FillCell>(), editorText = ref('')
const editorKind = ref<'auto' | 'text' | 'number' | 'boolean'>('auto'), editorTouched = ref(false)
const changes = ref<FillChange[]>([]), conflict = ref(false), conflictReview = ref<string[]>([])
const grants = ref<FillGrant[]>([]), grantsDirty = ref(false), showGrants = ref(false)
const grantType = ref<'user' | 'department'>('department'), grantPrincipal = ref(''), grantRange = ref(''), grantSheet = ref(0)
let alive = true, loadSequence = 0, poll: ReturnType<typeof setInterval> | undefined
let participantGeneration = 0, refreshingParticipants = false
const participants = ref<FillParticipant[]>([]), rosterError = ref(''), remoteRevision = ref(0)
const participantLabels = { not_started: '未填写', in_progress: '已保存 · 未确认完成', completed: '已完成', needs_confirmation: '表格已更新 · 待重新确认' }
const completedCount = computed(() => participants.value.filter(p => p.status === 'completed').length)
const selectedPeople = computed(() => recipients.value.users.filter(u => grantType.value === 'department' ? u.department === grantPrincipal.value : u.id === grantPrincipal.value))
const sheet = computed(() => task.value?.workbook.sheets.find(s => s.index === activeSheet.value))
const dirty = computed(() => changes.value.length > 0 || editorTouched.value || grantsDirty.value)
const visibleTasks = computed(() => tasks.value.filter(t => filter.value === 'all' || (filter.value === 'mine' ? t.is_owner : !t.is_owner)))
const selectedEditable = computed(() => !!(task.value && sheet.value && selected.value && canFill(task.value, sheet.value, selected.value.row, selected.value.column)))
const principalOptions = computed(() => grantType.value === 'department'
  ? recipients.value.departments.map(d => ({ id: d.id, label: departmentName(d.id) }))
  : recipients.value.users.map(u => ({ id: u.id, label: `${u.display_name} · ${departmentName(u.department)}` })))
const stateNames = { draft: '待发布', open: '填写中', closed: '已结束' }
function actionName(action: string) {
  return ({ created: '上传表格', grants_changed: '调整填写分配', cells_saved: '保存填写', submitted: '确认填写完成', opened: '开放填报', create: '上传表格', upload: '上传表格', grants: '调整填写分配', save: '保存填写', cells: '保存填写', submit: '确认填写完成', open: '开放填报', closed: '结束填报', close: '结束填报', state: '更改填报状态', download: '下载汇总' } as Record<string, string>)[action] ?? '更新填报任务'
}
function departmentName(id: string) {
  const provided = recipients.value.departments.find(d => d.id === id)?.name
  return provided && provided !== id ? provided : departments.find(d => d.id === id)?.name
    ?? ({ 'three-d-printing': '3D 打印', molding: '注塑部', warehouse: '仓管' } as Record<string, string>)[id] ?? id
}
function principalName(g: FillGrant) {
  return g.principal_type === 'department' ? departmentName(g.principal_id) : recipients.value.users.find(u => u.id === g.principal_id)?.display_name ?? '指定账号'
}
function sheetName(index: number) { return task.value?.workbook.sheets.find(s => s.index === index)?.name ?? `工作表 ${index + 1}` }
function time(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
}
function confirmLeave() {
  return !dirty.value || window.confirm('有尚未保存的填写内容或分配设置，确定离开并放弃这些修改吗？')
}
defineExpose({ confirmLeave })
const removeFactoryGuard = registerFactoryChangeGuard(confirmLeave)
onBeforeRouteLeave(() => confirmLeave())
onBeforeRouteUpdate((to, from) => {
  if (to.query.tool !== 'collaborative-sheets' || to.query.factory !== from.query.factory) return confirmLeave()
  return true
})
function beforeUnload(event: BeforeUnloadEvent) { if (dirty.value) { event.preventDefault(); event.returnValue = '' } }
async function refreshList() {
  const result = await api.list(props.factoryId)
  if (alive) tasks.value = result.items
}
async function refreshParticipants() {
  if (!task.value || busy.value || refreshingParticipants) return
  const id = task.value.id, generation = participantGeneration
  refreshingParticipants = true
  try {
    const snapshot = await api.participants(props.factoryId, id)
    if (!alive || task.value?.id !== id || generation !== participantGeneration || busy.value) return
    if (snapshot.revision < task.value.revision) return
    participants.value = snapshot.participants; remoteRevision.value = snapshot.revision; rosterError.value = ''
  } catch {
    if (alive && task.value?.id === id && generation === participantGeneration) rosterError.value = '人员状态暂未刷新，请稍后重试。'
  } finally { refreshingParticipants = false }
}
async function initialize() {
  if (props.factoryId === 'group') return
  loading.value = true
  const results = await Promise.allSettled([refreshList(), api.recipients(props.factoryId)])
  if (!alive) return
  if (results[1].status === 'fulfilled') recipients.value = results[1].value
  for (const result of results) if (result.status === 'rejected') error.value = getApiErrorMessage(result.reason)
  loading.value = false
}
function adopt(detail: FillTaskDetail, reset = true) {
  participantGeneration++
  participants.value = detail.participants ?? []; remoteRevision.value = detail.revision; rosterError.value = ''
  task.value = detail
  if (!detail.workbook.sheets.some(s => s.index === activeSheet.value)) activeSheet.value = detail.workbook.sheets[0]?.index ?? 0
  grants.value = detail.grants.map(g => ({ ...g }))
  grantsDirty.value = false
  if (reset) { changes.value = []; selected.value = undefined; editorTouched.value = false; conflictReview.value = [] }
  const idx = tasks.value.findIndex(t => t.id === detail.id)
  if (idx >= 0) tasks.value.splice(idx, 1, detail)
  else tasks.value.unshift(detail)
}
async function openTask(item: FillTask) {
  if (busy.value || !confirmLeave()) return
  const request = ++loadSequence
  busy.value = true; error.value = ''; notice.value = ''; conflict.value = false
  try {
    const result = await api.detail(props.factoryId, item.id)
    if (alive && request === loadSequence) { activeSheet.value = 0; adopt(result); showGrants.value = result.status === 'draft'; showUpload.value = false }
  } catch (e) { if (alive) error.value = getApiErrorMessage(e) }
  finally { if (alive && request === loadSequence) busy.value = false }
}
function pickFile(event: Event) {
  const input = event.target as HTMLInputElement
  file.value = input.files?.[0]
  if (file.value && !title.value) title.value = file.value.name.replace(/\.[^.]+$/, '')
}
async function create() {
  if (!file.value || !title.value.trim() || busy.value || !confirmLeave()) return
  if (!/\.(xls|xlsx)$/i.test(file.value.name)) { error.value = '请选择 .xls 或 .xlsx 表格。'; return }
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const result = await api.create(props.factoryId, title.value.trim(), file.value)
    if (!alive) return
    adopt(result); showGrants.value = true; showUpload.value = false; title.value = ''; file.value = undefined
    notice.value = '表格已上传，当前仅你可见。请分配填写范围后发布。'
  } catch (e) { if (alive) error.value = getApiErrorMessage(e) }
  finally { if (alive) busy.value = false }
}
function applyEditor(): boolean {
  if (!editorTouched.value || !selected.value || !sheet.value || !task.value) return true
  if (!selectedEditable.value) { error.value = '当前单元格不能填写，请刷新表格确认任务状态和权限。'; return false }
  try {
    const value = parseInput(editorText.value, editorKind.value)
    const key = { sheet: sheet.value.index, address: selected.value.address }
    changes.value = changes.value.filter(c => c.sheet !== key.sheet || c.address !== key.address)
    if (value !== selected.value.value) changes.value.push({ ...key, value })
    editorTouched.value = false
    return true
  } catch (e) { error.value = e instanceof Error ? e.message : '填写内容无效'; return false }
}
function selectCell(cell: FillCell) {
  if (busy.value || !applyEditor()) return false
  selected.value = cell
  const change = changes.value.find(c => c.sheet === activeSheet.value && c.address === cell.address)
  const value = change ? change.value : cell.value
  editorText.value = value === null ? '' : String(value)
  editorKind.value = value === null ? 'auto' : typeof value === 'number' ? 'number' : typeof value === 'boolean' ? 'boolean' : 'text'
  editorTouched.value = false
  return true
}
function inlineInput(text: string) { editorText.value = text; editorTouched.value = true }
function cancelEditor() {
  if (!selected.value) return
  const pending = changes.value.find(c => c.sheet === activeSheet.value && c.address === selected.value!.address)
  const value = pending ? pending.value : selected.value.value
  editorText.value = value === null ? '' : String(value); editorTouched.value = false; error.value = ''
}
function pasteCells(anchor: FillCell, text: string, literal?: { value: SheetValue }) {
  if (!task.value || !sheet.value || busy.value) return false
  try {
    const matrix = literal ? [[text]] : clipboardRows(text), batch: FillChange[] = []
    if (matrix.reduce((n, r) => n + r.length, 0) > 500) throw new Error('一次最多粘贴 500 格，请分批填写并保存。')
    matrix.forEach((line, r) => line.forEach((raw, c) => {
      const row = anchor.row + r, column = anchor.column + c, address = `${columnName(column)}${row + 1}`
      if (!canFill(task.value!, sheet.value!, row, column)) throw new Error(`${address} 是公式、合并区域内部或未授权单元格，本次粘贴未写入，请调整粘贴范围。`)
      const value = literal ? literal.value : parseInput(raw, 'auto')
      if (typeof value === 'string' && (value.length > 2000 || value.trimStart().startsWith('=') || /[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(value))) throw new Error(`${address} 内容过长、包含公式或不支持的字符，本次粘贴未写入。`)
      batch.push({ sheet: activeSheet.value, address, value })
    }))
    const replaced = new Set(batch.map(c => c.address))
    const next = changes.value.filter(c => c.sheet !== activeSheet.value || !replaced.has(c.address))
    for (const change of batch) {
      const original = sheet.value.cells.find(c => c.address === change.address)?.value ?? null
      if (change.value !== original) next.push(change)
    }
    if (next.length > 500) throw new Error('待保存内容超过 500 格，请先保存现有填写，再继续粘贴。')
    changes.value = next; error.value = ''; notice.value = `已粘贴 ${batch.length} 格，点击“保存填写”保存到服务器。`
    selected.value = anchor; cancelEditor(); return true
  } catch (e) { error.value = e instanceof Error ? e.message : '粘贴失败'; return false }
}
function selectSheet(index: number) {
  if (!applyEditor()) return
  activeSheet.value = index; selected.value = undefined
}
async function save(): Promise<boolean> {
  if (!task.value || busy.value || !applyEditor()) return false
  if (!changes.value.length) return true
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const localGrants = grantsDirty.value ? grants.value.map(g => ({ ...g })) : undefined
    const result = await api.save(props.factoryId, task.value, changes.value)
    if (!alive) return false
    adopt(result); conflict.value = false; notice.value = '填写内容已保存到服务器。'
    if (localGrants) { grants.value = localGrants; grantsDirty.value = true; notice.value += '分配设置仍未保存。' }
    return true
  } catch (e) {
    if (alive) {
      error.value = getApiErrorMessage(e)
      conflict.value = (e as { response?: { status?: number } }).response?.status === 409
    }
    return false
  } finally { if (alive) busy.value = false }
}
async function reload(keepChanges = false) {
  if (!task.value || busy.value || (!keepChanges && !confirmLeave())) return
  if (keepChanges && !applyEditor()) return
  busy.value = true; error.value = ''
  try {
    const result = await api.detail(props.factoryId, task.value.id)
    if (!alive) return
    const pending = changes.value
    const pendingGrants = keepChanges && grantsDirty.value ? grants.value.map(g => ({ ...g })) : undefined
    const comparison = pending.map(c => {
      const previous = task.value?.workbook.sheets.find(s => s.index === c.sheet)?.cells.find(x => x.address === c.address)?.value ?? null
      const current = result.workbook.sheets.find(s => s.index === c.sheet)?.cells.find(x => x.address === c.address)?.value ?? null
      return previous !== current ? `${sheetName(c.sheet)} ${c.address}：服务器已改为“${current ?? '空白'}”，你的填写是“${c.value ?? '空白'}”。` : ''
    }).filter(Boolean)
    adopt(result)
    if (keepChanges) {
      changes.value = pending
      conflictReview.value = comparison
      notice.value = '已读取最新版本，并保留你的待保存内容。请核对后再点击保存。'
      if (pendingGrants) {
        grants.value = pendingGrants; grantsDirty.value = true
        notice.value += '你的分配设置也已保留，请核对服务器上的分配后再保存设置。'
      }
    }
    conflict.value = false
  } catch (e) { if (alive) error.value = getApiErrorMessage(e) }
  finally { if (alive) busy.value = false }
}
function addGrant() {
  const bounds = rangeBounds(grantRange.value.trim())
  const target = task.value?.workbook.sheets.find(s => s.index === grantSheet.value)
  if (!grantPrincipal.value || !bounds || !target || bounds[2] >= target.rows || bounds[3] >= target.columns) {
    error.value = '请选择填写对象，并输入原表内有效的范围，例如 C3:N30。'; return
  }
  const grant: FillGrant = { principal_type: grantType.value, principal_id: grantPrincipal.value, sheet: grantSheet.value, range: grantRange.value.trim().toUpperCase() }
  if (!grants.value.some(g => JSON.stringify(g) === JSON.stringify(grant))) grants.value.push(grant)
  grantsDirty.value = true; error.value = ''; grantRange.value = ''
}
async function saveGrants() {
  if (!task.value || busy.value) return
  if (changes.value.length || editorTouched.value) { error.value = '请先保存填写内容，再保存分配设置。'; return }
  busy.value = true; error.value = ''
  try {
    const result = await api.grants(props.factoryId, task.value, grants.value)
    if (alive) { adopt(result); notice.value = '填写对象和范围已保存。' }
  } catch (e) { if (alive) error.value = getApiErrorMessage(e) }
  finally { if (alive) busy.value = false }
}
async function changeState(status: 'open' | 'closed') {
  if (!task.value || busy.value) return
  if (dirty.value) { error.value = '请先保存填写内容和分配设置，再更改任务状态。'; return }
  if (status === 'closed' && !window.confirm('结束填报后，所有参与人员将不能继续修改。确定结束吗？')) return
  busy.value = true; error.value = ''
  try {
    const result = await api.state(props.factoryId, task.value, status)
    if (alive) { adopt(result); notice.value = status === 'closed' ? '填报已结束，现在可以下载汇总版本。' : '填报已开放，指定人员登录后即可填写。' }
  } catch (e) { if (alive) error.value = getApiErrorMessage(e) }
  finally { if (alive) busy.value = false }
}
async function submit() {
  if (grantsDirty.value) { error.value = '请先保存分配设置，再确认填写完成。'; return }
  if (!task.value || busy.value || !(await save())) return
  busy.value = true; error.value = ''
  try {
    const result = await api.submit(props.factoryId, task.value)
    if (alive) { adopt(result); notice.value = '已标记填写完成。表格后续有修改时，需要重新确认。' }
  } catch (e) { if (alive) error.value = getApiErrorMessage(e) }
  finally { if (alive) busy.value = false }
}
async function download() {
  if (!task.value || busy.value) return
  if (dirty.value) { error.value = '请先保存所有修改，再下载汇总版本。'; return }
  busy.value = true; error.value = ''
  try {
    const blob = await api.download(props.factoryId, task.value)
    if (!alive) return
    const url = URL.createObjectURL(blob), anchor = document.createElement('a')
    anchor.href = url; anchor.download = task.value.original_name.replace(/(\.[^.]+)$/, '-已填写$1')
    anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 10_000)
    notice.value = '已下载服务器保存的填写版本。原始上传文件仍然保留。'
  } catch (e) { if (alive) error.value = getApiErrorMessage(e) }
  finally { if (alive) busy.value = false }
}
onMounted(() => {
  void initialize()
  window.addEventListener('beforeunload', beforeUnload)
  poll = setInterval(() => {
    if (!busy.value && document.visibilityState === 'visible' && props.factoryId !== 'group') {
      void refreshList().catch(() => { /* Explicit refresh remains available after transient polling failure. */ })
      void refreshParticipants()
    }
  }, 15_000)
})
onBeforeUnmount(() => { alive = false; loadSequence++; clearInterval(poll); removeFactoryGuard(); window.removeEventListener('beforeunload', beforeUnload) })
</script>

<template>
  <section class="cs-workspace" aria-label="协同填表">
    <div class="cs-heading">
      <div><h2>协同填表</h2><p>上传原表，指定部门或账号填写，集中保存后下载。</p></div>
      <div class="cs-actions">
        <Button variant="outline" :disabled="busy || loading || factoryId === 'group'" @click="initialize"><RefreshCw :size="16" />刷新任务</Button>
        <Button :disabled="busy || factoryId === 'group'" @click="showUpload = !showUpload"><Upload :size="16" />上传表格</Button>
      </div>
    </div>
    <p v-if="factoryId === 'group'" class="cs-message">请先在顶部选择你所属的厂区，再上传或填写表格。</p>
    <p v-if="error" class="cs-error" role="alert">{{ error }}</p>
    <p v-if="notice" class="cs-message" role="status">{{ notice }}</p>
    <div v-if="conflict" class="cs-warning" role="alert">
      <p>服务器上的表格已更新，你的填写内容仍保留在本页。</p>
      <Button variant="outline" :disabled="busy" @click="reload(true)">读取最新版本（保留我的填写）</Button>
    </div>
    <div v-if="conflictReview.length" class="cs-warning"><strong>以下单元格需要核对后再保存</strong><p v-for="line in conflictReview" :key="line">{{ line }}</p></div>
    <SectionPanel v-if="showUpload" title="新建填报任务" subtitle="上传后先设置填写范围，再发布给指定人员。">
      <form class="cs-upload-form" @submit.prevent="create">
        <label>任务名称<input v-model="title" required maxlength="160" placeholder="例如：2026 年货款汇总" :disabled="busy" /></label>
        <label>Excel 表格<input type="file" accept=".xls,.xlsx" required :disabled="busy" @change="pickFile" /></label>
        <Button type="submit" :disabled="busy || !file || !title.trim()">{{ busy ? '正在处理…' : '上传并设置填写范围' }}</Button>
      </form>
    </SectionPanel>
    <div v-if="factoryId !== 'group'" class="cs-layout">
      <aside class="cs-task-list" aria-label="填报任务列表">
        <label>任务范围<select v-model="filter"><option value="all">全部可见任务</option><option value="mine">我上传的</option><option value="assigned">分配给我的</option></select></label>
        <p v-if="loading">正在加载…</p>
        <p v-else-if="!visibleTasks.length" class="cs-empty">暂无填报任务。上传表格后即可分配填写。</p>
        <button v-for="item in visibleTasks" :key="item.id" type="button" class="cs-task" :class="{ active: item.id === task?.id }" :disabled="busy" @click="openTask(item)">
          <strong>{{ item.title }}</strong><span>{{ stateNames[item.status] }} · {{ item.is_owner ? '我上传的' : item.owner_name }}</span><small>{{ time(item.updated_at) }}</small>
        </button>
      </aside>
      <div v-if="task" class="cs-document">
        <div class="cs-document-heading">
          <div><h3>{{ task.title }}</h3><p>{{ task.original_name }} · {{ stateNames[task.status] }} · 上传人：{{ task.owner_name }}</p></div>
          <div class="cs-actions">
            <Button variant="outline" :disabled="busy" @click="reload()"><RefreshCw :size="15" />读取最新</Button>
            <Button v-if="task.is_owner" variant="outline" :disabled="busy || changes.length > 0 || editorTouched" @click="showGrants = !showGrants">分配填写</Button>
            <Button v-if="task.is_owner" variant="outline" :disabled="busy" @click="download"><Download :size="15" />下载汇总</Button>
          </div>
        </div>
        <div v-if="task.is_owner && showGrants" class="cs-assignment">
          <h4>填写对象与范围</h4>
          <p>参与人员可查看整张表，只能填写分配的区域。请避开表头；公式始终只读。</p>
          <div class="cs-grant-form">
            <label>工作表<select v-model.number="grantSheet" :disabled="busy"><option v-for="s in task.workbook.sheets" :key="s.index" :value="s.index">{{ s.name }}</option></select></label>
            <label>分配方式<select v-model="grantType" :disabled="busy" @change="grantPrincipal = ''"><option value="department">指定部门</option><option value="user">指定账号</option></select></label>
            <label>填写对象<select v-model="grantPrincipal" :disabled="busy"><option value="">请选择</option><option v-for="p in principalOptions" :key="p.id" :value="p.id">{{ p.label }}</option></select></label>
            <label>填写范围<input v-model="grantRange" :disabled="busy" placeholder="例如 C3:N30" aria-label="填写范围" /></label>
            <Button variant="outline" :disabled="busy" @click="addGrant"><Plus :size="14" />添加</Button>
          </div>
          <div v-if="grantPrincipal" class="cs-member-preview" aria-label="所选填写对象的账号">
            <p>当前厂区匹配账号（{{ selectedPeople.length }} 人）</p>
            <span v-for="person in selectedPeople" :key="person.id">{{ person.display_name }}</span>
            <p v-if="!selectedPeople.length">当前没有有效账号。</p>
          </div>
          <p v-if="!grants.length" class="cs-empty">还未分配填写范围。可为不同部门分别添加多个范围。</p>
          <ul class="cs-grants"><li v-for="(g, i) in grants" :key="i"><span>{{ principalName(g) }} · {{ sheetName(g.sheet) }} · {{ g.range }}</span><button type="button" :disabled="busy" :aria-label="`移除${principalName(g)}的${g.range}范围`" @click="grants.splice(i, 1); grantsDirty = true"><X :size="15" /></button></li></ul>
          <Button :disabled="busy || !grantsDirty || changes.length > 0 || editorTouched" @click="saveGrants">保存分配设置</Button>
        </div>
        <div class="cs-status-bar">
          <span v-if="busy">正在处理，请稍候…</span>
          <span v-else-if="changes.length || editorTouched">有未保存的填写内容</span><span v-else>当前显示已读取的服务器版本</span>
          <div class="cs-actions">
            <template v-if="task.status === 'open'">
              <Button :disabled="busy || (!changes.length && !editorTouched)" @click="save"><Save :size="15" />保存填写</Button>
              <Button v-if="task.editable_ranges.length" variant="outline" :disabled="busy || grantsDirty" @click="submit">我已填完</Button>
            </template>
            <Button v-if="task.is_owner && task.status !== 'open'" :disabled="busy || dirty || !task.grants.length" @click="changeState('open')">{{ task.status === 'draft' ? '发布填报' : '重新开放填写' }}</Button>
            <Button v-if="task.is_owner && task.status === 'open'" variant="outline" :disabled="busy || dirty" @click="changeState('closed')">结束填报</Button>
          </div>
        </div>
        <section class="cs-participants" aria-label="填写人员与进度">
          <div class="cs-heading"><h4>填写人员与进度 <small>{{ completedCount }} / {{ participants.length }} 人已完成</small></h4><Button variant="outline" :disabled="busy" @click="refreshParticipants">刷新人员状态</Button></div>
          <p>按已保存的分配列出当前厂区全部有效账号。已保存内容后，点击“我已填完”才会标为已完成。</p>
          <p v-if="grantsDirty" class="cs-roster-note">分配设置尚未保存，下面仍显示服务器上的名单。</p>
          <p v-if="rosterError" role="status" class="cs-roster-note">{{ rosterError }}</p>
          <p v-if="remoteRevision > task.revision" class="cs-roster-note">表格已有新版本，人员状态已更新；当前填写内容已保留，请使用“读取最新”核对表格。</p>
          <div class="cs-participant-list">
            <div v-for="person in participants" :key="person.user_id" :class="['cs-person', `cs-person-${person.status}`]" :data-participant="person.user_id">
              <strong>{{ person.display_name }}</strong><span>{{ departmentName(person.department) }}</span>
              <b>{{ participantLabels[person.status] }}</b>
              <small v-if="person.last_saved_at">最近保存 {{ time(person.last_saved_at) }}</small>
              <small v-else-if="person.submitted_at">确认时间 {{ time(person.submitted_at) }}</small>
            </div>
          </div>
          <p v-if="!participants.length" class="cs-empty">尚无有效填写账号，请先保存填写对象和范围。</p>
        </section>
        <div v-if="task.workbook.warnings.length" class="cs-warning"><p v-for="warning in task.workbook.warnings" :key="warning">{{ warning }}</p></div>
        <div class="cs-sheet-tabs" role="tablist" aria-label="工作表"><button v-for="s in task.workbook.sheets" :key="s.index" type="button" role="tab" :aria-selected="s.index === activeSheet" :disabled="busy" @click="selectSheet(s.index)">{{ s.name }}</button></div>
        <div v-if="sheet" class="cs-cell-editor">
          <template v-if="selected">
            <strong>{{ selected.address }}</strong>
            <template v-if="selectedEditable">
              <label class="cs-type-label">类型<select v-model="editorKind" :disabled="busy" @change="editorTouched = true"><option value="auto">自动识别</option><option value="text">文字</option><option value="number">数字</option><option value="boolean">是 / 否</option></select></label>
              <select v-if="editorKind === 'boolean'" v-model="editorText" aria-label="填写内容" :disabled="busy" @change="editorTouched = true"><option value="">空白</option><option value="true">是</option><option value="false">否</option></select>
              <textarea v-else v-model="editorText" aria-label="填写内容" rows="2" :disabled="busy" placeholder="输入内容；清空表示留空" @input="editorTouched = true" />
              <Button variant="outline" :disabled="busy || !editorTouched" @click="applyEditor">确认此格</Button>
            </template>
            <span v-else>{{ selected.formula ? '公式单元格，只读。' : task.status !== 'open' ? '填报尚未开放或已结束。' : '该单元格不在你的填写范围。' }}</span>
          </template>
          <span v-else>选中单元格直接打字，或双击修改。Enter / Tab 换格，Esc 取消，支持从 Excel 粘贴多格。</span>
          <small v-if="sheet">范围 A1:{{ columnName(sheet.columns - 1) }}{{ sheet.rows }}</small>
        </div>
        <FillGrid v-if="sheet" :key="`${task.id}:${sheet.index}`" :task="task" :sheet="sheet" :changes="changes" :selected="selected?.address ?? ''"
          :text="editorText" :disabled="busy" :select-cell="selectCell" :commit-editor="applyEditor" :cancel-editor="cancelEditor" :paste-cells="pasteCells"
          @input="inlineInput" @begin="editorKind = 'auto'" @text-mode="editorKind = 'text'" @save="save" />
        <p class="cs-grid-help">浅绿色区域可填写，黄色表示尚未保存。修改后点击“保存填写”或 Ctrl / ⌘ + S；公式和未授权区域只读。</p>
        <div class="cs-evidence">
          <details><summary>最近操作</summary><p v-if="!task.activity?.length">暂无操作记录。</p><p v-for="a in task.activity ?? []" :key="a.id">{{ a.actor_name }} · {{ actionName(a.action) }} · {{ time(a.created_at) }}</p></details>
        </div>
      </div>
      <div v-else class="cs-welcome"><h3>让大家在同一份表里填写</h3><p>选择左侧任务，或上传一张新表格。</p><p>原始文件会保留。填写结果由上传人统一下载。</p></div>
    </div>
  </section>
</template>
