<script setup lang="ts">
import { ref, watch } from 'vue'
import { internalQuoteApi, type ApiInternalQuoteAlternative } from '@/api/internalQuote'
import { getApiErrorMessage } from '@/lib/http'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import type { InternalQuote, InternalQuoteBatchProduct } from '@/types/internalQuoteDesk'

const props = defineProps<{ quote: InternalQuote; products: InternalQuoteBatchProduct[]; hasUnsavedChanges: () => boolean }>()
const emit = defineEmits<{ close: []; completed: [] }>()
const store = useInternalQuoteDeskStore()
const rows = ref<Array<{ name: string; selected: string; revision: number; options: ApiInternalQuoteAlternative[]; loading: boolean }>>([])
const busy = ref(false)
const loading = ref(true)
const error = ref('')
watch(() => props.quote.id, async (id) => {
  loading.value = true; error.value = ''; rows.value = []
  try {
    const result = await Promise.all(props.products.map(async product => {
      const [family, quote] = await Promise.all([internalQuoteApi.listAlternatives(product.quoteId), internalQuoteApi.get(product.quoteId)])
      return { name: product.productName, selected: product.quoteId, revision: quote.header_revision, loading: false,
        options: family.items.filter(item => !item.archived) }
    }))
    if (props.quote.id === id) rows.value = result
  } catch (cause) { if (props.quote.id === id) error.value = getApiErrorMessage(cause) }
  finally { if (props.quote.id === id) loading.value = false }
}, { immediate: true })
async function selectVersion(index: number) {
  const row = rows.value[index]!
  const id = row.selected
  row.loading = true; row.revision = 0; error.value = ''
  try {
    const quote = await internalQuoteApi.get(id)
    if (row.selected === id) row.revision = quote.header_revision
  } catch (cause) { if (row.selected === id) error.value = getApiErrorMessage(cause) }
  finally { if (row.selected === id) row.loading = false }
}
async function output() {
  if (busy.value) return
  if (props.hasUnsavedChanges()) { error.value = '当前页面还有未保存内容，请先保存当前款。'; return }
  if (rows.value.length !== props.products.length || rows.value.some(row => row.loading || !row.revision)) return
  busy.value = true; error.value = ''
  try {
    await store.exportSeries(props.quote.id, rows.value.map(row => ({ quote_id: row.selected, revision: row.revision })), `${props.quote.batchQuoteNo || props.quote.quoteNo}-系列报价.xlsx`)
    emit('completed')
  } catch (cause) { error.value = getApiErrorMessage(cause) }
  finally { busy.value = false }
}
</script>

<template>
  <div class="series-export-backdrop">
    <section role="dialog" aria-modal="true" aria-labelledby="series-export-title" class="series-export-dialog">
      <h2 id="series-export-title">系列报价一起输出</h2>
      <p>生成一个 Excel，每款一个工作表。请选择各款需要输出的方案版本。</p>
      <p>未输出的版本会在资料完整后一起输出并冻结；已输出的版本沿用原文件内容。</p>
      <p v-if="loading" role="status">正在读取系列报价…</p>
      <label v-for="(row, index) in rows" :key="index"><span>{{ index + 1 }}. {{ row.name }}</span><select v-model="row.selected" :aria-label="`${row.name} 输出版本`" :disabled="busy || row.loading" @change="selectVersion(index)"><option v-for="option in row.options" :key="option.quote_id" :value="option.quote_id">{{ option.scenario_name }} · {{ option.version_label }}{{ option.status === 'exported' ? '（已输出）' : '' }}</option></select></label>
      <p v-if="error" role="alert">{{ error }}</p>
      <footer><button type="button" :disabled="busy" @click="emit('close')">取消</button><button type="button" :disabled="busy || loading || rows.length !== products.length || rows.some(row => row.loading || !row.revision || !row.options.some(option => option.quote_id === row.selected))" @click="output">{{ busy ? '系列输出中…' : `确认输出全部 ${products.length} 款` }}</button></footer>
    </section>
  </div>
</template>

<style scoped>
.series-export-backdrop{position:fixed;inset:0;z-index:80;display:grid;place-items:center;background:#0f172a66;padding:20px}.series-export-dialog{width:min(620px,100%);max-height:85vh;overflow:auto;border-radius:16px;background:white;padding:24px;box-shadow:0 20px 60px #0f172a33}.series-export-dialog h2{font-size:20px;margin:0 0 14px}.series-export-dialog p{font-size:13px;color:#64748b;line-height:1.6}.series-export-dialog label{display:grid;gap:6px;margin:14px 0;font-size:14px}.series-export-dialog select{padding:9px;border:1px solid #cbd5e1;border-radius:8px;background:white}.series-export-dialog footer{display:flex;justify-content:flex-end;gap:10px;margin-top:22px}.series-export-dialog button{padding:10px 16px;border:1px solid #99f6e4;border-radius:8px;background:#f0fdfa;color:#0f766e}.series-export-dialog button:disabled{opacity:.5}.series-export-dialog [role=alert]{color:#b91c1c}
</style>
