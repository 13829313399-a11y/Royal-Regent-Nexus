<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { DialogContent, DialogDescription, DialogOverlay, DialogPortal, DialogRoot, DialogTitle } from 'reka-ui'
import { internalQuoteApi, type ApiInternalQuoteAlternative } from '@/api/internalQuote'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import { getApiErrorMessage } from '@/lib/http'
import type { InternalQuote } from '@/types/internalQuoteDesk'

const props = defineProps<{ quote: InternalQuote; hasUnsavedChanges?: () => boolean }>()
const emit = defineEmits<{ close: []; completed: [] }>()
const store = useInternalQuoteDeskStore()
const options = ref<ApiInternalQuoteAlternative[]>([])
const selected = ref<string[]>([])
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const rows = computed(() => options.value.filter(row => selected.value.includes(row.quote_id)))
let generation = 0
onBeforeUnmount(() => { generation += 1 })
watch(() => props.quote.id, async id => {
  const current = ++generation
  options.value = []; selected.value = []; loading.value = true; error.value = ''
  try {
    const family = await internalQuoteApi.listAlternatives(id)
    if (current !== generation) return
    options.value = family.items.filter(row => !row.archived)
  } catch (cause) { if (current === generation) error.value = getApiErrorMessage(cause) }
  finally { if (current === generation) loading.value = false }
}, { immediate: true })
async function output() {
  if (busy.value || loading.value || rows.value.length < 2 || rows.value.length > 20) return
  if (props.hasUnsavedChanges?.()) { error.value = '当前页面还有未保存内容，请先保存当前款，再合并输出。'; return }
  const id = props.quote.id, current = generation
  busy.value = true; error.value = ''
  try {
    const versions = await Promise.all(rows.value.map(async row => {
      const quote = await internalQuoteApi.get(row.quote_id)
      return { quote_id: row.quote_id, revision: quote.header_revision }
    }))
    if (id !== props.quote.id || current !== generation) return
    if (props.hasUnsavedChanges?.()) throw new Error('当前页面还有未保存内容，请先保存当前款，再合并输出。')
    await store.exportAlternatives(id, versions, `${props.quote.quoteNo}-多方案报价.xlsx`)
    if (id === props.quote.id && current === generation) emit('completed')
  } catch (cause) { if (current === generation) error.value = getApiErrorMessage(cause) }
  finally { busy.value = false }
}
</script>

<template>
  <DialogRoot :open="true" @update:open="!$event && !busy && emit('close')">
    <DialogPortal>
      <DialogOverlay class="alternative-export-overlay" />
      <DialogContent class="alternative-export-dialog" @escape-key-down="busy && $event.preventDefault()" @interact-outside="$event.preventDefault()">
        <DialogTitle class="title">多方案合并输出</DialogTitle>
        <DialogDescription class="description">勾选同一产品的 2–20 个方案版本。一个 Excel 内含包装、MOQ、出厂价汇总对比，详细成本各放一个工作表。</DialogDescription>
        <p class="notice">已输出版本沿用原文件；未输出版本通过核价后会一并输出并冻结。任一版本不满足条件时，全部取消，不改变历史版本。</p>
        <p v-if="loading" role="status">正在读取方案…</p>
        <fieldset :disabled="busy || loading" class="options">
          <legend>选择要对比的方案版本</legend>
          <label v-for="row in options" :key="row.quote_id">
            <input v-model="selected" type="checkbox" :value="row.quote_id" :aria-label="`${row.scenario_name} · ${row.version_label}`">
            <span><strong>{{ row.scenario_name }} · {{ row.version_label }}</strong><small>{{ ['released', 'exported'].includes(row.status) ? '已输出，保留原文件' : '未输出，将校验并冻结' }}</small></span>
          </label>
          <p v-if="!loading && options.length < 2">至少需要两个未归档方案版本。</p>
        </fieldset>
        <p v-if="error" role="alert" class="error">{{ error }}</p>
        <footer><span>已选 {{ rows.length }} 个版本</span><button :disabled="busy" @click="emit('close')">取消</button><button class="primary" :disabled="busy || loading || rows.length < 2 || rows.length > 20" @click="output">{{ busy ? '正在合并输出…' : '确认合并输出' }}</button></footer>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style scoped>
.alternative-export-overlay{position:fixed;inset:0;background:#0f172a66;z-index:1100}.alternative-export-dialog{position:fixed;z-index:1101;left:50%;top:50%;transform:translate(-50%,-50%);width:min(640px,calc(100vw - 32px));max-height:85vh;overflow:auto;box-sizing:border-box;border-radius:16px;background:white;padding:24px;color:#334155;box-shadow:0 20px 60px #0f172a33}.title{font-size:20px;font-weight:700;color:#134e4a;margin:0}.description,.notice{font-size:13px;line-height:1.7}.notice{background:#f0fdfa;padding:12px;border-radius:8px}.options{border:1px solid #e2e8f0;border-radius:8px;max-height:40vh;overflow:auto}.options legend{font-size:13px}.options label{display:flex;align-items:center;gap:10px;padding:12px;border-bottom:1px solid #f1f5f9;cursor:pointer}.options span{display:grid;gap:4px}.options strong{font-size:14px}.options small{font-size:12px;color:#64748b}footer{display:flex;align-items:center;gap:10px;margin-top:16px}footer span{margin-right:auto;font-size:13px}button{padding:9px 14px;border:1px solid #99d5cc;border-radius:8px;color:#0f766e;background:white;cursor:pointer}button.primary{background:#0f766e;color:white}button:disabled{opacity:.5;cursor:not-allowed}.error{color:#b91c1c;font-size:13px}
</style>
