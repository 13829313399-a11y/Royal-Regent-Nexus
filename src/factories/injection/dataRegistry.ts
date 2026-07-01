import type { ProductionFactoryContextId } from '@/data/enterpriseMock'
import type { InjectionModuleData } from '@/data/injectionSchedulingMock'
import { huadengInjectionModuleData } from '@/factories/huadeng/injection/data'
import { huakangAInjectionModuleData } from '@/factories/huakang-a/injection/data'
import { huakangBInjectionModuleData } from '@/factories/huakang-b/injection/data'
import { huaxingInjectionModuleData } from '@/factories/huaxing/injection/data'

export const injectionFactoryDataRegistry: Record<ProductionFactoryContextId, InjectionModuleData> = {
  'huakang-a': huakangAInjectionModuleData,
  'huakang-b': huakangBInjectionModuleData,
  huadeng: huadengInjectionModuleData,
  huaxing: huaxingInjectionModuleData,
}

export function getInjectionFactoryData(factoryId: ProductionFactoryContextId): InjectionModuleData {
  return injectionFactoryDataRegistry[factoryId]
}
