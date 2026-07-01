import type { ProductionFactoryContextId, Tone } from '@/data/enterpriseMock'

export interface InjectionFactoryHighlight {
  label: string
  value: string
  tone: Tone
}

export interface InjectionFactoryConfig {
  factoryId: ProductionFactoryContextId
  moduleTitle: string
  workspaceSummary: string
  dataStatus: string
  processStatus: string
  ownership: string
  highlights: InjectionFactoryHighlight[]
  implementationNotes: string[]
}
