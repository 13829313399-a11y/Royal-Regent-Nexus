import type { AIBusinessResult, AIEvidenceReferenceV1 } from '../types'
import { extractActionConfirmation, isActionConfirmationCandidate } from './actionConfirmation'
import { extractCartonProcurementResult, isCartonProcurementResultCandidate } from './cartonProcurement'
import {
  evidenceSource,
  extractSource,
  finiteNumber,
  localId,
  record,
  safeLinks,
  text,
  bool,
  type AIResultRenderer,
  type RenderedToolEnvelope,
} from './contracts'
import { extractCustomerOrderResult, isCustomerOrderResultCandidate } from './customerOrder'
import { extractInternalQuoteResult, isInternalQuoteResultCandidate } from './internalQuote'
import { extractKnowledgeSearchResult, isKnowledgeSearchCandidate } from './knowledge'
import {
  extractSchedulingAdvisorResult,
  isSchedulingAdvisorResultCandidate,
} from './injectionScheduling'
import { extractMoldingSampleResult, isMoldingSampleResultCandidate } from './moldingSample'
import { extractRawMaterialResult, isRawMaterialResultCandidate } from './rawMaterial'

const EVIDENCE_KEYS = [
  'evidence_id',
  'source_level',
  'source_name',
  'factory_id',
  'as_of',
  'entity_type',
  'entity_id',
  'entity_revision',
  'content_hash',
  'truncated',
  'cursor',
  'access_policy',
] as const
const FACTORY_IDS = new Set(['huakang-a', 'huakang-b', 'huakang-c', 'huakang-d', 'huadeng', 'huaxing'])
const SOURCE_LEVELS = new Set([
  'FORMAL_DOMAIN_SERVICE',
  'VERSIONED_MODULE_KNOWLEDGE',
  'AUTHENTICATED_SERVER_CONTEXT',
  'USER_PROVIDED',
  'MODEL_INFERENCE',
])
const ISO_OFFSET = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/
const CLOSED_ID = /^[a-z0-9][a-z0-9._:-]{0,159}$/

const renderers: AIResultRenderer[] = [
  {
    schemaVersion: 'knowledge-search-v1',
    resultType: 'knowledge.search_results',
    render: extractKnowledgeSearchResult,
  },
  {
    schemaVersion: 'internal-quote-summary-v1',
    resultType: 'internal_quote.summary_list',
    render: extractInternalQuoteResult,
  },
  {
    schemaVersion: 'molding-sample-summary-v1',
    resultType: 'molding_sample.summary_list',
    render: extractMoldingSampleResult,
  },
  {
    schemaVersion: 'carton-procurement-summary-v1',
    resultType: 'carton_procurement.summary_list',
    render: extractCartonProcurementResult,
  },
  {
    schemaVersion: 'raw-material-master-summary-v1',
    resultType: 'raw_material.master_summary_list',
    render: extractRawMaterialResult,
  },
  {
    schemaVersion: 'raw-material-inventory-summary-v1',
    resultType: 'raw_material.inventory_summary_list',
    render: extractRawMaterialResult,
  },
  {
    schemaVersion: 'customer-order-capabilities-v1',
    resultType: 'customer_order.capabilities',
    render: extractCustomerOrderResult,
  },
  {
    schemaVersion: 'customer-order-export-audit-summary-v1',
    resultType: 'customer_order.export_audit_summary_list',
    render: extractCustomerOrderResult,
  },
  {
    schemaVersion: 'ai-scheduling-preview-v1',
    resultType: 'injection_scheduling.preview_run',
    render: extractSchedulingAdvisorResult,
  },
  {
    schemaVersion: 'ai-scheduling-comparison-v1',
    resultType: 'injection_scheduling.preview_comparison',
    render: extractSchedulingAdvisorResult,
  },
  {
    schemaVersion: 'ai-action-confirmation-v1',
    resultType: 'ai.action_confirmation',
    render: extractActionConfirmation,
  },
]

const rendererByKey = new Map<string, AIResultRenderer>()
for (const renderer of renderers) {
  const key = rendererKey(renderer.schemaVersion, renderer.resultType)
  if (rendererByKey.has(key)) throw new Error(`Duplicate AI Renderer: ${key}`)
  rendererByKey.set(key, renderer)
}

function rendererKey(schemaVersion: unknown, resultType: unknown) {
  return `${text(schemaVersion, 120)}::${text(resultType, 160)}`
}

