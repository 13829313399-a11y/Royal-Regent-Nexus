<script setup lang="ts">
import { CheckCircle2, Crop, Eye, FileText, Image as ImageIcon, Plus, RefreshCw, Trash2, UploadCloud, XCircle } from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { cartonMarkApi, type CartonMarkAutoCheckResponse, type CartonMarkComparisonItem } from '@/api/cartonMark'
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
  fileName: string
  fileSize: number
  uploadedAt: string
  version: number
  pdfUrl?: string
  fileBlob?: Blob
}

interface StoredCartonMarkTemplateRecord extends Omit<CartonMarkTemplateRecord, 'pdfUrl' | 'factoryId' | 'factoryName'> {
  factoryId?: ProductionFactoryContextId
  factoryName?: string
}

interface CartonMarkPhotoRecord {
  id: string
  templateId: string
  factoryId: ProductionFactoryContextId
  factoryName: string
  customerName: string
  po: string
  item: string
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

interface StoredCartonMarkPhotoRecord extends Omit<CartonMarkPhotoRecord, 'imageUrl' | 'frontImageUrl' | 'sideImageUrl' | 'factoryId' | 'factoryName'> {
  factoryId?: ProductionFactoryContextId
  factoryName?: string
}

type CartonMarkPhotoSide = 'front' | 'side'

interface PhotoCropState {
  enabled: boolean
  isDragging: boolean
  startPoint: { x: number, y: number } | null
  selection: NormalizedCropSelection | null
  applied: boolean
  errorMessage: string
}

interface CustomerNameRecord {
  id: string
  factoryId: ProductionFactoryContextId
  factoryName: string
  name: string
  createdAt: string
}

const DB_NAME = 'rr-carton-mark-library'
const DB_VERSION = 2
const STORE_NAME = 'cartonMarkTemplates'
const PHOTO_STORE_NAME = 'cartonMarkPhotos'
const LOCAL_STORAGE_KEY = 'rr-carton-mark-library-records'
const PHOTO_LOCAL_STORAGE_KEY = 'rr-carton-mark-photo-records'
const CUSTOMER_STORAGE_KEY = 'rr-carton-mark-customer-library'
const ALL_CUSTOMERS = '全部'

const appStore = useAppStore()
const authStore = useAuthStore()
const route = useRoute()

const form = reactive({
  customerName: '',
  po: '',
  item: '',
})

const photoForm = reactive({
  customerName: ALL_CUSTOMERS,
  templateId: '',
})

const allRecords = ref<CartonMarkTemplateRecord[]>([])
const allPhotoRecords = ref<CartonMarkPhotoRecord[]>([])
const customerLibrary = ref<CustomerNameRecord[]>([])
const selectedFile = ref<File | null>(null)
const selectedFrontPhotoFile = ref<File | null>(null)
const selectedSidePhotoFile = ref<File | null>(null)
const selectedFrontPreviewUrl = ref('')
const selectedSidePreviewUrl = ref('')
const frontPreviewImage = ref<HTMLImageElement | null>(null)
const sidePreviewImage = ref<HTMLImageElement | null>(null)
const photoPreviewRenderTick = ref(0)
const fileInput = ref<HTMLInputElement | null>(null)
const frontPhotoFileInput = ref<HTMLInputElement | null>(null)
const sidePhotoFileInput = ref<HTMLInputElement | null>(null)
const comparisonRecord = ref<CartonMarkPhotoRecord | null>(null)
const autoCheckResult = ref<CartonMarkAutoCheckResponse | null>(null)
const autoCheckErrorMessage = ref('')
const recheckingPhotoId = ref('')
const activeCustomer = ref(ALL_CUSTOMERS)
const newCustomerName = ref('')
const searchKeyword = ref('')
const errorMessage = ref('')
const successMessage = ref('')
const photoErrorMessage = ref('')
const photoSuccessMessage = ref('')
const customerMessage = ref('')
const isLoading = ref(false)
const isSaving = ref(false)
const isSavingPhoto = ref(false)
const deletingRecordId = ref('')
const deletingPhotoRecordId = ref('')
const storageMode = ref<'indexedDb' | 'localStorage'>('indexedDb')
const pdfUrls = new Set<string>()
const imageUrls = new Set<string>()
const photoCropState = reactive<Record<CartonMarkPhotoSide, PhotoCropState>>({
  front: createPhotoCropState(),
  side: createPhotoCropState(),
})

const activeFactory = computed(() => appStore.activeProductionFactory)
const activeFactoryId = computed(() => activeFactory.value.id as ProductionFactoryContextId)
const currentDepartmentId = computed(() => String(route.params.department ?? 'qa'))
const isWarehouseWorkspace = computed(() => currentDepartmentId.value === 'pmc-warehouse')
const isAdmin = computed(() => authStore.hasPermission('system:user_manage'))
const canUploadTemplate = computed(() => isAdmin.value || authStore.hasPermission('carton_mark:template_upload'))
const canUploadPhoto = computed(() => isAdmin.value || authStore.hasPermission('carton_mark:photo_upload'))
const canReviewPhoto = computed(() => isAdmin.value || authStore.hasPermission('carton_mark:review'))
const canDeleteTemplate = computed(() => isWarehouseWorkspace.value && canUploadTemplate.value)
const currentUserName = computed(() => authStore.currentUser?.display_name ?? '当前账号')
const workspaceLabel = computed(() => isWarehouseWorkspace.value ? '纸箱部仓管模板库' : 'QA 箱唛实拍核验')
const templatePermissionHint = computed(() => {
  if (canUploadTemplate.value) {
    return isWarehouseWorkspace.value
      ? '当前账号可维护客名库，并上传客户箱唛 PDF 模板。'
      : '当前账号具备模板维护权限，也可在这里补录客户箱唛 PDF。'
  }

  return '当前账号只能查看模板资料；纸箱部仓管账号可维护客名库并上传 PDF。'
})
const photoPermissionHint = computed(() => {
  if (canUploadPhoto.value) {
    return '当前账号可上传纸箱到厂后的箱唛实拍图片，并交给 QA 核对。'
  }

  return '当前账号只能查看实拍记录；QA 检验员账号可上传图片并核对箱唛。'
})

const records = computed(() => {
  return sortRecords(allRecords.value.filter((record) => record.factoryId === activeFactoryId.value))
})

const photoRecords = computed(() => {
  return sortPhotoRecords(allPhotoRecords.value.filter((record) => record.factoryId === activeFactoryId.value))
})

const factoryCustomers = computed(() => {
  return customerLibrary.value
    .filter((customer) => customer.factoryId === activeFactoryId.value)
    .sort((left, right) => left.name.localeCompare(right.name, 'zh-CN'))
})

const selectedFileLabel = computed(() => {
  if (!selectedFile.value) return '未选择 PDF'

  return `${selectedFile.value.name} · ${formatFileSize(selectedFile.value.size)}`
})

const selectedFrontPhotoFileLabel = computed(() => {
  if (!selectedFrontPhotoFile.value) return '未选择正唛图片'

  return `${selectedFrontPhotoFile.value.name} · ${formatFileSize(selectedFrontPhotoFile.value.size)}`
})

const selectedSidePhotoFileLabel = computed(() => {
  if (!selectedSidePhotoFile.value) return '未选择侧唛图片'

  return `${selectedSidePhotoFile.value.name} · ${formatFileSize(selectedSidePhotoFile.value.size)}`
})

const hasSelectedCustomer = computed(() => {
  return factoryCustomers.value.some((customer) => normalizeKey(customer.name) === normalizeKey(form.customerName))
})

const canSubmit = computed(() => {
  return Boolean(
    canUploadTemplate.value
    && hasSelectedCustomer.value
    && form.po.trim()
    && form.item.trim()
    && selectedFile.value
    && isPdfFile(selectedFile.value),
  )
})

const selectedTemplateForPhoto = computed(() => {
  return records.value.find((record) => record.id === photoForm.templateId)
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

  return '已匹配到模板资料，但 PDF 原件没有保存在当前浏览器。请在纸箱仓管端重新上传这份 PDF。'
})

const templateCustomerOptions = computed(() => {
  const customerMap = new Map<string, { name: string, count: number }>()

  for (const record of records.value) {
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
  if (photoForm.customerName === ALL_CUSTOMERS) return records.value

  const customer = normalizeKey(photoForm.customerName)
  return records.value.filter((record) => normalizeKey(record.customerName) === customer)
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
const photoSubmitLabel = computed(() => {
  if (isSavingPhoto.value) return '对比中'
  return hasBothSelectedPhotos.value ? '开始自动核对' : '上传正唛和侧唛'
})
const autoCheckComparisons = computed(() => autoCheckResult.value?.comparisons ?? [])
const frontAutoCheckComparisons = computed(() => {
  return autoCheckComparisons.value.filter((item) => item.side === 'front')
})
const sideAutoCheckComparisons = computed(() => {
  return autoCheckComparisons.value.filter((item) => item.side === 'side')
})
const autoCheckExtractionMessages = computed(() => {
  return (autoCheckResult.value?.extraction ?? []).filter((status) => status.message || !status.ok)
})

const customerGroups = computed(() => {
  const recordCounts = new Map<string, { count: number, latestAt: string }>()

  for (const record of records.value) {
    const key = normalizeKey(record.customerName)
    const current = recordCounts.get(key)
    if (!current) {
      recordCounts.set(key, {
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

  return factoryCustomers.value.map((customer) => {
    const stats = recordCounts.get(normalizeKey(customer.name))

    return {
      name: customer.name,
      count: stats?.count ?? 0,
      latestAt: stats?.latestAt ?? customer.createdAt,
    }
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
      record.fileName,
    ].some((value) => normalizeKey(value).includes(keyword))

    return matchesCustomer && matchesKeyword
  })
})

const uniqueCustomerCount = computed(() => {
  return factoryCustomers.value.length
})

const latestRecord = computed(() => records.value[0])
const latestPhotoRecord = computed(() => photoRecords.value[0])

onMounted(async () => {
  isLoading.value = true

  try {
    const [storedRecords, storedPhotoRecords] = await Promise.all([
      readRecordsFromDb(),
      readPhotoRecordsFromDb(),
    ])
    storageMode.value = 'indexedDb'
    allRecords.value = sortRecords(storedRecords.map(normalizeStoredRecord).map(hydrateRecord))
    allPhotoRecords.value = sortPhotoRecords(storedPhotoRecords.map(normalizeStoredPhotoRecord).map(hydratePhotoRecord))
  } catch {
    storageMode.value = 'localStorage'
    allRecords.value = sortRecords(readRecordsFromLocalStorage())
    allPhotoRecords.value = sortPhotoRecords(readPhotoRecordsFromLocalStorage())
  } finally {
    customerLibrary.value = readCustomersFromLocalStorage()
    syncCustomerLibraryFromRecords()
    isLoading.value = false
  }
})

watch(activeFactoryId, () => {
  errorMessage.value = ''
  successMessage.value = ''
  photoErrorMessage.value = ''
  photoSuccessMessage.value = ''
  customerMessage.value = ''
  activeCustomer.value = ALL_CUSTOMERS
  photoForm.customerName = ALL_CUSTOMERS
  photoForm.templateId = ''
  resetPhotoSelection()

  if (!factoryCustomers.value.some((customer) => customer.name === form.customerName)) {
    form.customerName = ''
  }
})

watch(() => photoForm.customerName, () => {
  photoForm.templateId = ''
  resetPhotoSelection()
})

watch(() => photoForm.templateId, () => {
  resetPhotoSelection()
})

onBeforeUnmount(() => {
  for (const url of pdfUrls) {
    URL.revokeObjectURL(url)
  }

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

function hydrateRecord(record: StoredCartonMarkTemplateRecord): CartonMarkTemplateRecord {
  return {
    ...record,
    factoryId: record.factoryId ?? activeFactoryId.value,
    factoryName: record.factoryName ?? activeFactory.value.shortName,
    pdfUrl: record.fileBlob ? createPdfUrl(record.fileBlob) : undefined,
  }
}

function normalizeStoredRecord(record: StoredCartonMarkTemplateRecord): StoredCartonMarkTemplateRecord {
  return {
    ...record,
    factoryId: record.factoryId ?? activeFactoryId.value,
    factoryName: record.factoryName ?? activeFactory.value.shortName,
  }
}

function hydratePhotoRecord(record: StoredCartonMarkPhotoRecord): CartonMarkPhotoRecord {
  const frontImageUrl = record.frontImageBlob
    ? createImageUrl(record.frontImageBlob)
    : record.imageBlob ? createImageUrl(record.imageBlob) : undefined

  return {
    ...record,
    factoryId: record.factoryId ?? activeFactoryId.value,
    factoryName: record.factoryName ?? activeFactory.value.shortName,
    imageUrl: frontImageUrl,
    frontImageUrl,
    sideImageUrl: record.sideImageBlob ? createImageUrl(record.sideImageBlob) : undefined,
  }
}

function normalizeStoredPhotoRecord(record: StoredCartonMarkPhotoRecord): StoredCartonMarkPhotoRecord {
  return {
    ...record,
    factoryId: record.factoryId ?? activeFactoryId.value,
    factoryName: record.factoryName ?? activeFactory.value.shortName,
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
    return normalizeKey(record.customerName) === normalizeKey(photo.customerName)
      && normalizeKey(record.po) === normalizeKey(photo.po)
      && normalizeKey(record.item) === normalizeKey(photo.item)
  })
  if (matchedByPo) return matchedByPo

  const selectedTemplate = selectedTemplateForPhoto.value
  if (
    selectedTemplate
    && normalizeKey(selectedTemplate.customerName) === normalizeKey(photo.customerName)
    && normalizeKey(selectedTemplate.po) === normalizeKey(photo.po)
    && normalizeKey(selectedTemplate.item) === normalizeKey(photo.item)
  ) {
    return selectedTemplate
  }

  return null
}

function showPhotoAutoCheck(photo: CartonMarkPhotoRecord) {
  comparisonRecord.value = photo
  autoCheckResult.value = photo.autoCheckResult ?? null
  autoCheckErrorMessage.value = photo.autoCheckErrorMessage ?? ''
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
  return cartonMarkApi.autoCheck({
    customerName: template.customerName,
    po: template.po,
    item: template.item,
    pdfTemplate: template.fileBlob as Blob,
    frontPhoto,
    sidePhoto,
  })
}

async function replaceStoredPhotoRecord(nextPhoto: CartonMarkPhotoRecord) {
  const nextPhotoRecords = sortPhotoRecords(allPhotoRecords.value.map((record) => {
    return record.id === nextPhoto.id ? nextPhoto : record
  }))

  allPhotoRecords.value = nextPhotoRecords

  try {
    if (storageMode.value === 'indexedDb') {
      await savePhotoRecordSnapshotToDb(nextPhoto)
    } else {
      writePhotoRecordsToLocalStorage(nextPhotoRecords)
    }
  } catch {
    storageMode.value = 'localStorage'
    writePhotoRecordsToLocalStorage(nextPhotoRecords)
  }

  return nextPhoto
}

function resetForm() {
  form.customerName = ''
  form.po = ''
  form.item = ''
  selectedFile.value = null

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

    if (frontPhotoFileInput.value) {
      frontPhotoFileInput.value.value = ''
    }

    return
  }

  selectedSidePhotoFile.value = null
  resetPhotoCropState('side')

  if (selectedSidePreviewUrl.value) {
    revokeImageUrl(selectedSidePreviewUrl.value)
    selectedSidePreviewUrl.value = ''
  }

  if (sidePhotoFileInput.value) {
    sidePhotoFileInput.value.value = ''
  }
}

function resetPhotoSelection(clearComparison = true) {
  clearPhotoSelection('front', clearComparison)
  clearPhotoSelection('side', clearComparison)
}

function readCustomersFromLocalStorage() {
  if (typeof window === 'undefined') return []

  const rawCustomers = window.localStorage.getItem(CUSTOMER_STORAGE_KEY)
  if (!rawCustomers) return []

  try {
    return JSON.parse(rawCustomers) as CustomerNameRecord[]
  } catch {
    return []
  }
}

function writeCustomersToLocalStorage(nextCustomers: CustomerNameRecord[]) {
  if (typeof window === 'undefined') return

  window.localStorage.setItem(CUSTOMER_STORAGE_KEY, JSON.stringify(nextCustomers))
}

function syncCustomerLibraryFromRecords() {
  const nextCustomers = [...customerLibrary.value]

  for (const record of allRecords.value) {
    const exists = nextCustomers.some((customer) => {
      return customer.factoryId === record.factoryId
        && normalizeKey(customer.name) === normalizeKey(record.customerName)
    })

    if (!exists) {
      nextCustomers.push({
        id: `CUST-${record.factoryId}-${Date.now()}-${nextCustomers.length}`,
        factoryId: record.factoryId,
        factoryName: record.factoryName,
        name: record.customerName,
        createdAt: record.uploadedAt,
      })
    }
  }

  customerLibrary.value = nextCustomers
  writeCustomersToLocalStorage(nextCustomers)
}

function addCustomer() {
  const name = newCustomerName.value.trim()
  errorMessage.value = ''
  successMessage.value = ''
  customerMessage.value = ''

  if (!canUploadTemplate.value) {
    customerMessage.value = '当前账号无权维护客名库，请使用纸箱仓管账号操作。'
    return
  }

  if (!name) {
    customerMessage.value = '请输入客名后再新增。'
    return
  }

  const exists = factoryCustomers.value.some((customer) => normalizeKey(customer.name) === normalizeKey(name))
  if (exists) {
    form.customerName = factoryCustomers.value.find((customer) => normalizeKey(customer.name) === normalizeKey(name))?.name ?? name
    newCustomerName.value = ''
    customerMessage.value = `${activeFactory.value.shortName} 已有这个客名。`
    return
  }

  const nextCustomer: CustomerNameRecord = {
    id: `CUST-${activeFactoryId.value}-${Date.now()}`,
    factoryId: activeFactoryId.value,
    factoryName: activeFactory.value.shortName,
    name,
    createdAt: new Date().toISOString(),
  }

  customerLibrary.value = [...customerLibrary.value, nextCustomer]
  writeCustomersToLocalStorage(customerLibrary.value)
  form.customerName = name
  newCustomerName.value = ''
  customerMessage.value = `${activeFactory.value.shortName} 客名库已新增：${name}`
}

function removeCustomer(customer: CustomerNameRecord) {
  customerMessage.value = ''

  if (!canUploadTemplate.value) {
    customerMessage.value = '当前账号无权移除客名，请使用纸箱仓管账号操作。'
    return
  }

  customerLibrary.value = customerLibrary.value.filter((item) => item.id !== customer.id)
  writeCustomersToLocalStorage(customerLibrary.value)

  if (form.customerName === customer.name) {
    form.customerName = ''
  }

  if (activeCustomer.value === customer.name) {
    activeCustomer.value = ALL_CUSTOMERS
  }

  customerMessage.value = `${customer.name} 已从 ${activeFactory.value.shortName} 客名库移除；已上传箱唛资料不会删除。`
}

function openFilePicker() {
  errorMessage.value = ''
  successMessage.value = ''

  if (!canUploadTemplate.value) {
    errorMessage.value = '当前账号无权上传 PDF 资料，请使用纸箱仓管账号操作。'
    return
  }

  fileInput.value?.click()
}

function openPhotoFilePicker(side: CartonMarkPhotoSide) {
  photoErrorMessage.value = ''
  photoSuccessMessage.value = ''

  if (!canUploadPhoto.value) {
    photoErrorMessage.value = '当前账号无权上传实拍图片，请使用 QA 检验员账号操作。'
    return
  }

  if (side === 'front') {
    frontPhotoFileInput.value?.click()
    return
  }

  sidePhotoFileInput.value?.click()
}

function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  errorMessage.value = ''
  successMessage.value = ''

  if (!canUploadTemplate.value) {
    selectedFile.value = null
    input.value = ''
    errorMessage.value = '当前账号无权上传 PDF 资料，请使用纸箱仓管账号操作。'
    return
  }

  if (!file) {
    selectedFile.value = null
    return
  }

  if (!isPdfFile(file)) {
    selectedFile.value = null
    input.value = ''
    errorMessage.value = '只能导入 PDF 箱唛资料。'
    return
  }

  selectedFile.value = file
}

function handlePhotoFileChange(event: Event, side: CartonMarkPhotoSide) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  photoErrorMessage.value = ''
  photoSuccessMessage.value = ''

  if (!canUploadPhoto.value) {
    clearPhotoSelection(side)
    photoErrorMessage.value = '当前账号无权上传实拍图片，请使用 QA 检验员账号操作。'
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

async function submitTemplate() {
  errorMessage.value = ''
  successMessage.value = ''

  if (!canUploadTemplate.value) {
    errorMessage.value = '当前账号无权上传 PDF 资料，请使用纸箱仓管账号操作。'
    return
  }

  if (!selectedFile.value) {
    errorMessage.value = '请先选择 PDF 箱唛资料。'
    return
  }

  if (!canSubmit.value) {
    errorMessage.value = '请先从当前厂区客名库选择客名，并填写 PO、ITEM 和 PDF 资料。'
    return
  }

  isSaving.value = true

  const currentFile = selectedFile.value
  const customerName = form.customerName.trim()
  const po = form.po.trim()
  const item = form.item.trim()
  const version = records.value.filter((record) => {
    return normalizeKey(record.customerName) === normalizeKey(customerName)
      && normalizeKey(record.po) === normalizeKey(po)
      && normalizeKey(record.item) === normalizeKey(item)
  }).length + 1
  const record: CartonMarkTemplateRecord = {
    id: `CM-${Date.now()}`,
    factoryId: activeFactoryId.value,
    factoryName: activeFactory.value.shortName,
    customerName,
    po,
    item,
    fileName: currentFile.name,
    fileSize: currentFile.size,
    uploadedAt: new Date().toISOString(),
    version,
    pdfUrl: createPdfUrl(currentFile),
  }

  try {
    if (storageMode.value === 'indexedDb') {
      await saveRecordToDb(record, currentFile)
    } else {
      writeRecordsToLocalStorage([record, ...allRecords.value])
    }

    allRecords.value = sortRecords([record, ...allRecords.value])
    activeCustomer.value = customerName
    successMessage.value = `${activeFactory.value.shortName} · ${customerName} / ${po} / ${item} 已入库。`
    resetForm()
  } catch {
    storageMode.value = 'localStorage'
    allRecords.value = sortRecords([record, ...allRecords.value])
    writeRecordsToLocalStorage(allRecords.value)
    activeCustomer.value = customerName
    successMessage.value = `${activeFactory.value.shortName} · ${customerName} / ${po} / ${item} 已入库。`
    resetForm()
  } finally {
    isSaving.value = false
  }
}

async function deleteTemplateRecord(record: CartonMarkTemplateRecord) {
  errorMessage.value = ''
  successMessage.value = ''

  if (!canDeleteTemplate.value) {
    errorMessage.value = '当前账号无权删除箱唛资料，请使用纸箱仓管账号操作。'
    return
  }

  const shouldDelete = typeof window === 'undefined'
    || window.confirm(`确定删除 ${record.customerName} / ${record.po} / ${record.item} 的箱唛 PDF 资料吗？`)

  if (!shouldDelete) return

  deletingRecordId.value = record.id
  const nextRecords = sortRecords(allRecords.value.filter((item) => item.id !== record.id))

  try {
    if (storageMode.value === 'indexedDb') {
      await deleteRecordFromDb(record.id)
    } else {
      writeRecordsToLocalStorage(nextRecords)
    }
  } catch {
    storageMode.value = 'localStorage'
    writeRecordsToLocalStorage(nextRecords)
  }

  if (record.pdfUrl) {
    URL.revokeObjectURL(record.pdfUrl)
    pdfUrls.delete(record.pdfUrl)
  }

  allRecords.value = nextRecords

  if (photoForm.templateId === record.id) {
    photoForm.templateId = ''
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

  successMessage.value = `${record.customerName} / ${record.po} / ${record.item} 箱唛资料已删除；QA 实拍记录不会删除。`
  deletingRecordId.value = ''
}

async function submitPhoto() {
  photoErrorMessage.value = ''
  photoSuccessMessage.value = ''
  autoCheckErrorMessage.value = ''
  autoCheckResult.value = null

  if (!canUploadPhoto.value) {
    photoErrorMessage.value = '当前账号无权上传实拍图片，请使用 QA 检验员账号操作。'
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

  if (!template.fileBlob) {
    photoErrorMessage.value = '当前模板只有索引，没有 PDF 原件，无法自动核对。请纸箱仓管重新上传这份 PDF 模板。'
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
  }).length + 1
  const photoRecord: CartonMarkPhotoRecord = {
    id: `CMP-${Date.now()}`,
    templateId: template.id,
    factoryId: activeFactoryId.value,
    factoryName: activeFactory.value.shortName,
    customerName: template.customerName,
    po: template.po,
    item: template.item,
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
    autoCheckResult.value = result
  } catch (error) {
    const message = `自动核对未完成：${getApiErrorMessage(error)}`
    photoRecord.autoCheckErrorMessage = message
    photoRecord.autoCheckedAt = new Date().toISOString()
    autoCheckErrorMessage.value = message
  }

  try {
    if (storageMode.value === 'indexedDb') {
      await savePhotoRecordToDb(photoRecord)
    } else {
      writePhotoRecordsToLocalStorage([photoRecord, ...allPhotoRecords.value])
    }

    allPhotoRecords.value = sortPhotoRecords([photoRecord, ...allPhotoRecords.value])
    resetPhotoSelection(false)
    showPhotoAutoCheck(photoRecord)
    photoSuccessMessage.value = photoRecord.autoCheckResult
      ? `${activeFactory.value.shortName} · ${template.customerName} / ${template.po} / ${template.item} 已生成自动核对结果。`
      : `${activeFactory.value.shortName} · ${template.customerName} / ${template.po} / ${template.item} 实拍图片已保存，可稍后重新自动核对。`
  } catch {
    storageMode.value = 'localStorage'
    allPhotoRecords.value = sortPhotoRecords([photoRecord, ...allPhotoRecords.value])
    writePhotoRecordsToLocalStorage(allPhotoRecords.value)
    resetPhotoSelection(false)
    showPhotoAutoCheck(photoRecord)
    photoSuccessMessage.value = photoRecord.autoCheckResult
      ? `${activeFactory.value.shortName} · ${template.customerName} / ${template.po} / ${template.item} 已生成自动核对结果。`
      : `${activeFactory.value.shortName} · ${template.customerName} / ${template.po} / ${template.item} 实拍图片已保存，可稍后重新自动核对。`
  } finally {
    isSavingPhoto.value = false
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
    photoErrorMessage.value = '当前账号无权重新自动核对箱唛，请使用 QA 检验员账号操作。'
    return
  }

  const template = findTemplateForPhoto(photo)
  if (!template?.fileBlob) {
    photoErrorMessage.value = '没有找到可用于自动核对的 PDF 原件，请纸箱仓管重新上传这份 PDF 模板。'
    showPhotoAutoCheck(photo)
    return
  }

  const frontPhoto = photo.frontImageBlob ?? photo.imageBlob
  const sidePhoto = photo.sideImageBlob
  if (!frontPhoto || !sidePhoto) {
    photoErrorMessage.value = '当前浏览器没有保存完整正唛/侧唛图片原件，请重新上传实拍图片后再自动核对。'
    showPhotoAutoCheck(photo)
    return
  }

  recheckingPhotoId.value = photo.id

  try {
    const result = await runCartonMarkAutoCheck(template, frontPhoto, sidePhoto)
    const checkedPhoto: CartonMarkPhotoRecord = {
      ...photo,
      status: getPhotoStatusFromAutoCheck(result.summary.overall_status),
      autoCheckResult: result,
      autoCheckErrorMessage: '',
      autoCheckedAt: new Date().toISOString(),
    }

    await replaceStoredPhotoRecord(checkedPhoto)
    showPhotoAutoCheck(checkedPhoto)
    photoSuccessMessage.value = `${photo.customerName} / ${photo.po} / ${photo.item} 已重新生成自动核对结果。`
  } catch (error) {
    const message = `自动核对未完成：${getApiErrorMessage(error)}`
    const failedPhoto: CartonMarkPhotoRecord = {
      ...photo,
      autoCheckErrorMessage: message,
      autoCheckedAt: new Date().toISOString(),
    }

    await replaceStoredPhotoRecord(failedPhoto)
    showPhotoAutoCheck(failedPhoto)
    photoErrorMessage.value = message
  } finally {
    recheckingPhotoId.value = ''
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

function formatConfidence(confidence: number) {
  return `${Math.round(confidence * 100)}%`
}

async function deletePhotoRecord(photo: CartonMarkPhotoRecord) {
  photoErrorMessage.value = ''
  photoSuccessMessage.value = ''

  if (isWarehouseWorkspace.value) {
    photoErrorMessage.value = '纸箱部仓管端不能删除 QA 实拍记录，请到 QA 箱唛核验板块操作。'
    return
  }

  const shouldDelete = typeof window === 'undefined'
    || window.confirm(`确定删除 ${photo.customerName} / ${photo.po} / ${photo.item} 的这次箱唛实拍记录吗？删除后可重新上传正唛和侧唛。`)

  if (!shouldDelete) return

  deletingPhotoRecordId.value = photo.id
  const nextPhotoRecords = sortPhotoRecords(allPhotoRecords.value.filter((record) => record.id !== photo.id))

  try {
    if (storageMode.value === 'indexedDb') {
      await deletePhotoRecordFromDb(photo.id)
    } else {
      writePhotoRecordsToLocalStorage(nextPhotoRecords)
    }
  } catch {
    storageMode.value = 'localStorage'
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
    photoErrorMessage.value = '当前账号无权核对箱唛，请使用 QA 检验员账号操作。'
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

function readRecordsFromLocalStorage() {
  if (typeof window === 'undefined') return []

  const rawRecords = window.localStorage.getItem(LOCAL_STORAGE_KEY)
  if (!rawRecords) return []

  try {
    const parsed = JSON.parse(rawRecords) as CartonMarkTemplateRecord[]
    return parsed.map((record) => hydrateRecord({
      ...record,
      fileBlob: undefined,
    }))
  } catch {
    return []
  }
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

function writeRecordsToLocalStorage(nextRecords: CartonMarkTemplateRecord[]) {
  if (typeof window === 'undefined') return

  const serializableRecords = nextRecords.map(({ pdfUrl, fileBlob, ...record }) => record)
  window.localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(serializableRecords))
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
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'id' })
      }

      if (!db.objectStoreNames.contains(PHOTO_STORE_NAME)) {
        db.createObjectStore(PHOTO_STORE_NAME, { keyPath: 'id' })
      }
    }

    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

async function readRecordsFromDb() {
  const db = await openTemplateDb()

  return new Promise<StoredCartonMarkTemplateRecord[]>((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, 'readonly')
    const request = transaction.objectStore(STORE_NAME).getAll()

    request.onsuccess = () => resolve(request.result as StoredCartonMarkTemplateRecord[])
    request.onerror = () => reject(request.error)
    transaction.oncomplete = () => db.close()
    transaction.onerror = () => {
      db.close()
      reject(transaction.error)
    }
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

async function saveRecordToDb(record: CartonMarkTemplateRecord, file: File) {
  const db = await openTemplateDb()
  const { pdfUrl, ...storedRecord } = record

  return new Promise<void>((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, 'readwrite')
    transaction.objectStore(STORE_NAME).put({
      ...storedRecord,
      fileBlob: file,
    })

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

async function deleteRecordFromDb(recordId: string) {
  const db = await openTemplateDb()

  return new Promise<void>((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, 'readwrite')
    transaction.objectStore(STORE_NAME).delete(recordId)

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
  <div class="space-y-6">
    <section v-if="!isWarehouseWorkspace" class="rounded-lg border border-slate-200 bg-white p-5">
      <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <p class="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Carton Mark</p>
          <h2 class="mt-2 text-xl font-semibold tracking-tight text-slate-950">{{ workspaceLabel }}</h2>
        </div>
        <div class="flex flex-wrap gap-2 text-xs font-semibold">
          <span class="rounded-full bg-slate-100 px-3 py-1 text-slate-700">{{ activeFactory.shortName }}</span>
          <span class="rounded-full bg-teal-50 px-3 py-1 text-teal-700">{{ currentUserName }}</span>
        </div>
      </div>
    </section>

    <div v-if="!isWarehouseWorkspace" class="grid gap-4 md:grid-cols-4">
      <section class="rounded-lg border border-slate-200 bg-white p-5">
        <p class="text-xs uppercase tracking-[0.2em] text-slate-500">Templates</p>
        <p class="mt-3 text-3xl font-semibold text-slate-950">{{ records.length }}</p>
        <p class="mt-1 text-sm text-slate-500">{{ activeFactory.shortName }} 已上传资料</p>
      </section>
      <section class="rounded-lg border border-slate-200 bg-white p-5">
        <p class="text-xs uppercase tracking-[0.2em] text-slate-500">Photos</p>
        <p class="mt-3 text-3xl font-semibold text-slate-950">{{ photoRecords.length }}</p>
        <p class="mt-1 text-sm text-slate-500">QA 实拍图片</p>
      </section>
      <section class="rounded-lg border border-slate-200 bg-white p-5">
        <p class="text-xs uppercase tracking-[0.2em] text-slate-500">Customers</p>
        <p class="mt-3 text-3xl font-semibold text-slate-950">{{ uniqueCustomerCount }}</p>
        <p class="mt-1 text-sm text-slate-500">当前厂区客名库</p>
      </section>
      <section class="rounded-lg border border-slate-200 bg-white p-5">
        <p class="text-xs uppercase tracking-[0.2em] text-slate-500">Latest</p>
        <p class="mt-3 truncate text-lg font-semibold text-slate-950">
          {{ latestRecord?.customerName ?? '暂无资料' }}
        </p>
        <p class="mt-1 truncate text-sm text-slate-500">
          {{ latestRecord ? `${latestRecord.po} / ${latestRecord.item}` : '等待上传' }}
        </p>
      </section>
    </div>

    <div class="grid gap-6 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
      <div class="space-y-6">
        <form
          v-if="isWarehouseWorkspace"
          class="rounded-lg border border-slate-200 bg-white p-6"
          @submit.prevent="submitTemplate"
        >
        <div class="flex items-start justify-between gap-4">
          <div>
            <p class="text-xs font-semibold uppercase tracking-[0.2em] text-teal-700">Step 1</p>
            <h2 class="mt-2 text-xl font-semibold tracking-tight text-slate-950">上传客人箱唛资料模板</h2>
          </div>
          <span class="rounded-full bg-teal-50 px-3 py-1 text-xs font-semibold text-teal-700">
            PDF 入库
          </span>
        </div>
        <p
          class="mt-4 rounded-lg border px-4 py-3 text-sm"
          :class="canUploadTemplate ? 'border-teal-100 bg-teal-50 text-teal-800' : 'border-slate-200 bg-slate-50 text-slate-500'"
        >
          {{ templatePermissionHint }}
        </p>

        <div class="mt-6 rounded-lg border border-slate-200 bg-slate-50 p-4">
          <div class="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
            <div>
              <p class="text-sm font-semibold text-slate-950">当前厂区客名库</p>
              <p class="mt-1 text-xs text-slate-500">{{ activeFactory.shortName }} 独立维护，不与其他厂区共用</p>
            </div>
            <div class="flex w-full gap-2 md:w-auto">
              <input
                v-model.trim="newCustomerName"
                type="text"
                class="h-10 min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition focus:border-teal-500 focus:ring-4 focus:ring-teal-50 md:w-48"
                placeholder="新增客名"
                :disabled="!canUploadTemplate"
                @keydown.enter.prevent="addCustomer"
              >
              <button
                type="button"
                :disabled="!canUploadTemplate"
                class="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-slate-300"
                @click="addCustomer"
              >
                <Plus class="size-4" aria-hidden="true" />
                新增
              </button>
            </div>
          </div>

          <p v-if="customerMessage" class="mt-3 text-xs text-slate-600">{{ customerMessage }}</p>

          <div v-if="factoryCustomers.length" class="mt-4 flex flex-wrap gap-2">
            <span
              v-for="customer in factoryCustomers"
              :key="customer.id"
              class="inline-flex max-w-full items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700"
            >
              <span class="truncate">{{ customer.name }}</span>
              <button
                type="button"
                :disabled="!canUploadTemplate"
                class="inline-flex size-6 shrink-0 items-center justify-center rounded-md text-slate-400 transition hover:bg-red-50 hover:text-red-600 disabled:cursor-not-allowed disabled:hover:bg-transparent disabled:hover:text-slate-400"
                :title="`从${activeFactory.shortName}客名库移除`"
                @click="removeCustomer(customer)"
              >
                <Trash2 class="size-3.5" aria-hidden="true" />
              </button>
            </span>
          </div>
          <p v-else class="mt-4 rounded-lg border border-dashed border-slate-200 bg-white px-4 py-4 text-sm text-slate-500">
            当前厂区还没有客名，请先新增后再上传箱唛资料。
          </p>
        </div>

        <div class="mt-6 grid gap-4 md:grid-cols-3 xl:grid-cols-1 2xl:grid-cols-3">
          <label class="block">
            <span class="text-sm font-medium text-slate-700">客名</span>
            <select
              v-model="form.customerName"
              class="mt-2 h-11 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition focus:border-teal-500 focus:ring-4 focus:ring-teal-50"
              :disabled="!factoryCustomers.length || !canUploadTemplate"
            >
              <option value="">请选择客名</option>
              <option
                v-for="customer in factoryCustomers"
                :key="`select-${customer.id}`"
                :value="customer.name"
              >
                {{ customer.name }}
              </option>
            </select>
          </label>
          <label class="block">
            <span class="text-sm font-medium text-slate-700">PO</span>
            <input
              v-model.trim="form.po"
              type="text"
              class="mt-2 h-11 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition focus:border-teal-500 focus:ring-4 focus:ring-teal-50"
              placeholder="采购订单号"
              :disabled="!canUploadTemplate"
            >
          </label>
          <label class="block">
            <span class="text-sm font-medium text-slate-700">ITEM</span>
            <input
              v-model.trim="form.item"
              type="text"
              class="mt-2 h-11 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition focus:border-teal-500 focus:ring-4 focus:ring-teal-50"
              placeholder="产品 / Item"
              :disabled="!canUploadTemplate"
            >
          </label>
        </div>

        <div class="mt-5 rounded-lg border border-dashed border-slate-300 bg-slate-50 p-5">
          <input
            ref="fileInput"
            type="file"
            accept=".pdf,application/pdf"
            class="hidden"
            :disabled="!canUploadTemplate"
            @change="handleFileChange"
          >
          <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div class="flex min-w-0 items-center gap-3">
              <div class="flex size-11 shrink-0 items-center justify-center rounded-lg bg-white text-teal-700">
                <FileText class="size-5" aria-hidden="true" />
              </div>
              <div class="min-w-0">
                <p class="truncate text-sm font-semibold text-slate-900">{{ selectedFileLabel }}</p>
                <p class="mt-1 text-xs text-slate-500">客人箱唛资料 PDF</p>
              </div>
            </div>
            <button
              type="button"
              :disabled="!canUploadTemplate"
              class="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-teal-200 hover:text-teal-700 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400 disabled:hover:border-slate-200"
              @click="openFilePicker"
            >
              选择PDF
            </button>
          </div>
        </div>

        <p v-if="errorMessage" class="mt-4 rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
          {{ errorMessage }}
        </p>
        <p v-if="successMessage" class="mt-4 rounded-lg border border-green-100 bg-green-50 px-4 py-3 text-sm text-green-700">
          {{ successMessage }}
        </p>

        <button
          type="submit"
          :disabled="!canSubmit || isSaving"
          class="mt-5 inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-slate-950 px-5 text-sm font-semibold text-white transition hover:bg-teal-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          <UploadCloud class="size-4" aria-hidden="true" />
          {{ isSaving ? '入库中' : '导入PDF并入库' }}
        </button>

        <p class="mt-4 text-xs leading-5 text-slate-500">
          {{ storageMode === 'indexedDb' ? 'PDF 文件和资料索引会保存在当前浏览器资料库。' : '当前浏览器只保留资料索引；PDF 原件请以正式后端库为准。' }}
        </p>
        </form>

        <form
          v-if="!isWarehouseWorkspace"
          class="rounded-lg border border-slate-200 bg-white p-6"
          @submit.prevent="submitPhoto"
        >
          <div class="flex items-start justify-between gap-4">
            <div>
              <p class="text-xs font-semibold uppercase tracking-[0.2em] text-blue-700">QA 核验</p>
              <h2 class="mt-2 text-xl font-semibold tracking-tight text-slate-950">上传实际收到箱唛图片</h2>
            </div>
          <span class="rounded-full bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700">
            QA 实拍
          </span>
        </div>
        <p
          class="mt-4 rounded-lg border px-4 py-3 text-sm"
          :class="canUploadPhoto ? 'border-blue-100 bg-blue-50 text-blue-800' : 'border-slate-200 bg-slate-50 text-slate-500'"
        >
          {{ photoPermissionHint }}
        </p>

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
                    {{ record.customerName }} / {{ record.po }} / {{ record.item }} / V{{ record.version }}
                  </option>
                </select>
              </label>
            </div>

            <div
              v-if="selectedTemplateForPhoto"
              class="rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-800"
            >
              {{ selectedTemplateForPhoto.customerName }} · PO：{{ selectedTemplateForPhoto.po }} · ITEM：{{ selectedTemplateForPhoto.item }}
            </div>

            <div v-else-if="records.length && !filteredTemplateOptions.length" class="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-500">
              当前客名没有可选择的箱唛模板，请切换客名或先上传模板。
            </div>

            <div v-else class="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-500">
              当前厂区还没有可选择的箱唛模板，请联系纸箱部仓管先上传 PDF 模板。
            </div>
          </div>

          <div class="mt-5 grid gap-4 md:grid-cols-2">
            <div class="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-5">
              <input
                ref="frontPhotoFileInput"
                type="file"
                accept="image/*"
                class="hidden"
                :disabled="!canUploadPhoto"
                @change="handlePhotoFileChange($event, 'front')"
              >
              <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div class="flex min-w-0 items-center gap-3">
                  <div class="flex size-11 shrink-0 items-center justify-center rounded-lg bg-white text-blue-700">
                    <ImageIcon class="size-5" aria-hidden="true" />
                  </div>
                  <div class="min-w-0">
                    <p class="truncate text-sm font-semibold text-slate-900">{{ selectedFrontPhotoFileLabel }}</p>
                    <p class="mt-1 text-xs text-slate-500">正唛图片</p>
                  </div>
                </div>
                <div class="flex shrink-0 flex-wrap items-center gap-2">
                  <button
                    v-if="selectedFrontPhotoFile"
                    type="button"
                    class="inline-flex h-10 items-center justify-center gap-1.5 rounded-lg border border-red-100 bg-white px-3 text-sm font-semibold text-red-600 transition hover:border-red-200 hover:bg-red-50"
                    @click="clearPhotoSelection('front')"
                  >
                    <Trash2 class="size-4" aria-hidden="true" />
                    删除
                  </button>
                  <button
                    type="button"
                    :disabled="!canUploadPhoto"
                    class="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-blue-200 hover:text-blue-700 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400 disabled:hover:border-slate-200"
                    @click="openPhotoFilePicker('front')"
                  >
                    {{ selectedFrontPhotoFile ? '重选正唛' : '选择正唛' }}
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
                  <span
                    v-if="photoCropState.front.applied"
                    class="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700"
                  >
                    已裁剪
                  </span>
                  <span v-else class="text-xs font-medium text-slate-500">正唛 OCR 图片</span>
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
                ref="sidePhotoFileInput"
                type="file"
                accept="image/*"
                class="hidden"
                :disabled="!canUploadPhoto"
                @change="handlePhotoFileChange($event, 'side')"
              >
              <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div class="flex min-w-0 items-center gap-3">
                  <div class="flex size-11 shrink-0 items-center justify-center rounded-lg bg-white text-blue-700">
                    <ImageIcon class="size-5" aria-hidden="true" />
                  </div>
                  <div class="min-w-0">
                    <p class="truncate text-sm font-semibold text-slate-900">{{ selectedSidePhotoFileLabel }}</p>
                    <p class="mt-1 text-xs text-slate-500">侧唛图片</p>
                  </div>
                </div>
                <div class="flex shrink-0 flex-wrap items-center gap-2">
                  <button
                    v-if="selectedSidePhotoFile"
                    type="button"
                    class="inline-flex h-10 items-center justify-center gap-1.5 rounded-lg border border-red-100 bg-white px-3 text-sm font-semibold text-red-600 transition hover:border-red-200 hover:bg-red-50"
                    @click="clearPhotoSelection('side')"
                  >
                    <Trash2 class="size-4" aria-hidden="true" />
                    删除
                  </button>
                  <button
                    type="button"
                    :disabled="!canUploadPhoto"
                    class="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-blue-200 hover:text-blue-700 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400 disabled:hover:border-slate-200"
                    @click="openPhotoFilePicker('side')"
                  >
                    {{ selectedSidePhotoFile ? '重选侧唛' : '选择侧唛' }}
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
                  <span
                    v-if="photoCropState.side.applied"
                    class="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700"
                  >
                    已裁剪
                  </span>
                  <span v-else class="text-xs font-medium text-slate-500">侧唛 OCR 图片</span>
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

          <p v-if="photoErrorMessage" class="mt-4 rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
            {{ photoErrorMessage }}
          </p>
          <p v-if="photoSuccessMessage" class="mt-4 rounded-lg border border-green-100 bg-green-50 px-4 py-3 text-sm text-green-700">
            {{ photoSuccessMessage }}
          </p>
          <p v-if="autoCheckErrorMessage" class="mt-4 rounded-lg border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-700">
            {{ autoCheckErrorMessage }}
          </p>

          <button
            type="submit"
            :disabled="!canSubmitPhoto || isSavingPhoto"
            class="mt-5 inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-slate-950 px-5 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            <UploadCloud class="size-4" aria-hidden="true" />
            {{ photoSubmitLabel }}
          </button>

          <div v-if="photoRecords.length" class="mt-6 space-y-3">
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
                <p class="mt-1 text-xs text-slate-600">PO：{{ photo.po }} · ITEM：{{ photo.item }}</p>
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
                  {{ comparisonRecord.customerName }} · PO：{{ comparisonRecord.po }} · ITEM：{{ comparisonRecord.item }}
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
                <a
                  v-if="comparisonTemplate?.pdfUrl"
                  :href="comparisonTemplate.pdfUrl"
                  target="_blank"
                  rel="noreferrer"
                  class="inline-flex h-9 w-fit items-center justify-center gap-1.5 rounded-lg border border-blue-200 bg-white px-3 text-xs font-semibold text-blue-700 transition hover:bg-blue-50"
                >
                  <FileText class="size-3.5" aria-hidden="true" />
                  打开 PDF 模板
                </a>
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
                v-if="autoCheckExtractionMessages.length"
                class="rounded-lg border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-800"
              >
                <p class="font-semibold">识别提示</p>
                <ul class="mt-2 space-y-1">
                  <li
                    v-for="status in autoCheckExtractionMessages"
                    :key="`${status.source}-${status.engine}`"
                  >
                    {{ status.source }} · {{ status.engine }}：{{ status.message || '识别结果需要复核' }}
                  </li>
                </ul>
              </div>

              <section class="rounded-lg border border-slate-200">
                <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3">
                  <h4 class="text-sm font-semibold text-slate-950">正唛字段核对</h4>
                  <span class="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700">PDF 长框 vs QA 正唛</span>
                </div>
                <div
                  v-if="frontAutoCheckComparisons.length"
                  class="overflow-x-auto"
                >
                  <table class="min-w-full divide-y divide-slate-200 text-sm">
                    <thead class="bg-slate-50 text-left text-xs font-semibold text-slate-500">
                      <tr>
                        <th class="px-4 py-3">字段</th>
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
                  <span class="rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-semibold text-indigo-700">PDF 短框 vs QA 侧唛</span>
                </div>
                <div
                  v-if="sideAutoCheckComparisons.length"
                  class="overflow-x-auto"
                >
                  <table class="min-w-full divide-y divide-slate-200 text-sm">
                    <thead class="bg-slate-50 text-left text-xs font-semibold text-slate-500">
                      <tr>
                        <th class="px-4 py-3">字段</th>
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
                      <figcaption class="mb-2 text-xs font-semibold text-slate-700">QA 实拍正唛</figcaption>
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
                      <figcaption class="mb-2 text-xs font-semibold text-slate-700">QA 实拍侧唛</figcaption>
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
        </form>
      </div>

      <section class="rounded-lg border border-slate-200 bg-white p-6">
        <div class="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <h2 class="text-xl font-semibold tracking-tight text-slate-950">已上传箱唛资料库</h2>
            <p class="mt-1 text-sm text-slate-500">按客户归档 PO、ITEM 和 PDF 模板</p>
          </div>
          <input
            v-model.trim="searchKeyword"
            type="search"
            class="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm text-slate-900 outline-none transition focus:border-teal-500 focus:ring-4 focus:ring-teal-50 md:w-56"
            placeholder="搜索客名 / PO / ITEM"
          >
        </div>

        <div class="mt-5 flex gap-2 overflow-x-auto pb-1">
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

        <div v-if="isLoading" class="mt-5 rounded-lg border border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
          正在读取资料库
        </div>

        <div v-else-if="filteredRecords.length" class="mt-5 space-y-3">
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
                  PO：{{ record.po }} · ITEM：{{ record.item }}
                </p>
                <p class="mt-2 truncate text-sm text-slate-500">
                  {{ record.fileName }} · {{ formatFileSize(record.fileSize) }}
                </p>
              </div>

              <div class="flex shrink-0 flex-wrap items-center gap-2 text-sm">
                <span class="rounded-full bg-green-50 px-3 py-1 font-semibold text-green-700">已入库</span>
                <a
                  v-if="record.pdfUrl"
                  :href="record.pdfUrl"
                  target="_blank"
                  rel="noreferrer"
                  class="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-2 font-semibold text-slate-700 transition hover:border-teal-200 hover:text-teal-700"
                >
                  <FileText class="size-4" aria-hidden="true" />
                  查看PDF
                </a>
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
            <div class="mt-4 grid gap-3 border-t border-slate-200 pt-4 text-xs text-slate-500 sm:grid-cols-3">
              <span>客名：{{ record.customerName }}</span>
              <span>PO：{{ record.po }}</span>
              <span>上传：{{ formatDate(record.uploadedAt) }}</span>
            </div>
          </article>
        </div>

        <div v-else class="mt-5 rounded-lg border border-slate-200 bg-slate-50 px-4 py-10 text-center">
          <p class="text-sm font-semibold text-slate-700">暂无箱唛资料</p>
          <p class="mt-2 text-sm text-slate-500">上传后会按客名进入对应资料库。</p>
        </div>
      </section>
    </div>
  </div>
</template>
