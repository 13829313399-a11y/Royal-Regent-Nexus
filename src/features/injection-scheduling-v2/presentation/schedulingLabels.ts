import type {
  AutoScheduleAssignmentRecord,
  AutoScheduleGenerationOptions,
  AutoScheduleRunRecord,
  FactoryId,
  FitDecision,
  ImportDocumentKind,
  MachineRecord,
  OrderRecord,
  PlanSliceKey,
  TaskStatus,
} from '../types'

export type DisplayTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger'

export interface DisplayMeta<TCode extends string = string> {
  code: TCode
  label: string
  tone: DisplayTone
  iconToken?: string
  cssToken: string
  description?: string
}

type KnownPlanStatus = 'DRAFT' | 'PUBLISHED' | 'ARCHIVED'
type SolverStatus = AutoScheduleRunRecord['solverStatus']
type AssignmentDecision = AutoScheduleAssignmentRecord['decision']

const meta = <TCode extends string>(code: TCode, label: string, tone: DisplayTone, cssToken: string, description?: string): DisplayMeta<TCode> => ({
  code, label, tone, cssToken, ...(description ? { description } : {}),
})

function fromCatalog<TCode extends string>(catalog: Record<string, DisplayMeta<TCode>>, value: unknown, fallbackLabel = '未知状态'): DisplayMeta<TCode> {
  const code = String(value ?? '').trim()
  return catalog[code] ?? meta(code as TCode, fallbackLabel, 'warning', 'unknown', '系统返回了尚未登记的状态，请在技术信息中查看原始值。')
}

const planStatusCatalog: Record<KnownPlanStatus, DisplayMeta<KnownPlanStatus>> = {
  DRAFT: meta('DRAFT', '排产草案', 'info', 'draft'),
  PUBLISHED: meta('PUBLISHED', '当前执行', 'success', 'published'),
  ARCHIVED: meta('ARCHIVED', '历史版本', 'neutral', 'archived'),
}

const planSliceCatalog: Record<PlanSliceKey, DisplayMeta<PlanSliceKey>> = {
  execution: meta('execution', '当前执行', 'success', 'execution'),
  planning: meta('planning', '排产草案', 'info', 'planning'),
}

const taskStatusCatalog: Record<TaskStatus, DisplayMeta<TaskStatus>> = {
  RUNNING: meta('RUNNING', '正在生产', 'success', 'running'),
  QUEUED: meta('QUEUED', '排队中', 'info', 'queued'),
  BLOCKED: meta('BLOCKED', '异常 / 待料', 'danger', 'blocked'),
  COMPLETED: meta('COMPLETED', '已完成', 'success', 'completed'),
  CANCELLED: meta('CANCELLED', '已取消', 'neutral', 'cancelled'),
  REVIEW: meta('REVIEW', '待复核', 'warning', 'review'),
}

const fitDecisionCatalog: Record<FitDecision, DisplayMeta<FitDecision>> = {
  PASS: meta('PASS', '适配通过', 'success', 'pass'),
  REVIEW_REQUIRED: meta('REVIEW_REQUIRED', '需要人工复核', 'warning', 'review-required'),
  FAIL: meta('FAIL', '不适配', 'danger', 'fail'),
}

const machineStatusCatalog: Record<MachineRecord['status'], DisplayMeta<MachineRecord['status']>> = {
  available: meta('available', '可用', 'success', 'available'),
  running: meta('running', '生产中', 'success', 'running'),
  maintenance: meta('maintenance', '维护中', 'warning', 'maintenance'),
  offline: meta('offline', '已离线', 'neutral', 'offline'),
}

const normalizationStatusCatalog: Record<MachineRecord['normalizationStatus'], DisplayMeta<MachineRecord['normalizationStatus']>> = {
  COMPLETE: meta('COMPLETE', '资料已规范', 'success', 'complete'),
  REVIEW_REQUIRED: meta('REVIEW_REQUIRED', '资料待复核', 'warning', 'review-required'),
}

