import type {
  InjectionConstraintEvaluation,
  InjectionMachine,
  InjectionMold,
  InjectionOrder,
  InjectionRuleConfig,
  InjectionScoreBreakdown,
  InjectionSetupCost,
  InjectionSetupProfile,
  Recommendation,
} from '@/types/injectionSchedule'

export interface ScoreInjectionRecommendationInput {
  machine: InjectionMachine
  mold: InjectionMold
  order: InjectionOrder
  constraints: InjectionConstraintEvaluation
  setupCost: InjectionSetupCost
  config: InjectionRuleConfig
  previous: InjectionSetupProfile | null
  referenceAt: string
  estimatedStartAt: string | null
  estimatedEndAt: string | null
  machineLoadRatio: number
  downstreamUrgencyRatio?: number
  exactMatch?: boolean
  splitAcrossMachines?: boolean
  specialHandling?: boolean
}

const priorityUrgency: Record<InjectionOrder['priority'], number> = {
  P0: 1,
  P1: 0.75,
  P2: 0.5,
  P3: 0.25,
}

function clampRatio(value: number) {
  if (!Number.isFinite(value)) return 0
  return Math.min(Math.max(value, 0), 1)
}

function roundScore(value: number) {
  return Math.round((value + Number.EPSILON) * 100) / 100
}

function parseTimestamp(value: string | null) {
  if (!value) return null
  const timestamp = Date.parse(value)
  return Number.isFinite(timestamp) ? timestamp : null
}

function normalized(value: string | null) {
  return value?.trim().toLocaleUpperCase('en-US') ?? ''
}

function equalKnown(left: string | null, right: string | null) {
  const normalizedLeft = normalized(left)
  const normalizedRight = normalized(right)
  return Boolean(normalizedLeft) && normalizedLeft === normalizedRight
}

function inverseCostScore(weight: number, cost: number, ceiling: number) {
  if (!Number.isFinite(cost) || cost < 0) return 0
  if (!Number.isFinite(ceiling) || ceiling <= 0) return cost === 0 ? weight : 0
  return weight * (1 - clampRatio(cost / ceiling))
}

function calculateDeliverySlackHours(
  order: InjectionOrder,
  estimatedEndAt: string | null,
) {
  const dueAt = parseTimestamp(order.deliveryDueAt)
  const endAt = parseTimestamp(estimatedEndAt)
  if (dueAt == null || endAt == null) return null

  const bufferHours = Math.max(order.warehouseBufferHours, 0)
    + Math.max(order.downstreamBufferHours, 0)
  return (dueAt - endAt) / 3_600_000 - bufferHours
}

function dueUrgencyRatio(
  order: InjectionOrder,
  deliverySlackHours: number | null,
  horizonHours: number,
) {
  const priorityRatio = priorityUrgency[order.priority]
  if (deliverySlackHours == null) return priorityRatio
  if (deliverySlackHours <= 0) return 1
  if (!Number.isFinite(horizonHours) || horizonHours <= 0) return priorityRatio

  const scheduleRatio = 1 - clampRatio(deliverySlackHours / horizonHours)
  return Math.max(priorityRatio, scheduleRatio)
}

function sequenceContinuityRatio(
  previous: InjectionSetupProfile | null,
  mold: InjectionMold,
  order: InjectionOrder,
) {
  if (!previous) return 0

  const sameMold = equalKnown(previous.moldId, mold.id)
  const sameMaterial = equalKnown(
    previous.materialCode,
    order.materialCode ?? mold.materialCode,
  )
  const sameProduct = equalKnown(previous.productName, order.productName)

  if (sameMold && sameMaterial) return 1
  if (sameMold) return 0.8
  if (sameMaterial && sameProduct) return 0.5
  if (sameMaterial) return 0.3
  if (sameProduct) return 0.2
  return 0
}

