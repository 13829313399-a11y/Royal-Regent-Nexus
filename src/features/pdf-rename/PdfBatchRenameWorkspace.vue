<script setup lang="ts">
import {
  AlertCircle,
  CheckCircle2,
  Download,
  FileSearch,
  FileUp,
  Files,
  LoaderCircle,
  Plus,
  RotateCcw,
  ShieldCheck,
  Trash2,
} from '@lucide/vue'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  PdfRenameApiError,
  pdfRenameApi,
  type PdfRenamePreviewResult,
  type PdfRenameRuleCatalog,
  type PdfRenameManualOverride,
} from '@/api/pdfRename'
import { Button } from '@/components/ui/button'
import { downloadToolBlob, validatePdfFile } from './pdfRenameUtils'

const props = defineProps<{
  contextLabel: string
  factoryId: string
}>()

const catalog = ref<PdfRenameRuleCatalog | null>(null)
const selectedRuleId = ref('')
const files = ref<File[]>([])
const preview = ref<PdfRenamePreviewResult | null>(null)
const state = ref<'IDLE' | 'PREVIEWING' | 'PREVIEWED' | 'EXECUTING' | 'SUCCESS' | 'ERROR'>('IDLE')
const message = ref('')
const errorCode = ref('')
const errorAction = ref('')
const dragging = ref(false)
const ocrConfirmed = ref(false)
const manualNames = ref<Record<number, string>>({})
const manualConfirmed = ref<Record<number, boolean>>({})
const appliedManualSignature = ref('[]')
const inputRef = ref<HTMLInputElement | null>(null)
let requestController: AbortController | null = null

const scopedRules = computed(() => catalog.value?.rules.filter(rule => (
  !rule.factory_ids?.length || rule.factory_ids.includes(props.factoryId)
)) ?? [])
const activeRules = computed(() => scopedRules.value.filter(rule => rule.available))
const selectedRule = computed(() => activeRules.value.find(rule => rule.id === selectedRuleId.value) ?? null)
const draftRule = computed(() => scopedRules.value.find(rule => !rule.available) ?? null)
const maxFiles = computed(() => catalog.value?.limits.max_files ?? 50)
const maxBatchBytes = computed(() => catalog.value?.limits.max_batch_bytes ?? 200 * 1024 * 1024)
const isBusy = computed(() => state.value === 'PREVIEWING' || state.value === 'EXECUTING')
const manualOverrides = computed<PdfRenameManualOverride[]>(() => Object.entries(manualNames.value)
  .filter(([, name]) => name.trim())
  .map(([index, name]) => ({ source_index: Number(index), target_file_name: name.trim(), confirmed: manualConfirmed.value[Number(index)] === true })))
const manualUnconfirmed = computed(() => manualOverrides.value.some(item => !item.confirmed))
const manualDirty = computed(() => JSON.stringify(manualOverrides.value) !== appliedManualSignature.value)
const blockingFiles = computed(() => preview.value?.items.filter(item => item.status === 'ERROR') ?? [])
const downloadBlockReason = computed(() => {
  if (!preview.value) return ''
  if (manualUnconfirmed.value) return '请逐份勾选“确认此人工文件名并放行”，再应用人工改名。'
  if (manualDirty.value) return '人工文件名已修改，请先应用人工改名并重新预览。'
  if (state.value === 'ERROR') return `${message.value} ${errorAction.value}`
  if (preview.value.summary.error) return `仍有 ${preview.value.summary.error} 份文件存在错误，暂不能下载。`
  if (preview.value.summary.review && !ocrConfirmed.value) return '请先勾选复核确认，再下载 ZIP。'
  return ''
})
const canPreview = computed(() => (
  props.factoryId === 'huaxing'
  && Boolean(selectedRule.value?.available)
  && files.value.length > 0
  && !isBusy.value
  && !manualUnconfirmed.value
))
const canExecute = computed(() => (
  preview.value
  && selectedRule.value?.available
  && preview.value.summary.error === 0
  && (preview.value.summary.review === 0 || ocrConfirmed.value)
  && !isBusy.value
  && !manualDirty.value
  && !manualUnconfirmed.value
  && state.value !== 'ERROR'
))

function humanFileSize(bytes: number) {
  return bytes >= 1024 * 1024
    ? `${(bytes / 1024 / 1024).toFixed(1)} MB`
    : `${Math.max(1, Math.ceil(bytes / 1024))} KB`
}

