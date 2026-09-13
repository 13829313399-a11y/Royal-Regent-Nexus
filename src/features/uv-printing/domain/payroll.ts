import type { Money, UvPayrollState, UvReport } from '../contracts'
import { currencyMinorUnits, decimalAdd, decimalMultiply, decimalRound, formatScaled, money, splitRemainder } from './decimal'

/**
 * 班组计件金额与分摊（UV_PRINT_SHARED_SPEC.md 5.6）。
 *
 *   班组计件金额 = 可计薪合格数量 × 计件工价快照
 *
 * - 先汇总工作批次金额再分配，不每件向下取整；
 * - 同机同班、同一工作批次参与人员默认等分；
 * - 余数按稳定员工顺序补最小币种单位，合计完全一致（1.00 分给三人 = 0.34/0.33/0.33）；
 * - 无工价、未安排人员、质量未核清时显示「待核/未定价」，不自动发出 0 工资结果；
 * - 商业价与工价严格分开：这里只使用 piece_wage，绝不回退到商业价。
 */

export interface PayrollAllocationLine {
  worker_id: string
  worker_name: string
  employee_no: string
  amount: Money | null
  state: UvPayrollState
  remainder_adjusted: boolean
  reason: string
}

export interface PayrollAllocation {
  batch_total: Money | null
  state: UvPayrollState
  lines: PayrollAllocationLine[]
  /** 无法参与计薪的原因：未定价 / 未排班 / 待核质量。 */
  blocked_reason: string
}

export interface PayrollWorkerRef {
  worker_id: string
  worker_name: string
  employee_no: string
}

/**
 * 按工作批次汇总再分配。`components` 是已经按批次聚合好的金额，
 * 调用方不应传入逐件金额。
 */
export function allocateBatch(
  batchTotal: string,
  currency: string,
  workers: PayrollWorkerRef[],
  state: UvPayrollState = 'provisional',
): PayrollAllocation {
  if (workers.length === 0) {
    return {
      batch_total: money(currency, batchTotal),
      state: 'unpriced',
      lines: [],
      blocked_reason: '该工作批次未安排人员，无法拆分工资',
    }
  }

  const sorted = [...workers].sort((a, b) => a.worker_id.localeCompare(b.worker_id))
  const order = sorted.map((worker) => workers.findIndex((candidate) => candidate.worker_id === worker.worker_id))
  const shares = splitRemainder(batchTotal, sorted.length, currency, order)
  const minor = currencyMinorUnits(currency)
  const baseShare = formatScaled(
    BigInt(decimalRound(batchTotal, minor).replace('.', '').replace('-', '')) / BigInt(sorted.length),
    minor,
  )

  return {
    batch_total: money(currency, batchTotal),
    state,
    lines: sorted.map((worker, index) => ({
      worker_id: worker.worker_id,
      worker_name: worker.worker_name,
      employee_no: worker.employee_no,
      amount: money(currency, shares[index] ?? '0'),
      state,
      remainder_adjusted: (shares[index] ?? '0') !== baseShare,
      reason: '',
    })),
    blocked_reason: '',
  }
}

export interface ReportPayrollBreakdown {
  report_id: string
  bucket: 'priced' | 'unpriced' | 'quality_pending' | 'unassigned'
  reason: string
  amount: Money | null
}

/**
 * 单条报工的计薪构成。
 * 未做质量判定时只用已判合格量计薪并标注待核；没有任何合格量时不给 0 工资，
 * 而是明确「待核」。
 */
export function reportPayroll(
  report: UvReport,
  currency: string,
): { bucket: ReportPayrollBreakdown['bucket']; amount: Money | null; reason: string } {
  if (report.status === 'voided') {
    return { bucket: 'unassigned', amount: null, reason: '已作废，不计薪' }
  }

  const payroll = report.payroll
  if (!payroll || payroll.state === 'unpriced' || payroll.piece_wage === null) {
    return { bucket: 'unpriced', amount: null, reason: '该产品/工艺在此机台没有生效的计件工价' }
  }

  const goodQty = report.good_qty
  if (goodQty <= 0) {
    return {
      bucket: 'quality_pending',
      amount: null,
      reason: report.quality_status === 'pending' ? '质量尚未判定，暂不计薪' : '没有已确认合格数量',
    }
  }

  const amount = decimalRound(decimalMultiply(String(goodQty), payroll.piece_wage), 6)
  return {
    bucket: 'priced',
    amount: money(currency, amount),
    reason: report.quality_status === 'complete' ? '' : '质量未全部判清，按已判合格量暂算',
  }
}

export function sumMoney(currency: string, values: Array<Money | null>): Money | null {
  const present = values.filter((value): value is Money => value !== null)
  if (!present.length) return null
  const mixed = present.some((value) => value.currency !== currency)
  if (mixed) return null
  return money(currency, present.reduce((total, value) => decimalAdd(total, value.amount), '0'))
}
