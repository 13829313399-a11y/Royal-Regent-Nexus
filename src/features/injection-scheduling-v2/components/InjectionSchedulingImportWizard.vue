<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { AlertTriangle, CheckCircle2, FileSpreadsheet, RefreshCw, Upload, X } from '@lucide/vue'
import { getApiErrorMessage } from '@/lib/http'
import {
  approveImportMasterDifferences,
  confirmImportBatch,
  listImportBatches,
  listImportProfiles,
  listMasterDataProposals,
  proposeImportProfile,
  recoverImportBatch,
  retryImportPreview,
  reviewMasterDataProposal,
  transitionImportProfile,
  updateImportMappingDraft,
  uploadImportPreview,
} from '../api/injectionSchedulingV2Api'
import type { FactoryId, ImportBatchRecord, ImportDocumentKindChoice } from '../types'

const props = defineProps<{
  open: boolean
  factoryId: FactoryId
  businessDate: string
  canImport: boolean
  canConfirmDemand?: boolean
  canProposeProfile?: boolean
  canProposeMasterData?: boolean
  canManageProfiles?: boolean
  canReviewSharedMolds?: boolean
  canActivateSharedMolds?: boolean
  canManageFactoryCapabilities?: boolean
  canManageSharedMoldPrices?: boolean
  canManageMaster: boolean
  initialBatchId?: string
  sourceMode: 'live' | 'fallback'
}>()
const emit = defineEmits<{ close: []; confirmed: [batch: ImportBatchRecord]; batchChange: [batchId: string] }>()

const file = ref<File | null>(null)
const batch = ref<ImportBatchRecord | null>(null)
const recent = ref<ImportBatchRecord[]>([])
const busy = ref(false)
const error = ref('')
const masterReason = ref('')
const issueQuery = ref('')
const documentKind = ref<ImportDocumentKindChoice>('AUTO')
const selectedRowIds = ref<string[]>([])
const mappingDraft = ref<Record<string, string>>({})
const profileProposalName = ref('')
const profileProposalReason = ref('')
const profiles = ref<Array<Record<string, unknown>>>([])
const profileTransitionReason = ref('')
const governanceProposals = ref<Array<Record<string, unknown>>>([])
const governanceReason = ref('')

const stateLabel: Record<string, string> = {
  IDENTIFYING: '识别中', MAPPING_REQUIRED: '需要字段映射', PROFILE_REVIEW_PENDING: 'Profile 待审核',
  MASTER_REVIEW_REQUIRED: '主数据待审批', RECONCILIATION_CONFLICT: '对账冲突', PREVIEW_READY: '可确认接管',
  RESOLUTION_REVIEW_REQUIRED: '字段解析待复核', PARTIALLY_CONFIRMED: '部分已确认',
  CONFIRMED: '已确认', FAILED: '解析失败',
}
const blockingIssues = computed(() => batch.value?.issues.filter((item) => item.blocking) ?? [])
const filteredIssues = computed(() => {
  const query = issueQuery.value.trim().toLowerCase()
  if (!query) return batch.value?.issues ?? []
  return (batch.value?.issues ?? []).filter((item) => [item.code, item.message, item.sheetName, item.fieldName, item.rawValue].join(' ').toLowerCase().includes(query))
})
const profileName = computed(() => String(batch.value?.profile?.name ?? batch.value?.profile?.profile_code ?? '未识别'))
const isDemandOrder = computed(() => batch.value?.documentKind === 'DEMAND_ORDER')
const isMasterData = computed(() => batch.value?.documentKind === 'MASTER_DATA')
const pendingReadyRows = computed(() => (batch.value?.demandRows ?? []).filter((row) => row.resolutionStatus === 'READY' && row.confirmationState === 'PENDING'))
const pendingMasterRows = computed(() => (batch.value?.masterDataRows ?? []).filter((row) => row.resolutionStatus === 'PROPOSABLE' && row.confirmationState === 'PENDING'))
const canConfirm = computed(() => {
  if (!batch.value || blockingIssues.value.length > 0 || batch.value.status === 'CONFIRMED') return false
  if (isDemandOrder.value) {
    return Boolean(props.canConfirmDemand) && ['PREVIEW_READY', 'PARTIALLY_CONFIRMED'].includes(batch.value.batchState) && selectedRowIds.value.length > 0
  }
  if (isMasterData.value) {
    return Boolean(props.canProposeMasterData) && ['PREVIEW_READY', 'PARTIALLY_CONFIRMED'].includes(batch.value.batchState) && selectedRowIds.value.length > 0
  }
  return batch.value.batchState === 'PREVIEW_READY' && batch.value.status === 'PREVIEW'
})