function isKnownDomainCandidate(source: Record<string, unknown>) {
  return isInternalQuoteResultCandidate(source)
    || isMoldingSampleResultCandidate(source)
    || isCartonProcurementResultCandidate(source)
    || isRawMaterialResultCandidate(source)
    || isCustomerOrderResultCandidate(source)
    || isSchedulingAdvisorResultCandidate(source)
    || isActionConfirmationCandidate(source)
    || isKnowledgeSearchCandidate(source)
}

function extractGenericResult(value: unknown): AIBusinessResult | null {
  const source = record(value)
  if (!source) return null
  const sourceType = text(source.source_type, 64)
  const rawSummary = source.summary ?? source.description ?? source.answer ?? source.help_markdown
  const summary = text(rawSummary, 4_000)
  const links = safeLinks(source.entity_links ?? source.links)
  const factoryId = text(source.factory_id, 64)
  const asOf = text(source.as_of ?? source.updated_at, 80)
  const executionPublished = record(source.execution_published)
  const planningDraft = record(source.planning_draft)
  const isPlanContext = 'execution_published' in source || 'planning_draft' in source
  const backlogItems = Array.isArray(source.items)
    ? source.items
    : Array.isArray(source.orders)
      ? source.orders
      : null
  const isBacklog = backlogItems !== null
    || finiteNumber(source.total) !== undefined
    || finiteNumber(source.returned) !== undefined
  if (!sourceType && !summary && !links.length && !isPlanContext && !isBacklog) return null

  const planSummary = (plan: Record<string, unknown> | null) => plan
    ? {
        ...(text(plan.plan_id, 128) ? { planId: text(plan.plan_id, 128) } : {}),
        ...(text(plan.business_date, 40) ? { businessDate: text(plan.business_date, 40) } : {}),
        ...(finiteNumber(plan.revision) !== undefined ? { revision: finiteNumber(plan.revision) } : {}),
        ...(finiteNumber(plan.task_count) !== undefined ? { taskCount: finiteNumber(plan.task_count) } : {}),
        ...(finiteNumber(plan.running_count) !== undefined ? { runningCount: finiteNumber(plan.running_count) } : {}),
      }
    : null

  return {
    id: localId('result'),
    kind: isPlanContext ? 'plan_context' : isBacklog ? 'backlog' : 'generic',
    title: text(source.title ?? source.module_name, 120) || (isPlanContext
      ? '注塑排产状态'
      : isBacklog
        ? '注塑待排订单'
        : sourceType === 'FORMAL'
          ? '业务数据摘要'
          : '页面帮助'),
    summary,
    sourceType: sourceType || 'UNKNOWN',
    ...(factoryId ? { factoryId } : {}),
    ...(asOf ? { asOf } : {}),
    truncated: bool(source.truncated)
      || (typeof rawSummary === 'string' && rawSummary.trim().length > 4_000),
    links,
    ...(isPlanContext
      ? {
          planContext: {
            executionPublished: planSummary(executionPublished),
            planningDraft: planSummary(planningDraft),
            ...(finiteNumber(source.polling_revision) !== undefined
              ? { pollingRevision: finiteNumber(source.polling_revision) }
              : {}),
          },
        }
      : {}),
    ...(isBacklog
      ? {
          backlog: {
            ...(finiteNumber(source.total) !== undefined ? { total: finiteNumber(source.total) } : {}),
            ...(finiteNumber(source.returned) !== undefined
              ? { returned: finiteNumber(source.returned) }
              : backlogItems
                ? { returned: backlogItems.length }
                : {}),
            ...(text(source.source_scope, 120) ? { sourceScope: text(source.source_scope, 120) } : {}),
            ...(text(source.source_business_label, 120)
              ? { sourceBusinessLabel: text(source.source_business_label, 120) }
              : {}),
          },
        }
      : {}),
  }
}

