<script setup lang="ts">
import {
  AlertCircle,
  CheckCircle2,
  Download,
  FileText,
  LoaderCircle,
  RotateCcw,
  Settings2,
  X,
} from '@lucide/vue'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  DocumentToolApiError,
  type DocumentProcessingMetadata,
  type DocumentProcessingMode,
  type DocumentToolsCapabilities,
} from '@/api/tools'
import { Button } from '@/components/ui/button'
import { downloadToolBlob } from '@/components/tools/pdfToolUtils'
import { getDocumentTool } from '../constants'
import { useDocumentToolRunner } from '../composables/useDocumentToolRunner'
import type { DocumentToolId, DocumentWorkspaceState } from '../types'
import DocumentDropzone from './DocumentDropzone.vue'
import PdfSplitPanel from './panels/PdfSplitPanel.vue'
import PdfToExcelPanel from './panels/PdfToExcelPanel.vue'
import PdfToWordPanel from './panels/PdfToWordPanel.vue'
import PdfTranslationPanel from './panels/PdfTranslationPanel.vue'
import WordToPdfPanel from './panels/WordToPdfPanel.vue'

const props = defineProps<{
  toolId: DocumentToolId
  factoryId: string
  contextLabel: string
  capabilities: DocumentToolsCapabilities | null
  capabilitiesError?: string
}>()

const selectedFile = ref<File | null>(null)
const sourcePreviewUrl = ref('')
const resultPreviewUrl = ref('')
const state = ref<DocumentWorkspaceState>('IDLE')
const processingMode = ref<DocumentProcessingMode>('AUTO')
const errorMessage = ref('')
const errorCode = ref('')
const errorAction = ref('')
const resultBlob = ref<Blob | null>(null)
const resultFileName = ref('')
const resultSummary = ref<string[]>([])
const resultProcessing = ref<DocumentProcessingMetadata | null>(null)
const splitMode = ref<'each_page' | 'ranges'>('each_page')
const pageRanges = ref('')
const translationDirection = ref<'AUTO' | 'ZH_TO_EN' | 'EN_TO_ZH'>('AUTO')
const translationLayout = ref<'TRANSLATED_ONLY' | 'SIDE_BY_SIDE' | 'STACKED'>('TRANSLATED_ONLY')
const includeEditableDocx = ref(false)
const protectedTokens = ref('')
const wordOutputMode = ref<'EDITABLE' | 'LAYOUT_PRESERVING'>('EDITABLE')
const glossaryText = ref('')
const translationMemoryText = ref('')
const domainPrompt = ref('')
const elapsedSeconds = ref(0)
let elapsedTimer: ReturnType<typeof setInterval> | null = null
const runner = useDocumentToolRunner()

const tool = computed(() => getDocumentTool(props.toolId))
const capability = computed(() => props.capabilities?.tools[props.toolId] ?? null)
const toolAvailable = computed(() => capability.value?.available === true)
const modeAvailable = computed(() => {
  if (props.toolId === 'word-to-pdf' || props.toolId === 'pdf-split') {
    return capability.value?.modes.AUTO.available === true
  }
  return capability.value?.modes[processingMode.value].available === true
})
const isBusy = computed(() => state.value === 'RUNNING')
const canStart = computed(() => Boolean(selectedFile.value && toolAvailable.value && modeAvailable.value && !isBusy.value))
const supportsModeSelection = computed(() => !['word-to-pdf', 'pdf-split'].includes(props.toolId))

function stopElapsedTimer() {
  if (elapsedTimer) clearInterval(elapsedTimer)
  elapsedTimer = null
}

function clearObjectUrls() {
  if (sourcePreviewUrl.value) URL.revokeObjectURL(sourcePreviewUrl.value)
  if (resultPreviewUrl.value) URL.revokeObjectURL(resultPreviewUrl.value)
  sourcePreviewUrl.value = ''
  resultPreviewUrl.value = ''
}

function clearResult() {
  if (resultPreviewUrl.value) URL.revokeObjectURL(resultPreviewUrl.value)
  resultPreviewUrl.value = ''
  resultBlob.value = null
  resultFileName.value = ''
  resultSummary.value = []
  resultProcessing.value = null
}

