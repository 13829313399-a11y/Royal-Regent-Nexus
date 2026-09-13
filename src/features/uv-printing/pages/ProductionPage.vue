<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ClipboardCheck, FileWarning, Link2, Plus, ShieldCheck, TriangleAlert } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import type {
  UvHandoverRecord,
  UvMachine,
  UvPrintJob,
  UvProduct,
  UvReport,
  UvScope,
} from '../contracts'
import { UV_CONTEXT_KEY, UV_TRANSPORT_KEY } from '../composables/uvPageContext'
import { newOperationId, useUvCommand, useUvRequest } from '../composables/useUvRequest'
import { useUvToast } from '../composables/useUvToast'
import UvStateBlock from '../components/UvStateBlock.vue'
import UvTable from '../components/UvTable.vue'
import UvStatusPill from '../components/UvStatusPill.vue'
import UvNumber from '../components/UvNumber.vue'
import UvFilterBar from '../components/UvFilterBar.vue'
import UvDrawer from '../components/UvDrawer.vue'
import UvField from '../components/UvField.vue'
import UvFormField from '../components/UvFormField.vue'
import UvConfirmDialog from '../components/UvConfirmDialog.vue'
import JobReconcileDrawer from '../components/JobReconcileDrawer.vue'
import QuickReportDrawer from '../components/QuickReportDrawer.vue'
import { HANDOVER_STATE, QUALITY_STATUS, RAW_UNIT, RECONCILIATION, REPORT_STATUS, SOURCE_KIND, TIME_EVIDENCE_LABEL } from '../domain/status'
import { QUALITY_BUCKET_LABELS, QUALITY_BUCKETS, qualityDifference, validateQuality } from '../domain/quality'
import { shanghaiDateTimeString } from '../domain/businessTime'
import { formatDecimal, formatMoney } from '../domain/decimal'

/**
 * 生产记录：待核作业 / 有效报工 / 入库核数三个视角，主表与证据抽屉联动。
 *
 * - 草稿不计入有效产量、工资或经营产值；
 * - 更正保留原记录并创建新修订，前后数量差异可见；
 * - 操作栏是「关联、确认、补质量、更正」，不用含义模糊的统一「编辑」；
 * - 入库核数只做核数/交接，不冒充完整仓库库存系统。
 */

const ctx = inject(UV_CONTEXT_KEY)!
const transport = inject(UV_TRANSPORT_KEY)!
const route = useRoute()
const router = useRouter()
const toast = useUvToast()
const workspace = ctx.workspace
const scope = computed(() => workspace.scope.value)

type ViewKey = 'jobs' | 'reports' | 'handovers'

const VIEWS: Array<{ key: ViewKey; label: string; description: string }> = [
  { key: 'jobs', label: '待核采集作业', description: '设备发生的事实，需人工确认后才成为产量' },
  { key: 'reports', label: '有效报工', description: '车间确认做了多少件，是产量/工资/产值的主事实' },
  { key: 'handovers', label: '入库核数', description: '有人确认接收/交接多少件，可与报工有差异' },
]

const view = ref<ViewKey>((route.query.view as ViewKey) ?? 'reports')
const jobStatus = ref<string>((route.query.status as string) ?? '')
const reportStatus = ref<string>('')
const qualityFilter = ref<string>('')
const query = ref<string>('')
const selectedJob = ref<UvPrintJob | null>(null)
const reconcileOpen = ref(false)
const quickOpen = ref(false)
const detailReport = ref<UvReport | null>(null)

const jobRequest = useUvRequest<{ items: UvPrintJob[]; total: number }>(
  (signal) => transport.value.jobs({ ...scope.value, status: jobStatus.value || undefined, q: query.value || undefined, page_size: 200 }, signal),
  { watchSource: () => [scope.value.business_date, scope.value.shift, jobStatus.value, query.value, ctx.revision.value] },
)

const reportRequest = useUvRequest<{ items: UvReport[]; total: number }>(
  (signal) => transport.value.reports({ ...scope.value, status: reportStatus.value || undefined, q: query.value || undefined, page_size: 200 }, signal),
  { watchSource: () => [scope.value.business_date, scope.value.shift, reportStatus.value, query.value, ctx.revision.value] },
)

const handoverRequest = useUvRequest<{ items: UvHandoverRecord[]; total: number }>(
  (signal) => transport.value.handovers({ ...scope.value, page_size: 200 }, signal),
  { watchSource: () => [scope.value.business_date, ctx.revision.value] },
)

const machineRequest = useUvRequest<{ items: UvMachine[] }>(
  (signal) => transport.value.machines({ ...scope.value, page_size: 200 }, signal),
  { watchSource: () => [ctx.revision.value] },
)

const productRequest = useUvRequest<{ items: UvProduct[] }>(
  (signal) => transport.value.products({ ...scope.value, page_size: 200 }, signal),
  { watchSource: () => [ctx.revision.value] },
)

const jobs = computed(() => jobRequest.data.value?.items ?? [])
const reports = computed(() => reportRequest.data.value?.items ?? [])
const handovers = computed(() => handoverRequest.data.value?.items ?? [])
const machines = computed(() => machineRequest.data.value?.items ?? [])
const products = computed(() => productRequest.data.value?.items ?? [])

const confirmCommand = useUvCommand<unknown>()
const qualityCommand = useUvCommand<unknown>()
const correctionCommand = useUvCommand<unknown>()
const voidCommand = useUvCommand<unknown>()

const qualityEdit = ref<{ good: number; defective: number; pending: number; semi_finished: number }>({
  good: 0,
  defective: 0,
  pending: 0,
  semi_finished: 0,
})
const qualityReason = ref('')
const qualityOpen = ref(false)

