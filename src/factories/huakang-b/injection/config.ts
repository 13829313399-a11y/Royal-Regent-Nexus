import type { InjectionFactoryConfig } from '@/factories/injection/types'

export const huakangBInjectionFactoryConfig: InjectionFactoryConfig = {
  factoryId: 'huakang-b',
  moduleTitle: '华康B注塑排产中枢',
  workspaceSummary: '华康B后续走同一套公共壳子，但保留自己的机台能力、班次结构和结转策略。',
  dataStatus: '尚未接入正式主数据',
  processStatus: '骨架待接入',
  ownership: '生产部 / PMC / 计划',
  highlights: [
    { label: '数据状态', value: '待接订单池', tone: 'amber' },
    { label: '机台台账', value: '待导入', tone: 'red' },
    { label: '班次策略', value: '待确认', tone: 'blue' },
  ],
  implementationNotes: [
    '复用公共注塑页面骨架',
    '单独维护华康B机台和模具主数据',
    '后续补B厂结转与班次规则',
  ],
}
