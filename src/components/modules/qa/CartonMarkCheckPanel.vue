<script setup lang="ts">
import { CheckCircle2, ChevronLeft, ChevronRight, Crop, Eye, FileSpreadsheet, FileText, Image as ImageIcon, RefreshCw, Trash2, UploadCloud, XCircle } from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  cartonMarkApi,
  type CartonMarkAutoCheckResponse,
  type CartonMarkBatchCheckResponse,
  type CartonMarkComparisonItem,
  type CartonMarkCustomer,
  type CartonMarkDocumentContentComparison,
  type CartonMarkDocumentContentCheckResponse,
  type CartonMarkTemplateDocumentKind,
  type CartonMarkTemplateRecordResponse,
} from '@/api/cartonMark'
import CartonMarkCustomerDialog from '@/components/modules/qa/CartonMarkCustomerDialog.vue'
import type { ProductionFactoryContextId } from '@/data/enterpriseMock'
import { getApiErrorMessage } from '@/lib/http'
import {
  clampRatio,
  cropImageBlob,
  getContainedImageFrame,
  isUsableCropSelection,
  normalizeCropSelection,
  type NormalizedCropSelection,
} from '@/lib/imageCrop'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

interface CartonMarkTemplateRecord {
  id: string
  factoryId: ProductionFactoryContextId
  factoryName: string
  customerName: string
  po: string
  item: string
  contractNumber: string
  fileName: string
  fileSize: number
  uploadedAt: string
  version: number
  pdfUrl?: string
  fileBlob?: Blob
  excelFileName?: string
  excelFileSize?: number
  excelUrl?: string
  documentCheckResult?: CartonMarkDocumentContentCheckResponse
  documentCheckErrorMessage?: string
  documentCheckedAt?: string
  checkStatus: string
  qcReady: boolean
  createdByName: string
}

interface CartonMarkPhotoRecord {
  id: string
  templateId: string
  factoryId: ProductionFactoryContextId
  factoryName: string
  customerName: string
  po: string
  item: string
  contractNumber: string
  fileName: string
  fileSize: number
  uploadedAt: string
  sequence: number
  status: string
  reviewedAt?: string
  reviewedBy?: string
  autoCheckResult?: CartonMarkAutoCheckResponse
  autoCheckErrorMessage?: string
  autoCheckedAt?: string
  imageUrl?: string
  imageBlob?: Blob
  frontFileName?: string
  frontFileSize?: number
  frontImageUrl?: string
  frontImageBlob?: Blob
  sideFileName?: string
  sideFileSize?: number
  sideImageUrl?: string
  sideImageBlob?: Blob
}

interface StoredCartonMarkPhotoRecord extends Omit<CartonMarkPhotoRecord, 'imageUrl' | 'frontImageUrl' | 'sideImageUrl' | 'factoryId' | 'factoryName' | 'contractNumber'> {
  contractNumber?: string
  factoryId?: ProductionFactoryContextId
  factoryName?: string
}

type CartonMarkPhotoSide = 'front' | 'side'
type CartonMarkWorkspaceMode = 'warehouse' | 'qa' | 'qc'

interface PhotoCropState {
  enabled: boolean
  isDragging: boolean
  startPoint: { x: number, y: number } | null
  selection: NormalizedCropSelection | null
  applied: boolean
  errorMessage: string
}

interface LeftLabelFeedback {
  total: number
  passed: number
  issues: CartonMarkComparisonItem[]
}

const DB_NAME = 'rr-carton-mark-library'
const DB_VERSION = 2
const PHOTO_STORE_NAME = 'cartonMarkPhotos'
const PHOTO_LOCAL_STORAGE_KEY = 'rr-carton-mark-photo-records'
const ALL_CUSTOMERS = '全部'
const LEGACY_CARTON_MARK_FACTORY_ID: ProductionFactoryContextId = 'huaxing'
const LEGACY_CARTON_MARK_FACTORY_NAME = '华兴'

const appStore = useAppStore()
const authStore = useAuthStore()
const route = useRoute()
const props = defineProps<{
  workspaceMode?: CartonMarkWorkspaceMode
}>()

const form = reactive({
  customerName: '',
  item: '',
  contractNumber: '',
})

const photoForm = reactive({
  customerName: ALL_CUSTOMERS,
  templateId: '',
})

const allRecords = ref<CartonMarkTemplateRecord[]>([])
const allPhotoRecords = ref<CartonMarkPhotoRecord[]>([])
const customerOptions = ref<CartonMarkCustomer[]>([])
const selectedFile = ref<File | null>(null)
const selectedExcelFile = ref<File | null>(null)
const selectedFrontPhotoFile = ref<File | null>(null)
const selectedSidePhotoFile = ref<File | null>(null)
const selectedFrontBatchFiles = ref<File[]>([])
const selectedSideBatchFiles = ref<File[]>([])
const activeFrontBatchPhotoIndex = ref(0)
const activeSideBatchPhotoIndex = ref(0)
const croppedBatchPhotoIndexes = reactive<Record<CartonMarkPhotoSide, number[]>>({
  front: [],
  side: [],
})
const selectedFrontPreviewUrl = ref('')
const selectedSidePreviewUrl = ref('')
const frontPreviewImage = ref<HTMLImageElement | null>(null)
const sidePreviewImage = ref<HTMLImageElement | null>(null)
const photoPreviewRenderTick = ref(0)
const fileInput = ref<HTMLInputElement | null>(null)
const excelFileInput = ref<HTMLInputElement | null>(null)
const frontPhotoFileInput = ref<HTMLInputElement | null>(null)
const sidePhotoFileInput = ref<HTMLInputElement | null>(null)
const frontBatchPhotoFileInput = ref<HTMLInputElement | null>(null)
const sideBatchPhotoFileInput = ref<HTMLInputElement | null>(null)
const comparisonRecord = ref<CartonMarkPhotoRecord | null>(null)
const documentComparisonRecord = ref<CartonMarkTemplateRecord | null>(null)
const autoCheckResult = ref<CartonMarkAutoCheckResponse | null>(null)
const autoCheckErrorMessage = ref('')
const recheckingPhotoId = ref('')
const recheckingDocumentId = ref('')
const activeCustomer = ref(ALL_CUSTOMERS)
const searchKeyword = ref('')
const errorMessage = ref('')
const successMessage = ref('')
const documentReviewMessage = ref('')
const customerOptionsErrorMessage = ref('')
const photoErrorMessage = ref('')
const photoSuccessMessage = ref('')
const isLoading = ref(false)
const isLoadingCustomerOptions = ref(false)
const customerDialogOpen = ref(false)
const customerMutationBusy = ref(false)
const customerMutationError = ref('')
const isSaving = ref(false)
const isSavingPhoto = ref(false)
const isSavingBatchPhoto = ref(false)
const deletingRecordId = ref('')
const deletingPhotoRecordId = ref('')
const photoStorageMode = ref<'indexedDb' | 'localStorage'>('indexedDb')
const downloadingDocumentKey = ref('')
let factoryGeneration = 0
let templateRequestController: AbortController | null = null
let documentRecheckRequestController: AbortController | null = null
let customerOptionsRequestController: AbortController | null = null
let isPanelMounted = false
const pdfUrls = new Set<string>()
const excelUrls = new Set<string>()
const imageUrls = new Set<string>()
const photoCropState = reactive<Record<CartonMarkPhotoSide, PhotoCropState>>({
  front: createPhotoCropState(),
  side: createPhotoCropState(),
})

const activeFactory = computed(() => appStore.activeProductionFactory)
const activeFactoryId = computed(() => activeFactory.value.id as ProductionFactoryContextId)
const isCurrentFactoryTask = (factoryId: ProductionFactoryContextId, generation: number) => (
  activeFactoryId.value === factoryId && factoryGeneration === generation
)
const isWarehouseWorkspace = computed(() => {
  if (props.workspaceMode) return props.workspaceMode === 'warehouse'
  return String(route.params.department ?? 'qa') === 'pmc-warehouse'
})
const currentDepartmentId = computed(() => {
  if (isWarehouseWorkspace.value) return 'pmc-warehouse'
  return props.workspaceMode === 'qc' ? 'qc' : 'qa'
})
const warehousePermissionDepartments = ['pmc-warehouse', 'carton'] as const
const canInCurrentWorkspace = (permission: string) => {
  if (isWarehouseWorkspace.value) {
    return warehousePermissionDepartments.some((department) => authStore.can(permission, activeFactoryId.value, department))
  }
  return authStore.can(permission, activeFactoryId.value, currentDepartmentId.value)
}
const isAdmin = computed(() => canInCurrentWorkspace('system:user_manage'))
const canUploadTemplate = computed(() => isAdmin.value || canInCurrentWorkspace('carton_mark:template_upload'))
const canManageCustomers = computed(() => isAdmin.value || canInCurrentWorkspace('carton_mark:customer_manage'))
const canUploadPhoto = computed(() => isAdmin.value || authStore.can('carton_mark:photo_upload', activeFactoryId.value, currentDepartmentId.value))
const canReviewPhoto = computed(() => isAdmin.value || authStore.can('carton_mark:review', activeFactoryId.value, currentDepartmentId.value))
const canDeleteTemplate = computed(() => isWarehouseWorkspace.value && canUploadTemplate.value)
const currentUserName = computed(() => authStore.currentUser?.display_name ?? '当前账号')
const templatePermissionHint = computed(() => canUploadTemplate.value
  ? '先上传客人提供的 PO 箱唛 Excel，再上传调整排版和图案后的打印 PDF；系统只核对普通业务文字，图形内文字不参与比较。'
  : '当前账号只能查看箱唛资料；请使用纸箱部仓管账号上传 Excel 与打印 PDF。')
const photoPermissionHint = computed(() => {
  if (canUploadPhoto.value) {
    return '当前账号可选择纸箱部已完成 Excel–PDF 核对的打印 PDF，再上传现场箱唛照片核验。'
  }

  return '当前账号只能查看实拍记录；QC 检验员账号可上传现场照片并核对箱唛。'
})

const records = computed(() => {
  return sortRecords(allRecords.value.filter((record) => record.factoryId === activeFactoryId.value))
})

const photoRecords = computed(() => {
  return sortPhotoRecords(allPhotoRecords.value.filter((record) => record.factoryId === activeFactoryId.value))
})

const photoReadyRecords = computed(() => {
  return records.value.filter((record) => record.qcReady)
})

const selectedFileLabel = computed(() => {
  if (!selectedFile.value) return '未选择 PDF'

  return `${selectedFile.value.name} · ${formatFileSize(selectedFile.value.size)}`
})

const selectedExcelFileLabel = computed(() => {
  if (!selectedExcelFile.value) return '未选择 Excel'

  return `${selectedExcelFile.value.name} · ${formatFileSize(selectedExcelFile.value.size)}`
})

const selectedFrontPhotoFileLabel = computed(() => {
  if (!selectedFrontPhotoFile.value) return '未选择正唛图片'

  return `${selectedFrontPhotoFile.value.name} · ${formatFileSize(selectedFrontPhotoFile.value.size)}`
})

const selectedSidePhotoFileLabel = computed(() => {
  if (!selectedSidePhotoFile.value) return '未选择侧唛图片'

  return `${selectedSidePhotoFile.value.name} · ${formatFileSize(selectedSidePhotoFile.value.size)}`
})

const selectedFrontBatchFilesLabel = computed(() => selectedFrontBatchFiles.value.length
  ? `已选择 ${selectedFrontBatchFiles.value.length} 张正唛`
  : '未选择正唛')

const selectedSideBatchFilesLabel = computed(() => selectedSideBatchFiles.value.length
  ? `已选择 ${selectedSideBatchFiles.value.length} 张侧唛`
  : '未选择侧唛')

const hasSelectedCustomerOption = computed(() => {
  const selectedCustomer = normalizeKey(form.customerName)
  return Boolean(selectedCustomer) && customerOptions.value.some(
    (customer) => normalizeKey(customer.name) === selectedCustomer,
  )
})

const canSubmit = computed(() => {
  return Boolean(
    canUploadTemplate.value
    && hasSelectedCustomerOption.value
    && form.item.trim()
    && form.contractNumber.trim()
    && selectedExcelFile.value
    && isExcelFile(selectedExcelFile.value)
    && selectedFile.value
    && isPdfFile(selectedFile.value),
  )
})

const selectedTemplateForPhoto = computed(() => {
  return photoReadyRecords.value.find((record) => record.id === photoForm.templateId)
})

const comparisonTemplate = computed(() => {
  const photo = comparisonRecord.value
  if (!photo) return null

  return findTemplateForPhoto(photo)
})

const comparisonPdfPreviewUrl = computed(() => {
  const pdfUrl = comparisonTemplate.value?.pdfUrl

  return pdfUrl ? `${pdfUrl}#toolbar=0&navpanes=0&scrollbar=0&view=FitH` : ''
})

const comparisonPdfMissingMessage = computed(() => {
  if (!comparisonRecord.value) return ''

  if (!comparisonTemplate.value) {
    return '没有匹配到同客名、PO、ITEM 的 PDF 模板。'
  }

  return '已匹配到服务器模板，但打印 PDF 暂时无法读取，请稍后重试。'
})

const templateCustomerOptions = computed(() => {
  const customerMap = new Map<string, { name: string, count: number }>()

  for (const record of photoReadyRecords.value) {
    const key = normalizeKey(record.customerName)
    const current = customerMap.get(key)

    if (current) {
      current.count += 1
      continue
    }

    customerMap.set(key, {
      name: record.customerName,
      count: 1,
    })
  }

  return Array.from(customerMap.values()).sort((left, right) => left.name.localeCompare(right.name, 'zh-CN'))
})

const filteredTemplateOptions = computed(() => {
  if (photoForm.customerName === ALL_CUSTOMERS) return photoReadyRecords.value

  const customer = normalizeKey(photoForm.customerName)
  return photoReadyRecords.value.filter((record) => normalizeKey(record.customerName) === customer)
})

const canSubmitPhoto = computed(() => {
  return Boolean(
    canUploadPhoto.value
    && selectedTemplateForPhoto.value
    && selectedFrontPhotoFile.value
    && selectedSidePhotoFile.value
    && isImageFile(selectedFrontPhotoFile.value)
    && isImageFile(selectedSidePhotoFile.value),
  )
})
const hasBothSelectedPhotos = computed(() => Boolean(selectedFrontPhotoFile.value && selectedSidePhotoFile.value))
const batchPhotoCount = computed(() => selectedFrontBatchFiles.value.length + selectedSideBatchFiles.value.length)
const canSubmitBatchPhoto = computed(() => Boolean(
  canUploadPhoto.value
  && selectedTemplateForPhoto.value
  && batchPhotoCount.value,
))
const photoSubmitLabel = computed(() => {
  if (isSavingBatchPhoto.value) return '核对中'
  if (batchPhotoCount.value === 1) return '开始核对'
  if (batchPhotoCount.value > 1) return `开始批量核对（${batchPhotoCount.value} 张）`
  return '上传照片后开始核对'
})
const autoCheckComparisons = computed(() => autoCheckResult.value?.comparisons ?? [])
const frontAutoCheckComparisons = computed(() => {
  return autoCheckComparisons.value.filter((item) => item.side === 'front')
})
const sideAutoCheckComparisons = computed(() => {
  return autoCheckComparisons.value.filter((item) => item.side === 'side')
})
const frontLeftLabelFeedback = computed(() => buildLeftLabelFeedback(frontAutoCheckComparisons.value))
const sideLeftLabelFeedback = computed(() => buildLeftLabelFeedback(sideAutoCheckComparisons.value))
const autoCheckExtractionMessages = computed(() => {
  return (autoCheckResult.value?.extraction ?? []).filter((status) => status.message || !status.ok)
})
const autoCheckExtractionWarningMessages = computed(() => {
  return autoCheckExtractionMessages.value.filter((status) => (
    !status.ok || status.requires_review || /需复核|无法|失败|未识别/.test(status.message)
  ))
})
const autoCheckExtractionInfoMessages = computed(() => {
  return autoCheckExtractionMessages.value.filter((status) => (
    status.ok && !status.requires_review && !/需复核|无法|失败|未识别/.test(status.message)
  ))
})
const autoCheckMatchedPage = computed(() => {
  return (autoCheckResult.value?.extraction ?? []).find((status) => status.matched_page)?.matched_page ?? null
})

const documentCheckResult = computed(() => documentComparisonRecord.value?.documentCheckResult ?? null)
const documentCheckExtractionMessages = computed(() => {
  return (documentCheckResult.value?.extraction ?? []).filter((status) => status.message || !status.ok)
})
const documentCheckExtractionWarningMessages = computed(() => {
  return documentCheckExtractionMessages.value.filter((status) => (
    !status.ok || /需复核|无法|失败|未识别/.test(status.message)
  ))
})
const documentCheckExtractionInfoMessages = computed(() => {
  return documentCheckExtractionMessages.value.filter((status) => (
    status.ok && !/需复核|无法|失败|未识别/.test(status.message)
  ))
})

const customerGroups = computed(() => {
  const groups = new Map<string, { name: string, count: number, latestAt: string }>()

  for (const record of records.value) {
    const key = normalizeKey(record.customerName)
    const current = groups.get(key)
    if (!current) {
      groups.set(key, {
        name: record.customerName,
        count: 1,
        latestAt: record.uploadedAt,
      })
      continue
    }

    current.count += 1
    if (record.uploadedAt > current.latestAt) {
      current.latestAt = record.uploadedAt
    }
  }

  return Array.from(groups.values()).sort((left, right) => left.name.localeCompare(right.name, 'zh-CN'))
})

const visibleCustomerGroups = computed(() => {
  const keyword = normalizeKey(searchKeyword.value)
  if (!keyword) return customerGroups.value

  return customerGroups.value.filter((customer) => {
    if (normalizeKey(customer.name).includes(keyword)) return true

    return records.value.some((record) => {
      return normalizeKey(record.customerName) === normalizeKey(customer.name)
        && [record.item, record.contractNumber, record.fileName].some((value) => normalizeKey(value).includes(keyword))
    })
  })
})

const filteredRecords = computed(() => {
  const keyword = normalizeKey(searchKeyword.value)
  const customer = normalizeKey(activeCustomer.value)

  return records.value.filter((record) => {
    const matchesCustomer = activeCustomer.value === ALL_CUSTOMERS || normalizeKey(record.customerName) === customer
    const matchesKeyword = !keyword || [
      record.customerName,
      record.po,
      record.item,
      record.contractNumber,
      record.fileName,
      record.excelFileName ?? '',
    ].some((value) => normalizeKey(value).includes(keyword))

    return matchesCustomer && matchesKeyword
  })
})

