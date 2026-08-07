<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { AlertTriangle, CheckCircle2, FileSpreadsheet, RefreshCw, Upload, X } from '@lucide/vue'
import { getApiErrorMessage } from '@/lib/http'
import {
  approveImportMasterDifferences,
  confirmImportBatch,
  listImportBatches,
  recoverImportBatch,
  retryImportPreview,
  uploadImportPreview,
} from '../api/injectionSchedulingV2Api'
import type { FactoryId, ImportBatchRecord } from '../types'

const props = defineProps<{
  open: boolean
  factoryId: FactoryId
  businessDate: string
  canImport: boolean
  canManageMaster: boolean
  sourceMode: 'live' | 'fallback'
}>()
const emit = defineEmits<{ close: []; confirmed: [batch: ImportBatchRecord] }>()

const file = ref<File | null>(null)
const batch = ref<ImportBatchRecord | null>(null)
const recent = ref<ImportBatchRecord[]>([])
const busy = ref(false)
const error = ref('')
const masterReason = ref('')
const issueQuery = ref('')

const stateLabel: Record<string, string> = {
  IDENTIFYING: '识别中', MAPPING_REQUIRED: '需要字段映射', PROFILE_REVIEW_PENDING: 'Profile 待审核',
  MASTER_REVIEW_REQUIRED: '主数据待审批', RECONCILIATION_CONFLICT: '对账冲突', PREVIEW_READY: '可确认接管',
  CONFIRMED: '已确认', FAILED: '解析失败',
}
const blockingIssues = computed(() => batch.value?.issues.filter((item) => item.blocking) ?? [])
const filteredIssues = computed(() => {
  const query = issueQuery.value.trim().toLowerCase()
  if (!query) return batch.value?.issues ?? []
  return (batch.value?.issues ?? []).filter((item) => [item.code, item.message, item.sheetName, item.fieldName, item.rawValue].join(' ').toLowerCase().includes(query))
})
const profileName = computed(() => String(batch.value?.profile?.name ?? batch.value?.profile?.profile_code ?? '未识别'))
const canConfirm = computed(() => batch.value?.batchState === 'PREVIEW_READY' && blockingIssues.value.length === 0 && batch.value.status === 'PREVIEW')

async function loadRecent() {
  if (props.sourceMode !== 'live') return
  try {
    recent.value = await listImportBatches(props.factoryId)
  } catch (cause) {
    error.value = `历史批次读取失败：${getApiErrorMessage(cause)}`
  }
}

watch(() => [props.open, props.factoryId] as const, async ([open]) => {
  if (!open) return
  file.value = null
  batch.value = null
  error.value = ''
  masterReason.value = ''
  await loadRecent()
}, { immediate: true })

async function upload() {
  if (!file.value || !props.canImport || busy.value) return
  busy.value = true
  error.value = ''
  try {
    batch.value = await uploadImportPreview(props.factoryId, file.value)
    await loadRecent()
  } catch (cause) {
    error.value = `导入预览失败：${getApiErrorMessage(cause)}`
  } finally {
    busy.value = false
  }
}

async function recover(batchId: string) {
  busy.value = true
  error.value = ''
  try {
    batch.value = await recoverImportBatch(props.factoryId, batchId)
  } catch (cause) {
    error.value = `批次恢复失败：${getApiErrorMessage(cause)}`
  } finally {
    busy.value = false
  }
}

async function retry() {
  if (!batch.value?.artifactAvailable || busy.value) return
  busy.value = true
  error.value = ''
  try {
    batch.value = await retryImportPreview(props.factoryId, batch.value)
  } catch (cause) {
    error.value = `重新识别失败：${getApiErrorMessage(cause)}`
  } finally {
    busy.value = false
  }
}

async function approveMasters() {
  if (!batch.value || !props.canManageMaster || masterReason.value.trim().length < 4 || busy.value) return
  busy.value = true
  error.value = ''
  try {
    batch.value = await approveImportMasterDifferences(props.factoryId, batch.value, masterReason.value.trim())
    masterReason.value = ''
  } catch (cause) {
    error.value = `主数据审批失败：${getApiErrorMessage(cause)}`
  } finally {
    busy.value = false
  }
}