function adoptBatch(value: ImportBatchRecord) {
  batch.value = value
  const selectableRows = value.documentKind === 'MASTER_DATA' ? value.masterDataRows : value.demandRows
  selectedRowIds.value = selectableRows
    .filter((row) => row.resolutionStatus === (value.documentKind === 'MASTER_DATA' ? 'PROPOSABLE' : 'READY') && row.confirmationState === 'PENDING')
    .map((row) => row.rowId)
  const storedMappings = value.mappingDraft.mappings
  mappingDraft.value = storedMappings && typeof storedMappings === 'object'
    ? Object.fromEntries(Object.entries(storedMappings).map(([key, item]) => [key, String(item)]))
    : {}
  profileProposalName.value ||= `${String(value.profile?.name ?? '下单表')}字段别名修订`
  emit('batchChange', value.id)
}

const mappingReviewItems = computed(() => (batch.value?.mapping ?? []).filter((item) => String(item.status ?? '') !== 'MAPPED'))
const availableSourceHeaders = computed(() => [...new Set((batch.value?.mapping ?? []).map((item) => String(item.raw_header ?? '').trim()).filter(Boolean))])

function toggleRow(rowId: string, checked: boolean) {
  selectedRowIds.value = checked
    ? [...new Set([...selectedRowIds.value, rowId])]
    : selectedRowIds.value.filter((item) => item !== rowId)
}

function toggleAllReady(checked: boolean) {
  selectedRowIds.value = checked ? pendingReadyRows.value.map((row) => row.rowId) : []
}

function displayValue(value: unknown) {
  return value === null || value === undefined || value === '' ? '—' : String(value)
}

function proposalEntryCount(proposal: Record<string, unknown>) {
  const payload = proposal.payload
  if (!payload || typeof payload !== 'object' || !('entry_count' in payload)) return 0
  const count = Number(payload.entry_count)
  return Number.isFinite(count) ? count : 0
}

async function loadRecent() {
  if (props.sourceMode !== 'live') return
  try {
    recent.value = await listImportBatches(props.factoryId)
  } catch (cause) {
    error.value = `历史批次读取失败：${getApiErrorMessage(cause)}`
  }
}

async function loadProfiles() {
  if (!props.canManageProfiles || props.sourceMode !== 'live') return
  try {
    profiles.value = await listImportProfiles(props.factoryId)
  } catch (cause) {
    error.value = `Profile 列表读取失败：${getApiErrorMessage(cause)}`
  }
}

async function loadGovernanceProposals() {
  if ((!props.canReviewSharedMolds && !props.canActivateSharedMolds && !props.canManageFactoryCapabilities && !props.canManageSharedMoldPrices) || props.sourceMode !== 'live') return
  try {
    governanceProposals.value = await listMasterDataProposals(props.factoryId)
  } catch (cause) {
    error.value = `主数据提案读取失败：${getApiErrorMessage(cause)}`
  }
}

watch(() => [props.open, props.factoryId, props.initialBatchId] as const, async ([open]) => {
  if (!open) return
  file.value = null
  batch.value = null
  error.value = ''
  masterReason.value = ''
  await loadRecent()
  await loadProfiles()
  await loadGovernanceProposals()
  if (props.initialBatchId) await recover(props.initialBatchId)
}, { immediate: true })

async function upload() {
  if (!file.value || !props.canImport || busy.value) return
  busy.value = true
  error.value = ''
  try {
    adoptBatch(await uploadImportPreview(props.factoryId, file.value, documentKind.value))
    await loadRecent()
  } catch (cause) {
    error.value = `导入预览失败：${getApiErrorMessage(cause)}`
  } finally {
    busy.value = false
  }
}

