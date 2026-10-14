<script setup lang="ts">
import { computed, inject, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, type RouteLocationNormalized } from 'vue-router'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { Button } from '@/components/ui/button'
import { fabricMasterApi as api, type MasterKind, type MasterRecord, type MasterCandidate, type SaveMasterRequest, type MasterFields, type MasterStatus } from '@/api/fabricMaster'
import { getApiErrorMessage } from '@/lib/http'
import { warehouseRequestId } from './requestIdentity'
import FabricLocationSettings from './FabricLocationSettings.vue'
import { purchaseSearchKey } from './purchaseSearch'
import { Database, Plus } from '@lucide/vue'
import { useAuthStore } from '@/stores/auth'
import { pendingFabricMasterSaves } from './pendingFabricRequests'

const props = defineProps<{ view: string }>()
const auth = useAuthStore()
const pendingSave = computed(() => pendingFabricMasterSaves.get(auth.currentUser?.id ?? ''))
const saving = computed(() => !!pendingSave.value?.inFlight)
let authGeneration = 0
const kinds: Record<string, MasterKind> = { items: 'MATERIAL', partners: 'SUPPLIER', locations: 'LOCATION', units: 'UNIT' }
const kind = computed(() => kinds[props.view] ?? 'MATERIAL')
const titles = { MATERIAL: '物料资料', SUPPLIER: '供应商资料', LOCATION: '仓库与仓位', UNIT: '计量单位' }
const help = { MATERIAL: '现阶段在这里补齐编码、名称、分类和库存单位，确认后启用；规格、颜色和材质按已确认资料填写。', SUPPLIER: '采购模块接入前在这里维护供应商编号、名称及状态，联系人和电话选填；固定编号用于送货识别与收料对账。', LOCATION: '设置仓位适用的原料，入库时按分类选择对应架位或区域；通用仓位适用所有分类，历史单据保留。', UNIT: '维护码、米、卷等标准单位。物料换算仅在有依据时填写；当前收料按来源单位记账，不自动换算。' }
const labels: Record<keyof MasterFields, string> = { category: '物料分类', unit: '库存单位', old_code: '旧编码', spec: '规格', color: '颜色', composition: '材质 / 成分', contact: '联系人', phone: '联系电话', warehouse: '所属仓库', material_code: '适用物料编码', price_unit: '计价单位', ratio: '换算系数（1库存单位＝多少计价单位）', evidence: '换算依据', conditions: '适用条件', effective_date: '生效日期', note: '备注' }
const fieldLabel = (field: keyof MasterFields) => kind.value === 'LOCATION' && field === 'category' ? '适用原料' : labels[field]
const fields = computed<(keyof MasterFields)[]>(() => ({ MATERIAL: ['category','unit','old_code','spec','color','composition'], SUPPLIER: ['contact','phone'], LOCATION: ['warehouse','category'], UNIT: ['unit','material_code','price_unit','ratio','evidence','conditions','effective_date'] }[kind.value] as (keyof MasterFields)[]))
const statusNames: Record<MasterStatus, string> = { DRAFT: '待完善', ACTIVE: '启用', INACTIVE: '停用' }
const deletedLocations = ref<MasterRecord[]>([])
const records = ref<MasterRecord[]>([]), candidates = ref<MasterCandidate[]>([]), canManage = ref(false)
const headerSearch = inject(purchaseSearchKey, undefined)
const search = headerSearch?.search ?? ref(''), status = ref('ALL'), sort = ref('CODE'), offset = ref(0), candidateOffset = ref(0), showCandidates = ref(false)
const category = ref('ALL'), unitMode = ref('ALL'), unitFormMode = ref('STANDARD'), locationOpen = ref(false)
const standardUnits = ref<MasterRecord[]>([]), confirmedMaterials = ref<MasterRecord[]>([])
const warehouseTokens = ref<Record<string, string>>({})
const busy = ref(false), error = ref(''), notice = ref(''), candidateError = ref('')
const draft = ref<SaveMasterRequest>(), initialDraft = ref(''), submitted = ref<SaveMasterRequest>(), candidateConflict = ref<MasterCandidate>()
const changes = ref<Awaited<ReturnType<typeof api.history>>>([]), historyOpen = ref(false)
let sequence = 0, alive = true, deferredLoad = false
const filtered = computed(() => records.value.filter(row => kind.value !== 'MATERIAL' || category.value === 'ALL' || (row.data.category || 'UNCLASSIFIED') === category.value)
  .filter(row => kind.value !== 'UNIT' || unitMode.value === 'ALL' || (row.data.ratio ? 'CONVERSION' : 'STANDARD') === unitMode.value))
