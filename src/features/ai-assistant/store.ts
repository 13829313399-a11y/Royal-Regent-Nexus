import { computed, reactive, ref } from 'vue'
import { defineStore } from 'pinia'
import { productionFactoryContextIds } from '@/data/enterpriseMock'
import {
  AIClientError,
  getAICapabilities,
  normalizeAIFailure,
  streamAIResponse,
} from '@/api/ai'
import type {
  AIBusinessResult,
  AIActionConfirmation,
  AICartonProcurementSummary,
  AICapabilities,
  AIChatRequestMessage,
  AICloudProcessingConsent,
  AIConversationMessage,
  AICustomerOrderCustomerCapability,
  AICustomerOrderExportAuditSummary,
  AIEntityLink,
  AIFailure,
  AIPageContext,
  AIRawMaterialInventorySummary,
  AIRawMaterialMasterSummary,
  AIRequestAttachment,
  AISchedulingMetricDelta,
  AISchedulingPreviewMetrics,
  AISchedulingPreviewRun,
  AIInternalQuoteSummary,
  AIMoldingSampleSummary,
  AISourceSummary,
  AIStreamEnvelope,
  AIToolActivityItem,
} from './types'

const MAX_CONVERSATION_MESSAGES = 12
const MAX_MESSAGE_CHARS = 8_000
const MAX_TOTAL_INPUT_CHARS = 40_000
const MAX_TOOL_ACTIVITIES = 8
const MAX_SOURCES = 12
const MAX_BUSINESS_RESULTS = 8
const TRUNCATED_RESPONSE_MESSAGE = '回答过长，后续内容未显示。请缩小问题范围后重试。'
const INTERNAL_LINK_PATTERN = /^\/(?:modules(?:\/|$)|tools(?:\/|$)|workbench(?:\/|$))/
const CAPABILITY_INVALIDATING_ERROR_CODES = new Set([
  'AI_DISABLED',
  'AI_NOT_CONFIGURED',
  'AI_PILOT_ACCESS_DENIED',
  'AI_PROVIDER_AUTHENTICATION_FAILED',
])

let localIdSequence = 0

function localId(prefix: string) {
  localIdSequence += 1
  return `${prefix}-${Date.now()}-${localIdSequence}`
}

function text(value: unknown, maxLength = 1_000) {
  return typeof value === 'string' ? value.trim().slice(0, maxLength) : ''
}

function streamText(value: unknown) {
  return typeof value === 'string' ? value : ''
}

function bool(value: unknown) {
  return value === true
}

function finiteNumber(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function boundedText(value: unknown, minLength: number, maxLength: number) {
  if (typeof value !== 'string') return null
  const normalized = value.trim()
  return normalized.length >= minLength && normalized.length <= maxLength
    ? normalized
    : null
}

function boundedInteger(value: unknown, minimum: number, maximum: number) {
  return typeof value === 'number'
    && Number.isInteger(value)
    && value >= minimum
    && value <= maximum
    ? value
    : null
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]) {
  const actual = Object.keys(value)
  return actual.length === keys.length && actual.every((key) => keys.includes(key))
}

function safeLinks(value: unknown): AIEntityLink[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((item) => {
    const source = record(item)
    if (!source) return []
    const route = text(source.route, 300)
    if (!INTERNAL_LINK_PATTERN.test(route)) return []
    const rawQuery = record(source.query)
    const query = rawQuery
      ? Object.fromEntries(
          Object.entries(rawQuery)
            .filter((entry): entry is [string, string] => typeof entry[1] === 'string')
            .map(([key, itemValue]) => [key.slice(0, 64), itemValue.slice(0, 128)]),
        )
      : undefined
    return [{
      label: text(source.label, 100) || '打开业务页面',
      route,
      ...(query && Object.keys(query).length ? { query } : {}),
    }]
  })
}

function sourceLevel(value: unknown): AISourceSummary['level'] {
  const normalized = text(value, 40).toUpperCase()
  if (normalized === 'VERSIONED_MODULE_KNOWLEDGE') return 'MODULE_KNOWLEDGE'
  return ['FORMAL', 'MODULE_KNOWLEDGE', 'USER_PROVIDED', 'MODEL_INFERENCE'].includes(normalized)
    ? normalized as AISourceSummary['level']
    : 'UNKNOWN'
}

function sourceLabel(level: AISourceSummary['level']) {
  return {
    FORMAL: '系统正式数据',
    MODULE_KNOWLEDGE: '受控页面知识',
    USER_PROVIDED: '用户提供内容',
    MODEL_INFERENCE: '模型推断',
    UNKNOWN: '来源待确认',
  }[level]
}

function extractSource(value: unknown): AISourceSummary | null {
  if (typeof value === 'string') {
    const normalized = value.trim().toUpperCase()
    if (!['USER_PROVIDED', 'MODEL_INFERENCE'].includes(normalized)) return null
    const level = normalized as 'USER_PROVIDED' | 'MODEL_INFERENCE'
    return {
      id: localId('source'),
      level,
      label: sourceLabel(level),
      links: [],
    }
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

function isInternalQuoteResultCandidate(source: Record<string, unknown>) {
  const resultType = typeof source.result_type === 'string' ? source.result_type : ''
  const schemaVersion = typeof source.schema_version === 'string' ? source.schema_version : ''
  return resultType === 'internal_quote'
    || resultType.startsWith('internal_quote.')
    || schemaVersion === 'internal-quote'
    || schemaVersion.startsWith('internal-quote-')
    || Object.hasOwn(source, 'quotes')
}

function extractInternalQuoteResult(
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

function isMoldingSampleResultCandidate(source: Record<string, unknown>) {
  const resultType = typeof source.result_type === 'string' ? source.result_type : ''
  const schemaVersion = typeof source.schema_version === 'string' ? source.schema_version : ''
  return resultType === 'molding_sample'
    || resultType.startsWith('molding_sample.')
    || schemaVersion === 'molding-sample'
    || schemaVersion.startsWith('molding-sample-')
}

function extractMoldingSampleResult(
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
    'orders',
  ])) return null
  if (
    source.result_type !== 'molding_sample.summary_list'
    || source.schema_version !== 'molding-sample-summary-v1'
    || source.source_type !== 'FORMAL'
  ) return null
  const factoryId = boundedText(source.factory_id, 1, 64)
  const asOf = boundedText(source.as_of, 1, 40)
  const total = boundedInteger(source.total, 0, Number.MAX_SAFE_INTEGER)
  const returned = boundedInteger(source.returned, 0, 20)
  const limit = boundedInteger(source.limit, 1, 20)
  const offset = boundedInteger(source.offset, 0, 10_000)
  const rawOrders = Array.isArray(source.orders) ? source.orders : null
  if (
    !factoryId
    || !productionFactoryContextIds.includes(factoryId as (typeof productionFactoryContextIds)[number])
    || !asOf
    || total === null
    || returned === null
    || limit === null
    || offset === null
    || rawOrders === null
    || rawOrders.length > 20
    || returned !== rawOrders.length
    || total < returned
    || typeof source.truncated !== 'boolean'
    || source.truncated !== (offset + returned < total)
  ) return null

  const orders: AIMoldingSampleSummary[] = []
  for (const rawOrder of rawOrders) {
    const order = record(rawOrder)
    if (!order || !hasExactKeys(order, [
      'order_id',
      'order_number',
      'product_name',
      'client_name',
      'status',
      'stage',
      'order_date',
      'production_factory_id',
      'updated_at',
    ])) return null
    const orderId = boundedText(order.order_id, 1, 64)
    const orderNumber = boundedText(order.order_number, 0, 128)
    const productName = boundedText(order.product_name, 0, 255)
    const clientName = boundedText(order.client_name, 0, 255)
    const status = boundedText(order.status, 0, 32)
    const stage = boundedText(order.stage, 0, 20)
    const orderDate = boundedText(order.order_date, 0, 20)
    const updatedAt = boundedText(order.updated_at, 0, 32)
    const rawProductionFactoryId = order.production_factory_id
    const productionFactoryId = rawProductionFactoryId === null
      ? null
      : boundedText(rawProductionFactoryId, 1, 64)
    if (
      !orderId
      || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(orderId)
      || orderNumber === null
      || productName === null
      || clientName === null
      || status === null
      || stage === null
      || orderDate === null
      || updatedAt === null
      || (rawProductionFactoryId !== null && productionFactoryId === null)
      || (productionFactoryId !== null
        && !productionFactoryContextIds.includes(productionFactoryId as (typeof productionFactoryContextIds)[number]))
    ) return null
    orders.push({
      orderId,
      orderNumber,
      productName,
      clientName,
      status,
      stage,
      orderDate,
      productionFactoryId,
      updatedAt,
    })
  }
  return {
    id: localId('result'),
    kind: 'molding_sample_list',
    title: '啤办任务摘要',
    summary: `本次返回 ${returned} 条，共 ${total} 条。`,
    sourceType: 'FORMAL',
    factoryId,
    asOf,
    truncated: source.truncated,
    links: [],
    moldingSample: { total, returned, limit, offset, orders },
  }
}

