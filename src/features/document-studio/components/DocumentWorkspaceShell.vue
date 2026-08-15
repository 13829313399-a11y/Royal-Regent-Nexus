<script setup lang="ts">
import {
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  Download,
  FileCheck2,
  FileText,
  History,
  Info,
  LoaderCircle,
  LockKeyhole,
  RotateCcw,
  Settings2,
  X,
} from '@lucide/vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { sharedToolsApi } from '@/api/tools'
import type { AIArtifactData } from '@/api/aiArtifacts'
import { Button } from '@/components/ui/button'
import DocumentTranslationTool from '@/components/tools/DocumentTranslationTool.vue'
import { downloadToolBlob } from '@/components/tools/pdfToolUtils'
import { getDocumentTool } from '../constants'
import {
  cancelDocumentJob,
  createDocumentJob,
  documentJobTypeForTool,
  downloadDocumentJobResult,
  getDocumentJob,
  getDocumentJobCapabilities,
  getDocumentJobResult,
  retryDocumentJob,
  type DocumentJob,
  type DocumentJobCapabilities,
  type DocumentProcessingMode,
  type DocumentPreflight,
} from '../api/documentJobs'
import type { DocumentToolId, DocumentWorkspaceState } from '../types'
import DocumentDropzone from './DocumentDropzone.vue'
import DocumentReviewPanel from './DocumentReviewPanel.vue'

const props = defineProps<{
  toolId: DocumentToolId
  factoryId: string
  contextLabel: string
}>()

const selectedFile = ref<File | null>(null)
const previewUrl = ref('')
const resultPreviewUrl = ref('')
const previewPane = ref<'source' | 'result'>('source')
const state = ref<DocumentWorkspaceState>('EMPTY')
const errorMessage = ref('')
const resultBlob = ref<Blob | null>(null)
const resultFileName = ref('')
const resultSummary = ref<string[]>([])
const splitMode = ref<'each_page' | 'ranges'>('each_page')
const pageRanges = ref('')
const processingMode = ref<DocumentProcessingMode>('LOCAL_PRIVATE')
const cloudConsentAccepted = ref(false)
const sheetStrategy = ref<'TABLE_PER_SHEET' | 'PAGE_PER_SHEET' | 'MERGE_SAME_SCHEMA'>('TABLE_PER_SHEET')
const typeInference = ref<'CONSERVATIVE' | 'SMART'>('CONSERVATIVE')
const wordMode = ref<'EDITABLE' | 'LAYOUT_PRESERVING'>('EDITABLE')
const translationDirection = ref<'AUTO' | 'ZH_TO_EN' | 'EN_TO_ZH'>('AUTO')
const translationLayout = ref<'TRANSLATED_ONLY' | 'SIDE_BY_SIDE' | 'STACKED'>('TRANSLATED_ONLY')
const includeEditableDocx = ref(false)
const protectedTokens = ref('')
const settingsPreset = ref<'STANDARD' | 'DATA_TABLE' | 'LAYOUT' | 'BILINGUAL'>('STANDARD')
const showOfficeTranslation = ref(false)
const jobCapabilities = ref<DocumentJobCapabilities | null>(null)
const currentJob = ref<DocumentJob | null>(null)
const uploadedSource = ref<AIArtifactData | null>(null)
const cachedPreflight = ref<DocumentPreflight | null>(null)
const operationId = ref('')
const batchQueue = ref<File[]>([])
const batchTotal = ref(0)
const batchCompleted = ref(0)
const batchRunning = ref(false)
let pollTimer: ReturnType<typeof setTimeout> | null = null

