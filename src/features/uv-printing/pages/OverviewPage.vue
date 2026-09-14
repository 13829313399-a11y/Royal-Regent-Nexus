<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { AlertTriangle, ArrowRight, Boxes, ClipboardList, Droplets, Printer, UserCheck } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import type {
  UvHandoverRecord,
  UvInkBalance,
  UvInkSku,
  UvMachine,
  UvPrintJob,
  UvProduct,
  UvReport,
  UvSummary,
} from '../contracts'
import { UV_CONTEXT_KEY, UV_TRANSPORT_KEY } from '../composables/uvPageContext'
import { useUvRequest } from '../composables/useUvRequest'
import { useUvToast } from '../composables/useUvToast'
import UvStateBlock from '../components/UvStateBlock.vue'
import UvMachineCard from '../components/UvMachineCard.vue'
import UvNumber from '../components/UvNumber.vue'
import UvStatusPill from '../components/UvStatusPill.vue'
import UvTable from '../components/UvTable.vue'
import QuickReportDrawer from '../components/QuickReportDrawer.vue'
import { COVERAGE, HANDOVER_STATE, RECONCILIATION, REPORT_STATUS, SOURCE_KIND } from '../domain/status'
import { formatDuration, shanghaiDateTimeString, shanghaiTimeString } from '../domain/businessTime'
import { decimalSum, formatMoney } from '../domain/decimal'
import { readAllPages } from '../transport/pagination'

/**
 * 生产驾驶舱：首屏回答「现在要处理什么、哪些机器需要关注」。
 *
 * - 只有四个紧凑摘要，不做十几个同权重大 KPI；
 * - 机台矩阵是主视图，默认突出需要关注的机台；
 * - 「待处理」点击后打开已筛选的真实清单（本页内切换），处理完成只更新对应行和计数；
 * - 卡片上的产品名、今日合格数、运行状态可能来自不同时间尺度，各自带标签；
 * - 数字口径不同的字段不并成一个统计窗口。
 */

const ctx = inject(UV_CONTEXT_KEY)!
const transport = inject(UV_TRANSPORT_KEY)!
const route = useRoute()
const router = useRouter()
const toast = useUvToast()

const workspace = ctx.workspace
const scope = computed(() => workspace.scope.value)
const revision = ctx.revision

type FocusKey = 'all' | 'unmatched' | 'needs_unit' | 'quality' | 'low_ink' | 'handover'

const focus = ref<FocusKey>('all')
const selectedMachineId = ref<string | null>(null)
const quickOpen = ref(false)

const summaryRequest = useUvRequest<UvSummary>(
  (signal) => transport.value.summary(scope.value, signal),
  { watchSource: () => [scope.value.business_date, scope.value.shift, revision.value] },
)

const machineRequest = useUvRequest<{ items: UvMachine[] }>(
  (signal) => readAllPages((nextScope, nextSignal) => transport.value.machines(nextScope, nextSignal), scope.value, signal),
  { watchSource: () => [revision.value] },
)

const jobRequest = useUvRequest<{ items: UvPrintJob[] }>(
  (signal) => readAllPages((nextScope, nextSignal) => transport.value.jobs(nextScope, nextSignal), { ...scope.value, date_from: scope.value.business_date, date_to: scope.value.business_date }, signal),
  { watchSource: () => [scope.value.business_date, revision.value] },
)

const reportRequest = useUvRequest<{ items: UvReport[] }>(
  (signal) => readAllPages((nextScope, nextSignal) => transport.value.reports(nextScope, nextSignal), scope.value, signal),
  { watchSource: () => [scope.value.business_date, scope.value.shift, revision.value] },
)

const handoverRequest = useUvRequest<{ items: UvHandoverRecord[] }>(
  (signal) => readAllPages((nextScope, nextSignal) => transport.value.handovers(nextScope, nextSignal), scope.value, signal),
  { watchSource: () => [scope.value.business_date, revision.value] },
)

