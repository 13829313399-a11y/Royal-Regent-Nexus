import type {
  ConstraintResult,
  InjectionConstraintCode,
  InjectionConstraintEvaluation,
  InjectionConstraintOverride,
  InjectionMachine,
  InjectionMachineCapability,
  InjectionMaterialRule,
  InjectionMold,
  InjectionOrder,
  InjectionRuleConfig,
} from '@/types/injectionSchedule'

export type InjectionConstraintOverrides = Partial<
  Record<InjectionConstraintCode, InjectionConstraintOverride>
>

export interface EvaluateInjectionConstraintsInput {
  machine: InjectionMachine
  mold: InjectionMold
  order: InjectionOrder
  config: InjectionRuleConfig
  overrides?: InjectionConstraintOverrides
}

interface ConstraintResultInput {
  code: InjectionConstraintCode
  label: string
  status: 'pass' | 'fail' | 'unknown'
  reason: string
  missingFields?: string[]
  actual?: unknown
  expected?: unknown
  override?: InjectionConstraintOverride
  overrideable?: boolean
}

const armCapacity: Record<InjectionMachine['armType'], number> = {
  none: 0,
  single: 1,
  double: 2,
}

const fieldLabels: Record<string, string> = {
  'mold.lengthMm': '模具长度',
  'mold.widthMm': '模具宽度',
  'mold.moldThicknessMm': '模具厚度',
  'mold.requiredOpeningStrokeMm': '模具所需开模行程',
  'machine.tieBarWidthMm': '机台拉杆内距宽度',
  'machine.tieBarHeightMm': '机台拉杆内距高度',
  'machine.minMoldThicknessMm': '机台最小模厚',
  'machine.maxMoldThicknessMm': '机台最大模厚',
  'machine.maxOpeningStrokeMm': '机台最大开模行程',
  'machine.maxShotWeightG': '机台最大射胶量',
  'order/mold.grossShotWeightG': '订单或模具整啤毛重',
  'config.shotSafetyFactor': '厂区射胶安全系数',
}

const armLabels: Record<InjectionMachine['armType'], string> = {
  none: '无机械手',
  single: '单臂',
  double: '双臂',
}

const capabilityLabels: Record<InjectionMachineCapability, string> = {
  core_pull: '抽芯',
  double_core_pull: '两边抽芯',
  deep_nozzle: '深唧嘴',
  high_pressure: '高压',
  two_color: '双色',
  automatic_pull: '自动拉',
  submersible: '潜水工艺',
}

function formatMissingFields(fields: readonly string[]) {
  return fields.map((field) => fieldLabels[field] ?? field).join('、')
}

function normalizeCode(value: string) {
  return value.trim().toLocaleUpperCase('en-US')
}

function uniqueNormalized(values: readonly string[]) {
  return new Set(values.map(normalizeCode).filter(Boolean))
}

function isPositiveFinite(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
}

function makeConstraintResult(input: ConstraintResultInput): ConstraintResult {
  const overrideReason = input.override?.reason.trim() ?? ''
  const canOverride = input.overrideable !== false
    && input.status !== 'pass'
    && Boolean(overrideReason)

  if (canOverride) {
    return {
      code: input.code,
      label: input.label,
      status: 'override',
      blocking: false,
      autoPublishBlocked: true,
      reason: `${input.reason}；人工例外：${overrideReason}`,
      missingFields: input.missingFields ?? [],
      actual: input.actual ?? null,
      expected: input.expected ?? null,
      originalStatus: input.status === 'pass' ? null : input.status,
      override: {
        ...input.override!,
        reason: overrideReason,
      },
    }
  }

  return {
    code: input.code,
    label: input.label,
    status: input.status,
    blocking: input.status !== 'pass',
    autoPublishBlocked: input.status !== 'pass',
    reason: input.reason,
    missingFields: input.missingFields ?? [],
    actual: input.actual ?? null,
    expected: input.expected ?? null,
    originalStatus: null,
    override: null,
  }
}

function evaluateFactory(
  machine: InjectionMachine,
  mold: InjectionMold,
  order: InjectionOrder,
  config: InjectionRuleConfig,
  override?: InjectionConstraintOverride,
) {
  const factoryIds = {
    configured: config.factoryId,
    machine: machine.factoryId,
    mold: mold.factoryId,
    order: order.factoryId,
  }
  const matches = Object.values(factoryIds).every((factoryId) => factoryId === config.factoryId)

  return makeConstraintResult({
    code: 'factory_match',
    label: '厂区一致',
    status: matches ? 'pass' : 'fail',
    reason: matches
      ? `机台、模具和订单均属于厂区 ${config.factoryId}`
      : `禁止跨厂排程：配置、机台、模具和订单的厂区不一致`,
    actual: factoryIds,
    expected: config.factoryId,
    // Cross-factory isolation is an authorization/data boundary, not a
    // schedulable exception.
    override,
    overrideable: false,
  })
}

