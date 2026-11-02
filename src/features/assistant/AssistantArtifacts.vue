<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { assistantApi, AssistantApiError } from './api'
import AssistantDataset from './AssistantDataset.vue'
import { renderMarkdown } from './markdown'
import type { Artifact } from './types'
import { useAssistantStore } from '@/stores/assistant'
const props = defineProps<{ selected?: string }>()
const assistant = useAssistantStore()
const items = ref<Artifact[]>([]), current = ref<Artifact | null>(null), text = ref(''), error = ref(''), notice = ref(''), cursor = ref<string | null>(null)
const revision = ref(1), query = ref('')
const listing = ref(false), saving = ref(false), opening = ref(false)
const downloading = ref(false), conflict = ref(false), latestContent = ref('')
const pending = ref<{id?: string; version?: number} | null>(null)
const preview = computed(() => renderMarkdown(text.value))
const dirty = computed(() => !!current.value && text.value !== current.value.content)
let listGeneration = 0, openGeneration = 0, alive = true, appliedQuery = ''
function clearPrivate() { listGeneration++; openGeneration++; items.value=[]; current.value=null; text.value=''; latestContent.value=''; pending.value=null; cursor.value=null;query.value='';appliedQuery='';revision.value=1;conflict.value=false;opening.value=false;listing.value=false;saving.value=false;downloading.value=false;notice.value='';error.value='' }
function failed(e: unknown) {
  if (e instanceof AssistantApiError && [403,410].includes(e.status)) clearPrivate()
  error.value = e instanceof Error ? e.message : '成果操作未完成'
  conflict.value = e instanceof AssistantApiError && e.code === 'revision_conflict'
}
async function list(more = false) {
  if (more && (listing.value || !cursor.value)) return
  const ticket = ++listGeneration
  if (!more) { appliedQuery = query.value; cursor.value = null; items.value = [] }
  const search = appliedQuery, after = more ? cursor.value || '' : ''
  listing.value = true
  try {
    const r = await assistantApi.artifacts(after, search)
    if (!alive || ticket !== listGeneration) return
    items.value = more ? [...items.value, ...r.items.filter(a => !items.value.some(old => old.id === a.id))] : r.items
    cursor.value = r.next_cursor; error.value = ''
  } catch(e) { if (alive && ticket === listGeneration) failed(e) }
  finally { if (alive && ticket === listGeneration) listing.value = false }
}
async function open(id: string, version?: number, retainDraft=false) {
  if (saving.value || downloading.value) return
  if (dirty.value && !retainDraft) { pending.value={id,version}; return }
  const ticket = ++openGeneration
  const draft = text.value
  opening.value = true
  try {
    const a = await assistantApi.artifact(id, version)
    if (!alive || ticket !== openGeneration) return
    current.value=a; text.value=retainDraft ? draft : a.content; revision.value=a.revision
    latestContent.value=retainDraft ? a.content : ''; conflict.value=false; error.value=''
    notice.value=retainDraft ? '已读取最新版本，原编辑仍保留。请对照最新正文合并，再保存新版本。' : ''
  } catch(e) { if (alive && ticket === openGeneration) failed(e) }
  finally { if (alive && ticket === openGeneration) opening.value = false }
}
function back() { if (dirty.value) {pending.value={};return};openGeneration++; opening.value=false;current.value=null;latestContent.value='';conflict.value=false }
function discard() { const target=pending.value;pending.value=null;if(!target)return;text.value=current.value?.content || '';if(target.id)void open(target.id,target.version);else back() }
async function copyDraft() { try { await navigator.clipboard.writeText(text.value); notice.value='编辑内容已复制，可用于手动合并。' } catch { error.value='请选中成果正文并复制，当前浏览器无法直接复制。' } }
function changeRevision(event: Event) {
  const select = event.target as HTMLSelectElement, target = Number(select.value)
  select.value = String(revision.value)
  if (current.value) void open(current.value.id, target)
}
async function save() {
  if (!current.value || saving.value || opening.value || !dirty.value || revision.value !== current.value.current_revision) return
  const ticket = ++openGeneration, id = current.value.id, base = current.value.current_revision, content = text.value
  saving.value = true
  try { const a = await assistantApi.reviseArtifact(id, base, content); if (!alive || ticket !== openGeneration) return; current.value = a; revision.value = a.revision; text.value=a.content;latestContent.value='';conflict.value=false;notice.value = '新版本已保存'; error.value = ''; await list() } catch(e) { if (alive && ticket === openGeneration) failed(e) }
  finally { if (alive && ticket === openGeneration) saving.value = false }
}
async function download(format: string) {
  if (!current.value || saving.value || opening.value || downloading.value) return
  if (dirty.value) {error.value='请先保存修改，再导出当前内容。';return}
  const ticket=openGeneration,id=current.value.id,version=revision.value
  downloading.value=true
  try {
    const blob=await assistantApi.exportArtifact(id,format,version)
    if(!alive || ticket!==openGeneration || dirty.value)return
    const url=URL.createObjectURL(blob),link=document.createElement('a')
    link.href=url;link.download=`曜灵成果-第${version}版.${format}`;link.click()
    setTimeout(()=>URL.revokeObjectURL(url),1000);notice.value='已生成下载文件'
  }catch(e){if(alive && ticket===openGeneration)failed(e)}
  finally {if(alive && ticket===openGeneration)downloading.value=false}
}
watch(text, () => { notice.value = '' })
watch(() => assistant.visibilityGeneration, clearPrivate, {flush:'sync'})
watch(() => props.selected, id => { if (id) void open(id) })
onMounted(() => { window.addEventListener('auth-session-boundary-changed',clearPrivate);void list(); if(props.selected) void open(props.selected) })
onBeforeUnmount(() => { alive = false;clearPrivate();window.removeEventListener('auth-session-boundary-changed',clearPrivate) })
</script>
<template>
  <section class="yl-artifacts"><p class="yl-muted">仅本人可见。删除源会话或文件、撤销来源权限后，相关成果全部版本停止读取和导出。</p>
    <template v-if="current">
      <button :disabled="saving || downloading" @click="back">返回成果列表</button>
      <div class="yl-artifact-heading"><h3>{{ current.title }}</h3><span>{{ current.edit_origin === 'manual_edit' ? '人工编辑' : '初次保存' }}</span></div>
      <label>版本 <select :value="revision" :disabled="opening || saving || downloading" @change="changeRevision"><option v-for="v in current.current_revision" :key="v" :value="v">{{ v }}</option></select></label>
      <p v-if="revision !== current.current_revision" class="yl-muted">正在查看只读旧版本；原数据与旧来源保持对应。</p>
      <p v-if="opening" role="status">正在读取成果版本…</p>
      <AssistantDataset v-for="dataset in current.datasets || []" :key="dataset.dataset_id" :dataset="dataset" :initial-view="current.kind === 'chart' ? 'chart' : 'table'"/>
      <p v-if="current.datasets?.length" class="yl-muted">下方说明可以人工编辑；上方原查询数据保持不变。需要最新数据时，请返回原模块重新查询。</p>
      <details><summary>预览成果说明</summary><div class="yl-markdown" v-html="preview"/></details>
      <label class="yl-artifact-editor">成果说明<textarea v-model="text" aria-label="成果正文" rows="10" :readonly="opening || saving || revision !== current.current_revision"/></label>
      <p v-if="dirty" role="status" class="yl-muted">有未保存的修改，请先保存为新版本，再导出当前内容。</p>
      <details v-if="latestContent" class="yl-artifact-merge"><summary>对照最新已保存正文</summary><pre>{{ latestContent }}</pre></details>
      <div class="yl-artifact-actions"><button @click="save" :disabled="opening || saving || downloading || !dirty || !text.trim() || revision !== current.current_revision">{{ saving ? '正在保存…' : '保存为新版本' }}</button><button :disabled="opening || saving || downloading" @click="open(current!.id,undefined,dirty)">{{ conflict || dirty ? '读取最新版本并保留草稿' : '读取最新版本' }}</button><button v-if="dirty || conflict" @click="copyDraft">复制编辑内容</button><button v-for="format in current.export_formats" :key="format" :disabled="opening || saving || downloading || dirty" @click="download(format)">导出 {{ format.toUpperCase() }}</button></div>
      <details v-if="current.source_refs.length"><summary>依据来源（{{ current.source_refs.length }}）</summary><p v-for="source in current.source_refs" :key="source.source_id">{{ source.title }}</p></details>
    </template>
    <template v-else><form @submit.prevent="list()"><input v-model="query" aria-label="搜索私有成果" placeholder="搜索标题和正文"/><button>搜索</button></form><button v-for="a in items" :key="a.id" class="yl-artifact-item" @click="open(a.id)"><strong>{{ a.title }}</strong><small>第 {{ a.current_revision }} 版</small></button><p v-if="listing" role="status">正在检索成果…</p><p v-if="!listing && !items.length" class="yl-muted">回答结束后，选择“保存成果”或“转检查清单”。</p><button v-if="cursor" :disabled="listing" @click="list(true)">更多成果</button></template>
    <p v-if="error" role="alert" class="yl-error">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
    <div v-if="pending" class="yl-artifact-pending" role="alert"><p>正文有未保存的修改。继续会放弃这份编辑；已保存版本仍保留。</p><button @click="pending=null">保留编辑</button><button @click="discard">放弃草稿并继续</button></div>
  </section>
</template>
