<script setup lang="ts">
import {
  ArrowRight,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  FileText,
  Image,
  Languages,
  LayoutTemplate,
  ListChecks,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  Type,
  Upload,
  X,
} from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'
import {
  sharedToolsApi,
  type DocumentTranslationDirection,
  type DocumentTranslationStatus,
} from '@/api/tools'
import { getApiErrorMessage } from '@/lib/http'
import { downloadToolBlob, formatPdfFileSize } from './pdfToolUtils'
import {
  extractExcelSheetNames,
  validateTranslationDocument,
} from './documentTranslationUtils'


const props = withDefaults(defineProps<{
  contextLabel?: string
  factoryId?: string
}>(), {
  contextLabel: '全部厂区',
  factoryId: '',
})

const fileInput = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)
const sheetNames = ref<string[]>([])
const selectedSheetNames = ref<string[]>([])
const direction = ref<DocumentTranslationDirection>('zh_to_en')
const isDragging = ref(false)
const isTranslating = ref(false)
const isLoadingSheets = ref(false)
const isLoadingStatus = ref(true)
const serviceStatus = ref<DocumentTranslationStatus | null>(null)
const statusError = ref('')
const errorMessage = ref('')
const successMessage = ref('')
const resultMetrics = ref<{ translated: number; skipped: number; parts: number } | null>(null)
const selectedFileSize = computed(() => selectedFile.value ? formatPdfFileSize(selectedFile.value.size) : '')
const isExcel = computed(() => Boolean(selectedFile.value?.name.match(/\.xls[xm]$/i)))
const allSheetsSelected = computed(() => sheetNames.value.length > 0
  && selectedSheetNames.value.length === sheetNames.value.length)
const selectedDirectionReady = computed(() => serviceStatus.value?.directions[direction.value] !== false)
const selectedModeAvailable = computed(() => serviceStatus.value?.available === true)
const canTranslate = computed(() => Boolean(selectedFile.value)
  && !isTranslating.value
  && !isLoadingSheets.value
  && (!isExcel.value || selectedSheetNames.value.length > 0)
  && selectedModeAvailable.value
  && selectedDirectionReady.value)

let fileSelectionVersion = 0

function resetResult() {
  errorMessage.value = ''
  successMessage.value = ''
  resultMetrics.value = null
}

async function selectFile(file: File | undefined) {
  const selectionVersion = ++fileSelectionVersion
  resetResult()
  if (!file) return
  const error = validateTranslationDocument(file)
  if (error) {
    selectedFile.value = null
    sheetNames.value = []
    selectedSheetNames.value = []
    errorMessage.value = error
    if (fileInput.value) fileInput.value.value = ''
    return
  }

  selectedFile.value = file
  sheetNames.value = []
  selectedSheetNames.value = []
  if (!/\.xls[xm]$/i.test(file.name)) return

  isLoadingSheets.value = true
  try {
    const names = await extractExcelSheetNames(file)
    if (selectionVersion !== fileSelectionVersion) return
    sheetNames.value = names
    selectedSheetNames.value = [...names]
  }
  catch (sheetError) {
    if (selectionVersion !== fileSelectionVersion) return
    selectedFile.value = null
    errorMessage.value = sheetError instanceof Error
      ? sheetError.message
      : '无法读取 Excel 工作表列表。'
    if (fileInput.value) fileInput.value.value = ''
  }
  finally {
    if (selectionVersion === fileSelectionVersion) isLoadingSheets.value = false
  }
}

function handleFileChange(event: Event) {
  void selectFile((event.target as HTMLInputElement).files?.[0])
}

function handleDrop(event: DragEvent) {
  isDragging.value = false
  void selectFile(event.dataTransfer?.files?.[0])
}

function clearFile() {
  fileSelectionVersion += 1
  selectedFile.value = null
  sheetNames.value = []
  selectedSheetNames.value = []
  isLoadingSheets.value = false
  resetResult()
  if (fileInput.value) fileInput.value.value = ''
}

function toggleAllSheets() {
  selectedSheetNames.value = allSheetsSelected.value ? [] : [...sheetNames.value]
  resetResult()
}

function setDirection(value: DocumentTranslationDirection) {
  direction.value = value
  resetResult()
}

async function loadServiceStatus() {
  isLoadingStatus.value = true
  statusError.value = ''
  try {
    serviceStatus.value = await sharedToolsApi.getDocumentTranslationStatus()
  }
  catch (error) {
    serviceStatus.value = null
    statusError.value = getApiErrorMessage(error)
  }
  finally {
    isLoadingStatus.value = false
  }
}

