import axios from 'axios'
import { uploadAIArtifact, type AIArtifactData } from '@/api/aiArtifacts'
import { http } from '@/lib/http'
import { createRandomUuidHex } from '@/lib/randomUuid'
import type { DocumentToolId } from '../types'

export type DocumentJobType =
  | 'PDF_TO_EXCEL'
  | 'PDF_TO_WORD'
  | 'WORD_TO_PDF'
  | 'PDF_TRANSLATION'
  | 'PDF_SPLIT'
export type DocumentProcessingMode = 'AUTO' | 'LOCAL_PRIVATE' | 'AI_ENHANCED'
export type DocumentJobState =
  | 'CREATED' | 'PREFLIGHTING' | 'READY' | 'RUNNING' | 'REVIEW_REQUIRED'
  | 'VERIFYING' | 'COMPLETED' | 'FAILED' | 'CANCELLED' | 'EXPIRED'
export type DocumentRouteDecision =
  | 'SYNC_LOCAL' | 'TASK_LOCAL' | 'TASK_AI_ENHANCED' | 'REVIEW_REQUIRED'
  | 'UNSUPPORTED'
export type DocumentReviewAction = 'ACCEPT' | 'EDIT' | 'MARK_UNKNOWN'

export interface DocumentReviewIssue {
  contract_version: '1'
  issue_id: string
  severity: 'INFO' | 'WARNING' | 'ERROR'
  kind: string
  page_number: number
  target_id: string
  original_value: string
  proposed_value: string
  confidence: number
  message: string
  options: DocumentReviewAction[]
}

export interface DocumentQualityReport {
  contract_version: '1'
  snapshot_sha256: string
  overall_confidence: number
  page_count: number
  native_text_page_count: number
  ocr_page_count: number
  block_count: number
  table_count: number
  review_required: boolean
  issues: DocumentReviewIssue[]
  warnings: string[]
}

export interface DocumentSnapshot {
  contract_version: '1'
  source_artifact_id: string
  source_sha256: string
  revision: number
  page_count: number
  document_kind: string
  languages: string[]
  warnings: string[]
  pages: Array<{
    page_number: number
    width: number
    height: number
    rotation: number
    extraction_route: string
    blocks: Array<{
      block_id: string
      kind: string
      bbox: [number, number, number, number]
      raw_text: string
      normalized_text: string
      confidence: number
      source: string
      needs_review: boolean
    }>
    tables: Array<{
      table_id: string
      page_number: number
      bbox: [number, number, number, number]
      row_count: number
      column_count: number
      confidence: number
      cells: Array<{
        cell_id: string
        raw_text: string
        normalized_value: string
        confidence: number
        source_page: number
        source_bbox: [number, number, number, number]
      }>
    }>
  }>
}

export interface DocumentJobOptionsInput {
  splitMode?: 'each_page' | 'ranges'
  splitPageRanges?: string
  sheetStrategy?: 'TABLE_PER_SHEET' | 'PAGE_PER_SHEET' | 'MERGE_SAME_SCHEMA'
  typeInference?: 'CONSERVATIVE' | 'SMART'
  wordMode?: 'EDITABLE' | 'LAYOUT_PRESERVING'
  translationDirection?: 'AUTO' | 'ZH_TO_EN' | 'EN_TO_ZH'
  translationLayout?: 'TRANSLATED_ONLY' | 'SIDE_BY_SIDE' | 'STACKED'
  protectedTokens?: string[]
  includeEditableDocx?: boolean
}

export interface DocumentJobCapabilities {
  contract_version: '1'
  available: boolean
  artifact_upload_available: boolean
  task_runtime_available: boolean
  cloud_ocr_available: boolean
  local_translation_available: boolean
  office_renderer_available: boolean
  supported_job_types: DocumentJobType[]
  legacy_fallback_job_types: DocumentJobType[]
}

export interface DocumentPreflight {
  contract_version: '1'
  source_artifact_id: string
  source_sha256: string
  filename: string
  detected_mime_type: string
  size_bytes: number
  page_count: number
  native_text_pages: number
  scanned_pages: number
  route_decision: DocumentRouteDecision
  warnings: string[]
}

