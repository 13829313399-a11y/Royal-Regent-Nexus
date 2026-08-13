import { http } from '@/lib/http'
import type {
  AIArtifactEgressConsent,
  AIInjectionSchedulingPageContext,
} from '@/features/ai-assistant/types'

export type AITaskType = 'READ' | 'COMPUTE' | 'SIMULATE' | 'PREVIEW'
export type AITaskState =
  | 'CREATED' | 'UNDERSTOOD' | 'PLANNED' | 'RUNNING' | 'WAITING_INPUT'
  | 'WAITING_APPROVAL' | 'VERIFYING' | 'COMPLETED' | 'CANCELLING'
  | 'CANCELLED' | 'FAILED' | 'RETRY_PENDING'
export type AITaskWorkerStatus = 'QUEUED' | 'LEASED' | 'WAITING_RETRY' | 'IDLE'
export type AITaskStepState =
  | 'PENDING' | 'RUNNING' | 'WAITING_INPUT' | 'VERIFYING'
  | 'COMPLETED' | 'CANCELLED' | 'FAILED' | 'RETRY_PENDING'

export interface AITaskSummary {
  id: string
  conversation_id: string | null
  factory_scope: string
  task_type: AITaskType
  state: AITaskState
  maximum_risk: 'READ_ONLY' | 'PREVIEW_WITH_AUDIT'
  primary_skill_id: string
  revision: number
  step_count: number
  worker_status: AITaskWorkerStatus
  created_at: string
  updated_at: string
  terminal_at: string | null
}

export interface AITaskCapabilities {
  contract_version: '1'
  available: boolean
  worker_enabled: boolean
}

export interface AITaskStep {
  id: string
  task_id: string
  ordinal: number
  key: string
  kind: AITaskType
  label: string
  state: AITaskStepState
  tool_name: string | null
  tool_version: string | null
  arguments_hash: string
  side_effect_class: 'NONE' | 'PREVIEW_STATE'
  idempotent: boolean
  revision: number
  attempt_count: number
  max_attempts: number
  result_hash: string
  result_metadata: Record<string, unknown>
  created_at: string
  updated_at: string
  started_at: string | null
  completed_at: string | null
  failure_code: string
}

export interface AITaskDetail extends AITaskSummary {
  owner_user_id: string
  input_message_id: string | null
  primary_skill_version: string
  primary_skill_hash: string
  prompt_version: string
  prompt_hash: string
  runtime_plan: Record<string, unknown>
  runtime_plan_hash: string
  input_hash: string
  retention_expires_at: string | null
  backup_delete_by: string | null
  cancellation_requested_at: string | null
  resume_requested_at: string | null
  failure_code: string
  lease_expires_at: string | null
  last_heartbeat_at: string | null
  next_attempt_at: string | null
  claim_count: number
  steps: AITaskStep[]
}

export interface AITaskEvent {
  id: string
  task_id: string
  step_id: string | null
  sequence: number
  event_type: string
  actor_type: 'USER' | 'SYSTEM'
  transition_from: string | null
  transition_to: string | null
  reason_code: string
  evidence: unknown[]
  artifacts: unknown[]
  created_at: string
}

export interface AIArtifactTranslationTaskInput {
  artifactId: string
  artifactSha256: string
  factoryId: string
  direction: 'zh_to_en' | 'en_to_zh'
  selectedSheetNames?: string[]
  operationId?: string
}

export interface AIVisionObservationTaskInput {
  artifactId: string
  factoryId: string
  consent: AIArtifactEgressConsent
  pageContext: AIInjectionSchedulingPageContext
  operationId?: string
}

export interface AIVisionComparisonTaskInput {
  observationTaskId: string
  factoryId: string
  operationId?: string
}

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('AI Task response is invalid')
  return value as Record<string, unknown>
}

function closed(source: Record<string, unknown>, fields: readonly string[]) {
  if (Object.keys(source).some((key) => !fields.includes(key))) throw new Error('AI Task response has unknown fields')
}

function stringValue(value: unknown, nullable = false): string | null {
  if (nullable && value === null) return null
  if (typeof value !== 'string') throw new Error('AI Task string is invalid')
  return value
}

function integer(value: unknown, minimum = 0): number {
  if (!Number.isInteger(value) || Number(value) < minimum) throw new Error('AI Task integer is invalid')
  return Number(value)
}

const summaryFields = [
  'id', 'conversation_id', 'factory_scope', 'task_type', 'state', 'maximum_risk',
  'primary_skill_id', 'revision', 'step_count', 'worker_status', 'created_at',
  'updated_at', 'terminal_at',
] as const

