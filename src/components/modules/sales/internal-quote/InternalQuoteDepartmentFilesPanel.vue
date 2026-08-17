<script setup lang="ts">
import { Download, File, FileImage, FileSpreadsheet, FileText, LoaderCircle, TriangleAlert } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { internalQuoteApi, internalQuoteAttachmentPreviewUrl, type ApiInternalQuoteAttachmentContentPreview } from '@/api/internalQuote'
import type { InternalQuoteAttachmentRecord } from '@/types/internalQuoteDesk'

const props = defineProps<{
  quoteId: string
  sectionLabel: string
  attachments: InternalQuoteAttachmentRecord[]
  requestedAttachmentId?: string
}>()
const emit = defineEmits<{
  download: [attachment: InternalQuoteAttachmentRecord]
  select: [attachmentId: string]
}>()

const selectedAttachmentId = ref('')
const loading = ref(false)
const errorMessage = ref('')
const contentPreview = ref<ApiInternalQuoteAttachmentContentPreview>()
const activeSheetIndex = ref(0)
let loadVersion = 0

const selectedAttachment = computed(() => (
  props.attachments.find((attachment) => attachment.id === selectedAttachmentId.value)
))
const extension = computed(() => {
  const name = selectedAttachment.value?.fileName ?? ''
  const dot = name.lastIndexOf('.')
  return dot >= 0 ? name.slice(dot).toLowerCase() : ''
})
const previewKind = computed<'excel' | 'word' | 'pdf' | 'image' | 'other'>(() => {
  if (['.xlsx', '.xlsm', '.xls'].includes(extension.value)) return 'excel'
  if (['.docx', '.doc'].includes(extension.value)) return 'word'
  if (extension.value === '.pdf') return 'pdf'
  if (selectedAttachment.value?.contentType.startsWith('image/') || ['.jpg', '.jpeg', '.png', '.webp'].includes(extension.value)) return 'image'
  return 'other'
})
const inlinePreviewUrl = computed(() => selectedAttachment.value
  ? internalQuoteAttachmentPreviewUrl(props.quoteId, selectedAttachment.value.id)
  : '')
const activeSheet = computed(() => contentPreview.value?.sheets[activeSheetIndex.value])
const visibleColumnCount = computed(() => Math.min(
  activeSheet.value?.total_columns ?? 0,
  Math.max(0, ...((activeSheet.value?.rows ?? []).map((row) => row.length))),
))
const columnIndexes = computed(() => Array.from({ length: visibleColumnCount.value }, (_, index) => index))

watch(() => [props.requestedAttachmentId, props.attachments.map((attachment) => attachment.id).join('|')] as const, ([requestedId]) => {
  const requestedExists = requestedId && props.attachments.some((attachment) => attachment.id === requestedId)
  const currentExists = props.attachments.some((attachment) => attachment.id === selectedAttachmentId.value)
  const nextId = requestedExists ? requestedId : currentExists ? selectedAttachmentId.value : props.attachments[0]?.id ?? ''
  if (selectedAttachmentId.value !== nextId) selectedAttachmentId.value = nextId
}, { immediate: true })

watch(selectedAttachment, async (attachment) => {
  const version = ++loadVersion
  errorMessage.value = ''
  contentPreview.value = undefined
  activeSheetIndex.value = 0
  if (!attachment) return
  emit('select', attachment.id)
  if (!['excel', 'word'].includes(previewKind.value)) return
  loading.value = true
  try {
    const preview = await internalQuoteApi.previewAttachmentContent(props.quoteId, attachment.id)
    if (version === loadVersion) contentPreview.value = preview
  } catch {
    if (version === loadVersion) errorMessage.value = '当前附件无法生成内容预览，请下载原文件核对。'
  } finally {
    if (version === loadVersion) loading.value = false
  }
}, { immediate: true })

function chooseAttachment(event: Event) {
  selectedAttachmentId.value = (event.target as HTMLSelectElement).value
}

function columnLabel(index: number) {
  let value = index + 1
  let label = ''
  while (value > 0) {
    value -= 1
    label = String.fromCharCode(65 + (value % 26)) + label
    value = Math.floor(value / 26)
  }
  return label
}

function displayCell(value: unknown) {
  if (value === null || value === undefined) return ''
  if (typeof value === 'boolean') return value ? 'TRUE' : 'FALSE'
  return String(value)
}

function fileIcon() {
  if (previewKind.value === 'excel') return FileSpreadsheet
  if (previewKind.value === 'word' || previewKind.value === 'pdf') return FileText
  if (previewKind.value === 'image') return FileImage
  return File
}
</script>

