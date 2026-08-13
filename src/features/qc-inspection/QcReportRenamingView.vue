<script setup lang="ts">
import { AlertTriangle, ArrowDown, ArrowUp, CheckCircle2, Download, FileArchive, Plus, Trash2 } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { qcInspectionApi, type QcRenameBatch, type QcRenameGroupInput } from '@/api/qcInspection'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import { useQcInspectionWorkspace } from './context'

interface RenameGroupDraft extends QcRenameGroupInput {
  pdfFile: File | null
  imageFiles: File[]
}

const context = useQcInspectionWorkspace()
const groups = ref<RenameGroupDraft[]>([])
const previewBatch = ref<QcRenameBatch | null>(null)
const previewing = ref(false)
const executing = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const MAX_RENAME_GROUPS = 39

function createGroup(): RenameGroupDraft {
  return {
    group_id: `report-group-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    is_caixing: false,
    export_country: '',
    report_number: '',
    item_number: '',
    customer_po_no: '',
    quantity: '',
    actual_inspection_date: '',
    files: [],
    pdfFile: null,
    imageFiles: [],
  }
}

function addGroup() {
  if (groups.value.length >= MAX_RENAME_GROUPS) {
    errorMessage.value = `单批最多添加 ${MAX_RENAME_GROUPS} 个报告组。`
    return
  }
  const hadPreview = Boolean(previewBatch.value)
  groups.value.push(createGroup())
  previewBatch.value = null
  errorMessage.value = ''
  successMessage.value = hadPreview ? '报告组已变化，请重新生成改名预览。' : ''
}

function removeGroup(index: number) {
  const hadPreview = Boolean(previewBatch.value)
  groups.value.splice(index, 1)
  previewBatch.value = null
  successMessage.value = hadPreview ? '报告组已变化，请重新生成改名预览。' : ''
}

function onPdfChange(group: RenameGroupDraft, event: Event) {
  const hadPreview = Boolean(previewBatch.value)
  const file = (event.target as HTMLInputElement).files?.[0] ?? null
  group.pdfFile = file && /\.pdf$/i.test(file.name) ? file : null
  previewBatch.value = null
  successMessage.value = hadPreview ? 'PDF 已变化，请重新生成改名预览。' : ''
}

function onImagesChange(group: RenameGroupDraft, event: Event) {
  const hadPreview = Boolean(previewBatch.value)
  group.imageFiles = [...((event.target as HTMLInputElement).files ?? [])].filter((file) => /\.jpe?g$/i.test(file.name))
  previewBatch.value = null
  errorMessage.value = ''
  successMessage.value = hadPreview ? 'JPG/JPEG 已变化，请重新生成改名预览。' : ''
}

function moveImage(group: RenameGroupDraft, index: number, direction: -1 | 1) {
  const target = index + direction
  if (target < 0 || target >= group.imageFiles.length) return
  const hadPreview = Boolean(previewBatch.value)
  const [file] = group.imageFiles.splice(index, 1)
  if (file) group.imageFiles.splice(target, 0, file)
  previewBatch.value = null
  successMessage.value = hadPreview ? '图片顺序已变化，请重新生成改名预览。' : ''
}

function validateGroups() {
  if (!groups.value.length) return '请先选择 PDF/JPG 文件。'
  if (groups.value.length > MAX_RENAME_GROUPS) return `单批最多添加 ${MAX_RENAME_GROUPS} 个报告组。`
  for (const group of groups.value) {
    if (!group.pdfFile || group.imageFiles.length < 1) return `报告组 ${groups.value.indexOf(group) + 1} 必须明确选择 1 个 PDF 和至少 1 张 JPG/JPEG。`
    if (!group.item_number.trim()) return `请填写报告组 ${groups.value.indexOf(group) + 1} 的客户货号。`
    if (!group.customer_po_no.trim()) return `请填写报告组 ${groups.value.indexOf(group) + 1} 的 PO。`
    if (!group.actual_inspection_date) return `请选择报告组 ${groups.value.indexOf(group) + 1} 的实际验货日期。`
    if (group.is_caixing) {
      if (!group.report_number?.trim()) return `请填写彩星报告组 ${groups.value.indexOf(group) + 1} 的报告号。`
      if (!/^\d+$/.test(group.quantity?.trim() ?? '')) return `彩星报告组 ${groups.value.indexOf(group) + 1} 的数量必须为纯数字。`
    } else if (!/^[A-Za-z]{2,3}$/.test(group.export_country?.trim() ?? '')) {
      return `非彩星报告组 ${groups.value.indexOf(group) + 1} 必须填写 2–3 位英文国家代码。`
    }
  }
  return ''
}

const previewGroups = computed(() => previewBatch.value?.groups ?? [])
const hasValidPreviewGroup = computed(() => previewGroups.value.some((group) => group.success))

watch(groups, () => {
  if (!previewBatch.value) return
  previewBatch.value = null
  successMessage.value = '命名字段或文件顺序已变化，请重新生成改名预览。'
}, { deep: true })

async function previewRename() {
  if (!context.canRenamePreview.value) return
  errorMessage.value = validateGroups()
  successMessage.value = ''
  if (errorMessage.value) return
  previewing.value = true
  try {
    const uploads: Array<{ fileId: string; file: File }> = []
    const metadataGroups = groups.value.map(({ pdfFile, imageFiles, ...group }, groupIndex) => {
      const pdfId = `${group.group_id}-pdf-${groupIndex}`
      uploads.push({ fileId: pdfId, file: pdfFile! })
      const imageMetadata = imageFiles.map((file, imageIndex) => {
        const fileId = `${group.group_id}-jpg-${imageIndex + 1}`
        uploads.push({ fileId, file })
        return { file_id: fileId, source_file_name: file.name, sequence: imageIndex + 1 }
      })
      return {
        ...group,
        files: [
          { file_id: pdfId, source_file_name: pdfFile!.name },
          ...imageMetadata,
        ],
        export_country: group.export_country?.trim().toUpperCase(),
        item_number: group.item_number.trim(),
        customer_po_no: group.customer_po_no.trim(),
        quantity: group.quantity?.trim(),
        report_number: group.report_number?.trim(),
      }
    })
    previewBatch.value = await qcInspectionApi.previewRenameBatch(
      uploads,
      metadataGroups,
      context.factoryId.value,
    )
    successMessage.value = '改名预览已生成。请核对每个报告组的原名、目标名和校验结果。'
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    previewing.value = false
  }
}

function saveBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName
  anchor.click()
  URL.revokeObjectURL(url)
}

async function executeRename() {
  if (!previewBatch.value || !context.canRenameExecute.value || !hasValidPreviewGroup.value) return
  executing.value = true
  errorMessage.value = ''
  try {
    const result = await qcInspectionApi.executeRenameBatch(previewBatch.value.id, context.factoryId.value, previewBatch.value.revision)
    saveBlob(result.blob, result.fileName)
    successMessage.value = '已生成改名后的 ZIP。原始文件没有被覆盖。'
    await context.refresh()
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    executing.value = false
  }
}
</script>

<template>
  <div class="space-y-6">
    <SectionPanel title="验货报告批量改名" subtitle="上传不可变副本，预览并确认后生成改名 ZIP；系统不会覆盖用户原文件。">
      <div class="grid gap-4 md:grid-cols-3">
        <div class="rounded-xl border border-slate-200 bg-slate-50 p-4"><p class="text-xs font-semibold text-slate-500">非彩星</p><p class="mt-2 text-sm font-semibold text-slate-900">国家代码_客户货号_PO_实际验货日</p></div>
        <div class="rounded-xl border border-slate-200 bg-slate-50 p-4"><p class="text-xs font-semibold text-slate-500">彩星</p><p class="mt-2 text-sm font-semibold text-slate-900">报告号_客户货号_PO_数量_实际验货日</p></div>
        <div class="rounded-xl border border-slate-200 bg-slate-50 p-4"><p class="text-xs font-semibold text-slate-500">统一规则</p><p class="mt-2 text-sm font-semibold text-slate-900">YYYYMMDD · 多 JPG 增加 _01、_02</p></div>
      </div>

      <div v-if="!context.canRenamePreview.value" class="mt-5 rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800">当前为只读访问，不能上传文件或生成改名预览。</div>
      <div v-else class="mt-5 flex flex-col items-start gap-2 rounded-xl border border-slate-200 bg-slate-50 p-5"><p class="text-sm font-semibold text-slate-900">报告组必须由 QC 明确建立</p><p class="text-xs leading-5 text-slate-600">原文件名只用于显示和审计，不参与自动归组。每组单独选择 1 个 PDF 和有序 JPG/JPEG；单批最多 39 组。</p><Button type="button" @click="addGroup"><Plus class="size-4" aria-hidden="true" />添加报告组</Button></div>
    </SectionPanel>

    <SectionPanel v-if="groups.length" title="报告组与命名字段" subtitle="报告组、文件关系和多图顺序由 QC 显式确认；源文件名不参与业务归组。">
      <div class="space-y-4">
        <article v-for="(group, index) in groups" :key="group.group_id" class="rounded-xl border border-slate-200 p-4">
          <div class="flex flex-wrap items-start justify-between gap-3"><div><h3 class="font-semibold text-slate-950">报告组 {{ index + 1 }}</h3><p class="mt-1 text-xs text-slate-500">由 QC 人工确认 PDF 与图片属于同一报告。</p></div><div class="flex items-center gap-2"><StatusPill :label="`${group.pdfFile ? 1 : 0} PDF · ${group.imageFiles.length} JPG`" :tone="group.pdfFile && group.imageFiles.length > 0 ? 'green' : 'red'" compact /><Button type="button" size="icon-sm" variant="ghost" aria-label="删除报告组" @click="removeGroup(index)"><Trash2 class="size-4" /></Button></div></div>
          <div class="mt-4 grid gap-4 lg:grid-cols-2">
            <label class="space-y-1.5"><span class="text-sm font-semibold text-slate-700">选择 1 个 PDF *</span><input type="file" accept=".pdf,application/pdf" class="block w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm file:mr-3 file:rounded file:border-0 file:bg-teal-50 file:px-2 file:py-1" @change="onPdfChange(group, $event)"><span v-if="group.pdfFile" class="block break-all text-xs text-slate-500">{{ group.pdfFile.name }}</span></label>
            <label class="space-y-1.5"><span class="text-sm font-semibold text-slate-700">选择 1 张或多张 JPG/JPEG *</span><input type="file" multiple accept=".jpg,.jpeg,image/jpeg" class="block w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm file:mr-3 file:rounded file:border-0 file:bg-teal-50 file:px-2 file:py-1" @change="onImagesChange(group, $event)"></label>
          </div>
          <ol v-if="group.imageFiles.length" class="mt-3 space-y-2 rounded-xl bg-slate-50 p-3"><li v-for="(image, imageIndex) in group.imageFiles" :key="`${image.name}-${imageIndex}`" class="flex items-center gap-2 rounded-lg bg-white px-3 py-2 text-xs"><b class="text-teal-700">{{ String(imageIndex + 1).padStart(2, '0') }}</b><span class="min-w-0 flex-1 truncate">{{ image.name }}</span><button type="button" :disabled="imageIndex === 0" class="rounded p-1 text-slate-500 hover:bg-slate-100 disabled:opacity-30" aria-label="上移图片" @click="moveImage(group, imageIndex, -1)"><ArrowUp class="size-3.5" /></button><button type="button" :disabled="imageIndex === group.imageFiles.length - 1" class="rounded p-1 text-slate-500 hover:bg-slate-100 disabled:opacity-30" aria-label="下移图片" @click="moveImage(group, imageIndex, 1)"><ArrowDown class="size-3.5" /></button></li></ol>
          <div class="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <label class="space-y-1.5"><span class="text-sm font-semibold text-slate-700">报告类型</span><select v-model="group.is_caixing" class="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-teal-500"><option :value="false">非彩星</option><option :value="true">彩星</option></select></label>
            <label v-if="!group.is_caixing" class="space-y-1.5"><span class="text-sm font-semibold text-slate-700">出口国代码 *</span><input v-model="group.export_country" maxlength="3" placeholder="US" class="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm uppercase outline-none focus:border-teal-500"></label>
            <label v-else class="space-y-1.5"><span class="text-sm font-semibold text-slate-700">报告号 *</span><input v-model="group.report_number" class="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none focus:border-teal-500"></label>
            <label class="space-y-1.5"><span class="text-sm font-semibold text-slate-700">客户货号 *</span><input v-model="group.item_number" class="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none focus:border-teal-500"></label>
            <label class="space-y-1.5"><span class="text-sm font-semibold text-slate-700">PO *</span><input v-model="group.customer_po_no" class="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none focus:border-teal-500" placeholder="保留前导零"></label>
            <label v-if="group.is_caixing" class="space-y-1.5"><span class="text-sm font-semibold text-slate-700">数量 *</span><input v-model="group.quantity" inputmode="numeric" class="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none focus:border-teal-500" placeholder="只填数字"></label>
            <label class="space-y-1.5"><span class="text-sm font-semibold text-slate-700">实际验货日期 *</span><input v-model="group.actual_inspection_date" type="date" class="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none focus:border-teal-500"></label>
          </div>
        </article>
      </div>
      <p v-if="errorMessage" role="alert" class="mt-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"><AlertTriangle class="mt-0.5 size-4 shrink-0" aria-hidden="true" />{{ errorMessage }}</p>
      <p v-if="successMessage" class="mt-4 flex items-start gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800"><CheckCircle2 class="mt-0.5 size-4 shrink-0" aria-hidden="true" />{{ successMessage }}</p>
      <div class="mt-5 flex flex-wrap justify-between gap-3"><Button type="button" variant="outline" :disabled="groups.length >= MAX_RENAME_GROUPS" @click="addGroup"><Plus class="size-4" aria-hidden="true" />{{ groups.length >= MAX_RENAME_GROUPS ? '已达 39 组上限' : '继续添加报告组' }}</Button><Button type="button" :disabled="previewing || !context.canRenamePreview.value" @click="previewRename"><FileArchive class="size-4" aria-hidden="true" />{{ previewing ? '正在校验…' : '生成改名预览' }}</Button></div>
    </SectionPanel>

    <SectionPanel v-if="previewBatch" title="改名结果预览" subtitle="组内任一文件失败时整组保持原名；其他正常报告组可继续。">
      <div class="space-y-4">
        <article v-for="group in previewGroups" :key="group.group_id" class="overflow-hidden rounded-xl border border-slate-200">
          <div class="flex items-center justify-between gap-3 bg-slate-50 px-4 py-3"><b class="text-sm text-slate-900">{{ group.group_id }}</b><StatusPill :label="group.success ? '校验通过' : '整组跳过'" :tone="group.success ? 'green' : 'red'" compact /></div>
          <div class="divide-y divide-slate-100">
            <div v-for="file in group.files" :key="file.source_file_name" class="grid gap-2 px-4 py-3 text-sm sm:grid-cols-2"><span class="break-all text-slate-600">{{ file.source_file_name }}</span><span class="break-all font-semibold text-slate-900">{{ file.target_file_name }}</span></div>
          </div>
          <ul v-if="group.issues.length" class="border-t border-red-100 bg-red-50 px-4 py-3 text-xs leading-5 text-red-800"><li v-for="issue in group.issues" :key="`${issue.code}-${issue.source_file_name}`">• {{ issue.message }}<span v-if="issue.source_file_name">（{{ issue.source_file_name }}）</span></li></ul>
        </article>
      </div>
      <div class="mt-5 flex flex-col items-end gap-2"><Button type="button" :disabled="!context.canRenameExecute.value || !hasValidPreviewGroup || executing" @click="executeRename"><Download class="size-4" aria-hidden="true" />{{ executing ? '正在生成 ZIP…' : '确认并下载改名 ZIP' }}</Button><p v-if="!context.canRenameExecute.value" class="text-xs text-amber-700">当前账号只有预览权限，不能执行并下载。</p><p v-else-if="!hasValidPreviewGroup" class="text-xs text-red-700">没有校验通过的报告组，不能生成 ZIP。</p></div>
    </SectionPanel>
  </div>
</template>
