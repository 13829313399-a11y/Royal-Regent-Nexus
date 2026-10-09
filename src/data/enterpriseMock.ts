import type { Component } from 'vue'
import {
  AlertTriangle,
  Archive,
  Boxes,
  Calculator,
  CalendarCheck2,
  CalendarClock,
  ClipboardCheck,
  FileSpreadsheet,
  FileStack,
  GitBranch,
  LayoutDashboard,
  Network,
  PackageCheck,
  Printer,
  Scissors,
  Settings2,
  Ship,
  ShieldCheck,
  UserCog,
  Users,
  Wrench,
} from '@lucide/vue'

export type Tone = 'teal' | 'blue' | 'amber' | 'red' | 'slate' | 'green'

export type FactoryContextId = 'group' | 'huakang-a' | 'huakang-b' | 'huakang-c' | 'huakang-d' | 'huadeng' | 'huaxing'

export type ProductionFactoryContextId = Exclude<FactoryContextId, 'group'>

export type DepartmentId =
  | 'overview'
  | 'engineering'
  | 'pmc-warehouse'
  | 'production'
  | 'qa'
  | 'qc'
  | 'sales-business'
  | 'accounting'

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
  permissions?: string[]
  preserveFactory?: boolean
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
  detailPage?: boolean
  statusMetrics: ModuleStatusMetric[]
  todos: string[]
  children: ModuleChildLink[]
  factoryIds?: FactoryContextId[]
  permissions?: string[]
  strictAccess?: boolean
  permissionDepartment?: string
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
  'qc',
  'sales-business',
  'accounting',
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
    id: 'huakang-c',
    name: '华康C',
    shortName: '华康C',
    description: '扩产筹备与产线协同厂区',
    health: 88,
    tone: 'blue',
  },
  {
    id: 'huakang-d',
    name: '华康D',
    shortName: '华康D',
    description: '新建产能与质量导入厂区',
    health: 86,
    tone: 'teal',
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
  'huakang-c',
  'huakang-d',
  'huadeng',
  'huaxing',
]

