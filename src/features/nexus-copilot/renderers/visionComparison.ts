export interface VisionObservationRow {
  row_index: number
  order_no: string | null
  order_no_confidence: number
  item_no: string | null
  item_no_confidence: number
  mold_no: string | null
  mold_no_confidence: number
  delivery_due_date: string | null
  delivery_due_date_confidence: number
  outstanding_quantity: string | null
  outstanding_quantity_confidence: number
  row_confidence: number
  uncertain_fields: string[]
}

export interface VisionProviderObservation {
  contract_version: '1'
  domain: 'INJECTION_SCHEDULING_BACKLOG'
  overall_confidence: number
  instructions_detected: boolean
  unreadable_region_count: number
  rows: VisionObservationRow[]
}

export interface VisionObservationResult {
  contract_version: '1'
  result_type: 'vision.injection_backlog_observation.v1'
  source_type: 'USER_PROVIDED'
  factory_id: string
  source_artifact_id: string
  source_sha256: string
  as_of: string
  provider: string
  model: string
  provider_call_count: 1
  tool_count: 0
  low_confidence_threshold: 0.8
  observation: VisionProviderObservation
}

export interface VisionFormalItem {
  order_id: string
  order_no: string
  item_no: string
  product_name: string
  mold_no: string
  priority_code: 'NORMAL' | 'URGENT' | 'CRITICAL'
  priority_business_label: string
  delivery_due_date: string
  order_quantity: number
  outstanding_quantity: number
  mold_enrichment_status: string
  mold_enrichment_business_label: string
  source_type: string
}

export interface VisionObservationEvidence {
  evidence_id: string
  source_level: 'USER_PROVIDED'
  source_name: 'vision.observe_injection_backlog_image'
  factory_id: string
  as_of: string
  entity_type: string | null
  entity_id: string | null
  entity_revision: number | null
  content_hash: string
  truncated: boolean
  cursor: string | null
  access_policy: 'REAUTHORIZE_ON_OPEN'
}

export interface VisionComparisonRow {
  status: 'MATCHED' | 'DIFFERENT' | 'IMAGE_ONLY' | 'FORMAL_ONLY' | 'UNCONFIRMED'
  observation: VisionObservationRow | null
  formal: VisionFormalItem | null
  field_comparisons: Array<{
    field: 'mold_no' | 'delivery_due_date' | 'outstanding_quantity'
    observed: string | null
    formal: string | null
    status: 'SAME' | 'DIFFERENT' | 'UNCONFIRMED'
  }>
  reason_code: string
}

export interface VisionComparisonResult {
  contract_version: '1'
  result_type: 'vision.injection_backlog_comparison.v1'
  source_type: 'FORMAL'
  factory_id: string
  observation_task_id: string
  source_artifact_id: string
  source_sha256: string
  observation_evidence: VisionObservationEvidence
  observation: VisionProviderObservation
  formal_backlog: {
    source_type: 'FORMAL'
    factory_id: string
    as_of: string
    source_scope: 'PLANNING_DRAFT' | 'GLOBAL_BACKLOG'
    source_business_label: string
    total: number
    limit: number
    offset: number
    returned: number
    truncated: boolean
    items: VisionFormalItem[]
    entity_links: Array<{
      label: string
      route: string
      query: Record<string, string>
    }>
  }
  comparison_rows: VisionComparisonRow[]
  matched_count: number
  different_count: number
  unconfirmed_count: number
  image_only_count: number
  formal_only_count: number
  no_write_performed: true
}

export type VisionTaskResult = VisionObservationResult | VisionComparisonResult

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function hasOnly(source: Record<string, unknown>, keys: readonly string[]) {
  return Object.keys(source).every((key) => keys.includes(key))
}

function finiteConfidence(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1
}

function nonNegativeInteger(value: unknown) {
  return Number.isInteger(value) && Number(value) >= 0
}

function nonNegativeNumber(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0
}

function safeBusinessId(value: unknown) {
  return typeof value === 'string' && /^[A-Za-z0-9._/-]{1,64}$/.test(value)
}

function nullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string'
}

function parseObservationRow(value: unknown): VisionObservationRow | null {
  const source = record(value)
  const keys = [
    'row_index', 'order_no', 'order_no_confidence', 'item_no', 'item_no_confidence',
    'mold_no', 'mold_no_confidence', 'delivery_due_date', 'delivery_due_date_confidence',
    'outstanding_quantity', 'outstanding_quantity_confidence', 'row_confidence',
    'uncertain_fields',
  ] as const
  if (!source || !hasOnly(source, keys) || Object.keys(source).length !== keys.length) return null
  if (!Number.isInteger(source.row_index) || Number(source.row_index) < 1) return null
  if (![source.order_no, source.item_no, source.mold_no, source.delivery_due_date, source.outstanding_quantity].every(nullableString)) return null
  if ([source.order_no, source.item_no, source.mold_no].some((item) => item !== null && !safeBusinessId(item))) return null
  if (![source.order_no_confidence, source.item_no_confidence, source.mold_no_confidence, source.delivery_due_date_confidence, source.outstanding_quantity_confidence, source.row_confidence].every(finiteConfidence)) return null
  if (!Array.isArray(source.uncertain_fields) || !source.uncertain_fields.every((item) => typeof item === 'string')) return null
  return source as unknown as VisionObservationRow
}

