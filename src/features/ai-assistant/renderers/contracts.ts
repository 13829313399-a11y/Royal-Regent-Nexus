import type {
  AIBusinessResult,
  AIEvidenceReferenceV1,
  AIEntityLink,
  AISourceSummary,
} from '../types'

const ALLOWED_INTERNAL_PATHS = new Set([
  '/modules/production/injection-scheduling',
  '/modules/sales-business/internal-quote-desk',
  '/modules/molding-sample',
  '/modules/pmc-warehouse/carton-procurement',
  '/modules/pmc-warehouse/raw-material-management',
  '/modules/sales-business/po-schedule-intake',
  '/workbench/ai',
])

let rendererLocalIdSequence = 0

export interface RendererContext {
  evidence: AIEvidenceReferenceV1[]
}

export interface AIResultRenderer {
  schemaVersion: string
  resultType: string
  render: (value: Record<string, unknown>) => AIBusinessResult | null
}

export interface RenderedToolEnvelope {
  businessResult: AIBusinessResult | null
  sources: AISourceSummary[]
}

export function localId(prefix: string) {
  rendererLocalIdSequence += 1
  return `${prefix}-${Date.now()}-${rendererLocalIdSequence}`
}

export function text(value: unknown, maxLength = 1_000) {
  return typeof value === 'string' ? value.trim().slice(0, maxLength) : ''
}

export function bool(value: unknown) {
  return value === true
}

export function finiteNumber(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

export function record(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const prototype = Object.getPrototypeOf(value)
  if (prototype !== Object.prototype && prototype !== null) return null
  return value as Record<string, unknown>
}

export function boundedText(value: unknown, minLength: number, maxLength: number) {
  if (typeof value !== 'string') return null
  const normalized = value.trim()
  return normalized.length >= minLength && normalized.length <= maxLength
    ? normalized
    : null
}

export function boundedInteger(value: unknown, minimum: number, maximum: number) {
  return typeof value === 'number'
    && Number.isInteger(value)
    && value >= minimum
    && value <= maximum
    ? value
    : null
}

export function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]) {
  const actual = Object.keys(value)
  return actual.length === keys.length
    && actual.every((key) => keys.includes(key))
    && !actual.some((key) => ['__proto__', 'prototype', 'constructor'].includes(key))
}

export function safeLinks(value: unknown): AIEntityLink[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((item) => {
    const source = record(item)
    if (!source) return []
    const route = text(source.route, 300)
    if (!ALLOWED_INTERNAL_PATHS.has(route)) return []
    const rawQuery = record(source.query)
    const query = rawQuery
      ? Object.fromEntries(
          Object.entries(rawQuery)
            .filter(([key, itemValue]) => (
              /^[a-z][a-z0-9_]{0,63}$/.test(key)
              && typeof itemValue === 'string'
            ))
            .map(([key, itemValue]) => [key, (itemValue as string).slice(0, 128)]),
        )
      : undefined
    return [{
      label: text(source.label, 100) || '打开业务页面',
      route,
      ...(query && Object.keys(query).length ? { query } : {}),
    }]
  })
}

export function sourceLevel(value: unknown): AISourceSummary['level'] {
  const normalized = text(value, 40).toUpperCase()
  if (normalized === 'VERSIONED_MODULE_KNOWLEDGE') return 'MODULE_KNOWLEDGE'
  if (normalized === 'FORMAL_DOMAIN_SERVICE') return 'FORMAL'
  if (normalized === 'AUTHENTICATED_SERVER_CONTEXT') return 'FORMAL'
  return ['FORMAL', 'MODULE_KNOWLEDGE', 'USER_PROVIDED', 'MODEL_INFERENCE'].includes(normalized)
    ? normalized as AISourceSummary['level']
    : 'UNKNOWN'
}

export function sourceLabel(level: AISourceSummary['level']) {
  return {
    FORMAL: '系统正式数据',
    MODULE_KNOWLEDGE: '受控页面知识',
    USER_PROVIDED: '用户提供内容',
    MODEL_INFERENCE: '模型推断',
    UNKNOWN: '来源待确认',
  }[level]
}

export function extractSource(value: unknown): AISourceSummary | null {
  if (typeof value === 'string') {
    const normalized = value.trim().toUpperCase()
    if (!['USER_PROVIDED', 'MODEL_INFERENCE'].includes(normalized)) return null
    const level = normalized as 'USER_PROVIDED' | 'MODEL_INFERENCE'
    return { id: localId('source'), level, label: sourceLabel(level), links: [] }
  }
  const source = record(value)
  if (!source) return null
  const level = sourceLevel(source.source_type ?? source.level)
  const factoryId = text(source.factory_id, 64)
  const updatedAt = text(source.as_of ?? source.updated_at ?? source.last_reviewed_at, 80)
  const label = text(source.source_label, 120) || sourceLabel(level)
  const links = safeLinks(source.entity_links ?? source.links)
  if (level === 'UNKNOWN' && !factoryId && !updatedAt && !links.length) return null
  return {
    id: localId('source'),
    level,
    label,
    ...(factoryId ? { factoryId } : {}),
    ...(updatedAt ? { updatedAt } : {}),
    links,
  }
}

export function evidenceSource(evidence: AIEvidenceReferenceV1): AISourceSummary {
  const level = sourceLevel(evidence.sourceLevel)
  return {
    id: evidence.evidenceId,
    level,
    label: sourceLabel(level),
    ...(evidence.factoryId ? { factoryId: evidence.factoryId } : {}),
    updatedAt: evidence.asOf,
    links: [],
  }
}

export function toolResultData(value: unknown) {
  const result = record(value)
  return result ? result.data : undefined
}

export function toolActivityLabel(toolName: string) {
  if (toolName.startsWith('internal_quote.')) return '正在读取内部报价摘要'
  if (toolName.startsWith('molding_sample.')) return '正在读取啤办任务摘要'
  if (toolName.startsWith('carton_procurement.')) return '正在读取纸箱采购摘要'
  if (toolName === 'raw_material.list_master_summaries') return '正在读取原料主数据摘要'
  if (toolName === 'raw_material.list_inventory_summaries') return '正在读取原料库存摘要'
  if (toolName === 'customer_order.get_capabilities') return '正在读取客户订单能力边界'
  if (toolName === 'customer_order.list_export_audits') return '正在读取客户订单导出审计摘要'
  if (toolName === 'injection_scheduling.generate_preview') return '正在生成候选排产方案（尚未应用）'
  if (toolName === 'injection_scheduling.compare_previews') return '正在比较候选排产方案'
  if (toolName === 'injection_scheduling.propose_apply') return '正在准备正式 Apply 确认（尚未执行）'
  if (toolName.startsWith('injection_scheduling.')) return '正在读取排产信息'
  if (toolName.startsWith('knowledge.')) return '正在读取页面帮助'
  if (toolName.startsWith('identity.')) return '正在核对当前上下文'
  return '正在读取已授权信息'
}
