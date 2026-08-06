<script setup lang="ts">
import {
  Archive,
  CheckCircle2,
  Download,
  FileText,
  LoaderCircle,
  Scissors,
  ShieldCheck,
  Upload,
  X,
} from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { sharedToolsApi, type PdfSplitOptions } from '@/api/tools'
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
const isSplitting = ref(false)
const splitMode = ref<PdfSplitOptions['mode']>('each_page')
const pageRanges = ref('')
const errorMessage = ref('')
const successMessage = ref('')
const resultSummary = ref<{ pageCount: number; fileCount: number } | null>(null)

const selectedFileSize = computed(() => selectedFile.value ? formatPdfFileSize(selectedFile.value.size) : '')
const canSplit = computed(() => Boolean(selectedFile.value)
  && !isSplitting.value
  && (splitMode.value === 'each_page' || Boolean(pageRanges.value.trim())))

function resetResult() {
  errorMessage.value = ''
  successMessage.value = ''
  resultSummary.value = null
}

watch([splitMode, pageRanges], resetResult)

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

async function splitFile() {
  if (!selectedFile.value || !canSplit.value) return

  isSplitting.value = true
  resetResult()
  try {
    const result = await sharedToolsApi.splitPdf(selectedFile.value, {
      mode: splitMode.value,
      pageRanges: pageRanges.value,
    })
    downloadToolBlob(result.blob, result.fileName)
    resultSummary.value = { pageCount: result.pageCount, fileCount: result.fileCount }
    successMessage.value = `${result.fileName} 已生成并开始下载。`
  }
  catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  }
  finally {
    isSplitting.value = false
  }
}
</script>