const correctionOpen = ref(false)
const voidOpen = ref(false)
const correctionReason = ref('')
const correctionQty = ref('')
const correctionGood = ref('')
const correctionDefective = ref('')
const correctionPending = ref('')
const correctionSemi = ref('')

const handoverOpen = ref(false)
const handoverTarget = ref<UvHandoverRecord | null>(null)
const handoverReceived = ref('')
const handoverReceiver = ref('')
const handoverNote = ref('')

const selectedJobView = computed(() => selectedJob.value)

const filteredReports = computed(() => reports.value.filter((report) => {
  if (qualityFilter.value === 'pending') return report.quality_status !== 'complete'
  if (qualityFilter.value === 'unpriced') return report.commercial?.pricing_state !== 'priced'
  if (qualityFilter.value === 'draft') return report.status === 'draft'
  if (qualityFilter.value === 'corrected') return report.status === 'corrected' || report.replaces_report_id !== null
  return true
}))

const activeReports = computed(() => filteredReports.value.filter((report) => report.status !== 'voided'))

const counters = computed(() => ({
  jobs: jobs.value.length,
  unmatched: jobs.value.filter((job) => job.reconciliation === 'unmatched').length,
  needsUnit: jobs.value.filter((job) => job.reconciliation === 'needs_unit').length,
  drafts: reports.value.filter((report) => report.status === 'draft').length,
  qualityPending: activeReports.value.filter((report) => report.quality_status !== 'complete').length,
  unpriced: activeReports.value.filter((report) => report.commercial?.pricing_state !== 'priced').length,
  handoverDiff: handovers.value.filter((handover) => handover.state === 'difference').length,
}))

const filterChips = computed(() => {
  if (view.value === 'jobs') {
    return [
      {
        key: 'status',
        label: '核对状态',
        value: jobStatus.value,
        active: Boolean(jobStatus.value),
        options: [
          { value: '', label: '全部核对状态' },
          { value: 'unmatched', label: '产品未匹配' },
          { value: 'needs_unit', label: '数量单位待确认' },
          { value: 'ready', label: '可分配' },
          { value: 'partially_allocated', label: '部分已分配' },
          { value: 'allocated', label: '已分配完' },
          { value: 'ignored', label: '已忽略' },
        ],
      },
      { key: 'q', label: '搜索', value: query.value || '（未填写）', active: Boolean(query.value) },
    ]
  }
  if (view.value === 'reports') {
    return [
      {
        key: 'status',
        label: '报工状态',
        value: reportStatus.value,
        active: Boolean(reportStatus.value),
        options: [
          { value: '', label: '全部状态' },
          { value: 'draft', label: '草稿' },
          { value: 'confirmed', label: '已确认' },
          { value: 'corrected', label: '已更正' },
          { value: 'voided', label: '已作废' },
        ],
      },
      {
        key: 'quality',
        label: '附加视图',
        value: qualityFilter.value,
        active: Boolean(qualityFilter.value),
        options: [
          { value: '', label: '不加筛选' },
          { value: 'pending', label: '只看待质量核对' },
          { value: 'unpriced', label: '只看未定价' },
          { value: 'corrected', label: '只看更正记录' },
        ],
      },
      { key: 'q', label: '搜索', value: query.value || '（未填写）', active: Boolean(query.value) },
    ]
  }
  return []
})

function machineCode(machineId: string): string {
  return machines.value.find((machine) => machine.id === machineId)?.code ?? machineId
}

function productLabel(productId: string | null): string {
  if (!productId) return '未匹配'
  const product = products.value.find((candidate) => candidate.id === productId)
  return product ? `${product.product_no} · ${product.name}` : productId
}

function changeView(next: ViewKey) {
  view.value = next
  void router.replace({ query: { ...route.query, view: next } })
}

function onFilterChange(key: string, value: string) {
  if (key === 'status' && view.value === 'jobs') jobStatus.value = value
  else if (key === 'status') reportStatus.value = value
  else if (key === 'quality') qualityFilter.value = value
  else if (key === 'q') query.value = value === '（未填写）' ? '' : value
}

function clearFilters() {
  jobStatus.value = ''
  reportStatus.value = ''
  qualityFilter.value = ''
  query.value = ''
}

function openReconcile(job: UvPrintJob) {
  selectedJob.value = job
  reconcileOpen.value = true
}

function openReport(report: UvReport) {
  detailReport.value = report
}

function qualitySummary(report: UvReport): string {
  return `${QUALITY_BUCKET_LABELS.good} ${report.good_qty} / ${QUALITY_BUCKET_LABELS.defective} ${report.defective_qty} / ${QUALITY_BUCKET_LABELS.pending} ${report.pending_qty} / ${QUALITY_BUCKET_LABELS.semi_finished} ${report.semi_finished_qty}`
}

async function confirmReport(report: UvReport) {
  const operationId = newOperationId()
  const result = await confirmCommand.execute(operationId, async () => {
    const response = await transport.value.confirmReport({
      factory_id: 'huakang-a',
      operation_id: operationId,
      expected_version: report.version,
      report_id: report.id,
    })
    return response.data
  })
  if (!result) return
  ctx.markDirty()
  detailReport.value = null
  toast.push({
    message: `已确认报工 ${report.product_no} ${report.reported_qty} 件`,
    detail: '确认时在同一事务重新校验剩余量与来源分配；缺价可确认但会标记未定价。',
    tone: 'green',
    retryable: false,
  })
}

