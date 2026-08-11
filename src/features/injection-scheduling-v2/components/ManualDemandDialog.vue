<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { AlertTriangle, Boxes, Search, X } from '@lucide/vue'
import {
  cancelManualDemand,
  createManualDemand,
  getSharedMoldDetail,
  listSharedMoldCatalog,
  updateManualDemand,
  type ManualDemandInput,
  type SharedMoldCatalogItem,
  type SharedMoldDetail,
} from '../api/injectionSchedulingV2Api'
import type { OrderRecord } from '../types'
import { useDialogFocus } from '../composables/useDialogFocus'
import { factoryMeta, materialReadinessMeta, priorityMeta, quantityBasisMeta } from '../presentation/schedulingLabels'

const props = defineProps<{
  open: boolean
  factoryId: string
  businessDate: string
  order: OrderRecord | null
  canEdit: boolean
}>()
const emit = defineEmits<{ close: []; saved: []; cancelled: [] }>()

const search = ref('')
const results = ref<SharedMoldCatalogItem[]>([])
const detail = ref<SharedMoldDetail | null>(null)
const loadingCatalog = ref(false)
const loadingDetail = ref(false)
const saving = ref(false)
const cancelling = ref(false)
const error = ref('')
const dialogRoot = ref<HTMLElement | null>(null)
const requestClose = () => emit('close')
const { announcement: dialogAnnouncement } = useDialogFocus(() => props.open, dialogRoot, {
  onEscape: requestClose,
  openAnnouncement: () => `${props.order ? '修改排期需求' : '新增排期任务'}对话框已打开，按 Escape 关闭。`,
})
const cancelReason = ref('不再需要排期')
const form = reactive<ManualDemandInput>({
  businessDate: '', moldDefinitionId: '', moldOutputSpecId: null,
  plannedQuantity: 1, quantityBasis: 'UNITS', itemNo: '', productName: '',
  deliveryDueDate: '', priorityCode: 'NORMAL', materialReadinessStatus: 'unknown',
  warehouseText: '', materialName: '', colorName: '', remark: '',
})
const priorityOptions = ['NORMAL', 'URGENT', 'CRITICAL'] as const
const materialReadinessOptions = ['unknown', 'ready', 'partial', 'blocked'] as const
const quantityBasisOptions = ['UNITS', 'SHOTS'] as const

const selectedOutput = computed(() => detail.value?.outputs.find((item) => item.id === form.moldOutputSpecId) ?? null)
const hasFactoryCapability = computed(() => Boolean(detail.value?.capabilities.length))
const outputSelectionValid = computed(() => !detail.value?.outputs.length || Boolean(form.moldOutputSpecId))
const canSubmit = computed(() => props.canEdit && !saving.value && Boolean(form.moldDefinitionId) && form.plannedQuantity > 0 && hasFactoryCapability.value && outputSelectionValid.value)
const sourceMoldNo = computed(() => detail.value?.displayMoldNo || detail.value?.canonicalMoldNo || '')

function errorMessage(cause: unknown) {
  if (cause && typeof cause === 'object' && 'response' in cause) {
    const response = (cause as { response?: { data?: { detail?: unknown } } }).response
    const detailValue = response?.data?.detail
    if (typeof detailValue === 'string') return detailValue
    if (detailValue && typeof detailValue === 'object' && 'message' in detailValue) return String((detailValue as { message: unknown }).message)
  }
  return cause instanceof Error ? cause.message : '操作失败，请稍后重试'
}