function buildReasons(
  deliverySlackHours: number | null,
  previous: InjectionSetupProfile | null,
  mold: InjectionMold,
  setupCost: InjectionSetupCost,
) {
  const reasons: string[] = []

  if (deliverySlackHours != null && deliverySlackHours < 0) {
    reasons.push(`预计超期 ${Math.abs(deliverySlackHours).toFixed(1)} 小时，货期优先`)
  }
  else if (deliverySlackHours != null) {
    reasons.push(`预计交期余量 ${deliverySlackHours.toFixed(1)} 小时`)
  }
  else {
    reasons.push('交期或预计完成时间缺失，货期分仅使用订单优先级')
  }

  if (previous && equalKnown(previous.moldId, mold.id)) {
    reasons.push('与前序任务同模，适合连续生产')
  }
  if (setupCost.totalMinutes === 0) {
    reasons.push('相邻任务无需换模、换料或转色')
  }
  else {
    reasons.push(`预计换型 ${setupCost.totalMinutes} 分钟`)
  }

  return reasons
}

export function scoreInjectionRecommendation({
  machine,
  mold,
  order,
  constraints,
  setupCost,
  config,
  previous,
  referenceAt,
  estimatedStartAt,
  estimatedEndAt,
  machineLoadRatio,
  downstreamUrgencyRatio,
  exactMatch = false,
  splitAcrossMachines = false,
  specialHandling = false,
}: ScoreInjectionRecommendationInput): Recommendation {
  // Parsing the reference time here ensures the scoring input is deterministic
  // and never falls back to Date.now().
  const referenceTimestamp = parseTimestamp(referenceAt)
  if (referenceTimestamp == null) {
    throw new Error('排程评分必须提供有效的版本基准时间 referenceAt')
  }

  const deliverySlackHours = calculateDeliverySlackHours(order, estimatedEndAt)
  const scoring = config.scoring
  const weights = scoring.weights
  const continuityRatio = sequenceContinuityRatio(previous, mold, order)
  const effectiveDownstreamUrgency = clampRatio(
    downstreamUrgencyRatio ?? order.downstreamUrgency,
  )

  const scoreBreakdown: InjectionScoreBreakdown = {
    dueUrgency: roundScore(weights.dueUrgency * dueUrgencyRatio(
      order,
      deliverySlackHours,
      scoring.dueUrgencyHorizonHours,
    )),
    sameMoldMaterial: roundScore(weights.sameMoldMaterial * continuityRatio),
    setupCost: roundScore(inverseCostScore(
      weights.setupCost,
      setupCost.totalMinutes,
      scoring.setupCostCeilingMinutes,
    )),
    colorTransition: roundScore(inverseCostScore(
      weights.colorTransition,
      setupCost.colorChangeMinutes,
      scoring.colorTransitionCeilingMinutes,
    )),
    loadBalance: roundScore(weights.loadBalance * (1 - clampRatio(machineLoadRatio))),
    downstreamImpact: roundScore(weights.downstreamImpact * effectiveDownstreamUrgency),
    exactMatch: exactMatch ? weights.exactMatch : 0,
    splitPenalty: splitAcrossMachines ? weights.splitPenalty : 0,
    specialHandlingPenalty: specialHandling ? weights.specialHandlingPenalty : 0,
  }

  const totalScore = roundScore(
    Object.values(scoreBreakdown).reduce((sum, value) => sum + value, 0),
  )

  return {
    machineId: machine.id,
    factoryId: machine.factoryId,
    rank: null,
    eligible: constraints.eligible,
    autoPublishAllowed: constraints.autoPublishAllowed,
    score: constraints.eligible ? totalScore : null,
    hardConstraints: constraints.results,
    scoreBreakdown,
    setupCost,
    estimatedStartAt,
    estimatedEndAt,
    deliverySlackHours,
    reasons: [
      ...buildReasons(deliverySlackHours, previous, mold, setupCost),
      ...(!constraints.eligible ? constraints.failureReasons : []),
    ],
  }
}