const tool = computed(() => getDocumentTool(props.toolId))
const isPdf = computed(() => selectedFile.value?.name.toLowerCase().endsWith('.pdf') ?? false)
const activeStates: DocumentWorkspaceState[] = ['UPLOADING', 'PREFLIGHTING', 'RUNNING', 'VERIFYING']
const isBusy = computed(() => activeStates.includes(state.value))
const hasActiveJob = computed(() => Boolean(
  currentJob.value
  && !['COMPLETED', 'FAILED', 'CANCELLED', 'EXPIRED'].includes(currentJob.value.state),
))
const taskRuntimeAvailable = computed(() => Boolean(
  jobCapabilities.value?.available
  && jobCapabilities.value.supported_job_types.includes(documentJobTypeForTool(props.toolId)),
))
const effectiveToolAvailable = computed(() => tool.value.available || taskRuntimeAvailable.value)
const workspaceTool = computed(() => ({ ...tool.value, available: effectiveToolAvailable.value }))
const canStart = computed(() => Boolean(
  selectedFile.value
  && effectiveToolAvailable.value
  && !isBusy.value
  && !hasActiveJob.value
  && (processingMode.value !== 'AI_ENHANCED' || cloudConsentAccepted.value),
))
const stateLabel = computed(() => ({
  EMPTY: '等待文件',
  PREFLIGHTING: '文件预检',
  READY: '已就绪',
  UPLOADING: '安全上传',
  RUNNING: '处理中',
  REVIEW_REQUIRED: '需要复核',
  VERIFYING: '结果验证',
  COMPLETED: '已完成',
  FAILED: '处理失败',
  CANCELLED: '已取消',
  EXPIRED: '结果已过期',
}[state.value]))

function stopPolling() {
  if (pollTimer) clearTimeout(pollTimer)
  pollTimer = null
}

function clearPreviewUrl() {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
  if (resultPreviewUrl.value) URL.revokeObjectURL(resultPreviewUrl.value)
  resultPreviewUrl.value = ''
  previewPane.value = 'source'
}

function resetWorkspace() {
  stopPolling()
  clearPreviewUrl()
  selectedFile.value = null
  state.value = 'EMPTY'
  errorMessage.value = ''
  resultBlob.value = null
  resultFileName.value = ''
  resultSummary.value = []
  splitMode.value = 'each_page'
  pageRanges.value = ''
  processingMode.value = 'LOCAL_PRIVATE'
  cloudConsentAccepted.value = false
  sheetStrategy.value = 'TABLE_PER_SHEET'
  typeInference.value = 'CONSERVATIVE'
  wordMode.value = 'EDITABLE'
  translationDirection.value = 'AUTO'
  translationLayout.value = 'TRANSLATED_ONLY'
  includeEditableDocx.value = false
  protectedTokens.value = ''
  settingsPreset.value = 'STANDARD'
  showOfficeTranslation.value = false
  currentJob.value = null
  uploadedSource.value = null
  cachedPreflight.value = null
  operationId.value = ''
  batchQueue.value = []
  batchTotal.value = 0
  batchCompleted.value = 0
  batchRunning.value = false
}

function selectFile(file: File) {
  stopPolling()
  clearPreviewUrl()
  selectedFile.value = file
  previewUrl.value = URL.createObjectURL(file)
  state.value = 'READY'
  errorMessage.value = ''
  resultBlob.value = null
  resultFileName.value = ''
  resultSummary.value = []
  currentJob.value = null
  uploadedSource.value = null
  cachedPreflight.value = null
  operationId.value = ''
}

function selectFiles(files: File[]) {
  resetWorkspace()
  const [first, ...remaining] = files
  if (!first) return
  batchQueue.value = remaining
  batchTotal.value = files.length
  selectFile(first)
}

function showValidationError(message: string) {
  errorMessage.value = message
  state.value = 'FAILED'
}

function humanFileSize(bytes: number) {
  return bytes >= 1024 * 1024
    ? `${(bytes / 1024 / 1024).toFixed(1)} MB`
    : `${Math.max(1, Math.ceil(bytes / 1024))} KB`
}

function applySettingsPreset() {
  if (settingsPreset.value === 'DATA_TABLE') {
    sheetStrategy.value = 'MERGE_SAME_SCHEMA'
    typeInference.value = 'SMART'
  }
  else if (settingsPreset.value === 'LAYOUT') {
    wordMode.value = 'LAYOUT_PRESERVING'
    translationLayout.value = 'TRANSLATED_ONLY'
  }
  else if (settingsPreset.value === 'BILINGUAL') {
    translationLayout.value = 'SIDE_BY_SIDE'
    includeEditableDocx.value = true
  }
  else {
    sheetStrategy.value = 'TABLE_PER_SHEET'
    typeInference.value = 'CONSERVATIVE'
    wordMode.value = 'EDITABLE'
    translationLayout.value = 'TRANSLATED_ONLY'
    includeEditableDocx.value = false
  }
}

