import type { Component } from 'vue'
import {
  AlertTriangle,
  Archive,
  Boxes,
  ClipboardCheck,
  FileStack,
  GitBranch,
  LayoutDashboard,
  Network,
  PackageCheck,
  Settings2,
  ShieldCheck,
  UserCog,
  Users,
  Wrench,
} from '@lucide/vue'

export type Tone = 'teal' | 'blue' | 'amber' | 'red' | 'slate' | 'green'

export type FactoryContextId = 'group' | 'huakang-a' | 'huakang-b' | 'huadeng' | 'huaxing'

export type DepartmentId =
  | 'overview'
  | 'engineering'
  | 'pmc-warehouse'
  | 'production'
  | 'qa'
  | 'sales-business'

export type ModuleDepartmentId = Exclude<DepartmentId, 'overview'>

export interface FactoryContext {
  id: FactoryContextId
  name: string
  shortName: string
  description: string
  health: number
  tone: Tone
}

export interface Department {
  id: DepartmentId
  name: string
  shortName: string
  focus: string
}

export interface NavigationItem {
  label: string
  to: string
  icon: Component
  departmentId?: DepartmentId
}

export interface NavigationGroup {
  label: string
  items: NavigationItem[]
}

export interface Metric {
  label: string
  value: string
  detail: string
  tone: Tone
}

export interface FactoryHeat {
  factoryId: FactoryContextId
  name: string
  status: string
  statusTone: Tone
  score: number
  summary: string
  metrics: string
}

export interface TimelineItem {
  title: string
  meta: string
  tone: Tone
}

export interface ModuleHealth {
  name: string
  value: number
  tone: Tone
}

export interface ModuleStatusMetric {
  label: string
  value: string
  tone: Tone
}

export interface ModuleChildLink {
  label: string
  route?: string
  summary?: string
}

export interface EnterpriseModule {
  id: string
  title: string
  owner: string
  summary: string
  status: string
  statusTone: Tone
  stats: string
  icon: Component
  href?: string
  route?: string
  statusMetrics: ModuleStatusMetric[]
  todos: string[]
  children: ModuleChildLink[]
}

export interface PermissionRow {
  role: string
  view: boolean
  edit: boolean
  approve: boolean
}

export interface TodoItem {
  id: string
  title: string
  meta: string
}

export interface ApprovalRow {
  id: string
  customer: string
  factory: string
  status: string
  statusTone: Tone
  owner: string
  sla: string
  summary: string
  amount: string
}

export interface ApprovalStep {
  label: string
  state: 'done' | 'active' | 'pending'
  owner: string
}

export interface DepartmentModuleRegistryEntry {
  departmentId: ModuleDepartmentId
  heroTitle: string
  heroSubtitle: string
  panelTitle: string
  panelSubtitle: string
  modules: EnterpriseModule[]
  quickCandidates: string[]
  permissionRows: PermissionRow[]
  todos: TodoItem[]
}

export const moduleDepartmentIds: ModuleDepartmentId[] = [
  'engineering',
  'pmc-warehouse',
  'production',
  'qa',
  'sales-business',
]

export const factoryContexts: FactoryContext[] = [
  {
    id: 'group',
    name: '集团总览',
    shortName: '集团',
    description: '集团级业务中台',
    health: 91,
    tone: 'teal',
  },
  {
    id: 'huakang-a',
    name: '华康A',
    shortName: '华康A',
    description: '主力制造厂区',
    health: 93,
    tone: 'teal',
  },
  {
    id: 'huakang-b',
    name: '华康B',
    shortName: '华康B',
    description: '材料与产能协同厂区',
    health: 82,
    tone: 'amber',
  },
  {
    id: 'huadeng',
    name: '华登',
    shortName: '华登',
    description: '精密制造与稳定交付厂区',
    health: 95,
    tone: 'green',
  },
  {
    id: 'huaxing',
    name: '华兴',
    shortName: '华兴',
    description: '快速扩产与异常治理厂区',
    health: 74,
    tone: 'red',
  },
]

