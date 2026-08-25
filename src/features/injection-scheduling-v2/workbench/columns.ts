import type {
  WorkbenchCellChange,
  WorkbenchColumn,
  WorkbenchColumnPreset,
  WorkbenchEditableField,
  WorkbenchJob,
} from './types'
import { dueSlackPresentation, formatAClass, priorityPresentation, statusPresentation } from './presentation'

const frozen: WorkbenchColumn[] = [
  { key: 'machineCode', label: '机台', width: 88, frozen: true },
  { key: 'status', label: '状态', width: 86, editable: 'status', format: 'status', frozen: true },
  { key: 'orderNo', label: '单号', width: 126, frozen: true },
  { key: 'itemNo', label: '货号', width: 108, frozen: true },
  { key: 'productName', label: '产品名称', width: 180, frozen: true },
  { key: 'moldNo', label: '模号', width: 112, frozen: true },
  { key: 'orderQuantity', label: '订单数', width: 96, format: 'number', frozen: true },
  { key: 'outstandingQuantity', label: '未完数', width: 96, format: 'number', frozen: true },
]

const planning: WorkbenchColumn[] = [
  { key: 'deliveryDueDate', label: '交货日', width: 108, format: 'date' },
  { key: 'deliverySlackDays', label: '交期余量', width: 104, format: 'slack' },
  { key: 'priority', label: '优先级', width: 88, format: 'priority' },
  { key: 'requiredMachineA', label: '要求A级', width: 92, format: 'aClass' },
  { key: 'materialName', label: '原料', width: 112 },
  { key: 'colorName', label: '颜色', width: 104 },
  { key: 'armRequirement', label: '机械手', width: 108 },
  { key: 'fixtureRequirement', label: '夹具', width: 108 },
  { key: 'plannedStart', label: '计划开始', width: 154, editable: 'plannedStart', format: 'datetime' },
  { key: 'plannedFinish', label: '计划完成', width: 154, editable: 'plannedFinish', format: 'datetime' },
  { key: 'shiftTargetQuantity', label: '班次目标', width: 104, editable: 'shiftTargetQuantity', format: 'number' },
  { key: 'warehouseText', label: '仓位', width: 100, editable: 'warehouseText' },
  { key: 'materialReadinessStatus', label: '齐料', width: 90 },
  { key: 'parsedConstraintSummary', label: '机台限制', width: 220 },
  { key: 'orderRemark', label: '订单备注', width: 210, editable: 'orderRemark' },
]

const reporting: WorkbenchColumn[] = [
  { key: 'shiftTargetQuantity', label: '班次目标', width: 104, editable: 'shiftTargetQuantity', format: 'number' },
  { key: 'todayDayQuantity', label: '今日白班', width: 104, format: 'number' },
  { key: 'todayNightQuantity', label: '今日夜班', width: 104, format: 'number' },
  { key: 'openingCompletedQuantity', label: '接管已完', width: 104, format: 'number' },
  { key: 'reportedQuantity', label: '累计回报', width: 104, format: 'number' },
  { key: 'completedQuantity', label: '已完数', width: 98, format: 'number' },
  { key: 'completionRate', label: '完成率', width: 90, format: 'percent' },
  { key: 'downtimeMinutes', label: '停机分钟', width: 98, format: 'number' },
  { key: 'estimatedFinish', label: '预计完成', width: 154, format: 'datetime' },
  { key: 'materialReadinessStatus', label: '齐料', width: 90 },
  { key: 'warehouseText', label: '仓位', width: 100, editable: 'warehouseText' },
  { key: 'orderRemark', label: '异常/备注', width: 220, editable: 'orderRemark' },
]