function clearError() {
  message.value = ''
  errorCode.value = ''
  errorAction.value = ''
}

function invalidatePreview() {
  preview.value = null
  ocrConfirmed.value = false
  manualNames.value = {}
  manualConfirmed.value = {}
  appliedManualSignature.value = '[]'
  clearError()
  state.value = files.value.length ? 'IDLE' : 'IDLE'
}

function showError(error: unknown, fallback: string) {
  if (error instanceof PdfRenameApiError) {
    message.value = error.message
    errorCode.value = error.code
    errorAction.value = error.action
  }
  else {
    message.value = error instanceof Error ? error.message : fallback
    errorCode.value = 'PDF_RENAME_FAILED'
    errorAction.value = '请检查文件和规则后重试；若持续失败，请联系管理员。'
  }
  state.value = 'ERROR'
}

function addFiles(selected: FileList | File[] | undefined) {
  if (isBusy.value) return
  const incoming = Array.from(selected ?? [])
  if (!incoming.length) return
  const unique = [...files.value]
  const keys = new Set(unique.map(file => `${file.name}\u0000${file.size}\u0000${file.lastModified}`))
  for (const file of incoming) {
    const validation = validatePdfFile(file)
    if (validation) {
      showError(new Error(`${file.name}：${validation}`), 'PDF 文件不符合要求。')
      return
    }
    const key = `${file.name}\u0000${file.size}\u0000${file.lastModified}`
    if (!keys.has(key)) {
      unique.push(file)
      keys.add(key)
    }
  }
  if (unique.length > maxFiles.value) {
    showError(new Error(`单批最多加入 ${maxFiles.value} 份 PDF。`), '文件数量超过限制。')
    return
  }
  if (unique.reduce((total, file) => total + file.size, 0) > maxBatchBytes.value) {
    showError(new Error('单批 PDF 总大小不能超过 200 MB。'), '文件总大小超过限制。')
    return
  }
  files.value = unique
  invalidatePreview()
  if (inputRef.value) inputRef.value.value = ''
}

function removeFile(index: number) {
  files.value.splice(index, 1)
  files.value = [...files.value]
  invalidatePreview()
}

function reset() {
  requestController?.abort()
  requestController = null
  files.value = []
  invalidatePreview()
  if (inputRef.value) inputRef.value.value = ''
}

function selectRule(value: string) {
  selectedRuleId.value = value
  invalidatePreview()
}

function editManualName(index: number, name: string) {
  manualNames.value[index] = name
  manualConfirmed.value[index] = false
  ocrConfirmed.value = false
}

function confirmManualName(index: number, confirmed: boolean) {
  manualConfirmed.value[index] = confirmed
  ocrConfirmed.value = false
}

async function createPreview() {
  if (!canPreview.value) return
  requestController?.abort()
  const controller = new AbortController()
  requestController = controller
  const overrides = manualOverrides.value.map(item => ({ ...item }))
  clearError()
  ocrConfirmed.value = false
  state.value = 'PREVIEWING'
  try {
    const result = await pdfRenameApi.previewPdfRename(
      files.value,
      selectedRuleId.value,
      props.factoryId,
      controller.signal,
      overrides,
    )
    if (controller.signal.aborted) return
    preview.value = result
    appliedManualSignature.value = JSON.stringify(overrides)
    state.value = 'PREVIEWED'
  }
  catch (error) {
    if (controller.signal.aborted) return
    showError(error, '批量改名预览失败。')
  }
  finally {
    if (requestController === controller) requestController = null
  }
}

async function executeRename() {
  if (!preview.value || !canExecute.value) return
  requestController?.abort()
  const controller = new AbortController()
  requestController = controller
  clearError()
  state.value = 'EXECUTING'
  try {
    const result = await pdfRenameApi.executePdfRename(
      files.value,
      selectedRuleId.value,
      preview.value.preview_token,
      ocrConfirmed.value,
      props.factoryId,
      controller.signal,
      manualOverrides.value,
    )
    if (controller.signal.aborted) return
    downloadToolBlob(result.blob, result.fileName)
    message.value = `已生成 ${result.fileCount} 份改名后的 PDF，并打包下载。`
    state.value = 'SUCCESS'
  }
  catch (error) {
    if (controller.signal.aborted) return
    showError(error, '批量改名执行失败。')
  }
  finally {
    if (requestController === controller) requestController = null
  }
}

