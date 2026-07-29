import { taskRiskMeta } from '@/lib/injectionSchedulingPresentation'
import type {
  InjectionMachine,
  ScheduleFieldScheme,
  ScheduleTask,
} from '@/types/injectionScheduling'

export type ScheduleSpreadsheetColumnKey =
  | 'sequence'
  | 'machine'
  | 'automationMode'
  | 'remark'
  | 'itemNo'
  | 'warehouse'
  | 'machineRequirement'
  | 'moldNo'
  | 'productName'
  | 'orderNo'
  | 'setQuantity'
  | 'orderQuantity'
  | 'completedQuantity'
  | 'remainingQuantity'
  | 'dailyTarget'
  | 'productionDays'
  | 'completionRate'
  | 'material'
  | 'waterRatio'
  | 'color'
  | 'colorPowder'
  | 'netWeight'
  | 'grossWeight'
  | 'materialWeight'
  | 'sprayPaint'
  | 'orderDate'
  | 'deliveryStart'
  | 'deliveryDue'
  | 'moldChangeReference'
  | 'colorChangeReference'
  | 'changeover'
  | 'downtime'
  | 'plannedStart'
  | 'plannedEnd'
  | 'plannedMonth'
  | 'inboundAt'
  | 'deliverySlack'
  | 'materialShortage'
  | 'allocatedMaterial'
  | 'shiftEnd'
  | 'shiftTarget'
  | 'dayShift'
  | 'nightShift'
  | 'unitPrice'
  | 'outsourcingPrice'
  | 'ratio'
  | 'status'

export interface ScheduleSpreadsheetColumn {
  key: ScheduleSpreadsheetColumnKey
  label: string
  group: string
  width: number
  minWidth: number
  maxWidth: number
  align: 'left' | 'center' | 'right'
  frozen?: boolean
  sensitive?: boolean
  schemes: ScheduleFieldScheme[]
  value: (task: ScheduleTask, machine: InjectionMachine, rowIndex: number) => string | number | null | undefined
}

const allSchemes: ScheduleFieldScheme[] = ['core', 'full', 'screen']
const fullOnly: ScheduleFieldScheme[] = ['full']
const coreAndFull: ScheduleFieldScheme[] = ['core', 'full']
const productionSchemes: ScheduleFieldScheme[] = ['core', 'full', 'screen']

function dateOnly(value?: string) {
  if (!value) return undefined
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    timeZone: 'Asia/Shanghai',
  }).format(date).replace('/', '-')
}

function dateTime(value?: string) {
  if (!value) return undefined
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Asia/Shanghai',
  }).format(date).replace('/', '-')
}

function decimal(value: number | undefined, digits = 1) {
  return value == null ? undefined : Number(value.toFixed(digits))
}