function evaluateMachineStatus(
  machine: InjectionMachine,
  config: InjectionRuleConfig,
  override?: InjectionConstraintOverride,
) {
  const statusAllowed = config.schedulableMachineStatuses.includes(machine.status)
  const available = statusAllowed && !machine.schedulingLocked

  return makeConstraintResult({
    code: 'machine_status',
    label: '机台状态',
    status: available ? 'pass' : 'fail',
    reason: available
      ? `机台状态 ${machine.status} 可参与排程`
      : machine.schedulingLocked
        ? `机台 ${machine.machineNo} 已锁定，不能排入新任务`
        : `机台状态 ${machine.status} 不可排程`,
    actual: {
      status: machine.status,
      schedulingLocked: machine.schedulingLocked,
    },
    expected: {
      statuses: config.schedulableMachineStatuses,
      schedulingLocked: false,
    },
    override,
  })
}

function evaluateMoldDimensions(
  machine: InjectionMachine,
  mold: InjectionMold,
  override?: InjectionConstraintOverride,
) {
  const fields = {
    'mold.lengthMm': mold.lengthMm,
    'mold.widthMm': mold.widthMm,
    'machine.tieBarWidthMm': machine.tieBarWidthMm,
    'machine.tieBarHeightMm': machine.tieBarHeightMm,
  }
  const missingFields = Object.entries(fields)
    .filter(([, value]) => !isPositiveFinite(value))
    .map(([field]) => field)

  if (missingFields.length) {
    return makeConstraintResult({
      code: 'mold_dimensions',
      label: '模具尺寸',
      status: 'unknown',
      reason: `模具或机台空间资料缺失：${formatMissingFields(missingFields)}`,
      missingFields,
      actual: fields,
      expected: '模具长宽可放入机台拉杆内距',
      override,
    })
  }

  const fitsNormally = mold.lengthMm! <= machine.tieBarWidthMm!
    && mold.widthMm! <= machine.tieBarHeightMm!
  const fitsRotated = mold.widthMm! <= machine.tieBarWidthMm!
    && mold.lengthMm! <= machine.tieBarHeightMm!
  const fits = fitsNormally || fitsRotated

  return makeConstraintResult({
    code: 'mold_dimensions',
    label: '模具尺寸',
    status: fits ? 'pass' : 'fail',
    reason: fits
      ? `模具 ${mold.lengthMm}×${mold.widthMm}mm 可放入拉杆内距 ${machine.tieBarWidthMm}×${machine.tieBarHeightMm}mm`
      : `模具 ${mold.lengthMm}×${mold.widthMm}mm 超出机台拉杆内距 ${machine.tieBarWidthMm}×${machine.tieBarHeightMm}mm`,
    actual: {
      lengthMm: mold.lengthMm,
      widthMm: mold.widthMm,
    },
    expected: {
      tieBarWidthMm: machine.tieBarWidthMm,
      tieBarHeightMm: machine.tieBarHeightMm,
      rotationAllowed: true,
    },
    override,
  })
}

function evaluateMoldThickness(
  machine: InjectionMachine,
  mold: InjectionMold,
  override?: InjectionConstraintOverride,
) {
  const fields = {
    'mold.moldThicknessMm': mold.moldThicknessMm,
    'machine.minMoldThicknessMm': machine.minMoldThicknessMm,
    'machine.maxMoldThicknessMm': machine.maxMoldThicknessMm,
  }
  const missingFields = Object.entries(fields)
    .filter(([, value]) => !isPositiveFinite(value))
    .map(([field]) => field)

  if (missingFields.length) {
    return makeConstraintResult({
      code: 'mold_thickness',
      label: '模厚范围',
      status: 'unknown',
      reason: `模厚资料缺失：${formatMissingFields(missingFields)}`,
      missingFields,
      actual: fields,
      expected: '模厚处于机台允许范围内',
      override,
    })
  }

  const thickness = mold.moldThicknessMm!
  const fits = thickness >= machine.minMoldThicknessMm!
    && thickness <= machine.maxMoldThicknessMm!

  return makeConstraintResult({
    code: 'mold_thickness',
    label: '模厚范围',
    status: fits ? 'pass' : 'fail',
    reason: fits
      ? `模厚 ${thickness}mm 位于机台范围 ${machine.minMoldThicknessMm}–${machine.maxMoldThicknessMm}mm`
      : `模厚 ${thickness}mm 不在机台范围 ${machine.minMoldThicknessMm}–${machine.maxMoldThicknessMm}mm`,
    actual: thickness,
    expected: {
      minimumMm: machine.minMoldThicknessMm,
      maximumMm: machine.maxMoldThicknessMm,
    },
    override,
  })
}

