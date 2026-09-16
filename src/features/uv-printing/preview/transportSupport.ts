import type {
  CreateUvReport,
  UvCoverage,
  UvMeta,
  UvQuality,
  UvScope,
  UvWarning,
} from '../contracts'
import { hasNegativeBucket, qualityBucketTotal } from '../domain/quality'
import { SAMPLE_FACTORY_ID, SAMPLE_AS_OF } from './constants'

/** UV 域结构化错误，兼容宿主 FastAPI 的 detail 归一。 */
export class UvError extends Error {
  readonly code: string
  readonly status: number
  readonly fields: Record<string, string>
  readonly retryable: boolean

  constructor(
    code: string,
    message: string,
    options: { status?: number; fields?: Record<string, string>; retryable?: boolean } = {},
  ) {
    super(message)
    this.name = 'UvError'
    this.code = code
    this.status = options.status ?? 400
    this.fields = options.fields ?? {}
    this.retryable = options.retryable ?? false
  }
}

export const UV_ERROR_CODES = {
  unauthorized: 'uv_unauthorized',
  forbidden: 'uv_forbidden',
  notFound: 'uv_not_found',
  versionConflict: 'uv_version_conflict',
  operationConflict: 'uv_operation_conflict',
  qualityMismatch: 'uv_quality_mismatch',
  allocationOverflow: 'uv_allocation_overflow',
  insufficientStock: 'uv_insufficient_stock',
  invalidField: 'uv_invalid_field',
  factoryMismatch: 'uv_factory_mismatch',
  serviceUnavailable: 'uv_service_unavailable',
  timeout: 'uv_timeout',
} as const

export function metaFor(options: {
  coverage?: UvCoverage
  warnings?: UvWarning[]
  asOf?: string
} = {}): UvMeta {
  return {
    factory_id: SAMPLE_FACTORY_ID,
    as_of: options.asOf ?? SAMPLE_AS_OF,
    data_mode: 'sample',
    coverage: options.coverage ?? 'complete',
    warnings: options.warnings ?? [],
  }
}

export interface FactoryScopedInput {
  factory_id: string
}

export function assertScopeFactory(input: FactoryScopedInput): void {
  if (!input || input.factory_id !== SAMPLE_FACTORY_ID) {
    throw new UvError(
      UV_ERROR_CODES.factoryMismatch,
      '样例数据只提供华康A，其他厂区不会回落到华康A。',
      { status: 422, fields: { factory_id: '只允许 huakang-a' } },
    )
  }
}

export function assertVersion(expected: number, actual: number): void {
  if (expected !== actual) {
    throw new UvError(
      UV_ERROR_CODES.versionConflict,
      `对象已被他人更新（期望版本 ${expected}，当前版本 ${actual}），请刷新后重试。`,
      { status: 409, retryable: true },
    )
  }
}

export function validateQualityTotals(quality: UvQuality): void {
  if (hasNegativeBucket(quality)) {
    throw new UvError(UV_ERROR_CODES.invalidField, '质量分桶不能为负数。', {
      status: 422,
      fields: { quality: '分桶必须为非负整数' },
    })
  }
  const total = qualityBucketTotal(quality)
  if (total !== quality.reported_qty) {
    throw new UvError(
      UV_ERROR_CODES.qualityMismatch,
      `质量分桶合计 ${total} 与报工数量 ${quality.reported_qty} 不一致，差额 ${total - quality.reported_qty} 件。`,
      { status: 422, fields: { quality: `差额 ${total - quality.reported_qty}` } },
    )
  }
}

export function validateDraft(input: CreateUvReport, machineExists: boolean, productVersionExists: boolean): void {
  const fields: Record<string, string> = {}
  if (!input.business_date) fields.business_date = '缺少业务日期'
  if (input.shift !== 'day' && input.shift !== 'night') fields.shift = '班次必须是白班或夜班'
  if (!machineExists) fields.machine_id = '机台不在本厂区'
  if (!productVersionExists) fields.process_version_id = '产品工艺版本不存在'
  if (input.reported_qty < 0 || !Number.isInteger(input.reported_qty)) {
    fields.reported_qty = '报工数量必须为非负整数'
  }
  if (Object.keys(fields).length) {
    throw new UvError(UV_ERROR_CODES.invalidField, '报工字段校验失败，请检查标记字段。', {
      status: 422,
      fields,
    })
  }
}

export function paginate<T>(items: T[], page = 1, pageSize = 50) {
  const safeSize = Math.min(Math.max(pageSize || 50, 1), 200)
  const safePage = Math.max(page || 1, 1)
  const start = (safePage - 1) * safeSize
  return {
    items: items.slice(start, start + safeSize),
    total: items.length,
    page: safePage,
    page_size: safeSize,
  }
}

export function nowIso(): string {
  return new Date().toISOString()
}