export interface DocumentJob {
  contract_version: '1'
  id: string
  task_id: string | null
  operation_id: string
  factory_id: string
  source_artifact_id: string
  source_filename: string
  job_type: DocumentJobType
  processing_mode: DocumentProcessingMode
  state: DocumentJobState
  revision: number
  created_at: string
  updated_at: string
  terminal_at: string | null
  page_range?: { contract_version: '1'; kind: 'ALL' | 'PAGES'; pages: number[] }
  preflight?: DocumentPreflight | null
  snapshot_artifact_id?: string | null
  result_artifact_id?: string | null
  quality_report_artifact_id?: string | null
  quality_report?: DocumentQualityReport | null
  snapshot_sha256?: string | null
  input_hash?: string
  runtime_plan_hash?: string
  failure_code?: string
}

export interface DocumentJobResult {
  contract_version: '1'
  task_id: string
  artifact_id: string
  filename: string
  mime_type: string
  size_bytes: number
  sha256: string
  download_url: string
}

export interface DocumentJobOperationalMetrics {
  contract_version: '1'
  total_jobs: number
  completed_jobs: number
  failed_jobs: number
  cancelled_jobs: number
  active_jobs: number
  review_jobs: number
  success_rate: number
  review_rate: number
  p50_duration_ms: number
  p95_duration_ms: number
  cloud_page_count: number
  average_quality_confidence: number | null
}

export interface CreateDocumentJobInput {
  file: File
  factoryId: string
  toolId: DocumentToolId
  processingMode?: DocumentProcessingMode
  cloudConsentAccepted?: boolean
  options?: DocumentJobOptionsInput
  /** @deprecated Use options.splitMode. */
  splitMode?: 'each_page' | 'ranges'
  /** @deprecated Use options.splitPageRanges. */
  splitPageRanges?: string
  sourceArtifact?: AIArtifactData
  preflight?: DocumentPreflight
  operationId?: string
  onStage?: (stage: 'UPLOADING' | 'PREFLIGHTING' | 'READY') => void
  onSource?: (source: AIArtifactData) => void
  onPreflight?: (preflight: DocumentPreflight) => void
  onOperationId?: (operationId: string) => void
}

const TOOL_JOB_TYPES: Record<DocumentToolId, DocumentJobType> = {
  'pdf-to-excel': 'PDF_TO_EXCEL',
  'pdf-to-word': 'PDF_TO_WORD',
  'word-to-pdf': 'WORD_TO_PDF',
  'pdf-translation': 'PDF_TRANSLATION',
  'pdf-split': 'PDF_SPLIT',
}

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Document Job 响应无效。')
  }
  return value as Record<string, unknown>
}

function strings(value: unknown): string[] {
  if (!Array.isArray(value) || value.some(item => typeof item !== 'string')) {
    throw new Error('Document Job 列表字段无效。')
  }
  return value as string[]
}

function parseCapabilities(value: unknown): DocumentJobCapabilities {
  const source = record(value)
  if (source.contract_version !== '1') throw new Error('Document Job 合同版本无效。')
  return {
    contract_version: '1',
    available: source.available === true,
    artifact_upload_available: source.artifact_upload_available === true,
    task_runtime_available: source.task_runtime_available === true,
    cloud_ocr_available: source.cloud_ocr_available === true,
    local_translation_available: source.local_translation_available === true,
    office_renderer_available: source.office_renderer_available === true,
    supported_job_types: strings(source.supported_job_types) as DocumentJobType[],
    legacy_fallback_job_types: strings(source.legacy_fallback_job_types) as DocumentJobType[],
  }
}

function parsePreflight(value: unknown): DocumentPreflight {
  const source = record(value)
  if (source.contract_version !== '1') throw new Error('文档预检合同版本无效。')
  return {
    contract_version: '1',
    source_artifact_id: String(source.source_artifact_id),
    source_sha256: String(source.source_sha256),
    filename: String(source.filename),
    detected_mime_type: String(source.detected_mime_type),
    size_bytes: Number(source.size_bytes),
    page_count: Number(source.page_count),
    native_text_pages: Number(source.native_text_pages),
    scanned_pages: Number(source.scanned_pages),
    route_decision: String(source.route_decision) as DocumentRouteDecision,
    warnings: strings(source.warnings),
  }
}

