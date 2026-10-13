<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { assistantApi } from './api'
import type { Artifact } from './types'
const props = defineProps<{ selected?: string }>()
const items = ref<Artifact[]>([]), current = ref<Artifact | null>(null), text = ref(''), error = ref(''), notice = ref(''), cursor = ref<string | null>(null)
const revision = ref(1), query = ref('')
const listing = ref(false), saving = ref(false)
let listGeneration = 0, openGeneration = 0, alive = true, appliedQuery = ''
function failed(e: unknown) { error.value = e instanceof Error ? e.message : '成果操作未完成' }
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
async function open(id: string, version?: number) {
  const ticket = ++openGeneration
  try { const a = await assistantApi.artifact(id, version); if (!alive || ticket !== openGeneration) return; current.value = a; text.value = a.content; revision.value = a.revision; error.value = ''; notice.value = '' } catch(e) { if (alive && ticket === openGeneration) failed(e) }
}
function back() { openGeneration++; current.value = null }
async function save() {
  if (!current.value || saving.value) return
  const ticket = ++openGeneration, id = current.value.id, base = current.value.current_revision, content = text.value
  saving.value = true
  try { const a = await assistantApi.reviseArtifact(id, base, content); if (!alive || ticket !== openGeneration) return; current.value = a; revision.value = a.revision; notice.value = '新版本已保存'; error.value = ''; await list() } catch(e) { if (alive && ticket === openGeneration) failed(e) }
  finally { if (alive) saving.value = false }
}
async function download(format: string) { if (!current.value) return; try { const b = await assistantApi.exportArtifact(current.value.id, format, revision.value); const url = URL.createObjectURL(b); const a = document.createElement('a'); a.href=url; a.download=`曜灵成果.${format}`; a.click(); setTimeout(() => URL.revokeObjectURL(url),1000); notice.value = '已生成下载文件' } catch(e) { failed(e) } }
watch(() => props.selected, id => { if (id) void open(id) })
onMounted(() => { void list(); if(props.selected) void open(props.selected) })
onBeforeUnmount(() => { alive = false; listGeneration++; openGeneration++ })
</script>
<template>
  <section class="yl-artifacts"><p class="yl-muted">仅本人可见。删除源会话或文件、撤销来源权限后，相关成果全部版本停止读取和导出。</p>
    <template v-if="current"><button @click="back">返回成果列表</button><h3>{{ current.title }}</h3><label>版本 <select v-model="revision" @change="open(current!.id, revision)"><option v-for="v in current.current_revision" :key="v" :value="v">{{ v }}</option></select></label><textarea v-model="text" aria-label="成果正文" rows="12"/><div class="yl-artifact-actions"><button @click="save" :disabled="saving || !text.trim() || revision !== current.current_revision">保存为新版本</button><button @click="open(current!.id)">读取最新版本</button><button v-for="format in current.export_formats" :key="format" @click="download(format)">导出 {{ format.toUpperCase() }}</button></div></template>
    <template v-else><form @submit.prevent="list()"><input v-model="query" aria-label="搜索私有成果" placeholder="搜索标题和正文"/><button>搜索</button></form><button v-for="a in items" :key="a.id" class="yl-artifact-item" @click="open(a.id)"><strong>{{ a.title }}</strong><small>第 {{ a.current_revision }} 版</small></button><p v-if="listing" role="status">正在检索成果…</p><p v-if="!listing && !items.length" class="yl-muted">回答结束后，选择“保存成果”或“转检查清单”。</p><button v-if="cursor" :disabled="listing" @click="list(true)">更多成果</button></template>
    <p v-if="error" role="alert" class="yl-error">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
  </section>
</template>
