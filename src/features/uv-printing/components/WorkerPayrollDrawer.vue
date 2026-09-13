<script setup lang="ts">
import { computed } from 'vue'
import { AlertTriangle, Calculator, CheckCircle2, History, Info } from '@lucide/vue'
import type { BusinessDate, Money, UvPayrollState, UvWorkerRef } from '../contracts'
import { EMPLOY_STATE_LABELS, PAYROLL_STATE, QUALITY_STATUS, WORKER_ROLE_LABELS } from '../domain/status'
import type { StatusView } from '../domain/status'
import { SHIFT_LABELS } from '../domain/businessTime'
import { formatMoney } from '../domain/decimal'
import UvDrawer from './UvDrawer.vue'
import UvStatusPill from './UvStatusPill.vue'
import UvNumber from './UvNumber.vue'

/**
 * 员工工资抽屉（UV_PRINT_SHARED_SPEC.md 5.6 / 6.7）。
 *
 * - 工资构成：逐条报工给出 机台 / 产品 / 合格数 / 计件工价快照 / 金额；
 * - 分摊依据：同机同班同工作批次等分，余数按稳定员工顺序补最小币种单位，合计完全一致；
 * - 待核项：未定价 / 未排班 / 质量未判清 分别说明，金额缺失时显示「未定价」「未排班」「待核」，
 *   绝不显示 0 工资；
 * - 本抽屉只呈现计件工资，**不呈现任何商业执行价或产值**；
 * - 离职员工的历史排班与工资快照保留并标注为历史；当前排班改动不会改写已确认工资。
 */

export interface WorkerPayrollDetailRow {
  key: string
  reportId: string
  businessDate: BusinessDate
  shiftLabel: string
  machineLabel: string
  productLabel: string
  goodQty: number
  pieceWage: string | null
  rateVersionId: string | null
  amount: Money | null
  state: UvPayrollState
  reason: string
  /** 质量未判清：本行按已判合格量暂算。 */
  qualityPending: boolean
}

export interface WorkerPayrollAllocationParticipant {
  workerId: string
  workerName: string
  employeeNo: string
  amount: Money | null
  /** 该员工拿到余数补足的最小币种单位。 */
  remainderAdjusted: boolean
}

export interface WorkerPayrollAllocationGroup {
  key: string
  label: string
  currency: string
  batchTotal: Money | null
  participantCount: number
  baseShare: Money | null
  participants: WorkerPayrollAllocationParticipant[]
}

export interface WorkerPayrollPendingItem {
  key: 'unpriced' | 'unassigned' | 'quality'
  label: string
  count: number
  reason: string
}

const props = withDefaults(defineProps<{
  open: boolean
  worker: UvWorkerRef | null
  businessDate: BusinessDate
  dateFrom: BusinessDate
  dateTo: BusinessDate
  currency: string
  line: { report_count: number; good_qty: number; amount: Money | null; state: UvPayrollState; remainder_adjusted: boolean } | null
  /** 工资预览合计（同范围同名册口径）。 */
  previewTotal: Money | null
  previewState: UvPayrollState
  rows: WorkerPayrollDetailRow[]
  allocations: WorkerPayrollAllocationGroup[]
  pending: WorkerPayrollPendingItem[]
  /** 当前范围仍有未定价/未排班/待核报工时为 true。 */
  provisional: boolean
  canReadPayroll: boolean
}>(), {
  line: null,
  previewTotal: null,
  previewState: 'provisional',
})

const emit = defineEmits<{ close: [] }>()

const stateView = computed<StatusView>(() => PAYROLL_STATE[props.previewState])

function rowStateView(state: UvPayrollState): StatusView {
  return PAYROLL_STATE[state]
}

const isLeft = computed(() => props.worker?.employ_state === 'left')

const totalText = computed(() => {
  if (!props.canReadPayroll) return '没有查看工资的权限'
  if (!props.line || props.line.amount === null) {
    return props.previewState === 'unpriced' ? '未定价' : '待核'
  }
  return formatMoney(props.line.amount)
})

const totalHint = computed(() => {
  if (!props.canReadPayroll) {
    return '薪资数字由服务端按 payroll_read 权限下发；前端不猜测、不用样例补齐。'
  }
  if (!props.line || props.line.amount === null) {
    return '本范围内该员工没有可计薪的合格产量或工价，这不是 0 工资。'
  }
  if (props.provisional) {
    return '本合计为暂算：存在未定价、未排班或质量未判清的报工，确认后金额可能变化。'
  }
  return '本合计与工资预览合计口径一致，分摊余数已按最小币种单位补足。'
})
</script>