function isCartonProcurementResultCandidate(source: Record<string, unknown>) {
  const resultType = typeof source.result_type === 'string' ? source.result_type : ''
  const schemaVersion = typeof source.schema_version === 'string' ? source.schema_version : ''
  return resultType === 'carton_procurement'
    || resultType.startsWith('carton_procurement.')
    || schemaVersion === 'carton-procurement'
    || schemaVersion.startsWith('carton-procurement-')
}

function extractCartonProcurementResult(
  source: Record<string, unknown>,
): AIBusinessResult | null {
  if (!hasExactKeys(source, [
    'schema_version', 'result_type', 'source_type', 'factory_id', 'as_of',
    'total', 'limit', 'offset', 'returned', 'truncated', 'orders',
  ])) return null
  if (
    source.result_type !== 'carton_procurement.summary_list'
    || source.schema_version !== 'carton-procurement-summary-v1'
    || source.source_type !== 'FORMAL'
  ) return null
  const factoryId = boundedText(source.factory_id, 1, 64)
  const asOf = boundedText(source.as_of, 1, 40)
  const total = boundedInteger(source.total, 0, Number.MAX_SAFE_INTEGER)
  const returned = boundedInteger(source.returned, 0, 20)
  const limit = boundedInteger(source.limit, 1, 20)
  const offset = boundedInteger(source.offset, 0, 10_000)
  const rawOrders = Array.isArray(source.orders) ? source.orders : null
  if (
    !factoryId
    || !productionFactoryContextIds.includes(factoryId as (typeof productionFactoryContextIds)[number])
    || !asOf
    || total === null
    || returned === null
    || limit === null
    || offset === null
    || rawOrders === null
    || rawOrders.length > 20
    || returned !== rawOrders.length
    || total < returned
    || typeof source.truncated !== 'boolean'
    || source.truncated !== (offset + returned < total)
  ) return null

  const orders: AICartonProcurementSummary[] = []
  for (const rawOrder of rawOrders) {
    const order = record(rawOrder)
    if (!order || !hasExactKeys(order, [
      'order_id', 'order_no', 'customer_name', 'contract_no', 'item_no',
      'product_name', 'order_date', 'due_date', 'status', 'revision', 'updated_at',
    ])) return null
    const orderId = boundedText(order.order_id, 1, 96)
    const orderNo = boundedText(order.order_no, 1, 64)
    const customerName = boundedText(order.customer_name, 0, 255)
    const contractNo = boundedText(order.contract_no, 0, 128)
    const itemNo = boundedText(order.item_no, 0, 128)
    const productName = boundedText(order.product_name, 0, 255)
    const orderDate = boundedText(order.order_date, 0, 10)
    const dueDate = boundedText(order.due_date, 0, 10)
    const status = boundedText(order.status, 1, 32)
    const revision = boundedInteger(order.revision, 1, Number.MAX_SAFE_INTEGER)
    const updatedAt = boundedText(order.updated_at, 0, 40)
    if (
      !orderId
      || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$/.test(orderId)
      || !orderNo
      || customerName === null
      || contractNo === null
      || itemNo === null
      || productName === null
      || orderDate === null
      || dueDate === null
      || !status
      || revision === null
      || updatedAt === null
    ) return null
    orders.push({
      orderId, orderNo, customerName, contractNo, itemNo, productName,
      orderDate, dueDate, status, revision, updatedAt,
    })
  }
  return {
    id: localId('result'),
    kind: 'carton_procurement_list',
    title: '纸箱采购摘要',
    summary: `本次返回 ${returned} 条，共 ${total} 条。`,
    sourceType: 'FORMAL',
    factoryId,
    asOf,
    truncated: source.truncated,
    links: [],
    cartonProcurement: { total, returned, limit, offset, orders },
  }
}

function isRawMaterialResultCandidate(source: Record<string, unknown>) {
  const resultType = typeof source.result_type === 'string' ? source.result_type : ''
  const schemaVersion = typeof source.schema_version === 'string' ? source.schema_version : ''
  return resultType === 'raw_material'
    || resultType.startsWith('raw_material.')
    || schemaVersion === 'raw-material'
    || schemaVersion.startsWith('raw-material-')
}

function commonRawMaterialPage(source: Record<string, unknown>, itemsKey: 'materials' | 'batches') {
  const factoryId = boundedText(source.factory_id, 1, 64)
  const asOf = boundedText(source.as_of, 1, 40)
  const total = boundedInteger(source.total, 0, Number.MAX_SAFE_INTEGER)
  const returned = boundedInteger(source.returned, 0, 20)
  const limit = boundedInteger(source.limit, 1, 20)
  const offset = boundedInteger(source.offset, 0, 10_000)
  const items = Array.isArray(source[itemsKey]) ? source[itemsKey] as unknown[] : null
  if (
    !factoryId
    || !productionFactoryContextIds.includes(factoryId as (typeof productionFactoryContextIds)[number])
    || !asOf
    || total === null
    || returned === null
    || limit === null
    || offset === null
    || items === null
    || items.length > 20
    || returned !== items.length
    || total < returned
    || typeof source.truncated !== 'boolean'
    || source.truncated !== (offset + returned < total)
  ) return null
  return { factoryId, asOf, total, returned, limit, offset, items }
}

