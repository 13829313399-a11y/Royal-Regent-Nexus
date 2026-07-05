<script setup lang="ts">
import {
  AlertTriangle,
  Boxes,
  Database,
  FileSpreadsheet,
  FileText,
  Layers3,
  Package,
  Plus,
  RefreshCcw,
  Search,
  SquareTerminal,
  UploadCloud,
  Waypoints,
} from '@lucide/vue'
import { strFromU8, unzipSync } from 'fflate'
import { computed, ref } from 'vue'
import ProgressMeter from '@/components/common/ProgressMeter.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import type { Tone } from '@/data/enterpriseMock'
import type { InjectionSectionId } from '@/data/injectionSchedulingMock'
import { useInjectionModuleData } from '@/factories/injection/useInjectionModuleData'
import { useInjectionWorkflowBridge } from '@/factories/injection/useInjectionWorkflowBridge'

const props = defineProps<{
  activeSection: InjectionSectionId
}>()
const emit = defineEmits<{
  (e: 'change-section', section: InjectionSectionId): void
}>()

const {
  activeProductionFactoryId,
  injectionColorTransitionRisks,
  injectionExecutionCandidateRows,
  injectionExecutionConstraintRows,
  injectionExecutionRuleMetrics,
  injectionExecutionScheduleRows,
  injectionExecutionTasks,
  injectionInboundWritebackRows,
  injectionMachineLoad,
  injectionMachineMasterRows,
  injectionMoldMachineMappingRows,
  injectionMoldTargetDetailRows,
  injectionOverviewMetrics,
  injectionPendingOrderDetailRows,
  injectionShiftHandoverRows,
  injectionShiftReportRows,
  injectionShiftSummaries,
  injectionWarehouseInboundRows,
  injectionWorkflowStages,
} = useInjectionModuleData()

interface ActivePendingOrderRow {
  poolKey?: string
  orderNo: string
  customer: string
  productName: string
  moldCode: string
  color: string
  material: string
  quantity: string
  dueDate: string
  machineAdvice: string
  machineModel?: string
  armType?: string
  remark?: string
  moldSize?: string
  issue: string
  tone: Tone
}

const importedOrderPoolActive = ref(false)
const importedPendingOrderRows = ref<ActivePendingOrderRow[]>([])
const manualPendingOrderRows = ref<ActivePendingOrderRow[]>([])
const pendingOrderSearchText = ref('')
const pendingOrderStatusFilter = ref<'all' | 'ready' | 'confirmed' | 'attention'>('all')
const manualOrderFormVisible = ref(false)
const manualOrderForm = ref({
  orderNo: '',
  customer: '',
  productName: '',
  moldCode: '',
  color: '',
  material: '',
  quantity: '',
  dueDate: '',
  machineModel: '',
  remark: '',
})

const activePendingOrderRows = computed(() =>
  [
    ...(importedOrderPoolActive.value ? importedPendingOrderRows.value : injectionPendingOrderDetailRows.value),
    ...manualPendingOrderRows.value,
  ],
)
const compactPendingOrders = computed(() => activePendingOrderRows.value)
const compactCandidateRows = computed(() => injectionExecutionCandidateRows.value.slice(0, 8))
const compactScheduleRows = computed(() => injectionExecutionScheduleRows.value.slice(0, 8))
const compactMachineRows = computed(() => injectionMachineMasterRows.value)

const {
  selectedPendingOrderMachines,
  schedulingDraftGenerated,
  schedulingReviewRequested,
  schedulingDraftReleased,
  shiftReportDraftSubmitted,
  inboundWritebackDraftConfirmed,
  getPendingOrderMachineKey,
  getPendingOrderMachineOptions,
  getSelectedPendingOrderMachine,
  handlePendingOrderMachineChange,
  handleDraftMachineChange,
  getPendingOrderStatusLabel,
  getPendingOrderStatusTone,
  pendingOrderMachineDraftRows,
  schedulingDraftMetrics,
  releasedExecutionRows,
  shiftReportDraftRows,
  shiftReportDraftMetrics,
  inboundWritebackDraftRows,
  inboundWritebackDraftMetrics,
  generateSchedulingDraft,
  submitSchedulingReview,
  approveSchedulingDraft,
  submitShiftReportDraft,
  confirmInboundWritebackDraft,
} = useInjectionWorkflowBridge({
  pendingOrders: compactPendingOrders,
  moldMachineMappingRows: injectionMoldMachineMappingRows,
  storageKey: computed(() => `injection-workflow:${activeProductionFactoryId.value}`),
})

const isSchedulingWorkbench = computed(() =>
  props.activeSection === 'order-import',
)

const manualMachineEditCount = computed(() =>
  compactPendingOrders.value.filter((row) => selectedPendingOrderMachines.value[getPendingOrderMachineKey(row)]).length,
)

const schedulingWorkbenchSteps = computed(() => [
  {
    label: '订单池',
    value: compactPendingOrders.value.length,
    detail: importedOrderPoolActive.value ? '上传订单已入池' : '当前使用默认订单池',
    tone: compactPendingOrders.value.length > 0 ? 'teal' : 'slate',
  },
  {
    label: '智能排机',
    value: pendingOrderMachineDraftRows.value.length,
    detail: schedulingDraftGenerated.value ? '已生成排机草稿' : '等待文员点击排机',
    tone: schedulingDraftGenerated.value ? 'blue' : 'slate',
  },
  {
    label: '人工微调',
    value: manualMachineEditCount.value,
    detail: manualMachineEditCount.value > 0 ? '已手动改选机台' : '可直接按系统推荐',
    tone: manualMachineEditCount.value > 0 ? 'green' : 'amber',
  },
  {
    label: '主管审核',
    value: schedulingDraftReleased.value ? '通过' : schedulingReviewRequested.value ? '待审' : '未提',
    detail: schedulingDraftReleased.value
      ? '已通过并下发执行'
      : schedulingReviewRequested.value
          ? '等待主管确认'
          : '草稿完成后提交',
    tone: schedulingDraftReleased.value ? 'green' : schedulingReviewRequested.value ? 'amber' : 'slate',
  },
] satisfies { label: string; value: string | number; detail: string; tone: PanelTone }[])

const panelTone = {
  green: 'bg-emerald-50 border-emerald-100',
  blue: 'bg-blue-50 border-blue-100',
  amber: 'bg-amber-50 border-amber-100',
  red: 'bg-red-50 border-red-100',
  teal: 'bg-teal-50 border-teal-100',
  slate: 'bg-slate-100 border-slate-200',
} as const

type PanelTone = keyof typeof panelTone

const pendingOrderFilters = [
  { key: 'all', label: '全部' },
  { key: 'ready', label: '可排' },
  { key: 'confirmed', label: '人工已选' },
  { key: 'attention', label: '待补规则' },
] as const

const getPendingOrderPoolState = (row: ActivePendingOrderRow) => {
  const key = getPendingOrderMachineKey(row)
  const hasManualSelection = Boolean(selectedPendingOrderMachines.value[key])
  const hasOptions = getPendingOrderMachineOptions(row).length > 0

  if (hasManualSelection) {
    return 'confirmed'
  }

  return hasOptions ? 'ready' : 'attention'
}

const pendingOrderPoolSummaryCards = computed(() => {
  const total = compactPendingOrders.value.length
  const confirmed = compactPendingOrders.value.filter((row) => getPendingOrderPoolState(row) === 'confirmed').length
  const ready = compactPendingOrders.value.filter((row) => getPendingOrderPoolState(row) === 'ready').length
  const attention = compactPendingOrders.value.filter((row) => getPendingOrderPoolState(row) === 'attention').length

  return [
    { label: '订单池', value: total, detail: importedOrderPoolActive.value ? '上传订单 + 手工补单' : '默认订单 + 手工补单', tone: total > 0 ? 'teal' : 'slate' },
    { label: '可直接排机', value: ready, detail: '已有候选机台，可进入排机草稿', tone: ready > 0 ? 'blue' : 'slate' },
    { label: '人工已选', value: confirmed, detail: '计划员已确认下发机台', tone: confirmed > 0 ? 'green' : 'slate' },
    { label: '待补规则', value: attention, detail: '缺机台候选或模具映射', tone: attention > 0 ? 'amber' : 'green' },
  ] satisfies { label: string; value: number; detail: string; tone: PanelTone }[]
})

const filteredPendingOrders = computed(() => {
  const keyword = pendingOrderSearchText.value.trim().toLowerCase()

  return compactPendingOrders.value.filter((row) => {
    const state = getPendingOrderPoolState(row)
    const matchesFilter = pendingOrderStatusFilter.value === 'all' || state === pendingOrderStatusFilter.value
    const haystack = [
      row.orderNo,
      row.customer,
      row.productName,
      row.moldCode,
      row.color,
      row.material,
      row.machineAdvice,
      row.issue,
    ].join(' ').toLowerCase()

    return matchesFilter && (!keyword || haystack.includes(keyword))
  })
})

const resetManualOrderForm = () => {
  manualOrderForm.value = {
    orderNo: '',
    customer: '',
    productName: '',
    moldCode: '',
    color: '',
    material: '',
    quantity: '',
    dueDate: '',
    machineModel: '',
    remark: '',
  }
}

const createManualPendingOrder = () => {
  const form = manualOrderForm.value
  if (!form.orderNo.trim() || !form.productName.trim() || !form.moldCode.trim() || !form.quantity.trim()) {
    return
  }

  const mapping = injectionMoldMachineMappingRows.value.find((row) => row.moldCode === form.moldCode.trim())
  const machineAdvice = mapping
    ? [mapping.recommendedMachine, mapping.backupMachine].filter(Boolean).join(' / ')
    : '待系统推荐'

  manualPendingOrderRows.value = [
    {
      poolKey: `manual-${Date.now()}-${form.orderNo.trim()}-${form.moldCode.trim()}`,
      orderNo: form.orderNo.trim(),
      customer: form.customer.trim() || form.orderNo.trim().slice(0, 3) || '手工客户',
      productName: form.productName.trim(),
      moldCode: form.moldCode.trim(),
      color: form.color.trim() || '待补颜色',
      material: form.material.trim() || '待补料型',
      quantity: form.quantity.trim(),
      dueDate: form.dueDate.trim() || '待补交期',
      machineAdvice,
      machineModel: form.machineModel.trim(),
      armType: '',
      remark: form.remark.trim(),
      moldSize: '待补尺寸',
      issue: machineAdvice === '待系统推荐' ? '待补规则' : '手工补单',
      tone: machineAdvice === '待系统推荐' ? 'amber' : 'blue',
    },
    ...manualPendingOrderRows.value,
  ]
  resetManualOrderForm()
  manualOrderFormVisible.value = false
}