export const departments: Department[] = [
  {
    id: 'overview',
    name: '管理驾驶舱',
    shortName: '总览',
    focus: '集团指标、跨厂区事项、模块健康度',
  },
  {
    id: 'engineering',
    name: '工程部',
    shortName: '工程',
    focus: 'BOM、图纸、工艺路线、工程变更',
  },
  {
    id: 'pmc-warehouse',
    name: 'PMC / 仓管',
    shortName: 'PMC',
    focus: '物料计划、库存、收发、齐套风险',
  },
  {
    id: 'production',
    name: '生产部',
    shortName: '生产',
    focus: '排程、工单、产能、现场进度',
  },
  {
    id: 'qa',
    name: 'QA 部',
    shortName: 'QA',
    focus: '检验、异常、复判、质量门禁',
  },
  {
    id: 'sales-business',
    name: '业务部',
    shortName: '业务',
    focus: '客户、报价、合同、订单审批',
  },
]

export const departmentMap = Object.fromEntries(
  departments.map((department) => [department.id, department]),
) as Record<DepartmentId, Department>

export function isModuleDepartmentId(value: string): value is ModuleDepartmentId {
  return moduleDepartmentIds.includes(value as ModuleDepartmentId)
}

export function getDepartmentRoute(departmentId: ModuleDepartmentId, moduleId?: string) {
  return moduleId ? `/modules/${departmentId}/${moduleId}` : `/modules/${departmentId}`
}

export function getDepartmentRegistryEntry(departmentId: ModuleDepartmentId) {
  return departmentModuleRegistry[departmentId]
}

export function getDepartmentModule(departmentId: ModuleDepartmentId, moduleId: string) {
  return departmentModuleRegistry[departmentId].modules.find((module) => module.id === moduleId)
}

export const navigationGroups: NavigationGroup[] = [
  {
    label: 'MAIN',
    items: [
      { label: '管理驾驶舱', to: '/', icon: LayoutDashboard },
      { label: '工程部', to: getDepartmentRoute('engineering'), icon: Wrench, departmentId: 'engineering' },
      { label: 'PMC / 仓管', to: getDepartmentRoute('pmc-warehouse'), icon: Archive, departmentId: 'pmc-warehouse' },
      { label: '生产部', to: getDepartmentRoute('production'), icon: Boxes, departmentId: 'production' },
      { label: 'QA 部', to: getDepartmentRoute('qa'), icon: ShieldCheck, departmentId: 'qa' },
      { label: '业务部', to: getDepartmentRoute('sales-business'), icon: ClipboardCheck, departmentId: 'sales-business' },
    ],
  },
  {
    label: 'CROSS FACTORY',
    items: [
      { label: '跨厂区审批', to: '/workbench', icon: GitBranch },
      { label: '异常与预警', to: '/workbench', icon: AlertTriangle },
      { label: '权限与组织', to: getDepartmentRoute('engineering'), icon: Users },
    ],
  },
  {
    label: 'CONFIG',
    items: [
      { label: '模块配置', to: getDepartmentRoute('production'), icon: Settings2 },
      { label: '角色权限', to: getDepartmentRoute('qa'), icon: UserCog },
      { label: '流程中心', to: '/workbench', icon: Network },
    ],
  },
]

export const overviewMetrics: Metric[] = [
  { label: '待处理审批', value: '128', detail: '跨厂区 37 · 超时 8', tone: 'teal' },
  { label: '今日生产单', value: '46', detail: '准时率 94.6%', tone: 'blue' },
  { label: 'QA 异常', value: '9', detail: '严重 1 · 待复判 4', tone: 'amber' },
  { label: '库存预警', value: '17', detail: '原料 11 · 成品 6', tone: 'red' },
]

