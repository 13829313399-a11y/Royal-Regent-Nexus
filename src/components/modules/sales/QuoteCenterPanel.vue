<script setup lang="ts">
import { CheckCircle2, Download, KeyRound, Search, ShieldCheck, UploadCloud, Users } from '@lucide/vue'
import { computed, ref } from 'vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import { useAuthStore } from '@/stores/auth'

type ConversionStatus = '待转换' | '待复核' | '已生成'
type DetailCompareStatus = '上调' | '下调' | '持平'

interface CustomerPriceConversionRow {
  id: string
  customerId: string
  customer: string
  workshop: string
  account: string
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
  workshop: string
  account: string
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
  createdAt: string
  sheetCount: number
  detailCount: number
  totalCustomerHkd: number
  deltaFromPreviousHkd: number
}

const currentAccount = '车间业务-A01'
const authStore = useAuthStore()

const customerOptions: CustomerOption[] = [
  {
    id: 'buzzbee',
    name: 'BuzzBee',
    workshop: '啤机车间 A',
    account: 'huaxing_molding_a_sales',
    owner: '李业务',
    activeQuoteCount: 1,
  },
  {
    id: 'target',
    name: 'Target',
    workshop: '啤机车间 A',
    account: 'huaxing_molding_a_sales',
    owner: '李业务',
    activeQuoteCount: 1,
  },
]

const selectedCustomerId = ref(customerOptions[0]?.id ?? '')
const detailSearchQuery = ref('')
const importedCustomerId = ref('')
const importedFileName = ref('')
const importedFileSize = ref('')
const importedAt = ref('')
const selectedSheetId = ref('all')
const selectedExportVersionId = ref('')
const importedWorkbookSheets = ref<ImportedWorkbookSheet[]>([])
const exportedQuoteVersions = ref<ExportedQuoteVersion[]>([])

const conversionRows = ref<CustomerPriceConversionRow[]>([
  {
    id: 'QTC-HKA-260707-018',
    customerId: 'buzzbee',
    customer: 'BuzzBee',
    workshop: '啤机车间 A',
    account: 'huaxing_molding_a_sales',
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
    customerId: 'target',
    customer: 'Target',
    workshop: '啤机车间 A',
    account: 'huaxing_molding_a_sales',
    internalPriceHkd: 8.42,
    customerPriceHkd: 10.2,
    marginBand: '21.1%',
    status: '待复核',
    quoteNo: 'CQ-HKA-260707-006',
    sourceFileName: 'Target-内部报价-260707.xlsx',
    updatedAt: '今天 10:15',
  },
  {
    id: 'QTC-HKB-260707-011',
    customerId: 'zuru',
    customer: 'Zuru',
    workshop: '啤机车间 B',
    account: '车间业务-B01',
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
    account: '车间业务-P01',
    internalPriceHkd: 4.35,
    customerPriceHkd: 5.2,
    marginBand: '19.5%',
    status: '已生成',
    quoteNo: 'CQ-HD-260707-002',
    sourceFileName: 'Spin-Master-内部报价-260706.xlsx',
    updatedAt: '昨天 15:20',
  },
])

const currentUsername = computed(() => authStore.currentUser?.username ?? currentAccount)

const isWorkshopSalesAccount = computed(() => {
  return authStore.roles.includes('车间业务跟客')
})

const allowedCustomerIds = computed(() => {
  if (isWorkshopSalesAccount.value) {
    return customerOptions
      .filter((customer) => customer.account === currentUsername.value)
      .map((customer) => customer.id)
  }

  return customerOptions.map((customer) => customer.id)
})

const ownCustomers = computed(() => {
  return customerOptions.filter((customer) => allowedCustomerIds.value.includes(customer.id))
})

const selectedCustomer = computed<CustomerOption>(() => {
  return ownCustomers.value.find((customer) => customer.id === selectedCustomerId.value)
    ?? (ownCustomers.value[0] as CustomerOption)
    ?? (customerOptions[0] as CustomerOption)
})