async function transitionProfile(profile: Record<string, unknown>, target: 'activate' | 'retire') {
  if (!props.canManageProfiles || profileTransitionReason.value.trim().length < 8 || busy.value) return
  busy.value = true
  error.value = ''
  try {
    await transitionImportProfile(props.factoryId, profile, target, profileTransitionReason.value.trim())
    profileTransitionReason.value = ''
    await loadProfiles()
  } catch (cause) {
    error.value = `Profile 状态变更失败：${getApiErrorMessage(cause)}`
  } finally {
    busy.value = false
  }
}

async function reviewProposal(proposal: Record<string, unknown>, action: 'approve' | 'activate') {
  if (governanceReason.value.trim().length < 4 || busy.value) return
  busy.value = true
  error.value = ''
  try {
    await reviewMasterDataProposal(props.factoryId, proposal, action, governanceReason.value.trim())
    governanceReason.value = ''
    await loadGovernanceProposals()
  } catch (cause) {
    error.value = `主数据提案处理失败：${getApiErrorMessage(cause)}`
  } finally {
    busy.value = false
  }
}

async function recover(batchId: string) {
  busy.value = true
  error.value = ''
  try {
    adoptBatch(await recoverImportBatch(props.factoryId, batchId))
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
    adoptBatch(await retryImportPreview(props.factoryId, batch.value))
  } catch (cause) {
    error.value = `重新识别失败：${getApiErrorMessage(cause)}`
  } finally {
    busy.value = false
  }
}

async function saveMappingDraft() {
  if (!batch.value || busy.value || !Object.keys(mappingDraft.value).length) return
  busy.value = true
  error.value = ''
  try {
    adoptBatch(await updateImportMappingDraft(props.factoryId, batch.value, mappingDraft.value))
  } catch (cause) {
    error.value = `映射草案保存失败：${getApiErrorMessage(cause)}`
  } finally {
    busy.value = false
  }
}

async function submitProfileProposal() {
  if (!batch.value || !props.canProposeProfile || profileProposalReason.value.trim().length < 4 || busy.value) return
  busy.value = true
  error.value = ''
  try {
    adoptBatch(await proposeImportProfile(props.factoryId, batch.value, profileProposalName.value.trim(), profileProposalReason.value.trim()))
  } catch (cause) {
    error.value = `Profile 草案提交失败：${getApiErrorMessage(cause)}`
  } finally {
    busy.value = false
  }
}

