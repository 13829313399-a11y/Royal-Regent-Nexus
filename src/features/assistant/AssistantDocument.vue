<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { FileText } from '@lucide/vue'
import { useAssistantStore } from '@/stores/assistant'
import { assistantApi, AssistantApiError } from './api'
import type { DocumentFile } from './types'
import { documentParseMessage, formatDocument } from './documentFormat'
import type { DocumentSegment } from './documentFormat'
import AssistantOcrPreview from './AssistantOcrPreview.vue'
import AssistantDocumentSearch from './AssistantDocumentSearch.vue'
import AssistantDocumentReplacement from './AssistantDocumentReplacement.vue'
const props = defineProps<{ id: string; status?: DocumentFile['parse_status'] }>()
const emit = defineEmits<{ deleted: [] }>()
const store = useAssistantStore()
const file = ref<DocumentFile | null>(null), error = ref(''), preview = ref('')
const ocrParts = ref<DocumentSegment[]>([])
const readButton = ref<HTMLButtonElement>(), closeButton = ref<HTMLButtonElement>()
async function closePreview() { preview.value = ''; ocrParts.value = []; await nextTick(); if (alive) readButton.value?.focus() }
const loading = ref(false), reading = ref(false), deleting = ref(false), confirming = ref(false), deleted = ref(false), unavailable = ref(false)
const labels: Record<string, string> = { queued: '排队中', parsing: '解析中', ready: '可分析', failed: '解析失败', superseded: '已被替换 · 原索引不再使用' }
const parseMessage = computed(() => documentParseMessage(file.value?.error_code))
let generation = 0, alive = true
async function load() {
  const ticket = ++generation
  ocrParts.value = []
  file.value = null; preview.value = ''; error.value = ''; confirming.value = false; unavailable.value = false; deleted.value = false
  loading.value = true; reading.value = false; deleting.value = false
  try { const value = await assistantApi.document(props.id); if (alive && ticket === generation) file.value = value }
  catch (e) { if (alive && ticket === generation) { error.value = e instanceof Error ? e.message : '文件信息暂不可用'; unavailable.value = e instanceof AssistantApiError && [404, 410].includes(e.status) } }
  finally { if (alive && ticket === generation) loading.value = false }
}
async function read() {
  const ticket = generation
  reading.value = true; error.value = ''
  try {
    const parts = await (file.value?.document_version ? assistantApi.documentContent(props.id,file.value.document_version) : assistantApi.documentContent(props.id))
    if (!alive || ticket !== generation) return
    preview.value = formatDocument(parts)
    ocrParts.value = parts.filter(p => p.locator.kind === 'ocr_region')
    await nextTick()
    if (alive && ticket === generation) closeButton.value?.focus()
  } catch (e) { if (alive && ticket === generation) { preview.value = ''; error.value = e instanceof Error ? e.message : '文件内容当前不可用' } }
  finally { if (alive && ticket === generation) reading.value = false }
}
async function remove() {
  if (deleting.value || store.anyBusy) return
  const ticket = ++generation
  deleting.value = true; preview.value = ''; error.value = ''
  try {
    await assistantApi.removeDocument(props.id)
    if (!alive || ticket !== generation) return
    deleted.value = true; file.value = null; confirming.value = false; emit('deleted')
  } catch (e) { if (alive && ticket === generation) error.value = e instanceof Error ? e.message : '文件删除未完成' }
  finally { if (alive && ticket === generation) { deleting.value = false; reading.value = false } }
}
function replaced() {
  generation++; preview.value = ''; ocrParts.value = []; error.value = ''; reading.value = false
  if (file.value) file.value = {...file.value,parse_status:'superseded'}
  // Existing event clears cached derived content and refreshes its visibility.
  emit('deleted')
}
watch(() => [props.id, props.status, store.identityGeneration], load, { immediate: true })
onBeforeUnmount(() => { alive = false; generation++ })
</script>
<template>
  <section class="yl-history-document" aria-label="已上传文档">
    <p v-if="deleted" role="status">文件已删除，相关回答和成果已停止读取。</p>
    <template v-else-if="file">
      <strong><FileText :size="15"/>{{ file.name }}</strong><small>{{ labels[file.parse_status] || '状态待核对' }}{{ file.parse_status === 'failed' ? ` · ${parseMessage}` : '' }}</small>
      <div class="yl-document-actions"><button ref="readButton" v-if="file.parse_status === 'ready'" :disabled="reading || deleting" @click="read">{{ reading ? '正在读取…' : '查看文件原文' }}</button><button :disabled="deleting || store.anyBusy" @click="confirming = true">删除文件</button></div><small v-if="store.anyBusy">请先停止生成或等待回答结束，再删除文件。</small>
      <div v-if="confirming" class="yl-delete-confirm"><p>删除此文件后，依赖它的历史回答和成果全部版本将不可读取或导出。</p><button :disabled="deleting || store.anyBusy" @click="remove">{{ deleting ? '正在删除…' : '确认删除文件' }}</button><button :disabled="deleting" @click="confirming = false">保留文件</button></div>
      <div v-if="preview" class="yl-file-preview" @keydown.esc.stop="closePreview"><button ref="closeButton" @click="closePreview">关闭文件原文</button><AssistantOcrPreview v-if="ocrParts.length" :id="id" :parts="ocrParts"/><pre>{{ preview }}</pre></div>
      <AssistantDocumentSearch v-if="file.parse_status === 'ready' && file.session_id && file.document_version" :file="file"/>
      <AssistantDocumentReplacement v-if="file.parse_status === 'ready' && file.session_id && file.document_version" :file="file" @replaced="replaced"/>
    </template>
    <p v-else-if="loading" role="status">正在读取文件信息…</p>
    <p v-if="error" role="status">{{ error }}</p><button v-if="!loading && !deleted && !unavailable && !file" @click="load">重试读取文件</button>
  </section>
</template>
