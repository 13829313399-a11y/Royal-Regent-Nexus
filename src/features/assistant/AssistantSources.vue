<script setup lang="ts">
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { ExternalLink, Globe, FileText, BriefcaseBusiness, BookOpen } from '@lucide/vue'
import { assistantApi } from './api'
import { formatBusinessDateTime } from '@/lib/dateTime'
import { sourceSummary } from './sourceSummary'
import type { EvidencePart, SourceRecord } from './v2'
import { documentLocation, formatDocumentSegment } from './documentFormat'
import type { DocumentSegment } from './documentFormat'
import AssistantOcrPreview from './AssistantOcrPreview.vue'
import { getAuthenticationGeneration } from '@/lib/authenticationGeneration'
const props = defineProps<{ evidence: EvidencePart | null }>()
const preview = ref(''), error = ref('')
const ocrParts = ref<DocumentSegment[]>([]), previewFileId = ref('')
const readingSource = ref<string | null>(null)
const closeButton = ref<HTMLButtonElement>()
const sourceRows = computed(() => {
  let number = 0
  return (props.evidence?.sources || []).map(source => ({ source, number: source.kind === 'file' && source.citation_eligible === false ? null : ++number }))
})
let opener: HTMLElement | null = null
let generation = 0
function clearPreview() { generation++; preview.value = ''; ocrParts.value = []; previewFileId.value = ''; error.value = ''; readingSource.value = null; opener = null }
async function closePreview() { const target = opener; clearPreview(); await nextTick(); if (target?.isConnected) target.focus() }
watch(() => props.evidence, clearPreview, { flush: 'sync' })
onMounted(() => window.addEventListener('auth-session-boundary-changed', clearPreview))
onBeforeUnmount(() => { clearPreview(); window.removeEventListener('auth-session-boundary-changed', clearPreview) })
const summary = computed(() => {
  const search = props.evidence?.search
  if (!search) return '当前回答还没有来源'
  if (search.execution === 'pending') return '正在查找公开资料'
  if (search.execution === 'unconfirmed') return '本次未取得可核验的联网证据'
  if (search.execution === 'failed') return '检索未完成，已有资料保留'
  if (search.execution === 'confirmed' && search.evidence_level === 'none') return '已完成检索，暂未返回合适来源'
  if (search.execution === 'confirmed') {
    const current = props.evidence?.sources.filter(s => s.kind === 'web' && !s.origin) || []
    const read = current.filter(s => s.kind === 'web' && s.evidence_level === 'page_content').length
    return `${current.length} 个本轮公开来源 · ${read} 个已取得正文摘录`
  }
  return props.evidence?.sources.some(s => s.origin) ? '沿用资料 · 保留原查询时间' : '本轮使用的资料'
})
function safeLink(source: SourceRecord) {
  if (source.kind !== 'web') return undefined
  try { const url = new URL(source.url); return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? source.url : undefined } catch { return undefined }
}
function webHost(source: SourceRecord) {
  const url = safeLink(source)
  return url ? new URL(url).hostname : '来源地址不可用'
}
function readFailure(code?: string | null) {
  if (code === 'page_address_forbidden' || code === 'page_url_invalid') return '地址不符合公开网页读取范围'
  if (code === 'page_timeout') return '网页读取超时'
  if (code === 'page_too_large') return '网页超过读取大小限制'
  if (code === 'page_type_unsupported') return '此链接不是可读取的网页或文本'
  if (code === 'page_content_empty') return '未取得可用正文，可能需要登录或由脚本加载'
  return '网页读取未完成，仍可打开原站核对'
}
function location(source: SourceRecord) {
  if (source.kind !== 'file') return ''
  return documentLocation(source.locator)
}
async function read(source: SourceRecord, event: MouseEvent) {
  if (source.kind !== 'file' || source.file_ref.kind !== 'document') return
  clearPreview()
  opener = event.currentTarget as HTMLElement
  const ticket = generation, identity = getAuthenticationGeneration()
  readingSource.value = source.source_id
  try {
    const parts = await (source.document_version ? assistantApi.documentContent(source.file_ref.id, source.document_version) : assistantApi.documentContent(source.file_ref.id))
    if (ticket !== generation || identity !== getAuthenticationGeneration()) return
    if (source.locator.kind === 'document') {
      preview.value = `${source.title}\n检索范围：本次选择 ${source.retrieval?.selected_chunks ?? 0} / ${source.retrieval?.total_chunks ?? 0} 个片段。\n未命中不代表不存在；此范围记录不能用作正文引用。`
      await nextTick()
      if (ticket === generation && identity === getAuthenticationGeneration()) closeButton.value?.focus()
      return
    }
    const part = parts.find(p => JSON.stringify(p.locator) === JSON.stringify(source.locator))
    if (!part) { error.value = '引用位置当前不可用，请重新读取资料。'; return }
    const span = source.excerpt_range
    // Backend spans count Unicode code points; JS string offsets count UTF-16.
    const characters = Array.from(part.text)
    if (span && !(span.start >= 0 && span.end > span.start && span.end <= characters.length && span.total === characters.length)) {
      error.value = '引用片段已变化，请重新读取资料。'; return
    }
    preview.value = `${source.title}\n\n${formatDocumentSegment(span ? {...part,text:characters.slice(span.start,span.end).join('')} : part)}${span && span.end-span.start < span.total ? '\n仅显示本轮召回片段，原位置包含更多文字。' : ''}`
    previewFileId.value = source.file_ref.id
    ocrParts.value = part.locator.kind === 'ocr_region' ? [part] : []
    await nextTick()
    if (ticket === generation && identity === getAuthenticationGeneration()) closeButton.value?.focus()
  } catch (e) { if (ticket === generation && identity === getAuthenticationGeneration()) error.value = e instanceof Error ? e.message : '资料不可用' }
  finally { if (ticket === generation) readingSource.value = null }
}
</script>
<template>
  <section class="yl-sources" aria-label="回答来源">
    <p class="yl-source-summary" role="status">{{ summary }}</p>
    <p v-if="sourceSummary(evidence)" class="yl-source-summary">{{ sourceSummary(evidence) }}</p>
    <details v-if="evidence?.search.research_summary" class="yl-reasoning"><summary>公开研究草稿 · 尚需来源核验</summary><p>{{ evidence.search.research_summary }}</p></details>
    <p v-for="failure in evidence?.search.page_failures || []" :key="failure.url" class="yl-error">{{ readFailure(failure.code) }}：{{ failure.url }}</p>
    <article v-for="{ source, number } in sourceRows" :key="source.source_id" class="yl-source-card">
      <div class="yl-source-heading"><span>{{ number ?? '范围' }}</span><Globe v-if="source.kind === 'web'" :size="15"/><FileText v-else-if="source.kind === 'file'" :size="15"/><BriefcaseBusiness v-else-if="source.kind === 'business'" :size="15"/><BookOpen v-else :size="15"/><small>{{ {web:'公开资料',file:'私有文件',business:'业务快照',help:'系统说明'}[source.kind] }}</small></div>
      <strong>{{ source.title }}</strong>
      <template v-if="source.kind === 'web'">
        <small>{{ webHost(source) }}</small><small :title="source.retrieved_at">获取于 {{ formatBusinessDateTime(source.retrieved_at) }}（北京时间）{{ source.origin ? ' · 沿用资料' : '' }}</small>
        <small>{{ source.evidence_level === 'page_content' ? '已取得正文摘录，不能据此声称已读全文' : '检索条目，尚未取得正文' }}</small>
        <small v-if="source.read_status === 'failed'">{{ readFailure(source.read_error) }}</small>
        <small v-else-if="source.evidence_level !== 'page_content'">尚未尝试读取正文</small>
        <details v-if="source.excerpt"><summary>{{ source.evidence_level === 'page_content' ? '查看正文摘录' : '查看检索摘要' }}</summary><p class="yl-web-excerpt">{{ source.excerpt }}</p><small v-if="source.locator">提取文本第 {{ source.locator.start }}–{{ source.locator.end }} 行{{ source.excerpt_truncated ? ' · 已截取' : '' }}</small></details>
        <small v-if="source.final_url && source.final_url !== source.url">跳转后：{{ source.final_url }}</small>
        <a v-if="safeLink(source)" :href="safeLink(source)" target="_blank" rel="noopener noreferrer">打开原站 <ExternalLink :size="13"/></a>
      </template>
      <template v-else-if="source.kind === 'file'"><small>{{ location(source) }}</small><button :disabled="readingSource === source.source_id" @click="read(source, $event)">{{ readingSource === source.source_id ? '正在读取…' : source.citation_eligible === false ? '查看检索范围' : '查看引用位置' }}</button></template>
      <template v-else-if="source.kind === 'business'"><small>{{ source.scope.scope_label }} · {{ source.data_mode }}</small><small>截至 {{ source.as_of }}</small><small v-if="source.unknown_fields.length">未知：{{ source.unknown_fields.join('、') }}</small></template>
      <small v-else>{{ source.knowledge_version }}</small>
    </article>
    <p v-if="error" role="status" class="yl-error">{{ error }}</p>
    <div v-if="preview" class="yl-file-preview" @keydown.esc.stop="closePreview"><button ref="closeButton" @click="closePreview">关闭引用原文</button><AssistantOcrPreview v-if="ocrParts.length" :id="previewFileId" :parts="ocrParts"/><pre>{{ preview }}</pre></div>
  </section>
</template>
