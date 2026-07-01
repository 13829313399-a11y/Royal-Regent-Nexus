import type { InjectionFactoryConfig } from '@/factories/injection/types'

export const huakangAInjectionFactoryConfig: InjectionFactoryConfig = {
  factoryId: 'huakang-a',
  moduleTitle: '华康A注塑排产中枢',
  workspaceSummary: '先复用公共排产骨架，后续单独接入华康A的订单池、机台台账、模具目标和特殊工艺规则。',
  dataStatus: '尚未接入正式主数据',
  processStatus: '骨架待接入',
  ownership: '生产部 / PMC / 计划',
  highlights: [
    { label: '数据状态', value: '待接订单池', tone: 'amber' },
    { label: '机台台账', value: '待导入', tone: 'red' },
    { label: '规则层', value: '待定义', tone: 'blue' },
  ],
  implementationNotes: [
    '复用公共注塑页面骨架',
    '单独维护华康A机台和模具主数据',
    '后续补A厂独立排产规则',
  ],
}