async function translateFile() {
  if (!selectedFile.value || !canTranslate.value) return
  isTranslating.value = true
  resetResult()
  try {
    const result = await sharedToolsApi.translateDocument(
      selectedFile.value,
      direction.value,
      isExcel.value ? [...selectedSheetNames.value] : undefined,
    )
    downloadToolBlob(result.blob, result.fileName)
    resultMetrics.value = {
      translated: result.translatedUnitCount,
      skipped: result.skippedUnitCount,
      parts: result.processedPartCount,
    }
    successMessage.value = `${result.fileName} 已生成并开始下载。`
  }
  catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  }
  finally {
    isTranslating.value = false
  }
}

onMounted(loadServiceStatus)
</script>

<template>
  <section class="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-[0_18px_50px_-32px_rgba(15,23,42,0.45)]" aria-labelledby="document-translation-title">
    <div class="border-b border-slate-200/80 bg-gradient-to-r from-violet-50/90 via-white to-indigo-50/70 px-5 py-5 sm:px-7">
      <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div class="flex items-start gap-4">
          <span class="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-violet-700 text-white shadow-lg shadow-violet-900/15">
            <Languages class="size-6" aria-hidden="true" />
          </span>
          <div>
            <div class="flex flex-wrap items-center gap-2">
              <h2 id="document-translation-title" class="text-xl font-bold tracking-tight text-slate-950">文档翻译</h2>
              <span class="rounded-full bg-violet-100 px-2.5 py-1 text-[11px] font-bold tracking-wide text-violet-800">Excel / Word</span>
            </div>
            <p class="mt-1.5 max-w-2xl text-sm leading-6 text-slate-600">Excel 可选择需要翻译的工作表，Word 翻译整份文档；直接替换原文件文字，不重建表格与页面。</p>
          </div>
        </div>
        <span class="inline-flex w-fit items-center gap-2 rounded-full border border-slate-200 bg-white/90 px-3 py-1.5 text-xs font-semibold text-slate-600 shadow-sm">
          <ShieldCheck class="size-3.5 text-violet-700" aria-hidden="true" />
          {{ props.contextLabel }}可用
        </span>
      </div>
    </div>

    <div class="grid gap-0 lg:grid-cols-[minmax(0,1fr)_300px]">
      <div class="p-5 sm:p-7">
        <fieldset class="mt-5">
          <legend class="text-sm font-bold text-slate-900">选择翻译方向</legend>
          <div class="mt-3 grid gap-3 sm:grid-cols-2">
            <button
              v-for="option in [
                { value: 'zh_to_en' as const, source: '中文', target: 'English', note: '中文内容转为英文' },
                { value: 'en_to_zh' as const, source: 'English', target: '中文', note: '英文内容转为中文' },
              ]"
              :key="option.value"
              type="button"
              class="flex items-center gap-3 rounded-xl border px-4 py-3 text-left transition"
              :class="direction === option.value
                ? 'border-violet-400 bg-violet-50 text-violet-950 ring-2 ring-violet-100'
                : 'border-slate-200 bg-white text-slate-600 hover:border-violet-200 hover:bg-violet-50/40'"
              :aria-pressed="direction === option.value"
              @click="setDirection(option.value)"
            >
              <span class="text-sm font-bold">{{ option.source }}</span>
              <ArrowRight class="size-4 shrink-0 text-violet-500" aria-hidden="true" />
              <span class="text-sm font-bold">{{ option.target }}</span>
              <small class="ml-auto hidden text-xs text-slate-400 xl:block">{{ option.note }}</small>
            </button>
          </div>
        </fieldset>

        <label
          class="group mt-5 flex min-h-48 cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-7 text-center transition"
          :class="isDragging
            ? 'border-violet-500 bg-violet-50'
            : selectedFile
              ? 'border-violet-300 bg-violet-50/50'
              : 'border-slate-300 bg-slate-50/70 hover:border-violet-400 hover:bg-violet-50/45'"
          @dragenter.prevent="isDragging = true"
          @dragover.prevent="isDragging = true"
          @dragleave.prevent="isDragging = false"
          @drop.prevent="handleDrop"
        >
          <input ref="fileInput" type="file" class="sr-only" accept=".xlsx,.xlsm,.docx" @change="handleFileChange">

          <template v-if="selectedFile">
            <span class="flex size-14 items-center justify-center rounded-2xl bg-white text-violet-700 shadow-sm ring-1 ring-violet-100">
              <FileSpreadsheet v-if="isExcel" class="size-7" aria-hidden="true" />
              <FileText v-else class="size-7" aria-hidden="true" />
            </span>
            <strong class="mt-4 max-w-full truncate text-base text-slate-950">{{ selectedFile.name }}</strong>
            <span class="mt-1 text-sm text-slate-500">{{ selectedFileSize }} · 点击可替换文件</span>
          </template>
          <template v-else>
            <span class="flex size-14 items-center justify-center rounded-2xl bg-white text-slate-500 shadow-sm ring-1 ring-slate-200 transition group-hover:text-violet-700 group-hover:ring-violet-200">
              <Upload class="size-7" aria-hidden="true" />
            </span>
            <strong class="mt-4 text-base text-slate-950">拖拽 Excel 或 Word 到这里，或点击选择</strong>
            <span class="mt-1 text-sm text-slate-500">支持 .xlsx、.xlsm、.docx，单个文件不超过 20MB</span>
            <span class="mt-1 text-xs text-slate-400">旧版 .xls 请先另存为 .xlsx，以免转换破坏原格式</span>
          </template>
        </label>

        <section
          v-if="selectedFile && isExcel"
          class="mt-5 rounded-2xl border border-violet-100 bg-violet-50/45 p-4"
          aria-labelledby="sheet-selection-title"
        >
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div class="flex items-center gap-2.5">
              <span class="flex size-8 items-center justify-center rounded-lg bg-white text-violet-700 shadow-sm ring-1 ring-violet-100">
                <ListChecks class="size-4" aria-hidden="true" />
              </span>
              <div>
                <h3 id="sheet-selection-title" class="text-sm font-bold text-slate-900">选择需要翻译的工作表</h3>
                <p class="mt-0.5 text-xs text-slate-500">未勾选的 Sheet 内容保持原样。</p>
              </div>
            </div>
            <div v-if="!isLoadingSheets" class="flex items-center gap-2">
              <span class="rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-violet-700 ring-1 ring-violet-100">
                已选 {{ selectedSheetNames.length }}/{{ sheetNames.length }}
              </span>
              <button
                type="button"
                class="text-xs font-bold text-violet-700 hover:text-violet-900"
                :aria-pressed="allSheetsSelected"
                @click="toggleAllSheets"
              >
                {{ allSheetsSelected ? '取消全选' : '全部选择' }}
              </button>
            </div>
          </div>

          <div v-if="isLoadingSheets" class="mt-4 flex items-center gap-2 rounded-xl bg-white/80 px-3 py-3 text-sm text-slate-500">
            <LoaderCircle class="size-4 animate-spin text-violet-600" aria-hidden="true" />
            正在读取工作表列表…
          </div>
          <div v-else class="mt-4 grid max-h-52 gap-2 overflow-y-auto pr-1 sm:grid-cols-2">
            <label
              v-for="sheetName in sheetNames"
              :key="sheetName"
              class="flex cursor-pointer items-center gap-2.5 rounded-xl border px-3 py-2.5 text-sm transition"
              :class="selectedSheetNames.includes(sheetName)
                ? 'border-violet-300 bg-white font-semibold text-violet-950 shadow-sm'
                : 'border-slate-200 bg-white/60 text-slate-500 hover:border-violet-200'"
            >
              <input
                v-model="selectedSheetNames"
                type="checkbox"
                :value="sheetName"
                class="size-4 rounded border-slate-300 text-violet-700 focus:ring-violet-500"
                @change="resetResult"
              >
              <span class="min-w-0 truncate" :title="sheetName">{{ sheetName }}</span>
            </label>
          </div>
          <p v-if="!isLoadingSheets && selectedSheetNames.length === 0" class="mt-3 text-xs font-medium text-amber-700" role="status">
            请至少选择一个工作表后再翻译。
          </p>
        </section>

        <div class="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div class="min-h-8 text-sm">
            <p v-if="errorMessage" class="font-medium text-red-700" role="alert">{{ errorMessage }}</p>
            <div v-else-if="successMessage" class="text-emerald-700" role="status">
              <p class="flex items-start gap-2 font-medium"><CheckCircle2 class="mt-0.5 size-4 shrink-0" aria-hidden="true" />{{ successMessage }}</p>
              <p v-if="resultMetrics" class="mt-1 pl-6 text-xs text-emerald-700/80">
                已翻译 {{ resultMetrics.translated }} 段 · 跳过 {{ resultMetrics.skipped }} 段 · 处理 {{ resultMetrics.parts }} 个文档部件
              </p>
            </div>
            <p v-else class="text-slate-500">文字长度变化可能影响自动换行或分页，但不会改写原有样式和对象。</p>
          </div>

          <div class="flex shrink-0 items-center gap-2">
            <button
              v-if="selectedFile"
              type="button"
              class="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 text-sm font-semibold text-slate-600 transition hover:border-slate-300 hover:bg-slate-50"
              :disabled="isTranslating"
              @click="clearFile"
            >
              <X class="size-4" aria-hidden="true" />
              清除
            </button>
            <button
              type="button"
              class="inline-flex h-10 min-w-40 items-center justify-center gap-2 rounded-xl bg-violet-700 px-5 text-sm font-semibold text-white shadow-sm transition hover:bg-violet-800 disabled:cursor-not-allowed disabled:bg-slate-300"
              :disabled="!canTranslate"
              @click="translateFile"
            >
              <LoaderCircle v-if="isTranslating" class="size-4 animate-spin" aria-hidden="true" />
              <Download v-else class="size-4" aria-hidden="true" />
              {{ isTranslating ? '正在翻译…' : '翻译并下载' }}
            </button>
          </div>
        </div>
      </div>

      <aside class="border-t border-slate-200/80 bg-slate-50/70 p-5 sm:p-7 lg:border-l lg:border-t-0" aria-label="格式保留说明">
        <p class="text-xs font-bold uppercase tracking-[0.14em] text-slate-400">原样保留</p>
        <ul class="mt-5 space-y-4">
          <li v-for="item in [
            { icon: LayoutTemplate, title: '版式、表格与线条', note: '保留边框、合并、行列尺寸和页面结构。' },
            { icon: Image, title: '图片与绘图对象', note: '图片、形状、图表和定位关系不重建。' },
            { icon: Type, title: '字体、字号与样式', note: '保留每个文字片段原有字体和强调样式。' },
            { icon: FileSpreadsheet, title: '公式与工作簿设置', note: '公式、宏、打印设置和非文字值保持不变。' },
          ]" :key="item.title" class="flex gap-3">
            <span class="flex size-8 shrink-0 items-center justify-center rounded-lg bg-white text-violet-700 shadow-sm ring-1 ring-slate-200">
              <component :is="item.icon" class="size-4" aria-hidden="true" />
            </span>
            <div>
              <strong class="text-sm text-slate-900">{{ item.title }}</strong>
              <p class="mt-0.5 text-xs leading-5 text-slate-500">{{ item.note }}</p>
            </div>
          </li>
        </ul>

        <div class="mt-6 rounded-xl border p-4" :class="selectedModeAvailable ? 'border-emerald-100 bg-emerald-50/80' : 'border-amber-200 bg-amber-50/80'">
          <p class="flex items-center gap-2 text-xs font-bold" :class="selectedModeAvailable ? 'text-emerald-900' : 'text-amber-900'">
            <LoaderCircle v-if="isLoadingStatus" class="size-4 animate-spin" aria-hidden="true" />
            <ShieldCheck v-else-if="selectedModeAvailable" class="size-4" aria-hidden="true" />
            <RefreshCw v-else class="size-4" aria-hidden="true" />
            {{ isLoadingStatus ? '正在检查翻译模型' : selectedModeAvailable ? '离线翻译已就绪' : '翻译模型未就绪' }}
          </p>
          <p class="mt-2 text-xs leading-5" :class="selectedModeAvailable ? 'text-emerald-800/80' : 'text-amber-800/90'">
            {{ serviceStatus?.available
              ? '文档正文只在当前服务器内处理，不发送到第三方服务，也不保存源文件、结果或翻译记录。'
              : statusError || '请联系系统管理员安装中英双向离线模型后再使用。' }}
          </p>
          <button v-if="!isLoadingStatus && !selectedModeAvailable" type="button" class="mt-3 inline-flex items-center gap-1.5 text-xs font-bold text-amber-800 hover:text-amber-950" @click="loadServiceStatus">
            <RefreshCw class="size-3.5" aria-hidden="true" />重新检查
          </button>
        </div>
      </aside>
    </div>
  </section>
</template>
