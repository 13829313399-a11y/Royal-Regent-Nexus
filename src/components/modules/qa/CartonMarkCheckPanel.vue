<script setup lang="ts">
import { Camera, CheckCircle2, ChevronLeft, ChevronRight, Crop, Eye, FileSpreadsheet, FileText, Image as ImageIcon, RefreshCw, RotateCcw, RotateCw, Trash2, UploadCloud, XCircle } from '@lucide/vue'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import {
  cartonMarkApi,
  type CartonMarkAsset,
  type CartonMarkQcRecord,
  type CartonMarkQcSubmission,
  type CartonMarkAutoCheckResponse,
  type CartonMarkComparisonItem,
  type CartonMarkCustomer,
  type CartonMarkDocumentContentComparison,
  type CartonMarkDocumentContentCheckResponse,
  type CartonMarkTemplateDocumentKind,
  type CartonMarkTemplateRecordResponse,
} from '@/api/cartonMark'
import CartonMarkCustomerDialog from '@/components/modules/qa/CartonMarkCustomerDialog.vue'
import CartonMarkCustomerRecognition from '@/components/modules/qa/CartonMarkCustomerRecognition.vue'
import type { ProductionFactoryContextId } from '@/data/enterpriseMock'
import { getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'
import {
  clampRatio,
  cropImageBlob,
  getContainedImageFrame,
  isUsableCropSelection,
  normalizeCropSelection,
  rotateImageBlob,
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
  manualReleased: boolean
  manualReleaseReason: string
  manualReleaseSourceStatus: string
  manualReleasedByName: string
  manualReleasedAt: string
}

interface CartonMarkPhotoRecord {
  server?: CartonMarkQcRecord
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
  note: '',
  correctsRecordId: '',
})

