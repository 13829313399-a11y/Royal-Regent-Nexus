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
  Settings2,
  ShieldCheck,
  UserCog,
  Users,
  Wrench,
} from '@lucide/vue'

export type Tone = 'teal' | 'blue' | 'amber' | 'red' | 'slate' | 'green'

export type FactoryContextId = 'group' | 'huakang-a' | 'huakang-b' | 'huadeng' | 'huaxing'

export type ProductionFactoryContextId = Exclude<FactoryContextId, 'group'>

export type DepartmentId =
  | 'overview'
  | 'engineering'
  | 'pmc-warehouse'
  | 'production'
  | 'qa'
  | 'sales-business'

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

export interface EnterpriseModule {
  id: string
  title: string
  owner: string
  summary: string
  status: string
  statusTone: Tone
  stats: string
  icon: Component
  to?: string
}

export interface MoldingSampleSummary {
  label: string
  value: string
  detail: string
  tone: Tone
}

export interface MoldingSampleLine {
  id: string
  customerMoldNo: string
  moldName: string
  material: string
  color: string
  pms: string
  toner: string
  shotsPerSet: string
  quantity: number
  requiredDate: string
  owner: string
  status: string
  statusTone: Tone
}

export interface MoldingSampleOrder {
  customer: string
  productNo: string
  productName: string
  source: string
  documentNo: string
  requester: string
  requestDate: string
  requiredDate: string
  note: string
}

export interface MoldingProgressStage {
  label: string
  detail: string
  status: string
  tone: Tone
}