const moldEnrichmentStatusCatalog: Record<string, DisplayMeta<string>> = {
  MATCHED: meta('MATCHED', '共享资料已补齐', 'success', 'matched'),
  PENDING: meta('PENDING', '模具资料待补齐', 'warning', 'pending'),
  AMBIGUOUS: meta('AMBIGUOUS', '模具匹配有歧义', 'warning', 'ambiguous'),
}

const factoryReadinessStatusCatalog: Record<string, DisplayMeta<string>> = {
  FACTORY_READY: meta('FACTORY_READY', '可直接排机', 'success', 'factory-ready'),
  DRAFT_READY: meta('DRAFT_READY', '草案可排 · 发布前补实体', 'warning', 'draft-ready'),
  NOT_FACTORY_READY: meta('NOT_FACTORY_READY', '厂区资源待补齐', 'warning', 'not-factory-ready'),
  CAPABILITY_CONFLICT: meta('CAPABILITY_CONFLICT', '厂区能力存在冲突', 'danger', 'capability-conflict'),
}

const orderStatusCatalog: Record<OrderRecord['status'], DisplayMeta<OrderRecord['status']>> = {
  BACKLOG: meta('BACKLOG', '待排', 'warning', 'backlog'),
  SCHEDULED: meta('SCHEDULED', '已排产', 'info', 'scheduled'),
  COMPLETED: meta('COMPLETED', '已完成', 'success', 'completed'),
  CANCELLED: meta('CANCELLED', '已取消', 'neutral', 'cancelled'),
}

const priorityCatalog: Record<OrderRecord['priorityCode'], DisplayMeta<OrderRecord['priorityCode']>> = {
  NORMAL: meta('NORMAL', '普通', 'neutral', 'normal'),
  URGENT: meta('URGENT', '加急', 'warning', 'urgent'),
  CRITICAL: meta('CRITICAL', '特急', 'danger', 'critical'),
}

const materialReadinessCatalog: Record<OrderRecord['materialReadinessStatus'], DisplayMeta<OrderRecord['materialReadinessStatus']>> = {
  unknown: meta('unknown', '物料状态待确认', 'warning', 'unknown'),
  ready: meta('ready', '物料已就绪', 'success', 'ready'),
  partial: meta('partial', '部分物料待齐', 'warning', 'partial'),
  blocked: meta('blocked', '物料未就绪', 'danger', 'blocked'),
}

const solverTypeCatalog: Record<AutoScheduleGenerationOptions['solver'], DisplayMeta<AutoScheduleGenerationOptions['solver']>> = {
  AUTO: meta('AUTO', '系统自动选择', 'info', 'auto'),
  CP_SAT: meta('CP_SAT', '优化求解', 'info', 'cp-sat'),
  HEURISTIC: meta('HEURISTIC', '快速排产', 'neutral', 'heuristic'),
}

const autoScheduleRunStatusCatalog: Record<AutoScheduleRunRecord['status'], DisplayMeta<AutoScheduleRunRecord['status']>> = {
  CREATED: meta('CREATED', '正在准备方案', 'info', 'created'),
  VALIDATING: meta('VALIDATING', '正在检查排产条件', 'info', 'validating'),
  GENERATING_CANDIDATES: meta('GENERATING_CANDIDATES', '正在生成候选安排', 'info', 'generating-candidates'),
  SOLVING: meta('SOLVING', '正在优化排产方案', 'info', 'solving'),
  SUCCEEDED: meta('SUCCEEDED', '方案已生成', 'success', 'succeeded'),
  PARTIAL: meta('PARTIAL', '方案已生成，仍有待复核或未安排项', 'warning', 'partial'),
  APPLIED: meta('APPLIED', '已应用到排产草案', 'success', 'applied'),
  FAILED: meta('FAILED', '方案生成失败', 'danger', 'failed'),
  CANCELLED: meta('CANCELLED', '已取消', 'neutral', 'cancelled'),
}