const displayed = computed(() => filtered.value.slice(offset.value, offset.value + 50))
const mainFields = computed<(keyof MasterFields)[]>(() => kind.value === 'MATERIAL' ? ['category','unit'] : kind.value === 'SUPPLIER' ? ['contact','phone'] : kind.value === 'LOCATION' ? ['warehouse','category'] : unitFormMode.value === 'CONVERSION' ? fields.value : [])
const optionalFields = computed(() => kind.value === 'MATERIAL' ? fields.value.filter(field => !mainFields.value.includes(field)) : [])
const filteredCandidates = computed(() => candidates.value.filter(row => !search.value.trim() || [row.code, row.name, row.data.unit, row.data.old_code].join(' ').toLocaleLowerCase().includes(search.value.trim().toLocaleLowerCase())))
const displayedCandidates = computed(() => filteredCandidates.value.slice(candidateOffset.value, candidateOffset.value + 20))
const dirty = computed(() => !!draft.value && JSON.stringify(draft.value) !== initialDraft.value)
function clone<T>(value: T): T { return JSON.parse(JSON.stringify(value)) as T }
function leave(to?: RouteLocationNormalized) {
  if (to?.name === 'login' || to?.name === 'forbidden') return true
  if (saving.value || pendingSave.value) { error.value = '保存结果尚未确认，请先核对原保存结果。'; return false }
  return !dirty.value || window.confirm('资料尚未保存，确定离开？')
}
onBeforeRouteLeave(leave); onBeforeRouteUpdate(leave); onBeforeUnmount(() => { alive = false; sequence++ })
function closeDraft() { if (!saving.value && (pendingSave.value || leave())) { draft.value = undefined; submitted.value = undefined } }
function beforeUnload(event: BeforeUnloadEvent) { if (pendingSave.value) { event.preventDefault(); event.returnValue = '' } }
window.addEventListener('beforeunload', beforeUnload)
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
async function load() {
  const ticket = ++sequence; busy.value = true; error.value = ''; canManage.value = false; records.value = []; deletedLocations.value = []; candidates.value = []; candidateError.value = ''; standardUnits.value = []; confirmedMaterials.value = []; warehouseTokens.value = {}
  if (saving.value) { deferredLoad = true; return }
  deferredLoad = false
  const requestedKind = kind.value
  try { const result = await api.list(kind.value, kind.value === 'LOCATION' ? '' : search.value.trim(), kind.value === 'LOCATION' ? 'ALL' : status.value, sort.value); if (ticket !== sequence) return
    records.value = result.items; deletedLocations.value = result.deleted_items ?? []; canManage.value = result.can_manage; warehouseTokens.value = result.warehouse_tokens ?? {}
    if (requestedKind === 'MATERIAL' || showCandidates.value) {
      try { const result = await api.candidates(requestedKind); if (ticket === sequence) candidates.value = result }
      catch (e) { if (ticket === sequence) candidateError.value = getApiErrorMessage(e) }
      if (ticket !== sequence) return
    }
    if (kind.value === 'MATERIAL' || kind.value === 'UNIT') { const result = await api.list(kind.value === 'MATERIAL' ? 'UNIT' : 'MATERIAL', '', 'ACTIVE'); if (ticket === sequence) { standardUnits.value = kind.value === 'MATERIAL' ? result.items.filter(row => !row.data.ratio) : []; confirmedMaterials.value = kind.value === 'UNIT' ? result.items : [] } }
  } catch (e) { if (ticket === sequence) error.value = getApiErrorMessage(e) }
  finally { if (ticket === sequence) busy.value = false }
}
watch(saving, pending => { if (!pending && deferredLoad) void load() })
watch(() => props.view, () => { search.value = ''; status.value = 'ALL'; sort.value = 'CODE'; category.value = 'ALL'; unitMode.value = 'ALL'; offset.value = 0; candidateOffset.value = 0; showCandidates.value = kind.value === 'MATERIAL'; draft.value = undefined; submitted.value = undefined; historyOpen.value = false; notice.value = ''; void load() }, { immediate: true })
watch([() => auth.currentUser?.id, () => auth.authorizationVersion], () => {
  authGeneration++; sequence++; canManage.value = false; draft.value = undefined; submitted.value = undefined
  changes.value = []; historyOpen.value = false; candidateConflict.value = undefined; notice.value = ''
  search.value = ''; void load()
}, { flush: 'sync' })
watch(() => headerSearch?.submitted.value, () => query())
watch([category, unitMode, search], () => { offset.value = 0; candidateOffset.value = 0 })
function query() { offset.value = 0; candidateOffset.value = 0; void load() }
function edit(record?: MasterRecord, candidate?: MasterCandidate) {
  if (!canManage.value || busy.value || pendingSave.value) return
  candidateConflict.value = candidate
  unitFormMode.value = record?.data.ratio ? 'CONVERSION' : 'STANDARD'
  draft.value = { factory_id: 'huakang-c', request_id: warehouseRequestId(), id: record?.id ?? null, expected_revision: record?.revision ?? 0,
    kind: kind.value, code: record?.code ?? candidate?.code ?? '', name: record?.name ?? candidate?.name ?? '', status: record?.status ?? 'DRAFT', data: clone(record?.data ?? candidate?.data ?? {}) }
  initialDraft.value = JSON.stringify(draft.value); submitted.value = undefined; error.value = ''
}
function fieldRequired(field: keyof MasterFields) { return draft.value?.status === 'ACTIVE' && (kind.value === 'MATERIAL' && ['category','unit'].includes(field) || kind.value === 'LOCATION' && field === 'warehouse') || kind.value === 'UNIT' && unitFormMode.value === 'CONVERSION' && fields.value.includes(field) }
function fieldLimit(field: keyof MasterFields) { return field === 'evidence' || field === 'conditions' ? 1000 : field === 'phone' ? 64 : ['unit','price_unit','ratio'].includes(field) ? 32 : ['old_code','color','contact','warehouse','material_code'].includes(field) ? 128 : 255 }
function newConversion() { edit(); unitFormMode.value = 'CONVERSION' }
async function save() {
  if (!draft.value || saving.value || !canManage.value) return
  if (!submitted.value && kind.value === 'UNIT' && unitFormMode.value === 'CONVERSION' && fields.value.some(field => !draft.value?.data[field])) { error.value = '换算资料须补齐物料、两种单位、系数、依据、条件和生效日期。'; return }
  submitted.value ??= clone({ ...draft.value, data: { ...draft.value.data, effective_date: draft.value.data.effective_date || null } })
  if (!pendingSave.value) pendingFabricMasterSaves.set(auth.currentUser?.id ?? '', { body: submitted.value, actorId: auth.currentUser?.id, inFlight: false })
  const request = pendingSave.value!
  if (request.actorId !== auth.currentUser?.id) return
  const generation = authGeneration
  request.inFlight = true; error.value = ''
  try { await api.save(request.body); pendingFabricMasterSaves.delete(request.actorId ?? ''); if (!alive || generation !== authGeneration) return; draft.value = undefined; submitted.value = undefined; notice.value = '资料已保存；历史入库单保留当时的资料。'; await load() }
  catch (e) {
    const code = (e as { response?: { status?: number } }).response?.status
    if (code && code < 500 && ![401,403,408,429].includes(code)) pendingFabricMasterSaves.delete(request.actorId ?? '')
    if (!alive || generation !== authGeneration) return
    error.value = getApiErrorMessage(e)
    if ([401,403,404,409].includes(code ?? 0)) { draft.value = undefined; submitted.value = undefined; await load(); error.value = getApiErrorMessage(e) }
    else if (!pendingSave.value) submitted.value = undefined
  } finally { request.inFlight = false }
}
function retrySave() {
  if (!pendingSave.value || pendingSave.value.actorId !== auth.currentUser?.id || !canManage.value || saving.value) return
  draft.value = clone(pendingSave.value.body); submitted.value = pendingSave.value.body
  void save()
}
async function history(record: MasterRecord) { const ticket = ++sequence; busy.value = true; error.value = ''; changes.value = []
  try { const result = await api.history(record.id); if (ticket === sequence) { changes.value = result; historyOpen.value = true } }
  catch (e) { if (ticket === sequence) error.value = getApiErrorMessage(e) }
  finally { if (ticket === sequence) busy.value = false }
}
function deletedRecord(record: Partial<MasterRecord>) { return !!(record.data as Record<string, unknown> | undefined)?._deleted }
function changedFields(before: Partial<MasterRecord>, after: MasterRecord) { return Object.keys({ ...before.data, ...after.data }).filter(field => field in labels) as (keyof MasterFields)[] }
function shown(value: unknown) { return value == null || value === '' ? '—' : String(value) }
function categoryLabel(value: unknown) { return value === 'FABRIC' ? '布料' : value === 'ACCESSORY' ? '辅料' : value === 'THREAD' ? '线' : '待分类' }
</script>