export interface MoldingSampleFactoryRecord {
  factoryId: ProductionFactoryContextId
  order: MoldingSampleOrder
  stages: MoldingProgressStage[]
  lines: MoldingSampleLine[]
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

export const productionFactoryContextIds: ProductionFactoryContextId[] = [
  'huakang-a',
  'huakang-b',
  'huadeng',
  'huaxing',
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

export const navigationGroups: NavigationGroup[] = [
  {
    label: 'MAIN',
    items: [
      { label: '管理驾驶舱', to: '/', icon: LayoutDashboard, departmentId: 'overview' },
      { label: '工程部', to: '/modules', icon: Wrench, departmentId: 'engineering' },
      { label: 'PMC / 仓管', to: '/modules', icon: Archive, departmentId: 'pmc-warehouse' },
      { label: '生产部', to: '/modules', icon: Boxes, departmentId: 'production' },
      { label: 'QA 部', to: '/modules', icon: ShieldCheck, departmentId: 'qa' },
      { label: '业务部', to: '/workbench', icon: ClipboardCheck, departmentId: 'sales-business' },
    ],
  },
  {
    label: 'CROSS FACTORY',
    items: [
      { label: '跨厂区审批', to: '/workbench', icon: GitBranch },
      { label: '异常与预警', to: '/workbench', icon: AlertTriangle },
      { label: '权限与组织', to: '/modules', icon: Users },
    ],
  },
  {
    label: 'CONFIG',
    items: [
      { label: '模块配置', to: '/modules', icon: Settings2 },
      { label: '角色权限', to: '/modules', icon: UserCog },
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

export const engineeringModules: EnterpriseModule[] = [
  {
    id: 'molding-sample',
    title: '啤办进度追踪',
    owner: '工程部 · 负责人 肖科',
    summary: '啤办单登记、颜色用料、试啤进度、出办确认',
    status: '已上线',
    statusTone: 'green',
    stats: '明细 14 · 风险 2',
    icon: ClipboardCheck,
    to: '/modules/molding-sample',
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
  },
]

export const moldingSampleOrder: MoldingSampleOrder = {
  customer: 'BuzzBee',
  productNo: '62437',
  productName: '链条枪',
  source: '62437三弹、四弹枪新色啤办单',
  documentNo: 'W-G026-00',
  requester: '肖科',
  requestDate: '2026-04-09',
  requiredDate: '2026-04-13',
  note: '见客样办，枪身不可刮花，颜色要对办，工程订色粉。',
}

export const moldingSampleSummary: MoldingSampleSummary[] = [
  { label: '啤办单', value: '62437', detail: 'BuzzBee · 链条枪', tone: 'teal' },
  { label: '明细行', value: '14', detail: '按模具与颜色拆分', tone: 'blue' },
  { label: '目标啤数', value: '420', detail: '14项 × 30啤', tone: 'green' },
  { label: '需办日期', value: '04-13', detail: '落单 2026-04-09', tone: 'amber' },
]

export const moldingProgressStages: MoldingProgressStage[] = [
  { label: '通知单导入', detail: 'Excel 字段已拆成单头和明细', status: '完成', tone: 'green' },
  { label: '备料配色', detail: '色粉 71120 / 71139 / 70040 / 70039 / 71137', status: '进行中', tone: 'blue' },
  { label: '排机试啤', detail: '按模具与颜色逐项登记现场状态', status: '待排程', tone: 'amber' },
  { label: 'QA 对办', detail: '颜色、刮花、外观按客样确认', status: '待确认', tone: 'slate' },
]

export const moldingSampleLines: MoldingSampleLine[] = [
  {
    id: 'BP-62437-001',
    customerMoldNo: 'BBT62450-A-01',
    moldName: '左右枪身A款',
    material: 'HIPS 425',
    color: '深绿色',
    pms: '2272C',
    toner: '71139',
    shotsPerSet: '1/1',
    quantity: 30,
    requiredDate: '2026-04-13',
    owner: '肖科',
    status: '待排机',
    statusTone: 'amber',
  },
  {
    id: 'BP-62437-002',
    customerMoldNo: 'BBT62450-A-02',
    moldName: 'A款装饰件',
    material: 'ABS 740',
    color: '暗蓝色',
    pms: '2935C',
    toner: '71120',
    shotsPerSet: '1/1',
    quantity: 30,
    requiredDate: '2026-04-13',
    owner: '肖科',
    status: '配色中',
    statusTone: 'blue',
  },
  {
    id: 'BP-62437-003',
    customerMoldNo: 'BBT62450-A-02-2',
    moldName: '手柄饰件',
    material: 'ABS 740',
    color: '暗蓝色',
    pms: '2935C',
    toner: '71120',
    shotsPerSet: '1/1',
    quantity: 30,
    requiredDate: '2026-04-13',
    owner: '肖科',
    status: '配色中',
    statusTone: 'blue',
  },
  {
    id: 'BP-62437-004',
    customerMoldNo: 'BBT62450-B-01',
    moldName: '左右枪身B款',
    material: 'HIPS 425',
    color: '暗蓝色',
    pms: '2935C',
    toner: '70039',
    shotsPerSet: '1/1',
    quantity: 30,
    requiredDate: '2026-04-13',
    owner: '肖科',
    status: '待试啤',
    statusTone: 'amber',
  },
  {
    id: 'BP-62437-005',
    customerMoldNo: 'BBT62450-B-02',
    moldName: 'B款装饰件',
    material: 'ABS 740',
    color: '深绿色',
    pms: '2272C',
    toner: '70040',
    shotsPerSet: '1/1',
    quantity: 30,
    requiredDate: '2026-04-13',
    owner: '肖科',
    status: '待试啤',
    statusTone: 'amber',
  },
  {
    id: 'BP-62437-006',
    customerMoldNo: 'BBT62450-04',
    moldName: '拉环',
    material: 'PP AV161',
    color: '深蓝色',
    pms: '7694C',
    toner: '71137',
    shotsPerSet: '1/1',
    quantity: 30,
    requiredDate: '2026-04-13',
    owner: '肖科',
    status: '已备料',
    statusTone: 'green',
  },
  {
    id: 'BP-62437-007',
    customerMoldNo: 'BBT62659-01',
    moldName: '左右枪身',
    material: 'HIPS 425',
    color: '暗蓝色',
    pms: '2935C',
    toner: '70039',
    shotsPerSet: '1/1',
    quantity: 30,
    requiredDate: '2026-04-13',
    owner: '肖科',
    status: '试啤中',
    statusTone: 'teal',
  },
  {
    id: 'BP-62437-008',
    customerMoldNo: 'BBT62659-01',
    moldName: '左右枪身',
    material: 'HIPS 425',
    color: '深绿色',
    pms: '2272C',
    toner: '71139',
    shotsPerSet: '1/1',
    quantity: 30,
    requiredDate: '2026-04-13',
    owner: '肖科',
    status: '颜色复核',
    statusTone: 'red',
  },
  {
    id: 'BP-62437-009',
    customerMoldNo: 'BBT62659-02',
    moldName: '左右手柄',
    material: 'ABS 740',
    color: '暗蓝色',
    pms: '2935C',
    toner: '71120',
    shotsPerSet: '1/1',
    quantity: 30,
    requiredDate: '2026-04-13',
    owner: '肖科',
    status: '待试啤',
    statusTone: 'amber',
  },
  {
    id: 'BP-62437-010',
    customerMoldNo: 'BBT62659-02',
    moldName: '左右手柄',
    material: 'ABS 740',
    color: '深绿色',
    pms: '2272C',
    toner: '70040',
    shotsPerSet: '1/1',
    quantity: 30,
    requiredDate: '2026-04-13',
    owner: '肖科',
    status: '待配色',
    statusTone: 'blue',
  },
  {
    id: 'BP-62437-011',
    customerMoldNo: 'BBT62659-03',
    moldName: '左右枪身装饰件',
    material: 'ABS 740',
    color: '暗蓝色',
    pms: '2935C',
    toner: '71120',
    shotsPerSet: '1/1',
    quantity: 30,
    requiredDate: '2026-04-13',
    owner: '肖科',
    status: '试啤中',
    statusTone: 'teal',
  },
  {
    id: 'BP-62437-012',
    customerMoldNo: 'BBT62659-03',
    moldName: '左右枪身装饰件',
    material: 'ABS 740',
    color: '深绿色',
    pms: '2272C',
    toner: '70040',
    shotsPerSet: '1/1',
    quantity: 30,
    requiredDate: '2026-04-13',
    owner: '肖科',
    status: '颜色复核',
    statusTone: 'red',
  },
  {
    id: 'BP-62437-013',
    customerMoldNo: 'BBT62659-04',
    moldName: '左右枪身长装饰件',
    material: 'PP AV161',
    color: '暗蓝色',
    pms: '2935C',
    toner: '71120',
    shotsPerSet: '1/1',
    quantity: 30,
    requiredDate: '2026-04-13',
    owner: '肖科',
    status: '待试啤',
    statusTone: 'amber',
  },
  {
    id: 'BP-62437-014',
    customerMoldNo: 'BBT62659-04',
    moldName: '左右枪身长装饰件',
    material: 'PP AV161',
    color: '深绿色',
    pms: '2272C',
    toner: '70040',
    shotsPerSet: '1/1',
    quantity: 30,
    requiredDate: '2026-04-13',
    owner: '肖科',
    status: '待配色',
    statusTone: 'blue',
  },
]

const huakangBMoldingSampleOrder: MoldingSampleOrder = {
  customer: 'Zuru',
  productNo: '73120',
  productName: '泡泡枪',
  source: '73120双色泡泡枪啤办单',
  documentNo: 'W-G031-00',
  requester: '林科',
  requestDate: '2026-04-11',
  requiredDate: '2026-04-16',
  note: '透明件不可混点，外壳蓝色需按首办确认，试啤后交 QA 留样。',
}

const huakangBMoldingSampleLines: MoldingSampleLine[] = [
  {
    id: 'BP-73120-001',
    customerMoldNo: 'ZUR73120-01',
    moldName: '左右外壳',
    material: 'ABS 757',
    color: '湖蓝色',
    pms: '2995C',
    toner: '81210',
    shotsPerSet: '1/1',
    quantity: 40,
    requiredDate: '2026-04-16',
    owner: '林科',
    status: '试啤中',
    statusTone: 'teal',
  },
  {
    id: 'BP-73120-002',
    customerMoldNo: 'ZUR73120-02',
    moldName: '透明水箱',
    material: 'PC 110',
    color: '透明',
    pms: 'Clear',
    toner: 'N/A',
    shotsPerSet: '1/1',
    quantity: 40,
    requiredDate: '2026-04-16',
    owner: '林科',
    status: '外观复核',
    statusTone: 'red',
  },
  {
    id: 'BP-73120-003',
    customerMoldNo: 'ZUR73120-03',
    moldName: '扳机',
    material: 'POM 900P',
    color: '白色',
    pms: 'White',
    toner: '81002',
    shotsPerSet: '1/1',
    quantity: 40,
    requiredDate: '2026-04-16',
    owner: '林科',
    status: '已备料',
    statusTone: 'green',
  },
  {
    id: 'BP-73120-004',
    customerMoldNo: 'ZUR73120-04',
    moldName: '装饰盖',
    material: 'ABS 757',
    color: '橙色',
    pms: '1655C',
    toner: '81233',
    shotsPerSet: '1/1',
    quantity: 40,
    requiredDate: '2026-04-16',
    owner: '林科',
    status: '待排机',
    statusTone: 'amber',
  },
]

const huadengMoldingSampleOrder: MoldingSampleOrder = {
  customer: 'Spin Master',
  productNo: '90818',
  productName: '飞盘发射器',
  source: '90818新款飞盘发射器啤办单',
  documentNo: 'W-G041-00',
  requester: '周工',
  requestDate: '2026-04-12',
  requiredDate: '2026-04-18',
  note: '结构件需先确认装配间隙，齿轮件试啤后提交寿命测试样。',
}

const huadengMoldingSampleLines: MoldingSampleLine[] = [
  {
    id: 'BP-90818-001',
    customerMoldNo: 'SM90818-01',
    moldName: '上盖',
    material: 'ABS 747',
    color: '石墨灰',
    pms: 'Cool Gray 10C',
    toner: '92018',
    shotsPerSet: '1/1',
    quantity: 25,
    requiredDate: '2026-04-18',
    owner: '周工',
    status: '已出办',
    statusTone: 'green',
  },
  {
    id: 'BP-90818-002',
    customerMoldNo: 'SM90818-02',
    moldName: '下盖',
    material: 'ABS 747',
    color: '石墨灰',
    pms: 'Cool Gray 10C',
    toner: '92018',
    shotsPerSet: '1/1',
    quantity: 25,
    requiredDate: '2026-04-18',
    owner: '周工',
    status: '已出办',
    statusTone: 'green',
  },
  {
    id: 'BP-90818-003',
    customerMoldNo: 'SM90818-03',
    moldName: '齿轮组',
    material: 'POM 100P',
    color: '本色',
    pms: 'Natural',
    toner: 'N/A',
    shotsPerSet: '1/1',
    quantity: 30,
    requiredDate: '2026-04-18',
    owner: '周工',
    status: '寿命测试',
    statusTone: 'blue',
  },
  {
    id: 'BP-90818-004',
    customerMoldNo: 'SM90818-04',
    moldName: '安全锁',
    material: 'PP K8003',
    color: '红色',
    pms: '186C',
    toner: '92044',
    shotsPerSet: '1/1',
    quantity: 30,
    requiredDate: '2026-04-18',
    owner: '周工',
    status: '待 QA',
    statusTone: 'amber',
  },
]

const huaxingMoldingSampleOrder: MoldingSampleOrder = {
  customer: 'Target',
  productNo: '56206',
  productName: '软弹枪',
  source: '56206软弹枪配色啤办单',
  documentNo: 'W-G052-00',
  requester: '陈科',
  requestDate: '2026-04-10',
  requiredDate: '2026-04-15',
  note: '枪身表面不可刮花，橙色枪口为安全色，颜色偏差需当天复核。',
}

const huaxingMoldingSampleLines: MoldingSampleLine[] = [
  {
    id: 'BP-56206-001',
    customerMoldNo: 'TGT56206-01',
    moldName: '左右枪身',
    material: 'HIPS 425',
    color: '军绿色',
    pms: '5743C',
    toner: '76012',
    shotsPerSet: '1/1',
    quantity: 35,
    requiredDate: '2026-04-15',
    owner: '陈科',
    status: '颜色复核',
    statusTone: 'red',
  },
  {
    id: 'BP-56206-002',
    customerMoldNo: 'TGT56206-02',
    moldName: '枪口',
    material: 'ABS 740',
    color: '安全橙',
    pms: 'Orange 021C',
    toner: '76088',
    shotsPerSet: '1/1',
    quantity: 35,
    requiredDate: '2026-04-15',
    owner: '陈科',
    status: '待试啤',
    statusTone: 'amber',
  },
  {
    id: 'BP-56206-003',
    customerMoldNo: 'TGT56206-03',
    moldName: '弹匣',
    material: 'PP AV161',
    color: '黑色',
    pms: 'Black C',
    toner: '76001',
    shotsPerSet: '1/1',
    quantity: 35,
    requiredDate: '2026-04-15',
    owner: '陈科',
    status: '试啤中',
    statusTone: 'teal',
  },
  {
    id: 'BP-56206-004',
    customerMoldNo: 'TGT56206-04',
    moldName: '装饰件',
    material: 'ABS 740',
    color: '浅灰色',
    pms: '421C',
    toner: '76032',
    shotsPerSet: '1/1',
    quantity: 35,
    requiredDate: '2026-04-15',
    owner: '陈科',
    status: '颜色复核',
    statusTone: 'red',
  },
]

export const moldingSampleFactoryRecords: Record<ProductionFactoryContextId, MoldingSampleFactoryRecord> = {
  'huakang-a': {
    factoryId: 'huakang-a',
    order: moldingSampleOrder,
    stages: moldingProgressStages,
    lines: moldingSampleLines,
  },
  'huakang-b': {
    factoryId: 'huakang-b',
    order: huakangBMoldingSampleOrder,
    stages: moldingProgressStages,
    lines: huakangBMoldingSampleLines,
  },
  huadeng: {
    factoryId: 'huadeng',
    order: huadengMoldingSampleOrder,
    stages: moldingProgressStages,
    lines: huadengMoldingSampleLines,
  },
  huaxing: {
    factoryId: 'huaxing',
    order: huaxingMoldingSampleOrder,
    stages: moldingProgressStages,
    lines: huaxingMoldingSampleLines,
  },
}

export function isProductionFactoryContextId(factoryId: string): factoryId is ProductionFactoryContextId {
  return productionFactoryContextIds.includes(factoryId as ProductionFactoryContextId)
}

export function getMoldingSampleRecord(factoryId: FactoryContextId | string | undefined) {
  const resolvedFactoryId = isProductionFactoryContextId(factoryId ?? '')
    ? factoryId as ProductionFactoryContextId
    : 'huakang-a'

  return moldingSampleFactoryRecords[resolvedFactoryId]
}

export function getMoldingSampleModuleStats(factoryId: FactoryContextId | string | undefined) {
  const record = getMoldingSampleRecord(factoryId)
  const riskCount = record.lines.filter((line) => line.statusTone === 'red').length

  return `明细 ${record.lines.length} · 风险 ${riskCount}`
}

export const permissionRows: PermissionRow[] = [
  { role: '工程主管', view: true, edit: true, approve: true },
  { role: '工程师', view: true, edit: true, approve: false },
  { role: '生产主管', view: true, edit: false, approve: true },
  { role: 'QA 主管', view: true, edit: false, approve: true },
]

export const departmentTodos: TodoItem[] = [
  { id: 'ECN-260626-014', title: '变更影响确认', meta: '华康A · 生产/QA 待确认' },
  { id: 'BOM-PA-802', title: '版本发布', meta: '工程主管审批 · 今日到期' },
  { id: 'M-771', title: '保养异常', meta: '设备维护 · 待分派' },
]

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

export const quickModuleCandidates = [
  '工程问题单',
  '样品承认书',
  '物料替代申请',
  '客户图纸评审',
]
