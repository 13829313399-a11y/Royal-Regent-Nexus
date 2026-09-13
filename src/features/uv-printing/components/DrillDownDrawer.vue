<script setup lang="ts">
import { computed, inject, watch } from 'vue'
import { Ban } from '@lucide/vue'
import type {
  UvDrillKind,
  UvExpense,
  UvHandoverRecord,
  UvInkMovement,
  UvPayrollLine,
  UvPrintJob,
  UvReport,
  UvScope,
} from '../contracts'
import { UV_CONTEXT_KEY, UV_TRANSPORT_KEY } from '../composables/uvPageContext'
import { useUvRequest } from '../composables/useUvRequest'
import {
  EXPENSE_CATEGORY_LABELS,
  DRILL_KIND_LABELS,
  HANDOVER_STATE,
  INK_MOVEMENT_LABELS,
  JOB_STATE,
  QUALITY_STATUS,
  RECONCILIATION,
  SOURCE_KIND,
} from '../domain/status'
import { formatDecimal, formatMoney, trimTrailingZeros } from '../domain/decimal'
import { SHIFT_LABELS, shanghaiDateTimeString } from '../domain/businessTime'
import UvDrawer from './UvDrawer.vue'
import UvNumber from './UvNumber.vue'
import UvStateBlock from './UvStateBlock.vue'
import UvStatusPill from './UvStatusPill.vue'

/**
 * 下钻抽屉：任何指标/行点击后打开**对应的真实来源清单**。
 *
 * - 数据来自同一个 transport，并使用与报表完全相同的筛选范围；
 * - 每种来源有自己的字段与口径说明，不共用一张「通用表」假装能下钻；
 * - 个人工资明细还需要 uv_printing:payroll_read，缺权限时显示「未授权」而不是隐藏行；
 * - 读取失败显示错误与重试，绝不回落样例数据，也不显示 0。
 */

const props = withDefaults(defineProps<{
  open: boolean
  kind: UvDrillKind | null
  /** 下钻引用：类别、日期或空。 */
  drillRef: string | null
  /** 指标或行名称，用于标题与口径说明。 */
  subject: string
  scope: UvScope
  currency: string
  canReadCost: boolean
  canReadPayroll: boolean
  periodLabel: string
}>(), {})

const emit = defineEmits<{ close: [] }>()

const ctx = inject(UV_CONTEXT_KEY)!
const transport = inject(UV_TRANSPORT_KEY)!
const workspace = ctx.workspace

const isOpen = computed(() => props.open && props.kind !== null)
const kind = computed<UvDrillKind>(() => props.kind ?? 'reports')
const kindLabel = computed(() => DRILL_KIND_LABELS[kind.value])

const drillScope = computed<UvScope>(() => {
  const base = { ...props.scope, page_size: 200 }
  if (kind.value === 'expenses' && props.drillRef) return { ...base, status: props.drillRef }
  if (kind.value === 'ink_movements') return { ...base, status: 'issue_out' }
  return base
})

interface DrillData {
  reports: UvReport[]
  unpricedReports: UvReport[]
  jobs: UvPrintJob[]
  inkMovements: UvInkMovement[]
  expenses: UvExpense[]
  payroll: UvPayrollLine[]
  handovers: UvHandoverRecord[]
  note: string
}

async function loadDrill(signal: AbortSignal): Promise<DrillData> {
  const scope = drillScope.value
  const empty: DrillData = {
    reports: [], unpricedReports: [], jobs: [], inkMovements: [], expenses: [], payroll: [], handovers: [], note: '',
  }
  switch (kind.value) {
    case 'reports': {
      const response = await transport.value.reports(scope, signal)
      return { ...empty, reports: response.data.items }
    }
    case 'unpriced_reports': {
      const response = await transport.value.reports({ ...scope, page_size: 200 }, signal)
      return {
        ...empty,
        unpricedReports: response.data.items.filter(
          (report) => report.status !== 'voided' && report.commercial?.pricing_state !== 'priced',
        ),
      }
    }
    case 'jobs': {
      const response = await transport.value.jobs(scope, signal)
      return { ...empty, jobs: response.data.items }
    }
    case 'ink_movements': {
      const response = await transport.value.inkMovements(scope, signal)
      return { ...empty, inkMovements: response.data.items }
    }
    case 'expenses': {
      const response = await transport.value.expenses(scope, signal)
      return { ...empty, expenses: response.data.items }
    }
    case 'payroll': {
      const response = await transport.value.payrollPreview({
        ...scope,
        date_from: scope.date_from ?? scope.business_date,
        date_to: scope.date_to ?? scope.business_date,
      }, signal)
      return {
        ...empty,
        payroll: response.data.lines,
        note: response.data.unpriced_reports
          ? `${response.data.unpriced_reports} 条报工没有生效计件工价，相关行显示未定价而不是 0。`
          : response.data.unassigned_reports
            ? `${response.data.unassigned_reports} 条报工没有排班人员，未参与分摊。`
            : '',
      }
    }
    case 'handovers': {
      const response = await transport.value.handovers(scope, signal)
      return { ...empty, handovers: response.data.items }
    }
    default: {
      return empty
    }
  }
}

