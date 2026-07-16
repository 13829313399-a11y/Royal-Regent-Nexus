<script setup lang="ts">
import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  Clock3,
  Download,
  FileSpreadsheet,
  FileText,
  Layers3,
  LoaderCircle,
  Paperclip,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  Send,
  ShieldCheck,
  Trash2,
  Upload,
  X,
} from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'
import { internalQuoteApi } from '@/api/internalQuote'
import { getApiErrorMessage } from '@/lib/http'
import { calculateInternalQuoteSection } from '@/lib/internalQuoteCalculator'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import type {
  InternalQuoteAttachment,
  InternalQuoteCostLine,
  InternalQuoteCreateInput,
  InternalQuoteDepartment,
  InternalQuoteDetail,
  InternalQuoteExportFile,
  InternalQuoteImportPreview,
  InternalQuoteImportType,
  InternalQuoteSectionPayload,
  InternalQuoteSectionStatus,
  InternalQuoteStatus,
  InternalQuoteSummary,
  InternalQuoteWorkshop,
} from '@/types/internalQuote'

interface EditorColumn {
  key: string
  label: string
  type?: 'number' | 'select' | 'text'
  step?: string
  options?: Array<{ value: string; label: string }>
}

interface ParameterField {
  key: string
  label: string
  suffix: string
}

const genericColumns: EditorColumn[] = [
  { key: 'quantity', label: '数量', type: 'number', step: '0.01' },
  { key: 'unitPriceHkd', label: '单价 HKD', type: 'number', step: '0.0001' },
]

const departmentColumns: Record<InternalQuoteDepartment, EditorColumn[]> = {
  sales: genericColumns,
  engineering: [
    { key: 'fields.mode', label: '计价方式', type: 'select', options: [{ value: 'mold', label: '模具摊销' }, { value: 'direct', label: '直接计价' }] },
    ...genericColumns,
    { key: 'fields.mold_price_rmb', label: '模具总价 RMB', type: 'number', step: '0.01' },
    { key: 'fields.amortization_qty', label: '摊销数量', type: 'number', step: '1' },
  ],
  electronic: [
    { key: 'quantity', label: '数量', type: 'number', step: '0.01' },
    { key: 'fields.unit_price_rmb', label: '零件单价 RMB', type: 'number', step: '0.0001' },
  ],
  molding: [
    { key: 'fields.mode', label: '工艺', type: 'select', options: [{ value: 'injection', label: '注塑' }, { value: 'blow', label: '吹气' }] },
    { key: 'fields.material', label: '材质' },
    { key: 'fields.material_grade', label: '料型' },
    { key: 'fields.weight_g', label: '克重 g', type: 'number', step: '0.01' },
    { key: 'fields.loss_pct', label: '料损 %', type: 'number', step: '0.1' },
    { key: 'fields.material_price_hkd_lb', label: '料价 HK$/Lb', type: 'number', step: '0.01' },
    { key: 'fields.machine_model', label: '机型' },
    { key: 'fields.shot_price_hkd', label: '啤价 HKD', type: 'number', step: '0.0001' },
    { key: 'fields.sets', label: '模数', type: 'number', step: '1' },
    { key: 'fields.target', label: '台班目标', type: 'number', step: '1' },
    { key: 'fields.blow_labor_hkd', label: '吹气人工', type: 'number', step: '0.0001' },
    { key: 'fields.flash_hkd', label: '水口费', type: 'number', step: '0.0001' },
    { key: 'fields.profit_multiplier', label: '利润倍数', type: 'number', step: '0.01' },
  ],
  painting: genericColumns,
  slush: genericColumns,
  sewing: [
    { key: 'fields.usage', label: '用量', type: 'number', step: '0.0001' },
    { key: 'fields.material_price_hkd', label: '材料单价 HKD', type: 'number', step: '0.0001' },
    { key: 'fields.markup', label: '加成倍数', type: 'number', step: '0.01' },
  ],
  assembly: [
    { key: 'fields.mode', label: '计价方式', type: 'select', options: [{ value: 'process', label: '工序人工' }, { value: 'direct', label: '直接计价' }] },
    ...genericColumns,
    { key: 'fields.base_rate_hkd', label: '台班基准', type: 'number', step: '0.01' },
    { key: 'fields.people_count', label: '工序人数', type: 'number', step: '0.01' },
    { key: 'fields.team_count', label: '组数', type: 'number', step: '0.01' },
    { key: 'fields.production_qty', label: '每组产量', type: 'number', step: '0.01' },
  ],
}

const parameterFields: Partial<Record<InternalQuoteDepartment, ParameterField[]>> = {
  electronic: [
    { key: 'bonding_cost_rmb', label: '邦定费', suffix: 'RMB' },
    { key: 'smt_cost_rmb', label: 'SMT费', suffix: 'RMB' },
    { key: 'labor_cost_rmb', label: '人工费', suffix: 'RMB' },
    { key: 'test_repair_rmb', label: '测试维修', suffix: 'RMB' },
    { key: 'packing_shipping_rmb', label: '包装运输', suffix: 'RMB' },
    { key: 'profit_pct', label: '利润', suffix: '%' },
    { key: 'tax_diff_rmb', label: '税差', suffix: 'RMB' },
  ],
  sewing: [{ key: 'labor_hkd', label: '额外人工', suffix: 'HKD（明细含“人工”时不重复计）' }],
}

const importTypeByDepartment: Partial<Record<InternalQuoteDepartment, InternalQuoteImportType>> = {
  engineering: 'mold',
  electronic: 'electronic',
  painting: 'painting',
  sewing: 'sewing',
  assembly: 'assembly',
}

const importTypeLabels: Record<InternalQuoteImportType, string> = {
  mold: '模具报价表',
  electronic: '电子报价表',
  painting: '喷油报价表',
  sewing: '车缝报价表',
  assembly: '装配报价表',
}

const appStore = useAppStore()
const authStore = useAuthStore()

const workshops = ref<InternalQuoteWorkshop[]>([])
const quotes = ref<InternalQuoteSummary[]>([])
const selectedQuote = ref<InternalQuoteDetail | null>(null)
const importBatches = ref<InternalQuoteImportPreview[]>([])
const importPreview = ref<InternalQuoteImportPreview | null>(null)
const attachments = ref<InternalQuoteAttachment[]>([])
const exportFiles = ref<InternalQuoteExportFile[]>([])
const selectedQuoteId = ref('')
const activeDepartment = ref<InternalQuoteDepartment>('sales')
const editingPayload = ref<InternalQuoteSectionPayload>(emptyPayload())
const workshopFilter = ref('')
const statusFilter = ref('')
const keyword = ref('')
const isLoading = ref(false)
const isDetailLoading = ref(false)
const isSaving = ref(false)
const isExporting = ref(false)
const isImporting = ref(false)
const isUploadingAttachment = ref(false)
const showCreateDialog = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const reviewComment = ref('')
const createDraft = ref<InternalQuoteCreateInput>(createEmptyDraft('huaxing'))

const factoryId = computed(() => appStore.activeProductionFactory.id)
const factoryName = computed(() => appStore.activeProductionFactory.name)
const canCreate = computed(() => authStore.can('internal_pricing:create', factoryId.value, 'sales-business'))
const canEdit = computed(() => authStore.can('internal_pricing:edit', factoryId.value, 'sales-business'))
const canReview = computed(() => authStore.can('internal_pricing:review', factoryId.value, 'sales-business'))
const canExport = computed(() => authStore.can('internal_pricing:export', factoryId.value, 'sales-business'))
const selectedSection = computed(() => selectedQuote.value?.sections.find(
  (section) => section.department === activeDepartment.value,
) ?? null)
const pendingReviewCount = computed(() => quotes.value.filter((quote) =>
  quote.status === 'drafting' || quote.status === 'reopened',
).length)
const completedCount = computed(() => quotes.value.filter((quote) =>
  quote.status === 'fully_approved' || quote.status === 'exported',
).length)
const activeColumns = computed(() => departmentColumns[activeDepartment.value])
const activeParameterFields = computed(() => parameterFields[activeDepartment.value] ?? [])
const activeImportType = computed(() => importTypeByDepartment[activeDepartment.value] ?? null)
const activeImportLabel = computed(() => activeImportType.value ? importTypeLabels[activeImportType.value] : '')
const latestDepartmentImport = computed(() => importBatches.value.find(
  (batch) => batch.targetDepartment === activeDepartment.value,
) ?? null)
const localCalculation = computed(() => calculateInternalQuoteSection(activeDepartment.value, editingPayload.value))
const localSubtotal = computed(() => localCalculation.value.subtotalHkd)
const localLossAmount = computed(() => localCalculation.value.lossAmountHkd)
const localTotal = computed(() => localCalculation.value.totalHkd)
const fxSnapshot = computed(() => {
  const fx = editingPayload.value.referenceSnapshot?.fx
  return fx && typeof fx === 'object' && !Array.isArray(fx) ? fx as Record<string, unknown> : {}
})
const sectionEditable = computed(() => Boolean(
  canEdit.value
  && selectedSection.value
  && !['approved', 'pending_review'].includes(selectedSection.value.status),
))