function parseJob(value: unknown): DocumentJob {
  const source = record(value)
  if (source.contract_version !== '1') throw new Error('Document Job 合同版本无效。')
  return {
    ...(source as unknown as DocumentJob),
    contract_version: '1',
    revision: Number(source.revision),
  }
}

export function documentJobTypeForTool(toolId: DocumentToolId) {
  return TOOL_JOB_TYPES[toolId]
}

export async function getDocumentJobCapabilities(factoryId?: string) {
  const response = await http.get('/tools/document-jobs/capabilities', {
    skipForbiddenSessionRefresh: true,
    params: factoryId ? { factory_id: factoryId } : undefined,
  })
  return parseCapabilities(response.data)
}

export async function preflightDocumentJob(input: {
  factoryId: string
  artifactId: string
  toolId: DocumentToolId
  processingMode?: DocumentProcessingMode
}) {
  const response = await http.post('/tools/document-jobs/preflight', {
    contract_version: '1',
    factory_id: input.factoryId,
    source_artifact_id: input.artifactId,
    job_type: documentJobTypeForTool(input.toolId),
    processing_mode: input.processingMode ?? 'LOCAL_PRIVATE',
  })
  return parsePreflight(response.data)
}

export async function createDocumentJob(input: CreateDocumentJobInput) {
  const operationId = input.operationId
    ?? `docop-${createRandomUuidHex()}`
  input.onOperationId?.(operationId)
  let source = input.sourceArtifact
  if (!source) {
    input.onStage?.('UPLOADING')
    source = await uploadAIArtifact(
      input.file,
      input.factoryId,
      'CONFIDENTIAL_BUSINESS',
    )
    input.onSource?.(source)
  }
  let preflight = input.preflight
  if (!preflight) {
    input.onStage?.('PREFLIGHTING')
    preflight = await preflightDocumentJob({
      factoryId: input.factoryId,
      artifactId: source.id,
      toolId: input.toolId,
      processingMode: input.processingMode,
    })
    input.onPreflight?.(preflight)
  }
  if (!['TASK_LOCAL', 'TASK_AI_ENHANCED'].includes(preflight.route_decision)) {
    throw new Error(preflight.warnings[0] || '当前文档任务运行时不可用。')
  }
  input.onStage?.('READY')
  const response = await http.post('/tools/document-jobs', {
    contract_version: '1',
    operation_id: operationId,
    idempotency_key: operationId,
    factory_id: input.factoryId,
    source_artifact_id: source.id,
    source_sha256: source.sha256,
    job_type: documentJobTypeForTool(input.toolId),
    processing_mode: input.processingMode ?? 'LOCAL_PRIVATE',
    page_range: { contract_version: '1', kind: 'ALL', pages: [] },
    options: {
      split_mode: input.options?.splitMode ?? input.splitMode ?? 'each_page',
      split_page_ranges: (input.options?.splitMode ?? input.splitMode) === 'ranges'
        ? input.options?.splitPageRanges ?? input.splitPageRanges ?? ''
        : '',
      profile: 'GENERAL',
      review_threshold: 0.85,
      sheet_strategy: input.options?.sheetStrategy ?? 'TABLE_PER_SHEET',
      type_inference: input.options?.typeInference ?? 'CONSERVATIVE',
      word_mode: input.options?.wordMode ?? 'EDITABLE',
      translation_direction: input.options?.translationDirection ?? 'AUTO',
      translation_layout: input.options?.translationLayout ?? 'TRANSLATED_ONLY',
      glossary_version: 'rrn-manufacturing-v1',
      protected_tokens: input.options?.protectedTokens ?? [],
      include_editable_docx: input.options?.includeEditableDocx ?? false,
      preserve_bookmarks: true,
      office_output_quality: 'STANDARD',
    },
    ...((input.processingMode === 'AI_ENHANCED' && input.cloudConsentAccepted)
      ? {
          cloud_consent: {
            accepted: true,
            provider: 'qwen',
            region: 'cn-beijing',
            purpose: 'DOCUMENT_PARSE',
            notice_version: 'document-cloud-v1',
          },
        }
      : {}),
  })
  return { source, preflight, job: parseJob(response.data) }
}

