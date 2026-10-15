<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { FileText } from '@lucide/vue'
import { useAssistantStore } from '@/stores/assistant'
import { assistantApi, AssistantApiError } from './api'
import type { DocumentFile } from './types'
const props = defineProps<{ id: string }>()
const emit = defineEmits<{ deleted: [] }>()
const store = useAssistantStore()
const file = ref<DocumentFile | null>(null), error = ref(''), preview = ref('')
const loading = ref(false), reading = ref(false), deleting = ref(false), confirming = ref(false), deleted = ref(false), unavailable = ref(false)
const labels: Record<string, string> = { queued: '排队中', parsing: '解析中', ready: '可分析', failed: '解析失败' }
const parseMessages: Record<string, string> = {
  pdf_encrypted: '请上传未加密的 PDF', pdf_invalid: 'PDF 无法读取，请核对文件', pdf_ocr_required: '扫描文件需要先识别成文字',
  file_page_limit: '页数超过限制，请拆分文件', file_text_limit: '文字量超过限制，请拆分文件',
  file_encoding: '请使用 UTF-8 或带 BOM 的 UTF-16 文本', csv_invalid: 'CSV 格式有误，请核对引号和分隔符', file_empty: '没有可分析的文字',
  parse_timeout: '解析超时，请拆分后重新上传', parse_interrupted: '解析已中断，请重新上传',
  parse_memory_limit: '解析超出内存限制，请拆分后重新上传', parse_resource_unavailable: '解析服务的资源保护暂不可用，请联系管理员',
}
const parseMessage = computed(() => parseMessages[file.value?.error_code || ''] || '请核对文件后重新上传')
let generation = 0, alive = true
async function load() {
  const ticket = ++generation
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
    const parts = await assistantApi.documentContent(props.id)
    if (!alive || ticket !== generation) return
    preview.value = parts.map(part => {
      const l = part.locator
      const position = l.kind === 'page' ? `第 ${l.page} 页` : l.kind === 'lines' ? `第 ${l.start}–${l.end} 行` : '引用原文'
      return `${position}\n${part.text}`
    }).join('\n\n')
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
watch(() => [props.id, store.identityGeneration], load, { immediate: true })
onBeforeUnmount(() => { alive = false; generation++ })
</script>
<template>
  <section class="yl-history-document" aria-label="已上传文档">
    <p v-if="deleted" role="status">文件已删除，相关回答和成果已停止读取。</p>
    <template v-else-if="file">
      <strong><FileText :size="15"/>{{ file.name }}</strong><small>{{ labels[file.parse_status] || '状态待核对' }}{{ file.parse_status === 'failed' ? ` · ${parseMessage}` : '' }}</small>
      <div class="yl-document-actions"><button v-if="file.parse_status === 'ready'" :disabled="reading || deleting" @click="read">{{ reading ? '正在读取…' : '查看文件原文' }}</button><button :disabled="deleting || store.anyBusy" @click="confirming = true">删除文件</button></div><small v-if="store.anyBusy">请先停止生成或等待回答结束，再删除文件。</small>
      <div v-if="confirming" class="yl-delete-confirm"><p>删除此文件后，依赖它的历史回答和成果全部版本将不可读取或导出。</p><button :disabled="deleting || store.anyBusy" @click="remove">{{ deleting ? '正在删除…' : '确认删除文件' }}</button><button :disabled="deleting" @click="confirming = false">保留文件</button></div>
      <div v-if="preview" class="yl-file-preview"><button @click="preview = ''">关闭文件原文</button><pre>{{ preview }}</pre></div>
    </template>
    <p v-else-if="loading" role="status">正在读取文件信息…</p>
    <p v-if="error" role="status">{{ error }}</p><button v-if="!loading && !deleted && !unavailable && !file" @click="load">重试读取文件</button>
  </section>
</template>
