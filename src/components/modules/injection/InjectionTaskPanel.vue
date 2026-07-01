<script setup lang="ts">
import {
  AlertTriangle,
  Boxes,
  CheckCircle2,
  ClipboardList,
  Database,
  Factory,
  FileSpreadsheet,
  FileText,
  Layers3,
  Package,
  RefreshCcw,
  ShieldAlert,
  SquareTerminal,
  UploadCloud,
  Waypoints,
} from '@lucide/vue'
import { strFromU8, unzipSync } from 'fflate'
import { computed, ref } from 'vue'
import ProgressMeter from '@/components/common/ProgressMeter.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import type { InjectionSectionId } from '@/data/injectionSchedulingMock'
import { useInjectionModuleData } from '@/factories/injection/useInjectionModuleData'

const props = defineProps<{
  activeSection: InjectionSectionId
}>()

const {
  injectionColorTransitionRisks,
  injectionConfigRuleCards,
  injectionDataCenterDatasets,
  injectionDataSourceStatus,
  injectionExecutionCandidateRows,
  injectionExecutionConstraintRows,
  injectionExecutionRuleMetrics,
  injectionExecutionScheduleRows,
  injectionExecutionTasks,
  injectionInboundWritebackRows,
  injectionMachineLoad,
  injectionMachineMasterRows,
  injectionMachineProfileRows,
  injectionMoldMachineMappingRows,
  injectionMoldTargetDetailRows,
  injectionMoldTargetRows,
  injectionOrderImportTasks,
  injectionOverviewMetrics,
  injectionPendingOrderDetailRows,
  injectionPendingOrderFieldGroups,
  injectionPendingOrderValidationRules,
  injectionReportingMetrics,
  injectionShiftHandoverRows,
  injectionShiftReportImportMappingRows,
  injectionShiftReportChecklistItems,
  injectionShiftReportRows,
  injectionShiftReportTemplateGroups,
  injectionShiftSummaries,
  injectionWarehouseInboundRows,
  injectionWritebackRuleCards,
  injectionWritebackKeyMatchRows,
  injectionWorkflowStages,
} = useInjectionModuleData()

const compactPendingOrders = computed(() => injectionPendingOrderDetailRows.value.slice(0, 18))
const compactCandidateRows = computed(() => injectionExecutionCandidateRows.value.slice(0, 8))
const compactScheduleRows = computed(() => injectionExecutionScheduleRows.value.slice(0, 8))
const compactMachineRows = computed(() => injectionMachineMasterRows.value.slice(0, 18))
const compactMachineProfiles = computed(() => injectionMachineProfileRows.value.slice(0, 8))
const compactMoldRows = computed(() => injectionMoldTargetDetailRows.value.slice(0, 16))
const compactMappingRows = computed(() => injectionMoldMachineMappingRows.value.slice(0, 10))

const panelTone = {
  green: 'bg-emerald-50 border-emerald-100',
  blue: 'bg-blue-50 border-blue-100',
  amber: 'bg-amber-50 border-amber-100',
  red: 'bg-red-50 border-red-100',
  teal: 'bg-teal-50 border-teal-100',
  slate: 'bg-slate-100 border-slate-200',
} as const

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
  issue: string
  tone: ImportTone
  errors: string[]
  warnings: string[]
}

interface PendingOrderMachineRow {
  orderNo: string
  moldCode: string
  machineAdvice: string
  issue: string
  tone: ImportTone
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
]

const importFileInput = ref<HTMLInputElement | null>(null)
const importedFileName = ref('')
const importedSheetName = ref('')
const importHeaders = ref<string[]>([])
const importedRows = ref<ImportedOrderPreviewRow[]>([])
const importErrorMessage = ref('')
const selectedPendingOrderMachines = ref<Record<string, string>>({})

const importPreviewRows = computed(() => importedRows.value.slice(0, 8))
const importProblemRows = computed(() =>
  importedRows.value.filter((row) => row.errors.length > 0 || row.warnings.length > 0).slice(0, 10),
)