const quoteStatusMeta: Record<InternalQuoteStatus, { label: string; tone: string }> = {
  drafting: { label: '分段填报中', tone: 'amber' },
  fully_approved: { label: '全部已通过', tone: 'green' },
  exported: { label: '已受控导出', tone: 'teal' },
  reopened: { label: '已重开', tone: 'red' },
  archived: { label: '已归档', tone: 'slate' },
}

const sectionStatusMeta: Record<InternalQuoteSectionStatus, { label: string; tone: string }> = {
  draft: { label: '草稿', tone: 'slate' },
  pending_review: { label: '待审核', tone: 'amber' },
  approved: { label: '已通过', tone: 'green' },
  rejected: { label: '已退回', tone: 'red' },
}

const auditActionLabels: Record<string, string> = {
  create: '创建报价单',
  save_draft: '保存分段草稿',
  submit: '提交分段审核',
  approve: '审核通过',
  reject: '审核退回',
  reopen: '重开分段',
  export: '导出报价明细',
  import_preview: '生成 Excel 导入预览',
  import_confirm: '确认合并 Excel 数据',
  attachment_upload: '上传报价附件',
  download_export: '下载受控导出文件',
}

function emptyPayload(): InternalQuoteSectionPayload {
  return { currency: 'HKD', lossPct: 0, parameters: {}, referenceSnapshot: {}, rows: [] }
}

function createEmptyDraft(factory = 'huaxing'): InternalQuoteCreateInput {
  return {
    factoryId: factory,
    workshopCode: '',
    quoteNo: '',
    productName: '',
    customer: '',
    qty: 10000,
    versionLabel: 'V1',
  }
}

function clonePayload(payload: InternalQuoteSectionPayload): InternalQuoteSectionPayload {
  return JSON.parse(JSON.stringify(payload)) as InternalQuoteSectionPayload
}

