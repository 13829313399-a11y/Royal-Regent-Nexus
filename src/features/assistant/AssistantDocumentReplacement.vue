<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useAssistantStore } from '@/stores/assistant'
import { assistantApi } from './api'
import type { DocumentFile } from './types'
const props = defineProps<{ file: DocumentFile }>()
const emit = defineEmits<{ replaced: [] }>()
const store = useAssistantStore()
const choice = ref(''), error = ref(''), busy = ref(false)
const candidates = computed(() => (store.drafts[props.file.session_id || '']?.documents || []).filter(d => d.id !== props.file.id && d.parse_status === 'ready' && d.document_version))
let generation = 0, alive = true
watch(() => [props.file.id,props.file.document_version,store.identityGeneration], () => { generation++; choice.value='';error.value='';busy.value=false }, {flush:'sync'})
watch(candidates, values => { if (!values.some(d=>d.id===choice.value)) choice.value='' })
onBeforeUnmount(() => { alive=false;generation++ })
async function replace() {
  const candidate=candidates.value.find(d=>d.id===choice.value)
  if (busy.value || store.anyBusy || !candidate?.document_version || !props.file.document_version) return
  const ticket=++generation, sid=props.file.session_id!
  busy.value=true;error.value=''
  try {
    const result=await assistantApi.replaceDocument(props.file.id,candidate.id,props.file.document_version,candidate.document_version)
    if (!alive || ticket!==generation) return
    const draft=store.drafts[sid]
    if (draft) draft.documents=draft.documents.filter(d=>d.id!==props.file.id).map(d=>d.id===result.file.id?result.file:d)
    emit('replaced')
  } catch(e) { if (alive && ticket===generation) error.value=e instanceof Error?e.message:'替换未完成，原文件保持可用。' }
  finally { if (alive && ticket===generation) busy.value=false }
}
</script>
<template>
  <details class="yl-document-replace">
    <summary>替换文件版本</summary>
    <p>先从输入区上传新版本，解析完成后在下方选择。替换成功会停用旧索引，依赖旧文件的回答及成果全部版本将不可读取或导出。</p>
    <template v-if="candidates.length">
      <select v-model="choice" aria-label="用于替换的新文件" :disabled="busy || store.anyBusy"><option value="">选择已解析的新文件</option><option v-for="item in candidates" :key="item.id" :value="item.id">{{ item.name }} · {{ item.document_version?.slice(0,12) }}</option></select>
      <button type="button" :disabled="!choice || busy || store.anyBusy" @click="replace">{{ busy ? '正在替换…' : '确认替换并停用旧索引' }}</button>
    </template>
    <p v-else>当前会话没有其他可用的新文件。</p>
    <p v-if="store.anyBusy">请先停止生成或等待回答结束。</p>
    <p v-if="error" role="status">{{ error }}</p>
  </details>
</template>
<style scoped>
.yl-document-replace { min-width: 0; margin-top: .75rem; }
.yl-document-replace summary { cursor: pointer; }
.yl-document-replace p { margin: .5rem 0; overflow-wrap: anywhere; }
.yl-document-replace select { display: block; width: 100%; min-width: 0; max-width: 100%; min-height: 40px; margin: .5rem 0; border: 1px solid var(--yl-line); border-radius: 8px; background: var(--yl-paper); padding: 6px 9px; }
.yl-document-replace button { white-space: normal; }
</style>