const visibleConversionRows = computed(() => {
  return conversionRows.value.filter((row) => {
    const inScope = row.customerId === selectedCustomer.value.id && allowedCustomerIds.value.includes(row.customerId)
    const canAccessAccount = isWorkshopSalesAccount.value
      ? row.account === currentUsername.value
      : true

    return inScope && canAccessAccount
  })
})

const existingSelectedSourceFileName = computed(() => {
  return visibleConversionRows.value.find((row) => row.sourceFileName !== '待导入')?.sourceFileName ?? ''
})

const selectedImportFileName = computed(() => {
  if (importedCustomerId.value === selectedCustomer.value.id && importedFileName.value) {
    return importedFileName.value
  }

  return existingSelectedSourceFileName.value
})

const selectedImportFileDetail = computed(() => {
  if (!selectedImportFileName.value) {
    return '导入后会锁定到当前选择客户'
  }

  if (importedCustomerId.value === selectedCustomer.value.id) {
    return `${importedFileSize.value} · ${importedAt.value}`
  }

  return '已有内部报价来源'
})

const activeWorkbookSheets = computed(() => {
  return importedCustomerId.value === selectedCustomer.value.id ? importedWorkbookSheets.value : []
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
  return exportedQuoteVersions.value.filter((version) => version.customerId === selectedCustomer.value.id)
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
  return visibleConversionRows.value.length > 0 && Boolean(selectedImportFileName.value)
})

const conversionMetrics = computed(() => {
  const selectedRows = visibleConversionRows.value
  const readyRows = selectedRows.filter((row) => row.status !== '已生成')

  return [
    { label: '我的客户', value: String(ownCustomers.value.length), detail: '仅显示本人绑定客户' },
    { label: '已导入内部报价', value: selectedImportFileName.value ? '1' : '0', detail: selectedImportFileName.value || '等待 Excel' },
    { label: '可输出报客价', value: String(readyRows.length), detail: selectedCustomer.value.name },
  ]
})

const permissionRules = [
  {
    title: '账号范围',
    detail: '车间业务员只看到本人车间绑定客户',
    icon: Users,
  },
  {
    title: '转换动作',
    detail: '仅本人车间客户可转换并输出报客价',
    icon: KeyRound,
  },
  {
    title: '主管复核',
    detail: '跨车间查看和复核交给业务经理权限',
    icon: ShieldCheck,
  },
]

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

function createMockWorkbookSheets(customer: CustomerOption, sourceFileName: string): ImportedWorkbookSheet[] {
  const customerPrefix = customer.id === 'target' ? 'TGT' : 'BB'
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
  const canAccessAccount = isWorkshopSalesAccount.value
    ? row.account === currentUsername.value
    : true

  return canAccessAccount
    && allowedCustomerIds.value.includes(row.customerId)
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

function handleInternalQuoteImport(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]

  if (!file || !selectedCustomer.value) {
    return
  }

  importedFileName.value = file.name
  importedFileSize.value = formatFileSize(file.size)
  importedCustomerId.value = selectedCustomer.value.id
  importedAt.value = '刚刚'

  conversionRows.value = conversionRows.value.map((row) => {
    if (row.customerId !== selectedCustomer.value.id || !allowedCustomerIds.value.includes(row.customerId)) {
      return row
    }

    return {
      ...row,
      status: row.status === '已生成' ? '待复核' : '待转换',
      quoteNo: row.quoteNo === '待生成' ? '待生成' : row.quoteNo,
      sourceFileName: file.name,
      updatedAt: '刚刚',
    }
  })

  importedWorkbookSheets.value = createMockWorkbookSheets(selectedCustomer.value, file.name)
  selectedSheetId.value = 'all'
  selectedExportVersionId.value = ''

  input.value = ''
}