const importSummaryCards = computed(() => {
  const total = importedRows.value.length
  const passed = importedRows.value.filter((row) => row.errors.length === 0 && row.warnings.length === 0).length
  const warnings = importedRows.value.filter((row) => row.errors.length === 0 && row.warnings.length > 0).length
  const errors = importedRows.value.filter((row) => row.errors.length > 0).length

  return [
    { label: '预览行数', value: total, detail: importedSheetName.value || '等待上传', tone: total > 0 ? 'teal' : 'slate' },
    { label: '可导入', value: passed, detail: '字段完整且无重复风险', tone: 'green' },
    { label: '待确认', value: warnings, detail: '可进入订单池前需人工看一眼', tone: warnings > 0 ? 'amber' : 'slate' },
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

const importFieldMatchRows = computed(() =>
  expectedImportFields.map((field) => {
    const matchedHeader = findMatchedHeader(importHeaders.value, field)
    const tone: ImportTone = matchedHeader ? 'green' : field.required ? 'red' : 'amber'

    return {
      ...field,
      matchedHeader: matchedHeader || '未匹配',
      status: matchedHeader ? '已匹配' : field.required ? '缺字段' : '可后补',
      tone,
    }
  }),
)

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

const buildImportedRows = (
  records: Record<string, unknown>[],
  headerRowIndex: number,
  matchedHeaders: Partial<Record<ImportFieldKey, string>>,
) => {
  const baseRows = records
    .map((record, index) => {
      const row = expectedImportFields.reduce((accumulator, field) => {
        const value = readRecordValue(record, field, matchedHeaders)
        accumulator[field.key] = field.key === 'dueDate' ? normalizeExcelDate(value) : value
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

    if (importedRows.value.length === 0) {
      importErrorMessage.value = '已读取文件，但没有识别到可导入的订单行。'
    }
  } catch (error) {
    importHeaders.value = []
    importedRows.value = []
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
  importErrorMessage.value = ''
}

const openImportFilePicker = () => {
  importFileInput.value?.click()
}

const getPendingOrderMachineKey = (row: Pick<PendingOrderMachineRow, 'orderNo' | 'moldCode'>) =>
  `${row.orderNo}::${row.moldCode}`

const splitMachineOptions = (value = '') =>
  value
    .split('/')
    .map((item) => item.trim())
    .filter((item) =>
      item
      && !['待确认', '待系统推荐', '待补备选机台', '待补机台映射'].includes(item)
      && !item.includes('待补'),
    )

const getPendingOrderMachineOptions = (row: PendingOrderMachineRow) => {
  const mapping = injectionMoldMachineMappingRows.value.find((item) => item.moldCode === row.moldCode)
  const options = [
    selectedPendingOrderMachines.value[getPendingOrderMachineKey(row)],
    row.machineAdvice,
    mapping?.recommendedMachine,
    mapping?.backupMachine,
  ].flatMap((item) => splitMachineOptions(item))

  return [...new Set(options)]
}

const getSelectedPendingOrderMachine = (row: PendingOrderMachineRow) => {
  const key = getPendingOrderMachineKey(row)
  const options = getPendingOrderMachineOptions(row)

  return selectedPendingOrderMachines.value[key] || options[0] || row.machineAdvice || '待确认'
}

const handlePendingOrderMachineChange = (row: PendingOrderMachineRow, event: Event) => {
  const target = event.target as HTMLSelectElement
  selectedPendingOrderMachines.value = {
    ...selectedPendingOrderMachines.value,
    [getPendingOrderMachineKey(row)]: target.value,
  }
}

const getPendingOrderStatusLabel = (row: PendingOrderMachineRow) =>
  selectedPendingOrderMachines.value[getPendingOrderMachineKey(row)] ? '已选机' : row.issue

const getPendingOrderStatusTone = (row: PendingOrderMachineRow): ImportTone =>
  selectedPendingOrderMachines.value[getPendingOrderMachineKey(row)] ? 'green' : row.tone
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
                月计划页只做“看全局 + 找风险”，真正操作下沉到订单导入、智能排机和排机结果。
              </p>
            </div>
          </div>
        </SectionPanel>
      </div>
    </template>

    <template v-else-if="props.activeSection === 'order-import'">
      <SectionPanel
        title="订单导入操作台"
        subtitle="先上传订单表，系统即时识别字段、预览订单并拦截错误行。"
      >
        <div class="grid gap-5 xl:grid-cols-[0.95fr_1.05fr]">
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
                    {{ importedSheetName || '支持 .xlsx、.csv、.tsv，上传后先进入预览，不会直接覆盖订单池。' }}
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

          <article class="rounded-2xl border border-slate-200 bg-white p-5">
            <div class="flex items-center justify-between gap-3">
              <div>
                <p class="text-xs uppercase tracking-[0.2em] text-slate-500">Field Mapping</p>
                <h3 class="mt-2 text-lg font-semibold text-slate-950">字段匹配</h3>
              </div>
              <CheckCircle2 class="size-5 text-teal-600" aria-hidden="true" />
            </div>
            <div class="mt-4 grid gap-2 sm:grid-cols-2">
              <div
                v-for="field in importFieldMatchRows"
                :key="field.key"
                class="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2"
              >
                <div class="flex items-center justify-between gap-3">
                  <p class="text-sm font-semibold text-slate-900">{{ field.label }}</p>
                  <StatusPill :label="field.status" :tone="field.tone" compact />
                </div>
                <p class="mt-1 truncate text-xs text-slate-500">{{ field.matchedHeader }}</p>
              </div>
            </div>
          </article>
        </div>

        <div v-if="importedRows.length > 0" class="mt-6 grid gap-5 xl:grid-cols-[1.25fr_0.75fr]">
          <article class="rounded-2xl border border-slate-200 bg-white p-5">
            <div class="flex items-center justify-between gap-3">
              <h3 class="font-semibold text-slate-950">导入预览</h3>
              <StatusPill :label="`${importedRows.length} 行`" tone="teal" compact />
            </div>
            <div class="mt-4 overflow-x-auto">
              <table class="min-w-full text-left text-sm">
                <thead class="border-b border-slate-200 text-xs uppercase tracking-[0.18em] text-slate-500">
                  <tr>
                    <th class="pb-3 pr-4 font-medium">行号</th>
                    <th class="pb-3 pr-4 font-medium">订单</th>
                    <th class="pb-3 pr-4 font-medium">产品 / 模具</th>
                    <th class="pb-3 pr-4 font-medium">颜色 / 料型</th>
                    <th class="pb-3 pr-4 font-medium">F列推荐机型</th>
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
            <div class="mt-4 space-y-3">
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

      <div class="grid gap-6 xl:grid-cols-[0.82fr_1.18fr]">
        <SectionPanel
          title="导入步骤"
          subtitle="先导订单，再做字段校验和人工补齐，流程尽量像工厂现场真实习惯。"
        >
          <div class="space-y-3">
            <article
              v-for="task in injectionOrderImportTasks"
              :key="task.step"
              class="rounded-2xl border p-4"
              :class="panelTone[task.tone]"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="flex items-center gap-3">
                  <span class="flex size-10 items-center justify-center rounded-2xl bg-white text-slate-700">
                    <ClipboardList class="size-4" aria-hidden="true" />
                  </span>
                  <div>
                    <h3 class="font-semibold text-slate-950">{{ task.step }}</h3>
                    <p class="mt-1 text-xs text-slate-500">{{ task.owner }}</p>
                  </div>
                </div>
                <StatusPill :label="task.status" :tone="task.tone" compact />
              </div>
              <p class="mt-4 text-sm leading-6 text-slate-600">{{ task.detail }}</p>
            </article>
          </div>
        </SectionPanel>

        <SectionPanel
          title="字段校验"
          subtitle="把高风险和缺字段直接放在导入旁边，工厂人员一进来就知道要先补什么。"
        >
          <div class="grid gap-4 md:grid-cols-2">
            <article
              v-for="rule in injectionPendingOrderValidationRules"
              :key="rule.label"
              class="rounded-2xl border border-slate-200 bg-white p-4"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="flex items-center gap-3">
                  <span class="flex size-10 items-center justify-center rounded-2xl bg-slate-100 text-slate-700">
                    <ShieldAlert class="size-4" aria-hidden="true" />
                  </span>
                  <div>
                    <h3 class="font-semibold text-slate-950">{{ rule.label }}</h3>
                    <p class="mt-1 text-xs text-slate-500">{{ rule.hit }}</p>
                  </div>
                </div>
                <StatusPill :label="rule.hit" :tone="rule.tone" compact />
              </div>
              <p class="mt-4 text-sm leading-6 text-slate-600">{{ rule.detail }}</p>
            </article>
          </div>
        </SectionPanel>
      </div>

      <SectionPanel
        title="订单池"
        subtitle="这里保留工厂最常看的几列，避免一屏表头太宽、太难用。"
      >
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
                v-for="row in compactPendingOrders"
                :key="`${row.orderNo}-${row.moldCode}-${row.machineAdvice}`"
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
        </div>
      </SectionPanel>

      <SectionPanel
        title="订单标准字段"
        subtitle="现场如果不知道要补什么，这里就是最简版字段说明。"
      >
        <div class="grid gap-4 xl:grid-cols-3">
          <article
            v-for="group in injectionPendingOrderFieldGroups"
            :key="group.title"
            class="rounded-2xl border border-slate-200 bg-white p-5"
          >
            <h3 class="font-semibold text-slate-950">{{ group.title }}</h3>
            <p class="mt-1 text-xs text-slate-500">{{ group.owner }}</p>
            <div class="mt-4 space-y-3">
              <article
                v-for="field in group.fields"
                :key="`${group.title}-${field.label}`"
                class="rounded-xl bg-slate-50 px-4 py-3"
              >
                <div class="flex items-center justify-between gap-3">
                  <p class="font-medium text-slate-900">{{ field.label }}</p>
                  <StatusPill :label="field.required ? '必填' : '建议'" :tone="field.required ? 'red' : 'blue'" compact />
                </div>
                <p class="mt-2 text-xs text-slate-500">来源：{{ field.source }}</p>
              </article>
            </div>
          </article>
        </div>
      </SectionPanel>
    </template>

    <template v-else-if="props.activeSection === 'smart-scheduling'">
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
      <section class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <article
          v-for="metric in injectionReportingMetrics"
          :key="metric.label"
          class="rounded-2xl border border-slate-200 bg-white p-5"
        >
          <p class="text-sm text-slate-500">{{ metric.label }}</p>
          <p class="mt-4 text-3xl font-semibold tracking-tight text-slate-950">{{ metric.value }}</p>
          <p class="mt-3 text-xs leading-5 text-slate-500">{{ metric.detail }}</p>
        </article>
      </section>

      <div class="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <SectionPanel
          title="日报清单"
          subtitle="车间最常看的日报和回报动作统一放这页。"
        >
          <div class="space-y-3">
            <article
              v-for="item in injectionShiftReportChecklistItems"
              :key="item.title"
              class="rounded-2xl border p-4"
              :class="panelTone[item.tone]"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <h3 class="font-semibold text-slate-950">{{ item.title }}</h3>
                  <p class="mt-1 text-xs text-slate-500">{{ item.owner }}</p>
                </div>
                <StatusPill :label="item.status" :tone="item.tone" compact />
              </div>
              <p class="mt-3 text-sm leading-6 text-slate-600">{{ item.detail }}</p>
            </article>
          </div>
        </SectionPanel>

        <SectionPanel
          title="录入模板"
          subtitle="先把车间每天必须回报的字段固定下来，后面接 Excel 或表单都直接复用这套结构。"
        >
          <div class="space-y-4">
            <article
              v-for="group in injectionShiftReportTemplateGroups"
              :key="group.title"
              class="rounded-2xl border border-slate-200 bg-white p-5"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <h3 class="font-semibold text-slate-950">{{ group.title }}</h3>
                  <p class="mt-1 text-xs text-slate-500">{{ group.owner }}</p>
                </div>
                <StatusPill :label="`${group.fields.length} 项`" tone="blue" compact />
              </div>
              <div class="mt-4 grid gap-3">
                <article
                  v-for="field in group.fields"
                  :key="`${group.title}-${field.label}`"
                  class="rounded-xl bg-slate-50 px-4 py-3"
                >
                  <div class="flex items-center justify-between gap-3">
                    <p class="font-medium text-slate-900">{{ field.label }}</p>
                    <StatusPill :label="field.required ? '必填' : '选填'" :tone="field.required ? 'red' : 'blue'" compact />
                  </div>
                  <p class="mt-2 text-xs text-slate-500">来源：{{ field.source }}</p>
                  <p class="mt-2 text-sm leading-6 text-slate-600">{{ field.summary }}</p>
                </article>
              </div>
            </article>
          </div>
        </SectionPanel>
      </div>

      <SectionPanel
        title="班次交接"
        subtitle="交接记录单独放一块，避免和排机逻辑混在一起。"
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
        title="班次日报表"
        subtitle="保留最常用日报字段，适合后面继续做真实录入表单。"
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

      <SectionPanel
        title="导入字段映射"
        subtitle="把车间 Excel 列和系统字段先对齐，后面接真实日报导入时就能直接套规则。"
      >
        <div class="overflow-x-auto">
          <table class="min-w-full text-left text-sm">
            <thead class="border-b border-slate-200 text-xs uppercase tracking-[0.2em] text-slate-500">
              <tr>
                <th class="pb-3 pr-4 font-medium">来源列</th>
                <th class="pb-3 pr-4 font-medium">系统字段</th>
                <th class="pb-3 pr-4 font-medium">示例</th>
                <th class="pb-3 pr-4 font-medium">规则</th>
                <th class="pb-3 font-medium">要求</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in injectionShiftReportImportMappingRows"
                :key="`${row.sourceColumn}-${row.targetField}`"
                class="border-b border-slate-100 align-top last:border-b-0"
              >
                <td class="py-4 pr-4 font-semibold text-slate-950">{{ row.sourceColumn }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.targetField }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.sample }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.rule }}</td>
                <td class="py-4">
                  <StatusPill :label="row.required ? '必填' : '选填'" :tone="row.tone" compact />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </SectionPanel>
    </template>

    <template v-else-if="props.activeSection === 'inbound-orders'">
      <div class="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <SectionPanel
          title="入库单"
          subtitle="入库页只做送货单、PMC 和状态闭环，不和日报、排机混在一起。"
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
          title="联动规则"
          subtitle="先把送货单入库后的状态机定清楚，后面接 ERP 或仓库表时就不会反复改逻辑。"
        >
          <div class="space-y-4">
            <article
              v-for="card in injectionWritebackRuleCards"
              :key="card.title"
              class="rounded-2xl border border-slate-200 bg-white p-5"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <h3 class="font-semibold text-slate-950">{{ card.title }}</h3>
                  <p class="mt-1 text-xs text-slate-500">{{ card.owner }} · {{ card.trigger }}</p>
                </div>
                <StatusPill :label="card.status" :tone="card.tone" compact />
              </div>
              <p class="mt-4 text-sm leading-6 text-slate-600">{{ card.summary }}</p>
              <div class="mt-4 flex flex-wrap gap-2">
                <span
                  v-for="item in card.items"
                  :key="`${card.title}-${item}`"
                  class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600"
                >
                  {{ item }}
                </span>
              </div>
            </article>
          </div>
        </SectionPanel>
      </div>

      <SectionPanel
        title="入库回写"
        subtitle="真正影响第二天待排池刷新的，就是这张回写状态。"
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

      <SectionPanel
        title="主键映射"
        subtitle="把日报、送货单、排产池之间怎么命中同一条业务记录说清楚，后面接接口时最不容易返工。"
      >
        <div class="overflow-x-auto">
          <table class="min-w-full text-left text-sm">
            <thead class="border-b border-slate-200 text-xs uppercase tracking-[0.2em] text-slate-500">
              <tr>
                <th class="pb-3 pr-4 font-medium">阶段</th>
                <th class="pb-3 pr-4 font-medium">业务主键</th>
                <th class="pb-3 pr-4 font-medium">来源主键</th>
                <th class="pb-3 pr-4 font-medium">目标记录</th>
                <th class="pb-3 pr-4 font-medium">阻塞</th>
                <th class="pb-3 font-medium">状态</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in injectionWritebackKeyMatchRows"
                :key="`${row.stage}-${row.sourceKey}`"
                class="border-b border-slate-100 align-top last:border-b-0"
              >
                <td class="py-4 pr-4 font-semibold text-slate-950">{{ row.stage }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.businessKey }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.sourceKey }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.targetRecord }}</td>
                <td class="py-4 pr-4 text-slate-600">{{ row.blocker }}</td>
                <td class="py-4">
                  <StatusPill :label="row.status" :tone="row.tone" compact />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </SectionPanel>
    </template>

    <template v-else>
      <div class="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <SectionPanel
          title="数据底座"
          subtitle="基础资料页统一放机台、模具和历史数据，不再拆成很多菜单。"
        >
          <div class="space-y-3">
            <article
              v-for="dataset in injectionDataCenterDatasets"
              :key="dataset.name"
              class="rounded-2xl border border-slate-200 bg-white p-5"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <h3 class="font-semibold text-slate-950">{{ dataset.name }}</h3>
                  <p class="mt-1 text-xs text-slate-500">{{ dataset.owner }} · {{ dataset.freshness }}</p>
                </div>
                <StatusPill :label="dataset.status" :tone="dataset.statusTone" compact />
              </div>
              <div class="mt-4">
                <ProgressMeter :value="dataset.completeness" :tone="dataset.statusTone" label="完整度" />
              </div>
              <p class="mt-4 text-sm leading-6 text-slate-600">{{ dataset.summary }}</p>
            </article>
          </div>
        </SectionPanel>

        <SectionPanel
          title="数据源状态"
          subtitle="主管和计划只需要在这一页知道哪些资料还不完整。"
        >
          <div class="space-y-3">
            <article
              v-for="source in injectionDataSourceStatus"
              :key="source.name"
              class="rounded-2xl border border-slate-200 bg-white p-5"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <h3 class="font-semibold text-slate-950">{{ source.name }}</h3>
                  <p class="mt-1 text-xs text-slate-500">{{ source.freshness }}</p>
                </div>
                <StatusPill :label="source.status" :tone="source.statusTone" compact />
              </div>
              <p class="mt-4 text-sm leading-6 text-slate-600">{{ source.summary }}</p>
            </article>
          </div>
        </SectionPanel>
      </div>

      <section class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <article
          v-for="mold in injectionMoldTargetRows"
          :key="mold.moldCode"
          class="rounded-2xl border border-slate-200 bg-white p-5"
        >
          <div class="flex items-start justify-between gap-3">
            <div>
              <h3 class="font-semibold text-slate-950">{{ mold.moldCode }}</h3>
              <p class="mt-1 text-xs text-slate-500">{{ mold.source }}</p>
            </div>
            <StatusPill :label="mold.health" :tone="mold.tone" compact />
          </div>
          <div class="mt-4 grid gap-3">
            <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">24H：{{ mold.target24h }}</div>
            <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">11H：{{ mold.target11h }}</div>
          </div>
        </article>
      </section>

      <div class="grid gap-6 xl:grid-cols-[1.08fr_0.92fr]">
        <SectionPanel
          title="机台档案"
          subtitle="机台台账保留在基础资料页里，现场查资料更顺。"
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

        <SectionPanel
          title="模具目标台账"
          subtitle="模具目标页只保留目标、节拍、优选机台和健康度这些关键管理字段。"
        >
          <div class="overflow-x-auto">
            <table class="min-w-full text-left text-sm">
              <thead class="border-b border-slate-200 text-xs uppercase tracking-[0.2em] text-slate-500">
                <tr>
                  <th class="pb-3 pr-4 font-medium">模具</th>
                  <th class="pb-3 pr-4 font-medium">客户 / 产品</th>
                  <th class="pb-3 pr-4 font-medium">穴数 / 节拍</th>
                  <th class="pb-3 pr-4 font-medium">24H / 11H</th>
                  <th class="pb-3 pr-4 font-medium">优选机台</th>
                  <th class="pb-3 font-medium">健康度</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="mold in compactMoldRows"
                  :key="`${mold.moldCode}-${mold.productName}`"
                  class="border-b border-slate-100 last:border-b-0"
                >
                  <td class="py-4 pr-4 font-semibold text-slate-950">{{ mold.moldCode }}</td>
                  <td class="py-4 pr-4 text-slate-600">
                    <div>{{ mold.customer }}</div>
                    <div class="mt-1 text-xs text-slate-500">{{ mold.productName }}</div>
                  </td>
                  <td class="py-4 pr-4 text-slate-600">
                    <div>{{ mold.cavity }}</div>
                    <div class="mt-1 text-xs text-slate-500">{{ mold.cycleTime }}</div>
                  </td>
                  <td class="py-4 pr-4 text-slate-600">
                    <div>{{ mold.target24h }}</div>
                    <div class="mt-1 text-xs text-slate-500">{{ mold.target11h }}</div>
                  </td>
                  <td class="py-4 pr-4 text-slate-600">{{ mold.preferredMachine }}</td>
                  <td class="py-4">
                    <StatusPill :label="mold.health" :tone="mold.tone" compact />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </SectionPanel>

      </div>

      <div class="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
        <SectionPanel
          title="机台卡片"
          subtitle="保留少量卡片方便扫一眼状态，但不再单独占一个菜单。"
        >
          <div class="space-y-3">
            <article
              v-for="machine in compactMachineProfiles"
              :key="machine.machine"
              class="rounded-2xl border border-slate-200 bg-white p-4"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="flex items-center gap-3">
                  <span class="flex size-10 items-center justify-center rounded-2xl bg-slate-100 text-slate-700">
                    <Factory class="size-4" aria-hidden="true" />
                  </span>
                  <div>
                    <h3 class="font-semibold text-slate-950">{{ machine.machine }}</h3>
                    <p class="mt-1 text-xs text-slate-500">{{ machine.tonnage }} · {{ machine.armType }} · {{ machine.workshop }}</p>
                  </div>
                </div>
                <StatusPill :label="machine.status" :tone="machine.tone" compact />
              </div>
              <p class="mt-4 text-sm leading-6 text-slate-600">{{ machine.fit }}</p>
            </article>
          </div>
        </SectionPanel>

        <SectionPanel
          title="模具映射与规则"
          subtitle="映射和规则留在基础资料页里集中维护，但只保留最必要的信息。"
        >
          <div class="grid gap-4 lg:grid-cols-[1.05fr_0.95fr]">
            <div class="space-y-3">
              <article
                v-for="row in compactMappingRows"
                :key="`${row.moldCode}-${row.recommendedMachine}`"
                class="rounded-2xl border border-slate-200 bg-white p-4"
              >
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <h3 class="font-semibold text-slate-950">{{ row.moldCode }}</h3>
                    <p class="mt-1 text-xs text-slate-500">{{ row.customer }} · {{ row.productName }}</p>
                  </div>
                  <StatusPill :label="row.status" :tone="row.tone" compact />
                </div>
                <div class="mt-4 grid gap-3">
                  <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">候选池：{{ row.candidatePool }}</div>
                  <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">主机台：{{ row.recommendedMachine }}</div>
                  <div class="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">备选：{{ row.backupMachine }}</div>
                </div>
              </article>
            </div>

            <div class="space-y-3">
              <article
                v-for="card in injectionConfigRuleCards"
                :key="card.title"
                class="rounded-2xl border border-slate-200 bg-white p-5"
              >
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <h3 class="font-semibold text-slate-950">{{ card.title }}</h3>
                    <p class="mt-1 text-xs text-slate-500">{{ card.owner }}</p>
                  </div>
                  <StatusPill :label="card.status" :tone="card.tone" compact />
                </div>
                <p class="mt-4 text-sm leading-6 text-slate-600">{{ card.summary }}</p>
              </article>
            </div>
          </div>
        </SectionPanel>
      </div>
    </template>
  </div>
</template>