const latestPhotoRecord = computed(() => photoRecords.value[0])

onMounted(async () => {
  isPanelMounted = true
  isLoading.value = true
  const requestedFactoryId = activeFactoryId.value
  const requestedFactoryName = activeFactory.value.shortName
  const requestedFactoryGeneration = factoryGeneration
  templateRequestController = new AbortController()
  if (isWarehouseWorkspace.value) {
    void loadCustomerOptions(requestedFactoryId, requestedFactoryGeneration)
  }

  const templatesPromise = cartonMarkApi.listTemplates(requestedFactoryId, templateRequestController.signal)
  const photosPromise = readPhotoRecordsFromDb()
    .then((storedPhotoRecords) => ({
      mode: 'indexedDb' as const,
      records: storedPhotoRecords.map(normalizeStoredPhotoRecord),
    }))
    .catch(() => ({
      mode: 'localStorage' as const,
      records: readPhotoRecordsFromLocalStorage(),
    }))

  const [templatesResult, photosResult] = await Promise.allSettled([templatesPromise, photosPromise])
  if (!isPanelMounted) return

  if (photosResult.status === 'fulfilled') {
    photoStorageMode.value = photosResult.value.mode
    allPhotoRecords.value = sortPhotoRecords(photosResult.value.records.map(hydratePhotoRecord))
  }

  if (!isCurrentFactoryTask(requestedFactoryId, requestedFactoryGeneration)) return

  if (templatesResult.status === 'fulfilled') {
    allRecords.value = sortRecords(templatesResult.value.map((record) => mapTemplateRecord(record, requestedFactoryName)))
  } else {
    allRecords.value = []
    const message = `箱唛资料库读取失败：${getApiErrorMessage(templatesResult.reason)}`
    if (isWarehouseWorkspace.value) errorMessage.value = message
    else photoErrorMessage.value = message
  }

  isLoading.value = false
})

async function loadTemplateRecords(factoryId: ProductionFactoryContextId, factoryName: string, generation: number) {
  templateRequestController?.abort()
  const controller = new AbortController()
  templateRequestController = controller
  isLoading.value = true

  try {
    const persistedRecords = await cartonMarkApi.listTemplates(factoryId, controller.signal)
    if (!isCurrentFactoryTask(factoryId, generation) || !isPanelMounted) return
    allRecords.value = sortRecords(persistedRecords.map((record) => mapTemplateRecord(record, factoryName)))
  } catch (error) {
    if (!isCurrentFactoryTask(factoryId, generation) || !isPanelMounted || controller.signal.aborted) return
    allRecords.value = []
    const message = `箱唛资料库读取失败：${getApiErrorMessage(error)}`
    if (isWarehouseWorkspace.value) errorMessage.value = message
    else photoErrorMessage.value = message
  } finally {
    if (isCurrentFactoryTask(factoryId, generation) && isPanelMounted) {
      isLoading.value = false
    }
  }
}

async function loadCustomerOptions(factoryId: ProductionFactoryContextId, generation: number) {
  customerOptionsRequestController?.abort()
  const controller = new AbortController()
  customerOptionsRequestController = controller
  isLoadingCustomerOptions.value = true
  customerOptionsErrorMessage.value = ''

  try {
    const nextCustomerOptions = await cartonMarkApi.listCustomers(factoryId, controller.signal)
    if (!isCurrentFactoryTask(factoryId, generation) || !isPanelMounted) return
    customerOptions.value = nextCustomerOptions
    if (!nextCustomerOptions.some((customer) => normalizeKey(customer.name) === normalizeKey(form.customerName))) {
      form.customerName = ''
    }
  } catch (error) {
    if (!isCurrentFactoryTask(factoryId, generation) || !isPanelMounted || controller.signal.aborted) return
    customerOptions.value = []
    form.customerName = ''
    customerOptionsErrorMessage.value = `箱唛客户资料读取失败：${getApiErrorMessage(error)}`
  } finally {
    if (isCurrentFactoryTask(factoryId, generation) && isPanelMounted) {
      isLoadingCustomerOptions.value = false
    }
  }
}

function reloadCustomerOptions() {
  void loadCustomerOptions(activeFactoryId.value, factoryGeneration)
}

async function createManagedCustomer(name: string) {
  if (!canManageCustomers.value || customerMutationBusy.value) return
  const requestedFactoryId = activeFactoryId.value
  const requestedGeneration = factoryGeneration
  customerMutationBusy.value = true
  customerMutationError.value = ''
  try {
    const customer = await cartonMarkApi.createCustomer(requestedFactoryId, name)
    await loadCustomerOptions(requestedFactoryId, requestedGeneration)
    if (isCurrentFactoryTask(requestedFactoryId, requestedGeneration)) {
      form.customerName = customer.name
    }
  } catch (error) {
    if (isCurrentFactoryTask(requestedFactoryId, requestedGeneration)) {
      customerMutationError.value = getApiErrorMessage(error)
    }
  } finally {
    if (isCurrentFactoryTask(requestedFactoryId, requestedGeneration)) {
      customerMutationBusy.value = false
    }
  }
}

async function updateManagedCustomer(customer: CartonMarkCustomer, name: string) {
  if (!canManageCustomers.value || customerMutationBusy.value) return
  const requestedFactoryId = activeFactoryId.value
  const requestedGeneration = factoryGeneration
  const wasSelected = normalizeKey(form.customerName) === normalizeKey(customer.name)
  customerMutationBusy.value = true
  customerMutationError.value = ''
  try {
    const updated = await cartonMarkApi.updateCustomer(
      requestedFactoryId,
      customer.id,
      name,
      customer.revision,
    )
    await loadCustomerOptions(requestedFactoryId, requestedGeneration)
    if (wasSelected && isCurrentFactoryTask(requestedFactoryId, requestedGeneration)) {
      form.customerName = updated.name
    }
  } catch (error) {
    if (isCurrentFactoryTask(requestedFactoryId, requestedGeneration)) {
      customerMutationError.value = getApiErrorMessage(error)
    }
  } finally {
    if (isCurrentFactoryTask(requestedFactoryId, requestedGeneration)) {
      customerMutationBusy.value = false
    }
  }
}

async function deleteManagedCustomer(customer: CartonMarkCustomer) {
  if (!canManageCustomers.value || customerMutationBusy.value) return
  const requestedFactoryId = activeFactoryId.value
  const requestedGeneration = factoryGeneration
  customerMutationBusy.value = true
  customerMutationError.value = ''
  try {
    await cartonMarkApi.deleteCustomer(requestedFactoryId, customer.id, customer.revision)
    await loadCustomerOptions(requestedFactoryId, requestedGeneration)
  } catch (error) {
    if (isCurrentFactoryTask(requestedFactoryId, requestedGeneration)) {
      customerMutationError.value = getApiErrorMessage(error)
    }
  } finally {
    if (isCurrentFactoryTask(requestedFactoryId, requestedGeneration)) {
      customerMutationBusy.value = false
    }
  }
}

function revokeTemplateUrls() {
  for (const url of pdfUrls) {
    URL.revokeObjectURL(url)
  }
  pdfUrls.clear()

  for (const url of excelUrls) {
    URL.revokeObjectURL(url)
  }
  excelUrls.clear()
}

watch(activeFactoryId, () => {
  factoryGeneration += 1
  templateRequestController?.abort()
  documentRecheckRequestController?.abort()
  customerOptionsRequestController?.abort()
  revokeTemplateUrls()
  allRecords.value = []
  customerOptions.value = []
  customerDialogOpen.value = false
  customerMutationBusy.value = false
  customerMutationError.value = ''
  const requestedFactoryId = activeFactoryId.value
  const requestedFactoryName = activeFactory.value.shortName
  const requestedFactoryGeneration = factoryGeneration
  void loadTemplateRecords(requestedFactoryId, requestedFactoryName, requestedFactoryGeneration)
  if (isWarehouseWorkspace.value) {
    void loadCustomerOptions(requestedFactoryId, requestedFactoryGeneration)
  }
  errorMessage.value = ''
  successMessage.value = ''
  documentReviewMessage.value = ''
  customerOptionsErrorMessage.value = ''
  photoErrorMessage.value = ''
  photoSuccessMessage.value = ''
  documentComparisonRecord.value = null
  activeCustomer.value = ALL_CUSTOMERS
  photoForm.customerName = ALL_CUSTOMERS
  photoForm.templateId = ''
  isSaving.value = false
  isSavingPhoto.value = false
  isSavingBatchPhoto.value = false
  recheckingPhotoId.value = ''
  recheckingDocumentId.value = ''
  deletingRecordId.value = ''
  downloadingDocumentKey.value = ''
  resetForm()
  resetPhotoSelection()
  resetBatchPhotoSelection()
})

watch(() => photoForm.customerName, () => {
  photoForm.templateId = ''
  resetPhotoSelection()
  resetBatchPhotoSelection()
})

watch(() => photoForm.templateId, () => {
  resetPhotoSelection()
  resetBatchPhotoSelection()
})

onBeforeUnmount(() => {
  isPanelMounted = false
  factoryGeneration += 1
  templateRequestController?.abort()
  documentRecheckRequestController?.abort()
  customerOptionsRequestController?.abort()
  revokeTemplateUrls()

  for (const url of imageUrls) {
    URL.revokeObjectURL(url)
  }
})

function normalizeKey(value: string) {
  return value.trim().toUpperCase()
}

function isPdfFile(file: File) {
  return file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
}

function isExcelFile(file: File) {
  return /\.(xls|xlsx|xlsm)$/i.test(file.name)
}

function isImageFile(file: File) {
  return file.type.startsWith('image/') || /\.(png|jpe?g|webp|gif|bmp|heic|heif)$/i.test(file.name)
}

function formatFileSize(size: number) {
  if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value))
}

function createPdfUrl(blob: Blob) {
  const url = URL.createObjectURL(blob)
  pdfUrls.add(url)
  return url
}

function createExcelUrl(blob: Blob) {
  const url = URL.createObjectURL(blob)
  excelUrls.add(url)
  return url
}

async function ensureTemplatePdfBlob(template: CartonMarkTemplateRecord) {
  if (template.fileBlob) return template.fileBlob

  const requestedFactoryId = activeFactoryId.value
  const requestedFactoryGeneration = factoryGeneration
  if (template.factoryId !== requestedFactoryId) {
    throw new Error('模板所属厂区与当前厂区不一致，请重新选择。')
  }

  const blob = await cartonMarkApi.downloadTemplateDocument(template.id, 'print_pdf', requestedFactoryId)
  if (!isCurrentFactoryTask(requestedFactoryId, requestedFactoryGeneration) || !isPanelMounted) {
    throw new Error('厂区已切换，本次文件读取已取消。')
  }

  template.fileBlob = blob
  if (!template.pdfUrl) template.pdfUrl = createPdfUrl(blob)
  return blob
}

async function openTemplateDocument(
  record: CartonMarkTemplateRecord,
  kind: CartonMarkTemplateDocumentKind,
  pdfPage?: number | null,
) {
  const requestKey = `${record.id}:${kind}`
  downloadingDocumentKey.value = requestKey
  const requestedFactoryId = activeFactoryId.value
  const requestedFactoryGeneration = factoryGeneration

  try {
    const blob = kind === 'print_pdf'
      ? await ensureTemplatePdfBlob(record)
      : await cartonMarkApi.downloadTemplateDocument(record.id, kind, requestedFactoryId)
    if (!isCurrentFactoryTask(requestedFactoryId, requestedFactoryGeneration) || !isPanelMounted) return

    if (kind === 'print_pdf') {
      const url = record.pdfUrl ?? createPdfUrl(blob)
      record.pdfUrl = url
      const targetUrl = pdfPage && pdfPage > 0 ? `${url}#page=${pdfPage}` : url
      window.open(targetUrl, '_blank', 'noopener,noreferrer')
      return
    }

    const url = createExcelUrl(blob)
    record.excelUrl = url
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = record.excelFileName || 'carton-mark-source.xlsx'
    anchor.click()
  } catch (error) {
    if (!isPanelMounted || !isCurrentFactoryTask(requestedFactoryId, requestedFactoryGeneration)) return
    const message = `文件读取失败：${getApiErrorMessage(error)}`
    if (isWarehouseWorkspace.value) errorMessage.value = message
    else photoErrorMessage.value = message
  } finally {
    if (isPanelMounted && downloadingDocumentKey.value === requestKey) downloadingDocumentKey.value = ''
  }
}

function createImageUrl(blob: Blob) {
  const url = URL.createObjectURL(blob)
  imageUrls.add(url)
  return url
}

function revokeImageUrl(url: string) {
  URL.revokeObjectURL(url)
  imageUrls.delete(url)
}

function createPhotoCropState(): PhotoCropState {
  return {
    enabled: false,
    isDragging: false,
    startPoint: null,
    selection: null,
    applied: false,
    errorMessage: '',
  }
}

function resetPhotoCropState(side: CartonMarkPhotoSide, keepApplied = false) {
  const state = photoCropState[side]
  state.enabled = false
  state.isDragging = false
  state.startPoint = null
  state.selection = null
  state.errorMessage = ''
  if (!keepApplied) {
    state.applied = false
  }
}

function getPhotoPreviewImage(side: CartonMarkPhotoSide) {
  return side === 'front' ? frontPreviewImage.value : sidePreviewImage.value
}

function getSelectedPhotoFile(side: CartonMarkPhotoSide) {
  return side === 'front' ? selectedFrontPhotoFile.value : selectedSidePhotoFile.value
}

function setSelectedPhotoFile(side: CartonMarkPhotoSide, file: File) {
  if (side === 'front') {
    selectedFrontPhotoFile.value = file
    if (selectedFrontPreviewUrl.value) {
      revokeImageUrl(selectedFrontPreviewUrl.value)
    }
    selectedFrontPreviewUrl.value = createImageUrl(file)
    return
  }

  selectedSidePhotoFile.value = file
  if (selectedSidePreviewUrl.value) {
    revokeImageUrl(selectedSidePreviewUrl.value)
  }
  selectedSidePreviewUrl.value = createImageUrl(file)
}

function getBatchPhotoFiles(side: CartonMarkPhotoSide) {
  return side === 'front' ? selectedFrontBatchFiles.value : selectedSideBatchFiles.value
}

function setBatchPhotoFiles(side: CartonMarkPhotoSide, files: File[]) {
  if (side === 'front') {
    selectedFrontBatchFiles.value = files
    return
  }

  selectedSideBatchFiles.value = files
}

function getActiveBatchPhotoIndex(side: CartonMarkPhotoSide) {
  return side === 'front' ? activeFrontBatchPhotoIndex.value : activeSideBatchPhotoIndex.value
}

function setActiveBatchPhotoIndex(side: CartonMarkPhotoSide, index: number) {
  if (side === 'front') {
    activeFrontBatchPhotoIndex.value = index
    return
  }

  activeSideBatchPhotoIndex.value = index
}

function getBatchPhotoPositionLabel(side: CartonMarkPhotoSide) {
  const files = getBatchPhotoFiles(side)
  if (!files.length) return '未选择图片'

  return `第 ${getActiveBatchPhotoIndex(side) + 1} / ${files.length} 张`
}

function canMoveBatchPhoto(side: CartonMarkPhotoSide, direction: -1 | 1) {
  const nextIndex = getActiveBatchPhotoIndex(side) + direction
  return nextIndex >= 0 && nextIndex < getBatchPhotoFiles(side).length
}

function isActiveBatchPhotoCropped(side: CartonMarkPhotoSide) {
  return croppedBatchPhotoIndexes[side].includes(getActiveBatchPhotoIndex(side))
}

function resetBatchPhotoCropMarks(side: CartonMarkPhotoSide) {
  croppedBatchPhotoIndexes[side] = []
}

function markActiveBatchPhotoCropped(side: CartonMarkPhotoSide) {
  const index = getActiveBatchPhotoIndex(side)
  if (!croppedBatchPhotoIndexes[side].includes(index)) {
    croppedBatchPhotoIndexes[side].push(index)
  }
}

function showBatchPhotoAt(side: CartonMarkPhotoSide, index: number) {
  const files = getBatchPhotoFiles(side)
  const nextFile = files[index]
  if (!nextFile) return

  clearPhotoSelection(side, false)
  setActiveBatchPhotoIndex(side, index)
  setSelectedPhotoFile(side, nextFile)
  photoPreviewRenderTick.value += 1
}

function switchActiveBatchPhoto(side: CartonMarkPhotoSide, direction: -1 | 1) {
  if (!canMoveBatchPhoto(side, direction)) return
  showBatchPhotoAt(side, getActiveBatchPhotoIndex(side) + direction)
}

function enablePhotoCrop(side: CartonMarkPhotoSide) {
  const state = photoCropState[side]
  state.enabled = true
  state.isDragging = false
  state.startPoint = null
  state.selection = null
  state.errorMessage = ''
  photoErrorMessage.value = ''
  photoSuccessMessage.value = ''
  photoPreviewRenderTick.value += 1
}

function cancelPhotoCrop(side: CartonMarkPhotoSide) {
  resetPhotoCropState(side, true)
}

function getCropPointFromPointer(event: PointerEvent) {
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  return {
    x: clampRatio((event.clientX - rect.left) / Math.max(1, rect.width)),
    y: clampRatio((event.clientY - rect.top) / Math.max(1, rect.height)),
  }
}

function startPhotoCrop(event: PointerEvent, side: CartonMarkPhotoSide) {
  const state = photoCropState[side]
  if (!state.enabled) return

  event.preventDefault()
  ;(event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId)
  const point = getCropPointFromPointer(event)
  state.isDragging = true
  state.startPoint = point
  state.selection = {
    x: point.x,
    y: point.y,
    width: 0,
    height: 0,
  }
}

function movePhotoCrop(event: PointerEvent, side: CartonMarkPhotoSide) {
  const state = photoCropState[side]
  if (!state.enabled || !state.isDragging || !state.startPoint) return

  event.preventDefault()
  state.selection = normalizeCropSelection(state.startPoint, getCropPointFromPointer(event))
}

function finishPhotoCrop(event: PointerEvent, side: CartonMarkPhotoSide) {
  const state = photoCropState[side]
  if (!state.isDragging) return

  movePhotoCrop(event, side)
  state.isDragging = false
  state.startPoint = null
  ;(event.currentTarget as HTMLElement).releasePointerCapture?.(event.pointerId)
}

