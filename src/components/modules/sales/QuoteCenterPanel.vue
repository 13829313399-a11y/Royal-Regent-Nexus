<script setup lang="ts">
import { CheckCircle2, Download, Eye, Search, UploadCloud, Users } from '@lucide/vue'
import { computed, ref } from 'vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import {
  buildBuzzBeeCustomerQuoteFileName,
  convertBuzzBeeInternalQuote,
  createBuzzBeeCustomerQuoteWorkbook,
  type BuzzBeeConversionResult,
} from '@/lib/customerPriceConverters/buzzbee'
import {
  DISNEY_CUSTOMER_QUOTE_TEMPLATE_URL,
  buildDisneyCustomerQuoteFileName,
  convertDisneyInternalQuote,
  createDisneyCustomerQuoteWorkbook,
  type DisneyConversionResult,
} from '@/lib/customerPriceConverters/disney'
import {
  DICKY_CUSTOMER_QUOTE_TEMPLATE_URL,
  buildDickyCustomerQuoteFileName,
  convertDickyInternalQuote,
  createDickyCustomerQuoteWorkbook,
  type DickyConversionResult,
} from '@/lib/customerPriceConverters/dicky'
import {
  CAIXING_PLASTIC_CUSTOMER_QUOTE_TEMPLATE_URL,
  CAIXING_PLUSH_CUSTOMER_QUOTE_TEMPLATE_URL,
  buildCaixingCustomerQuoteFileName,
  convertCaixingInternalQuote,
  createCaixingCustomerQuoteWorkbook,
  type CaixingConversionResult,
  type CaixingProductType,
} from '@/lib/customerPriceConverters/caixing'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

type ConversionStatus = '待转换' | '待复核' | '已生成'
type DetailCompareStatus = '上调' | '下调' | '持平'

interface CustomerPriceConversionRow {
  id: string
  customerId: string
  customer: string
  workshop: string
  internalPriceHkd: number
  customerPriceHkd: number
  marginBand: string
  status: ConversionStatus
  quoteNo: string
  sourceFileName: string
  updatedAt: string
}

interface CustomerOption {
  id: string
  name: string
  factoryId: string
  department: string
  workshop: string
  owner: string
  activeQuoteCount: number
}

interface QuoteSheetDetailRow {
  id: string
  sheetId: string
  sheetName: string
  itemNo: string
  description: string
  internalPriceHkd: number
  customerPriceHkd: number
  previousCustomerPriceHkd: number
  differenceHkd: number
  marginBand: string
  compareStatus: DetailCompareStatus
}

interface ImportedWorkbookSheet {
  id: string
  name: string
  sourceFileName: string
  rowCount: number
  totalInternalHkd: number
  totalCustomerHkd: number
  details: QuoteSheetDetailRow[]
}

interface ExportedQuoteVersion {
  id: string
  fileName: string
  customerId: string
  customerName: string
  productType?: CaixingProductType
  createdAt: string
  sheetCount: number
  detailCount: number
  totalCustomerHkd: number
  deltaFromPreviousHkd: number
}

const authStore = useAuthStore()
const appStore = useAppStore()

const customerOptions: CustomerOption[] = [
  {
    id: 'buzzbee',
    name: 'BuzzBee',
    factoryId: 'huaxing',
    department: 'sales-business',
    workshop: '啤机车间 A',
    owner: '李业务',
    activeQuoteCount: 1,
  },
  {
    id: 'disney',
    name: '迪士尼',
    factoryId: 'huaxing',
    department: 'sales-business',
    workshop: '啤机车间 A',
    owner: '李业务',
    activeQuoteCount: 1,
  },
  {
    id: 'dicky',
    name: 'Dickie',
    factoryId: 'huaxing',
    department: 'sales-business',
    workshop: '啤机车间 A',
    owner: 'Ben / Dickie',
    activeQuoteCount: 1,
  },
  {
    id: 'caixing',
    name: '彩星',
    factoryId: 'huaxing',
    department: 'sales-business',
    workshop: '啤机车间 A',
    owner: '陈善杰',
    activeQuoteCount: 2,
  },
]

const selectedCustomerId = ref(customerOptions[0]?.id ?? '')
const caixingProductTypeOptions = [
  { id: 'plastic', label: '塑胶', detail: '塑胶 / 注塑类报客价' },
  { id: 'plush', label: '毛绒', detail: '毛绒 / 车衣车发类报客价' },
] satisfies Array<{ id: CaixingProductType, label: string, detail: string }>
const selectedCaixingProductType = ref<CaixingProductType>('plastic')
const importedCaixingProductType = ref<CaixingProductType | ''>('')
const detailSearchQuery = ref('')
const importedCustomerId = ref('')
const importedFileName = ref('')
const importedFileSize = ref('')
const importedAt = ref('')
const importErrorMessage = ref('')
const exportErrorMessage = ref('')
const isExportingCustomerQuote = ref(false)
const selectedSheetId = ref('all')
const selectedExportVersionId = ref('')
const importedWorkbookSheets = ref<ImportedWorkbookSheet[]>([])
const exportedQuoteVersions = ref<ExportedQuoteVersion[]>([])
const buzzBeeConversionResult = ref<BuzzBeeConversionResult | null>(null)
const disneyConversionResult = ref<DisneyConversionResult | null>(null)
const dickyConversionResult = ref<DickyConversionResult | null>(null)
const caixingConversionResult = ref<CaixingConversionResult | null>(null)
const isImportDragActive = ref(false)
let importDragDepth = 0
const XLSX_MIME_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
const EXCEL_HTML_MIME_TYPE = 'application/vnd.ms-excel;charset=utf-8'

