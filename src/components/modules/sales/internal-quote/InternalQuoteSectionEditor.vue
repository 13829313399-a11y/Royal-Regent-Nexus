<script setup lang="ts">
import { AlertCircle, CheckCircle2, ChevronDown, Download, FileSpreadsheet, FileUp, Info, LockKeyhole, Paperclip, RefreshCw, Save, Send, XCircle } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import type { ApiInternalQuoteImportPreview, ApiInternalQuoteSection } from '@/api/internalQuote'
import InternalQuoteSectionForm from './InternalQuoteSectionForm.vue'
import { cloneInternalQuotePayload, normalizeInternalQuotePayload } from '@/lib/internalQuoteSectionPayload'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import type { InternalQuote, InternalQuoteSection, InternalQuoteSectionCode, InternalQuoteSectionStatus } from '@/types/internalQuoteDesk'

const props = defineProps<{
  quote: InternalQuote
  section: InternalQuoteSection
  canEdit: boolean
  canReview: boolean
}>()

const quoteStore = useInternalQuoteDeskStore()
const draftPayload = ref<Record<string, unknown>>({})
const baselinePayload = ref('')
const importPreview = ref<ApiInternalQuoteImportPreview>()
const importMode = ref<'append' | 'replace'>('append')
const actionReason = ref('')
const reasonAction = ref<'reject' | 'na' | 'reopen'>()
const localMessage = ref('')
const localError = ref('')
const importInput = ref<HTMLInputElement>()
const attachmentInput = ref<HTMLInputElement>()
const selectedImportType = ref<ApiInternalQuoteImportPreview['import_type']>()

const statusMeta: Record<InternalQuoteSectionStatus, { label: string; tone: string }> = {
  draft: { label: '草稿', tone: 'slate' }, pending_review: { label: '待主管审核', tone: 'amber' },
  approved: { label: '审核通过', tone: 'green' }, rejected: { label: '已退回', tone: 'red' },
  na_pending: { label: '不适用待审', tone: 'amber' }, not_applicable: { label: '不适用', tone: 'slate' },
}

const mutable = computed(() => ['draft', 'rejected'].includes(props.section.status))
const editable = computed(() => props.canEdit && mutable.value && !quoteStore.submitting)
const reviewable = computed(() => props.canReview && ['pending_review', 'na_pending'].includes(props.section.status) && !quoteStore.submitting)
const canReopen = computed(() => props.canEdit && ['approved', 'not_applicable'].includes(props.section.status) && !quoteStore.submitting)
const isDirty = computed(() => JSON.stringify(draftPayload.value) !== baselinePayload.value)
type ImportOption = { type: ApiInternalQuoteImportPreview['import_type']; label: string; buttonLabel: string }
const importOptions = computed<ImportOption[]>(() => ({
  engineering: [
    { type: 'hardware', label: '五金报价单', buttonLabel: '五金 Excel 导入' },
    { type: 'mold', label: '模具报价单 / 合同', buttonLabel: '模具 Excel 导入' },
  ],
  electronic: [{ type: 'electronic', label: '电子报价单', buttonLabel: 'Excel 预览导入' }],
  painting: [{ type: 'painting', label: '喷油核价表', buttonLabel: 'Excel 预览导入' }],
  sewing: [{ type: 'sewing', label: '车缝报价单', buttonLabel: 'Excel 预览导入' }],
  assembly: [{ type: 'assembly', label: '生产排拉工序表', buttonLabel: 'Excel 预览导入' }],
} as Partial<Record<InternalQuoteSectionCode, ImportOption[]>>)[props.section.code] ?? [])

function importOption(type: ApiInternalQuoteImportPreview['import_type']) {
  return importOptions.value.find((option) => option.type === type)
}

function openImport(option: ImportOption) {
  selectedImportType.value = option.type
  importInput.value?.click()
}

const reasonActionAllowed = computed(() => {
  if (reasonAction.value === 'reject') return reviewable.value
  if (reasonAction.value === 'na') return editable.value
  if (reasonAction.value === 'reopen') return canReopen.value
  return false
})

