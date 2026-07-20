import type { ProductionFactoryContextId } from '../data/enterpriseMock.js'
import type { MoldingSampleOrder } from '../types/moldingSample.js'

export type MoldingSampleProductionFactoryId = ProductionFactoryContextId
export type MoldingSampleDispatchMode = 'self-only' | 'cross-factory'

export interface MoldingSampleFactoryCapability {
  factoryId: ProductionFactoryContextId
  label: string
  hasMoldingDepartment: boolean
  dispatchMode: MoldingSampleDispatchMode
  allowedProductionFactoryIds: readonly ProductionFactoryContextId[]
  suggestedProductionFactoryId: ProductionFactoryContextId
}

export interface MoldingSampleProductionAssignmentValidation {
  valid: boolean
  productionFactoryId: ProductionFactoryContextId | null
  error: string
}

const huakangProductionFactoryIds = ['huakang-a', 'huakang-b'] as const

export const moldingSampleFactoryCapabilities = {
  'huakang-a': {
    factoryId: 'huakang-a',
    label: '华康A',
    hasMoldingDepartment: true,
    dispatchMode: 'self-only',
    allowedProductionFactoryIds: ['huakang-a'],
    suggestedProductionFactoryId: 'huakang-a',
  },
  'huakang-b': {
    factoryId: 'huakang-b',
    label: '华康B',
    hasMoldingDepartment: true,
    dispatchMode: 'self-only',
    allowedProductionFactoryIds: ['huakang-b'],
    suggestedProductionFactoryId: 'huakang-b',
  },
  'huakang-c': {
    factoryId: 'huakang-c',
    label: '华康C',
    hasMoldingDepartment: false,
    dispatchMode: 'cross-factory',
    allowedProductionFactoryIds: huakangProductionFactoryIds,
    suggestedProductionFactoryId: 'huakang-a',
  },
  'huakang-d': {
    factoryId: 'huakang-d',
    label: '华康D',
    hasMoldingDepartment: false,
    dispatchMode: 'cross-factory',
    allowedProductionFactoryIds: huakangProductionFactoryIds,
    suggestedProductionFactoryId: 'huakang-b',
  },
  huadeng: {
    factoryId: 'huadeng',
    label: '华登',
    hasMoldingDepartment: true,
    dispatchMode: 'self-only',
    allowedProductionFactoryIds: ['huadeng'],
    suggestedProductionFactoryId: 'huadeng',
  },
  huaxing: {
    factoryId: 'huaxing',
    label: '华兴',
    hasMoldingDepartment: true,
    dispatchMode: 'self-only',
    allowedProductionFactoryIds: ['huaxing'],
    suggestedProductionFactoryId: 'huaxing',
  },
} as const satisfies Record<ProductionFactoryContextId, MoldingSampleFactoryCapability>

export function isMoldingSampleFactoryId(factoryId: string): factoryId is ProductionFactoryContextId {
  return Object.prototype.hasOwnProperty.call(moldingSampleFactoryCapabilities, factoryId)
}

export function getMoldingSampleFactoryCapability(factoryId: string) {
  return isMoldingSampleFactoryId(factoryId)
    ? moldingSampleFactoryCapabilities[factoryId]
    : null
}

export function getMoldingSampleFactoryLabel(factoryId: string | null | undefined) {
  const normalizedFactoryId = factoryId?.trim() ?? ''
  if (!normalizedFactoryId) {
    return '待派厂'
  }

  return getMoldingSampleFactoryCapability(normalizedFactoryId)?.label ?? normalizedFactoryId
}

export function getAllowedMoldingSampleProductionFactoryIds(factoryId: string) {
  return getMoldingSampleFactoryCapability(factoryId)?.allowedProductionFactoryIds ?? []
}

export function getSuggestedMoldingSampleProductionFactoryId(factoryId: string) {
  return getMoldingSampleFactoryCapability(factoryId)?.suggestedProductionFactoryId ?? null
}

export function validateMoldingSampleProductionAssignment(
  sourceFactoryId: string,
  productionFactoryId: string | null | undefined,
): MoldingSampleProductionAssignmentValidation {
  const normalizedSourceFactoryId = sourceFactoryId.trim()
  const normalizedProductionFactoryId = productionFactoryId?.trim() ?? ''
  const capability = getMoldingSampleFactoryCapability(normalizedSourceFactoryId)

  if (!capability) {
    return {
      valid: false,
      productionFactoryId: null,
      error: `未知开单厂：${normalizedSourceFactoryId || '未指定'}`,
    }
  }

  if (!normalizedProductionFactoryId) {
    if (capability.hasMoldingDepartment) {
      return {
        valid: true,
        productionFactoryId: capability.factoryId,
        error: '',
      }
    }

    return {
      valid: false,
      productionFactoryId: null,
      error: '华康C/D啤办单必须选择华康A或华康B承接生产',
    }
  }

  if (!isMoldingSampleFactoryId(normalizedProductionFactoryId)
    || !capability.allowedProductionFactoryIds.some((factoryId) => factoryId === normalizedProductionFactoryId)) {
    return {
      valid: false,
      productionFactoryId: null,
      error: `${capability.label}啤办单只能由${capability.allowedProductionFactoryIds
        .map((factoryId) => getMoldingSampleFactoryLabel(factoryId))
        .join('、')}承接生产`,
    }
  }

  return {
    valid: true,
    productionFactoryId: normalizedProductionFactoryId,
    error: '',
  }
}

type MoldingSampleFactoryAssignmentOrder = Pick<
  MoldingSampleOrder,
  'factory_id' | 'production_factory_id'
> & Partial<Pick<MoldingSampleOrder, 'send_to' | 'workshop'>>

export function resolveMoldingSampleProductionFactoryId(
  order: MoldingSampleFactoryAssignmentOrder,
): string | null {
  if (order.send_to === '发至湖南'
    || order.send_to === '发至模厂'
    || order.workshop === '模厂') {
    return null
  }

  const assignedFactoryId = order.production_factory_id?.trim()
  if (assignedFactoryId) {
    return assignedFactoryId
  }

  const capability = getMoldingSampleFactoryCapability(order.factory_id.trim())
  return capability?.hasMoldingDepartment ? capability.factoryId : null
}
