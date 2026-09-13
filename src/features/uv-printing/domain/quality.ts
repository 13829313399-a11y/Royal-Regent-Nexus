import type { UvQuality, UvQualityStatus } from '../contracts'
import { decimalDivide, formatPercent } from './decimal'

/** 质量四分法：reported = good + defective + pending + semi_finished。 */

export const QUALITY_BUCKETS = ['good', 'defective', 'pending', 'semi_finished'] as const

export const QUALITY_BUCKET_LABELS: Record<(typeof QUALITY_BUCKETS)[number], string> = {
  good: '合格',
  defective: '不良',
  pending: '待判',
  semi_finished: '半成品',
}

export function emptyQuality(reportedQty = 0): UvQuality {
  return {
    reported_qty: reportedQty,
    good_qty: 0,
    defective_qty: 0,
    pending_qty: reportedQty,
    semi_finished_qty: 0,
  }
}

export function qualityBucketTotal(quality: UvQuality): number {
  return quality.good_qty + quality.defective_qty + quality.pending_qty + quality.semi_finished_qty
}

export function qualityIsBalanced(quality: UvQuality): boolean {
  return qualityBucketTotal(quality) === quality.reported_qty
}

export function qualityDifference(quality: UvQuality): number {
  return qualityBucketTotal(quality) - quality.reported_qty
}

export function hasNegativeBucket(quality: UvQuality): boolean {
  return (
    quality.good_qty < 0
    || quality.defective_qty < 0
    || quality.pending_qty < 0
    || quality.semi_finished_qty < 0
  )
}

export function qualityStatusOf(quality: UvQuality): UvQualityStatus {
  if (quality.pending_qty === quality.reported_qty && quality.reported_qty > 0) return 'pending'
  if (quality.pending_qty > 0 || quality.semi_finished_qty > 0) return 'partial'
  return 'complete'
}

/**
 * 合格率默认 good / (good + defective)；分母为 0 显示「—」，
 * 同时展示待判/半成品比例以免把「还没判」误当成「没问题」。
 */
export function yieldRate(quality: UvQuality): string | null {
  const denominator = quality.good_qty + quality.defective_qty
  if (denominator <= 0) return null
  return decimalDivide(String(quality.good_qty), String(denominator), 6)
}

export function pendingShare(quality: UvQuality): string | null {
  if (quality.reported_qty <= 0) return null
  return decimalDivide(
    String(quality.pending_qty + quality.semi_finished_qty),
    String(quality.reported_qty),
    6,
  )
}

export interface QualityValidationIssue {
  code: 'negative' | 'over' | 'under'
  message: string
}

/** 校验只提示具体差异，不自动抹平。 */
export function validateQuality(quality: UvQuality): QualityValidationIssue[] {
  const issues: QualityValidationIssue[] = []
  if (hasNegativeBucket(quality)) {
    issues.push({ code: 'negative', message: '质量分桶不能为负数' })
  }
  const difference = qualityDifference(quality)
  if (difference > 0) {
    issues.push({ code: 'over', message: `分桶合计比报工数量多 ${difference} 件，请核对后保存` })
  }
  if (difference < 0) {
    issues.push({ code: 'under', message: `分桶合计比报工数量少 ${Math.abs(difference)} 件，差额仍在待判` })
  }
  return issues
}

/** 把未分配数量归入待判桶，只用于「建议」，不自动提交。 */
export function suggestPendingFill(quality: UvQuality): UvQuality {
  const difference = quality.reported_qty - qualityBucketTotal(quality)
  if (difference === 0) return quality
  return { ...quality, pending_qty: Math.max(0, quality.pending_qty + difference) }
}

export function formatYield(rate: string | null, scale = 2): string {
  return formatPercent(rate, scale)
}
