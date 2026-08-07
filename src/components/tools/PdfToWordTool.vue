<script setup lang="ts">
import {
  CheckCircle2,
  Download,
  FileText,
  LoaderCircle,
  ShieldCheck,
  Upload,
  X,
} from '@lucide/vue'
import { computed, ref } from 'vue'
import { sharedToolsApi, type PdfToWordMetrics } from '@/api/tools'
import { getApiErrorMessage } from '@/lib/http'
import { downloadToolBlob, formatPdfFileSize, validatePdfFile } from './pdfToolUtils'


const props = withDefaults(defineProps<{
  contextLabel?: string
}>(), {
  contextLabel: '全部厂区',
})

const fileInput = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)
const isDragging = ref(false)
const isConverting = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const conversionMetrics = ref<PdfToWordMetrics | null>(null)

const canConvert = computed(() => Boolean(selectedFile.value) && !isConverting.value)
const selectedFileSize = computed(() => selectedFile.value ? formatPdfFileSize(selectedFile.value.size) : '')

function resetResult() {
  errorMessage.value = ''
  successMessage.value = ''
  conversionMetrics.value = null
}

function selectFile(file: File | undefined) {
  resetResult()
  if (!file) return

  const error = validatePdfFile(file)
  if (error) {
    selectedFile.value = null
    errorMessage.value = error
    if (fileInput.value) fileInput.value.value = ''
    return
  }
  selectedFile.value = file
}

function handleFileChange(event: Event) {
  selectFile((event.target as HTMLInputElement).files?.[0])
}

function handleDrop(event: DragEvent) {
  isDragging.value = false
  selectFile(event.dataTransfer?.files?.[0])
}

function clearFile() {
  selectedFile.value = null
  resetResult()
  if (fileInput.value) fileInput.value.value = ''
}

async function convertFile() {
  if (!selectedFile.value || isConverting.value) return

  isConverting.value = true
  resetResult()
  try {
    const result = await sharedToolsApi.convertPdfToWord(selectedFile.value)
    downloadToolBlob(result.blob, result.fileName)
    conversionMetrics.value = result.metrics
    successMessage.value = `${result.fileName} 已生成并开始下载。`
  }
  catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  }
  finally {
    isConverting.value = false
  }
}
</script>