function makeLine(): InternalQuoteCostLine {
  return {
    id: `line-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    category: '',
    itemName: '',
    specification: '',
    quantity: 1,
    unitPriceHkd: 0,
    amountHkd: 0,
    note: '',
    fields: defaultLineFields(activeDepartment.value),
  }
}

function defaultLineFields(department: InternalQuoteDepartment): Record<string, unknown> {
  if (department === 'engineering') return { mode: 'direct', mold_price_rmb: 0, amortization_qty: 1 }
  if (department === 'electronic') return { unit_price_rmb: 0 }
  if (department === 'molding') return {
    mode: 'injection', material: '', material_grade: '', weight_g: 0, loss_pct: 3,
    material_price_hkd_lb: 0, machine_model: '', shot_price_hkd: 0, sets: 1, target: 1,
    blow_labor_hkd: 0, flash_hkd: 0, profit_multiplier: 1,
  }
  if (department === 'painting' || department === 'slush') return { mode: 'operation' }
  if (department === 'sewing') return { usage: 0, material_price_hkd: 0, markup: 1 }
  if (department === 'assembly') return { mode: 'process', base_rate_hkd: 310, people_count: 0, team_count: 1, production_qty: 1 }
  return {}
}

function getLineField(row: InternalQuoteCostLine, key: string): unknown {
  if (key.startsWith('fields.')) return row.fields?.[key.slice(7)] ?? ''
  return row[key as keyof InternalQuoteCostLine] ?? ''
}

function updateLineField(row: InternalQuoteCostLine, column: EditorColumn, event: Event) {
  const target = event.target as HTMLInputElement | HTMLSelectElement
  const value: string | number = column.type === 'number' ? Number(target.value) || 0 : target.value
  if (column.key.startsWith('fields.')) {
    row.fields ??= {}
    row.fields[column.key.slice(7)] = value
  } else {
    ;(row as unknown as Record<string, unknown>)[column.key] = value
  }
}

function linePreviewAmount(row: InternalQuoteCostLine) {
  return localCalculation.value.lineBreakdown.find((item) => item.lineId === row.id)?.amountHkd ?? 0
}

function formatMoney(value: number) {
  return new Intl.NumberFormat('zh-HK', {
    style: 'currency',
    currency: 'HKD',
    minimumFractionDigits: 2,
  }).format(Number(value) || 0)
}

function formatDate(value: string) {
  if (!value) return '—'
  const normalized = value.includes('T') ? value : value.replace(' ', 'T')
  const date = new Date(normalized)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

function formatFileSize(value: number) {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

function departmentName(department: string) {
  return selectedQuote.value?.sections.find((section) => section.department === department)?.departmentName
    ?? department
}

function downloadBlob(blob: Blob, fileName: string) {
  const url = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.URL.revokeObjectURL(url)
}

function quoteProgress(quote: InternalQuoteSummary) {
  return quote.totalSections ? Math.round(quote.approvedCount / quote.totalSections * 100) : 0
}

function clearMessages() {
  errorMessage.value = ''
  successMessage.value = ''
}

async function loadWorkspace(preferredQuoteId = selectedQuoteId.value) {
  isLoading.value = true
  clearMessages()
  try {
    const [nextWorkshops, nextQuotes] = await Promise.all([
      internalQuoteApi.listWorkshops(factoryId.value),
      internalQuoteApi.listQuotes(factoryId.value, {
        workshopCode: workshopFilter.value || undefined,
        status: statusFilter.value || undefined,
        keyword: keyword.value.trim() || undefined,
      }),
    ])
    workshops.value = nextWorkshops
    quotes.value = nextQuotes
    if (!createDraft.value.workshopCode || !nextWorkshops.some((item) => item.code === createDraft.value.workshopCode)) {
      createDraft.value.workshopCode = nextWorkshops[0]?.code ?? ''
    }
    const nextId = nextQuotes.some((quote) => quote.id === preferredQuoteId)
      ? preferredQuoteId
      : nextQuotes[0]?.id ?? ''
    selectedQuoteId.value = nextId
    if (nextId) await loadQuote(nextId)
    else {
      selectedQuote.value = null
      importBatches.value = []
      importPreview.value = null
      attachments.value = []
      exportFiles.value = []
    }
  } catch (error) {
    workshops.value = []
    quotes.value = []
    selectedQuote.value = null
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isLoading.value = false
  }
}

async function loadQuote(quoteId: string) {
  if (!quoteId) return
  isDetailLoading.value = true
  clearMessages()
  try {
    const detail = await internalQuoteApi.getQuote(quoteId)
    const [nextImports, nextAttachments, nextExports] = await Promise.allSettled([
      internalQuoteApi.listImports(quoteId),
      internalQuoteApi.listAttachments(quoteId),
      canExport.value ? internalQuoteApi.listExports(quoteId) : Promise.resolve([]),
    ])
    selectedQuote.value = detail
    importBatches.value = nextImports.status === 'fulfilled' ? nextImports.value : []
    attachments.value = nextAttachments.status === 'fulfilled' ? nextAttachments.value : []
    exportFiles.value = nextExports.status === 'fulfilled' ? nextExports.value : []
    selectedQuoteId.value = quoteId
    const matchingSection = selectedQuote.value.sections.find((section) => section.department === activeDepartment.value)
      ?? selectedQuote.value.sections[0]
    if (matchingSection) {
      activeDepartment.value = matchingSection.department
      editingPayload.value = clonePayload(matchingSection.payload)
      importPreview.value = importBatches.value.find((batch) => (
        batch.targetDepartment === matchingSection.department && batch.status === 'previewed'
      )) ?? null
    }

    const artifactFailures: Array<{ label: string; reason: unknown }> = []
    if (nextImports.status === 'rejected') artifactFailures.push({ label: 'Excel 导入记录', reason: nextImports.reason })
    if (nextAttachments.status === 'rejected') artifactFailures.push({ label: '报价附件', reason: nextAttachments.reason })
    if (nextExports.status === 'rejected') artifactFailures.push({ label: '受控导出历史', reason: nextExports.reason })
    if (artifactFailures.length) {
      errorMessage.value = `报价详情已加载，但${artifactFailures.map((item) => item.label).join('、')}读取失败：${getApiErrorMessage(artifactFailures[0].reason)}`
    }
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isDetailLoading.value = false
  }
}

function selectDepartment(department: InternalQuoteDepartment) {
  activeDepartment.value = department
  const section = selectedQuote.value?.sections.find((item) => item.department === department)
  editingPayload.value = section ? clonePayload(section.payload) : emptyPayload()
  importPreview.value = importBatches.value.find((batch) => (
    batch.targetDepartment === department && batch.status === 'previewed'
  )) ?? null
  reviewComment.value = ''
  clearMessages()
}

function openCreateDialog() {
  createDraft.value = {
    ...createEmptyDraft(factoryId.value),
    workshopCode: workshopFilter.value || workshops.value[0]?.code || '',
  }
  showCreateDialog.value = true
  clearMessages()
}

async function createQuote() {
  if (!canCreate.value || !createDraft.value.workshopCode) return
  isSaving.value = true
  clearMessages()
  try {
    const created = await internalQuoteApi.createQuote({
      ...createDraft.value,
      factoryId: factoryId.value,
      qty: Number(createDraft.value.qty) || 0,
    })
    showCreateDialog.value = false
    workshopFilter.value = created.workshopCode
    successMessage.value = `${created.quoteNo} 已建立，并生成 8 个部门分段`
    await loadWorkspace(created.id)
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isSaving.value = false
  }
}

function addRow() {
  editingPayload.value.rows.push(makeLine())
}

function removeRow(index: number) {
  editingPayload.value.rows.splice(index, 1)
}

async function saveSection(submit: boolean) {
  if (!selectedQuote.value || !selectedSection.value || !sectionEditable.value) return
  isSaving.value = true
  clearMessages()
  try {
    const updated = await internalQuoteApi.updateSection(
      selectedQuote.value.id,
      selectedSection.value.department,
      selectedSection.value.revision,
      editingPayload.value,
      submit,
    )
    selectedQuote.value = updated
    editingPayload.value = clonePayload(
      updated.sections.find((section) => section.department === activeDepartment.value)?.payload ?? emptyPayload(),
    )
    successMessage.value = submit ? '分段已提交主管审核' : '分段草稿已保存'
    await refreshQuoteSummary(updated)
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isSaving.value = false
  }
}

async function reviewSection(action: 'approve' | 'reject' | 'reopen') {
  if (!selectedQuote.value || !selectedSection.value || !canReview.value) return
  if ((action === 'reject' || action === 'reopen') && !reviewComment.value.trim()) {
    errorMessage.value = '退回或重开必须填写原因'
    return
  }
  isSaving.value = true
  clearMessages()
  try {
    const updated = await internalQuoteApi.reviewSection(
      selectedQuote.value.id,
      selectedSection.value.department,
      { action, comment: reviewComment.value.trim() },
    )
    selectedQuote.value = updated
    editingPayload.value = clonePayload(
      updated.sections.find((section) => section.department === activeDepartment.value)?.payload ?? emptyPayload(),
    )
    reviewComment.value = ''
    successMessage.value = action === 'approve' ? '分段审核通过' : action === 'reject' ? '分段已退回修改' : '分段已重开'
    await refreshQuoteSummary(updated)
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isSaving.value = false
  }
}

async function previewExcelImport(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  const quote = selectedQuote.value
  const importType = activeImportType.value
  if (!file || !quote || !importType || !sectionEditable.value) return
  isImporting.value = true
  clearMessages()
  try {
    const preview = await internalQuoteApi.previewImport(quote.id, importType, file)
    importPreview.value = preview
    importBatches.value = [preview, ...importBatches.value.filter((batch) => batch.batchId !== preview.batchId)]
    successMessage.value = `已解析 ${preview.rows.length} 行，请核对后选择追加或替换`
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    input.value = ''
    isImporting.value = false
  }
}

async function confirmExcelImport(mode: 'append' | 'replace') {
  const quote = selectedQuote.value
  const section = selectedSection.value
  const preview = importPreview.value
  if (!quote || !section || !preview || !sectionEditable.value) return
  isImporting.value = true
  clearMessages()
  try {
    const updated = await internalQuoteApi.confirmImport(
      quote.id,
      preview.batchId,
      section.revision,
      mode,
    )
    selectedQuote.value = updated
    editingPayload.value = clonePayload(
      updated.sections.find((item) => item.department === activeDepartment.value)?.payload ?? emptyPayload(),
    )
    importBatches.value = await internalQuoteApi.listImports(quote.id)
    importPreview.value = null
    successMessage.value = mode === 'replace'
      ? `已用 ${preview.sourceFileName} 替换当前分段`
      : `已把 ${preview.sourceFileName} 追加到当前分段`
    await refreshQuoteSummary(updated)
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isImporting.value = false
  }
}

async function uploadAttachment(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  const quote = selectedQuote.value
  if (!file || !quote || !canEdit.value) return
  isUploadingAttachment.value = true
  clearMessages()
  try {
    const attachment = await internalQuoteApi.uploadAttachment(quote.id, activeDepartment.value, file)
    attachments.value = [attachment, ...attachments.value]
    successMessage.value = `${attachment.fileName} 已归档到${departmentName(attachment.department)}`
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    input.value = ''
    isUploadingAttachment.value = false
  }
}

async function downloadAttachment(attachment: InternalQuoteAttachment) {
  if (!selectedQuote.value) return
  clearMessages()
  try {
    const blob = await internalQuoteApi.downloadAttachment(selectedQuote.value.id, attachment.id)
    downloadBlob(blob, attachment.fileName)
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  }
}

async function downloadRetainedExport(file: InternalQuoteExportFile) {
  if (!selectedQuote.value || !canExport.value) return
  clearMessages()
  try {
    const blob = await internalQuoteApi.downloadRetainedExport(selectedQuote.value.id, file.id)
    downloadBlob(blob, file.fileName)
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  }
}

async function refreshQuoteSummary(detail: InternalQuoteDetail) {
  const nextQuotes = await internalQuoteApi.listQuotes(factoryId.value, {
    workshopCode: workshopFilter.value || undefined,
    status: statusFilter.value || undefined,
    keyword: keyword.value.trim() || undefined,
  })
  quotes.value = nextQuotes
  selectedQuoteId.value = detail.id
}

async function exportQuote() {
  if (!selectedQuote.value || !canExport.value) return
  isExporting.value = true
  clearMessages()
  try {
    const quote = selectedQuote.value
    const blob = await internalQuoteApi.exportQuote(quote.id)
    downloadBlob(blob, `${quote.quoteNo}_${quote.workshopName}_内部报价明细.xlsx`)
    successMessage.value = '内部报价明细已受控导出'
    await loadQuote(quote.id)
    await refreshQuoteSummary(selectedQuote.value as InternalQuoteDetail)
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isExporting.value = false
  }
}

watch(factoryId, () => {
  workshopFilter.value = ''
  statusFilter.value = ''
  keyword.value = ''
  createDraft.value = createEmptyDraft(factoryId.value)
  void loadWorkspace('')
})

watch([workshopFilter, statusFilter], () => {
  void loadWorkspace('')
})

onMounted(() => {
  void loadWorkspace()
})
</script>

<template>
  <section class="quote-workspace">
    <header class="quote-command-bar">
      <div>
        <p class="eyebrow"><Layers3 class="size-4" /> 八部门协同核价</p>
        <h2>内部报价明细工作台</h2>
        <p>所有报价按厂区和车间独立管理；业务建立单据后，由八个责任分段填写、提交和审核。</p>
      </div>
      <div class="command-actions">
        <span class="factory-chip"><Building2 class="size-4" />{{ factoryName }}</span>
        <button type="button" class="primary-button" :disabled="!canCreate" @click="openCreateDialog">
          <Plus class="size-4" /> 新建内部报价
        </button>
      </div>
    </header>

    <div v-if="errorMessage" class="feedback error"><AlertTriangle class="size-4" />{{ errorMessage }}</div>
    <div v-if="successMessage" class="feedback success"><CheckCircle2 class="size-4" />{{ successMessage }}</div>

    <div class="metric-grid">
      <article><span>当前车间</span><strong>{{ workshopFilter ? workshops.find((item) => item.code === workshopFilter)?.name : '全部' }}</strong><small>厂区内独立归集</small></article>
      <article><span>报价单</span><strong>{{ quotes.length }}</strong><small>当前筛选结果</small></article>
      <article><span>填报 / 重开</span><strong>{{ pendingReviewCount }}</strong><small>仍需推进的报价</small></article>
      <article><span>已通过 / 导出</span><strong>{{ completedCount }}</strong><small>八段全部完成</small></article>
    </div>

    <div class="filter-bar">
      <div class="workshop-switcher" aria-label="内部报价车间筛选">
        <button type="button" :class="{ active: !workshopFilter }" @click="workshopFilter = ''">全部车间</button>
        <button
          v-for="workshop in workshops"
          :key="workshop.code"
          type="button"
          :class="{ active: workshopFilter === workshop.code }"
          @click="workshopFilter = workshop.code"
        >
          {{ workshop.name }}
        </button>
      </div>
      <label class="search-field">
        <Search class="size-4" />
        <input v-model="keyword" type="search" placeholder="搜索报价单、客户或产品" @keyup.enter="loadWorkspace('')" />
      </label>
      <select v-model="statusFilter" aria-label="报价状态筛选">
        <option value="">全部状态</option>
        <option value="drafting">分段填报中</option>
        <option value="reopened">已重开</option>
        <option value="fully_approved">全部已通过</option>
        <option value="exported">已受控导出</option>
      </select>
      <button type="button" class="icon-button" aria-label="刷新报价列表" @click="loadWorkspace()"><RefreshCw class="size-4" /></button>
    </div>

    <div v-if="isLoading" class="loading-state"><LoaderCircle class="size-6 animate-spin" /> 正在读取车间报价…</div>

    <div v-else-if="!quotes.length" class="empty-state">
      <FileText class="size-10" />
      <h3>当前车间还没有内部报价</h3>
      <p>新建报价后，系统会自动生成八个部门分段并进入填报流程。</p>
      <button v-if="canCreate" type="button" class="primary-button" @click="openCreateDialog"><Plus class="size-4" /> 新建第一张报价</button>
    </div>

    <div v-else class="workspace-grid">
      <aside class="quote-list-panel">
        <div class="panel-title"><span>报价单列表</span><small>{{ quotes.length }} 张</small></div>
        <button
          v-for="quote in quotes"
          :key="quote.id"
          type="button"
          class="quote-card"
          :class="{ selected: selectedQuoteId === quote.id }"
          @click="loadQuote(quote.id)"
        >
          <div class="quote-card-top">
            <span class="workshop-badge">{{ quote.workshopName }}</span>
            <span class="status-pill" :data-tone="quoteStatusMeta[quote.status].tone">{{ quoteStatusMeta[quote.status].label }}</span>
          </div>
          <strong>{{ quote.quoteNo }}</strong>
          <p>{{ quote.productName }}</p>
          <div class="quote-meta"><span>{{ quote.customer }}</span><span>{{ quote.versionLabel }}</span></div>
          <div class="progress-track"><span :style="{ width: `${quoteProgress(quote)}%` }" /></div>
          <div class="quote-progress"><span>{{ quote.approvedCount }}/{{ quote.totalSections }} 分段通过</span><span>{{ formatMoney(quote.totalHkd) }}</span></div>
        </button>
      </aside>

      <main class="quote-detail-panel">
        <div v-if="isDetailLoading" class="loading-state compact"><LoaderCircle class="size-5 animate-spin" /> 正在读取报价详情…</div>
        <template v-else-if="selectedQuote">
          <header class="detail-header">
            <div>
              <div class="detail-kicker">
                <span class="workshop-badge">{{ selectedQuote.workshopName }}</span>
                <span class="status-pill" :data-tone="quoteStatusMeta[selectedQuote.status].tone">{{ quoteStatusMeta[selectedQuote.status].label }}</span>
              </div>
              <h3>{{ selectedQuote.quoteNo }} · {{ selectedQuote.productName }}</h3>
              <p>{{ selectedQuote.customer }} · {{ selectedQuote.qty.toLocaleString() }} PCS · {{ selectedQuote.versionLabel }} · 创建人 {{ selectedQuote.createdByName }}</p>
            </div>
            <div class="detail-total">
              <span>八分段成本合计</span>
              <strong>{{ formatMoney(selectedQuote.totalHkd) }}</strong>
              <button
                type="button"
                class="export-button"
                :disabled="!canExport || !['fully_approved', 'exported'].includes(selectedQuote.status) || isExporting"
                @click="exportQuote"
              >
                <LoaderCircle v-if="isExporting" class="size-4 animate-spin" />
                <Download v-else class="size-4" />
                {{ isExporting ? '生成中…' : '导出 XLSX' }}
              </button>
            </div>
          </header>

          <div class="section-tabs">
            <button
              v-for="section in selectedQuote.sections"
              :key="section.id"
              type="button"
              :class="{ active: activeDepartment === section.department }"
              @click="selectDepartment(section.department)"
            >
              <span>{{ section.departmentName }}</span>
              <small class="status-pill" :data-tone="sectionStatusMeta[section.status].tone">{{ sectionStatusMeta[section.status].label }}</small>
              <b>{{ formatMoney(section.calculation.totalHkd) }}</b>
            </button>
          </div>

          <section v-if="selectedSection" class="section-editor">
            <header class="editor-head">
              <div>
                <p class="eyebrow"><CircleDollarSign class="size-4" /> {{ selectedSection.departmentName }}成本分段</p>
                <h4>{{ sectionStatusMeta[selectedSection.status].label }} · 修订 {{ selectedSection.revision }}</h4>
                <p>金额按部门专用公式实时预览，并由服务器按同一公式复算；提交后进入主管审核。</p>
              </div>
              <div class="section-owner">
                <span>最近填写</span>
                <strong>{{ selectedSection.filledBy || '尚未填写' }}</strong>
                <small>{{ formatDate(selectedSection.filledAt) }}</small>
              </div>
            </header>

            <div v-if="selectedSection.status === 'rejected'" class="review-note rejected">
              <AlertTriangle class="size-4" />
              <div><strong>主管已退回</strong><span>{{ selectedSection.reviewComment || '请修订后重新提交' }}</span></div>
            </div>
            <div v-else-if="selectedSection.status === 'approved'" class="review-note approved">
              <ShieldCheck class="size-4" />
              <div><strong>{{ selectedSection.reviewedBy }} 已审核通过</strong><span>{{ formatDate(selectedSection.reviewedAt) }}</span></div>
            </div>

            <div class="formula-snapshot">
              <span>公式 {{ selectedSection.calculation.formulaVersion }}</span>
              <span>参考版本 {{ String(editingPayload.referenceSnapshot.version || 'rr2-2026-v1') }}</span>
              <span>RMB/HKD {{ Number(fxSnapshot.rmb_hkd || 0.85) }}</span>
              <span>HKD/USD {{ Number(fxSnapshot.hkd_usd || 7.8) }}</span>
            </div>

            <section v-if="activeImportType" class="import-workbench">
              <header>
                <div>
                  <p><FileSpreadsheet class="size-4" /><strong>{{ activeImportLabel }}导入</strong></p>
                  <span>只生成预览，不会直接改动当前分段；确认时仍校验修订号。</span>
                </div>
                <label class="secondary-button file-button" :class="{ disabled: !sectionEditable || isImporting }">
                  <LoaderCircle v-if="isImporting" class="size-4 animate-spin" />
                  <Upload v-else class="size-4" />
                  {{ isImporting ? '处理中…' : '选择 XLSX 预览' }}
                  <input
                    type="file"
                    accept=".xlsx,.xlsm"
                    :disabled="!sectionEditable || isImporting"
                    @change="previewExcelImport"
                  />
                </label>
              </header>
              <p v-if="latestDepartmentImport && !importPreview" class="latest-import">
                最近导入：{{ latestDepartmentImport.sourceFileName }} ·
                {{ latestDepartmentImport.status === 'confirmed' ? '已确认' : '待确认' }} ·
                {{ formatDate(latestDepartmentImport.createdAt) }}
              </p>
              <article v-if="importPreview" class="import-preview">
                <div class="preview-meta">
                  <div><strong>{{ importPreview.sourceFileName }}</strong><span>{{ importPreview.sheetName }} · 表头第 {{ importPreview.headerRow }} 行 · {{ importPreview.rows.length }} 条</span></div>
                  <code>SHA-256 {{ importPreview.sourceSha256.slice(0, 16) }}…</code>
                </div>
                <div class="preview-table-wrap">
                  <table>
                    <thead><tr><th>#</th><th>类别</th><th>项目</th><th>规格</th><th>数量</th><th>预览单价</th><th>备注</th></tr></thead>
                    <tbody>
                      <tr v-for="(row, index) in importPreview.rows.slice(0, 8)" :key="row.id">
                        <td>{{ index + 1 }}</td><td>{{ row.category || '—' }}</td><td>{{ row.itemName || '—' }}</td><td>{{ row.specification || '—' }}</td><td>{{ row.quantity }}</td><td>{{ row.unitPriceHkd }}</td><td>{{ row.note || '—' }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <p v-if="importPreview.rows.length > 8" class="preview-more">另有 {{ importPreview.rows.length - 8 }} 条将在确认时一并合并。</p>
                <div v-if="importPreview.warnings.length" class="preview-warnings"><AlertTriangle class="size-4" />{{ importPreview.warnings.join('；') }}</div>
                <footer>
                  <button type="button" class="secondary-button" :disabled="isImporting || !sectionEditable" @click="confirmExcelImport('append')">追加到现有明细</button>
                  <button type="button" class="primary-button" :disabled="isImporting || !sectionEditable" @click="confirmExcelImport('replace')">替换当前分段</button>
                </footer>
              </article>
            </section>

            <div v-if="activeParameterFields.length" class="parameter-grid">
              <label v-for="field in activeParameterFields" :key="field.key">
                <span>{{ field.label }}</span>
                <div><input v-model.number="editingPayload.parameters[field.key]" :disabled="!sectionEditable" type="number" min="0" step="0.01" /><small>{{ field.suffix }}</small></div>
              </label>
            </div>

            <div class="cost-table-wrap">
              <table class="cost-table">
                <thead><tr><th>#</th><th>类别</th><th>项目</th><th>规格</th><th v-for="column in activeColumns" :key="column.key">{{ column.label }}</th><th>金额 HKD</th><th>备注</th><th></th></tr></thead>
                <tbody>
                  <tr v-for="(row, index) in editingPayload.rows" :key="row.id">
                    <td>{{ index + 1 }}</td>
                    <td><input v-model="row.category" :disabled="!sectionEditable" aria-label="成本类别" /></td>
                    <td><input v-model="row.itemName" :disabled="!sectionEditable" aria-label="成本项目" /></td>
                    <td><input v-model="row.specification" :disabled="!sectionEditable" aria-label="规格" /></td>
                    <td v-for="column in activeColumns" :key="column.key">
                      <select
                        v-if="column.type === 'select'"
                        :value="String(getLineField(row, column.key))"
                        :disabled="!sectionEditable"
                        :aria-label="column.label"
                        @change="updateLineField(row, column, $event)"
                      >
                        <option v-for="option in column.options" :key="option.value" :value="option.value">{{ option.label }}</option>
                      </select>
                      <input
                        v-else
                        :value="String(getLineField(row, column.key))"
                        :disabled="!sectionEditable"
                        :type="column.type === 'number' ? 'number' : 'text'"
                        :min="column.type === 'number' ? 0 : undefined"
                        :step="column.step"
                        :aria-label="column.label"
                        @input="updateLineField(row, column, $event)"
                      />
                    </td>
                    <td class="amount-cell">{{ formatMoney(linePreviewAmount(row)) }}</td>
                    <td><input v-model="row.note" :disabled="!sectionEditable" aria-label="备注" /></td>
                    <td><button type="button" class="row-delete" :disabled="!sectionEditable" aria-label="删除成本行" @click="removeRow(index)"><Trash2 class="size-4" /></button></td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="editor-summary">
              <button type="button" class="secondary-button" :disabled="!sectionEditable" @click="addRow"><Plus class="size-4" /> 添加成本行</button>
              <label v-if="activeDepartment === 'sales'">分段损耗 <input v-model.number="editingPayload.lossPct" :disabled="!sectionEditable" type="number" min="0" max="100" step="0.1" />%</label>
              <span>小计 <strong>{{ formatMoney(localSubtotal) }}</strong></span>
              <span v-if="localLossAmount">损耗 <strong>{{ formatMoney(localLossAmount) }}</strong></span>
              <span>折合 RMB <strong>¥{{ localCalculation.totalRmb.toFixed(2) }}</strong></span>
              <span>折合 USD <strong>US${{ localCalculation.totalUsd.toFixed(2) }}</strong></span>
              <span class="section-total">分段合计 <strong>{{ formatMoney(localTotal) }}</strong></span>
            </div>

            <div v-if="selectedSection.calculation.warnings.length" class="calculation-warnings">
              <AlertTriangle class="size-4" /> {{ selectedSection.calculation.warnings.join('；') }}
            </div>

            <div class="editor-actions">
              <div v-if="sectionEditable" class="write-actions">
                <button type="button" class="secondary-button" :disabled="isSaving" @click="saveSection(false)"><Save class="size-4" /> 保存草稿</button>
                <button type="button" class="primary-button" :disabled="isSaving" @click="saveSection(true)"><Send class="size-4" /> 提交审核</button>
              </div>
              <p v-else-if="selectedSection.status === 'pending_review'" class="locked-hint"><Clock3 class="size-4" /> 已提交，等待主管审核</p>
              <p v-else-if="!canEdit" class="locked-hint"><ShieldCheck class="size-4" /> 当前账号只有查看权限</p>

              <div v-if="canReview && ['pending_review', 'approved'].includes(selectedSection.status)" class="review-actions">
                <input v-model="reviewComment" type="text" maxlength="500" :placeholder="selectedSection.status === 'approved' ? '填写重开原因（必填）' : '审核意见；退回时必填'" />
                <button v-if="selectedSection.status === 'pending_review'" type="button" class="approve-button" :disabled="isSaving" @click="reviewSection('approve')"><CheckCircle2 class="size-4" /> 通过</button>
                <button v-if="selectedSection.status === 'pending_review'" type="button" class="reject-button" :disabled="isSaving" @click="reviewSection('reject')"><RotateCcw class="size-4" /> 退回</button>
                <button v-if="selectedSection.status === 'approved'" type="button" class="reject-button" :disabled="isSaving" @click="reviewSection('reopen')"><RotateCcw class="size-4" /> 重开</button>
              </div>
            </div>
          </section>

          <section class="artifact-grid">
            <article class="artifact-panel">
              <header>
                <div><Paperclip class="size-4" /><strong>报价附件</strong><span>{{ attachments.length }} 个</span></div>
                <label class="secondary-button file-button" :class="{ disabled: !canEdit || isUploadingAttachment }">
                  <LoaderCircle v-if="isUploadingAttachment" class="size-4 animate-spin" />
                  <Upload v-else class="size-4" />
                  上传到{{ selectedSection?.departmentName }}
                  <input
                    type="file"
                    accept=".xlsx,.xlsm,.pdf,.png,.jpg,.jpeg,.webp,.docx"
                    :disabled="!canEdit || isUploadingAttachment"
                    @change="uploadAttachment"
                  />
                </label>
              </header>
              <p v-if="!attachments.length" class="artifact-empty">暂无附件。可上传 Excel、PDF、Word 或常见图片，单个不超过 10MB。</p>
              <div v-else class="artifact-list">
                <button v-for="attachment in attachments" :key="attachment.id" type="button" @click="downloadAttachment(attachment)">
                  <FileText class="size-4" />
                  <span><strong>{{ attachment.fileName }}</strong><small>{{ departmentName(attachment.department) }} · {{ formatFileSize(attachment.sizeBytes) }} · {{ attachment.uploadedByName }} · {{ formatDate(attachment.uploadedAt) }}</small></span>
                  <code>{{ attachment.sha256.slice(0, 12) }}</code>
                  <Download class="size-4" />
                </button>
              </div>
            </article>

            <article v-if="canExport" class="artifact-panel">
              <header><div><Download class="size-4" /><strong>受控导出历史</strong><span>{{ exportFiles.length }} 份</span></div><small>每份均保留 SHA-256 与分段修订快照</small></header>
              <p v-if="!exportFiles.length" class="artifact-empty">全部分段审核通过并导出后，文件将在此留存。</p>
              <div v-else class="artifact-list">
                <button v-for="file in exportFiles" :key="file.id" type="button" @click="downloadRetainedExport(file)">
                  <FileSpreadsheet class="size-4" />
                  <span><strong>{{ file.fileName }}</strong><small>{{ formatFileSize(file.sizeBytes) }} · {{ file.exportedByName }} · {{ formatDate(file.exportedAt) }}</small></span>
                  <span class="export-state" :data-current="file.status === 'current'">{{ file.status === 'current' ? '当前版' : '历史版' }}</span>
                  <code>{{ file.sha256.slice(0, 12) }}</code>
                  <Download class="size-4" />
                </button>
              </div>
            </article>
          </section>

          <section class="timeline-panel">
            <header><div><Clock3 class="size-4" /><strong>报价操作记录</strong></div><small>完整审计 · 最新在前</small></header>
            <div v-if="!selectedQuote.auditLogs.length" class="timeline-empty">暂无操作记录</div>
            <div v-else class="timeline-list">
              <article v-for="log in selectedQuote.auditLogs.slice(0, 12)" :key="log.id">
                <span class="timeline-dot" />
                <div><strong>{{ auditActionLabels[log.action] || log.action }}</strong><p>{{ log.actorName }}<template v-if="log.department"> · {{ selectedQuote.sections.find((section) => section.department === log.department)?.departmentName || log.department }}</template></p></div>
                <span>{{ log.detail || '—' }}</span>
                <time>{{ formatDate(log.createdAt) }}</time>
              </article>
            </div>
          </section>
        </template>
      </main>
    </div>

    <div v-if="showCreateDialog" class="dialog-backdrop" @click.self="showCreateDialog = false">
      <form class="create-dialog" @submit.prevent="createQuote">
        <header><div><p class="eyebrow"><FileText class="size-4" /> 新建报价</p><h3>建立车间内部报价单</h3><span>保存后自动生成八个部门分段。</span></div><button type="button" aria-label="关闭" @click="showCreateDialog = false"><X class="size-5" /></button></header>
        <div class="create-grid">
          <label><span>所属厂区</span><input :value="factoryName" disabled /></label>
          <label><span>所属车间 *</span><select v-model="createDraft.workshopCode" required><option v-for="workshop in workshops" :key="workshop.code" :value="workshop.code">{{ workshop.name }}</option></select></label>
          <label><span>报价单号 / 货号 *</span><input v-model="createDraft.quoteNo" required maxlength="128" placeholder="例如 47765A" /></label>
          <label><span>版本 *</span><input v-model="createDraft.versionLabel" required maxlength="64" placeholder="V1" /></label>
          <label class="wide"><span>产品名称 *</span><input v-model="createDraft.productName" required maxlength="255" /></label>
          <label><span>客户 *</span><input v-model="createDraft.customer" required maxlength="128" /></label>
          <label><span>报价数量 *</span><input v-model.number="createDraft.qty" required type="number" min="1" step="1" /></label>
        </div>
        <footer><button type="button" class="secondary-button" @click="showCreateDialog = false">取消</button><button type="submit" class="primary-button" :disabled="isSaving"><LoaderCircle v-if="isSaving" class="size-4 animate-spin" /><ChevronRight v-else class="size-4" /> 建立报价并进入分段</button></footer>
      </form>
    </div>
  </section>
</template>

<style scoped>
.quote-workspace { display: grid; gap: 14px; }
.quote-command-bar, .filter-bar, .quote-list-panel, .quote-detail-panel, .metric-grid article, .empty-state { border: 1px solid #dbe5ea; background: rgb(255 255 255 / 92%); box-shadow: 0 14px 30px rgb(15 23 42 / 4%); }
.quote-command-bar { display: flex; align-items: center; justify-content: space-between; gap: 18px; border-radius: 14px; padding: 20px 22px; }
.quote-command-bar h2 { margin: 5px 0 0; font-size: 23px; font-weight: 950; letter-spacing: -.025em; }
.quote-command-bar p:last-child { margin: 7px 0 0; color: #64748b; font-size: 12px; line-height: 1.65; }
.eyebrow { display: flex; align-items: center; gap: 6px; margin: 0; color: #0f766e; font-size: 10px; font-weight: 900; letter-spacing: .12em; text-transform: uppercase; }
.command-actions, .write-actions, .review-actions { display: flex; align-items: center; gap: 9px; }
.factory-chip { display: inline-flex; height: 36px; align-items: center; gap: 7px; border: 1px solid #cbd5e1; border-radius: 9px; padding: 0 12px; color: #475569; font-size: 11px; font-weight: 800; }
.primary-button, .secondary-button, .export-button, .approve-button, .reject-button { display: inline-flex; min-height: 36px; align-items: center; justify-content: center; gap: 7px; border-radius: 9px; padding: 0 13px; font-size: 11px; font-weight: 900; transition: .15s ease; }
.primary-button { border: 1px solid #0f766e; background: #0f766e; color: white; box-shadow: 0 8px 18px rgb(15 118 110 / 18%); }
.primary-button:hover:not(:disabled) { background: #115e59; }
.secondary-button { border: 1px solid #cbd5e1; background: white; color: #334155; }
.secondary-button:hover:not(:disabled) { border-color: #0f766e; color: #0f766e; }
button:disabled { cursor: not-allowed; opacity: .48; }
.feedback { display: flex; align-items: center; gap: 8px; border-radius: 10px; padding: 10px 13px; font-size: 12px; font-weight: 800; }
.feedback.error { border: 1px solid #fecaca; background: #fef2f2; color: #b91c1c; }
.feedback.success { border: 1px solid #a7f3d0; background: #ecfdf5; color: #047857; }
.metric-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
.metric-grid article { border-radius: 12px; padding: 13px 15px; }
.metric-grid span, .metric-grid small { display: block; color: #64748b; font-size: 10px; }
.metric-grid strong { display: block; margin-top: 6px; color: #0f172a; font-size: 20px; }
.metric-grid small { margin-top: 4px; }
.filter-bar { display: flex; align-items: center; gap: 10px; border-radius: 12px; padding: 10px 12px; }
.workshop-switcher { display: flex; flex-wrap: wrap; gap: 6px; }
.workshop-switcher button { height: 32px; border: 1px solid #dbe5ea; border-radius: 8px; background: #f8fafc; padding: 0 11px; color: #64748b; font-size: 11px; font-weight: 800; }
.workshop-switcher button.active { border-color: #14b8a6; background: #f0fdfa; color: #0f766e; box-shadow: inset 0 0 0 1px #99f6e4; }
.search-field { display: flex; min-width: 240px; flex: 1; align-items: center; gap: 7px; border: 1px solid #dbe5ea; border-radius: 8px; padding: 0 10px; color: #94a3b8; }
.search-field input { height: 32px; min-width: 0; flex: 1; border: 0; background: transparent; font-size: 11px; outline: none; }
.filter-bar select, .create-grid select { height: 34px; border: 1px solid #dbe5ea; border-radius: 8px; background: white; padding: 0 9px; color: #334155; font-size: 11px; outline: none; }
.icon-button { display: grid; width: 34px; height: 34px; place-items: center; border: 1px solid #dbe5ea; border-radius: 8px; background: white; color: #64748b; }
.loading-state, .empty-state { display: flex; min-height: 220px; align-items: center; justify-content: center; gap: 10px; border-radius: 14px; color: #64748b; font-size: 12px; }
.loading-state.compact { min-height: 150px; border: 0; box-shadow: none; }
.empty-state { flex-direction: column; text-align: center; }
.empty-state h3 { margin: 3px 0 0; color: #0f172a; font-size: 17px; }
.empty-state p { margin: 0 0 7px; }
.workspace-grid { display: grid; grid-template-columns: 330px minmax(0, 1fr); gap: 12px; align-items: start; }
.quote-list-panel, .quote-detail-panel { min-width: 0; border-radius: 14px; }
.quote-list-panel { display: grid; max-height: calc(100vh - 220px); gap: 8px; overflow-y: auto; padding: 12px; position: sticky; top: 78px; }
.panel-title { display: flex; align-items: center; justify-content: space-between; padding: 3px 4px 7px; }
.panel-title span { font-size: 12px; font-weight: 900; }
.panel-title small { color: #64748b; font-size: 10px; }
.quote-card { width: 100%; border: 1px solid #e2e8f0; border-radius: 11px; background: white; padding: 12px; text-align: left; transition: .15s ease; }
.quote-card:hover { border-color: #99f6e4; transform: translateY(-1px); }
.quote-card.selected { border-color: #14b8a6; background: linear-gradient(135deg, #f0fdfa, white); box-shadow: inset 3px 0 #0f766e, 0 9px 20px rgb(15 118 110 / 8%); }
.quote-card-top, .quote-meta, .quote-progress { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.workshop-badge { display: inline-flex; align-items: center; border: 1px solid #99f6e4; border-radius: 999px; background: #f0fdfa; padding: 4px 8px; color: #0f766e; font-size: 9px; font-weight: 900; }
.status-pill { display: inline-flex; width: fit-content; align-items: center; border-radius: 999px; padding: 3px 7px; font-size: 9px; font-weight: 900; }
.status-pill[data-tone="green"] { background: #dcfce7; color: #15803d; }
.status-pill[data-tone="amber"] { background: #fef3c7; color: #b45309; }
.status-pill[data-tone="red"] { background: #fee2e2; color: #b91c1c; }
.status-pill[data-tone="teal"] { background: #ccfbf1; color: #0f766e; }
.status-pill[data-tone="slate"] { background: #f1f5f9; color: #475569; }
.quote-card > strong { display: block; margin-top: 10px; color: #0f172a; font-size: 13px; }
.quote-card > p { margin: 4px 0 9px; overflow: hidden; color: #475569; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.quote-meta, .quote-progress { color: #64748b; font-size: 9px; }
.progress-track { height: 4px; margin: 9px 0 6px; overflow: hidden; border-radius: 999px; background: #e2e8f0; }
.progress-track span { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, #0f766e, #2dd4bf); }
.quote-detail-panel { overflow: hidden; }
.detail-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; border-bottom: 1px solid #e2e8f0; padding: 18px 20px; }
.detail-kicker { display: flex; align-items: center; gap: 7px; }
.detail-header h3 { margin: 10px 0 0; font-size: 20px; font-weight: 950; }
.detail-header p { margin: 6px 0 0; color: #64748b; font-size: 10px; }
.detail-total { min-width: 190px; text-align: right; }
.detail-total > span { display: block; color: #64748b; font-size: 10px; }
.detail-total > strong { display: block; margin: 5px 0 9px; color: #0f766e; font-size: 22px; }
.export-button { margin-left: auto; border: 1px solid #0f766e; background: #f0fdfa; color: #0f766e; }
.section-tabs { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 7px; border-bottom: 1px solid #e2e8f0; background: #f8fafc; padding: 10px 12px; }
.section-tabs button { display: grid; grid-template-columns: 1fr auto; gap: 5px 7px; border: 1px solid #e2e8f0; border-radius: 9px; background: white; padding: 9px 10px; text-align: left; }
.section-tabs button.active { border-color: #14b8a6; background: #f0fdfa; box-shadow: inset 0 0 0 1px #99f6e4; }
.section-tabs button > span { font-size: 11px; font-weight: 900; }
.section-tabs button > b { grid-column: 1 / -1; color: #475569; font-size: 10px; }
.section-editor { padding: 18px 20px; }
.editor-head { display: flex; justify-content: space-between; gap: 16px; }
.editor-head h4 { margin: 7px 0 0; color: #0f172a; font-size: 16px; }
.editor-head > div:first-child > p:last-child { margin: 5px 0 0; color: #64748b; font-size: 10px; }
.section-owner { min-width: 150px; border-left: 1px solid #e2e8f0; padding-left: 15px; }
.section-owner span, .section-owner small { display: block; color: #64748b; font-size: 9px; }
.section-owner strong { display: block; margin: 5px 0; font-size: 11px; }
.review-note { display: flex; align-items: flex-start; gap: 8px; margin-top: 13px; border-radius: 9px; padding: 10px 12px; }
.review-note.rejected { border: 1px solid #fecaca; background: #fef2f2; color: #b91c1c; }
.review-note.approved { border: 1px solid #a7f3d0; background: #ecfdf5; color: #047857; }
.review-note strong, .review-note span { display: block; font-size: 10px; }
.review-note span { margin-top: 2px; font-weight: 600; }
.formula-snapshot { display: flex; flex-wrap: wrap; gap: 6px 12px; margin-top: 12px; border: 1px solid #ccfbf1; border-radius: 8px; background: #f0fdfa; padding: 8px 10px; color: #0f766e; font-size: 9px; font-weight: 800; }
.file-button { cursor: pointer; }
.file-button.disabled { cursor: not-allowed; opacity: .48; }
.file-button input { display: none; }
.import-workbench { margin-top: 12px; border: 1px solid #bae6fd; border-radius: 10px; background: #f8fdff; padding: 11px 12px; }
.import-workbench > header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.import-workbench > header p { display: flex; align-items: center; gap: 6px; margin: 0; color: #0369a1; font-size: 11px; }
.import-workbench > header span { display: block; margin-top: 3px; color: #64748b; font-size: 9px; }
.latest-import { margin: 9px 0 0; color: #64748b; font-size: 9px; }
.import-preview { margin-top: 10px; border-top: 1px solid #dbeafe; padding-top: 10px; }
.preview-meta { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.preview-meta strong, .preview-meta span { display: block; font-size: 10px; }
.preview-meta span { margin-top: 3px; color: #64748b; }
.preview-meta code, .artifact-list code { color: #64748b; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 8px; }
.preview-table-wrap { margin-top: 8px; overflow-x: auto; border: 1px solid #dbe5ea; border-radius: 8px; background: white; }
.preview-table-wrap table { width: 100%; min-width: 680px; border-collapse: collapse; font-size: 9px; }
.preview-table-wrap th { background: #f1f5f9; padding: 7px; color: #64748b; text-align: left; }
.preview-table-wrap td { border-top: 1px solid #eef2f7; padding: 7px; color: #334155; }
.preview-more { margin: 6px 0 0; color: #64748b; font-size: 9px; }
.preview-warnings { display: flex; align-items: flex-start; gap: 6px; margin-top: 7px; color: #c2410c; font-size: 9px; }
.import-preview footer { display: flex; justify-content: flex-end; gap: 8px; margin-top: 9px; }
.parameter-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px; margin-top: 12px; }
.parameter-grid label { display: grid; gap: 4px; color: #475569; font-size: 9px; font-weight: 800; }
.parameter-grid label > div { display: flex; align-items: center; gap: 6px; }
.parameter-grid input { width: 100%; height: 32px; border: 1px solid #cbd5e1; border-radius: 7px; padding: 0 7px; color: #0f172a; outline: none; }
.parameter-grid small { color: #94a3b8; font-size: 8px; white-space: nowrap; }
.cost-table-wrap { margin-top: 14px; overflow-x: auto; border: 1px solid #e2e8f0; border-radius: 10px; }
.cost-table { width: 100%; min-width: 1120px; border-collapse: collapse; font-size: 10px; }
.cost-table th { background: #f8fafc; padding: 9px 7px; color: #64748b; font-weight: 900; text-align: left; }
.cost-table td { border-top: 1px solid #e2e8f0; padding: 5px; color: #334155; }
.cost-table input, .cost-table select { width: 100%; min-width: 88px; height: 31px; border: 1px solid transparent; border-radius: 6px; background: transparent; padding: 0 6px; color: #0f172a; font-size: 10px; outline: none; }
.cost-table input:not(:disabled):hover, .cost-table input:not(:disabled):focus, .cost-table select:not(:disabled):hover, .cost-table select:not(:disabled):focus { border-color: #99f6e4; background: #f0fdfa; }
.cost-table input:disabled, .cost-table select:disabled { color: #475569; }
.amount-cell { min-width: 100px; font-weight: 800; white-space: nowrap; }
.row-delete { display: grid; width: 29px; height: 29px; place-items: center; border: 0; border-radius: 6px; background: transparent; color: #94a3b8; }
.row-delete:hover:not(:disabled) { background: #fef2f2; color: #dc2626; }
.editor-summary { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 10px 16px; margin-top: 12px; border: 1px solid #dbe5ea; border-radius: 10px; background: #f8fafc; padding: 10px 12px; color: #64748b; font-size: 10px; }
.editor-summary .secondary-button { margin-right: auto; }
.editor-summary label { display: flex; align-items: center; gap: 5px; }
.editor-summary input { width: 62px; height: 29px; border: 1px solid #cbd5e1; border-radius: 6px; padding: 0 5px; text-align: right; }
.editor-summary strong { color: #0f172a; }
.editor-summary .section-total { border-left: 1px solid #cbd5e1; padding-left: 15px; color: #0f766e; }
.editor-summary .section-total strong { color: #0f766e; font-size: 13px; }
.calculation-warnings { display: flex; align-items: flex-start; gap: 6px; margin-top: 8px; border: 1px solid #fed7aa; border-radius: 8px; background: #fff7ed; padding: 8px 10px; color: #c2410c; font-size: 9px; }
.editor-actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px; margin-top: 12px; }
.locked-hint { display: flex; align-items: center; gap: 6px; margin: 0; color: #64748b; font-size: 10px; }
.review-actions { min-width: min(100%, 520px); margin-left: auto; }
.review-actions input { height: 36px; min-width: 190px; flex: 1; border: 1px solid #cbd5e1; border-radius: 8px; padding: 0 10px; font-size: 10px; outline: none; }
.approve-button { border: 1px solid #16a34a; background: #16a34a; color: white; }
.reject-button { border: 1px solid #fca5a5; background: #fff1f2; color: #be123c; }
.artifact-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; border-top: 1px solid #e2e8f0; padding: 16px 20px; }
.artifact-panel { min-width: 0; border: 1px solid #dbe5ea; border-radius: 10px; background: #f8fafc; padding: 11px; }
.artifact-panel > header { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.artifact-panel > header > div { display: flex; align-items: center; gap: 6px; color: #0f172a; font-size: 10px; }
.artifact-panel > header > div > span, .artifact-panel > header > small { color: #64748b; font-size: 8px; }
.artifact-panel .secondary-button { min-height: 30px; padding: 0 9px; font-size: 9px; }
.artifact-empty { margin: 10px 0 0; color: #94a3b8; font-size: 9px; }
.artifact-list { display: grid; gap: 6px; margin-top: 9px; }
.artifact-list button { display: grid; grid-template-columns: auto minmax(0, 1fr) auto auto auto; align-items: center; gap: 7px; width: 100%; border: 1px solid #e2e8f0; border-radius: 8px; background: white; padding: 8px; color: #64748b; text-align: left; }
.artifact-list button:hover { border-color: #99f6e4; background: #f0fdfa; color: #0f766e; }
.artifact-list button > span:first-of-type { min-width: 0; }
.artifact-list strong, .artifact-list small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.artifact-list strong { color: #334155; font-size: 9px; }
.artifact-list small { margin-top: 3px; color: #94a3b8; font-size: 8px; }
.export-state { border-radius: 999px; background: #e2e8f0; padding: 3px 6px; color: #64748b; font-size: 8px; font-weight: 900; white-space: nowrap; }
.export-state[data-current="true"] { background: #ccfbf1; color: #0f766e; }
.timeline-panel { border-top: 1px solid #e2e8f0; padding: 16px 20px 20px; }
.timeline-panel > header, .timeline-panel > header > div { display: flex; align-items: center; justify-content: space-between; gap: 7px; }
.timeline-panel > header strong { font-size: 11px; }
.timeline-panel > header small { color: #64748b; font-size: 9px; }
.timeline-list { display: grid; gap: 0; margin-top: 11px; }
.timeline-list article { display: grid; grid-template-columns: 10px minmax(150px, .8fr) minmax(180px, 1fr) auto; align-items: center; gap: 9px; border-top: 1px solid #f1f5f9; padding: 9px 0; }
.timeline-dot { width: 7px; height: 7px; border-radius: 999px; background: #14b8a6; box-shadow: 0 0 0 3px #ccfbf1; }
.timeline-list strong, .timeline-list p, .timeline-list > article > span, .timeline-list time { margin: 0; font-size: 9px; }
.timeline-list p, .timeline-list > article > span, .timeline-list time { color: #64748b; }
.timeline-empty { margin-top: 10px; color: #94a3b8; font-size: 10px; }
.dialog-backdrop { position: fixed; inset: 0; z-index: 80; display: grid; place-items: center; background: rgb(15 23 42 / 48%); padding: 20px; backdrop-filter: blur(4px); }
.create-dialog { width: min(680px, 100%); border: 1px solid #cbd5e1; border-radius: 16px; background: white; box-shadow: 0 28px 80px rgb(15 23 42 / 28%); }
.create-dialog > header { display: flex; align-items: flex-start; justify-content: space-between; border-bottom: 1px solid #e2e8f0; padding: 18px 20px; }
.create-dialog h3 { margin: 7px 0 3px; font-size: 20px; }
.create-dialog header span { color: #64748b; font-size: 10px; }
.create-dialog header button { display: grid; width: 32px; height: 32px; place-items: center; border: 0; border-radius: 8px; background: #f1f5f9; color: #64748b; }
.create-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; padding: 18px 20px; }
.create-grid label { display: grid; gap: 6px; }
.create-grid label.wide { grid-column: 1 / -1; }
.create-grid label span { color: #475569; font-size: 10px; font-weight: 800; }
.create-grid input, .create-grid select { width: 100%; height: 38px; border: 1px solid #cbd5e1; border-radius: 8px; background: white; padding: 0 10px; color: #0f172a; font-size: 11px; outline: none; }
.create-grid input:focus, .create-grid select:focus { border-color: #14b8a6; box-shadow: 0 0 0 3px rgb(20 184 166 / 10%); }
.create-grid input:disabled { background: #f8fafc; color: #64748b; }
.create-dialog > footer { display: flex; justify-content: flex-end; gap: 9px; border-top: 1px solid #e2e8f0; padding: 14px 20px; }
@media (max-width: 1100px) { .workspace-grid { grid-template-columns: 1fr; } .quote-list-panel { position: static; max-height: 360px; } .section-tabs { grid-template-columns: repeat(2, minmax(0, 1fr)); } .artifact-grid { grid-template-columns: 1fr; } }
@media (max-width: 760px) { .quote-command-bar, .detail-header, .editor-head, .import-workbench > header, .preview-meta { align-items: stretch; flex-direction: column; } .command-actions { width: 100%; justify-content: space-between; } .metric-grid { grid-template-columns: 1fr 1fr; } .filter-bar { align-items: stretch; flex-direction: column; } .search-field { min-width: 0; } .section-tabs { grid-template-columns: 1fr 1fr; } .detail-total { text-align: left; } .export-button { margin-left: 0; } .section-owner { border-left: 0; padding-left: 0; } .review-actions { width: 100%; flex-wrap: wrap; } .review-actions input { width: 100%; flex-basis: 100%; } .artifact-panel > header { align-items: flex-start; flex-direction: column; } .artifact-list button { grid-template-columns: auto minmax(0, 1fr) auto; } .artifact-list code, .artifact-list .export-state { grid-column: 2; } .timeline-list article { grid-template-columns: 10px 1fr; } .timeline-list article > span, .timeline-list time { grid-column: 2; } .create-grid { grid-template-columns: 1fr; } .create-grid label.wide { grid-column: auto; } }
</style>