async function approveMasters() {
  if (!batch.value || !props.canManageMaster || masterReason.value.trim().length < 4 || busy.value) return
  busy.value = true
  error.value = ''
  try {
    adoptBatch(await approveImportMasterDifferences(props.factoryId, batch.value, masterReason.value.trim()))
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
    const confirmed = await confirmImportBatch(props.factoryId, batch.value, props.businessDate, selectedRowIds.value)
    adoptBatch(confirmed)
    emit('confirmed', confirmed)
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
        <div><FileSpreadsheet :size="22" /><div><strong id="import-wizard-title">导入计划表 / 下单表</strong><span>{{ factoryId }} · 业务日 {{ businessDate }}</span></div></div>
        <button type="button" aria-label="关闭导入向导" @click="emit('close')"><X :size="18" /></button>
      </header>

      <p v-if="sourceMode === 'fallback' || !canImport" class="wizard-banner error"><AlertTriangle :size="16" />当前为只读模式或账号缺少导入权限。</p>
      <p v-if="error" class="wizard-banner error"><AlertTriangle :size="16" />{{ error }}</p>

      <div v-if="!batch" class="wizard-upload-step">
        <label class="document-kind"><span>文件类型</span><select v-model="documentKind" :disabled="busy"><option value="AUTO">自动识别（推荐）</option><option value="DEMAND_ORDER">客户下单表</option><option value="PLANNED_SCHEDULE">已排计划表</option><option value="SYSTEM_ROUND_TRIP">系统回写文件</option><option value="MASTER_DATA">共享模具 / 单价主数据</option></select><small>自动识别只接受已登记的文档签名或 Profile；不确定的文件会停在预览，不会写入排产。</small></label>
        <label class="file-picker"><Upload :size="26" /><strong>选择 .xlsx 计划或下单文件</strong><span>{{ file?.name || '文件只用于受限解析；服务端按批次和厂区隔离保存 72 小时' }}</span><input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" :disabled="!canImport || busy" @change="file = ($event.target as HTMLInputElement).files?.[0] ?? null" /></label>
        <button class="wizard-primary" :disabled="!file || !canImport || busy" @click="upload"><RefreshCw v-if="busy" :size="16" class="spinning" /><Upload v-else :size="16" />{{ busy ? '识别中' : '生成预览' }}</button>
        <div v-if="recent.length" class="recent-batches"><strong>恢复最近批次</strong><button v-for="item in recent" :key="item.id" @click="recover(item.id)"><span>{{ item.sourceFileName }}</span><b>{{ stateLabel[item.batchState] || item.batchState }} · r{{ item.revision }}</b></button></div>
        <details v-if="canReviewSharedMolds || canActivateSharedMolds || canManageFactoryCapabilities || canManageSharedMoldPrices" open><summary>已整理主数据提案（{{ governanceProposals.length }}）</summary><div class="mapping-editor"><p><AlertTriangle :size="15" />无需重复上传源表。公司模具与华兴机安能力独立治理；单价按原表值，以人民币、每啤/每模次、华兴全客户全合同口径激活。</p><input v-model="governanceReason" placeholder="审核或激活依据（至少 4 个字符）" /><div class="action-list"><p v-for="proposal in governanceProposals" :key="String(proposal.id)"><b>{{ proposal.entity_type }} · {{ proposal.action_type }}</b><span>{{ proposal.status }} · r{{ proposal.revision }} · {{ proposalEntryCount(proposal) }} 条来源 · {{ proposal.proposed_by_name || proposal.proposed_by }}</span><small><button v-if="proposal.status === 'PROPOSED' && (proposal.entity_type !== 'FACTORY_MOLD_CAPABILITY_BUNDLE' ? canReviewSharedMolds : canManageFactoryCapabilities)" :disabled="busy || governanceReason.trim().length < 4" @click="reviewProposal(proposal, 'approve')">独立批准</button><button v-if="proposal.status === 'APPROVED' && proposal.entity_type === 'MOLD_DEFINITION_BUNDLE' && canActivateSharedMolds" :disabled="busy || governanceReason.trim().length < 4" @click="reviewProposal(proposal, 'activate')">激活公司模具</button><button v-if="proposal.status === 'APPROVED' && proposal.entity_type === 'FACTORY_MOLD_CAPABILITY_BUNDLE' && canManageFactoryCapabilities" :disabled="busy || governanceReason.trim().length < 4" @click="reviewProposal(proposal, 'activate')">激活华兴机安能力</button><button v-if="proposal.status === 'APPROVED' && proposal.entity_type === 'COMMERCIAL_RATE_RULE' && canManageSharedMoldPrices" :disabled="busy || governanceReason.trim().length < 4" @click="reviewProposal(proposal, 'activate')">激活人民币单价</button></small></p></div></div></details>
      </div>

      <div v-else class="wizard-preview">
        <nav class="wizard-steps" aria-label="导入步骤"><span class="done">1 选择文件</span><span class="done">2 模板映射</span><span :class="{ done: batch.batchState === 'PREVIEW_READY' || batch.status === 'CONFIRMED' }">3 解析对账</span><span :class="{ done: batch.status === 'CONFIRMED' }">4 确认接管</span></nav>
        <div class="batch-heading"><div><strong>{{ batch.sourceFileName }}</strong><span>{{ batch.documentKind }} · 批次 {{ batch.id }} · generation {{ batch.previewGeneration }} · r{{ batch.revision }}</span></div><em :class="batch.batchState.toLowerCase()">{{ stateLabel[batch.batchState] || batch.batchState }}</em></div>
        <div class="preview-cards"><article><span>Profile</span><strong>{{ profileName }}</strong><small>revision {{ batch.profile?.revision ?? '—' }}</small></article><article><span>{{ isDemandOrder ? '需求行' : '已排基线' }}</span><strong>{{ isDemandOrder ? batch.demandRows.length : batch.scheduledBaselineTasks.length }}</strong><small>{{ isDemandOrder ? `可确认 ${pendingReadyRows.length} 行` : '原计划锁定接管' }}</small></article><article><span>{{ isDemandOrder ? '已选行' : '待排订单' }}</span><strong>{{ isDemandOrder ? selectedRowIds.length : batch.backlogOrders.length }}</strong><small>{{ isDemandOrder ? '只进入 DRAFT / BACKLOG' : '不伪造 Task' }}</small></article><article><span>阻断问题</span><strong>{{ blockingIssues.length }}</strong><small>不可一键绕过</small></article></div>

        <details v-if="isDemandOrder" open><summary>需求接收与模具补齐（{{ batch.demandRows.length }}）</summary><div class="demand-toolbar"><label><input type="checkbox" :checked="pendingReadyRows.length > 0 && selectedRowIds.length === pendingReadyRows.length" :disabled="!pendingReadyRows.length" @change="toggleAllReady(($event.target as HTMLInputElement).checked)" />选择全部可导入行</label><span>先导入有效下单行，再从模具库补齐；客户、价格和暂时未匹配的模具都不阻断进入待排池。</span></div><div class="demand-table"><div class="demand-head"><span>选择</span><span>源行</span><span>单号</span><span>款号 / 模号 / 产品</span><span>数量 / 交期</span><span>模具补齐</span><span>导入状态</span></div><div v-for="row in batch.demandRows" :key="row.rowId" class="demand-row"><span><input type="checkbox" :checked="selectedRowIds.includes(row.rowId)" :disabled="row.resolutionStatus !== 'READY' || row.confirmationState !== 'PENDING'" @change="toggleRow(row.rowId, ($event.target as HTMLInputElement).checked)" /></span><span>{{ displayValue(row.source.source_row) }}</span><span>{{ displayValue(row.canonical.source_document_no) }}</span><span>{{ displayValue(row.canonical.product_group_no) }} · {{ displayValue(row.canonical.source_mold_no) }}<small>{{ displayValue(row.canonical.product_name) }}</small></span><span>{{ displayValue(row.canonical.order_quantity) }}<small>{{ displayValue(row.canonical.delivery_due_date) }}</small></span><span>{{ displayValue(row.resolvedValues.mold_enrichment_status) }}<small>{{ displayValue(row.resolvedValues.factory_readiness_status) }}</small></span><span><b>{{ row.confirmationState === 'CONFIRMED' ? '已导入' : row.resolutionStatus }}</b><small>{{ row.resolutionReasons.join('、') || '可进入待排' }}</small></span></div></div></details>
        <details v-if="isMasterData" open><summary>主数据提案预览（{{ batch.masterDataRows.length }}）</summary><div class="demand-toolbar"><label><input type="checkbox" :checked="pendingMasterRows.length > 0 && selectedRowIds.length === pendingMasterRows.length" :disabled="!pendingMasterRows.length" @change="selectedRowIds = ($event.target as HTMLInputElement).checked ? pendingMasterRows.map((row) => row.rowId) : []" />选择全部可提案行</label><span>这里只创建 Proposal 和字段证据；批准前不激活模具或价格。</span></div><div class="demand-table"><div class="demand-head"><span>选择</span><span>Sheet / 行</span><span>类型</span><span>模号 / 货号</span><span>名称 / 单价</span><span>状态</span><span>激活边界</span></div><div v-for="row in batch.masterDataRows" :key="row.rowId" class="demand-row"><span><input type="checkbox" :checked="selectedRowIds.includes(row.rowId)" :disabled="row.resolutionStatus !== 'PROPOSABLE' || row.confirmationState !== 'PENDING'" @change="toggleRow(row.rowId, ($event.target as HTMLInputElement).checked)" /></span><span>{{ displayValue(row.source.sheet_name) }} / {{ displayValue(row.source.source_row) }}</span><span>{{ row.entityType }}</span><span>{{ displayValue(row.canonical.mold_no) }}<small>{{ displayValue(row.canonical.item_no) }}</small></span><span>{{ displayValue(row.canonical.product_name || row.canonical.mold_name) }}<small>{{ displayValue(row.canonical.amount) }} {{ displayValue(row.canonical.currency) }}</small></span><span><b>{{ row.confirmationState === 'PROPOSED' ? '已提案' : row.resolutionStatus }}</b></span><span><small>{{ row.activationBlockers.join('、') || '待独立审批' }}</small></span></div></div></details>
        <details v-if="canManageProfiles"><summary>Profile 版本治理（{{ profiles.length }}）</summary><div class="mapping-editor"><p><AlertTriangle :size="15" />激活、恢复启用和退役需要独立 Profile 管理权限；提交人不能批准自己的草案。</p><input v-model="profileTransitionReason" placeholder="状态变更依据（至少 8 个字符）" /><div class="action-list"><p v-for="profile in profiles" :key="String(profile.id)"><b>{{ profile.name }} · r{{ profile.revision }}</b><span>{{ profile.document_kind }} · {{ profile.status }} · lifecycle {{ profile.lifecycle_revision }}</span><small><button v-if="profile.status === 'PROFILE_DRAFT'" :disabled="busy || profileTransitionReason.trim().length < 8" @click="transitionProfile(profile, 'activate')">审核激活</button><button v-if="profile.status === 'RETIRED'" :disabled="busy || profileTransitionReason.trim().length < 8" @click="transitionProfile(profile, 'activate')">恢复启用</button><button v-if="profile.status === 'ACTIVE'" :disabled="busy || profileTransitionReason.trim().length < 8" @click="transitionProfile(profile, 'retire')">退役</button></small></p></div></div></details>
        <details v-if="canReviewSharedMolds || canActivateSharedMolds || canManageFactoryCapabilities"><summary>共享模具提案治理（{{ governanceProposals.length }}）</summary><div class="mapping-editor"><p><AlertTriangle :size="15" />审核与激活分步执行；先激活公司模具，再激活华兴机安能力。价格提案在合同及明确作用域签字前不能激活。</p><input v-model="governanceReason" placeholder="审核或激活依据（至少 4 个字符）" /><div class="action-list"><p v-for="proposal in governanceProposals" :key="String(proposal.id)"><b>{{ proposal.entity_type }} · {{ proposal.action_type }}</b><span>{{ proposal.status }} · r{{ proposal.revision }} · {{ proposal.proposed_by_name || proposal.proposed_by }}</span><small><button v-if="proposal.status === 'PROPOSED' && (proposal.entity_type !== 'FACTORY_MOLD_CAPABILITY_BUNDLE' ? canReviewSharedMolds : canManageFactoryCapabilities)" :disabled="busy || governanceReason.trim().length < 4" @click="reviewProposal(proposal, 'approve')">独立批准</button><button v-if="proposal.status === 'APPROVED' && proposal.entity_type === 'MOLD_DEFINITION_BUNDLE' && canActivateSharedMolds" :disabled="busy || governanceReason.trim().length < 4" @click="reviewProposal(proposal, 'activate')">激活公司模具</button><button v-if="proposal.status === 'APPROVED' && proposal.entity_type === 'FACTORY_MOLD_CAPABILITY_BUNDLE' && canManageFactoryCapabilities" :disabled="busy || governanceReason.trim().length < 4" @click="reviewProposal(proposal, 'activate')">激活华兴机安能力</button></small></p></div></div></details>

        <details open><summary>Sheet 角色与字段映射（{{ batch.mapping.length }}）</summary><div class="mapping-table"><div v-for="(item, index) in batch.mapping.slice(0, 80)" :key="index"><span>{{ item.raw_header || item.source_header || item.source || item.cell_ref || '—' }}</span><b>{{ item.canonical_field || item.field_name || item.target || '未映射' }}</b><em>{{ item.status || item.match_status || '' }}</em></div></div><div v-if="mappingReviewItems.length" class="mapping-editor"><p><AlertTriangle :size="15" />未知表头只保存为草案；须由另一位 Profile 管理员审核激活后，才能用原 artifact 重新识别。</p><label v-for="item in mappingReviewItems" :key="String(item.canonical_field)"><span>{{ item.canonical_field }}{{ item.required ? '（必填）' : '' }}</span><select v-model="mappingDraft[String(item.canonical_field)]"><option value="">选择来源表头</option><option v-for="header in availableSourceHeaders" :key="header" :value="header">{{ header }}</option></select></label><div class="mapping-actions"><button :disabled="busy || !Object.keys(mappingDraft).length" @click="saveMappingDraft">保存映射草案</button><input v-model="profileProposalName" placeholder="Profile 草案名称" /><input v-model="profileProposalReason" placeholder="提交依据（至少 4 个字符）" /><button :disabled="!canProposeProfile || busy || profileProposalReason.trim().length < 4 || !Object.keys(batch.mappingDraft).length" @click="submitProfileProposal">提交 Profile 审核</button></div><small v-if="!canProposeProfile">当前账号可编辑预览，但没有提交 Profile 草案权限。</small></div></details>
        <details open><summary>问题与差异（{{ batch.issues.length }}）</summary><input v-model="issueQuery" class="issue-search" placeholder="按源行、字段、错误码筛选" /><div class="issue-list"><p v-for="issue in filteredIssues.slice(0, 120)" :key="issue.id" :class="{ blocking: issue.blocking }"><b>{{ issue.code }}</b><span>{{ issue.message }}</span><small>{{ issue.sheetName }}{{ issue.sourceRow ? ` · 行 ${issue.sourceRow}` : '' }}{{ issue.cellRef ? ` · ${issue.cellRef}` : '' }}</small></p><p v-if="!filteredIssues.length" class="empty"><CheckCircle2 :size="16" />当前筛选下无问题</p></div></details>
        <details><summary>对账动作（{{ batch.reconciliationActions.length }}）与计算差异（{{ batch.calculationComparisons.length }}）</summary><div class="action-list"><p v-for="(item, index) in batch.reconciliationActions.slice(0, 100)" :key="index"><b>{{ item.action_type }}</b><span>{{ item.reason_code || item.stable_order_key || item.stable_row_key }}</span></p></div></details>

        <div v-if="batch.batchState === 'MASTER_REVIEW_REQUIRED'" class="master-review"><p><AlertTriangle :size="16" />存在 {{ batch.masterDifferences.length }} 项主数据差异，需独立审批。</p><textarea v-model="masterReason" rows="2" placeholder="输入审批依据（至少 4 个字符）" :disabled="!canManageMaster" /><button :disabled="!canManageMaster || masterReason.trim().length < 4 || busy" @click="approveMasters">审批所列主数据并重新对账</button></div>
        <footer><button class="wizard-secondary" @click="batch = null">新建批次</button><button class="wizard-secondary" :disabled="!batch.artifactAvailable || busy || batch.status === 'CONFIRMED'" @click="retry"><RefreshCw :size="15" />用原文件重新识别</button><button class="wizard-primary" :disabled="!canConfirm || busy" @click="confirm"><CheckCircle2 :size="16" />{{ busy ? '处理中' : batch.status === 'CONFIRMED' ? '已确认' : isDemandOrder ? `确认所选 ${selectedRowIds.length} 行进入待排` : isMasterData ? `提交所选 ${selectedRowIds.length} 条提案` : '确认基线接管' }}</button></footer>
      </div>
    </section>
  </div>
</template>

<style scoped>
.import-wizard-backdrop{position:fixed;inset:0;z-index:70;background:rgba(5,13,24,.62);display:grid;place-items:center;padding:24px}.import-wizard{width:min(1180px,96vw);max-height:92vh;overflow:auto;background:#f8fafc;border:1px solid #cbd5e1;border-radius:18px;box-shadow:0 28px 80px rgba(15,23,42,.38);color:#0f172a}.import-wizard>header{position:sticky;top:0;z-index:2;display:flex;justify-content:space-between;align-items:center;padding:18px 22px;background:#fff;border-bottom:1px solid #e2e8f0}.import-wizard>header>div{display:flex;align-items:center;gap:12px}.import-wizard>header div div{display:grid}.import-wizard>header span{font-size:12px;color:#64748b}.import-wizard button{border:1px solid #cbd5e1;border-radius:9px;background:#fff;padding:9px 13px;cursor:pointer}.import-wizard button:disabled{opacity:.48;cursor:not-allowed}.wizard-banner{margin:14px 22px 0;padding:10px 12px;border-radius:9px;display:flex;gap:8px}.wizard-banner.error{background:#fff1f2;color:#be123c}.wizard-upload-step{padding:28px;display:grid;gap:16px}.document-kind{display:grid;grid-template-columns:110px 1fr;align-items:center;gap:8px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:12px}.document-kind select{padding:9px;border:1px solid #cbd5e1;border-radius:8px;background:#fff}.document-kind small{grid-column:2;color:#64748b}.file-picker{border:2px dashed #94a3b8;border-radius:14px;padding:34px;display:grid;place-items:center;gap:8px;background:#fff;cursor:pointer}.file-picker span{color:#64748b;font-size:13px}.file-picker input{margin-top:8px}.wizard-primary{display:inline-flex;align-items:center;justify-content:center;gap:7px;background:#0f766e!important;color:#fff;border-color:#0f766e!important}.wizard-secondary{display:inline-flex;gap:6px;align-items:center}.recent-batches{display:grid;gap:7px}.recent-batches>button{display:flex;justify-content:space-between;text-align:left}.recent-batches b{font-size:12px;color:#475569}.wizard-preview{padding:18px 22px 22px}.wizard-steps{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:16px}.wizard-steps span{padding:8px;border-radius:8px;background:#e2e8f0;color:#64748b;font-size:12px;text-align:center}.wizard-steps .done{background:#ccfbf1;color:#115e59}.batch-heading{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}.batch-heading>div{display:grid}.batch-heading span{font-size:12px;color:#64748b}.batch-heading em{font-style:normal;padding:6px 10px;border-radius:999px;background:#fef3c7;color:#92400e;font-size:12px}.batch-heading em.preview_ready,.batch-heading em.partially_confirmed,.batch-heading em.confirmed{background:#dcfce7;color:#166534}.preview-cards{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:15px}.preview-cards article{display:grid;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:12px}.preview-cards span,.preview-cards small{color:#64748b;font-size:12px}.preview-cards strong{font-size:20px}.wizard-preview details{background:#fff;border:1px solid #e2e8f0;border-radius:10px;margin:9px 0;padding:11px}.wizard-preview summary{cursor:pointer;font-weight:650}.mapping-table{margin-top:9px;max-height:230px;overflow:auto}.mapping-table>div{display:grid;grid-template-columns:1.2fr 1.2fr .6fr;gap:8px;padding:7px;border-top:1px solid #f1f5f9;font-size:12px}.mapping-table em{font-style:normal;color:#64748b}.mapping-editor{margin-top:10px;padding:10px;background:#fff7ed;border-radius:9px;display:grid;gap:8px}.mapping-editor p{display:flex;gap:6px;margin:0;color:#9a3412}.mapping-editor>label{display:grid;grid-template-columns:220px 1fr;align-items:center;gap:8px}.mapping-editor select,.mapping-editor input{padding:8px;border:1px solid #cbd5e1;border-radius:7px;background:#fff}.mapping-actions{display:grid;grid-template-columns:auto 1fr 1.4fr auto;gap:8px}.demand-toolbar{display:flex;justify-content:space-between;gap:12px;margin:10px 0;color:#475569;font-size:12px}.demand-table{overflow:auto;max-height:340px}.demand-head,.demand-row{min-width:1000px;display:grid;grid-template-columns:55px 55px 1.15fr 1.45fr .9fr 1fr 1.15fr;gap:8px;align-items:center;padding:8px;border-top:1px solid #f1f5f9;font-size:12px}.demand-head{position:sticky;top:0;background:#f8fafc;font-weight:650;z-index:1}.demand-row>span{display:grid}.demand-row small{color:#64748b}.issue-search{width:100%;box-sizing:border-box;margin:9px 0;padding:8px;border:1px solid #cbd5e1;border-radius:8px}.issue-list{max-height:260px;overflow:auto}.issue-list p,.action-list p{display:grid;grid-template-columns:170px 1fr auto;gap:8px;margin:0;padding:7px;border-top:1px solid #f1f5f9;font-size:12px}.issue-list p.blocking{background:#fff7ed}.issue-list small{color:#64748b}.issue-list .empty{display:flex;color:#166534}.master-review{margin-top:12px;padding:12px;border-radius:10px;background:#fff7ed}.master-review p{display:flex;gap:7px}.master-review textarea{width:100%;box-sizing:border-box;margin:6px 0;padding:8px}.wizard-preview footer{display:flex;justify-content:flex-end;gap:8px;margin-top:16px}@media(max-width:760px){.preview-cards{grid-template-columns:repeat(2,1fr)}.wizard-steps{grid-template-columns:repeat(2,1fr)}.mapping-table>div,.issue-list p{grid-template-columns:1fr}.document-kind,.mapping-editor>label,.mapping-actions{grid-template-columns:1fr}.document-kind small{grid-column:1}.import-wizard-backdrop{padding:8px}}
</style>
