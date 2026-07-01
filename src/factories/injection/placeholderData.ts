import type { ProductionFactoryContextId } from '@/data/enterpriseMock'
import {
  injectionPendingOrderFieldGroups,
  injectionSectionNav,
  type InjectionModuleData,
} from '@/data/injectionSchedulingMock'
import {
  createPlaceholderValidationRules,
  createSharedInjectionConfigRuleCards,
  sharedInjectionWorkflowStages,
} from '@/factories/injection/rules'

const factoryNameMap: Record<ProductionFactoryContextId, string> = {
  'huakang-a': '华康A',
  'huakang-b': '华康B',
  huadeng: '华登',
  huaxing: '华兴',
}

export function createPlaceholderInjectionModuleData(factoryId: ProductionFactoryContextId): InjectionModuleData {
  const factoryName = factoryNameMap[factoryId]

  return {
    sectionNav: injectionSectionNav,
    overviewMetrics: [
      { label: '待排订单', value: '待接入', detail: `${factoryName}订单池尚未接入`, tone: 'amber' },
      { label: '结转订单', value: '待接入', detail: '结转逻辑待定义', tone: 'blue' },
      { label: '运行机台', value: '待接入', detail: '机台台账待导入', tone: 'teal' },
      { label: '排产异常', value: '待接入', detail: '异常策略待配置', tone: 'red' },
    ],
    shiftSummaries: [
      {
        shift: '待建档',
        date: '2026-07-01',
        completion: 0,
        machineRunning: '待接机台台账',
        carryOver: '待定义结转口径',
        alert: `${factoryName}尚未接入真实班次数据`,
      },
    ],
    machineLoad: [],
    colorTransitionRisks: [],
    dataSourceStatus: [
      { name: '订单池', freshness: '未接入', status: '待接', statusTone: 'amber', summary: `${factoryName}待排订单标准表尚未导入。` },
      { name: '机台主数据', freshness: '未接入', status: '待接', statusTone: 'amber', summary: `${factoryName}机台台账尚未导入。` },
      { name: '模具目标', freshness: '未接入', status: '风险', statusTone: 'red', summary: `${factoryName}模具目标、穴数和优选机台尚未建档。` },
      { name: '历史数据库', freshness: '未接入', status: '待接', statusTone: 'blue', summary: `${factoryName}历史回报与入库回写尚未打通。` },
    ],
    executionTasks: [
      { title: `${factoryName}待接机台台账`, meta: '先接机台台账，再承接候选机台推荐', tone: 'amber' },
      { title: `${factoryName}待接模具主数据`, meta: '需补模具目标、穴数、节拍与优选机台', tone: 'red' },
    ],
    workflowStages: sharedInjectionWorkflowStages.map((stage) => ({
      ...stage,
      state: 'pending',
      detail:
        stage.title === '订单入池'
          ? `${factoryName}待接真实订单标准表。`
          : stage.title === '结转识别'
            ? '待定义结转延续规则。'
            : stage.title === '智能排机'
              ? '待接机台与模具主数据。'
              : stage.title === '人工微调'
                ? '待建立异常处理口径。'
                : '待接日报、入库与回写。',
    })),
    dataCenterDatasets: [
      { name: '订单主数据', owner: '计划 / 文员', freshness: '未接入', completeness: 0, status: '待接', statusTone: 'amber', summary: `${factoryName}待排订单标准表尚未导入。`, issues: ['缺标准订单池'] },
      { name: '机台主数据', owner: '生产主管', freshness: '未接入', completeness: 0, status: '待接', statusTone: 'amber', summary: `${factoryName}机台台账尚未导入。`, issues: ['缺机台编码', '缺机台限制'] },
      { name: '模具目标数据', owner: '工程 / 生产', freshness: '未接入', completeness: 0, status: '风险', statusTone: 'red', summary: `${factoryName}模具目标主数据尚未建档。`, issues: ['缺24H/11H目标', '缺优选机台映射'] },
      { name: '历史生产数据', owner: '系统回写', freshness: '未接入', completeness: 0, status: '待接', statusTone: 'blue', summary: `${factoryName}历史回报与入库回写尚未打通。`, issues: ['缺回报回写'] },
    ],
    orderSnapshotRows: [],
    machineProfileRows: [],
    moldTargetRows: [],
    executionQueueRows: [],
    executionRuleMetrics: [
      { label: '设备台账', value: '待导入', detail: `${factoryName}机台台账尚未接入`, tone: 'teal' },
      { label: '五轴双臂', value: '待导入', detail: '机械手能力待建档', tone: 'blue' },
      { label: '特殊工艺机', value: '待导入', detail: 'PVC / PC / 双色等规则待整理', tone: 'amber' },
      { label: '注意 / 新购', value: '待导入', detail: '设备状态待整理', tone: 'red' },
    ],
    executionConstraintRows: [],
    executionCandidateRows: [],
    executionScheduleRows: [],
    manualActionRows: [
      { title: `${factoryName}待定义人工微调动作`, reason: '真实机台与模具规则尚未接入', owner: '计划员 / 生产主管', action: '先补主数据与例外规则', tone: 'amber' },
    ],
    reportingMetrics: [
      { label: '班次达成率', value: '待接入', detail: `${factoryName}日报未接入`, tone: 'green' },
      { label: '当日产值', value: '待接入', detail: '产值口径待确认', tone: 'blue' },
      { label: '待入库单', value: '待接入', detail: '入库回写待打通', tone: 'amber' },
      { label: '停机异常', value: '待接入', detail: '停机分类待统一', tone: 'red' },
    ],
    shiftReportRows: [],
    warehouseInboundRows: [],
    configRuleCards: createSharedInjectionConfigRuleCards([
      `${factoryName}模具总表待导入`,
      `${factoryName}机台台账待导入`,
    ]).map((card) => {
      if (card.title === '排机规则优先级') {
        return {
          ...card,
          status: '沿用公共规则',
          summary: `${factoryName}先沿用公共排机规则，后续只补本厂参数和权重。`,
        }
      }

      if (card.title === '模具 → 机台映射') {
        return {
          ...card,
          summary: `${factoryName}待建立模具与机台的正式映射。`,
        }
      }

      if (card.title === '颜色 / 料型例外规则') {
        return {
          ...card,
          status: '待补',
          tone: 'amber',
          summary: `${factoryName}待整理特殊料型与颜色切换规则。`,
          items: ['料型限制', '换色顺序', '特殊机械手要求'],
        }
      }

      if (card.title === '组织与权限') {
        return {
          ...card,
          summary: `${factoryName}先复用公共权限骨架，后续再细化。`,
          items: ['计划员', '生产主管', 'PMC', '文员'],
        }
      }

      return card
    }),
    pendingOrderFieldGroups: injectionPendingOrderFieldGroups,
    pendingOrderValidationRules: createPlaceholderValidationRules(factoryName),
    orderImportTasks: [
      { step: '订单标准字段', owner: '计划 / 文员', status: '已定义', detail: `${factoryName}先沿用公共订单字段骨架。`, tone: 'green' },
      { step: '真实订单导入', owner: '计划', status: '待接入', detail: `${factoryName}待导入真实待排订单标准表。`, tone: 'amber' },
      { step: '模具编码关联', owner: '工程 / 生产', status: '待接入', detail: `${factoryName}待把订单模具编码和模具总表打通。`, tone: 'amber' },
      { step: '结转 / 回写闭环', owner: 'PMC / 系统', status: '待接入', detail: `${factoryName}待接日报、结转和入库回写。`, tone: 'red' },
    ],
    pendingOrderDetailRows: [],
    machineMasterRows: [],
    moldTargetDetailRows: [],
    moldMachineMappingRows: [],
    shiftReportChecklistItems: [
      { title: '回报闭环待建立', owner: '车间 / PMC', status: '待建立', detail: `${factoryName}的班次日报、交接和入库回写尚未接入。`, tone: 'amber' },
    ],
    shiftHandoverRows: [],
    inboundWritebackRows: [],
  }
}
