import type { InjectionFactoryConfig } from '@/factories/injection/types'

export const huadengInjectionFactoryConfig: InjectionFactoryConfig = {
  factoryId: 'huadeng',
  moduleTitle: '华登注塑排产中枢',
  workspaceSummary: '华登也走公共排产骨架，但保留自己独立的数据导入、工艺限制和配置中心。',
  dataStatus: '尚未接入正式主数据',
  processStatus: '骨架待接入',
  ownership: '生产部 / PMC / 计划 / 工程',
  highlights: [
    { label: '数据状态', value: '待接订单池', tone: 'amber' },
    { label: '模具目标', value: '待导入', tone: 'red' },
    { label: '配置中心', value: '待建立', tone: 'blue' },
  ],
  implementationNotes: [
    '复用公共注塑页面骨架',
    '单独维护华登机台和模具主数据',
    '后续补华登配置中心和规则集',
  ],
}
