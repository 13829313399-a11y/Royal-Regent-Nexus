<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useAssistantStore } from '@/stores/assistant'
import { assistantApi } from './api'
import { documentLocation, formatDocumentSegment } from './documentFormat'
import type { DocumentFile, DocumentSearchResult } from './types'
const props = defineProps<{ file: DocumentFile }>()
const store = useAssistantStore()
const query = ref(''), error = ref(''), busy = ref(false)
const result = ref<DocumentSearchResult | null>(null)
const input = ref<HTMLInputElement>(), heading = ref<HTMLElement>()
let generation = 0, alive = true
function clear() { generation++; query.value = ''; error.value = ''; result.value = null; busy.value = false }
async function search() {
  if (busy.value || !query.value.trim() || !props.file.session_id) return
  const ticket = ++generation
  busy.value = true; error.value = ''; result.value = null
  try {
    const value = await assistantApi.searchDocuments(props.file.session_id, [props.file.id], query.value.trim())
    if (!alive || ticket !== generation) return
    result.value = value
    await nextTick()
    if (alive && ticket === generation) heading.value?.focus()
  } catch (e) { if (alive && ticket === generation) error.value = e instanceof Error ? e.message : '文件检索暂不可用，请重试。' }
  finally { if (alive && ticket === generation) busy.value = false }
}
watch(() => [props.file.id, props.file.document_version, store.identityGeneration], clear, { flush: 'sync' })
onBeforeUnmount(() => { alive = false; generation++ })
</script>
<template>
  <details class="yl-file-retrieval">
    <summary>检索文件片段</summary>
    <p>按编号、关键词或原位置查找。此操作只读取文件，不生成模型回答。</p>
    <small>解析位置 {{ file.indexed_segments ?? file.parse_index?.length ?? 0 }} 处 · 版本 {{ file.document_version?.slice(0,12) }}</small>
    <div role="search" :aria-label="`检索${file.name}`" class="yl-retrieval-query">
      <input ref="input" v-model="query" aria-label="文件编号或关键词" maxlength="2000" placeholder="例如：SYN-R0913、验收条件、第2页" @keydown.enter.prevent="search"/>
      <button type="button" :disabled="busy || !query.trim()" @click="search">{{ busy ? '检索中…' : '查找片段' }}</button>
    </div>
    <p v-if="error" role="status">{{ error }}</p>
    <div v-if="result" @keydown.esc.stop="input?.focus()">
      <h4 ref="heading" tabindex="-1">{{ result.materials.length ? `选取 ${result.report.selected_chunks} / ${result.report.total_chunks} 个片段` : '未命中所查内容' }}</h4>
      <p role="status">{{ result.report.notice }}</p>
      <p v-if="result.report.unmatched_identifiers.length">未命中编号：{{ result.report.unmatched_identifiers.join('、') }}</p>
      <details v-for="part in result.materials" :key="part.source_id" class="yl-retrieval-hit">
        <summary>{{ documentLocation(part.locator) }}<span v-if="part.excerpt_range.end-part.excerpt_range.start < part.excerpt_range.total"> · 部分文字</span></summary>
        <pre>{{ formatDocumentSegment(part) }}</pre>
      </details>
    </div>
  </details>
</template>
<style scoped>
.yl-file-retrieval { min-width: 0; margin-top: .75rem; }
.yl-file-retrieval summary { cursor: pointer; overflow-wrap: anywhere; }
.yl-file-retrieval p, .yl-file-retrieval small { display: block; margin: .5rem 0; overflow-wrap: anywhere; }
.yl-retrieval-query { display: flex; flex-wrap: wrap; gap: .5rem; margin: .5rem 0; }
.yl-retrieval-query input { flex: 1 1 10rem; min-width: 0; width: 100%; min-height: 40px; border: 1px solid var(--yl-line); border-radius: 8px; background: var(--yl-paper); padding: 6px 9px; }
.yl-retrieval-hit { margin-top: .5rem; }
.yl-retrieval-hit pre { max-height: 18rem; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; }
</style>