function parseObservation(value: unknown): VisionProviderObservation | null {
  const source = record(value)
  const keys = ['contract_version', 'domain', 'overall_confidence', 'instructions_detected', 'unreadable_region_count', 'rows'] as const
  if (!source || !hasOnly(source, keys) || Object.keys(source).length !== keys.length) return null
  if (source.contract_version !== '1' || source.domain !== 'INJECTION_SCHEDULING_BACKLOG') return null
  if (!finiteConfidence(source.overall_confidence) || typeof source.instructions_detected !== 'boolean') return null
  if (!nonNegativeInteger(source.unreadable_region_count) || !Array.isArray(source.rows) || source.rows.length > 20) return null
  const rows = source.rows.map(parseObservationRow)
  if (rows.some((row) => row === null)) return null
  return { ...source, rows } as VisionProviderObservation
}

function parseFormalItem(value: unknown): VisionFormalItem | null {
  const source = record(value)
  const keys = [
    'order_id', 'order_no', 'item_no', 'product_name', 'mold_no', 'priority_code',
    'priority_business_label', 'delivery_due_date', 'order_quantity',
    'outstanding_quantity', 'mold_enrichment_status',
    'mold_enrichment_business_label', 'source_type',
  ] as const
  if (!source || !hasOnly(source, keys) || Object.keys(source).length !== keys.length) return null
  for (const name of [
    'order_id', 'order_no', 'item_no', 'product_name', 'mold_no',
    'priority_business_label', 'delivery_due_date', 'mold_enrichment_status',
    'mold_enrichment_business_label', 'source_type',
  ]) {
    if (typeof source[name] !== 'string') return null
  }
  if (!['NORMAL', 'URGENT', 'CRITICAL'].includes(String(source.priority_code))) return null
  if (!nonNegativeNumber(source.order_quantity) || !nonNegativeNumber(source.outstanding_quantity)) return null
  return source as unknown as VisionFormalItem
}

function parseObservationEvidence(value: unknown): VisionObservationEvidence | null {
  const source = record(value)
  const keys = [
    'evidence_id', 'source_level', 'source_name', 'factory_id', 'as_of',
    'entity_type', 'entity_id', 'entity_revision', 'content_hash', 'truncated',
    'cursor', 'access_policy',
  ] as const
  if (!source || !hasOnly(source, keys) || Object.keys(source).length !== keys.length) return null
  if (source.source_level !== 'USER_PROVIDED' || source.source_name !== 'vision.observe_injection_backlog_image') return null
  if (source.access_policy !== 'REAUTHORIZE_ON_OPEN' || typeof source.truncated !== 'boolean') return null
  if (![source.evidence_id, source.factory_id, source.as_of].every((item) => typeof item === 'string')) return null
  if (typeof source.content_hash !== 'string' || !/^sha256:[a-f0-9]{64}$/.test(source.content_hash)) return null
  if (!nullableString(source.entity_type) || !nullableString(source.entity_id) || !nullableString(source.cursor)) return null
  if (source.entity_revision !== null && !nonNegativeInteger(source.entity_revision)) return null
  return source as unknown as VisionObservationEvidence
}

function parseEntityLink(value: unknown) {
  const source = record(value)
  if (!source || !hasOnly(source, ['label', 'route', 'query']) || Object.keys(source).length !== 3) return null
  const query = record(source.query)
  if (typeof source.label !== 'string' || typeof source.route !== 'string' || !query) return null
  if (!Object.values(query).every((item) => typeof item === 'string')) return null
  return { label: source.label, route: source.route, query: query as Record<string, string> }
}

function parseComparisonRow(value: unknown): VisionComparisonRow | null {
  const source = record(value)
  const keys = ['status', 'observation', 'formal', 'field_comparisons', 'reason_code'] as const
  if (!source || !hasOnly(source, keys) || Object.keys(source).length !== keys.length) return null
  if (!['MATCHED', 'DIFFERENT', 'IMAGE_ONLY', 'FORMAL_ONLY', 'UNCONFIRMED'].includes(String(source.status))) return null
  const observation = source.observation === null ? null : parseObservationRow(source.observation)
  const formal = source.formal === null ? null : parseFormalItem(source.formal)
  if (source.observation !== null && !observation) return null
  if (source.formal !== null && !formal) return null
  if (!Array.isArray(source.field_comparisons) || typeof source.reason_code !== 'string') return null
  const comparisons = source.field_comparisons.map((item) => {
    const entry = record(item)
    if (!entry || !hasOnly(entry, ['field', 'observed', 'formal', 'status']) || Object.keys(entry).length !== 4) return null
    if (!['mold_no', 'delivery_due_date', 'outstanding_quantity'].includes(String(entry.field))) return null
    if (!nullableString(entry.observed) || !nullableString(entry.formal)) return null
    if (!['SAME', 'DIFFERENT', 'UNCONFIRMED'].includes(String(entry.status))) return null
    return entry
  })
  if (comparisons.some((entry) => entry === null)) return null
  return { ...source, observation, formal, field_comparisons: comparisons } as VisionComparisonRow
}