export const factoryHeatmap: FactoryHeat[] = [
  {
    factoryId: 'huakang-a',
    name: '华康A',
    status: '良好',
    statusTone: 'green',
    score: 88,
    summary: '工程 96 · PMC 91 · 生产 94 · QA 88 · 业务 93',
    metrics: '主力厂区，跨部门流转稳定',
  },
  {
    factoryId: 'huakang-b',
    name: '华康B',
    status: '关注',
    statusTone: 'amber',
    score: 74,
    summary: 'PMC 库存预警增加，QA 复判排队',
    metrics: '库存与复判环节需要今日处理',
  },
  {
    factoryId: 'huadeng',
    name: '华登',
    status: '良好',
    statusTone: 'green',
    score: 92,
    summary: '生产达成率最高，业务回款跟进稳定',
    metrics: '交付稳定，审批 SLA 保持健康',
  },
  {
    factoryId: 'huaxing',
    name: '华兴',
    status: '预警',
    statusTone: 'red',
    score: 63,
    summary: '工程变更积压，生产排程需二次确认',
    metrics: '排程冲突和物料替代待确认',
  },
]

export const crossFactoryItems: TimelineItem[] = [
  { title: '华兴生产排程冲突', meta: '生产部 · 还剩 1.5 小时', tone: 'red' },
  { title: '华康B 原料库存预警', meta: 'PMC/仓管 · 今日需处理', tone: 'amber' },
  { title: '华登 QA 批次复核完成', meta: 'QA 部 · 等待业务确认', tone: 'teal' },
]

export const moduleHealth: ModuleHealth[] = [
  { name: '工程部', value: 86, tone: 'teal' },
  { name: 'PMC/仓管', value: 74, tone: 'blue' },
  { name: '生产部', value: 81, tone: 'teal' },
  { name: 'QA 部', value: 66, tone: 'amber' },
  { name: '业务部', value: 78, tone: 'teal' },
]

