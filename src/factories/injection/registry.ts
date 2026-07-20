import type { ProductionFactoryContextId } from '@/data/enterpriseMock'
import { huadengInjectionFactoryConfig } from '@/factories/huadeng/injection/config'
import { huakangAInjectionFactoryConfig } from '@/factories/huakang-a/injection/config'
import { huakangBInjectionFactoryConfig } from '@/factories/huakang-b/injection/config'
import { huaxingInjectionFactoryConfig } from '@/factories/huaxing/injection/config'
import type { InjectionFactoryConfig } from '@/factories/injection/types'

function createPlaceholderInjectionFactoryConfig(
  factoryId: ProductionFactoryContextId,
  factoryName: string,
): InjectionFactoryConfig {
  return {
    factoryId,
    moduleTitle: `${factoryName}注塑排产中枢`,
    workspaceSummary: `${factoryName}复用公共排产组件，并单独接入本厂订单池、机台、模具和班次数据。`,
    dataStatus: '尚未接入正式主数据',
    processStatus: '公共骨架已就绪',
    ownership: '生产部 / PMC / 计划 / 工程',
    highlights: [
      { label: '公共组件', value: '已启用', tone: 'teal' },
      { label: '本厂数据', value: '待接入', tone: 'amber' },
      { label: '跨厂隔离', value: '独立', tone: 'blue' },
    ],
    implementationNotes: [
      '复用公共注塑页面骨架',
      `只读取${factoryName}自己的排产数据`,
      '未接入数据时显示本厂空态，不回退其他厂区',
    ],
  }
}

const huakangCInjectionFactoryConfig = createPlaceholderInjectionFactoryConfig('huakang-c', '华康C')
const huakangDInjectionFactoryConfig = createPlaceholderInjectionFactoryConfig('huakang-d', '华康D')

export const injectionFactoryRegistry: Record<ProductionFactoryContextId, InjectionFactoryConfig> = {
  'huakang-a': huakangAInjectionFactoryConfig,
  'huakang-b': huakangBInjectionFactoryConfig,
  'huakang-c': huakangCInjectionFactoryConfig,
  'huakang-d': huakangDInjectionFactoryConfig,
  huadeng: huadengInjectionFactoryConfig,
  huaxing: huaxingInjectionFactoryConfig,
}

export function getInjectionFactoryConfig(factoryId: ProductionFactoryContextId): InjectionFactoryConfig {
  return injectionFactoryRegistry[factoryId]
}
