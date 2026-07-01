import type {
  ConfigRuleCard,
  InjectionStage,
  PendingOrderValidationRule,
} from '@/data/injectionSchedulingMock'

export const sharedInjectionWorkflowStages: InjectionStage[] = [
  {
    title: '订单入池',
    owner: '计划 / 文员',
    detail: '导入 PDF、Excel、图片和手工补单，统一进入待排订单池。',
    state: 'done',
  },
  {
    title: '结转识别',
    owner: '系统',
    detail: '自动识别上一班未完成订单并锁定原机台延续。',
    state: 'done',
  },
  {
    title: '智能排机',
    owner: '系统 + 计划员',
    detail: '综合同模、啤重、料型、颜色顺序和历史命中率排机。',
    state: 'active',
  },
  {
    title: '人工微调',
    owner: '生产主管',
    detail: '处理异常、颜色逆序、目标缺失与重点插单。',
    state: 'pending',
  },
  {
    title: '回报闭环',
    owner: '车间 / PMC',
    detail: '日报、入库、月结与历史回写，反哺下一轮排产。',
    state: 'pending',
  },
]

export function createSharedInjectionConfigRuleCards(mappingItems: string[]): ConfigRuleCard[] {
  return [
    {
      title: '排机规则优先级',
      owner: '计划规则',
      summary: '决定同模同机、结转优先、颜色顺序、啤重匹配和负载均衡的权重。',
      status: '待参数化',
      tone: 'amber',
      items: ['结转优先', '同套模强制同机', '颜色浅到深', '啤重 / 吨位适配'],
    },
    {
      title: '模具 → 机台映射',
      owner: '人工学习映射',
      summary: '规则通用，但映射数据按车间独立维护；每个厂只替换自己的模具、机台和例外关系。',
      status: mappingItems.length > 0 ? '按厂维护' : '待建立',
      tone: mappingItems.length > 0 ? 'amber' : 'red',
      items: mappingItems.length > 0 ? mappingItems : ['待补机台映射'],
    },
    {
      title: '颜色 / 料型例外规则',
      owner: '生产工艺',
      summary: '识别黑转白、特殊料型、五轴双臂需求等例外场景。',
      status: '待补',
      tone: 'red',
      items: ['黑后接白需人工确认', 'TPE / PVC 特殊料型优先固定机台', '三板模优先五轴双臂'],
    },
    {
      title: '组织与权限',
      owner: '管理员',
      summary: '区分计划员、生产主管、PMC、文员对数据中心、执行页和回报页的操作权限。',
      status: '基础已就绪',
      tone: 'blue',
      items: ['计划员可排机', '生产主管可微调', 'PMC 可看回报与入库', '文员可维护订单池'],
    },
  ]
}

export function createPlaceholderValidationRules(factoryName: string): PendingOrderValidationRule[] {
  return [
    { label: '缺订单池', hit: '未接入', detail: `${factoryName}尚未导入待排订单标准表。`, tone: 'amber' },
    { label: '缺模具目标', hit: '未接入', detail: `${factoryName}尚未导入模具目标主数据。`, tone: 'red' },
    { label: '缺机台台账', hit: '未接入', detail: `${factoryName}尚未导入机台主数据。`, tone: 'amber' },
  ]
}