export const departmentModuleRegistry: Record<ModuleDepartmentId, DepartmentModuleRegistryEntry> = {
  engineering: {
    departmentId: 'engineering',
    heroTitle: '工程模块中心',
    heroSubtitle: '先把入口、权限、状态、待办、跨部门影响统一起来',
    panelTitle: '工程部模块',
    panelSubtitle: '面向 BOM、资料、变更和设备维保的统一模块层',
    modules: [
      {
        id: 'bom-process',
        title: 'BOM / 工艺路线',
        owner: '工程部 · 负责人 陈工',
        summary: '版本管理、物料结构、工艺步骤、变更追踪',
        status: '已上线',
        statusTone: 'green',
        stats: '待办 12 · 今日变更 4',
        icon: PackageCheck,
        route: getDepartmentRoute('engineering', 'bom-process'),
        statusMetrics: [
          { label: '版本', value: '12', tone: 'green' },
          { label: '变更', value: '4', tone: 'blue' },
        ],
        todos: ['待确认替代料 BOM 2 条', 'A 厂新模工艺路线待冻结'],
        children: [
          { label: '版本中心', summary: '管理 BOM 版本、冻结节点和发版记录' },
          { label: '工艺步骤', summary: '梳理工艺顺序、工序卡和特殊要求' },
          { label: '变更追踪', summary: '追踪每次变更的影响范围和执行情况' },
        ],
      },
      {
        id: 'ecn',
        title: 'ECN 工程变更',
        owner: '跨工程 / 生产 / QA',
        summary: '变更申请、影响分析、审批流、版本冻结',
        status: '设计中',
        statusTone: 'blue',
        stats: '待审批 8 · 超时 1',
        icon: GitBranch,
        route: getDepartmentRoute('engineering', 'ecn'),
        statusMetrics: [
          { label: '待审批', value: '8', tone: 'amber' },
          { label: '超时', value: '1', tone: 'red' },
        ],
        todos: ['先打通工程与生产的影响矩阵', '补齐冻结前后的版本对照'],
        children: [
          { label: '申请池', summary: '统一接收变更申请与补充材料' },
          { label: '影响分析', summary: '横向评估工程、生产、QA 和成本影响' },
          { label: '审批路径', summary: '沉淀变更审批链和责任节点' },
        ],
      },
      {
        id: 'drawings',
        title: '图纸与模具资料',
        owner: '图纸库 · 版本锁定',
        summary: '图纸归档、模具台账、借阅、变更关联',
        status: '规划中',
        statusTone: 'amber',
        stats: '资料 248 · 缺失 9',
        icon: FileStack,
        route: getDepartmentRoute('engineering', 'drawings'),
        statusMetrics: [
          { label: '资料库', value: '248', tone: 'blue' },
          { label: '缺失', value: '9', tone: 'red' },
        ],
        todos: ['先补模具借阅记录', '图纸版本追踪需接 ECN'],
        children: [
          { label: '图纸归档', summary: '沉淀版本图纸和受控资料' },
          { label: '模具台账', summary: '建立模具履历、寿命和配套资料' },
          { label: '借阅记录', summary: '追踪资料外借、回收与责任人' },
        ],
      },
      {
        id: 'maintenance',
        title: '设备与治具维护',
        owner: '工程 / 生产共用',
        summary: '点检计划、维修记录、寿命预警、保养任务',
        status: '待拆分',
        statusTone: 'slate',
        stats: '设备 76 · 预警 3',
        icon: Wrench,
        route: getDepartmentRoute('engineering', 'maintenance'),
        statusMetrics: [
          { label: '设备', value: '76', tone: 'teal' },
          { label: '预警', value: '3', tone: 'amber' },
        ],
        todos: ['拆分治具寿命和设备保养两条线', '补点检责任人映射'],
        children: [
          { label: '点检计划', summary: '按设备和治具类型建立点检节奏' },
          { label: '保养任务', summary: '安排周期保养、到期预警和执行确认' },
          { label: '维修记录', summary: '记录故障、维修和寿命恢复情况' },
        ],
      },
    ],
    quickCandidates: ['工程问题单', '样品承认书', '物料替代申请', '客户图纸评审'],
    permissionRows: [
      { role: '工程主管', view: true, edit: true, approve: true },
      { role: '工程师', view: true, edit: true, approve: false },
      { role: '生产主管', view: true, edit: false, approve: true },
      { role: 'QA 主管', view: true, edit: false, approve: true },
    ],
    todos: [
      { id: 'ECN-260626-014', title: '变更影响确认', meta: '华康A · 生产 / QA 待确认' },
      { id: 'BOM-PA-802', title: '版本发布', meta: '工程主管审批 · 今日到期' },
      { id: 'M-771', title: '保养异常', meta: '设备维护 · 待分派' },
    ],
  },
  'pmc-warehouse': {
    departmentId: 'pmc-warehouse',
    heroTitle: 'PMC / 仓管模块中心',
    heroSubtitle: '围绕计划、库存、到货和齐套风险建立统一入口',
    panelTitle: 'PMC / 仓管模块',
    panelSubtitle: '适合承载物料计划、库存预警、入库与月结流程',
    modules: [
      {
        id: 'material-plan',
        title: '物料计划与齐套',
        owner: 'PMC 主计划',
        summary: '订单拉动、齐套检查、缺料预警、跨厂区协同',
        status: '规划中',
        statusTone: 'amber',
        stats: '缺料 11 · 风险工单 6',
        icon: Archive,
        route: getDepartmentRoute('pmc-warehouse', 'material-plan'),
        statusMetrics: [
          { label: '缺料', value: '11', tone: 'red' },
          { label: '齐套率', value: '92%', tone: 'teal' },
        ],
        todos: ['补齐来料 ETA', '建立齐套风险分层'],
        children: [
          { label: '物料池', summary: '沉淀订单所需原料与包材清单' },
          { label: '齐套检查', summary: '按工单检查来料、库存和替代料情况' },
          { label: '缺料预警', summary: '高亮阻塞生产的关键缺料项' },
        ],
      },
      {
        id: 'warehouse-receiving',
        title: '入库与月结',
        owner: '仓管 / PMC',
        summary: '送货单、入库确认、月底结算、异常回溯',
        status: '设计中',
        statusTone: 'blue',
        stats: '待入库 19 · 月结待核 4',
        icon: PackageCheck,
        route: getDepartmentRoute('pmc-warehouse', 'warehouse-receiving'),
        statusMetrics: [
          { label: '待入库', value: '19', tone: 'amber' },
          { label: '月结', value: '4', tone: 'blue' },
        ],
        todos: ['接入生产部入库单回写', '月结金额校验待补'],
        children: [
          { label: '入库单', summary: '承接车间送货、PMC 入库和签字流' },
          { label: '对账清单', summary: '对照送货数、单价和异常差异' },
          { label: '月结台账', summary: '月底汇总供应商和车间结算数据' },
        ],
      },
      {
        id: 'inventory-alert',
        title: '库存预警',
        owner: '仓管预警台',
        summary: '原料、包材、半成品、成品库存告警与补货建议',
        status: '已上线',
        statusTone: 'green',
        stats: '预警 17 · 今日解除 5',
        icon: AlertTriangle,
        route: getDepartmentRoute('pmc-warehouse', 'inventory-alert'),
        statusMetrics: [
          { label: '预警', value: '17', tone: 'red' },
          { label: '已解除', value: '5', tone: 'green' },
        ],
        todos: ['高频缺料料号应升级为重点监控', '补安全库存曲线'],
        children: [
          { label: '原料预警', summary: '识别高频波动和安全库存不足的料号' },
          { label: '包材预警', summary: '追踪包材短缺与交付风险' },
          { label: '成品预警', summary: '发现积压与紧缺成品的异常波动' },
        ],
      },
    ],
    quickCandidates: ['供应商到货跟踪', '备料看板', '跨厂调拨单', '月结核价清单'],
    permissionRows: [
      { role: 'PMC 主管', view: true, edit: true, approve: true },
      { role: '仓管员', view: true, edit: true, approve: false },
      { role: '采购', view: true, edit: false, approve: false },
      { role: '生产主管', view: true, edit: false, approve: true },
    ],
    todos: [
      { id: 'PMC-210', title: '缺料工单复核', meta: '华康B · 影响 6 张生产单' },
      { id: 'WH-044', title: '入库单待确认', meta: '送货批次 19 单 · 今日需清理' },
      { id: 'SET-008', title: '月底月结差异', meta: '2 家供应商待核价' },
    ],
  },
  production: {
    departmentId: 'production',
    heroTitle: '生产模块中心',
    heroSubtitle: '把排产、执行、回报、外发和配置从普通入口升级为生产调度中心',
    panelTitle: '生产部模块',
    panelSubtitle: '优先承载注塑排产这类重流程、重数据、重可视化的业务模块',
    modules: [
      {
        id: 'injection-scheduling',
        title: '注塑排产中枢',
        owner: '生产部 / PMC / 计划',
        summary: '订单导入、智能排机、结转延续、日报、入库、历史反哺一体化',
        status: '结构升级中',
        statusTone: 'amber',
        stats: '待排 86 · 结转 12 · 异常 4',
        icon: Boxes,
        href: '/paiji/',
        route: getDepartmentRoute('production', 'injection-scheduling'),
        statusMetrics: [
          { label: '待排', value: '86', tone: 'amber' },
          { label: '结转', value: '12', tone: 'blue' },
          { label: '异常', value: '4', tone: 'red' },
        ],
        todos: ['先改成驾驶舱 + 数据中心 + 排机执行分区', '待补机台与模具原始主数据'],
        children: [
          { label: '驾驶舱', summary: '聚合待排、结转、异常、机台负载和班次达成' },
          { label: '数据中心', summary: '统一订单、机台、模具目标和历史生产主数据' },
          { label: '排机执行', summary: '承接智能排机、人工微调、顺序重排和结转延续' },
          { label: '回报中心', summary: '汇总日报、入库、月结和执行结果回写' },
          { label: '配置中心', summary: '维护规则参数、模具映射、权限和责任人' },
        ],
      },
      {
        id: 'production-plan',
        title: '生产计划管理',
        owner: '计划排程',
        summary: '月计划、跨线排程、计划调整、工单分发',
        status: '设计中',
        statusTone: 'blue',
        stats: '月计划 3 版 · 待调整 7',
        icon: ClipboardCheck,
        href: '/production-plan/',
        route: getDepartmentRoute('production', 'production-plan'),
        statusMetrics: [
          { label: '月计划', value: '3', tone: 'blue' },
          { label: '待调整', value: '7', tone: 'amber' },
        ],
        todos: ['和排产中枢打通上游数据', '补跨厂区计划对比'],
        children: [
          { label: '月计划', summary: '承接月度排产与产能拆分' },
          { label: '日计划', summary: '细化到日的执行计划和插单处理' },
          { label: '计划对比', summary: '比较计划、实际与跨厂调度差异' },
        ],
      },
      {
        id: 'outsource-control',
        title: '啤机外发协同',
        owner: '生产外发 / PMC',
        summary: '外发订单、供应商能力、交付回收、PMC 跟催',
        status: '已接入',
        statusTone: 'green',
        stats: '供应商 12 · 待跟催 5',
        icon: Network,
        href: '/pi-outsource/',
        route: getDepartmentRoute('production', 'outsource-control'),
        statusMetrics: [
          { label: '供应商', value: '12', tone: 'teal' },
          { label: '待跟催', value: '5', tone: 'amber' },
        ],
        todos: ['补供应商稼动率热力图', '回收时间需接主排产'],
        children: [
          { label: '外发订单', summary: '管理外发批次、产能和状态变化' },
          { label: '供应商看板', summary: '观察供应商能力、稼动率和交期表现' },
          { label: '回收进度', summary: '跟踪回收节点、异常和 PMC 跟催' },
        ],
      },
      {
        id: 'spray-production',
        title: '喷油部生产管理',
        owner: '喷油车间',
        summary: '喷油工单、线体产能、报价工价、现场日报',
        status: '已上线',
        statusTone: 'green',
        stats: '线体 6 · 今日工单 14',
        icon: Wrench,
        href: '/penyou/',
        route: getDepartmentRoute('production', 'spray-production'),
        statusMetrics: [
          { label: '线体', value: '6', tone: 'teal' },
          { label: '工单', value: '14', tone: 'blue' },
        ],
        todos: ['与注塑排产共享交接节拍', '补喷油异常回写'],
        children: [
          { label: '工单池', summary: '集中管理喷油工单和优先级' },
          { label: '线体看板', summary: '观察线体产能、负载和异常' },
          { label: '日报中心', summary: '沉淀工价、产值和班次回报' },
        ],
      },
    ],
    quickCandidates: ['注塑生产驾驶舱', '停机异常池', '班次达成看板', '换模节拍分析'],
    permissionRows: [
      { role: '生产主管', view: true, edit: true, approve: true },
      { role: '计划员', view: true, edit: true, approve: false },
      { role: 'PMC', view: true, edit: false, approve: true },
      { role: '车间文员', view: true, edit: true, approve: false },
    ],
    todos: [
      { id: 'SCH-301', title: '注塑排产结构改造', meta: '先完成模块注册和驾驶舱入口' },
      { id: 'REP-098', title: '白夜班日报对齐', meta: '目标值和实际回报口径待统一' },
      { id: 'OUT-021', title: '外发回收异常', meta: '2 家供应商交期回收延迟' },
    ],
  },
  qa: {
    departmentId: 'qa',
    heroTitle: 'QA 模块中心',
    heroSubtitle: '把检验、异常、复判和质量门禁模块集中承载',
    panelTitle: 'QA 部模块',
    panelSubtitle: '适合搭建检验台账、异常闭环和批次质量门禁',
    modules: [
      {
        id: 'incoming-inspection',
        title: '来料与成品检验',
        owner: 'QA 验货组',
        summary: '来料验收、成品抽检、AQL 记录、批次归档',
        status: '已上线',
        statusTone: 'green',
        stats: '待验 9 · 退回 1',
        icon: ShieldCheck,
        route: getDepartmentRoute('qa', 'incoming-inspection'),
        statusMetrics: [
          { label: '待验', value: '9', tone: 'amber' },
          { label: '退回', value: '1', tone: 'red' },
        ],
        todos: ['补生产批次关联', '统一 AQL 结论模板'],
        children: [
          { label: '来料检验', summary: '记录来料质量门禁和结果' },
          { label: '成品抽检', summary: '留存成品抽检和 AQL 判断' },
          { label: '批次记录', summary: '建立批次、样本和结果归档' },
        ],
      },
      {
        id: 'quality-exception',
        title: '异常与复判',
        owner: 'QA 主管 / 工程协同',
        summary: '异常登记、复判、责任归属、关闭时效',
        status: '设计中',
        statusTone: 'blue',
        stats: '待复判 4 · 严重 1',
        icon: AlertTriangle,
        route: getDepartmentRoute('qa', 'quality-exception'),
        statusMetrics: [
          { label: '待复判', value: '4', tone: 'amber' },
          { label: '严重', value: '1', tone: 'red' },
        ],
        todos: ['先打通工程与生产责任归属', '建立异常关闭 SLA'],
        children: [
          { label: '异常池', summary: '集中展示待关闭和严重异常' },
          { label: '复判路径', summary: '沉淀 QA、工程、生产的复判流程' },
          { label: '关闭复盘', summary: '复盘责任归属与纠正措施' },
        ],
      },
      {
        id: 'quality-reports',
        title: '质量周报与客户报告',
        owner: 'QA 文控',
        summary: '周报、客户报告、留样和附件归档',
        status: '规划中',
        statusTone: 'amber',
        stats: '周报 2 · 待补图 6',
        icon: FileStack,
        route: getDepartmentRoute('qa', 'quality-reports'),
        statusMetrics: [
          { label: '周报', value: '2', tone: 'blue' },
          { label: '待补', value: '6', tone: 'amber' },
        ],
        todos: ['补图片与批次绑定', '输出客户版报告模板'],
        children: [
          { label: '周报', summary: '沉淀内部周报和质量趋势' },
          { label: '客户报告', summary: '输出对客检验和异常说明文档' },
          { label: '附件归档', summary: '归档图片、附件和原始记录' },
        ],
      },
    ],
    quickCandidates: ['制程巡检', '异常复盘库', '客户投诉闭环', '留样追踪'],
    permissionRows: [
      { role: 'QA 主管', view: true, edit: true, approve: true },
      { role: '检验员', view: true, edit: true, approve: false },
      { role: '工程主管', view: true, edit: false, approve: true },
      { role: '生产主管', view: true, edit: false, approve: true },
    ],
    todos: [
      { id: 'QA-420', title: '批次复判待处理', meta: '华康B · 4 条未关闭' },
      { id: 'QA-451', title: '客户报告补图', meta: '本周 6 份报告待完成附件' },
      { id: 'QA-478', title: '异常归责确认', meta: '需工程和生产共同签字' },
    ],
  },
  'sales-business': {
    departmentId: 'sales-business',
    heroTitle: '业务模块中心',
    heroSubtitle: '把客户、报价、合同、订单和审批工作台连成统一入口',
    panelTitle: '业务部模块',
    panelSubtitle: '优先承接报价审批、交期协同和客户交付风险',
    modules: [
      {
        id: 'quote-center',
        title: '报价与成本中心',
        owner: '业务 / 工程 / 财务',
        summary: '报价、核价、成本复核、利润带分析',
        status: '规划中',
        statusTone: 'amber',
        stats: '待核价 6 · 超时 2',
        icon: ClipboardCheck,
        route: getDepartmentRoute('sales-business', 'quote-center'),
        statusMetrics: [
          { label: '待核价', value: '6', tone: 'amber' },
          { label: '超时', value: '2', tone: 'red' },
        ],
        todos: ['先打通工程成本输入', '补利润带分层'],
        children: [
          { label: '报价池', summary: '集中跟踪报价与状态' },
          { label: '核价复核', summary: '拉通工程、采购与财务核价' },
          { label: '利润分析', summary: '按客户和项目观察利润带变化' },
        ],
      },
      {
        id: 'order-approval',
        title: '订单审批工作台',
        owner: '业务经理',
        summary: '客户订单、交期变更、信用额度、跨部门审批',
        status: '已接入',
        statusTone: 'green',
        stats: '待审批 128 · 超时 8',
        icon: GitBranch,
        route: getDepartmentRoute('sales-business', 'order-approval'),
        statusMetrics: [
          { label: '待审批', value: '128', tone: 'blue' },
          { label: '超时', value: '8', tone: 'red' },
        ],
        todos: ['将审批详情与模块中心打通', '增加客户优先级过滤'],
        children: [
          { label: '审批池', summary: '聚合跨部门审批单和优先级' },
          { label: '交期变更', summary: '跟踪交期变化与影响范围' },
          { label: '信用复核', summary: '承接客户信用和额度复审' },
        ],
      },
      {
        id: 'customer-delivery',
        title: '客户交付风险',
        owner: '业务交付组',
        summary: '客户优先级、交付承诺、延期风险、跨厂区协同',
        status: '设计中',
        statusTone: 'blue',
        stats: '风险客户 5 · 延期 3',
        icon: Users,
        route: getDepartmentRoute('sales-business', 'customer-delivery'),
        statusMetrics: [
          { label: '风险客户', value: '5', tone: 'amber' },
          { label: '延期', value: '3', tone: 'red' },
        ],
        todos: ['接入生产与 QA 风险信号', '区分集团客户和普通客户'],
        children: [
          { label: '客户清单', summary: '按客户等级和交付要求分层管理' },
          { label: '交付风险', summary: '识别延期、质量和产能风险' },
          { label: '跨厂协同', summary: '处理多厂区交付和资源协调' },
        ],
      },
    ],
    quickCandidates: ['合同台账', '客户信用门禁', '回款跟进', '交期预警'],
    permissionRows: [
      { role: '业务经理', view: true, edit: true, approve: true },
      { role: '业务员', view: true, edit: true, approve: false },
      { role: '总经理', view: true, edit: false, approve: true },
      { role: 'PMC', view: true, edit: false, approve: true },
    ],
    todos: [
      { id: 'BUS-118', title: '客户信用复核', meta: '上海联志 · 6 小时内需完成' },
      { id: 'BUS-131', title: '报价审批超时', meta: '2 单需重新拉通工程与 PMC' },
      { id: 'BUS-144', title: '交付承诺复核', meta: '华登厂区有 3 单延期风险' },
    ],
  },
}