const solverStatusCatalog: Record<SolverStatus, DisplayMeta<SolverStatus>> = {
  NOT_RUN: meta('NOT_RUN', '尚未运行优化求解', 'neutral', 'not-run'),
  HEURISTIC: meta('HEURISTIC', '快速排产已完成', 'success', 'heuristic'),
  OPTIMAL: meta('OPTIMAL', '模型目标下已找到最优结果', 'success', 'optimal'),
  FEASIBLE: meta('FEASIBLE', '已找到可行方案', 'success', 'feasible'),
  INFEASIBLE: meta('INFEASIBLE', '未找到可行方案', 'danger', 'infeasible'),
  TIME_LIMIT: meta('TIME_LIMIT', '已达到求解时间上限', 'warning', 'time-limit'),
  UNAVAILABLE: meta('UNAVAILABLE', '优化服务暂不可用', 'warning', 'unavailable'),
}

const assignmentDecisionCatalog: Record<AssignmentDecision, DisplayMeta<AssignmentDecision>> = {
  PASS: meta('PASS', '可应用', 'success', 'pass'),
  REVIEW_REQUIRED: meta('REVIEW_REQUIRED', '待复核', 'warning', 'review-required'),
  UNASSIGNED: meta('UNASSIGNED', '未安排', 'danger', 'unassigned'),
}

const importDocumentKindCatalog: Record<ImportDocumentKind, DisplayMeta<ImportDocumentKind>> = {
  DEMAND_ORDER: meta('DEMAND_ORDER', '下单需求', 'info', 'demand-order'),
  PLANNED_SCHEDULE: meta('PLANNED_SCHEDULE', '历史计划表', 'info', 'planned-schedule'),
  SYSTEM_ROUND_TRIP: meta('SYSTEM_ROUND_TRIP', '系统回写文件', 'info', 'system-round-trip'),
  MASTER_DATA: meta('MASTER_DATA', '主数据资料', 'warning', 'master-data'),
}

const importBatchStateCatalog: Record<string, DisplayMeta<string>> = {
  IDENTIFYING: meta('IDENTIFYING', '正在识别文件', 'info', 'identifying'),
  MAPPING_REQUIRED: meta('MAPPING_REQUIRED', '需要字段映射', 'warning', 'mapping-required'),
  PROFILE_REVIEW_PENDING: meta('PROFILE_REVIEW_PENDING', '模板待审核', 'warning', 'profile-review-pending'),
  MASTER_REVIEW_REQUIRED: meta('MASTER_REVIEW_REQUIRED', '主数据待审核', 'warning', 'master-review-required'),
  RESOLUTION_REVIEW_REQUIRED: meta('RESOLUTION_REVIEW_REQUIRED', '匹配结果待复核', 'warning', 'resolution-review-required'),
  RECONCILIATION_CONFLICT: meta('RECONCILIATION_CONFLICT', '存在对账冲突', 'danger', 'reconciliation-conflict'),
  PREVIEW_READY: meta('PREVIEW_READY', '预览已就绪', 'success', 'preview-ready'),
  PARTIALLY_CONFIRMED: meta('PARTIALLY_CONFIRMED', '部分已确认', 'warning', 'partially-confirmed'),
  CONFIRMED: meta('CONFIRMED', '已确认', 'success', 'confirmed'),
  FAILED: meta('FAILED', '处理失败', 'danger', 'failed'),
}

const factoryCatalog: Record<FactoryId, DisplayMeta<FactoryId>> = {
  huaxing: meta('huaxing', '华兴', 'neutral', 'huaxing'),
  'huakang-a': meta('huakang-a', '华康 A', 'neutral', 'huakang-a'),
  'huakang-b': meta('huakang-b', '华康 B', 'neutral', 'huakang-b'),
  'huakang-c': meta('huakang-c', '华康 C', 'neutral', 'huakang-c'),
  'huakang-d': meta('huakang-d', '华康 D', 'neutral', 'huakang-d'),
  huadeng: meta('huadeng', '华登', 'neutral', 'huadeng'),
}