const conversionRows = ref<CustomerPriceConversionRow[]>([
  {
    id: 'QTC-HKA-260707-018',
    customerId: 'buzzbee',
    customer: 'BuzzBee',
    workshop: '啤机车间 A',
    internalPriceHkd: 12.86,
    customerPriceHkd: 15.4,
    marginBand: '19.8%',
    status: '待转换',
    quoteNo: '待生成',
    sourceFileName: '待导入',
    updatedAt: '今天 09:30',
  },
  {
    id: 'QTC-HKA-260707-022',
    customerId: 'disney',
    customer: '迪士尼',
    workshop: '啤机车间 A',
    internalPriceHkd: 8.42,
    customerPriceHkd: 10.2,
    marginBand: '21.1%',
    status: '待转换',
    quoteNo: '待生成',
    sourceFileName: '待导入',
    updatedAt: '今天 10:15',
  },
  {
    id: 'QTC-HKA-260709-041',
    customerId: 'dicky',
    customer: 'Dickie',
    workshop: '啤机车间 A',
    internalPriceHkd: 0,
    customerPriceHkd: 0,
    marginBand: '-',
    status: '待转换',
    quoteNo: '待生成',
    sourceFileName: '待导入',
    updatedAt: '今天 14:30',
  },
  {
    id: 'QTC-HKA-260708-031',
    customerId: 'caixing',
    customer: '彩星',
    workshop: '啤机车间 A',
    internalPriceHkd: 0,
    customerPriceHkd: 0,
    marginBand: '-',
    status: '待转换',
    quoteNo: '待生成',
    sourceFileName: '待导入',
    updatedAt: '今天 11:20',
  },
  {
    id: 'QTC-HKB-260707-011',
    customerId: 'zuru',
    customer: 'Zuru',
    workshop: '啤机车间 B',
    internalPriceHkd: 16.08,
    customerPriceHkd: 19.1,
    marginBand: '18.8%',
    status: '待转换',
    quoteNo: '待生成',
    sourceFileName: '待导入',
    updatedAt: '昨天 17:40',
  },
  {
    id: 'QTC-HD-260707-004',
    customerId: 'spin-master',
    customer: 'Spin Master',
    workshop: '喷油车间',
    internalPriceHkd: 4.35,
    customerPriceHkd: 5.2,
    marginBand: '19.5%',
    status: '已生成',
    quoteNo: 'CQ-HD-260707-002',
    sourceFileName: 'Spin-Master-内部报价-260706.xlsx',
    updatedAt: '昨天 15:20',
  },
])

const visibleCustomers = computed(() => customerOptions.map((customer) => ({
  ...customer,
  factoryId: appStore.activeProductionFactory.id,
})))

const selectedCustomer = computed<CustomerOption>(() => {
  return visibleCustomers.value.find((customer) => customer.id === selectedCustomerId.value)
    ?? (visibleCustomers.value[0] as CustomerOption)
})

const canImportSelectedCustomer = computed(() => {
  return authStore.can(
    'customer_price:import_internal_quote',
    selectedCustomer.value.factoryId,
    selectedCustomer.value.department,
  )
})

const canExportSelectedCustomer = computed(() => {
  return authStore.can(
    'customer_price:export_customer_quote',
    selectedCustomer.value.factoryId,
    selectedCustomer.value.department,
  )
})

const selectedCustomerOperationSummary = computed(() => {
  if (canImportSelectedCustomer.value && canExportSelectedCustomer.value) {
    return { value: '可导入/输出', detail: '全部客户按相同权限操作' }
  }

  if (canImportSelectedCustomer.value) {
    return { value: '仅可导入', detail: '当前账号没有输出权限' }
  }

  if (canExportSelectedCustomer.value) {
    return { value: '仅可输出', detail: '当前账号没有导入权限' }
  }

  return { value: '仅查看', detail: '当前账号没有导入和输出权限' }
})

const selectedCaixingProductTypeOption = computed(() => {
  return caixingProductTypeOptions.find((option) => option.id === selectedCaixingProductType.value)
    ?? caixingProductTypeOptions[0]
})

const selectedImportMatchesCurrentChoice = computed(() => {
  if (importedCustomerId.value !== selectedCustomer.value.id) {
    return false
  }

  if (selectedCustomer.value.id !== 'caixing') {
    return true
  }

  return importedCaixingProductType.value === selectedCaixingProductType.value
})

const visibleConversionRows = computed(() => {
  return conversionRows.value.filter((row) => row.customerId === selectedCustomer.value.id)
})

const existingSelectedSourceFileName = computed(() => {
  if (selectedCustomer.value.id === 'buzzbee' || selectedCustomer.value.id === 'disney' || selectedCustomer.value.id === 'dicky' || selectedCustomer.value.id === 'caixing') {
    return ''
  }

  return visibleConversionRows.value.find((row) => row.sourceFileName !== '待导入')?.sourceFileName ?? ''
})

const selectedImportFileName = computed(() => {
  if (selectedImportMatchesCurrentChoice.value && importedFileName.value) {
    return importedFileName.value
  }

  return existingSelectedSourceFileName.value
})

const selectedImportFileDetail = computed(() => {
  if (importErrorMessage.value && !selectedImportFileName.value) {
    return importErrorMessage.value
  }

  if (!selectedImportFileName.value) {
    return '导入后会锁定到当前选择客户'
  }

  if (selectedImportMatchesCurrentChoice.value) {
    return `${importedFileSize.value} · ${importedAt.value}`
  }

  return '已有内部报价来源'
})

const activeWorkbookSheets = computed(() => {
  return selectedImportMatchesCurrentChoice.value ? importedWorkbookSheets.value : []
})

const activeWorkbookDetailRows = computed(() => {
  return activeWorkbookSheets.value.flatMap((sheet) => sheet.details)
})

const selectedSheetRows = computed(() => {
  const baseRows = selectedSheetId.value === 'all'
    ? activeWorkbookDetailRows.value
    : activeWorkbookDetailRows.value.filter((row) => row.sheetId === selectedSheetId.value)
  const query = detailSearchQuery.value.trim().toLowerCase()

  if (!query) {
    return baseRows
  }

  return baseRows.filter((row) => {
    return row.sheetName.toLowerCase().includes(query)
      || row.itemNo.toLowerCase().includes(query)
      || row.description.toLowerCase().includes(query)
  })
})

const activeExportedVersions = computed(() => {
  return exportedQuoteVersions.value.filter((version) => {
    if (version.customerId !== selectedCustomer.value.id) {
      return false
    }

    if (selectedCustomer.value.id !== 'caixing') {
      return true
    }

    return version.productType === selectedCaixingProductType.value
  })
})

const hasActiveBuzzBeeConversion = computed(() => {
  return selectedCustomer.value.id === 'buzzbee'
    && selectedImportMatchesCurrentChoice.value
    && Boolean(buzzBeeConversionResult.value)
})

const hasActiveDisneyConversion = computed(() => {
  return selectedCustomer.value.id === 'disney'
    && selectedImportMatchesCurrentChoice.value
    && Boolean(disneyConversionResult.value)
})

const hasActiveDickyConversion = computed(() => {
  return selectedCustomer.value.id === 'dicky'
    && selectedImportMatchesCurrentChoice.value
    && Boolean(dickyConversionResult.value)
})