function evaluateOpeningStroke(
  machine: InjectionMachine,
  mold: InjectionMold,
  override?: InjectionConstraintOverride,
) {
  const fields = {
    'mold.requiredOpeningStrokeMm': mold.requiredOpeningStrokeMm,
    'machine.maxOpeningStrokeMm': machine.maxOpeningStrokeMm,
  }
  const missingFields = Object.entries(fields)
    .filter(([, value]) => !isPositiveFinite(value))
    .map(([field]) => field)

  if (missingFields.length) {
    return makeConstraintResult({
      code: 'opening_stroke',
      label: '开模行程',
      status: 'unknown',
      reason: `开模行程资料缺失：${formatMissingFields(missingFields)}`,
      missingFields,
      actual: fields,
      expected: '模具所需开模行程不超过机台上限',
      override,
    })
  }

  const fits = mold.requiredOpeningStrokeMm! <= machine.maxOpeningStrokeMm!
  return makeConstraintResult({
    code: 'opening_stroke',
    label: '开模行程',
    status: fits ? 'pass' : 'fail',
    reason: fits
      ? `所需开模行程 ${mold.requiredOpeningStrokeMm}mm 不超过机台上限 ${machine.maxOpeningStrokeMm}mm`
      : `所需开模行程 ${mold.requiredOpeningStrokeMm}mm 超过机台上限 ${machine.maxOpeningStrokeMm}mm`,
    actual: mold.requiredOpeningStrokeMm,
    expected: machine.maxOpeningStrokeMm,
    override,
  })
}

function evaluateShotCapacity(
  machine: InjectionMachine,
  mold: InjectionMold,
  order: InjectionOrder,
  config: InjectionRuleConfig,
  override?: InjectionConstraintOverride,
) {
  const grossShotWeightG = order.grossShotWeightG ?? mold.grossShotWeightG
  const fields = {
    grossShotWeightG,
    'machine.maxShotWeightG': machine.maxShotWeightG,
    'config.shotSafetyFactor': config.shotSafetyFactor,
  }
  const safetyFactorValid = Number.isFinite(config.shotSafetyFactor)
    && config.shotSafetyFactor > 0
    && config.shotSafetyFactor <= 1
  const missingFields = [
    ...(!isPositiveFinite(grossShotWeightG) ? ['order/mold.grossShotWeightG'] : []),
    ...(!isPositiveFinite(machine.maxShotWeightG) ? ['machine.maxShotWeightG'] : []),
    ...(!safetyFactorValid ? ['config.shotSafetyFactor'] : []),
  ]

  if (missingFields.length) {
    return makeConstraintResult({
      code: 'shot_capacity',
      label: '安全射胶量',
      status: 'unknown',
      reason: `射胶量关键资料缺失或无效：${formatMissingFields(missingFields)}`,
      missingFields,
      actual: fields,
      expected: '整啤毛重与机台最大射胶量均为正数，安全系数在 (0, 1] 内',
      override,
    })
  }

  const safeCapacityG = machine.maxShotWeightG! * config.shotSafetyFactor
  const fits = grossShotWeightG! <= safeCapacityG
  return makeConstraintResult({
    code: 'shot_capacity',
    label: '安全射胶量',
    status: fits ? 'pass' : 'fail',
    reason: fits
      ? `整啤毛重 ${grossShotWeightG}g 不超过安全射胶量 ${safeCapacityG.toFixed(1)}g`
      : `整啤毛重 ${grossShotWeightG}g 超过安全射胶量 ${safeCapacityG.toFixed(1)}g`,
    actual: grossShotWeightG,
    expected: {
      maximumG: safeCapacityG,
      machineMaximumG: machine.maxShotWeightG,
      safetyFactor: config.shotSafetyFactor,
    },
    override,
  })
}