const isMissingMasterDataValue = (value: string | undefined) =>
  !value || value.includes('待补') || value.includes('未填写') || value.includes('待建')

interface DraftReferenceRow {
  selectedMachine: string
  moldCode: string
  machineModel?: string
  armType?: string
  remark?: string
  moldSize?: string
}

const getDraftMachineProfile = (row: DraftReferenceRow) =>
  injectionMachineMasterRows.value.find((machine) => machine.machine === row.selectedMachine)

const getDraftRequiredMachineModel = (row: DraftReferenceRow) =>
  row.machineModel?.trim() || '待补推荐机型'

const getDraftSelectedMachineType = (row: DraftReferenceRow) => {
  const machine = getDraftMachineProfile(row)

  return machine ? `${machine.tonnage} · ${machine.processRange}` : '机台资料待补'
}

const getDraftSelectedMachineHardware = (row: DraftReferenceRow) => {
  const machine = getDraftMachineProfile(row)

  return machine ? `${machine.screw} · ${machine.robot}` : '缺机台台账'
}

const getDraftMoldDetail = (row: DraftReferenceRow) =>
  injectionMoldTargetDetailRows.value.find((mold) => mold.moldCode === row.moldCode)

const getDraftMoldSize = (row: DraftReferenceRow) =>
  row.moldSize && !isMissingMasterDataValue(row.moldSize) ? row.moldSize : '待补尺寸'

const getDraftMoldReference = (row: DraftReferenceRow) => {
  const mold = getDraftMoldDetail(row)
  const cavity = mold?.cavity && !isMissingMasterDataValue(mold.cavity) ? mold.cavity : '穴数待补'
  const cycleTime = mold?.cycleTime && !isMissingMasterDataValue(mold.cycleTime) ? mold.cycleTime : '节拍待补'

  return `${getDraftMoldSize(row)} · ${cavity} · ${cycleTime}`
}

const getDraftSprayLabel = (row: DraftReferenceRow) =>
  row.remark?.includes('喷油') ? '需喷油' : '普通注塑'

const getDraftSprayTone = (row: DraftReferenceRow): Tone =>
  row.remark?.includes('喷油') ? 'amber' : 'slate'

const getDraftProcessRemark = (row: DraftReferenceRow) =>
  row.remark?.trim() || '无特殊工艺备注'

const getDraftArmRequirement = (row: DraftReferenceRow) =>
  row.armType?.trim() || '机械手未指定'

const workflowTone = {
  done: 'green',
  active: 'blue',
  pending: 'slate',
} as const

type ImportTone = 'green' | 'amber' | 'red' | 'blue' | 'slate' | 'teal'
type ImportFieldKey =
  | 'orderNo'
  | 'customer'
  | 'productName'
  | 'moldCode'
  | 'color'
  | 'material'
  | 'quantity'
  | 'dueDate'
  | 'machineModel'
  | 'remark'

interface ExpectedImportField {
  key: ImportFieldKey
  label: string
  required: boolean
  aliases: string[]
  preferredAliases?: string[]
}

interface ImportedOrderPreviewRow {
  rowNumber: number
  orderNo: string
  customer: string
  productName: string
  moldCode: string
  color: string
  material: string
  quantity: string
  dueDate: string
  machineModel: string
  remark: string
  issue: string
  tone: ImportTone
  errors: string[]
  warnings: string[]
}

const expectedImportFields: ExpectedImportField[] = [
  { key: 'orderNo', label: '订单号', required: true, aliases: ['订单号', '订单编号', '单号', '工单号', '生产单号', '排单号', 'orderNo', 'order no'] },
  { key: 'customer', label: '客户', required: false, aliases: ['客户', '客户名称', '客人', 'customer'] },
  { key: 'productName', label: '产品名称', required: true, aliases: ['产品名称', '产品', '品名', '货品名称', '啤件名称', '制品名称', '名称', 'productName'] },
  { key: 'moldCode', label: '模具编号', required: true, aliases: ['模具编号', '模具编码', '模具号', '模号', '模具', '工模', 'moldCode', 'mold'] },
  { key: 'color', label: '颜色', required: true, aliases: ['颜色', '色号', '色粉', 'color'] },
  { key: 'material', label: '料型', required: true, aliases: ['料型', '材料', '原料', '胶料', '材质', '用料', 'material'] },
  { key: 'quantity', label: '待排数量', required: true, aliases: ['待排数量', '欠数', '数量', '订单数量', '订单数', '订单数套', '需啤啤数', '需啤数', '排产数量', '未完成数量', 'shortage', 'qty'] },
  {
    key: 'dueDate',
    label: '交期',
    required: true,
    aliases: ['交货期', '交货日期', '走货期', '出货日期', '交期', 'delivery', 'dueDate', 'due'],
    preferredAliases: ['交货期', '交货日期', '走货期', '出货日期'],
  },
  { key: 'machineModel', label: '推荐机型', required: false, aliases: ['机型', '推荐机型', '机种', '吨位', '机台类型', 'machineModel'] },
  { key: 'remark', label: '备注', required: false, aliases: ['备注', '工艺备注', '排产备注', '生产备注', '喷油', 'remark', 'note'] },
]

const importFileInput = ref<HTMLInputElement | null>(null)
const importedFileName = ref('')
const importedSheetName = ref('')
const importHeaders = ref<string[]>([])
const importedRows = ref<ImportedOrderPreviewRow[]>([])
const importErrorMessage = ref('')

const importPreviewRows = computed(() => importedRows.value)
const importProblemRows = computed(() =>
  importedRows.value.filter((row) => row.errors.length > 0 || row.warnings.length > 0),
)

const importSummaryCards = computed(() => {
  const total = importedRows.value.length
  const passed = importedRows.value.filter((row) => row.errors.length === 0 && row.warnings.length === 0).length
  const warnings = importedRows.value.filter((row) => row.errors.length === 0 && row.warnings.length > 0).length
  const errors = importedRows.value.filter((row) => row.errors.length > 0).length

  return [
    { label: '预览行数', value: total, detail: importedSheetName.value || '等待上传', tone: total > 0 ? 'teal' : 'slate' },
    { label: '可入池', value: passed, detail: '字段完整且无重复风险，会进入当前订单池', tone: 'green' },
    { label: '待确认', value: warnings, detail: '会进入订单池，但下发前需人工看一眼', tone: warnings > 0 ? 'amber' : 'slate' },
    { label: '错误行', value: errors, detail: '必须补齐后再导入', tone: errors > 0 ? 'red' : 'green' },
  ] satisfies { label: string; value: number; detail: string; tone: ImportTone }[]
})

const normalizeHeader = (value: unknown) =>
  String(value ?? '')
    .trim()
    .toLowerCase()
    .replace(/[\s_：:（）()【】\[\]\/\\.\-*]/g, '')

const scoreHeaderMatch = (header: string, field: ExpectedImportField) => {
  const normalizedHeader = normalizeHeader(header)
  const normalizedAliases = field.aliases.map((alias) => normalizeHeader(alias))
  const normalizedPreferredAliases = (field.preferredAliases ?? []).map((alias) => normalizeHeader(alias))

  if (normalizedPreferredAliases.includes(normalizedHeader)) {
    return 120
  }
  if (normalizedAliases.includes(normalizedHeader)) {
    return 100
  }
  if (normalizedPreferredAliases.some((alias) => alias.length > 1 && normalizedHeader.includes(alias))) {
    return 80
  }
  if (normalizedAliases.some((alias) => alias.length > 1 && normalizedHeader.includes(alias))) {
    return 50
  }

  return 0
}

const findMatchedHeader = (headers: string[], field: ExpectedImportField) =>
  headers
    .map((header, index) => ({ header, index, score: scoreHeaderMatch(header, field) }))
    .filter((item) => item.score > 0)
    .sort((left, right) => right.score - left.score || left.index - right.index)[0]?.header

const readFileAsArrayBuffer = (file: File) => new Promise<ArrayBuffer>((resolve, reject) => {
  const reader = new FileReader()
  reader.onload = () => {
    if (reader.result instanceof ArrayBuffer) {
      resolve(reader.result)
      return
    }

    reject(new Error('文件读取失败'))
  }
  reader.onerror = () => reject(reader.error ?? new Error('文件读取失败'))
  reader.readAsArrayBuffer(file)
})

const parseXml = (content: string) => new DOMParser().parseFromString(content, 'application/xml')

const getZipText = (zip: Record<string, Uint8Array>, path: string) => {
  const file = zip[path]
  return file ? strFromU8(file) : ''
}

const getCellText = (element: Element) =>
  Array.from(element.getElementsByTagName('t'))
    .map((node) => node.textContent ?? '')
    .join('')

const readSharedStrings = (zip: Record<string, Uint8Array>) => {
  const xml = getZipText(zip, 'xl/sharedStrings.xml')
  if (!xml) {
    return []
  }

  const document = parseXml(xml)
  return Array.from(document.getElementsByTagName('si')).map((item) => getCellText(item))
}

const resolveWorksheetPath = (zip: Record<string, Uint8Array>) => {
  const workbookXml = getZipText(zip, 'xl/workbook.xml')
  const relationsXml = getZipText(zip, 'xl/_rels/workbook.xml.rels')

  if (!workbookXml || !relationsXml) {
    return 'xl/worksheets/sheet1.xml'
  }

  const workbook = parseXml(workbookXml)
  const relations = parseXml(relationsXml)
  const firstSheet = Array.from(workbook.getElementsByTagName('sheet'))[0]
  const relationId = firstSheet?.getAttribute('r:id')
  const relation = Array.from(relations.getElementsByTagName('Relationship'))
    .find((item) => item.getAttribute('Id') === relationId)
  const target = relation?.getAttribute('Target') ?? 'worksheets/sheet1.xml'

  return target.startsWith('/xl/') ? target.slice(1) : `xl/${target.replace(/^\/+/, '')}`
}

const columnNameToIndex = (columnName: string) =>
  columnName.split('').reduce((total, char) => total * 26 + char.charCodeAt(0) - 64, 0) - 1

const readXlsxCellValue = (cell: Element, sharedStrings: string[]) => {
  const type = cell.getAttribute('t')

  if (type === 'inlineStr') {
    return getCellText(cell).trim()
  }

  const rawValue = cell.getElementsByTagName('v')[0]?.textContent ?? ''
  if (type === 's') {
    return sharedStrings[Number(rawValue)] ?? ''
  }

  return rawValue.trim()
}