function extractRawMaterialMasterResult(source: Record<string, unknown>): AIBusinessResult | null {
  if (!hasExactKeys(source, [
    'schema_version', 'result_type', 'source_type', 'catalog_scope', 'factory_id',
    'as_of', 'total', 'limit', 'offset', 'returned', 'truncated', 'materials',
  ])) return null
  if (
    source.schema_version !== 'raw-material-master-summary-v1'
    || source.result_type !== 'raw_material.master_summary_list'
    || source.source_type !== 'FORMAL'
    || source.catalog_scope !== 'ALL_FACTORIES'
  ) return null
  const page = commonRawMaterialPage(source, 'materials')
  if (!page) return null
  const materials: AIRawMaterialMasterSummary[] = []
  for (const rawItem of page.items) {
    const item = record(rawItem)
    if (!item || !hasExactKeys(item, [
      'material_id', 'material_code', 'material_name', 'category', 'spec',
      'unit', 'safety_stock_kg', 'status', 'updated_at',
    ])) return null
    const materialId = boundedText(item.material_id, 1, 64)
    const materialCode = boundedText(item.material_code, 1, 128)
    const materialName = boundedText(item.material_name, 0, 255)
    const category = boundedText(item.category, 0, 128)
    const spec = boundedText(item.spec, 0, 255)
    const unit = boundedText(item.unit, 0, 64)
    const updatedAt = boundedText(item.updated_at, 0, 32)
    const safetyStockKg = item.safety_stock_kg === null ? null : finiteNumber(item.safety_stock_kg)
    if (
      !materialId
      || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(materialId)
      || !materialCode
      || materialName === null
      || category === null
      || spec === null
      || unit === null
      || (item.safety_stock_kg !== null && (
        safetyStockKg === undefined
        || safetyStockKg === null
        || safetyStockKg < 0
      ))
      || !['启用', '停用'].includes(String(item.status))
      || updatedAt === null
    ) return null
    materials.push({
      materialId, materialCode, materialName, category, spec, unit,
      safetyStockKg: safetyStockKg ?? null,
      status: item.status as '启用' | '停用',
      updatedAt,
    })
  }
  return {
    id: localId('result'),
    kind: 'raw_material_master_list',
    title: '原料主数据摘要',
    summary: `全厂共享目录本次返回 ${page.returned} 条，共 ${page.total} 条。`,
    sourceType: 'FORMAL',
    factoryId: page.factoryId,
    asOf: page.asOf,
    truncated: source.truncated as boolean,
    links: [],
    rawMaterialMaster: {
      total: page.total,
      returned: page.returned,
      limit: page.limit,
      offset: page.offset,
      materials,
    },
  }
}

function extractRawMaterialInventoryResult(source: Record<string, unknown>): AIBusinessResult | null {
  if (!hasExactKeys(source, [
    'schema_version', 'result_type', 'source_type', 'factory_id', 'as_of',
    'total', 'limit', 'offset', 'returned', 'truncated', 'batches',
  ])) return null
  if (
    source.schema_version !== 'raw-material-inventory-summary-v1'
    || source.result_type !== 'raw_material.inventory_summary_list'
    || source.source_type !== 'FORMAL'
  ) return null
  const page = commonRawMaterialPage(source, 'batches')
  if (!page) return null
  const batches: AIRawMaterialInventorySummary[] = []
  for (const rawItem of page.items) {
    const item = record(rawItem)
    if (!item || !hasExactKeys(item, [
      'batch_id', 'material_name', 'batch_no', 'location',
      'initial_weight_kg', 'available_weight_kg', 'updated_at',
    ])) return null
    const batchId = boundedText(item.batch_id, 1, 96)
    const materialName = boundedText(item.material_name, 0, 255)
    const batchNo = boundedText(item.batch_no, 0, 128)
    const location = boundedText(item.location, 0, 128)
    const initialWeightKg = finiteNumber(item.initial_weight_kg)
    const availableWeightKg = finiteNumber(item.available_weight_kg)
    const updatedAt = boundedText(item.updated_at, 0, 32)
    if (
      !batchId
      || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$/.test(batchId)
      || materialName === null
      || batchNo === null
      || location === null
      || initialWeightKg === undefined
      || initialWeightKg < 0
      || availableWeightKg === undefined
      || availableWeightKg < 0
      || updatedAt === null
    ) return null
    batches.push({
      batchId, materialName, batchNo, location, initialWeightKg, availableWeightKg, updatedAt,
    })
  }
  return {
    id: localId('result'),
    kind: 'raw_material_inventory_list',
    title: '原料库存摘要',
    summary: `本次返回 ${page.returned} 个批次，共 ${page.total} 个。`,
    sourceType: 'FORMAL',
    factoryId: page.factoryId,
    asOf: page.asOf,
    truncated: source.truncated as boolean,
    links: [],
    rawMaterialInventory: {
      total: page.total,
      returned: page.returned,
      limit: page.limit,
      offset: page.offset,
      batches,
    },
  }
}

function extractRawMaterialResult(source: Record<string, unknown>) {
  if (source.result_type === 'raw_material.master_summary_list') {
    return extractRawMaterialMasterResult(source)
  }
  if (source.result_type === 'raw_material.inventory_summary_list') {
    return extractRawMaterialInventoryResult(source)
  }
  return null
}

function isCustomerOrderResultCandidate(source: Record<string, unknown>) {
  const resultType = typeof source.result_type === 'string' ? source.result_type : ''
  const schemaVersion = typeof source.schema_version === 'string' ? source.schema_version : ''
  return resultType === 'customer_order'
    || resultType.startsWith('customer_order.')
    || schemaVersion === 'customer-order'
    || schemaVersion.startsWith('customer-order-')
}

function verifiedCustomerOrderFactory(source: Record<string, unknown>) {
  const factoryId = boundedText(source.factory_id, 1, 64)
  return factoryId
    && productionFactoryContextIds.includes(factoryId as (typeof productionFactoryContextIds)[number])
    ? factoryId
    : null
}