function clearError() {
  errorMessage.value = ''
  errorCode.value = ''
  errorAction.value = ''
}

function resetWorkspace() {
  runner.cancel()
  stopElapsedTimer()
  clearObjectUrls()
  selectedFile.value = null
  state.value = 'IDLE'
  processingMode.value = 'AUTO'
  clearError()
  resultBlob.value = null
  resultFileName.value = ''
  resultSummary.value = []
  resultProcessing.value = null
  splitMode.value = 'each_page'
  pageRanges.value = ''
  translationDirection.value = 'AUTO'
  translationLayout.value = 'TRANSLATED_ONLY'
  includeEditableDocx.value = false
  protectedTokens.value = ''
  wordOutputMode.value = 'EDITABLE'
  glossaryText.value = ''
  translationMemoryText.value = ''
  domainPrompt.value = ''
  elapsedSeconds.value = 0
}

function selectFiles(files: File[]) {
  const file = files[0]
  if (!file) return
  clearObjectUrls()
  clearResult()
  clearError()
  selectedFile.value = file
  if (file.name.toLowerCase().endsWith('.pdf')) {
    sourcePreviewUrl.value = URL.createObjectURL(file)
  }
  state.value = 'FILE_SELECTED'
}

function showValidationError(message: string) {
  errorMessage.value = message
  errorCode.value = 'DOCUMENT_FILE_INVALID'
  errorAction.value = '请重新选择符合格式和大小要求的文件。'
  state.value = 'ERROR'
}

function humanFileSize(bytes: number) {
  return bytes >= 1024 * 1024
    ? `${(bytes / 1024 / 1024).toFixed(1)} MB`
    : `${Math.max(1, Math.ceil(bytes / 1024))} KB`
}

function protectedTokenList() {
  return protectedTokens.value
    .split(/[\n,]/)
    .map(item => item.trim())
    .filter(Boolean)
}

function translationPairs(value: string, label: string) {
  return value.split('\n').map(line => line.trim()).filter(Boolean).map((line) => {
    const match = line.match(/^(.+?)(?:=>|=|→)(.+)$/)
    if (!match?.[1]?.trim() || !match[2]?.trim()) {
      throw new DocumentToolApiError(
        `${label}格式不正确。`,
        'DOCUMENT_TRANSLATION_OPTIONS_INVALID',
        `请按“源文 => 译文”格式填写${label}，每行一组。`,
      )
    }
    return { source: match[1].trim(), target: match[2].trim() }
  })
}

async function runConversion() {
  const file = selectedFile.value
  if (!file || !canStart.value) return
  if (props.toolId === 'pdf-split' && splitMode.value === 'ranges' && !pageRanges.value.trim()) {
    showValidationError('请输入页段，例如 1-3,5,8-10。')
    return
  }

  clearError()
  clearResult()
  state.value = 'RUNNING'
  elapsedSeconds.value = 0
  elapsedTimer = setInterval(() => elapsedSeconds.value += 1, 1000)

  try {
    const result = await runner.run({
      toolId: props.toolId,
      file,
      processingMode: processingMode.value,
      splitMode: splitMode.value,
      pageRanges: pageRanges.value,
      translationDirection: translationDirection.value,
      translationLayout: translationLayout.value,
      protectedTokens: protectedTokenList(),
      includeEditableDocx: includeEditableDocx.value,
      wordOutputMode: wordOutputMode.value,
      glossary: translationPairs(glossaryText.value, '术语表'),
      translationMemory: translationPairs(translationMemoryText.value, '翻译记忆'),
      domainPrompt: domainPrompt.value,
    })
    resultBlob.value = result.blob
    resultFileName.value = result.fileName
    resultProcessing.value = result.processing
    resultSummary.value = result.summary

    if (!resultBlob.value) throw new Error('服务器没有返回结果文件。')
    if (resultBlob.value.type === 'application/pdf') resultPreviewUrl.value = URL.createObjectURL(resultBlob.value)
    state.value = 'SUCCESS'
  }
  catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      errorMessage.value = '本次处理已取消。'
      errorCode.value = 'DOCUMENT_REQUEST_CANCELLED'
      errorAction.value = '可调整设置后重新处理。'
    }
    else if (error instanceof DocumentToolApiError) {
      errorMessage.value = error.message
      errorCode.value = error.code
      errorAction.value = error.action
    }
    else {
      errorMessage.value = error instanceof Error ? error.message : '文档处理失败，请稍后重试。'
      errorCode.value = 'DOCUMENT_TOOL_FAILED'
      errorAction.value = '请重试；若持续失败，请联系管理员并提供错误码。'
    }
    state.value = 'ERROR'
  }
  finally {
    stopElapsedTimer()
  }
}