export function parseVisionTaskResult(value: unknown): VisionTaskResult | null {
  const source = record(value)
  if (!source || source.contract_version !== '1') return null
  const observation = parseObservation(source.observation)
  if (!observation) return null
  if (source.result_type === 'vision.injection_backlog_observation.v1') {
    const keys = ['contract_version', 'result_type', 'source_type', 'factory_id', 'source_artifact_id', 'source_sha256', 'as_of', 'provider', 'model', 'provider_call_count', 'tool_count', 'low_confidence_threshold', 'observation'] as const
    if (!hasOnly(source, keys) || Object.keys(source).length !== keys.length) return null
    if (source.source_type !== 'USER_PROVIDED' || source.provider_call_count !== 1 || source.tool_count !== 0 || source.low_confidence_threshold !== 0.8) return null
    if (![source.factory_id, source.source_artifact_id, source.source_sha256, source.as_of, source.provider, source.model].every((item) => typeof item === 'string')) return null
    return { ...source, observation } as VisionObservationResult
  }
  if (source.result_type !== 'vision.injection_backlog_comparison.v1') return null
  const keys = ['contract_version', 'result_type', 'source_type', 'factory_id', 'observation_task_id', 'source_artifact_id', 'source_sha256', 'observation_evidence', 'observation', 'formal_backlog', 'comparison_rows', 'matched_count', 'different_count', 'unconfirmed_count', 'image_only_count', 'formal_only_count', 'no_write_performed'] as const
  if (!hasOnly(source, keys) || Object.keys(source).length !== keys.length || source.source_type !== 'FORMAL' || source.no_write_performed !== true) return null
  const observationEvidence = parseObservationEvidence(source.observation_evidence)
  if (!observationEvidence) return null
  const formal = record(source.formal_backlog)
  const formalKeys = [
    'source_type', 'factory_id', 'as_of', 'source_scope', 'source_business_label',
    'total', 'limit', 'offset', 'returned', 'truncated', 'items', 'entity_links',
  ] as const
  if (!formal || !hasOnly(formal, formalKeys) || Object.keys(formal).length !== formalKeys.length) return null
  if (formal.source_type !== 'FORMAL' || !['PLANNING_DRAFT', 'GLOBAL_BACKLOG'].includes(String(formal.source_scope))) return null
  if (![formal.factory_id, formal.as_of, formal.source_business_label].every((item) => typeof item === 'string')) return null
  if (![formal.total, formal.limit, formal.offset, formal.returned].every(nonNegativeInteger) || typeof formal.truncated !== 'boolean' || !Array.isArray(formal.items) || !Array.isArray(formal.entity_links)) return null
  const items = formal.items.map(parseFormalItem)
  const entityLinks = formal.entity_links.map(parseEntityLink)
  if (items.some((item) => item === null) || entityLinks.some((item) => item === null) || formal.returned !== items.length || !Array.isArray(source.comparison_rows) || source.comparison_rows.length > 70) return null
  const rows = source.comparison_rows.map(parseComparisonRow)
  if (rows.some((row) => row === null)) return null
  for (const key of ['matched_count', 'different_count', 'unconfirmed_count', 'image_only_count', 'formal_only_count']) {
    if (!Number.isInteger(source[key]) || Number(source[key]) < 0) return null
  }
  const counts = Object.fromEntries(
    ['MATCHED', 'DIFFERENT', 'UNCONFIRMED', 'IMAGE_ONLY', 'FORMAL_ONLY']
      .map((status) => [status, rows.filter((row) => row?.status === status).length]),
  )
  if (
    source.matched_count !== counts.MATCHED
    || source.different_count !== counts.DIFFERENT
    || source.unconfirmed_count !== counts.UNCONFIRMED
    || source.image_only_count !== counts.IMAGE_ONLY
    || source.formal_only_count !== counts.FORMAL_ONLY
  ) return null
  return {
    ...source,
    observation_evidence: observationEvidence,
    observation,
    formal_backlog: { ...formal, items, entity_links: entityLinks },
    comparison_rows: rows,
  } as unknown as VisionComparisonResult
}