export async function getDocumentJob(taskId: string) {
  const response = await http.get(`/tools/document-jobs/${encodeURIComponent(taskId)}`)
  return parseJob(response.data)
}

export async function getDocumentJobSnapshot(taskId: string): Promise<DocumentSnapshot> {
  const response = await http.get(`/tools/document-jobs/${encodeURIComponent(taskId)}/snapshot`)
  return response.data as DocumentSnapshot
}

export async function reviewDocumentJob(input: {
  job: DocumentJob
  actions: Array<{
    issue: DocumentReviewIssue
    action: DocumentReviewAction
    replacementValue?: string
  }>
}) {
  const { job } = input
  if (!job.task_id || !job.input_hash || !job.runtime_plan_hash || !job.snapshot_sha256) {
    throw new Error('复核任务缺少绑定哈希，请刷新后重试。')
  }
  const response = await http.post(
    `/tools/document-jobs/${encodeURIComponent(job.task_id)}/review`,
    {
      contract_version: '1',
      expected_revision: job.revision,
      expected_input_hash: job.input_hash,
      expected_runtime_plan_hash: job.runtime_plan_hash,
      patches: input.actions.map(({ issue, action, replacementValue }) => ({
        contract_version: '1',
        patch_id: `docpatch-${createRandomUuidHex()}`,
        operation_id: job.operation_id,
        issue_id: issue.issue_id,
        action,
        ...(action === 'EDIT' ? { replacement_value: replacementValue ?? '' } : {}),
        expected_snapshot_sha256: job.snapshot_sha256,
      })),
    },
  )
  return parseJob(response.data)
}

export async function listDocumentJobs(factoryId?: string) {
  const response = await http.get('/tools/document-jobs', {
    params: { ...(factoryId ? { factory_id: factoryId } : {}), limit: 20 },
  })
  const source = record(response.data)
  if (source.contract_version !== '1' || !Array.isArray(source.items)) {
    throw new Error('Document Job 列表响应无效。')
  }
  return source.items.map(parseJob)
}

export async function getDocumentJobMetrics(factoryId?: string) {
  const response = await http.get('/tools/document-jobs/metrics', {
    params: factoryId ? { factory_id: factoryId } : undefined,
  })
  return response.data as DocumentJobOperationalMetrics
}

export async function cancelDocumentJob(job: DocumentJob) {
  if (!job.task_id) throw new Error('Document Job 缺少任务标识。')
  const response = await http.post(
    `/tools/document-jobs/${encodeURIComponent(job.task_id)}/cancel`,
    {
      contract_version: '1',
      expected_revision: job.revision,
      reason_code: 'USER_CANCELLED',
    },
  )
  return parseJob(response.data)
}

export async function retryDocumentJob(job: DocumentJob) {
  if (!job.task_id) throw new Error('Document Job 缺少任务标识。')
  const response = await http.post(
    `/tools/document-jobs/${encodeURIComponent(job.task_id)}/retry`,
    {
      contract_version: '1',
      expected_revision: job.revision,
    },
  )
  return parseJob(response.data)
}

export async function getDocumentJobResult(taskId: string): Promise<DocumentJobResult> {
  const response = await http.get(`/tools/document-jobs/${encodeURIComponent(taskId)}/result`)
  return response.data as DocumentJobResult
}

export async function downloadDocumentJobResult(result: DocumentJobResult) {
  const path = result.download_url.replace(/^\/api/, '')
  const response = await http.get<Blob>(path, { responseType: 'blob' })
  return response.data
}

export function isDocumentJobUnavailable(error: unknown) {
  if (!axios.isAxiosError(error)) return false
  const status = error.response?.status
  const detail = error.response?.data?.detail
  const code = detail && typeof detail === 'object' ? detail.code : ''
  return status === 404 || code === 'DOCUMENT_JOB_UNAVAILABLE'
}