function cancelConversion() {
  runner.cancel()
}

function downloadResult() {
  if (resultBlob.value) downloadToolBlob(resultBlob.value, resultFileName.value)
}

watch(() => props.toolId, resetWorkspace)
watch(capability, (value) => {
  if (!value || !supportsModeSelection.value || value.modes[processingMode.value].available) return
  const fallback = (['AUTO', 'LOCAL'] as const).find(mode => value.modes[mode].available)
  if (fallback) processingMode.value = fallback
}, { immediate: true })
onBeforeUnmount(resetWorkspace)
</script>

<template>
  <div class="bg-slate-50/70">
    <div v-if="!capabilities && !capabilitiesError" class="grid min-h-[320px] place-items-center text-sm text-slate-500">
      <div class="flex items-center gap-2">
        <LoaderCircle class="size-4 animate-spin" aria-hidden="true" />
        正在读取服务器能力…
      </div>
    </div>

    <div v-else-if="capabilitiesError" class="mx-auto max-w-2xl px-6 py-16 text-center">
      <AlertCircle class="mx-auto size-8 text-rose-500" aria-hidden="true" />
      <h2 class="mt-3 text-base font-semibold text-slate-950">无法读取工具能力</h2>
      <p class="mt-2 text-sm text-slate-600">{{ capabilitiesError }}</p>
      <p class="mt-2 font-mono text-xs text-rose-600">DOCUMENT_CAPABILITIES_UNAVAILABLE</p>
    </div>

    <div v-else-if="!toolAvailable" class="mx-auto max-w-2xl px-6 py-16 text-center">
      <AlertCircle class="mx-auto size-8 text-amber-500" aria-hidden="true" />
      <h2 class="mt-3 text-base font-semibold text-slate-950">{{ tool.label }}当前不可用</h2>
      <p class="mt-2 text-sm text-slate-600">{{ capability?.reason }}</p>
      <p v-if="capability?.reason_code" class="mt-2 font-mono text-xs text-amber-700">{{ capability.reason_code }}</p>
    </div>

    <DocumentDropzone v-else-if="!selectedFile" :tool="tool" @select="selectFiles" @error="showValidationError" />

    <div v-else class="grid lg:grid-cols-[minmax(0,1fr)_340px]">
      <main class="min-w-0 border-b border-slate-200 p-5 sm:p-6 lg:border-b-0 lg:border-r">
        <div class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-4">
          <div class="flex min-w-0 items-center gap-3">
            <span class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-teal-50 text-teal-700"><FileText class="size-5" aria-hidden="true" /></span>
            <div class="min-w-0">
              <p class="truncate text-sm font-semibold text-slate-950">{{ selectedFile.name }}</p>
              <p class="mt-0.5 text-xs text-slate-500">{{ humanFileSize(selectedFile.size) }} · {{ contextLabel }}</p>
            </div>
          </div>
          <Button variant="ghost" size="sm" :disabled="isBusy" @click="resetWorkspace"><X class="size-4" aria-hidden="true" />更换文件</Button>
        </div>

        <div v-if="state === 'RUNNING'" class="mt-5 rounded-xl border border-teal-200 bg-teal-50 p-5">
          <div class="flex items-center gap-3 text-sm font-semibold text-teal-900"><LoaderCircle class="size-5 animate-spin" aria-hidden="true" />正在处理{{ elapsedSeconds ? ` · 已用时 ${elapsedSeconds} 秒` : '' }}</div>
          <p class="mt-2 text-xs leading-5 text-teal-800/80">服务器正在解析文档并生成新文件；同步接口不伪造处理百分比。</p>
          <Button class="mt-4" variant="outline" size="sm" @click="cancelConversion">取消当前请求</Button>
        </div>

        <div v-else-if="state === 'SUCCESS'" class="mt-5 rounded-xl border border-emerald-200 bg-emerald-50 p-5">
          <div class="flex items-center gap-2 text-base font-semibold text-emerald-900"><CheckCircle2 class="size-5" aria-hidden="true" />转换完成</div>
          <p class="mt-2 break-all text-sm font-medium text-emerald-900">{{ resultFileName }}</p>
          <div class="mt-3 flex flex-wrap gap-2"><span v-for="item in resultSummary" :key="item" class="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-emerald-800">{{ item }}</span></div>
          <div v-if="resultProcessing?.warnings.length" class="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-900"><p v-for="warning in resultProcessing.warnings" :key="warning">{{ warning }}</p></div>
          <div class="mt-4 flex flex-wrap gap-2">
            <Button @click="downloadResult"><Download class="size-4" aria-hidden="true" />下载结果</Button>
            <Button variant="outline" @click="runConversion"><RotateCcw class="size-4" aria-hidden="true" />重新处理</Button>
          </div>
        </div>

        <div v-else-if="state === 'ERROR'" class="mt-5 rounded-xl border border-rose-200 bg-rose-50 p-5" role="alert">
          <div class="flex items-center gap-2 text-sm font-semibold text-rose-900"><AlertCircle class="size-5" aria-hidden="true" />{{ errorMessage }}</div>
          <p v-if="errorCode" class="mt-2 font-mono text-xs text-rose-700">{{ errorCode }}</p>
          <p v-if="errorAction" class="mt-2 text-xs leading-5 text-rose-800">解决办法：{{ errorAction }}</p>
        </div>

        <iframe v-if="resultPreviewUrl || sourcePreviewUrl" class="mt-5 h-[430px] w-full rounded-xl border border-slate-200 bg-white" :src="resultPreviewUrl || sourcePreviewUrl" title="文档预览" />
      </main>

      <aside class="bg-white" aria-label="处理设置">
        <div class="flex items-center gap-2 border-b border-slate-200 px-5 py-4"><Settings2 class="size-4 text-teal-700" aria-hidden="true" /><h2 class="text-sm font-semibold text-slate-950">处理设置</h2></div>
        <div class="space-y-5 p-5">
          <PdfToExcelPanel v-if="toolId === 'pdf-to-excel'" v-model:mode="processingMode" :capability="capability" :disabled="isBusy" />
          <PdfToWordPanel v-else-if="toolId === 'pdf-to-word'" v-model:mode="processingMode" v-model:output-mode="wordOutputMode" :capability="capability" :disabled="isBusy" />
          <WordToPdfPanel v-else-if="toolId === 'word-to-pdf'" />
          <PdfTranslationPanel
            v-else-if="toolId === 'pdf-translation'"
            v-model:mode="processingMode"
            v-model:direction="translationDirection"
            v-model:layout="translationLayout"
            v-model:protected-tokens="protectedTokens"
            v-model:include-editable-docx="includeEditableDocx"
            v-model:glossary-text="glossaryText"
            v-model:translation-memory-text="translationMemoryText"
            v-model:domain-prompt="domainPrompt"
            :capability="capability"
            :disabled="isBusy"
          />
          <PdfSplitPanel v-else v-model:mode="splitMode" v-model:page-ranges="pageRanges" :disabled="isBusy" />

          <div class="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs leading-5 text-slate-600"><strong class="font-semibold text-slate-800">运行边界</strong><p class="mt-1">转换只调用服务器本地工具，不创建外部任务，也不把文档内容发送到第三方服务。</p></div>
        </div>

        <div class="border-t border-slate-200 p-5"><Button class="w-full" size="lg" :disabled="!canStart" @click="runConversion"><LoaderCircle v-if="isBusy" class="size-4 animate-spin" aria-hidden="true" /><RotateCcw v-else-if="state === 'ERROR'" class="size-4" aria-hidden="true" />{{ isBusy ? '处理中…' : state === 'ERROR' ? '重新处理' : '开始处理' }}</Button></div>
      </aside>
    </div>
  </div>
</template>