<template>
  <section class="department-files-panel" :aria-label="`${sectionLabel}资料预览`">
    <header>
      <div><strong>{{ sectionLabel }}资料</strong><span>仅显示分配给当前部门的附件</span></div>
      <b>{{ attachments.length }}</b>
    </header>

    <div v-if="attachments.length" class="department-file-picker">
      <component :is="fileIcon()" />
      <select :value="selectedAttachmentId" aria-label="选择部门资料" @change="chooseAttachment">
        <option v-for="attachment in attachments" :key="attachment.id" :value="attachment.id">{{ attachment.fileName }}</option>
      </select>
      <button v-if="selectedAttachment" type="button" :title="`下载 ${selectedAttachment.fileName}`" aria-label="下载当前资料" @click="emit('download', selectedAttachment)"><Download /></button>
    </div>

    <div v-if="!attachments.length" class="department-file-empty">
      <File /><strong>暂无部门资料</strong><span>上传附件并分配给{{ sectionLabel }}后，可在这里直接预览。</span>
    </div>
    <div v-else-if="loading" class="department-file-state"><LoaderCircle class="spinning" /><strong>正在生成预览…</strong><span>只读取有限内容，不修改原文件。</span></div>
    <div v-else-if="errorMessage" class="department-file-state error"><TriangleAlert /><strong>预览失败</strong><span>{{ errorMessage }}</span></div>

    <div v-else-if="previewKind === 'image'" class="department-image-preview"><img :src="inlinePreviewUrl" :alt="`${selectedAttachment?.fileName} 预览`"></div>
    <iframe v-else-if="previewKind === 'pdf'" class="department-pdf-preview" :src="inlinePreviewUrl" :title="`${selectedAttachment?.fileName} PDF 预览`" />

    <template v-else-if="previewKind === 'excel' && contentPreview">
      <nav class="department-sheet-tabs" aria-label="附件工作表">
        <button v-for="(sheet,index) in contentPreview.sheets" :key="`${sheet.name}-${index}`" type="button" :class="{ active: activeSheetIndex === index }" @click="activeSheetIndex = index">{{ sheet.name }}</button>
      </nav>
      <div v-if="activeSheet" class="department-excel-meta"><span>{{ activeSheet.total_rows }} 行 × {{ activeSheet.total_columns }} 列</span><strong v-if="activeSheet.truncated">仅显示前 200 行、40 列</strong></div>
      <div v-if="activeSheet?.rows.length" class="department-excel-scroll">
        <table><thead><tr><th /><th v-for="columnIndex in columnIndexes" :key="columnIndex">{{ columnLabel(columnIndex) }}</th></tr></thead><tbody><tr v-for="(row,rowIndex) in activeSheet.rows" :key="rowIndex"><th>{{ rowIndex + 1 }}</th><td v-for="columnIndex in columnIndexes" :key="columnIndex" :title="displayCell(row[columnIndex])">{{ displayCell(row[columnIndex]) }}</td></tr></tbody></table>
      </div>
      <div v-else class="department-file-state compact"><strong>该工作表为空</strong><span>请选择其他工作表或下载原文件。</span></div>
    </template>

    <div v-else-if="previewKind === 'word' && contentPreview" class="department-word-preview">
      <p v-for="warning in contentPreview.warnings" :key="warning" class="word-preview-warning"><TriangleAlert />{{ warning }}</p>
      <article v-if="contentPreview.paragraphs.length"><p v-for="(paragraph,index) in contentPreview.paragraphs" :key="index">{{ paragraph }}</p></article>
      <div v-else class="department-file-state compact"><strong>没有提取到可读文字</strong><span>请下载原文件查看完整内容和排版。</span></div>
    </div>

    <div v-else-if="previewKind === 'other'" class="department-file-state"><File /><strong>该格式暂不支持内嵌显示</strong><span>可以下载原文件查看。</span></div>

    <footer v-if="selectedAttachment"><span>{{ Math.max(1, Math.ceil(selectedAttachment.sizeBytes / 1024)) }} KB</span><span>{{ selectedAttachment.uploadedBy }}</span><span>{{ selectedAttachment.uploadedAt }}</span></footer>
  </section>
</template>

