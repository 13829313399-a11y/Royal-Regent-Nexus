import type { AIActionConfirmation, AIBusinessResult } from '../types'
import { productionFactoryContextIds } from '@/data/enterpriseMock'
import { boundedInteger, boundedText, bool, hasExactKeys, localId, record } from './contracts'


export function isActionConfirmationCandidate(source: Record<string, unknown>) {
  return source.result_type === 'ai.action_confirmation'
    || source.schema_version === 'ai-action-confirmation-v1'
}

export function extractActionConfirmation(source: Record<string, unknown>): AIBusinessResult | null {
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
