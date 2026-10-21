<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, type RouteLocationNormalized } from 'vue-router'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { Warehouse, Plus, Upload, Download } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { fabricMasterApi as api, type MasterRecord, type LocationInput, type LocationPreview, type LocationApply, type WarehouseRename, type LocationManage } from '@/api/fabricMaster'
import { locationCategoryLabels } from './fabricLocationZones'
import FabricLocationManageDialog from './FabricLocationManageDialog.vue'
import { getApiErrorMessage } from '@/lib/http'
import { warehouseRequestId } from './requestIdentity'
import { useAuthStore } from '@/stores/auth'
import { pendingFabricLocationManage } from './pendingFabricRequests'

const props = defineProps<{ records: MasterRecord[]; deletedRecords?: MasterRecord[]; warehouseTokens: Record<string, string>; canManage: boolean; busy: boolean; search: string; status: string }>()
const emit = defineEmits<{ edit: [record: MasterRecord]; history: [record: MasterRecord]; refresh: []; locked: [value: boolean] }>()
const auth = useAuthStore()
const pendingManage = computed(() => pendingFabricLocationManage.get(auth.currentUser?.id ?? ''))
const blocked = computed(() => props.busy || !!pendingManage.value)
const showDeleted = ref(false), selectedIds = ref<string[]>([]), manageAction = ref<LocationManage['action']>()
const manageRecords = ref<MasterRecord[]>([]), manageIds = ref<string[]>([])
const availableRecords = computed(() => showDeleted.value ? props.deletedRecords ?? [] : props.records)
const groups = computed(() => [...new Set(availableRecords.value.map(row => row.data.warehouse || '待补所属仓库'))].map(warehouse => ({ warehouse,
  all: availableRecords.value.filter(row => (row.data.warehouse || '待补所属仓库') === warehouse),
  places: availableRecords.value.filter(row => (row.data.warehouse || '待补所属仓库') === warehouse && (showDeleted.value || props.status === 'ALL' || row.status === props.status)
    && `${row.code} ${row.name} ${JSON.stringify(row.data)}`.toLocaleLowerCase().includes(props.search.trim().toLocaleLowerCase())),
})).filter(group => group.places.length))
const mode = ref<'warehouse' | 'bins' | 'import' | 'rename'>(), warehouse = ref(''), bins = ref(''), original = ref('')
const category = ref<NonNullable<LocationInput['category']>>('')
const groupToken = ref(''), file = ref<File>(), plan = ref<LocationPreview>(), submitted = ref<LocationApply | WarehouseRename>()
const busy = ref(false), error = ref(''), notice = ref(''), initial = ref('')
let alive = true, generation = 0
onBeforeUnmount(() => { alive = false; generation++; emit('locked', false) })
const content = () => JSON.stringify([warehouse.value, bins.value, category.value, file.value?.name, file.value?.lastModified])
const title = computed(() => mode.value === 'rename' ? '修改仓库' : mode.value === 'warehouse' ? '添加仓库' : mode.value === 'import' ? '导入仓库仓位' : '添加仓位')
const inputRows = (): LocationInput[] => [{ warehouse: warehouse.value.trim(), bins: bins.value.trim(), ...(category.value ? { category: category.value } : {}) }]
function leave(to?: RouteLocationNormalized) {
  if (to?.name === 'login' || to?.name === 'forbidden') return true
  if (pendingManage.value) { error.value = '仓位操作结果尚未确认，请先核对原提交。'; return false }
  return !busy.value && (!mode.value || (!submitted.value && initial.value === content()) || window.confirm(submitted.value ? '保存结果待确认，请先核对资料。确定离开？' : '仓位资料尚未保存，确定离开？'))
}
onBeforeRouteLeave(leave); onBeforeRouteUpdate(leave)
function beforeUnload(event: BeforeUnloadEvent) { if (pendingManage.value) { event.preventDefault(); event.returnValue = '' } }
window.addEventListener('beforeunload', beforeUnload)
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
watch(() => pendingManage.value?.inFlight, (value, previous) => { if (previous && !value && !pendingManage.value && !manageAction.value && props.canManage) emit('refresh') }, { flush: 'sync' })
watch(() => !!mode.value || !!manageAction.value, value => emit('locked', value))
watch(() => [props.search, props.status, props.records, props.deletedRecords, showDeleted.value], () => { selectedIds.value = [] })
watch(() => props.canManage, value => { if (!value) { manageAction.value = undefined; mode.value = undefined; submitted.value = undefined; plan.value = undefined; generation++; busy.value = false } })
function toggleGroup(rows: MasterRecord[]) { const ids = rows.map(row => row.id); selectedIds.value = ids.every(id => selectedIds.value.includes(id)) ? selectedIds.value.filter(id => !ids.includes(id)) : [...new Set([...selectedIds.value, ...ids])] }
function openManage(action: LocationManage['action'], rows?: MasterRecord[]) {
  if (!props.canManage || blocked.value) return
  manageRecords.value = rows ?? groups.value.flatMap(group => group.places).filter(row => !selectedIds.value.length || selectedIds.value.includes(row.id))
  manageIds.value = action === 'CATEGORY' && !selectedIds.value.length && !rows ? [] : manageRecords.value.map(row => row.id)
  manageAction.value = action
}
function resumeManage() {
  if (!props.canManage || props.busy || !pendingManage.value || pendingManage.value.inFlight) return
  manageRecords.value = pendingManage.value.records
  manageIds.value = pendingManage.value.body.selections.map(row => row.id)
  manageAction.value = pendingManage.value.body.action
}
function managed(message: string) { manageAction.value = undefined; selectedIds.value = []; notice.value = message; emit('refresh') }
function close() { if (leave()) { mode.value = undefined; submitted.value = undefined; plan.value = undefined; generation++ } }
function open(next: typeof mode.value, name = '') {
  if (!props.canManage || blocked.value) return
  mode.value = next; warehouse.value = name; original.value = name; bins.value = ''; file.value = undefined; plan.value = undefined; submitted.value = undefined; error.value = ''
  category.value = ''
  groupToken.value = props.warehouseTokens[name] ?? ''
  initial.value = content(); generation++
}
watch([warehouse, bins, category, file], () => { if (!submitted.value) plan.value = undefined })
function choose(event: Event) { file.value = (event.target as HTMLInputElement).files?.[0]; error.value = '' }
async function download() {
  error.value = ''
  try { const blob = await api.locationTemplate(); if (!alive) return
    const url = URL.createObjectURL(blob), link = document.createElement('a'); link.href = url; link.download = '布料仓库仓位模板.xlsx'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (e) { if (alive) error.value = getApiErrorMessage(e) }
}
async function preview() {
  if (busy.value || !props.canManage) return
  if (mode.value === 'warehouse' && props.records.some(row => row.data.warehouse === warehouse.value.trim())) { error.value = '该仓库已存在，请在对应仓库旁添加仓位。'; return }
  const ticket = ++generation; busy.value = true; error.value = ''; plan.value = undefined
  try {
    const result = mode.value === 'import' ? await api.previewLocationFile(file.value!) : await api.previewLocations(inputRows())
    if (alive && ticket === generation) plan.value = result
  } catch (e) { if (alive && ticket === generation) error.value = getApiErrorMessage(e) }
  finally { if (alive && ticket === generation) busy.value = false }
}
async function save() {
  if (busy.value || !props.canManage) return
  if (!submitted.value) {
    if (mode.value === 'rename') { if (!groupToken.value) { error.value = '仓库版本未加载，请刷新资料后重试。'; return }; submitted.value = { factory_id: 'huakang-c', request_id: warehouseRequestId(), warehouse: original.value, name: warehouse.value.trim(), expected_group_token: groupToken.value } }
    else { if (!plan.value || plan.value.errors.length || !plan.value.new) return
      submitted.value = { factory_id: 'huakang-c', request_id: warehouseRequestId(), preview_token: plan.value.preview_token,
        rows: plan.value.rows ?? inputRows() }
    }
  }
  busy.value = true; error.value = ''
  try {
    if ('expected_group_token' in submitted.value) await api.renameWarehouse(submitted.value)
    else await api.applyLocations(submitted.value)
    if (!alive) return
    mode.value = undefined; submitted.value = undefined; plan.value = undefined; notice.value = '仓库仓位已保存，历史单据保留原资料。'; emit('refresh')
  } catch (e) {
    if (!alive) return
    error.value = getApiErrorMessage(e)
    const status = (e as { response?: { status?: number } }).response?.status
    if (status && status < 500 && status !== 408) { submitted.value = undefined; plan.value = undefined
      if ([401,403,409].includes(status)) { mode.value = undefined; emit('refresh') }
    }
  } finally { if (alive) busy.value = false }
}
</script>

<template>
  <section class="fabric-location-settings" aria-label="仓库与仓位设置">
    <div class="fabric-master-card-heading"><div><h2><Warehouse :size="18" />仓库与仓位</h2><p>设置架位／区域及适用原料，入库按分类筛出位置，再选具体架／区。</p></div><div v-if="canManage" class="fabric-master-tools"><Button v-if="!showDeleted" size="sm" variant="outline" :disabled="blocked || !records.length" @click="openManage('CATEGORY')">设置分料区</Button><Button size="sm" variant="outline" :disabled="blocked" @click="download"><Download :size="14" />下载仓位模板</Button><Button size="sm" variant="outline" :disabled="blocked" @click="open('import')"><Upload :size="14" />导入仓库仓位</Button><Button size="sm" :disabled="blocked" @click="open('warehouse')"><Plus :size="14" />添加仓库</Button></div></div>
    <p v-if="error && !mode" class="fabric-error" role="alert">{{ error }}</p><p v-if="notice" class="fabric-success" role="status">{{ notice }}</p>
    <p v-if="pendingManage && !manageAction" class="fabric-message" role="status">仓位操作结果尚未确认。<Button v-if="canManage" variant="outline" size="sm" :disabled="props.busy || pendingManage.inFlight" @click="resumeManage">核对原仓位操作</Button><span v-else>请由原提交账号恢复权限后核对。</span></p>
    <div class="location-maintenance-bar"><Button variant="ghost" size="sm" :disabled="blocked" @click="showDeleted = !showDeleted">{{ showDeleted ? '返回仓位列表' : `已删除（${deletedRecords?.length ?? 0}）` }}</Button><template v-if="canManage"><span>已选 {{ selectedIds.length }} 个</span><Button v-if="!showDeleted" variant="outline" size="sm" :disabled="blocked || !selectedIds.length" @click="openManage('DELETE')">删除所选</Button><Button v-else variant="outline" size="sm" :disabled="blocked || !selectedIds.length" @click="openManage('RESTORE')">恢复所选</Button></template></div>
    <div class="fabric-warehouse-groups">
      <article v-for="group in groups" :key="group.warehouse" class="fabric-warehouse-group">
        <header><div><h3><input v-if="canManage" type="checkbox" :checked="group.places.every(row => selectedIds.includes(row.id))" :disabled="blocked" :aria-label="`全选 ${group.warehouse} 当前仓位`" @change="toggleGroup(group.places)" />{{ group.warehouse }}</h3><p>{{ group.all.length }} 个仓位 · {{ group.all.filter(row => row.status === 'ACTIVE').length }} 个启用</p></div><div v-if="canManage && !showDeleted" class="fabric-master-tools"><Button size="sm" variant="outline" :disabled="blocked" :aria-label="`添加 ${group.warehouse} 仓位`" @click="open('bins', group.warehouse)">＋ 添加仓位</Button><Button v-if="group.all.every(row => !!row.data.warehouse)" size="sm" variant="ghost" :disabled="blocked" :aria-label="`修改仓库 ${group.warehouse}`" @click="open('rename', group.warehouse)">修改仓库</Button><Button size="sm" variant="ghost" :disabled="blocked" :aria-label="`删除仓库 ${group.warehouse}`" @click="openManage('DELETE', group.all)">删除仓库</Button></div></header>
        <div class="fabric-location-chips"><div v-for="row in group.places" :key="row.id" class="fabric-location-chip" :data-status="row.status"><input v-if="canManage" v-model="selectedIds" type="checkbox" :value="row.id" :disabled="blocked" :aria-label="`勾选仓位 ${group.warehouse} ${row.code}`" /><button type="button" :disabled="!canManage || blocked || showDeleted" :aria-label="`修改仓位 ${group.warehouse} ${row.code}`" @click="emit('edit', row)"><strong>{{ row.code }}</strong><span class="fabric-location-category">{{ locationCategoryLabels[row.data.category ?? ''] || '未分类' }}</span><span v-if="row.name !== row.code">{{ row.name }}</span><small>{{ showDeleted ? '已删除' : row.status === 'ACTIVE' ? '启用' : row.status === 'DRAFT' ? '待完善' : '停用' }}</small></button><button type="button" class="fabric-location-history" :disabled="blocked" :aria-label="`查看仓位 ${row.code} 修改记录`" @click="emit('history', row)">记录</button></div></div>
      </article>
      <div v-if="!props.busy && !groups.length" class="fabric-master-empty"><Warehouse :size="28" /><h3>{{ showDeleted ? '暂无已删除仓位' : records.length ? '没有符合筛选的仓位' : '先建立仓库和仓位' }}</h3><p>{{ showDeleted ? '未使用仓位删除后可在这里恢复。' : records.length ? '调整关键字或状态后查看。' : '添加仓库并填写首个仓位，也可以用模板批量导入。' }}</p><Button v-if="canManage && !showDeleted && !records.length" size="sm" @click="open('warehouse')">添加仓库</Button></div>
    </div>
    <p class="fabric-master-note">原料分区可选布料、辅料或线；未分类仓位不能用于新入库或调入。分区调整只影响后续入库和调入，不改动历史库存。未使用的仓位可删除并恢复；有库存或业务记录时请停用，原编码和记录保留。</p>
  </section>
  <DialogRoot :open="!!mode" @update:open="value => { if (!value) close() }"><DialogPortal><DialogOverlay class="warehouse-guide-overlay" /><DialogContent class="warehouse-guide fabric-edit-dialog fabric-master-dialog"><header class="warehouse-guide-heading"><div><DialogTitle>{{ title }}</DialogTitle><DialogDescription>{{ mode === 'rename' ? '整组仓位同步更名，保留编码、状态及历史单据。' : '先预览核对仓库与仓位，再一次保存。' }}</DialogDescription></div><Button size="sm" variant="ghost" :disabled="busy" @click="close">关闭</Button></header>
    <form class="warehouse-guide-body fabric-master-form" @submit.prevent="mode === 'rename' || submitted ? save() : preview()"><fieldset :disabled="busy || !!submitted">
      <template v-if="mode !== 'import'"><label class="fabric-master-wide">仓库名称 <span>*</span><input v-model="warehouse" aria-label="仓库名称" maxlength="128" :readonly="mode === 'bins'" required placeholder="例如 布料一仓" /></label><label v-if="mode !== 'rename'" class="fabric-master-wide">{{ mode === 'warehouse' ? '首个仓位 / 范围' : '仓位 / 范围' }} <span>*</span><textarea v-model="bins" aria-label="仓位或范围" maxlength="16000" required placeholder="例如 A01-A20，或 A01、A02、B01" /><small>支持同前缀升序范围，前导零保留；不同仓库请使用不同编码。</small></label><label v-if="mode !== 'rename'">适用原料<select v-model="category" aria-label="新仓位适用原料"><option value="">未分类（禁止新入库）</option><option v-for="(name, value) in locationCategoryLabels" :key="value" :value="value">{{ name }}</option></select></label></template>
      <label v-else class="fabric-master-wide">仓位模板文件 <span>*</span><input type="file" accept=".xlsx,.xlsm" aria-label="仓位模板文件" required @change="choose" /><small>仅导入“导入数据”页，最多 5 MB、1000 行及 1000 个展开仓位，禁止公式。模板新增仓位尚未分类，保存后须设置适用原料才可入库。</small></label>
    </fieldset>
    <section v-if="plan" class="fabric-location-preview" aria-label="仓位导入预览"><h3>新增 {{ plan.new }} 个 · 已有 {{ plan.unchanged }} 个</h3><p v-for="message in plan.errors" :key="message" class="fabric-row-error">{{ message }}</p><p>已有同仓仓位保持原状态；本次不增加库存。</p><div class="warehouse-table-scroll"><table><thead><tr><th>仓库</th><th>仓位</th><th>适用原料</th><th>处理</th></tr></thead><tbody><tr v-for="(row, index) in plan.items.slice(0,100)" :key="index"><td>{{ row.warehouse }}</td><td>{{ row.code }}</td><td>{{ locationCategoryLabels[row.category ?? ''] || '未分类' }}</td><td>{{ row.action === 'NEW' ? '新增并启用' : row.status === 'INACTIVE' ? '已有 · 保持停用' : '已有 · 跳过' }}</td></tr></tbody></table></div><p v-if="plan.items.length > 100">显示前 100 项，共 {{ plan.items.length }} 项。</p></section>
    <p v-if="error" class="fabric-error" role="alert">{{ error }}</p><p v-if="submitted" class="fabric-intake-alert">保存结果待确认，内容已锁定。重试使用同一个请求。</p>
    <div class="fabric-dialog-actions"><Button variant="outline" type="button" :disabled="busy" @click="close">返回</Button><Button v-if="mode !== 'rename' && !submitted" variant="outline" type="submit" :disabled="busy">{{ busy ? '正在预览…' : '预览仓位' }}</Button><Button v-if="mode === 'rename' || plan || submitted" :type="mode === 'rename' || submitted ? 'submit' : 'button'" :disabled="busy || (!submitted && mode !== 'rename' && (!plan?.new || !!plan.errors.length))" @click="mode !== 'rename' && !submitted && save()">{{ busy ? '正在保存…' : submitted ? '重试保存' : mode === 'rename' ? '保存仓库' : '确认保存' }}</Button></div>
    </form></DialogContent></DialogPortal></DialogRoot>
<FabricLocationManageDialog v-if="manageAction" :action="manageAction" :records="manageRecords" :initial-ids="manageIds" @close="manageAction = undefined" @saved="managed" />
</template>

<style scoped>
.fabric-location-category{color:var(--primary);font-size:12px}.location-maintenance-bar{display:flex;gap:12px;align-items:center;padding:12px 24px;font-size:13px;color:var(--muted-foreground)}.fabric-location-chip>input{align-self:center;margin-left:9px;width:14px;height:14px}.fabric-warehouse-group h3{display:flex;align-items:center;gap:9px}.fabric-warehouse-group h3 input{width:15px;height:15px}
</style>