function extractCustomerOrderCapabilities(
  source: Record<string, unknown>,
): AIBusinessResult | null {
  if (!hasExactKeys(source, [
    'schema_version', 'result_type', 'source_type', 'factory_id', 'as_of',
    'authoritative_order_ledger', 'official_order_total_available',
    'supported_operations', 'customers',
  ])) return null
  if (
    source.schema_version !== 'customer-order-capabilities-v1'
    || source.result_type !== 'customer_order.capabilities'
    || source.source_type !== 'FORMAL'
    || source.authoritative_order_ledger !== false
    || source.official_order_total_available !== false
  ) return null
  const factoryId = verifiedCustomerOrderFactory(source)
  const asOf = boundedText(source.as_of, 1, 40)
  const operations = Array.isArray(source.supported_operations)
    ? source.supported_operations
    : null
  const rawCustomers = Array.isArray(source.customers) ? source.customers : null
  if (
    !factoryId
    || !asOf
    || !operations
    || operations.length !== 3
    || operations.join('|') !== 'PREVIEW|CONTROLLED_EXPORT|EXPORT_AUDIT'
    || !rawCustomers
    || rawCustomers.length > 20
  ) return null
  const customers: AICustomerOrderCustomerCapability[] = []
  const codes = new Set<string>()
  for (const rawCustomer of rawCustomers) {
    const customer = record(rawCustomer)
    if (!customer || !hasExactKeys(customer, [
      'customer_code', 'customer_name', 'batch_preview_available',
      'controlled_export_available',
    ])) return null
    const customerCode = boundedText(customer.customer_code, 1, 64)
    const customerName = boundedText(customer.customer_name, 1, 128)
    if (
      !customerCode
      || !/^[A-Za-z0-9][A-Za-z0-9-]{0,63}$/.test(customerCode)
      || !customerName
      || customer.batch_preview_available !== true
      || customer.controlled_export_available !== true
      || codes.has(customerCode)
    ) return null
    codes.add(customerCode)
    customers.push({
      customerCode,
      customerName,
      batchPreviewAvailable: true,
      controlledExportAvailable: true,
    })
  }
  return {
    id: localId('result'),
    kind: 'customer_order_capabilities',
    title: '客户订单能力边界',
    summary: '当前支持受控预览、导出与导出审计；尚无权威订单总台账，不能提供官方订单总数。',
    sourceType: 'FORMAL',
    factoryId,
    asOf,
    links: [],
    customerOrderCapabilities: {
      authoritativeOrderLedger: false,
      officialOrderTotalAvailable: false,
      supportedOperations: operations as Array<'PREVIEW' | 'CONTROLLED_EXPORT' | 'EXPORT_AUDIT'>,
      customers,
    },
  }
}

function extractCustomerOrderExportAudits(
  source: Record<string, unknown>,
): AIBusinessResult | null {
  if (!hasExactKeys(source, [
    'schema_version', 'result_type', 'source_type', 'factory_id', 'as_of',
    'limit', 'offset', 'returned', 'truncated', 'audits',
  ])) return null
  if (
    source.schema_version !== 'customer-order-export-audit-summary-v1'
    || source.result_type !== 'customer_order.export_audit_summary_list'
    || source.source_type !== 'FORMAL'
  ) return null
  const factoryId = verifiedCustomerOrderFactory(source)
  const asOf = boundedText(source.as_of, 1, 40)
  const limit = boundedInteger(source.limit, 1, 20)
  const offset = boundedInteger(source.offset, 0, 10_000)
  const returned = boundedInteger(source.returned, 0, 20)
  const rawAudits = Array.isArray(source.audits) ? source.audits : null
  if (
    !factoryId
    || !asOf
    || limit === null
    || offset === null
    || returned === null
    || !rawAudits
    || rawAudits.length > 20
    || rawAudits.length !== returned
    || typeof source.truncated !== 'boolean'
  ) return null
  const audits: AICustomerOrderExportAuditSummary[] = []
  for (const rawAudit of rawAudits) {
    const audit = record(rawAudit)
    if (!audit || !hasExactKeys(audit, [
      'audit_id', 'customer_code', 'received_date', 'preview_schema_version',
      'output_file_name', 'output_template', 'confirmed_issue_count',
      'manual_override_count', 'created_at',
    ])) return null
    const auditId = boundedText(audit.audit_id, 1, 96)
    const customerCode = boundedText(audit.customer_code, 1, 64)
    const receivedDate = boundedText(audit.received_date, 0, 32)
    const previewSchemaVersion = boundedText(audit.preview_schema_version, 0, 96)
    const outputFileName = boundedText(audit.output_file_name, 0, 255)
    const outputTemplate = boundedText(audit.output_template, 0, 128)
    const confirmedIssueCount = boundedInteger(audit.confirmed_issue_count, 0, Number.MAX_SAFE_INTEGER)
    const manualOverrideCount = boundedInteger(audit.manual_override_count, 0, Number.MAX_SAFE_INTEGER)
    const createdAt = boundedText(audit.created_at, 0, 32)
    if (
      !auditId
      || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$/.test(auditId)
      || !customerCode
      || !/^[A-Za-z0-9][A-Za-z0-9-]{0,63}$/.test(customerCode)
      || receivedDate === null
      || previewSchemaVersion === null
      || outputFileName === null
      || outputTemplate === null
      || confirmedIssueCount === null
      || manualOverrideCount === null
      || createdAt === null
    ) return null
    audits.push({
      auditId, customerCode, receivedDate, previewSchemaVersion, outputFileName,
      outputTemplate, confirmedIssueCount, manualOverrideCount, createdAt,
    })
  }
  return {
    id: localId('result'),
    kind: 'customer_order_export_audit_list',
    title: '客户订单导出审计摘要',
    summary: `本次返回 ${returned} 条导出审计；该数量不是订单总数。`,
    sourceType: 'FORMAL',
    factoryId,
    asOf,
    truncated: source.truncated,
    links: [],
    customerOrderExportAudits: { returned, limit, offset, audits },
  }
}

function extractCustomerOrderResult(source: Record<string, unknown>) {
  if (source.result_type === 'customer_order.capabilities') {
    return extractCustomerOrderCapabilities(source)
  }
  if (source.result_type === 'customer_order.export_audit_summary_list') {
    return extractCustomerOrderExportAudits(source)
  }
  return null
}

function nullableNonNegativeNumber(value: unknown) {
  if (value === null) return null
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : undefined
}

function nullableNonNegativeInteger(value: unknown) {
  const normalized = nullableNonNegativeNumber(value)
  if (normalized === null) return null
  return normalized !== undefined && Number.isInteger(normalized) ? normalized : undefined
}

function schedulingDelta(value: unknown): AISchedulingMetricDelta | null {
  const source = record(value)
  if (!source || !hasExactKeys(source, ['before', 'after', 'change'])) return null
  const before = nullableNonNegativeInteger(source.before)
  const after = nullableNonNegativeInteger(source.after)
  const change = source.change === null
    ? null
    : typeof source.change === 'number' && Number.isInteger(source.change)
      ? source.change
      : undefined
  return before === undefined || after === undefined || change === undefined
    ? null
    : { before, after, change }
}