async function runConversion() {
  const file = selectedFile.value
  if (!file || !effectiveToolAvailable.value) return
  if (batchTotal.value > 1) batchRunning.value = true
  if (props.toolId === 'pdf-split' && splitMode.value === 'ranges' && !pageRanges.value.trim()) {
    errorMessage.value = '请输入页段，例如 1-3,5,8-10。'
    state.value = 'FAILED'
    return
  }

  const previousState = state.value
  state.value = 'RUNNING'
  errorMessage.value = ''
  resultBlob.value = null
  resultSummary.value = []

  try {
    if (taskRuntimeAvailable.value) {
      if (
        currentJob.value?.task_id
        && previousState === 'FAILED'
        && !['FAILED', 'CANCELLED', 'EXPIRED'].includes(currentJob.value.state)
      ) {
        await pollDocumentJob()
        return
      }
      if (currentJob.value?.state === 'FAILED') {
        currentJob.value = await retryDocumentJob(currentJob.value)
        state.value = mapJobState(currentJob.value)
        await pollDocumentJob()
        return
      }
      const created = await createDocumentJob({
        file,
        factoryId: props.factoryId,
        toolId: props.toolId,
        processingMode: processingMode.value,
        cloudConsentAccepted: cloudConsentAccepted.value,
        options: {
          splitMode: splitMode.value,
          splitPageRanges: pageRanges.value,
          sheetStrategy: sheetStrategy.value,
          typeInference: typeInference.value,
          wordMode: wordMode.value,
          translationDirection: translationDirection.value,
          translationLayout: translationLayout.value,
          protectedTokens: protectedTokens.value
            .split(/[\n,]/)
            .map(item => item.trim())
            .filter(Boolean),
          includeEditableDocx: includeEditableDocx.value,
        },
        sourceArtifact: uploadedSource.value ?? undefined,
        preflight: cachedPreflight.value ?? undefined,
        operationId: operationId.value || undefined,
        onStage: stage => state.value = stage,
        onSource: source => uploadedSource.value = source,
        onPreflight: preflight => cachedPreflight.value = preflight,
        onOperationId: value => operationId.value = value,
      })
      currentJob.value = created.job
      resultSummary.value = [
        `${created.preflight.page_count} 页`,
        created.preflight.scanned_pages
          ? `预检发现 ${created.preflight.scanned_pages} 个扫描页`
          : created.preflight.warnings.some(item => item.includes('仅分类前'))
            ? '预检页含原生文本'
            : '原生文档',
      ]
      state.value = mapJobState(created.job)
      await pollDocumentJob()
      return
    }

    state.value = 'RUNNING'
    if (props.toolId === 'pdf-to-excel') {
      const result = await sharedToolsApi.convertPdfToExcel(file)
      resultBlob.value = result.blob
      resultFileName.value = result.fileName
      resultSummary.value = [
        `${result.metrics.pageCount} 页`,
        `${result.metrics.tableCount} 个表格`,
        `${result.metrics.ocrPageCount} 个 OCR 页`,
      ]
    }
    else if (props.toolId === 'pdf-to-word') {
      const result = await sharedToolsApi.convertPdfToWord(file)
      resultBlob.value = result.blob
      resultFileName.value = result.fileName
      resultSummary.value = [
        `${result.metrics.pageCount} 页`,
        `${result.metrics.imageCount} 张图片`,
        `${result.metrics.ocrPageCount} 个 OCR 页`,
      ]
    }
    else if (props.toolId === 'pdf-split') {
      const result = await sharedToolsApi.splitPdf(file, {
        mode: splitMode.value,
        pageRanges: pageRanges.value,
      })
      resultBlob.value = result.blob
      resultFileName.value = result.fileName
      resultSummary.value = [`${result.pageCount} 页`, `${result.fileCount} 个输出文件`]
    }

    if (!resultBlob.value) throw new Error('当前工具尚未接入处理器。')
    downloadToolBlob(resultBlob.value, resultFileName.value)
    state.value = 'COMPLETED'
    await advanceBatch()
  }
  catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '文档处理失败，请稍后重试。'
    state.value = 'FAILED'
  }
}

function mapJobState(job: DocumentJob): DocumentWorkspaceState {
  if (job.state === 'CREATED') return 'READY'
  return job.state
}

