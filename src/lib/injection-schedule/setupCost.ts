import type {
  InjectionSetupCost,
  InjectionSetupOverride,
  InjectionSetupProfile,
  InjectionSetupRuleConfig,
} from '@/types/injectionSchedule'

export interface CalculateInjectionSetupCostInput {
  previous: InjectionSetupProfile | null
  next: InjectionSetupProfile
  config: InjectionSetupRuleConfig
  colorOverride?: InjectionSetupOverride
}

function normalizeCode(value: string | null) {
  return value?.trim().toLocaleUpperCase('en-US') ?? ''
}

function safeMinutes(value: number) {
  return Number.isFinite(value) && value >= 0 ? value : 0
}

function sameValue(left: string | null, right: string | null) {
  const normalizedLeft = normalizeCode(left)
  const normalizedRight = normalizeCode(right)
  return Boolean(normalizedLeft) && normalizedLeft === normalizedRight
}

function resolveMaterialMinutes(
  previous: InjectionSetupProfile,
  next: InjectionSetupProfile,
  config: InjectionSetupRuleConfig,
) {
  if (sameValue(previous.materialCode, next.materialCode)) {
    return {
      minutes: safeMinutes(config.sameMaterialChangeMinutes),
      sameMaterial: true,
      qualityFlag: null,
      reason: '同材料连续生产，无需换料或洗机',
    }
  }

  const previousCode = normalizeCode(previous.materialCode)
  const nextCode = normalizeCode(next.materialCode)
  if (previousCode && nextCode) {
    const matrixRule = config.materialTransitionMatrix.find((rule) =>
      normalizeCode(rule.fromMaterialCode) === previousCode
      && normalizeCode(rule.toMaterialCode) === nextCode)
    if (matrixRule) {
      return {
        minutes: safeMinutes(matrixRule.minutes),
        sameMaterial: false,
        qualityFlag: null,
        reason: `材料 ${previous.materialCode} → ${next.materialCode} 按厂区矩阵换料`,
      }
    }
  }

  return {
    minutes: safeMinutes(config.differentMaterialChangeMinutes),
    sameMaterial: false,
    qualityFlag: previousCode && nextCode ? null : 'material_code_missing',
    reason: previousCode && nextCode
      ? `材料 ${previous.materialCode} → ${next.materialCode} 使用默认换料时间`
      : '相邻任务材料代码缺失，使用默认换料时间',
  }
}

function resolveColorMinutes(
  previous: InjectionSetupProfile,
  next: InjectionSetupProfile,
  config: InjectionSetupRuleConfig,
  override?: InjectionSetupOverride,
) {
  if (override) {
    const reason = override.reason.trim()
    if (!reason) {
      throw new Error('颜色转换人工例外必须填写原因')
    }
    if (!Number.isFinite(override.colorTransitionMinutes) || override.colorTransitionMinutes < 0) {
      throw new RangeError('颜色转换人工例外分钟数必须是非负有限数值')
    }
    return {
      minutes: override.colorTransitionMinutes,
      direction: 'matrix' as const,
      qualityFlag: null,
      reason: `颜色转换使用人工例外：${reason}`,
      override: { ...override, reason },
    }
  }

  if (sameValue(previous.colorCode, next.colorCode)) {
    return {
      minutes: safeMinutes(config.sameColorChangeMinutes),
      direction: 'same' as const,
      qualityFlag: null,
      reason: '同色连续生产，无需转色',
      override: null,
    }
  }

  const previousCode = normalizeCode(previous.colorCode)
  const nextCode = normalizeCode(next.colorCode)
  if (previousCode && nextCode) {
    const matrixRule = config.colorTransitionMatrix.find((rule) =>
      normalizeCode(rule.fromColorCode) === previousCode
      && normalizeCode(rule.toColorCode) === nextCode)
    if (matrixRule) {
      return {
        minutes: safeMinutes(matrixRule.minutes),
        direction: 'matrix' as const,
        qualityFlag: null,
        reason: `颜色 ${previous.colorCode} → ${next.colorCode} 按厂区矩阵转色`,
        override: null,
      }
    }
  }

  const previousRank = previous.colorRank
  const nextRank = next.colorRank
  if (
    typeof previousRank === 'number'
    && Number.isFinite(previousRank)
    && typeof nextRank === 'number'
    && Number.isFinite(nextRank)
  ) {
    const lightToDark = previousRank <= nextRank
    return {
      minutes: safeMinutes(lightToDark
        ? config.lightToDarkColorMinutes
        : config.darkToLightColorMinutes),
      direction: lightToDark ? 'light_to_dark' as const : 'dark_to_light' as const,
      qualityFlag: null,
      reason: lightToDark
        ? `颜色等级 ${previousRank} → ${nextRank}，按浅色到深色转换`
        : `颜色等级 ${previousRank} → ${nextRank}，按深色到浅色洗机转换`,
      override: null,
    }
  }

  return {
    minutes: safeMinutes(config.unknownColorTransitionMinutes),
    direction: 'unknown' as const,
    qualityFlag: 'color_transition_data_missing',
    reason: '颜色代码或颜色等级缺失，使用未知颜色转换时间',
    override: null,
  }
}

export function calculateInjectionSetupCost({
  previous,
  next,
  config,
  colorOverride,
}: CalculateInjectionSetupCostInput): InjectionSetupCost {
  if (!previous) {
    const firstTaskSetupMinutes = safeMinutes(config.firstTaskSetupMinutes)
    return {
      totalMinutes: firstTaskSetupMinutes,
      moldChangeMinutes: firstTaskSetupMinutes,
      materialChangeMinutes: 0,
      colorChangeMinutes: 0,
      sameMold: false,
      sameMaterial: false,
      colorDirection: 'unknown',
      reasons: ['机台首个任务使用首件装模准备时间'],
      dataQualityFlags: [],
      colorOverride: null,
    }
  }

  const sameMold = sameValue(previous.moldId, next.moldId)
  const moldChangeMinutes = safeMinutes(sameMold
    ? config.sameMoldChangeMinutes
    : config.differentMoldChangeMinutes)
  const material = resolveMaterialMinutes(previous, next, config)
  const color = resolveColorMinutes(previous, next, config, colorOverride)
  const dataQualityFlags = [
    ...(!normalizeCode(previous.moldId) || !normalizeCode(next.moldId)
      ? ['mold_id_missing']
      : []),
    ...(material.qualityFlag ? [material.qualityFlag] : []),
    ...(color.qualityFlag ? [color.qualityFlag] : []),
  ]
  const reasons = [
    sameMold
      ? '同模相邻任务，换模成本按同模规则降低'
      : '模具不同，使用标准换模时间',
    material.reason,
    color.reason,
  ]

  return {
    totalMinutes: moldChangeMinutes + material.minutes + color.minutes,
    moldChangeMinutes,
    materialChangeMinutes: material.minutes,
    colorChangeMinutes: color.minutes,
    sameMold,
    sameMaterial: material.sameMaterial,
    colorDirection: color.direction,
    reasons,
    dataQualityFlags: [...new Set(dataQualityFlags)],
    colorOverride: color.override,
  }
}
