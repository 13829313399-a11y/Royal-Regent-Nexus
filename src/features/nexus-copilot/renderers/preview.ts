export type AIPreviewStatus = 'READY' | 'STALE' | 'EXPIRED' | 'ACCESS_REVOKED' | 'INVALID'

export interface AIPreviewManifest {
  schema_version: 'ai-preview-manifest-v1'
  preview_id: string
  preview_type: string
  source_revision_hash: string
  factory_id: string
  input_hash: string
  assumptions: Array<{ key: string; label: string; value: string }>
  evidence_refs: Array<{
    evidence_id: string
    source_level: 'FORMAL_DOMAIN_SERVICE' | 'VERSIONED_MODULE_KNOWLEDGE' | 'AUTHENTICATED_SERVER_CONTEXT' | 'USER_PROVIDED' | 'MODEL_INFERENCE'
    source_name: string
    factory_id: string | null
    as_of: string
    entity_type: string | null
    entity_id: string | null
    entity_revision: number | null
    content_hash: string
    truncated: boolean
    cursor: string | null
    access_policy: 'REAUTHORIZE_ON_OPEN'
  }>
  created_by: string
  created_at: string
  expires_at: string
  status: AIPreviewStatus
  deterministic_service: boolean
  can_propose_action: boolean
  action_capability: 'CREATE_PROPOSAL_ONLY' | null
  no_write_performed: true
}

export interface AIScenarioCompare {
  schema_version: 'ai-scenario-compare-v1'
  preview_type: string
  preview_ids: string[]
  source_revision_hashes: string[]
  comparable: boolean
  comparison_basis: 'SAME_SOURCE_REVISION' | 'MIXED_SOURCE_REVISION'
  warning: string
  no_write_performed: true
}

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function exact(source: Record<string, unknown>, keys: readonly string[]) {
  return Object.keys(source).length === keys.length
    && Object.keys(source).every((key) => keys.includes(key))
}

function validDate(value: unknown) {
  return typeof value === 'string' && value.length <= 40 && Number.isFinite(Date.parse(value))
}

function parseAssumption(value: unknown) {
  const source = record(value)
  if (!source || !exact(source, ['key', 'label', 'value'])) return null
  if (typeof source.key !== 'string' || !/^[a-z][a-z0-9_]{1,63}$/.test(source.key)) return null
  if (typeof source.label !== 'string' || !source.label || source.label.length > 120) return null
  if (typeof source.value !== 'string' || !source.value || source.value.length > 240) return null
  return source as unknown as AIPreviewManifest['assumptions'][number]
}

function parseEvidence(value: unknown) {
  const source = record(value)
  const keys = [
    'evidence_id', 'source_level', 'source_name', 'factory_id', 'as_of',
    'entity_type', 'entity_id', 'entity_revision', 'content_hash', 'truncated',
    'cursor', 'access_policy',
  ] as const
  if (!source || !exact(source, keys)) return null
  if (typeof source.evidence_id !== 'string' || typeof source.source_name !== 'string') return null
  if (![
    'FORMAL_DOMAIN_SERVICE', 'VERSIONED_MODULE_KNOWLEDGE',
    'AUTHENTICATED_SERVER_CONTEXT', 'USER_PROVIDED', 'MODEL_INFERENCE',
  ].includes(String(source.source_level))) return null
  if (source.factory_id !== null && typeof source.factory_id !== 'string') return null
  if (!validDate(source.as_of) || typeof source.content_hash !== 'string' || !/^sha256:[a-f0-9]{64}$/.test(source.content_hash)) return null
  if (source.entity_type !== null && typeof source.entity_type !== 'string') return null
  if (source.entity_id !== null && typeof source.entity_id !== 'string') return null
  if (source.entity_revision !== null && (!Number.isInteger(source.entity_revision) || Number(source.entity_revision) < 0)) return null
  if (typeof source.truncated !== 'boolean' || (source.cursor !== null && typeof source.cursor !== 'string')) return null
  if (source.access_policy !== 'REAUTHORIZE_ON_OPEN') return null
  return source as unknown as AIPreviewManifest['evidence_refs'][number]
}