function schedulingMetrics(value: unknown): AISchedulingPreviewMetrics | null {
  const source = record(value)
  if (!source || !hasExactKeys(source, [
    'input_order_count', 'scheduled_count', 'review_count', 'unassigned_count',
    'moved_task_count', 'overdue', 'mold_changes', 'dark_to_light_changes',
    'load_ratio_min', 'load_ratio_max', 'load_ratio_average', 'solver_elapsed_ms',
  ])) return null
  const inputOrderCount = nullableNonNegativeInteger(source.input_order_count)
  const scheduledCount = nullableNonNegativeInteger(source.scheduled_count)
  const reviewCount = nullableNonNegativeInteger(source.review_count)
  const unassignedCount = nullableNonNegativeInteger(source.unassigned_count)
  const movedTaskCount = nullableNonNegativeInteger(source.moved_task_count)
  const loadRatioMin = nullableNonNegativeNumber(source.load_ratio_min)
  const loadRatioMax = nullableNonNegativeNumber(source.load_ratio_max)
  const loadRatioAverage = nullableNonNegativeNumber(source.load_ratio_average)
  const solverElapsedMs = nullableNonNegativeNumber(source.solver_elapsed_ms)
  const overdue = schedulingDelta(source.overdue)
  const moldChanges = schedulingDelta(source.mold_changes)
  const darkToLightChanges = schedulingDelta(source.dark_to_light_changes)
  if (
    inputOrderCount === undefined || scheduledCount === undefined
    || reviewCount === undefined || unassignedCount === undefined
    || movedTaskCount === undefined || loadRatioMin === undefined
    || loadRatioMax === undefined || loadRatioAverage === undefined
    || solverElapsedMs === undefined || !overdue || !moldChanges || !darkToLightChanges
  ) return null
  return {
    inputOrderCount, scheduledCount, reviewCount, unassignedCount, movedTaskCount,
    overdue, moldChanges, darkToLightChanges, loadRatioMin, loadRatioMax,
    loadRatioAverage, solverElapsedMs,
  }
}

function schedulingPreviewRun(value: unknown): AISchedulingPreviewRun | null {
  const source = record(value)
  if (!source || !hasExactKeys(source, [
    'run_id', 'plan_id', 'plan_revision', 'rule_revision', 'status',
    'requested_solver', 'actual_solver', 'solver_status', 'fallback_used',
    'scenario_group_id', 'scenario_name', 'alternative_no', 'horizon_start',
    'horizon_end', 'metrics',
  ])) return null
  const runId = boundedText(source.run_id, 1, 96)
  const planId = boundedText(source.plan_id, 1, 96)
  const planRevision = boundedInteger(source.plan_revision, 1, Number.MAX_SAFE_INTEGER)
  const ruleRevision = boundedInteger(source.rule_revision, 1, Number.MAX_SAFE_INTEGER)
  const solverStatus = boundedText(source.solver_status, 1, 32)
  const scenarioGroupId = boundedText(source.scenario_group_id, 1, 96)
  const scenarioName = boundedText(source.scenario_name, 1, 128)
  const alternativeNo = boundedInteger(source.alternative_no, 1, 9)
  const horizonStart = boundedText(source.horizon_start, 1, 40)
  const horizonEnd = boundedText(source.horizon_end, 1, 40)
  const metrics = schedulingMetrics(source.metrics)
  if (
    !runId || !planId || planRevision === null || ruleRevision === null
    || !['SUCCEEDED', 'PARTIAL'].includes(String(source.status))
    || !['HEURISTIC', 'CP_SAT', 'AUTO'].includes(String(source.requested_solver))
    || !['HEURISTIC', 'CP_SAT'].includes(String(source.actual_solver))
    || !solverStatus || typeof source.fallback_used !== 'boolean'
    || !scenarioGroupId || !scenarioName || alternativeNo === null
    || !horizonStart || !horizonEnd || !metrics
  ) return null
  return {
    runId,
    planId,
    planRevision,
    ruleRevision,
    status: source.status as 'SUCCEEDED' | 'PARTIAL',
    requestedSolver: source.requested_solver as 'HEURISTIC' | 'CP_SAT' | 'AUTO',
    actualSolver: source.actual_solver as 'HEURISTIC' | 'CP_SAT',
    solverStatus,
    fallbackUsed: source.fallback_used,
    scenarioGroupId,
    scenarioName,
    alternativeNo,
    horizonStart,
    horizonEnd,
    metrics,
  }
}

function isSchedulingAdvisorResultCandidate(source: Record<string, unknown>) {
  return source.result_type === 'injection_scheduling.preview_run'
    || source.result_type === 'injection_scheduling.preview_comparison'
    || source.schema_version === 'ai-scheduling-preview-v1'
    || source.schema_version === 'ai-scheduling-comparison-v1'
}

function extractSchedulingAdvisorResult(source: Record<string, unknown>): AIBusinessResult | null {
  const isPreview = source.result_type === 'injection_scheduling.preview_run'
  const expectedKeys = isPreview
    ? [
        'schema_version', 'result_type', 'source_type', 'risk_level', 'factory_id',
        'as_of', 'candidate_label', 'applied', 'intent_objective', 'run', 'entity_links',
      ]
    : [
        'schema_version', 'result_type', 'source_type', 'factory_id', 'as_of',
        'candidate_label', 'comparable_snapshot', 'comparison_warning', 'runs',
        'entity_links',
      ]
  if (!hasExactKeys(source, expectedKeys)) return null
  if (
    source.source_type !== 'FORMAL'
    || source.candidate_label !== '候选方案，尚未应用'
    || (isPreview && (
      source.schema_version !== 'ai-scheduling-preview-v1'
      || source.risk_level !== 'PREVIEW_WITH_AUDIT'
      || source.applied !== false
      || !['BALANCED', 'DELIVERY_PRIORITY', 'MINIMIZE_CHANGEOVER', 'LOAD_BALANCE']
        .includes(String(source.intent_objective))
    ))
    || (!isPreview && (
      source.schema_version !== 'ai-scheduling-comparison-v1'
      || source.result_type !== 'injection_scheduling.preview_comparison'
      || typeof source.comparable_snapshot !== 'boolean'
    ))
  ) return null
  const factoryId = boundedText(source.factory_id, 1, 64)
  const asOf = boundedText(source.as_of, 1, 40)
  if (
    !factoryId
    || !productionFactoryContextIds.includes(factoryId as (typeof productionFactoryContextIds)[number])
    || !asOf
  ) return null
  const rawRuns = isPreview ? [source.run] : Array.isArray(source.runs) ? source.runs : null
  if (!rawRuns || rawRuns.length < 1 || rawRuns.length > 4 || (!isPreview && rawRuns.length < 2)) return null
  const runs = rawRuns.map(schedulingPreviewRun)
  if (runs.some((run) => run === null)) return null
  const comparisonWarning = isPreview
    ? undefined
    : boundedText(source.comparison_warning, 1, 300)
  if (!isPreview && !comparisonWarning) return null
  return {
    id: localId('result'),
    kind: isPreview ? 'scheduling_preview' : 'scheduling_comparison',
    title: isPreview ? 'AI 排产候选方案' : '排产候选方案对比',
    summary: isPreview
      ? '方案由现有调度器生成并写入 PREVIEW 历史；尚未应用到计划草案。'
      : comparisonWarning!,
    sourceType: 'FORMAL',
    factoryId,
    asOf,
    links: safeLinks(source.entity_links),
    schedulingPreviews: {
      candidateLabel: '候选方案，尚未应用',
      ...(!isPreview ? { comparableSnapshot: source.comparable_snapshot as boolean } : {}),
      ...(comparisonWarning ? { comparisonWarning } : {}),
      runs: runs as AISchedulingPreviewRun[],
    },
  }
}