const parseXlsxRows = (buffer: ArrayBuffer) => {
  const zip = unzipSync(new Uint8Array(buffer))
  const sheetPath = resolveWorksheetPath(zip)
  const worksheetXml = getZipText(zip, sheetPath)

  if (!worksheetXml) {
    throw new Error('没有读取到工作表')
  }

  const sharedStrings = readSharedStrings(zip)
  const worksheet = parseXml(worksheetXml)

  return Array.from(worksheet.getElementsByTagName('row')).map((row) => {
    const cells: string[] = []
    Array.from(row.getElementsByTagName('c')).forEach((cell) => {
      const reference = cell.getAttribute('r') ?? ''
      const columnName = reference.match(/[A-Z]+/)?.[0]
      const columnIndex = columnName ? columnNameToIndex(columnName) : cells.length
      cells[columnIndex] = readXlsxCellValue(cell, sharedStrings)
    })

    return cells
  })
}

const parseDelimitedLine = (line: string, delimiter: string) => {
  const cells: string[] = []
  let current = ''
  let inQuotes = false

  for (let index = 0; index < line.length; index += 1) {
    const char = line[index]
    const next = line[index + 1]

    if (char === '"' && next === '"') {
      current += '"'
      index += 1
      continue
    }

    if (char === '"') {
      inQuotes = !inQuotes
      continue
    }

    if (char === delimiter && !inQuotes) {
      cells.push(current.trim())
      current = ''
      continue
    }

    current += char
  }

  cells.push(current.trim())
  return cells
}

const parseDelimitedRows = (buffer: ArrayBuffer, fileName: string) => {
  const text = new TextDecoder('utf-8').decode(buffer).replace(/^\uFEFF/, '')
  const delimiter = fileName.toLowerCase().endsWith('.tsv') || text.includes('\t') ? '\t' : ','

  return text
    .replace(/\r\n/g, '\n')
    .split('\n')
    .map((line) => parseDelimitedLine(line, delimiter))
    .filter(rowHasContent)
}

const normalizeExcelDate = (value: string) => {
  if (!/^\d{5}(?:\.\d+)?$/.test(value)) {
    return value
  }

  const serial = Number(value)
  if (!Number.isFinite(serial) || serial < 20000 || serial > 60000) {
    return value
  }

  const date = new Date(Math.round((serial - 25569) * 86400 * 1000))
  return Number.isNaN(date.getTime()) ? value : date.toISOString().slice(0, 10)
}

const tableRowsToRecords = (rows: unknown[][]) => {
  const headerRowIndex = findHeaderRowIndex(rows)
  const headers = (rows[headerRowIndex] ?? [])
    .map((cell, index) => String(cell ?? '').trim() || `空列${index + 1}`)
  const records = rows.slice(headerRowIndex + 1)
    .map((row) => headers.reduce((record, header, index) => {
      record[header] = String(row[index] ?? '').trim()
      return record
    }, {} as Record<string, unknown>))
    .filter((record) => Object.values(record).some((value) => String(value ?? '').trim()))

  return {
    headerRowIndex,
    headers: headers.filter((header) => !header.startsWith('空列')),
    records,
  }
}

const rowHasContent = (row: unknown[]) => row.some((cell) => String(cell ?? '').trim())

const scoreHeaderRow = (row: unknown[]) => {
  const cells = row.map((cell) => normalizeHeader(cell))

  return expectedImportFields.reduce((score, field) => {
    const aliases = field.aliases.map((alias) => normalizeHeader(alias))
    return score + (cells.some((cell) => aliases.some((alias) => cell === alias || cell.includes(alias))) ? 1 : 0)
  }, 0)
}

const findHeaderRowIndex = (rows: unknown[][]) => {
  let bestIndex = rows.findIndex(rowHasContent)
  let bestScore = -1

  rows.slice(0, 20).forEach((row, index) => {
    const score = scoreHeaderRow(row)
    if (score > bestScore) {
      bestScore = score
      bestIndex = index
    }
  })

  return bestScore >= 3 ? bestIndex : Math.max(bestIndex, 0)
}

const readRecordValue = (
  record: Record<string, unknown>,
  field: ExpectedImportField,
  matchedHeaders: Partial<Record<ImportFieldKey, string>>,
) => {
  const header = matchedHeaders[field.key]
  return header ? String(record[header] ?? '').trim() : ''
}

const normalizeImportedRemark = (value: string, header = '') => {
  const normalizedHeader = normalizeHeader(header)
  const normalizedValue = value.trim()

  if (!normalizedHeader.includes('喷油')) {
    return normalizedValue
  }

  if (!normalizedValue || /^(否|无|不|no|n)$/i.test(normalizedValue)) {
    return normalizedValue
  }

  if (/^(是|yes|y)$/i.test(normalizedValue)) {
    return '喷油'
  }

  return normalizedValue.includes('喷油') ? normalizedValue : `喷油 / ${normalizedValue}`
}

const buildImportedRows = (
  records: Record<string, unknown>[],
  headerRowIndex: number,
  matchedHeaders: Partial<Record<ImportFieldKey, string>>,
) => {
  const baseRows = records
    .map((record, index) => {
      const row = expectedImportFields.reduce((accumulator, field) => {
        const value = readRecordValue(record, field, matchedHeaders)
        accumulator[field.key] = field.key === 'dueDate'
          ? normalizeExcelDate(value)
          : field.key === 'remark'
              ? normalizeImportedRemark(value, matchedHeaders[field.key])
              : value
        return accumulator
      }, {} as Record<ImportFieldKey, string>)

      return {
        ...row,
        rowNumber: headerRowIndex + index + 2,
        issue: '待校验',
        tone: 'slate' as ImportTone,
        errors: [] as string[],
        warnings: [] as string[],
      }
    })
    .filter((row) => expectedImportFields.some((field) => row[field.key].trim()))

  const duplicateCounter = new Map<string, number>()
  baseRows.forEach((row) => {
    const key = `${row.orderNo}::${row.moldCode}`
    if (row.orderNo && row.moldCode) {
      duplicateCounter.set(key, (duplicateCounter.get(key) ?? 0) + 1)
    }
  })

  return baseRows.map((row) => {
    const errors = expectedImportFields
      .filter((field) => field.required && !row[field.key])
      .map((field) => `缺少${field.label}`)
    const quantityNumber = Number(row.quantity.replace(/,/g, ''))

    if (row.quantity && (!Number.isFinite(quantityNumber) || quantityNumber <= 0)) {
      errors.push('待排数量不是有效数字')
    }

    const warnings: string[] = []
    if (duplicateCounter.get(`${row.orderNo}::${row.moldCode}`) && duplicateCounter.get(`${row.orderNo}::${row.moldCode}`)! > 1) {
      warnings.push('同单同模重复')
    }

    const tone: ImportTone = errors.length > 0 ? 'red' : warnings.length > 0 ? 'amber' : 'green'
    const issue = errors.length > 0 ? '错误' : warnings.length > 0 ? '待确认' : '可导入'

    return {
      ...row,
      errors,
      warnings,
      issue,
      tone,
    }
  })
}

const parseImportedMachineTonnage = (tonnage: string) => {
  const matched = tonnage.match(/\d+/)
  return matched ? Number.parseInt(matched[0], 10) : 0
}

const inferImportedMachineBand = (machineModel: string) => {
  const compact = machineModel.replace(/\s+/g, '')
  const bands = [
    { pattern: /50A/, min: 380, max: 550 },
    { pattern: /32A/, min: 300, max: 330 },
    { pattern: /24A/, min: 240, max: 270 },
    { pattern: /18A/, min: 180, max: 210 },
    { pattern: /14A/, min: 140, max: 170 },
    { pattern: /12A/, min: 110, max: 140 },
    { pattern: /10A/, min: 90, max: 120 },
    { pattern: /7A/, min: 80, max: 110 },
    { pattern: /5A/, min: 45, max: 95 },
    { pattern: /4A/, min: 40, max: 85 },
  ] as const

  return bands.find((band) => band.pattern.test(compact)) ?? null
}

const matchesImportedMaterialProcess = (material: string, processRange: string) => {
  const upperMaterial = material.toUpperCase()

  if (upperMaterial.includes('PVC')) {
    return processRange.includes('PVC')
  }

  if (upperMaterial.includes('PC')) {
    return processRange.includes('PC')
  }

  if (upperMaterial.includes('PMMA') || upperMaterial.includes('TPE')) {
    return !processRange.includes('PVC')
  }

  return !processRange.includes('PVC') && !processRange.includes('PC')
}

const splitImportedMachineCandidates = (value = '') =>
  value
    .split('/')
    .map((item) => item.trim())
    .filter((item) => item && !item.includes('待补') && !item.includes('待确认'))

const resolveImportedMachineAdvice = (row: ImportedOrderPreviewRow) => {
  const directMachine = injectionMachineMasterRows.value.find((machine) =>
    row.machineModel.includes(machine.machine),
  )?.machine
  const mapping = injectionMoldMachineMappingRows.value.find((item) => item.moldCode === row.moldCode)
  const band = inferImportedMachineBand(row.machineModel)
  const machineCandidates = injectionMachineMasterRows.value
    .filter((machine) => {
      if (band) {
        const tonnage = parseImportedMachineTonnage(machine.tonnage)
        return tonnage >= band.min
          && tonnage <= band.max
          && matchesImportedMaterialProcess(row.material, machine.processRange)
      }

      return Boolean(row.material) && matchesImportedMaterialProcess(row.material, machine.processRange)
    })
    .sort((left, right) => {
      const toneRank: Record<Tone, number> = { green: 4, blue: 3, amber: 2, teal: 2, slate: 1, red: 0 }
      const statusRank = (status: string) => status === '运行' ? 3 : status === '新购' ? 2 : status === '注意' ? 1 : 0

      return statusRank(right.status) - statusRank(left.status)
        || toneRank[right.tone] - toneRank[left.tone]
        || parseImportedMachineTonnage(left.tonnage) - parseImportedMachineTonnage(right.tonnage)
    })
    .map((machine) => machine.machine)
  const candidates = [
    directMachine,
    mapping?.recommendedMachine,
    mapping?.backupMachine,
    ...machineCandidates,
  ].flatMap((item) => splitImportedMachineCandidates(item))

  return [...new Set(candidates)].slice(0, 4).join(' / ') || '待系统推荐'
}

const buildImportedPendingOrderRows = (rows: ImportedOrderPreviewRow[]): ActivePendingOrderRow[] =>
  rows
    .filter((row) => row.errors.length === 0)
    .map((row) => {
      const machineAdvice = resolveImportedMachineAdvice(row)
      const hasMachineAdvice = machineAdvice !== '待系统推荐'

      return {
        poolKey: `import-${row.rowNumber}-${row.orderNo}-${row.moldCode}`,
        orderNo: row.orderNo,
        customer: row.customer || row.orderNo.slice(0, 3) || '导入客户',
        productName: row.productName,
        moldCode: row.moldCode,
        color: row.color,
        material: row.material,
        quantity: row.quantity,
        dueDate: row.dueDate,
        machineAdvice,
        machineModel: row.machineModel,
        armType: '',
        remark: row.remark,
        moldSize: '待补尺寸',
        issue: hasMachineAdvice ? row.issue : '待补规则',
        tone: hasMachineAdvice ? row.tone : 'amber',
      }
    })