const skuRequest = useUvRequest<{ items: UvInkSku[] }>(
  (signal) => readAllPages((nextScope, nextSignal) => transport.value.inkSkus(nextScope, nextSignal), scope.value, signal),
  { watchSource: () => [revision.value] },
)

const balanceRequest = useUvRequest<{ items: UvInkBalance[] }>(
  (signal) => readAllPages((nextScope, nextSignal) => transport.value.inkBalances(nextScope, nextSignal), scope.value, signal),
  { watchSource: () => [revision.value] },
)

const productRequest = useUvRequest<{ items: UvProduct[] }>(
  (signal) => readAllPages((nextScope, nextSignal) => transport.value.products(nextScope, nextSignal), scope.value, signal),
  { watchSource: () => [revision.value] },
)

const summary = computed(() => summaryRequest.data.value)
const machines = computed(() => machineRequest.data.value?.items ?? [])
const jobs = computed(() => jobRequest.data.value?.items ?? [])
const reports = computed(() => reportRequest.data.value?.items ?? [])
const handovers = computed(() => handoverRequest.data.value?.items ?? [])
const skus = computed(() => skuRequest.data.value?.items ?? [])
const balances = computed(() => balanceRequest.data.value?.items ?? [])
const products = computed(() => productRequest.data.value?.items ?? [])

const anyLoading = computed(() =>
  summaryRequest.loading.value || machineRequest.loading.value || jobRequest.loading.value || reportRequest.loading.value,
)

const primaryError = computed(() =>
  summaryRequest.error.value ?? machineRequest.error.value ?? jobRequest.error.value ?? reportRequest.error.value,
)

const coverage = computed(() => COVERAGE[summaryRequest.coverage.value])

const confirmedReports = computed(() => reports.value.filter((report) => report.status === 'confirmed' || report.status === 'corrected'))
const activeReports = computed(() => reports.value.filter((report) => report.status !== 'voided'))

const unmatchedJobs = computed(() => jobs.value.filter((job) => job.reconciliation === 'unmatched'))
const needsUnitJobs = computed(() => jobs.value.filter((job) => job.reconciliation === 'needs_unit'))
const qualityReports = computed(() => activeReports.value.filter((report) => report.quality_status !== 'complete'))
const lowBalances = computed(() => balances.value.filter((balance) => balance.low_stock))
const differenceHandovers = computed(() => handovers.value.filter((handover) => handover.state === 'difference'))

const goodQty = computed(() => confirmedReports.value.reduce((total, report) => total + report.good_qty, 0))
const pendingQty = computed(() => confirmedReports.value.reduce((total, report) => total + report.pending_qty, 0))
const unpricedCount = computed(() => activeReports.value.filter((report) => report.commercial?.pricing_state !== 'priced').length)

const outputValue = computed(() => {
  if (!workspace.can('uv_printing:cost_read')) return null
  const priced = confirmedReports.value
    .map((report) => report.commercial?.output_value ?? null)
    .filter((value): value is { currency: string; amount: string } => value !== null)
  if (!priced.length) return null
  const currency = priced[0]!.currency
  if (priced.some((value) => value.currency !== currency)) return null
  return {
    currency,
    amount: decimalSum(priced.map((value) => value.amount)),
    partial: unpricedCount.value > 0,
  }
})

const attentionTotal = computed(() =>
  unmatchedJobs.value.length
  + needsUnitJobs.value.length
  + qualityReports.value.length
  + lowBalances.value.length
  + differenceHandovers.value.length,
)

const selectedMachine = computed(() => machines.value.find((machine) => machine.id === selectedMachineId.value) ?? null)

function machineGoodQty(machineId: string): number | null {
  const machineReports = confirmedReports.value.filter((report) => report.machine_id === machineId)
  if (!machineReports.length) return null
  return machineReports.reduce((total, report) => total + report.good_qty, 0)
}

function machineCrew(machineId: string): string[] {
  // 当班人员来自排班；这里只用报工工作人员名做轻量提示，避免再造一套排班读取。
  const names = new Set<string>()
  for (const report of activeReports.value.filter((candidate) => candidate.machine_id === machineId)) {
    for (const name of report.worker_names) names.add(name)
  }
  return [...names].slice(0, 3)
}