function isActionConfirmationCandidate(source: Record<string, unknown>) {
  return source.result_type === 'ai.action_confirmation'
    || source.schema_version === 'ai-action-confirmation-v1'
}

function extractActionConfirmation(source: Record<string, unknown>): AIBusinessResult | null {
  if (!hasExactKeys(source, [
    'schema_version', 'result_type', 'source_type', 'confirmation_id',
    'tool_name', 'risk_level', 'factory_id', 'entity_type', 'entity_id',
    'entity_revision', 'args_hash', 'expires_at', 'status', 'created_at',
    'confirmed_at', 'executed_at', 'failure_code', 'action_summary',
  ])) return null
  if (
    source.schema_version !== 'ai-action-confirmation-v1'
    || source.result_type !== 'ai.action_confirmation'
    || source.source_type !== 'FORMAL'
    || source.tool_name !== 'injection_scheduling.apply_preview_run'
    || source.risk_level !== 'CONSEQUENTIAL_WRITE'
    || source.entity_type !== 'auto_schedule_run'
  ) return null
  const confirmationId = boundedText(source.confirmation_id, 1, 96)
  const factoryId = boundedText(source.factory_id, 1, 64)
  const entityId = boundedText(source.entity_id, 1, 96)
  const entityRevision = boundedInteger(source.entity_revision, 1, Number.MAX_SAFE_INTEGER)
  const argsHash = boundedText(source.args_hash, 64, 64)
  const expiresAt = boundedText(source.expires_at, 1, 40)
  const createdAt = boundedText(source.created_at, 1, 40)
  const confirmedAt = boundedText(source.confirmed_at, 0, 40)
  const executedAt = boundedText(source.executed_at, 0, 40)
  const failureCode = boundedText(source.failure_code, 0, 96)
  const validStatuses = [
    'PENDING', 'CONFIRMED', 'EXECUTED', 'EXPIRED', 'CANCELLED', 'STALE', 'FAILED',
  ] as const
  const status = validStatuses.includes(source.status as typeof validStatuses[number])
    ? source.status as typeof validStatuses[number]
    : null
  const summary = record(source.action_summary)
  if (!summary || !hasExactKeys(summary, [
    'action_type', 'run_id', 'plan_id', 'plan_revision', 'rule_revision',
    'assignment_count', 'review_required_count', 'effect_label',
    'requires_override_reason',
  ])) return null
  const runId = boundedText(summary.run_id, 1, 96)
  const planId = boundedText(summary.plan_id, 1, 96)
  const planRevision = boundedInteger(summary.plan_revision, 1, Number.MAX_SAFE_INTEGER)
  const ruleRevision = boundedInteger(summary.rule_revision, 1, Number.MAX_SAFE_INTEGER)
  const assignmentCount = boundedInteger(summary.assignment_count, 0, 500)
  const reviewRequiredCount = boundedInteger(summary.review_required_count, 0, 500)
  if (
    !confirmationId || !factoryId
    || !productionFactoryContextIds.includes(factoryId as (typeof productionFactoryContextIds)[number])
    || !entityId || entityRevision === null || !argsHash || !/^[a-f0-9]{64}$/.test(argsHash)
    || !expiresAt || !createdAt || confirmedAt === null || executedAt === null
    || failureCode === null || !status
    || summary.action_type !== 'APPLY_INJECTION_AUTO_SCHEDULE_RUN'
    || summary.effect_label !== '应用到 DRAFT，不会发布生产'
    || typeof summary.requires_override_reason !== 'boolean'
    || !runId || !planId || planRevision === null || ruleRevision === null
    || assignmentCount === null || reviewRequiredCount === null
    || reviewRequiredCount > assignmentCount
  ) return null
  const confirmation: AIActionConfirmation = {
    confirmationId,
    toolName: 'injection_scheduling.apply_preview_run',
    riskLevel: 'CONSEQUENTIAL_WRITE',
    factoryId,
    entityType: 'auto_schedule_run',
    entityId,
    entityRevision,
    argsHash,
    expiresAt,
    status,
    createdAt,
    confirmedAt,
    executedAt,
    failureCode,
    actionSummary: {
      actionType: 'APPLY_INJECTION_AUTO_SCHEDULE_RUN',
      runId,
      planId,
      planRevision,
      ruleRevision,
      assignmentCount,
      reviewRequiredCount,
      effectLabel: '应用到 DRAFT，不会发布生产',
      requiresOverrideReason: summary.requires_override_reason,
    },
  }
  return {
    id: localId('result'),
    kind: 'action_confirmation',
    title: '正式 Apply 操作确认',
    summary: '该操作尚未执行；只有当前用户在确认卡上明确确认后，才会应用到 DRAFT。',
    sourceType: 'FORMAL',
    factoryId,
    asOf: createdAt,
    links: [],
    actionConfirmation: confirmation,
  }
}