export const scheduleSpreadsheetColumns: ScheduleSpreadsheetColumn[] = [
  { key: 'sequence', label: '拖动/序号', group: '机台与基础信息', width: 70, minWidth: 62, maxWidth: 92, align: 'center', frozen: true, schemes: fullOnly, value: (task, _machine, rowIndex) => task.current ? '锁定' : rowIndex + 1 },
  { key: 'machine', label: '机位', group: '机台与基础信息', width: 82, minWidth: 72, maxWidth: 110, align: 'center', frozen: true, schemes: allSchemes, value: (_task, machine) => machine.name },
  { key: 'automationMode', label: '是否全自动', group: '机台与基础信息', width: 92, minWidth: 82, maxWidth: 130, align: 'center', frozen: true, schemes: fullOnly, value: (task) => task.worksheet.automationMode },
  { key: 'remark', label: '备注', group: '机台与基础信息', width: 150, minWidth: 110, maxWidth: 260, align: 'left', frozen: true, schemes: productionSchemes, value: (task) => task.worksheet.remark || task.remark },
  { key: 'itemNo', label: '货号', group: '机台与基础信息', width: 126, minWidth: 105, maxWidth: 190, align: 'left', frozen: true, schemes: fullOnly, value: (task) => task.requirement.itemNo },
  { key: 'warehouse', label: '仓库', group: '机台与基础信息', width: 92, minWidth: 76, maxWidth: 150, align: 'left', frozen: true, schemes: fullOnly, value: (task) => task.worksheet.warehouse },
  { key: 'machineRequirement', label: '安机/机型要求', group: '机台与基础信息', width: 116, minWidth: 96, maxWidth: 160, align: 'center', frozen: true, schemes: allSchemes, value: (task) => task.worksheet.machineClassRequirement },
  { key: 'moldNo', label: '工模', group: '机台与基础信息', width: 138, minWidth: 118, maxWidth: 190, align: 'left', frozen: true, schemes: allSchemes, value: (task) => task.requirement.mold.moldNo },
  { key: 'productName', label: '名称', group: '机台与基础信息', width: 220, minWidth: 150, maxWidth: 360, align: 'left', schemes: allSchemes, value: (task) => task.requirement.productName },
  { key: 'orderNo', label: '单号', group: '机台与基础信息', width: 146, minWidth: 120, maxWidth: 210, align: 'left', schemes: allSchemes, value: (task) => task.requirement.orderNo },
  { key: 'setQuantity', label: '套数', group: '订单与产能', width: 86, minWidth: 72, maxWidth: 110, align: 'right', schemes: fullOnly, value: (task) => task.worksheet.setQuantity },
  { key: 'orderQuantity', label: '订单数', group: '订单与产能', width: 88, minWidth: 76, maxWidth: 118, align: 'right', schemes: allSchemes, value: (task) => task.production.orderQuantity },
  { key: 'completedQuantity', label: '已啤数', group: '订单与产能', width: 88, minWidth: 76, maxWidth: 118, align: 'right', schemes: allSchemes, value: (task) => task.production.completedQuantity },
  { key: 'remainingQuantity', label: '欠数', group: '订单与产能', width: 88, minWidth: 76, maxWidth: 118, align: 'right', schemes: allSchemes, value: (task) => task.production.remainingQuantity },
  { key: 'dailyTarget', label: '计划日目标', group: '订单与产能', width: 94, minWidth: 82, maxWidth: 124, align: 'right', schemes: allSchemes, value: (task) => task.production.effectiveDailyTarget },
  { key: 'productionDays', label: '啤货天数', group: '订单与产能', width: 88, minWidth: 76, maxWidth: 116, align: 'right', schemes: fullOnly, value: (task) => task.worksheet.productionDays ?? decimal(task.production.productionDurationHours / 24, 2) },
  { key: 'completionRate', label: '完成率', group: '订单与产能', width: 82, minWidth: 72, maxWidth: 108, align: 'right', schemes: fullOnly, value: (task) => task.production.orderQuantity > 0 ? `${Math.round(task.production.completedQuantity / task.production.orderQuantity * 100)}%` : undefined },
  { key: 'material', label: '用料', group: '材料、颜色与重量', width: 132, minWidth: 106, maxWidth: 210, align: 'left', schemes: allSchemes, value: (task) => task.requirement.material },
  { key: 'waterRatio', label: '水口比例', group: '材料、颜色与重量', width: 82, minWidth: 72, maxWidth: 110, align: 'center', schemes: fullOnly, value: (task) => task.worksheet.waterRatio },
  { key: 'color', label: '颜色', group: '材料、颜色与重量', width: 104, minWidth: 88, maxWidth: 150, align: 'left', schemes: allSchemes, value: (task) => task.requirement.color },
  { key: 'colorPowder', label: '色粉', group: '材料、颜色与重量', width: 98, minWidth: 82, maxWidth: 150, align: 'left', schemes: fullOnly, value: (task) => task.worksheet.colorPowder },
  { key: 'netWeight', label: '净重(g)', group: '材料、颜色与重量', width: 88, minWidth: 76, maxWidth: 116, align: 'right', schemes: fullOnly, value: (task) => task.worksheet.netWeightGrams },
  { key: 'grossWeight', label: '毛重/整啤(g)', group: '材料、颜色与重量', width: 106, minWidth: 90, maxWidth: 136, align: 'right', schemes: fullOnly, value: (task) => task.worksheet.grossWeightGrams },
  { key: 'materialWeight', label: '用料重(KG)', group: '材料、颜色与重量', width: 100, minWidth: 88, maxWidth: 132, align: 'right', schemes: fullOnly, value: (task) => task.worksheet.materialWeightKg },
  { key: 'sprayPaint', label: '是否喷油', group: '材料、颜色与重量', width: 84, minWidth: 72, maxWidth: 110, align: 'center', schemes: fullOnly, value: (task) => task.worksheet.sprayPaint },
  { key: 'orderDate', label: '下单期', group: '排程日期与切换损耗', width: 126, minWidth: 112, maxWidth: 150, align: 'center', schemes: fullOnly, value: (task) => dateOnly(task.worksheet.orderDate) },
  { key: 'deliveryStart', label: '开始交货期', group: '排程日期与切换损耗', width: 126, minWidth: 112, maxWidth: 150, align: 'center', schemes: fullOnly, value: (task) => dateOnly(task.worksheet.deliveryStartAt) },
  { key: 'deliveryDue', label: '交货完成期', group: '排程日期与切换损耗', width: 126, minWidth: 112, maxWidth: 150, align: 'center', schemes: fullOnly, value: (task) => dateOnly(task.worksheet.deliveryDueAt || task.timing.deliveryDueAt) },
  { key: 'moldChangeReference', label: '转模参考时间', group: '排程日期与切换损耗', width: 104, minWidth: 92, maxWidth: 134, align: 'right', schemes: fullOnly, value: (task) => decimal(task.worksheet.moldChangeReferenceHours, 2) },
  { key: 'colorChangeReference', label: '转色参考时间', group: '排程日期与切换损耗', width: 104, minWidth: 92, maxWidth: 134, align: 'right', schemes: fullOnly, value: (task) => decimal(task.worksheet.colorChangeReferenceHours, 2) },
  { key: 'changeover', label: '转模/色时间', group: '排程日期与切换损耗', width: 100, minWidth: 88, maxWidth: 130, align: 'right', schemes: fullOnly, value: (task) => task.worksheet.changeoverHours ?? decimal(task.changeover.totalHours, 2) },
  { key: 'downtime', label: '机/模故时间', group: '排程日期与切换损耗', width: 100, minWidth: 88, maxWidth: 130, align: 'right', schemes: fullOnly, value: (task) => task.worksheet.downtimeHours },
  { key: 'plannedStart', label: '计划生产期', group: '排程日期与切换损耗', width: 138, minWidth: 120, maxWidth: 170, align: 'center', schemes: fullOnly, value: (task) => dateTime(task.worksheet.plannedProductionAt || task.timing.plannedStart) },
  { key: 'plannedEnd', label: '计划完成期', group: '排程日期与切换损耗', width: 138, minWidth: 120, maxWidth: 170, align: 'center', schemes: productionSchemes, value: (task) => dateTime(task.worksheet.plannedCompletionAt || task.timing.plannedEnd) },
  { key: 'plannedMonth', label: '计划完成月', group: '排程日期与切换损耗', width: 102, minWidth: 88, maxWidth: 130, align: 'center', schemes: fullOnly, value: (task) => task.worksheet.plannedCompletionMonth },
  { key: 'inboundAt', label: '入库期', group: '排程日期与切换损耗', width: 126, minWidth: 112, maxWidth: 150, align: 'center', schemes: coreAndFull, value: (task) => dateOnly(task.worksheet.inboundAt || task.timing.inboundAt) },
  { key: 'deliverySlack', label: '交期差', group: '排程日期与切换损耗', width: 92, minWidth: 78, maxWidth: 120, align: 'right', schemes: productionSchemes, value: (task) => task.worksheet.deliverySlackDays != null ? `${decimal(task.worksheet.deliverySlackDays, 1)}天` : `${decimal(task.timing.slackHours / 24, 1)}天` },
  { key: 'materialShortage', label: '料欠', group: '配料与班次', width: 86, minWidth: 74, maxWidth: 112, align: 'right', schemes: fullOnly, value: (task) => task.worksheet.materialShortage },
  { key: 'allocatedMaterial', label: '已配料数', group: '配料与班次', width: 92, minWidth: 78, maxWidth: 120, align: 'right', schemes: fullOnly, value: (task) => task.worksheet.allocatedMaterialQuantity },
  { key: 'shiftEnd', label: '每班结束时间', group: '配料与班次', width: 112, minWidth: 96, maxWidth: 150, align: 'center', schemes: fullOnly, value: (task) => task.worksheet.shiftEndAt || task.worksheet.shiftTime },
  { key: 'shiftTarget', label: '每班计划啤数', group: '配料与班次', width: 108, minWidth: 94, maxWidth: 142, align: 'right', schemes: fullOnly, value: (task) => task.worksheet.shiftTarget },
  { key: 'dayShift', label: '白班', group: '配料与班次', width: 82, minWidth: 72, maxWidth: 108, align: 'right', schemes: fullOnly, value: (task) => task.worksheet.dayShiftQuantity },
  { key: 'nightShift', label: '晚班', group: '配料与班次', width: 82, minWidth: 72, maxWidth: 108, align: 'right', schemes: fullOnly, value: (task) => task.worksheet.nightShiftQuantity },
  { key: 'unitPrice', label: '单价/啤', group: '商业字段（受限）', width: 92, minWidth: 80, maxWidth: 120, align: 'right', sensitive: true, schemes: [], value: (task) => task.worksheet.unitPricePerShot },
  { key: 'outsourcingPrice', label: '外发单价', group: '商业字段（受限）', width: 94, minWidth: 82, maxWidth: 124, align: 'right', sensitive: true, schemes: [], value: (task) => task.worksheet.outsourcingUnitPrice },
  { key: 'ratio', label: '比例', group: '商业字段（受限）', width: 82, minWidth: 72, maxWidth: 108, align: 'right', sensitive: true, schemes: [], value: (task) => task.worksheet.ratio },
  { key: 'status', label: '状态', group: '排程状态', width: 92, minWidth: 80, maxWidth: 120, align: 'center', schemes: coreAndFull, value: (task) => taskRiskMeta[task.risk].label },
]

export const defaultScheduleSpreadsheetWidths = Object.fromEntries(
  scheduleSpreadsheetColumns.map((column) => [column.key, column.width]),
) as Record<ScheduleSpreadsheetColumnKey, number>

export function scheduleColumnsForScheme(scheme: ScheduleFieldScheme) {
  return scheduleSpreadsheetColumns.filter((column) => (
    !column.sensitive && column.schemes.includes(scheme)
  ))
}

export function formatScheduleCellValue(value: string | number | null | undefined) {
  if (value == null || value === '') return '—'
  if (typeof value === 'number') {
    return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(value)
  }
  return value
}
