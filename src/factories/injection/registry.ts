import type { ProductionFactoryContextId } from '@/data/enterpriseMock'
import { huadengInjectionFactoryConfig } from '@/factories/huadeng/injection/config'
import { huakangAInjectionFactoryConfig } from '@/factories/huakang-a/injection/config'
import { huakangBInjectionFactoryConfig } from '@/factories/huakang-b/injection/config'
import { huaxingInjectionFactoryConfig } from '@/factories/huaxing/injection/config'
import type { InjectionFactoryConfig } from '@/factories/injection/types'

export const injectionFactoryRegistry: Record<ProductionFactoryContextId, InjectionFactoryConfig> = {
  'huakang-a': huakangAInjectionFactoryConfig,
  'huakang-b': huakangBInjectionFactoryConfig,
  huadeng: huadengInjectionFactoryConfig,
  huaxing: huaxingInjectionFactoryConfig,
}

export function getInjectionFactoryConfig(factoryId: ProductionFactoryContextId): InjectionFactoryConfig {
  return injectionFactoryRegistry[factoryId]
}
