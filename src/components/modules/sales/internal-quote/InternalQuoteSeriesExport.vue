<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { internalQuoteApi, type ApiInternalQuote, type ApiInternalQuoteAlternative } from '@/api/internalQuote'
import { getApiErrorMessage } from '@/lib/http'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import type { InternalQuote, InternalQuoteBatchProduct } from '@/types/internalQuoteDesk'

const props = defineProps<{ quote: InternalQuote; products: InternalQuoteBatchProduct[]; hasUnsavedChanges: () => boolean }>()
const emit = defineEmits<{ close: []; completed: []; resolve: [quoteId: string, sectionCode: string] }>()
const store = useInternalQuoteDeskStore()
const rows = ref<Array<{ name: string; selected: string; revision: number; options: ApiInternalQuoteAlternative[]; loading: boolean; problems: Array<{ section_code: string; section_name: string; reason: string }> }>>([])
const busy = ref(false)
const loading = ref(true)
const error = ref('')
let generation = 0
onBeforeUnmount(() => { generation += 1 })
function problemsFor(quote: ApiInternalQuote) {
  if (quote.document_archive || quote.version_archived || quote.status === 'archived') return [{ section_code: '', section_name: '报价', reason: '报价已归档，请先恢复后输出。' }]
  if (quote.final_release_status === 'issued') return []
  const problems = [...(quote.readiness?.blockers ?? [])].map(({ section_code, section_name, reason }) => ({ section_code, section_name, reason }))
  if (quote.formula_recalculation_required) problems.push({ section_code: 'formula', section_name: '计算公式', reason: '仍有旧公式核算，请前往处理旧公式。' })
  if (quote.module_version && quote.module_version !== 'v4' && quote.final_release_status !== 'approved') problems.push({ section_code: '', section_name: '审核', reason: '历史报价须通过最终审核后才能输出。' })
  return problems
}
function resolve(quoteId: string, sectionCode: string) {
  if (busy.value) return
  if (props.hasUnsavedChanges()) { error.value = '请先保存当前页面，再前往处理。'; return }
  emit('resolve', quoteId, sectionCode)
}
async function loadRows() {
  const id = props.quote.id
  const current = ++generation
  loading.value = true; error.value = ''; rows.value = []
  try {
    const result = await Promise.all(props.products.map(async product => {
      const [family, quote] = await Promise.all([internalQuoteApi.listAlternatives(product.quoteId), internalQuoteApi.get(product.quoteId)])
      return { name: product.productName, selected: product.quoteId, revision: quote.header_revision, loading: false, problems: problemsFor(quote),
        options: family.items.filter(item => !item.archived) }
    }))
    if (props.quote.id === id && generation === current) rows.value = result
  } catch (cause) { if (props.quote.id === id && generation === current) error.value = getApiErrorMessage(cause) }
  finally { if (props.quote.id === id && generation === current) loading.value = false }
}
watch(() => [props.quote.id, props.quote.factoryId, props.products.map(product => product.quoteId).join(',')], loadRows, { immediate: true })
async function selectVersion(index: number, keepError = false) {
  const row = rows.value[index]!
  const id = row.selected
  const current = generation
  row.loading = true; row.revision = 0; if (!keepError) error.value = ''
  try {
    const quote = await internalQuoteApi.get(id)
    if (row.selected === id && generation === current) { row.revision = quote.header_revision; row.problems = problemsFor(quote) }
  } catch (cause) { if (row.selected === id && generation === current) error.value = getApiErrorMessage(cause) }
  finally { if (row.selected === id && generation === current) row.loading = false }
}
async function refreshStatus() {
  if (rows.value.length !== props.products.length) { await loadRows(); return }
  await Promise.all(rows.value.map((_, index) => selectVersion(index)))
}
async function output() {
  if (busy.value) return
  if (props.hasUnsavedChanges()) { error.value = '当前页面还有未保存内容，请先保存当前款。'; return }
  if (rows.value.length !== props.products.length || rows.value.some(row => row.loading || !row.revision)) return
  if (rows.value.some(row => row.problems.length)) { error.value = '请先处理各款下方列出的待补项目，再重新读取状态。'; return }
  const current = generation
  busy.value = true; error.value = ''
  try {
    await store.exportSeries(props.quote.id, rows.value.map(row => ({ quote_id: row.selected, revision: row.revision })), `${props.quote.batchQuoteNo || props.quote.quoteNo}-系列报价.xlsx`)
    if (current === generation) emit('completed')
  } catch (cause) { if (current === generation) { error.value = getApiErrorMessage(cause); await Promise.all(rows.value.map((_, index) => selectVersion(index, true))) } }
  finally { if (current === generation) busy.value = false }
}
</script>