function parseSummary(value: unknown): AITaskSummary {
  const source = record(value)
  closed(source, summaryFields)
  const id = stringValue(source.id) as string
  if (!/^aitask-[a-f0-9]{32}$/.test(id)) throw new Error('AI Task id is invalid')
  return {
    id,
    conversation_id: stringValue(source.conversation_id, true),
    factory_scope: stringValue(source.factory_scope) as string,
    task_type: stringValue(source.task_type) as AITaskType,
    state: stringValue(source.state) as AITaskState,
    maximum_risk: stringValue(source.maximum_risk) as AITaskSummary['maximum_risk'],
    primary_skill_id: stringValue(source.primary_skill_id) as string,
    revision: integer(source.revision, 1),
    step_count: integer(source.step_count, 1),
    worker_status: stringValue(source.worker_status) as AITaskWorkerStatus,
    created_at: stringValue(source.created_at) as string,
    updated_at: stringValue(source.updated_at) as string,
    terminal_at: stringValue(source.terminal_at, true),
  }
}

function parseStep(value: unknown): AITaskStep {
  const source = record(value)
  const fields = [
    'id', 'task_id', 'ordinal', 'key', 'kind', 'label', 'state', 'tool_name',
    'tool_version', 'arguments_hash', 'side_effect_class', 'idempotent', 'revision',
    'attempt_count', 'max_attempts', 'result_hash', 'result_metadata', 'created_at',
    'updated_at', 'started_at', 'completed_at', 'failure_code',
  ] as const
  closed(source, fields)
  return {
    id: stringValue(source.id) as string,
    task_id: stringValue(source.task_id) as string,
    ordinal: integer(source.ordinal, 1),
    key: stringValue(source.key) as string,
    kind: stringValue(source.kind) as AITaskType,
    label: stringValue(source.label) as string,
    state: stringValue(source.state) as AITaskStepState,
    tool_name: stringValue(source.tool_name, true),
    tool_version: stringValue(source.tool_version, true),
    arguments_hash: stringValue(source.arguments_hash) as string,
    side_effect_class: stringValue(source.side_effect_class) as AITaskStep['side_effect_class'],
    idempotent: source.idempotent === true,
    revision: integer(source.revision, 1),
    attempt_count: integer(source.attempt_count),
    max_attempts: integer(source.max_attempts, 1),
    result_hash: stringValue(source.result_hash) as string,
    result_metadata: record(source.result_metadata),
    created_at: stringValue(source.created_at) as string,
    updated_at: stringValue(source.updated_at) as string,
    started_at: stringValue(source.started_at, true),
    completed_at: stringValue(source.completed_at, true),
    failure_code: stringValue(source.failure_code) as string,
  }
}

export function parseAITaskDetail(value: unknown): AITaskDetail {
  const source = record(value)
  const detailFields = [
    'id', 'owner_user_id', 'conversation_id', 'input_message_id', 'factory_scope',
    'task_type', 'state', 'maximum_risk', 'primary_skill_id', 'primary_skill_version',
    'primary_skill_hash', 'prompt_version', 'prompt_hash', 'runtime_plan',
    'runtime_plan_hash', 'input_hash', 'revision', 'step_count', 'created_at',
    'updated_at', 'terminal_at', 'retention_expires_at', 'backup_delete_by',
    'cancellation_requested_at', 'resume_requested_at', 'failure_code',
    'worker_status', 'lease_expires_at', 'last_heartbeat_at', 'next_attempt_at',
    'claim_count', 'steps',
  ] as const
  closed(source, detailFields)
  if (!Array.isArray(source.steps)) throw new Error('AI Task steps are invalid')
  const summary = parseSummary(Object.fromEntries(summaryFields.map((key) => [key, source[key]])))
  return {
    ...summary,
    owner_user_id: stringValue(source.owner_user_id) as string,
    input_message_id: stringValue(source.input_message_id, true),
    primary_skill_version: stringValue(source.primary_skill_version) as string,
    primary_skill_hash: stringValue(source.primary_skill_hash) as string,
    prompt_version: stringValue(source.prompt_version) as string,
    prompt_hash: stringValue(source.prompt_hash) as string,
    runtime_plan: record(source.runtime_plan),
    runtime_plan_hash: stringValue(source.runtime_plan_hash) as string,
    input_hash: stringValue(source.input_hash) as string,
    retention_expires_at: stringValue(source.retention_expires_at, true),
    backup_delete_by: stringValue(source.backup_delete_by, true),
    cancellation_requested_at: stringValue(source.cancellation_requested_at, true),
    resume_requested_at: stringValue(source.resume_requested_at, true),
    failure_code: stringValue(source.failure_code) as string,
    lease_expires_at: stringValue(source.lease_expires_at, true),
    last_heartbeat_at: stringValue(source.last_heartbeat_at, true),
    next_attempt_at: stringValue(source.next_attempt_at, true),
    claim_count: integer(source.claim_count),
    steps: source.steps.map(parseStep),
  }
}