watch(() => [props.quote.id, props.section.code, props.section.revision, props.section.updatedAt, props.canEdit, props.canReview] as const, () => {
  draftPayload.value = normalizeInternalQuotePayload(props.section.code, props.section.payload)
  baselinePayload.value = JSON.stringify(draftPayload.value)
  importPreview.value = undefined
  selectedImportType.value = undefined
  reasonAction.value = undefined
  actionReason.value = ''
  localMessage.value = ''
  localError.value = ''
}, { immediate: true })

function resetFeedback() { localMessage.value = ''; localError.value = '' }
function errorText(error: unknown) { return error instanceof Error ? error.message : '操作失败。' }

async function saveDraft(showMessage = true) {
  resetFeedback()
  try {
    const result = await quoteStore.saveSection(props.quote.id, props.section.code, props.section.revision, cloneInternalQuotePayload(props.section.code, draftPayload.value)) as ApiInternalQuoteSection
    baselinePayload.value = JSON.stringify(draftPayload.value)
    if (showMessage) localMessage.value = `${props.section.label}草稿已保存，服务端已生成 revision ${result.revision} 并重新计算。`
    return result
  } catch (error) {
    localError.value = errorText(error)
    return undefined
  }
}

async function submitSection() {
  resetFeedback()
  try {
    let revision = props.section.revision
    if (isDirty.value) {
      const saved = await quoteStore.saveSection(props.quote.id, props.section.code, revision, cloneInternalQuotePayload(props.section.code, draftPayload.value)) as ApiInternalQuoteSection
      revision = saved.revision
    }
    await quoteStore.submitSection(props.quote.id, props.section.code, revision)
    localMessage.value = `${props.section.label}已提交主管审核。`
  } catch (error) { localError.value = errorText(error) }
}

async function approveSection() {
  resetFeedback()
  try {
    await quoteStore.reviewSection(props.quote.id, props.section.code, props.section.revision, 'approve')
    localMessage.value = props.section.status === 'na_pending' ? '不适用申请已批准。' : `${props.section.label}已审核通过。`
  } catch (error) { localError.value = errorText(error) }
}

function openReason(action: 'reject' | 'na' | 'reopen') { reasonAction.value = action; actionReason.value = ''; resetFeedback() }

async function confirmReasonAction() {
  if (!reasonAction.value || !actionReason.value.trim()) return
  if (!reasonActionAllowed.value) {
    reasonAction.value = undefined
    actionReason.value = ''
    localError.value = '当前账号没有执行该操作的权限。'
    return
  }
  const reason = actionReason.value.trim()
  resetFeedback()
  try {
    if (reasonAction.value === 'reject') await quoteStore.reviewSection(props.quote.id, props.section.code, props.section.revision, 'reject', reason)
    else if (reasonAction.value === 'na') await quoteStore.requestSectionNa(props.quote.id, props.section.code, props.section.revision, reason)
    else await quoteStore.reopenSection(props.quote.id, props.section.code, props.section.revision, reason)
    localMessage.value = reasonAction.value === 'reject' ? '审核已退回并留存原因。' : reasonAction.value === 'na' ? '不适用申请已提交主管审核。' : '分段已合法重开。'
    reasonAction.value = undefined
    actionReason.value = ''
  } catch (error) { localError.value = errorText(error) }
}

async function handleImportFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  const importType = selectedImportType.value
  input.value = ''
  selectedImportType.value = undefined
  if (!file || !importType || !editable.value) return
  resetFeedback()
  try {
    importPreview.value = await quoteStore.previewImport(props.quote.id, importType, file)
    localMessage.value = `${file.name} 已完成预览；尚未写入正式分段。`
  } catch (error) { localError.value = errorText(error) }
}

async function confirmImport() {
  if (!importPreview.value || !editable.value) {
    importPreview.value = undefined
    localError.value = '当前账号没有确认导入该分段的权限。'
    return
  }
  resetFeedback()
  try {
    await quoteStore.confirmImport(props.quote.id, importPreview.value.batch_id, importPreview.value.target_revision, importMode.value)
    localMessage.value = `预览批次已${importMode.value === 'append' ? '追加' : '替换'}写入，分段已重新计算。`
    importPreview.value = undefined
  } catch (error) { localError.value = errorText(error) }
}