<template>
  <div class="series-export-backdrop">
    <section role="dialog" aria-modal="true" aria-labelledby="series-export-title" class="series-export-dialog">
      <h2 id="series-export-title">系列报价一起输出</h2>
      <p>生成一个 Excel，每款一个工作表。请选择各款需要输出的方案版本。</p>
      <p>未输出的版本会在资料完整后一起输出并冻结；已输出的版本沿用原文件内容。</p>
      <p v-if="loading" role="status">正在读取系列报价…</p>
      <div v-for="(row, index) in rows" :key="index" class="series-product"><label><span>{{ index + 1 }}. {{ row.name }}</span><select v-model="row.selected" :aria-label="`${row.name} 输出版本`" :disabled="busy || row.loading" @change="selectVersion(index)"><option v-for="option in row.options" :key="option.quote_id" :value="option.quote_id">{{ option.scenario_name }} · {{ option.version_label }}{{ option.status === 'exported' ? '（已输出）' : '' }}</option></select></label>
        <ul v-if="row.problems.length" class="series-problems"><li v-for="(problem, pi) in row.problems" :key="pi"><span>{{ problem.section_name }}：{{ problem.reason }}</span><button type="button" :disabled="busy || row.loading" @click="resolve(row.selected, problem.section_code)">前往处理</button></li></ul>
        <p v-else-if="!row.loading && row.revision > 0" class="series-ready">已就绪；已输出版本沿用原文件。</p>
        <p v-else-if="!row.loading">状态未能读取，请重新读取状态。</p>
      </div>
      <p v-if="error" role="alert">{{ error }}</p>
      <footer><button type="button" :disabled="busy || loading || rows.some(row => row.loading)" @click="refreshStatus">重新读取状态</button><button type="button" :disabled="busy" @click="emit('close')">取消</button><button type="button" :disabled="busy || loading || rows.length !== products.length || rows.some(row => row.loading || !row.revision || !row.options.some(option => option.quote_id === row.selected))" @click="output">{{ busy ? '系列输出中…' : `确认输出全部 ${products.length} 款` }}</button></footer>
    </section>
  </div>
</template>

<style scoped>
.series-export-backdrop{position:fixed;inset:0;z-index:80;display:grid;place-items:center;background:#0f172a66;padding:20px}.series-export-dialog{width:min(620px,100%);max-height:85vh;overflow:auto;border-radius:16px;background:white;padding:24px;box-shadow:0 20px 60px #0f172a33}.series-export-dialog h2{font-size:20px;margin:0 0 14px}.series-export-dialog p{font-size:13px;color:#64748b;line-height:1.6}.series-export-dialog label{display:grid;gap:6px;margin:14px 0;font-size:14px}.series-export-dialog select{padding:9px;border:1px solid #cbd5e1;border-radius:8px;background:white}.series-export-dialog footer{display:flex;justify-content:flex-end;gap:10px;margin-top:22px}.series-export-dialog button{padding:10px 16px;border:1px solid #99f6e4;border-radius:8px;background:#f0fdfa;color:#0f766e}.series-export-dialog button:disabled{opacity:.5}.series-export-dialog [role=alert]{color:#b91c1c}
.series-problems{list-style:none;padding:0;margin:8px 0;color:#92400e;font-size:13px}.series-problems li{display:flex;gap:12px;align-items:center;justify-content:space-between;padding:8px;background:#fffbeb;border:1px solid #fde68a;border-radius:8px;margin-top:6px}.series-problems span{white-space:pre-line;overflow-wrap:anywhere}.series-problems button{flex-shrink:0}.series-export-dialog [role=alert]{white-space:pre-line;overflow-wrap:anywhere}.series-export-dialog .series-ready{color:#0f766e}.series-export-dialog footer{flex-wrap:wrap}@media(max-width:600px){.series-problems li{align-items:flex-start;flex-direction:column}}
</style>