/** 机台排序：需要关注的排前面，但用户选择后不因为轮询跳位置。 */
const orderedMachines = computed(() => {
  const list = [...machines.value]
  return list.sort((a, b) => {
    const rank = (machine: UvMachine) => {
      if (machine.freshness === 'stale' || machine.freshness === 'never_seen') return 0
      if (machine.admin_status === 'maintenance' || machine.runtime_status === 'error') return 1
      if (machine.runtime_status === 'printing') return 2
      if (machine.admin_status === 'disabled') return 4
      return 3
    }
    return rank(a) - rank(b) || a.code.localeCompare(b.code, 'en')
  })
})

const workerSummary = computed(() => {
  const totalReports = confirmedReports.value.length
  const unassigned = confirmedReports.value.filter((report) => report.worker_ids.length === 0).length
  return { totalReports, unassigned }
})

const focusCards = computed(() => [
  {
    key: 'unmatched' as FocusKey,
    label: '产品未匹配',
    count: unmatchedJobs.value.length,
    hint: '原始任务名没有唯一对应产品，需人工确认',
    icon: ClipboardList,
  },
  {
    key: 'needs_unit' as FocusKey,
    label: '数量单位待确认',
    count: needsUnitJobs.value.length,
    hint: '适配器未声明单位时不自动乘每板件数',
    icon: Printer,
  },
  {
    key: 'quality' as FocusKey,
    label: '待质量核对',
    count: qualityReports.value.length,
    hint: '质量未判清前不进入良率分母',
    icon: UserCheck,
  },
  {
    key: 'low_ink' as FocusKey,
    label: '墨水低于阈值',
    count: lowBalances.value.length,
    hint: '按 SKU 独立比较，同色不同供应商不合并',
    icon: Droplets,
  },
  {
    key: 'handover' as FocusKey,
    label: '入库核数差异',
    count: differenceHandovers.value.length,
    hint: '核数差异不覆盖报工原值',
    icon: Boxes,
  },
])

function productLabel(productId: string | null): string {
  if (!productId) return '未匹配产品'
  const product = products.value.find((candidate) => candidate.id === productId)
  return product ? `${product.product_no} · ${product.name}` : productId
}

function machineCode(machineId: string): string {
  return machines.value.find((machine) => machine.id === machineId)?.code ?? machineId
}

function openProduction(status: string) {
  void router.push({ path: `${workspace.workspacePath}/production`, query: { ...route.query, view: 'jobs', status } })
}

function openInk(lowOnly: boolean) {
  void router.push({
    path: `${workspace.workspacePath}/ink`,
    query: { ...route.query, view: 'stock', low: lowOnly ? '1' : undefined },
  })
}

function openMachine(machineId: string) {
  void router.push({ path: `${workspace.workspacePath}/machines/${machineId}`, query: route.query })
}

function selectMachine(machineId: string) {
  selectedMachineId.value = selectedMachineId.value === machineId ? null : machineId
}

watch(primaryError, (error) => {
  if (error) toast.push({ message: '驾驶舱读取失败', detail: error.message, tone: 'red', retryable: true })
})

function retryAll() {
  void summaryRequest.run()
  void machineRequest.run()
  void jobRequest.run()
  void reportRequest.run()
  void handoverRequest.run()
  void skuRequest.run()
  void balanceRequest.run()
  void productRequest.run()
}
</script>