const importRowResolutionCatalog: Record<string, DisplayMeta<string>> = {
  READY: meta('READY', '可以导入', 'success', 'ready'),
  PROPOSABLE: meta('PROPOSABLE', '可以提交提案', 'success', 'proposable'),
  AUTO_CONFIRMED: meta('AUTO_CONFIRMED', '系统已确认', 'success', 'auto-confirmed'),
  REVIEW_REQUIRED: meta('REVIEW_REQUIRED', '需要人工复核', 'warning', 'review-required'),
  IDENTITY_REVIEW_REQUIRED: meta('IDENTITY_REVIEW_REQUIRED', '业务标识待复核', 'warning', 'identity-review-required'),
  AMBIGUOUS: meta('AMBIGUOUS', '存在多项匹配', 'warning', 'ambiguous'),
  NOT_FOUND: meta('NOT_FOUND', '未找到匹配资料', 'warning', 'not-found'),
  PRICE_REVIEW_REQUIRED: meta('PRICE_REVIEW_REQUIRED', '单价需要复核', 'warning', 'price-review-required'),
  CONFLICT: meta('CONFLICT', '存在数据冲突', 'danger', 'conflict'),
  INVALID: meta('INVALID', '数据无效', 'danger', 'invalid'),
  DUPLICATE: meta('DUPLICATE', '重复数据', 'warning', 'duplicate'),
  UPDATE: meta('UPDATE', '可以更新', 'info', 'update'),
  REMOVAL_REVIEW: meta('REMOVAL_REVIEW', '移除操作待复核', 'warning', 'removal-review'),
}

const importConfirmationStateCatalog: Record<string, DisplayMeta<string>> = {
  PENDING: meta('PENDING', '待确认', 'warning', 'pending'),
  CONFIRMED: meta('CONFIRMED', '已导入', 'success', 'confirmed'),
  PROPOSED: meta('PROPOSED', '已提交提案', 'success', 'proposed'),
  PARTIALLY_CONFIRMED: meta('PARTIALLY_CONFIRMED', '部分已确认', 'warning', 'partially-confirmed'),
}

const masterDataEntityCatalog: Record<string, DisplayMeta<string>> = {
  MOLD_DEFINITION_BUNDLE: meta('MOLD_DEFINITION_BUNDLE', '公司模具资料', 'info', 'mold-definition-bundle'),
  FACTORY_MOLD_CAPABILITY_BUNDLE: meta('FACTORY_MOLD_CAPABILITY_BUNDLE', '厂区机安能力', 'info', 'factory-mold-capability-bundle'),
  COMMERCIAL_RATE_RULE: meta('COMMERCIAL_RATE_RULE', '人民币单价规则', 'warning', 'commercial-rate-rule'),
  MOLD: meta('MOLD', '模具资料', 'info', 'mold'),
  MACHINE: meta('MACHINE', '机台资料', 'info', 'machine'),
}

const profileStatusCatalog: Record<string, DisplayMeta<string>> = {
  PROFILE_DRAFT: meta('PROFILE_DRAFT', '模板草案', 'warning', 'profile-draft'),
  ACTIVE: meta('ACTIVE', '使用中', 'success', 'active'),
  RETIRED: meta('RETIRED', '已停用', 'neutral', 'retired'),
}

const masterProposalStatusCatalog: Record<string, DisplayMeta<string>> = {
  PROPOSED: meta('PROPOSED', '待审核', 'warning', 'proposed'),
  UNDER_REVIEW: meta('UNDER_REVIEW', '审核中', 'info', 'under-review'),
  APPROVED: meta('APPROVED', '已批准', 'success', 'approved'),
  ACTIVE: meta('ACTIVE', '已生效', 'success', 'active'),
  REJECTED: meta('REJECTED', '已驳回', 'danger', 'rejected'),
  SUPERSEDED: meta('SUPERSEDED', '已被新版本替代', 'neutral', 'superseded'),
  RETIRED: meta('RETIRED', '已停用', 'neutral', 'retired'),
}

const proposalActionCatalog: Record<string, DisplayMeta<string>> = {
  CREATE: meta('CREATE', '新增', 'info', 'create'),
  REVISE: meta('REVISE', '修订', 'info', 'revise'),
  CREATE_OR_REVISE: meta('CREATE_OR_REVISE', '新增或修订', 'info', 'create-or-revise'),
  MERGE: meta('MERGE', '合并', 'warning', 'merge'),
  SPLIT: meta('SPLIT', '拆分', 'warning', 'split'),
  RETIRE: meta('RETIRE', '停用', 'neutral', 'retire'),
  ALIAS_REDIRECT: meta('ALIAS_REDIRECT', '调整别名指向', 'warning', 'alias-redirect'),
  ACTIVATE: meta('ACTIVATE', '启用', 'success', 'activate'),
}

