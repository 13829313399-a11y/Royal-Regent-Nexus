<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { cuttingApi, errorMessage, type Access, type Kind, type MasterRecord, type MaterialData, type ResourceData, type BomData, type SaveCommand, type StateCommand } from './api'
import { CUTTING_FACTORY } from './navigation'

const access = ref<Access | null>(null)
const loading = ref(true), saving = ref(false), editor = ref(false)
const error = ref(''), notice = ref(''), query = ref(''), code = ref(''), reason = ref('')
const kind = ref<Kind>('bom'), records = ref<MasterRecord[]>([]), editing = ref<MasterRecord | null>(null)
const page = ref(1), total = ref(0)
const material = reactive<MaterialData>({ name: '', category: 'fabric', unit: '', specification: '', color: '', source_reference: '' })
const resource = reactive<ResourceData>({ name: '', execution: 'internal', process: 'cutting', contact: '', source_reference: '' })
const bom = reactive<BomData>({ name: '', item_no: '', style: '', color: '', source_reference: '', parts: [], requirements: [] })
const materialQuery = ref(''), selectedMaterial = ref(''), materialOptions = ref<MasterRecord[]>([])
const materialPage = ref(1), materialTotal = ref(0)
const materialReferences = reactive<Record<string, { code: string; name: string }>>({})
const history = ref<MasterRecord | null>(null), historyRows = ref<MasterRecord[]>([])
const historyPage = ref(1), historyTotal = ref(0), historyBusy = ref(false)
const transition = ref<MasterRecord | null>(null), transitionReason = ref('')
type Pending = { type: 'save'; body: SaveCommand; id?: string } | { type: 'state'; body: StateCommand; id: string }
const pending = ref<Pending | null>(null)
const pendingUncertain = ref(false), needsLogin = ref(false)
const editorBaseline = ref('')
const editorSnapshot = () => JSON.stringify({ code: code.value, reason: reason.value, data: kind.value === 'material' ? material : kind.value === 'resource' ? resource : bom })
const dirty = computed(() => (editor.value && editorSnapshot() !== editorBaseline.value) || (!!transition.value && !!transitionReason.value))
let generation = 0, materialGeneration = 0, alive = true
function resetMaterialSearch() {
  materialGeneration++
  materialOptions.value = []; selectedMaterial.value = ''; materialPage.value = 1; materialTotal.value = 0
}
watch([materialQuery, editor, kind], resetMaterialSearch, { flush: 'sync' })
function permitDiscard() {
  if (saving.value || pending.value) {
    error.value = saving.value ? '正在保存，请等待结果后再离开。' : '保存结果尚未确认，请先“重试原操作”确认结果后再离开。'
    return false
  }
  return !dirty.value || window.confirm('有尚未保存的内容，离开将放弃这些内容。确定继续？')
}
onBeforeRouteLeave(permitDiscard)
function beforeUnload(event: BeforeUnloadEvent) {
  if (!dirty.value && !saving.value && !pending.value) return
  event.preventDefault()
  event.returnValue = ''
}
onMounted(() => window.addEventListener('beforeunload', beforeUnload))
onBeforeUnmount(() => {
  alive = false; generation++; materialGeneration++
  window.removeEventListener('beforeunload', beforeUnload)
})
const available = computed(() => access.value?.enabled && access.value?.schema_ready)
const can = (action: string) => access.value?.permissions.includes(action) ?? false
const canEdit = computed(() => can(kind.value === 'bom' ? 'bom_write' : 'master_write'))
const labels: Record<Kind, string> = { bom: '产品与配套 BOM', material: '物料与单位', resource: '本厂与外发资源' }
const statuses = { active: '有效', inactive: '停用', draft: '草稿', published: '已发布' }
const fieldLabels: Record<string, string> = { name: '名称', category: '类别', unit: '单位', specification: '规格', color: '颜色', source_reference: '来源', execution: '执行方式', process: '工序', contact: '联系资料' }
const valueLabels: Record<string, string> = { fabric: '布料', accessory: '辅料', internal: '本厂', outsourced: '外发', cutting: '裁剪' }
const businessTime = (value: string) => new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).format(new Date(value))

