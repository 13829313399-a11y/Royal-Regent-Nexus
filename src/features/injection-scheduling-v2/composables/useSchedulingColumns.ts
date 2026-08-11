import type { ColumnPreset, SchedulingColumnDefinition } from '../types'

export const schedulingColumns: SchedulingColumnDefinition[] = [
  { key: 'status', title: '状态', group: '执行', width: 92, align: 'center', frozen: true, presets: ['planner', 'production', 'fit', 'full'] },
  { key: 'sequence', title: '队列', group: '执行', width: 54, align: 'center', presets: ['planner', 'production', 'fit', 'full'] },
  { key: 'position', title: '机位', group: '机台与排程', width: 70, align: 'center', presets: ['full'] },
  { key: 'machineCode', title: '机号', group: '机台与排程', width: 82, align: 'center', frozen: true, presets: ['planner', 'production', 'fit', 'full'] },
  { key: 'automation', title: '是否全自动', group: '机台与排程', width: 92, presets: ['full'] },
  { key: 'marker', title: '标记/备注', group: '机台与排程', width: 82, presets: ['full'] },
  { key: 'moldA', title: '模具安数', group: '机台与排程', width: 94, presets: ['planner', 'fit', 'full'] },
  { key: 'moldNo', title: '工模', group: '机台与排程', width: 160, frozen: true, presets: ['planner', 'production', 'fit', 'full'] },
  { key: 'productName', title: '名称', group: '机台与排程', width: 220, frozen: true, presets: ['planner', 'production', 'full'] },
  { key: 'orderNo', title: '单号', group: '机台与排程', width: 128, presets: ['planner', 'production', 'full'] },
  { key: 'itemNo', title: '货号', group: '机台与排程', width: 136, presets: ['planner', 'production', 'full'] },
  { key: 'setQuantity', title: '数量(套)', group: '数量与进度', width: 88, align: 'right', presets: ['full'] },
  { key: 'orderQuantity', title: '订单数', group: '数量与进度', width: 90, align: 'right', presets: ['production', 'full'] },
  { key: 'completedQuantity', title: '已啤数', group: '数量与进度', width: 92, align: 'right', presets: ['production', 'full'] },
  { key: 'outstandingQuantity', title: '欠数', group: '数量与进度', width: 92, align: 'right', presets: ['planner', 'production', 'full'] },
  { key: 'progress', title: '进度', group: '数量与进度', width: 112, presets: ['planner', 'production', 'full'] },
  { key: 'targetQuantity', title: '计划目标', group: '数量与进度', width: 94, align: 'right', presets: ['production', 'full'] },
  { key: 'shiftCompleted', title: '本班已啤', group: '数量与进度', width: 94, align: 'right', presets: ['production', 'full'] },
  { key: 'sprueRatio', title: '水口比例', group: '数量与进度', width: 84, align: 'right', presets: ['full'] },
  { key: 'color', title: '颜色', group: '颜色与物料', width: 94, presets: ['fit', 'full'] },
  { key: 'powder', title: '色粉', group: '颜色与物料', width: 92, presets: ['full'] },
  { key: 'material', title: '用料', group: '颜色与物料', width: 172, presets: ['fit', 'full'] },
  { key: 'netWeightG', title: '净重(g)', group: '颜色与物料', width: 84, align: 'right', presets: ['fit', 'full'] },
  { key: 'grossWeightG', title: '毛重(g)', group: '颜色与物料', width: 84, align: 'right', presets: ['full'] },
  { key: 'materialKg', title: '用料重(KG)', group: '颜色与物料', width: 100, align: 'right', presets: ['full'] },
  { key: 'unitPrice', title: '单价/啤', group: '价格', width: 84, align: 'right', presets: ['full'] },
  { key: 'ratio', title: '比例', group: '价格', width: 74, align: 'right', presets: ['full'] },
  { key: 'orderDate', title: '下单期', group: '货期与计划', width: 102, presets: ['full'] },
  { key: 'deliveryStart', title: '开始交货期', group: '货期与计划', width: 106, presets: ['full'] },
  { key: 'deliveryDue', title: '交货完成期', group: '货期与计划', width: 106, presets: ['planner', 'production', 'full'] },
  { key: 'moldChangeRef', title: '转模参考', group: '货期与计划', width: 88, align: 'right', presets: ['full'] },
  { key: 'colorChangeRef', title: '转色参考', group: '货期与计划', width: 88, align: 'right', presets: ['full'] },
  { key: 'setupTime', title: '转模/色时间', group: '货期与计划', width: 94, align: 'right', presets: ['full'] },
  { key: 'downtime', title: '机/模故时间', group: '货期与计划', width: 94, align: 'right', presets: ['production', 'full'] },
  { key: 'exception', title: '异常类型', group: '货期与计划', width: 110, presets: ['production', 'full'] },
  { key: 'plannedStart', title: '计划生产期', group: '货期与计划', width: 136, presets: ['planner', 'production', 'full'] },
  { key: 'plannedFinish', title: '计划完成期', group: '货期与计划', width: 136, presets: ['planner', 'production', 'full'] },
  { key: 'planMonth', title: '计划完成月', group: '货期与计划', width: 92, presets: ['full'] },
  { key: 'warehouseDate', title: '入库期', group: '货期与计划', width: 104, presets: ['full'] },
  { key: 'slack', title: '交期差', group: '货期与计划', width: 78, align: 'right', presets: ['planner', 'production', 'full'] },
  { key: 'spray', title: '是否喷油', group: '生产辅助', width: 84, presets: ['full'] },
  { key: 'productionDays', title: '啤货天数', group: '生产辅助', width: 84, align: 'right', presets: ['full'] },
  { key: 'machineA', title: '机台安数', group: '生产辅助', width: 86, presets: ['fit', 'full'] },
  { key: 'shotCapacity', title: '射胶量(g)', group: '生产辅助', width: 90, align: 'right', presets: ['fit', 'full'] },
  { key: 'fit', title: '适配结论', group: '生产辅助', width: 98, presets: ['fit', 'full'] },
  { key: 'warehouse', title: '仓库', group: '生产辅助', width: 110, presets: ['planner', 'full'] },
  { key: 'remark', title: '备注', group: '生产辅助', width: 194, presets: ['planner', 'production', 'full'] },
  { key: 'shipDate', title: '走货期', group: '生产辅助', width: 98, presets: ['full'] },
  { key: 'arm', title: '单双臂', group: '生产辅助', width: 80, presets: ['fit', 'full'] },
  { key: 'fixture', title: '夹具', group: '生产辅助', width: 78, presets: ['fit', 'full'] },
]