const exportBindingSourceCatalog: Record<string, DisplayMeta<string>> = {
  IMPORT_PROFILE: meta('IMPORT_PROFILE', '来源模板已锁定', 'success', 'import-profile'),
  SYSTEM_STANDARD: meta('SYSTEM_STANDARD', '系统标准模板', 'info', 'system-standard'),
  LEGACY_UNKNOWN: meta('LEGACY_UNKNOWN', '历史来源，未记录模板', 'warning', 'legacy-unknown'),
}

const integrationStatusCatalog: Record<string, DisplayMeta<string>> = {
  ACTIVE: meta('ACTIVE', '正常接收', 'success', 'active'),
  ERROR: meta('ERROR', '同步异常', 'danger', 'error'),
  NOT_CONFIGURED: meta('NOT_CONFIGURED', '未配置接口', 'neutral', 'not-configured'),
}

const integrationSourceCatalog: Record<string, DisplayMeta<string>> = {
  ERP: meta('ERP', 'ERP 新单增量同步', 'info', 'erp'),
  DEVICE: meta('DEVICE', '现场设备生产采集', 'info', 'device'),
}

const speedModelStatusCatalog: Record<string, DisplayMeta<string>> = {
  ACTIVE: meta('ACTIVE', '已启用', 'success', 'active'),
  INSUFFICIENT_DATA: meta('INSUFFICIENT_DATA', '样本不足', 'warning', 'insufficient-data'),
}

const quantityBasisCatalog: Record<string, DisplayMeta<string>> = {
  UNITS: meta('UNITS', '件 / 套', 'neutral', 'units'),
  SHOTS: meta('SHOTS', '啤数', 'neutral', 'shots'),
}

const demandSourceCatalog: Record<string, DisplayMeta<string>> = {
  MANUAL_PLANNING_DEMAND: meta('MANUAL_PLANNING_DEMAND', '手工需求', 'info', 'manual-planning-demand'),
  DEMAND_ORDER: meta('DEMAND_ORDER', '下单表', 'info', 'demand-order'),
  DEMAND_ORDER_VERSION: meta('DEMAND_ORDER_VERSION', '下单表', 'info', 'demand-order-version'),
  PLANNED_SCHEDULE: meta('PLANNED_SCHEDULE', '历史计划表', 'neutral', 'planned-schedule'),
}

const unassignedReasonCatalog: Record<string, DisplayMeta<string>> = {
  MATERIAL_BLOCKED: meta('MATERIAL_BLOCKED', '物料未就绪', 'danger', 'material-blocked'),
  MOLD_MISSING: meta('MOLD_MISSING', '模具资料缺失', 'danger', 'mold-missing'),
  NO_ELIGIBLE_MACHINE: meta('NO_ELIGIBLE_MACHINE', '没有符合条件的机台', 'danger', 'no-eligible-machine'),
  ALREADY_FULLY_ALLOCATED: meta('ALREADY_FULLY_ALLOCATED', '订单已全部安排', 'neutral', 'already-fully-allocated'),
  HORIZON_EXCEEDED: meta('HORIZON_EXCEEDED', '当前排期窗口不足', 'warning', 'horizon-exceeded'),
  CP_SAT_INFEASIBLE: meta('CP_SAT_INFEASIBLE', '优化模型未找到可行安排', 'danger', 'cp-sat-infeasible'),
}

const capacitySourceCatalog: Record<string, DisplayMeta<string>> = {
  SOURCE_DAILY_CAPACITY: meta('SOURCE_DAILY_CAPACITY', '下单表模具日产量', 'info', 'source-daily-capacity'),
  ACTIVE_SPEED_MODEL: meta('ACTIVE_SPEED_MODEL', '有效速度模型', 'info', 'active-speed-model'),
  MOLD_DAILY_CAPACITY: meta('MOLD_DAILY_CAPACITY', '共享模具日产量', 'info', 'mold-daily-capacity'),
  DEFAULT_RATE: meta('DEFAULT_RATE', '系统默认速度', 'neutral', 'default-rate'),
  SYSTEM_DEFAULT_RATE: meta('SYSTEM_DEFAULT_RATE', '系统默认速度', 'neutral', 'system-default-rate'),
}

