<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { internalQuoteApi, type ApiInternalQuoteImportPreview } from '@/api/internalQuote'
import type { OutputLayout } from '@/api/internalQuoteOutput'
import { getApiErrorMessage } from '@/lib/http'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import InternalQuoteImportAssignment from './InternalQuoteImportAssignment.vue'
const props = defineProps<{ quoteId: string; sources: NonNullable<OutputLayout['import_sources']> }>()
const emit = defineEmits<{ close: []; replaced: [] }>()
const store = useInternalQuoteDeskStore()
const sourceId = ref(props.sources.find(s => s.editable)?.id ?? '')
const source = computed(() => props.sources.find(s => s.id === sourceId.value))
const preview = ref<ApiInternalQuoteImportPreview>()
const assignments = ref<Record<string, string>>({})
const busy = ref(false)
const error = ref('')
let active = true
onBeforeUnmount(() => { active = false })
const complete = computed(() => (preview.value?.assignment_rows ?? []).every(r => Boolean(assignments.value[r.key])))
async function choose(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]; input.value = ''
  if (!file || !source.value || busy.value) return
  busy.value = true; error.value = ''; preview.value = undefined; assignments.value = {}
  try {
    const result = await internalQuoteApi.previewImport(props.quoteId, source.value.import_type, file, undefined, source.value.id)
    if (active) preview.value = result
  } catch (cause) { if (active) error.value = getApiErrorMessage(cause) }
  finally { if (active) busy.value = false }
}
async function replace() {
  if (!preview.value || !complete.value || busy.value) return
  busy.value = true; error.value = ''
  try {
    const result = await internalQuoteApi.confirmImport(props.quoteId, preview.value.batch_id, preview.value.target_revision, assignments.value)
    store.applySavedSections(props.quoteId, [result.section])
    if (active) emit('replaced')
  } catch (cause) { if (active) error.value = getApiErrorMessage(cause) }
  finally { if (active) busy.value = false }
}
</script>
<template>
  <DialogRoot :open="true" @update:open="value => { if (!value && !busy) emit('close') }"><DialogPortal><DialogOverlay class="replace-source-overlay" />
    <DialogContent class="replace-source-dialog" @escape-key-down="e => { if (busy) e.preventDefault() }" @pointer-down-outside="e => { if (busy) e.preventDefault() }">
      <DialogTitle>更换报价单</DialogTitle><DialogDescription>确认后清除所选旧文件及其生成的明细，更新为新报价。其他来源和手动新增明细保留。</DialogDescription>
      <label>旧报价单<select v-model="sourceId" :disabled="busy" @change="preview = undefined; error = ''"><option value="">请选择</option><option v-for="item in sources.filter(s => s.editable)" :key="item.id" :value="item.id">{{ item.file_name }}</option></select></label>
      <label>选择新报价单<input type="file" accept=".xlsx,.xlsm,.xls" :disabled="busy || !source" @change="choose"></label>
      <div v-if="preview" class="replace-source-preview"><strong>{{ preview.diff_summary.replaced_file_name }} → {{ preview.source_file_name }}</strong><p>新报价识别 {{ preview.row_count }} 行。原文件关联的批注和截图引用随旧明细一并清除。</p><p v-for="warning in preview.warnings" :key="warning">{{ warning }}</p><InternalQuoteImportAssignment v-if="preview.assignment_rows?.length" v-model="assignments" :rows="preview.assignment_rows" :components="preview.assignment_components ?? []" :disabled="busy" /></div>
      <p v-if="error" class="replace-source-error" role="alert">{{ error }}</p>
      <footer><button :disabled="busy" @click="emit('close')">取消</button><button class="primary" :disabled="busy || !preview || !complete" @click="replace">{{ busy ? '正在处理…' : '确认更换报价单' }}</button></footer>
    </DialogContent>
  </DialogPortal></DialogRoot>
</template>
<style scoped>
.replace-source-overlay{position:fixed;inset:0;z-index:120;background:#173e3559}.replace-source-dialog{position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);z-index:121;width:min(760px,calc(100vw - 32px));max-height:85vh;overflow:auto;padding:24px;border-radius:14px;background:#fff;color:#234b45}.replace-source-dialog h2{margin:0 0 12px;font-size:20px}.replace-source-dialog p{font-size:13px;line-height:1.7}.replace-source-dialog label{display:grid;gap:8px;margin:16px 0;font-size:14px}.replace-source-dialog select,.replace-source-dialog input{padding:10px;border:1px solid #c7dcd4;border-radius:6px}.replace-source-preview{background:#eff9f4;padding:16px;border-radius:8px}.replace-source-error{color:#a13620}.replace-source-dialog footer{display:flex;justify-content:flex-end;gap:12px;margin-top:20px}.replace-source-dialog button{border:1px solid #bad5ca;border-radius:6px;padding:9px 14px;background:#fff;color:#206858;cursor:pointer}.replace-source-dialog button.primary{background:#14796b;color:#fff}.replace-source-dialog button:disabled{opacity:.5;cursor:not-allowed}
</style>