function getPhotoCropFrameStyle(side: CartonMarkPhotoSide) {
  photoPreviewRenderTick.value
  const image = getPhotoPreviewImage(side)
  if (!image) {
    return {
      inset: '0px',
    }
  }

  const frame = getContainedImageFrame(
    image.clientWidth,
    image.clientHeight,
    image.naturalWidth,
    image.naturalHeight,
  )

  return {
    left: `${frame.left}px`,
    top: `${frame.top}px`,
    width: `${frame.width}px`,
    height: `${frame.height}px`,
  }
}

function getPhotoCropSelectionStyle(side: CartonMarkPhotoSide) {
  const selection = photoCropState[side].selection
  if (!selection) {
    return {
      display: 'none',
    }
  }

  return {
    left: `${selection.x * 100}%`,
    top: `${selection.y * 100}%`,
    width: `${selection.width * 100}%`,
    height: `${selection.height * 100}%`,
  }
}

function handlePhotoPreviewLoad() {
  photoPreviewRenderTick.value += 1
}

function buildCroppedPhotoFileName(fileName: string) {
  const dotIndex = fileName.lastIndexOf('.')
  if (dotIndex <= 0) {
    return `${fileName}-crop.png`
  }

  return `${fileName.slice(0, dotIndex)}-crop.png`
}

async function applyPhotoCrop(side: CartonMarkPhotoSide) {
  const state = photoCropState[side]
  const file = getSelectedPhotoFile(side)
  if (!file) return

  if (!isUsableCropSelection(state.selection)) {
    state.errorMessage = '请框选完整箱唛区域后再应用。'
    return
  }

  try {
    const croppedFile = await cropImageBlob(file, state.selection as NormalizedCropSelection, buildCroppedPhotoFileName(file.name))
    setSelectedPhotoFile(side, croppedFile)
    const files = [...getBatchPhotoFiles(side)]
    files[getActiveBatchPhotoIndex(side)] = croppedFile
    setBatchPhotoFiles(side, files)
    markActiveBatchPhotoCropped(side)
    resetPhotoCropState(side)
    photoCropState[side].applied = true
    photoSuccessMessage.value = side === 'front'
      ? '正唛已裁剪为箱唛区域，将使用裁剪图自动核对。'
      : '侧唛已裁剪为箱唛区域，将使用裁剪图自动核对。'
    photoPreviewRenderTick.value += 1
  } catch (error) {
    state.errorMessage = getApiErrorMessage(error)
  }
}

function mapTemplateRecord(record: CartonMarkTemplateRecordResponse, factoryName: string): CartonMarkTemplateRecord {
  return {
    id: record.id,
    factoryId: record.factory_id as ProductionFactoryContextId,
    factoryName,
    customerName: record.customer_name,
    po: record.po,
    item: record.item,
    contractNumber: record.contract_number,
    fileName: record.pdf_file_name,
    fileSize: record.pdf_file_size,
    uploadedAt: record.created_at,
    version: record.version,
    excelFileName: record.excel_file_name,
    excelFileSize: record.excel_file_size,
    documentCheckResult: record.check_result,
    documentCheckedAt: record.updated_at,
    checkStatus: record.check_status,
    qcReady: record.qc_ready,
    createdByName: record.created_by_name,
  }
}

function hydratePhotoRecord(record: StoredCartonMarkPhotoRecord): CartonMarkPhotoRecord {
  const frontImageUrl = record.frontImageBlob
    ? createImageUrl(record.frontImageBlob)
    : record.imageBlob ? createImageUrl(record.imageBlob) : undefined

  return {
    ...record,
    contractNumber: record.contractNumber ?? '',
    factoryId: record.factoryId ?? LEGACY_CARTON_MARK_FACTORY_ID,
    factoryName: record.factoryName ?? LEGACY_CARTON_MARK_FACTORY_NAME,
    imageUrl: frontImageUrl,
    frontImageUrl,
    sideImageUrl: record.sideImageBlob ? createImageUrl(record.sideImageBlob) : undefined,
  }
}

function normalizeStoredPhotoRecord(record: StoredCartonMarkPhotoRecord): StoredCartonMarkPhotoRecord {
  return {
    ...record,
    contractNumber: record.contractNumber ?? '',
    factoryId: record.factoryId ?? LEGACY_CARTON_MARK_FACTORY_ID,
    factoryName: record.factoryName ?? LEGACY_CARTON_MARK_FACTORY_NAME,
  }
}

function sortRecords(nextRecords: CartonMarkTemplateRecord[]) {
  return [...nextRecords].sort((left, right) => right.uploadedAt.localeCompare(left.uploadedAt))
}

function sortPhotoRecords(nextRecords: CartonMarkPhotoRecord[]) {
  return [...nextRecords].sort((left, right) => right.uploadedAt.localeCompare(left.uploadedAt))
}

function findTemplateForPhoto(photo: CartonMarkPhotoRecord) {
  const matchedById = records.value.find((record) => record.id === photo.templateId)
  if (matchedById) return matchedById

  const matchedByPo = records.value.find((record) => {
    const poMatches = !photo.po
      || !record.po
      || normalizeKey(record.po) === normalizeKey(photo.po)
    return normalizeKey(record.customerName) === normalizeKey(photo.customerName)
      && poMatches
      && normalizeKey(record.item) === normalizeKey(photo.item)
      && normalizeKey(record.contractNumber) === normalizeKey(photo.contractNumber)
  })
  if (matchedByPo) return matchedByPo

  const selectedTemplate = selectedTemplateForPhoto.value
  if (
    selectedTemplate
    && normalizeKey(selectedTemplate.customerName) === normalizeKey(photo.customerName)
    && normalizeKey(selectedTemplate.po) === normalizeKey(photo.po)
    && normalizeKey(selectedTemplate.item) === normalizeKey(photo.item)
    && normalizeKey(selectedTemplate.contractNumber) === normalizeKey(photo.contractNumber)
  ) {
    return selectedTemplate
  }

  return null
}

function showPhotoAutoCheck(photo: CartonMarkPhotoRecord) {
  comparisonRecord.value = photo
  autoCheckResult.value = photo.autoCheckResult ?? null
  autoCheckErrorMessage.value = photo.autoCheckErrorMessage ?? ''
  const template = findTemplateForPhoto(photo)
  if (template && !template.fileBlob) {
    void ensureTemplatePdfBlob(template).catch((error) => {
      if (!isPanelMounted || comparisonRecord.value?.id !== photo.id) return
      photoErrorMessage.value = `打印 PDF 读取失败：${getApiErrorMessage(error)}`
    })
  }
}

function getPhotoAutoCheckSummary(photo: CartonMarkPhotoRecord) {
  if (photo.autoCheckResult) {
    const summary = photo.autoCheckResult.summary
    return `自动核对：${summary.overall_status} · 通过 ${summary.pass_count} / 异常 ${summary.mismatch_count} / 待复核 ${summary.review_count + summary.missing_count}`
  }

  if (photo.autoCheckErrorMessage) {
    return photo.autoCheckErrorMessage
  }

  return '尚未生成自动核对明细。'
}

async function runCartonMarkAutoCheck(
  template: CartonMarkTemplateRecord,
  frontPhoto: Blob,
  sidePhoto: Blob,
) {
  const pdfTemplate = await ensureTemplatePdfBlob(template)
  return cartonMarkApi.autoCheck({
    customerName: template.customerName,
    po: template.po,
    item: template.item,
    pdfTemplate,
    frontPhoto,
    sidePhoto,
  })
}

async function runCartonMarkBatchAutoCheck(
  template: CartonMarkTemplateRecord,
  frontPhotos: Blob[],
  sidePhotos: Blob[],
) {
  const pdfTemplate = await ensureTemplatePdfBlob(template)
  return cartonMarkApi.batchAutoCheck({
    customerName: template.customerName,
    po: template.po,
    item: template.item,
    pdfTemplate,
    frontPhotos,
    sidePhotos,
  })
}

async function replaceStoredPhotoRecord(nextPhoto: CartonMarkPhotoRecord) {
  const nextPhotoRecords = sortPhotoRecords(allPhotoRecords.value.map((record) => {
    return record.id === nextPhoto.id ? nextPhoto : record
  }))

  allPhotoRecords.value = nextPhotoRecords

  try {
    if (photoStorageMode.value === 'indexedDb') {
      await savePhotoRecordSnapshotToDb(nextPhoto)
    } else {
      writePhotoRecordsToLocalStorage(nextPhotoRecords)
    }
  } catch {
    photoStorageMode.value = 'localStorage'
    writePhotoRecordsToLocalStorage(nextPhotoRecords)
  }

  return nextPhoto
}

function resetForm() {
  form.customerName = ''
  form.item = ''
  form.contractNumber = ''
  selectedExcelFile.value = null
  selectedFile.value = null

  if (excelFileInput.value) {
    excelFileInput.value.value = ''
  }

  if (fileInput.value) {
    fileInput.value.value = ''
  }
}

function clearPhotoSelection(side: CartonMarkPhotoSide, clearComparison = true) {
  photoErrorMessage.value = ''
  photoSuccessMessage.value = ''

  if (clearComparison) {
    comparisonRecord.value = null
    autoCheckResult.value = null
    autoCheckErrorMessage.value = ''
  }

  if (side === 'front') {
    selectedFrontPhotoFile.value = null
    resetPhotoCropState('front')

    if (selectedFrontPreviewUrl.value) {
      revokeImageUrl(selectedFrontPreviewUrl.value)
      selectedFrontPreviewUrl.value = ''
    }

    if (frontBatchPhotoFileInput.value) {
      frontBatchPhotoFileInput.value.value = ''
    }

    return
  }

  selectedSidePhotoFile.value = null
  resetPhotoCropState('side')

  if (selectedSidePreviewUrl.value) {
    revokeImageUrl(selectedSidePreviewUrl.value)
    selectedSidePreviewUrl.value = ''
  }

  if (sideBatchPhotoFileInput.value) {
    sideBatchPhotoFileInput.value.value = ''
  }
}

function resetPhotoSelection(clearComparison = true) {
  clearPhotoSelection('front', clearComparison)
  clearPhotoSelection('side', clearComparison)
}

function clearBatchPhotoSelection(side: CartonMarkPhotoSide) {
  clearPhotoSelection(side, false)
  setActiveBatchPhotoIndex(side, 0)
  resetBatchPhotoCropMarks(side)

  if (side === 'front') {
    selectedFrontBatchFiles.value = []
    if (frontBatchPhotoFileInput.value) frontBatchPhotoFileInput.value.value = ''
    return
  }

  selectedSideBatchFiles.value = []
  if (sideBatchPhotoFileInput.value) sideBatchPhotoFileInput.value.value = ''
}

function resetBatchPhotoSelection() {
  clearBatchPhotoSelection('front')
  clearBatchPhotoSelection('side')
}

function openFilePicker() {
  errorMessage.value = ''
  successMessage.value = ''
  documentReviewMessage.value = ''

  if (!canUploadTemplate.value) {
    errorMessage.value = '当前账号无权上传打印 PDF，请使用纸箱仓管账号操作。'
    return
  }

  fileInput.value?.click()
}

function showDocumentCheck(record: CartonMarkTemplateRecord) {
  documentComparisonRecord.value = record
}

function openExcelFilePicker() {
  errorMessage.value = ''
  successMessage.value = ''
  documentReviewMessage.value = ''

  if (!canUploadTemplate.value) {
    errorMessage.value = '当前账号无权上传客人 Excel，请使用纸箱仓管账号操作。'
    return
  }

  excelFileInput.value?.click()
}

function openPhotoFilePicker(side: CartonMarkPhotoSide) {
  photoErrorMessage.value = ''
  photoSuccessMessage.value = ''

  if (!canUploadPhoto.value) {
    photoErrorMessage.value = '当前账号无权上传实拍图片，请使用 QC 检验员账号操作。'
    return
  }

  if (side === 'front') {
    frontPhotoFileInput.value?.click()
    return
  }

  sidePhotoFileInput.value?.click()
}

function openBatchPhotoFilePicker(side: CartonMarkPhotoSide) {
  photoErrorMessage.value = ''
  photoSuccessMessage.value = ''

  if (!canUploadPhoto.value) {
    photoErrorMessage.value = '当前账号无权上传实拍图片，请使用 QC 检验员账号操作。'
    return
  }

  if (side === 'front') {
    frontBatchPhotoFileInput.value?.click()
    return
  }

  sideBatchPhotoFileInput.value?.click()
}

function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  errorMessage.value = ''
  successMessage.value = ''
  documentReviewMessage.value = ''

  if (!canUploadTemplate.value) {
    selectedFile.value = null
    input.value = ''
    errorMessage.value = '当前账号无权上传打印 PDF，请使用纸箱仓管账号操作。'
    return
  }

  if (!file) {
    selectedFile.value = null
    return
  }

  if (!isPdfFile(file)) {
    selectedFile.value = null
    input.value = ''
    errorMessage.value = '打印箱唛只支持 PDF 文件。'
    return
  }

  selectedFile.value = file
}

function handleExcelFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  errorMessage.value = ''
  successMessage.value = ''
  documentReviewMessage.value = ''

  if (!canUploadTemplate.value) {
    selectedExcelFile.value = null
    input.value = ''
    errorMessage.value = '当前账号无权上传客人 Excel，请使用纸箱仓管账号操作。'
    return
  }

  if (!file) {
    selectedExcelFile.value = null
    return
  }

  if (!isExcelFile(file)) {
    selectedExcelFile.value = null
    input.value = ''
    errorMessage.value = '客人 PO 箱唛只支持 .xls、.xlsx 或 .xlsm 文件。'
    return
  }

  selectedExcelFile.value = file
}

function handlePhotoFileChange(event: Event, side: CartonMarkPhotoSide) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  photoErrorMessage.value = ''
  photoSuccessMessage.value = ''

  if (!canUploadPhoto.value) {
    clearPhotoSelection(side)
    photoErrorMessage.value = '当前账号无权上传实拍图片，请使用 QC 检验员账号操作。'
    return
  }

  if (!file) {
    clearPhotoSelection(side)
    return
  }

  if (!isImageFile(file)) {
    clearPhotoSelection(side)
    photoErrorMessage.value = '只能上传箱唛实拍图片。'
    return
  }

  comparisonRecord.value = null
  autoCheckResult.value = null
  autoCheckErrorMessage.value = ''

  if (side === 'front') {
    clearPhotoSelection('front', false)
    setSelectedPhotoFile('front', file)
    return
  }

  clearPhotoSelection('side', false)
  setSelectedPhotoFile('side', file)
}

function handleBatchPhotoFileChange(event: Event, side: CartonMarkPhotoSide) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  photoErrorMessage.value = ''
  photoSuccessMessage.value = ''

  if (!canUploadPhoto.value) {
    clearBatchPhotoSelection(side)
    photoErrorMessage.value = '当前账号无权上传实拍图片，请使用 QC 检验员账号操作。'
    return
  }

  const validFiles = files.filter(isImageFile)
  if (files.length && validFiles.length !== files.length) {
    photoErrorMessage.value = '已忽略非图片文件；批量核验只接收箱唛实拍图片。'
  }

  clearPhotoSelection(side, false)
  setActiveBatchPhotoIndex(side, 0)
  resetBatchPhotoCropMarks(side)
  setBatchPhotoFiles(side, validFiles)

  if (validFiles[0]) {
    setSelectedPhotoFile(side, validFiles[0])
    photoPreviewRenderTick.value += 1
  }
}

async function submitTemplate() {
  errorMessage.value = ''
  successMessage.value = ''
  documentReviewMessage.value = ''

  if (!canUploadTemplate.value) {
    errorMessage.value = '当前账号无权上传箱唛资料，请使用纸箱仓管账号操作。'
    return
  }

  if (!selectedExcelFile.value || !selectedFile.value) {
    errorMessage.value = '请先选择客人 PO 箱唛 Excel 和打印 PDF。'
    return
  }

  if (!canSubmit.value) {
    errorMessage.value = '请填写客名、ITEM、合同号，并选择有效的 Excel 与 PDF 文件。'
    return
  }

  isSaving.value = true

  const requestedFactoryId = activeFactoryId.value
  const requestedFactoryName = activeFactory.value.shortName
  const requestedFactoryGeneration = factoryGeneration
  const currentFile = selectedFile.value
  const currentExcelFile = selectedExcelFile.value
  const customerName = form.customerName.trim()
  const item = form.item.trim()
  const contractNumber = form.contractNumber.trim()
  templateRequestController?.abort()
  const controller = new AbortController()
  templateRequestController = controller

  try {
    const persistedRecord = await cartonMarkApi.createTemplate({
      factoryId: requestedFactoryId,
      customerName,
      item,
      contractNumber,
      excelContract: currentExcelFile,
      printPdf: currentFile,
      signal: controller.signal,
    })
    if (isCurrentFactoryTask(requestedFactoryId, requestedFactoryGeneration) && isPanelMounted) {
      const record = mapTemplateRecord(persistedRecord, requestedFactoryName)
      allRecords.value = sortRecords([record, ...allRecords.value.filter((item) => item.id !== record.id)])
      activeCustomer.value = customerName
      documentComparisonRecord.value = record
      if (record.checkStatus === '核对通过') {
        successMessage.value = `${requestedFactoryName} · ${customerName} · ITEM：${item} 的 Excel 与打印 PDF 文字一致，已归档${record.qcReady ? '并可流转 QC' : ''}。`
      } else if (record.checkStatus === '发现差异') {
        errorMessage.value = `${requestedFactoryName} · ${customerName} · ITEM：${item} 已完成核对并归档；${record.checkStatus}，请修正打印 PDF 后重新上传。`
      } else {
        documentReviewMessage.value = `${requestedFactoryName} · ${customerName} · ITEM：${item} 已完成核对并归档；${record.checkStatus || '需复核'}，请纸箱部人工确认 Excel 与打印 PDF 内容。人工确认前不会流转 QC。`
      }
      resetForm()
    }
  } catch (error) {
    if (isCurrentFactoryTask(requestedFactoryId, requestedFactoryGeneration) && isPanelMounted && !controller.signal.aborted) {
      errorMessage.value = `Excel 与打印 PDF 核对未完成：${getApiErrorMessage(error)}`
    }
  } finally {
    if (isCurrentFactoryTask(requestedFactoryId, requestedFactoryGeneration) && isPanelMounted) {
      isSaving.value = false
    }
  }
}