watch(() => props.factoryId, async (factoryId) => {
  reset()
  catalog.value = null
  selectedRuleId.value = ''
  if (factoryId !== 'huaxing') return
  const controller = new AbortController()
  requestController = controller
  try {
    const result = await pdfRenameApi.getPdfRenameRules(factoryId, controller.signal)
    if (controller.signal.aborted) return
    catalog.value = result
    selectedRuleId.value = activeRules.value[0]?.id ?? ''
  }
  catch (error) {
    if (controller.signal.aborted) return
    showError(error, '无法读取批量改名规则。')
  }
  finally {
    if (requestController === controller) requestController = null
  }
}, { immediate: true, flush: 'sync' })

onBeforeUnmount(() => requestController?.abort())
</script>

<template>
  <div v-if="factoryId === 'huaxing'" class="min-w-0 overflow-hidden rounded-xl border border-slate-200 bg-slate-50/70" aria-label="华兴 PDF 批量改名">
    <div v-if="!catalog && state !== 'ERROR'" class="grid min-h-[320px] place-items-center text-sm text-slate-500">
      <div class="flex items-center gap-2"><LoaderCircle class="size-4 animate-spin" aria-hidden="true" />正在读取改名规则…</div>
    </div>

    <div v-else class="grid xl:grid-cols-[minmax(0,1fr)_360px]">
      <main class="min-w-0 border-b border-slate-200 p-5 sm:p-6 xl:border-b-0 xl:border-r">
        <div class="mb-5 grid gap-2 sm:grid-cols-3" aria-label="批量改名步骤">
          <div class="rounded-xl border border-teal-200 bg-teal-50 p-3"><span class="text-xs font-bold text-teal-700">01 选择规则</span><p class="mt-1 text-sm text-slate-700">每类需求独立配置</p></div>
          <div class="rounded-xl border border-slate-200 bg-white p-3"><span class="text-xs font-bold text-slate-500">02 识别预览</span><p class="mt-1 text-sm text-slate-700">核对识别内容与新文件名</p></div>
          <div class="rounded-xl border border-slate-200 bg-white p-3"><span class="text-xs font-bold text-slate-500">03 打包下载</span><p class="mt-1 text-sm text-slate-700">源文件保持不变</p></div>
        </div>

        <div v-if="!activeRules.length" class="mb-5 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <div class="flex items-start gap-3">
            <AlertCircle class="mt-0.5 size-5 shrink-0 text-amber-600" aria-hidden="true" />
            <div><h2 class="text-sm font-semibold text-amber-950">当前厂区暂无可用改名规则</h2><p class="mt-1 text-sm leading-6 text-amber-900/80">批量改名框架已保留，规则按厂区独立配置。收集到本厂区样例后，即可新增对应规则。</p></div>
          </div>
        </div>

        <section
          class="rounded-2xl border-2 border-dashed p-5 transition-colors sm:p-6"
          :class="dragging ? 'border-teal-500 bg-teal-50' : 'border-slate-300 bg-white'"
          aria-labelledby="batch-upload-title"
          @dragenter.prevent="dragging = true"
          @dragover.prevent="dragging = true"
          @dragleave.prevent="dragging = false"
          @drop.prevent="dragging = false; addFiles($event.dataTransfer?.files)"
        >
          <input ref="inputRef" class="sr-only" type="file" accept=".pdf,application/pdf" multiple @change="addFiles(($event.target as HTMLInputElement).files ?? undefined)">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div class="flex items-center gap-3">
              <span class="flex size-11 items-center justify-center rounded-xl bg-teal-50 text-teal-700"><FileUp class="size-5" aria-hidden="true" /></span>
              <div><h2 id="batch-upload-title" class="text-base font-semibold text-slate-950">加入需要改名的 PDF</h2><p class="mt-0.5 text-sm text-slate-500">最多 {{ maxFiles }} 份，单份 20 MB，本批总计不超过 200 MB</p></div>
            </div>
            <Button variant="outline" :disabled="isBusy" @click="inputRef?.click()"><Plus class="size-4" aria-hidden="true" />{{ files.length ? '继续添加' : '选择文件' }}</Button>
          </div>
        </section>

        <div v-if="files.length" class="mt-5 overflow-hidden rounded-xl border border-slate-200 bg-white">
          <div class="flex items-center justify-between border-b border-slate-200 px-4 py-3"><div class="flex items-center gap-2 text-sm font-semibold text-slate-900"><Files class="size-4 text-teal-700" aria-hidden="true" />已加入 {{ files.length }} 份 PDF</div><Button variant="ghost" size="sm" :disabled="isBusy" @click="reset"><Trash2 class="size-4" aria-hidden="true" />清空</Button></div>
          <div class="max-h-52 divide-y divide-slate-100 overflow-y-auto">
            <div v-for="(file, index) in files" :key="`${file.name}-${file.size}-${file.lastModified}`" class="flex items-center gap-3 px-4 py-3">
              <FileSearch class="size-4 shrink-0 text-slate-400" aria-hidden="true" />
              <div class="min-w-0 flex-1"><p class="truncate text-sm font-medium text-slate-800">{{ file.name }}</p><p class="mt-0.5 text-xs text-slate-500">{{ humanFileSize(file.size) }}</p></div>
              <Button variant="ghost" size="icon" :disabled="isBusy" :aria-label="`移除 ${file.name}`" @click="removeFile(index)"><Trash2 class="size-4" aria-hidden="true" /></Button>
            </div>
          </div>
        </div>

        <div v-if="state === 'ERROR'" class="mt-5 rounded-xl border border-rose-200 bg-rose-50 p-4" role="alert">
          <p class="flex items-center gap-2 text-sm font-semibold text-rose-900"><AlertCircle class="size-4" aria-hidden="true" />{{ message }}</p>
          <p v-if="errorCode" class="mt-2 font-mono text-xs text-rose-700">{{ errorCode }}</p>
          <p v-if="errorAction" class="mt-1 text-xs leading-5 text-rose-800">解决办法：{{ errorAction }}</p>
        </div>

        <div v-if="preview" class="mt-5 overflow-hidden rounded-xl border border-slate-200 bg-white">
          <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3"><h2 class="text-sm font-semibold text-slate-950">改名预览</h2><div class="flex gap-2 text-xs"><span class="rounded-full bg-emerald-50 px-2 py-1 font-semibold text-emerald-700">可执行 {{ preview.summary.ready }}</span><span class="rounded-full bg-amber-50 px-2 py-1 font-semibold text-amber-700">待复核 {{ preview.summary.review }}</span><span class="rounded-full bg-rose-50 px-2 py-1 font-semibold text-rose-700">错误 {{ preview.summary.error }}</span></div></div>
          <div class="overflow-x-auto">
            <table class="w-full min-w-[720px] text-left text-sm">
              <thead class="bg-slate-50 text-xs font-semibold text-slate-500"><tr><th class="px-4 py-3">原文件名</th><th class="px-4 py-3">识别结果</th><th class="px-4 py-3">新文件名</th><th class="px-4 py-3">状态</th></tr></thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="(item, index) in preview.items" :key="index" class="align-top">
                  <td class="max-w-52 px-4 py-3 text-slate-700"><span class="break-all">{{ item.source_file_name }}</span></td>
                  <td class="max-w-64 px-4 py-3">
                    <dl v-if="item.fields.length" class="space-y-2 text-xs leading-5">
                      <div v-for="field in item.fields.filter(field => field.key !== 'report_header')" :key="field.key">
                        <dt class="font-semibold text-slate-500">{{ field.label }}</dt>
                        <dd class="break-all font-medium text-slate-900">{{ field.normalized_text || '未识别' }}</dd>
                      </div>
                    </dl>
                    <p v-else class="break-all font-medium text-slate-900">{{ item.interval_name || '—' }}</p>
                    <details v-if="item.fields.length" class="mt-2 text-xs leading-5">
                      <summary class="cursor-pointer text-teal-700 focus-visible:outline-teal-600">查看识别依据</summary>
                      <div v-for="field in item.fields" :key="field.key" class="mt-2 rounded-md bg-slate-50 p-2">
                        <p class="font-semibold text-slate-600">{{ field.label }} · {{ field.route === 'QWEN' ? '千问识别' : field.route === 'LOCAL_OCR' ? '本地扫描识别' : 'PDF 文字' }}</p>
                        <p class="whitespace-pre-wrap break-all text-slate-500">{{ field.raw_text || '未识别' }}</p>
                      </div>
                    </details>
                    <p v-for="issue in item.issues" :key="issue.code" class="mt-1 text-xs leading-5" :class="item.status === 'ERROR' ? 'text-rose-700' : 'text-amber-700'">{{ issue.message }}</p>
                  </td>
                  <td class="max-w-64 break-all px-4 py-3 text-teal-800">
                    <p class="font-medium">{{ item.target_file_name || '—' }}</p>
                    <p v-if="item.manual_override" class="mt-1 text-xs font-semibold text-amber-800">人工改名 · 待最终复核</p>
                    <details v-if="item.manual_override_allowed !== false" :open="item.status === 'ERROR'" class="mt-3 text-xs leading-5">
                      <summary class="cursor-pointer font-semibold">{{ item.status === 'ERROR' ? '人工改名并放行' : '修改文件名（可选）' }}</summary>
                      <label class="mt-2 block text-slate-700">正确文件名
                        <input :value="manualNames[index] ?? ''" :disabled="isBusy" :aria-label="`人工文件名 ${item.source_file_name}`" class="mt-1 w-full min-w-44 rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-900" placeholder="请输入核对后的完整文件名.pdf" @input="editManualName(index, ($event.target as HTMLInputElement).value)">
                      </label>
                      <p class="mt-1 text-slate-500">可省略 .pdf；清空可撤销人工改名。原识别依据保留。</p>
                      <label v-if="manualNames[index]?.trim()" class="mt-2 flex items-start gap-2 text-amber-950">
                        <input type="checkbox" :checked="manualConfirmed[index] === true" :disabled="isBusy" :aria-label="`确认人工改名 ${item.source_file_name}`" class="mt-1 size-4 shrink-0" @change="confirmManualName(index, ($event.target as HTMLInputElement).checked)">
                        <span>确认此人工文件名并放行</span>
                      </label>
                    </details>
                    <p v-else class="mt-2 text-xs text-rose-700">此异常不能人工放行，请按错误提示处理文件或联系管理员。</p>
                  </td>
                  <td class="px-4 py-3"><span class="rounded-full px-2 py-1 text-xs font-bold" :class="item.status === 'READY' ? 'bg-emerald-50 text-emerald-700' : item.status === 'REVIEW' ? 'bg-amber-50 text-amber-700' : 'bg-rose-50 text-rose-700'">{{ item.status === 'READY' ? '可执行' : item.status === 'REVIEW' ? '待复核' : '错误' }}</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div v-if="state === 'SUCCESS'" class="mt-5 rounded-xl border border-emerald-200 bg-emerald-50 p-4"><p class="flex items-center gap-2 text-sm font-semibold text-emerald-900"><CheckCircle2 class="size-5" aria-hidden="true" />{{ message }}</p></div>
      </main>

      <aside class="bg-white" aria-label="批量改名设置">
        <div class="border-b border-slate-200 px-5 py-4"><h2 class="text-sm font-semibold text-slate-950">改名规则</h2><p class="mt-1 text-xs text-slate-500">当前上下文：{{ contextLabel }}</p></div>
        <div class="space-y-5 p-5">
          <div v-if="catalog?.recognition" class="rounded-xl border border-teal-100 bg-teal-50/70 p-3 text-xs leading-5 text-teal-900">
            <p class="font-semibold">{{ catalog.recognition.label }}</p>
            <p class="mt-1">{{ catalog.recognition.description }}</p>
          </div>
          <label class="block"><span class="text-sm font-semibold text-slate-800">选择规则</span><select class="mt-2 h-11 w-full rounded-xl border border-slate-300 bg-white px-3 text-sm text-slate-800 outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-100" :value="selectedRuleId" :disabled="isBusy || !activeRules.length" @change="selectRule(($event.target as HTMLSelectElement).value)"><option value="">{{ activeRules.length ? '请选择规则' : '暂无可用规则' }}</option><option v-for="rule in activeRules" :key="rule.id" :value="rule.id">{{ rule.label }} · {{ rule.version }}</option></select></label>

          <div v-if="selectedRule" class="rounded-xl border border-slate-200 bg-slate-50 p-4"><p class="text-sm font-semibold text-slate-900">{{ selectedRule.label }}</p><p class="mt-2 text-xs leading-5 text-slate-600">{{ selectedRule.description }}</p><div v-if="selectedRule.regions.length" class="mt-3 space-y-2"><div v-for="region in selectedRule.regions" :key="region.key" class="rounded-lg bg-white p-2.5 text-xs text-slate-600"><span class="font-semibold text-slate-800">{{ region.label }}</span><span class="ml-2">第 {{ region.page_number }} 页 · 固定区域</span></div></div></div>

          <div v-else-if="draftRule" class="rounded-xl border border-amber-200 bg-amber-50 p-4"><p class="text-sm font-semibold text-amber-950">{{ draftRule.label }}</p><p class="mt-2 text-xs leading-5 text-amber-900/80">{{ draftRule.description }}</p><ul class="mt-3 space-y-2 text-xs text-amber-900"><li v-for="item in draftRule.setup_checklist" :key="item" class="flex gap-2"><span aria-hidden="true">□</span><span>{{ item }}</span></li></ul></div>

          <div class="rounded-xl border border-teal-100 bg-teal-50/70 p-3 text-xs leading-5 text-teal-900"><p class="flex items-center gap-2 font-semibold"><ShieldCheck class="size-4" aria-hidden="true" />处理边界</p><p class="mt-1">{{ catalog?.recognition?.mode === 'qwen' ? '仅将命名所需的首页区域发送给已配置的千问；识别文本在服务器内存暂存 15 分钟供预览和下载复用。' : '在本地读取命名所需的固定区域。' }} 不长期保存文件或识别内容；下载生成新 ZIP，不修改源文件。</p></div>

          <label v-if="preview?.summary.review" class="flex cursor-pointer items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-3"><input v-model="ocrConfirmed" type="checkbox" :disabled="isBusy || manualDirty" class="mt-1 size-4 rounded border-amber-400 text-teal-700"><span class="text-xs leading-5 text-amber-950"><strong class="block font-semibold">已对照原 PDF 逐项复核最终文件名</strong>请按所选规则确认全部字段、排列顺序及人工修改的文件名无误，再生成文件。</span></label>
        </div>

        <div class="space-y-2 border-t border-slate-200 p-5">
          <Button v-if="!preview" class="w-full" size="lg" :disabled="!canPreview" @click="createPreview"><LoaderCircle v-if="state === 'PREVIEWING'" class="size-4 animate-spin" aria-hidden="true" /><FileSearch v-else class="size-4" aria-hidden="true" />{{ state === 'PREVIEWING' ? '正在识别…' : '生成改名预览' }}</Button>
          <template v-else>
            <div v-if="downloadBlockReason" id="rename-download-blockers" role="alert" class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-950">
              <p class="font-semibold">{{ downloadBlockReason }}</p>
              <template v-if="preview.summary.error">
                <ul class="mt-2 max-h-48 space-y-2 overflow-y-auto">
                  <li v-for="(item, index) in blockingFiles" :key="index" class="break-all"><strong>{{ item.source_file_name }}</strong><p>{{ item.issues.filter(issue => issue.code !== 'PDF_RENAME_OCR_REVIEW_REQUIRED').map(issue => issue.message).join('；') || '识别或文件名校验失败。' }}</p></li>
                </ul>
                <p class="mt-2">勾选复核不会跳过错误。识别异常可在对应行人工改名并确认放行，再应用修改；重名、损坏等问题仍须处理。</p>
              </template>
            </div>
            <Button class="w-full" size="lg" :disabled="!canExecute" :aria-describedby="downloadBlockReason ? 'rename-download-blockers' : undefined" @click="executeRename"><LoaderCircle v-if="state === 'EXECUTING'" class="size-4 animate-spin" aria-hidden="true" /><Download v-else class="size-4" aria-hidden="true" />{{ state === 'EXECUTING' ? '正在生成…' : '确认并下载 ZIP' }}</Button>
            <Button class="w-full" variant="outline" :disabled="!canPreview" @click="createPreview"><RotateCcw class="size-4" aria-hidden="true" />{{ state === 'PREVIEWING' ? '正在识别…' : manualDirty ? '应用人工改名并重新预览' : '重新识别预览' }}</Button>
          </template>
        </div>
      </aside>
    </div>
  </div>
</template>