function resetForm() {
  const lineage = props.order?.lineage ?? {}
  const basis = lineage.quantity_basis === 'SHOTS' ? 'SHOTS' : 'UNITS'
  Object.assign(form, {
    businessDate: props.businessDate,
    moldDefinitionId: props.order?.moldDefinitionId ?? '',
    moldOutputSpecId: props.order?.moldOutputSpecId ?? null,
    plannedQuantity: basis === 'SHOTS' ? Number(lineage.planned_shots || 1) : (props.order?.orderQuantity ?? 1),
    quantityBasis: basis,
    itemNo: props.order?.itemNo ?? '',
    productName: props.order?.productName ?? '',
    deliveryDueDate: props.order?.deliveryDueDate ?? '',
    priorityCode: props.order?.priorityCode ?? 'NORMAL',
    materialReadinessStatus: props.order?.materialReadinessStatus ?? 'unknown',
    warehouseText: props.order?.warehouseText ?? '',
    materialName: String(lineage.material_name ?? ''),
    colorName: String(lineage.color_name ?? ''),
    remark: props.order?.remark ?? '',
  })
  search.value = String(lineage.source_mold_no ?? '')
  results.value = []
  detail.value = null
  error.value = ''
  cancelReason.value = '不再需要排期'
}

async function searchMolds() {
  loadingCatalog.value = true
  error.value = ''
  try {
    const page = await listSharedMoldCatalog(props.factoryId, { q: search.value.trim(), readiness: 'ALL', pageSize: 20 })
    results.value = page.items
  } catch (cause) {
    error.value = errorMessage(cause)
  } finally {
    loadingCatalog.value = false
  }
}

async function selectMold(item: Pick<SharedMoldCatalogItem, 'id'>, preserveValues = false) {
  loadingDetail.value = true
  error.value = ''
  try {
    const loaded = await getSharedMoldDetail(props.factoryId, item.id)
    detail.value = loaded
    form.moldDefinitionId = loaded.id
    const existingOutput = loaded.outputs.find((output) => output.id === form.moldOutputSpecId)
    form.moldOutputSpecId = existingOutput?.id ?? (loaded.outputs.length === 1 ? loaded.outputs[0]!.id : null)
    if (!preserveValues) applyOutputDefaults(true)
  } catch (cause) {
    error.value = errorMessage(cause)
  } finally {
    loadingDetail.value = false
  }
}

function applyOutputDefaults(force = false) {
  const output = selectedOutput.value
  if (!output) return
  if (force || !form.itemNo) form.itemNo = output.itemNo
  if (force || !form.productName) form.productName = output.productName
  if (force || !form.materialName) form.materialName = output.defaultMaterial
  if (force || !form.colorName) form.colorName = output.defaultColor
}

async function submit() {
  if (!canSubmit.value) return
  saving.value = true
  error.value = ''
  try {
    if (props.order) await updateManualDemand(props.factoryId, props.order, { ...form })
    else await createManualDemand(props.factoryId, { ...form })
    emit('saved')
  } catch (cause) {
    error.value = errorMessage(cause)
  } finally {
    saving.value = false
  }
}

async function cancelDemand() {
  if (!props.order || cancelReason.value.trim().length < 2) {
    error.value = '请填写至少 2 个字的取消原因'
    return
  }
  cancelling.value = true
  error.value = ''
  try {
    await cancelManualDemand(props.factoryId, props.order, cancelReason.value.trim())
    emit('cancelled')
  } catch (cause) {
    error.value = errorMessage(cause)
  } finally {
    cancelling.value = false
  }
}

watch(() => props.open, async (open) => {
  if (!open) return
  resetForm()
  if (form.moldDefinitionId) await selectMold({ id: form.moldDefinitionId }, true)
  else await searchMolds()
})
</script>

