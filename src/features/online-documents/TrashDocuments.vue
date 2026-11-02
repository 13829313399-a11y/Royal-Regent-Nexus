<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { isAxiosError } from 'axios'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'
import { onlineDocuments as api, type OnlineDocument, type DocumentCommand } from '@/api/onlineDocuments'

const props = defineProps<{ factoryId: string; documents: OnlineDocument[] }>()
const emit = defineEmits<{ close: []; changed: [document: OnlineDocument]; complete: [count: number] }>()
const documents = ref(props.documents.map(d => ({ ...d })))
const commands = ref<DocumentCommand[]>([])
const completed = ref(0)
const loading = ref(false)
const busy = ref(false)
const uncertain = ref(false)
const error = ref('')
const heading = ref<HTMLElement>()
let disposed = false

async function check() {
  if (busy.value || uncertain.value) return
  loading.value = true; error.value = ''; commands.value = []
  try {
    const current = await Promise.all(props.documents.map(d => api.detail(props.factoryId, d.id)))
    if (disposed) return
    documents.value = current
    const blocked = current.find(d => d.access !== 'owner' || d.deleted_at || d.editing || d.pending_save || d.save_error)
    if (blocked) {
      error.value = `「${blocked.title}.${blocked.format}」暂时不能移入回收站。请确认文件属于你、仍在文档列表中，并让所有人保存成功、关闭编辑窗口后重试。`
      return
    }
    commands.value = current.map(d => ({ request_id: createRandomUuid(), expected_version: d.state_version }))
  } catch (e) { if (!disposed) error.value = getApiErrorMessage(e) }
  finally { if (!disposed) loading.value = false }
}

async function execute() {
  if (busy.value || loading.value || !commands.value.length) return
  busy.value = true; error.value = ''
  try {
    // Each file uses the existing owner/closed-editor/version checks. Keep the
    // original command for an uncertain response and resume only that file.
    while (completed.value < documents.value.length) {
      const index = completed.value
      const doc = documents.value[index]!
      const result = await api.command(props.factoryId, doc.id, 'trash', commands.value[index]!)
      if (disposed) return
      completed.value++; uncertain.value = false
      emit('changed', result)
      if (result.operation_notice) {
        commands.value = []
        error.value = result.operation_notice + '。批量操作已停止，请关闭后刷新列表核对。'
        return
      }
    }
    emit('complete', completed.value)
  } catch (e) {
    if (disposed) return
    const status = isAxiosError(e) ? e.response?.status : undefined
    uncertain.value = !status || status === 408 || status >= 500
    const doc = documents.value[completed.value]!
    error.value = `「${doc.title}.${doc.format}」：` + (uncertain.value ? '操作结果尚未确认，请重试原操作。' : '未能移入回收站，后续文件尚未处理。') + getApiErrorMessage(e)
    if (!uncertain.value) commands.value = []
  } finally { if (!disposed) busy.value = false }
}

onMounted(async () => { await nextTick(); if (disposed) return; heading.value?.focus(); void check() })
onBeforeUnmount(() => { disposed = true })
</script>

<template>
  <section class="od-trash-confirmation" aria-labelledby="od-trash-heading" :aria-busy="loading || busy">
    <h3 id="od-trash-heading" ref="heading" tabindex="-1">移入回收站 · {{ documents.length }} 份文档</h3>
    <p>现有共享会被取消，同事将无法继续访问。文件及历史版本保留，可在回收站恢复。</p>
    <p>所有人须先保存成功并关闭编辑窗口。按清单逐份处理，遇到失败会停止。</p>
    <ul aria-label="待移入回收站的文档"><li v-for="(doc, index) in documents" :key="doc.id">{{ doc.title }}.{{ doc.format }}<span v-if="index < completed"> · 已确认处理</span></li></ul>
    <p v-if="loading" role="status">正在检查文件及保存状态…</p>
    <p v-if="completed" role="status">已确认处理 {{ completed }} / {{ documents.length }} 份</p>
    <p v-if="error" class="od-trash-error" role="alert">{{ error }}</p>
    <div class="od-trash-actions">
      <Button v-if="commands.length" variant="destructive" :disabled="busy || loading" @click="execute">{{ busy ? '正在移入…' : uncertain ? '重试原操作' : `确认移入 ${documents.length} 份文档` }}</Button>
      <Button v-else-if="!completed" variant="outline" :disabled="loading || busy" @click="check">重新检查</Button>
      <Button variant="outline" :disabled="busy || uncertain" @click="emit('close')">{{ completed ? '关闭' : '取消' }}</Button>
    </div>
  </section>
</template>

<style scoped>
.od-trash-confirmation { margin:0 18px 18px; padding:16px; border:1px solid var(--color-destructive); border-radius:var(--radius-lg); background:var(--color-card); min-width:0; }
h3 { font-size:16px; font-weight:600; overflow-wrap:anywhere; }
p,li { font-size:13px; overflow-wrap:anywhere; }
p { margin-top:10px; color:var(--color-muted-foreground); }
ul { margin:12px 0; max-height:180px; overflow:auto; padding-left:20px; list-style:disc; }
li+li { margin-top:6px; }
.od-trash-error { color:var(--color-destructive); }
.od-trash-actions { display:flex; flex-wrap:wrap; gap:10px; margin-top:14px; }
@media(max-width:700px) { .od-trash-confirmation { margin:0 12px 12px; padding:12px; } }
</style>