async function recheckTemplateRecord(record: CartonMarkTemplateRecord) {
  errorMessage.value = ''
  successMessage.value = ''
  documentReviewMessage.value = ''

  if (!canUploadTemplate.value) {
    errorMessage.value = '当前账号无权重新核对箱唛资料，请使用纸箱仓管账号操作。'
    return
  }

  const requestedFactoryId = activeFactoryId.value
  const requestedFactoryName = activeFactory.value.shortName
  const requestedFactoryGeneration = factoryGeneration
  if (record.factoryId !== requestedFactoryId) {
    errorMessage.value = '这份箱唛资料不属于当前厂区，请切换厂区后再重新核对。'
    return
  }

  documentRecheckRequestController?.abort()
  const controller = new AbortController()
  documentRecheckRequestController = controller
  recheckingDocumentId.value = record.id

  try {
    const persistedRecord = await cartonMarkApi.recheckTemplate(record.id, requestedFactoryId, controller.signal)
    if (!isCurrentFactoryTask(requestedFactoryId, requestedFactoryGeneration) || !isPanelMounted || controller.signal.aborted) return

    const refreshedRecord = {
      ...mapTemplateRecord(persistedRecord, requestedFactoryName),
      pdfUrl: record.pdfUrl,
      fileBlob: record.fileBlob,
      excelUrl: record.excelUrl,
    }
    allRecords.value = sortRecords(allRecords.value.map((item) => item.id === record.id ? refreshedRecord : item))
    documentComparisonRecord.value = refreshedRecord

    if (refreshedRecord.checkStatus === '核对通过') {
      successMessage.value = `${requestedFactoryName} · ${refreshedRecord.customerName} · ITEM：${refreshedRecord.item} 已按最新规则重新核对；普通业务文字一致，图形内文字已忽略${refreshedRecord.qcReady ? '，可流转 QC' : ''}。`
    } else if (refreshedRecord.checkStatus === '发现差异') {
      errorMessage.value = `${requestedFactoryName} · ${refreshedRecord.customerName} · ITEM：${refreshedRecord.item} 已按最新规则重新核对；仍发现普通业务文字差异，请检查打印 PDF。`
    } else {
      documentReviewMessage.value = `${requestedFactoryName} · ${refreshedRecord.customerName} · ITEM：${refreshedRecord.item} 已按最新规则重新核对；${refreshedRecord.checkStatus || '需复核'}，请纸箱部人工确认普通业务文字。`
    }
  } catch (error) {
    if (isCurrentFactoryTask(requestedFactoryId, requestedFactoryGeneration) && isPanelMounted && !controller.signal.aborted) {
      errorMessage.value = `箱唛资料重新核对失败：${getApiErrorMessage(error)}`
    }
  } finally {
    if (isCurrentFactoryTask(requestedFactoryId, requestedFactoryGeneration) && isPanelMounted && recheckingDocumentId.value === record.id) {
      recheckingDocumentId.value = ''
    }
    if (documentRecheckRequestController === controller) {
      documentRecheckRequestController = null
    }
  }
}

async function deleteTemplateRecord(record: CartonMarkTemplateRecord) {
  errorMessage.value = ''
  successMessage.value = ''
  documentReviewMessage.value = ''

  if (!canDeleteTemplate.value) {
    errorMessage.value = '当前账号无权删除箱唛资料，请使用纸箱仓管账号操作。'
    return
  }

  const shouldDelete = typeof window === 'undefined'
    || window.confirm(`确定删除 ${record.customerName} / ITEM：${record.item} 的客人 Excel、打印 PDF 和核对记录吗？`)

  if (!shouldDelete) return

  deletingRecordId.value = record.id
  const requestedFactoryId = activeFactoryId.value
  const requestedFactoryGeneration = factoryGeneration

  try {
    await cartonMarkApi.deleteTemplate(record.id, requestedFactoryId)
  } catch (error) {
    if (!isCurrentFactoryTask(requestedFactoryId, requestedFactoryGeneration) || !isPanelMounted) return
    errorMessage.value = `箱唛资料删除失败：${getApiErrorMessage(error)}`
    deletingRecordId.value = ''
    return
  }

  if (!isCurrentFactoryTask(requestedFactoryId, requestedFactoryGeneration) || !isPanelMounted) return

  const nextRecords = sortRecords(allRecords.value.filter((item) => item.id !== record.id))

  if (record.pdfUrl) {
    URL.revokeObjectURL(record.pdfUrl)
    pdfUrls.delete(record.pdfUrl)
  }

  if (record.excelUrl) {
    URL.revokeObjectURL(record.excelUrl)
    excelUrls.delete(record.excelUrl)
  }

  allRecords.value = nextRecords

  if (photoForm.templateId === record.id) {
    photoForm.templateId = ''
  }


  if (documentComparisonRecord.value?.id === record.id) {
    documentComparisonRecord.value = null
  }

  if (
    activeCustomer.value !== ALL_CUSTOMERS
    && !nextRecords.some((item) => {
      return item.factoryId === activeFactoryId.value
        && normalizeKey(item.customerName) === normalizeKey(activeCustomer.value)
    })
  ) {
    activeCustomer.value = ALL_CUSTOMERS
  }

  successMessage.value = `${record.customerName} / ITEM：${record.item} 箱唛源文件与核对记录已归档；QC 实拍记录不会删除。`
  deletingRecordId.value = ''
}

async function submitPhoto() {
  photoErrorMessage.value = ''
  photoSuccessMessage.value = ''
  autoCheckErrorMessage.value = ''
  autoCheckResult.value = null

  if (!canUploadPhoto.value) {
    photoErrorMessage.value = '当前账号无权上传实拍图片，请使用 QC 检验员账号操作。'
    return
  }

  const template = selectedTemplateForPhoto.value

  if (!template) {
    photoErrorMessage.value = '请先选择要核对的箱唛模板。'
    return
  }

  if (!selectedFrontPhotoFile.value || !selectedSidePhotoFile.value) {
    photoErrorMessage.value = '请先选择正唛和侧唛两张图片。'
    return
  }

  if (!canSubmitPhoto.value) {
    photoErrorMessage.value = '请选择模板，并上传有效的正唛和侧唛图片。'
    return
  }

  const requestedFactoryId = activeFactoryId.value
  const requestedFactoryName = activeFactory.value.shortName
  const requestedFactoryGeneration = factoryGeneration
  if (template.factoryId !== requestedFactoryId) {
    photoErrorMessage.value = '模板所属厂区与当前厂区不一致，请重新选择。'
    return
  }

  isSavingPhoto.value = true

  const frontFile = selectedFrontPhotoFile.value
  const sideFile = selectedSidePhotoFile.value
  const frontImageUrl = createImageUrl(frontFile)
  const sideImageUrl = createImageUrl(sideFile)
  const sequence = photoRecords.value.filter((record) => {
    return normalizeKey(record.customerName) === normalizeKey(template.customerName)
      && normalizeKey(record.po) === normalizeKey(template.po)
      && normalizeKey(record.item) === normalizeKey(template.item)
      && normalizeKey(record.contractNumber) === normalizeKey(template.contractNumber)
  }).length + 1
  const photoRecord: CartonMarkPhotoRecord = {
    id: `CMP-${Date.now()}`,
    templateId: template.id,
    factoryId: requestedFactoryId,
    factoryName: requestedFactoryName,
    customerName: template.customerName,
    po: template.po,
    item: template.item,
    contractNumber: template.contractNumber,
    fileName: `${frontFile.name} / ${sideFile.name}`,
    fileSize: frontFile.size + sideFile.size,
    uploadedAt: new Date().toISOString(),
    sequence,
    status: '待复核',
    imageUrl: frontImageUrl,
    imageBlob: frontFile,
    frontFileName: frontFile.name,
    frontFileSize: frontFile.size,
    frontImageUrl,
    frontImageBlob: frontFile,
    sideFileName: sideFile.name,
    sideFileSize: sideFile.size,
    sideImageUrl,
    sideImageBlob: sideFile,
  }

  try {
    const result = await runCartonMarkAutoCheck(template, frontFile, sideFile)
    photoRecord.status = getPhotoStatusFromAutoCheck(result.summary.overall_status)
    photoRecord.autoCheckResult = result
    photoRecord.autoCheckErrorMessage = ''
    photoRecord.autoCheckedAt = new Date().toISOString()
    if (isCurrentFactoryTask(requestedFactoryId, requestedFactoryGeneration)) {
      autoCheckResult.value = result
    }
  } catch (error) {
    const message = `自动核对未完成：${getApiErrorMessage(error)}`
    photoRecord.autoCheckErrorMessage = message
    photoRecord.autoCheckedAt = new Date().toISOString()
    if (isCurrentFactoryTask(requestedFactoryId, requestedFactoryGeneration)) {
      autoCheckErrorMessage.value = message
    }
  }

  try {
    if (photoStorageMode.value === 'indexedDb') {
      await savePhotoRecordToDb(photoRecord)
    } else {
      writePhotoRecordsToLocalStorage([photoRecord, ...allPhotoRecords.value])
    }

    allPhotoRecords.value = sortPhotoRecords([photoRecord, ...allPhotoRecords.value])
    if (isCurrentFactoryTask(requestedFactoryId, requestedFactoryGeneration)) {
      resetPhotoSelection(false)
      showPhotoAutoCheck(photoRecord)
      photoSuccessMessage.value = photoRecord.autoCheckResult
        ? `${requestedFactoryName} · ${template.customerName} / ${template.po} / ${template.item} 已生成自动核对结果。`
        : `${requestedFactoryName} · ${template.customerName} / ${template.po} / ${template.item} 实拍图片已保存，可稍后重新自动核对。`
    }
  } catch {
    photoStorageMode.value = 'localStorage'
    allPhotoRecords.value = sortPhotoRecords([photoRecord, ...allPhotoRecords.value])
    writePhotoRecordsToLocalStorage(allPhotoRecords.value)
    if (isCurrentFactoryTask(requestedFactoryId, requestedFactoryGeneration)) {
      resetPhotoSelection(false)
      showPhotoAutoCheck(photoRecord)
      photoSuccessMessage.value = photoRecord.autoCheckResult
        ? `${requestedFactoryName} · ${template.customerName} / ${template.po} / ${template.item} 已生成自动核对结果。`
        : `${requestedFactoryName} · ${template.customerName} / ${template.po} / ${template.item} 实拍图片已保存，可稍后重新自动核对。`
    }
  } finally {
    if (isCurrentFactoryTask(requestedFactoryId, requestedFactoryGeneration)) {
      isSavingPhoto.value = false
    }
  }
}

function createBatchPhotoRecords(
  template: CartonMarkTemplateRecord,
  batchResult: CartonMarkBatchCheckResponse,
  factoryId: ProductionFactoryContextId,
  factoryName: string,
  frontFiles: File[],
  sideFiles: File[],
) {
  const uploadedAt = new Date().toISOString()
  const existingCount = allPhotoRecords.value.filter((record) => {
    return record.factoryId === factoryId
      && normalizeKey(record.customerName) === normalizeKey(template.customerName)
      && normalizeKey(record.po) === normalizeKey(template.po)
      && normalizeKey(record.item) === normalizeKey(template.item)
      && normalizeKey(record.contractNumber) === normalizeKey(template.contractNumber)
  }).length

  return batchResult.items.flatMap((batchItem, batchIndex): CartonMarkPhotoRecord[] => {
    const isFront = batchItem.side === 'front'
    const sourceFile = (isFront ? frontFiles : sideFiles)[batchItem.file_index]
    if (!sourceFile) return []

    const imageUrl = createImageUrl(sourceFile)
    const record: CartonMarkPhotoRecord = {
      id: `CMP-BATCH-${Date.now()}-${batchIndex}`,
      templateId: template.id,
      factoryId,
      factoryName,
      customerName: template.customerName,
      po: template.po,
      item: template.item,
      contractNumber: template.contractNumber,
      fileName: sourceFile.name,
      fileSize: sourceFile.size,
      uploadedAt,
      sequence: existingCount + batchIndex + 1,
      status: getPhotoStatusFromAutoCheck(batchItem.result.summary.overall_status),
      autoCheckResult: batchItem.result,
      autoCheckErrorMessage: '',
      autoCheckedAt: uploadedAt,
    }

    if (isFront) {
      record.imageUrl = imageUrl
      record.imageBlob = sourceFile
      record.frontFileName = sourceFile.name
      record.frontFileSize = sourceFile.size
      record.frontImageUrl = imageUrl
      record.frontImageBlob = sourceFile
    } else {
      record.sideFileName = sourceFile.name
      record.sideFileSize = sourceFile.size
      record.sideImageUrl = imageUrl
      record.sideImageBlob = sourceFile
    }

    return [record]
  })
}

async function submitBatchPhoto() {
  photoErrorMessage.value = ''
  photoSuccessMessage.value = ''
  autoCheckErrorMessage.value = ''

  if (!canUploadPhoto.value) {
    photoErrorMessage.value = '当前账号无权上传实拍图片，请使用 QC 检验员账号操作。'
    return
  }

  const template = selectedTemplateForPhoto.value
  if (!template) {
    photoErrorMessage.value = '请先选择已通过纸箱部核对的箱唛模板。'
    return
  }

  if (!canSubmitBatchPhoto.value) {
    photoErrorMessage.value = '请至少选择一张正唛或侧唛图片。'
    return
  }

  const requestedFactoryId = activeFactoryId.value
  const requestedFactoryName = activeFactory.value.shortName
  const requestedFactoryGeneration = factoryGeneration
  if (template.factoryId !== requestedFactoryId) {
    photoErrorMessage.value = '模板所属厂区与当前厂区不一致，请重新选择。'
    return
  }
  const requestedFrontFiles = [...selectedFrontBatchFiles.value]
  const requestedSideFiles = [...selectedSideBatchFiles.value]

  isSavingBatchPhoto.value = true
  try {
    const batchResult = await runCartonMarkBatchAutoCheck(
      template,
      requestedFrontFiles,
      requestedSideFiles,
    )
    const batchRecords = createBatchPhotoRecords(
      template,
      batchResult,
      requestedFactoryId,
      requestedFactoryName,
      requestedFrontFiles,
      requestedSideFiles,
    )
    if (!batchRecords.length) {
      throw new Error('批量图片与核对结果不一致，请重新选择图片后再试。')
    }

    const batchRecordIds = new Set(batchRecords.map((record) => record.id))
    const mergeBatchRecords = () => sortPhotoRecords([
      ...batchRecords,
      ...allPhotoRecords.value.filter((record) => !batchRecordIds.has(record.id)),
    ])
    try {
      if (photoStorageMode.value === 'indexedDb') {
        await Promise.all(batchRecords.map((record) => savePhotoRecordToDb(record)))
      } else {
        writePhotoRecordsToLocalStorage(mergeBatchRecords())
      }
    } catch {
      photoStorageMode.value = 'localStorage'
      writePhotoRecordsToLocalStorage(mergeBatchRecords())
    }

    const nextPhotoRecords = mergeBatchRecords()
    allPhotoRecords.value = nextPhotoRecords
    if (isCurrentFactoryTask(requestedFactoryId, requestedFactoryGeneration)) {
      const latestRecord = batchRecords.at(-1) as CartonMarkPhotoRecord
      showPhotoAutoCheck(latestRecord)
      resetBatchPhotoSelection()
      const summary = batchResult.summary
      const actionName = batchRecords.length === 1 ? '核对' : '批量核对'
      photoSuccessMessage.value = `${actionName}完成 ${batchRecords.length} 张：通过 ${summary.pass_count} 项，异常 ${summary.mismatch_count} 项，待复核 ${summary.review_count + summary.missing_count} 项。`
    }
  } catch (error) {
    if (isCurrentFactoryTask(requestedFactoryId, requestedFactoryGeneration)) {
      photoErrorMessage.value = `核对未完成：${getApiErrorMessage(error)}`
    }
  } finally {
    if (isCurrentFactoryTask(requestedFactoryId, requestedFactoryGeneration)) {
      isSavingBatchPhoto.value = false
    }
  }
}

function getPhotoStatusFromAutoCheck(status: string) {
  if (status === '核对通过' || status === '发现异常' || status === '需复核' || status === '未识别') {
    return status
  }

  return '待复核'
}

async function rerunAutoCheckForPhoto(photo: CartonMarkPhotoRecord) {
  photoErrorMessage.value = ''
  photoSuccessMessage.value = ''

  if (!canReviewPhoto.value) {
    photoErrorMessage.value = '当前账号无权重新自动核对箱唛，请使用 QC 检验员账号操作。'
    return
  }

  const requestedFactoryId = activeFactoryId.value
  const requestedFactoryGeneration = factoryGeneration
  if (photo.factoryId !== requestedFactoryId) {
    photoErrorMessage.value = '实拍记录所属厂区与当前厂区不一致，请重新选择。'
    return
  }

  const template = findTemplateForPhoto(photo)
  if (!template) {
    photoErrorMessage.value = '没有找到可用于自动核对的服务器箱唛模板。'
    showPhotoAutoCheck(photo)
    return
  }

  const frontPhoto = photo.frontImageBlob ?? photo.imageBlob
  const sidePhoto = photo.sideImageBlob
  if (!frontPhoto && !sidePhoto) {
    photoErrorMessage.value = '当前浏览器没有保存图片原件，请重新上传实拍图片后再自动核对。'
    showPhotoAutoCheck(photo)
    return
  }

  recheckingPhotoId.value = photo.id

  try {
    const result = frontPhoto && sidePhoto
      ? await runCartonMarkAutoCheck(template, frontPhoto, sidePhoto)
      : (await runCartonMarkBatchAutoCheck(
          template,
          frontPhoto ? [frontPhoto] : [],
          sidePhoto ? [sidePhoto] : [],
        )).items[0]?.result
    if (!result) {
      throw new Error('没有生成可用的批量核对结果。')
    }
    const checkedPhoto: CartonMarkPhotoRecord = {
      ...photo,
      status: getPhotoStatusFromAutoCheck(result.summary.overall_status),
      autoCheckResult: result,
      autoCheckErrorMessage: '',
      autoCheckedAt: new Date().toISOString(),
    }

    await replaceStoredPhotoRecord(checkedPhoto)
    if (isCurrentFactoryTask(requestedFactoryId, requestedFactoryGeneration)) {
      showPhotoAutoCheck(checkedPhoto)
      photoSuccessMessage.value = `${photo.customerName} / ${photo.po} / ${photo.item} 已重新生成自动核对结果。`
    }
  } catch (error) {
    const message = `自动核对未完成：${getApiErrorMessage(error)}`
    const failedPhoto: CartonMarkPhotoRecord = {
      ...photo,
      autoCheckErrorMessage: message,
      autoCheckedAt: new Date().toISOString(),
    }

    await replaceStoredPhotoRecord(failedPhoto)
    if (isCurrentFactoryTask(requestedFactoryId, requestedFactoryGeneration)) {
      showPhotoAutoCheck(failedPhoto)
      photoErrorMessage.value = message
    }
  } finally {
    if (isCurrentFactoryTask(requestedFactoryId, requestedFactoryGeneration)) {
      recheckingPhotoId.value = ''
    }
  }
}