<template>
  <div class="space-y-4">
    <header class="uv-page-head">
      <div class="uv-page-head__titles">
        <p class="uv-page-head__eyebrow">Production Cockpit</p>
        <h1>生产驾驶舱</h1>
        <p class="uv-page-head__desc">
          先看需要处理的记录与机台，再看今天的产量口径。本页数字全部来自「已确认报工」，采集作业与入库核数各自独立。
        </p>
      </div>
      <div class="uv-page-head__actions">
        <UvStatusPill :status="coverage" compact />
        <span v-if="workspace.isReadOnly.value" class="uv-readonly-note">只读：没有报工权限</span>
        <Button type="button" size="lg" :disabled="!workspace.can('uv_printing:report')" @click="quickOpen = true">
          <Printer class="size-4" aria-hidden="true" />
          现场快速报工
        </Button>
      </div>
    </header>

    <UvStateBlock
      v-if="primaryError && !summary"
      state="error"
      subject="驾驶舱摘要"
      :message="primaryError.message"
      :detail="`业务日 ${scope.business_date}${scope.shift ? ` · 班次 ${scope.shift}` : ' · 全天'}`"
      retryable
      @retry="retryAll"
    />

    <UvStateBlock v-else-if="anyLoading && !summary" state="loading" subject="驾驶舱摘要" />

    <UvStateBlock
      v-else-if="!machines.length && !confirmedReports.length"
      state="empty"
      subject="机台与报工"
      hint="本厂区当前业务日没有机台主数据或报工记录；这是真实空数据，不是读取失败。"
    />

    <template v-else>
      <section class="uv-grid uv-grid--summary" aria-label="四个紧凑摘要">
        <div class="uv-summary-card">
          <p class="uv-summary-card__label">
            今日合格件数
            <span class="uv-field__hint">已确认报工</span>
          </p>
          <p class="uv-summary-card__value">{{ goodQty.toLocaleString('en-US') }}</p>
          <p class="uv-summary-card__meta">
            待判 {{ pendingQty }} 件 ·
            <button type="button" class="uv-row-button" style="display: inline" @click="focus = 'quality'">
              待质量核对 {{ qualityReports.length }} 条
            </button>
          </p>
        </div>

        <div class="uv-summary-card">
          <p class="uv-summary-card__label">
            在线机台
            <span class="uv-field__hint">心跳 5 分钟内</span>
          </p>
          <p class="uv-summary-card__value">
            {{ machines.filter((machine) => machine.freshness === 'fresh').length }}<span class="uv-num__unit">/{{ machines.length }}</span>
          </p>
          <p class="uv-summary-card__meta">
            有效机台（非停用）{{ machines.filter((machine) => machine.admin_status !== 'disabled').length }} 台 ·
            采集失联不等于停机
          </p>
        </div>

        <button
          type="button"
          class="uv-summary-card"
          :class="attentionTotal ? 'uv-summary-card--attention' : ''"
          @click="focus = 'unmatched'"
        >
          <p class="uv-summary-card__label">
            待处理记录
            <AlertTriangle v-if="attentionTotal" class="size-3.5" aria-hidden="true" />
          </p>
          <p class="uv-summary-card__value">{{ attentionTotal }}</p>
          <p class="uv-summary-card__meta">未匹配 {{ unmatchedJobs.length }} · 单位待确认 {{ needsUnitJobs.length }} · 低库 {{ lowBalances.length }}</p>
        </button>

        <div class="uv-summary-card">
          <p class="uv-summary-card__label">
            今日产值
            <span class="uv-field__hint">合格件 × 商业执行价快照</span>
          </p>
          <p class="uv-summary-card__value">
            <UvNumber
              v-if="outputValue"
              :money="{ currency: outputValue.currency, amount: outputValue.amount }"
              size="lg"
            />
            <UvNumber v-else-if="!workspace.can('uv_printing:cost_read')" :value="null" state="pending" size="lg" />
            <UvNumber v-else :value="null" state="unpriced" size="lg" />
          </p>
          <p class="uv-summary-card__meta">
            <template v-if="!workspace.can('uv_printing:cost_read')">没有成本权限，产值不下发前端</template>
            <template v-else-if="unpricedCount">口径：暂算，{{ unpricedCount }} 条报工未定价</template>
            <template v-else>口径：已定价报工合计 · 不含面积参考产值</template>
          </p>
        </div>
      </section>

      <div class="uv-split uv-split--main-aside">
        <section class="uv-panel" aria-label="当前机台矩阵">
          <div class="uv-panel__head">
            <div>
              <h2 class="uv-panel__title">当前机台矩阵</h2>
              <p class="uv-panel__subtitle">
                行政状态、遥测状态、采集新鲜度是三个独立维度；点击机台进入详情，查看任务时序与原始证据。
              </p>
            </div>
            <div class="uv-actions">
              <Button variant="outline" size="sm" type="button" @click="retryAll">刷新矩阵</Button>
            </div>
          </div>
          <div class="uv-panel__body">
            <UvStateBlock
              v-if="machineRequest.loading.value && !machines.length"
              state="loading"
              subject="机台列表"
              compact
            />
            <UvStateBlock
              v-else-if="machineRequest.error.value"
              state="error"
              subject="机台列表"
              :message="machineRequest.error.value.message"
              retryable
              compact
              @retry="machineRequest.run"
            />
            <div v-else class="uv-machine-grid">
              <UvMachineCard
                v-for="machine in orderedMachines"
                :key="machine.id"
                :machine="machine"
                :good-qty="machineGoodQty(machine.id)"
                :reports="activeReports.filter((report) => report.machine_id === machine.id)"
                :crew="machineCrew(machine.id)"
                :as-of="workspace.sampleAsOf.value"
                :selected="selectedMachineId === machine.id"
                @open="selectMachine(machine.id)"
                @focus="selectedMachineId = machine.id"
              />
            </div>
          </div>
        </section>

        <aside class="uv-panel" aria-label="需要处理">
          <div class="uv-panel__head">
            <div>
              <h2 class="uv-panel__title">需要处理</h2>
              <p class="uv-panel__subtitle">逐项处理；处理完成后只更新对应行与计数，不强迫回首页。</p>
            </div>
          </div>
          <div class="uv-panel__body space-y-3">
            <button
              v-for="card in focusCards"
              :key="card.key"
              type="button"
              class="uv-summary-card"
              :class="[card.count ? 'uv-summary-card--attention' : '', focus === card.key ? 'ring-1 ring-teal-600' : '']"
              style="width: 100%"
              @click="focus = card.key"
            >
              <p class="uv-summary-card__label">
                <span>{{ card.label }}</span>
                <component :is="card.icon" class="size-3.5" aria-hidden="true" />
              </p>
              <p class="uv-summary-card__value">{{ card.count }}</p>
              <p class="uv-summary-card__meta">{{ card.hint }}</p>
            </button>

            <div class="uv-callout">
              <p><strong>排班人员</strong>：已确认报工 {{ workerSummary.totalReports }} 条，其中
                {{ workerSummary.unassigned }} 条没有排班人员，工资按「未排班」处理而不是 0。</p>
            </div>
          </div>
        </aside>
      </div>

      <section class="uv-panel" aria-label="待处理清单">
        <div class="uv-panel__head">
          <div>
            <h2 class="uv-panel__title">
              待处理清单 ·
              {{ focus === 'all' ? '全部' : focusCards.find((card) => card.key === focus)?.label }}
            </h2>
            <p class="uv-panel__subtitle">
              业务日 {{ scope.business_date }} · {{ scope.shift ? (scope.shift === 'day' ? '白班' : '夜班') : '全天' }}
            </p>
          </div>
          <div class="uv-actions">
            <Button variant="ghost" size="sm" type="button" @click="focus = 'all'">显示全部</Button>
          </div>
        </div>
        <div class="uv-panel__body uv-panel__body--flush">
          <UvStateBlock
            v-if="focus === 'all'"
            state="empty"
            subject="待处理清单选择"
            hint="在上面的「需要处理」里选择一类，这里会显示已筛选的真实清单。"
            compact
          />

          <UvTable
            v-else-if="focus === 'unmatched' || focus === 'needs_unit'"
            :columns="[
              { key: 'task', label: '原始任务名' },
              { key: 'machine', label: '机台', width: 96 },
              { key: 'state', label: '作业/核对状态', width: 150 },
              { key: 'candidates', label: '候选产品' },
              { key: 'time', label: '时间', width: 160 },
              { key: 'action', label: '处理', width: 120, align: 'right' },
            ]"
            :min-width="900"
            caption="待核对的采集作业"
          >
            <tr v-for="job in (focus === 'unmatched' ? unmatchedJobs : needsUnitJobs)" :key="job.id">
              <td>
                <span class="uv-row-primary">{{ job.raw_task_name }}</span>
                <span class="uv-row-sub">{{ job.raw_product_name ?? '原始产品名缺失' }} · 源作业 {{ job.source_job_id }}</span>
              </td>
              <td>{{ machineCode(job.machine_id) }}</td>
              <td>
                <UvStatusPill :status="RECONCILIATION[job.reconciliation]" compact />
                <span class="uv-row-sub">原始次数 {{ job.raw_count ?? '—' }} · 单位 {{ job.raw_unit === 'unknown' ? '未声明' : job.raw_unit }}</span>
              </td>
              <td>
                <ul class="uv-list">
                  <li v-for="candidate in job.candidates" :key="candidate.product_id">
                    <span class="uv-list__dot" aria-hidden="true" />
                    <span>{{ productLabel(candidate.product_id) }}<span class="uv-row-sub">（{{ candidate.reason }}）</span></span>
                  </li>
                  <li v-if="!job.candidates.length"><span class="uv-list__dot" aria-hidden="true" />没有候选产品，需要人工指定</li>
                </ul>
              </td>
              <td>
                <span class="uv-mono">{{ job.completed_at ? shanghaiDateTimeString(job.completed_at) : shanghaiTimeString(job.started_at ?? '') }}</span>
                <span class="uv-row-sub">{{ job.time_evidence === 'inferred' ? '推断时间' : job.time_evidence === 'unknown' ? '时间待确认' : '设备时间' }}</span>
              </td>
              <td style="text-align: right">
                <Button variant="outline" size="sm" type="button" @click="openProduction(job.reconciliation)">
                  去核对
                </Button>
              </td>
            </tr>
          </UvTable>

          <UvTable
            v-else-if="focus === 'quality'"
            :columns="[
              { key: 'product', label: '货号 / 品名' },
              { key: 'machine', label: '机台', width: 96 },
              { key: 'qty', label: '报工 / 待判', width: 140 },
              { key: 'status', label: '质量状态', width: 150 },
              { key: 'action', label: '处理', width: 120, align: 'right' },
            ]"
            :min-width="820"
            caption="待质量核对的报工"
          >
            <tr v-for="report in qualityReports" :key="report.id">
              <td>
                <span class="uv-row-primary">{{ report.product_no }} · {{ report.product_name }}</span>
                <span class="uv-row-sub">{{ report.business_date }} · {{ report.shift === 'day' ? '白班' : '夜班' }}</span>
              </td>
              <td>{{ machineCode(report.machine_id) }}</td>
              <td>
                <UvNumber :qty="report.reported_qty" size="sm" />
                <span class="uv-row-sub">待判 {{ report.pending_qty }} · 半成品 {{ report.semi_finished_qty }}</span>
              </td>
              <td>
                <UvStatusPill :status="REPORT_STATUS[report.status]" compact />
                <span class="uv-row-sub">{{ report.quality_status === 'pending' ? '全部未判' : '部分已判' }}</span>
              </td>
              <td style="text-align: right">
                <Button variant="outline" size="sm" type="button" @click="openProduction('quality')">
                  补质量
                </Button>
              </td>
            </tr>
          </UvTable>

          <UvTable
            v-else-if="focus === 'low_ink'"
            :columns="[
              { key: 'sku', label: '墨水 SKU' },
              { key: 'available', label: '可用 ml', width: 120, align: 'right' },
              { key: 'bottles', label: '折合瓶数', width: 110, align: 'right' },
              { key: 'threshold', label: '阈值 ml', width: 110, align: 'right' },
              { key: 'action', label: '处理', width: 120, align: 'right' },
            ]"
            :min-width="760"
            caption="低于阈值的墨水 SKU"
          >
            <tr v-for="balance in lowBalances" :key="balance.sku_id">
              <td>
                <span class="uv-row-primary">
                  {{ skus.find((sku) => sku.id === balance.sku_id)?.supplier ?? '未知供应商' }} ·
                  {{ skus.find((sku) => sku.id === balance.sku_id)?.color ?? '未知颜色' }}
                </span>
                <span class="uv-row-sub">
                  材质 {{ skus.find((sku) => sku.id === balance.sku_id)?.material === 'hard' ? '硬墨' : skus.find((sku) => sku.id === balance.sku_id)?.material === 'soft' ? '软墨' : '其他' }}
                  · 包装 {{ balance.package_ml }}ml
                </span>
              </td>
              <td><UvNumber :decimal="balance.available_ml" :decimal-scale="1" size="sm" unit="ml" /></td>
              <td><UvNumber :decimal="balance.bottle_equivalent" :decimal-scale="2" size="sm" unit="瓶" /></td>
              <td><UvNumber :decimal="balance.threshold_ml" :decimal-scale="0" size="sm" unit="ml" /></td>
              <td style="text-align: right">
                <Button variant="outline" size="sm" type="button" @click="openInk(true)">去领用/入库</Button>
              </td>
            </tr>
          </UvTable>

          <UvTable
            v-else
            :columns="[
              { key: 'product', label: '货号 / 品名' },
              { key: 'date', label: '交接日', width: 116 },
              { key: 'qty', label: '报工 / 实收 / 差异', width: 180, align: 'right' },
              { key: 'state', label: '状态', width: 140 },
              { key: 'receiver', label: '接收方', width: 140 },
              { key: 'action', label: '处理', width: 120, align: 'right' },
            ]"
            :min-width="900"
            caption="入库核数差异"
          >
            <tr v-for="handover in differenceHandovers" :key="handover.id">
              <td>
                <span class="uv-row-primary">{{ handover.product_no }} · {{ handover.product_name }}</span>
                <span class="uv-row-sub">{{ handover.note || '核数记录不代表仓库已入账' }}</span>
              </td>
              <td>{{ handover.business_date }}</td>
              <td>
                {{ handover.reported_qty }} / {{ handover.received_qty }} /
                <UvNumber :qty="handover.difference_qty" size="sm" :state="handover.difference_qty === 0 ? 'normal' : 'pending'" />
              </td>
              <td><UvStatusPill :status="HANDOVER_STATE[handover.state]" compact /></td>
              <td>{{ handover.receiver || '待确认接收方' }}</td>
              <td style="text-align: right">
                <Button variant="outline" size="sm" type="button" @click="openProduction('handover')">去核对</Button>
              </td>
            </tr>
          </UvTable>
        </div>
      </section>

      <section class="uv-panel" aria-label="最近有效报工">
        <div class="uv-panel__head">
          <div>
            <h2 class="uv-panel__title">最近有效报工</h2>
            <p class="uv-panel__subtitle">
              只列已确认的报工。来源标签区分「设备记录」与「人工确认」；价格与工资列只在有权限时显示。
            </p>
          </div>
          <div class="uv-actions">
            <Button variant="outline" size="sm" type="button" @click="router.push({ path: `${workspace.workspacePath}/production`, query: route.query })">
              查看全部
              <ArrowRight class="size-3.5" aria-hidden="true" />
            </Button>
          </div>
        </div>
        <div class="uv-panel__body uv-panel__body--flush">
          <UvStateBlock
            v-if="reportRequest.error.value"
            state="error"
            subject="报工列表"
            :message="reportRequest.error.value.message"
            retryable
            compact
            @retry="reportRequest.run"
          />
          <UvStateBlock
            v-else-if="!confirmedReports.length"
            state="empty"
            subject="已确认报工"
            hint="本业务日还没有已确认报工；草稿不计入有效产量。"
            compact
          />
          <UvTable
            v-else
            :columns="[
              { key: 'machine', label: '机台', width: 96 },
              { key: 'product', label: '货号 / 品名' },
              { key: 'qty', label: '报工 / 合格', width: 130, align: 'right' },
              { key: 'quality', label: '质量四桶', width: 190 },
              { key: 'source', label: '来源', width: 120 },
              { key: 'workers', label: '人员', width: 170 },
              { key: 'state', label: '更正状态', width: 130 },
            ]"
            :min-width="1020"
            dense
            caption="最近有效报工"
          >
            <tr v-for="report in confirmedReports.slice(0, 12)" :key="report.id">
              <td>{{ machineCode(report.machine_id) }}</td>
              <td>
                <span class="uv-row-primary">{{ report.product_no }} · {{ report.product_name }}</span>
                <span class="uv-row-sub">{{ report.business_date }} · {{ report.shift === 'day' ? '白班' : '夜班' }}</span>
              </td>
              <td>
                <UvNumber :qty="report.reported_qty" size="sm" />
                <span class="uv-row-sub">合格 {{ report.good_qty }} · 待判 {{ report.pending_qty }}</span>
              </td>
              <td>
                <div class="uv-stack" :aria-label="`合格 ${report.good_qty}、不良 ${report.defective_qty}、待判 ${report.pending_qty}、半成品 ${report.semi_finished_qty}`">
                  <span class="uv-stack__good" :style="{ width: `${(report.good_qty / Math.max(report.reported_qty, 1)) * 100}%` }" />
                  <span class="uv-stack__defective" :style="{ width: `${(report.defective_qty / Math.max(report.reported_qty, 1)) * 100}%` }" />
                  <span class="uv-stack__pending" :style="{ width: `${(report.pending_qty / Math.max(report.reported_qty, 1)) * 100}%` }" />
                  <span class="uv-stack__semi" :style="{ width: `${(report.semi_finished_qty / Math.max(report.reported_qty, 1)) * 100}%` }" />
                </div>
                <span class="uv-row-sub">
                  良 {{ report.good_qty }} / 不良 {{ report.defective_qty }} / 待判 {{ report.pending_qty }} / 半成品 {{ report.semi_finished_qty }}
                </span>
              </td>
              <td><UvStatusPill :status="SOURCE_KIND[report.source_kind]" compact /></td>
              <td>
                <span v-if="report.worker_names.length">{{ report.worker_names.join('、') }}</span>
                <span v-else class="uv-num--pending">未排班</span>
              </td>
              <td>
                <UvStatusPill :status="REPORT_STATUS[report.status]" compact />
                <span v-if="report.correction_reason" class="uv-row-sub">{{ report.correction_reason }}</span>
              </td>
            </tr>
          </UvTable>
        </div>
      </section>
    </template>

    <Transition name="uv-drawer">
      <aside
        v-if="selectedMachine"
        class="uv-panel"
        style="position: fixed; right: 16px; bottom: 16px; z-index: 40; width: min(360px, calc(100vw - 32px))"
        aria-label="选中机台快捷操作"
      >
        <div class="uv-panel__head">
          <div>
            <h2 class="uv-panel__title">{{ selectedMachine.code }} · {{ selectedMachine.name }}</h2>
            <p class="uv-panel__subtitle">
              当前任务 {{ selectedMachine.current_task_name ?? '无' }} · 最后心跳
              {{ selectedMachine.last_heartbeat_at ? shanghaiDateTimeString(selectedMachine.last_heartbeat_at) : '从未上报' }}
            </p>
          </div>
        </div>
        <div class="uv-panel__body uv-actions">
          <Button type="button" size="sm" @click="openMachine(selectedMachine.id)">打开机台详情</Button>
          <Button variant="outline" size="sm" type="button" @click="selectedMachineId = null">关闭</Button>
        </div>
      </aside>
    </Transition>

    <QuickReportDrawer
      v-if="quickOpen"
      :open="quickOpen"
      @close="quickOpen = false"
      @saved="() => { quickOpen = false; ctx.markDirty() }"
    />
  </div>
</template>