const request = useUvRequest<DrillData>(loadDrill, {
  watchSource: () => [
    isOpen.value,
    kind.value,
    props.drillRef,
    drillScope.value.business_date,
    drillScope.value.date_from,
    drillScope.value.date_to,
    drillScope.value.shift,
    ctx.revision.value,
  ],
  immediate: false,
})

watch(isOpen, (open) => {
  if (open) void request.run()
  else request.reset()
})

const data = computed(() => request.data.value)
const itemCount = computed(() => {
  const value = data.value
  if (!value) return 0
  switch (kind.value) {
    case 'reports': return value.reports.length
    case 'unpriced_reports': return value.unpricedReports.length
    case 'jobs': return value.jobs.length
    case 'ink_movements': return value.inkMovements.length
    case 'expenses': return value.expenses.length
    case 'payroll': return value.payroll.length
    case 'handovers': return value.handovers.length
    default: return 0
  }
})

const isEmpty = computed(() => request.settled.value && !request.loading.value && itemCount.value === 0)
const payrollForbidden = computed(() => kind.value === 'payroll' && !props.canReadPayroll)
const costForbidden = computed(() =>
  !props.canReadCost && (kind.value === 'expenses' || kind.value === 'ink_movements'),
)

const scopeLabel = computed(() => {
  const scope = props.scope
  const parts = [
    scope.business_date ? `业务日 ${scope.business_date}` : '',
    scope.date_from ? `从 ${scope.date_from}` : '',
    scope.date_to ? `到 ${scope.date_to}` : '',
    shiftLabelOf(scope.shift),
  ].filter(Boolean)
  return parts.join(' · ')
})

const drillNote = computed(() => {
  switch (kind.value) {
    case 'reports':
      return '业务报工：与报表同筛选范围的报工记录；草稿与已作废记录保留并标注状态，产值只按已确认且已定价的记录。'
    case 'unpriced_reports':
      return '未定价报工：没有生效执行价的记录。这些记录既不计入产值，也不按 0 计入，全部进入暂算说明。'
    case 'jobs':
      return '采集作业：设备事实，与业务报工分开。作业状态、核对状态与时间证据分别展示，未核对完的作业不代表产量。'
    case 'ink_movements':
      return '墨水流水：只列领用出库，油墨领用成本按流水金额合计；采购入库与人工录入的「油墨费用」按来源去重，不重复计入。'
    case 'expenses':
      return `费用记录：归属期 ${props.periodLabel} 内、发生日在本页筛选范围内的记录；不同币种分别列示，不折汇相加。`
    case 'payroll':
      return '工资明细：按同机同班同工作批次等分，余数补最小币种单位后合计完全一致；未定价与未排班分别标注。'
    case 'handovers':
      return '入库核数：核数差异不覆盖报工原值，也不代表仓库已入账。'
    default:
      return ''
  }
})

function reportMoney(report: UvReport, field: 'commercial' | 'payroll'): string {
  const value = field === 'commercial' ? report.commercial?.output_value : report.payroll?.amount
  return value ? formatMoney(value) : '—'
}

function formatAmount(value: string | null | undefined): string {
  return value === null || value === undefined ? '—' : formatDecimal(trimTrailingZeros(value), 2)
}

/** 班次一律用业务语言显示，不直接展示 day/night 枚举。 */
function shiftLabelOf(shift: 'day' | 'night' | 'all' | undefined): string {
  if (shift === undefined) return '全天'
  return SHIFT_LABELS[shift] ?? '全天'
}
</script>