const allRecords = ref<CartonMarkTemplateRecord[]>([])
const allPhotoRecords = ref<CartonMarkPhotoRecord[]>([])
const customerOptions = ref<CartonMarkCustomer[]>([])
const selectedFile = ref<File | null>(null)
const selectedExcelFile = ref<File | null>(null)
const selectedExcelAssetId = ref('')
const selectedPdfAssetId = ref('')
const librarySelectionGeneration = { pdf: 0, excel: 0 }
let libraryMetadataGeneration = 0
const pendingLibraryReads = reactive({ pdf: false, excel: false })
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
const frontCameraInput = ref<HTMLInputElement | null>(null)
const sideCameraInput = ref<HTMLInputElement | null>(null)
const photoFormPanel = ref<HTMLFormElement | null>(null)
const comparisonRecord = ref<CartonMarkPhotoRecord | null>(null)
const comparisonReviewSources = computed(() => {
  const rows = comparisonRecord.value?.server?.template_snapshot.source_assets
  return Array.isArray(rows) ? rows.filter(row => typeof row?.id === 'string' && typeof row?.file_name === 'string') as { id: string; file_name: string }[] : []
})
async function openQcReviewOriginal(record: CartonMarkPhotoRecord, assetId: string) {
  const factory = activeFactoryId.value, generation = factoryGeneration
  try {
    const blob = await cartonMarkApi.downloadQcReviewSource(record.id, assetId, factory)
    if (isCurrentFactoryTask(factory, generation) && isPanelMounted) window.open(createImageUrl(blob), '_blank', 'noopener,noreferrer')
  } catch (cause) {
    if (isCurrentFactoryTask(factory, generation) && isPanelMounted) photoErrorMessage.value = getApiErrorMessage(cause)
  }
}
const documentComparisonRecord = ref<CartonMarkTemplateRecord | null>(null)
function isManualReview(record: CartonMarkTemplateRecord) { return record.documentCheckResult?.review_method === 'manual_sources' }
function hasImageSources(review: { review_method?: unknown; source_assets?: unknown } | undefined) {
  return review?.review_method === 'manual_sources' && Array.isArray(review.source_assets) && review.source_assets.length > 0 && review.source_assets.every(source => source.kind === 'image')
}
function isImageReference(record: CartonMarkTemplateRecord) { return hasImageSources(record.documentCheckResult) }
function isImageQcRecord(record: CartonMarkPhotoRecord) { return hasImageSources(record.server?.template_snapshot) }
async function openReviewOriginal(record: CartonMarkTemplateRecord, assetId: string) {
  const factory = activeFactoryId.value, generation = factoryGeneration
  try {
    const blob = await cartonMarkApi.downloadReviewSource(record.id, assetId, factory)
    if (!isCurrentFactoryTask(factory, generation) || !isPanelMounted) return
    window.open(createImageUrl(blob), '_blank', 'noopener,noreferrer')
  } catch (cause) {
    if (isCurrentFactoryTask(factory, generation) && isPanelMounted) {
      if (manualReleaseRecord.value) manualReleaseError.value = getApiErrorMessage(cause)
      else errorMessage.value = getApiErrorMessage(cause)
    }
  }
}
const autoCheckResult = ref<CartonMarkAutoCheckResponse | null>(null)
const autoCheckErrorMessage = ref('')
const viewedAutoRevision = ref<number | null>(null)
const viewedAutoTime = ref('')
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
const customerRecognitionBusy = ref(false)
const manualReleaseRecord = ref<CartonMarkTemplateRecord | null>(null)
const manualReleaseReason = ref('')
const manualReleaseError = ref('')
const isManualReleasing = ref(false)
const customerMutationBusy = ref(false)
const customerMutationError = ref('')
const isSaving = ref(false)
const isSavingPhoto = ref(false)
const isSavingBatchPhoto = ref(false)
const deletingRecordId = ref('')
const serverPhotoTotal = ref(0)
const loadingServerPhotos = ref(false)
const qcContractFilter = ref('')
const qcItemFilter = ref('')
const frozenComparisonTemplate = ref<CartonMarkTemplateRecord | null>(null)
const reviewNote = ref('')
let qcRequestController: AbortController | null = null
let qcLoadGeneration = 0
let pendingSubmission: CartonMarkQcSubmission | null = null
const pendingActions = new Map<string, { action: '核对通过' | '发现异常' | '重新自动核对' | '作废', expected_revision: number, request_id: string, note: string }>()
const downloadingDocumentKey = ref('')
let factoryGeneration = 0
let appliedQcTemplateRequest = '', qcSelectionGeneration = 0
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
const isRotatingPhoto = reactive<Record<CartonMarkPhotoSide, boolean>>({
  front: false,
  side: false,
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
const canReleaseTemplate = computed(() => isAdmin.value || warehousePermissionDepartments.some(
  (department) => authStore.can('carton_mark:template_release', activeFactoryId.value, department),
))
const canUploadPhoto = computed(() => isAdmin.value || authStore.can('carton_mark:photo_upload', activeFactoryId.value, currentDepartmentId.value))
const canReviewPhoto = computed(() => isAdmin.value || authStore.can('carton_mark:review', activeFactoryId.value, currentDepartmentId.value))
const canDeleteTemplate = computed(() => isWarehouseWorkspace.value && canUploadTemplate.value)
const canOpenQc = computed(() => authStore.can('carton_mark:read', activeFactoryId.value, 'qc'))
const canOpenWarehouse = computed(() => warehousePermissionDepartments.some(department => authStore.can('carton_mark:read', activeFactoryId.value, department)))
const currentUserName = computed(() => authStore.currentUser?.display_name ?? '当前账号')
const templatePermissionHint = computed(() => canUploadTemplate.value
  ? '先上传客人提供的 PO 箱唛 Excel，再上传调整排版和图案后的打印 PDF；系统只核对普通业务文字，图形内文字不参与比较。'
  : '当前账号只能查看箱唛资料；请使用纸箱部仓管账号上传 Excel 与打印 PDF。')
const photoPermissionHint = computed(() => {
  if (canUploadPhoto.value) {
    return '选择已核对或审核通过的订单资料，再上传现场箱唛照片；PDF 支持文字核对，图片资料供人工对照。'
  }

  return '当前账号只能查看实拍记录；QC 检验员账号可上传现场照片并核对箱唛。'
})

const records = computed(() => {
  return sortRecords(allRecords.value.filter((record) => record.factoryId === activeFactoryId.value))
})

const photoRecords = computed(() => {
  if (!canInCurrentWorkspace('carton_mark:read')) return []
  return sortPhotoRecords(allPhotoRecords.value.filter(record => record.factoryId === activeFactoryId.value
    && (!qcContractFilter.value.trim() || record.contractNumber === qcContractFilter.value.trim())
    && (!qcItemFilter.value.trim() || record.item === qcItemFilter.value.trim())))
})

const photoReadyRecords = computed(() => {
  return records.value.filter((record) => record.qcReady)
})

const selectedFileLabel = computed(() => {
  if (pendingLibraryReads.pdf) return '正在读取仓库 PDF…'
  if (!selectedFile.value) return '未选择 PDF'

  return `${selectedFile.value.name} · ${formatFileSize(selectedFile.value.size)}`
})

const selectedExcelFileLabel = computed(() => {
  if (pendingLibraryReads.excel) return '正在读取仓库 Excel…'
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
    && !customerRecognitionBusy.value
    && !pendingLibraryReads.pdf && !pendingLibraryReads.excel
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

  return photo.server ? frozenComparisonTemplate.value : findTemplateForPhoto(photo)
})

const comparisonPdfPreviewUrl = computed(() => {
  const pdfUrl = comparisonTemplate.value?.pdfUrl

  return pdfUrl ? `${pdfUrl}#toolbar=0&navpanes=0&scrollbar=0&view=FitH` : ''
})

const comparisonPdfMissingMessage = computed(() => {
  if (!comparisonRecord.value) return ''

  if (!comparisonTemplate.value) {
    return '未读取到这次核验使用的资料原件。'
  }

  return '已匹配到服务器模板，但打印 PDF 暂时无法读取，请稍后重试。'
})

const templateCustomerOptions = computed(() => {
  const customerMap = new Map<string, { name: string, count: number }>()

  for (const customer of customerOptions.value) {
    customerMap.set(normalizeKey(customer.name), {
      name: customer.name,
      count: 0,
    })
  }

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
  if (selectedTemplateForPhoto.value && isImageReference(selectedTemplateForPhoto.value)) return isSavingBatchPhoto.value ? '保存中' : batchPhotoCount.value ? `保存照片待人工复核（${batchPhotoCount.value} 张）` : '选择照片后保存留档'
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
  void loadCustomerOptions(requestedFactoryId, requestedFactoryGeneration)

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
    allPhotoRecords.value = sortPhotoRecords([...photosResult.value.records.map(hydratePhotoRecord), ...allPhotoRecords.value.filter(photo => photo.server)])
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
  if (!isWarehouseWorkspace.value) void loadServerPhotos()
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
    if (photoForm.templateId && !photoReadyRecords.value.some(record => record.id === photoForm.templateId)) photoForm.templateId = ''
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

function refreshTemplates() {
  if (isLoading.value || isSaving.value || isSavingBatchPhoto.value || isManualReleasing.value || recheckingDocumentId.value) return
  if (isWarehouseWorkspace.value) errorMessage.value = ''
  else photoErrorMessage.value = ''
  void loadTemplateRecords(activeFactoryId.value, activeFactory.value.shortName, factoryGeneration)
  if (!isWarehouseWorkspace.value) void loadServerPhotos()
}

async function selectQcTemplate(record: CartonMarkTemplateRecord) {
  if (isWarehouseWorkspace.value || !canUploadPhoto.value || !record.qcReady || record.factoryId !== activeFactoryId.value || isSavingBatchPhoto.value || photoForm.templateId === record.id) return
  const scope = activeFactoryId.value, generation = factoryGeneration
  const selection = ++qcSelectionGeneration
  photoForm.customerName = record.customerName
  await nextTick()
  if (!isPanelMounted || !canUploadPhoto.value || selection !== qcSelectionGeneration || !isCurrentFactoryTask(scope, generation) || !photoReadyRecords.value.some(item => item.id === record.id)) return
  photoForm.templateId = record.id
  photoErrorMessage.value = ''
  await nextTick()
  if (isCurrentFactoryTask(scope, generation)) photoFormPanel.value?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
}

watch([() => route.query?.template, () => route.query?.factory, photoReadyRecords, isLoading, canUploadPhoto], ([template, factory]) => {
  if (typeof template !== 'string' || !template.trim()) { appliedQcTemplateRequest = ''; return }
  if (isWarehouseWorkspace.value || isLoading.value || !isPanelMounted || !canUploadPhoto.value) return
  if (typeof factory === 'string' && factory !== activeFactoryId.value) return
  const request = `${activeFactoryId.value}:${template}`
  const record = photoReadyRecords.value.find(item => item.id === template)
  if (record && appliedQcTemplateRequest !== request) { appliedQcTemplateRequest = request; void selectQcTemplate(record) }
  else if (!record) photoErrorMessage.value = '这份模板尚未通过核对或人工放行、已移出，或不属于当前厂区，请刷新资料后重新选择。'
}, { flush: 'post' })

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

watch([activeFactoryId, () => authStore.currentUser?.id, () => authStore.authorizationVersion], () => {
  factoryGeneration += 1
  qcRequestController?.abort(); qcLoadGeneration++
  allPhotoRecords.value = allPhotoRecords.value.filter(photo => !photo.server)
  serverPhotoTotal.value = 0; comparisonRecord.value = null; frozenComparisonTemplate.value = null; reviewNote.value = ''
  qcContractFilter.value = ''; qcItemFilter.value = ''
  photoForm.note = ''; photoForm.correctsRecordId = ''; pendingSubmission = null; pendingActions.clear()
  if (!isWarehouseWorkspace.value && isPanelMounted) void loadServerPhotos()
  appliedQcTemplateRequest = ''; qcSelectionGeneration++
  templateRequestController?.abort()
  documentRecheckRequestController?.abort()
  customerOptionsRequestController?.abort()
  revokeTemplateUrls()
  allRecords.value = []
  customerOptions.value = []
  customerDialogOpen.value = false
  manualReleaseRecord.value = null
  manualReleaseReason.value = ''
  manualReleaseError.value = ''
  isManualReleasing.value = false
  customerMutationBusy.value = false
  customerMutationError.value = ''
  const requestedFactoryId = activeFactoryId.value
  const requestedFactoryName = activeFactory.value.shortName
  const requestedFactoryGeneration = factoryGeneration
  void loadTemplateRecords(requestedFactoryId, requestedFactoryName, requestedFactoryGeneration)
  void loadCustomerOptions(requestedFactoryId, requestedFactoryGeneration)
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
  photoForm.correctsRecordId = ''; photoForm.note = ''
  resetPhotoSelection()
  resetBatchPhotoSelection()
})

watch(() => photoForm.templateId, () => {
  photoForm.correctsRecordId = ''; photoForm.note = ''
  resetPhotoSelection()
  resetBatchPhotoSelection()
})

onBeforeUnmount(() => {
  isPanelMounted = false
  factoryGeneration += 1
  templateRequestController?.abort()
  documentRecheckRequestController?.abort()
  customerOptionsRequestController?.abort()
  qcRequestController?.abort()
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

function buildRotatedPhotoFileName(fileName: string, direction: 'left' | 'right') {
  const dotIndex = fileName.lastIndexOf('.')
  const baseName = dotIndex > 0 ? fileName.slice(0, dotIndex) : fileName
  return `${baseName}-rotate-${direction}.png`
}

async function rotateActiveBatchPhoto(side: CartonMarkPhotoSide, degrees: -90 | 90) {
  const file = getSelectedPhotoFile(side)
  if (!file || isRotatingPhoto[side]) return
  const requestedFactoryId = activeFactoryId.value
  const requestedGeneration = factoryGeneration
  const requestedIndex = getActiveBatchPhotoIndex(side)

  isRotatingPhoto[side] = true
  photoErrorMessage.value = ''
  photoSuccessMessage.value = ''
  try {
    const direction = degrees < 0 ? 'left' : 'right'
    const rotatedFile = await rotateImageBlob(
      file,
      degrees,
      buildRotatedPhotoFileName(file.name, direction),
    )
    if (!isPanelMounted || !isCurrentFactoryTask(requestedFactoryId, requestedGeneration)) return
    const files = [...getBatchPhotoFiles(side)]
    if (!files[requestedIndex]) return
    files[requestedIndex] = rotatedFile
    setBatchPhotoFiles(side, files)
    if (getActiveBatchPhotoIndex(side) === requestedIndex) {
      setSelectedPhotoFile(side, rotatedFile)
      resetPhotoCropState(side, true)
      photoPreviewRenderTick.value += 1
    }
    photoSuccessMessage.value = `${side === 'front' ? '正唛' : '侧唛'}第 ${requestedIndex + 1} 张已${degrees < 0 ? '向左' : '向右'}旋转 90°，将使用旋转后的图片核对。`
  } catch (error) {
    if (isPanelMounted && isCurrentFactoryTask(requestedFactoryId, requestedGeneration)) {
      photoErrorMessage.value = getApiErrorMessage(error)
    }
  } finally {
    isRotatingPhoto[side] = false
  }
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
    manualReleased: record.manual_released,
    manualReleaseReason: record.manual_release_reason,
    manualReleaseSourceStatus: record.manual_release_source_status,
    manualReleasedByName: record.manual_released_by_name,
    manualReleasedAt: record.manual_released_at,
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
  return photo.server ? null : records.value.find(record => record.id === photo.templateId) ?? null
}

function showPhotoAutoCheck(photo: CartonMarkPhotoRecord) {
  const previous = comparisonRecord.value
  if (previous?.server && previous.id !== photo.id) {
    for (const url of [previous.frontImageUrl, previous.sideImageUrl]) if (url) revokeImageUrl(url)
    previous.frontImageBlob = undefined; previous.sideImageBlob = undefined
    previous.frontImageUrl = undefined; previous.sideImageUrl = undefined
  }
  if (frozenComparisonTemplate.value?.pdfUrl) {
    URL.revokeObjectURL(frozenComparisonTemplate.value.pdfUrl)
    pdfUrls.delete(frozenComparisonTemplate.value.pdfUrl)
  }
  comparisonRecord.value = photo; frozenComparisonTemplate.value = null; reviewNote.value = ''
  const event = photo.server?.events.filter(e => e.kind === 'AUTO_CHECK').at(-1)
  viewedAutoRevision.value = event?.revision ?? null
  viewedAutoTime.value = event?.created_at ?? photo.autoCheckedAt ?? ''
  autoCheckResult.value = photo.autoCheckResult ?? null
  autoCheckErrorMessage.value = photo.autoCheckErrorMessage ?? ''
  if (photo.server) { void loadQcOriginals(photo); return }
  const template = findTemplateForPhoto(photo)
  if (template && !template.fileBlob) void ensureTemplatePdfBlob(template).catch(error => {
    if (isPanelMounted && comparisonRecord.value?.id === photo.id) photoErrorMessage.value = `打印 PDF 读取失败：${getApiErrorMessage(error)}`
  })
}
function qcRequestId() {
  return createRandomUuid()
}
function mapQcRecord(value: CartonMarkQcRecord): CartonMarkPhotoRecord {
  const auto = [...value.events].reverse().find(e => e.kind === 'AUTO_CHECK')
  const review = [...value.events].reverse().find(e => e.kind === 'REVIEW' && e.status !== '待复核')
  const front = value.photos.find(p => p.side === 'front'), side = value.photos.find(p => p.side === 'side')
  return { server: value, id: value.id, templateId: value.template_id,
    factoryId: value.factory_id as ProductionFactoryContextId, factoryName: activeFactory.value.shortName,
    customerName: value.customer_name, po: value.po, item: value.item, contractNumber: value.contract_number,
    fileName: front?.file_name ?? side?.file_name ?? '', fileSize: value.photos.reduce((sum, p) => sum + p.size_bytes, 0),
    uploadedAt: value.created_at, sequence: 1, status: value.status,
    frontFileName: front?.file_name, frontFileSize: front?.size_bytes, sideFileName: side?.file_name, sideFileSize: side?.size_bytes,
    autoCheckResult: auto?.result ?? undefined, autoCheckErrorMessage: auto?.error, autoCheckedAt: auto?.created_at,
    reviewedAt: review?.created_at, reviewedBy: review?.actor_name }
}
async function loadServerPhotos(append = false) {
  const factory = activeFactoryId.value, generation = factoryGeneration, request = ++qcLoadGeneration
  const contractNumber = qcContractFilter.value.trim(), item = qcItemFilter.value.trim()
  const offset = append ? allPhotoRecords.value.filter(p => p.server).length : 0
  loadingServerPhotos.value = true
  try {
    const page = await cartonMarkApi.listQcRecords(factory, offset, { contractNumber, item })
    if (!isPanelMounted || !isCurrentFactoryTask(factory, generation) || request !== qcLoadGeneration
      || contractNumber !== qcContractFilter.value.trim() || item !== qcItemFilter.value.trim()) return
    const existing = append ? allPhotoRecords.value : allPhotoRecords.value.filter(p => !p.server)
    const incoming = page.items.map(mapQcRecord), ids = new Set(incoming.map(p => p.id))
    allPhotoRecords.value = sortPhotoRecords([...existing.filter(p => !ids.has(p.id)), ...incoming]); serverPhotoTotal.value = page.total
  } catch (error) {
    if (isCurrentFactoryTask(factory, generation) && request === qcLoadGeneration) photoErrorMessage.value = `QC 服务端留档读取失败：${getApiErrorMessage(error)}`
  } finally {
    if (isCurrentFactoryTask(factory, generation) && request === qcLoadGeneration) loadingServerPhotos.value = false
  }
}
async function loadQcOriginals(photo: CartonMarkPhotoRecord) {
  const server = photo.server; if (!server) return
  const factory = activeFactoryId.value, generation = factoryGeneration
  qcRequestController?.abort(); const controller = new AbortController(); qcRequestController = controller
  const downloads = await Promise.allSettled([cartonMarkApi.downloadQcTemplate(factory, photo.id, controller.signal),
    ...server.photos.map(p => cartonMarkApi.downloadQcPhoto(factory, photo.id, p.id, controller.signal))])
  if (!isPanelMounted || !isCurrentFactoryTask(factory, generation) || comparisonRecord.value?.id !== photo.id || controller.signal.aborted) return
  let failed = false; const pdf = downloads[0]
  if (pdf?.status === 'fulfilled') {
    const url = URL.createObjectURL(pdf.value); pdfUrls.add(url)
    frozenComparisonTemplate.value = { id: photo.templateId, factoryId: photo.factoryId, factoryName: photo.factoryName,
      customerName: photo.customerName, po: photo.po, item: photo.item, contractNumber: photo.contractNumber,
      fileName: String(server.template_snapshot.pdf_file_name ?? '历史打印稿.pdf'), fileSize: pdf.value.size,
      uploadedAt: photo.uploadedAt, version: server.template_version, fileBlob: pdf.value, pdfUrl: url,
      checkStatus: String(server.template_snapshot.check_status ?? ''), qcReady: true, createdByName: server.created_by_name,
      manualReleased: !!server.template_snapshot.manual_released_at, manualReleaseReason: String(server.template_snapshot.manual_release_reason ?? ''),
      manualReleaseSourceStatus: '', manualReleasedByName: String(server.template_snapshot.manual_released_by_name ?? ''), manualReleasedAt: String(server.template_snapshot.manual_released_at ?? '') }
  } else failed = true
  server.photos.forEach((p, index) => {
    const downloaded = downloads[index + 1]; if (downloaded?.status !== 'fulfilled') { failed = true; return }
    const previousUrl = p.side === 'front' ? photo.frontImageUrl : photo.sideImageUrl
    if (previousUrl) revokeImageUrl(previousUrl)
    const url = URL.createObjectURL(downloaded.value); imageUrls.add(url)
    if (p.side === 'front') { photo.frontImageBlob = downloaded.value; photo.frontImageUrl = url }
    else { photo.sideImageBlob = downloaded.value; photo.sideImageUrl = url }
  })
  if (failed) photoErrorMessage.value = '部分留档原件读取失败，请重新打开核验记录。'
}
async function actOnQcPhoto(photo: CartonMarkPhotoRecord, action: '核对通过' | '发现异常' | '重新自动核对' | '作废') {
  if (!photo.server || !canReviewPhoto.value || photo.factoryId !== activeFactoryId.value || recheckingPhotoId.value) return
  if (comparisonRecord.value?.id !== photo.id && action !== '重新自动核对') { showPhotoAutoCheck(photo); photoErrorMessage.value = '请在核验明细中填写复核说明，再确认操作。'; return }
  const factory = activeFactoryId.value, generation = factoryGeneration
  const note = comparisonRecord.value?.id === photo.id ? reviewNote.value.trim() : ''
  photoErrorMessage.value = ''; photoSuccessMessage.value = ''
  if ((action === '发现异常' || action === '作废') && note.length < 5) { photoErrorMessage.value = '请填写至少 5 字的异常或作废原因。'; return }
  const previous = pendingActions.get(photo.id)
  const payload = previous && previous.action === action && previous.note === note && previous.expected_revision === photo.server.revision
    ? previous : { action, expected_revision: photo.server.revision, request_id: qcRequestId(), note }
  pendingActions.set(photo.id, payload); recheckingPhotoId.value = photo.id
  try {
    const saved = await cartonMarkApi.qcAction(factory, photo.id, payload)
    if (!isPanelMounted || !isCurrentFactoryTask(factory, generation)) return
    pendingActions.delete(photo.id)
    const updated = { ...mapQcRecord(saved), frontImageUrl: photo.frontImageUrl, frontImageBlob: photo.frontImageBlob, sideImageUrl: photo.sideImageUrl, sideImageBlob: photo.sideImageBlob }
    allPhotoRecords.value = sortPhotoRecords(allPhotoRecords.value.map(p => p.id === photo.id ? updated : p))
    showPhotoAutoCheck(updated); photoSuccessMessage.value = `${action}已保存到服务器，原照片和历次结果已保留。`
  } catch (error) {
    if (isCurrentFactoryTask(factory, generation)) photoErrorMessage.value = `未保存：${getApiErrorMessage(error)}。请保留当前页面重试；如记录已变化，请刷新。`
  } finally { if (isCurrentFactoryTask(factory, generation)) recheckingPhotoId.value = '' }
}
async function startCorrection(photo: CartonMarkPhotoRecord) {
  if (!photo.server || photo.status !== '发现异常' || !canUploadPhoto.value) return
  const template = photoReadyRecords.value.find(t => t.customerName === photo.customerName && t.po === photo.po && t.item === photo.item && t.contractNumber === photo.contractNumber)
  if (!template) { photoErrorMessage.value = '当前没有该合同货号的可用资料版本，请先确认资料。'; return }
  await selectQcTemplate(template); resetBatchPhotoSelection(); photoForm.correctsRecordId = photo.id; photoForm.note = ''
  photoFormPanel.value?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
}

function getPhotoAutoCheckSummary(photo: CartonMarkPhotoRecord) {
  if (isImageQcRecord(photo)) return '图片资料 · 人工对照，不执行自动核对'
  if (photo.autoCheckResult) {
    const summary = photo.autoCheckResult.summary
    return `自动核对：${summary.overall_status} · 通过 ${summary.pass_count} / 异常 ${summary.mismatch_count} / 待复核 ${summary.review_count + summary.missing_count}`
  }

  if (photo.autoCheckErrorMessage) {
    return photo.autoCheckErrorMessage
  }

  return '尚未生成自动核对明细。'
}


function resetForm() {
  librarySelectionGeneration.pdf++
  librarySelectionGeneration.excel++
  libraryMetadataGeneration++
  pendingLibraryReads.pdf = false
  pendingLibraryReads.excel = false
  form.customerName = ''
  form.item = ''
  form.contractNumber = ''
  selectedExcelFile.value = null
  selectedFile.value = null
  selectedExcelAssetId.value = ''
  selectedPdfAssetId.value = ''

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
    if (frontCameraInput.value) frontCameraInput.value.value = ''

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
  if (sideCameraInput.value) sideCameraInput.value.value = ''
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

function selectPrintPdf(file: File | undefined, input?: HTMLInputElement, libraryCompletion = false) {
  librarySelectionGeneration.pdf++
  if (!libraryCompletion) libraryMetadataGeneration++
  pendingLibraryReads.pdf = false
  selectedPdfAssetId.value = ''
  errorMessage.value = ''
  successMessage.value = ''
  documentReviewMessage.value = ''

  if (!canUploadTemplate.value) {
    selectedFile.value = null
    if (input) input.value = ''
    errorMessage.value = '当前账号无权上传打印 PDF，请使用纸箱仓管账号操作。'
    return
  }

  if (!file) {
    selectedFile.value = null
    return
  }

  if (!isPdfFile(file)) {
    selectedFile.value = null
    if (input) input.value = ''
    errorMessage.value = '打印箱唛只支持 PDF 文件。'
    return
  }

  selectedFile.value = file
}

function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  selectPrintPdf(input.files?.[0], input)
}

function handlePdfFileDrop(event: DragEvent) {
  selectPrintPdf(event.dataTransfer?.files[0])
}

function selectExcelContract(file: File | undefined, input?: HTMLInputElement, libraryCompletion = false) {
  librarySelectionGeneration.excel++
  if (!libraryCompletion) libraryMetadataGeneration++
  pendingLibraryReads.excel = false
  selectedExcelAssetId.value = ''
  errorMessage.value = ''
  successMessage.value = ''
  documentReviewMessage.value = ''

  if (!canUploadTemplate.value) {
    selectedExcelFile.value = null
    if (input) input.value = ''
    errorMessage.value = '当前账号无权上传客人 Excel，请使用纸箱仓管账号操作。'
    return
  }

  if (!file) {
    selectedExcelFile.value = null
    return
  }

  if (!isExcelFile(file)) {
    selectedExcelFile.value = null
    if (input) input.value = ''
    errorMessage.value = '客人 PO 箱唛只支持 .xls、.xlsx 或 .xlsm 文件。'
    return
  }

  selectedExcelFile.value = file
}

function handleExcelFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  selectExcelContract(input.files?.[0], input)
}

async function useLibraryAsset(asset: CartonMarkAsset) {
  if (asset.kind === 'image') return
  if (!canUploadTemplate.value || isSaving.value || asset.factory_id !== activeFactoryId.value) return
  const requestedFactoryId = activeFactoryId.value
  const requestedGeneration = factoryGeneration
  const selection = ++librarySelectionGeneration[asset.kind]
  const metadata = ++libraryMetadataGeneration
  const previousForm = { ...form }
  pendingLibraryReads[asset.kind] = true
  if (asset.kind === 'pdf') {
    selectedFile.value = null
    selectedPdfAssetId.value = ''
  } else {
    selectedExcelFile.value = null
    selectedExcelAssetId.value = ''
  }
  try {
    const blob = await cartonMarkApi.downloadAsset(requestedFactoryId, asset.id)
    if (!isPanelMounted || !isCurrentFactoryTask(requestedFactoryId, requestedGeneration)
      || selection !== librarySelectionGeneration[asset.kind] || isSaving.value || !canUploadTemplate.value) return
    const canFillMetadata = metadata === libraryMetadataGeneration
    const file = new File([blob], asset.file_name, { type: blob.type })
    if (asset.kind === 'pdf') {
      selectPrintPdf(file, undefined, true)
      selectedPdfAssetId.value = asset.id
    } else {
      selectExcelContract(file, undefined, true)
      selectedExcelAssetId.value = asset.id
    }
    if (canFillMetadata && asset.contract_number && form.contractNumber === previousForm.contractNumber) form.contractNumber = asset.contract_number
    const items = [...new Set(asset.orders.map(order => order.item_no))]
    if (canFillMetadata && items.length === 1 && form.item === previousForm.item) form.item = items[0] || ''
    successMessage.value = `已从仓库选择 ${asset.file_name}，提交核对时直接使用保存的原文件。`
  } catch (error) {
    if (isPanelMounted && isCurrentFactoryTask(requestedFactoryId, requestedGeneration)
      && selection === librarySelectionGeneration[asset.kind]) errorMessage.value = getApiErrorMessage(error)
  } finally {
    if (selection === librarySelectionGeneration[asset.kind]) pendingLibraryReads[asset.kind] = false
  }
}

defineExpose({ useLibraryAsset, refreshTemplates })

function handleExcelFileDrop(event: DragEvent) {
  selectExcelContract(event.dataTransfer?.files[0])
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

function selectBatchPhotoFiles(files: File[], side: CartonMarkPhotoSide) {
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

function handleBatchPhotoFileChange(event: Event, side: CartonMarkPhotoSide) {
  const input = event.target as HTMLInputElement
  selectBatchPhotoFiles(Array.from(input.files ?? []), side)
}

function openPhotoCamera(side: CartonMarkPhotoSide) {
  if (!canUploadPhoto.value || isSavingBatchPhoto.value || isRotatingPhoto[side]) return
  const input = side === 'front' ? frontCameraInput.value : sideCameraInput.value
  if (input) { input.value = ''; input.click() }
}

function handleCameraPhotoChange(event: Event, side: CartonMarkPhotoSide) {
  const input = event.target as HTMLInputElement
  const photos = Array.from(input.files ?? [])
  input.value = ''
  if (!photos.length || !canUploadPhoto.value || isSavingBatchPhoto.value || isRotatingPhoto[side]) return
  const previous = [...getBatchPhotoFiles(side)], cropped = [...croppedBatchPhotoIndexes[side]]
  selectBatchPhotoFiles([...previous, ...photos], side)
  croppedBatchPhotoIndexes[side] = cropped
  showBatchPhotoAt(side, Math.max(0, getBatchPhotoFiles(side).length - 1))
}

function handleBatchPhotoDrop(event: DragEvent, side: CartonMarkPhotoSide) {
  selectBatchPhotoFiles(Array.from(event.dataTransfer?.files ?? []), side)
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

  librarySelectionGeneration.pdf++
  librarySelectionGeneration.excel++
  libraryMetadataGeneration++
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
      excelAssetId: selectedExcelAssetId.value || undefined,
      pdfAssetId: selectedPdfAssetId.value || undefined,
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

function openManualRelease(record: CartonMarkTemplateRecord) {
  if (isManualReleasing.value) return
  manualReleaseError.value = ''
  if (!canReleaseTemplate.value) {
    const message = '当前账号无权人工放行箱唛模板，请联系纸箱部主管、经理或系统管理员。'
    if (isWarehouseWorkspace.value) errorMessage.value = message
    else photoErrorMessage.value = message
    return
  }
  if (record.qcReady) return

  manualReleaseRecord.value = record
  manualReleaseReason.value = ''
  if (isManualReview(record)) void confirmManualRelease()
}

function closeManualRelease() {
  if (isManualReleasing.value) return
  manualReleaseRecord.value = null
  manualReleaseReason.value = ''
  manualReleaseError.value = ''
}

async function confirmManualRelease() {
  const record = manualReleaseRecord.value
  const reason = manualReleaseReason.value.trim()
  manualReleaseError.value = ''

  if (!record || !canReleaseTemplate.value) {
    manualReleaseError.value = '当前账号无权人工放行箱唛模板。'
    return
  }
  if (!isManualReview(record) && reason.length < 5) {
    manualReleaseError.value = '请填写至少 5 个字符的放行理由。'
    return
  }

  const requestedFactoryId = activeFactoryId.value
  const requestedFactoryName = activeFactory.value.shortName
  const requestedGeneration = factoryGeneration
  if (record.factoryId !== requestedFactoryId) {
    manualReleaseError.value = '这份箱唛资料不属于当前厂区，请切换厂区后再操作。'
    return
  }

  isManualReleasing.value = true
  try {
    const persistedRecord = await cartonMarkApi.manualReleaseTemplate(record.id, requestedFactoryId, reason)
    if (!isCurrentFactoryTask(requestedFactoryId, requestedGeneration) || !isPanelMounted) return

    const releasedRecord = {
      ...mapTemplateRecord(persistedRecord, requestedFactoryName),
      pdfUrl: record.pdfUrl,
      fileBlob: record.fileBlob,
      excelUrl: record.excelUrl,
    }
    allRecords.value = sortRecords(allRecords.value.map((item) => item.id === record.id ? releasedRecord : item))
    if (documentComparisonRecord.value?.id === record.id) {
      documentComparisonRecord.value = releasedRecord
    }
    if (!isWarehouseWorkspace.value) {
      photoForm.customerName = releasedRecord.customerName
      await nextTick()
      photoForm.templateId = releasedRecord.id
      photoSuccessMessage.value = `${releasedRecord.customerName} · ITEM：${releasedRecord.item} 已人工审核放行并自动选中，可上传现场箱唛照片。`
    } else {
      successMessage.value = `${releasedRecord.customerName} · ITEM：${releasedRecord.item} 已人工审核放行，可供 QC 选择。`
    }
    manualReleaseRecord.value = null
    manualReleaseReason.value = ''
  } catch (error) {
    if (isCurrentFactoryTask(requestedFactoryId, requestedGeneration) && isPanelMounted) {
      manualReleaseError.value = getApiErrorMessage(error)
      if (isManualReview(record)) {
        if (isWarehouseWorkspace.value) errorMessage.value = manualReleaseError.value
        else photoErrorMessage.value = manualReleaseError.value
        manualReleaseRecord.value = null
      }
    }
  } finally {
    if (isCurrentFactoryTask(requestedFactoryId, requestedGeneration) && isPanelMounted) {
      isManualReleasing.value = false
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

async function submitBatchPhoto() {
  photoErrorMessage.value = ''; photoSuccessMessage.value = ''
  if (isSavingBatchPhoto.value || !canUploadPhoto.value || !canSubmitBatchPhoto.value) return
  const template = selectedTemplateForPhoto.value
  if (!template || template.factoryId !== activeFactoryId.value) { photoErrorMessage.value = '请先选择当前厂区已确认的资料版本。'; return }
  const factory = activeFactoryId.value, generation = factoryGeneration
  const frontPhotos = [...selectedFrontBatchFiles.value], sidePhotos = [...selectedSideBatchFiles.value]
  const note = photoForm.note.trim(), correctsRecordId = photoForm.correctsRecordId || undefined
  if (correctsRecordId && note.length < 5) { photoErrorMessage.value = '请填写至少 5 字的整改说明。'; return }
  if (frontPhotos.length + sidePhotos.length > 20) { photoErrorMessage.value = '每次最多上传 20 张图片。'; return }
  const sameFiles = (a: File[], b: File[]) => a.length === b.length && a.every((file, index) => file === b[index])
  if (!pendingSubmission || pendingSubmission.factoryId !== factory || pendingSubmission.templateId !== template.id
    || pendingSubmission.note !== note || pendingSubmission.correctsRecordId !== correctsRecordId
    || !sameFiles(pendingSubmission.frontPhotos, frontPhotos) || !sameFiles(pendingSubmission.sidePhotos, sidePhotos)) {
    pendingSubmission = { factoryId: factory, templateId: template.id, requestId: qcRequestId(), frontPhotos, sidePhotos, mode: 'batch', note, correctsRecordId }
  }
  const submission = pendingSubmission; isSavingBatchPhoto.value = true
  try {
    const saved = await cartonMarkApi.createQcRecords(submission)
    if (!isPanelMounted || !isCurrentFactoryTask(factory, generation)) return
    const incoming = saved.map(mapQcRecord), ids = new Set(incoming.map(p => p.id))
    allPhotoRecords.value = sortPhotoRecords([...incoming, ...allPhotoRecords.value.filter(p => !ids.has(p.id))]); pendingSubmission = null
    resetBatchPhotoSelection(); photoForm.note = ''; photoForm.correctsRecordId = ''
    if (incoming[0]) showPhotoAutoCheck(incoming[0])
    photoSuccessMessage.value = `已保存 ${incoming.length} 条 QC 留档到服务器，照片和资料版本已绑定，请人工复核。`
    void loadServerPhotos()
  } catch (error) {
    if (isCurrentFactoryTask(factory, generation)) photoErrorMessage.value = `服务端未确认保存：${getApiErrorMessage(error)}。照片选择已保留，请在当前页面重试。`
  } finally { if (isCurrentFactoryTask(factory, generation)) isSavingBatchPhoto.value = false }
}

async function rerunAutoCheckForPhoto(photo: CartonMarkPhotoRecord) { await actOnQcPhoto(photo, '重新自动核对') }

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

async function deletePhotoRecord(photo: CartonMarkPhotoRecord) { await actOnQcPhoto(photo, '作废') }
async function reviewPhoto(photo: CartonMarkPhotoRecord, status: '核对通过' | '发现异常') { await actOnQcPhoto(photo, status) }

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

</script>

<template>
  <!-- 箱唛模板来自后端资料库；浏览器本地存储仅保留历史现场照片。 -->
  <div class="space-y-6">
    <div class="grid items-start gap-6 grid-cols-1 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
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
              当前厂区尚未添加箱唛客户。填写合同号可先识别客名，再由主管或管理员确认加入客户库。
            </p>
            <p v-else id="carton-mark-customer-help" class="mt-1 text-xs text-slate-500">
              客名由当前厂区纸箱部主管以上维护，并作为右侧客户资料集合的归档名称。
            </p>
            <CartonMarkCustomerRecognition
              class="mt-3"
              :factory-id="activeFactoryId"
              :factory-name="activeFactory.shortName"
              :contract-number="form.contractNumber"
              :item="form.item"
              :excel-asset-id="selectedExcelAssetId"
              :pdf-asset-id="selectedPdfAssetId"
              :selected-customer="form.customerName"
              :customers="customerOptions"
              :allowed="isWarehouseWorkspace && canUploadTemplate && canOpenWarehouse"
              :can-manage="canManageCustomers"
              @select="form.customerName = $event"
              @customers-changed="reloadCustomerOptions"
              @busy="customerRecognitionBusy = $event"
            />
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
          <div
            class="rounded-lg border border-dashed border-teal-300 bg-teal-50/40 p-5"
            @dragover.prevent
            @drop.prevent="handleExcelFileDrop"
          >
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
                  <p class="mt-1 text-xs font-medium text-teal-700">可点击选择或拖拽 Excel 到此处</p>
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

          <div
            class="rounded-lg border border-dashed border-blue-300 bg-blue-50/40 p-5"
            @dragover.prevent
            @drop.prevent="handlePdfFileDrop"
          >
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
                  <p class="mt-1 text-xs font-medium text-blue-700">可点击选择或拖拽 PDF 到此处</p>
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
          Excel、打印 PDF 和核对结果会保存到公司资料库；自动核对通过，或经纸箱部主管以上填写理由人工放行后，PDF 才可供 QC 现场核验。
        </p>
        </form>

        <section v-if="isWarehouseWorkspace && documentComparisonRecord && isManualReview(documentComparisonRecord)" class="order-3 rounded-lg border border-amber-200 bg-white p-6 xl:col-span-2">
          <h2 class="text-xl font-semibold">单 PDF / 图片审核资料</h2>
          <p class="mt-2 text-sm">{{ documentComparisonRecord.customerName }} · 合同 {{ documentComparisonRecord.contractNumber }} · ITEM {{ documentComparisonRecord.item }}</p>
          <p class="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{{ isImageReference(documentComparisonRecord) ? '图片资料供 QC 人工对照和照片留档。' : 'PDF 审核通过后可用于 QC 文字核对。' }}<template v-if="documentComparisonRecord.documentCheckResult?.review_note"> 备注：{{ documentComparisonRecord.documentCheckResult.review_note }}</template></p>
          <div class="mt-3 flex flex-wrap gap-2">
            <button v-for="source in documentComparisonRecord.documentCheckResult?.source_assets" :key="source.id" type="button" class="rounded-lg border px-3 py-2 text-sm" @click="openReviewOriginal(documentComparisonRecord, source.id)">查看原稿：{{ source.file_name }}</button>
            <button type="button" class="rounded-lg border px-3 py-2 text-sm" @click="openTemplateDocument(documentComparisonRecord, 'print_pdf')">{{ isImageReference(documentComparisonRecord) ? '查看图片合并预览' : '查看 PDF' }}</button>
            <button v-if="canReleaseTemplate && !documentComparisonRecord.qcReady" type="button" :disabled="isManualReleasing" class="rounded-lg bg-amber-700 px-3 py-2 text-sm text-white disabled:opacity-50" @click="openManualRelease(documentComparisonRecord)">审核通过</button>
          </div>
          <p v-if="documentComparisonRecord.manualReleased" class="mt-3 text-sm text-emerald-800">人工审核通过：{{ documentComparisonRecord.manualReleasedByName }} · {{ formatDate(documentComparisonRecord.manualReleasedAt) }}；依据：{{ documentComparisonRecord.manualReleaseReason }}</p>
        </section>
        <section
          v-if="isWarehouseWorkspace && documentComparisonRecord && !isManualReview(documentComparisonRecord)"
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
          ref="photoFormPanel"
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
            <div v-if="selectedTemplateForPhoto && isImageReference(selectedTemplateForPhoto)" class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
              图片资料暂仅支持人工对照。保存照片后请查看原图并复核。
              <div class="mt-2 flex flex-wrap gap-2"><button v-for="source in selectedTemplateForPhoto.documentCheckResult?.source_assets" :key="source.id" type="button" class="rounded-lg border bg-white px-3 py-2 text-xs" @click="openReviewOriginal(selectedTemplateForPhoto, source.id)">查看原图：{{ source.file_name }}</button></div>
            </div>
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
                  aria-label="选择箱唛模板"
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

            <p
              v-if="customerOptionsErrorMessage"
              class="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"
            >
              {{ customerOptionsErrorMessage }}
              <button type="button" class="font-semibold underline underline-offset-2" @click="reloadCustomerOptions">重试</button>
            </p>

            <div
              v-if="selectedTemplateForPhoto"
              class="rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-800"
            >
              {{ selectedTemplateForPhoto.customerName }} · 合同：{{ selectedTemplateForPhoto.contractNumber || '未填写' }} · ITEM：{{ selectedTemplateForPhoto.item }}
            </div>

            <div v-else-if="filteredTemplateOptions.length" class="rounded-lg border border-dashed border-blue-200 bg-blue-50/50 px-4 py-4 text-sm text-slate-600">
              请选择已核对或审核通过的资料，再上传现场箱唛照片。
            </div>

            <div v-else-if="records.length" class="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-500">
              当前客名没有可用资料，请先完成核对或审核。
            </div>

            <div v-else class="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-500">
              当前厂区还没有可流转 QC 的资料，请先上传并完成核对或审核。
            </div>
          </div>

          <p class="mt-5 rounded-lg border border-dashed border-blue-200 bg-blue-50/50 px-4 py-3 text-xs leading-5 text-slate-600">
            正唛和侧唛均可一次选择多张，每张照片独立留档。PDF 资料会自动核对文字；图片资料请人工对照。
            手机可直接拍照，优先使用后置摄像头；再次拍照会追加图片。拍后可旋转、裁剪，点击下方按钮才上传。
          </p>

          <div class="mt-4 grid gap-4 md:grid-cols-2">
            <div
              class="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-5"
              @dragover.prevent
              @drop.prevent="handleBatchPhotoDrop($event, 'front')"
            >
              <input
                ref="frontBatchPhotoFileInput"
                type="file"
                accept="image/*"
                multiple
                class="hidden"
                :disabled="!canUploadPhoto"
                @change="handleBatchPhotoFileChange($event, 'front')"
              >
              <input ref="frontCameraInput" type="file" accept="image/*" capture="environment" aria-label="拍摄正唛照片" class="hidden" :disabled="!canUploadPhoto || isSavingBatchPhoto" @change="handleCameraPhotoChange($event, 'front')">
              <div class="flex flex-col gap-4">
                <div class="flex min-w-0 items-center gap-3">
                  <div class="flex size-11 shrink-0 items-center justify-center rounded-lg bg-white text-blue-700">
                    <ImageIcon class="size-5" aria-hidden="true" />
                  </div>
                  <div class="min-w-0 flex-1">
                    <p class="truncate text-sm font-semibold text-slate-900">{{ selectedFrontBatchFilesLabel }}</p>
                    <p class="mt-1 text-xs text-slate-500">正唛图片 · 可一次选择多张；一张只保留一块正唛</p>
                    <p class="mt-1 text-xs font-medium text-blue-700">可点击选择或拖拽多张正唛到此处</p>
                  </div>
                </div>
                <div class="flex shrink-0 flex-wrap items-center gap-2">
                  <button v-if="canUploadPhoto" type="button" aria-label="拍摄正唛" :disabled="isSavingBatchPhoto || isRotatingPhoto.front" class="inline-flex h-11 items-center gap-1.5 rounded-lg border border-blue-200 bg-white px-3 text-sm font-semibold text-blue-700 disabled:opacity-50" @click="openPhotoCamera('front')"><Camera class="size-4" aria-hidden="true" />{{ selectedFrontBatchFiles.length ? '再拍正唛' : '拍照正唛' }}</button>
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
                      type="button"
                      aria-label="当前正唛向左旋转 90 度"
                      :disabled="isRotatingPhoto.front"
                      class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-600 transition hover:border-blue-200 hover:text-blue-700 disabled:cursor-wait disabled:opacity-50"
                      @click="rotateActiveBatchPhoto('front', -90)"
                    >
                      <RotateCcw class="size-3.5" aria-hidden="true" />
                      左转
                    </button>
                    <button
                      type="button"
                      aria-label="当前正唛向右旋转 90 度"
                      :disabled="isRotatingPhoto.front"
                      class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-600 transition hover:border-blue-200 hover:text-blue-700 disabled:cursor-wait disabled:opacity-50"
                      @click="rotateActiveBatchPhoto('front', 90)"
                    >
                      <RotateCw class="size-3.5" aria-hidden="true" />
                      右转
                    </button>
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

            <div
              class="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-5"
              @dragover.prevent
              @drop.prevent="handleBatchPhotoDrop($event, 'side')"
            >
              <input
                ref="sideBatchPhotoFileInput"
                type="file"
                accept="image/*"
                multiple
                class="hidden"
                :disabled="!canUploadPhoto"
                @change="handleBatchPhotoFileChange($event, 'side')"
              >
              <input ref="sideCameraInput" type="file" accept="image/*" capture="environment" aria-label="拍摄侧唛照片" class="hidden" :disabled="!canUploadPhoto || isSavingBatchPhoto" @change="handleCameraPhotoChange($event, 'side')">
              <div class="flex flex-col gap-4">
                <div class="flex min-w-0 items-center gap-3">
                  <div class="flex size-11 shrink-0 items-center justify-center rounded-lg bg-white text-blue-700">
                    <ImageIcon class="size-5" aria-hidden="true" />
                  </div>
                  <div class="min-w-0 flex-1">
                    <p class="truncate text-sm font-semibold text-slate-900">{{ selectedSideBatchFilesLabel }}</p>
                    <p class="mt-1 text-xs text-slate-500">侧唛图片 · 可一次选择多张；一张只保留一块侧唛</p>
                    <p class="mt-1 text-xs font-medium text-blue-700">可点击选择或拖拽多张侧唛到此处</p>
                  </div>
                </div>
                <div class="flex shrink-0 flex-wrap items-center gap-2">
                  <button v-if="canUploadPhoto" type="button" aria-label="拍摄侧唛" :disabled="isSavingBatchPhoto || isRotatingPhoto.side" class="inline-flex h-11 items-center gap-1.5 rounded-lg border border-blue-200 bg-white px-3 text-sm font-semibold text-blue-700 disabled:opacity-50" @click="openPhotoCamera('side')"><Camera class="size-4" aria-hidden="true" />{{ selectedSideBatchFiles.length ? '再拍侧唛' : '拍照侧唛' }}</button>
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
                      type="button"
                      aria-label="当前侧唛向左旋转 90 度"
                      :disabled="isRotatingPhoto.side"
                      class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-600 transition hover:border-blue-200 hover:text-blue-700 disabled:cursor-wait disabled:opacity-50"
                      @click="rotateActiveBatchPhoto('side', -90)"
                    >
                      <RotateCcw class="size-3.5" aria-hidden="true" />
                      左转
                    </button>
                    <button
                      type="button"
                      aria-label="当前侧唛向右旋转 90 度"
                      :disabled="isRotatingPhoto.side"
                      class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-600 transition hover:border-blue-200 hover:text-blue-700 disabled:cursor-wait disabled:opacity-50"
                      @click="rotateActiveBatchPhoto('side', 90)"
                    >
                      <RotateCw class="size-3.5" aria-hidden="true" />
                      右转
                    </button>
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

          <div class="mt-4 space-y-2">
            <p v-if="photoForm.correctsRecordId" class="text-sm font-semibold text-amber-700">整改原记录：{{ photoForm.correctsRecordId }} · 新照片另行留档</p>
            <label class="block text-sm font-semibold text-slate-700" for="qc-upload-note">{{ photoForm.correctsRecordId ? '整改说明（至少 5 字）' : '现场说明（选填）' }}</label>
            <textarea id="qc-upload-note" v-model="photoForm.note" :disabled="isSavingBatchPhoto" maxlength="1000" rows="2" class="w-full rounded-lg border border-slate-200 p-3 text-sm" />
            <button v-if="photoForm.correctsRecordId" type="button" class="text-xs text-slate-500" @click="photoForm.correctsRecordId = ''; photoForm.note = ''">取消整改关联</button>
            <p class="text-xs text-slate-500">保存到服务器后可跨设备查询。{{ selectedTemplateForPhoto && isImageReference(selectedTemplateForPhoto) ? '图片资料需人工对照。' : '自动核对结果需人工确认。' }}每次最多 20 张、合计 100 MB。</p>
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
              <p class="mt-1 text-sm text-slate-500">服务器保存照片原件、资料版本和复核历史；本机旧记录仅供查阅。</p>
            </div>
            <span class="w-fit rounded-full bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700">{{ photoRecords.length }} 条实拍</span>
          </div>

          <div class="mt-4 flex flex-wrap items-center gap-2">
            <input v-model="qcContractFilter" aria-label="查询 QC 合同号" maxlength="128" placeholder="合同号（完整）" class="min-w-0 rounded-lg border border-slate-200 px-3 py-2 text-sm">
            <input v-model="qcItemFilter" aria-label="查询 QC 货号" maxlength="128" placeholder="货号（完整）" class="min-w-0 rounded-lg border border-slate-200 px-3 py-2 text-sm">
            <button type="button" :disabled="loadingServerPhotos" class="rounded-lg border border-blue-200 px-3 py-2 text-sm text-blue-700" @click="loadServerPhotos()">{{ loadingServerPhotos ? '查询中' : '查询留档' }}</button>
            <button type="button" class="text-xs text-slate-500" @click="qcContractFilter = ''; qcItemFilter = ''; loadServerPhotos()">查看全部</button>
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
                <p class="mt-1 text-xs font-semibold text-blue-700">{{ photo.server ? `服务器留档 · 资料 V${photo.server.template_version} · ${photo.server.created_by_name}` : '历史本机记录 · 未上传服务器' }}</p>
                <p class="mt-1 text-xs text-slate-500">{{ formatDate(photo.uploadedAt) }} · {{ photo.id }}</p>
                <p v-if="photo.server?.note" class="mt-1 text-xs text-slate-600">说明：{{ photo.server.note }}</p>
                <p v-if="photo.server?.corrects_record_id" class="mt-1 text-xs text-amber-700">整改原记录：{{ photo.server.corrects_record_id }}</p>
                <p v-for="correction in allPhotoRecords.filter(p => p.server?.corrects_record_id === photo.id)" :key="correction.id" class="mt-1 text-xs text-blue-700">整改记录：{{ correction.id }} · {{ correction.status }}</p>
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
                    v-if="canReviewPhoto && photo.server && photo.status !== '已作废' && !isImageQcRecord(photo)"
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
                    v-if="canReviewPhoto && photo.server && photo.status !== '已作废'"
                    type="button"
                    class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-green-200 bg-white px-3 text-xs font-semibold text-green-700 transition hover:bg-green-50"
                    @click="reviewPhoto(photo, '核对通过')"
                  >
                    <CheckCircle2 class="size-3.5" aria-hidden="true" />
                    核对通过
                  </button>
                  <button
                    v-if="canReviewPhoto && photo.server && photo.status !== '已作废'"
                    type="button"
                    class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-red-200 bg-white px-3 text-xs font-semibold text-red-700 transition hover:bg-red-50"
                    @click="reviewPhoto(photo, '发现异常')"
                  >
                    <XCircle class="size-3.5" aria-hidden="true" />
                    标记异常
                  </button>
                  <button
                    v-if="canReviewPhoto && photo.server && photo.status !== '已作废'"
                    type="button"
                    :disabled="!!recheckingPhotoId"
                    class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-600 transition hover:border-red-200 hover:bg-red-50 hover:text-red-700 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
                    @click="deletePhotoRecord(photo)"
                  >
                    <Trash2 class="size-3.5" aria-hidden="true" />
                    作废留档
                  </button>
                  <button v-if="canUploadPhoto && photo.server && photo.status === '发现异常'" type="button" class="rounded-lg border border-amber-200 bg-white px-3 py-1 text-xs font-semibold text-amber-700" @click="startCorrection(photo)">提交整改照片</button>
                </div>
              </div>
            </article>
          </div>

          <button v-if="allPhotoRecords.filter(p => p.server).length < serverPhotoTotal" type="button" :disabled="loadingServerPhotos" class="mt-4 rounded-lg border border-slate-200 px-4 py-2 text-sm" @click="loadServerPhotos(true)">{{ loadingServerPhotos ? '读取中' : '加载更多服务器记录' }}</button>

          <section
            v-if="comparisonRecord"
            class="mt-6 border-t border-slate-200 pt-6"
          >
            <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p class="text-xs font-semibold uppercase tracking-[0.18em] text-blue-700">AUTO CHECK</p>
                <h3 class="mt-2 text-lg font-semibold tracking-tight text-slate-950">{{ isImageQcRecord(comparisonRecord) ? '图片资料人工核验' : '自动核对结果' }}</h3>
                <p class="mt-1 text-xs text-slate-600">
                  {{ comparisonRecord.customerName }} · 合同：{{ comparisonRecord.contractNumber || '未填写' }} · ITEM：{{ comparisonRecord.item }}
                  <span v-if="comparisonRecord.server"> · 留档资料 V{{ comparisonRecord.server.template_version }} · {{ comparisonRecord.status }}</span>
                </p>
                <p v-if="viewedAutoTime" class="mt-1 text-xs text-slate-500">
                  {{ viewedAutoRevision ? `正在查看第 ${viewedAutoRevision} 次自动核对` : '自动核对' }}：{{ formatDate(viewedAutoTime) }}
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

            <div v-if="comparisonRecord.server" class="mt-4 space-y-3 rounded-lg border border-slate-200 p-4">
              <h4 class="text-sm font-semibold text-slate-900">留档与复核历史</h4>
              <div v-if="comparisonRecord.server.template_snapshot.review_method === 'manual_sources'" class="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
                <p>本次资料已经内部审核通过。{{ isImageQcRecord(comparisonRecord) ? '图片仅供人工对照。' : 'PDF 用于文字核对。' }}</p>
                <p class="mt-1">审核人：{{ comparisonRecord.server.template_snapshot.manual_released_by_name }} · {{ comparisonRecord.server.template_snapshot.manual_released_at }}</p>
                <div class="mt-2 flex flex-wrap gap-2"><button v-for="source in comparisonReviewSources" :key="source.id" type="button" class="rounded-lg border bg-white px-3 py-2 text-xs" @click="openQcReviewOriginal(comparisonRecord, source.id)">查看当时原稿：{{ source.file_name }}</button></div>
              </div>
              <div v-for="event in comparisonRecord.server.events" :key="event.revision" class="border-b border-slate-100 pb-2 text-xs text-slate-600">
                <p>第 {{ event.revision }} 次 · {{ isImageQcRecord(comparisonRecord) && event.revision === 1 && event.kind === 'REVIEW' ? '照片留档' : event.kind === 'AUTO_CHECK' ? '自动核对' : event.kind === 'VOID' ? '作废' : '人工复核' }} · {{ event.status }} · {{ event.actor_name }} · {{ formatDate(event.created_at) }}</p>
                <p v-if="event.note" class="mt-1">{{ event.note }}</p>
                <p v-if="event.error" class="mt-1 text-amber-700">{{ event.error }}</p>
                <button v-if="event.result" type="button" class="mt-1 text-blue-700" @click="autoCheckResult = event.result; autoCheckErrorMessage = event.error; viewedAutoRevision = event.revision; viewedAutoTime = event.created_at">查看第 {{ event.revision }} 次自动核对结果</button>
              </div>
              <template v-if="canReviewPhoto && comparisonRecord.status !== '已作废'">
                <label for="qc-review-note" class="block text-sm font-semibold text-slate-700">复核说明（异常、作废至少 5 字）</label>
                <textarea id="qc-review-note" v-model="reviewNote" maxlength="1000" rows="2" class="w-full rounded-lg border border-slate-200 p-3 text-sm" />
                <div class="flex flex-wrap gap-2">
                  <button type="button" :disabled="!!recheckingPhotoId" class="rounded-lg border border-green-200 px-3 py-2 text-sm text-green-700" @click="reviewPhoto(comparisonRecord, '核对通过')">确认核对通过</button>
                  <button type="button" :disabled="!!recheckingPhotoId" class="rounded-lg border border-red-200 px-3 py-2 text-sm text-red-700" @click="reviewPhoto(comparisonRecord, '发现异常')">确认发现异常</button>
                  <button type="button" :disabled="!!recheckingPhotoId" class="rounded-lg border border-slate-200 px-3 py-2 text-sm" @click="deletePhotoRecord(comparisonRecord)">确认作废留档</button>
                </div>
              </template>
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
              {{ isImageQcRecord(comparisonRecord) ? '照片已留档。请打开当时原图，与现场照片人工对照后确认核对通过或标记异常。' : '自动核对结果尚未生成，请选择 PDF 模板并上传现场照片后开始自动核对。' }}
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
                        v-if="frontLeftLabelFeedback.total === 0 && comparisonRecord.server && canReviewPhoto && comparisonRecord.status !== '已作废'"
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
                        v-if="sideLeftLabelFeedback.total === 0 && comparisonRecord.server && canReviewPhoto && comparisonRecord.status !== '已作废'"
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
              {{ isWarehouseWorkspace ? '按客户查看客人 Excel、打印 PDF、自动核对与人工放行记录。' : '选用已确认资料：PDF 支持文字核对，图片资料供人工对照。' }}
            </p>
          </div>
          <input
            v-model.trim="searchKeyword"
            type="search"
            class="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm text-slate-900 outline-none transition focus:border-teal-500 focus:ring-4 focus:ring-teal-50 md:w-56"
            :placeholder="isWarehouseWorkspace ? '搜索客名 / ITEM / 合同号' : '搜索客名 / 合同号 / ITEM'"
          >
          <button type="button" aria-label="刷新箱唛核对资料" :disabled="isLoading || isSaving || isSavingBatchPhoto || isManualReleasing || Boolean(recheckingDocumentId)" class="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold disabled:opacity-50" @click="refreshTemplates"><RefreshCw class="size-4" aria-hidden="true" />刷新资料</button>
        </div>
        <RouterLink v-if="!isWarehouseWorkspace && canOpenWarehouse" :to="{ path: '/modules/pmc-warehouse/carton-mark-check', query: { factory: activeFactoryId, panel: 'check' } }" class="mt-3 inline-flex text-sm font-semibold text-teal-700 underline underline-offset-2">查看纸箱部资料核对</RouterLink>

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
                  {{ isManualReview(record) ? `人工审核资料：${record.documentCheckResult?.source_assets?.map(source => source.file_name).join('、')}` : `客人 Excel：${record.excelFileName || '旧资料未上传'}` }}<template v-if="record.excelFileSize"> · {{ formatFileSize(record.excelFileSize) }}</template>
                </p>
                <p class="truncate text-sm text-slate-500" :class="isWarehouseWorkspace ? 'mt-1' : 'mt-2'">
                  {{ isImageReference(record) ? '图片合并预览' : isManualReview(record) ? 'QC 参考 PDF' : '打印 PDF' }}：{{ record.fileName }} · {{ formatFileSize(record.fileSize) }}
                </p>
              </div>

              <div class="flex shrink-0 flex-wrap items-center gap-2 text-sm">
                <RouterLink v-if="isWarehouseWorkspace && record.qcReady && canOpenQc" :to="{ path: '/modules/qc/carton-mark-check', query: { factory: record.factoryId, template: record.id } }" :aria-label="`用模板 ${record.fileName} 打开 QC 核验`" class="inline-flex rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 font-semibold text-blue-700">打开 QC 核验</RouterLink>
                <button v-if="!isWarehouseWorkspace && record.qcReady && canUploadPhoto" type="button" :aria-label="`选用模板 ${record.fileName}`" :disabled="isSavingBatchPhoto" class="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 font-semibold text-blue-700 disabled:opacity-50" @click="selectQcTemplate(record)">{{ photoForm.templateId === record.id ? '已选用' : '选用此模板' }}</button>
                <span
                  class="rounded-full border px-3 py-1 font-semibold"
                  :class="record.documentCheckResult ? getDocumentCheckStatusClass(record.documentCheckResult.summary.overall_status) : 'border-slate-200 bg-slate-100 text-slate-600'"
                >
                  {{ isManualReview(record) ? record.manualReleased ? '人工审核通过' : '待人工审核' : record.documentCheckResult?.summary.overall_status || '待补 Excel 核对' }}
                </span>
                <span
                  v-if="record.manualReleased"
                  class="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 font-semibold text-emerald-700"
                >
                  人工放行
                </span>
                <button
                  v-if="canReleaseTemplate && !record.qcReady"
                  type="button"
                  :disabled="isManualReleasing"
                  class="inline-flex items-center gap-1 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 font-semibold text-amber-800 transition hover:bg-amber-100"
                  @click="openManualRelease(record)"
                >
                  <CheckCircle2 class="size-4" aria-hidden="true" />
                  {{ isManualReview(record) ? isManualReleasing && manualReleaseRecord?.id === record.id ? '审核中…' : '审核通过' : '人工审核放行' }}
                </button>
                <button
                  v-if="isWarehouseWorkspace && record.excelFileName"
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
                  {{ downloadingDocumentKey === `${record.id}:print_pdf` ? '读取中' : isImageReference(record) ? '图片合并预览' : isManualReview(record) ? 'QC 参考 PDF' : '打印 PDF' }}
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
            <div
              v-if="record.manualReleased"
              class="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800"
            >
              <p class="font-semibold">人工放行：{{ record.manualReleasedByName }} · {{ formatDate(record.manualReleasedAt) }}</p>
              <p v-if="!isManualReview(record)" class="mt-1">自动核对状态：{{ record.manualReleaseSourceStatus || record.checkStatus }}；理由：{{ record.manualReleaseReason }}</p>
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
    <div
      v-if="manualReleaseRecord && !isManualReview(manualReleaseRecord)"
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4"
      role="presentation"
      @click.self="closeManualRelease"
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="carton-mark-manual-release-title"
        class="w-full max-w-lg rounded-xl border border-slate-200 bg-white p-6 shadow-2xl"
      >
        <div class="flex items-start justify-between gap-4">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.18em] text-amber-700">MANUAL RELEASE</p>
            <h2 id="carton-mark-manual-release-title" class="mt-2 text-xl font-semibold text-slate-950">人工审核放行箱唛模板</h2>
            <p class="mt-2 text-sm text-slate-600">
              {{ manualReleaseRecord.customerName }} · 合同：{{ manualReleaseRecord.contractNumber || '未填写' }} · ITEM：{{ manualReleaseRecord.item }}
            </p>
          </div>
          <button
            type="button"
            aria-label="关闭人工放行窗口"
            :disabled="isManualReleasing"
            class="rounded-lg border border-slate-200 p-2 text-slate-500 transition hover:bg-slate-50 disabled:opacity-50"
            @click="closeManualRelease"
          >
            <XCircle class="size-5" aria-hidden="true" />
          </button>
        </div>

        <div class="mt-5 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-900">
          当前自动核对结果为“{{ manualReleaseRecord.checkStatus || '需复核' }}”。人工放行不会改写该结果，但会允许 QC 选用此模板；重新自动核对后，本次放行将自动撤销。
        </div>

        <label class="mt-5 block" for="carton-mark-manual-release-reason">
          <span class="text-sm font-semibold text-slate-800">放行理由 <span class="text-red-600">*</span></span>
          <textarea
            id="carton-mark-manual-release-reason"
            v-model="manualReleaseReason"
            rows="4"
            maxlength="500"
            :disabled="isManualReleasing"
            class="mt-2 w-full resize-y rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-amber-500 focus:ring-4 focus:ring-amber-50 disabled:bg-slate-100"
            placeholder="请说明已人工核对的内容、差异可接受原因或现场处置依据（至少 5 个字符）"
          />
        </label>
        <div class="mt-1 flex items-start justify-between gap-3 text-xs">
          <p class="text-slate-500">审核人：{{ currentUserName }}；系统记录理由和审核时间。</p>
          <span class="shrink-0 text-slate-400">{{ manualReleaseReason.length }}/500</span>
        </div>
        <p v-if="manualReleaseError" role="alert" class="mt-3 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-sm text-red-700">
          {{ manualReleaseError }}
        </p>

        <div class="mt-6 flex justify-end gap-3">
          <button
            type="button"
            :disabled="isManualReleasing"
            class="h-10 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
            @click="closeManualRelease"
          >
            取消
          </button>
          <button
            type="button"
            :disabled="isManualReleasing || manualReleaseReason.trim().length < 5"
            class="inline-flex h-10 items-center gap-2 rounded-lg bg-amber-600 px-4 text-sm font-semibold text-white transition hover:bg-amber-700 disabled:cursor-not-allowed disabled:bg-slate-300"
            @click="confirmManualRelease"
          >
            <CheckCircle2 class="size-4" aria-hidden="true" />
            {{ isManualReleasing ? '正在放行' : '确认人工放行' }}
          </button>
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
