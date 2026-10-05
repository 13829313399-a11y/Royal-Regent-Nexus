export const CUTTING_BASE = '/modules/production/cutting'
export const CUTTING_FACTORY = 'huakang-c'

export function isCuttingFactory(factory: unknown): factory is typeof CUTTING_FACTORY {
  return factory === CUTTING_FACTORY
}

// This first delivery contains navigation and business explanations only.
// Register canonical backend permissions before connecting any business data.
export const CUTTING_WORKSPACES = [
  {
    path: 'planning', short: '排期', title: '生产排期', icon: 'CalendarRange',
    description: '从订单、工程 BOM 和物料交期出发，安排本厂与外发裁剪。',
    tabs: ['订单总台账', '待排任务', '每日计划'],
    columns: ['放产日期', '客户', '生产单号', '合同号', '货号', '款式 / 颜色', '订单数量（套）', '物料交期', '贴合 / 捆条', '执行方', '计划开始', '计划完成', '累计计划（套）', '累计完成（套）'],
    empty: '订单与物料交期尚未接入',
    next: '接入华康 C 订单下发、工程确认的生产 BOM 和采购交期后，主管可分配本厂及外发任务。',
    rules: ['一般经过 3 个工作日开始供数，起算边界及工作日历待确认。', '按当前阶段必需物料判断可生产批次，其他辅料继续跟进。', '预计交期支持预排，实际可用物料决定可执行数量。'],
  },
  {
    path: 'reporting', short: '填数', title: '每日生产填数', icon: 'ClipboardCheck',
    description: '主管安排每日计划，文员登记实际产量；散片与完整配套分别记录。',
    tabs: ['待填任务', '每日报数', '散片与异常', '交接与外发回收'],
    columns: ['生产日期', '生产单号', '货号 / 款式', '执行方', '当日计划（套）', '合格完成（套）', '散片数量', '交接数量（套）', '填报人', '状态'],
    empty: '生产任务与日报尚未接入',
    next: '订单拆分和计划发布能力完成后，按任务填回当天实际完成数量。',
    rules: ['完整套数依据 BOM 部件配比核算，不把所有裁片数量相加。', '完成、交接、外发收回与验收各自保留，不重复统计。', '未填报与明确填零分开；确认后的更正保留原记录。'],
  },
  {
    path: 'materials', short: '物料库存', title: '物料库存', icon: 'Boxes',
    description: '跟进布料与辅料交期，核对仓库、本厂现场和外发在外物料。',
    tabs: ['库存台账', '采购交期', '领退与调拨', '耗用与盘点'],
    columns: ['物料编码', '名称 / 规格 / 颜色', '批次', '保管位置', '单位', '实际结存', '已占用', '可用量', '预计到料', '质量状态'],
    empty: '物料库存尚未接入',
    next: '对接统一物料收发事实后展示库存；预计到料不作为实际结存。',
    rules: ['可配置当前阶段必需物料，允许部分到料分批生产。', '仓库到现场或外发厂的转移，不增加全厂库存。', '填报产量不自动再次扣料；实际耗用单独留存依据。'],
  },
  {
    path: 'closing', short: '月结', title: '生产与外发月结', icon: 'CalendarCheck2',
    description: '同时核对内部生产、库存和材料费用，以及外发裁剪加工费。',
    tabs: ['内部月结', '外发对账', '结算与应付', '付款核销'],
    columns: ['结算月份', '核对范围', '加工厂 / 执行方', '生产核对', '库存核对', '材料费用', '加工费', '币种', '应付 / 未付', '状态'],
    empty: '月结与结算尚未开放',
    next: '生产、收发耗料与外发验收链完成，并确认计价及复核规则后，开放月结。',
    rules: ['内部月结与外发结算分别保存状态，支持跨月订单。', '外发仅含裁剪；加工费与我方材料费用分别归集。', '验收、结算、付款是不同事实；锁月后调整需保留依据。'],
  },
  {
    path: 'master', short: '基础资料', title: '基础资料', icon: 'Settings2',
    description: '统一产品配套、生产 BOM、执行资源、物料和工作日历。',
    tabs: ['产品与配套 BOM', '物料与单位', '本厂与外发资源', '工作日历'],
    columns: ['资料编码', '名称', '分类', '规格 / 单位', '责任部门', '有效版本', '生效日期', '状态'],
    empty: '基础资料维护尚未开放',
    next: '先接入权威资料和版本记录，再开放生产 BOM、必需物料配置及采购交期登记。',
    rules: ['生产 BOM 需由工程确认，报价 BOM 不直接作为生产依据。', '订单、BOM、价格保留有效版本，停用资料不删除历史。', '华康 C 建立自己的客户映射，不搬移华康 D 历史订单。'],
  },
  {
    path: 'costs', short: '物料费用', title: '实际生产物料费用', icon: 'Calculator',
    description: '从实际耗用追溯订单材料费用，分别呈现损耗、在制和待计价。',
    tabs: ['订单费用', '耗用明细', '标准与实际对比', '在制与待计价'],
    columns: ['生产单号', '执行方', '物料 / 批次', '实际耗用', '单位', '计价依据', '材料费用', '币种', '在制归集', '核对状态'],
    empty: '实际材料费用尚未接入',
    next: '实际耗料、批次价格和计价政策确认后归集费用，不用计划用量代替实际成本。',
    rules: ['未知价格显示待计价，不用零元代替缺失价格。', '材料费用与外发加工费分开，不同币种不直接相加。', '历史费用保留原依据，补价不覆盖已冻结的月结。'],
  },
] as const

export type CuttingWorkspace = typeof CUTTING_WORKSPACES[number]
