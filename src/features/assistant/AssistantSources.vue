<script setup lang="ts">
import { computed, ref } from 'vue'
import { ExternalLink, Globe, FileText, BriefcaseBusiness, BookOpen } from '@lucide/vue'
import { assistantApi } from './api'
import type { EvidencePart, SourceRecord } from './v2'
const props = defineProps<{ evidence: EvidencePart | null }>()
const preview = ref(''), error = ref('')
const summary = computed(() => {
  const search = props.evidence?.search
  if (!search) return '当前回答还没有来源'
  if (search.execution === 'pending') return '正在查找公开资料'
  if (search.execution === 'unconfirmed') return '本次未取得可核验的联网证据'
  if (search.execution === 'failed') return '检索未完成，已有资料保留'
  if (search.execution === 'confirmed' && search.evidence_level === 'none') return '已完成检索，暂未返回合适来源'
  if (search.execution === 'confirmed') return `${props.evidence?.sources.filter(s => s.kind === 'web').length} 个联网来源 · 检索条目`
  return props.evidence?.sources.some(s => s.origin) ? '沿用资料 · 保留原查询时间' : '本轮使用的资料'
})
function safeLink(source: SourceRecord) {
  if (source.kind !== 'web') return undefined
  try { const url = new URL(source.url); return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? source.url : undefined } catch { return undefined }
}
function location(source: SourceRecord) {
  if (source.kind !== 'file') return ''
  const l = source.locator
  return l.kind === 'page' ? `第 ${l.page} 页` : l.kind === 'lines' ? `第 ${l.start}–${l.end} 行` : l.kind === 'paragraph' ? `第 ${l.paragraph} 段` : l.kind === 'sheet' ? `${l.sheet}!${l.cells}` : '图片'
}
async function read(source: SourceRecord) {
  if (source.kind !== 'file' || source.file_ref.kind !== 'document') return
  try {
    const parts = await assistantApi.documentContent(source.file_ref.id)
    const part = parts.find(p => JSON.stringify(p.locator) === JSON.stringify(source.locator))
    preview.value = `${source.title} · ${location(source)}\n\n${part?.text || '该位置当前不可用'}`; error.value = ''
  } catch (e) { error.value = e instanceof Error ? e.message : '资料不可用' }
}
</script>
<template>
  <section class="yl-sources" aria-label="回答来源">
    <p class="yl-source-summary" role="status">{{ summary }}</p>
    <article v-for="(source, index) in evidence?.sources || []" :key="source.source_id" class="yl-source-card">
      <div class="yl-source-heading"><span>{{ index + 1 }}</span><Globe v-if="source.kind === 'web'" :size="15"/><FileText v-else-if="source.kind === 'file'" :size="15"/><BriefcaseBusiness v-else-if="source.kind === 'business'" :size="15"/><BookOpen v-else :size="15"/><small>{{ {web:'公开资料',file:'私有文件',business:'业务快照',help:'系统说明'}[source.kind] }}</small></div>
      <strong>{{ source.title }}</strong>
      <template v-if="source.kind === 'web'"><small>{{ source.site_name }}</small><small>检索于 {{ source.retrieved_at }}{{ source.origin ? ' · 沿用资料' : '' }}</small><small>{{ source.evidence_level === 'page_content' ? '取得网页正文' : '检索条目，未声明已读全文' }}</small><a v-if="safeLink(source)" :href="safeLink(source)" target="_blank" rel="noopener noreferrer">打开原站 <ExternalLink :size="13"/></a></template>
      <template v-else-if="source.kind === 'file'"><small>{{ location(source) }}</small><button @click="read(source)">查看引用位置</button></template>
      <template v-else-if="source.kind === 'business'"><small>{{ source.scope.scope_label }} · {{ source.data_mode }}</small><small>截至 {{ source.as_of }}</small><small v-if="source.unknown_fields.length">未知：{{ source.unknown_fields.join('、') }}</small></template>
      <small v-else>{{ source.knowledge_version }}</small>
    </article>
    <p v-if="error" role="status" class="yl-error">{{ error }}</p>
    <div v-if="preview" class="yl-file-preview"><button @click="preview = ''">关闭引用原文</button><pre>{{ preview }}</pre></div>
  </section>
</template>
