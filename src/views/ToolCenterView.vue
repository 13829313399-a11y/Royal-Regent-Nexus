<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import PdfBatchRenameWorkspace from '@/features/pdf-rename/PdfBatchRenameWorkspace.vue'
import CollaborativeSheetsWorkspace from '@/features/collaborative-sheets/CollaborativeSheetsWorkspace.vue'
import {
  ArrowRight,
  FileText,
  Files,
  FolderOpen,
  Maximize2,
  PanelRight,
  Upload,
  X,
  Scissors,
  AlertCircle,
  Languages,
} from '@lucide/vue'
import PageHeader from '@/components/common/PageHeader.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { Button } from '@/components/ui/button'
import {
  documentTools,
  isActiveJob,
  operationLabels,
  statusLabels,
  type Anchor,
  type Artifact,
  type Capabilities,
  type Issue,
  type Job,
  type Operation,
  type Source,
} from '@/api/documentTools'
import { getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'
import PdfCanvas from '@/features/document-tools/PdfCanvas.vue'
import ToolOptions from '@/features/document-tools/ToolOptions.vue'
import TranslationOptions from '@/features/document-tools/TranslationOptions.vue'
import ResultReview from '@/features/document-tools/ResultReview.vue'
import TaskActions from '@/features/document-tools/TaskActions.vue'
import {
  normalizeCuts,
  parseGroups,
} from '@/features/document-tools/coordinates'
import '@/features/document-tools/workbench.css'

const appStore = useAppStore()
const route = useRoute()
const router = useRouter()
const imageTranslationUrl = computed(() => `/image-translation/?${new URLSearchParams({ factory: appStore.activeFactoryId })}`)
watch(() => route.query.tool, (tool) => {
  if (tool === 'image-translation') window.location.replace(imageTranslationUrl.value)
}, { immediate: true })
// Do not use activeProductionFactory: its group fallback is Huaxing.
const isHuaxing = computed(() => appStore.activeFactoryId === 'huaxing'
  && (!route.query.factory || route.query.factory === 'huaxing'))
const renameActive = computed(() => isHuaxing.value && route.query.tool === 'pdf-batch-rename')
const sheetsActive = computed(() => route.query.tool === 'collaborative-sheets')
function selectSheets() {
  const query = { ...route.query }
  if (sheetsActive.value) delete query.tool
  else query.tool = 'collaborative-sheets'
  focused.value = false
  void router.replace({ query })
}
function selectRename(active: boolean) {
  const query = { ...route.query }
  if (active && isHuaxing.value) query.tool = 'pdf-batch-rename'
  else delete query.tool
  focused.value = false
  void router.replace({ query })
}
watch(isHuaxing, (allowed) => {
  if (!allowed && route.query.tool === 'pdf-batch-rename') {
    const query = { ...route.query }
    delete query.tool
    void router.replace({ query })
  }
}, { immediate: true, flush: 'sync' })

interface UploadItem {
  id: string
  name: string
  size: number
  progress: number
  state: string
  error?: string
  sourceId?: string
  jobId?: string
  file?: File
}
const root = ref<HTMLElement>(),
  workspace = ref<HTMLElement>(),
  picker = ref<HTMLInputElement>(),
  tasksDialog = ref<HTMLDialogElement>(),
  deleteDialog = ref<HTMLDialogElement>(),
  settingsDialog = ref<HTMLDialogElement>()
const deletingJob = ref<Job>(),
  deleteError = ref('')
let taskMutationSequence = 0,
  jobListSequence = 0
const capabilities = ref<Capabilities>(),
  uploads = ref<UploadItem[]>([]),
  jobs = ref<Job[]>([]),
  jobTotal = ref(0),
  taskPage = ref(1),
  currentSource = ref<Source>(),
  currentJob = ref<Job>(),
  selectedUpload = ref('')
const operation = ref<Operation>('pdf_to_excel'),
  options = ref<Record<string, unknown>>({}),
  error = ref(''),
  notice = ref(''),
  busy = ref(false),
  initializing = ref(false),
  submitting = ref(false),
  refreshing = ref(false),
  dragging = ref(false),
  focused = ref(false),
  width = ref(1400),
  workspaceWidth = ref(0)
const view = ref<'source' | 'compare' | 'result'>('source'),
  resultLayout = ref(false),
  pageIndex = ref(0),
  resultPage = ref(0),
  anchor = ref<Anchor>(),
  selectedTarget = ref(''),
  regionMode = ref(false),
  selectedRegion = ref<number[]>(),
  issues = ref<Issue[]>([]),
  issuesTotal = ref(0),
  issuePage = ref(1),
  password = ref('')
const cuts = ref<number[]>([]),
  axis = ref<'x' | 'y'>('y'),
  dimensions = ref({ width: 0, height: 0 }),
  suggestions = ref<number[]>([]),
  protectedRegions = ref<Array<{ kind: string; bbox_pt: number[] }>>([]),
  cutHistory = ref<number[][]>([[]]),
  cutPosition = ref(0),
  checkedArtifacts = ref<string[]>([])
let poll: ReturnType<typeof setTimeout> | undefined,
  observer: ResizeObserver | undefined,
  disposed = false,
  selectionSequence = 0,
  lastCapabilitiesAt = 0
const batchId = createRandomUuid()
const toolIds: Operation[] = (Object.keys(operationLabels) as Operation[]).filter(id => id !== 'image_translate')
const engineLabels: Record<string, string> = {
  office: 'Office 渲染',
  pdf: 'PDF 解析',
  local_ocr: '本地识别',
  qwen: '千问增强',
}
const narrow = computed(() => width.value < 1100),
  phone = computed(() => width.value < 700)
// Two document panes need their own usable width, after both rails and the app shell.
const canCompare = computed(() => workspaceWidth.value >= 1000)
const extent = computed(() =>
  axis.value === 'x' ? dimensions.value.width : dimensions.value.height,
)
const capability = computed(() =>
  capabilities.value?.operations.find((item) => item.id === operation.value),
)
const translating = computed(() => operation.value.endsWith('_translate'))
const translationUnavailable = computed(() => translating.value && !(options.value.translation_engine === 'online'
  ? capabilities.value?.translation?.online_available : capabilities.value?.translation?.offline_available))
const snapPoints = computed(() => [
  ...suggestions.value,
  ...protectedRegions.value.flatMap((region) =>
    axis.value === 'y'
      ? [region.bbox_pt[1]!, region.bbox_pt[3]!]
      : [region.bbox_pt[0]!, region.bbox_pt[2]!],
  ),
])
const pdfOutput = computed(
  () =>
    !!currentJob.value &&
    ['word_to_pdf', 'excel_to_pdf', 'pdf_split', 'pdf_translate'].includes(
      currentJob.value.operation,
    ),
)
const sourceReady = computed(
  () =>
    currentSource.value &&
    ['succeeded', 'ready', 'complete', 'completed'].includes(
      currentSource.value.inspection_status,
    ),
)
const compatible = computed(() => {
  const type = currentSource.value?.detected_type?.toLowerCase() ?? ''
  if (!type) return true
  if (!translating.value && currentSource.value?.manifest.supported_operations?.length)
    return currentSource.value.manifest.supported_operations.includes(
      operation.value,
    )
  return operation.value.startsWith('word_')
    ? ['doc', 'docx', 'word'].includes(type)
    : operation.value.startsWith('excel_')
      ? ['xls', 'xlsx', 'excel'].includes(type)
      : type === 'pdf'
})
const sourcePreview = computed(
  () =>
    currentSource.value?.artifacts.find(
      (item) => item.role === 'preview' && item.format === 'pdf',
    ) ??
    currentSource.value?.artifacts.find(
      (item) => item.role === 'source' && item.format === 'pdf',
    ),
)
const resultPreview = computed(
  () =>
    currentJob.value?.artifacts.find(
      (item) => item.role === 'preview' && item.format === 'pdf',
    ) ??
    currentJob.value?.artifacts.find(
      (item) => item.role === 'result' && item.format === 'pdf',
    ),
)
const results = computed(
  () =>
    currentJob.value?.artifacts.filter((item) =>
      ['result', 'package'].includes(item.role),
    ) ?? [],
)
const hasResult = computed(
  () =>
    currentJob.value?.execution_status === 'succeeded' &&
    currentJob.value.operation !== 'inspect',
)
const canRecognizeRegion = computed(
  () =>
    currentSource.value?.detected_type === 'pdf' &&
    !currentJob.value?.operation.endsWith('_translate') &&
    hasResult.value &&
    !!sourcePreview.value,
)
const cropMode = computed(
  () => operation.value === 'pdf_split' && options.value.split_mode === 'crop',
)
const progressText = computed(() => {
  const job = currentJob.value
  if (!job) return '上传文件后自动读取页面与工作表'
  return `${statusLabels[job.stage] ?? job.stage ?? '准备处理'}${job.total_units ? ` · ${job.completed_units} / ${job.total_units}` : ''}`
})
const sheetDefaults = () =>
  (currentSource.value?.manifest.sheets ?? [])
    .filter((item) => typeof item === 'string' || !item.hidden)
    .map((item) => (typeof item === 'string' ? item : item.name))
function defaults() {
  if (translating.value) {
    options.value = { translation_direction: 'zh_to_en',
      translation_engine: capabilities.value?.translation?.offline_available ? 'offline'
        : capabilities.value?.translation?.online_available ? 'online' : 'offline',
      ...(operation.value === 'pdf_translate' ? { page_selection: 'all' } : {}),
      ...(operation.value === 'excel_translate' ? { sheets: sheetDefaults() } : {}) }
    return
  }
  options.value = {
    page_selection: 'all',
    ...(operation.value !== 'pdf_split' ? { ai_mode: 'auto' } : {}),
    ...(operation.value === 'pdf_to_word' ? { layout_mode: 'editable' } : {}),
    ...(operation.value === 'word_to_excel'
      ? {
          word_mode: 'tables',
          include_notes_sheet: true,
          include_headers_footers: false,
          merge_continuation_tables: false,
        }
      : {}),
    ...(operation.value === 'pdf_to_excel'
      ? {
          preserve_merges: true,
          include_notes_sheet: true,
          merge_continuation_tables: false,
          numeric_locale: 'preserve_ambiguous',
        }
      : {}),
    ...(operation.value.startsWith('excel_')
      ? {
          sheets: sheetDefaults(),
          include_hidden: false,
          formula_mode: 'display',
          paper: 'original',
          orientation: 'auto',
          ...(operation.value === 'excel_to_pdf'
            ? { print_mode: 'original' }
            : {}),
        }
      : {}),
    ...(operation.value === 'pdf_split'
      ? {
          split_mode: 'groups',
          groups: '',
          every_n: 1,
          duplicate_policy: 'keep',
          axis: axis.value,
        }
      : {}),
  }
}
watch(operation, defaults, { immediate: true })
watch(canCompare, (value) => {
  if (!value && view.value === 'compare')
    view.value = hasResult.value ? 'result' : 'source'
})
function stateLabel(state: string) {
  return (
    (
      {
        uploading: '上传中',
        inspecting: '正在读取',
        ready: '设置就绪',
      } as Record<string, string>
    )[state] ??
    statusLabels[state] ??
    state
  )
}
function tone(state: string): 'red' | 'green' | 'amber' | 'teal' | 'slate' {
  return state === 'failed'
    ? 'red'
    : ['succeeded', 'ready', 'passed', 'manually_confirmed'].includes(state)
      ? 'green'
      : ['needs_review', 'awaiting_input'].includes(state)
        ? 'amber'
        : ['running', 'uploading', 'inspecting'].includes(state)
          ? 'teal'
          : 'slate'
}
function resetSourceState() {
  resultLayout.value = false
  anchor.value = undefined
  selectedTarget.value = ''
  selectedRegion.value = undefined
  pageIndex.value = 0
  cuts.value = []
  cutHistory.value = [[]]
  cutPosition.value = 0
  suggestions.value = []
  protectedRegions.value = []
  issues.value = []
  issuesTotal.value = 0
  issuePage.value = 1
  password.value = ''
}
async function selectSource(sourceId: string, jobId?: string) {
  const ticket = ++selectionSequence
  error.value = ''
  try {
    const [source, job] = await Promise.all([
      documentTools.source(sourceId),
      jobId ? documentTools.job(jobId) : Promise.resolve(undefined),
    ])
    if (ticket !== selectionSequence) return
    resetSourceState()
    currentSource.value = source
    currentJob.value = job
    selectedUpload.value =
      uploads.value.find((item) => item.sourceId === sourceId)?.id ?? ''
    if (job && toolIds.includes(job.operation as Operation)) {
      operation.value = job.operation as Operation
      await nextTick()
      options.value = { ...job.options }
    } else if (operation.value === 'excel_translate') options.value.sheets = sheetDefaults()
    else if (operation.value.startsWith('excel_')) defaults()
    if (job?.execution_status === 'succeeded' && job.operation !== 'inspect') {
      view.value = canCompare.value ? 'compare' : 'result'
      await loadIssues()
    } else view.value = 'source'
    schedule()
  } catch (problem) {
    error.value = getApiErrorMessage(problem)
  }
}
async function selectJob(job: Job) {
  if (job.operation === 'image_translate') {
    window.location.assign(`${imageTranslationUrl.value}&job=${encodeURIComponent(job.id)}`)
    return
  }
  tasksDialog.value?.close()
  if (job.source_id) await selectSource(job.source_id, job.id)
  else {
    currentJob.value = job
    currentSource.value = undefined
  }
}
async function uploadOne(item: UploadItem) {
  if (!item.file) return
  item.state = 'uploading'
  item.error = undefined
  try {
    const response = await documentTools.upload(item.file, (value) => {
      item.progress = value
    })
    item.sourceId = response.source_id
    item.jobId = response.inspection_job_id
    item.state = 'inspecting'
    item.file = undefined
    if (!currentSource.value || selectedUpload.value === item.id)
      await selectSource(response.source_id, response.inspection_job_id)
    schedule()
  } catch (problem) {
    item.state = 'failed'
    item.error = getApiErrorMessage(problem)
  }
}
async function acceptFiles(files: File[]) {
  if (!files.length) return
  notice.value = ''
  for (const file of files) {
    const item: UploadItem = {
      id: createRandomUuid(),
      name: file.name,
      size: file.size,
      progress: 0,
      state: 'uploading',
      file,
    }
    uploads.value.push(item)
    const stored = uploads.value[uploads.value.length - 1]!
    if (!/\.(docx?|xlsx?|pdf)$/i.test(file.name)) {
      stored.state = 'failed'
      stored.error = '请选择 DOC、DOCX、XLS、XLSX 或 PDF 文件'
      continue
    }
    if (
      capabilities.value &&
      file.size > capabilities.value.limits.max_file_bytes
    ) {
      stored.state = 'failed'
      stored.error = `文件超过 ${Math.round(capabilities.value.limits.max_file_bytes / 1024 / 1024)} MB 限制`
      continue
    }
    if (!currentSource.value) selectedUpload.value = stored.id
    await uploadOne(stored)
  }
  try {
    await loadJobs()
    schedule()
  } catch (problem) {
    error.value = getApiErrorMessage(problem)
  }
}
function picked(event: Event) {
  const input = event.target as HTMLInputElement
  void acceptFiles(Array.from(input.files ?? []))
  input.value = ''
}
function drop(event: DragEvent) {
  dragging.value = false
  void acceptFiles(Array.from(event.dataTransfer?.files ?? []))
}
async function loadJobs() {
  const ticket = ++jobListSequence
  const response = await documentTools.jobs(taskPage.value)
  if (ticket !== jobListSequence || disposed) return
  const lastPage = Math.max(1, Math.ceil(response.total / 20))
  if (taskPage.value > lastPage) {
    taskPage.value = lastPage
    return loadJobs()
  }
  jobs.value = response.items
  jobTotal.value = response.total
}
async function refreshCapabilities() {
  const response = await documentTools.capabilities()
  if (!disposed) {
    capabilities.value = response
    lastCapabilitiesAt = Date.now()
  }
}
async function refresh(forceCapabilities = false) {
  if (refreshing.value || disposed || busy.value) return
  const ticket = taskMutationSequence
  refreshing.value = true
  try {
    await Promise.all([
      loadJobs(),
      forceCapabilities || Date.now() - lastCapabilitiesAt >= 15000
        ? refreshCapabilities()
        : Promise.resolve(),
    ])
    const activeUploads = uploads.value.filter(
      (item) => item.state === 'inspecting' && item.sourceId,
    )
    for (const item of activeUploads) {
      const job = await documentTools.job(item.jobId!)
      if (ticket !== taskMutationSequence) return
      item.state =
        job.execution_status === 'succeeded'
          ? 'ready'
          : isActiveJob(job)
            ? 'inspecting'
            : job.execution_status
      item.error = job.error_message
      if (currentSource.value?.id === item.sourceId) {
        const source = await documentTools.source(item.sourceId!)
        if (ticket !== taskMutationSequence) return
        if (currentSource.value?.id === source.id) currentSource.value = source
      }
    }
    if (currentJob.value && isActiveJob(currentJob.value)) {
      const previous = currentJob.value
      const updated = await documentTools.job(previous.id)
      if (ticket !== taskMutationSequence) return
      if (currentJob.value?.id === previous.id) {
        currentJob.value = updated
        if (updated.execution_status === 'succeeded') {
          if (currentSource.value) {
            const source = await documentTools.source(currentSource.value.id)
            if (ticket !== taskMutationSequence) return
            if (currentSource.value?.id === source.id)
              currentSource.value = source
          }
          if (updated.operation !== 'inspect') {
            view.value = canCompare.value ? 'compare' : 'result'
            await loadIssues()
          } else if (operation.value === 'excel_translate') options.value.sheets = sheetDefaults()
          else if (operation.value.startsWith('excel_')) defaults()
        }
      }
    }
  } catch (problem) {
    if (ticket === taskMutationSequence)
      error.value = getApiErrorMessage(problem)
  } finally {
    refreshing.value = false
    schedule()
  }
}
function schedule() {
  clearTimeout(poll)
  if (disposed) return
  const active =
    jobs.value.some(isActiveJob) ||
    (currentJob.value && isActiveJob(currentJob.value)) ||
    uploads.value.some((item) => item.state === 'inspecting')
  if (active)
    poll = setTimeout(() => void refresh(), document.hidden ? 15000 : 1800)
  else if (capabilities.value && !capabilities.value.worker.online)
    poll = setTimeout(
      async () => {
        try {
          await refreshCapabilities()
        } catch (problem) {
          error.value = getApiErrorMessage(problem)
        } finally {
          schedule()
        }
      },
      document.hidden ? 30000 : 15000,
    )
}
function visibility() {
  if (!document.hidden) void refresh(true)
  else schedule()
}
async function start() {
  if (!currentSource.value || busy.value) return
  if (translationUnavailable.value) {
    error.value = '所选翻译服务尚未就绪，请更换翻译方式或联系管理员配置。'
    return
  }
  busy.value = true
  submitting.value = true
  error.value = ''
  try {
    const payload = Object.fromEntries(
      Object.entries(options.value).filter(
        ([, value]) => value !== '' && value !== undefined,
      ),
    )
    if (operation.value === 'pdf_split') {
      if (['groups', 'extract'].includes(String(payload.split_mode))) {
        const groups = parseGroups(
          String(payload.groups ?? ''),
          currentSource.value.manifest.pages?.length ?? 0,
        )
        if (!groups.length) throw new Error('请填写输出分组')
      }
      if (payload.split_mode === 'crop')
        Object.assign(payload, {
          cuts_pt: cuts.value,
          axis: axis.value,
          page_index: pageIndex.value,
        })
    }
    const response = await documentTools.create(
      currentSource.value.id,
      operation.value,
      payload,
      batchId,
    )
    currentJob.value = await documentTools.job(response.job_id)
    notice.value = '任务已在后台开始，可以继续处理其他文件。'
    await loadJobs()
    schedule()
  } catch (problem) {
    error.value = getApiErrorMessage(problem)
  } finally {
    busy.value = false
    submitting.value = false
  }
}
async function runAction(action: () => Promise<unknown>) {
  error.value = ''
  busy.value = true
  try {
    await action()
    await loadJobs()
    schedule()
  } catch (problem) {
    error.value = getApiErrorMessage(problem)
  } finally {
    busy.value = false
  }
}
async function withdrawJob(job: Job) {
  if (busy.value) return
  taskMutationSequence++
  jobListSequence++
  await runAction(async () => {
    const updated = await documentTools.cancel(job.id)
    if (currentJob.value?.id === job.id) currentJob.value = updated
    const item = uploads.value.find((entry) => entry.jobId === job.id)
    if (item) item.state = updated.execution_status
    if (
      job.operation === 'inspect' &&
      currentSource.value?.id === job.source_id
    )
      currentSource.value = await documentTools.source(job.source_id!)
    notice.value =
      updated.execution_status === 'cancelled'
        ? '任务已撤回，原文件保留。需要时可重试；已开始的处理可能稍后停止。'
        : '任务已结束，无需撤回。'
  })
}
function requestDelete(job: Job) {
  deletingJob.value = job
  deleteError.value = ''
  openDialog(deleteDialog.value)
}
async function confirmDelete() {
  const job = deletingJob.value
  if (!job || busy.value) return
  busy.value = true
  deleteError.value = ''
  taskMutationSequence++
  jobListSequence++
  try {
    await documentTools.delete(job.id)
    selectionSequence++
    checkedArtifacts.value = checkedArtifacts.value.filter(
      (id) => !job.artifacts.some((artifact) => artifact.id === id),
    )
    uploads.value = uploads.value.filter((item) => item.jobId !== job.id)
    if (currentJob.value?.id === job.id) {
      resetSourceState()
      currentJob.value = undefined
      currentSource.value = undefined
      selectedUpload.value = ''
    }
    jobs.value = jobs.value.filter((item) => item.id !== job.id)
    deleteDialog.value?.close()
    deletingJob.value = undefined
    notice.value = '任务已从列表删除，原文件和其他任务保留。'
    await loadJobs()
  } catch (problem) {
    if (deletingJob.value) deleteError.value = getApiErrorMessage(problem)
    else error.value = getApiErrorMessage(problem)
  } finally {
    busy.value = false
    schedule()
  }
}
async function followJob(jobId: string) {
  const job = await documentTools.job(jobId)
  if (job.source_id && job.source_id !== currentSource.value?.id) {
    await selectSource(job.source_id, job.id)
  } else {
    currentJob.value = job
    if (!job.source_id) currentSource.value = undefined
  }
  if (job.operation === 'inspect') {
    const item = uploads.value.find((entry) => entry.sourceId === job.source_id)
    if (item) {
      item.jobId = job.id
      item.state = isActiveJob(job) ? 'inspecting' : job.execution_status
    }
  }
  await loadJobs()
  schedule()
}
function toggleRegion() {
  if (!canRecognizeRegion.value) return
  regionMode.value = !regionMode.value
  view.value = 'source'
}
function generateFromDialog() {
  void start()
  settingsDialog.value?.close()
}
function locateIssue(issue: Issue) {
  locate(issue.source, issue.target_id ?? '')
  tasksDialog.value?.close()
}
async function paginateIssues(delta: number) {
  issuePage.value += delta
  try {
    await loadIssues()
  } catch (problem) {
    error.value = getApiErrorMessage(problem)
  }
}
async function paginateTasks(delta: number) {
  taskPage.value += delta
  try {
    await loadJobs()
  } catch (problem) {
    error.value = getApiErrorMessage(problem)
  }
}
async function unlock() {
  if (!currentSource.value || !password.value) return
  const value = password.value
  password.value = ''
  await runAction(async () => {
    const response = await documentTools.password(
      currentSource.value!.id,
      value,
    )
    await followJob(response.job_id)
    const item = uploads.value.find(
      (entry) => entry.sourceId === currentSource.value!.id,
    )
    if (item) {
      item.state = 'inspecting'
      item.jobId = response.job_id
    }
  })
}
async function loadIssues() {
  if (!currentJob.value) return
  const result = await documentTools.issues(
    currentJob.value.id,
    issuePage.value,
  )
  issues.value = result.items
  issuesTotal.value = result.total
}
function locate(source: Anchor, target: string) {
  anchor.value = source
  selectedTarget.value = target
  if (source.page_index != null) pageIndex.value = source.page_index
  view.value = canCompare.value ? 'compare' : 'source'
  notice.value =
    source.anchor_precision === 'cell'
      ? '已定位到原文单元格'
      : source.bbox_pt
        ? '按原文区域定位；来源精度为区域或区块'
        : `原文位置：${source.sheet ?? ''} ${source.cell ?? ''} ${source.block_id ?? ''}`
}
async function recognizeRegion() {
  if (!canRecognizeRegion.value || !currentJob.value || !selectedRegion.value)
    return
  await runAction(async () => {
    const response = await documentTools.revise(currentJob.value!.id, {
      base_revision: currentJob.value!.revision,
      corrections: [],
      region: { page_index: pageIndex.value, bbox_pt: selectedRegion.value! },
    })
    await followJob(response.job_id)
    regionMode.value = false
    selectedRegion.value = undefined
  })
}
function setCuts(values: number[]) {
  cuts.value = normalizeCuts(values, extent.value)
  cutHistory.value = cutHistory.value.slice(0, cutPosition.value + 1)
  cutHistory.value.push([...cuts.value])
  cutPosition.value++
  const crossing = cuts.value.filter((cut) =>
    protectedRegions.value.some((region) => {
      const a = axis.value === 'x' ? 0 : 1
      return (
        cut > region.bbox_pt[a]! + 0.1 && cut < region.bbox_pt[a + 2]! - 0.1
      )
    }),
  )
  if (crossing.length)
    notice.value = `${crossing.length} 条切线可能穿过正文、表格行或图片，请对照预览移动切线。`
}
function undo() {
  if (cutPosition.value > 0)
    cuts.value = [...cutHistory.value[--cutPosition.value]!]
}
function redo() {
  if (cutPosition.value < cutHistory.value.length - 1)
    cuts.value = [...cutHistory.value[++cutPosition.value]!]
}
function setAxis(value: 'x' | 'y') {
  axis.value = value
  cuts.value = []
  cutHistory.value = [[]]
  cutPosition.value = 0
  suggestions.value = []
  protectedRegions.value = []
}
async function suggest() {
  if (!currentSource.value) return
  await runAction(async () => {
    const response = await documentTools.suggestions(
      currentSource.value!.id,
      pageIndex.value,
      axis.value,
    )
    suggestions.value = response.cuts_pt
    protectedRegions.value = response.protected_regions
    notice.value = response.cuts_pt.length
      ? '候选切点已就绪，选择“加入草稿”后可继续调整。'
      : '未找到可靠的切点，请手动添加并对照原文。'
  })
}
function changeSourcePage(index: number) {
  if (pageIndex.value !== index) {
    pageIndex.value = index
    cuts.value = []
    cutHistory.value = [[]]
    cutPosition.value = 0
    suggestions.value = []
    protectedRegions.value = []
    selectedRegion.value = undefined
  }
}
function openDialog(dialog?: HTMLDialogElement) {
  dialog?.showModal()
}
function toggleArtifact(id: string, checked: boolean) {
  checkedArtifacts.value = checked
    ? [...checkedArtifacts.value, id]
    : checkedArtifacts.value.filter((item) => item !== id)
}
function downloadable(artifact: Artifact) {
  return (
    !artifact.expires_at ||
    (typeof artifact.expires_at === 'number'
      ? artifact.expires_at * 1000
      : new Date(artifact.expires_at).getTime()) > Date.now()
  )
}
async function initialize() {
  if (initializing.value) return
  initializing.value = true
  error.value = ''
  try {
    await Promise.all([refreshCapabilities(), loadJobs()])
  } catch (problem) {
    error.value = getApiErrorMessage(problem)
  } finally {
    initializing.value = false
    schedule()
  }
}
onMounted(() => {
  void initialize()
  if (root.value && typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (entry.target === root.value) width.value = entry.contentRect.width
        if (entry.target === workspace.value)
          workspaceWidth.value = entry.contentRect.width
      }
    })
    observer.observe(root.value)
    if (workspace.value) observer.observe(workspace.value)
  }
  document.addEventListener('visibilitychange', visibility)
})
onBeforeUnmount(() => {
  disposed = true
  selectionSequence++
  clearTimeout(poll)
  observer?.disconnect()
  document.removeEventListener('visibilitychange', visibility)
})
</script>