function extractBusinessResult(value: unknown): AIBusinessResult | null {
  const source = record(value)
  if (!source) return null
  if (isInternalQuoteResultCandidate(source)) return extractInternalQuoteResult(source)
  if (isMoldingSampleResultCandidate(source)) return extractMoldingSampleResult(source)
  if (isCartonProcurementResultCandidate(source)) return extractCartonProcurementResult(source)
  if (isRawMaterialResultCandidate(source)) return extractRawMaterialResult(source)
  if (isCustomerOrderResultCandidate(source)) return extractCustomerOrderResult(source)
  if (isSchedulingAdvisorResultCandidate(source)) return extractSchedulingAdvisorResult(source)
  if (isActionConfirmationCandidate(source)) return extractActionConfirmation(source)
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

function toolResultData(value: unknown) {
  const result = record(value)
  return result ? result.data : undefined
}

function toolActivityLabel(toolName: string) {
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

function publicStreamFailure(event: AIStreamEnvelope) {
  return normalizeAIFailure(event.payload)
}

export const useAIAssistantStore = defineStore('aiAssistant', () => {
  const capabilities = ref<AICapabilities | null>(null)
  const capabilitiesLoading = ref(false)
  const isOpen = ref(false)
  const status = ref<'idle' | 'streaming' | 'error'>('idle')
  const messages = ref<AIConversationMessage[]>([])
  const activities = ref<AIToolActivityItem[]>([])
  const sources = ref<AISourceSummary[]>([])
  const businessResults = ref<AIBusinessResult[]>([])
  const lastError = ref('')
  const lastFailure = ref<AIFailure | null>(null)
  const retryPrompt = ref('')
  let activeController: AbortController | null = null
  let activeAssistant: AIConversationMessage | null = null
  let activePrompt = ''
  let activeHadAttachments = false
  let conversationGeneration = 0
  let capabilitiesGeneration = 0
  let capabilitiesRequest: Promise<void> | null = null

  const canUse = computed(() => Boolean(
    capabilities.value?.enabled
    && capabilities.value.available
    && capabilities.value.streaming
    && capabilities.value.pilot_access?.granted
    && (
      capabilities.value.pilot_access.max_tool_risk_level === 'PREVIEW_WITH_AUDIT'
      || capabilities.value.pilot_access.max_tool_risk_level === 'READ_ONLY'
      || (
        capabilities.value.pilot_access.max_tool_risk_level === undefined
        && capabilities.value.pilot_access.read_only
      )
    )
    && capabilities.value.pilot_access.status === 'GRANTED',
  ))
  const isStreaming = computed(() => status.value === 'streaming')
  const canRetry = computed(() => Boolean(retryPrompt.value && !isStreaming.value && canUse.value))

  function loadCapabilities(force = false): Promise<void> {
    if (capabilitiesRequest) return capabilitiesRequest
    if (capabilities.value && !force) return Promise.resolve()
    const generation = ++capabilitiesGeneration
    capabilitiesLoading.value = true
    const request = (async () => {
      try {
        const next = await getAICapabilities()
        if (generation === capabilitiesGeneration) capabilities.value = next
      } catch {
        if (generation === capabilitiesGeneration) capabilities.value = null
      } finally {
        if (generation === capabilitiesGeneration) capabilitiesLoading.value = false
      }
    })()
    capabilitiesRequest = request
    void request.finally(() => {
      if (capabilitiesRequest === request) capabilitiesRequest = null
    })
    return request
  }

  function clearActiveRequest() {
    activeController = null
    activeAssistant = null
    activePrompt = ''
    activeHadAttachments = false
  }

  function abortForReset() {
    activeController?.abort()
    clearActiveRequest()
  }

  function failureMessage(failure: AIFailure) {
    return failure.retryAfterSeconds
      ? `${failure.message} 建议 ${failure.retryAfterSeconds} 秒后再试。`
      : failure.message
  }

  function invalidateCapabilities() {
    capabilitiesGeneration += 1
    capabilities.value = null
    capabilitiesLoading.value = false
    capabilitiesRequest = null
  }

  function recordFailure(failure: AIFailure, failedPrompt = '') {
    lastFailure.value = failure
    lastError.value = failureMessage(failure)
    retryPrompt.value = failure.retryable ? failedPrompt : ''
    if (CAPABILITY_INVALIDATING_ERROR_CODES.has(failure.code)) invalidateCapabilities()
  }

  function cancelActiveRequest() {
    const controller = activeController
    if (!controller || status.value !== 'streaming') return false
    const assistant = activeAssistant
    const cancelledPrompt = activePrompt
    const canRetryCancelledPrompt = !activeHadAttachments
    controller.abort()
    clearActiveRequest()
    if (assistant?.status === 'streaming') {
      assistant.status = 'cancelled'
      if (!assistant.text) assistant.text = '已停止生成。'
    }
    activities.value = activities.value.filter((item) => item.status !== 'running')
    status.value = 'idle'
    lastFailure.value = null
    lastError.value = ''
    retryPrompt.value = canRetryCancelledPrompt ? cancelledPrompt : ''
    return true
  }

  function clearConversation() {
    conversationGeneration += 1
    abortForReset()
    status.value = 'idle'
    messages.value = []
    activities.value = []
    sources.value = []
    businessResults.value = []
    lastError.value = ''
    lastFailure.value = null
    retryPrompt.value = ''
  }

  function resetForSession() {
    clearConversation()
    isOpen.value = false
    invalidateCapabilities()
  }

  function openDrawer() {
    if (canUse.value) isOpen.value = true
  }

  function closeDrawer() {
    clearConversation()
    isOpen.value = false
  }

  function addSource(candidate: AISourceSummary | null) {
    if (!candidate) return
    const key = `${candidate.level}|${candidate.factoryId ?? ''}|${candidate.updatedAt ?? ''}|${candidate.label}`
    if (sources.value.some((item) => `${item.level}|${item.factoryId ?? ''}|${item.updatedAt ?? ''}|${item.label}` === key)) return
    if (sources.value.length < MAX_SOURCES) sources.value.push(candidate)
  }

  function addBusinessResult(candidate: AIBusinessResult | null) {
    if (!candidate) return
    const resultKey = (item: AIBusinessResult) => [
      item.kind,
      item.sourceType,
      item.factoryId ?? '',
      item.asOf ?? '',
      item.summary,
      item.planContext?.executionPublished?.planId ?? '',
      item.planContext?.planningDraft?.planId ?? '',
      item.backlog?.sourceScope ?? '',
      item.backlog?.total ?? '',
      item.backlog?.returned ?? '',
      item.internalQuote?.total ?? '',
      item.internalQuote?.quotes[0]?.quoteId ?? '',
      item.moldingSample?.total ?? '',
      item.moldingSample?.orders[0]?.orderId ?? '',
      item.cartonProcurement?.total ?? '',
      item.cartonProcurement?.orders[0]?.orderId ?? '',
      item.rawMaterialMaster?.total ?? '',
      item.rawMaterialMaster?.materials[0]?.materialId ?? '',
      item.rawMaterialInventory?.total ?? '',
      item.rawMaterialInventory?.batches[0]?.batchId ?? '',
    ].join('|')
    const key = resultKey(candidate)
    if (businessResults.value.some((item) => resultKey(item) === key)) return
    if (businessResults.value.length < MAX_BUSINESS_RESULTS) businessResults.value.push(candidate)
  }

  function updateToolActivity(event: AIStreamEnvelope) {
    if (!event.type.startsWith('tool.')) return
    const callId = text(event.payload.tool_call_id ?? event.payload.call_id, 128)
      || `${event.request_id}-${event.sequence}`
    const toolName = text(event.payload.tool_name ?? event.payload.name, 160)
    const existing = activities.value.find((item) => item.id === callId)
    const payloadStatus = text(event.payload.status, 40).toLowerCase()
    const nextStatus = ['failed', 'error', 'denied', 'timed_out'].includes(payloadStatus)
      || event.type.endsWith('failed')
      || event.type.endsWith('error')
      ? 'error'
      : payloadStatus === 'completed'
        || payloadStatus === 'success'
        || event.type.endsWith('completed')
        || event.type.endsWith('done')
        ? 'complete'
        : 'running'
    if (existing) {
      existing.status = nextStatus
      return
    }
    if (activities.value.length >= MAX_TOOL_ACTIVITIES) return
    activities.value.push({
      id: callId,
      label: toolActivityLabel(toolName),
      status: nextStatus,
    })
  }

  function applyStreamEvent(event: AIStreamEnvelope, assistant: AIConversationMessage) {
    updateToolActivity(event)
    addSource(extractSource(event.payload.source))
    addSource(extractSource(event.payload.input_source))
    if (Array.isArray(event.payload.sources)) {
      event.payload.sources.forEach((item) => addSource(extractSource(item)))
    }
    const toolResult = toolResultData(event.payload.tool_result)
    const result = toolResultData(event.payload.result)
    for (const value of [toolResult, result]) {
      const source = record(value)
      const businessResult = extractBusinessResult(value)
      if (
        !source
        || (
          !isInternalQuoteResultCandidate(source)
          && !isMoldingSampleResultCandidate(source)
          && !isCartonProcurementResultCandidate(source)
          && !isRawMaterialResultCandidate(source)
          && !isCustomerOrderResultCandidate(source)
        )
        || businessResult
      ) {
        addSource(extractSource(value))
      }
      addBusinessResult(businessResult)
    }
    if (event.type === 'message.delta') {
      const delta = streamText(event.payload.delta)
      const remaining = Math.max(MAX_MESSAGE_CHARS - assistant.text.length, 0)
      assistant.text += delta.slice(0, remaining)
      if (delta.length > remaining) assistant.status = 'truncated'
    } else if (event.type === 'message.completed') {
      if (assistant.status !== 'truncated') assistant.status = 'complete'
    } else if (event.type === 'error') {
      assistant.status = 'error'
      const failure = publicStreamFailure(event)
      if (!assistant.text) assistant.text = failure.message
      recordFailure(failure)
      status.value = 'error'
    } else if (event.type === 'response.completed') {
      if (assistant.status !== 'truncated') assistant.status = 'complete'
    }
  }

  function requestHistory(): AIChatRequestMessage[] {
    const candidates = messages.value
      .filter((message) => message.text.trim() && message.status === 'complete')
      .slice(-MAX_CONVERSATION_MESSAGES)
    const selected: AIConversationMessage[] = []
    let remainingChars = MAX_TOTAL_INPUT_CHARS
    for (let index = candidates.length - 1; index >= 0; index -= 1) {
      const candidate = candidates[index]
      if (!candidate) continue
      const candidateText = candidate.text.trim()
      if (candidateText.length > remainingChars) break
      selected.push(candidate)
      remainingChars -= candidateText.length
    }
    return selected.reverse().map((message) => ({
      role: message.role,
      content: [{ type: 'input_text', text: message.text.trim() }],
    }))
  }

  async function sendMessage(
    prompt: string,
    pageContext: AIPageContext | null,
    attachments: readonly AIRequestAttachment[] = [],
    cloudProcessingConsent: AICloudProcessingConsent | null = null,
  ) {
    const normalized = prompt.trim()
    if (!normalized || isStreaming.value || !canUse.value) return false
    if (normalized.length > MAX_MESSAGE_CHARS) {
      lastFailure.value = null
      retryPrompt.value = ''
      lastError.value = `单条消息不能超过 ${MAX_MESSAGE_CHARS} 个字符。`
      status.value = 'error'
      return false
    }
    if (attachments.length && !cloudProcessingConsent?.accepted) {
      lastFailure.value = null
      retryPrompt.value = ''
      lastError.value = '发送图片前，请先确认同意云端处理。'
      status.value = 'error'
      return false
    }

    lastError.value = ''
    lastFailure.value = null
    retryPrompt.value = ''
    activities.value = []
    sources.value = []
    businessResults.value = []
    messages.value.push({
      id: localId('user'),
      role: 'user',
      text: normalized,
      status: 'complete',
      createdAt: new Date().toISOString(),
    })
    messages.value = messages.value.slice(-(MAX_CONVERSATION_MESSAGES - 1))
    const history = requestHistory()
    const assistant = reactive<AIConversationMessage>({
      id: localId('assistant'),
      role: 'assistant',
      text: '',
      status: 'streaming',
      createdAt: new Date().toISOString(),
    })
    messages.value.push(assistant)
    const generation = conversationGeneration
    const controller = new AbortController()
    activeController = controller
    activeAssistant = assistant
    activePrompt = normalized
    activeHadAttachments = attachments.length > 0
    status.value = 'streaming'

    try {
      const terminal = await streamAIResponse({
        messages: history,
        pageContext,
        attachments,
        cloudProcessingConsent,
        signal: controller.signal,
        onEvent: (event) => {
          if (generation !== conversationGeneration || controller.signal.aborted) return
          applyStreamEvent(event, assistant)
        },
      })
      if (generation !== conversationGeneration || controller.signal.aborted) return false
      if (terminal.type === 'response.completed') {
        if (assistant.status === 'truncated') {
          recordFailure({
            code: 'AI_RESPONSE_TRUNCATED',
            message: TRUNCATED_RESPONSE_MESSAGE,
            retryable: true,
          }, attachments.length ? '' : normalized)
          status.value = 'error'
          return false
        }
        if (!assistant.text) assistant.text = 'AI 已完成响应，但没有返回可显示的文本。'
        assistant.status = 'complete'
        lastFailure.value = null
        lastError.value = ''
        retryPrompt.value = ''
        status.value = 'idle'
        return true
      }
      if (terminal.type === 'error') {
        const failure = normalizeAIFailure(terminal.payload)
        recordFailure(failure, failure.retryable && !attachments.length ? normalized : '')
      } else {
        recordFailure({
          code: 'AI_STREAM_INTERRUPTED',
          message: 'AI 连接意外中断，请重新发起请求。',
          retryable: true,
        }, attachments.length ? '' : normalized)
      }
      status.value = 'error'
      return false
    } catch (error) {
      if (generation !== conversationGeneration || controller.signal.aborted) return false
      const failure: AIFailure = error instanceof AIClientError
        ? {
            code: error.code,
            message: error.message,
            retryable: error.retryable,
            ...(error.retryAfterSeconds !== undefined
              ? { retryAfterSeconds: error.retryAfterSeconds }
              : {}),
          }
        : {
            code: 'AI_STREAM_INTERRUPTED',
            message: 'AI 连接意外中断，请重新发起请求。',
            retryable: true,
          }
      assistant.status = 'error'
      if (!assistant.text) assistant.text = failure.message
      recordFailure(failure, attachments.length ? '' : normalized)
      if (error instanceof AIClientError && error.status === 403) invalidateCapabilities()
      status.value = 'error'
      return false
    } finally {
      if (activeController === controller) clearActiveRequest()
    }
  }

  async function retryLastTextRequest(pageContext: AIPageContext | null) {
    const prompt = retryPrompt.value
    if (!prompt || isStreaming.value || !canUse.value) return false
    const assistantIndex = messages.value.length - 1
    const assistant = messages.value[assistantIndex]
    const user = messages.value[assistantIndex - 1]
    if (
      assistant
      && user
      && assistant.role === 'assistant'
      && ['error', 'cancelled', 'truncated'].includes(assistant.status)
      && user.role === 'user'
      && user.text.trim() === prompt
    ) {
      messages.value.splice(assistantIndex - 1, 2)
    }
    retryPrompt.value = ''
    return sendMessage(prompt, pageContext)
  }

  return {
    capabilities,
    capabilitiesLoading,
    isOpen,
    status,
    messages,
    activities,
    sources,
    businessResults,
    lastError,
    lastFailure,
    canUse,
    isStreaming,
    canRetry,
    loadCapabilities,
    cancelActiveRequest,
    clearConversation,
    resetForSession,
    openDrawer,
    closeDrawer,
    sendMessage,
    retryLastTextRequest,
  }
})
