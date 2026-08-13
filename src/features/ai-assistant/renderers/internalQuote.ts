import type { AIBusinessResult, AIInternalQuoteSummary } from '../types'
import { productionFactoryContextIds } from '@/data/enterpriseMock'
import { boundedInteger, boundedText, bool, hasExactKeys, localId, record, safeLinks, text } from './contracts'


const INTERNAL_QUOTE_STATUS_CONTRACT: Record<string, {
  statusLabel: string
  stageCode: string
  stageLabel: string
  navigationTarget: 'collaboration' | 'summary'
}> = {
  drafting: {
    statusLabel: '协作草稿', stageCode: 'COLLABORATION', stageLabel: '分段协作填写', navigationTarget: 'collaboration',
  },
  section_reviewing: {
    statusLabel: '待分段审核', stageCode: 'SECTION_REVIEW', stageLabel: '分段审核', navigationTarget: 'collaboration',
  },
  pending_review: {
    statusLabel: '待分段审核', stageCode: 'SECTION_REVIEW', stageLabel: '分段审核', navigationTarget: 'collaboration',
  },
  rejected: {
    statusLabel: '已退回', stageCode: 'RETURNED', stageLabel: '退回后修正', navigationTarget: 'collaboration',
  },
  ready_for_final_review: {
    statusLabel: '待最终提交', stageCode: 'FINAL_SUBMISSION', stageLabel: '等待提交最终放行', navigationTarget: 'summary',
  },
  final_reviewing: {
    statusLabel: '待最终放行', stageCode: 'FINAL_REVIEW', stageLabel: '等待负责跟客确认放行', navigationTarget: 'summary',
  },
  fully_approved: {
    statusLabel: '已放行', stageCode: 'RELEASED', stageLabel: '最终放行已通过', navigationTarget: 'summary',
  },
  exported: {
    statusLabel: '已导出', stageCode: 'EXPORTED', stageLabel: '受控文件已导出', navigationTarget: 'summary',
  },
  archived: {
    statusLabel: '已归档', stageCode: 'ARCHIVED', stageLabel: '报价已归档', navigationTarget: 'collaboration',
  },
  unknown: {
    statusLabel: '状态待确认', stageCode: 'UNKNOWN', stageLabel: '请在内部报价台核对', navigationTarget: 'collaboration',
  },
}

export function isInternalQuoteResultCandidate(source: Record<string, unknown>) {
  const resultType = typeof source.result_type === 'string' ? source.result_type : ''
  const schemaVersion = typeof source.schema_version === 'string' ? source.schema_version : ''
  return resultType === 'internal_quote'
    || resultType.startsWith('internal_quote.')
    || schemaVersion === 'internal-quote'
    || schemaVersion.startsWith('internal-quote-')
    || Object.hasOwn(source, 'quotes')
}

export function extractInternalQuoteResult(
  source: Record<string, unknown>,
): AIBusinessResult | null {
  if (!hasExactKeys(source, [
    'schema_version',
    'result_type',
    'source_type',
    'factory_id',
    'as_of',
    'total',
    'limit',
    'offset',
    'returned',
    'truncated',
    'quotes',
  ])) return null
  if (
    source.result_type !== 'internal_quote.summary_list'
    || source.schema_version !== 'internal-quote-summary-v1'
    || source.source_type !== 'FORMAL'
  ) return null
  const factoryId = boundedText(source.factory_id, 1, 64)
  const asOf = boundedText(source.as_of, 1, 40)
  const total = boundedInteger(source.total, 0, Number.MAX_SAFE_INTEGER)
  const returned = boundedInteger(source.returned, 0, 20)
  const limit = boundedInteger(source.limit, 1, 20)
  const offset = boundedInteger(source.offset, 0, 10_000)
  const rawQuotes = Array.isArray(source.quotes) ? source.quotes : null
  if (
    !factoryId
    || !productionFactoryContextIds.includes(factoryId as (typeof productionFactoryContextIds)[number])
    || !asOf
    || total === null
    || returned === null
    || limit === null
    || offset === null
    || rawQuotes === null
    || rawQuotes.length > 20
    || returned !== rawQuotes.length
    || total < returned
    || typeof source.truncated !== 'boolean'
    || source.truncated !== (offset + returned < total)
  ) return null

  const quotes: AIInternalQuoteSummary[] = []
  for (const rawQuote of rawQuotes) {
    const quote = record(rawQuote)
    if (!quote || !hasExactKeys(quote, [
      'quote_id',
      'quote_no',
      'customer',
      'status_code',
      'status_label',
      'current_stage_code',
      'current_stage_label',
      'version_label',
      'updated_at',
      'navigation_target',
    ])) return null
    const quoteId = boundedText(quote.quote_id, 1, 64)
    const quoteNo = boundedText(quote.quote_no, 1, 128)
    const customer = boundedText(quote.customer, 0, 128)
    const statusCode = boundedText(quote.status_code, 1, 32)
    const versionLabel = boundedText(quote.version_label, 0, 64)
    const updatedAt = boundedText(quote.updated_at, 0, 32)
    const policy = statusCode ? INTERNAL_QUOTE_STATUS_CONTRACT[statusCode] : undefined
    if (
      !quoteId
      || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(quoteId)
      || !quoteNo
      || customer === null
      || !statusCode
      || !policy
      || quote.status_label !== policy.statusLabel
      || quote.current_stage_code !== policy.stageCode
      || quote.current_stage_label !== policy.stageLabel
      || quote.navigation_target !== policy.navigationTarget
      || versionLabel === null
      || updatedAt === null
    ) return null
    quotes.push({
      quoteId,
      quoteNo,
      customer,
      statusCode,
      statusLabel: policy.statusLabel,
      currentStageCode: policy.stageCode,
      currentStageLabel: policy.stageLabel,
      versionLabel,
      updatedAt,
      navigationTarget: policy.navigationTarget,
    })
  }

  return {
    id: localId('result'),
    kind: 'internal_quote_list',
    title: '内部报价摘要',
    summary: `本次返回 ${returned} 条，共 ${total} 条。`,
    sourceType: 'FORMAL',
    factoryId,
    asOf,
    truncated: source.truncated,
    links: [],
    internalQuote: { total, returned, limit, offset, quotes },
  }
}