<template>
  <section class="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-[0_18px_50px_-32px_rgba(15,23,42,0.45)]" aria-labelledby="pdf-to-word-title">
    <div class="border-b border-slate-200/80 bg-gradient-to-r from-cyan-50/90 via-white to-teal-50/60 px-5 py-5 sm:px-7">
      <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div class="flex items-start gap-4">
          <span class="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-cyan-700 text-white shadow-lg shadow-cyan-900/15">
            <FileText class="size-6" aria-hidden="true" />
          </span>
          <div>
            <div class="flex flex-wrap items-center gap-2">
              <h2 id="pdf-to-word-title" class="text-xl font-bold tracking-tight text-slate-950">PDF 转 Word</h2>
              <span class="rounded-full bg-cyan-100 px-2.5 py-1 text-[11px] font-bold tracking-wide text-cyan-800">已启用</span>
            </div>
            <p class="mt-1.5 max-w-2xl text-sm leading-6 text-slate-600">提取 PDF 中的可编辑文字和表格并生成 Word；扫描页或异常字体会自动尝试本机 OCR。</p>
          </div>
        </div>
        <span class="inline-flex w-fit items-center gap-2 rounded-full border border-slate-200 bg-white/90 px-3 py-1.5 text-xs font-semibold text-slate-600 shadow-sm">
          <ShieldCheck class="size-3.5 text-cyan-700" aria-hidden="true" />
          {{ props.contextLabel }}可用
        </span>
      </div>
    </div>

    <div class="grid gap-0 lg:grid-cols-[minmax(0,1fr)_300px]">
      <div class="p-5 sm:p-7">
        <label
          class="group flex min-h-56 cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-8 text-center transition"
          :class="isDragging
            ? 'border-cyan-500 bg-cyan-50'
            : selectedFile
              ? 'border-cyan-300 bg-cyan-50/50'
              : 'border-slate-300 bg-slate-50/70 hover:border-cyan-400 hover:bg-cyan-50/45'"
          @dragenter.prevent="isDragging = true"
          @dragover.prevent="isDragging = true"
          @dragleave.prevent="isDragging = false"
          @drop.prevent="handleDrop"
        >
          <input ref="fileInput" type="file" class="sr-only" accept="application/pdf,.pdf" @change="handleFileChange">

          <template v-if="selectedFile">
            <span class="flex size-14 items-center justify-center rounded-2xl bg-white text-cyan-700 shadow-sm ring-1 ring-cyan-100">
              <FileText class="size-7" aria-hidden="true" />
            </span>
            <strong class="mt-4 max-w-full truncate text-base text-slate-950">{{ selectedFile.name }}</strong>
            <span class="mt-1 text-sm text-slate-500">{{ selectedFileSize }} · 点击可替换文件</span>
          </template>
          <template v-else>
            <span class="flex size-14 items-center justify-center rounded-2xl bg-white text-slate-500 shadow-sm ring-1 ring-slate-200 transition group-hover:text-cyan-700 group-hover:ring-cyan-200">
              <Upload class="size-7" aria-hidden="true" />
            </span>
            <strong class="mt-4 text-base text-slate-950">拖拽 PDF 到这里，或点击选择文件</strong>
            <span class="mt-1 text-sm text-slate-500">单个文件不超过 20MB，最多 80 页</span>
          </template>
        </label>

        <div class="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div class="min-h-6 text-sm">
            <p v-if="errorMessage" class="font-medium text-red-700" role="alert">{{ errorMessage }}</p>
            <div v-else-if="successMessage" class="text-emerald-700" role="status">
              <p class="flex items-start gap-2 font-medium"><CheckCircle2 class="mt-0.5 size-4 shrink-0" aria-hidden="true" />{{ successMessage }}</p>
              <p v-if="conversionMetrics" class="mt-1 pl-6 text-xs text-emerald-700/80">
                {{ conversionMetrics.pageCount }} 页 · {{ conversionMetrics.tableCount }} 个表格 · {{ conversionMetrics.textPageCount }} 个文字页<span v-if="conversionMetrics.ocrPageCount"> · {{ conversionMetrics.ocrPageCount }} 个 OCR 页</span>
              </p>
            </div>
            <p v-else class="text-slate-500">输出为可编辑 .docx；复杂版式和 OCR 内容建议对照原 PDF 复核。</p>
          </div>

          <div class="flex shrink-0 items-center gap-2">
            <button
              v-if="selectedFile"
              type="button"
              class="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 text-sm font-semibold text-slate-600 transition hover:border-slate-300 hover:bg-slate-50"
              :disabled="isConverting"
              @click="clearFile"
            >
              <X class="size-4" aria-hidden="true" />
              清除
            </button>
            <button
              type="button"
              class="inline-flex h-10 min-w-36 items-center justify-center gap-2 rounded-xl bg-cyan-700 px-5 text-sm font-semibold text-white shadow-sm transition hover:bg-cyan-800 disabled:cursor-not-allowed disabled:bg-slate-300"
              :disabled="!canConvert"
              @click="convertFile"
            >
              <LoaderCircle v-if="isConverting" class="size-4 animate-spin" aria-hidden="true" />
              <Download v-else class="size-4" aria-hidden="true" />
              {{ isConverting ? '正在转换…' : '转换并下载' }}
            </button>
          </div>
        </div>
      </div>

      <aside class="border-t border-slate-200/80 bg-slate-50/70 p-5 sm:p-7 lg:border-l lg:border-t-0" aria-label="转换说明">
        <p class="text-xs font-bold uppercase tracking-[0.14em] text-slate-400">转换流程</p>
        <ol class="mt-5 space-y-5">
          <li v-for="(step, index) in ['选择 PDF 文件', '提取文字与表格', '下载新的 Word']" :key="step" class="flex gap-3">
            <span class="flex size-7 shrink-0 items-center justify-center rounded-full bg-white text-xs font-bold text-cyan-700 shadow-sm ring-1 ring-slate-200">{{ index + 1 }}</span>
            <div>
              <strong class="text-sm text-slate-900">{{ step }}</strong>
              <p class="mt-1 text-xs leading-5 text-slate-500">
                {{ index === 0 ? '支持文字型和可 OCR 的扫描 PDF。' : index === 1 ? '按页面顺序写入段落和可编辑表格。' : '输出为 .docx，不覆盖源 PDF。' }}
              </p>
            </div>
          </li>
        </ol>

        <div class="mt-6 rounded-xl border border-cyan-100 bg-cyan-50/80 p-4">
          <p class="flex items-center gap-2 text-xs font-bold text-cyan-900"><ShieldCheck class="size-4" aria-hidden="true" />即时处理</p>
          <p class="mt-2 text-xs leading-5 text-cyan-800/80">文件仅用于本次转换，不保存 PDF、Word 或转换记录。</p>
        </div>
      </aside>
    </div>
  </section>
</template>