const extended: WorkbenchColumn[] = [
  { key: 'setQuantity', label: '套数', width: 86, format: 'number' },
  { key: 'moldName', label: '模具名称', width: 160 },
  { key: 'sprueRatio', label: '水口比', width: 86, format: 'decimal' },
  { key: 'colorPowderCode', label: '色粉编码', width: 106 },
  { key: 'netWeightG', label: '净重g', width: 88, format: 'decimal' },
  { key: 'grossWeightG', label: '毛重g', width: 88, format: 'decimal' },
  { key: 'materialWeightKg', label: '用料kg', width: 92, format: 'decimal' },
  { key: 'unitPrice', label: '单价', width: 86, format: 'decimal' },
  { key: 'sprayRequired', label: '喷油', width: 78, format: 'boolean' },
  { key: 'orderDate', label: '下单日', width: 108, format: 'date' },
  { key: 'deliveryStartDate', label: '交期开始', width: 108, format: 'date' },
  { key: 'locked', label: '锁定', width: 76, editable: 'locked', format: 'boolean' },
  { key: 'manualOverrideReason', label: '人工原因', width: 180, editable: 'manualOverrideReason' },
  { key: 'machineRemark', label: '机台备注', width: 200 },
  { key: 'suggestionReason', label: '建议理由', width: 220 },
  { key: 'moldEnrichmentStatus', label: '模具补全', width: 106 },
  { key: 'sourceSheetName', label: '来源工作表', width: 130 },
  { key: 'sourceRowNumber', label: '来源行', width: 86, format: 'number' },
  { key: 'updatedByName', label: '最后修改人', width: 112 },
  { key: 'updatedAt', label: '最后修改', width: 154, format: 'datetime' },
]

function uniqueColumns(columns: WorkbenchColumn[]) {
  const seen = new Set<keyof WorkbenchJob>()
  return columns.filter((column) => !seen.has(column.key) && seen.add(column.key))
}

export const workbenchColumnPresets: Record<WorkbenchColumnPreset, WorkbenchColumn[]> = {
  scheduler: uniqueColumns([...frozen, ...planning]),
  reporter: uniqueColumns([...frozen, ...reporting]),
  full: uniqueColumns([...frozen, ...planning, ...reporting, ...extended]),
}

export function formatWorkbenchCell(job: WorkbenchJob, column: WorkbenchColumn) {
  const value = job[column.key]
  if (value == null || value === '') return '—'
  if (column.format === 'status') return statusPresentation(job.status).label
  if (column.format === 'priority') return priorityPresentation(String(value)).label
  if (column.format === 'slack') return dueSlackPresentation(Number(value)).label
  if (column.format === 'aClass') return formatAClass(Number(value))
  if (column.format === 'boolean') return value ? '是' : '否'
  if (column.format === 'percent') return `${(Number(value) * 100).toFixed(1)}%`
  if (column.format === 'number') return Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 0 })
  if (column.format === 'decimal') return Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
  if (column.format === 'datetime') return String(value).replace('T', ' ')
  return String(value)
}

export function normalizeWorkbenchEdit(field: WorkbenchEditableField, raw: string): string | number | boolean {
  const value = raw.trim()
  if (field === 'shiftTargetQuantity') {
    const parsed = Number(value.replaceAll(',', ''))
    if (!Number.isFinite(parsed) || parsed < 0) throw new Error('班次目标必须是不小于零的数字')
    return parsed
  }
  if (field === 'locked') {
    if (!['是', '否', 'true', 'false', '1', '0'].includes(value.toLowerCase())) throw new Error('锁定列只能输入是或否')
    return ['是', 'true', '1'].includes(value.toLowerCase())
  }
  if (field === 'status') {
    const status = ({ '已排': 'PLANNED', '已排队': 'PLANNED', '暂停': 'PAUSED', PLANNED: 'PLANNED', PAUSED: 'PAUSED' } as Record<string, string>)[value]
    if (!status) throw new Error('规划状态只能输入已排或暂停')
    return status
  }
  return value
}

export function buildPasteChanges(
  jobs: WorkbenchJob[],
  columns: WorkbenchColumn[],
  startRow: number,
  startColumn: number,
  clipboardText: string,
) {
  const matrix = clipboardText.replace(/\r/g, '').split('\n').filter((row, index, rows) => row.length > 0 || index < rows.length - 1).map((row) => row.split('\t'))
  const changes: WorkbenchCellChange[] = []
  matrix.forEach((row, rowOffset) => row.forEach((raw, columnOffset) => {
    const job = jobs[startRow + rowOffset]
    const column = columns[startColumn + columnOffset]
    if (!job || !column?.editable) return
    changes.push({
      jobId: job.id,
      expectedTaskRevision: job.taskRevision,
      expectedOrderRevision: job.orderRevision,
      field: column.editable,
      value: normalizeWorkbenchEdit(column.editable, raw),
    })
  }))
  if (!changes.length) throw new Error('粘贴区域没有可编辑单元格')
  if (changes.length > 200) throw new Error('一次最多保存 200 个单元格')
  return changes
}
