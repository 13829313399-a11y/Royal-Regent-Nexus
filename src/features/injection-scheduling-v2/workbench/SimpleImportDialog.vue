<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, FileSearch, FileSpreadsheet, RefreshCw, Upload, X } from '@lucide/vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { useDialogFocus } from '../composables/useDialogFocus'
import { applyWorkbenchImportMapping, confirmWorkbenchImport, previewWorkbenchImport } from './api'
import { mappingStatusLabel } from './presentation'
import WorkbenchActionButton from './ui/WorkbenchActionButton.vue'
import type { ImportBatchRecord, ImportDocumentKindChoice } from '../types'

const props = defineProps<{ open: boolean; factoryId: string; businessDate: string }>()
const emit = defineEmits<{ close: []; imported: [message: string] }>()
const root = ref<HTMLElement | null>(null)
const file = ref<File | null>(null)
const kind = ref<ImportDocumentKindChoice>('AUTO')
const batch = ref<ImportBatchRecord | null>(null)
const mappingDraft = ref<Record<string, string>>({})
const loading = ref(false)
const loadingAction = ref<'AUTO' | 'AI' | 'CONFIRM' | null>(null)
const error = ref('')
const dragActive = ref(false)
const mappingOpen = ref(true)
const { announcement } = useDialogFocus(() => props.open, root, {
  onEscape: () => emit('close'),
  initialFocus: () => root.value?.querySelector<HTMLElement>('[data-import-file]') ?? null,
})
watch(() => props.open, (open) => {
  if (!open) { file.value = null; batch.value = null; mappingDraft.value = {}; error.value = ''; kind.value = 'AUTO' }
})
watch(kind, () => { if (batch.value) { batch.value = null; mappingDraft.value = {}; error.value = '' } })
const mappingText = (item: Record<string, unknown>, key: string) => item[key] == null ? '' : String(item[key])
const blockingCount = computed(() => batch.value?.issues.filter((issue) => issue.blocking).length ?? 0)
const nonMappingBlockingCount = computed(() => batch.value?.issues.filter((issue) => issue.blocking && !issue.code.includes('MAPPING')).length ?? 0)
const destination = computed(() => batch.value?.documentKind === 'DEMAND_ORDER' ? '待排池（需求订单）' : '当前规划（接管既有排机）')
const previewRows = computed(() => {
  if (!batch.value) return []
  if (batch.value.documentKind === 'DEMAND_ORDER') return batch.value.demandRows.slice(0, 25).map((row) => row.resolvedValues)
  return [...batch.value.scheduledBaselineTasks, ...batch.value.backlogOrders].slice(0, 25)
})
const mappingRows = computed(() => batch.value?.mapping ?? [])
const mappedFieldRows = computed(() => mappingRows.value.filter((item) => mappingText(item, 'canonical_field')))
const confidenceScore = (item: Record<string, unknown>) => {
  const value = Number(item.confidence_score)
  return Number.isFinite(value) ? value : null
}
const confidenceLabel = (item: Record<string, unknown>) => {
  const score = confidenceScore(item)
  if (score == null) return mappingStatusLabel(mappingText(item, 'status'))
  if (score >= 0.85) return `高置信 ${Math.round(score * 100)}%`
  if (score >= 0.6) return `需复核 ${Math.round(score * 100)}%`
  return `低置信 ${Math.round(score * 100)}%`
}
const confidenceTone = (item: Record<string, unknown>): 'green' | 'amber' | 'red' => {
  const score = confidenceScore(item)
  if (score == null) return mappingText(item, 'status') === 'MAPPED' ? 'green' : 'amber'
  return score >= 0.85 ? 'green' : score >= 0.6 ? 'amber' : 'red'
}
const canonicalLabels: Record<string, string> = {
  machine_code: '机台编号', mold_no: '模具编号', source_mold_no: '来源模具编号', order_no: '订单编号',
  item_no: '货号', product_name: '产品名称', order_quantity: '订单数量', completed_quantity: '已完成数量',
  planned_start: '计划开始', planned_finish: '计划完成', customer_name: '客户名称', source_document_no: '来源单号',
  product_group_no: '产品组号', required_shots: '需求模数', source_daily_capacity: '来源日产能',
  delivery_due_date: '交付日期', material_name: '材料名称', color_name: '颜色', order_remark: '订单备注',
}
const canonicalLabel = (value: string) => canonicalLabels[value] || value || '未映射来源列'
const mappingReviewItems = computed(() => mappedFieldRows.value.filter((item) => mappingText(item, 'canonical_field')
  && (mappingText(item, 'status') !== 'MAPPED' || (confidenceScore(item) ?? 1) < 0.85)))