<template>
  <div v-if="open" ref="dialogRoot" class="manual-demand-backdrop" tabindex="-1" @mousedown.self="requestClose">
    <section class="manual-demand-dialog" role="dialog" aria-modal="true" aria-labelledby="manual-demand-title">
      <p class="scheduling-sr-only dialog-live-announcement" role="status" aria-live="polite">{{ dialogAnnouncement }}</p>
      <header>
        <div><Boxes :size="19" /><div><strong id="manual-demand-title">{{ order ? '修改排期需求' : '新增排期任务' }}</strong><span>无需下单表，直接从共享模具库建立待排需求</span></div></div>
        <button type="button" aria-label="关闭" @click="requestClose"><X :size="18" /></button>
      </header>
      <div class="manual-demand-body">
        <p v-if="error" class="manual-demand-error"><AlertTriangle :size="15" />{{ error }}</p>
        <div class="mold-picker">
          <label><span>搜索共享模具</span><div><Search :size="15" /><input v-model="search" placeholder="模具编号、货号或产品名称" @keyup.enter="searchMolds" /><button type="button" :disabled="loadingCatalog" @click="searchMolds">{{ loadingCatalog ? '搜索中' : '搜索' }}</button></div></label>
          <div v-if="results.length" class="mold-results">
            <button v-for="item in results" :key="item.id" type="button" :class="{ selected: form.moldDefinitionId === item.id }" @click="selectMold(item)">
              <strong>{{ item.displayMoldNo || item.canonicalMoldNo }}</strong><span>{{ item.standardName }} · {{ item.moldAClass ?? '—' }}A</span><em>{{ item.factoryReadiness.activeCapabilityCount ? `有${factoryMeta(props.factoryId).label}机安数据` : `缺少${factoryMeta(props.factoryId).label}机安数据` }}</em>
            </button>
          </div>
        </div>
        <div v-if="loadingDetail" class="manual-demand-loading">正在读取模具详情…</div>
        <div v-else-if="detail" class="selected-mold">
          <strong>{{ sourceMoldNo }} · {{ detail.standardName }}</strong>
          <span>{{ detail.moldAClass ?? detail.factoryCapability?.machineClass ?? '—' }}A · {{ detail.defaultArmType || '机械手待补' }} · {{ detail.defaultFixtureType || '夹具待补' }}</span>
          <em :class="{ warning: !hasFactoryCapability }">{{ hasFactoryCapability ? '草案可排；发布前再落实实体模具' : '缺少当前厂区机安能力，不能建立需求' }}</em>
        </div>
        <form @submit.prevent="submit">
          <label v-if="detail?.outputs.length"><span>产品输出 *</span><select v-model="form.moldOutputSpecId" @change="applyOutputDefaults(true)"><option :value="null" disabled>请选择</option><option v-for="output in detail.outputs" :key="output.id" :value="output.id">{{ output.itemNo || '未设货号' }} · {{ output.productName }} · {{ output.cavityCount || '—' }} 穴</option></select></label>
          <label><span>计划数量 *</span><input v-model.number="form.plannedQuantity" type="number" min="0.0001" step="0.0001" required /></label>
          <label><span>数量口径</span><select v-model="form.quantityBasis"><option v-for="value in quantityBasisOptions" :key="value" :value="value">{{ quantityBasisMeta(value).label }}</option></select></label>
          <label><span>货号</span><input v-model="form.itemNo" /></label>
          <label><span>产品名称</span><input v-model="form.productName" /></label>
          <label><span>交货日期</span><input v-model="form.deliveryDueDate" type="date" /></label>
          <label><span>优先级</span><select v-model="form.priorityCode"><option v-for="value in priorityOptions" :key="value" :value="value">{{ priorityMeta(value).label }}</option></select></label>
          <label><span>物料状态</span><select v-model="form.materialReadinessStatus"><option v-for="value in materialReadinessOptions" :key="value" :value="value">{{ materialReadinessMeta(value).label }}</option></select></label>
          <label><span>仓库 / 下单人</span><input v-model="form.warehouseText" /></label>
          <label><span>用料名称</span><input v-model="form.materialName" /></label>
          <label><span>颜色 / 色粉号</span><input v-model="form.colorName" /></label>
          <label class="wide"><span>备注</span><textarea v-model="form.remark" rows="2" /></label>
          <div v-if="order" class="cancel-demand wide"><label><span>取消原因</span><input v-model="cancelReason" /></label><button type="button" :disabled="!canEdit || cancelling" @click="cancelDemand">{{ cancelling ? '取消中' : '取消此需求' }}</button></div>
          <footer class="wide"><button type="button" @click="requestClose">关闭</button><button class="primary" type="submit" :disabled="!canSubmit">{{ saving ? '保存中' : order ? '保存修改' : '加入待排池' }}</button></footer>
        </form>
      </div>
    </section>
  </div>