export const approvalRows: ApprovalRow[] = [
  {
    id: 'HK-A-260626-018',
    customer: '宁波盛源',
    factory: '华康A',
    status: '待审批',
    statusTone: 'amber',
    owner: '李经理',
    sla: '2h',
    summary: '报价变更，需工程与 PMC 二次确认',
    amount: '¥ 428,600',
  },
  {
    id: 'HD-260626-044',
    customer: '广州嘉和',
    factory: '华登',
    status: '跟进中',
    statusTone: 'blue',
    owner: '周主管',
    sla: '8h',
    summary: '客户交期提前，生产排程待确认',
    amount: '¥ 213,900',
  },
  {
    id: 'HX-260626-071',
    customer: '深圳奥联',
    factory: '华兴',
    status: '风险',
    statusTone: 'red',
    owner: '王业务',
    sla: '1d',
    summary: 'QA 异常未关闭，不建议放行',
    amount: '¥ 601,240',
  },
  {
    id: 'HKB-260626-102',
    customer: '杭州凯铭',
    factory: '华康B',
    status: '已通过',
    statusTone: 'green',
    owner: '陈专员',
    sla: '完成',
    summary: '报价审批完成，等待合同归档',
    amount: '¥ 162,800',
  },
  {
    id: 'HKA-260626-118',
    customer: '上海联志',
    factory: '华康A',
    status: '跟进中',
    statusTone: 'blue',
    owner: '李经理',
    sla: '6h',
    summary: '客户信用额度需复核',
    amount: '¥ 89,300',
  },
]

export const approvalSteps: ApprovalStep[] = [
  { label: '业务提交', state: 'done', owner: '已完成' },
  { label: '工程确认', state: 'done', owner: '已完成' },
  { label: 'PMC 复核', state: 'active', owner: '进行中' },
  { label: '总经理审批', state: 'pending', owner: '待处理' },
]