async function load() {
  const request = ++generation
  loading.value = true; error.value = ''; records.value = []
  try {
    const rights = await cuttingApi.access()
    if (!alive || request !== generation) return
    access.value = rights
    if (!rights.enabled || !rights.schema_ready) return
    const result = await cuttingApi.list(kind.value, page.value, query.value)
    if (!alive || request !== generation) return
    records.value = result.data; total.value = result.total
  } catch (e) { if (alive && request === generation) { access.value = null; error.value = errorMessage(e) } }
  finally { if (alive && request === generation) loading.value = false }
}
onMounted(load)
function switchKind(next: Kind) {
  if (next === kind.value || !permitDiscard()) return
  kind.value = next; page.value = 1; query.value = ''; editor.value = false; history.value = null; transition.value = null; notice.value = ''; void load()
}
function openEditor(record?: MasterRecord) {
  if (!permitDiscard()) return
  transition.value = null; resetMaterialSearch()
  editing.value = record ?? null; code.value = record?.code ?? ''; reason.value = ''; error.value = ''; notice.value = ''
  materialOptions.value = []; selectedMaterial.value = ''; materialQuery.value = ''
  Object.assign(material, { name: '', category: 'fabric', unit: '', specification: '', color: '', source_reference: '' })
  Object.assign(resource, { name: '', execution: 'internal', process: 'cutting', contact: '', source_reference: '' })
  Object.assign(bom, { name: '', item_no: '', style: '', color: '', source_reference: '', parts: [], requirements: [] })
  if (record) Object.assign(kind.value === 'material' ? material : kind.value === 'resource' ? resource : bom, JSON.parse(JSON.stringify(record.data)))
  Object.assign(materialReferences, record?.material_references ?? {})
  editorBaseline.value = editorSnapshot()
  editor.value = true
}
function closeEditor() {
  if (permitDiscard()) editor.value = false
}
function openTransition(record: MasterRecord) {
  if (!permitDiscard()) return
  editor.value = false; transition.value = record; transitionReason.value = ''
}
function closeTransition() {
  if (permitDiscard()) transition.value = null
}
async function findMaterials(nextPage = 1) {
  resetMaterialSearch()
  const request = materialGeneration
  const current = () => alive && editor.value && kind.value === 'bom' && request === materialGeneration
  try {
    const result = await cuttingApi.list('material', nextPage, materialQuery.value)
    if (!current()) return
    materialPage.value = nextPage; materialTotal.value = result.total
    materialOptions.value = result.data.filter(row => row.status === 'active'); selectedMaterial.value = ''
    for (const row of result.data) materialReferences[`${row.id}:${row.version}`] = { code: row.code, name: row.data.name }
  } catch (e) { if (current()) error.value = errorMessage(e) }
}
function addMaterial() {
  const selected = materialOptions.value.find(row => row.id === selectedMaterial.value)
  if (!selected) return
  const data = selected.data as MaterialData
  bom.requirements.push({ material_id: selected.id, material_version: selected.version, part_codes: [], quantity_per_set: '', unit: data.unit, required_for_cutting: true, stage: '裁剪', note: '' })
}
function materialLabel(id: string, version: number) {
  const option = materialReferences[`${id}:${version}`]
  return option ? `${option.code} · ${option.name} / V${version}` : `物料资料待核对 / V${version}`
}
function submit() {
  if (saving.value || pending.value) return
  pendingUncertain.value = false; needsLogin.value = false
  const data = kind.value === 'material' ? material : kind.value === 'resource' ? resource : bom
  pending.value = { type: 'save', id: editing.value?.id, body: JSON.parse(JSON.stringify({ factory_id: CUTTING_FACTORY, operation_id: crypto.randomUUID(), expected_version: editing.value?.version ?? 0, reason: reason.value, kind: kind.value, code: code.value, data })) }
  void executePending()
}
function confirmTransition() {
  if (saving.value || pending.value) return
  const record = transition.value
  if (!record) return
  pendingUncertain.value = false; needsLogin.value = false
  pending.value = { type: 'state', id: record.id, body: { factory_id: CUTTING_FACTORY, operation_id: crypto.randomUUID(), expected_version: record.version, reason: transitionReason.value, status: record.kind === 'bom' ? 'published' : record.status === 'active' ? 'inactive' : 'active' } }
  void executePending()
}
async function executePending() {
  if (!pending.value || saving.value) return
  saving.value = true; error.value = ''; notice.value = ''
  const command = pending.value
  try {
    const saved = command.type === 'save' ? await cuttingApi.save(command.body, command.id) : await cuttingApi.state(command.id, command.body)
    if (!alive) return
    pending.value = null; pendingUncertain.value = false; needsLogin.value = false
    editor.value = false; transition.value = null; history.value = null
    notice.value = `已保存 ${saved.code}，版本 V${saved.version}（${statuses[saved.status]}）。`
    await load()
  } catch (e) {
    if (!alive) return
    const status = (e as { response?: { status?: number } })?.response?.status
    error.value = errorMessage(e)
    // A retry rejection cannot establish whether an earlier timed-out attempt committed.
    if (status && status < 500 && status !== 408 && !pendingUncertain.value) pending.value = null
    else {
      pendingUncertain.value = true
      error.value += ' 保存结果尚未确认，请使用“重试原操作”，不要另建记录。'
    }
    if (status === 401 || status === 403) { access.value = null; records.value = []; editor.value = false; transition.value = null; history.value = null }
    if (status === 401 && pending.value) {
      needsLogin.value = true
      error.value += ' 请在新标签页重新登录，再返回此页重试原操作。'
    }
  } finally { saving.value = false }
}
async function showHistory(record: MasterRecord, nextPage = 1) {
  history.value = record; historyRows.value = []; historyBusy.value = true; error.value = ''
  try {
    const result = await cuttingApi.versions(record.id, nextPage)
    if (!alive || history.value?.id !== record.id) return
    historyRows.value = result.data; historyPage.value = nextPage; historyTotal.value = result.total
    for (const row of result.data) Object.assign(materialReferences, row.material_references ?? {})
  } catch (e) { error.value = errorMessage(e) }
  finally { historyBusy.value = false }
}
function parts(data: MasterRecord['data']) { return (data as BomData).parts ?? [] }
function requirements(data: MasterRecord['data']) { return (data as BomData).requirements ?? [] }
</script>