</template>

<style scoped>
.manual-demand-backdrop{position:fixed;inset:0;z-index:80;display:grid;place-items:center;padding:24px;background:rgba(4,18,31,.58)}
.manual-demand-dialog{width:min(920px,96vw);max-height:92vh;overflow:auto;border:1px solid #c9d8e5;border-radius:18px;background:#f8fbfd;box-shadow:0 24px 70px rgba(3,24,42,.28);color:#132238}
.manual-demand-dialog>header{position:sticky;top:0;z-index:2;display:flex;align-items:center;justify-content:space-between;padding:18px 22px;border-bottom:1px solid #d9e4ec;background:#fff}
.manual-demand-dialog>header>div{display:flex;gap:10px;align-items:center}.manual-demand-dialog header strong,.manual-demand-dialog header span{display:block}.manual-demand-dialog header span{margin-top:2px;color:#667991;font-size:12px}.manual-demand-dialog header button{border:0;background:transparent;color:#42556c}
.manual-demand-body{display:grid;gap:14px;padding:18px 22px}.manual-demand-error{display:flex;gap:7px;align-items:center;margin:0;padding:10px 12px;border:1px solid #fecaca;border-radius:10px;background:#fff1f2;color:#b42318}
.mold-picker>label>span,.manual-demand-body form label>span{display:block;margin-bottom:5px;color:#52657a;font-size:12px;font-weight:700}.mold-picker>label>div{display:flex;align-items:center;gap:8px;padding:0 8px;border:1px solid #bccddd;border-radius:9px;background:white}.mold-picker input{flex:1;padding:10px 0;border:0;outline:0}.mold-picker button{padding:7px 12px;border:1px solid #a9c1d3;border-radius:7px;background:#eef7f6;color:#087365}
.mold-results{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;max-height:180px;margin-top:8px;overflow:auto}.mold-results button{display:grid;gap:2px;padding:10px;text-align:left;border:1px solid #d2dee8;border-radius:9px;background:#fff}.mold-results button.selected{border-color:#0b8a78;background:#eaf9f5}.mold-results span,.mold-results em{color:#65788d;font-size:11px;font-style:normal}.mold-results em{color:#997000}
.selected-mold{display:flex;gap:9px;align-items:center;padding:11px 12px;border-radius:10px;background:#eaf8f4}.selected-mold span{color:#52677a;font-size:12px}.selected-mold em{margin-left:auto;color:#087365;font-size:12px;font-style:normal}.selected-mold em.warning{color:#b54708}.manual-demand-loading{color:#65788d}
.manual-demand-body form{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.manual-demand-body form input,.manual-demand-body form select,.manual-demand-body form textarea{width:100%;box-sizing:border-box;padding:9px 10px;border:1px solid #c3d2df;border-radius:8px;background:#fff;color:#17283d}.wide{grid-column:1/-1}.cancel-demand{display:flex;align-items:end;gap:10px;padding-top:10px;border-top:1px solid #dde6ed}.cancel-demand label{flex:1}.cancel-demand button{padding:9px 13px;border:1px solid #efb0aa;border-radius:8px;background:#fff;color:#b42318}
.manual-demand-body footer{display:flex;justify-content:flex-end;gap:9px;padding-top:4px}.manual-demand-body footer button{padding:9px 16px;border:1px solid #bfd0dd;border-radius:8px;background:#fff}.manual-demand-body footer .primary{border-color:#087f70;background:#087f70;color:#fff}.manual-demand-body footer button:disabled{opacity:.45}
@media (max-width:760px){.manual-demand-body form{grid-template-columns:1fr}.mold-results{grid-template-columns:1fr}.selected-mold{align-items:flex-start;flex-direction:column}.selected-mold em{margin-left:0}}
</style>