<template>
  <UvDrawer
    :open="open"
    :title="`工资构成 · ${worker?.display_name ?? '员工'}`"
    :subtitle="`${worker?.employee_no ?? '工号待登记'} · ${WORKER_ROLE_LABELS[worker?.role ?? ''] ?? '岗位待登记'} · ${EMPLOY_STATE_LABELS[worker?.employ_state ?? ''] ?? '在职状态待确认'} · ${dateFrom} ~ ${dateTo}`"
    size="lg"
    close-hint="Esc 关闭"
    @close="emit('close')"
  >
    <div v-if="!canReadPayroll" class="uv-state uv-state--warning uv-state--compact" role="alert">
      <div class="uv-state__icon uv-state__icon--warning" aria-hidden="true">
        <AlertTriangle class="size-5" />
      </div>
      <p class="uv-state__title">没有查看工资的权限</p>
      <p class="uv-state__message">
        当前账号在华康A生产部缺少 uv_printing:payroll_read。服务端会完全省略工资字段，
        本抽屉不会显示金额、也不会用样例数据模拟一份工资。
      </p>
    </div>

    <template v-else>
      <p v-if="isLeft" class="uv-callout uv-callout--warning" role="status">
        <History class="inline size-3.5" aria-hidden="true" />
        该员工已于 {{ worker?.left_on ?? '历史日期' }} 离职：以下为
        <strong>历史排班与工资快照</strong>，保留原值；修改当前排班不会改变已确认的历史工资。
      </p>

      <section class="uv-section">
        <h3 class="uv-section__title"><span class="uv-section__index">1</span>工资构成（逐条报工）</h3>
        <p class="uv-callout">
          <Info class="inline size-3.5" aria-hidden="true" />
          班组计件金额 = 可计薪合格数量 × 计件工价快照。这里只使用计件工价，
          <strong>商业执行价与产值不在本抽屉显示</strong>，两套价格严格分开。
        </p>

        <div v-if="rows.length" class="uv-matrix-scroll" style="margin-top: 10px">
          <table class="uv-table uv-table--dense" data-uv="payroll-breakdown">
            <caption class="uv-table-caption">按报工逐条列出，便于核对机台、产品与工价快照。</caption>
            <thead>
              <tr>
                <th scope="col">业务日期·班次</th>
                <th scope="col">机台</th>
                <th scope="col">产品</th>
                <th scope="col">合格数</th>
                <th scope="col">计件工价快照</th>
                <th scope="col">本员工分摊金额</th>
                <th scope="col">状态</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="row.key" :data-report-id="row.reportId">
                <td>{{ row.businessDate }} · {{ row.shiftLabel }}</td>
                <td>{{ row.machineLabel }}</td>
                <td>
                  {{ row.productLabel }}
                  <span class="uv-row-sub">报工号 {{ row.reportId }}</span>
                </td>
                <td class="uv-table-cell--right">
                  <UvNumber :qty="row.goodQty" :state="row.goodQty > 0 ? 'normal' : 'pending'" />
                </td>
                <td class="uv-table-cell--right">
                  <span v-if="row.pieceWage" class="uv-mono">{{ row.pieceWage }} {{ currency }}/件</span>
                  <span v-else class="uv-field__missing">未定价</span>
                  <span v-if="row.rateVersionId" class="uv-row-sub">价规版本 {{ row.rateVersionId }}</span>
                </td>
                <td class="uv-table-cell--right">
                  <UvNumber
                    v-if="row.amount"
                    :money="row.amount"
                    :state="row.state === 'confirmed' ? 'normal' : 'provisional'"
                  />
                  <UvNumber
                    v-else
                    :state="row.pieceWage === null ? 'unpriced' : 'pending'"
                  />
                </td>
                <td>
                  <UvStatusPill :status="rowStateView(row.state)" compact />
                  <span v-if="row.qualityPending" class="uv-row-sub">
                    {{ QUALITY_STATUS.partial.label }}：本行按已判合格量暂算，待判数量判定后金额会变
                  </span>
                  <span v-if="row.reason" class="uv-row-sub">{{ row.reason }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="uv-state uv-state--compact">
          <p class="uv-state__title">本范围内没有该员工参与的报工</p>
          <p class="uv-state__hint">
            报工存在但未安排人员时显示为「未排班」，不会按 0 工资处理；请先核对排班与工作批次。
          </p>
        </div>
      </section>

      <section class="uv-section">
        <h3 class="uv-section__title"><span class="uv-section__index">2</span>分摊依据</h3>
        <p class="uv-callout uv-callout--accent">
          <Calculator class="inline size-3.5" aria-hidden="true" />
          同机同班同一工作批次的参与人员<strong>等分</strong>该批次计件金额；余数按
          <strong>稳定员工顺序（工号升序）</strong>补最小币种单位，因此 1.00 分给三人是
          0.34 + 0.33 + 0.33，<strong>合计完全一致</strong>，不会出现 0.99 或 1.01。
        </p>

        <div v-if="allocations.length" class="uv-payroll-splits">
          <article v-for="group in allocations" :key="group.key" class="uv-callout" data-uv="payroll-split">
            <p class="uv-row-primary">{{ group.label }}</p>
            <p class="uv-row-sub">
              批次金额 {{ formatMoney(group.batchTotal) }} ÷ {{ group.participantCount }} 人，基准
              {{ formatMoney(group.baseShare) }}；余数补最小币种单位（{{ group.currency }}）。
            </p>
            <ul class="uv-list">
              <li v-for="participant in group.participants" :key="participant.workerId">
                <span class="uv-list__dot" aria-hidden="true" />
                <span>
                  {{ participant.workerName }}（{{ participant.employeeNo }}）：
                  <strong>{{ formatMoney(participant.amount) }}</strong>
                  <span v-if="participant.remainderAdjusted" class="uv-chip">余数补足</span>
                  <span v-else class="uv-row-sub">等分基准</span>
                </span>
              </li>
            </ul>
          </article>
        </div>
        <p v-else class="uv-state uv-state--compact">
          <span class="uv-state__hint">本范围没有可分摊的批次金额，分摊依据在有计件金额后显示。</span>
        </p>
      </section>

      <section class="uv-section">
        <h3 class="uv-section__title"><span class="uv-section__index">3</span>待核项</h3>
        <ul v-if="pending.length" class="uv-list" data-uv="payroll-pending">
          <li v-for="item in pending" :key="item.key">
            <AlertTriangle class="size-3.5" style="margin-top: 2px" aria-hidden="true" />
            <span>
              <strong>{{ item.label }}</strong> · {{ item.count }} 条：{{ item.reason }}
            </span>
          </li>
        </ul>
        <p v-else class="uv-callout">
          <CheckCircle2 class="inline size-3.5" aria-hidden="true" />
          本范围没有未定价、未排班或质量未判清的报工。
        </p>
      </section>

      <section class="uv-section">
        <h3 class="uv-section__title"><span class="uv-section__index">4</span>工资预览</h3>
        <div class="uv-detail-grid">
          <div class="uv-field">
            <dt class="uv-field__label">本员工合计（{{ dateFrom }} ~ {{ dateTo }}）</dt>
            <dd class="uv-field__value">
              <UvNumber
                v-if="line && line.amount"
                :money="line.amount"
                size="lg"
                align="left"
                :state="previewState === 'confirmed' ? 'normal' : 'provisional'"
                emphasis
              />
              <UvNumber
                v-else
                size="lg"
                align="left"
                :state="previewState === 'unpriced' ? 'unpriced' : 'pending'"
                emphasis
              />
              <span class="uv-field__hint">{{ totalHint }}</span>
            </dd>
          </div>
          <div class="uv-field">
            <dt class="uv-field__label">计入报工 / 合格数</dt>
            <dd class="uv-field__value">
              <UvNumber :qty="line?.report_count ?? 0" :state="line ? 'normal' : 'pending'" align="left" unit="条" />
              <UvNumber :qty="line?.good_qty ?? 0" :state="line ? 'normal' : 'pending'" align="left" unit="件" />
            </dd>
          </div>
          <div class="uv-field">
            <dt class="uv-field__label">计薪口径</dt>
            <dd class="uv-field__value">
              <UvStatusPill :status="stateView" compact />
              <span class="uv-field__hint">
                {{ stateView.label }}：{{ previewState === 'confirmed' ? '已按确认口径核定' : '分摊合计已对齐，等待确认' }}
              </span>
            </dd>
          </div>
          <div class="uv-field">
            <dt class="uv-field__label">工资预览合计（全部员工）</dt>
            <dd class="uv-field__value">
              <UvNumber
                v-if="previewTotal"
                :money="previewTotal"
                :state="previewState === 'confirmed' ? 'normal' : 'provisional'"
              />
              <UvNumber v-else :state="previewState === 'unpriced' ? 'unpriced' : 'pending'" />
              <span class="uv-field__hint">各员工分摊额之和；合计完全一致，不允许四舍五入丢失 0.01。</span>
            </dd>
          </div>
        </div>
        <p class="uv-callout">
          <Info class="inline size-3.5" aria-hidden="true" />
          本抽屉只呈现计件工资口径；商业执行价、面积费率与产值为独立口径，不在此处换算。
        </p>
      </section>
    </template>
  </UvDrawer>
</template>