<template>
  <section class="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-[0_18px_50px_-32px_rgba(15,23,42,0.45)]" aria-labelledby="pdf-split-title">
    <div class="border-b border-slate-200/80 bg-gradient-to-r from-amber-50/90 via-white to-orange-50/60 px-5 py-5 sm:px-7">
      <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div class="flex items-start gap-4">
          <span class="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-amber-600 text-white shadow-lg shadow-amber-900/15">
            <Scissors class="size-6" aria-hidden="true" />
          </span>
          <div>
            <div class="flex flex-wrap items-center gap-2">
              <h2 id="pdf-split-title" class="text-xl font-bold tracking-tight text-slate-950">PDF 拆分</h2>
              <span class="rounded-full bg-amber-100 px-2.5 py-1 text-[11px] font-bold tracking-wide text-amber-800">已启用</span>
            </div>
            <p class="mt-1.5 max-w-2xl text-sm leading-6 text-slate-600">可将每一页单独拆出，也可按指定页段生成多份 PDF，完成后统一打包下载。</p>
          </div>
        </div>
        <span class="inline-flex w-fit items-center gap-2 rounded-full border border-slate-200 bg-white/90 px-3 py-1.5 text-xs font-semibold text-slate-600 shadow-sm">
          <ShieldCheck class="size-3.5 text-amber-700" aria-hidden="true" />
          {{ props.contextLabel }}可用
        </span>
      </div>
    </div>

    <div class="grid gap-0 lg:grid-cols-[minmax(0,1fr)_300px]">
      <div class="space-y-5 p-5 sm:p-7">
        <label
          class="group flex min-h-44 cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-7 text-center transition"
          :class="isDragging
            ? 'border-amber-500 bg-amber-50'
            : selectedFile
              ? 'border-amber-300 bg-amber-50/50'
              : 'border-slate-300 bg-slate-50/70 hover:border-amber-400 hover:bg-amber-50/45'"
          @dragenter.prevent="isDragging = true"
          @dragover.prevent="isDragging = true"
          @dragleave.prevent="isDragging = false"
          @drop.prevent="handleDrop"
        >
          <input ref="fileInput" type="file" class="sr-only" accept="application/pdf,.pdf" @change="handleFileChange">
          <template v-if="selectedFile">
            <span class="flex size-12 items-center justify-center rounded-2xl bg-white text-amber-700 shadow-sm ring-1 ring-amber-100">
              <FileText class="size-6" aria-hidden="true" />
            </span>
            <strong class="mt-3 max-w-full truncate text-base text-slate-950">{{ selectedFile.name }}</strong>
            <span class="mt-1 text-sm text-slate-500">{{ selectedFileSize }} · 点击可替换文件</span>
          </template>
          <template v-else>
            <span class="flex size-12 items-center justify-center rounded-2xl bg-white text-slate-500 shadow-sm ring-1 ring-slate-200 transition group-hover:text-amber-700 group-hover:ring-amber-200">
              <Upload class="size-6" aria-hidden="true" />
            </span>
            <strong class="mt-3 text-base text-slate-950">拖拽 PDF 到这里，或点击选择文件</strong>
            <span class="mt-1 text-sm text-slate-500">单个文件不超过 20MB，最多 80 页</span>
          </template>
        </label>

        <fieldset>
          <legend class="text-sm font-bold text-slate-900">选择拆分方式</legend>
          <div class="mt-3 grid gap-3 sm:grid-cols-2">
            <label class="cursor-pointer rounded-xl border p-4 transition" :class="splitMode === 'each_page' ? 'border-amber-400 bg-amber-50 ring-1 ring-amber-100' : 'border-slate-200 hover:bg-slate-50'">
              <span class="flex items-start gap-3">
                <input v-model="splitMode" type="radio" value="each_page" class="mt-1 accent-amber-600">
                <span>
                  <strong class="block text-sm text-slate-900">每页单独拆分</strong>
                  <small class="mt-1 block text-xs leading-5 text-slate-500">每一页生成一份 PDF。</small>
                </span>
              </span>
            </label>
            <label class="cursor-pointer rounded-xl border p-4 transition" :class="splitMode === 'ranges' ? 'border-amber-400 bg-amber-50 ring-1 ring-amber-100' : 'border-slate-200 hover:bg-slate-50'">
              <span class="flex items-start gap-3">
                <input v-model="splitMode" type="radio" value="ranges" class="mt-1 accent-amber-600">
                <span>
                  <strong class="block text-sm text-slate-900">按指定页段拆分</strong>
                  <small class="mt-1 block text-xs leading-5 text-slate-500">每个页段生成一份 PDF。</small>
                </span>
              </span>
            </label>
          </div>
          <label v-if="splitMode === 'ranges'" class="mt-3 block">
            <span class="text-xs font-semibold text-slate-600">页码或页段</span>
            <input
              v-model="pageRanges"
              type="text"
              inputmode="text"
              class="mt-1.5 h-11 w-full rounded-xl border border-slate-200 bg-white px-3.5 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-amber-400 focus:ring-2 focus:ring-amber-100"
              placeholder="例如：1-3,4,5-7"
            >
            <span class="mt-1.5 block text-xs text-slate-500">逗号分隔；1-3 会合并为一份，4 会单独生成一份。</span>
          </label>
        </fieldset>

        <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div class="min-h-6 text-sm">
            <p v-if="errorMessage" class="font-medium text-red-700" role="alert">{{ errorMessage }}</p>
            <div v-else-if="successMessage" class="text-emerald-700" role="status">
              <p class="flex items-start gap-2 font-medium"><CheckCircle2 class="mt-0.5 size-4 shrink-0" aria-hidden="true" />{{ successMessage }}</p>
              <p v-if="resultSummary" class="mt-1 pl-6 text-xs text-emerald-700/80">原文件 {{ resultSummary.pageCount }} 页 · 已生成 {{ resultSummary.fileCount }} 份 PDF</p>
            </div>
            <p v-else class="text-slate-500">拆分结果以 ZIP 下载，源 PDF 不会被修改。</p>
          </div>

          <div class="flex shrink-0 items-center gap-2">
            <button
              v-if="selectedFile"
              type="button"
              class="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 text-sm font-semibold text-slate-600 transition hover:border-slate-300 hover:bg-slate-50"
              :disabled="isSplitting"
              @click="clearFile"
            >
              <X class="size-4" aria-hidden="true" />
              清除
            </button>
            <button
              type="button"
              class="inline-flex h-10 min-w-40 items-center justify-center gap-2 rounded-xl bg-amber-600 px-5 text-sm font-semibold text-white shadow-sm transition hover:bg-amber-700 disabled:cursor-not-allowed disabled:bg-slate-300"
              :disabled="!canSplit"
              @click="splitFile"
            >
              <LoaderCircle v-if="isSplitting" class="size-4 animate-spin" aria-hidden="true" />
              <Download v-else class="size-4" aria-hidden="true" />
              {{ isSplitting ? '正在拆分…' : '拆分并下载 ZIP' }}
            </button>
          </div>
        </div>
      </div>

      <aside class="border-t border-slate-200/80 bg-slate-50/70 p-5 sm:p-7 lg:border-l lg:border-t-0" aria-label="拆分说明">
        <p class="text-xs font-bold uppercase tracking-[0.14em] text-slate-400">拆分流程</p>
        <ol class="mt-5 space-y-5">
          <li v-for="(step, index) in ['选择 PDF 文件', '设置拆分页码', '下载拆分压缩包']" :key="step" class="flex gap-3">
            <span class="flex size-7 shrink-0 items-center justify-center rounded-full bg-white text-xs font-bold text-amber-700 shadow-sm ring-1 ring-slate-200">{{ index + 1 }}</span>
            <div>
              <strong class="text-sm text-slate-900">{{ step }}</strong>
              <p class="mt-1 text-xs leading-5 text-slate-500">
                {{ index === 0 ? '支持普通和扫描 PDF，不改变页面内容。' : index === 1 ? '可逐页拆分，也可组合连续页段。' : '所有结果打包为一个 .zip 文件。' }}
              </p>
            </div>
          </li>
        </ol>

        <div class="mt-6 rounded-xl border border-amber-100 bg-amber-50/80 p-4">
          <p class="flex items-center gap-2 text-xs font-bold text-amber-900"><Archive class="size-4" aria-hidden="true" />文件命名</p>
          <p class="mt-2 text-xs leading-5 text-amber-800/80">结果按“原文件名_第1-3页.pdf”等规则命名，便于归档。</p>
        </div>
        <div class="mt-3 rounded-xl border border-slate-200 bg-white p-4">
          <p class="flex items-center gap-2 text-xs font-bold text-slate-700"><ShieldCheck class="size-4 text-amber-700" aria-hidden="true" />即时处理</p>
          <p class="mt-2 text-xs leading-5 text-slate-500">不保存 PDF、ZIP 或拆分记录。</p>
        </div>
      </aside>
    </div>
  </section>
</template>
