<script setup lang="ts">
import {
  CheckCircle2,
  Download,
  FileSpreadsheet,
  FileText,
  LoaderCircle,
  ShieldCheck,
  Upload,
  X,
} from '@lucide/vue'
import { computed, ref } from 'vue'
import { sharedToolsApi, type PdfToExcelMetrics } from '@/api/tools'
import { getApiErrorMessage } from '@/lib/http'


const MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024

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
const conversionMetrics = ref<PdfToExcelMetrics | null>(null)

const canConvert = computed(() => Boolean(selectedFile.value) && !isConverting.value)
const selectedFileSize = computed(() => selectedFile.value ? formatFileSize(selectedFile.value.size) : '')

function formatFileSize(size: number) {
  if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function validatePdf(file: File) {
  if (!file.name.toLowerCase().endsWith('.pdf')) return '只支持上传 .pdf 文件。'
  if (file.type && file.type !== 'application/pdf') return '文件类型不是有效的 PDF。'
  if (file.size <= 0) return 'PDF 文件不能为空。'
  if (file.size > MAX_FILE_SIZE_BYTES) return '单个 PDF 不可超过 20MB。'
  return ''
}

function selectFile(file: File | undefined) {
  errorMessage.value = ''
  successMessage.value = ''
  conversionMetrics.value = null
  if (!file) return

  const error = validatePdf(file)
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
  errorMessage.value = ''
  successMessage.value = ''
  conversionMetrics.value = null
  if (fileInput.value) fileInput.value.value = ''
}

function downloadBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}

async function convertFile() {
  if (!selectedFile.value || isConverting.value) return

  isConverting.value = true
  errorMessage.value = ''
  successMessage.value = ''
  conversionMetrics.value = null
  try {
    const result = await sharedToolsApi.convertPdfToExcel(selectedFile.value)
    downloadBlob(result.blob, result.fileName)
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
  <section class="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-[0_18px_50px_-32px_rgba(15,23,42,0.45)]" aria-labelledby="pdf-to-excel-title">
    <div class="border-b border-slate-200/80 bg-gradient-to-r from-teal-50/90 via-white to-emerald-50/60 px-5 py-5 sm:px-7">
      <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div class="flex items-start gap-4">
          <span class="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-teal-700 text-white shadow-lg shadow-teal-900/15">
            <FileSpreadsheet class="size-6" aria-hidden="true" />
          </span>
          <div>
            <div class="flex flex-wrap items-center gap-2">
              <h2 id="pdf-to-excel-title" class="text-xl font-bold tracking-tight text-slate-950">PDF 转 Excel</h2>
              <span class="rounded-full bg-teal-100 px-2.5 py-1 text-[11px] font-bold tracking-wide text-teal-800">已启用</span>
            </div>
            <p class="mt-1.5 max-w-2xl text-sm leading-6 text-slate-600">标准表格转为数据表；订单、表单等版式页面按坐标还原，异常字体和扫描件会自动尝试本机 OCR。</p>
          </div>
        </div>
        <span class="inline-flex w-fit items-center gap-2 rounded-full border border-slate-200 bg-white/90 px-3 py-1.5 text-xs font-semibold text-slate-600 shadow-sm">
          <ShieldCheck class="size-3.5 text-teal-700" aria-hidden="true" />
          {{ props.contextLabel }}可用
        </span>
      </div>
    </div>

    <div class="grid gap-0 lg:grid-cols-[minmax(0,1fr)_300px]">
      <div class="p-5 sm:p-7">
        <label
          class="group flex min-h-56 cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-8 text-center transition"
          :class="isDragging
            ? 'border-teal-500 bg-teal-50 shadow-[inset_0_0_0_1px_rgba(13,148,136,0.08)]'
            : selectedFile
              ? 'border-teal-300 bg-teal-50/50'
              : 'border-slate-300 bg-slate-50/70 hover:border-teal-400 hover:bg-teal-50/45'"
          @dragenter.prevent="isDragging = true"
          @dragover.prevent="isDragging = true"
          @dragleave.prevent="isDragging = false"
          @drop.prevent="handleDrop"
        >
          <input ref="fileInput" type="file" class="sr-only" accept="application/pdf,.pdf" @change="handleFileChange">

          <template v-if="selectedFile">
            <span class="flex size-14 items-center justify-center rounded-2xl bg-white text-teal-700 shadow-sm ring-1 ring-teal-100">
              <FileText class="size-7" aria-hidden="true" />
            </span>
            <strong class="mt-4 max-w-full truncate text-base text-slate-950">{{ selectedFile.name }}</strong>
            <span class="mt-1 text-sm text-slate-500">{{ selectedFileSize }} · 点击可替换文件</span>
          </template>
          <template v-else>
            <span class="flex size-14 items-center justify-center rounded-2xl bg-white text-slate-500 shadow-sm ring-1 ring-slate-200 transition group-hover:text-teal-700 group-hover:ring-teal-200">
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
            <p v-else class="text-slate-500">所有内容按文本写入，物料号、订单号等前导零不会被自动删除。</p>
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
              class="inline-flex h-10 min-w-36 items-center justify-center gap-2 rounded-xl bg-teal-700 px-5 text-sm font-semibold text-white shadow-sm transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-slate-300"
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
          <li v-for="(step, index) in ['选择 PDF 文件', '识别表格与文字', '下载新的 Excel']" :key="step" class="flex gap-3">
            <span class="flex size-7 shrink-0 items-center justify-center rounded-full bg-white text-xs font-bold text-teal-700 shadow-sm ring-1 ring-slate-200">{{ index + 1 }}</span>
            <div>
              <strong class="text-sm text-slate-900">{{ step }}</strong>
              <p class="mt-1 text-xs leading-5 text-slate-500">
                {{ index === 0 ? '支持文字型、表格型和可 OCR 的扫描 PDF。' : index === 1 ? '自动区分数据表与版式页，并写入独立工作表。' : '输出为 .xlsx，不覆盖源 PDF。' }}
              </p>
            </div>
          </li>
        </ol>

        <div class="mt-6 rounded-xl border border-teal-100 bg-teal-50/80 p-4">
          <p class="flex items-center gap-2 text-xs font-bold text-teal-900"><ShieldCheck class="size-4" aria-hidden="true" />即时处理</p>
          <p class="mt-2 text-xs leading-5 text-teal-800/80">文件仅用于本次转换，不保存 PDF、Excel 或转换记录。</p>
        </div>
      </aside>
    </div>
  </section>
</template>
