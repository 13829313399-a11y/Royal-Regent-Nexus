import { http } from '@/lib/http'
import type {
  AIActionConfirmation,
  AIActionExecutionResult,
} from '@/features/ai-assistant/types'

interface ConfirmationEnvelope {
  schema_version: 'ai-action-confirmation-v1'
  result_type: 'ai.action_confirmation'
  source_type: 'FORMAL'
  confirmation_id: string
  tool_name: 'injection_scheduling.apply_preview_run'
  risk_level: 'CONSEQUENTIAL_WRITE'
  factory_id: string
  entity_type: 'auto_schedule_run'
  entity_id: string
  entity_revision: number
  args_hash: string
  expires_at: string
  status: AIActionConfirmation['status']
  created_at: string
  confirmed_at: string
  executed_at: string
  failure_code: string
  action_summary: {
    action_type: 'APPLY_INJECTION_AUTO_SCHEDULE_RUN'
    run_id: string
    plan_id: string
    plan_revision: number
    rule_revision: number
    assignment_count: number
    review_required_count: number
    effect_label: '应用到 DRAFT，不会发布生产'
    requires_override_reason: boolean
  }
}

function mapConfirmation(value: ConfirmationEnvelope): AIActionConfirmation {
  return {
    confirmationId: value.confirmation_id,
    toolName: value.tool_name,
    riskLevel: value.risk_level,
    factoryId: value.factory_id,
    entityType: value.entity_type,
    entityId: value.entity_id,
    entityRevision: value.entity_revision,
    argsHash: value.args_hash,
    expiresAt: value.expires_at,
    status: value.status,
    createdAt: value.created_at,
    confirmedAt: value.confirmed_at,
    executedAt: value.executed_at,
    failureCode: value.failure_code,
    actionSummary: {
      actionType: value.action_summary.action_type,
      runId: value.action_summary.run_id,
      planId: value.action_summary.plan_id,
      planRevision: value.action_summary.plan_revision,
      ruleRevision: value.action_summary.rule_revision,
      assignmentCount: value.action_summary.assignment_count,
      reviewRequiredCount: value.action_summary.review_required_count,
      effectLabel: value.action_summary.effect_label,
      requiresOverrideReason: value.action_summary.requires_override_reason,
    },
  }
}

export function newAIActionExecutionRequestId() {
  const bytes = new Uint8Array(16)
  globalThis.crypto.getRandomValues(bytes)
  return `web-ai-action-${Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('')}`
}

export async function confirmAIAction(confirmation: AIActionConfirmation) {
  const { data } = await http.post<ConfirmationEnvelope>(
    `/ai/action-confirmations/${confirmation.confirmationId}/confirm`,
    {
      factory_id: confirmation.factoryId,
      expected_args_hash: confirmation.argsHash,
    },
  )
  return mapConfirmation(data)
}

export async function cancelAIAction(confirmation: AIActionConfirmation) {
  const { data } = await http.post<ConfirmationEnvelope>(
    `/ai/action-confirmations/${confirmation.confirmationId}/cancel`,
    {
      factory_id: confirmation.factoryId,
      expected_args_hash: confirmation.argsHash,
    },
  )
  return mapConfirmation(data)
}

export async function executeAIAction(
  confirmation: AIActionConfirmation,
  reviewOverrideReason: string,
  executionRequestId = newAIActionExecutionRequestId(),
) {
  const { data } = await http.post<{
    confirmation: ConfirmationEnvelope
    result: AIActionExecutionResult
  }>(`/ai/action-confirmations/${confirmation.confirmationId}/execute`, {
    factory_id: confirmation.factoryId,
    expected_args_hash: confirmation.argsHash,
    execution_request_id: executionRequestId,
    review_override_reason: reviewOverrideReason,
  })
  return {
    confirmation: mapConfirmation(data.confirmation),
    result: data.result,
  }
}