function parseEvidence(value: unknown): AIEvidenceReferenceV1[] {
  if (!Array.isArray(value) || value.length > 16) return []
  const parsed: AIEvidenceReferenceV1[] = []
  for (const item of value) {
    const source = record(item)
    if (!source || Object.keys(source).length !== EVIDENCE_KEYS.length) return []
    if (!Object.keys(source).every((key) => EVIDENCE_KEYS.includes(key as typeof EVIDENCE_KEYS[number]))) return []
    const evidenceId = text(source.evidence_id, 160)
    const sourceLevel = text(source.source_level, 64)
    const sourceName = text(source.source_name, 160)
    const factoryId = source.factory_id === null ? undefined : text(source.factory_id, 64)
    const asOf = text(source.as_of, 80)
    const entityType = source.entity_type === null ? undefined : text(source.entity_type, 120)
    const entityId = source.entity_id === null ? undefined : text(source.entity_id, 160)
    const entityRevision = source.entity_revision === null
      ? undefined
      : finiteNumber(source.entity_revision)
    const contentHash = text(source.content_hash, 80)
    const cursor = source.cursor === null ? undefined : text(source.cursor, 256)
    if (
      !CLOSED_ID.test(evidenceId)
      || !SOURCE_LEVELS.has(sourceLevel)
      || !CLOSED_ID.test(sourceName)
      || (factoryId !== undefined && !FACTORY_IDS.has(factoryId))
      || !ISO_OFFSET.test(asOf)
      || Number.isNaN(Date.parse(asOf))
      || (entityType !== undefined && !CLOSED_ID.test(entityType))
      || (entityId !== undefined && !CLOSED_ID.test(entityId))
      || (entityRevision !== undefined && (!Number.isInteger(entityRevision) || entityRevision < 0))
      || !/^sha256:[a-f0-9]{64}$/.test(contentHash)
      || typeof source.truncated !== 'boolean'
      || (source.cursor !== null && !cursor)
      || source.access_policy !== 'REAUTHORIZE_ON_OPEN'
    ) return []
    parsed.push({
      evidenceId,
      sourceLevel: sourceLevel as AIEvidenceReferenceV1['sourceLevel'],
      sourceName,
      ...(factoryId ? { factoryId } : {}),
      asOf,
      ...(entityType ? { entityType } : {}),
      ...(entityId ? { entityId } : {}),
      ...(entityRevision !== undefined ? { entityRevision } : {}),
      contentHash,
      truncated: source.truncated,
      ...(cursor ? { cursor } : {}),
      accessPolicy: 'REAUTHORIZE_ON_OPEN',
    })
  }
  return parsed
}

function safeUnknownResult(
  source: Record<string, unknown>,
  evidence: AIEvidenceReferenceV1[],
): AIBusinessResult | null {
  if (!evidence.length) return null
  const keys = Object.keys(source)
  if (keys.some((key) => ['__proto__', 'prototype', 'constructor'].includes(key))) return null
  let summary = ''
  try {
    summary = JSON.stringify(source, null, 2).slice(0, 4_000)
  } catch {
    return null
  }
  return {
    id: localId('result'),
    kind: 'generic',
    title: '未注册结果（只读）',
    summary,
    sourceType: 'UNKNOWN',
    factoryId: evidence[0]?.factoryId,
    asOf: evidence[0]?.asOf,
    truncated: summary.length >= 4_000 || evidence.some((item) => item.truncated),
    links: [],
    evidence,
    rendererStatus: 'safe_fallback',
  }
}

export class RendererRegistry {
  readonly registeredKeys = Object.freeze([...rendererByKey.keys()].sort())

  renderEnvelope(value: unknown): RenderedToolEnvelope | null {
    const envelope = record(value)
    if (!envelope || envelope.ok !== true) return null
    const source = record(envelope.data)
    if (!source) return null
    const evidence = parseEvidence(envelope.evidence)
    const renderer = rendererByKey.get(rendererKey(source.schema_version, source.result_type))
    let businessResult = renderer?.render(source) ?? null
    const domainCandidate = isKnownDomainCandidate(source)
    if (!renderer && domainCandidate) {
      businessResult = safeUnknownResult(source, evidence)
    } else if (!renderer && !domainCandidate) {
      businessResult = extractGenericResult(source)
    }
    if (businessResult) {
      businessResult = {
        ...businessResult,
        ...(evidence.length ? { evidence } : {}),
        rendererStatus: renderer ? 'registered' : businessResult.rendererStatus ?? 'legacy_adapter',
      }
    }
    const sources = [
      ...evidence.map(evidenceSource),
      ...(!domainCandidate || businessResult ? [extractSource(source)] : []),
    ].filter((item): item is NonNullable<typeof item> => item !== null)
    return { businessResult, sources }
  }
}

export const rendererRegistry = new RendererRegistry()