function openQuality(report: UvReport) {
  detailReport.value = report
  qualityEdit.value = {
    good: report.good_qty,
    defective: report.defective_qty,
    pending: report.pending_qty,
    semi_finished: report.semi_finished_qty,
  }
  qualityReason.value = ''
  qualityOpen.value = true
}

const qualityTotal = computed(() =>
  qualityEdit.value.good + qualityEdit.value.defective + qualityEdit.value.pending + qualityEdit.value.semi_finished,
)

const qualityIssues = computed(() => {
  const report = detailReport.value
  if (!report) return []
  return validateQuality({
    reported_qty: report.reported_qty,
    good_qty: qualityEdit.value.good,
    defective_qty: qualityEdit.value.defective,
    pending_qty: qualityEdit.value.pending,
    semi_finished_qty: qualityEdit.value.semi_finished,
  })
})

async function saveQuality() {
  const report = detailReport.value
  if (!report || qualityIssues.value.length) return
  const operationId = newOperationId()
  const result = await qualityCommand.execute(operationId, async () => {
    const response = await transport.value.updateQuality({
      factory_id: 'huakang-a',
      operation_id: operationId,
      expected_version: report.version,
      report_id: report.id,
      quality: {
        reported_qty: report.reported_qty,
        good_qty: qualityEdit.value.good,
        defective_qty: qualityEdit.value.defective,
        pending_qty: qualityEdit.value.pending,
        semi_finished_qty: qualityEdit.value.semi_finished,
      },
      reason: qualityReason.value,
    })
    return response.data
  })
  if (!result) return
  ctx.markDirty()
  qualityOpen.value = false
  detailReport.value = null
  toast.push({
    message: `已保存质量修订：${report.product_no}`,
    detail: '已确认报工的补录同样创建可追溯修订，不原地覆盖后让已确认工资无声变化。',
    tone: 'green',
    retryable: false,
  })
}

function openCorrection(report: UvReport) {
  detailReport.value = report
  correctionReason.value = ''
  correctionQty.value = String(report.reported_qty)
  correctionGood.value = String(report.good_qty)
  correctionDefective.value = String(report.defective_qty)
  correctionPending.value = String(report.pending_qty)
  correctionSemi.value = String(report.semi_finished_qty)
  correctionOpen.value = true
}

const correctionDelta = computed(() => {
  const report = detailReport.value
  if (!report) return 0
  return Number(correctionQty.value || '0') - report.reported_qty
})

async function submitCorrection() {
  const report = detailReport.value
  if (!report || !correctionReason.value.trim()) return
  const operationId = newOperationId()
  const result = await correctionCommand.execute(operationId, async () => {
    const response = await transport.value.correctReport({
      factory_id: 'huakang-a',
      operation_id: operationId,
      expected_version: report.version,
      report_id: report.id,
      reason: correctionReason.value,
      correction: {
        factory_id: 'huakang-a',
        operation_id: operationId,
        expected_version: 0,
        business_date: report.business_date,
        shift: report.shift,
        shift_template_version_id: report.shift_template_version_id,
        machine_id: report.machine_id,
        product_id: report.product_id,
        process_version_id: report.process_version_id,
        reported_qty: Number(correctionQty.value || '0'),
        good_qty: Number(correctionGood.value || '0'),
        defective_qty: Number(correctionDefective.value || '0'),
        pending_qty: Number(correctionPending.value || '0'),
        semi_finished_qty: Number(correctionSemi.value || '0'),
        worker_ids: report.worker_ids,
        notes: report.notes,
        source_allocations: [],
        evidence_job_ids: [],
      },
    })
    return response.data
  })
  if (!result) return
  ctx.markDirty()
  correctionOpen.value = false
  detailReport.value = null
  toast.push({
    message: `已创建更正修订：${report.product_no}`,
    detail: '原记录保留为作废并反向抵消旧有效量；历史金额走更正，不做全表重算。',
    tone: 'green',
    retryable: false,
  })
}

async function submitVoid() {
  const report = detailReport.value
  if (!report || !correctionReason.value.trim()) return
  const operationId = newOperationId()
  const result = await voidCommand.execute(operationId, async () => {
    const response = await transport.value.voidReport({
      factory_id: 'huakang-a',
      operation_id: operationId,
      expected_version: report.version,
      report_id: report.id,
      reason: correctionReason.value,
    })
    return response.data
  })
  if (!result) return
  ctx.markDirty()
  voidOpen.value = false
  detailReport.value = null
  toast.push({
    message: `已作废报工 ${report.product_no}`,
    detail: '作废是明确的业务决定，事实记录保留；作废与重复怀疑不同。',
    tone: 'amber',
    retryable: false,
  })
}

function openHandover(record: UvHandoverRecord) {
  handoverTarget.value = record
  handoverReceived.value = String(record.received_qty)
  handoverReceiver.value = record.receiver
  handoverNote.value = record.note
  handoverOpen.value = true
}

async function saveHandover() {
  const record = handoverTarget.value
  if (!record) return
  const operationId = newOperationId()
  const result = await confirmCommand.execute(operationId, async () => {
    const response = await transport.value.saveHandover({
      factory_id: 'huakang-a',
      operation_id: operationId,
      expected_version: record.version,
      id: record.id,
      business_date: record.business_date,
      report_id: record.report_id,
      product_id: record.product_id,
      received_qty: Number(handoverReceived.value || '0'),
      receiver: handoverReceiver.value,
      note: handoverNote.value,
    })
    return response.data
  })
  if (!result) return
  ctx.markDirty()
  handoverOpen.value = false
  handoverTarget.value = null
  toast.push({
    message: `已保存交接核数：${record.product_no}`,
    detail: '核数不覆盖报工原值；未经 PMC 承接不宣布增加仓库库存。',
    tone: 'green',
    retryable: false,
  })
}