<template>
  <section class="cutting-page cutting-master">
    <header class="cutting-page-heading"><div><p class="cutting-eyebrow">华康 C / 裁床部</p><h1>基础资料</h1><p>登记物料、执行方及工程生产 BOM；修订保留原版本。</p></div><span class="cutting-status">基础资料 · P1b</span></header>
    <p class="cutting-notice">BOM 中可分别指定当前裁剪必需料和后续辅料。工作日历、单位换算及订单接入将在后续批次开放。</p>
    <p v-if="error" role="alert" class="cutting-error">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
    <button v-if="pending" type="button" :disabled="saving" @click="executePending">重试原操作</button>
    <a v-if="pending && needsLogin" href="/login" target="_blank" rel="noopener noreferrer">在新标签页重新登录</a>
    <div class="cutting-panel">
      <nav class="cutting-section-nav" aria-label="基础资料分类"><button v-for="(label, key) in labels" :key="key" :disabled="saving || !!pending" :aria-pressed="kind === key" @click="switchKind(key)">{{ label }}</button></nav>
      <p v-if="loading" role="status" class="cutting-master-message">正在读取基础资料…</p>
      <div v-else-if="!available" class="cutting-master-message"><p>{{ access ? '基础资料尚未启用，请由管理员完成迁移与启用。' : '基础资料暂不可读取，请检查账号权限或服务状态。' }}</p><button type="button" @click="load">重新检查</button></div>
      <template v-else>
        <div class="cutting-master-toolbar"><form @submit.prevent="page = 1; load()"><label>资料编码 <input v-model="query" maxlength="80" /></label><button :disabled="saving || !!pending">查询</button></form><button v-if="canEdit" :disabled="saving || !!pending" type="button" @click="openEditor()">新增资料</button><span v-else>当前为只读</span></div>
        <div class="cutting-table-scroll"><table><thead><tr><th>编码</th><th>名称</th><th>版本</th><th>状态</th><th>资料来源</th><th>操作</th></tr></thead><tbody>
          <tr v-for="row in records" :key="row.id"><td>{{ row.code }}</td><td>{{ row.data.name }}</td><td>V{{ row.version }}</td><td>{{ statuses[row.status] }}</td><td>{{ row.data.source_reference }}</td><td class="cutting-master-actions">
            <button :disabled="saving || !!pending" @click="showHistory(row)">版本记录</button><button v-if="canEdit && row.status !== 'inactive'" :disabled="saving || !!pending" @click="openEditor(row)">{{ row.kind === 'bom' ? '修订草稿' : '修订' }}</button>
            <button v-if="row.kind === 'bom' ? row.status === 'draft' && can('bom_publish') : can('master_write')" :disabled="saving || !!pending" @click="openTransition(row)">{{ row.kind === 'bom' ? '发布' : row.status === 'active' ? '停用' : '启用' }}</button>
          </td></tr><tr v-if="!records.length"><td colspan="6">暂无符合条件的资料</td></tr>
        </tbody></table></div>
        <div class="cutting-master-toolbar"><span>共 {{ total }} 条 · 第 {{ page }} 页</span><button :disabled="page <= 1 || saving || !!pending" @click="page--; load()">上一页</button><button :disabled="page * 50 >= total || saving || !!pending" @click="page++; load()">下一页</button></div>
      </template>
    </div>
    <form v-if="editor && available" class="cutting-panel cutting-master-form" @submit.prevent="submit">
      <h2>{{ editing ? '修订' : '新增' }}{{ labels[kind] }}</h2><p v-if="kind === 'bom'">保存为草稿，需具有工程发布权限的人员核对后发布。已发布版本继续保留。</p>
      <fieldset :disabled="saving || !!pending"><div class="cutting-master-fields">
        <label>资料编码<input v-model="code" required maxlength="80" :disabled="!!editing" /></label>
        <template v-if="kind === 'material'">
          <label>物料名称<input v-model="material.name" required maxlength="120" /></label><label>类别<select v-model="material.category"><option value="fabric">布料</option><option value="accessory">辅料</option></select></label><label>基本单位<input v-model="material.unit" required maxlength="120" placeholder="如：米" /></label><label>规格<input v-model="material.specification" maxlength="200" /></label><label>颜色<input v-model="material.color" maxlength="120" /></label><label>权威物料编码／资料来源<input v-model="material.source_reference" required maxlength="120" /></label>
        </template>
        <template v-else-if="kind === 'resource'">
          <label>执行方名称<input v-model="resource.name" required maxlength="120" /></label><label>执行方式<select v-model="resource.execution"><option value="internal">本厂裁剪</option><option value="outsourced">外发裁剪</option></select></label><label>负责人／联系资料<input v-model="resource.contact" maxlength="120" /></label><label>资料来源<input v-model="resource.source_reference" required maxlength="120" /></label>
        </template>
        <template v-else>
          <label>产品名称<input v-model="bom.name" required maxlength="120" /></label><label>货号<input v-model="bom.item_no" required maxlength="80" /></label><label>款式／规格<input v-model="bom.style" required maxlength="120" /></label><label>颜色<input v-model="bom.color" required maxlength="120" /></label><label>工程生产 BOM 来源／版本号<input v-model="bom.source_reference" required maxlength="120" /></label>
        </template>
      </div>
      <template v-if="kind === 'bom'">
        <h3>每套部件构成</h3><div v-for="(part, i) in bom.parts" :key="i" class="cutting-master-fields cutting-master-line"><label>部件编码<input v-model="part.code" required maxlength="80" /></label><label>部件名称<input v-model="part.name" required maxlength="120" /></label><label>每套裁片数<input v-model.number="part.pieces_per_set" type="number" min="1" max="100000" step="1" required /></label><button type="button" @click="bom.parts.splice(i, 1)">移除部件</button></div><button type="button" @click="bom.parts.push({ code: '', name: '', pieces_per_set: 1 })">添加部件</button>
        <h3>物料用量与当前阶段必需料</h3><div class="cutting-master-toolbar"><label>按物料编码查询<input v-model="materialQuery" maxlength="80" /></label><button type="button" @click="findMaterials()">查询物料</button><select v-model="selectedMaterial" aria-label="选择物料版本"><option value="">请选择有效物料</option><option v-for="option in materialOptions" :key="option.id" :value="option.id">{{ option.code }} · {{ option.data.name }} / V{{ option.version }}</option></select><button type="button" :disabled="!selectedMaterial" @click="addMaterial">加入 BOM</button><button v-if="materialPage > 1" type="button" @click="findMaterials(materialPage - 1)">上一批物料</button><button v-if="materialPage * 50 < materialTotal" type="button" @click="findMaterials(materialPage + 1)">下一批物料</button></div>
        <section v-for="(row, i) in bom.requirements" :key="i" class="cutting-master-line"><p>{{ materialLabel(row.material_id, row.material_version) }}</p><div class="cutting-master-fields"><label>每套净用量（{{ row.unit }}）<input v-model="row.quantity_per_set" type="number" min="0.000001" step="0.000001" required /></label><label>适用部件（可多选）<select v-model="row.part_codes" multiple required><option v-for="part in bom.parts" :key="part.code" :value="part.code">{{ part.code }} · {{ part.name }}</option></select></label><label>适用阶段<input v-model="row.stage" required maxlength="120" /></label><label class="cutting-master-checkbox"><input v-model="row.required_for_cutting" type="checkbox" />当前裁剪必需物料</label><label>未到料影响／备注<input v-model="row.note" maxlength="300" /></label><button type="button" @click="bom.requirements.splice(i, 1)">移除物料</button></div></section>
        <p>未勾选的辅料继续跟进，但不统一阻止裁剪排期。当前仅配置用量依据，不计算库存或自动排期。</p>
      </template>
      <label>登记／修订原因<input v-model="reason" required maxlength="500" /></label><div class="cutting-master-toolbar"><button type="submit">{{ kind === 'bom' ? '保存草稿' : '保存资料' }}</button><button type="button" @click="closeEditor">取消</button></div></fieldset>
    </form>
    <form v-if="transition && available" class="cutting-panel cutting-master-form" @submit.prevent="confirmTransition"><h2>{{ transition.kind === 'bom' ? '确认发布 BOM' : '确认变更资料状态' }}：{{ transition.code }}</h2><p>本次操作保留原资料版本及操作依据。</p><fieldset :disabled="saving || !!pending"><label>核对依据／原因<input v-model="transitionReason" required maxlength="500" /></label><div class="cutting-master-toolbar"><button>确认</button><button type="button" @click="closeTransition">取消</button></div></fieldset></form>
    <section v-if="history && available" class="cutting-panel cutting-master-form"><h2>{{ history.code }} · 版本记录</h2><p v-if="historyBusy">正在读取版本…</p><details v-for="revision in historyRows" :key="revision.version"><summary>V{{ revision.version }} · {{ statuses[revision.status] }} · {{ businessTime(revision.created_at) }}</summary><p>{{ revision.data.name }} · 来源：{{ revision.data.source_reference }}</p><p>操作人：{{ revision.actor_id }} · 原因：{{ revision.reason }}</p>
      <dl v-if="revision.kind !== 'bom'"><template v-for="(value, key) in revision.data" :key="key"><dt>{{ fieldLabels[key] ?? key }}</dt><dd>{{ valueLabels[String(value)] ?? value }}</dd></template></dl>
      <template v-else><p>货号：{{ (revision.data as BomData).item_no }} · 款式：{{ (revision.data as BomData).style }} · 颜色：{{ (revision.data as BomData).color }}</p><ul><li v-for="part in parts(revision.data)" :key="part.code">{{ part.code }} · {{ part.name }}：每套 {{ part.pieces_per_set }} 片</li></ul><ul><li v-for="(row, i) in requirements(revision.data)" :key="i">{{ materialLabel(row.material_id, row.material_version) }}：每套 {{ row.quantity_per_set }} {{ row.unit }}；部件 {{ row.part_codes.join('、') }}；{{ row.stage }}；{{ row.required_for_cutting ? '裁剪必需' : '后续辅料' }}；{{ row.note }}</li></ul></template>
    </details><div class="cutting-master-toolbar"><button :disabled="historyPage <= 1 || historyBusy" @click="showHistory(history, historyPage - 1)">较新版本</button><button :disabled="historyPage * 50 >= historyTotal || historyBusy" @click="showHistory(history, historyPage + 1)">较早版本</button><button @click="history = null">关闭记录</button></div></section>
  </section>
</template>
