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
import {
  getInjectionFactoryConfig,
  injectionFactoryRegistry,
} from '@/factories/injection/registry'
import {
  getInjectionFactoryData,
  injectionFactoryDataRegistry,
} from '@/factories/injection/dataRegistry'

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

type InjectionConfigRecord = {
  factoryId: string
  moduleTitle: string
  workspaceSummary: string
}

type InjectionDataRecord = {
  overviewMetrics: Array<{ detail: string }>
  dataSourceStatus: Array<{ summary: string }>
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
      injectionFactoryRegistry,
      injectionFactoryDataRegistry,
    ]) {
      expect(sortedKeys(registry)).toEqual([...expectedPhysicalFactoryIds].sort())
    }
  })

  it.each(Object.entries(newFactoryNames))(
    'keeps %s enterprise, molding and injection data independent',
    (factoryId, factoryName) => {
      const enterpriseRegistry = enterpriseMoldingSampleFactoryRecords as unknown as Record<string, EnterpriseMoldingRecord>
      const workflowRegistry = workflowMoldingSampleFactoryRecords as unknown as Record<string, WorkflowMoldingRecord>
      const injectionConfigRegistry = injectionFactoryRegistry as unknown as Record<string, InjectionConfigRecord>
      const injectionDataRegistry = injectionFactoryDataRegistry as unknown as Record<string, InjectionDataRecord>

      const enterpriseRecord = enterpriseRegistry[factoryId]
      const workflowRecord = workflowRegistry[factoryId]
      const injectionConfig = injectionConfigRegistry[factoryId]
      const injectionData = injectionDataRegistry[factoryId]

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

      expect(injectionConfig).toBeDefined()
      expect(injectionConfig.factoryId).toBe(factoryId)
      expect(injectionConfig).toBe(getInjectionFactoryConfig(factoryId as never))
      expect(injectionConfig).not.toBe(injectionConfigRegistry.huaxing)
      expect(`${injectionConfig.moduleTitle} ${injectionConfig.workspaceSummary}`).toContain(factoryName)
      expect(`${injectionConfig.moduleTitle} ${injectionConfig.workspaceSummary}`).not.toContain('华兴')

      expect(injectionData).toBeDefined()
      expect(injectionData).toBe(getInjectionFactoryData(factoryId as never))
      expect(injectionData).not.toBe(injectionDataRegistry.huaxing)
      expect(injectionData.overviewMetrics).not.toBe(injectionDataRegistry.huaxing.overviewMetrics)
      expect(injectionData.dataSourceStatus).not.toBe(injectionDataRegistry.huaxing.dataSourceStatus)
      expect(JSON.stringify(injectionData)).toContain(factoryName)
      expect(JSON.stringify(injectionData)).not.toContain('华兴')
    },
  )

  it('does not share the Huakang C and D registry objects with each other', () => {
    const registries = [
      enterpriseMoldingSampleFactoryRecords,
      workflowMoldingSampleFactoryRecords,
      injectionFactoryRegistry,
      injectionFactoryDataRegistry,
    ] as Array<Record<string, unknown>>

    for (const registry of registries) {
      expect(registry['huakang-c']).not.toBe(registry['huakang-d'])
    }
  })
})