const hasActiveCaixingConversion = computed(() => {
  return selectedCustomer.value.id === 'caixing'
    && selectedImportMatchesCurrentChoice.value
    && caixingConversionResult.value?.productType === selectedCaixingProductType.value
})

const comparisonMetrics = computed(() => {
  const totalInternal = activeWorkbookSheets.value.reduce((sum, sheet) => sum + sheet.totalInternalHkd, 0)
  const totalCustomer = activeWorkbookSheets.value.reduce((sum, sheet) => sum + sheet.totalCustomerHkd, 0)
  const delta = activeExportedVersions.value[0]?.deltaFromPreviousHkd ?? 0

  return [
    { label: '导入 Sheet', value: String(activeWorkbookSheets.value.length), detail: `${activeWorkbookDetailRows.value.length} 条明细` },
    { label: '内部价合计', value: formatHkd(totalInternal), detail: selectedImportFileName.value || '等待导入' },
    { label: '报客价合计', value: formatHkd(totalCustomer), detail: delta === 0 ? '暂无版本差异' : `较上一版 ${formatSignedHkd(delta)}` },
    { label: '已输出版本', value: String(activeExportedVersions.value.length), detail: activeExportedVersions.value[0]?.fileName ?? '暂无导出' },
  ]
})

const canExportCustomerQuote = computed(() => {
  if (!canExportSelectedCustomer.value) {
    return false
  }

  if (selectedCustomer.value.id === 'buzzbee') {
    return hasActiveBuzzBeeConversion.value
  }

  if (selectedCustomer.value.id === 'disney') {
    return hasActiveDisneyConversion.value
  }

  if (selectedCustomer.value.id === 'dicky') {
    return hasActiveDickyConversion.value
  }

  if (selectedCustomer.value.id === 'caixing') {
    return hasActiveCaixingConversion.value
  }

  return visibleConversionRows.value.length > 0 && Boolean(selectedImportFileName.value)
})

const hasSelectedCustomerImport = computed(() => Boolean(selectedImportFileName.value))

const importOverviewMetrics = computed(() => [
  { label: '当前客户', value: selectedCustomer.value.name, detail: selectedCustomer.value.id === 'caixing' ? `${selectedCaixingProductTypeOption.value.label} · ${selectedCustomer.value.owner}` : `${selectedCustomer.value.workshop} · ${selectedCustomer.value.owner}` },
  { label: '内部报价', value: selectedImportFileName.value ? '已导入' : '待导入', detail: selectedImportFileName.value || '等待 Excel' },
  {
    label: '操作权限',
    value: selectedCustomerOperationSummary.value.value,
    detail: canExportCustomerQuote.value
      ? '右上角可输出报客价'
      : selectedCustomerOperationSummary.value.detail,
  },
])

function getCompareStatus(differenceHkd: number): DetailCompareStatus {
  if (differenceHkd > 0.01) {
    return '上调'
  }

  if (differenceHkd < -0.01) {
    return '下调'
  }

  return '持平'
}

function createDetailRow(
  sheetId: string,
  sheetName: string,
  itemNo: string,
  description: string,
  internalPriceHkd: number,
  customerPriceHkd: number,
  previousCustomerPriceHkd: number,
): QuoteSheetDetailRow {
  const differenceHkd = Number((customerPriceHkd - previousCustomerPriceHkd).toFixed(2))

  return {
    id: `${sheetId}-${itemNo}`,
    sheetId,
    sheetName,
    itemNo,
    description,
    internalPriceHkd,
    customerPriceHkd,
    previousCustomerPriceHkd,
    differenceHkd,
    marginBand: `${(((customerPriceHkd - internalPriceHkd) / internalPriceHkd) * 100).toFixed(1)}%`,
    compareStatus: getCompareStatus(differenceHkd),
  }
}

function buildMarginBand(internalPriceHkd: number, customerPriceHkd: number) {
  if (!internalPriceHkd) {
    return '-'
  }

  return `${(((customerPriceHkd - internalPriceHkd) / internalPriceHkd) * 100).toFixed(1)}%`
}

function createMockWorkbookSheets(customer: CustomerOption, sourceFileName: string): ImportedWorkbookSheet[] {
  const customerPrefix = customer.id === 'disney' ? 'DSN' : 'BB'
  const sheetSpecs = [
    {
      id: `${customer.id}-injection`,
      name: '注塑件',
      rows: [
        createDetailRow(`${customer.id}-injection`, '注塑件', `${customerPrefix}-INJ-001`, '外壳主件', 12.86, 15.4, 14.8),
        createDetailRow(`${customer.id}-injection`, '注塑件', `${customerPrefix}-INJ-002`, '手柄饰件', 8.42, 10.2, 10.2),
        createDetailRow(`${customer.id}-injection`, '注塑件', `${customerPrefix}-INJ-003`, '透明配件', 6.7, 8.1, 8.4),
      ],
    },
    {
      id: `${customer.id}-spray`,
      name: '喷油加工',
      rows: [
        createDetailRow(`${customer.id}-spray`, '喷油加工', `${customerPrefix}-SPY-001`, '双色喷油', 3.15, 4.05, 3.86),
        createDetailRow(`${customer.id}-spray`, '喷油加工', `${customerPrefix}-SPY-002`, '移印 LOGO', 1.28, 1.65, 1.65),
      ],
    },
    {
      id: `${customer.id}-packing`,
      name: '包装配件',
      rows: [
        createDetailRow(`${customer.id}-packing`, '包装配件', `${customerPrefix}-PKG-001`, '彩盒与说明书', 2.4, 3.1, 2.92),
        createDetailRow(`${customer.id}-packing`, '包装配件', `${customerPrefix}-PKG-002`, '吸塑托盘', 1.82, 2.25, 2.3),
      ],
    },
  ]

  return sheetSpecs.map((sheet) => ({
    id: sheet.id,
    name: sheet.name,
    sourceFileName,
    rowCount: sheet.rows.length,
    totalInternalHkd: Number(sheet.rows.reduce((sum, row) => sum + row.internalPriceHkd, 0).toFixed(2)),
    totalCustomerHkd: Number(sheet.rows.reduce((sum, row) => sum + row.customerPriceHkd, 0).toFixed(2)),
    details: sheet.rows,
  }))
}