function escapeExcelCell(value: string | number) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function exportCustomerQuoteExcel() {
  if (!selectedCustomer.value || !canExportCustomerQuote.value) {
    return
  }

  visibleConversionRows.value.forEach((row) => {
    if (row.status !== '已生成') {
      generateCustomerQuote(row.id)
    }
  })

  const detailRows = activeWorkbookDetailRows.value
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

  const blob = new Blob([workbookHtml], { type: 'application/vnd.ms-excel;charset=utf-8' })
  const url = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  const date = new Date().toISOString().slice(0, 10).replace(/-/g, '')
  const versionNumber = activeExportedVersions.value.length + 1
  const fileName = `${selectedCustomer.value.name}-报客价-V${versionNumber}-${date}.xls`

  anchor.href = url
  anchor.download = fileName
  anchor.click()
  window.URL.revokeObjectURL(url)

  const totalCustomerHkd = detailRows.length > 0
    ? Number(detailRows.reduce((sum, row) => sum + row.customerPriceHkd, 0).toFixed(2))
    : Number(visibleConversionRows.value.reduce((sum, row) => sum + row.customerPriceHkd, 0).toFixed(2))
  const previousVersion = activeExportedVersions.value[0]
  const exportedVersion: ExportedQuoteVersion = {
    id: `EXP-${selectedCustomer.value.id}-${Date.now()}`,
    fileName,
    customerId: selectedCustomer.value.id,
    customerName: selectedCustomer.value.name,
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
}
</script>

<template>
  <div class="space-y-6">
    <SectionPanel
      title="客价转换台"
      subtitle="内部价转报客价，按车间客户权限管控"
    >
      <template #action>
        <div class="hidden items-center gap-2 rounded-lg border border-teal-200 bg-teal-50 px-3 py-2 text-xs font-medium text-teal-700 sm:inline-flex">
          <CheckCircle2 class="size-4" aria-hidden="true" />
          选择客户 · 导入内部报价 · 输出报客价
        </div>
      </template>

      <div class="grid gap-4 md:grid-cols-3">
        <article
          v-for="metric in conversionMetrics"
          :key="metric.label"
          class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-4"
        >
          <p class="text-xs font-medium text-slate-500">{{ metric.label }}</p>
          <div class="mt-3 flex items-end justify-between gap-3">
            <p class="text-2xl font-semibold text-slate-950">{{ metric.value }}</p>
            <p class="text-right text-xs text-slate-500">{{ metric.detail }}</p>
          </div>
        </article>
      </div>

      <div class="mt-5 grid gap-3 lg:grid-cols-3">
        <article
          v-for="rule in permissionRules"
          :key="rule.title"
          class="rounded-lg border border-slate-200 bg-white px-4 py-4"
        >
          <div class="flex items-start gap-3">
            <span class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-700">
              <component :is="rule.icon" class="size-4" aria-hidden="true" />
            </span>
            <div>
              <h3 class="text-sm font-semibold text-slate-950">{{ rule.title }}</h3>
              <p class="mt-1 text-xs leading-5 text-slate-500">{{ rule.detail }}</p>
            </div>
          </div>
        </article>
      </div>
    </SectionPanel>

    <SectionPanel
      title="内部价转客价"
      subtitle="先选择本人客户，再导入内部报价 Excel，最后输出报客价 Excel"
    >
      <template #action>
        <button
          type="button"
          class="inline-flex h-9 items-center gap-2 rounded-lg bg-slate-950 px-3 text-xs font-semibold text-white transition-colors hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
          :disabled="!canExportCustomerQuote"
          @click="exportCustomerQuoteExcel"
        >
          <Download class="size-4" aria-hidden="true" />
          输出报客价 Excel
        </button>
      </template>

      <div class="grid gap-4 lg:grid-cols-3">
        <div class="rounded-lg border border-slate-200 bg-slate-50 p-4">
          <div class="flex items-center gap-2 text-sm font-semibold text-slate-950">
            <Users class="size-4 text-teal-700" aria-hidden="true" />
            1. 选择自己的客户
          </div>
          <div class="mt-4 grid gap-3 sm:grid-cols-2">
            <button
              v-for="customer in ownCustomers"
              :key="customer.id"
              type="button"
              class="rounded-lg border px-4 py-3 text-left transition-colors"
              :class="selectedCustomerId === customer.id
                ? 'border-teal-300 bg-white shadow-[0_8px_24px_rgba(13,148,136,0.10)]'
                : 'border-slate-200 bg-white hover:border-teal-200'"
              @click="selectedCustomerId = customer.id"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <p class="font-semibold text-slate-950">{{ customer.name }}</p>
                  <p class="mt-1 text-xs text-slate-500">{{ customer.workshop }} · {{ customer.owner }}</p>
                </div>
                <span class="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-600">
                  {{ customer.activeQuoteCount }} 单
                </span>
              </div>
            </button>
          </div>
        </div>

        <div class="rounded-lg border border-slate-200 bg-slate-50 p-4">
          <div class="flex items-center gap-2 text-sm font-semibold text-slate-950">
            <UploadCloud class="size-4 text-teal-700" aria-hidden="true" />
            2. 导入内部报价 Excel
          </div>
          <label class="mt-4 flex min-h-32 cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 bg-white px-4 py-5 text-center transition-colors hover:border-teal-300">
            <UploadCloud class="size-6 text-slate-400" aria-hidden="true" />
            <span class="mt-3 text-sm font-semibold text-slate-800">导入内部报价 Excel</span>
            <span class="mt-1 text-xs text-slate-500">支持 .xls / .xlsx</span>
            <input
              class="sr-only"
              type="file"
              accept=".xls,.xlsx,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              @change="handleInternalQuoteImport"
            >
          </label>
          <div class="mt-3 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600">
            <p class="font-medium text-slate-800">{{ selectedImportFileName || '尚未导入内部报价表' }}</p>
            <p class="mt-1">{{ selectedImportFileDetail }}</p>
          </div>
        </div>

        <div class="rounded-lg border border-slate-200 bg-slate-50 p-4">
          <div class="flex items-center gap-2 text-sm font-semibold text-slate-950">
            <Download class="size-4 text-teal-700" aria-hidden="true" />
            3. 输出报客价 Excel
          </div>
          <div class="mt-4 rounded-lg border border-slate-200 bg-white px-4 py-4">
            <p class="text-xs font-medium text-slate-500">当前输出客户</p>
            <p class="mt-2 text-lg font-semibold text-slate-950">{{ selectedCustomer.name }}</p>
            <p class="mt-1 text-xs text-slate-500">
              {{ canExportCustomerQuote ? '内部报价已就绪，可输出报客价表' : '请先导入当前客户的内部报价 Excel' }}
            </p>
          </div>
          <button
            type="button"
            class="mt-4 inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-slate-950 px-4 text-sm font-semibold text-white transition-colors hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
            :disabled="!canExportCustomerQuote"
            @click="exportCustomerQuoteExcel"
          >
            <Download class="size-4" aria-hidden="true" />
            输出报客价 Excel
          </button>
        </div>
      </div>

      <div class="mt-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div class="flex flex-wrap items-center gap-2 text-sm text-slate-600">
          <span class="inline-flex items-center gap-2 rounded-lg bg-teal-50 px-3 py-2 text-teal-700">
            当前客户：{{ selectedCustomer.name }}
          </span>
        </div>

        <label class="relative block min-w-0 lg:w-72">
          <Search class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
          <input
            v-model="detailSearchQuery"
            type="search"
            class="h-10 w-full rounded-lg border border-slate-200 bg-white pl-9 pr-3 text-sm text-slate-800 outline-none transition-colors placeholder:text-slate-400 focus:border-teal-400"
            placeholder="搜索 Sheet、项目或编号"
          >
        </label>
      </div>

      <div class="mt-5 rounded-lg border border-slate-200 bg-white p-4">
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

      <div class="mt-4 rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-3 text-xs leading-5 text-slate-600">
        权限口径：车间业务账号进来后只选择本人绑定客户；导入内部报价 Excel 后，只能输出该客户的报客价 Excel。业务经理和管理员后续可拥有跨车间查看、复核和客户分配权限。
      </div>
    </SectionPanel>
  </div>
</template>