export function isFactoryContextId(factoryId: string): factoryId is FactoryContextId {
  return factoryContexts.some((factory) => factory.id === factoryId)
}

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
    focus: '纸箱采购、库存、收发、齐套风险',
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
    id: 'qc',
    name: 'QC 部',
    shortName: 'QC',
    focus: '验货总排期、临时加单、验货执行、问题处理与汇总报表',
  },
  {
    id: 'sales-business',
    name: '业务部',
    shortName: '业务',
    focus: '客户、报价、内部定价、印尼物料和 PO 排期协同',
  },
  {
    id: 'accounting',
    name: '会计部',
    shortName: '会计',
    focus: '应收应付、费用、资金与月结协同',
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

export function getFactoryScopedRoute(route: string, factoryId: FactoryContextId) {
  const [path, rawQuery = ''] = route.split('?', 2)
  const query = new URLSearchParams(rawQuery)
  query.set('factory', factoryId)
  return `${path}?${query.toString()}`
}

const factoryTextAliases: Record<ProductionFactoryContextId, string[]> = {
  'huakang-a': ['华康A', '华康 A', 'A厂', 'A 厂'],
  'huakang-b': ['华康B', '华康 B', 'B厂', 'B 厂'],
  'huakang-c': ['华康C', '华康 C', 'C厂', 'C 厂'],
  'huakang-d': ['华康D', '华康 D', 'D厂', 'D 厂'],
  huadeng: ['华登'],
  huaxing: ['华兴'],
}

function resolveProductionFactoryContextId(factoryId: FactoryContextId): ProductionFactoryContextId {
  return productionFactoryContextIds.includes(factoryId as ProductionFactoryContextId)
    ? factoryId as ProductionFactoryContextId
    : 'huaxing'
}

export function isFactoryScopedTextVisible(text: string, factoryId: FactoryContextId) {
  const resolvedFactoryId = resolveProductionFactoryContextId(factoryId)
  const referencedFactories = productionFactoryContextIds.filter((candidateFactoryId) =>
    factoryTextAliases[candidateFactoryId].some((alias) => text.includes(alias)),
  )

  return referencedFactories.length === 0 || referencedFactories.includes(resolvedFactoryId)
}

export function getFactoryScopedTodoItems(
  todos: TodoItem[],
  factoryId: FactoryContextId,
) {
  const resolvedFactoryId = resolveProductionFactoryContextId(factoryId)
  if (resolvedFactoryId === 'huakang-c' || resolvedFactoryId === 'huakang-d') {
    return []
  }

  return todos.filter((todo) =>
    isFactoryScopedTextVisible(`${todo.title} ${todo.meta}`, resolvedFactoryId),
  )
}

export function getFactoryScopedModule(
  module: EnterpriseModule,
  factoryId: FactoryContextId,
): EnterpriseModule {
  const resolvedFactoryId = resolveProductionFactoryContextId(factoryId)
  const isNewFactoryContext = resolvedFactoryId === 'huakang-c' || resolvedFactoryId === 'huakang-d'
  const usesSharedRawMaterialCatalog = module.id === 'raw-material-management'
  const usesIndependentEmptyState = isNewFactoryContext && !usesSharedRawMaterialCatalog
  const factoryName = factoryContexts.find((factory) => factory.id === resolvedFactoryId)?.shortName ?? resolvedFactoryId

  return {
    ...module,
    href: module.href && !/^https?:\/\//i.test(module.href)
      ? getFactoryScopedRoute(module.href, resolvedFactoryId)
      : module.href,
    route: module.route ? getFactoryScopedRoute(module.route, resolvedFactoryId) : undefined,
    stats: usesSharedRawMaterialCatalog && isNewFactoryContext
      ? `${factoryName} · 公共原料资料已接入`
      : usesIndependentEmptyState
        ? `${factoryName} · 当前暂无本厂数据`
        : module.stats,
    statusMetrics: module.statusMetrics.map((metric) => {
      if (usesSharedRawMaterialCatalog && isNewFactoryContext) {
        return metric.label === '原料'
          ? { ...metric, value: '共享', tone: 'teal' }
          : { ...metric, value: '—', tone: 'slate' }
      }

      return usesIndependentEmptyState
        ? { ...metric, value: '—', tone: 'slate' }
        : { ...metric }
    }),
    todos: isNewFactoryContext
      ? []
      : module.todos.filter((todo) => isFactoryScopedTextVisible(todo, resolvedFactoryId)),
    children: module.children.map((child) => ({
      ...child,
      route: child.route ? getFactoryScopedRoute(child.route, resolvedFactoryId) : undefined,
    })),
  }
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
      { label: 'QC 部', to: getDepartmentRoute('qc'), icon: CalendarCheck2, departmentId: 'qc' },
      { label: '业务部', to: getDepartmentRoute('sales-business'), icon: ClipboardCheck, departmentId: 'sales-business' },
      { label: '会计部', to: getDepartmentRoute('accounting'), icon: Calculator, departmentId: 'accounting' },
    ],
  },
  {
    label: 'TOOLS',
    items: [
      { label: '公共工具栏', to: '/tools', icon: FileSpreadsheet, preserveFactory: true },
    ],
  },
  {
    label: 'CROSS FACTORY',
    items: [
      { label: '跨厂区审批', to: '/workbench', icon: GitBranch },
      { label: '异常与预警', to: '/workbench', icon: AlertTriangle },
      { label: '权限与组织', to: '/system/users', icon: Users, permissions: ['system:user_manage'] },
    ],
  },
  {
    label: 'CONFIG',
    items: [
      { label: '模块配置', to: getDepartmentRoute('production'), icon: Settings2, departmentId: 'production' },
      { label: '内置职位权限', to: '/system/iam/roles', icon: UserCog, permissions: ['system:permission_catalog_read'] },
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

/**
 * QC owns this domain. QA may still surface the shared inspection entry as a
 * cross-department public link, without sharing QC data or authorization scope.
 */
export const qcInspectionOperationsModule: EnterpriseModule = {
  id: 'inspection-operations',
  title: 'QC 验货工作台',
  owner: 'QC 部 / 业务部协同',
  summary: '按客户管理总排期，批量导入未走货订单，跟进验货与问题处理',
  status: '待部署',
  statusTone: 'amber',
  stats: '正式数据以 QC 接口为准',
  icon: CalendarCheck2,
  route: '/modules/qc/inspection-operations',
  statusMetrics: [
    { label: '入口', value: '4 类', tone: 'teal' },
    { label: '范围', value: '本厂', tone: 'blue' },
    { label: '导入', value: '批量勾选', tone: 'slate' },
  ],
  todos: [
    '导入未走货订单并批量勾选确认',
    '完成验货结果和问题单点录入闭环',
    '按客户筛选排期并生成验货报表',
  ],
  children: [
    { label: '验货总排期', route: '/modules/qc/inspection-operations' },
    { label: '排期明细', route: '/modules/qc/inspection-operations/schedule-details' },
    { label: '问题闭环', route: '/modules/qc/inspection-operations/problems' },
    { label: '报表中心', route: '/modules/qc/inspection-operations/reports' },
  ],
}

export const qcCartonMarkVerificationModule: EnterpriseModule = {
  id: 'carton-mark-check',
  title: '箱唛核验',
  owner: 'QC / 纸箱部协同',
  summary: '承接纸箱部已核对的打印 PDF，使用现场箱唛照片逐项核验文字内容',
  status: '建设中',
  statusTone: 'blue',
  stats: '打印 PDF · 现场照片',
  icon: PackageCheck,
  route: getDepartmentRoute('qc', 'carton-mark-check'),
  statusMetrics: [
    { label: '基准', value: 'PDF', tone: 'blue' },
    { label: '现场', value: '照片', tone: 'teal' },
    { label: '比对', value: '逐项', tone: 'amber' },
  ],
  todos: ['接收纸箱部核对通过的打印 PDF', '上传现场正唛与侧唛照片', '复核并处理文字差异'],
  children: [
    { label: '打印 PDF', summary: '只接收纸箱部已完成 Excel–PDF 文字核对的版本' },
    { label: '现场拍照', summary: 'QC 上传纸箱现场正唛、侧唛照片' },
    { label: '逐项核验', summary: '使用打印 PDF 与现场照片逐项核验并保留结果' },
  ],
}

export const departmentModuleRegistry: Record<ModuleDepartmentId, DepartmentModuleRegistryEntry> = {
  engineering: {
    departmentId: 'engineering',
    heroTitle: '工程模块中心',
    heroSubtitle: '先把入口、权限、状态、待办、跨部门影响统一起来',
    panelTitle: '工程部模块',
    panelSubtitle: '面向 BOM、资料、变更和设备维保的统一模块层',
    modules: [
      {
        id: 'molding-sample',
        title: '啤办进度追踪',
        owner: '工程部 · 负责人 肖科',
        summary: '啤办单登记、颜色用料、试啤进度、出办确认',
        status: '已上线',
        statusTone: 'green',
        stats: '明细 14 · 风险 2',
        icon: ClipboardCheck,
        route: '/modules/molding-sample',
        statusMetrics: [
          { label: '明细', value: '14', tone: 'blue' },
          { label: '风险', value: '2', tone: 'red' },
          { label: '厂区', value: '6', tone: 'teal' },
        ],
        todos: ['按厂区切换啤办单明细', '补 QA 对办与出办留样闭环'],
        children: [
          { label: '通知单导入', summary: '拆分啤办单头与明细字段，统一导入来源' },
          { label: '试啤进度', summary: '按模具、颜色、色粉与状态追踪试啤过程' },
          { label: 'QA 对办', summary: '沉淀颜色、外观和留样确认节点' },
        ],
      },
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
    heroSubtitle: '统一进入纸箱、布料与半成品仓库，跟进到货、收发和月结',
    panelTitle: 'PMC / 仓管模块',
    panelSubtitle: '按仓库办理业务，各入口标明当前开放范围',
    modules: [
      {
        id: 'fabric-warehouse', title: '布料仓', owner: '华康C · 仓管',
        summary: '采购来源、布料辅料收发、批次与缸号库存，沿用纸箱工作区操作方式',
        status: '采购与入库可用', statusTone: 'teal', stats: '七个工作区 · 追货与实收入库',
        icon: Boxes, route: '/modules/pmc-warehouse/fabric-warehouse',
        detailPage: false, factoryIds: ['huakang-c'], statusMetrics: [], todos: [], children: [],
      },
      {
        id: 'semi-finished-warehouse', title: '半成品仓', owner: '华康C · 仓管',
        summary: '加工回货、多轮发出与回收、在外跟进、返修和包装交接',
        status: '框架预览', statusTone: 'amber', stats: '八个工作区 · 加工流转待接入',
        icon: Archive, route: '/modules/pmc-warehouse/semi-finished-warehouse',
        detailPage: false, factoryIds: ['huakang-c'], statusMetrics: [], todos: [], children: [],
      },
      {
        id: 'carton-procurement',
        title: '纸箱采购协同',
        owner: '纸箱下单 / 采购 / 仓管',
        summary: '人工录单、历史规格复用、交期跟进、分批收料、库存月结与齐套反馈',
        status: '核心闭环',
        statusTone: 'green',
        stats: '订单 · 收料 · 库存 · 月结已持久化',
        icon: PackageCheck,
        route: getDepartmentRoute('pmc-warehouse', 'carton-procurement'),
        statusMetrics: [
          { label: '订单', value: '人工确认', tone: 'teal' },
          { label: '供应商', value: '固定 1 家', tone: 'blue' },
          { label: '台账', value: '后端持久化', tone: 'green' },
        ],
        todos: [
          '确认客户主数据唯一编码和历史数据补齐规则',
          '确认验货期、内部要求到货日与供应商承诺交期的维护关系',
          '确认包装物数量换算、必需清单和库存唯一记账来源',
        ],
        children: [
          { label: '工作台', summary: '集中展示待办、交期预警、疑似漏单、收料异常、库存与月结概览' },
          { label: '纸箱订单', summary: '承接人工录单、连续录入、历史规格复用、订单变更与采购单打印' },
          { label: '每周核对', summary: '按客户导入排期并识别漏单、数量差异、交期变化和多匹配' },
          { label: '交期管理', summary: '维护承诺交期和内部到货要求，形成逾期与装配缺料提醒' },
          { label: '收料管理', summary: '保留送货单或照片凭证，人工确认实收、破损、拒收与有效数量' },
          { label: '库存管理', summary: '通过入库、出库、调拨、盘点、退货和冲销流水计算库存余额' },
          { label: '月结管理', summary: '按月份与客户核对期初、入库、出库、调整、期末数量和金额' },
          { label: '基础资料', summary: '维护客户、固定纸箱供应商、货号、包装物类型、规格版本与仓位' },
          { label: '报表中心', summary: '提供客户订单、交期、收料、库存、月结、齐套和交付质量报表' },
          { label: '系统协同', summary: '向订单处理中心与装配车间回写下单、到货、齐套和缺料风险状态' },
        ],
      },
      {
        id: 'carton-supplier',
        title: '供应商协同',
        owner: '东康供应商 / 仓管',
        summary: '按模块权限查看已下单采购单、确认交期和登记发货；内部仓管核实收料',
        status: '已接入',
        statusTone: 'teal',
        stats: '已发行订单 · 供应商发货 · 仓管核实',
        icon: PackageCheck,
        route: '/carton-supplier',
        statusMetrics: [
          { label: '订单', value: '已发行', tone: 'teal' },
          { label: '供应商', value: '权限开通', tone: 'blue' },
          { label: '收料', value: '仓管核实', tone: 'green' },
        ],
        todos: [],
        children: [
          { label: '采购单', summary: '仅查看东康已下单厂区的采购单' },
          { label: '交期与发货', summary: '供应商确认纸品交期并登记实际发货' },
          { label: '仓库反馈', summary: '内部仓管核实实收并反馈差异' },
        ],
      },
      {
        id: 'carton-mark-check',
        title: '箱唛资料模板',
        owner: '纸箱部仓管',
        summary: '客人 PO 箱唛 Excel 与排版 PDF 核对，确认文字不变后流转 QC 实拍核验',
        status: '建设中',
        statusTone: 'blue',
        stats: 'Excel → PDF → QC',
        icon: PackageCheck,
        route: getDepartmentRoute('pmc-warehouse', 'carton-mark-check'),
        statusMetrics: [
          { label: '客人原稿', value: 'Excel', tone: 'teal' },
          { label: '印刷箱唛', value: 'PDF', tone: 'blue' },
          { label: '流转', value: 'QC', tone: 'amber' },
        ],
        todos: ['上传客人 PO 箱唛 Excel', '核对排版 PDF 的文字内容', '把核对后的 PDF 流转给 QC 实拍核验'],
        children: [
          { label: '客人 Excel', summary: '按客户、合同号和 ITEM 保存客人提供的 PO 箱唛原稿' },
          { label: '印刷 PDF', summary: '保存调整空间排版并增加图案后的待印刷箱唛文档' },
          { label: '内容核对', summary: '逐项比较 Excel 与 PDF 的文字内容，排版和新增图案不作为差异' },
          { label: 'QC 流转', summary: '内容核对后流转 PDF，由 QC 使用 PDF 与现场照片核验' },
        ],
      },
      {
        id: 'raw-material-management',
        title: '原料管理模块',
        owner: '仓库原料台',
        summary: '原料资料、仓库领料、库存批次与库存流水统一管理',
        status: '建设中',
        statusTone: 'blue',
        stats: '原料 34 · 低库 3',
        icon: Boxes,
        route: getDepartmentRoute('pmc-warehouse', 'raw-material-management'),
        statusMetrics: [
          { label: '原料', value: '34', tone: 'teal' },
          { label: '待出库', value: '5', tone: 'amber' },
          { label: '低库存', value: '3', tone: 'red' },
        ],
        todos: ['补原料主数据模型', '领料单对接库存扣减', '批次流水接正式接口'],
        children: [
          { label: '原料资料', summary: '维护物料编号、类别、供应商、单价和安全库存' },
          { label: '仓库领料单', summary: '承接啤办领料、确认出库和撤回流水' },
          { label: '库存批次', summary: '管理批次号、库位、可用重量和消耗进度' },
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
    heroSubtitle: '集中承载生产计划、车间执行、任务回报和外发协同',
    panelTitle: '生产部模块',
    panelSubtitle: '承载生产计划、啤办任务和各车间生产管理模块',
    modules: [
      {
        id: 'injection-scheduling',
        title: '注塑排产中枢',
        owner: '啤机部 / PMC',
        summary: '四厂独立排产、共享模具资料，连接计划表、现场开工和白夜班报数',
        status: '业务工作台',
        statusTone: 'teal',
        stats: '真实排程 · 班次累计报工',
        route: getDepartmentRoute('production', 'injection-scheduling'),
        permissions: ['injection_scheduling:read'],
        icon: CalendarClock,
        statusMetrics: [
          { label: '排程', value: '机台甘特', tone: 'teal' },
          { label: '执行', value: '白夜报工', tone: 'teal' },
          { label: '资料', value: '四厂共享模具', tone: 'slate' },
        ],
        todos: ['查看未排需求与交期风险', '填写实际开工和班次累计数'],
        children: [
          { label: '排程工作台', summary: '机台甘特、自动排产与手动调整' },
          { label: '全字段计划表', summary: '精确查询、参数维护与 Excel 往返' },
          { label: '现场执行', summary: '开工、转机、白夜班报数与滚动回算' },
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
        todos: ['补生产执行数据衔接', '补跨厂区计划对比'],
        children: [
          { label: '月计划', summary: '承接月度排产与产能拆分' },
          { label: '日计划', summary: '细化到日的执行计划和插单处理' },
          { label: '计划对比', summary: '比较计划、实际与跨厂调度差异' },
        ],
      },
      {
        id: 'three-d-printing',
        title: '3D打印机管理',
        owner: '华康A · 3D部门',
        summary: '打印机实时状态、生产记录、产品图片、物料库存、计划和维护统一管理',
        status: '正式上线',
        statusTone: 'green',
        stats: '11 台打印机 · 云端历史 · 边缘控制',
        icon: Printer,
        route: '/modules/production/three-d-printing',
        factoryIds: ['huakang-a'],
        permissions: ['three_d_printing:read'],
        strictAccess: true,
        permissionDepartment: 'three-d-printing',
        statusMetrics: [
          { label: '机台', value: '11', tone: 'teal' },
          { label: '数据', value: '云端', tone: 'blue' },
          { label: '控制', value: '管理员', tone: 'amber' },
        ],
        todos: ['完成边缘代理现场验收', '正式切换前执行旧系统只读窗口与最终迁移'],
        children: [
          { label: '打印机看板', summary: '查看局域网设备实时状态、进度和温度' },
          { label: '生产记录', summary: '保留旧历史并支持设备自动建单' },
          { label: '产品与图片', summary: '图片独立持久化，避免整库保存失败' },
          { label: '物料与仓库', summary: '库存快照、入库和消耗流水可追溯' },
          { label: '计划与维护', summary: '生产计划和机台维护成本统一管理' },
        ],
      },
      {
        id: 'molding-sample-production-task',
        title: '啤办生产任务单',
        owner: '啤机部 / 工程部',
        summary: '接收工程啤办单通知、啤机执行、用料费用回填、完成回传',
        status: '已接入',
        statusTone: 'green',
        stats: '待接收 2 · 生产中 1',
        icon: ClipboardCheck,
        route: '/modules/production/molding-sample-tasks',
        statusMetrics: [
          { label: '通知', value: '2', tone: 'blue' },
          { label: '执行', value: '1', tone: 'amber' },
          { label: '回传', value: '1', tone: 'green' },
        ],
        todos: ['接收工程新建啤办单通知', '啤机完成后回传状态和用料费用'],
        children: [
          { label: '任务通知', summary: '工程新建或审核流转后，生产任务单可以看到对应啤办单' },
          { label: '啤机执行', summary: '啤机部按单据明细回填实际用料、啤办费用和问题反馈' },
          { label: '完成回传', summary: '生产完成后把状态、完成日期和执行记录回传到工程啤办单' },
        ],
      },
      {
        id: 'cutting',
        title: '裁床部',
        owner: '华康C · 生产部',
        summary: '本厂与外发裁剪：排期、填数、物料库存、月结、基础资料及实际材料费用',
        status: '分阶段建设',
        statusTone: 'teal',
        stats: '工作区已开放 · 业务待接入',
        icon: Scissors,
        route: '/modules/production/cutting',
        detailPage: false,
        factoryIds: ['huakang-c'],
        statusMetrics: [],
        todos: [],
        children: [],
      },
      {
        id: 'spray-production',
        title: '喷油部生产管理',
        owner: '喷油车间',
        summary: '模块待重构，敬请期待',
        status: '待重构',
        statusTone: 'slate',
        stats: '暂未开放',
        icon: Wrench,
        detailPage: false,
        factoryIds: ['huaxing', 'huakang-a', 'huakang-b', 'huadeng'],
        statusMetrics: [],
        todos: [],
        children: [],
      },
      {
        id: 'uv-printing',
        title: 'UV打印管理',
        owner: '华康A · 生产部',
        summary: '模块待重建，敬请期待',
        status: '待重建',
        statusTone: 'slate',
        stats: '暂未开放',
        icon: Printer,
        detailPage: false,
        factoryIds: ['huakang-a'],
        statusMetrics: [],
        todos: [],
        children: [],
      },
    ],
    quickCandidates: ['生产计划驾驶舱', '停机异常池', '班次达成看板', '工序节拍分析'],
    permissionRows: [
      { role: '生产主管', view: true, edit: true, approve: true },
      { role: '计划员', view: true, edit: true, approve: false },
      { role: 'PMC', view: true, edit: false, approve: true },
      { role: '车间文员', view: true, edit: true, approve: false },
    ],
    todos: [
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
      qcInspectionOperationsModule,
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
  qc: {
    departmentId: 'qc',
    heroTitle: 'QC 验货运营中心',
    heroSubtitle: '按客户安排总排期，批量导入未走货订单，跟进验货结果、问题处理与汇总报表',
    panelTitle: 'QC 部模块',
    panelSubtitle: '独立于 QA 来料与成品检验，所有正式数据按厂区和 QC 权限读取',
    modules: [qcInspectionOperationsModule, qcCartonMarkVerificationModule],
    quickCandidates: ['客户验货配置', '验货机构维护', 'QC 审计查询', '集团汇总授权'],
    permissionRows: [
      { role: 'QC 检验员', view: true, edit: true, approve: false },
      { role: 'QC 主管', view: true, edit: true, approve: true },
      { role: 'QC 经理', view: true, edit: true, approve: true },
      { role: '集团授权人员', view: true, edit: false, approve: true },
    ],
    todos: [],
  },
  'sales-business': {
    departmentId: 'sales-business',
    heroTitle: '业务模块中心',
    heroSubtitle: '把内部成本报价、客户报价转换、送印尼物料和 PO 入排期连成统一入口',
    panelTitle: '业务部模块',
    panelSubtitle: '优先承接内部报价协作、客价转换、送印尼物料和 PO 入排期',
    modules: [
      {
        id: 'internal-quote-desk',
        title: '内部报价台',
        owner: '业务部 / 各核价责任部门',
        summary: '业务部与工程部建单，支持最多 20 款批量报价、九责任分段连续协作、指定审核人整单审核和受控输出',
        status: '整单流程已接入',
        statusTone: 'teal',
        stats: '批量最多 20 款 · 九责任分段',
        icon: Calculator,
        route: '/modules/sales-business/internal-quote-desk',
        statusMetrics: [
          { label: '建单', value: '业务 / 工程', tone: 'teal' },
          { label: '协作', value: '九责任分段', tone: 'blue' },
          { label: '审核', value: '整单一次提交', tone: 'green' },
        ],
        todos: ['新建、复制或批量创建内部报价', '保存九责任分段并提交整单审核', '整单审核通过后生成受控输出'],
        children: [
          { label: '报价首页', summary: '经营概览、搜索筛选、客户维护、建单复制和批量报价' },
          { label: '整单协作', summary: '九责任分段连续填写，支持产品与组件切换' },
          { label: '整单审核', summary: '指定审核人统一通过或退回整单' },
          { label: '受控输出', summary: '审核通过后预览、导出并交接客价转换' },
        ],
      },
      {
        id: 'customer-price-conversion',
        title: '客价转换台',
        owner: '车间业务',
        summary: '选择客户、导入内部报价、输出报客价 Excel',
        status: '已接入',
        statusTone: 'green',
        stats: '待转换 5 · 待复核 1',
        icon: FileSpreadsheet,
        route: '/modules/sales-business/customer-price-conversion',
        statusMetrics: [
          { label: '待转换', value: '5', tone: 'amber' },
          { label: '待复核', value: '1', tone: 'blue' },
          { label: '客户可见', value: '全部', tone: 'teal' },
        ],
        todos: ['查看并选择全部客户', '导入任一客户内部报价 Excel', '输出客户报价与版本差异'],
        children: [
          { label: '客户选择', summary: '全部客户使用同一套账号权限查看和转换' },
          { label: '报价导入', summary: '识别客户内部报价 Excel 与多 Sheet 明细' },
          { label: '报客价输出', summary: '按客户模板生成报客价文件' },
          { label: '版本对比', summary: '对比明细、利润带和历史导出版本' },
        ],
      },
      {
        id: 'indonesia-material-shipment',
        title: '送印尼物料',
        owner: '业务部 / PMC',
        summary: '统筹送往印尼的物料需求、备料、装运、清关和到货跟踪',
        status: '规划中',
        statusTone: 'amber',
        stats: '待备料 5 · 在途 3',
        icon: Ship,
        route: '/modules/sales-business/indonesia-material-shipment',
        statusMetrics: [
          { label: '待备料', value: '5', tone: 'amber' },
          { label: '在途', value: '3', tone: 'blue' },
          { label: '待确认', value: '2', tone: 'teal' },
        ],
        todos: ['汇总印尼物料需求与交期', '跟踪备料、装箱和出运节点', '记录清关与到货签收结果'],
        children: [
          { label: '物料需求', summary: '集中登记送往印尼的物料清单、数量和需求日期' },
          { label: '备料装箱', summary: '跟踪齐套、包装、箱数、重量和负责人' },
          { label: '出运清关', summary: '记录订舱、装柜、报关、船期和清关状态' },
          { label: '到货确认', summary: '回填印尼收货、差异、签收和异常处理结果' },
        ],
      },
      {
        id: 'po-schedule-intake',
        title: '客户订单中心',
        owner: '业务部 / 跟客',
        summary: '导入客户PO与客户排期，沉淀统一订单数据，并按月份形成可供生产部门调用的厂区总排期',
        status: '基础功能试用',
        statusTone: 'green',
        stats: '按厂区配置客户 PO 解析 · 客户排期导出',
        icon: CalendarClock,
        route: '/modules/sales-business/po-schedule-intake',
        statusMetrics: [
          { label: '当前客户', value: '按厂区配置', tone: 'blue' },
          { label: '统一字段', value: '17', tone: 'amber' },
          { label: '输出工作表', value: '2', tone: 'teal' },
        ],
        todos: ['导入客户PO与现有排期', '确认17个统一订单字段', '查看月度走货、临期和生产未完成订单'],
        children: [
          { label: 'PO 入客户排期', summary: '导入PO和客户排期，校验映射后输出填好数据的客户排期' },
          { label: '厂区总排期', summary: '按客户和月份汇总待走货PO、临期风险及生产模块只读反馈' },
          { label: '异常与提醒', summary: '集中查看订单阻断、交付临期/逾期、生产未完成和版本落后' },
        ],
      },
    ],
    quickCandidates: ['客户订单台账', '客户排期导入', '厂区总排期', '异常与提醒', '印尼物料台账'],
    permissionRows: [
      { role: '业务经理', view: true, edit: true, approve: true },
      { role: '车间业务主管', view: true, edit: true, approve: true },
      { role: '车间业务员', view: true, edit: true, approve: false },
      { role: '总经理', view: true, edit: false, approve: true },
      { role: 'PMC', view: true, edit: false, approve: true },
    ],
    todos: [
      { id: 'BUS-118', title: '客户信用复核', meta: '上海联志 · 6 小时内需完成' },
      { id: 'BUS-131', title: '报价审批超时', meta: '2 单需重新拉通工程与 PMC' },
      { id: 'BUS-144', title: '印尼物料出运复核', meta: '3 批在途 · 2 批待确认船期' },
      { id: 'BUS-162', title: '客户订单排期确认', meta: '待确认 2 · 待汇总 1' },
    ],
  },
  accounting: {
    departmentId: 'accounting',
    heroTitle: '会计模块中心',
    heroSubtitle: '统一承接应收应付、费用、资金和月结事项，后续按正式账务流程接入',
    panelTitle: '会计部模块',
    panelSubtitle: '先建立账务协同入口和职责边界，再逐步接入凭证与报表数据',
    modules: [
      {
        id: 'indonesia-invoice-reconciliation',
        title: '印尼票据核对',
        owner: '会计部 · 公共模块',
        summary: '集中核对 RRI 与 RRM 的客户票、供应商票，并汇总金额差异和待复核事项',
        status: '前端已就绪',
        statusTone: 'teal',
        stats: 'RRI · RRM 双厂区',
        icon: Calculator,
        route: '/modules/accounting/indonesia-invoice-reconciliation',
        statusMetrics: [
          { label: '票据', value: '双票核对', tone: 'teal' },
          { label: '厂区', value: 'RRI · RRM', tone: 'blue' },
          { label: '状态', value: '前端就绪', tone: 'green' },
        ],
        todos: ['导入客户票与供应商票', '复核单号、日期、货号、数量和金额', '跟进差异并确认核对结论'],
        children: [
          { label: '双票导入', summary: '同一票据组分别选择客户票与供应商票 PDF' },
          { label: '字段核对', summary: '核对单号、日期、SKU、数量、单价与总额' },
          { label: '差异汇总', summary: '集中查看金额和资料差异的处理状态' },
          { label: '票据记录', summary: '沉淀 RRI、RRM 两个厂区的核对记录' },
        ],
      },
    ],
    quickCandidates: ['印尼票据核对', '应收应付对账', '付款申请', '月结报表'],
    permissionRows: [
      { role: '会计主管', view: true, edit: true, approve: true },
      { role: '会计', view: true, edit: true, approve: false },
      { role: '出纳', view: true, edit: true, approve: false },
      { role: '总经理', view: true, edit: false, approve: true },
    ],
    todos: [
      { id: 'ACC-101', title: 'RRI 客户票待核对', meta: '需补齐对应供应商票后复核' },
      { id: 'ACC-112', title: 'RRM 单价差异待确认', meta: '需复核 0.98 核对规则与票据币种' },
      { id: 'ACC-124', title: '印尼票据汇总口径确认', meta: '需明确月结前的核对截止日期' },
    ],
  },
}

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
  'huakang-c': {
    factoryId: 'huakang-c',
    order: {
      ...huakangBMoldingSampleOrder,
      customer: '待接入',
      productNo: 'HKC',
      productName: '华康C厂区数据待接入',
      source: '华康C独立数据源',
      documentNo: '',
      requester: '',
      requestDate: '',
      requiredDate: '',
      note: '当前厂区暂无示例数据，正式页面只读取华康C自己的后端数据。',
    },
    stages: moldingProgressStages.map((stage) => ({ ...stage })),
    lines: [],
  },
  'huakang-d': {
    factoryId: 'huakang-d',
    order: {
      ...huakangBMoldingSampleOrder,
      customer: '待接入',
      productNo: 'HKD',
      productName: '华康D厂区数据待接入',
      source: '华康D独立数据源',
      documentNo: '',
      requester: '',
      requestDate: '',
      requiredDate: '',
      note: '当前厂区暂无示例数据，正式页面只读取华康D自己的后端数据。',
    },
    stages: moldingProgressStages.map((stage) => ({ ...stage })),
    lines: [],
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