function parseEvent(value: unknown): AITaskEvent {
  const source = record(value)
  const fields = [
    'id', 'task_id', 'step_id', 'sequence', 'event_type', 'actor_type',
    'transition_from', 'transition_to', 'reason_code', 'evidence', 'artifacts', 'created_at',
  ] as const
  closed(source, fields)
  if (!Array.isArray(source.evidence) || !Array.isArray(source.artifacts)) throw new Error('AI Task Event references are invalid')
  return {
    id: stringValue(source.id) as string,
    task_id: stringValue(source.task_id) as string,
    step_id: stringValue(source.step_id, true),
    sequence: integer(source.sequence, 1),
    event_type: stringValue(source.event_type) as string,
    actor_type: stringValue(source.actor_type) as AITaskEvent['actor_type'],
    transition_from: stringValue(source.transition_from, true),
    transition_to: stringValue(source.transition_to, true),
    reason_code: stringValue(source.reason_code) as string,
    evidence: source.evidence,
    artifacts: source.artifacts,
    created_at: stringValue(source.created_at) as string,
  }
}

export async function listAITasks(input: { conversationId?: string; cursor?: string; limit?: number } = {}) {
  const response = await http.get('/ai/tasks', {
    params: {
      ...(input.conversationId ? { conversation_id: input.conversationId } : {}),
      ...(input.cursor ? { cursor: input.cursor } : {}),
      limit: input.limit ?? 20,
    },
  })
  const source = record(response.data)
  closed(source, ['items', 'next_cursor'])
  if (!Array.isArray(source.items)) throw new Error('AI Task list is invalid')
  return {
    items: source.items.map(parseSummary),
    next_cursor: stringValue(source.next_cursor, true),
  }
}

export async function getAITaskCapabilities(): Promise<AITaskCapabilities> {
  const response = await http.get('/ai/tasks/capabilities', {
    skipForbiddenSessionRefresh: true,
  })
  const source = record(response.data)
  closed(source, ['contract_version', 'available', 'worker_enabled'])
  if (source.contract_version !== '1') throw new Error('AI Task capability version is invalid')
  return {
    contract_version: '1',
    available: source.available === true,
    worker_enabled: source.worker_enabled === true,
  }
}

async function sha256Hex(value: string) {
  const digest = await globalThis.crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(value),
  )
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('')
}

function newOperationId() {
  return `atrans-${globalThis.crypto.randomUUID().replaceAll('-', '')}`
}

function schedulingPageContext(factoryId: string): AIInjectionSchedulingPageContext {
  return {
    route_name: 'injection-scheduling-v2',
    path: '/modules/production/injection-scheduling',
    factory_id: factoryId,
    module_id: 'injection-scheduling',
    selected_entity: null,
  }
}

export async function createArtifactTranslationTask(
  input: AIArtifactTranslationTaskInput,
) {
  const operationId = input.operationId ?? newOperationId()
  const taskInput = JSON.stringify({
    contract: 'artifact-translation-task-v1',
    artifact_id: input.artifactId,
    artifact_sha256: input.artifactSha256,
    factory_id: input.factoryId,
    direction: input.direction,
    selected_sheet_names: input.selectedSheetNames ?? null,
    operation_id: operationId,
  })
  const response = await http.post('/ai/tasks', {
    task_type: 'PREVIEW',
    factory_scope: input.factoryId,
    primary_skill_id: 'files.document_translation',
    primary_skill_version: '1.0.0',
    proposed_tool_names: ['artifacts.translate_document_local'],
    proposed_max_steps: 1,
    proposed_maximum_risk: 'PREVIEW_WITH_AUDIT',
    input_hash: await sha256Hex(taskInput),
    idempotency_key: operationId,
    steps: [{
      key: 'translate_document',
      kind: 'PREVIEW',
      label: '本地翻译并生成派生文件',
      tool_name: 'artifacts.translate_document_local',
      arguments: {
        factory_id: input.factoryId,
        artifact_id: input.artifactId,
        operation_id: operationId,
        direction: input.direction,
        ...(input.selectedSheetNames
          ? { selected_sheet_names: input.selectedSheetNames }
          : {}),
      },
    }],
  })
  return parseAITaskDetail(response.data)
}