<style scoped>
.department-files-panel{display:grid;min-height:calc(100vh - 108px);overflow:hidden;border:1px solid #dbe5ea;border-radius:11px;background:#fff;grid-template-rows:auto auto minmax(0,1fr) auto}.department-files-panel>header{display:flex;align-items:center;justify-content:space-between;gap:10px;border-bottom:1px solid #ccfbf1;background:linear-gradient(105deg,#134e4a,#0f766e);padding:11px 12px}.department-files-panel>header>div{display:grid}.department-files-panel>header strong{color:#fff;font-size:13px}.department-files-panel>header span{margin-top:2px;color:#ccfbf1;font-size:10px}.department-files-panel>header b{display:grid;min-width:26px;height:26px;place-items:center;border-radius:999px;background:#fff;color:#0f766e;font-size:11px}
.department-file-picker{display:grid;grid-template-columns:20px minmax(0,1fr) 32px;align-items:center;gap:7px;border-bottom:1px solid #e2e8f0;background:#f8fafc;padding:8px}.department-file-picker>svg{width:17px;color:#0f766e}.department-file-picker select{min-width:0;height:34px;border:1px solid #cbd5e1;border-radius:7px;background:#fff;padding:0 7px;color:#334155;font-size:11px;font-weight:700}.department-file-picker button{display:grid;width:32px;height:32px;place-items:center;border:1px solid #99f6e4;border-radius:7px;background:#fff;color:#0f766e}.department-file-picker button svg{width:14px}
.department-file-empty,.department-file-state{display:grid;min-height:260px;place-content:center;justify-items:center;gap:7px;padding:24px;color:#64748b;text-align:center}.department-file-empty svg,.department-file-state svg{width:30px;color:#0f766e}.department-file-empty strong,.department-file-state strong{color:#334155;font-size:13px}.department-file-empty span,.department-file-state span{max-width:260px;font-size:11px;line-height:1.55}.department-file-state.error svg,.department-file-state.error strong{color:#b91c1c}.department-file-state.compact{min-height:160px}.spinning{animation:department-file-spin .8s linear infinite}
.department-image-preview{display:grid;min-height:0;place-items:center;overflow:auto;background:#e2e8f0;padding:10px}.department-image-preview img{display:block;max-width:100%;max-height:calc(100vh - 235px);border-radius:7px;background:#fff;object-fit:contain;box-shadow:0 8px 24px rgb(15 23 42/.16)}.department-pdf-preview{width:100%;height:100%;min-height:520px;border:0;background:#e2e8f0}
.department-sheet-tabs{display:flex;overflow-x:auto;gap:4px;border-bottom:1px solid #e2e8f0;padding:6px}.department-sheet-tabs button{height:28px;flex:0 0 auto;border:1px solid #cbd5e1;border-radius:6px;background:#fff;padding:0 8px;color:#475569;font-size:10px;font-weight:800}.department-sheet-tabs button.active{border-color:#0f766e;background:#0f766e;color:#fff}.department-excel-meta{display:flex;flex-wrap:wrap;justify-content:space-between;gap:6px;border-bottom:1px solid #e2e8f0;background:#f0fdfa;padding:6px 8px;color:#0f766e;font-size:10px}.department-excel-meta strong{color:#b45309}.department-excel-scroll{min-height:0;overflow:auto}.department-excel-scroll table{border-collapse:separate;border-spacing:0;min-width:100%;font-size:10px}.department-excel-scroll th,.department-excel-scroll td{height:25px;max-width:220px;border-right:1px solid #e2e8f0;border-bottom:1px solid #e2e8f0;padding:3px 6px;overflow:hidden;color:#334155;text-overflow:ellipsis;white-space:nowrap}.department-excel-scroll thead th{position:sticky;z-index:2;top:0;min-width:72px;background:#e2e8f0;text-align:center}.department-excel-scroll tbody th{position:sticky;z-index:1;left:0;width:36px;min-width:36px;background:#f1f5f9;color:#64748b;text-align:right}.department-excel-scroll thead th:first-child{left:0;z-index:3;width:36px;min-width:36px}
.department-word-preview{min-height:0;overflow:auto;background:#e2e8f0;padding:12px}.department-word-preview article{min-height:100%;border-radius:5px;background:#fff;padding:24px 28px;box-shadow:0 6px 20px rgb(15 23 42/.12)}.department-word-preview article p{margin:0 0 10px;color:#334155;font-size:12px;line-height:1.75;white-space:pre-wrap}.word-preview-warning{display:flex;align-items:flex-start;gap:5px;margin:0 0 8px;border:1px solid #fde68a;border-radius:7px;background:#fffbeb;padding:7px;color:#92400e;font-size:10px;line-height:1.45}.word-preview-warning svg{width:13px;flex:0 0 auto}
.department-files-panel>footer{display:flex;flex-wrap:wrap;gap:8px;border-top:1px solid #e2e8f0;background:#f8fafc;padding:7px 9px;color:#94a3b8;font-size:9px}@keyframes department-file-spin{to{transform:rotate(360deg)}}
</style>