function evaluateArmType(
  machine: InjectionMachine,
  mold: InjectionMold,
  order: InjectionOrder,
  override?: InjectionConstraintOverride,
) {
  const requirement = order.armRequirement ?? mold.armRequirement
  const fits = armCapacity[machine.armType] >= armCapacity[requirement]

  return makeConstraintResult({
    code: 'arm_type',
    label: '机械手单双臂',
    status: fits ? 'pass' : 'fail',
    reason: fits
      ? `机台${armLabels[machine.armType]}能力满足${armLabels[requirement]}要求`
      : `订单要求${armLabels[requirement]}，机台仅支持${armLabels[machine.armType]}`,
    actual: machine.armType,
    expected: requirement,
    override,
  })
}

function evaluateFixtures(
  machine: InjectionMachine,
  mold: InjectionMold,
  order: InjectionOrder,
  override?: InjectionConstraintOverride,
) {
  const required = uniqueNormalized([
    ...mold.fixtureRequirements,
    ...order.fixtureRequirements,
  ])

  if (!required.size) {
    return makeConstraintResult({
      code: 'fixtures',
      label: '夹具与辅具',
      status: 'pass',
      reason: '订单和模具没有额外夹具、吸盘或气剪要求',
      actual: machine.supportedFixtures,
      expected: [],
      override,
    })
  }

  if (machine.supportedFixtures == null) {
    return makeConstraintResult({
      code: 'fixtures',
      label: '夹具与辅具',
      status: 'unknown',
      reason: '机台夹具、吸盘和气剪能力资料缺失',
      missingFields: ['machine.supportedFixtures'],
      actual: null,
      expected: [...required],
      override,
    })
  }

  const supported = uniqueNormalized(machine.supportedFixtures)
  const missing = [...required].filter((fixture) => !supported.has(fixture))
  return makeConstraintResult({
    code: 'fixtures',
    label: '夹具与辅具',
    status: missing.length ? 'fail' : 'pass',
    reason: missing.length
      ? `机台缺少必需夹具/辅具：${missing.join('、')}`
      : '机台夹具、吸盘和气剪能力满足要求',
    actual: machine.supportedFixtures,
    expected: [...required],
    override,
  })
}

function evaluateCapabilities(
  machine: InjectionMachine,
  mold: InjectionMold,
  order: InjectionOrder,
  override?: InjectionConstraintOverride,
) {
  const required = new Set<InjectionMachineCapability>([
    ...mold.capabilitiesRequired,
    ...order.capabilitiesRequired,
  ])

  if (!required.size) {
    return makeConstraintResult({
      code: 'capabilities',
      label: '工艺能力',
      status: 'pass',
      reason: '订单和模具没有额外工艺能力要求',
      actual: machine.capabilities,
      expected: [],
      override,
    })
  }

  if (machine.capabilities == null) {
    return makeConstraintResult({
      code: 'capabilities',
      label: '工艺能力',
      status: 'unknown',
      reason: '机台抽芯、唧嘴、压力等工艺能力资料缺失',
      missingFields: ['machine.capabilities'],
      actual: null,
      expected: [...required],
      override,
    })
  }

  const supported = new Set(machine.capabilities)
  const missing = [...required].filter((capability) => !supported.has(capability))
  return makeConstraintResult({
    code: 'capabilities',
    label: '工艺能力',
    status: missing.length ? 'fail' : 'pass',
    reason: missing.length
      ? `机台缺少必需工艺能力：${missing.map((capability) => capabilityLabels[capability]).join('、')}`
      : '机台工艺能力满足要求',
    actual: machine.capabilities,
    expected: [...required],
    override,
  })
}

function materialMatches(materialCode: string, candidates: readonly string[]) {
  const normalizedMaterial = normalizeCode(materialCode)
  return candidates.some((candidate) => {
    const normalizedCandidate = normalizeCode(candidate)
    return normalizedMaterial === normalizedCandidate
      || normalizedMaterial.startsWith(`${normalizedCandidate}-`)
      || normalizedMaterial.startsWith(`${normalizedCandidate} `)
  })
}