export function parsePreviewManifest(value: unknown): AIPreviewManifest | null {
  const source = record(value)
  const keys = [
    'schema_version', 'preview_id', 'preview_type', 'source_revision_hash',
    'factory_id', 'input_hash', 'assumptions', 'evidence_refs', 'created_by',
    'created_at', 'expires_at', 'status', 'deterministic_service',
    'can_propose_action', 'action_capability', 'no_write_performed',
  ] as const
  if (!source || !exact(source, keys) || source.schema_version !== 'ai-preview-manifest-v1') return null
  if (typeof source.preview_id !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._:-]{7,159}$/.test(source.preview_id)) return null
  if (typeof source.preview_type !== 'string' || !/^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$/.test(source.preview_type)) return null
  if (typeof source.source_revision_hash !== 'string' || !/^[a-f0-9]{64}$/.test(source.source_revision_hash)) return null
  if (typeof source.input_hash !== 'string' || !/^[a-f0-9]{64}$/.test(source.input_hash)) return null
  if (typeof source.factory_id !== 'string' || typeof source.created_by !== 'string') return null
  if (!validDate(source.created_at) || !validDate(source.expires_at) || Date.parse(source.expires_at as string) <= Date.parse(source.created_at as string)) return null
  if (!['READY', 'STALE', 'EXPIRED', 'ACCESS_REVOKED', 'INVALID'].includes(String(source.status))) return null
  if (typeof source.deterministic_service !== 'boolean' || typeof source.can_propose_action !== 'boolean' || source.no_write_performed !== true) return null
  if (source.action_capability !== null && source.action_capability !== 'CREATE_PROPOSAL_ONLY') return null
  if (source.can_propose_action !== (source.action_capability === 'CREATE_PROPOSAL_ONLY')) return null
  if (source.status !== 'READY' && source.can_propose_action) return null
  if (!Array.isArray(source.assumptions) || source.assumptions.length < 1 || source.assumptions.length > 16) return null
  if (!Array.isArray(source.evidence_refs) || source.evidence_refs.length < 1 || source.evidence_refs.length > 8) return null
  const assumptions = source.assumptions.map(parseAssumption)
  const evidence = source.evidence_refs.map(parseEvidence)
  if (assumptions.some((item) => item === null) || evidence.some((item) => item === null)) return null
  if (new Set(assumptions.map((item) => item!.key)).size !== assumptions.length) return null
  if (new Set(evidence.map((item) => item!.evidence_id)).size !== evidence.length) return null
  const expiredNow = Date.parse(source.expires_at as string) <= Date.now()
  return {
    ...source,
    assumptions,
    evidence_refs: evidence,
    ...(expiredNow ? {
      status: 'EXPIRED',
      can_propose_action: false,
      action_capability: null,
    } : {}),
  } as unknown as AIPreviewManifest
}

export function parseScenarioCompare(value: unknown): AIScenarioCompare | null {
  const source = record(value)
  const keys = [
    'schema_version', 'preview_type', 'preview_ids', 'source_revision_hashes',
    'comparable', 'comparison_basis', 'warning', 'no_write_performed',
  ] as const
  if (!source || !exact(source, keys) || source.schema_version !== 'ai-scenario-compare-v1') return null
  if (typeof source.preview_type !== 'string' || !/^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$/.test(source.preview_type)) return null
  if (!Array.isArray(source.preview_ids) || source.preview_ids.length < 2 || source.preview_ids.length > 4) return null
  if (!source.preview_ids.every((item) => typeof item === 'string' && item.length >= 8 && item.length <= 160)) return null
  if (new Set(source.preview_ids).size !== source.preview_ids.length) return null
  if (!Array.isArray(source.source_revision_hashes) || source.source_revision_hashes.length < 1 || source.source_revision_hashes.length > 4) return null
  if (!source.source_revision_hashes.every((item) => typeof item === 'string' && /^[a-f0-9]{64}$/.test(item))) return null
  if (new Set(source.source_revision_hashes).size !== source.source_revision_hashes.length) return null
  if (typeof source.comparable !== 'boolean' || typeof source.warning !== 'string' || !source.warning || source.warning.length > 300) return null
  const expectedComparable = source.source_revision_hashes.length === 1
  const expectedBasis = expectedComparable ? 'SAME_SOURCE_REVISION' : 'MIXED_SOURCE_REVISION'
  if (source.comparable !== expectedComparable || source.comparison_basis !== expectedBasis || source.no_write_performed !== true) return null
  return source as unknown as AIScenarioCompare
}