async function handleAttachment(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || !props.canEdit) return
  resetFeedback()
  try {
    await quoteStore.uploadAttachment(props.quote.id, props.section.code, file)
    localMessage.value = `附件 ${file.name} 已校验并留存。`
  } catch (error) { localError.value = errorText(error) }
}

async function downloadAttachment(id: string, fileName: string) {
  resetFeedback()
  try { await quoteStore.downloadAttachment(props.quote.id, id, fileName) }
  catch (error) { localError.value = errorText(error) }
}
</script>

<template>
  <section class="quote-section-editor">
    <header class="quote-editor-head">
      <div><div class="quote-editor-title-row"><h2>{{ section.label }}核价明细</h2><span class="quote-editor-status" :class="`tone-${statusMeta[section.status].tone}`"><i />{{ statusMeta[section.status].label }}</span><span class="quote-revision">revision {{ section.revision }}</span><span v-if="isDirty" class="dirty">有未保存修改</span></div><p>{{ section.formulaHint }}</p></div>
      <div class="quote-editor-tools">
        <button v-for="option in importOptions" :key="option.type" type="button" :disabled="!editable || quoteStore.fileBusy" @click="openImport(option)"><FileUp />{{ option.buttonLabel }}<ChevronDown /></button>
        <button type="button" :disabled="!props.canEdit || quoteStore.fileBusy" @click="attachmentInput?.click()"><Paperclip />上传附件</button>
        <input ref="importInput" class="sr-only" type="file" accept=".xlsx,.xlsm" @change="handleImportFile">
        <input ref="attachmentInput" class="sr-only" type="file" accept=".xlsx,.xlsm,.xls,.pdf,.doc,.docx,.png,.jpg,.jpeg,.webp" @change="handleAttachment">
      </div>
    </header>

    <div v-if="!editable" class="quote-lock-banner"><LockKeyhole />{{ mutable ? '当前账号没有本分段编辑权限，页面保持只读。' : `当前分段为“${statusMeta[section.status].label}”，需退回或合法重开后才能编辑。` }}</div>
    <div class="quote-dependency-strip"><span><Info />依赖数据</span><b v-for="dependency in section.dependencies" :key="dependency">{{ dependency }}</b><em>公式：{{ quote.formulaVersion }} · 计算 {{ section.calculationStatus }} · 依赖 {{ section.dependencyStatus }}</em></div>
    <div v-if="section.warnings.length" class="quote-warning-list"><p v-for="warning in section.warnings" :key="warning"><AlertCircle />{{ warning }}</p></div>

    <section v-if="importPreview && editable" class="quote-import-preview">
      <header><div><FileSpreadsheet /><span><strong>{{ importOption(importPreview.import_type)?.label }} · {{ importPreview.source_file_name }}</strong><small>{{ importPreview.sheet_name }} · 表头第 {{ importPreview.header_row }} 行 · 识别 {{ importPreview.row_count }} 行 · 预览不会修改正式数据</small></span></div><button type="button" aria-label="关闭导入预览" @click="importPreview = undefined"><XCircle /></button></header>
      <div class="preview-metrics"><span>当前 {{ Number(importPreview.diff_summary.existing_rows ?? 0) }} 行</span><span>导入 {{ Number(importPreview.diff_summary.imported_rows ?? 0) }} 行</span><span>追加后 {{ Number(importPreview.diff_summary.append_result_rows ?? 0) }} 行</span><span>替换后 {{ Number(importPreview.diff_summary.replace_result_rows ?? 0) }} 行</span></div>
      <div v-if="importPreview.warnings.length" class="preview-warnings"><p v-for="warning in importPreview.warnings" :key="warning"><AlertCircle />{{ warning }}</p></div>
      <footer><label><input v-model="importMode" type="radio" value="append">追加</label><label><input v-model="importMode" type="radio" value="replace">替换</label><span /><button type="button" class="secondary" @click="importPreview = undefined">取消</button><button type="button" class="primary" :disabled="quoteStore.submitting || !editable" @click="confirmImport">确认{{ importMode === 'append' ? '追加' : '替换' }}</button></footer>
    </section>

    <InternalQuoteSectionForm v-model="draftPayload" :code="section.code" :customer="quote.customer" :rmb-hkd-rate="quote.fxRmbHkd" :disabled="!editable" />

    <section class="calculation-snapshot"><header><strong>服务端权威计算快照</strong><span>保存后由 {{ quote.formulaVersion }} 重算；前端不生成正式金额</span></header><div class="snapshot-table-scroll"><table><thead><tr><th>项目</th><th>类型</th><th>公式口径</th><th>金额 HKD</th></tr></thead><tbody><tr v-for="line in section.lines" :key="line.id"><td>{{ line.item }}</td><td>{{ line.specification }}</td><td>{{ line.formula }}</td><td>{{ line.amountHkd.toFixed(4) }}</td></tr><tr v-if="!section.lines.length"><td colspan="4" class="empty">保存有效明细后显示服务端计算结果</td></tr></tbody><tfoot><tr><td colspan="3">{{ section.label }}权威小计</td><td>HKD {{ section.totalHkd.toFixed(4) }}</td></tr></tfoot></table></div></section>

    <section class="quote-attachments"><header><strong>分段附件</strong><span>扩展名、文件头、大小和 SHA-256 均由服务端校验</span></header><div><button v-for="attachment in section.attachments" :key="attachment.id" type="button" :title="`${attachment.uploadedBy} · ${attachment.uploadedAt} · ${attachment.sha256}`" @click="downloadAttachment(attachment.id, attachment.fileName)"><Paperclip />{{ attachment.fileName }}<Download /></button><em v-if="!section.attachments.length">暂无附件</em></div></section>

    <p v-if="localMessage" class="quote-local-message"><CheckCircle2 />{{ localMessage }}</p>
    <p v-if="localError" class="quote-local-error"><AlertCircle />{{ localError }}</p>

    <section v-if="reasonAction && reasonActionAllowed" class="quote-reason-panel"><div><strong>{{ reasonAction === 'reject' ? '填写退回原因' : reasonAction === 'na' ? '填写不适用原因' : '填写重开原因' }}</strong><span>原因将进入业务操作时间线和不可变审核记录。</span></div><textarea v-model="actionReason" rows="2" placeholder="必须填写原因" /><button type="button" class="secondary" @click="reasonAction = undefined">取消</button><button type="button" class="primary" :disabled="!actionReason.trim() || quoteStore.submitting || !reasonActionAllowed" @click="confirmReasonAction">确认</button></section>

    <footer class="quote-editor-actions"><div><span>最后更新 {{ section.updatedAt }}</span><b>所有写入均携带 revision；409 时保留当前表单，不覆盖他人修改</b></div><div>
      <button v-if="editable" type="button" class="secondary" @click="openReason('na')">申请不适用</button>
      <button v-if="editable" type="button" class="secondary" :disabled="quoteStore.submitting" @click="saveDraft()"><Save />保存草稿</button>
      <button v-if="editable" type="button" class="primary" :disabled="quoteStore.submitting" @click="submitSection"><Send />{{ isDirty ? '保存并提交审核' : '提交分段审核' }}</button>
      <button v-if="reviewable" type="button" class="danger" @click="openReason('reject')"><XCircle />{{ section.status === 'na_pending' ? '退回申请' : '退回' }}</button>
      <button v-if="reviewable" type="button" class="primary" @click="approveSection"><CheckCircle2 />{{ section.status === 'na_pending' ? '批准不适用' : '审核通过' }}</button>
      <button v-if="canReopen" type="button" class="secondary" @click="openReason('reopen')"><RefreshCw />合法重开</button>
    </div></footer>
  </section>