const requiredMappingItems = computed(() => {
  const blockedFields = new Set(batch.value?.issues.filter((issue) => issue.blocking).map((issue) => issue.fieldName).filter(Boolean) ?? [])
  return mappingReviewItems.value.filter((item) => Boolean(item.required) || blockedFields.has(mappingText(item, 'canonical_field')))
})
const availableSourceHeaders = computed(() => [...new Set(mappingRows.value.map((item) => mappingText(item, 'raw_header').trim()).filter(Boolean))])
const selectedMappings = computed(() => Object.fromEntries(Object.entries(mappingDraft.value).filter(([, value]) => value.trim())))
const mappingValuesUnique = computed(() => {
  const values = Object.values(selectedMappings.value)
  return new Set(values).size === values.length
})
const mappingCorrectionsComplete = computed(() => requiredMappingItems.value.length > 0
  && requiredMappingItems.value.every((item) => Boolean(selectedMappings.value[mappingText(item, 'canonical_field')]))
  && mappingValuesUnique.value)
const canConfirm = computed(() => {
  if (!batch.value) return false
  if (blockingCount.value === 0) return ['PREVIEW_READY', 'PARTIALLY_CONFIRMED'].includes(batch.value.batchState)
  return nonMappingBlockingCount.value === 0 && mappingCorrectionsComplete.value
})
const importExplanation = computed(() => {
  if (!batch.value) return ''
  const rowCount = batch.value.demandRows.length + batch.value.scheduledBaselineTasks.length + batch.value.backlogOrders.length
  return batch.value.documentKind === 'DEMAND_ORDER'
    ? `将导入 ${rowCount} 条待排订单，不改变任何当前机台计划。`
    : `将接管 ${rowCount} 条已有计划任务，并保留来源机台、顺序与期初进度。`
})
const recognition = computed(() => batch.value?.recognition ?? {})
const recognitionSource = computed(() => {
  const source = mappingText(recognition.value, 'source')
  if (source === 'SAVED_TEMPLATE') return '已保存模板'
  if (source === 'BUILTIN_PROFILE') return '内置模板'
  if (source === 'MANUAL_CORRECTION') return '人工修正模板'
  if (source === 'SIGNED_SYSTEM_EXPORT') return '系统签名模板'
  if (source === 'AI_SKILL' || mappingText(recognition.value, 'mode') === 'AI_SKILL') return '千问智能识别'
  return '确定性模板'
})
const layoutDetails = computed(() => {
  const aiMapping = objectValue(recognition.value.mapping)
  const recognitionLayout = objectValue(recognition.value.layout)
  const profileRecognition = objectValue(objectValue(batch.value?.profile).recognition_config)
  const source = Object.keys(aiMapping).length ? aiMapping : Object.keys(recognitionLayout).length ? recognitionLayout : profileRecognition
  const sheet = objectValue(source.source_sheet ?? source.plan_sheet)
  const rowLayout = objectValue(source.row_layout)
  const shift = objectValue(source.shift_grid)
  const anchors = Array.isArray(source.metadata_anchors) ? source.metadata_anchors : []
  return {
    sheetName: mappingText(sheet, 'sheet_name') || mappingText(recognition.value, 'sheet_name') || '—',
    headerRows: Array.isArray(sheet.header_rows) ? sheet.header_rows.join('、') : '—',
    dataRange: sheet.data_start_row ? `${sheet.data_start_row}–${sheet.data_end_row || '末行'}` : '—',
    rowLayout: mappingText(rowLayout, 'layout_type') || '—',
    machineRule: mappingText(rowLayout, 'machine_header_rule') || 'NONE',
    shiftGrid: shift.enabled ? `${mappingText(shift, 'start_column')}–${mappingText(shift, 'end_column')}` : '未启用',
    anchorCount: anchors.length,
  }
})
const activeStep = computed(() => batch.value ? 3 : loading.value ? 2 : file.value ? 2 : 1)
function setFile(next: File | null) { file.value = next; batch.value = null; mappingDraft.value = {}; error.value = '' }
function pickFile(event: Event) { setFile((event.target as HTMLInputElement).files?.[0] ?? null) }
function dropFile(event: DragEvent) { dragActive.value = false; setFile(event.dataTransfer?.files?.[0] ?? null) }
function objectValue(value: unknown): Record<string, unknown> { return value && typeof value === 'object' ? value as Record<string, unknown> : {} }
async function preview(mode: 'AUTO' | 'AI' = 'AUTO') {
  if (!file.value) { error.value = '请先选择 Excel 文件'; return }
  loading.value = true; loadingAction.value = mode; error.value = ''
  try { batch.value = await previewWorkbenchImport(props.factoryId, file.value, kind.value, props.businessDate, mode); mappingDraft.value = {} }
  catch (cause) {
    const detail = cause instanceof Error ? cause.message : ''
    error.value = `识别失败${detail ? `：${detail}` : ''}。你可以重试，或选择表格类型后手动对齐必填表头。`
  }
  finally { loading.value = false; loadingAction.value = null }
}
async function confirm() {
  if (!batch.value) return
  loading.value = true; loadingAction.value = 'CONFIRM'; error.value = ''
  try {
    let readyBatch = batch.value
    if (Object.keys(selectedMappings.value).length) {
      readyBatch = await applyWorkbenchImportMapping(props.factoryId, readyBatch, selectedMappings.value)
      batch.value = readyBatch
      mappingDraft.value = {}
    }
    const remainingBlockers = readyBatch.issues.filter((issue) => issue.blocking)
    if (remainingBlockers.length || !['PREVIEW_READY', 'PARTIALLY_CONFIRMED'].includes(readyBatch.batchState)) {
      error.value = `映射重新校验后仍有 ${remainingBlockers.length} 个阻断问题，请检查预览。`
      return
    }
    const result = await confirmWorkbenchImport(props.factoryId, readyBatch, props.businessDate)
    emit('imported', `已导入 ${result.sourceFileName}，去向：${destination.value}`)
    emit('close')
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '导入失败' }
  finally { loading.value = false; loadingAction.value = null }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="wb-modal-pop">
    <div v-if="open" class="wb-modal-layer" @mousedown.self="emit('close')">
      <section ref="root" class="wb-modal wb-import-modal" role="dialog" aria-modal="true" aria-labelledby="wb-import-title" tabindex="-1">
        <p class="wb-sr-only" role="status" aria-live="polite">{{ announcement }}</p>
        <header><div><p>只读解析 · 确认后入库</p><h2 id="wb-import-title">Excel 导入工作台</h2></div><WorkbenchActionButton variant="ghost" icon-only aria-label="关闭导入" @click="emit('close')"><template #icon><X :size="18" /></template></WorkbenchActionButton></header>
        <ol class="wb-import-rail" aria-label="导入进度"><li :class="{ active: activeStep === 1, done: activeStep > 1 }"><span><Check v-if="activeStep > 1" :size="12" /><template v-else>1</template></span>选择文件</li><li :class="{ active: activeStep === 2, done: activeStep > 2 }"><span><Check v-if="activeStep > 2" :size="12" /><template v-else>2</template></span>识别解析</li><li :class="{ active: activeStep === 3 }"><span>3</span>校验并确认</li></ol>
        <div class="wb-import-step">
          <label class="wb-file-picker" :class="{ active: dragActive }" @dragenter.prevent="dragActive = true" @dragover.prevent="dragActive = true" @dragleave.prevent="dragActive = false" @drop.prevent="dropFile"><FileSpreadsheet :size="24" /><span><b>{{ file?.name || '拖入或选择 Excel 文件' }}</b><small>支持 .xlsx / .xls，源文件始终只读</small></span><input data-import-file type="file" accept=".xlsx,.xls" @change="pickFile" /></label>
          <label>表格类型<select v-model="kind"><option value="AUTO">自动识别</option><option value="DEMAND_ORDER">下单/需求表</option><option value="PLANNED_SCHEDULE">已排生产日计划表</option></select></label>
          <WorkbenchActionButton variant="primary" :disabled="!file" :loading="loadingAction === 'AUTO'" loading-text="正在读取表结构并匹配模板…" @click="preview('AUTO')"><template #icon><FileSearch :size="15" /></template>智能识别并预览</WorkbenchActionButton>
        </div>
        <div v-if="batch" class="wb-import-preview">
          <div class="wb-recognition-bar">
            <span>识别来源</span><StatusPill :label="recognitionSource" :tone="recognitionSource === '千问智能识别' ? 'blue' : recognitionSource === '人工修正模板' ? 'amber' : 'green'" compact />
            <small>AI 只负责结构映射，原文件仍由后端确定性解析。</small>
            <WorkbenchActionButton variant="ghost" :disabled="!file || loading" :loading="loadingAction === 'AI'" loading-text="千问识别中…" @click="preview('AI')"><template #icon><RefreshCw :size="14" /></template>千问重新识别</WorkbenchActionButton>
          </div>
          <div class="wb-import-result"><div><span>识别类型</span><b>{{ batch.documentKind === 'DEMAND_ORDER' ? '需求订单' : '已排生产计划' }}</b></div><div><span>入库去向</span><b>{{ destination }}</b></div><div><span>可导入行</span><b>{{ batch.demandRows.length + batch.scheduledBaselineTasks.length + batch.backlogOrders.length }}</b></div><div><span>阻断问题</span><b :class="{ danger: blockingCount }">{{ blockingCount }}</b></div></div>
          <p class="wb-import-explanation">{{ importExplanation }}</p>
          <details class="wb-layout-details">
            <summary>识别布局详情</summary>
            <dl><div><dt>工作表</dt><dd>{{ layoutDetails.sheetName }}</dd></div><div><dt>表头行</dt><dd>{{ layoutDetails.headerRows }}</dd></div><div><dt>数据行</dt><dd>{{ layoutDetails.dataRange }}</dd></div><div><dt>行布局</dt><dd>{{ layoutDetails.rowLayout }}</dd></div><div><dt>机台标题规则</dt><dd>{{ layoutDetails.machineRule }}</dd></div><div><dt>班次矩阵</dt><dd>{{ layoutDetails.shiftGrid }}</dd></div><div><dt>元数据锚点</dt><dd>{{ layoutDetails.anchorCount }}</dd></div></dl>
          </details>
          <section v-if="mappedFieldRows.length" class="wb-mapping-panel">
            <button type="button" class="wb-mapping-summary" :aria-expanded="mappingOpen" @click="mappingOpen = !mappingOpen">字段映射预览（{{ mappedFieldRows.length }}）<span v-if="mappingReviewItems.length">{{ mappingReviewItems.length }} 项可修正</span></button>
            <div v-show="mappingOpen">
            <div class="wb-mapping-table">
              <div v-for="(item, index) in mappedFieldRows" :key="`${mappingText(item, 'canonical_field')}-${index}`">
                <span>{{ mappingText(item, 'raw_header') || '未识别来源列' }}</span>
                <b>{{ canonicalLabel(mappingText(item, 'canonical_field')) }}</b>
                <StatusPill :label="confidenceLabel(item)" :tone="confidenceTone(item)" compact />
              </div>
            </div>
            <div v-if="mappingReviewItems.length" class="wb-mapping-editor">
              <p>低置信度或缺失字段可在这里直接选择来源列；确认时会保存为本厂区模板并重新校验。</p>
              <label v-for="item in mappingReviewItems" :key="mappingText(item, 'canonical_field')">
                <span>{{ canonicalLabel(mappingText(item, 'canonical_field')) }}{{ item.required ? '（必填）' : '' }}</span>
                <select v-model="mappingDraft[mappingText(item, 'canonical_field')]">
                  <option value="">选择来源表头</option>
                  <option v-for="header in availableSourceHeaders" :key="header" :value="header">{{ header }}</option>
                </select>
              </label>
              <small v-if="!mappingValuesUnique" class="danger" role="alert">同一来源列不能映射到多个字段。</small>
            </div>
            </div>
          </section>
          <div class="wb-preview-table"><table><thead><tr><th>#</th><th>单号/货号</th><th>产品/模具</th><th>数量</th></tr></thead><tbody><tr v-for="(row, index) in previewRows" :key="index"><td>{{ index + 1 }}</td><td>{{ row.order_no || row.item_no || row.source_line_key || '—' }}</td><td>{{ row.product_name || row.mold_no || row.mold_name || '—' }}</td><td>{{ row.order_quantity || row.planned_quantity || '—' }}</td></tr></tbody></table></div>
          <ul v-if="batch.issues.length" class="wb-import-issues"><li v-for="issue in batch.issues.slice(0, 6)" :key="issue.id" :class="{ danger: issue.blocking }">{{ issue.sheetName }} {{ issue.cellRef }}：{{ issue.message }}</li></ul>
          <p v-if="!canConfirm" class="wb-inline-warning">当前预览还有需处理的映射或阻断问题，本次不会写入业务数据。</p>
        </div>
        <p v-if="error" class="wb-error-banner">{{ error }}</p>
        <footer><WorkbenchActionButton variant="secondary" @click="emit('close')">取消</WorkbenchActionButton><WorkbenchActionButton variant="primary" :disabled="!canConfirm" :loading="loadingAction === 'CONFIRM'" loading-text="正在导入…" @click="confirm"><template #icon><Upload :size="15" /></template>{{ Object.keys(selectedMappings).length ? '保存本厂区模板并导入' : '确认导入' }}</WorkbenchActionButton></footer>
      </section>
    </div>
    </Transition>
  </Teleport>
</template>