watch(() => route.query.view, (next) => {
  if (next === 'jobs' || next === 'reports' || next === 'handovers') view.value = next
})

watch(() => route.query.status, (next) => {
  if (typeof next === 'string') jobStatus.value = next
})
</script>

<template>
  <div class="space-y-4">
    <header class="uv-page-head">
      <div class="uv-page-head__titles">
        <p class="uv-page-head__eyebrow">Production Records</p>
        <h1>生产记录</h1>
        <p class="uv-page-head__desc">
          三种记录必须分清：设备记录是证据，人工确认才是产量，入库核数是交接。选中任意一行，右侧抽屉分三段说明「我看到了什么 / 我确认什么 / 会影响什么」。
        </p>
      </div>
      <div class="uv-page-head__actions">
        <Button variant="outline" type="button" @click="changeView('jobs')">
          <FileWarning class="size-4" aria-hidden="true" />
          待核 {{ counters.unmatched + counters.needsUnit }}
        </Button>
        <Button
          type="button"
          :disabled="!workspace.can('uv_printing:report')"
          @click="quickOpen = true"
        >
          <Plus class="size-4" aria-hidden="true" />
          快速报工
        </Button>
      </div>
    </header>

    <nav class="uv-filters" aria-label="生产记录视角">
      <div class="uv-filters__row">
        <div class="uv-check-row" role="tablist">
          <button
            v-for="item in VIEWS"
            :key="item.key"
            type="button"
            role="tab"
            class="uv-chip"
            :class="view === item.key ? 'uv-check--on' : ''"
            :aria-selected="view === item.key"
            @click="changeView(item.key)"
          >
            {{ item.label }}
          </button>
        </div>
        <div class="uv-filters__meta">
          <span class="uv-filters__summary">
            {{ VIEWS.find((item) => item.key === view)?.description }}
          </span>
        </div>
      </div>
    </nav>

    <UvFilterBar
      v-if="view !== 'handovers'"
      :chips="filterChips"
      :summary="`业务日 ${scope.business_date} · ${scope.shift ? (scope.shift === 'day' ? '白班' : '夜班') : '全天'}`"
      @change="onFilterChange"
      @clear="clearFilters"
    />

    <!-- 待核采集作业 -->
    <section v-if="view === 'jobs'" class="uv-panel" aria-label="待核采集作业">
      <div class="uv-panel__head">
        <div>
          <h2 class="uv-panel__title">采集作业（设备记录）</h2>
          <p class="uv-panel__subtitle">
            原始任务名、单位与时间证据都保留原样；「可分配量」只在单位与每板件数确认后产生，且累计分配不得超过可分配量。
          </p>
        </div>
        <div class="uv-actions">
          <UvStatusPill :status="{ label: `未匹配 ${counters.unmatched}`, tone: 'amber' }" compact />
          <UvStatusPill :status="{ label: `单位待确认 ${counters.needsUnit}`, tone: 'amber' }" compact />
        </div>
      </div>
      <div class="uv-panel__body uv-panel__body--flush">
        <UvStateBlock
          v-if="jobRequest.loading.value && !jobs.length"
          state="loading"
          subject="采集作业"
        />
        <UvStateBlock
          v-else-if="jobRequest.error.value"
          state="error"
          subject="采集作业"
          :message="jobRequest.error.value.message"
          retryable
          @retry="jobRequest.run"
        />
        <UvStateBlock
          v-else-if="!jobs.length"
          state="no-result"
          subject="采集作业"
          hint="当前筛选没有设备记录。采集缺席不阻塞人工报工。"
          @action="clearFilters"
        />
        <UvTable
          v-else
          :columns="[
            { key: 'task', label: '原始任务 / 产品名' },
            { key: 'machine', label: '机台', width: 92 },
            { key: 'state', label: '作业状态', width: 140 },
            { key: 'recon', label: '核对状态', width: 156 },
            { key: 'raw', label: '原始次数/单位', width: 140, align: 'right' },
            { key: 'available', label: '可分配量', width: 120, align: 'right' },
            { key: 'time', label: '完成时间', width: 168 },
            { key: 'action', label: '操作', width: 132, align: 'right' },
          ]"
          :min-width="1180"
          dense
          caption="采集作业待核清单"
        >
          <tr v-for="job in jobs" :key="job.id">
            <td>
              <span class="uv-row-primary">{{ job.raw_task_name }}</span>
              <span class="uv-row-sub">
                {{ job.raw_product_name ?? '软件未提供产品名' }} · 源作业 {{ job.source_job_id }}
                <template v-if="job.duplicate_suspect"> · 疑似相似（不自动删除）</template>
              </span>
            </td>
            <td>{{ machineCode(job.machine_id) }}</td>
            <td>
              <UvStatusPill
                :status="job.state === 'completed' ? { label: '已完成', tone: 'green' } : job.state === 'uncertain' ? { label: '完工不确定', tone: 'amber' } : job.state === 'cancelled' ? { label: '已取消', tone: 'slate' } : job.state === 'running' ? { label: '进行中', tone: 'teal' } : { label: '观察到', tone: 'slate' }"
                compact
              />
              <span class="uv-row-sub">{{ TIME_EVIDENCE_LABEL[job.time_evidence] }}</span>
            </td>
            <td><UvStatusPill :status="RECONCILIATION[job.reconciliation]" compact /></td>
            <td>
              <UvNumber :value="job.raw_count ?? null" state="missing" size="sm" />
              <span class="uv-row-sub">{{ RAW_UNIT[job.raw_unit] }}</span>
            </td>
            <td>
              <UvNumber
                :qty="job.available_piece_qty"
                size="sm"
                :state="job.available_piece_qty === null ? 'pending' : job.available_piece_qty === 0 ? 'zero' : 'normal'"
                unit="件"
              />
            </td>
            <td>
              <span class="uv-mono">{{ job.completed_at ? shanghaiDateTimeString(job.completed_at) : '时间待确认' }}</span>
            </td>
            <td style="text-align: right">
              <Button
                variant="outline"
                size="sm"
                type="button"
                @click="openReconcile(job)"
              >
                <Link2 class="size-3.5" aria-hidden="true" />
                关联 / 确认
              </Button>
            </td>
          </tr>
        </UvTable>
      </div>
    </section>

    <!-- 有效报工 -->
    <section v-else-if="view === 'reports'" class="uv-panel" aria-label="业务报工">
      <div class="uv-panel__head">
        <div>
          <h2 class="uv-panel__title">业务报工</h2>
          <p class="uv-panel__subtitle">
            价格与工资列只在有权限时显示；现场表不挤满财务列。草稿不计入有效产量与经营产值。
          </p>
        </div>
        <div class="uv-actions">
          <UvStatusPill :status="{ label: `草稿 ${counters.drafts}`, tone: 'slate' }" compact />
          <UvStatusPill :status="{ label: `待质量 ${counters.qualityPending}`, tone: 'amber' }" compact />
          <UvStatusPill v-if="workspace.can('uv_printing:cost_read')" :status="{ label: `未定价 ${counters.unpriced}`, tone: 'amber' }" compact />
        </div>
      </div>
      <div class="uv-panel__body uv-panel__body--flush">
        <UvStateBlock
          v-if="reportRequest.loading.value && !reports.length"
          state="loading"
          subject="业务报工"
        />
        <UvStateBlock
          v-else-if="reportRequest.error.value"
          state="error"
          subject="业务报工"
          :message="reportRequest.error.value.message"
          retryable
          @retry="reportRequest.run"
        />
        <UvStateBlock
          v-else-if="!filteredReports.length"
          state="no-result"
          subject="业务报工"
          hint="当前筛选没有报工记录；也可以直接在现场快速报工录入。"
          @action="clearFilters"
        />
        <UvTable
          v-else
          :columns="[
            { key: 'date', label: '业务日期', width: 116 },
            { key: 'shift', label: '班次', width: 82 },
            { key: 'machine', label: '机台', width: 92 },
            { key: 'product', label: '货号 / 品名' },
            { key: 'qty', label: '报工数量', width: 104, align: 'right' },
            { key: 'quality', label: '合格 / 不良 / 待判 / 半成品', width: 210 },
            { key: 'source', label: '来源', width: 116 },
            { key: 'match', label: '来源分配', width: 120, align: 'right' },
            { key: 'state', label: '处理状态', width: 132 },
            { key: 'action', label: '操作', width: 190, align: 'right' },
          ]"
          :min-width="1360"
          dense
          caption="业务报工清单"
        >
          <tr
            v-for="report in filteredReports"
            :key="report.id"
            :aria-selected="detailReport?.id === report.id"
            @click="openReport(report)"
          >
            <td>{{ report.business_date }}</td>
            <td>{{ report.shift === 'day' ? '白班' : '夜班' }}</td>
            <td>{{ machineCode(report.machine_id) }}</td>
            <td>
              <span class="uv-row-primary">{{ report.product_no }} · {{ report.product_name }}</span>
              <span class="uv-row-sub">{{ report.notes || '无备注' }}</span>
            </td>
            <td><UvNumber :qty="report.reported_qty" size="sm" /></td>
            <td>
              <span class="uv-mono">
                {{ report.good_qty }} / {{ report.defective_qty }} / {{ report.pending_qty }} / {{ report.semi_finished_qty }}
              </span>
              <div class="uv-stack" :aria-label="qualitySummary(report)">
                <span class="uv-stack__good" :style="{ width: `${(report.good_qty / Math.max(report.reported_qty, 1)) * 100}%` }" />
                <span class="uv-stack__defective" :style="{ width: `${(report.defective_qty / Math.max(report.reported_qty, 1)) * 100}%` }" />
                <span class="uv-stack__pending" :style="{ width: `${(report.pending_qty / Math.max(report.reported_qty, 1)) * 100}%` }" />
                <span class="uv-stack__semi" :style="{ width: `${(report.semi_finished_qty / Math.max(report.reported_qty, 1)) * 100}%` }" />
              </div>
            </td>
            <td><UvStatusPill :status="SOURCE_KIND[report.source_kind]" compact /></td>
            <td>
              <UvNumber :qty="report.allocation_total" size="sm" unit="件" />
              <span class="uv-row-sub">{{ report.allocation_total ? '已占用来源额度' : '无来源分配' }}</span>
            </td>
            <td>
              <UvStatusPill :status="REPORT_STATUS[report.status]" compact />
              <span class="uv-row-sub">
                <UvStatusPill :status="QUALITY_STATUS[report.quality_status]" compact />
              </span>
            </td>
            <td style="text-align: right">
              <div class="uv-actions uv-actions--end">
                <Button
                  v-if="report.status === 'draft'"
                  size="sm"
                  type="button"
                  :disabled="!workspace.can('uv_printing:report')"
                  @click.stop="confirmReport(report)"
                >
                  确认
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  type="button"
                  :disabled="!workspace.can('uv_printing:quality') || report.status === 'voided'"
                  @click.stop="openQuality(report)"
                >
                  补质量
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  type="button"
                  :disabled="!workspace.can('uv_printing:report') || report.status === 'voided'"
                  @click.stop="openCorrection(report)"
                >
                  更正
                </Button>
              </div>
            </td>
          </tr>
        </UvTable>
      </div>
    </section>

    <!-- 入库核数 -->
    <section v-else class="uv-panel" aria-label="入库核数与交接">
      <div class="uv-panel__head">
        <div>
          <h2 class="uv-panel__title">入库核数 / 交接记录</h2>
          <p class="uv-panel__subtitle">
            只做核数与交接：可以和报工有差异，但不覆盖报工原值，也不宣布仓库已收货。
          </p>
        </div>
        <div class="uv-actions">
          <UvStatusPill :status="{ label: `差异 ${counters.handoverDiff}`, tone: counters.handoverDiff ? 'amber' : 'green' }" compact />
        </div>
      </div>
      <div class="uv-panel__body uv-panel__body--flush">
        <UvStateBlock
          v-if="handoverRequest.loading.value && !handovers.length"
          state="loading"
          subject="入库核数"
        />
        <UvStateBlock
          v-else-if="handoverRequest.error.value"
          state="error"
          subject="入库核数"
          :message="handoverRequest.error.value.message"
          retryable
          @retry="handoverRequest.run"
        />
        <UvStateBlock
          v-else-if="!handovers.length"
          state="empty"
          subject="入库核数记录"
          compact
        />
        <UvTable
          v-else
          :columns="[
            { key: 'date', label: '交接日', width: 116 },
            { key: 'product', label: '货号 / 品名' },
            { key: 'reported', label: '报工数量', width: 110, align: 'right' },
            { key: 'received', label: '实际接收', width: 110, align: 'right' },
            { key: 'diff', label: '差异', width: 100, align: 'right' },
            { key: 'state', label: '状态', width: 140 },
            { key: 'receiver', label: '接收方', width: 140 },
            { key: 'action', label: '操作', width: 110, align: 'right' },
          ]"
          :min-width="1100"
          dense
          caption="入库核数清单"
        >
          <tr v-for="record in handovers" :key="record.id">
            <td>{{ record.business_date }}</td>
            <td>
              <span class="uv-row-primary">{{ record.product_no }} · {{ record.product_name }}</span>
              <span class="uv-row-sub">{{ record.note || '无备注' }}</span>
            </td>
            <td><UvNumber :qty="record.reported_qty" size="sm" /></td>
            <td><UvNumber :qty="record.received_qty" size="sm" /></td>
            <td>
              <UvNumber
                :qty="record.difference_qty"
                size="sm"
                :state="record.difference_qty === 0 ? 'normal' : 'pending'"
              />
            </td>
            <td><UvStatusPill :status="HANDOVER_STATE[record.state]" compact /></td>
            <td>{{ record.receiver || '待确认' }}</td>
            <td style="text-align: right">
              <Button
                variant="outline"
                size="sm"
                type="button"
                :disabled="!workspace.can('uv_printing:report')"
                @click="openHandover(record)"
              >
                核数
              </Button>
            </td>
          </tr>
        </UvTable>
      </div>
    </section>

    <!-- 报工详情 / 证据抽屉 -->
    <UvDrawer
      :open="Boolean(detailReport)"
      size="lg"
      :title="detailReport ? `报工详情 · ${detailReport.product_no}` : ''"
      :subtitle="detailReport ? `${detailReport.business_date} · ${detailReport.shift === 'day' ? '白班' : '夜班'} · ${machineCode(detailReport.machine_id)}` : ''"
      @close="detailReport = null"
    >
      <template v-if="detailReport">
        <div class="uv-section">
          <p class="uv-section__title"><span class="uv-section__index">1</span>我看到了什么（证据）</p>
          <dl class="uv-detail-grid">
            <UvField label="报工来源" :value="SOURCE_KIND[detailReport.source_kind].label" />
            <UvField label="来源分配" :value="detailReport.allocation_total ? `${detailReport.allocation_total} 件` : '未关联采集作业'" />
            <UvField label="工艺版本" :value="detailReport.process_version_id" mono />
            <UvField
              label="更正关联"
              :value="detailReport.replaces_report_id ? `替换 ${detailReport.replaces_report_id}` : null"
              missing-label="首轮原始报工"
            />
            <UvField label="创建 / 更新" :value="`${shanghaiDateTimeString(detailReport.created_at)} / ${shanghaiDateTimeString(detailReport.updated_at)}`" :span="2" />
            <UvField label="更正原因" :value="detailReport.correction_reason || null" missing-label="无" :span="2" />
          </dl>
        </div>

        <div class="uv-section">
          <p class="uv-section__title"><span class="uv-section__index">2</span>我确认什么（数量与质量）</p>
          <dl class="uv-detail-grid">
            <UvField label="报工数量" :value="`${detailReport.reported_qty} 件`" emphasis />
            <UvField label="合格" :value="`${detailReport.good_qty} 件`" />
            <UvField label="不良" :value="`${detailReport.defective_qty} 件`" />
            <UvField label="待判" :value="`${detailReport.pending_qty} 件`" />
            <UvField label="半成品" :value="`${detailReport.semi_finished_qty} 件`" />
            <UvField
              label="守恒检查"
              :value="qualityDifference(detailReport) === 0 ? '分桶合计等于报工数量' : `差额 ${qualityDifference(detailReport)} 件`"
            />
            <UvField label="参与人员" :value="detailReport.worker_names.join('、') || null" missing-label="未排班" :span="2" />
          </dl>
          <div v-if="qualityDifference(detailReport) !== 0" class="uv-callout uv-callout--warning">
            分桶合计与报工数量不一致：系统提示具体差额，不自动抹平。
          </div>
        </div>

        <div class="uv-section">
          <p class="uv-section__title"><span class="uv-section__index">3</span>会影响什么</p>
          <dl class="uv-detail-grid">
            <UvField
              label="产值"
              :value="detailReport.commercial?.output_value ? formatMoney(detailReport.commercial.output_value) : null"
              :missing-label="detailReport.commercial?.pricing_state === 'unpriced' ? '未定价' : '没有成本权限'"
              :hint="detailReport.commercial?.unit_price ? `执行单价 ${formatDecimal(detailReport.commercial.unit_price, 6)} · 基准：已确认合格件` : ''"
            />
            <UvField
              label="面积参考产值"
              :value="detailReport.commercial?.area_value ? formatMoney(detailReport.commercial.area_value) : null"
              missing-label="无面积费率"
              hint="与按件产值是备选视角，绝不把二者相加"
            />
            <UvField
              label="班组计件工资"
              :value="detailReport.payroll?.amount ? formatMoney(detailReport.payroll.amount) : null"
              :missing-label="detailReport.payroll?.state === 'unpriced' ? '未定价' : '没有工资权限'"
              :hint="detailReport.payroll?.piece_wage ? `计件工价 ${formatDecimal(detailReport.payroll.piece_wage, 6)}（与商业价分开）` : ''"
            />
            <UvField
              label="工资状态"
              :value="detailReport.payroll ? (detailReport.payroll.state === 'confirmed' ? '已确认' : detailReport.payroll.state === 'provisional' ? '暂算待核' : '未定价') : null"
              missing-label="不适用"
            />
          </dl>

          <div v-if="detailReport.worker_shares?.length" class="uv-section">
            <p class="uv-section__title">个人分摊（余数按稳定员工顺序补最小币种单位）</p>
            <ul class="uv-list">
              <li v-for="share in detailReport.worker_shares" :key="share.worker_id">
                <span class="uv-list__dot" aria-hidden="true" />
                <span>{{ share.worker_name }}：{{ share.amount ? formatMoney(share.amount) : '未定价' }}</span>
              </li>
            </ul>
          </div>

          <div v-if="detailReport.status === 'voided'" class="uv-callout uv-callout--warning">
            <TriangleAlert class="inline size-3.5" aria-hidden="true" />
            该记录已作废：事实保留为审计证据，不再计入产量、工资与产值。
          </div>
          <div v-if="detailReport.status === 'draft'" class="uv-callout uv-callout--accent">
            <ClipboardCheck class="inline size-3.5" aria-hidden="true" />
            草稿不计入有效产量、工资或经营产值，也不消耗正式来源分配额度。
          </div>
          <p v-if="!workspace.can('uv_printing:quality')" class="uv-readonly-note">
            没有质量权限：补质量按钮不可用。
          </p>
        </div>

        <div v-if="qualityCommand.error.value || confirmCommand.error.value" class="uv-callout uv-callout--warning" role="alert">
          {{ (qualityCommand.error.value ?? confirmCommand.error.value)?.message }}
        </div>
      </template>

      <template #actions>
        <Button variant="outline" type="button" @click="detailReport = null">关闭</Button>
        <Button
          v-if="detailReport?.status === 'draft'"
          type="button"
          :disabled="!workspace.can('uv_printing:report') || confirmCommand.pending.value"
          @click="detailReport && confirmReport(detailReport)"
        >
          <ShieldCheck class="size-4" aria-hidden="true" />
          确认报工
        </Button>
        <Button
          v-if="detailReport && detailReport.status !== 'voided'"
          variant="outline"
          type="button"
          :disabled="!workspace.can('uv_printing:quality')"
          @click="detailReport && openQuality(detailReport)"
        >
          补质量
        </Button>
        <Button
          v-if="detailReport && detailReport.status !== 'voided'"
          variant="destructive"
          type="button"
          :disabled="!workspace.can('uv_printing:report')"
          @click="correctionReason = ''; voidOpen = true"
        >
          作废
        </Button>
      </template>
    </UvDrawer>

    <!-- 质量补录 -->
    <UvDrawer
      :open="qualityOpen"
      size="md"
      title="质量分桶核对"
      subtitle="reported = 合格 + 不良 + 待判 + 半成品；四个桶互斥且非负。"
      :busy="qualityCommand.pending.value"
      @close="qualityOpen = false"
    >
      <div v-if="detailReport" class="uv-form">
        <UvField label="报工数量（不可在此修改）" :value="`${detailReport.reported_qty} 件`" :span="2" />
        <UvFormField v-for="bucket in QUALITY_BUCKETS" :key="bucket" :label="QUALITY_BUCKET_LABELS[bucket]">
          <input v-model.number="qualityEdit[bucket]" class="uv-input" type="number" min="0" step="1">
        </UvFormField>
        <UvFormField label="补录原因" field-id="uv-q-reason" :span="2" help="会写入修订记录，便于追溯为什么数值变化。">
          <textarea id="uv-q-reason" v-model="qualityReason" class="uv-input uv-textarea" rows="2" />
        </UvFormField>
      </div>
      <div class="uv-callout" :class="qualityIssues.length ? 'uv-callout--warning' : ''">
        分桶合计 {{ qualityTotal }} 件 ·
        {{ qualityIssues.length ? qualityIssues.map((issue) => issue.message).join('；') : '守恒通过' }}
      </div>
      <p class="uv-state__hint">
        合格率按 合格 ÷（合格 + 不良）计算，分母为 0 显示「—」；待判与半成品不进入分母。
      </p>

      <template #actions>
        <Button variant="outline" type="button" @click="qualityOpen = false">取消</Button>
        <Button
          type="button"
          :disabled="Boolean(qualityIssues.length) || qualityCommand.pending.value"
          @click="saveQuality"
        >
          保存质量修订
        </Button>
      </template>
    </UvDrawer>

    <!-- 更正 -->
    <UvDrawer
      :open="correctionOpen"
      size="md"
      title="创建更正修订"
      subtitle="原记录不覆盖：作废原修订并反向抵消旧有效量，新修订引用原单。"
      :busy="correctionCommand.pending.value"
      @close="correctionOpen = false"
    >
      <div v-if="detailReport" class="uv-form">
        <UvField label="原数量" :value="`${detailReport.reported_qty} 件（${detailReport.good_qty} 合格）`" :span="2" />
        <UvFormField label="新报工数量" field-id="uv-c-qty">
          <input id="uv-c-qty" v-model="correctionQty" class="uv-input" type="number" min="0" step="1">
        </UvFormField>
        <UvFormField label="数量差异" :field-id="'uv-c-delta'">
          <p class="uv-input" :class="correctionDelta ? 'uv-callout--warning' : ''" style="display: flex; align-items: center">
            {{ correctionDelta > 0 ? `+${correctionDelta}` : correctionDelta }} 件
          </p>
        </UvFormField>
        <UvFormField label="合格" field-id="uv-c-good">
          <input id="uv-c-good" v-model="correctionGood" class="uv-input" type="number" min="0" step="1">
        </UvFormField>
        <UvFormField label="不良" field-id="uv-c-def">
          <input id="uv-c-def" v-model="correctionDefective" class="uv-input" type="number" min="0" step="1">
        </UvFormField>
        <UvFormField label="待判" field-id="uv-c-pending">
          <input id="uv-c-pending" v-model="correctionPending" class="uv-input" type="number" min="0" step="1">
        </UvFormField>
        <UvFormField label="半成品" field-id="uv-c-semi">
          <input id="uv-c-semi" v-model="correctionSemi" class="uv-input" type="number" min="0" step="1">
        </UvFormField>
        <UvFormField label="更正原因" required field-id="uv-c-reason" :span="2">
          <textarea id="uv-c-reason" v-model="correctionReason" class="uv-input uv-textarea" rows="2" placeholder="例如：入库核数发现 5 件外观不良" />
        </UvFormField>
      </div>
      <div class="uv-callout">
        历史金额走更正而不是全表重算；已关期间的更正必须产生有原因的调整。
      </div>

      <template #actions>
        <Button variant="outline" type="button" @click="correctionOpen = false">取消</Button>
        <Button
          type="button"
          :disabled="!correctionReason.trim() || correctionCommand.pending.value"
          @click="submitCorrection"
        >
          创建更正修订
        </Button>
      </template>
    </UvDrawer>

    <!-- 交接核数 -->
    <UvDrawer
      :open="handoverOpen"
      size="sm"
      title="入库核数"
      subtitle="核数记录不覆盖报工原值，也不代表 PMC 仓库已入账。"
      :busy="confirmCommand.pending.value"
      @close="handoverOpen = false"
    >
      <div v-if="handoverTarget" class="uv-form">
        <UvField label="产品" :value="`${handoverTarget.product_no} · ${handoverTarget.product_name}`" :span="2" />
        <UvField label="报工数量" :value="`${handoverTarget.reported_qty} 件`" />
        <UvFormField label="实际接收件数" field-id="uv-h-qty">
          <input id="uv-h-qty" v-model="handoverReceived" class="uv-input" type="number" min="0" step="1">
        </UvFormField>
        <UvFormField label="接收方" field-id="uv-h-receiver">
          <input id="uv-h-receiver" v-model="handoverReceiver" class="uv-input" type="text" placeholder="仓管姓名或岗位" >
        </UvFormField>
        <UvFormField label="备注" field-id="uv-h-note" :span="2">
          <textarea id="uv-h-note" v-model="handoverNote" class="uv-input uv-textarea" rows="2" />
        </UvFormField>
      </div>
      <div class="uv-callout">
        差异 = 实际接收 − 报工数量；留空接收方会保存为「待接收核对」。
      </div>

      <template #actions>
        <Button variant="outline" type="button" @click="handoverOpen = false">取消</Button>
        <Button type="button" :disabled="confirmCommand.pending.value" @click="saveHandover">保存核数</Button>
      </template>
    </UvDrawer>

    <UvConfirmDialog
      :open="voidOpen"
      title="作废这条报工"
      :impacts="[
        '原报工保留为审计证据，不会被删除',
        '该报工不再计入有效产量、工资与经营产值',
        '已占用的来源分配额度会被释放',
        detailReport ? `对象：${detailReport.product_no} ${detailReport.reported_qty} 件（${detailReport.id}）` : '',
      ].filter(Boolean)"
      confirm-label="确认作废"
      destructive
      require-reason
      reason-label="作废原因"
      :busy="voidCommand.pending.value"
      @cancel="voidOpen = false"
      @confirm="submitVoid"
    />

    <JobReconcileDrawer
      :open="reconcileOpen"
      :job="selectedJobView"
      :machines="machines"
      :products="products"
      @close="reconcileOpen = false; selectedJob = null"
      @saved="reconcileOpen = false; selectedJob = null"
    />

    <QuickReportDrawer
      v-if="quickOpen"
      :open="quickOpen"
      @close="quickOpen = false"
      @saved="quickOpen = false"
    />
  </div>
</template>