async function confirm() {
  if (!batch.value || !canConfirm.value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    batch.value = await confirmImportBatch(props.factoryId, batch.value, props.businessDate)
    emit('confirmed', batch.value)
  } catch (cause) {
    error.value = `确认接管失败：${getApiErrorMessage(cause)}`
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div v-if="open" class="import-wizard-backdrop" role="presentation" @mousedown.self="emit('close')">
    <section class="import-wizard" role="dialog" aria-modal="true" aria-labelledby="import-wizard-title">
      <header>
        <div><FileSpreadsheet :size="22" /><div><strong id="import-wizard-title">导入计划表</strong><span>{{ factoryId }} · 业务日 {{ businessDate }}</span></div></div>
        <button type="button" aria-label="关闭导入向导" @click="emit('close')"><X :size="18" /></button>
      </header>

      <p v-if="sourceMode === 'fallback' || !canImport" class="wizard-banner error"><AlertTriangle :size="16" />当前为只读模式或账号缺少导入权限。</p>
      <p v-if="error" class="wizard-banner error"><AlertTriangle :size="16" />{{ error }}</p>

      <div v-if="!batch" class="wizard-upload-step">
        <label class="file-picker"><Upload :size="26" /><strong>选择 .xlsx 计划文件</strong><span>{{ file?.name || '文件只用于受限解析；服务端按批次和厂区隔离保存 72 小时' }}</span><input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" :disabled="!canImport || busy" @change="file = ($event.target as HTMLInputElement).files?.[0] ?? null" /></label>
        <button class="wizard-primary" :disabled="!file || !canImport || busy" @click="upload"><RefreshCw v-if="busy" :size="16" class="spinning" /><Upload v-else :size="16" />{{ busy ? '识别中' : '生成预览' }}</button>
        <div v-if="recent.length" class="recent-batches"><strong>恢复最近批次</strong><button v-for="item in recent" :key="item.id" @click="recover(item.id)"><span>{{ item.sourceFileName }}</span><b>{{ stateLabel[item.batchState] || item.batchState }} · r{{ item.revision }}</b></button></div>
      </div>

      <div v-else class="wizard-preview">
        <nav class="wizard-steps" aria-label="导入步骤"><span class="done">1 选择文件</span><span class="done">2 模板映射</span><span :class="{ done: batch.batchState === 'PREVIEW_READY' || batch.status === 'CONFIRMED' }">3 解析对账</span><span :class="{ done: batch.status === 'CONFIRMED' }">4 确认接管</span></nav>
        <div class="batch-heading"><div><strong>{{ batch.sourceFileName }}</strong><span>批次 {{ batch.id }} · generation {{ batch.previewGeneration }} · r{{ batch.revision }}</span></div><em :class="batch.batchState.toLowerCase()">{{ stateLabel[batch.batchState] || batch.batchState }}</em></div>
        <div class="preview-cards"><article><span>Profile</span><strong>{{ profileName }}</strong><small>revision {{ batch.profile?.revision ?? '—' }}</small></article><article><span>已排基线</span><strong>{{ batch.scheduledBaselineTasks.length }}</strong><small>原计划锁定接管</small></article><article><span>待排订单</span><strong>{{ batch.backlogOrders.length }}</strong><small>不伪造 Task</small></article><article><span>阻断问题</span><strong>{{ blockingIssues.length }}</strong><small>不可一键绕过</small></article></div>

        <details open><summary>Sheet 角色与字段映射（{{ batch.mapping.length }}）</summary><div class="mapping-table"><div v-for="(item, index) in batch.mapping.slice(0, 80)" :key="index"><span>{{ item.source_header || item.source || item.cell_ref || '—' }}</span><b>{{ item.canonical_field || item.field_name || item.target || '未映射' }}</b><em>{{ item.status || item.match_status || '' }}</em></div></div></details>
        <details open><summary>问题与差异（{{ batch.issues.length }}）</summary><input v-model="issueQuery" class="issue-search" placeholder="按源行、字段、错误码筛选" /><div class="issue-list"><p v-for="issue in filteredIssues.slice(0, 120)" :key="issue.id" :class="{ blocking: issue.blocking }"><b>{{ issue.code }}</b><span>{{ issue.message }}</span><small>{{ issue.sheetName }}{{ issue.sourceRow ? ` · 行 ${issue.sourceRow}` : '' }}{{ issue.cellRef ? ` · ${issue.cellRef}` : '' }}</small></p><p v-if="!filteredIssues.length" class="empty"><CheckCircle2 :size="16" />当前筛选下无问题</p></div></details>
        <details><summary>对账动作（{{ batch.reconciliationActions.length }}）与计算差异（{{ batch.calculationComparisons.length }}）</summary><div class="action-list"><p v-for="(item, index) in batch.reconciliationActions.slice(0, 100)" :key="index"><b>{{ item.action_type }}</b><span>{{ item.reason_code || item.stable_order_key || item.stable_row_key }}</span></p></div></details>

        <div v-if="batch.batchState === 'MASTER_REVIEW_REQUIRED'" class="master-review"><p><AlertTriangle :size="16" />存在 {{ batch.masterDifferences.length }} 项主数据差异，需独立审批。</p><textarea v-model="masterReason" rows="2" placeholder="输入审批依据（至少 4 个字符）" :disabled="!canManageMaster" /><button :disabled="!canManageMaster || masterReason.trim().length < 4 || busy" @click="approveMasters">审批所列主数据并重新对账</button></div>
        <footer><button class="wizard-secondary" @click="batch = null">新建批次</button><button class="wizard-secondary" :disabled="!batch.artifactAvailable || busy || batch.status === 'CONFIRMED'" @click="retry"><RefreshCw :size="15" />用原文件重新识别</button><button class="wizard-primary" :disabled="!canConfirm || busy" @click="confirm"><CheckCircle2 :size="16" />{{ busy ? '处理中' : batch.status === 'CONFIRMED' ? '已确认' : '确认基线接管' }}</button></footer>
      </div>
    </section>
  </div>
</template>

<style scoped>
.import-wizard-backdrop{position:fixed;inset:0;z-index:70;background:rgba(5,13,24,.62);display:grid;place-items:center;padding:24px}.import-wizard{width:min(1100px,96vw);max-height:92vh;overflow:auto;background:#f8fafc;border:1px solid #cbd5e1;border-radius:18px;box-shadow:0 28px 80px rgba(15,23,42,.38);color:#0f172a}.import-wizard>header{position:sticky;top:0;z-index:2;display:flex;justify-content:space-between;align-items:center;padding:18px 22px;background:#fff;border-bottom:1px solid #e2e8f0}.import-wizard>header>div{display:flex;align-items:center;gap:12px}.import-wizard>header div div{display:grid}.import-wizard>header span{font-size:12px;color:#64748b}.import-wizard button{border:1px solid #cbd5e1;border-radius:9px;background:#fff;padding:9px 13px;cursor:pointer}.import-wizard button:disabled{opacity:.48;cursor:not-allowed}.wizard-banner{margin:14px 22px 0;padding:10px 12px;border-radius:9px;display:flex;gap:8px}.wizard-banner.error{background:#fff1f2;color:#be123c}.wizard-upload-step{padding:28px;display:grid;gap:16px}.file-picker{border:2px dashed #94a3b8;border-radius:14px;padding:34px;display:grid;place-items:center;gap:8px;background:#fff;cursor:pointer}.file-picker span{color:#64748b;font-size:13px}.file-picker input{margin-top:8px}.wizard-primary{display:inline-flex;align-items:center;justify-content:center;gap:7px;background:#0f766e!important;color:#fff;border-color:#0f766e!important}.wizard-secondary{display:inline-flex;gap:6px;align-items:center}.recent-batches{display:grid;gap:7px}.recent-batches>button{display:flex;justify-content:space-between;text-align:left}.recent-batches b{font-size:12px;color:#475569}.wizard-preview{padding:18px 22px 22px}.wizard-steps{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:16px}.wizard-steps span{padding:8px;border-radius:8px;background:#e2e8f0;color:#64748b;font-size:12px;text-align:center}.wizard-steps .done{background:#ccfbf1;color:#115e59}.batch-heading{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}.batch-heading>div{display:grid}.batch-heading span{font-size:12px;color:#64748b}.batch-heading em{font-style:normal;padding:6px 10px;border-radius:999px;background:#fef3c7;color:#92400e;font-size:12px}.batch-heading em.preview_ready,.batch-heading em.confirmed{background:#dcfce7;color:#166534}.preview-cards{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:15px}.preview-cards article{display:grid;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:12px}.preview-cards span,.preview-cards small{color:#64748b;font-size:12px}.preview-cards strong{font-size:20px}.wizard-preview details{background:#fff;border:1px solid #e2e8f0;border-radius:10px;margin:9px 0;padding:11px}.wizard-preview summary{cursor:pointer;font-weight:650}.mapping-table{margin-top:9px;max-height:230px;overflow:auto}.mapping-table>div{display:grid;grid-template-columns:1.2fr 1.2fr .6fr;gap:8px;padding:7px;border-top:1px solid #f1f5f9;font-size:12px}.mapping-table em{font-style:normal;color:#64748b}.issue-search{width:100%;box-sizing:border-box;margin:9px 0;padding:8px;border:1px solid #cbd5e1;border-radius:8px}.issue-list{max-height:260px;overflow:auto}.issue-list p,.action-list p{display:grid;grid-template-columns:170px 1fr auto;gap:8px;margin:0;padding:7px;border-top:1px solid #f1f5f9;font-size:12px}.issue-list p.blocking{background:#fff7ed}.issue-list small{color:#64748b}.issue-list .empty{display:flex;color:#166534}.master-review{margin-top:12px;padding:12px;border-radius:10px;background:#fff7ed}.master-review p{display:flex;gap:7px}.master-review textarea{width:100%;box-sizing:border-box;margin:6px 0;padding:8px}.wizard-preview footer{display:flex;justify-content:flex-end;gap:8px;margin-top:16px}@media(max-width:760px){.preview-cards{grid-template-columns:repeat(2,1fr)}.wizard-steps{grid-template-columns:repeat(2,1fr)}.mapping-table>div,.issue-list p{grid-template-columns:1fr}.import-wizard-backdrop{padding:8px}}
</style>
