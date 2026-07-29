import type {
  EligibilityCheck,
  EligibilityResult,
  InjectionMachine,
  OrderRequirement,
  RobotArmType,
} from '@/types/injectionScheduling'

const armRank: Record<RobotArmType, number> = {
  none: 0,
  'single-arm': 1,
  'multi-arm': 2,
}

interface EligibilityInput {
  machine: InjectionMachine
  requirement: OrderRequirement
}

function missingCheck(code: string, label: string, reason: string): EligibilityCheck {
  return { code, label, passed: false, severity: 'warning', reason }
}

export function evaluateMachineEligibility({ machine, requirement }: EligibilityInput): EligibilityResult {
  const mold = requirement.mold
  const capability = machine.capability
  const checks: EligibilityCheck[] = []
  const capabilityIncomplete = machine.resourceState === 'warning'

  if (
    mold.widthMm == null
    || mold.heightMm == null
    || capability.tieBarWidthMm <= 0
    || capability.tieBarHeightMm <= 0
  ) {
    checks.push(missingCheck('mold-dimensions', '模具长宽', '模具或机台缺少长宽参数，需人工复核拉杆内距。'))
  } else {
    const passed = mold.widthMm <= capability.tieBarWidthMm && mold.heightMm <= capability.tieBarHeightMm
    checks.push({
      code: 'mold-dimensions',
      label: '模具长宽',
      passed,
      severity: 'hard',
      expected: `≤ ${capability.tieBarWidthMm}×${capability.tieBarHeightMm}mm`,
      actual: `${mold.widthMm}×${mold.heightMm}mm`,
      reason: passed ? '模具尺寸在机台有效范围内。' : '模具尺寸超过拉杆内距或模板有效范围。',
    })
  }

  if (
    mold.thicknessMm == null
    || capability.minMoldThicknessMm <= 0
    || capability.maxMoldThicknessMm <= 0
  ) {
    checks.push(missingCheck('mold-thickness', '模具厚度', '模具或机台缺少模厚参数，需人工复核容模范围。'))
  } else {
    const passed = mold.thicknessMm >= capability.minMoldThicknessMm
      && mold.thicknessMm <= capability.maxMoldThicknessMm
    checks.push({
      code: 'mold-thickness',
      label: '容模厚度',
      passed,
      severity: 'hard',
      expected: `${capability.minMoldThicknessMm}–${capability.maxMoldThicknessMm}mm`,
      actual: `${mold.thicknessMm}mm`,
      reason: passed ? '模厚在机台容模范围内。' : '模厚超出机台容模范围。',
    })
  }

  for (const [code, label, required, available] of [
    ['opening-stroke', '开模行程', mold.openingStrokeMm, capability.openingStrokeMm],
    ['ejection-stroke', '顶出行程', mold.ejectionStrokeMm, capability.ejectionStrokeMm],
  ] as const) {
    if (required == null || available <= 0) {
      checks.push(missingCheck(code, label, `缺少${label}需求或机台能力，需工艺补录。`))
    } else {
      const passed = required <= available
      checks.push({
        code,
        label,
        passed,
        severity: 'hard',
        expected: `≤ ${available}mm`,
        actual: `${required}mm`,
        reason: passed ? `${label}满足。` : `${label}需求超过机台能力。`,
      })
    }
  }

  if (mold.shotWeightGrams == null || capability.shotCapacityGrams <= 0) {
    checks.push(missingCheck('shot-capacity', '整啤毛重', '缺少整啤毛重或机台射胶能力，需人工复核。'))
  } else {
    const effectiveCapacity = capability.shotCapacityGrams * capability.safetyUtilization
    const materialFactor = ['PC', 'PMMA'].some((material) => requirement.material.toUpperCase().includes(material))
      ? 1.08
      : 1
    const required = mold.shotWeightGrams * materialFactor
    const passed = required <= effectiveCapacity
    checks.push({
      code: 'shot-capacity',
      label: '有效射胶量',
      passed,
      severity: 'hard',
      expected: `≤ ${effectiveCapacity.toFixed(0)}g`,
      actual: `${required.toFixed(0)}g`,
      reason: passed ? '整啤毛重在安全利用率范围内。' : '整啤毛重超过机台有效射胶能力。',
    })
  }

  const armRequirement = mold.armRequirement ?? 'none'
  if (capabilityIncomplete && capability.armType === 'none') {
    checks.push(missingCheck('robot-arm', '机械手', '机台机械手能力未完整录入，需人工复核。'))
  } else {
    checks.push({
      code: 'robot-arm',
      label: '机械手',
      passed: armRank[capability.armType] >= armRank[armRequirement],
      severity: 'hard',
      expected: armRequirement,
      actual: capability.armType,
      reason: armRank[capability.armType] >= armRank[armRequirement]
        ? '机械手能力满足取件需求。'
        : '产品要求多臂/双臂机械手，当前机台能力不足。',
    })
  }

  if (capabilityIncomplete && (mold.requiresCorePull || mold.requiresUnscrewing)) {
    checks.push(missingCheck('special-process', '抽芯 / 绞牙能力', '机台特殊工艺能力未完整录入，需人工复核。'))
  } else {
    checks.push({
      code: 'core-pull',
      label: '抽芯能力',
      passed: !mold.requiresCorePull || capability.supportsCorePull,
      severity: 'hard',
      reason: !mold.requiresCorePull || capability.supportsCorePull ? '抽芯能力满足。' : '模具需要抽芯，但机台不可抽芯。',
    })
    checks.push({
      code: 'unscrewing',
      label: '绞牙能力',
      passed: !mold.requiresUnscrewing || capability.supportsUnscrewing,
      severity: 'hard',
      reason: !mold.requiresUnscrewing || capability.supportsUnscrewing ? '绞牙能力满足。' : '模具需要绞牙，但机台未配置。',
    })
  }

  const normalizedMaterial = requirement.material.toUpperCase()
  if (!capability.compatibleMaterials.length) {
    checks.push(missingCheck('material-screw', '材料与螺杆', '机台材料兼容清单未录入，需人工复核。'))
  } else {
    const materialPassed = capability.compatibleMaterials.some(
      (material) => normalizedMaterial.includes(material.toUpperCase()),
    )
    checks.push({
      code: 'material-screw',
      label: '材料与螺杆',
      passed: materialPassed,
      severity: 'hard',
      expected: capability.compatibleMaterials.join(' / '),
      actual: requirement.material,
      reason: materialPassed ? '材料与螺杆配置兼容。' : '材料不在该机台螺杆兼容清单中。',
    })
  }

  const transparentPassed = !capability.transparentOnly || requirement.colorFamily === 'natural'
  checks.push({
    code: 'transparent-only',
    label: '透明专机',
    passed: transparentPassed,
    severity: 'hard',
    reason: transparentPassed ? '颜色符合专机限制。' : '该机台只允许透明/本色任务。',
  })

  const resourcePassed = machine.resourceState !== 'blocked' && mold.state !== 'blocked'
  checks.push({
    code: 'resource-state',
    label: '机台与模具状态',
    passed: resourcePassed,
    severity: 'hard',
    actual: `机台 ${machine.resourceState} / 模具 ${mold.state}`,
    reason: resourcePassed ? '机台与模具可用于排程。' : '机台或模具处于停机、机故、模故状态。',
  })

  const complete = !checks.some((check) => check.severity === 'warning' && !check.passed)
  const hardPassed = !checks.some((check) => check.severity === 'hard' && !check.passed)
  return {
    eligible: complete && hardPassed,
    complete,
    status: !complete ? 'incomplete' : hardPassed ? 'eligible' : 'ineligible',
    checks,
  }
}