export const planStatusMeta = (code: unknown) => fromCatalog(planStatusCatalog, code)
export const planSliceMeta = (code: unknown) => fromCatalog(planSliceCatalog, code)
export const taskStatusMeta = (code: unknown) => fromCatalog(taskStatusCatalog, code)
export const fitDecisionMeta = (code: unknown) => fromCatalog(fitDecisionCatalog, code, '需要系统确认')
export const machineStatusMeta = (code: unknown) => fromCatalog(machineStatusCatalog, code)
export const normalizationStatusMeta = (code: unknown) => fromCatalog(normalizationStatusCatalog, code, '资料状态待确认')
export const moldEnrichmentStatusMeta = (code: unknown) => fromCatalog(moldEnrichmentStatusCatalog, code, '共享模具状态待确认')
export const factoryReadinessStatusMeta = (code: unknown) => fromCatalog(factoryReadinessStatusCatalog, code, '厂区就绪状态待确认')
export const orderStatusMeta = (code: unknown) => fromCatalog(orderStatusCatalog, code)
export const priorityMeta = (code: unknown) => fromCatalog(priorityCatalog, code)
export const materialReadinessMeta = (code: unknown) => fromCatalog(materialReadinessCatalog, code)
export const solverTypeMeta = (code: unknown) => fromCatalog(solverTypeCatalog, code)
export const autoScheduleRunStatusMeta = (code: unknown) => fromCatalog(autoScheduleRunStatusCatalog, code)
export const solverStatusMeta = (code: unknown) => fromCatalog(solverStatusCatalog, code)
export const assignmentDecisionMeta = (code: unknown) => fromCatalog(assignmentDecisionCatalog, code)
export const importDocumentKindMeta = (code: unknown) => fromCatalog(importDocumentKindCatalog, code)
export const importBatchStateMeta = (code: unknown) => fromCatalog(importBatchStateCatalog, code)
export const factoryMeta = (code: unknown) => fromCatalog(factoryCatalog, code, '未知厂区')
export const importRowResolutionMeta = (code: unknown) => fromCatalog(importRowResolutionCatalog, code, '处理状态待确认')
export const importConfirmationStateMeta = (code: unknown) => fromCatalog(importConfirmationStateCatalog, code, '确认状态待确认')
export const masterDataEntityMeta = (code: unknown) => fromCatalog(masterDataEntityCatalog, code, '主数据类型待确认')
export const profileStatusMeta = (code: unknown) => fromCatalog(profileStatusCatalog, code, '模板状态待确认')
export const masterProposalStatusMeta = (code: unknown) => fromCatalog(masterProposalStatusCatalog, code, '提案状态待确认')
export const proposalActionMeta = (code: unknown) => fromCatalog(proposalActionCatalog, code, '提案动作待确认')
export const exportBindingSourceMeta = (code: unknown) => fromCatalog(exportBindingSourceCatalog, code, '来源模板状态待确认')
export const integrationStatusMeta = (code: unknown) => fromCatalog(integrationStatusCatalog, code, '接口状态待确认')
export const integrationSourceMeta = (code: unknown) => fromCatalog(integrationSourceCatalog, code, '接口来源待确认')
export const speedModelStatusMeta = (code: unknown) => fromCatalog(speedModelStatusCatalog, code, '速度模型状态待确认')
export const quantityBasisMeta = (code: unknown) => fromCatalog(quantityBasisCatalog, code, '数量口径待确认')
export const demandSourceMeta = (code: unknown) => fromCatalog(demandSourceCatalog, code, '来源待确认')
export const unassignedReasonMeta = (code: unknown) => fromCatalog(unassignedReasonCatalog, code, '未安排原因待确认')
export const capacitySourceMeta = (code: unknown) => fromCatalog(capacitySourceCatalog, code, '工时依据待确认')