async function completeDocumentJob(job: DocumentJob) {
  if (!job.task_id) throw new Error('Document Job 缺少任务标识。')
  const result = await getDocumentJobResult(job.task_id)
  const blob = await downloadDocumentJobResult(result)
  resultBlob.value = blob
  resultFileName.value = result.filename
  if (job.quality_report) {
    resultSummary.value = [
      `${job.quality_report.page_count} 页`,
      `质量置信度 ${Math.round(job.quality_report.overall_confidence * 100)}%`,
      `${job.quality_report.table_count} 个表格`,
      `${job.quality_report.ocr_page_count} 个 OCR 页`,
    ]
  }
  if (result.mime_type === 'application/pdf') {
    if (resultPreviewUrl.value) URL.revokeObjectURL(resultPreviewUrl.value)
    resultPreviewUrl.value = URL.createObjectURL(blob)
    previewPane.value = 'result'
  }
  downloadToolBlob(blob, result.filename)
  state.value = 'COMPLETED'
  await advanceBatch()
}

async function advanceBatch() {
  if (!batchRunning.value) return
  batchCompleted.value += 1
  const next = batchQueue.value.shift()
  if (!next) {
    batchRunning.value = false
    return
  }
  selectFile(next)
  await nextTick()
  await runConversion()
}

async function pollDocumentJob() {
  stopPolling()
  const taskId = currentJob.value?.task_id
  if (!taskId) return
  try {
    const job = await getDocumentJob(taskId)
    currentJob.value = job
    state.value = mapJobState(job)
    if (job.state === 'COMPLETED') {
      await completeDocumentJob(job)
      return
    }
    if (['FAILED', 'CANCELLED', 'EXPIRED', 'REVIEW_REQUIRED'].includes(job.state)) {
      if (job.state === 'FAILED') {
        errorMessage.value = job.failure_code
          ? `处理失败（${job.failure_code}）。`
          : '文档任务处理失败。'
      }
      return
    }
    pollTimer = setTimeout(() => void pollDocumentJob(), 1_500)
  }
  catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '读取文档任务状态失败。'
    state.value = 'FAILED'
  }
}

async function resumeAfterReview(job: DocumentJob) {
  currentJob.value = job
  state.value = mapJobState(job)
  errorMessage.value = ''
  await pollDocumentJob()
}

function handleReviewError(message: string) {
  errorMessage.value = message
}

async function cancelCurrentJob() {
  if (!currentJob.value) return
  try {
    currentJob.value = await cancelDocumentJob(currentJob.value)
    state.value = mapJobState(currentJob.value)
    stopPolling()
    if (currentJob.value.state !== 'CANCELLED') {
      pollTimer = setTimeout(() => void pollDocumentJob(), 1_000)
    }
  }
  catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '取消文档任务失败。'
  }
}

function downloadAgain() {
  if (resultBlob.value) downloadToolBlob(resultBlob.value, resultFileName.value)
}

watch(() => props.toolId, resetWorkspace)
watch(processingMode, () => {
  cachedPreflight.value = null
})
watch(settingsPreset, applySettingsPreset)
watch(() => props.factoryId, async () => {
  resetWorkspace()
  try {
    jobCapabilities.value = await getDocumentJobCapabilities(props.factoryId)
  }
  catch {
    jobCapabilities.value = null
  }
})
onMounted(async () => {
  try {
    jobCapabilities.value = await getDocumentJobCapabilities(props.factoryId)
  }
  catch {
    jobCapabilities.value = null
  }
})
onBeforeUnmount(() => {
  stopPolling()
  clearPreviewUrl()
})
</script>