</template>

<style scoped>
.quote-section-editor{min-width:0;overflow:hidden;border:1px solid #dbe5ea;border-radius:13px;background:#fff;box-shadow:0 12px 28px rgb(15 23 42/.05)}.quote-editor-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding:16px;border-bottom:1px solid #e2e8f0}.quote-editor-title-row{display:flex;flex-wrap:wrap;align-items:center;gap:7px}.quote-editor-title-row h2{margin:0;color:#0f172a;font-size:17px;font-weight:900}.quote-editor-head p{margin:6px 0 0;color:#64748b;font-size:12px;line-height:1.55}.quote-editor-status,.quote-revision,.dirty{display:inline-flex;align-items:center;gap:5px;border-radius:999px;padding:4px 7px;font-size:11px;font-weight:900}.quote-editor-status{background:color-mix(in srgb,var(--tone) 10%,white);color:var(--tone)}.quote-editor-status i{width:5px;height:5px;border-radius:99px;background:currentColor}.quote-revision{background:#f1f5f9;color:#64748b;font-family:ui-monospace,SFMono-Regular,Consolas,monospace}.dirty{background:#fff7ed;color:#c2410c}.tone-slate{--tone:#64748b}.tone-amber{--tone:#d97706}.tone-green{--tone:#059669}.tone-red{--tone:#dc2626}.quote-editor-tools{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:6px}.quote-editor-tools button{display:inline-flex;height:34px;align-items:center;gap:5px;border:1px solid #dbe5ea;border-radius:8px;background:#fff;padding:0 10px;color:#475569;font-size:12px;font-weight:800}.quote-editor-tools button:first-child{border-color:#0f766e;background:#0f766e;color:#fff}.quote-editor-tools button:disabled{cursor:not-allowed;opacity:.4}.quote-editor-tools svg{width:14px;height:14px}.quote-lock-banner,.quote-dependency-strip{display:flex;align-items:center;gap:7px;border-bottom:1px solid #e2e8f0;padding:10px 13px;font-size:11px}.quote-lock-banner{background:#fffbeb;color:#92400e}.quote-lock-banner svg{width:14px}.quote-dependency-strip{flex-wrap:wrap;background:#f8fafc;color:#64748b}.quote-dependency-strip>span{display:inline-flex;align-items:center;gap:5px;color:#0f766e;font-weight:900}.quote-dependency-strip svg{width:13px}.quote-dependency-strip b{border:1px solid #dbe5ea;border-radius:999px;background:#fff;padding:3px 6px;color:#475569;font-size:11px}.quote-dependency-strip em{margin-left:auto;color:#94a3b8;font-size:11px;font-style:normal}.quote-warning-list{display:grid;gap:5px;padding:10px 13px;background:#fef2f2}.quote-warning-list p,.preview-warnings p{display:flex;align-items:flex-start;gap:5px;margin:0;color:#b91c1c;font-size:11px}.quote-warning-list svg,.preview-warnings svg{width:13px;flex:0 0 auto}
.quote-import-preview{margin:12px;border:1px solid #bfdbfe;border-radius:10px;background:#eff6ff}.quote-import-preview>header{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 12px}.quote-import-preview>header>div{display:flex;gap:8px}.quote-import-preview>header svg{width:18px;color:#2563eb}.quote-import-preview>header span{display:grid}.quote-import-preview>header strong{color:#1e3a8a;font-size:12px}.quote-import-preview>header small{margin-top:2px;color:#64748b;font-size:11px}.quote-import-preview>header button{border:0;background:transparent;color:#64748b}.preview-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;border-top:1px solid #dbeafe;padding:10px 12px;background:#fff}.preview-metrics span{border-radius:7px;background:#eff6ff;padding:8px;color:#1d4ed8;font-size:11px;text-align:center}.preview-warnings{display:grid;gap:5px;border-top:1px solid #fed7aa;background:#fff7ed;padding:9px 12px}.quote-import-preview>footer{display:flex;align-items:center;gap:10px;border-top:1px solid #dbeafe;padding:9px 12px}.quote-import-preview>footer label{display:flex;align-items:center;gap:4px;color:#475569;font-size:12px}.quote-import-preview>footer span{flex:1}.quote-import-preview>footer button{height:31px;border-radius:7px;padding:0 10px;font-size:12px;font-weight:900}.quote-import-preview .secondary{border:1px solid #cbd5e1;background:#fff;color:#475569}.quote-import-preview .primary{border:1px solid #2563eb;background:#2563eb;color:#fff}
.calculation-snapshot{border-top:1px solid #dbe5ea}.calculation-snapshot>header,.quote-attachments header{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px;padding:11px 13px;background:#f8fafc}.calculation-snapshot header strong,.quote-attachments strong{color:#334155;font-size:12px}.calculation-snapshot header span,.quote-attachments header span{color:#64748b;font-size:11px}.snapshot-table-scroll{overflow:auto}.calculation-snapshot table{width:100%;min-width:650px;border-collapse:collapse}.calculation-snapshot th{background:#eef2f6;padding:8px;color:#64748b;font-size:11px;text-align:left}.calculation-snapshot td{border-top:1px solid #eef2f6;padding:8px;color:#475569;font-size:12px}.calculation-snapshot td:last-child,.calculation-snapshot tfoot td{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-weight:900}.calculation-snapshot tfoot td{background:#f8fafc;color:#0f766e;text-align:right}.empty{padding:22px!important;color:#94a3b8!important;text-align:center}.quote-attachments{border-top:1px solid #e2e8f0}.quote-attachments>div{display:flex;flex-wrap:wrap;gap:7px;padding:11px 13px}.quote-attachments>div button{display:inline-flex;align-items:center;gap:5px;border:1px solid #dbe5ea;border-radius:999px;background:#fff;padding:6px 9px;color:#475569;font-size:11px}.quote-attachments>div button:hover{border-color:#99f6e4;color:#0f766e}.quote-attachments svg{width:12px}.quote-attachments em{color:#94a3b8;font-size:11px;font-style:normal}.quote-local-message,.quote-local-error{display:flex;align-items:center;gap:6px;margin:0;border-top:1px solid;padding:10px 13px;font-size:11px}.quote-local-message{border-color:#a7f3d0;background:#ecfdf5;color:#047857}.quote-local-error{border-color:#fecaca;background:#fef2f2;color:#b91c1c}.quote-local-message svg,.quote-local-error svg{width:14px}
.quote-reason-panel{display:grid;grid-template-columns:minmax(180px,1fr) minmax(240px,2fr) auto auto;align-items:center;gap:8px;border-top:1px solid #fed7aa;background:#fff7ed;padding:10px 13px}.quote-reason-panel>div{display:grid}.quote-reason-panel strong{color:#9a3412;font-size:12px}.quote-reason-panel span{margin-top:2px;color:#c2410c;font-size:11px}.quote-reason-panel textarea{min-width:0;border:1px solid #fdba74;border-radius:7px;padding:7px 9px;font-size:13px;resize:none}.quote-reason-panel button{height:32px;border-radius:7px;padding:0 10px;font-size:12px;font-weight:900}.quote-reason-panel button.secondary{border:1px solid #fdba74;background:#fff;color:#9a3412}.quote-reason-panel button.primary{border:1px solid #c2410c;background:#c2410c;color:#fff}.quote-editor-actions{position:sticky;bottom:0;z-index:4;display:flex;align-items:center;justify-content:space-between;gap:12px;border-top:1px solid #cbd5e1;background:rgb(248 250 252/.96);padding:11px 13px;backdrop-filter:blur(8px)}.quote-editor-actions>div:first-child{display:grid}.quote-editor-actions>div:first-child span{color:#64748b;font-size:11px}.quote-editor-actions>div:first-child b{margin-top:3px;color:#94a3b8;font-size:10px;font-weight:500}.quote-editor-actions>div:last-child{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:6px}.quote-editor-actions button{display:inline-flex;height:34px;align-items:center;gap:5px;border-radius:8px;padding:0 10px;font-size:12px;font-weight:900}.quote-editor-actions button svg{width:13px}.quote-editor-actions button.secondary{border:1px solid #cbd5e1;background:#fff;color:#475569}.quote-editor-actions button.primary{border:1px solid #0f766e;background:#0f766e;color:#fff}.quote-editor-actions button.danger{border:1px solid #fecaca;background:#fff;color:#dc2626}.quote-editor-actions button:disabled{opacity:.45}
@media(max-width:800px){.quote-editor-head,.quote-editor-actions{align-items:stretch;flex-direction:column}.quote-editor-tools,.quote-editor-actions>div:last-child{justify-content:flex-start}.quote-editor-actions{position:static}.quote-reason-panel{grid-template-columns:1fr}.quote-dependency-strip em{margin-left:0}.preview-metrics{grid-template-columns:1fr 1fr}}
</style>