function findMaterialConflict(
  materialCode: string,
  machine: InjectionMachine,
  mold: InjectionMold,
): { status: 'fail' | 'unknown'; reason: string; rule: InjectionMaterialRule | null } | null {
  const requiredScrewTypes = uniqueNormalized(mold.requiredScrewTypes)
  if (requiredScrewTypes.size) {
    if (!machine.screwType) {
      return {
        status: 'unknown',
        reason: `模具要求螺杆 ${[...requiredScrewTypes].join('、')}，但机台螺杆资料缺失`,
        rule: null,
      }
    }
    if (!requiredScrewTypes.has(normalizeCode(machine.screwType))) {
      return {
        status: 'fail',
        reason: `机台螺杆 ${machine.screwType} 不满足模具要求 ${[...requiredScrewTypes].join('、')}`,
        rule: null,
      }
    }
  }

  for (const rule of machine.materialRules ?? []) {
    const matches = materialMatches(materialCode, rule.materialCodes)
    if (rule.mode === 'deny' && matches) {
      return { status: 'fail', reason: rule.reason || `机台禁止材料 ${materialCode}`, rule }
    }
    if (rule.mode === 'allow_only' && !matches) {
      return {
        status: 'fail',
        reason: rule.reason || `机台只允许 ${rule.materialCodes.join('、')}`,
        rule,
      }
    }
    if (rule.mode === 'requires_screw' && matches) {
      if (!machine.screwType) {
        return {
          status: 'unknown',
          reason: `材料 ${materialCode} 需要指定螺杆，但机台螺杆资料缺失`,
          rule,
        }
      }
      if (!uniqueNormalized(rule.allowedScrewTypes).has(normalizeCode(machine.screwType))) {
        return {
          status: 'fail',
          reason: rule.reason || `材料 ${materialCode} 不兼容机台螺杆 ${machine.screwType}`,
          rule,
        }
      }
    }
  }

  return null
}

function evaluateMaterialRestrictions(
  machine: InjectionMachine,
  mold: InjectionMold,
  order: InjectionOrder,
  override?: InjectionConstraintOverride,
) {
  const materialCode = order.materialCode ?? mold.materialCode

  if (machine.materialRules == null) {
    return makeConstraintResult({
      code: 'material_restrictions',
      label: '材料与螺杆限制',
      status: 'unknown',
      reason: '机台材料限制资料尚未确认',
      missingFields: ['machine.materialRules'],
      actual: null,
      expected: materialCode,
      override,
    })
  }

  if (!materialCode) {
    return makeConstraintResult({
      code: 'material_restrictions',
      label: '材料与螺杆限制',
      status: 'unknown',
      reason: '订单和模具均缺少材料代码，无法校验 PVC、PC 或螺杆限制',
      missingFields: ['order/mold.materialCode'],
      actual: null,
      expected: machine.materialRules,
      override,
    })
  }

  const conflict = findMaterialConflict(materialCode, machine, mold)
  return makeConstraintResult({
    code: 'material_restrictions',
    label: '材料与螺杆限制',
    status: conflict?.status ?? 'pass',
    reason: conflict?.reason ?? `材料 ${materialCode} 与机台材料/螺杆限制兼容`,
    missingFields: conflict?.status === 'unknown' ? ['machine.screwType'] : [],
    actual: {
      materialCode,
      screwType: machine.screwType,
    },
    expected: conflict?.rule ?? machine.materialRules,
    override,
  })
}

export function evaluateInjectionConstraints({
  machine,
  mold,
  order,
  config,
  overrides = {},
}: EvaluateInjectionConstraintsInput): InjectionConstraintEvaluation {
  const results = [
    evaluateFactory(machine, mold, order, config, overrides.factory_match),
    evaluateMachineStatus(machine, config, overrides.machine_status),
    evaluateMoldDimensions(machine, mold, overrides.mold_dimensions),
    evaluateMoldThickness(machine, mold, overrides.mold_thickness),
    evaluateOpeningStroke(machine, mold, overrides.opening_stroke),
    evaluateShotCapacity(machine, mold, order, config, overrides.shot_capacity),
    evaluateArmType(machine, mold, order, overrides.arm_type),
    evaluateFixtures(machine, mold, order, overrides.fixtures),
    evaluateCapabilities(machine, mold, order, overrides.capabilities),
    evaluateMaterialRestrictions(machine, mold, order, overrides.material_restrictions),
  ]

  return {
    results,
    eligible: results.every((result) => !result.blocking),
    autoPublishAllowed: results.every((result) => !result.autoPublishBlocked),
    hasUnknownData: results.some((result) =>
      result.status === 'unknown'
      || (result.status === 'override' && result.originalStatus === 'unknown')),
    failureReasons: results
      .filter((result) => result.status === 'fail' || result.status === 'unknown')
      .map((result) => result.reason),
  }
}

export function canAutoPublishFromConstraints(results: readonly ConstraintResult[]) {
  return results.length > 0 && results.every((result) => !result.autoPublishBlocked)
}