<template>
  <div class="fabric-master-workspace">
    <div v-if="kind !== 'LOCATION'" class="fabric-master-card-heading"><div><h2><Database :size="18" />{{ titles[kind] }}</h2><p>{{ help[kind] }}</p></div><div class="fabric-master-tools"><Button v-if="canManage" size="sm" :disabled="busy" @click="edit()"><Plus :size="14" />新增资料</Button><Button v-if="canManage && kind === 'UNIT'" size="sm" variant="outline" :disabled="busy" @click="newConversion">新增物料换算</Button><Button v-if="kind !== 'MATERIAL'" size="sm" variant="outline" :disabled="busy" @click="showCandidates = !showCandidates; candidateOffset = 0; load()">{{ showCandidates ? '收起导入候选' : '查看导入候选' }}</Button></div></div>
    <div v-if="kind === 'MATERIAL'" class="fabric-material-intake">
      <div><strong>采购物料自动归集</strong><p>采购表中的编码、名称和单位自动带入待确认列表；核对分类后保存并启用。已建档编码不重复新增。</p></div>
      <Button variant="outline" size="sm" :disabled="busy" @click="query">{{ busy ? '正在读取…' : '刷新归集' }}</Button>
    </div>
    <nav v-if="kind === 'MATERIAL'" class="fabric-material-views" aria-label="物料资料范围">
      <button :aria-pressed="showCandidates" @click="showCandidates = true">待确认物料 <span>{{ busy || candidateError || error ? '—' : filteredCandidates.length }}</span></button>
      <button :aria-pressed="!showCandidates" @click="showCandidates = false">已建档资料</button>
    </nav>
    <details v-if="kind === 'UNIT'" class="fabric-unit-guide"><summary>计量单位怎么用？</summary><ol><li><strong>先建标准单位</strong>：例如编码 YD、名称“码”，核对后设为启用。编码和名称各自保持唯一。</li><li><strong>物料选择库存单位</strong>：在物料资料选择“码”。同一种物料尽量统一用同一单位登记，入库和出库核对原单位。</li><li><strong>按原单位看库存</strong>：例如实收 100 码、发出 20 码，结存 80 码；米、公斤分别统计。</li></ol><p>“新增物料换算”用于保存有依据的计价换算资料，目前不会自动换算实收、库存或价格。每卷长度不同，不能统一设为“1 卷＝固定码数”。</p></details>
    <p v-if="pendingSave && !draft" class="fabric-message" role="status">资料保存结果尚未确认。<Button v-if="pendingSave.actorId === auth.currentUser?.id && canManage" variant="outline" size="sm" :disabled="busy || saving" @click="retrySave">核对原保存结果</Button><span v-else>请由原提交账号恢复权限后核对。</span></p>
    <p v-if="error && !draft" class="fabric-error" role="alert">{{ error }}</p><p v-if="notice" class="fabric-success" role="status">{{ notice }}</p>
    <form v-if="!headerSearch || kind !== 'MATERIAL' || !showCandidates" class="fabric-master-filters" @submit.prevent="query"><fieldset :disabled="busy || locationOpen" class="fabric-filter-bar"><label v-if="!headerSearch" class="fabric-master-search">查找资料<input v-model="search" aria-label="基础资料关键字" type="search" maxlength="128" placeholder="编码 / 名称 / 规格 / 仓库" /></label><label v-if="kind !== 'MATERIAL' || !showCandidates">状态<select v-model="status" aria-label="基础资料状态" @change="query"><option value="ALL">全部状态</option><option value="DRAFT">待完善</option><option value="ACTIVE">启用</option><option value="INACTIVE">停用</option></select></label><label v-if="kind === 'MATERIAL' && !showCandidates">分类<select v-model="category" aria-label="基础物料分类"><option value="ALL">全部分类</option><option value="FABRIC">布料</option><option value="ACCESSORY">辅料</option><option value="THREAD">线</option><option value="UNCLASSIFIED">待分类</option></select></label><label v-if="kind === 'UNIT'">类型<select v-model="unitMode" aria-label="单位资料类型"><option value="ALL">全部类型</option><option value="STANDARD">标准单位</option><option value="CONVERSION">物料换算</option></select></label><label v-if="kind !== 'MATERIAL' || !showCandidates">排序<select v-model="sort" aria-label="基础资料排序" @change="query"><option value="CODE">编码顺序</option><option value="NAME">名称顺序</option><option value="UPDATED">最近更新</option></select></label><Button variant="outline" size="sm" type="submit">查询</Button><Button variant="ghost" size="sm" type="button" @click="search = ''; status = 'ALL'; sort = 'CODE'; category = 'ALL'; unitMode = 'ALL'; query()">清空筛选</Button><span class="fabric-master-count">{{ kind === 'MATERIAL' && showCandidates ? (busy || candidateError || error ? '—' : filteredCandidates.length) : kind === 'LOCATION' ? records.length : filtered.length }} {{ kind === 'MATERIAL' && showCandidates ? '项待确认' : '条资料' }}</span></fieldset></form>
    <p v-if="busy" class="fabric-message" role="status">正在查询资料…</p><p v-else-if="!canManage" class="fabric-master-note">当前账号可查看，资料维护由负责人办理。</p>
    <FabricLocationSettings v-if="kind === 'LOCATION'" :records="records" :deleted-records="deletedLocations" :warehouse-tokens="warehouseTokens" :can-manage="canManage" :busy="busy" :search="search" :status="status" @edit="edit($event)" @history="history($event)" @refresh="load" @locked="locationOpen = $event" />
    <template v-else>
    <section v-if="showCandidates" class="fabric-master-candidates"><div class="fabric-master-candidate-heading"><div><h3>{{ kind === 'MATERIAL' ? '待确认物料 · 自动归集' : '导入候选 · 尚未建立资料' }}</h3><p>{{ kind === 'MATERIAL' ? '仅归集当前已导入的采购来源；如有名称或单位冲突，请先核对原采购资料。' : '核对来源并补齐后保存；供应商编码由人工确认。' }}</p></div><span>{{ busy || candidateError || error ? '—' : filteredCandidates.length }} 条候选</span></div><p v-if="candidateError" class="fabric-error" role="alert">自动归集读取失败：{{ candidateError }}。请刷新重试。</p><div class="fabric-candidate-grid"><article v-for="row in displayedCandidates" :key="row.key"><strong>{{ row.code || '编码待填写' }} · {{ row.name }}</strong><small>{{ row.source_count }} 条采购来源<template v-if="row.data.unit"> · {{ row.data.unit }}</template></small><p v-if="row.conflict" class="fabric-row-error">同编码有不同名称或单位，请核对。</p><Button v-if="canManage" variant="outline" size="sm" :disabled="busy" @click="edit(undefined, row)">{{ kind === 'MATERIAL' ? '核对并建档' : '补齐资料' }}</Button></article></div><p v-if="!filteredCandidates.length && !busy && !candidateError && !error">暂无未建档的导入候选。</p><footer class="warehouse-list-footer"><span>显示 {{ displayedCandidates.length }} 条候选</span><div><Button variant="outline" size="sm" :disabled="candidateOffset === 0" @click="candidateOffset -= 20">上一页候选</Button><Button variant="outline" size="sm" :disabled="candidateOffset + 20 >= filteredCandidates.length" @click="candidateOffset += 20">下一页候选</Button></div></footer></section>
    <template v-if="kind !== 'MATERIAL' || !showCandidates"><div class="warehouse-table-scroll" role="region" aria-label="布料仓基础资料列表" tabindex="0"><table class="fabric-master-table"><thead><tr><th>{{ kind === 'SUPPLIER' ? '供应商编号 / 名称' : '编码 / 名称' }}</th><template v-if="kind === 'MATERIAL'"><th>分类 / 单位</th><th>规格 / 颜色 / 材质</th></template><template v-else-if="kind === 'SUPPLIER'"><th>联系人</th><th>联系电话</th></template><template v-else><th>类型 / 适用物料</th><th>单位 / 换算关系</th><th>依据 / 生效日期</th></template><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="row in displayed" :key="row.id"><td><strong>{{ row.code }}</strong><span>{{ row.name }}</span><small v-if="row.data.old_code">旧编码 {{ row.data.old_code }}</small></td><template v-if="kind === 'MATERIAL'"><td>{{ categoryLabel(row.data.category) }}<span>{{ shown(row.data.unit) }}</span></td><td><span>{{ shown(row.data.spec) }}</span><small>{{ [row.data.color, row.data.composition].filter(Boolean).join(' · ') || '颜色、材质待补充' }}</small></td></template><template v-else-if="kind === 'SUPPLIER'"><td>{{ shown(row.data.contact) }}</td><td>{{ shown(row.data.phone) }}</td></template><template v-else><td>{{ row.data.ratio ? '物料换算' : '标准单位' }}<small v-if="row.data.material_code">{{ row.data.material_code }}</small></td><td>{{ row.data.ratio ? `1 ${row.data.unit} = ${row.data.ratio} ${row.data.price_unit}` : row.name }}</td><td><span>{{ shown(row.data.evidence) }}</span><small v-if="row.data.effective_date">{{ row.data.effective_date }} 起 · {{ row.data.conditions }}</small></td></template><td><span class="fabric-master-status" :data-status="row.status">{{ statusNames[row.status] }}</span></td><td><div class="fabric-master-row-actions"><Button v-if="canManage" size="sm" variant="outline" :disabled="busy" @click="edit(row)">修改资料</Button><Button variant="ghost" size="sm" :disabled="busy" @click="history(row)">修改记录</Button></div></td></tr></tbody></table></div>
    <div v-if="!busy && !filtered.length" class="fabric-master-empty"><Database :size="28" /><h3>暂无符合条件的资料</h3><p>可调整筛选，或从采购导入候选补齐资料。</p></div><footer class="warehouse-list-footer"><span>共 {{ filtered.length }} 条 · {{ filtered.length ? offset + 1 : 0 }}–{{ Math.min(offset + 50, filtered.length) }}</span><div><Button variant="outline" size="sm" :disabled="!offset || busy" @click="offset -= 50">上一页</Button><Button variant="outline" size="sm" :disabled="offset + 50 >= filtered.length || busy" @click="offset += 50">下一页</Button></div></footer></template>
    </template>
  </div>
  <DialogRoot :open="!!draft" @update:open="value => { if (!value) closeDraft() }"><DialogPortal><DialogOverlay class="warehouse-guide-overlay" /><DialogContent class="warehouse-guide fabric-edit-dialog fabric-master-dialog"><header class="warehouse-guide-heading"><div><DialogTitle>{{ candidateConflict && kind === 'MATERIAL' ? '核对并建立' : draft?.id ? '修改' : '新增' }}{{ titles[kind] }}</DialogTitle><DialogDescription>{{ help[kind] }}</DialogDescription></div><Button variant="ghost" size="sm" :disabled="saving" @click="closeDraft">关闭</Button></header><form v-if="draft" class="warehouse-guide-body fabric-master-form" @submit.prevent="save"><p v-if="candidateConflict && kind === 'MATERIAL'" class="fabric-intake-alert">已带入采购来源资料。核对名称、分类和库存单位后，将状态选为“启用（已确认资料）”再保存；未核对完整可先保存为“待完善”。</p><p v-if="candidateConflict?.conflict" class="fabric-intake-alert">该编码在采购表有多种资料，请确认正确名称和单位：{{ candidateConflict.variants.map(v => `${v.name} · ${v.unit}`).join('；') }}</p><fieldset :disabled="saving || !!submitted"><legend>基本资料</legend><label>{{ kind === 'SUPPLIER' ? '供应商编号' : kind === 'LOCATION' ? '仓位编码' : '编码' }} <span>*</span><input v-model="draft.code" :aria-label="kind === 'SUPPLIER' ? '供应商编号' : '资料编码'" :readonly="!!draft.id" maxlength="128" required /><small v-if="draft.id">{{ kind === 'SUPPLIER' ? '供应商编号保留，修改名称不会改写历史单据。' : '编码保留，修改名称不会改写历史单据。' }}</small><small v-else-if="kind === 'SUPPLIER'">每家供应商一个固定编号，例如 GYS001；可沿用原系统编号。</small></label><label>{{ kind === 'LOCATION' ? '仓位名称' : '名称' }} <span>*</span><input v-model="draft.name" aria-label="资料名称" maxlength="255" required /></label><label>状态<select v-model="draft.status" aria-label="资料启用状态"><option value="DRAFT">待完善</option><option value="ACTIVE">启用（已确认资料）</option><option value="INACTIVE">停用</option></select></label><template v-for="field in mainFields" :key="field"><label :class="{ 'fabric-master-wide': field === 'evidence' || field === 'conditions' }">{{ fieldLabel(field) }} <span v-if="fieldRequired(field)">*</span><select v-if="field === 'category'" v-model="draft.data.category" :aria-label="fieldLabel(field)" :required="fieldRequired(field)"><option value="">{{ kind === 'LOCATION' ? '通用（不限原料）' : '待分类' }}</option><option value="FABRIC">布料</option><option value="ACCESSORY">辅料</option><option value="THREAD">线</option></select><select v-else-if="field === 'material_code'" v-model="draft.data.material_code" :aria-label="fieldLabel(field)" :required="fieldRequired(field)"><option value="">选择已启用物料</option><option v-if="draft.data.material_code && !confirmedMaterials.some(row => row.code === draft?.data.material_code)" :value="draft.data.material_code">{{ draft.data.material_code }}（当前未启用）</option><option v-for="row in confirmedMaterials" :key="row.id" :value="row.code">{{ row.code }} · {{ row.name }}</option></select><textarea v-else-if="field === 'evidence' || field === 'conditions'" v-model="draft.data[field]" :aria-label="fieldLabel(field)" maxlength="1000" :required="fieldRequired(field)" /><input v-else v-model="draft.data[field]" :aria-label="fieldLabel(field)" :list="field === 'unit' ? 'fabric-master-standard-units' : undefined" :readonly="kind === 'LOCATION' && !!draft.id && !!draft.data.warehouse" :type="field === 'effective_date' ? 'date' : 'text'" :inputmode="field === 'ratio' ? 'decimal' : 'text'" :maxlength="fieldLimit(field)" :required="fieldRequired(field)" /></label></template></fieldset>
    <fieldset v-if="optionalFields.length" :disabled="saving || !!submitted"><legend>补充资料 · 选填</legend><label v-for="field in optionalFields" :key="field">{{ fieldLabel(field) }}<input v-model="draft.data[field]" :aria-label="fieldLabel(field)" :maxlength="fieldLimit(field)" /></label></fieldset><fieldset :disabled="saving || !!submitted"><label class="fabric-master-wide">备注<textarea v-model="draft.data.note" aria-label="资料备注" maxlength="2000" /></label></fieldset><datalist id="fabric-master-standard-units"><option v-for="row in standardUnits" :key="row.id" :value="row.name">{{ row.code }}</option></datalist><p v-if="kind === 'UNIT'" class="fabric-master-note">{{ unitFormMode === 'CONVERSION' ? '换算系数必须有物料依据；当前只保存配置，收料不会自动换算。' : '标准单位填写编码、名称及状态即可，例如码、米、卷。' }}</p><p v-if="error" class="fabric-error" role="alert">{{ error }}</p><p v-if="submitted" class="fabric-intake-alert">保存结果待确认，内容已锁定；重试会使用同一个请求。</p><div class="fabric-dialog-actions"><Button variant="outline" type="button" :disabled="saving" @click="closeDraft">返回</Button><Button type="submit" :disabled="saving">{{ saving ? '正在保存…' : submitted ? '重试保存' : '保存资料' }}</Button></div></form></DialogContent></DialogPortal></DialogRoot>
  <DialogRoot v-model:open="historyOpen"><DialogPortal><DialogOverlay class="warehouse-guide-overlay" /><DialogContent class="warehouse-guide fabric-edit-dialog fabric-master-dialog"><header class="warehouse-guide-heading"><div><DialogTitle>资料修改记录</DialogTitle><DialogDescription>保留每次保存时的资料和经办人。</DialogDescription></div><Button variant="ghost" @click="historyOpen = false">关闭</Button></header><div class="warehouse-guide-body"><section v-for="entry in changes" :key="entry.after.revision" class="fabric-source-evidence"><h3>第 {{ entry.after.revision }} 版 · {{ entry.actor_name }}</h3><p>{{ entry.occurred_at }}</p><p>{{ entry.after.code }} · {{ entry.after.name }} · {{ deletedRecord(entry.after) ? '已删除' : deletedRecord(entry.before) ? `已恢复 · ${statusNames[entry.after.status]}` : statusNames[entry.after.status] }}</p><p v-for="field in changedFields(entry.before, entry.after)" :key="field"><template v-if="entry.before.data?.[field] !== entry.after.data[field]">{{ fieldLabel(field) }}：{{ field === 'category' ? categoryLabel(entry.before.data?.[field]) : shown(entry.before.data?.[field]) }} → {{ field === 'category' ? categoryLabel(entry.after.data[field]) : shown(entry.after.data[field]) }}</template></p></section><p v-if="!changes.length">暂无修改记录。</p></div></DialogContent></DialogPortal></DialogRoot>
</template>
