import type { AIBusinessResult, AISchedulingMetricDelta, AISchedulingPreviewMetrics, AISchedulingPreviewRun } from '../types'
import { productionFactoryContextIds } from '@/data/enterpriseMock'
import { boundedInteger, boundedText, bool, finiteNumber, hasExactKeys, localId, record, safeLinks, text } from './contracts'
import { parsePreviewManifest, parseScenarioCompare } from '@/features/nexus-copilot/renderers/preview'


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
  const legacyKeys = [
    'run_id', 'plan_id', 'plan_revision', 'rule_revision', 'status',
    'requested_solver', 'actual_solver', 'solver_status', 'fallback_used',
    'scenario_group_id', 'scenario_name', 'alternative_no', 'horizon_start',
    'horizon_end', 'metrics',
  ]
  const currentKeys = [...legacyKeys, 'preview_manifest']
  if (!source || (!hasExactKeys(source, legacyKeys) && !hasExactKeys(source, currentKeys))) return null
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
  const previewManifest = source.preview_manifest === undefined
    ? undefined
    : parsePreviewManifest(source.preview_manifest)
  if (
    !runId || !planId || planRevision === null || ruleRevision === null
    || !['SUCCEEDED', 'PARTIAL'].includes(String(source.status))
    || !['HEURISTIC', 'CP_SAT', 'AUTO'].includes(String(source.requested_solver))
    || !['HEURISTIC', 'CP_SAT'].includes(String(source.actual_solver))
    || !solverStatus || typeof source.fallback_used !== 'boolean'
    || !scenarioGroupId || !scenarioName || alternativeNo === null
    || !horizonStart || !horizonEnd || !metrics
    || (source.preview_manifest !== undefined && !previewManifest)
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
    ...(previewManifest ? { previewManifest } : {}),
  }
}

export function isSchedulingAdvisorResultCandidate(source: Record<string, unknown>) {
  return source.result_type === 'injection_scheduling.preview_run'
    || source.result_type === 'injection_scheduling.preview_comparison'
    || source.schema_version === 'ai-scheduling-preview-v1'
    || source.schema_version === 'ai-scheduling-comparison-v1'
}

export function extractSchedulingAdvisorResult(source: Record<string, unknown>): AIBusinessResult | null {
  const isPreview = source.result_type === 'injection_scheduling.preview_run'
  const legacyKeys = isPreview
    ? [
        'schema_version', 'result_type', 'source_type', 'risk_level', 'factory_id',
        'as_of', 'candidate_label', 'applied', 'intent_objective', 'run', 'entity_links',
      ]
    : [
        'schema_version', 'result_type', 'source_type', 'factory_id', 'as_of',
        'candidate_label', 'comparable_snapshot', 'comparison_warning', 'runs',
        'entity_links',
      ]
  const currentKeys = isPreview ? legacyKeys : [...legacyKeys, 'scenario_compare']
  if (!hasExactKeys(source, legacyKeys) && !hasExactKeys(source, currentKeys)) return null
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
  const scenarioCompare = isPreview || source.scenario_compare === undefined
    ? undefined
    : parseScenarioCompare(source.scenario_compare)
  if (
    (!isPreview && !comparisonWarning)
    || (source.scenario_compare !== undefined && !scenarioCompare)
    || (scenarioCompare && scenarioCompare.comparable !== source.comparable_snapshot)
  ) return null
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
      ...(scenarioCompare ? { scenarioCompare } : {}),
      runs: runs as AISchedulingPreviewRun[],
    },
  }
}