export const uploadedPlanFieldCount = 43

export const schedulingPlannerColumnKeys = [
  'status', 'machineCode', 'moldNo', 'productName',
  'sequence', 'moldA', 'orderNo', 'itemNo',
  'outstandingQuantity', 'progress', 'deliveryDue', 'slack',
  'plannedStart', 'plannedFinish', 'warehouse', 'remark',
] as const

export const schedulingFrozenKeysByPreset: Record<ColumnPreset, readonly string[]> = {
  planner: ['status', 'machineCode', 'moldNo', 'productName'],
  production: ['status', 'machineCode', 'moldNo', 'productName'],
  fit: ['status', 'machineCode', 'moldNo'],
  full: ['status', 'machineCode', 'moldNo', 'productName'],
}

export const schedulingColumnKeys = schedulingColumns.map((column) => String(column.key))
export const maxSchedulingFrozenWidth = 554
export const schedulingDefaultColumnOrder = [
  ...schedulingPlannerColumnKeys,
  ...schedulingColumnKeys.filter((key) => !schedulingPlannerColumnKeys.includes(key as typeof schedulingPlannerColumnKeys[number])),
]

export function normalizeSchedulingColumnOrder(columnOrder: readonly string[], preset: ColumnPreset, customFrozenKeys?: readonly string[]) {
  const frozenKeys = new Set(customFrozenKeys ?? schedulingFrozenKeysByPreset[preset])
  const knownKeys = columnOrder.filter((key) => schedulingColumnKeys.includes(key))
  return [
    ...knownKeys.filter((key) => frozenKeys.has(key)),
    ...knownKeys.filter((key) => !frozenKeys.has(key)),
  ]
}

export function getColumnMoveDecision(columnOrder: readonly string[], key: string, direction: -1 | 1, preset: ColumnPreset, customFrozenKeys?: readonly string[]) {
  const normalizedOrder = normalizeSchedulingColumnOrder(columnOrder, preset, customFrozenKeys)
  const currentIndex = normalizedOrder.indexOf(key)
  const targetIndex = currentIndex + direction
  const frozenKeys = new Set(customFrozenKeys ?? schedulingFrozenKeysByPreset[preset])
  const pinned = frozenKeys.has(key)
  if (currentIndex < 0) return { allowed: false as const, reason: '字段不存在于当前列顺序', targetKey: null }
  if (targetIndex < 0) return { allowed: false as const, reason: pinned ? '已经是冻结区第一列' : '已经是滚动区第一列', targetKey: null }
  if (targetIndex >= normalizedOrder.length) return { allowed: false as const, reason: pinned ? '已经是冻结区最后一列' : '已经是滚动区最后一列', targetKey: null }
  const targetKey = normalizedOrder[targetIndex]!
  if (pinned !== frozenKeys.has(targetKey)) {
    return { allowed: false as const, reason: pinned ? '冻结列不能移动到滚动区' : '普通列不能移动到冻结区', targetKey: null }
  }
  return { allowed: true as const, reason: '', targetKey }
}

export function schedulingColumnWidth(key: string, widths: Readonly<Record<string, number>>) {
  const column = schedulingColumns.find((item) => String(item.key) === key)
  return widths[key] ?? column?.width ?? 0
}

export function schedulingFrozenWidth(frozenKeys: readonly string[], widths: Readonly<Record<string, number>>) {
  return frozenKeys.reduce((total, key) => total + schedulingColumnWidth(key, widths), 0)
}

export function getFrozenColumnToggleDecision(
  frozenKeys: readonly string[],
  key: string,
  visibleKeys: readonly string[],
  widths: Readonly<Record<string, number>>,
) {
  if (frozenKeys.includes(key)) return { allowed: true as const, reason: '' }
  if (!visibleKeys.includes(key)) return { allowed: false as const, reason: '请先显示该字段，再将它设为冻结列' }
  const nextWidth = schedulingFrozenWidth([...frozenKeys, key], widths)
  if (nextWidth > maxSchedulingFrozenWidth) {
    return { allowed: false as const, reason: `冻结宽度将达到 ${nextWidth}px，超过 ${maxSchedulingFrozenWidth}px 的小屏预算` }
  }
  return { allowed: true as const, reason: '' }
}
