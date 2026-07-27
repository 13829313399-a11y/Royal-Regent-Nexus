import { describe, expect, it } from 'vitest'
import {
  factoryContexts,
  getFactoryScopedRoute,
  getMoldingSampleRecord as getEnterpriseMoldingSampleRecord,
  moldingSampleFactoryRecords as enterpriseMoldingSampleFactoryRecords,
  productionFactoryContextIds,
} from '@/data/enterpriseMock'
import {
  getMoldingSampleRecord as getWorkflowMoldingSampleRecord,
  moldingSampleFactoryRecords as workflowMoldingSampleFactoryRecords,
} from '@/data/moldingSampleWorkflowMock'

type EnterpriseMoldingRecord = {
  factoryId: string
  order: Record<string, unknown>
  lines: unknown[]
}

type WorkflowMoldingRecord = {
  factory_id: string
  order: { factory_id: string }
  items: unknown[]
}

const expectedPhysicalFactoryIds = [
  'huakang-a',
  'huakang-b',
  'huakang-c',
  'huakang-d',
  'huadeng',
  'huaxing',
]

const newFactoryNames = {
  'huakang-c': '华康C',
  'huakang-d': '华康D',
} as const

function sortedKeys(value: object) {
  return Object.keys(value).sort()
}

describe('enterprise factory registry scope', () => {
  it.each(['huakang-c', 'huakang-d'] as const)(
    'adds %s to internal routes while preserving existing query state',
    (factoryId) => {
      expect(getFactoryScopedRoute('/modules/engineering', factoryId)).toBe(
        `/modules/engineering?factory=${factoryId}`,
      )
      expect(getFactoryScopedRoute('/modules/internal?section=sales', factoryId)).toBe(
        `/modules/internal?section=sales&factory=${factoryId}`,
      )
    },
  )

  it('registers every non-group factory in each production data registry', () => {
    expect(factoryContexts.filter(({ id }) => id !== 'group').map(({ id }) => id)).toEqual(
      expectedPhysicalFactoryIds,
    )
    expect([...productionFactoryContextIds]).toEqual(expectedPhysicalFactoryIds)

    for (const registry of [
      enterpriseMoldingSampleFactoryRecords,
      workflowMoldingSampleFactoryRecords,
    ]) {
      expect(sortedKeys(registry)).toEqual([...expectedPhysicalFactoryIds].sort())
    }
  })

  it.each(Object.entries(newFactoryNames))(
    'keeps %s enterprise and molding data independent',
    (factoryId, factoryName) => {
      const enterpriseRegistry = enterpriseMoldingSampleFactoryRecords as unknown as Record<string, EnterpriseMoldingRecord>
      const workflowRegistry = workflowMoldingSampleFactoryRecords as unknown as Record<string, WorkflowMoldingRecord>
      const enterpriseRecord = enterpriseRegistry[factoryId]
      const workflowRecord = workflowRegistry[factoryId]

      expect(enterpriseRecord).toBeDefined()
      expect(enterpriseRecord.factoryId).toBe(factoryId)
      expect(enterpriseRecord).toBe(getEnterpriseMoldingSampleRecord(factoryId))
      expect(enterpriseRecord).not.toBe(enterpriseRegistry.huaxing)
      expect(enterpriseRecord.order).not.toBe(enterpriseRegistry.huaxing.order)
      expect(enterpriseRecord.lines).not.toBe(enterpriseRegistry.huaxing.lines)
      expect(JSON.stringify(enterpriseRecord)).toContain(factoryName)
      expect(JSON.stringify(enterpriseRecord)).not.toContain('华兴')

      expect(workflowRecord).toBeDefined()
      expect(workflowRecord.factory_id).toBe(factoryId)
      expect(workflowRecord.order.factory_id).toBe(factoryId)
      expect(workflowRecord).toBe(getWorkflowMoldingSampleRecord(factoryId))
      expect(workflowRecord).not.toBe(workflowRegistry.huaxing)
      expect(workflowRecord.order).not.toBe(workflowRegistry.huaxing.order)
      expect(workflowRecord.items).not.toBe(workflowRegistry.huaxing.items)
      expect(JSON.stringify(workflowRecord)).toContain(factoryName)
      expect(JSON.stringify(workflowRecord)).not.toContain('华兴')

    },
  )

  it('does not share the Huakang C and D registry objects with each other', () => {
    const registries = [
      enterpriseMoldingSampleFactoryRecords,
      workflowMoldingSampleFactoryRecords,
    ] as Array<Record<string, unknown>>

    for (const registry of registries) {
      expect(registry['huakang-c']).not.toBe(registry['huakang-d'])
    }
  })
})