function getPhotoStatusClass(status: string) {
  if (status === '核对通过') {
    return 'bg-green-50 text-green-700'
  }

  if (status === '发现异常') {
    return 'bg-red-50 text-red-700'
  }

  return 'bg-amber-50 text-amber-700'
}

function getAutoCheckStatusClass(status: string) {
  if (status === '核对通过') {
    return 'border-green-200 bg-green-50 text-green-700'
  }

  if (status === '发现异常') {
    return 'border-red-200 bg-red-50 text-red-700'
  }

  if (status === '未识别') {
    return 'border-slate-200 bg-slate-50 text-slate-600'
  }

  return 'border-amber-200 bg-amber-50 text-amber-700'
}

function getDocumentCheckStatusClass(status: string) {
  if (status === '核对通过') return 'border-green-200 bg-green-50 text-green-700'
  if (status === '发现差异') return 'border-red-200 bg-red-50 text-red-700'
  return 'border-amber-200 bg-amber-50 text-amber-700'
}

function getDocumentComparisonStatusLabel(status: CartonMarkDocumentContentComparison['status']) {
  if (status === 'pass') return '一致'
  if (status === 'changed') return '文字改变'
  if (status === 'missing') return 'PDF 缺失'
  if (status === 'unexpected') return 'PDF 多出'
  if (status === 'review') return '需复核'
  return '待判断'
}

function getDocumentComparisonStatusClass(status: CartonMarkDocumentContentComparison['status']) {
  if (status === 'pass') return 'bg-green-50 text-green-700'
  if (status === 'changed') return 'bg-red-50 text-red-700'
  if (status === 'missing' || status === 'unexpected') return 'bg-orange-50 text-orange-700'
  return 'bg-amber-50 text-amber-700'
}

function getComparisonStatusLabel(status: CartonMarkComparisonItem['status']) {
  if (status === 'pass') return '通过'
  if (status === 'mismatch') return '不一致'
  if (status === 'missing_expected') return 'PDF 未识别'
  if (status === 'missing_actual') return '照片未识别'
  if (status === 'review') return '需复核'
  return '待判断'
}

function getComparisonStatusClass(status: CartonMarkComparisonItem['status']) {
  if (status === 'pass') return 'bg-green-50 text-green-700'
  if (status === 'mismatch') return 'bg-red-50 text-red-700'
  if (status === 'missing_expected' || status === 'missing_actual') return 'bg-orange-50 text-orange-700'
  return 'bg-amber-50 text-amber-700'
}

function getComparisonScopeLabel(scope: CartonMarkComparisonItem['comparison_scope'] | undefined) {
  return scope === 'left_label' ? '左侧字段名' : '右侧数值'
}

function isLeftLabelComparison(item: CartonMarkComparisonItem) {
  return item.comparison_scope === 'left_label' || item.field_key.startsWith('left_label:')
}

function buildLeftLabelFeedback(comparisons: CartonMarkComparisonItem[]): LeftLabelFeedback {
  const leftLabelComparisons = comparisons.filter(isLeftLabelComparison)
  return {
    total: leftLabelComparisons.length,
    passed: leftLabelComparisons.filter((item) => item.status === 'pass').length,
    issues: leftLabelComparisons.filter((item) => item.status !== 'pass'),
  }
}

function getLeftLabelFeedbackText(feedback: LeftLabelFeedback) {
  if (feedback.total === 0) {
    return '本次结果尚未返回左侧字段名核验记录；请重新自动核对以生成反馈。'
  }

  if (feedback.issues.length === 0) {
    return `已核对 ${feedback.total} 个左侧字段名，均与 PDF 模板一致。`
  }

  return `已核对 ${feedback.total} 个左侧字段名，其中 ${feedback.passed} 个一致，${feedback.issues.length} 个需要处理。`
}

function getLeftLabelFeedbackBadge(feedback: LeftLabelFeedback) {
  if (feedback.total === 0) return '待生成反馈'
  if (feedback.issues.length === 0) return '左侧字段名一致'
  return `需处理 ${feedback.issues.length} 项`
}

function getLeftLabelFeedbackClass(feedback: LeftLabelFeedback) {
  if (feedback.total === 0) return 'border-amber-200 bg-amber-50 text-amber-800'
  if (feedback.issues.length > 0) return 'border-red-200 bg-red-50 text-red-800'
  return 'border-green-200 bg-green-50 text-green-800'
}

function getLeftLabelFeedbackBadgeClass(feedback: LeftLabelFeedback) {
  if (feedback.total === 0) return 'bg-amber-100 text-amber-800'
  if (feedback.issues.length > 0) return 'bg-red-100 text-red-800'
  return 'bg-green-100 text-green-800'
}

function formatConfidence(confidence: number) {
  return `${Math.round(confidence * 100)}%`
}

async function deletePhotoRecord(photo: CartonMarkPhotoRecord) {
  photoErrorMessage.value = ''
  photoSuccessMessage.value = ''

  if (isWarehouseWorkspace.value || !canReviewPhoto.value) {
    photoErrorMessage.value = isWarehouseWorkspace.value
      ? '纸箱部仓管端不能删除 QC 实拍记录，请到 QC 箱唛核验板块操作。'
      : '当前账号无权删除 QC 实拍记录，请使用 QC 复核账号操作。'
    return
  }

  const shouldDelete = typeof window === 'undefined'
    || window.confirm(`确定删除 ${photo.customerName} / ${photo.po} / ${photo.item} 的这次箱唛实拍记录吗？删除后可重新上传正唛和侧唛。`)

  if (!shouldDelete) return

  deletingPhotoRecordId.value = photo.id
  const nextPhotoRecords = sortPhotoRecords(allPhotoRecords.value.filter((record) => record.id !== photo.id))

  try {
    if (photoStorageMode.value === 'indexedDb') {
      await deletePhotoRecordFromDb(photo.id)
    } else {
      writePhotoRecordsToLocalStorage(nextPhotoRecords)
    }
  } catch {
    photoStorageMode.value = 'localStorage'
    writePhotoRecordsToLocalStorage(nextPhotoRecords)
  }

  for (const url of [photo.imageUrl, photo.frontImageUrl, photo.sideImageUrl]) {
    if (url) {
      revokeImageUrl(url)
    }
  }

  allPhotoRecords.value = nextPhotoRecords

  if (comparisonRecord.value?.id === photo.id) {
    comparisonRecord.value = null
    autoCheckResult.value = null
    autoCheckErrorMessage.value = ''
  }

  photoSuccessMessage.value = `${photo.customerName} / ${photo.po} / ${photo.item} 的实拍记录已删除，可以重新上传正唛和侧唛。`
  deletingPhotoRecordId.value = ''
}

async function reviewPhoto(photo: CartonMarkPhotoRecord, status: '核对通过' | '发现异常') {
  photoErrorMessage.value = ''
  photoSuccessMessage.value = ''

  if (!canReviewPhoto.value) {
    photoErrorMessage.value = '当前账号无权核对箱唛，请使用 QC 检验员账号操作。'
    return
  }

  const reviewedPhoto: CartonMarkPhotoRecord = {
    ...photo,
    status,
    reviewedAt: new Date().toISOString(),
    reviewedBy: currentUserName.value,
  }
  await replaceStoredPhotoRecord(reviewedPhoto)
  if (comparisonRecord.value?.id === photo.id) {
    showPhotoAutoCheck(reviewedPhoto)
  }

  photoSuccessMessage.value = `${photo.customerName} / ${photo.po} / ${photo.item} 已标记为${status}。`
}

function readPhotoRecordsFromLocalStorage() {
  if (typeof window === 'undefined') return []

  const rawRecords = window.localStorage.getItem(PHOTO_LOCAL_STORAGE_KEY)
  if (!rawRecords) return []

  try {
    const parsed = JSON.parse(rawRecords) as CartonMarkPhotoRecord[]
    return parsed.map((record) => hydratePhotoRecord({
      ...record,
      imageBlob: undefined,
      frontImageBlob: undefined,
      sideImageBlob: undefined,
    }))
  } catch {
    return []
  }
}

function writePhotoRecordsToLocalStorage(nextRecords: CartonMarkPhotoRecord[]) {
  if (typeof window === 'undefined') return

  const serializableRecords = nextRecords.map(({
    imageUrl,
    imageBlob,
    frontImageUrl,
    frontImageBlob,
    sideImageUrl,
    sideImageBlob,
    ...record
  }) => record)
  window.localStorage.setItem(PHOTO_LOCAL_STORAGE_KEY, JSON.stringify(serializableRecords))
}