const handleOrderImportFile = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) {
    return
  }

  importErrorMessage.value = ''
  importedFileName.value = file.name

  try {
    const buffer = await readFileAsArrayBuffer(file)
    const fileName = file.name.toLowerCase()
    const matrix = fileName.endsWith('.xlsx')
      ? parseXlsxRows(buffer)
      : parseDelimitedRows(buffer, file.name)
    const { headerRowIndex, headers, records } = tableRowsToRecords(matrix)
    const matchedHeaders = expectedImportFields.reduce((accumulator, field) => {
      const matchedHeader = findMatchedHeader(headers, field)
      if (matchedHeader) {
        accumulator[field.key] = matchedHeader
      }
      return accumulator
    }, {} as Partial<Record<ImportFieldKey, string>>)

    importHeaders.value = headers
    importedSheetName.value = `${fileName.endsWith('.xlsx') ? '首个工作表' : '文本表'} / 表头第 ${headerRowIndex + 1} 行`
    importedRows.value = buildImportedRows(records, headerRowIndex, matchedHeaders)
    importedPendingOrderRows.value = buildImportedPendingOrderRows(importedRows.value)
    importedOrderPoolActive.value = importedRows.value.length > 0

    if (importedRows.value.length === 0) {
      importErrorMessage.value = '已读取文件，但没有识别到可导入的订单行。'
    }
  } catch (error) {
    importHeaders.value = []
    importedRows.value = []
    importedPendingOrderRows.value = []
    importedOrderPoolActive.value = false
    importedSheetName.value = ''
    importErrorMessage.value = error instanceof Error ? error.message : '订单文件解析失败'
  } finally {
    input.value = ''
  }
}

const clearImportedOrderPreview = () => {
  importedFileName.value = ''
  importedSheetName.value = ''
  importHeaders.value = []
  importedRows.value = []
  importedPendingOrderRows.value = []
  importedOrderPoolActive.value = false
  importErrorMessage.value = ''
}

const openImportFilePicker = () => {
  importFileInput.value?.click()
}
</script>