<template>
  <div
    ref="root"
    class="app-page dt-workbench"
    data-yl-help="document-tools.overview"
    :class="{ 'dt-narrow': narrow, 'dt-phone': phone, 'dt-focus': focused }"
  >
    <PageHeader
      class="tools-hero rrn-portal-region"
      data-portal-region="tools-header"
      title="公共工具栏"
      :description="isHuaxing ? '协同填表、文档翻译、转换、精确分页与批量改名 · 华兴厂区' : '协同填表、文档翻译、转换与精确分页'"
      ><template #actions
        ><Button variant="outline" size="sm" :aria-pressed="sheetsActive" @click="selectSheets"
          ><Files :size="15" aria-hidden="true" />{{ sheetsActive ? '返回文档转换' : '协同填表' }}</Button
        ><Button as-child variant="outline" size="sm"><a :href="imageTranslationUrl"><Languages :size="15" aria-hidden="true" />图片 / PDF 翻译</a></Button
        ><Button v-if="isHuaxing" variant="outline" size="sm" :aria-pressed="renameActive" @click="selectRename(!renameActive)"
          ><Files :size="15" aria-hidden="true" />{{ renameActive ? '返回文档转换' : '批量改名' }}</Button
        ><Button v-if="!renameActive && !sheetsActive" variant="outline" size="sm" @click="openDialog(tasksDialog)"
          ><Files :size="15" aria-hidden="true" />我的任务</Button
        ><Button
          v-if="!renameActive && !sheetsActive"
          variant="outline"
          size="sm"
          :aria-pressed="focused"
          @click="focused = !focused"
          ><Maximize2 :size="15" aria-hidden="true" />{{
            focused ? '退出专注' : '专注模式'
          }}</Button
        ></template
      ></PageHeader
    >
    <input
      ref="picker"
      class="dt-file-picker"
      type="file"
      accept=".doc,.docx,.xls,.xlsx,.pdf"
      multiple
      aria-label="上传文档"
      @change="picked"
    />
    <div v-if="error && !renameActive && !sheetsActive" class="dt-alert" role="alert">
      <AlertCircle :size="16" aria-hidden="true" /><span>{{ error }}</span
      ><Button variant="ghost" size="sm" @click="initialize">重新连接</Button>
    </div>
    <p v-if="notice && !renameActive && !sheetsActive" class="dt-notice" role="status">{{ notice }}</p>
    <details v-if="capabilities?.engines && !renameActive && !sheetsActive" class="dt-engine-status">
      <summary>处理引擎状态</summary>
      <Button
        variant="ghost"
        size="sm"
        :disabled="initializing"
        @click="initialize"
        >刷新服务状态</Button
      >
      <span v-for="(engine, name) in capabilities.engines" :key="name"
        >{{ engineLabels[name] ?? name }}：{{
          !engine.configured
            ? '尚未配置'
            : engine.tested
              ? '已通过实测'
              : '已配置，尚未实测'
        }}</span
      >
    </details>
    <div
      v-if="capabilities && !capabilities.worker.online && !renameActive && !sheetsActive"
      class="dt-warning"
      role="status"
    >
      后台处理服务暂未在线，文件和任务会保留；服务恢复后继续处理。
    </div>
    <CollaborativeSheetsWorkspace
      v-if="sheetsActive"
      :key="appStore.activeFactoryId"
      :factory-id="appStore.activeFactoryId"
    />
    <PdfBatchRenameWorkspace
      v-if="renameActive"
      :key="appStore.activeFactoryId"
      :factory-id="appStore.activeFactoryId"
      context-label="华兴厂区（仅华兴可用）"
    />
    <div
      v-show="!renameActive && !sheetsActive"
      class="dt-desk"
      :class="{ dragging }"
      @dragover.prevent="dragging = true"
      @dragleave.self="dragging = false"
      @drop.prevent="drop"
    >
      <aside v-if="!focused" class="dt-rail" aria-label="文档工具与本批文件">
        <h2>文档工具</h2>
        <nav class="dt-tools" aria-label="选择文档工具">
          <a :href="imageTranslationUrl" class="dt-image-translation-link">
            <Languages :size="16" aria-hidden="true" /><span>图片 / PDF 翻译</span><ArrowRight :size="14" aria-hidden="true" />
          </a>
          <button
            v-for="tool in toolIds"
            :key="tool"
            type="button"
            :class="{ active: operation === tool, 'dt-tool-divider': tool === 'word_translate' || tool === 'pdf_split' }"
            :aria-pressed="operation === tool"
            @click="operation = tool"
          >
            <Scissors
              v-if="tool === 'pdf_split'"
              :size="16"
              aria-hidden="true"
            /><Languages v-else-if="tool.endsWith('_translate')" :size="16" aria-hidden="true" /><FileText v-else :size="16" aria-hidden="true" /><span>{{
              operationLabels[tool]
            }}</span>
          </button>
          <button v-if="isHuaxing" type="button" :aria-pressed="renameActive" @click="selectRename(true)">
            <Files :size="16" aria-hidden="true" /><span>批量改名 · 华兴</span>
          </button>
        </nav>
        <div class="dt-rail-heading">
          <h2>
            本批文件 <span>{{ uploads.length || '' }}</span>
          </h2>
          <Button
            variant="ghost"
            size="icon"
            aria-label="添加文档"
            @click="picker?.click()"
            ><Upload :size="15" aria-hidden="true"
          /></Button>
        </div>
        <div class="dt-file-list">
          <article
            v-for="item in uploads"
            :key="item.id"
            class="dt-file"
            :class="{ selected: selectedUpload === item.id }"
          >
            <button
              type="button"
              :disabled="!item.sourceId"
              :title="item.name"
              @click="selectSource(item.sourceId!, item.jobId)"
            >
              <span class="dt-file-name">{{ item.name }}</span
              ><small
                >{{ (item.size / 1024 / 1024).toFixed(2) }} MB ·
                {{ stateLabel(item.state) }}</small
              ></button
            ><progress
              v-if="item.state === 'uploading'"
              :value="item.progress"
              max="100"
              :aria-label="`${item.name} 上传进度`"
            />
            <p v-if="item.error" class="dt-file-error">{{ item.error }}</p>
            <Button
              v-if="item.state === 'failed' && item.file"
              variant="ghost"
              size="sm"
              @click="uploadOne(item)"
              >重试上传</Button
            >
          </article>
          <p v-if="!uploads.length" class="dt-rail-empty">
            支持多文件逐个上传<br />每份文档独立处理
          </p>
        </div>
      </aside>
      <main ref="workspace" class="dt-main" aria-label="文档工作台">
        <div class="dt-document-bar">
          <div>
            <strong>{{ currentSource?.original_name ?? '文档工作台' }}</strong
            ><span v-if="currentSource"
              >{{ currentSource.detected_type.toUpperCase()
              }}<template v-if="currentSource.manifest.pages?.length">
                · {{ currentSource.manifest.pages.length }} 页</template
              ><template v-if="currentSource.manifest.sheets?.length">
                · {{ currentSource.manifest.sheets.length }} 个工作表</template
              ></span
            ><span v-else>原生解析 · 原文对照 · 可编辑结果</span>
          </div>
          <TaskActions
            v-if="currentJob"
            :job="currentJob"
            :busy="busy"
            @withdraw="withdrawJob"
            @delete="requestDelete"
          />
          <Button
            v-if="narrow || focused"
            variant="outline"
            size="sm"
            @click="openDialog(settingsDialog)"
            ><PanelRight :size="15" aria-hidden="true" />设置</Button
          >
        </div>
        <section v-if="translating" class="dt-translation-intro" aria-label="文档翻译设置">
          <strong><Languages :size="18" aria-hidden="true" />{{ operationLabels[operation] }} · 中英互译</strong>
          <TranslationOptions v-model="options" :availability="capabilities?.translation" compact />
          <p>保留原件，生成独立译文。{{ operation === 'pdf_translate' ? 'PDF 译文重新排版，同时提供可编辑 Word。' : '保留文档格式；图片中的文字不翻译。' }}</p>
        </section>
        <div v-if="!currentSource && !currentJob" class="dt-empty">
          <div class="dt-drop">
            <div class="dt-upload-icon">
              <Upload :size="27" :stroke-width="1.5" aria-hidden="true" />
            </div>
            <h2>{{ translating ? '上传文档，生成中英译文' : '拖入文档，选择你需要的结果' }}</h2>
            <p>{{ translating ? '选择翻译方向与方式，上传后即可开始。' : 'Word、Excel 或 PDF，保留原文件，生成独立结果。' }}</p>
            <Button @click="picker?.click()"
              >选择文件 <ArrowRight :size="15" aria-hidden="true" /></Button
            ><small
              >DOC / DOCX · XLS / XLSX · PDF<template v-if="capabilities">
                · 最大
                {{
                  Math.round(capabilities.limits.max_file_bytes / 1024 / 1024)
                }}
                MB</template
              ></small
            >
          </div>
          <div class="dt-instructions">
            <span><b>01</b> 上传并读取文档</span
            ><span><b>02</b> 选择格式与范围</span
            ><span><b>03</b> 对照原文后下载</span>
          </div>
          <section class="dt-recent">
            <div>
              <h3>最近任务</h3>
              <Button variant="ghost" size="sm" @click="openDialog(tasksDialog)"
                >查看全部</Button
              >
            </div>
            <article
              v-for="job in jobs.slice(0, 3)"
              :key="job.id"
              class="dt-recent-task"
            >
              <button type="button" @click="selectJob(job)">
                <FileText :size="16" aria-hidden="true" /><span>{{
                  job.source_name || '结果打包'
                }}</span
                ><StatusPill
                  :label="stateLabel(job.execution_status)"
                  :tone="tone(job.execution_status)"
                  compact
                />
              </button>
              <TaskActions
                :job="job"
                :busy="busy"
                @withdraw="withdrawJob"
                @delete="requestDelete"
              />
            </article>
            <p v-if="!jobs.length">还没有任务。上传第一份文档开始处理。</p>
          </section>
        </div>
        <template v-else>
          <div class="dt-view-tabs" role="tablist" aria-label="文档视图">
            <button
              type="button"
              role="tab"
              :aria-selected="view === 'source'"
              @click="view = 'source'"
            >
              原文</button
            ><button
              v-if="canCompare"
              type="button"
              role="tab"
              :disabled="!hasResult"
              :aria-selected="view === 'compare'"
              @click="view = 'compare'"
            >
              对照</button
            ><button
              type="button"
              role="tab"
              :disabled="!hasResult"
              :aria-selected="view === 'result'"
              @click="view = 'result'"
            >
              结果</button
            ><span class="dt-tab-spacer" />
            <Button
              v-if="
                resultPreview &&
                hasResult &&
                !pdfOutput
              "
              variant="ghost"
              size="sm"
              :aria-pressed="resultLayout"
              @click="resultLayout = !resultLayout"
              >{{ resultLayout ? '核对数据' : 'PDF 校样' }}</Button
            >
            <Button
              v-if="canRecognizeRegion"
              variant="ghost"
              size="sm"
              :aria-pressed="regionMode"
              @click="toggleRegion"
              >{{ regionMode ? '退出框选' : '框选重新识别' }}</Button
            >
          </div>
          <div v-if="selectedRegion && regionMode" class="dt-region-action">
            已选择第 {{ pageIndex + 1 }} 页区域<Button
              variant="outline"
              size="sm"
              :disabled="busy"
              @click="recognizeRegion"
              >重新识别这里并生成新版</Button
            >
          </div>
          <div
            class="dt-document-content"
            :class="{ comparing: view === 'compare' }"
          >
            <div v-if="view !== 'result'" class="dt-source-pane">
              <PdfCanvas
                v-if="sourcePreview"
                :key="sourcePreview.id"
                :url="documentTools.artifactUrl(sourcePreview.id)"
                :page-index="pageIndex"
                :cuts="cuts"
                :snap-points="snapPoints"
                :axis="axis"
                :editing="cropMode"
                :select-region="regionMode"
                :highlight="anchor?.bbox_pt"
                @page="changeSourcePage"
                @cuts="setCuts"
                @dimensions="dimensions = $event"
                @region="selectedRegion = $event"
              />
              <div v-else class="dt-preview-empty">
                <FolderOpen :size="30" aria-hidden="true" />
                <h3>
                  {{ sourceReady ? '原文版式校样尚未生成' : '正在读取文档' }}
                </h3>
                <p>
                  Office 文档使用服务器 PDF 校样预览，生成后可核对结构化结果。
                </p>
                <a
                  v-for="artifact in currentSource?.artifacts.filter(
                    (item) => item.role === 'source',
                  )"
                  :key="artifact.id"
                  :href="documentTools.artifactUrl(artifact.id, true)"
                  >下载原文 · {{ artifact.filename }}</a
                >
              </div>
            </div>
            <div
              v-if="currentJob && hasResult"
              v-show="view !== 'source'"
              class="dt-result-pane"
            >
              <PdfCanvas
                v-if="resultPreview"
                v-show="resultLayout || pdfOutput"
                :url="documentTools.artifactUrl(resultPreview.id)"
                :page-index="resultPage"
                @page="resultPage = $event"
              /><ResultReview
                v-if="!pdfOutput"
                v-show="!resultLayout"
                :job="currentJob"
                :readonly="currentJob.operation.endsWith('_translate')"
                :selected-target="selectedTarget"
                @locate="locate"
                @revised="followJob"
              />
            </div>
          </div>
          <div
            v-if="currentJob?.execution_status === 'awaiting_input'"
            class="dt-password"
          >
            <label
              >此文件需要密码<input
                v-model="password"
                type="password"
                autocomplete="off"
                aria-label="文件密码"
                @keyup.enter="unlock" /></label
            ><Button :disabled="busy || !password" size="sm" @click="unlock"
              >解锁并继续</Button
            ><small>仅用于本次读取，不保存在浏览器。</small>
          </div>
          <footer class="dt-progress">
            <span>{{ progressText }}</span
            ><StatusPill
              v-if="currentJob"
              :label="stateLabel(currentJob.execution_status)"
              :tone="tone(currentJob.execution_status)"
              compact
            /><progress
              v-if="
                currentJob && isActiveJob(currentJob) && currentJob.total_units
              "
              :value="currentJob.completed_units"
              :max="currentJob.total_units"
              aria-label="实际处理进度"
            /><Button
              v-if="
                currentJob &&
                ['failed', 'cancelled'].includes(currentJob.execution_status)
              "
              variant="outline"
              size="sm"
              :disabled="busy"
              @click="
                runAction(async () =>
                  followJob((await documentTools.retry(currentJob!.id)).job_id),
                )
              "
              >重试任务</Button
            >
          </footer>
          <p v-if="currentJob?.error_message" class="dt-job-error" role="alert">
            {{ currentJob.error_message }}
          </p>
        </template>
      </main>
      <aside
        v-if="!narrow && !focused"
        class="dt-context"
        aria-label="当前文档设置"
      >
        <ToolOptions
          v-model="options"
          :operation="operation"
          :translation-availability="capabilities?.translation"
          :source="currentSource"
          :cuts="cuts"
          :axis="axis"
          :extent="extent"
          :suggestions="suggestions"
          @cuts="setCuts"
          @axis="setAxis"
          @undo="undo"
          @redo="redo"
          @suggest="suggest"
        />
        <div class="dt-generate">
          <p v-if="!compatible">
            此文件不适用
            {{ operationLabels[operation] }}，请选择与原文格式对应的工具。
          </p>
          <p v-if="capability && !capability.available">
            {{ capability.reason || '此转换引擎暂不可用' }}
          </p>
          <Button
            :disabled="
              busy || !sourceReady || !compatible || !capability?.available || translationUnavailable
            "
            @click="start"
            >{{
              initializing
                ? '读取服务状态…'
                : submitting
                  ? '正在提交…'
                  : operation === 'pdf_split'
                    ? '生成分页文件'
                    : translating ? '开始翻译' : '生成文档'
            }}<ArrowRight :size="15" aria-hidden="true" /></Button
          ><small v-if="!currentSource">上传文件后可生成结果</small>
        </div>
        <section v-if="hasResult" class="dt-result-actions">
          <StatusPill
            :label="stateLabel(currentJob!.quality_status)"
            :tone="tone(currentJob!.quality_status)"
            compact
          />
          <h3>结果文件</h3>
          <div v-for="artifact in results" :key="artifact.id">
            <a
              v-if="downloadable(artifact)"
              :href="documentTools.artifactUrl(artifact.id, true)"
              >{{ artifact.filename }}</a
            ><span v-else>{{ artifact.filename }} · 已过期</span>
          </div>
          <a
            v-for="artifact in currentJob?.artifacts.filter((item) =>
              ['report', 'mapping'].includes(item.role),
            )"
            :key="artifact.id"
            :href="documentTools.artifactUrl(artifact.id, true)"
            >{{
              artifact.role === 'report' ? '下载处理报告' : '下载来源映射'
            }}</a
          ><Button
            v-if="issuesTotal"
            variant="outline"
            size="sm"
            @click="openDialog(tasksDialog)"
            >查看 {{ issuesTotal }} 项核验提示</Button
          >
        </section>
      </aside>
    </div>
    <div v-if="hasResult && (narrow || focused) && !renameActive && !sheetsActive" class="dt-mobile-results">
      <a
        v-for="artifact in results"
        :key="artifact.id"
        :href="documentTools.artifactUrl(artifact.id, true)"
        >下载 {{ artifact.filename }}</a
      ><Button
        v-if="issuesTotal"
        variant="outline"
        size="sm"
        @click="openDialog(tasksDialog)"
        >核验提示 {{ issuesTotal }}</Button
      >
    </div>
    <dialog
      ref="settingsDialog"
      class="dt-dialog dt-settings-dialog"
      aria-labelledby="dt-settings-title"
    >
      <header>
        <h2 id="dt-settings-title">{{ operationLabels[operation] }} · 设置</h2>
        <Button
          variant="ghost"
          size="icon"
          aria-label="关闭设置"
          @click="settingsDialog?.close()"
          ><X :size="18"
        /></Button>
      </header>
      <div class="dt-dialog-body">
        <ToolOptions
          v-model="options"
          :operation="operation"
          :translation-availability="capabilities?.translation"
          :source="currentSource"
          :cuts="cuts"
          :axis="axis"
          :extent="extent"
          :suggestions="suggestions"
          @cuts="setCuts"
          @axis="setAxis"
          @undo="undo"
          @redo="redo"
          @suggest="suggest"
        />
        <p v-if="!compatible">当前文件与所选工具不匹配，请切换工具。</p>
        <p v-if="capability && !capability.available">
          {{ capability.reason }}
        </p>
        <Button
          class="dt-dialog-generate"
          :disabled="
            busy || !sourceReady || !compatible || !capability?.available || translationUnavailable
          "
          @click="generateFromDialog"
          >{{ translating ? '开始翻译' : '生成文档' }}</Button
        >
      </div>
    </dialog>
    <dialog
      ref="tasksDialog"
      class="dt-dialog dt-tasks-dialog"
      aria-labelledby="dt-tasks-title"
    >
      <header>
        <h2 id="dt-tasks-title">我的任务</h2>
        <Button
          variant="ghost"
          size="icon"
          aria-label="关闭我的任务"
          @click="tasksDialog?.close()"
          ><X :size="18"
        /></Button>
      </header>
      <div class="dt-dialog-body">
        <section v-if="issuesTotal && currentJob" class="dt-issues">
          <h3>当前结果 · {{ issuesTotal }} 项核验提示</h3>
          <article v-for="issue in issues" :key="issue.id">
            <strong>{{ issue.message }}</strong>
            <p>
              {{
                issue.source.page_index != null
                  ? `第 ${issue.source.page_index + 1} 页`
                  : ''
              }}
              {{ issue.source.sheet }} {{ issue.source.cell }} ·
              {{
                issue.source.anchor_precision === 'cell'
                  ? '单元格定位'
                  : '区域 / 区块定位'
              }}
            </p>
            <p v-if="issue.candidates.length">
              候选值：{{ issue.candidates.join(' / ') }}
            </p>
            <p>{{ issue.action }}</p>
            <Button variant="outline" size="sm" @click="locateIssue(issue)"
              >查看原文并核对</Button
            >
          </article>
          <div class="dt-pagination">
            <Button
              variant="outline"
              size="sm"
              :disabled="issuePage <= 1"
              @click="paginateIssues(-1)"
              >上一页提示</Button
            ><Button
              variant="outline"
              size="sm"
              :disabled="issuePage * 25 >= issuesTotal"
              @click="paginateIssues(1)"
              >下一页提示</Button
            >
          </div>
        </section>
        <p v-if="error" class="dt-job-error" role="alert">{{ error }}</p>
        <p v-if="notice" class="dt-notice" role="status">{{ notice }}</p>
        <div class="dt-task-controls">
          <Button
            variant="outline"
            size="sm"
            :disabled="refreshing"
            @click="refresh(true)"
            >刷新任务</Button
          ><Button
            variant="outline"
            size="sm"
            :disabled="!checkedArtifacts.length || busy"
            @click="
              runAction(async () =>
                followJob(
                  (await documentTools.package(checkedArtifacts)).job_id,
                ),
              )
            "
            >打包选中结果（{{ checkedArtifacts.length }}）</Button
          >
        </div>
        <article v-for="job in jobs" :key="job.id" class="dt-task">
          <button type="button" class="dt-task-title" @click="selectJob(job)">
            <FileText :size="17" aria-hidden="true" /><strong>{{
              job.source_name || '结果打包'
            }}</strong>
          </button>
          <div class="dt-task-meta">
            <span>{{
              operationLabels[job.operation as Operation] ??
              statusLabels[job.operation] ??
              job.operation
            }}</span
            ><span>{{
              new Date(job.created_at).toLocaleString('zh-CN', {
                timeZone: 'Asia/Shanghai',
              })
            }}</span
            ><StatusPill
              :label="stateLabel(job.execution_status)"
              :tone="tone(job.execution_status)"
              compact
            /><StatusPill
              v-if="job.execution_status === 'succeeded'"
              :label="stateLabel(job.quality_status)"
              :tone="tone(job.quality_status)"
              compact
            />
          </div>
          <p v-if="job.error_message">{{ job.error_message }}</p>
          <div class="dt-task-files">
            <label
              v-for="artifact in job.artifacts.filter((item) =>
                ['result', 'package'].includes(item.role),
              )"
              :key="artifact.id"
              ><input
                type="checkbox"
                :disabled="!downloadable(artifact)"
                :checked="checkedArtifacts.includes(artifact.id)"
                :aria-label="`选择 ${artifact.filename} 打包`"
                @change="
                  toggleArtifact(
                    artifact.id,
                    ($event.target as HTMLInputElement).checked,
                  )
                "
              /><a
                v-if="downloadable(artifact)"
                :href="documentTools.artifactUrl(artifact.id, true)"
                >{{ artifact.filename }} · v{{ artifact.revision }}</a
              ><span v-else>{{ artifact.filename }} · 已过期</span></label
            >
          </div>
          <div class="dt-task-actions">
            <TaskActions
              :job="job"
              :busy="busy"
              @withdraw="withdrawJob"
              @delete="requestDelete"
            /><Button
              v-if="['failed', 'cancelled'].includes(job.execution_status)"
              variant="outline"
              size="sm"
              :disabled="busy"
              @click="
                runAction(async () =>
                  followJob((await documentTools.retry(job.id)).job_id),
                )
              "
              >重试</Button
            >
          </div>
        </article>
        <p v-if="!jobs.length">还没有任务。所有文件与结果仅当前上传者可见。</p>
        <div class="dt-pagination">
          <Button
            variant="outline"
            size="sm"
            :disabled="taskPage <= 1"
            @click="paginateTasks(-1)"
            >上一页</Button
          ><span>第 {{ taskPage }} 页 · 共 {{ jobTotal }} 项</span
          ><Button
            variant="outline"
            size="sm"
            :disabled="taskPage * 20 >= jobTotal"
            @click="paginateTasks(1)"
            >下一页</Button
          >
        </div>
      </div>
    </dialog>
    <dialog
      ref="deleteDialog"
      class="dt-dialog dt-delete-dialog"
      aria-labelledby="dt-delete-title"
      aria-describedby="dt-delete-description"
      @cancel="busy && $event.preventDefault()"
    >
      <header><h2 id="dt-delete-title">删除这个任务？</h2></header>
      <div class="dt-dialog-body">
        <p class="dt-delete-name">
          {{ deletingJob?.source_name || '结果打包' }}
        </p>
        <p id="dt-delete-description">
          删除后，任务将从最近任务和我的任务中移除。原文件、已生成文件及其他任务会保留，任务记录无法在页面恢复。
        </p>
        <p
          v-if="
            deletingJob &&
            ['queued', 'running', 'awaiting_input'].includes(
              deletingJob.execution_status,
            )
          "
        >
          此任务尚未结束，删除时会同时撤回，不再发布新结果。
        </p>
        <p v-if="deleteError" class="dt-job-error" role="alert">
          {{ deleteError }}
        </p>
        <div class="dt-delete-controls">
          <Button
            variant="outline"
            :disabled="busy"
            autofocus
            @click="deleteDialog?.close()"
            >保留任务</Button
          >
          <Button
            variant="destructive"
            :disabled="busy"
            @click="confirmDelete"
            >{{ busy ? '正在删除…' : '确认删除' }}</Button
          >
        </div>
      </div>
    </dialog>
  </div>
</template>