function openTemplateDb() {
  return new Promise<IDBDatabase>((resolve, reject) => {
    if (typeof window === 'undefined' || !window.indexedDB) {
      reject(new Error('IndexedDB unavailable'))
      return
    }

    const request = window.indexedDB.open(DB_NAME, DB_VERSION)

    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(PHOTO_STORE_NAME)) {
        db.createObjectStore(PHOTO_STORE_NAME, { keyPath: 'id' })
      }
    }

    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

async function readPhotoRecordsFromDb() {
  const db = await openTemplateDb()

  return new Promise<StoredCartonMarkPhotoRecord[]>((resolve, reject) => {
    const transaction = db.transaction(PHOTO_STORE_NAME, 'readonly')
    const request = transaction.objectStore(PHOTO_STORE_NAME).getAll()

    request.onsuccess = () => resolve(request.result as StoredCartonMarkPhotoRecord[])
    request.onerror = () => reject(request.error)
    transaction.oncomplete = () => db.close()
    transaction.onerror = () => {
      db.close()
      reject(transaction.error)
    }
  })
}

async function savePhotoRecordToDb(record: CartonMarkPhotoRecord) {
  const db = await openTemplateDb()
  const { imageUrl, frontImageUrl, sideImageUrl, ...storedRecord } = record

  return new Promise<void>((resolve, reject) => {
    const transaction = db.transaction(PHOTO_STORE_NAME, 'readwrite')
    transaction.objectStore(PHOTO_STORE_NAME).put(storedRecord)

    transaction.oncomplete = () => {
      db.close()
      resolve()
    }
    transaction.onerror = () => {
      db.close()
      reject(transaction.error)
    }
  })
}

async function deletePhotoRecordFromDb(recordId: string) {
  const db = await openTemplateDb()

  return new Promise<void>((resolve, reject) => {
    const transaction = db.transaction(PHOTO_STORE_NAME, 'readwrite')
    transaction.objectStore(PHOTO_STORE_NAME).delete(recordId)

    transaction.oncomplete = () => {
      db.close()
      resolve()
    }
    transaction.onerror = () => {
      db.close()
      reject(transaction.error)
    }
  })
}

async function savePhotoRecordSnapshotToDb(record: CartonMarkPhotoRecord) {
  const db = await openTemplateDb()
  const { imageUrl, frontImageUrl, sideImageUrl, ...storedRecord } = record

  return new Promise<void>((resolve, reject) => {
    const transaction = db.transaction(PHOTO_STORE_NAME, 'readwrite')
    const store = transaction.objectStore(PHOTO_STORE_NAME)
    const request = store.get(record.id)

    request.onsuccess = () => {
      const existingRecord = request.result as StoredCartonMarkPhotoRecord | undefined
      store.put({
        ...existingRecord,
        ...storedRecord,
        imageBlob: storedRecord.imageBlob ?? existingRecord?.imageBlob,
        frontImageBlob: storedRecord.frontImageBlob ?? existingRecord?.frontImageBlob,
        sideImageBlob: storedRecord.sideImageBlob ?? existingRecord?.sideImageBlob,
      })
    }

    transaction.oncomplete = () => {
      db.close()
      resolve()
    }
    transaction.onerror = () => {
      db.close()
      reject(transaction.error)
    }
  })
}
</script>

<template>
  <!-- 箱唛模板来自后端资料库；浏览器本地存储仅保留历史现场照片。 -->
  <div class="space-y-6">
    <div class="grid items-start gap-6 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
      <div class="contents">
        <form
          v-if="isWarehouseWorkspace"
          class="order-1 rounded-lg border border-slate-200 bg-white p-6"
          @submit.prevent="submitTemplate"
        >
        <div class="flex items-start justify-between gap-4">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.2em] text-teal-700">纸箱部内容核对</p>
            <h2 class="mt-2 text-xl font-semibold tracking-tight text-slate-950">上传客人 Excel 与打印 PDF</h2>
          </div>
          <span class="rounded-full bg-teal-50 px-3 py-1 text-xs font-semibold text-teal-700">
            Excel → PDF
          </span>
        </div>
        <p
          class="mt-4 rounded-lg border px-4 py-3 text-sm"
          :class="canUploadTemplate ? 'border-teal-100 bg-teal-50 text-teal-800' : 'border-slate-200 bg-slate-50 text-slate-500'"
        >
          {{ templatePermissionHint }}
        </p>

        <div class="mt-4 grid gap-3 sm:grid-cols-3">
          <div class="rounded-lg border border-teal-100 bg-teal-50/70 px-4 py-3">
            <p class="text-xs font-semibold text-teal-700">01 客人原稿</p>
            <p class="mt-1 text-sm font-semibold text-slate-900">PO 箱唛 Excel</p>
          </div>
          <div class="rounded-lg border border-blue-100 bg-blue-50/70 px-4 py-3">
            <p class="text-xs font-semibold text-blue-700">02 打印文件</p>
            <p class="mt-1 text-sm font-semibold text-slate-900">调整排版与图案的 PDF</p>
          </div>
          <div class="rounded-lg border border-amber-100 bg-amber-50/70 px-4 py-3">
            <p class="text-xs font-semibold text-amber-700">03 只核文字</p>
            <p class="mt-1 text-sm font-semibold text-slate-900">排版与图形内文字不报差异</p>
          </div>
        </div>

        <div class="mt-6 grid gap-4 md:grid-cols-3">
          <div class="block">
            <div class="flex items-center justify-between gap-2">
              <label for="carton-mark-customer" class="text-sm font-medium text-slate-700">客名</label>
              <button
                v-if="canManageCustomers"
                type="button"
                class="rounded-md border border-teal-200 bg-teal-50 px-2.5 py-1 text-xs font-semibold text-teal-700 transition hover:bg-teal-100"
                @click="customerMutationError = ''; customerDialogOpen = true"
              >
                维护客户
              </button>
            </div>
            <select
              id="carton-mark-customer"
              v-model="form.customerName"
              aria-describedby="carton-mark-customer-help"
              class="mt-2 h-11 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition focus:border-teal-500 focus:ring-4 focus:ring-teal-50 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-500"
              :disabled="!canUploadTemplate || isLoadingCustomerOptions || !customerOptions.length"
            >
              <option value="">
                {{ isLoadingCustomerOptions ? '正在读取客户…' : customerOptions.length ? '请选择客户' : '当前厂区暂无客户' }}
              </option>
              <option
                v-for="customer in customerOptions"
                :key="customer.id"
                :value="customer.name"
              >
                {{ customer.name }}
              </option>
            </select>
            <p
              v-if="customerOptionsErrorMessage"
              id="carton-mark-customer-help"
              class="mt-1 text-xs text-red-600"
            >
              {{ customerOptionsErrorMessage }}
              <button type="button" class="font-semibold underline underline-offset-2" @click="reloadCustomerOptions">重试</button>
            </p>
            <p v-else-if="!isLoadingCustomerOptions && !customerOptions.length" id="carton-mark-customer-help" class="mt-1 text-xs text-amber-700">
              当前厂区尚未添加箱唛客户，请联系纸箱部主管或经理维护。
            </p>
            <p v-else id="carton-mark-customer-help" class="mt-1 text-xs text-slate-500">
              客名由当前厂区纸箱部主管以上维护，并作为右侧客户资料集合的归档名称。
            </p>
          </div>
          <label class="block">
            <span class="text-sm font-medium text-slate-700">ITEM</span>
            <input
              v-model.trim="form.item"
              type="text"
              class="mt-2 h-11 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition focus:border-teal-500 focus:ring-4 focus:ring-teal-50"
              placeholder="例如：203302017"
              :disabled="!canUploadTemplate"
            >
            <p class="mt-1 text-xs text-slate-500">用于区分同一客户的不同箱唛资料。</p>
          </label>
          <label class="block">
            <span class="text-sm font-medium text-slate-700">合同号</span>
            <input
              v-model.trim="form.contractNumber"
              type="text"
              class="mt-2 h-11 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition focus:border-teal-500 focus:ring-4 focus:ring-teal-50"
              placeholder="例如：HT-2026-001"
              :disabled="!canUploadTemplate"
            >
            <p class="mt-1 text-xs text-slate-500">用于同一客人、同一 ITEM 的合同归档。</p>
          </label>
        </div>

        <div class="mt-5 grid gap-4 lg:grid-cols-2">
          <div class="rounded-lg border border-dashed border-teal-300 bg-teal-50/40 p-5">
            <input
              ref="excelFileInput"
              type="file"
              accept=".xls,.xlsx,.xlsm,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              class="hidden"
              :disabled="!canUploadTemplate"
              @change="handleExcelFileChange"
            >
            <div class="flex h-full flex-col gap-4">
              <div class="flex min-w-0 items-center gap-3">
                <div class="flex size-11 shrink-0 items-center justify-center rounded-lg bg-white text-teal-700">
                  <FileSpreadsheet class="size-5" aria-hidden="true" />
                </div>
                <div class="min-w-0">
                  <p class="truncate text-sm font-semibold text-slate-900">{{ selectedExcelFileLabel }}</p>
                  <p class="mt-1 text-xs text-slate-500">客人提供的 PO 箱唛 Excel</p>
                </div>
              </div>
              <button
                type="button"
                :disabled="!canUploadTemplate"
                class="mt-auto inline-flex h-10 items-center justify-center rounded-lg border border-teal-200 bg-white px-4 text-sm font-semibold text-teal-700 transition hover:bg-teal-50 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
                @click="openExcelFilePicker"
              >
                选择 Excel 合同
              </button>
            </div>
          </div>

          <div class="rounded-lg border border-dashed border-blue-300 bg-blue-50/40 p-5">
            <input
              ref="fileInput"
              type="file"
              accept=".pdf,application/pdf"
              class="hidden"
              :disabled="!canUploadTemplate"
              @change="handleFileChange"
            >
            <div class="flex h-full flex-col gap-4">
              <div class="flex min-w-0 items-center gap-3">
                <div class="flex size-11 shrink-0 items-center justify-center rounded-lg bg-white text-blue-700">
                  <FileText class="size-5" aria-hidden="true" />
                </div>
                <div class="min-w-0">
                  <p class="truncate text-sm font-semibold text-slate-900">{{ selectedFileLabel }}</p>
                  <p class="mt-1 text-xs text-slate-500">实际用于打印箱唛的 PDF</p>
                </div>
              </div>
              <button
                type="button"
                :disabled="!canUploadTemplate"
                class="mt-auto inline-flex h-10 items-center justify-center rounded-lg border border-blue-200 bg-white px-4 text-sm font-semibold text-blue-700 transition hover:bg-blue-50 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
                @click="openFilePicker"
              >
                选择打印 PDF
              </button>
            </div>
          </div>
        </div>

        <p v-if="errorMessage" role="alert" class="mt-4 rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
          {{ errorMessage }}
        </p>
        <p v-if="documentReviewMessage" role="status" aria-live="polite" class="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          {{ documentReviewMessage }}
        </p>
        <p v-if="successMessage" aria-live="polite" class="mt-4 rounded-lg border border-green-100 bg-green-50 px-4 py-3 text-sm text-green-700">
          {{ successMessage }}
        </p>

        <button
          type="submit"
          :disabled="!canSubmit || isSaving"
          class="mt-5 inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-slate-950 px-5 text-sm font-semibold text-white transition hover:bg-teal-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          <UploadCloud class="size-4" aria-hidden="true" />
          {{ isSaving ? '正在核对文字内容' : '上传并核对 Excel 与 PDF' }}
        </button>

        <p class="mt-4 text-xs leading-5 text-slate-500">
          Excel、打印 PDF 和核对结果会保存到公司资料库；只有核对通过的 PDF 才可供 QC 现场核验。
        </p>
        </form>

        <section
          v-if="isWarehouseWorkspace && documentComparisonRecord"
          class="order-3 rounded-lg border border-slate-200 bg-white p-6 xl:col-span-2"
        >
          <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p class="text-xs font-semibold uppercase tracking-[0.18em] text-teal-700">Excel–PDF Check</p>
              <h2 class="mt-2 text-xl font-semibold tracking-tight text-slate-950">纸箱部文字内容核对结果</h2>
              <p class="mt-1 text-sm text-slate-600">
                {{ documentComparisonRecord.customerName }} · 合同：{{ documentComparisonRecord.contractNumber || '未填写' }} · ITEM：{{ documentComparisonRecord.item }}
              </p>
              <p v-if="documentComparisonRecord.documentCheckedAt" class="mt-1 text-xs text-slate-500">
                核对时间：{{ formatDate(documentComparisonRecord.documentCheckedAt) }} · 忽略空间排版及图形内文字，只比较普通业务文字
              </p>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <span
                v-if="documentCheckResult"
                class="inline-flex h-9 items-center rounded-lg border px-3 text-xs font-semibold"
                :class="getDocumentCheckStatusClass(documentCheckResult.summary.overall_status)"
              >
                {{ documentCheckResult.summary.overall_status }}
              </span>
              <button
                v-if="canUploadTemplate"
                type="button"
                :disabled="recheckingDocumentId === documentComparisonRecord.id"
                class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-amber-200 bg-white px-3 text-xs font-semibold text-amber-700 transition hover:bg-amber-50 disabled:cursor-wait disabled:opacity-60"
                @click="recheckTemplateRecord(documentComparisonRecord)"
              >
                <RefreshCw
                  class="size-3.5"
                  :class="recheckingDocumentId === documentComparisonRecord.id ? 'animate-spin' : ''"
                  aria-hidden="true"
                />
                {{ recheckingDocumentId === documentComparisonRecord.id ? '核对中' : '重新核对' }}
              </button>
              <button
                type="button"
                :disabled="downloadingDocumentKey === `${documentComparisonRecord.id}:source_excel`"
                class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-teal-200 bg-white px-3 text-xs font-semibold text-teal-700 transition hover:bg-teal-50"
                @click="openTemplateDocument(documentComparisonRecord, 'source_excel')"
              >
                <FileSpreadsheet class="size-3.5" aria-hidden="true" />
                {{ downloadingDocumentKey === `${documentComparisonRecord.id}:source_excel` ? '读取中' : '下载客人 Excel' }}
              </button>
              <button
                type="button"
                :disabled="downloadingDocumentKey === `${documentComparisonRecord.id}:print_pdf`"
                class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-blue-200 bg-white px-3 text-xs font-semibold text-blue-700 transition hover:bg-blue-50"
                @click="openTemplateDocument(documentComparisonRecord, 'print_pdf')"
              >
                <FileText class="size-3.5" aria-hidden="true" />
                {{ downloadingDocumentKey === `${documentComparisonRecord.id}:print_pdf` ? '读取中' : '查看打印 PDF' }}
              </button>
            </div>
          </div>

          <div v-if="documentCheckResult" class="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <div class="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <p class="text-xs font-semibold text-slate-500">文字一致</p>
              <p class="mt-1 text-xl font-semibold text-green-700">{{ documentCheckResult.summary.pass_count }}</p>
            </div>
            <div class="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <p class="text-xs font-semibold text-slate-500">文字改变</p>
              <p class="mt-1 text-xl font-semibold text-red-700">{{ documentCheckResult.summary.changed_count }}</p>
            </div>
            <div class="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <p class="text-xs font-semibold text-slate-500">PDF 缺失</p>
              <p class="mt-1 text-xl font-semibold text-orange-700">{{ documentCheckResult.summary.missing_count }}</p>
            </div>
            <div class="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <p class="text-xs font-semibold text-slate-500">PDF 多出</p>
              <p class="mt-1 text-xl font-semibold text-orange-700">{{ documentCheckResult.summary.unexpected_count }}</p>
            </div>
            <div class="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <p class="text-xs font-semibold text-slate-500">需人工复核</p>
              <p class="mt-1 text-xl font-semibold text-amber-700">{{ documentCheckResult.summary.review_count }}</p>
            </div>
          </div>

          <div
            v-if="documentCheckExtractionInfoMessages.length"
            class="mt-4 rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-800"
          >
            <p class="font-semibold">文件识别信息</p>
            <ul class="mt-2 space-y-1">
              <li
                v-for="(status, index) in documentCheckExtractionInfoMessages"
                :key="`document-info-${status.source}-${status.engine}-${index}`"
              >
                {{ status.source }} · {{ status.engine }}：{{ status.message }}
              </li>
            </ul>
          </div>

          <div
            v-if="documentCheckExtractionWarningMessages.length"
            class="mt-4 rounded-lg border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-800"
          >
            <p class="font-semibold">文件识别警告</p>
            <ul class="mt-2 space-y-1">
              <li
                v-for="(status, index) in documentCheckExtractionWarningMessages"
                :key="`document-warning-${status.source}-${status.engine}-${index}`"
              >
                {{ status.source }} · {{ status.engine }}：{{ status.message || '识别结果需要复核' }}
              </li>
            </ul>
          </div>

          <div v-if="documentCheckResult" class="mt-5 overflow-hidden rounded-lg border border-slate-200">
            <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-slate-50 px-4 py-3">
              <h3 class="text-sm font-semibold text-slate-950">逐项文字清单</h3>
              <span class="text-xs text-slate-500">客人 Excel 为原文 · 打印 PDF 为核对稿</span>
            </div>
            <div class="max-h-[520px] overflow-auto">
              <table class="min-w-full divide-y divide-slate-200 text-sm">
                <thead class="sticky top-0 bg-slate-50 text-left text-xs font-semibold text-slate-500">
                  <tr>
                    <th class="px-4 py-3">客人 Excel</th>
                    <th class="px-4 py-3">Excel 位置</th>
                    <th class="px-4 py-3">打印 PDF</th>
                    <th class="px-4 py-3">PDF 位置</th>
                    <th class="px-4 py-3">结果</th>
                    <th class="px-4 py-3">说明</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100 bg-white">
                  <tr
                    v-for="(item, index) in documentCheckResult.comparisons"
                    :key="`document-check-${index}-${item.expected_location}-${item.actual_location}`"
                  >
                    <td class="min-w-48 px-4 py-3 text-slate-800">{{ item.expected || '-' }}</td>
                    <td class="whitespace-nowrap px-4 py-3 text-xs text-slate-500">{{ item.expected_location || '-' }}</td>
                    <td class="min-w-48 px-4 py-3 text-slate-800">{{ item.actual || '-' }}</td>
                    <td class="whitespace-nowrap px-4 py-3 text-xs text-slate-500">{{ item.actual_location || '-' }}</td>
                    <td class="whitespace-nowrap px-4 py-3">
                      <span class="rounded-full px-2.5 py-1 text-xs font-semibold" :class="getDocumentComparisonStatusClass(item.status)">
                        {{ getDocumentComparisonStatusLabel(item.status) }}
                      </span>
                    </td>
                    <td class="min-w-48 px-4 py-3 text-xs text-slate-500">{{ item.note || '-' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <p
            v-else
            class="mt-5 rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-500"
          >
            {{ documentComparisonRecord.documentCheckErrorMessage || '这是一份旧版 PDF 资料，尚未补充客人 Excel，也没有纸箱部内容核对结果。' }}
          </p>
        </section>

        <form
          v-if="!isWarehouseWorkspace"
          class="order-1 rounded-lg border border-slate-200 bg-white p-6"
          @submit.prevent="submitBatchPhoto"
        >
          <div class="flex items-start justify-between gap-4">
            <div>
              <p class="text-xs font-semibold uppercase tracking-[0.2em] text-blue-700">QC 核验</p>
              <h2 class="mt-2 text-xl font-semibold tracking-tight text-slate-950">上传实际收到箱唛图片</h2>
            </div>
          <span class="rounded-full bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700">
            QC 实拍
          </span>
        </div>
        <p
          class="mt-4 rounded-lg border px-4 py-3 text-sm"
          :class="canUploadPhoto ? 'border-blue-100 bg-blue-50 text-blue-800' : 'border-slate-200 bg-slate-50 text-slate-500'"
        >
          {{ photoPermissionHint }}
        </p>

        <div class="mt-4 grid gap-3 rounded-lg border border-blue-100 bg-sky-50/70 p-4 text-sm text-slate-700 md:grid-cols-3">
          <div>
            <p class="font-semibold text-slate-900">1. 正对标签拍摄</p>
            <p class="mt-1 text-xs leading-5 text-slate-600">镜头尽量与箱唛平行、接近 90°；避免从侧面斜拍造成文字和表格变形。</p>
          </div>
          <div>
            <p class="font-semibold text-slate-900">2. 一张只拍一个唛</p>
            <p class="mt-1 text-xs leading-5 text-slate-600">让标签占画面约 70% 以上，四边和全部字段完整可见；不要把相邻唛、胶带或杂物拍进来。</p>
          </div>
          <div>
            <p class="font-semibold text-slate-900">3. 清晰、无反光</p>
            <p class="mt-1 text-xs leading-5 text-slate-600">建议最长边不少于 1600px，先对焦再拍；关闭直射闪光，避开阴影、褶皱和强反光。</p>
          </div>
        </div>

        <div class="mt-6 space-y-4">
            <div class="grid gap-4 md:grid-cols-[minmax(0,0.38fr)_minmax(0,0.62fr)]">
              <label class="block">
                <span class="text-sm font-medium text-slate-700">筛选客名</span>
                <select
                  v-model="photoForm.customerName"
                  class="mt-2 h-11 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-50"
                  :disabled="!templateCustomerOptions.length"
                >
                  <option :value="ALL_CUSTOMERS">全部客名</option>
                  <option
                    v-for="customer in templateCustomerOptions"
                    :key="`photo-customer-${customer.name}`"
                    :value="customer.name"
                  >
                    {{ customer.name }}（{{ customer.count }}）
                  </option>
                </select>
              </label>

              <label class="block">
                <span class="text-sm font-medium text-slate-700">选择箱唛模板</span>
                <select
                  v-model="photoForm.templateId"
                  class="mt-2 h-11 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-50"
                  :disabled="!filteredTemplateOptions.length"
                >
                  <option value="">请选择已上传模板</option>
                  <option
                    v-for="record in filteredTemplateOptions"
                    :key="`photo-template-${record.id}`"
                    :value="record.id"
                  >
                    {{ record.customerName }} / 合同：{{ record.contractNumber || '未填写' }} / ITEM：{{ record.item }} / V{{ record.version }}
                  </option>
                </select>
              </label>
            </div>

            <div
              v-if="selectedTemplateForPhoto"
              class="rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-800"
            >
              {{ selectedTemplateForPhoto.customerName }} · 合同：{{ selectedTemplateForPhoto.contractNumber || '未填写' }} · ITEM：{{ selectedTemplateForPhoto.item }}
            </div>

            <div v-else-if="records.length && !filteredTemplateOptions.length" class="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-500">
              当前客名没有已通过纸箱部 Excel–PDF 文字核对的打印 PDF，请先完成源文件核对。
            </div>

            <div v-else class="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-500">
              当前厂区还没有可流转 QC 的打印 PDF，请联系纸箱部仓管先上传 Excel 与 PDF 并完成内容核对。
            </div>
          </div>

          <p class="mt-5 rounded-lg border border-dashed border-blue-200 bg-blue-50/50 px-4 py-3 text-xs leading-5 text-slate-600">
            正唛和侧唛均可一次选择多张；系统会按你选择的类别分别核对，每张图片独立输出结果，无需文件配对。
          </p>

          <div class="mt-4 grid gap-4 md:grid-cols-2">
            <div class="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-5">
              <input
                ref="frontBatchPhotoFileInput"
                type="file"
                accept="image/*"
                multiple
                class="hidden"
                :disabled="!canUploadPhoto"
                @change="handleBatchPhotoFileChange($event, 'front')"
              >
              <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div class="flex min-w-0 items-center gap-3">
                  <div class="flex size-11 shrink-0 items-center justify-center rounded-lg bg-white text-blue-700">
                    <ImageIcon class="size-5" aria-hidden="true" />
                  </div>
                  <div class="min-w-0">
                    <p class="truncate text-sm font-semibold text-slate-900">{{ selectedFrontBatchFilesLabel }}</p>
                    <p class="mt-1 text-xs text-slate-500">正唛图片 · 可一次选择多张；一张只保留一块正唛</p>
                  </div>
                </div>
                <div class="flex shrink-0 flex-wrap items-center gap-2">
                  <button
                    v-if="selectedFrontBatchFiles.length"
                    type="button"
                    class="inline-flex h-10 items-center justify-center gap-1.5 rounded-lg border border-red-100 bg-white px-3 text-sm font-semibold text-red-600 transition hover:border-red-200 hover:bg-red-50"
                    @click="clearBatchPhotoSelection('front')"
                  >
                    <Trash2 class="size-4" aria-hidden="true" />
                    删除
                  </button>
                  <button
                    v-if="canReviewPhoto"
                    type="button"
                    :disabled="!canUploadPhoto"
                    class="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-blue-200 hover:text-blue-700 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400 disabled:hover:border-slate-200"
                    @click="openBatchPhotoFilePicker('front')"
                  >
                    {{ selectedFrontBatchFiles.length ? '重选正唛' : '选择正唛' }}
                  </button>
                </div>
              </div>
              <div
                v-if="selectedFrontPreviewUrl"
                class="mt-4 overflow-hidden rounded-lg border border-blue-100 bg-white"
              >
                <div class="relative h-56 bg-slate-100">
                  <img
                    ref="frontPreviewImage"
                    :src="selectedFrontPreviewUrl"
                    alt="正唛待对比预览"
                    class="h-full w-full select-none object-contain"
                    draggable="false"
                    @load="handlePhotoPreviewLoad"
                  >
                  <div
                    v-if="photoCropState.front.enabled"
                    class="absolute cursor-crosshair touch-none border border-blue-300/70 bg-blue-500/5"
                    :style="getPhotoCropFrameStyle('front')"
                    @pointerdown="startPhotoCrop($event, 'front')"
                    @pointermove="movePhotoCrop($event, 'front')"
                    @pointerup="finishPhotoCrop($event, 'front')"
                    @pointercancel="finishPhotoCrop($event, 'front')"
                  >
                    <div
                      class="absolute border-2 border-blue-500 bg-blue-400/20 shadow-[0_0_0_9999px_rgba(15,23,42,0.28)]"
                      :style="getPhotoCropSelectionStyle('front')"
                    />
                  </div>
                </div>
                <div class="flex flex-wrap items-center justify-between gap-2 border-t border-blue-100 px-3 py-2">
                  <div class="flex flex-wrap items-center gap-2">
                    <div class="inline-flex items-center rounded-lg border border-slate-200 bg-slate-50 p-0.5">
                      <button
                        type="button"
                        aria-label="上一张正唛"
                        :disabled="!canMoveBatchPhoto('front', -1)"
                        class="inline-flex size-7 items-center justify-center rounded-md text-slate-600 transition hover:bg-white hover:text-blue-700 disabled:cursor-not-allowed disabled:opacity-30"
                        @click="switchActiveBatchPhoto('front', -1)"
                      >
                        <ChevronLeft class="size-4" aria-hidden="true" />
                      </button>
                      <span class="min-w-20 text-center text-xs font-semibold text-slate-700">{{ getBatchPhotoPositionLabel('front') }}</span>
                      <button
                        type="button"
                        aria-label="下一张正唛"
                        :disabled="!canMoveBatchPhoto('front', 1)"
                        class="inline-flex size-7 items-center justify-center rounded-md text-slate-600 transition hover:bg-white hover:text-blue-700 disabled:cursor-not-allowed disabled:opacity-30"
                        @click="switchActiveBatchPhoto('front', 1)"
                      >
                        <ChevronRight class="size-4" aria-hidden="true" />
                      </button>
                    </div>
                    <span
                      v-if="photoCropState.front.applied || isActiveBatchPhotoCropped('front')"
                      class="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700"
                    >
                      已裁剪
                    </span>
                    <span v-else class="text-xs font-medium text-slate-500">当前照片可框选箱唛区域</span>
                  </div>
                  <div class="flex flex-wrap items-center gap-2">
                    <button
                      v-if="!photoCropState.front.enabled"
                      type="button"
                      class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-blue-200 bg-white px-3 text-xs font-semibold text-blue-700 transition hover:bg-blue-50"
                      @click="enablePhotoCrop('front')"
                    >
                      <Crop class="size-3.5" aria-hidden="true" />
                      框选箱唛区域
                    </button>
                    <template v-else>
                      <button
                        type="button"
                        class="inline-flex h-8 items-center rounded-lg border border-blue-200 bg-blue-600 px-3 text-xs font-semibold text-white transition hover:bg-blue-700"
                        @click="applyPhotoCrop('front')"
                      >
                        应用裁剪
                      </button>
                      <button
                        type="button"
                        class="inline-flex h-8 items-center rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-600 transition hover:border-slate-300"
                        @click="cancelPhotoCrop('front')"
                      >
                        取消
                      </button>
                    </template>
                  </div>
                </div>
                <p
                  v-if="photoCropState.front.errorMessage"
                  class="border-t border-red-100 bg-red-50 px-3 py-2 text-xs font-medium text-red-700"
                >
                  {{ photoCropState.front.errorMessage }}
                </p>
              </div>
            </div>

            <div class="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-5">
              <input
                ref="sideBatchPhotoFileInput"
                type="file"
                accept="image/*"
                multiple
                class="hidden"
                :disabled="!canUploadPhoto"
                @change="handleBatchPhotoFileChange($event, 'side')"
              >
              <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div class="flex min-w-0 items-center gap-3">
                  <div class="flex size-11 shrink-0 items-center justify-center rounded-lg bg-white text-blue-700">
                    <ImageIcon class="size-5" aria-hidden="true" />
                  </div>
                  <div class="min-w-0">
                    <p class="truncate text-sm font-semibold text-slate-900">{{ selectedSideBatchFilesLabel }}</p>
                    <p class="mt-1 text-xs text-slate-500">侧唛图片 · 可一次选择多张；一张只保留一块侧唛</p>
                  </div>
                </div>
                <div class="flex shrink-0 flex-wrap items-center gap-2">
                  <button
                    v-if="selectedSideBatchFiles.length"
                    type="button"
                    class="inline-flex h-10 items-center justify-center gap-1.5 rounded-lg border border-red-100 bg-white px-3 text-sm font-semibold text-red-600 transition hover:border-red-200 hover:bg-red-50"
                    @click="clearBatchPhotoSelection('side')"
                  >
                    <Trash2 class="size-4" aria-hidden="true" />
                    删除
                  </button>
                  <button
                    type="button"
                    :disabled="!canUploadPhoto"
                    class="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-blue-200 hover:text-blue-700 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400 disabled:hover:border-slate-200"
                    @click="openBatchPhotoFilePicker('side')"
                  >
                    {{ selectedSideBatchFiles.length ? '重选侧唛' : '选择侧唛' }}
                  </button>
                </div>
              </div>
              <div
                v-if="selectedSidePreviewUrl"
                class="mt-4 overflow-hidden rounded-lg border border-blue-100 bg-white"
              >
                <div class="relative h-56 bg-slate-100">
                  <img
                    ref="sidePreviewImage"
                    :src="selectedSidePreviewUrl"
                    alt="侧唛待对比预览"
                    class="h-full w-full select-none object-contain"
                    draggable="false"
                    @load="handlePhotoPreviewLoad"
                  >
                  <div
                    v-if="photoCropState.side.enabled"
                    class="absolute cursor-crosshair touch-none border border-blue-300/70 bg-blue-500/5"
                    :style="getPhotoCropFrameStyle('side')"
                    @pointerdown="startPhotoCrop($event, 'side')"
                    @pointermove="movePhotoCrop($event, 'side')"
                    @pointerup="finishPhotoCrop($event, 'side')"
                    @pointercancel="finishPhotoCrop($event, 'side')"
                  >
                    <div
                      class="absolute border-2 border-blue-500 bg-blue-400/20 shadow-[0_0_0_9999px_rgba(15,23,42,0.28)]"
                      :style="getPhotoCropSelectionStyle('side')"
                    />
                  </div>
                </div>
                <div class="flex flex-wrap items-center justify-between gap-2 border-t border-blue-100 px-3 py-2">
                  <div class="flex flex-wrap items-center gap-2">
                    <div class="inline-flex items-center rounded-lg border border-slate-200 bg-slate-50 p-0.5">
                      <button
                        type="button"
                        aria-label="上一张侧唛"
                        :disabled="!canMoveBatchPhoto('side', -1)"
                        class="inline-flex size-7 items-center justify-center rounded-md text-slate-600 transition hover:bg-white hover:text-blue-700 disabled:cursor-not-allowed disabled:opacity-30"
                        @click="switchActiveBatchPhoto('side', -1)"
                      >
                        <ChevronLeft class="size-4" aria-hidden="true" />
                      </button>
                      <span class="min-w-20 text-center text-xs font-semibold text-slate-700">{{ getBatchPhotoPositionLabel('side') }}</span>
                      <button
                        type="button"
                        aria-label="下一张侧唛"
                        :disabled="!canMoveBatchPhoto('side', 1)"
                        class="inline-flex size-7 items-center justify-center rounded-md text-slate-600 transition hover:bg-white hover:text-blue-700 disabled:cursor-not-allowed disabled:opacity-30"
                        @click="switchActiveBatchPhoto('side', 1)"
                      >
                        <ChevronRight class="size-4" aria-hidden="true" />
                      </button>
                    </div>
                    <span
                      v-if="photoCropState.side.applied || isActiveBatchPhotoCropped('side')"
                      class="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700"
                    >
                      已裁剪
                    </span>
                    <span v-else class="text-xs font-medium text-slate-500">当前照片可框选箱唛区域</span>
                  </div>
                  <div class="flex flex-wrap items-center gap-2">
                    <button
                      v-if="!photoCropState.side.enabled"
                      type="button"
                      class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-blue-200 bg-white px-3 text-xs font-semibold text-blue-700 transition hover:bg-blue-50"
                      @click="enablePhotoCrop('side')"
                    >
                      <Crop class="size-3.5" aria-hidden="true" />
                      框选箱唛区域
                    </button>
                    <template v-else>
                      <button
                        type="button"
                        class="inline-flex h-8 items-center rounded-lg border border-blue-200 bg-blue-600 px-3 text-xs font-semibold text-white transition hover:bg-blue-700"
                        @click="applyPhotoCrop('side')"
                      >
                        应用裁剪
                      </button>
                      <button
                        type="button"
                        class="inline-flex h-8 items-center rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-600 transition hover:border-slate-300"
                        @click="cancelPhotoCrop('side')"
                      >
                        取消
                      </button>
                    </template>
                  </div>
                </div>
                <p
                  v-if="photoCropState.side.errorMessage"
                  class="border-t border-red-100 bg-red-50 px-3 py-2 text-xs font-medium text-red-700"
                >
                  {{ photoCropState.side.errorMessage }}
                </p>
              </div>
            </div>
          </div>

          <p v-if="photoErrorMessage" role="alert" class="mt-4 rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
            {{ photoErrorMessage }}
          </p>
          <p v-if="photoSuccessMessage" aria-live="polite" class="mt-4 rounded-lg border border-green-100 bg-green-50 px-4 py-3 text-sm text-green-700">
            {{ photoSuccessMessage }}
          </p>
          <p v-if="autoCheckErrorMessage" class="mt-4 rounded-lg border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-700">
            {{ autoCheckErrorMessage }}
          </p>

          <button
            type="submit"
            :disabled="!canSubmitBatchPhoto || isSavingBatchPhoto"
            class="mt-5 inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-slate-950 px-5 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            <UploadCloud class="size-4" aria-hidden="true" />
            {{ photoSubmitLabel }}
          </button>

        </form>

        <section
          v-if="!isWarehouseWorkspace"
          class="order-3 rounded-lg border border-slate-200 bg-white p-6 xl:col-span-2"
        >
          <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p class="text-xs font-semibold uppercase tracking-[0.18em] text-blue-700">QC Results</p>
              <h2 class="mt-2 text-xl font-semibold tracking-tight text-slate-950">核验结果</h2>
              <p class="mt-1 text-sm text-slate-500">实拍上传记录、自动核对和证据对照集中显示在此区域。</p>
            </div>
            <span class="w-fit rounded-full bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700">{{ photoRecords.length }} 条实拍</span>
          </div>

          <div v-if="photoRecords.length" class="mt-5 space-y-3">
            <div class="flex items-center justify-between gap-3">
              <h3 class="text-sm font-semibold text-slate-950">实拍图片记录</h3>
              <span class="text-xs text-slate-500">最新：{{ latestPhotoRecord ? formatDate(latestPhotoRecord.uploadedAt) : '-' }}</span>
            </div>
            <article
              v-for="photo in photoRecords"
              :key="photo.id"
              class="flex gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3"
            >
              <div class="grid w-36 shrink-0 grid-cols-2 gap-2">
                <figure class="min-w-0">
                  <img
                    v-if="photo.frontImageUrl || photo.imageUrl"
                    :src="photo.frontImageUrl || photo.imageUrl"
                    :alt="`${photo.customerName} ${photo.po} 正唛实拍`"
                    class="h-20 w-full rounded-lg border border-slate-200 object-cover"
                  >
                  <div v-else class="flex h-20 w-full items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-400">
                    <ImageIcon class="size-5" aria-hidden="true" />
                  </div>
                  <figcaption class="mt-1 truncate text-center text-[11px] font-medium text-slate-500">正唛</figcaption>
                </figure>
                <figure class="min-w-0">
                  <img
                    v-if="photo.sideImageUrl"
                    :src="photo.sideImageUrl"
                    :alt="`${photo.customerName} ${photo.po} 侧唛实拍`"
                    class="h-20 w-full rounded-lg border border-slate-200 object-cover"
                  >
                  <div v-else class="flex h-20 w-full items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-400">
                    <ImageIcon class="size-5" aria-hidden="true" />
                  </div>
                  <figcaption class="mt-1 truncate text-center text-[11px] font-medium text-slate-500">侧唛</figcaption>
                </figure>
              </div>
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-2">
                  <p class="truncate text-sm font-semibold text-slate-950">{{ photo.customerName }}</p>
                  <span
                    class="rounded-full px-2 py-0.5 text-xs font-semibold"
                    :class="getPhotoStatusClass(photo.status)"
                  >
                    {{ photo.status }}
                  </span>
                </div>
                <p class="mt-1 text-xs text-slate-600">合同：{{ photo.contractNumber || '未填写' }} · ITEM：{{ photo.item }}</p>
                <p class="mt-1 truncate text-xs text-slate-500">
                  正唛：{{ photo.frontFileName ?? photo.fileName }} · 侧唛：{{ photo.sideFileName ?? '未上传' }}
                </p>
                <p class="mt-1 text-xs text-slate-500">第 {{ photo.sequence }} 次上传 · {{ formatDate(photo.uploadedAt) }}</p>
                <p v-if="photo.reviewedAt" class="mt-1 text-xs text-slate-500">
                  核对：{{ photo.reviewedBy }} · {{ formatDate(photo.reviewedAt) }}
                </p>
                <p
                  class="mt-1 line-clamp-2 text-xs"
                  :class="photo.autoCheckErrorMessage && !photo.autoCheckResult ? 'text-amber-700' : 'text-slate-500'"
                >
                  {{ getPhotoAutoCheckSummary(photo) }}
                </p>
                <div class="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-blue-200 bg-white px-3 text-xs font-semibold text-blue-700 transition hover:bg-blue-50"
                    @click="showPhotoAutoCheck(photo)"
                  >
                    <Eye class="size-3.5" aria-hidden="true" />
                    查看核验
                  </button>
                  <button
                    v-if="canReviewPhoto"
                    type="button"
                    :disabled="recheckingPhotoId === photo.id"
                    class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-indigo-200 bg-white px-3 text-xs font-semibold text-indigo-700 transition hover:bg-indigo-50 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
                    @click="rerunAutoCheckForPhoto(photo)"
                  >
                    <RefreshCw
                      class="size-3.5"
                      :class="recheckingPhotoId === photo.id ? 'animate-spin' : ''"
                      aria-hidden="true"
                    />
                    {{ recheckingPhotoId === photo.id ? '重算中' : '重新自动核对' }}
                  </button>
                  <button
                    v-if="canReviewPhoto"
                    type="button"
                    class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-green-200 bg-white px-3 text-xs font-semibold text-green-700 transition hover:bg-green-50"
                    @click="reviewPhoto(photo, '核对通过')"
                  >
                    <CheckCircle2 class="size-3.5" aria-hidden="true" />
                    核对通过
                  </button>
                  <button
                    v-if="canReviewPhoto"
                    type="button"
                    class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-red-200 bg-white px-3 text-xs font-semibold text-red-700 transition hover:bg-red-50"
                    @click="reviewPhoto(photo, '发现异常')"
                  >
                    <XCircle class="size-3.5" aria-hidden="true" />
                    标记异常
                  </button>
                  <button
                    type="button"
                    :disabled="deletingPhotoRecordId === photo.id"
                    class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-600 transition hover:border-red-200 hover:bg-red-50 hover:text-red-700 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
                    @click="deletePhotoRecord(photo)"
                  >
                    <Trash2 class="size-3.5" aria-hidden="true" />
                    {{ deletingPhotoRecordId === photo.id ? '删除中' : '删除记录' }}
                  </button>
                </div>
              </div>
            </article>
          </div>

          <section
            v-if="comparisonRecord"
            class="mt-6 border-t border-slate-200 pt-6"
          >
            <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-blue-700">AUTO CHECK</p>
                <h3 class="mt-2 text-lg font-semibold tracking-tight text-slate-950">自动核对结果</h3>
                <p class="mt-1 text-xs text-slate-600">
                  {{ comparisonRecord.customerName }} · 合同：{{ comparisonRecord.contractNumber || '未填写' }} · ITEM：{{ comparisonRecord.item }}
                </p>
                <p v-if="comparisonRecord.autoCheckedAt" class="mt-1 text-xs text-slate-500">
                  自动核对：{{ formatDate(comparisonRecord.autoCheckedAt) }}
                </p>
              </div>
              <div class="flex flex-wrap items-center gap-2">
                <span
                  v-if="autoCheckResult"
                  class="inline-flex h-9 items-center rounded-lg border px-3 text-xs font-semibold"
                  :class="getAutoCheckStatusClass(autoCheckResult.summary.overall_status)"
                >
                  {{ autoCheckResult.summary.overall_status }}
                </span>
                <button
                  v-if="comparisonTemplate"
                  type="button"
                  :disabled="downloadingDocumentKey === `${comparisonTemplate.id}:print_pdf`"
                  class="inline-flex h-9 w-fit items-center justify-center gap-1.5 rounded-lg border border-blue-200 bg-white px-3 text-xs font-semibold text-blue-700 transition hover:bg-blue-50"
                  @click="openTemplateDocument(comparisonTemplate, 'print_pdf', autoCheckMatchedPage)"
                >
                  <FileText class="size-3.5" aria-hidden="true" />
                  {{ downloadingDocumentKey === `${comparisonTemplate.id}:print_pdf` ? '读取中' : (autoCheckMatchedPage ? `打开 PDF 第 ${autoCheckMatchedPage} 页` : '打开 PDF 模板') }}
                </button>
              </div>
            </div>

            <div
              v-if="autoCheckResult"
              class="mt-4 grid gap-3 sm:grid-cols-4"
            >
              <div class="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <p class="text-xs font-semibold text-slate-500">通过</p>
                <p class="mt-1 text-xl font-semibold text-green-700">{{ autoCheckResult.summary.pass_count }}</p>
              </div>
              <div class="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <p class="text-xs font-semibold text-slate-500">不一致</p>
                <p class="mt-1 text-xl font-semibold text-red-700">{{ autoCheckResult.summary.mismatch_count }}</p>
              </div>
              <div class="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <p class="text-xs font-semibold text-slate-500">缺失识别</p>
                <p class="mt-1 text-xl font-semibold text-orange-700">{{ autoCheckResult.summary.missing_count }}</p>
              </div>
              <div class="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <p class="text-xs font-semibold text-slate-500">需复核</p>
                <p class="mt-1 text-xl font-semibold text-amber-700">{{ autoCheckResult.summary.review_count }}</p>
              </div>
            </div>

            <div
              v-if="autoCheckErrorMessage && !autoCheckResult"
              class="mt-4 rounded-lg border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-700"
            >
              {{ autoCheckErrorMessage }}
            </div>
            <div
              v-else-if="!autoCheckResult"
              class="mt-4 rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-500"
            >
              自动核对结果尚未生成，请选择 PDF 模板并上传正唛、侧唛两张照片后开始自动核对。
            </div>

            <div
              v-if="autoCheckResult"
              class="mt-5 space-y-5"
            >
              <div
                v-if="autoCheckExtractionInfoMessages.length"
                class="rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-800"
              >
                <p class="font-semibold">页面匹配信息</p>
                <ul class="mt-2 space-y-1">
                  <li
                    v-for="(status, index) in autoCheckExtractionInfoMessages"
                    :key="`photo-info-${status.source}-${status.engine}-${index}`"
                  >
                    {{ status.source }} · {{ status.engine }}：{{ status.message }}
                  </li>
                </ul>
              </div>

              <div
                v-if="autoCheckExtractionWarningMessages.length"
                class="rounded-lg border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-800"
              >
                <p class="font-semibold">识别警告</p>
                <ul class="mt-2 space-y-1">
                  <li
                    v-for="(status, index) in autoCheckExtractionWarningMessages"
                    :key="`photo-warning-${status.source}-${status.engine}-${index}`"
                  >
                    {{ status.source }} · {{ status.engine }}：{{ status.message || '识别结果需要复核' }}
                  </li>
                </ul>
              </div>

              <section class="rounded-lg border border-slate-200">
                <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3">
                  <h4 class="text-sm font-semibold text-slate-950">正唛字段核对</h4>
                  <span class="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700">打印 PDF 长框 vs QC 现场正唛</span>
                </div>
                <div class="border-b px-4 py-3" :class="getLeftLabelFeedbackClass(frontLeftLabelFeedback)">
                  <div class="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <p class="text-xs font-semibold">左侧字段名反馈</p>
                      <p class="mt-1 text-xs">{{ getLeftLabelFeedbackText(frontLeftLabelFeedback) }}</p>
                    </div>
                    <div class="flex items-center gap-2">
                      <span class="rounded-full px-2.5 py-1 text-xs font-semibold" :class="getLeftLabelFeedbackBadgeClass(frontLeftLabelFeedback)">
                        {{ getLeftLabelFeedbackBadge(frontLeftLabelFeedback) }}
                      </span>
                      <button
                        v-if="frontLeftLabelFeedback.total === 0"
                        type="button"
                        :disabled="recheckingPhotoId === comparisonRecord.id"
                        class="rounded-lg border border-amber-300 bg-white px-2.5 py-1 text-xs font-semibold text-amber-800 transition hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-60"
                        @click="rerunAutoCheckForPhoto(comparisonRecord)"
                      >
                        {{ recheckingPhotoId === comparisonRecord.id ? '核对中' : '重新自动核对' }}
                      </button>
                    </div>
                  </div>
                  <ul v-if="frontLeftLabelFeedback.issues.length" class="mt-2 space-y-1 text-xs">
                    <li v-for="item in frontLeftLabelFeedback.issues" :key="`front-left-feedback-${item.field_key}`">
                      {{ item.label }}：PDF「{{ item.expected || '未识别' }}」；照片「{{ item.actual || '未识别' }}」；{{ getComparisonStatusLabel(item.status) }}。
                    </li>
                  </ul>
                </div>
                <div
                  v-if="frontAutoCheckComparisons.length"
                  class="overflow-x-auto"
                >
                  <table class="min-w-full divide-y divide-slate-200 text-sm">
                    <thead class="bg-slate-50 text-left text-xs font-semibold text-slate-500">
                      <tr>
                        <th class="px-4 py-3">字段</th>
                        <th class="px-4 py-3">内容</th>
                        <th class="px-4 py-3">PDF 模板</th>
                        <th class="px-4 py-3">照片识别</th>
                        <th class="px-4 py-3">结果</th>
                        <th class="px-4 py-3">置信度</th>
                        <th class="px-4 py-3">说明</th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100 bg-white">
                      <tr
                        v-for="item in frontAutoCheckComparisons"
                        :key="`front-check-${item.field_key}`"
                      >
                        <td class="whitespace-nowrap px-4 py-3 font-semibold text-slate-900">{{ item.label }}</td>
                        <td class="whitespace-nowrap px-4 py-3 text-xs font-medium text-slate-600">{{ getComparisonScopeLabel(item.comparison_scope) }}</td>
                        <td class="min-w-40 px-4 py-3 text-slate-700">{{ item.expected || '-' }}</td>
                        <td class="min-w-40 px-4 py-3 text-slate-700">{{ item.actual || '-' }}</td>
                        <td class="whitespace-nowrap px-4 py-3">
                          <span
                            class="rounded-full px-2.5 py-1 text-xs font-semibold"
                            :class="getComparisonStatusClass(item.status)"
                          >
                            {{ getComparisonStatusLabel(item.status) }}
                          </span>
                        </td>
                        <td class="whitespace-nowrap px-4 py-3 text-xs text-slate-500">{{ formatConfidence(item.confidence) }}</td>
                        <td class="min-w-48 px-4 py-3 text-xs text-slate-500">{{ item.note || '-' }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <p
                  v-else
                  class="px-4 py-4 text-sm text-slate-500"
                >
                  正唛暂未识别到可核对字段。
                </p>
              </section>

              <section class="rounded-lg border border-slate-200">
                <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3">
                  <h4 class="text-sm font-semibold text-slate-950">侧唛字段核对</h4>
                  <span class="rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-semibold text-indigo-700">打印 PDF 短框 vs QC 现场侧唛</span>
                </div>
                <div class="border-b px-4 py-3" :class="getLeftLabelFeedbackClass(sideLeftLabelFeedback)">
                  <div class="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <p class="text-xs font-semibold">左侧字段名反馈</p>
                      <p class="mt-1 text-xs">{{ getLeftLabelFeedbackText(sideLeftLabelFeedback) }}</p>
                    </div>
                    <div class="flex items-center gap-2">
                      <span class="rounded-full px-2.5 py-1 text-xs font-semibold" :class="getLeftLabelFeedbackBadgeClass(sideLeftLabelFeedback)">
                        {{ getLeftLabelFeedbackBadge(sideLeftLabelFeedback) }}
                      </span>
                      <button
                        v-if="sideLeftLabelFeedback.total === 0"
                        type="button"
                        :disabled="recheckingPhotoId === comparisonRecord.id"
                        class="rounded-lg border border-amber-300 bg-white px-2.5 py-1 text-xs font-semibold text-amber-800 transition hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-60"
                        @click="rerunAutoCheckForPhoto(comparisonRecord)"
                      >
                        {{ recheckingPhotoId === comparisonRecord.id ? '核对中' : '重新自动核对' }}
                      </button>
                    </div>
                  </div>
                  <ul v-if="sideLeftLabelFeedback.issues.length" class="mt-2 space-y-1 text-xs">
                    <li v-for="item in sideLeftLabelFeedback.issues" :key="`side-left-feedback-${item.field_key}`">
                      {{ item.label }}：PDF「{{ item.expected || '未识别' }}」；照片「{{ item.actual || '未识别' }}」；{{ getComparisonStatusLabel(item.status) }}。
                    </li>
                  </ul>
                </div>
                <div
                  v-if="sideAutoCheckComparisons.length"
                  class="overflow-x-auto"
                >
                  <table class="min-w-full divide-y divide-slate-200 text-sm">
                    <thead class="bg-slate-50 text-left text-xs font-semibold text-slate-500">
                      <tr>
                        <th class="px-4 py-3">字段</th>
                        <th class="px-4 py-3">内容</th>
                        <th class="px-4 py-3">PDF 模板</th>
                        <th class="px-4 py-3">照片识别</th>
                        <th class="px-4 py-3">结果</th>
                        <th class="px-4 py-3">置信度</th>
                        <th class="px-4 py-3">说明</th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100 bg-white">
                      <tr
                        v-for="item in sideAutoCheckComparisons"
                        :key="`side-check-${item.field_key}`"
                      >
                        <td class="whitespace-nowrap px-4 py-3 font-semibold text-slate-900">{{ item.label }}</td>
                        <td class="whitespace-nowrap px-4 py-3 text-xs font-medium text-slate-600">{{ getComparisonScopeLabel(item.comparison_scope) }}</td>
                        <td class="min-w-40 px-4 py-3 text-slate-700">{{ item.expected || '-' }}</td>
                        <td class="min-w-40 px-4 py-3 text-slate-700">{{ item.actual || '-' }}</td>
                        <td class="whitespace-nowrap px-4 py-3">
                          <span
                            class="rounded-full px-2.5 py-1 text-xs font-semibold"
                            :class="getComparisonStatusClass(item.status)"
                          >
                            {{ getComparisonStatusLabel(item.status) }}
                          </span>
                        </td>
                        <td class="whitespace-nowrap px-4 py-3 text-xs text-slate-500">{{ formatConfidence(item.confidence) }}</td>
                        <td class="min-w-48 px-4 py-3 text-xs text-slate-500">{{ item.note || '-' }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <p
                  v-else
                  class="px-4 py-4 text-sm text-slate-500"
                >
                  侧唛暂未识别到可核对字段。
                </p>
              </section>
            </div>

            <details class="mt-5 rounded-lg border border-slate-200 bg-white">
              <summary class="cursor-pointer px-4 py-3 text-sm font-semibold text-slate-700">查看 PDF 与实拍图片证据</summary>
              <div class="space-y-5 border-t border-slate-200 px-4 py-4">
                <section>
                  <div class="flex flex-wrap items-center justify-between gap-2">
                    <h4 class="text-sm font-semibold text-slate-950">正唛对照</h4>
                    <span class="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700">PDF 中较长的大框</span>
                  </div>

                  <div class="mt-3 grid gap-4 xl:grid-cols-2">
                    <figure class="min-w-0">
                      <figcaption class="mb-2 text-xs font-semibold text-slate-700">PDF 模板</figcaption>
                      <div class="overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
                        <object
                          v-if="comparisonPdfPreviewUrl"
                          :data="comparisonPdfPreviewUrl"
                          type="application/pdf"
                          class="h-72 w-full"
                        >
                          <div class="flex h-72 items-center justify-center px-4 text-center text-sm text-slate-500">
                            当前浏览器无法预览 PDF
                          </div>
                        </object>
                        <div
                          v-else
                          class="flex h-72 items-center justify-center px-4 text-center text-sm text-slate-500"
                        >
                          {{ comparisonPdfMissingMessage }}
                        </div>
                      </div>
                    </figure>

                    <figure class="min-w-0">
                      <figcaption class="mb-2 text-xs font-semibold text-slate-700">QC 现场实拍正唛</figcaption>
                      <div class="flex min-h-72 items-center justify-center overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
                        <img
                          v-if="comparisonRecord.frontImageUrl || comparisonRecord.imageUrl"
                          :src="comparisonRecord.frontImageUrl || comparisonRecord.imageUrl"
                          :alt="`${comparisonRecord.customerName} 正唛实拍对照`"
                          class="max-h-[520px] w-full object-contain"
                        >
                      </div>
                    </figure>
                  </div>
                </section>

                <section class="border-t border-slate-200 pt-5">
                  <div class="flex flex-wrap items-center justify-between gap-2">
                    <h4 class="text-sm font-semibold text-slate-950">侧唛对照</h4>
                    <span class="rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-semibold text-indigo-700">PDF 中较短的小框</span>
                  </div>

                  <div class="mt-3 grid gap-4 xl:grid-cols-2">
                    <figure class="min-w-0">
                      <figcaption class="mb-2 text-xs font-semibold text-slate-700">PDF 模板</figcaption>
                      <div class="overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
                        <object
                          v-if="comparisonPdfPreviewUrl"
                          :data="comparisonPdfPreviewUrl"
                          type="application/pdf"
                          class="h-72 w-full"
                        >
                          <div class="flex h-72 items-center justify-center px-4 text-center text-sm text-slate-500">
                            当前浏览器无法预览 PDF
                          </div>
                        </object>
                        <div
                          v-else
                          class="flex h-72 items-center justify-center px-4 text-center text-sm text-slate-500"
                        >
                          {{ comparisonPdfMissingMessage }}
                        </div>
                      </div>
                    </figure>

                    <figure class="min-w-0">
                      <figcaption class="mb-2 text-xs font-semibold text-slate-700">QC 现场实拍侧唛</figcaption>
                      <div class="flex min-h-72 items-center justify-center overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
                        <img
                          v-if="comparisonRecord.sideImageUrl"
                          :src="comparisonRecord.sideImageUrl"
                          :alt="`${comparisonRecord.customerName} 侧唛实拍对照`"
                          class="max-h-[520px] w-full object-contain"
                        >
                      </div>
                    </figure>
                  </div>
                </section>
              </div>
            </details>
          </section>
        </section>
      </div>

      <section class="order-2 self-start rounded-lg border border-slate-200 bg-white p-6 xl:col-start-2 xl:row-start-1">
        <div class="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <h2 class="text-xl font-semibold tracking-tight text-slate-950">{{ isWarehouseWorkspace ? '客户箱唛集合' : '已上传箱唛资料库' }}</h2>
            <p class="mt-1 text-sm text-slate-500">
              {{ isWarehouseWorkspace ? '按客户查看客人 Excel、打印 PDF 与纸箱部文字核对记录。' : '只选用纸箱部核对通过的打印 PDF，与 QC 现场照片核验' }}
            </p>
          </div>
          <input
            v-model.trim="searchKeyword"
            type="search"
            class="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm text-slate-900 outline-none transition focus:border-teal-500 focus:ring-4 focus:ring-teal-50 md:w-56"
            :placeholder="isWarehouseWorkspace ? '搜索客名 / ITEM / 合同号' : '搜索客名 / 合同号 / ITEM'"
          >
        </div>

        <div v-if="isWarehouseWorkspace" class="mt-5 grid gap-3 sm:grid-cols-2">
          <button
            v-for="customer in visibleCustomerGroups"
            :key="customer.name"
            type="button"
            class="rounded-lg border p-4 text-left transition"
            :class="activeCustomer === customer.name ? 'border-teal-500 bg-teal-50 shadow-sm' : 'border-slate-200 bg-slate-50 hover:border-teal-200 hover:bg-teal-50/50'"
            @click="activeCustomer = customer.name"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <p class="truncate text-sm font-semibold text-slate-950">{{ customer.name }}</p>
                <p class="mt-1 text-xs text-slate-500">{{ customer.count }} 份箱唛文件链路</p>
              </div>
              <Eye class="size-4 shrink-0 text-teal-700" aria-hidden="true" />
            </div>
            <p class="mt-3 text-xs text-slate-500">最近上传：{{ formatDate(customer.latestAt) }}</p>
          </button>
          <p v-if="!visibleCustomerGroups.length" class="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-5 text-sm text-slate-500 sm:col-span-2">
            没有匹配的客户箱唛资料。
          </p>
        </div>

        <div v-else class="mt-5 flex gap-2 overflow-x-auto pb-1">
          <button
            type="button"
            class="shrink-0 rounded-lg border px-3 py-2 text-sm font-semibold transition"
            :class="activeCustomer === ALL_CUSTOMERS ? 'border-teal-500 bg-teal-50 text-teal-700' : 'border-slate-200 bg-white text-slate-600 hover:border-teal-200'"
            @click="activeCustomer = ALL_CUSTOMERS"
          >
            全部 {{ records.length }}
          </button>
          <button
            v-for="customer in customerGroups"
            :key="customer.name"
            type="button"
            class="shrink-0 rounded-lg border px-3 py-2 text-sm font-semibold transition"
            :class="activeCustomer === customer.name ? 'border-teal-500 bg-teal-50 text-teal-700' : 'border-slate-200 bg-white text-slate-600 hover:border-teal-200'"
            @click="activeCustomer = customer.name"
          >
            {{ customer.name }} {{ customer.count }}
          </button>
        </div>

        <div class="mt-5 max-h-[520px] overflow-y-auto pr-1">
          <div v-if="isLoading" class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
            正在读取资料库
          </div>

          <div v-else-if="isWarehouseWorkspace && activeCustomer === ALL_CUSTOMERS" class="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-10 text-center">
            <p class="text-sm font-semibold text-slate-700">请选择一个客户</p>
            <p class="mt-2 text-sm text-slate-500">右侧会展示该客户的客人 Excel、打印 PDF 和逐项核对结果。</p>
          </div>

          <div v-else-if="filteredRecords.length" class="space-y-3">
          <div v-if="isWarehouseWorkspace" class="flex items-center justify-between gap-3">
            <p class="text-sm font-semibold text-slate-950">{{ activeCustomer }} · 箱唛文件与核对记录</p>
            <span class="rounded-full bg-teal-50 px-3 py-1 text-xs font-semibold text-teal-700">{{ filteredRecords.length }} 份</span>
          </div>
          <article
            v-for="record in filteredRecords"
            :key="record.id"
            class="rounded-lg border border-slate-200 bg-slate-50 p-4"
          >
            <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <h3 class="text-base font-semibold text-slate-950">{{ record.customerName }}</h3>
                  <span class="rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-slate-600">
                    V{{ record.version }}
                  </span>
                </div>
                <p class="mt-2 text-sm text-slate-600">
                  <template v-if="isWarehouseWorkspace">ITEM：{{ record.item }} · 合同：{{ record.contractNumber || '未填写' }}</template>
                  <template v-else>合同：{{ record.contractNumber || '未填写' }} · ITEM：{{ record.item }}</template>
                </p>
                <p v-if="isWarehouseWorkspace" class="mt-2 truncate text-sm text-slate-500">
                  客人 Excel：{{ record.excelFileName || '旧资料未上传' }}<template v-if="record.excelFileSize"> · {{ formatFileSize(record.excelFileSize) }}</template>
                </p>
                <p class="truncate text-sm text-slate-500" :class="isWarehouseWorkspace ? 'mt-1' : 'mt-2'">
                  打印 PDF：{{ record.fileName }} · {{ formatFileSize(record.fileSize) }}
                </p>
              </div>

              <div class="flex shrink-0 flex-wrap items-center gap-2 text-sm">
                <span
                  class="rounded-full border px-3 py-1 font-semibold"
                  :class="record.documentCheckResult ? getDocumentCheckStatusClass(record.documentCheckResult.summary.overall_status) : 'border-slate-200 bg-slate-100 text-slate-600'"
                >
                  {{ record.documentCheckResult?.summary.overall_status || '待补 Excel 核对' }}
                </span>
                <button
                  v-if="isWarehouseWorkspace"
                  type="button"
                  :disabled="downloadingDocumentKey === `${record.id}:source_excel`"
                  class="inline-flex items-center gap-1 rounded-lg border border-teal-200 bg-white px-3 py-2 font-semibold text-teal-700 transition hover:bg-teal-50"
                  @click="openTemplateDocument(record, 'source_excel')"
                >
                  <FileSpreadsheet class="size-4" aria-hidden="true" />
                  {{ downloadingDocumentKey === `${record.id}:source_excel` ? '读取中' : '客人 Excel' }}
                </button>
                <button
                  type="button"
                  :disabled="downloadingDocumentKey === `${record.id}:print_pdf`"
                  class="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-2 font-semibold text-slate-700 transition hover:border-teal-200 hover:text-teal-700"
                  @click="openTemplateDocument(record, 'print_pdf')"
                >
                  <FileText class="size-4" aria-hidden="true" />
                  {{ downloadingDocumentKey === `${record.id}:print_pdf` ? '读取中' : '打印 PDF' }}
                </button>
                <button
                  v-if="isWarehouseWorkspace"
                  type="button"
                  class="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-2 font-semibold text-slate-700 transition hover:border-teal-200 hover:text-teal-700"
                  @click="showDocumentCheck(record)"
                >
                  <Eye class="size-4" aria-hidden="true" />
                  查看核对
                </button>
                <button
                  v-if="canDeleteTemplate"
                  type="button"
                  :disabled="deletingRecordId === record.id"
                  class="inline-flex items-center gap-1 rounded-lg border border-red-200 bg-white px-3 py-2 font-semibold text-red-600 transition hover:bg-red-50 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-400"
                  @click="deleteTemplateRecord(record)"
                >
                  <Trash2 class="size-4" aria-hidden="true" />
                  {{ deletingRecordId === record.id ? '删除中' : '删除' }}
                </button>
              </div>
            </div>
            <div class="mt-4 grid gap-3 border-t border-slate-200 pt-4 text-xs text-slate-500 sm:grid-cols-5">
              <span>客名：{{ record.customerName }}</span>
              <span>ITEM：{{ record.item }}</span>
              <span>合同：{{ record.contractNumber || '未填写' }}</span>
              <span>上传：{{ formatDate(record.uploadedAt) }}</span>
              <span>纸箱部核对：{{ record.documentCheckedAt ? formatDate(record.documentCheckedAt) : '待补' }}</span>
            </div>
          </article>
        </div>

          <div v-else class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-10 text-center">
            <p class="text-sm font-semibold text-slate-700">暂无箱唛资料</p>
            <p class="mt-2 text-sm text-slate-500">上传后会按客名进入对应资料库。</p>
          </div>
        </div>
      </section>
    </div>
    <CartonMarkCustomerDialog
      :open="customerDialogOpen"
      :customers="customerOptions"
      :busy="customerMutationBusy"
      :factory-name="activeFactory.shortName"
      :external-error="customerMutationError"
      @close="customerDialogOpen = false"
      @create="createManagedCustomer"
      @update="updateManagedCustomer"
      @delete="deleteManagedCustomer"
    />
  </div>
</template>