function formatHkd(value: number) {
  return new Intl.NumberFormat('zh-HK', {
    style: 'currency',
    currency: 'HKD',
    maximumFractionDigits: 2,
  }).format(value)
}

function formatSignedHkd(value: number) {
  if (value === 0) {
    return formatHkd(0)
  }

  return `${value > 0 ? '+' : ''}${formatHkd(value)}`
}

function formatFileSize(size: number) {
  if (size < 1024 * 1024) {
    return `${Math.max(1, Math.round(size / 1024))} KB`
  }

  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function readFileAsArrayBuffer(file: File) {
  return file.arrayBuffer()
}

function resolvePublicAssetUrl(url: string) {
  if (/^(?:[a-z][a-z\d+\-.]*:)?\/\//i.test(url) || url.startsWith('blob:') || url.startsWith('data:')) {
    return url
  }

  const baseUrl = import.meta.env.BASE_URL || '/'
  const normalizedBase = baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`
  const normalizedPath = url.replace(/^\/+/, '')

  return `${normalizedBase}${normalizedPath}`
}

async function fetchTemplateBuffer(templateUrl: string, label: string) {
  const templateResponse = await fetch(resolvePublicAssetUrl(templateUrl), { cache: 'no-cache' })
  if (!templateResponse.ok) {
    throw new Error(`${label}模板读取失败（${templateResponse.status}）`)
  }

  const templateBuffer = await templateResponse.arrayBuffer()
  const signature = new Uint8Array(templateBuffer.slice(0, 4))
  const isXlsxZip = signature[0] === 0x50 && signature[1] === 0x4b
  if (!isXlsxZip) {
    throw new Error(`${label}模板路径返回的不是 Excel 文件`)
  }

  return templateBuffer
}

function uint8ArrayToArrayBuffer(bytes: Uint8Array) {
  const copy = new Uint8Array(bytes.byteLength)
  copy.set(bytes)
  return copy.buffer
}

function downloadGeneratedFile(content: Uint8Array | ArrayBuffer | string, fileName: string, type: string) {
  const blobPart = content instanceof Uint8Array ? uint8ArrayToArrayBuffer(content) : content
  const blob = new Blob([blobPart], { type })
  const url = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')

  anchor.href = url
  anchor.download = fileName
  anchor.style.display = 'none'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => window.URL.revokeObjectURL(url), 1000)
}

function compareStatusClass(status: DetailCompareStatus) {
  if (status === '上调') {
    return 'bg-amber-50 text-amber-700 ring-amber-200'
  }

  if (status === '下调') {
    return 'bg-blue-50 text-blue-700 ring-blue-200'
  }

  return 'bg-emerald-50 text-emerald-700 ring-emerald-200'
}

function canGenerateQuote(row: CustomerPriceConversionRow) {
  return canExportSelectedCustomer.value
    && row.customerId === selectedCustomer.value.id
    && row.status !== '已生成'
}

function generateCustomerQuote(rowId: string) {
  const row = conversionRows.value.find((item) => item.id === rowId)
  if (!row || !canGenerateQuote(row)) {
    return
  }

  row.status = '已生成'
  row.quoteNo = row.quoteNo === '待生成' ? `CQ-${row.id.replace('QTC-', '')}` : row.quoteNo
  row.updatedAt = '刚刚'
}

async function importInternalQuoteFile(file: File | undefined) {
  const customer = selectedCustomer.value
  if (!file || !customer || !canImportSelectedCustomer.value) {
    return
  }

  importErrorMessage.value = ''

  try {
    if (customer.id === 'buzzbee') {
      if (!file.name.toLowerCase().endsWith('.xlsx')) {
        throw new Error('BuzzBee 当前先支持 .xlsx 内部报价，旧 .xls 请先另存为 .xlsx')
      }

      const buffer = await readFileAsArrayBuffer(file)
      const conversionResult = convertBuzzBeeInternalQuote(buffer, file.name)
      const detailCount = conversionResult.sheets.reduce((sum, sheet) => sum + sheet.details.length, 0)

      buzzBeeConversionResult.value = conversionResult
      disneyConversionResult.value = null
      dickyConversionResult.value = null
      caixingConversionResult.value = null
      importedWorkbookSheets.value = conversionResult.sheets
      importedFileSize.value = `${formatFileSize(file.size)} · ${conversionResult.sheets.length} Sheet / ${detailCount} 条`
    } else if (customer.id === 'disney') {
      if (!file.name.toLowerCase().endsWith('.xlsx')) {
        throw new Error('迪士尼当前先支持 .xlsx 内部报价，旧 .xls 请先另存为 .xlsx')
      }

      const buffer = await readFileAsArrayBuffer(file)
      const conversionResult = convertDisneyInternalQuote(buffer, file.name)
      const detailCount = conversionResult.sheets.reduce((sum, sheet) => sum + sheet.details.length, 0)

      buzzBeeConversionResult.value = null
      disneyConversionResult.value = conversionResult
      dickyConversionResult.value = null
      caixingConversionResult.value = null
      importedWorkbookSheets.value = conversionResult.sheets
      importedFileSize.value = `${formatFileSize(file.size)} · ${conversionResult.sheets.length} Sheet / ${detailCount} 条`
    } else if (customer.id === 'dicky') {
      if (!file.name.toLowerCase().endsWith('.xlsx')) {
        throw new Error('Dickie 当前先支持 .xlsx 内部报价，旧 .xls 请先另存为 .xlsx')
      }

      const buffer = await readFileAsArrayBuffer(file)
      const conversionResult = convertDickyInternalQuote(buffer, file.name)
      const detailCount = conversionResult.sheets.reduce((sum, sheet) => sum + sheet.details.length, 0)

      buzzBeeConversionResult.value = null
      disneyConversionResult.value = null
      dickyConversionResult.value = conversionResult
      caixingConversionResult.value = null
      importedWorkbookSheets.value = conversionResult.sheets
      importedFileSize.value = `${formatFileSize(file.size)} · ${conversionResult.sheets.length} Sheet / ${detailCount} 条`
    } else if (customer.id === 'caixing') {
      if (!file.name.toLowerCase().endsWith('.xlsx')) {
        throw new Error('彩星当前先支持 .xlsx 内部报价，旧 .xls 请先另存为 .xlsx')
      }

      const buffer = await readFileAsArrayBuffer(file)
      const conversionResult = convertCaixingInternalQuote(buffer, file.name, selectedCaixingProductType.value)
      const detailCount = conversionResult.sheets.reduce((sum, sheet) => sum + sheet.details.length, 0)

      buzzBeeConversionResult.value = null
      disneyConversionResult.value = null
      dickyConversionResult.value = null
      caixingConversionResult.value = conversionResult
      importedWorkbookSheets.value = conversionResult.sheets
      importedFileSize.value = `${formatFileSize(file.size)} · ${conversionResult.sheets.length} Sheet / ${detailCount} 条`
    } else {
      buzzBeeConversionResult.value = null
      disneyConversionResult.value = null
      dickyConversionResult.value = null
      caixingConversionResult.value = null
      importedWorkbookSheets.value = createMockWorkbookSheets(customer, file.name)
      importedFileSize.value = formatFileSize(file.size)
    }

    importedFileName.value = file.name
    importedCustomerId.value = customer.id
    importedCaixingProductType.value = customer.id === 'caixing' ? selectedCaixingProductType.value : ''
    importedAt.value = '刚刚'
    selectedSheetId.value = 'all'
    selectedExportVersionId.value = ''

    const totalInternalHkd = Number(importedWorkbookSheets.value.reduce((sum, sheet) => sum + sheet.totalInternalHkd, 0).toFixed(3))
    const totalCustomerHkd = Number(importedWorkbookSheets.value.reduce((sum, sheet) => sum + sheet.totalCustomerHkd, 0).toFixed(3))

    conversionRows.value = conversionRows.value.map((row) => {
      if (row.customerId !== customer.id) {
        return row
      }

      return {
        ...row,
        internalPriceHkd: totalInternalHkd || row.internalPriceHkd,
        customerPriceHkd: totalCustomerHkd || row.customerPriceHkd,
        marginBand: totalInternalHkd && totalCustomerHkd ? buildMarginBand(totalInternalHkd, totalCustomerHkd) : row.marginBand,
        status: row.status === '已生成' ? '待复核' : '待转换',
        quoteNo: row.quoteNo === '待生成' ? '待生成' : row.quoteNo,
        sourceFileName: file.name,
        updatedAt: '刚刚',
      }
    })
  } catch (error) {
    importedFileName.value = ''
    importedFileSize.value = ''
    importedCustomerId.value = ''
    importedCaixingProductType.value = ''
    importedAt.value = ''
    importedWorkbookSheets.value = []
    buzzBeeConversionResult.value = null
    disneyConversionResult.value = null
    dickyConversionResult.value = null
    caixingConversionResult.value = null
    importErrorMessage.value = error instanceof Error ? `导入失败：${error.message}` : '导入失败：内部报价解析失败'
  }
}

async function handleInternalQuoteImport(event: Event) {
  const input = event.target as HTMLInputElement
  await importInternalQuoteFile(input.files?.[0])

  input.value = ''
}

function handleInternalQuoteDragEnter() {
  if (!canImportSelectedCustomer.value) {
    return
  }

  importDragDepth += 1
  isImportDragActive.value = true
}

function handleInternalQuoteDragOver(event: DragEvent) {
  if (!canImportSelectedCustomer.value) {
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'none'
    }
    return
  }

  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = 'copy'
  }
  isImportDragActive.value = true
}

function handleInternalQuoteDragLeave() {
  importDragDepth = Math.max(0, importDragDepth - 1)
  if (importDragDepth === 0) {
    isImportDragActive.value = false
  }
}

async function handleInternalQuoteDrop(event: DragEvent) {
  importDragDepth = 0
  isImportDragActive.value = false
  if (!canImportSelectedCustomer.value) {
    return
  }

  await importInternalQuoteFile(event.dataTransfer?.files?.[0])
}

function escapeExcelCell(value: string | number) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

async function exportCustomerQuoteExcel() {
  if (!selectedCustomer.value || !canExportSelectedCustomer.value || !canExportCustomerQuote.value || isExportingCustomerQuote.value) {
    return
  }

  exportErrorMessage.value = ''
  isExportingCustomerQuote.value = true

  try {
    const detailRows = activeWorkbookDetailRows.value
    const date = new Date().toISOString().slice(0, 10).replace(/-/g, '')
    const versionNumber = activeExportedVersions.value.length + 1
    let fileName = `${selectedCustomer.value.name}-报客价-V${versionNumber}-${date}.xls`

    if (selectedCustomer.value.id === 'buzzbee' && buzzBeeConversionResult.value) {
      const workbook = createBuzzBeeCustomerQuoteWorkbook(buzzBeeConversionResult.value)
      fileName = buildBuzzBeeCustomerQuoteFileName(buzzBeeConversionResult.value)
      downloadGeneratedFile(workbook, fileName, XLSX_MIME_TYPE)
    } else if (selectedCustomer.value.id === 'disney' && disneyConversionResult.value) {
      const templateBuffer = await fetchTemplateBuffer(DISNEY_CUSTOMER_QUOTE_TEMPLATE_URL, '迪士尼报客')
      const workbook = createDisneyCustomerQuoteWorkbook(disneyConversionResult.value, templateBuffer)
      fileName = buildDisneyCustomerQuoteFileName(disneyConversionResult.value)
      downloadGeneratedFile(workbook, fileName, XLSX_MIME_TYPE)
    } else if (selectedCustomer.value.id === 'dicky' && dickyConversionResult.value) {
      const templateBuffer = await fetchTemplateBuffer(DICKY_CUSTOMER_QUOTE_TEMPLATE_URL, 'Dickie 报客')
      const workbook = createDickyCustomerQuoteWorkbook(dickyConversionResult.value, templateBuffer)
      fileName = buildDickyCustomerQuoteFileName(dickyConversionResult.value)
      downloadGeneratedFile(workbook, fileName, XLSX_MIME_TYPE)
    } else if (selectedCustomer.value.id === 'caixing' && caixingConversionResult.value) {
      const productType = caixingConversionResult.value.productType
      const templateUrl = productType === 'plush'
        ? CAIXING_PLUSH_CUSTOMER_QUOTE_TEMPLATE_URL
        : CAIXING_PLASTIC_CUSTOMER_QUOTE_TEMPLATE_URL
      const templateLabel = productType === 'plush' ? '彩星毛绒报客' : '彩星塑胶报客'
      const templateBuffer = await fetchTemplateBuffer(templateUrl, templateLabel)
      const workbook = createCaixingCustomerQuoteWorkbook(caixingConversionResult.value, templateBuffer)
      fileName = buildCaixingCustomerQuoteFileName(caixingConversionResult.value)
      downloadGeneratedFile(workbook, fileName, XLSX_MIME_TYPE)
    } else {
      const tableRows = detailRows.length > 0
        ? detailRows.map((row) => `
          <tr>
            <td>${escapeExcelCell(row.sheetName)}</td>
            <td>${escapeExcelCell(row.itemNo)}</td>
            <td>${escapeExcelCell(row.description)}</td>
            <td>${escapeExcelCell(row.internalPriceHkd)}</td>
            <td>${escapeExcelCell(row.customerPriceHkd)}</td>
            <td>${escapeExcelCell(row.previousCustomerPriceHkd)}</td>
            <td>${escapeExcelCell(formatSignedHkd(row.differenceHkd))}</td>
            <td>${escapeExcelCell(row.marginBand)}</td>
          </tr>
        `).join('')
        : visibleConversionRows.value.map((row) => `
          <tr>
            <td>${escapeExcelCell(row.sourceFileName)}</td>
            <td>${escapeExcelCell(row.id)}</td>
            <td>${escapeExcelCell(row.customer)}</td>
            <td>${escapeExcelCell(row.internalPriceHkd)}</td>
            <td>${escapeExcelCell(row.customerPriceHkd)}</td>
            <td>${escapeExcelCell(row.customerPriceHkd)}</td>
            <td>${escapeExcelCell(formatHkd(0))}</td>
            <td>${escapeExcelCell(row.marginBand)}</td>
          </tr>
        `).join('')

      const workbookHtml = `
        <html>
          <head>
            <meta charset="UTF-8">
            <style>
              table { border-collapse: collapse; }
              th, td { border: 1px solid #94a3b8; padding: 6px 10px; }
              th { background: #e2e8f0; }
            </style>
          </head>
          <body>
            <table>
              <thead>
                <tr>
                  <th>Sheet</th>
                  <th>项目编号</th>
                  <th>项目名称</th>
                  <th>内部价 HKD</th>
                  <th>报客价 HKD</th>
                  <th>上一版报客价 HKD</th>
                  <th>差异</th>
                  <th>利润带</th>
                </tr>
              </thead>
              <tbody>${tableRows}</tbody>
            </table>
          </body>
        </html>
      `

      downloadGeneratedFile(workbookHtml, fileName, EXCEL_HTML_MIME_TYPE)
    }

    visibleConversionRows.value.forEach((row) => {
      if (row.status !== '已生成') {
        generateCustomerQuote(row.id)
      }
    })

    const totalCustomerHkd = detailRows.length > 0
      ? Number(detailRows.reduce((sum, row) => sum + row.customerPriceHkd, 0).toFixed(2))
      : Number(visibleConversionRows.value.reduce((sum, row) => sum + row.customerPriceHkd, 0).toFixed(2))
    const previousVersion = activeExportedVersions.value[0]
    const exportedVersion: ExportedQuoteVersion = {
      id: `EXP-${selectedCustomer.value.id}-${Date.now()}`,
      fileName,
      customerId: selectedCustomer.value.id,
      customerName: selectedCustomer.value.name,
      productType: selectedCustomer.value.id === 'caixing' ? selectedCaixingProductType.value : undefined,
      createdAt: '刚刚',
      sheetCount: activeWorkbookSheets.value.length,
      detailCount: detailRows.length || visibleConversionRows.value.length,
      totalCustomerHkd,
      deltaFromPreviousHkd: previousVersion
        ? Number((totalCustomerHkd - previousVersion.totalCustomerHkd).toFixed(2))
        : 0,
    }

    exportedQuoteVersions.value = [exportedVersion, ...exportedQuoteVersions.value]
    selectedExportVersionId.value = exportedVersion.id
  } catch (error) {
    exportErrorMessage.value = error instanceof Error ? `导出失败：${error.message}` : '导出失败：报客价 Excel 生成失败'
  } finally {
    isExportingCustomerQuote.value = false
  }
}
</script>

<template>
  <div class="space-y-5">
    <SectionPanel
      title="导入内部报价"
      subtitle="右上角先点选客户，再把内部报价 Excel 导入到当前客户名下"
    >
      <template #action>
        <div class="flex flex-wrap items-center justify-end gap-2">
          <button
            v-for="customer in visibleCustomers"
            :key="customer.id"
            type="button"
            :data-testid="`customer-tab-${customer.id}`"
            :aria-pressed="selectedCustomerId === customer.id"
            class="inline-flex h-9 items-center gap-2 rounded-lg border px-3 text-xs font-semibold transition-colors"
            :class="selectedCustomerId === customer.id
              ? 'border-teal-300 bg-teal-50 text-teal-800 shadow-[0_8px_20px_rgba(13,148,136,0.10)]'
              : 'border-slate-200 bg-white text-slate-600 hover:border-teal-200 hover:text-slate-950'"
            @click="selectedCustomerId = customer.id"
          >
            <Users class="size-4" aria-hidden="true" />
            {{ customer.name }}
            <span class="rounded-full bg-white px-2 py-0.5 text-[11px] text-slate-500 ring-1 ring-slate-200">
              {{ customer.activeQuoteCount }} 单
            </span>
          </button>

          <button
            v-if="canExportCustomerQuote"
            type="button"
            class="inline-flex h-9 items-center gap-2 rounded-lg bg-slate-950 px-3 text-xs font-semibold text-white shadow-[0_10px_26px_rgba(15,23,42,0.16)] transition-colors hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
            :disabled="isExportingCustomerQuote"
            @click="exportCustomerQuoteExcel"
          >
            <Download class="size-4" aria-hidden="true" />
            {{ isExportingCustomerQuote ? '正在输出...' : '输出报客价 Excel' }}
          </button>
        </div>
      </template>

      <div
        v-if="selectedCustomer.id === 'caixing'"
        class="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
      >
        <div>
          <p class="text-xs font-semibold uppercase tracking-wide text-teal-700">彩星产品类型</p>
          <p class="mt-1 text-sm text-slate-600">{{ selectedCaixingProductTypeOption.detail }}</p>
        </div>
        <div class="inline-flex w-full rounded-lg border border-teal-200 bg-white p-1 sm:w-auto">
          <button
            v-for="option in caixingProductTypeOptions"
            :key="option.id"
            type="button"
            class="h-9 flex-1 rounded-md px-4 text-sm font-semibold transition-colors sm:w-24"
            :class="selectedCaixingProductType === option.id
              ? 'bg-teal-600 text-white shadow-[0_8px_18px_rgba(13,148,136,0.18)]'
              : 'text-slate-600 hover:bg-slate-50 hover:text-slate-950'"
            @click="selectedCaixingProductType = option.id"
          >
            {{ option.label }}
          </button>
        </div>
      </div>

      <div class="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <label
          class="flex min-h-[118px] flex-col items-center justify-center rounded-lg border px-6 py-5 text-center transition-colors"
          :class="!canImportSelectedCustomer
            ? 'cursor-not-allowed border-dashed border-slate-300 bg-slate-50 text-slate-500'
            : hasSelectedCustomerImport
              ? 'cursor-pointer border-emerald-800 bg-emerald-900 text-white shadow-[0_16px_32px_rgba(6,78,59,0.22)] hover:bg-emerald-800'
              : isImportDragActive
                ? 'cursor-pointer border-dashed border-teal-500 bg-teal-50 shadow-[0_16px_34px_rgba(13,148,136,0.16)]'
                : 'cursor-pointer border-dashed border-teal-300 bg-[linear-gradient(135deg,#ffffff,#f0fdfa)] shadow-[0_12px_26px_rgba(13,148,136,0.07)] hover:border-teal-500'"
          :aria-disabled="!canImportSelectedCustomer"
          @dragenter.prevent="handleInternalQuoteDragEnter"
          @dragover.prevent="handleInternalQuoteDragOver"
          @dragleave.prevent="handleInternalQuoteDragLeave"
          @drop.prevent="handleInternalQuoteDrop"
        >
          <span
            class="flex size-11 items-center justify-center rounded-xl shadow-[0_8px_18px_rgba(13,148,136,0.12)] ring-1 transition-colors"
            :class="!canImportSelectedCustomer
              ? 'bg-white text-slate-500 ring-slate-200'
              : hasSelectedCustomerImport
                ? 'bg-white/15 text-white ring-white/20'
                : isImportDragActive
                  ? 'bg-teal-600 text-white ring-teal-200'
                  : 'bg-white text-teal-700 ring-teal-100'"
          >
            <Eye v-if="!canImportSelectedCustomer" class="size-5" aria-hidden="true" />
            <CheckCircle2 v-else-if="hasSelectedCustomerImport" class="size-5" aria-hidden="true" />
            <UploadCloud v-else class="size-5" aria-hidden="true" />
          </span>
          <span
            class="mt-3 text-base font-semibold"
            :class="canImportSelectedCustomer && hasSelectedCustomerImport ? 'text-white' : 'text-slate-950'"
          >
            {{ !canImportSelectedCustomer ? '当前账号不可导入' : hasSelectedCustomerImport ? '已导入内部报价' : isImportDragActive ? '松开导入内部报价' : '导入内部报价 Excel' }}
          </span>
          <span
            class="mt-1 text-sm leading-6"
            :class="canImportSelectedCustomer && hasSelectedCustomerImport ? 'text-emerald-50' : 'text-slate-500'"
          >
            {{ !canImportSelectedCustomer
              ? '当前账号没有导入内部报价权限。'
              : hasSelectedCustomerImport
              ? `${selectedCustomer.name}：${selectedImportFileName}，点击可替换文件。`
              : isImportDragActive
                ? `当前客户：${selectedCustomer.name}。文件会导入到此客户名下。`
                : `当前客户：${selectedCustomer.name}。导入后会锁定客户并生成下方明细对比。`
            }}
          </span>
          <span
            class="mt-2 rounded-full px-3 py-1 text-xs font-medium ring-1"
            :class="!canImportSelectedCustomer
              ? 'bg-white text-slate-500 ring-slate-200'
              : hasSelectedCustomerImport
                ? 'bg-white/15 text-white ring-white/20'
                : isImportDragActive
                  ? 'bg-white text-teal-700 ring-teal-200'
                  : 'bg-white text-slate-500 ring-slate-200'"
          >
            {{ !canImportSelectedCustomer ? '权限限制：不可导入或替换' : hasSelectedCustomerImport ? '已就绪，可输出报客价' : isImportDragActive ? '松开鼠标导入 Excel' : '支持 .xls / .xlsx' }}
          </span>
            <input
              data-testid="quote-import-input"
              class="sr-only"
              type="file"
              accept=".xls,.xlsx,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              :disabled="!canImportSelectedCustomer"
              @change="handleInternalQuoteImport"
            >
        </label>

        <aside class="grid gap-2 sm:grid-cols-2 xl:grid-cols-2">
          <article class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">导入状态</p>
            <p class="mt-2 truncate text-sm font-semibold text-slate-950">
              {{ selectedImportFileName || '尚未导入内部报价表' }}
            </p>
            <p class="mt-1 truncate text-xs text-slate-500">{{ selectedImportFileDetail }}</p>
          </article>

          <article
            v-for="metric in importOverviewMetrics"
            :key="metric.label"
            class="rounded-lg border border-slate-200 bg-white px-4 py-3"
          >
            <p class="text-xs font-medium text-slate-500">{{ metric.label }}</p>
            <p class="mt-2 text-lg font-semibold text-slate-950">{{ metric.value }}</p>
            <p class="mt-1 truncate text-xs text-slate-500">{{ metric.detail }}</p>
          </article>
        </aside>

        <p
          v-if="exportErrorMessage"
          class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700 xl:col-span-2"
        >
          {{ exportErrorMessage }}
        </p>
      </div>
    </SectionPanel>

    <SectionPanel
      title="明细对比区"
      subtitle="下方整块区域用于承接 Sheet、报客价版本、明细价格差异和利润带对比"
    >
      <template #action>
        <label class="relative block min-w-0 lg:w-72">
          <Search class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
          <input
            v-model="detailSearchQuery"
            type="search"
            class="h-10 w-full rounded-lg border border-slate-200 bg-white pl-9 pr-3 text-sm text-slate-800 outline-none transition-colors placeholder:text-slate-400 focus:border-teal-400"
            placeholder="搜索 Sheet、项目或编号"
          >
        </label>
      </template>

      <div class="rounded-lg border border-slate-200 bg-white p-4">
        <div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h3 class="text-base font-semibold text-slate-950">多 Sheet / 多报客价明细对比区</h3>
            <p class="mt-1 text-sm text-slate-500">
              上传一个多 Sheet 内部报价表后，导出的每一份报客价都会沉淀为一个版本，方便逐项对比。
            </p>
          </div>
          <div class="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:w-[560px]">
            <div
              v-for="metric in comparisonMetrics"
              :key="metric.label"
              class="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2"
            >
              <p class="text-[11px] text-slate-500">{{ metric.label }}</p>
              <p class="mt-1 truncate text-sm font-semibold text-slate-950">{{ metric.value }}</p>
              <p class="mt-1 truncate text-[11px] text-slate-500">{{ metric.detail }}</p>
            </div>
          </div>
        </div>

        <div v-if="activeWorkbookSheets.length > 0" class="mt-5 grid gap-4 xl:grid-cols-[280px_1fr]">
          <div class="space-y-4">
            <div>
              <p class="text-xs font-semibold uppercase text-slate-500">工作簿 Sheet</p>
              <div class="mt-3 space-y-2">
                <button
                  type="button"
                  class="flex w-full items-center justify-between gap-3 rounded-lg border px-3 py-3 text-left text-sm transition-colors"
                  :class="selectedSheetId === 'all'
                    ? 'border-teal-300 bg-teal-50 text-teal-800'
                    : 'border-slate-200 bg-white text-slate-700 hover:border-teal-200'"
                  @click="selectedSheetId = 'all'"
                >
                  <span class="font-semibold">全部 Sheet</span>
                  <span class="rounded-full bg-white px-2 py-0.5 text-xs text-slate-500">{{ activeWorkbookDetailRows.length }} 条</span>
                </button>
                <button
                  v-for="sheet in activeWorkbookSheets"
                  :key="sheet.id"
                  type="button"
                  class="flex w-full items-center justify-between gap-3 rounded-lg border px-3 py-3 text-left text-sm transition-colors"
                  :class="selectedSheetId === sheet.id
                    ? 'border-teal-300 bg-teal-50 text-teal-800'
                    : 'border-slate-200 bg-white text-slate-700 hover:border-teal-200'"
                  @click="selectedSheetId = sheet.id"
                >
                  <span>
                    <span class="block font-semibold">{{ sheet.name }}</span>
                    <span class="mt-1 block text-xs text-slate-500">{{ sheet.sourceFileName }}</span>
                  </span>
                  <span class="rounded-full bg-white px-2 py-0.5 text-xs text-slate-500">{{ sheet.rowCount }} 条</span>
                </button>
              </div>
            </div>

            <div>
              <p class="text-xs font-semibold uppercase text-slate-500">导出版本</p>
              <div class="mt-3 space-y-2">
                <button
                  v-for="version in activeExportedVersions"
                  :key="version.id"
                  type="button"
                  class="w-full rounded-lg border px-3 py-3 text-left text-sm transition-colors"
                  :class="selectedExportVersionId === version.id
                    ? 'border-teal-300 bg-teal-50'
                    : 'border-slate-200 bg-white hover:border-teal-200'"
                  @click="selectedExportVersionId = version.id"
                >
                  <div class="flex items-start justify-between gap-3">
                    <span>
                      <span class="block font-semibold text-slate-950">{{ version.fileName }}</span>
                      <span class="mt-1 block text-xs text-slate-500">{{ version.createdAt }} · {{ version.detailCount }} 条</span>
                    </span>
                    <span
                      class="rounded-full px-2 py-0.5 text-xs ring-1"
                      :class="version.deltaFromPreviousHkd === 0
                        ? 'bg-slate-50 text-slate-500 ring-slate-200'
                        : version.deltaFromPreviousHkd > 0
                          ? 'bg-amber-50 text-amber-700 ring-amber-200'
                          : 'bg-blue-50 text-blue-700 ring-blue-200'"
                    >
                      {{ formatSignedHkd(version.deltaFromPreviousHkd) }}
                    </span>
                  </div>
                </button>
                <div v-if="activeExportedVersions.length === 0" class="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-3 py-4 text-sm text-slate-500">
                  输出报客价 Excel 后，这里会显示多个导出版本。
                </div>
              </div>
            </div>
          </div>

          <div class="overflow-hidden rounded-lg border border-slate-200">
            <div class="overflow-x-auto">
              <table class="min-w-[940px] w-full text-left text-sm">
                <thead class="bg-slate-50 text-xs font-semibold uppercase text-slate-500">
                  <tr>
                    <th class="px-4 py-3">Sheet</th>
                    <th class="px-4 py-3">项目编号</th>
                    <th class="px-4 py-3">项目名称</th>
                    <th class="px-4 py-3">内部价</th>
                    <th class="px-4 py-3">报客价</th>
                    <th class="px-4 py-3">上一版</th>
                    <th class="px-4 py-3">差异</th>
                    <th class="px-4 py-3">利润带</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-200 bg-white">
                  <tr
                    v-for="row in selectedSheetRows"
                    :key="row.id"
                    class="align-top"
                  >
                    <td class="px-4 py-4 font-medium text-slate-900">{{ row.sheetName }}</td>
                    <td class="px-4 py-4 text-slate-700">{{ row.itemNo }}</td>
                    <td class="px-4 py-4 text-slate-700">{{ row.description }}</td>
                    <td class="px-4 py-4 font-medium text-slate-950">{{ formatHkd(row.internalPriceHkd) }}</td>
                    <td class="px-4 py-4 font-semibold text-slate-950">{{ formatHkd(row.customerPriceHkd) }}</td>
                    <td class="px-4 py-4 text-slate-600">{{ formatHkd(row.previousCustomerPriceHkd) }}</td>
                    <td class="px-4 py-4">
                      <span
                        class="inline-flex rounded-full px-2.5 py-1 text-xs font-medium ring-1"
                        :class="compareStatusClass(row.compareStatus)"
                      >
                        {{ row.compareStatus }} {{ formatSignedHkd(row.differenceHkd) }}
                      </span>
                    </td>
                    <td class="px-4 py-4 text-slate-700">{{ row.marginBand }}</td>
                  </tr>
                  <tr v-if="selectedSheetRows.length === 0">
                    <td colspan="8" class="px-4 py-10 text-center text-sm text-slate-500">
                      当前筛选下暂无明细。
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div v-else class="mt-5 rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-10 text-center">
          <p class="text-sm font-semibold text-slate-800">等待导入多 Sheet 内部报价 Excel</p>
          <p class="mt-2 text-sm text-slate-500">
            导入后会在这里展示每个 Sheet、每次输出的报客价版本，以及明细价格差异。
          </p>
        </div>
      </div>
    </SectionPanel>
  </div>
</template>