export async function createVisionObservationTask(
  input: AIVisionObservationTaskInput,
) {
  const operationId = input.operationId ?? `vobs-${newOperationId()}`
  const canonicalInput = JSON.stringify({
    contract: 'vision-backlog-observation-task-v1',
    artifact_id: input.artifactId,
    factory_id: input.factoryId,
    consent: input.consent,
    operation_id: operationId,
  })
  const response = await http.post('/ai/tasks', {
    task_type: 'READ',
    factory_scope: input.factoryId,
    primary_skill_id: 'vision.screenshot_observation',
    primary_skill_version: '1.0.0',
    proposed_tool_names: ['vision.observe_injection_backlog_image'],
    proposed_max_steps: 1,
    proposed_maximum_risk: 'READ_ONLY',
    input_hash: await sha256Hex(canonicalInput),
    idempotency_key: operationId,
    page_context: input.pageContext,
    steps: [{
      key: 'observe_image',
      kind: 'READ',
      label: '生成图片 Observation（不调用业务 Tool）',
      tool_name: 'vision.observe_injection_backlog_image',
      arguments: {
        factory_id: input.factoryId,
        artifact_id: input.artifactId,
        operation_id: operationId,
        consent: input.consent,
      },
    }],
  })
  return parseAITaskDetail(response.data)
}

export async function createVisionComparisonTask(
  input: AIVisionComparisonTaskInput,
) {
  const operationId = input.operationId ?? `vcmp-${newOperationId()}`
  const canonicalInput = JSON.stringify({
    contract: 'vision-backlog-comparison-task-v1',
    observation_task_id: input.observationTaskId,
    factory_id: input.factoryId,
    operation_id: operationId,
  })
  const response = await http.post('/ai/tasks', {
    task_type: 'READ',
    factory_scope: input.factoryId,
    primary_skill_id: 'vision.screenshot_observation',
    primary_skill_version: '1.0.0',
    proposed_tool_names: ['vision.compare_injection_backlog'],
    proposed_max_steps: 1,
    proposed_maximum_risk: 'READ_ONLY',
    input_hash: await sha256Hex(canonicalInput),
    idempotency_key: operationId,
    page_context: schedulingPageContext(input.factoryId),
    steps: [{
      key: 'compare_formal_backlog',
      kind: 'READ',
      label: '重新鉴权并核对当前正式 Backlog',
      tool_name: 'vision.compare_injection_backlog',
      arguments: {
        factory_id: input.factoryId,
        observation_task_id: input.observationTaskId,
        operation_id: operationId,
      },
    }],
  })
  return parseAITaskDetail(response.data)
}

export async function getAITask(taskId: string) {
  const response = await http.get(`/ai/tasks/${encodeURIComponent(taskId)}`)
  return parseAITaskDetail(response.data)
}

export async function getAITaskEvents(taskId: string, after = 0, limit = 100) {
  const response = await http.get(`/ai/tasks/${encodeURIComponent(taskId)}/events`, {
    params: { after, limit },
  })
  const source = record(response.data)
  closed(source, ['items', 'next_after'])
  if (!Array.isArray(source.items)) throw new Error('AI Task Event page is invalid')
  return {
    items: source.items.map(parseEvent),
    next_after: source.next_after === null ? null : integer(source.next_after, 1),
  }
}

export async function cancelAITask(task: AITaskDetail) {
  const response = await http.post(`/ai/tasks/${encodeURIComponent(task.id)}/cancel`, {
    expected_revision: task.revision,
    reason_code: 'USER_CANCELLED',
  })
  return parseAITaskDetail(response.data)
}

export async function resumeAITask(task: AITaskDetail) {
  const response = await http.post(`/ai/tasks/${encodeURIComponent(task.id)}/resume`, {
    expected_revision: task.revision,
    expected_input_hash: task.input_hash,
    expected_runtime_plan_hash: task.runtime_plan_hash,
  })
  return parseAITaskDetail(response.data)
}

export function isAITaskId(value: unknown): value is string {
  return typeof value === 'string' && /^aitask-[a-f0-9]{32}$/.test(value)
}