<template>
  <div class="space-y-6">
    <template v-if="props.activeSection === 'monthly-plan'">
      <section class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <article
          v-for="metric in injectionOverviewMetrics"
          :key="metric.label"
          class="rounded-2xl border border-slate-200 bg-white p-5"
        >
          <p class="text-sm text-slate-500">{{ metric.label }}</p>
          <p class="mt-4 text-3xl font-semibold tracking-tight text-slate-950">{{ metric.value }}</p>
          <p class="mt-3 text-xs leading-5 text-slate-500">{{ metric.detail }}</p>
        </article>
      </section>

      <div class="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <SectionPanel
          title="班次概览"
          subtitle="先看本月计划里最常用的班次执行、结转和预警，不把所有信息一股脑堆在首页。"
        >
          <div class="grid gap-4 lg:grid-cols-2">
            <article
              v-for="shift in injectionShiftSummaries"
              :key="shift.shift"
              class="rounded-2xl border border-slate-200 bg-white p-5"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <p class="text-xs uppercase tracking-[0.22em] text-slate-500">{{ shift.date }}</p>
                  <h3 class="mt-2 text-lg font-semibold text-slate-950">{{ shift.shift }}</h3>
                </div>
                <StatusPill :label="`${shift.completion}%`" :tone="shift.completion >= 75 ? 'green' : 'amber'" />
              </div>
              <div class="mt-4">
                <ProgressMeter :value="shift.completion" :tone="shift.completion >= 75 ? 'green' : 'amber'" label="完成度" />
              </div>
              <div class="mt-4 grid gap-3 sm:grid-cols-2">
                <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">{{ shift.machineRunning }}</div>
                <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">{{ shift.carryOver }}</div>
              </div>
              <div class="mt-4 rounded-xl border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                {{ shift.alert }}
              </div>
            </article>
          </div>
        </SectionPanel>

        <SectionPanel
          title="重点动作"
          subtitle="首页只保留今天最值得处理的动作，不再塞满所有中后台内容。"
        >
          <div class="space-y-3">
            <article
              v-for="task in injectionExecutionTasks"
              :key="task.title"
              class="rounded-2xl border p-4"
              :class="panelTone[task.tone]"
            >
              <div class="flex items-start gap-3">
                <span class="flex size-10 shrink-0 items-center justify-center rounded-2xl bg-white text-slate-700">
                  <AlertTriangle class="size-4" aria-hidden="true" />
                </span>
                <div>
                  <h3 class="font-semibold text-slate-950">{{ task.title }}</h3>
                  <p class="mt-2 text-sm leading-6 text-slate-600">{{ task.meta }}</p>
                </div>
              </div>
            </article>
          </div>

          <div class="mt-4 rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-5 py-4">
            <div class="flex items-center gap-3">
              <Boxes class="size-5 text-slate-500" aria-hidden="true" />
              <p class="text-sm leading-6 text-slate-600">
                月计划页只做“看全局 + 找风险”，真正操作下沉到排机工作台。
              </p>
            </div>
          </div>
        </SectionPanel>
      </div>
    </template>

    <template v-else-if="isSchedulingWorkbench">
      <SectionPanel
        title="订单导入与待排池"
        subtitle="先把待排订单整理干净，再进入排机工作台生成草稿。"
      >
        <template #action>
          <div class="flex flex-wrap gap-2">
            <button
              type="button"
              class="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
              @click="manualOrderFormVisible = !manualOrderFormVisible"
            >
              <Plus class="size-4" aria-hidden="true" />
              手工补单
            </button>
            <button
              type="button"
              class="inline-flex items-center gap-2 rounded-lg bg-slate-950 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
              :disabled="compactPendingOrders.length === 0"
              @click="emit('change-section', 'smart-scheduling')"
            >
              进入排机工作台
              <SquareTerminal class="size-4" aria-hidden="true" />
            </button>
          </div>
        </template>

        <section class="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <article
            v-for="metric in pendingOrderPoolSummaryCards"
            :key="metric.label"
            class="rounded-2xl border p-4"
            :class="panelTone[metric.tone]"
          >
            <div class="flex items-center justify-between gap-3">
              <p class="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">{{ metric.label }}</p>
              <StatusPill :label="String(metric.value)" :tone="metric.tone" compact />
            </div>
            <p class="mt-3 text-sm leading-6 text-slate-600">{{ metric.detail }}</p>
          </article>
        </section>

        <div class="mt-5 grid gap-5">
          <article class="rounded-2xl border border-slate-200 bg-white p-5">
            <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div class="flex items-start gap-4">
                <span class="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-teal-50 text-teal-700">
                  <FileSpreadsheet class="size-5" aria-hidden="true" />
                </span>
                <div>
                  <p class="text-xs uppercase tracking-[0.2em] text-slate-500">Excel / CSV</p>
                  <h3 class="mt-2 text-lg font-semibold text-slate-950">
                    {{ importedFileName || '选择订单文件' }}
                  </h3>
                  <p class="mt-2 text-sm leading-6 text-slate-600">
                    {{ importedSheetName || '支持 .xlsx、.csv、.tsv，上传后会预览，并把可入池行带入当前订单池。' }}
                  </p>
                </div>
              </div>
              <div class="flex shrink-0 flex-wrap gap-2">
                <input
                  ref="importFileInput"
                  type="file"
                  accept=".xlsx,.csv,.tsv,.txt"
                  class="hidden"
                  @change="handleOrderImportFile"
                >
                <button
                  type="button"
                  class="inline-flex items-center gap-2 rounded-lg bg-slate-950 px-4 py-2 text-sm font-semibold text-white"
                  @click="openImportFilePicker"
                >
                  <UploadCloud class="size-4" aria-hidden="true" />
                  上传订单
                </button>
                <button
                  v-if="importedRows.length > 0 || importErrorMessage"
                  type="button"
                  class="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700"
                  @click="clearImportedOrderPreview"
                >
                  清空预览
                </button>
              </div>
            </div>

            <div
              v-if="importErrorMessage"
              class="mt-4 rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700"
            >
              {{ importErrorMessage }}
            </div>

            <div class="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <article
                v-for="metric in importSummaryCards"
                :key="metric.label"
                class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3"
              >
                <div class="flex items-center justify-between gap-2">
                  <p class="text-xs uppercase tracking-[0.18em] text-slate-500">{{ metric.label }}</p>
                  <StatusPill :label="String(metric.value)" :tone="metric.tone" compact />
                </div>
                <p class="mt-2 text-xl font-semibold text-slate-950">{{ metric.value }}</p>
                <p class="mt-1 text-xs leading-5 text-slate-500">{{ metric.detail }}</p>
              </article>
            </div>
          </article>

          <article
            v-if="manualOrderFormVisible"
            class="rounded-2xl border border-blue-100 bg-blue-50 p-5"
          >
            <div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <h3 class="font-semibold text-slate-950">手工补单</h3>
                <p class="mt-1 text-sm leading-6 text-slate-600">临时插单或漏导订单先补进当前待排池，后续再由后端保存。</p>
              </div>
              <StatusPill label="前端草稿" tone="blue" compact />
            </div>

            <div class="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
              <input v-model="manualOrderForm.orderNo" class="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-300" placeholder="订单号 *">
              <input v-model="manualOrderForm.productName" class="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-300" placeholder="产品名称 *">
              <input v-model="manualOrderForm.moldCode" class="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-300" placeholder="模具编号 *">
              <input v-model="manualOrderForm.quantity" class="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-300" placeholder="待排数量 *">
              <input v-model="manualOrderForm.dueDate" class="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-300" placeholder="交期">
              <input v-model="manualOrderForm.customer" class="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-300" placeholder="客户">
              <input v-model="manualOrderForm.color" class="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-300" placeholder="颜色">
              <input v-model="manualOrderForm.material" class="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-300" placeholder="料型">
              <input v-model="manualOrderForm.machineModel" class="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-300" placeholder="推荐机型">
              <input v-model="manualOrderForm.remark" class="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-300" placeholder="备注">
            </div>

            <div class="mt-4 flex flex-wrap justify-end gap-2">
              <button
                type="button"
                class="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700"
                @click="resetManualOrderForm"
              >
                清空
              </button>
              <button
                type="button"
                class="rounded-lg bg-slate-950 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
                :disabled="!manualOrderForm.orderNo || !manualOrderForm.productName || !manualOrderForm.moldCode || !manualOrderForm.quantity"
                @click="createManualPendingOrder"
              >
                加入待排池
              </button>
            </div>
          </article>

        </div>

        <div v-if="importedRows.length > 0" class="mt-6 grid gap-5 xl:grid-cols-[1.25fr_0.75fr]">
          <article class="rounded-2xl border border-slate-200 bg-white p-5">
            <div class="flex items-center justify-between gap-3">
              <h3 class="font-semibold text-slate-950">导入预览</h3>
              <StatusPill :label="`${importedRows.length} 行`" tone="teal" compact />
            </div>
            <div class="mt-4 max-h-[620px] overflow-auto pr-1">
              <table class="min-w-full text-left text-sm">
                <thead class="border-b border-slate-200 text-xs uppercase tracking-[0.18em] text-slate-500">
                  <tr>
                    <th class="pb-3 pr-4 font-medium">行号</th>
                    <th class="pb-3 pr-4 font-medium">订单</th>
                    <th class="pb-3 pr-4 font-medium">产品 / 模具</th>
                    <th class="pb-3 pr-4 font-medium">颜色 / 料型</th>
                    <th class="pb-3 pr-4 font-medium">F列推荐机型</th>
                    <th class="pb-3 pr-4 font-medium">备注</th>
                    <th class="pb-3 pr-4 font-medium">数量 / 交期</th>
                    <th class="pb-3 font-medium">状态</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="row in importPreviewRows"
                    :key="`preview-${row.rowNumber}-${row.orderNo}-${row.moldCode}`"
                    class="border-b border-slate-100 align-top last:border-b-0"
                  >
                    <td class="py-3 pr-4 text-slate-500">{{ row.rowNumber }}</td>
                    <td class="py-3 pr-4 font-semibold text-slate-950">{{ row.orderNo || '未填' }}</td>
                    <td class="py-3 pr-4 text-slate-600">
                      <div>{{ row.productName || '未填产品' }}</div>
                      <div class="mt-1 text-xs text-slate-500">{{ row.moldCode || '未填模具' }}</div>
                    </td>
                    <td class="py-3 pr-4 text-slate-600">
                      <div>{{ row.color || '未填颜色' }}</div>
                      <div class="mt-1 text-xs text-slate-500">{{ row.material || '未填料型' }}</div>
                    </td>
                    <td class="py-3 pr-4 text-slate-600">{{ row.machineModel || '待系统推荐' }}</td>
                    <td class="py-3 pr-4 text-slate-600">{{ row.remark || '无' }}</td>
                    <td class="py-3 pr-4 text-slate-600">
                      <div>{{ row.quantity || '未填数量' }}</div>
                      <div class="mt-1 text-xs text-slate-500">{{ row.dueDate || '未填交期' }}</div>
                    </td>
                    <td class="py-3">
                      <StatusPill :label="row.issue" :tone="row.tone" compact />
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </article>

          <article class="rounded-2xl border border-slate-200 bg-white p-5">
            <div class="flex items-center justify-between gap-3">
              <h3 class="font-semibold text-slate-950">错误行</h3>
              <StatusPill :label="`${importProblemRows.length} 行`" :tone="importProblemRows.length > 0 ? 'amber' : 'green'" compact />
            </div>
            <div class="mt-4 max-h-[620px] space-y-3 overflow-y-auto pr-1">
              <article
                v-for="row in importProblemRows"
                :key="`problem-${row.rowNumber}-${row.orderNo}-${row.moldCode}`"
                class="rounded-xl border p-4"
                :class="panelTone[row.tone]"
              >
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Row {{ row.rowNumber }}</p>
                    <h4 class="mt-1 font-semibold text-slate-950">{{ row.orderNo || '未识别订单' }}</h4>
                  </div>
                  <StatusPill :label="row.issue" :tone="row.tone" compact />
                </div>
                <p class="mt-3 text-sm leading-6 text-slate-700">
                  {{ [...row.errors, ...row.warnings].join('、') }}
                </p>
              </article>
              <div
                v-if="importProblemRows.length === 0"
                class="rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-700"
              >
                当前预览没有发现必填错误。
              </div>
            </div>
          </article>
        </div>
      </SectionPanel>

      <SectionPanel
        title="订单池"
        :subtitle="importedOrderPoolActive ? `当前使用上传订单池：${compactPendingOrders.length} 行可进入排机，错误行仍留在导入页。` : '这里保留工厂最常看的几列，避免一屏表头太宽、太难用。'"
      >
        <template #action>
          <StatusPill
            :label="importedOrderPoolActive ? `上传池 ${filteredPendingOrders.length}/${compactPendingOrders.length} 行` : `默认池 ${filteredPendingOrders.length}/${compactPendingOrders.length} 行`"
            :tone="importedOrderPoolActive ? 'teal' : 'blue'"
          />
        </template>

        <div class="mb-5 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div class="relative max-w-xl flex-1">
            <Search class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
            <input
              v-model="pendingOrderSearchText"
              type="search"
              class="w-full rounded-lg border border-slate-200 bg-white py-2 pl-10 pr-3 text-sm outline-none transition focus:border-teal-300 focus:ring-2 focus:ring-teal-100"
              placeholder="搜索单号、产品、模具、颜色、料型"
            >
          </div>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="filter in pendingOrderFilters"
              :key="filter.key"
              type="button"
              class="rounded-lg border px-3 py-2 text-sm font-semibold transition"
              :class="pendingOrderStatusFilter === filter.key
                ? 'border-slate-950 bg-slate-950 text-white'
                : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300'"
              @click="pendingOrderStatusFilter = filter.key"
            >
              {{ filter.label }}
            </button>
          </div>
        </div>

        <div class="overflow-x-auto">
          <table class="min-w-full text-left text-sm">
            <thead class="border-b border-slate-200 text-xs uppercase tracking-[0.2em] text-slate-500">
              <tr>
                <th class="pb-3 pr-4 font-medium">单号</th>
                <th class="pb-3 pr-4 font-medium">产品</th>
                <th class="pb-3 pr-4 font-medium">模具</th>
                <th class="pb-3 pr-4 font-medium">颜色 / 料型</th>
                <th class="pb-3 pr-4 font-medium">待排数量</th>
                <th class="pb-3 pr-4 font-medium">交期</th>
                <th class="pb-3 pr-4 font-medium">系统推荐</th>
                <th class="pb-3 font-medium">状态</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in filteredPendingOrders"
                :key="`pool-${getPendingOrderMachineKey(row)}`"
                class="border-b border-slate-100 align-top last:border-b-0"
              >
                <td class="py-4 pr-4 font-semibold text-slate-950">{{ row.orderNo }}</td>
                <td class="py-4 pr-4 text-slate-600">
                  <div>{{ row.customer }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ row.productName }}</div>
                </td>
                <td class="py-4 pr-4 text-slate-600">{{ row.moldCode }}</td>
                <td class="py-4 pr-4 text-slate-600">
                  <div>{{ row.color }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ row.material }}</div>
                </td>
                <td class="py-4 pr-4 text-slate-600">{{ row.quantity }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.dueDate }}</td>
                <td class="py-4 pr-4 text-slate-600">
                  <select
                    v-if="getPendingOrderMachineOptions(row).length > 0"
                    class="min-w-36 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-800 outline-none transition focus:border-teal-400 focus:ring-2 focus:ring-teal-100"
                    :value="getSelectedPendingOrderMachine(row)"
                    @change="handlePendingOrderMachineChange(row, $event)"
                  >
                    <option
                      v-for="machine in getPendingOrderMachineOptions(row)"
                      :key="`${row.orderNo}-${row.moldCode}-${machine}`"
                      :value="machine"
                    >
                      {{ machine }}
                    </option>
                  </select>
                  <div
                    v-else
                    class="inline-flex rounded-xl border border-amber-100 bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-700"
                  >
                    待补规则
                  </div>
                  <p class="mt-1 text-xs text-slate-500">
                    {{ selectedPendingOrderMachines[getPendingOrderMachineKey(row)] ? '人工已确认' : '系统推荐，可改选' }}
                  </p>
                </td>
                <td class="py-4">
                  <StatusPill :label="getPendingOrderStatusLabel(row)" :tone="getPendingOrderStatusTone(row)" compact />
                </td>
              </tr>
            </tbody>
          </table>

          <p
            v-if="filteredPendingOrders.length === 0"
            class="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-5 text-sm text-slate-600"
          >
            当前筛选下没有订单，调整搜索或状态筛选后再看。
          </p>
        </div>
      </SectionPanel>

    </template>

    <template v-else-if="props.activeSection === 'smart-scheduling'">
      <SectionPanel
        title="排机草稿与审核"
        subtitle="订单池确认后生成排机草稿，计划员可微调机台，主管审核通过后进入车间执行。"
      >
        <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <article
            v-for="metric in schedulingDraftMetrics"
            :key="metric.label"
            class="rounded-2xl border p-4"
            :class="panelTone[metric.tone]"
          >
            <p class="text-sm text-slate-500">{{ metric.label }}</p>
            <p class="mt-3 text-3xl font-semibold tracking-tight text-slate-950">{{ metric.value }}</p>
            <p class="mt-2 text-xs leading-5 text-slate-500">{{ metric.detail }}</p>
          </article>
        </div>

        <div class="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-5 py-4">
          <div>
            <h3 class="font-semibold text-slate-950">草稿状态</h3>
            <p class="mt-1 text-sm leading-6 text-slate-600">
              {{ schedulingDraftReleased ? '主管已通过，执行页可以承接车间任务。' : schedulingReviewRequested ? '草稿已提交主管审核，机台改动后会退回待提交。' : schedulingDraftGenerated ? '草稿已生成，可继续改机台后提交审核。' : '当前订单池可直接生成排机草稿。' }}
            </p>
          </div>
          <div class="flex flex-wrap gap-3">
            <button
              type="button"
              class="rounded-2xl px-5 py-3 text-sm font-semibold transition"
              :class="schedulingDraftGenerated ? 'bg-sky-100 text-sky-700' : 'bg-slate-950 text-white hover:bg-slate-800'"
              @click="generateSchedulingDraft"
            >
              {{ schedulingDraftGenerated ? '重新排机' : '生成排机草稿' }}
            </button>
            <button
              type="button"
              class="rounded-2xl px-5 py-3 text-sm font-semibold transition disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
              :class="schedulingReviewRequested ? 'bg-amber-100 text-amber-700' : 'bg-teal-600 text-white hover:bg-teal-700'"
              :disabled="!schedulingDraftGenerated || schedulingDraftReleased"
              @click="submitSchedulingReview"
            >
              {{ schedulingReviewRequested ? '已提交审核' : '提交主管审核' }}
            </button>
            <button
              type="button"
              class="rounded-2xl px-5 py-3 text-sm font-semibold transition disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
              :class="schedulingDraftReleased ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-950 text-white hover:bg-slate-800'"
              :disabled="!schedulingReviewRequested"
              @click="approveSchedulingDraft"
            >
              {{ schedulingDraftReleased ? '主管已通过' : '主管审核通过' }}
            </button>
          </div>
        </div>

        <div v-if="schedulingDraftGenerated" class="mt-5 overflow-x-auto">
          <table class="min-w-full text-left text-sm">
            <thead class="border-b border-slate-200 text-xs uppercase tracking-[0.2em] text-slate-500">
              <tr>
                <th class="pb-3 pr-4 font-medium">顺位</th>
                <th class="pb-3 pr-4 font-medium">单号 / 产品</th>
                <th class="pb-3 pr-4 font-medium">模具</th>
                <th class="pb-3 pr-4 font-medium">颜色 / 料型</th>
                <th class="pb-3 pr-4 font-medium">下发机台</th>
                <th class="pb-3 pr-4 font-medium">预计完成</th>
                <th class="pb-3 font-medium">状态</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in pendingOrderMachineDraftRows"
                :key="`schedule-draft-${getPendingOrderMachineKey(row)}-${row.selectedMachine}`"
                class="border-b border-slate-100 align-top last:border-b-0"
              >
                <td class="py-4 pr-4 font-semibold text-slate-950">{{ row.sequence }}</td>
                <td class="py-4 pr-4 text-slate-600">
                  <div class="font-semibold text-slate-950">{{ row.orderNo }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ row.productName }}</div>
                </td>
                <td class="py-4 pr-4 text-slate-600">{{ row.moldCode }}</td>
                <td class="py-4 pr-4 text-slate-600">
                  <div>{{ row.color }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ row.material }}</div>
                </td>
                <td class="py-4 pr-4">
                  <select
                    class="w-40 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-900 outline-none transition focus:border-teal-400 focus:ring-2 focus:ring-teal-100"
                    :value="row.selectedMachine"
                    aria-label="修改下发机台"
                    @change="handleDraftMachineChange(row, $event)"
                  >
                    <option
                      v-for="machine in row.machineOptions"
                      :key="`schedule-draft-machine-${getPendingOrderMachineKey(row)}-${machine}`"
                      :value="machine"
                    >
                      {{ machine }}
                    </option>
                  </select>
                  <div class="mt-1 text-xs leading-5 text-slate-500">{{ row.confirmState }}</div>
                </td>
                <td class="py-4 pr-4 text-slate-600">
                  <div class="font-semibold text-slate-950">{{ row.estimatedCompletionDate }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ row.estimatedStartWindow }}</div>
                </td>
                <td class="py-4">
                  <StatusPill :label="row.releaseState" :tone="row.releaseTone" compact />
                </td>
              </tr>
            </tbody>
          </table>

          <p
            v-if="pendingOrderMachineDraftRows.length === 0"
            class="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-5 text-sm text-slate-600"
          >
            当前订单池还没有可排机台，先补模具映射或机台规则。
          </p>
        </div>
        <p
          v-else
          class="mt-5 rounded-2xl border border-slate-200 bg-slate-50 p-5 text-sm text-slate-600"
        >
          生成草稿后，这里会显示可人工微调的排机明细。
        </p>
      </SectionPanel>

      <section class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <article
          v-for="metric in injectionExecutionRuleMetrics"
          :key="metric.label"
          class="rounded-2xl border border-slate-200 bg-white p-5"
        >
          <p class="text-sm text-slate-500">{{ metric.label }}</p>
          <p class="mt-4 text-3xl font-semibold tracking-tight text-slate-950">{{ metric.value }}</p>
          <p class="mt-3 text-xs leading-5 text-slate-500">{{ metric.detail }}</p>
        </article>
      </section>

      <div class="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <SectionPanel
          title="候选机台"
          subtitle="这里只放推荐结果和阻塞原因，计划员点击进来就知道下一步该怎么排。"
        >
          <div class="space-y-4">
            <article
              v-for="row in compactCandidateRows"
              :key="`${row.orderNo}-${row.moldCode}`"
              class="rounded-2xl border border-slate-200 bg-white p-5"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <p class="text-xs uppercase tracking-[0.2em] text-slate-500">{{ row.orderNo }}</p>
                  <h3 class="mt-2 text-lg font-semibold text-slate-950">{{ row.moldCode }}</h3>
                </div>
                <StatusPill :label="row.recommendedMachine" :tone="row.tone" compact />
              </div>
              <div class="mt-4 grid gap-3 md:grid-cols-2">
                <div class="rounded-xl bg-slate-50 px-4 py-3">
                  <p class="text-xs uppercase tracking-[0.2em] text-slate-500">备选机台</p>
                  <p class="mt-2 text-sm text-slate-900">{{ row.backupMachine }}</p>
                </div>
                <div class="rounded-xl bg-slate-50 px-4 py-3">
                  <p class="text-xs uppercase tracking-[0.2em] text-slate-500">当前阻塞</p>
                  <p class="mt-2 text-sm leading-6 text-slate-700">{{ row.blocker }}</p>
                </div>
              </div>
              <p class="mt-4 text-sm leading-6 text-slate-600">{{ row.reason }}</p>
            </article>
          </div>
        </SectionPanel>

        <SectionPanel
          title="设备拦截规则"
          subtitle="把工艺限制单独列出来，避免现场同事来回切页找原因。"
        >
          <div class="space-y-3">
            <article
              v-for="item in injectionExecutionConstraintRows"
              :key="item.machine"
              class="rounded-2xl border p-4"
              :class="panelTone[item.tone]"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <h3 class="font-semibold text-slate-950">{{ item.machine }}</h3>
                  <p class="mt-1 text-xs text-slate-500">{{ item.workshop }} · {{ item.tonnage }} · {{ item.robot }}</p>
                </div>
                <StatusPill :label="item.tone === 'red' ? '硬拦截' : item.tone === 'amber' ? '需确认' : '可候选'" :tone="item.tone" compact />
              </div>
              <p class="mt-3 text-sm leading-6 text-slate-700">{{ item.limit }}</p>
              <p class="mt-2 text-xs leading-5 text-slate-500">{{ item.action }}</p>
            </article>
          </div>
        </SectionPanel>
      </div>

      <SectionPanel
        title="规则流程"
        subtitle="智能排机页只保留排机逻辑主链，让页面更像操作台，而不是汇报页。"
      >
        <div class="grid gap-4 xl:grid-cols-5">
          <article
            v-for="stage in injectionWorkflowStages"
            :key="stage.title"
            class="rounded-2xl border border-slate-200 bg-white p-4"
          >
            <div class="flex items-center justify-between gap-3">
              <h3 class="font-semibold text-slate-950">{{ stage.title }}</h3>
              <StatusPill
                :label="stage.state === 'done' ? '已完成' : stage.state === 'active' ? '进行中' : '待进入'"
                :tone="workflowTone[stage.state]"
                compact
              />
            </div>
            <p class="mt-3 text-xs text-slate-500">{{ stage.owner }}</p>
            <p class="mt-3 text-sm leading-6 text-slate-600">{{ stage.detail }}</p>
          </article>
        </div>
      </SectionPanel>
    </template>

    <template v-else-if="props.activeSection === 'scheduling-results'">
      <SectionPanel
        title="执行下发确认"
        subtitle="承接主管审核后的排机草稿，按机台确认现场任务和开机窗口。"
      >
        <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <article
            v-for="metric in schedulingDraftMetrics"
            :key="metric.label"
            class="rounded-2xl border p-4"
            :class="panelTone[metric.tone]"
          >
            <p class="text-sm text-slate-500">{{ metric.label }}</p>
            <p class="mt-3 text-3xl font-semibold tracking-tight text-slate-950">{{ metric.value }}</p>
            <p class="mt-2 text-xs leading-5 text-slate-500">{{ metric.detail }}</p>
          </article>
        </div>

        <div class="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-5 py-4">
          <div>
            <h3 class="font-semibold text-slate-950">下发状态</h3>
            <p class="mt-1 text-sm leading-6 text-slate-600">
              {{ schedulingDraftReleased ? '排机单已进入执行，日报页可以承接班次回报。' : schedulingReviewRequested ? '排机草稿已提交主管审核，通过后下发到车间。' : schedulingDraftGenerated ? '排机草稿尚未提交审核，先回排机工作台确认。' : '当前还没有可下发的排机草稿。' }}
            </p>
          </div>
          <div class="flex flex-wrap gap-3">
            <button
              type="button"
              class="rounded-2xl px-5 py-3 text-sm font-semibold transition disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
              :class="schedulingDraftReleased ? 'bg-emerald-100 text-emerald-700' : 'bg-teal-600 text-white hover:bg-teal-700'"
              :disabled="!schedulingReviewRequested || schedulingDraftReleased"
              @click="approveSchedulingDraft"
            >
              {{ schedulingDraftReleased ? '已下发执行' : '主管审核通过' }}
            </button>
          </div>
        </div>

        <div class="mt-5 overflow-x-auto">
          <table class="min-w-full text-left text-sm">
            <thead class="border-b border-slate-200 text-xs uppercase tracking-[0.2em] text-slate-500">
              <tr>
                <th class="pb-3 pr-4 font-medium">顺位</th>
                <th class="pb-3 pr-4 font-medium">单号 / 产品</th>
                <th class="pb-3 pr-4 font-medium">模具</th>
                <th class="pb-3 pr-4 font-medium">颜色 / 料型</th>
                <th class="pb-3 pr-4 font-medium">数量 / 交期</th>
                <th class="pb-3 pr-4 font-medium">排机参考</th>
                <th class="pb-3 pr-4 font-medium">下发机台</th>
                <th class="pb-3 pr-4 font-medium">选机状态</th>
                <th class="pb-3 font-medium">下发状态</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in pendingOrderMachineDraftRows"
                :key="`draft-${getPendingOrderMachineKey(row)}-${row.selectedMachine}`"
                class="border-b border-slate-100 align-top last:border-b-0"
              >
                <td class="py-4 pr-4 font-semibold text-slate-950">{{ row.sequence }}</td>
                <td class="py-4 pr-4 text-slate-600">
                  <div class="font-semibold text-slate-950">{{ row.orderNo }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ row.productName }}</div>
                </td>
                <td class="py-4 pr-4 text-slate-600">{{ row.moldCode }}</td>
                <td class="py-4 pr-4 text-slate-600">
                  <div>{{ row.color }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ row.material }}</div>
                </td>
                <td class="py-4 pr-4 text-slate-600">
                  <div>{{ row.quantity }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ row.dueDate }}</div>
                </td>
                <td class="py-4 pr-4 text-slate-600">
                  <div class="min-w-[18rem] rounded-2xl border border-slate-100 bg-slate-50/80 p-3">
                    <div class="grid gap-2 sm:grid-cols-2">
                      <div>
                        <p class="text-[11px] uppercase tracking-[0.16em] text-slate-400">推荐机型</p>
                        <p class="mt-1 font-semibold text-slate-900">{{ getDraftRequiredMachineModel(row) }}</p>
                      </div>
                      <div>
                        <p class="text-[11px] uppercase tracking-[0.16em] text-slate-400">模具尺寸</p>
                        <p class="mt-1 font-semibold text-amber-700">{{ getDraftMoldSize(row) }}</p>
                      </div>
                    </div>
                    <div class="mt-3 border-t border-slate-200 pt-3">
                      <p class="text-[11px] uppercase tracking-[0.16em] text-slate-400">选中机台参数</p>
                      <p class="mt-1 font-semibold text-slate-900">{{ getDraftSelectedMachineType(row) }}</p>
                      <p class="mt-1 text-xs leading-5 text-slate-500">{{ getDraftSelectedMachineHardware(row) }}</p>
                    </div>
                    <div class="mt-3 flex flex-wrap gap-2">
                      <StatusPill :label="getDraftSprayLabel(row)" :tone="getDraftSprayTone(row)" compact />
                      <StatusPill :label="getDraftArmRequirement(row)" :tone="row.armType ? 'blue' : 'slate'" compact />
                    </div>
                    <p class="mt-2 text-xs leading-5 text-slate-500">
                      {{ getDraftMoldReference(row) }} · {{ getDraftProcessRemark(row) }}
                    </p>
                  </div>
                </td>
                <td class="py-4 pr-4">
                  <select
                    class="w-40 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-900 outline-none transition focus:border-teal-400 focus:ring-2 focus:ring-teal-100"
                    :value="row.selectedMachine"
                    aria-label="修改下发机台"
                    @change="handleDraftMachineChange(row, $event)"
                  >
                    <option
                      v-for="machine in row.machineOptions"
                      :key="`draft-machine-${getPendingOrderMachineKey(row)}-${machine}`"
                      :value="machine"
                    >
                      {{ machine }}
                    </option>
                  </select>
                  <div class="mt-1 text-xs leading-5 text-slate-500">人工改动后重新确认下发</div>
                </td>
                <td class="py-4 pr-4">
                  <StatusPill :label="row.confirmState" :tone="row.confirmTone" compact />
                </td>
                <td class="py-4">
                  <StatusPill :label="row.releaseState" :tone="row.releaseTone" compact />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </SectionPanel>

      <SectionPanel
        title="下发执行任务单"
        subtitle="这张表给现场班组看：下发后每台机要做什么、谁接、后面回报什么。"
      >
        <div class="mb-5 rounded-2xl border px-5 py-4"
          :class="schedulingDraftReleased ? 'border-emerald-100 bg-emerald-50' : 'border-slate-200 bg-slate-50'"
        >
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 class="font-semibold text-slate-950">
                {{ schedulingDraftReleased ? '已下发到车间执行' : '等待确认下发' }}
              </h3>
              <p class="mt-1 text-sm leading-6 text-slate-600">
                {{ schedulingDraftReleased ? '班组可以按机台执行，后续回报会进入日报表和入库回写。' : '先生成草稿并确认下发，任务单才会进入执行状态。' }}
              </p>
            </div>
            <StatusPill
              :label="schedulingDraftReleased ? '执行中' : schedulingDraftGenerated ? '草稿待下发' : '未生成草稿'"
              :tone="schedulingDraftReleased ? 'green' : schedulingDraftGenerated ? 'blue' : 'slate'"
            />
          </div>
        </div>

        <div class="grid gap-4 xl:grid-cols-3">
          <article
            v-for="row in releasedExecutionRows"
            :key="`release-${row.sequence}-${row.orderNo}-${row.moldCode}`"
            class="rounded-2xl border border-slate-200 bg-white p-5"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <p class="text-xs uppercase tracking-[0.2em] text-slate-500">任务 {{ row.sequence }}</p>
                <h3 class="mt-2 text-lg font-semibold text-slate-950">{{ row.selectedMachine }}</h3>
                <p class="mt-1 text-xs text-slate-500">{{ row.workshop }}</p>
              </div>
              <StatusPill :label="row.stateLabel" :tone="row.stateTone" compact />
            </div>

            <div class="mt-4 space-y-3 text-sm text-slate-700">
              <div class="rounded-xl bg-slate-50 px-4 py-3">
                <p class="text-xs uppercase tracking-[0.18em] text-slate-500">订单 / 模具</p>
                <p class="mt-2 font-semibold text-slate-950">{{ row.orderNo }} · {{ row.moldCode }}</p>
                <p class="mt-1 text-xs text-slate-500">{{ row.productName }}</p>
              </div>
              <div class="rounded-xl bg-slate-50 px-4 py-3">
                <p class="text-xs uppercase tracking-[0.18em] text-slate-500">颜色 / 料型 / 数量</p>
                <p class="mt-2 font-semibold text-slate-950">{{ row.color }} · {{ row.material }}</p>
                <p class="mt-1 text-xs text-slate-500">待排 {{ row.quantity }}</p>
              </div>
              <div class="rounded-xl border border-dashed border-slate-300 bg-slate-50 px-4 py-3">
                <p class="text-xs uppercase tracking-[0.18em] text-slate-500">班组动作</p>
                <p class="mt-2 font-semibold text-slate-950">{{ row.action }}</p>
                <p class="mt-1 text-xs text-slate-500">回报状态：{{ row.feedbackState }}</p>
              </div>
            </div>
          </article>
        </div>
      </SectionPanel>

      <SectionPanel
        title="排机结果"
        subtitle="把排机结果和开机窗口放在一页，现场更容易直接往下执行。"
      >
        <div class="grid gap-4 xl:grid-cols-3">
          <article
            v-for="row in compactScheduleRows"
            :key="`${row.orderNo}-${row.machine}`"
            class="rounded-2xl border border-slate-200 bg-white p-5"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <p class="text-xs uppercase tracking-[0.2em] text-slate-500">{{ row.orderNo }}</p>
                <h3 class="mt-2 text-lg font-semibold text-slate-950">{{ row.machine }}</h3>
              </div>
              <StatusPill :label="row.shiftPlan" :tone="row.tone" compact />
            </div>
            <div class="mt-4 space-y-3">
              <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">建议开机：{{ row.startWindow }}</div>
              <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">预计完工：{{ row.endWindow }}</div>
              <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">产出预估：{{ row.expectedOutput }}</div>
            </div>
            <p class="mt-4 text-sm leading-6 text-slate-600">{{ row.dependency }}</p>
          </article>
        </div>
      </SectionPanel>

      <div class="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <SectionPanel
          title="机台负载"
          subtitle="结果页只看当前排机结果占用了哪些机台，不再混太多策略说明。"
        >
          <div class="grid gap-4 md:grid-cols-2">
            <article
              v-for="machine in injectionMachineLoad"
              :key="machine.machine"
              class="rounded-2xl border border-slate-200 bg-white p-4"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <h3 class="font-semibold text-slate-950">{{ machine.machine }}</h3>
                  <p class="mt-1 text-xs text-slate-500">{{ machine.mold }}</p>
                </div>
                <StatusPill :label="machine.queueDepth" :tone="machine.tone" compact />
              </div>
              <div class="mt-4">
                <ProgressMeter :value="machine.utilization" :tone="machine.tone" label="机台负载" />
              </div>
              <p class="mt-4 text-sm text-slate-600">{{ machine.material }}</p>
            </article>
          </div>
        </SectionPanel>

        <SectionPanel
          title="颜色切换"
          subtitle="只保留换色顺序风险，方便快速确认是否需要改机或调顺序。"
        >
          <div class="space-y-3">
            <article
              v-for="risk in injectionColorTransitionRisks"
              :key="risk.machine"
              class="rounded-2xl border border-slate-200 bg-white px-5 py-4"
            >
              <div class="flex items-center justify-between gap-3">
                <div>
                  <h3 class="font-semibold text-slate-950">{{ risk.machine }}</h3>
                  <p class="mt-1 text-xs text-slate-500">{{ risk.route.join(' → ') }}</p>
                </div>
                <StatusPill :label="risk.risk" :tone="risk.tone" compact />
              </div>
            </article>
          </div>
        </SectionPanel>
      </div>
    </template>

    <template v-else-if="props.activeSection === 'daily-report'">
      <SectionPanel
        title="待回报任务"
        subtitle="承接主管已审核下发的排机任务，记录本班产量并预览欠数刷新。"
      >
        <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <article
            v-for="metric in shiftReportDraftMetrics"
            :key="metric.label"
            class="rounded-2xl border p-4"
            :class="panelTone[metric.tone]"
          >
            <p class="text-sm text-slate-500">{{ metric.label }}</p>
            <p class="mt-3 text-3xl font-semibold tracking-tight text-slate-950">{{ metric.value }}</p>
            <p class="mt-2 text-xs leading-5 text-slate-500">{{ metric.detail }}</p>
          </article>
        </div>

        <div class="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-5 py-4">
          <div>
            <h3 class="font-semibold text-slate-950">提交班次回报</h3>
            <p class="mt-1 text-sm leading-6 text-slate-600">
              回报提交后会进入日报记录，并为后续入库单和订单池回写提供依据。
            </p>
          </div>
          <button
            type="button"
            class="rounded-2xl px-5 py-3 text-sm font-semibold transition disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
            :class="shiftReportDraftSubmitted ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-950 text-white hover:bg-slate-800'"
            :disabled="!schedulingDraftReleased"
            @click="submitShiftReportDraft"
          >
            {{ shiftReportDraftSubmitted ? '回报已提交' : '提交班次回报' }}
          </button>
        </div>

        <div class="mt-5 overflow-x-auto">
          <table class="min-w-full text-left text-sm">
            <thead class="border-b border-slate-200 text-xs uppercase tracking-[0.2em] text-slate-500">
              <tr>
                <th class="pb-3 pr-4 font-medium">机台</th>
                <th class="pb-3 pr-4 font-medium">单号 / 模具</th>
                <th class="pb-3 pr-4 font-medium">产品</th>
                <th class="pb-3 pr-4 font-medium">待排数量</th>
                <th class="pb-3 pr-4 font-medium">本班回报</th>
                <th class="pb-3 pr-4 font-medium">刷新后欠数</th>
                <th class="pb-3 pr-4 font-medium">达成率</th>
                <th class="pb-3 font-medium">状态</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in shiftReportDraftRows"
                :key="`report-draft-${row.sequence}-${row.orderNo}-${row.moldCode}`"
                class="border-b border-slate-100 align-top last:border-b-0"
              >
                <td class="py-4 pr-4 font-semibold text-slate-950">{{ row.selectedMachine }}</td>
                <td class="py-4 pr-4 text-slate-600">
                  <div>{{ row.orderNo }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ row.moldCode }}</div>
                </td>
                <td class="py-4 pr-4 text-slate-600">{{ row.productName }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.quantity }}</td>
                <td class="py-4 pr-4 font-semibold text-slate-950">{{ row.reportedQuantity }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.shortageAfter }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.achievement }}</td>
                <td class="py-4">
                  <StatusPill :label="row.stateLabel" :tone="row.stateTone" compact />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </SectionPanel>

      <SectionPanel
        title="班次交接"
        subtitle="记录未完成数量、续啤、换模、停机和下一班注意事项。"
      >
        <div class="grid gap-4 xl:grid-cols-2">
          <article
            v-for="row in injectionShiftHandoverRows"
            :key="`${row.shift}-${row.machine}-${row.orderNo}`"
            class="rounded-2xl border border-slate-200 bg-white p-4"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="flex items-center gap-3">
                <span class="flex size-10 items-center justify-center rounded-2xl bg-slate-100 text-slate-700">
                  <RefreshCcw class="size-4" aria-hidden="true" />
                </span>
                <div>
                  <h3 class="font-semibold text-slate-950">{{ row.shift }}</h3>
                  <p class="mt-1 text-xs text-slate-500">{{ row.machine }} · {{ row.orderNo }}</p>
                </div>
              </div>
              <StatusPill :label="row.carryOverQty" :tone="row.tone" compact />
            </div>
            <p class="mt-3 text-sm leading-6 text-slate-600">{{ row.note }}</p>
          </article>
        </div>
      </SectionPanel>

      <SectionPanel
        title="日报记录"
        subtitle="保留已回报的班次明细，后续入库单和订单池回写都从这里承接。"
      >
        <div class="overflow-x-auto">
          <table class="min-w-full text-left text-sm">
            <thead class="border-b border-slate-200 text-xs uppercase tracking-[0.2em] text-slate-500">
              <tr>
                <th class="pb-3 pr-4 font-medium">机台</th>
                <th class="pb-3 pr-4 font-medium">操作员</th>
                <th class="pb-3 pr-4 font-medium">11H 目标</th>
                <th class="pb-3 pr-4 font-medium">实际</th>
                <th class="pb-3 pr-4 font-medium">差异</th>
                <th class="pb-3 font-medium">停机</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in injectionShiftReportRows"
                :key="`${row.machine}-${row.worker}`"
                class="border-b border-slate-100 last:border-b-0"
              >
                <td class="py-4 pr-4 font-semibold text-slate-950">{{ row.machine }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.worker }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.target11h }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.actual }}</td>
                <td class="py-4 pr-4">
                  <StatusPill :label="row.variance" :tone="row.tone" compact />
                </td>
                <td class="py-4 text-slate-600">{{ row.downtime }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </SectionPanel>

    </template>

    <template v-else-if="props.activeSection === 'inbound-orders'">
      <SectionPanel
        title="待入库确认"
        subtitle="承接日报页已提交的班次回报，确认本次要入库的数量和关联订单。"
      >
        <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <article
            v-for="metric in inboundWritebackDraftMetrics"
            :key="metric.label"
            class="rounded-2xl border p-4"
            :class="panelTone[metric.tone]"
          >
            <p class="text-sm text-slate-500">{{ metric.label }}</p>
            <p class="mt-3 text-3xl font-semibold tracking-tight text-slate-950">{{ metric.value }}</p>
            <p class="mt-2 text-xs leading-5 text-slate-500">{{ metric.detail }}</p>
          </article>
        </div>

        <div class="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-5 py-4">
          <div>
            <h3 class="font-semibold text-slate-950">确认入库</h3>
            <p class="mt-1 text-sm leading-6 text-slate-600">
              日报提交后生成待入库记录，确认后进入入库单记录，并刷新后续回写结果。
            </p>
          </div>
          <button
            type="button"
            class="rounded-2xl px-5 py-3 text-sm font-semibold transition disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
            :class="inboundWritebackDraftConfirmed ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-950 text-white hover:bg-slate-800'"
            :disabled="!shiftReportDraftSubmitted"
            @click="confirmInboundWritebackDraft"
          >
            {{ inboundWritebackDraftConfirmed ? '已确认入库' : '确认入库' }}
          </button>
        </div>

        <div class="mt-5 overflow-x-auto">
          <table class="min-w-full text-left text-sm">
            <thead class="border-b border-slate-200 text-xs uppercase tracking-[0.2em] text-slate-500">
              <tr>
                <th class="pb-3 pr-4 font-medium">入库单</th>
                <th class="pb-3 pr-4 font-medium">单号 / 模具</th>
                <th class="pb-3 pr-4 font-medium">机台</th>
                <th class="pb-3 pr-4 font-medium">入库数量</th>
                <th class="pb-3 pr-4 font-medium">刷新后欠数</th>
                <th class="pb-3 pr-4 font-medium">仓库</th>
                <th class="pb-3 pr-4 font-medium">ERP</th>
                <th class="pb-3 pr-4 font-medium">排产池</th>
                <th class="pb-3 font-medium">状态</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in inboundWritebackDraftRows"
                :key="`inbound-draft-${row.deliveryCode}-${row.orderNo}-${row.moldCode}`"
                class="border-b border-slate-100 align-top last:border-b-0"
              >
                <td class="py-4 pr-4 font-semibold text-slate-950">{{ row.deliveryCode }}</td>
                <td class="py-4 pr-4 text-slate-600">
                  <div>{{ row.orderNo }}</div>
                  <div class="mt-1 text-xs text-slate-500">{{ row.moldCode }}</div>
                </td>
                <td class="py-4 pr-4 text-slate-600">{{ row.selectedMachine }}</td>
                <td class="py-4 pr-4 font-semibold text-slate-950">{{ row.inboundQty }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.shortageAfter }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.warehouseStatus }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.erpStatus }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.schedulerStatus }}</td>
                <td class="py-4">
                  <StatusPill :label="row.stateLabel" :tone="row.stateTone" compact />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </SectionPanel>

      <SectionPanel
        title="入库单记录"
        subtitle="跟踪送货单、订单数量、用料、PMC 和当前入库状态。"
      >
        <div class="overflow-x-auto">
          <table class="min-w-full text-left text-sm">
            <thead class="border-b border-slate-200 text-xs uppercase tracking-[0.2em] text-slate-500">
              <tr>
                <th class="pb-3 pr-4 font-medium">送货单</th>
                <th class="pb-3 pr-4 font-medium">单号</th>
                <th class="pb-3 pr-4 font-medium">啤数</th>
                <th class="pb-3 pr-4 font-medium">用料 KG</th>
                <th class="pb-3 pr-4 font-medium">PMC</th>
                <th class="pb-3 font-medium">状态</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in injectionWarehouseInboundRows"
                :key="row.deliveryCode"
                class="border-b border-slate-100 last:border-b-0"
              >
                <td class="py-4 pr-4 font-semibold text-slate-950">{{ row.deliveryCode }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.orderNo }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.shots }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.materialKg }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.pmc }}</td>
                <td class="py-4">
                  <StatusPill :label="row.status" :tone="row.tone" compact />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </SectionPanel>

      <SectionPanel
        title="回写结果"
        subtitle="确认入库后，查看仓库、ERP 和订单池欠数刷新是否完成。"
      >
        <div class="grid gap-4 xl:grid-cols-2">
          <article
            v-for="row in injectionInboundWritebackRows"
            :key="`${row.deliveryCode}-${row.orderNo}`"
            class="rounded-2xl border border-slate-200 bg-white p-5"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <h3 class="font-semibold text-slate-950">{{ row.deliveryCode }} · {{ row.orderNo }}</h3>
                <p class="mt-1 text-xs text-slate-500">{{ row.owner }}</p>
              </div>
              <StatusPill :label="row.schedulerStatus" :tone="row.tone" compact />
            </div>
            <div class="mt-4 grid gap-3 sm:grid-cols-2">
              <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">入库数量：{{ row.inboundQty }}</div>
              <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">回写后欠数：{{ row.shortageAfter }}</div>
            </div>
            <div class="mt-4 flex flex-wrap gap-2">
              <span class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">仓库：{{ row.warehouseStatus }}</span>
              <span class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">ERP：{{ row.erpStatus }}</span>
              <span class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">排产池：{{ row.schedulerStatus }}</span>
            </div>
          </article>
        </div>
      </SectionPanel>

    </template>

    <template v-else>
      <div class="grid gap-6">
        <SectionPanel
          title="机台档案"
          subtitle="基础资料页只保留具体机台台账、工艺范围和当前状态。"
        >
          <div class="overflow-x-auto">
            <table class="min-w-full text-left text-sm">
              <thead class="border-b border-slate-200 text-xs uppercase tracking-[0.2em] text-slate-500">
                <tr>
                  <th class="pb-3 pr-4 font-medium">机台</th>
                  <th class="pb-3 pr-4 font-medium">吨位 / 螺杆</th>
                  <th class="pb-3 pr-4 font-medium">机械手 / 车间</th>
                  <th class="pb-3 pr-4 font-medium">工艺范围</th>
                  <th class="pb-3 pr-4 font-medium">颜色策略</th>
                  <th class="pb-3 pr-4 font-medium">保养</th>
                  <th class="pb-3 font-medium">状态</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="machine in compactMachineRows"
                  :key="machine.machine"
                  class="border-b border-slate-100 last:border-b-0"
                >
                  <td class="py-4 pr-4 font-semibold text-slate-950">{{ machine.machine }}</td>
                  <td class="py-4 pr-4 text-slate-600">
                    <div>{{ machine.tonnage }}</div>
                    <div class="mt-1 text-xs text-slate-500">{{ machine.screw }}</div>
                  </td>
                  <td class="py-4 pr-4 text-slate-600">
                    <div>{{ machine.robot }}</div>
                    <div class="mt-1 text-xs text-slate-500">{{ machine.workshop }}</div>
                  </td>
                  <td class="py-4 pr-4 text-slate-600">{{ machine.processRange }}</td>
                  <td class="py-4 pr-4 text-slate-600">{{ machine.colorPolicy }}</td>
                  <td class="py-4 pr-4 text-slate-600">{{ machine.maintenance }}</td>
                  <td class="py-4">
                    <StatusPill :label="machine.status" :tone="machine.tone" compact />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </SectionPanel>

      </div>
    </template>
  </div>
</template>