<template>
  <div class="min-h-[600px] bg-slate-50/70">
    <div v-if="errorMessage && state === 'FAILED' && !selectedFile" class="mx-5 mt-5 flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
      <AlertCircle class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span>{{ errorMessage }}</span>
      <button type="button" class="ml-auto rounded p-1 hover:bg-rose-100" aria-label="关闭错误" @click="errorMessage = ''; state = 'EMPTY'">
        <X class="size-3.5" aria-hidden="true" />
      </button>
    </div>

    <div v-if="toolId === 'pdf-translation' && showOfficeTranslation" class="p-5 sm:p-6">
      <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p class="text-xs font-bold uppercase tracking-[0.14em] text-teal-700">现有兼容能力</p>
          <h2 class="mt-1 text-lg font-semibold text-slate-950">Excel / Word 文档翻译</h2>
        </div>
        <Button variant="outline" @click="showOfficeTranslation = false">
          返回 PDF 翻译
        </Button>
      </div>
      <DocumentTranslationTool :context-label="contextLabel" :factory-id="factoryId" />
    </div>

    <div v-else-if="!selectedFile" class="grid xl:grid-cols-[minmax(0,1fr)_288px]">
      <DocumentDropzone
        :tool="workspaceTool"
        @select="selectFiles"
        @error="showValidationError"
      />
      <aside class="hidden border-l border-slate-200 bg-white xl:block" aria-label="最近文档任务">
        <div class="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div>
            <p class="text-xs font-bold uppercase tracking-[0.12em] text-slate-400">Recent jobs</p>
            <h2 class="mt-1 text-sm font-semibold text-slate-900">最近任务</h2>
          </div>
          <History class="size-4 text-teal-700" aria-hidden="true" />
        </div>
        <div class="flex min-h-[330px] items-center justify-center px-6 text-center">
          <div>
            <span class="mx-auto flex size-11 items-center justify-center rounded-xl bg-slate-100 text-slate-500">
              <History class="size-4.5" aria-hidden="true" />
            </span>
            <p class="mt-3 text-xs font-semibold text-slate-800">
              {{ taskRuntimeAvailable ? '暂无任务记录' : '暂无持久化记录' }}
            </p>
            <p class="mt-1.5 text-[11px] leading-5 text-slate-500">
              {{ taskRuntimeAvailable
                ? '启动文档任务后，持久化进度与结果会在任务记录中显示。'
                : '当前同步转换不会伪造任务；受控 Job 开放后在这里显示。' }}
            </p>
          </div>
        </div>
        <div class="mx-4 rounded-xl border border-slate-200 bg-slate-50 p-3 text-[11px] leading-5 text-slate-500">
          <strong class="font-semibold text-slate-700">安全边界</strong>
          <p class="mt-1">源文件只读；结果另存。AI 增强与云 OCR 默认关闭。</p>
        </div>
      </aside>
    </div>

    <div v-if="!selectedFile && !effectiveToolAvailable && !(toolId === 'pdf-translation' && showOfficeTranslation)" class="mx-auto -mt-20 flex max-w-3xl flex-col items-center px-6 pb-12 text-center">
      <div class="flex items-center gap-2 rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-800">
        <Info class="size-3.5" aria-hidden="true" />
        新任务链路默认关闭，当前未开放提交
      </div>
      <Button
        v-if="toolId === 'pdf-translation'"
        class="mt-3"
        variant="outline"
        @click="showOfficeTranslation = true"
      >
        继续使用现有 Excel / Word 翻译
        <ChevronRight class="size-4" aria-hidden="true" />
      </Button>
    </div>

    <template v-else-if="selectedFile">
      <header class="flex flex-wrap items-center gap-3 border-b border-slate-200 bg-white px-4 py-3 sm:px-5">
        <span class="flex size-9 items-center justify-center rounded-lg bg-rose-50 text-rose-700 ring-1 ring-rose-100">
          <FileText class="size-4.5" aria-hidden="true" />
        </span>
        <div class="min-w-0 flex-1">
          <p class="truncate text-sm font-semibold text-slate-900">{{ selectedFile.name }}</p>
          <p class="mt-0.5 text-xs text-slate-500">{{ humanFileSize(selectedFile.size) }} · 源文件只读</p>
          <p v-if="batchTotal > 1" class="mt-0.5 text-[11px] font-medium text-teal-700">
            批量队列 {{ Math.min(batchCompleted + 1, batchTotal) }} / {{ batchTotal }}
          </p>
        </div>
        <span
          aria-live="polite"
          class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold"
          :class="state === 'COMPLETED'
            ? 'bg-emerald-50 text-emerald-700'
            : state === 'FAILED' || state === 'EXPIRED'
              ? 'bg-rose-50 text-rose-700'
              : state === 'REVIEW_REQUIRED'
                ? 'bg-amber-50 text-amber-800'
                : isBusy
                ? 'bg-sky-50 text-sky-700'
                : 'bg-slate-100 text-slate-600'"
        >
          <LoaderCircle v-if="isBusy" class="size-3.5 animate-spin" aria-hidden="true" />
          <CheckCircle2 v-else-if="state === 'COMPLETED'" class="size-3.5" aria-hidden="true" />
          {{ stateLabel }}
        </span>
        <Button variant="ghost" size="icon" aria-label="移除文件" :disabled="isBusy" @click="resetWorkspace">
          <X class="size-4" aria-hidden="true" />
        </Button>
      </header>

      <div class="grid min-h-[535px] xl:grid-cols-[minmax(0,1fr)_336px]">
        <main class="min-w-0 border-b border-slate-200 bg-slate-100/70 p-4 xl:border-b-0 xl:border-r sm:p-5" aria-label="源文档预览">
          <DocumentReviewPanel
            v-if="state === 'REVIEW_REQUIRED' && currentJob"
            :job="currentJob"
            @completed="resumeAfterReview"
            @error="handleReviewError"
          />
          <div v-else class="flex h-full min-h-[470px] flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <div class="flex items-center justify-between border-b border-slate-200 px-4 py-2.5">
              <div class="flex items-center gap-2 text-xs font-semibold text-slate-700">
                <FileCheck2 class="size-4 text-teal-700" aria-hidden="true" />
                {{ previewPane === 'result' ? '结果预览' : '源文档预览' }}
              </div>
              <div class="flex items-center gap-1">
                <button v-if="resultPreviewUrl" type="button" class="rounded px-2 py-1 text-[11px] font-semibold" :class="previewPane === 'source' ? 'bg-slate-100 text-slate-700' : 'text-slate-400'" @click="previewPane = 'source'">源文件</button>
                <button v-if="resultPreviewUrl" type="button" class="rounded px-2 py-1 text-[11px] font-semibold" :class="previewPane === 'result' ? 'bg-teal-50 text-teal-800' : 'text-slate-400'" @click="previewPane = 'result'">派生结果</button>
                <span v-else class="text-[11px] text-slate-400">浏览器本地预览，不代表提取结果</span>
              </div>
            </div>
            <object
              v-if="previewPane === 'result' && resultPreviewUrl"
              :data="`${resultPreviewUrl}#toolbar=0&navpanes=0`"
              type="application/pdf"
              class="min-h-[430px] flex-1 bg-slate-100"
              aria-label="PDF 派生结果预览"
            />
            <object
              v-else-if="isPdf"
              :data="`${previewUrl}#toolbar=0&navpanes=0`"
              type="application/pdf"
              class="min-h-[430px] flex-1 bg-slate-100"
              aria-label="PDF 源文件预览"
            >
              <div class="grid h-full min-h-[430px] place-items-center p-8 text-center text-sm text-slate-500">
                当前浏览器无法内嵌预览 PDF，但仍可执行转换。
              </div>
            </object>
            <div v-else class="grid min-h-[430px] flex-1 place-items-center p-8 text-center">
              <div>
                <span class="mx-auto flex size-16 items-center justify-center rounded-2xl bg-blue-50 text-blue-700 ring-1 ring-blue-100">
                  <FileText class="size-7" aria-hidden="true" />
                </span>
                <p class="mt-4 text-sm font-semibold text-slate-900">Word 源文件已选择</p>
                <p class="mt-1 text-xs text-slate-500">浏览器不直接渲染 DOCX；服务器预检接入后提供结构预览。</p>
              </div>
            </div>
          </div>
        </main>

        <aside class="bg-white" aria-label="处理设置">
          <div class="flex items-center gap-2 border-b border-slate-200 px-5 py-4">
            <Settings2 class="size-4 text-teal-700" aria-hidden="true" />
            <h2 class="text-sm font-semibold text-slate-950">处理设置</h2>
          </div>
          <div class="space-y-5 p-5">
            <label class="block text-xs font-semibold text-slate-700">
              常用配置模板
              <select v-model="settingsPreset" class="mt-2 h-9 w-full rounded-lg border border-slate-300 bg-white px-2 text-xs">
                <option value="STANDARD">标准保守</option>
                <option value="DATA_TABLE">数据表增强</option>
                <option value="LAYOUT">版式保真</option>
                <option value="BILINGUAL">双语交付</option>
              </select>
            </label>
            <div>
              <p class="text-xs font-semibold text-slate-700">处理模式</p>
              <div class="mt-2 rounded-xl border border-teal-200 bg-teal-50 p-3">
                <div class="flex items-center gap-2 text-sm font-semibold text-teal-900">
                  <LockKeyhole class="size-4" aria-hidden="true" />
                  {{ taskRuntimeAvailable ? '可恢复文档任务' : '本地确定性处理' }}
                </div>
                <p class="mt-1.5 text-xs leading-5 text-teal-800/80">
                  {{ taskRuntimeAvailable
                    ? `源文件进入受控 Artifact，固定 Task 步骤生成派生结果；云 OCR ${jobCapabilities?.cloud_ocr_available ? '可选且需明确同意' : '未配置'}。`
                    : 'Document Job 未开放时沿用现有同步接口；AI 增强与云 OCR 保持关闭。' }}
                </p>
              </div>
            </div>

            <div v-if="taskRuntimeAvailable">
              <p class="text-xs font-semibold text-slate-700">数据处理边界</p>
              <div class="mt-2 grid grid-cols-2 gap-2">
                <button
                  type="button"
                  class="rounded-lg border px-3 py-2 text-xs font-semibold"
                  :class="processingMode === 'LOCAL_PRIVATE' ? 'border-teal-300 bg-teal-50 text-teal-800' : 'border-slate-200 text-slate-600'"
                  @click="processingMode = 'LOCAL_PRIVATE'; cloudConsentAccepted = false"
                >
                  本地私密
                </button>
                <button
                  type="button"
                  class="rounded-lg border px-3 py-2 text-xs font-semibold"
                  :class="processingMode === 'AI_ENHANCED' ? 'border-teal-300 bg-teal-50 text-teal-800' : 'border-slate-200 text-slate-600'"
                  :disabled="!jobCapabilities?.cloud_ocr_available"
                  @click="processingMode = 'AI_ENHANCED'"
                >
                  AI 增强{{ jobCapabilities?.cloud_ocr_available ? '' : '（未配置）' }}
                </button>
              </div>
              <label v-if="processingMode === 'AI_ENHANCED'" class="mt-2 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-[11px] leading-5 text-amber-900">
                <input v-model="cloudConsentAccepted" type="checkbox" class="mt-1">
                <span>我同意将需要增强识别的页面通过中国北京区域的 Qwen 文档解析服务处理；服务未就绪时保留本地结果并进入质量检查。</span>
              </label>
            </div>

            <div v-if="toolId === 'pdf-to-excel'">
              <label class="block text-xs font-semibold text-slate-700">
                工作表策略
                <select v-model="sheetStrategy" class="mt-2 h-9 w-full rounded-lg border border-slate-300 bg-white px-2 text-xs">
                  <option value="TABLE_PER_SHEET">每个表格一张表</option>
                  <option value="PAGE_PER_SHEET">每页一张表</option>
                  <option value="MERGE_SAME_SCHEMA">合并同结构表格</option>
                </select>
              </label>
              <label class="mt-3 block text-xs font-semibold text-slate-700">
                类型推断
                <select v-model="typeInference" class="mt-2 h-9 w-full rounded-lg border border-slate-300 bg-white px-2 text-xs">
                  <option value="CONSERVATIVE">保守（保留前导零）</option>
                  <option value="SMART">智能数字 / 日期</option>
                </select>
              </label>
            </div>

            <div v-if="toolId === 'pdf-to-word'">
              <p class="text-xs font-semibold text-slate-700">输出模式</p>
              <div class="mt-2 grid grid-cols-2 gap-2">
                <button type="button" class="rounded-lg border px-2 py-2 text-xs font-semibold" :class="wordMode === 'EDITABLE' ? 'border-teal-300 bg-teal-50 text-teal-800' : 'border-slate-200 text-slate-600'" @click="wordMode = 'EDITABLE'">可编辑</button>
                <button type="button" class="rounded-lg border px-2 py-2 text-xs font-semibold" :class="wordMode === 'LAYOUT_PRESERVING' ? 'border-teal-300 bg-teal-50 text-teal-800' : 'border-slate-200 text-slate-600'" @click="wordMode = 'LAYOUT_PRESERVING'">版式保真</button>
              </div>
            </div>

            <div v-if="toolId === 'pdf-translation'" class="space-y-3">
              <label class="block text-xs font-semibold text-slate-700">
                翻译方向
                <select v-model="translationDirection" class="mt-2 h-9 w-full rounded-lg border border-slate-300 bg-white px-2 text-xs">
                  <option value="AUTO">自动识别</option>
                  <option value="ZH_TO_EN">中文 → 英文</option>
                  <option value="EN_TO_ZH">英文 → 中文</option>
                </select>
              </label>
              <label class="block text-xs font-semibold text-slate-700">
                输出版式
                <select v-model="translationLayout" class="mt-2 h-9 w-full rounded-lg border border-slate-300 bg-white px-2 text-xs">
                  <option value="TRANSLATED_ONLY">仅译文</option>
                  <option value="SIDE_BY_SIDE">左右对照</option>
                  <option value="STACKED">上下对照</option>
                </select>
              </label>
              <label class="block text-xs font-semibold text-slate-700">
                额外保护词（逗号或换行分隔）
                <textarea v-model="protectedTokens" class="mt-2 min-h-16 w-full rounded-lg border border-slate-300 p-2 text-xs" placeholder="料号、型号、专有名词" />
              </label>
              <label class="flex items-center gap-2 text-xs text-slate-700">
                <input v-model="includeEditableDocx" type="checkbox">
                同时输出可编辑 DOCX（ZIP）
              </label>
            </div>

            <div v-if="toolId === 'pdf-split'">
              <p class="text-xs font-semibold text-slate-700">拆分方式</p>
              <div class="mt-2 grid grid-cols-2 gap-2">
                <button
                  type="button"
                  class="rounded-lg border px-3 py-2 text-xs font-semibold"
                  :class="splitMode === 'each_page' ? 'border-teal-300 bg-teal-50 text-teal-800' : 'border-slate-200 text-slate-600'"
                  @click="splitMode = 'each_page'"
                >
                  每页一个文件
                </button>
                <button
                  type="button"
                  class="rounded-lg border px-3 py-2 text-xs font-semibold"
                  :class="splitMode === 'ranges' ? 'border-teal-300 bg-teal-50 text-teal-800' : 'border-slate-200 text-slate-600'"
                  @click="splitMode = 'ranges'"
                >
                  指定页段
                </button>
              </div>
              <label v-if="splitMode === 'ranges'" class="mt-3 block text-xs font-medium text-slate-600">
                页段
                <input
                  v-model="pageRanges"
                  type="text"
                  class="mt-1.5 h-9 w-full rounded-lg border border-slate-300 px-3 text-sm outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100"
                  placeholder="例如 1-3,5,8-10"
                >
              </label>
            </div>

            <div class="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs leading-5 text-slate-600">
              <strong class="font-semibold text-slate-800">兼容边界</strong>
              <p class="mt-1">
                {{ taskRuntimeAvailable
                  ? '任务复用现有 AI Task / Artifact；结果下载时重新鉴权，源文件保持不变。'
                  : '当前操作完成后直接下载新文件，不写入虚构任务历史。' }}
              </p>
            </div>

            <div v-if="errorMessage" class="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs leading-5 text-rose-800" role="alert">
              <AlertCircle class="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
              {{ errorMessage }}
            </div>

            <div v-if="state === 'COMPLETED'" class="rounded-xl border border-emerald-200 bg-emerald-50 p-3">
              <div class="flex items-center gap-2 text-sm font-semibold text-emerald-800">
                <CheckCircle2 class="size-4" aria-hidden="true" />
                结果已生成
              </div>
              <p class="mt-1 truncate text-xs text-emerald-700">{{ resultFileName }}</p>
              <div class="mt-2 flex flex-wrap gap-1.5">
                <span v-for="item in resultSummary" :key="item" class="rounded bg-white/80 px-2 py-1 text-[11px] font-medium text-emerald-800">{{ item }}</span>
              </div>
              <Button class="mt-3 w-full" variant="outline" size="sm" @click="downloadAgain">
                <Download class="size-3.5" aria-hidden="true" />
                再次下载
              </Button>
            </div>
          </div>

          <div class="border-t border-slate-200 p-5">
            <Button
              v-if="currentJob && hasActiveJob"
              class="mb-2 w-full"
              variant="outline"
              :disabled="currentJob.state === 'CANCELLED'"
              @click="cancelCurrentJob"
            >
              取消任务
            </Button>
            <Button
              v-if="effectiveToolAvailable"
              class="w-full"
              size="lg"
              :disabled="!canStart"
              @click="runConversion"
            >
              <LoaderCircle v-if="isBusy" class="size-4 animate-spin" aria-hidden="true" />
              <RotateCcw v-else-if="state === 'FAILED'" class="size-4" aria-hidden="true" />
              {{ isBusy || hasActiveJob
                ? `${stateLabel}…`
                : state === 'FAILED'
                  ? '重新处理'
                  : batchTotal > 1
                    ? `开始批量处理（${batchTotal}）`
                    : '开始处理' }}
            </Button>
            <Button v-else class="w-full" size="lg" disabled>
              后续里程碑开放
            </Button>
          </div>
        </aside>
      </div>
    </template>
  </div>
</template>