<template>
  <UvDrawer
    :open="isOpen"
    :title="`${kindLabel} · ${subject}`"
    :subtitle="`${scopeLabel}${drillRef ? ` · 引用 ${drillRef}` : ''}`"
    size="lg"
    @close="emit('close')"
  >
    <div class="uv-drill-list">
      <p class="uv-callout">{{ drillNote }}</p>

      <UvStateBlock
        v-if="payrollForbidden"
        state="forbidden"
        subject="个人工资明细"
        message="当前账号在华康A生产部没有 uv_printing:payroll_read，工资明细不会下发到前端；这里不做「隐藏列」式权限控制，后端判定才是权威。"
      />

      <UvStateBlock
        v-else-if="costForbidden"
        state="forbidden"
        subject="费用与油墨金额"
        message="当前账号没有 uv_printing:cost_read，金额不会下发到前端；记录数量与状态仍可核对，但这里不显示金额，也不显示 0。"
      />

      <UvStateBlock
        v-else-if="request.loading.value"
        state="loading"
        :subject="kindLabel"
      />

      <UvStateBlock
        v-else-if="request.error.value"
        state="error"
        :subject="kindLabel"
        :message="request.error.value.message"
        :detail="request.error.value.code"
        retryable
        @retry="request.run"
      />

      <UvStateBlock
        v-else-if="isEmpty"
        state="empty"
        :subject="kindLabel"
        hint="当前筛选范围内没有对应来源记录；这是真实空数据，不是读取失败，也不会回落样例。"
      />

      <template v-else-if="data">
        <p class="uv-field__hint">
          共 {{ itemCount }} 条，最多展示 200 条；导出会使用与页面完全相同的筛选范围。
        </p>

        <!-- 业务报工 / 未定价报工 -->
        <template v-if="kind === 'reports' || kind === 'unpriced_reports'">
          <article
            v-for="report in (kind === 'reports' ? data.reports : data.unpricedReports)"
            :key="report.id"
            class="uv-drill-item"
          >
            <div class="uv-drill-item__head">
              <span class="uv-drill-item__title">
                {{ report.product_no }} · {{ report.product_name }}
              </span>
              <span class="uv-actions">
                <UvStatusPill :status="QUALITY_STATUS[report.quality_status]" compact />
                <UvStatusPill :status="SOURCE_KIND[report.source_kind]" compact />
              </span>
            </div>
            <div class="uv-drill-meta">
              <span>业务日 <strong>{{ report.business_date }}</strong></span>
              <span>班次 <strong>{{ shiftLabelOf(report.shift) }}</strong></span>
              <span>报工 <strong>{{ report.reported_qty }}</strong> 件</span>
              <span>合格 <strong>{{ report.good_qty }}</strong> 件</span>
              <span>不良 / 待判 / 半成品
                <strong>{{ report.defective_qty }} / {{ report.pending_qty }} / {{ report.semi_finished_qty }}</strong>
              </span>
              <span v-if="canReadCost">
                {{ report.commercial?.pricing_state === 'priced' ? '产值' : '产值（未定价）' }}
                <strong>{{ reportMoney(report, 'commercial') }}</strong>
              </span>
              <span v-if="canReadPayroll">
                班组计件工资 <strong>{{ reportMoney(report, 'payroll') }}</strong>
              </span>
              <span>人员 <strong>{{ report.worker_names.join('、') || '未排班' }}</strong></span>
            </div>
            <p v-if="report.notes" class="uv-row-sub">{{ report.notes }}</p>
          </article>
        </template>

        <!-- 采集作业 -->
        <template v-else-if="kind === 'jobs'">
          <article v-for="job in data.jobs" :key="job.id" class="uv-drill-item">
            <div class="uv-drill-item__head">
              <span class="uv-drill-item__title">{{ job.raw_task_name }}</span>
              <span class="uv-actions">
                <UvStatusPill :status="JOB_STATE[job.state]" compact />
                <UvStatusPill :status="RECONCILIATION[job.reconciliation]" compact />
              </span>
            </div>
            <div class="uv-drill-meta">
              <span>源作业 <strong>{{ job.source_job_id }}</strong></span>
              <span>开始 <strong>{{ job.started_at ? shanghaiDateTimeString(job.started_at) : '—' }}</strong></span>
              <span>结束 <strong>{{ job.completed_at ? shanghaiDateTimeString(job.completed_at) : '完工不确定' }}</strong></span>
              <span>原始数量 <strong>{{ job.raw_count ?? '—' }}</strong> · 单位 {{ job.raw_unit === 'unknown' ? '未声明' : job.raw_unit }}</span>
              <span>建议件数 <strong>{{ job.available_piece_qty ?? '待核对' }}</strong></span>
              <span>耗墨 <strong>{{ job.ink_total_ml ?? '设备未提供' }}</strong> ml</span>
              <span>时间证据 <strong>{{ job.time_evidence === 'observed' ? '设备时间' : job.time_evidence === 'inferred' ? '推断时间' : '时间待确认' }}</strong></span>
            </div>
            <p v-if="job.reconcile_note" class="uv-row-sub">{{ job.reconcile_note }}</p>
          </article>
        </template>

        <!-- 墨水流水 -->
        <template v-else-if="kind === 'ink_movements'">
          <article v-for="movement in data.inkMovements" :key="movement.id" class="uv-drill-item">
            <div class="uv-drill-item__head">
              <span class="uv-drill-item__title">{{ movement.sku_label }}</span>
              <span class="uv-num--pending">{{ INK_MOVEMENT_LABELS[movement.kind] }}</span>
            </div>
            <div class="uv-drill-meta">
              <span>发生日 <strong>{{ movement.occurred_on }}</strong></span>
              <span>领用 <strong>{{ formatAmount(movement.quantity_ml) }}</strong> ml</span>
              <span>结存 <strong>{{ formatAmount(movement.balance_after_ml) }}</strong> ml</span>
              <template v-if="canReadCost">
                <span>单价 <strong>{{ movement.unit_cost ? formatAmount(movement.unit_cost) : '缺单价' }}</strong></span>
                <span>金额 <strong>{{ movement.amount ? formatMoney(movement.amount) : '成本待核' }}</strong></span>
              </template>
              <span>凭证 <strong>{{ movement.source_doc || '无' }}</strong></span>
              <span>经办 <strong>{{ movement.created_by_name || '—' }}</strong></span>
            </div>
            <p v-if="movement.purpose" class="uv-row-sub">{{ movement.purpose }}</p>
          </article>
        </template>

        <!-- 费用记录 -->
        <template v-else-if="kind === 'expenses'">
          <article v-for="expense in data.expenses" :key="expense.id" class="uv-drill-item">
            <div class="uv-drill-item__head">
              <span class="uv-drill-item__title">{{ EXPENSE_CATEGORY_LABELS[expense.category] ?? '其他费用' }}</span>
              <span v-if="canReadCost" class="uv-drill-item__title">{{ formatMoney(expense.amount) }}</span>
            </div>
            <div class="uv-drill-meta">
              <span>发生日 <strong>{{ expense.occurred_on }}</strong></span>
              <span>归属期 <strong>{{ expense.period }}</strong></span>
              <span>币种 <strong>{{ expense.amount.currency }}</strong></span>
              <span>机台 <strong>{{ expense.machine_id ?? '全厂共用' }}</strong></span>
              <span>来源 <strong>{{ expense.source === 'ink_issue' ? '油墨出库' : expense.source === 'import' ? '导入归档' : '人工录入' }}</strong></span>
              <span>凭证 <strong>{{ expense.evidence || '无' }}</strong></span>
            </div>
            <p v-if="expense.note" class="uv-row-sub">{{ expense.note }}</p>
          </article>
        </template>

        <!-- 工资明细 -->
        <template v-else-if="kind === 'payroll'">
          <p v-if="data.note" class="uv-callout uv-callout--warning">{{ data.note }}</p>
          <article v-for="line in data.payroll" :key="line.worker_id" class="uv-drill-item">
            <div class="uv-drill-item__head">
              <span class="uv-drill-item__title">{{ line.worker_name }} · {{ line.employee_no || '无工号' }}</span>
              <span class="uv-drill-item__title">
                <UvNumber :money="line.amount" size="md" :state="line.amount === null ? 'unpriced' : 'normal'" />
              </span>
            </div>
            <div class="uv-drill-meta">
              <span>报工 <strong>{{ line.report_count }}</strong> 条</span>
              <span>合格 <strong>{{ line.good_qty }}</strong> 件</span>
              <span>工资状态 <strong>{{ line.state === 'confirmed' ? '已确认' : line.state === 'provisional' ? '暂算待核' : '未定价' }}</strong></span>
              <span>分摊依据 <strong>{{ line.allocation_basis }}</strong></span>
              <span>余数调整 <strong>{{ line.remainder_adjusted ? '已按最小币种单位补齐' : '无需补齐' }}</strong></span>
            </div>
            <p v-if="line.reason" class="uv-row-sub">{{ line.reason }}</p>
          </article>
        </template>

        <!-- 入库核数 -->
        <template v-else-if="kind === 'handovers'">
          <article v-for="handover in data.handovers" :key="handover.id" class="uv-drill-item">
            <div class="uv-drill-item__head">
              <span class="uv-drill-item__title">{{ handover.product_no }} · {{ handover.product_name }}</span>
              <UvStatusPill :status="HANDOVER_STATE[handover.state]" compact />
            </div>
            <div class="uv-drill-meta">
              <span>业务日 <strong>{{ handover.business_date }}</strong></span>
              <span>报工 <strong>{{ handover.reported_qty }}</strong> 件</span>
              <span>实收 <strong>{{ handover.received_qty }}</strong> 件</span>
              <span>差异 <strong>{{ handover.difference_qty }}</strong> 件</span>
              <span>接收方 <strong>{{ handover.receiver || '待确认' }}</strong></span>
            </div>
            <p v-if="handover.note" class="uv-row-sub">{{ handover.note }}</p>
          </article>
        </template>
      </template>

      <p v-if="workspace.isPreview.value" class="uv-field__hint">
        当前为样例预览：以上记录全部带 DEMO- 标记，只读浏览器内存。
      </p>
    </div>
  </UvDrawer>
</template>
