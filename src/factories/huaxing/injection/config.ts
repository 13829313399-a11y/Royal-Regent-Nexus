import type { InjectionFactoryConfig } from '@/factories/injection/types'
import { huaxingMachineImportSummary } from '@/data/huaxingMachineImport'
import { huaxingMoldImportSummary } from '@/data/huaxingMoldImport'

export const huaxingInjectionFactoryConfig: InjectionFactoryConfig = {
  factoryId: 'huaxing',
  moduleTitle: '华兴注塑排产中枢',
  workspaceSummary: '华兴先作为第一套正式实现，已经接入机台台账与模具总表，适合继续往真实排产规则和机台映射推进。',
  dataStatus: `机台 ${huaxingMachineImportSummary.rowCount} 台 / 模具明细 ${huaxingMoldImportSummary.rowCount} 条`,
  processStatus: '数据已接入，规则待细化',
  ownership: '生产部 / PMC / 计划 / 工程',
  highlights: [
    { label: '机台台账', value: `${huaxingMachineImportSummary.rowCount} 台`, tone: 'teal' },
    { label: '模具总表', value: `${huaxingMoldImportSummary.activeRowCount} 套在册`, tone: 'blue' },
    { label: '废模口径', value: `${huaxingMoldImportSummary.scrapRowCount} 条`, tone: 'amber' },
  ],
  implementationNotes: [
    '已接华兴机器设备明细',
    '已接华兴模具总表',
    '下一步补模具 -> 机台映射和24H/11H目标',
  ],
}
