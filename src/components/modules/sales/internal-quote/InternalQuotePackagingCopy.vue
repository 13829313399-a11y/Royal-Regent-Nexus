<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { internalQuoteApi, type ApiInternalQuoteBatchProduct, type ApiPackagingCopyPreview, type ApiPackagingCopyRequest } from '@/api/internalQuote'
import { getApiErrorMessage } from '@/lib/http'
import type { InternalQuote, InternalQuoteBatchProduct } from '@/types/internalQuoteDesk'

const props = defineProps<{ quote: InternalQuote; products: InternalQuoteBatchProduct[]; hasUnsavedChanges?: () => boolean }>()
const emit = defineEmits<{ close: []; copied: []; resolveFormula: [quoteId: string] }>()
// The currently open product may be the empty receiver: choose the source explicitly.
const sourceId = ref('')
const products = ref<ApiInternalQuoteBatchProduct[]>([])
const targets = ref<string[]>([])
const includeAssembly = ref(false)
const reason = ref('同一报价单多款产品共用包装')
const preview = ref<ApiPackagingCopyPreview>()
const request = ref<ApiPackagingCopyRequest>()
const busy = ref(false)
const loading = ref(false)
const error = ref('')
let generation = 0
const source = computed(() => products.value.find(row => row.quote_id === sourceId.value))
const candidates = computed(() => products.value.filter(row => row.quote_id !== sourceId.value))
const receivers = computed(() => products.value.filter(row => targets.value.includes(row.quote_id)))
const productLabel = (product: ApiInternalQuoteBatchProduct) => [product.product_name, product.scenario_name, product.version_label].filter(Boolean).join(' · ')
function targetIssue(product: ApiInternalQuoteBatchProduct) {
  const status = product.packaging_copy
  if (!status) return '包装状态不可用，请刷新状态后重试'
  return status.target_issue || (includeAssembly.value ? status.assembly_target_issue : '')
}
const sourceIssues = computed(() => {
  if (!source.value) return []
  const status = source.value.packaging_copy
  if (!status) return ['包装状态不可用，请刷新状态后重试']
  return [status.source_issue, includeAssembly.value ? status.assembly_issue : ''].filter(Boolean)
})
const canPreview = computed(() => !loading.value && !busy.value && !!source.value && targets.value.length > 0
  && !sourceIssues.value.length && receivers.value.every(row => !targetIssue(row)) && !!reason.value.trim())
function resetPreview() { preview.value = undefined; request.value = undefined }
function ensureSaved() {
  if (props.hasUnsavedChanges?.()) throw new Error('当前页面还有未保存内容，请先保存当前款，再复制包装。')
}
function resolveSourceFormula() {
  if (loading.value || busy.value || !source.value?.packaging_copy?.formula_recalculation_required) return
  error.value = ''
  try {
    ensureSaved()
    emit('resolveFormula', source.value.quote_id)
  } catch (cause) { error.value = getApiErrorMessage(cause) }
}
async function refreshProducts() {
  const ticket = ++generation
  const quoteId = props.quote.id
  resetPreview(); loading.value = true; error.value = ''; products.value = []
  try {
    const rows = await internalQuoteApi.listBatchProducts(quoteId)
    if (ticket !== generation) return
    products.value = rows
    if (!rows.some(row => row.quote_id === sourceId.value)) sourceId.value = ''
    targets.value = targets.value.filter(id => rows.some(row => row.quote_id === id && id !== sourceId.value && !targetIssue(row)))
  } catch (cause) {
    if (ticket === generation) error.value = '读取包装状态失败：' + getApiErrorMessage(cause)
  } finally {
    if (ticket === generation) loading.value = false
  }
}
watch(() => [props.quote.id, props.quote.factoryId], () => {
  sourceId.value = ''; targets.value = []; void refreshProducts()
}, { immediate: true })
onBeforeUnmount(() => { generation += 1 })
watch([sourceId, targets, includeAssembly, reason], resetPreview, { deep: true })
watch([sourceId, includeAssembly], () => {
  error.value = ''
  targets.value = targets.value.filter(id => id !== sourceId.value && products.value.some(row => row.quote_id === id && !targetIssue(row)))
})
async function showPreview() {
  if (!canPreview.value || !source.value) return
  const ticket = generation
  error.value = ''; busy.value = true
  try {
    ensureSaved()
    const body: ApiPackagingCopyRequest = {
      revision: source.value.header_revision,
      targets: receivers.value.map(row => ({ quote_id: row.quote_id, revision: row.header_revision })),
      include_assembly: includeAssembly.value, reason: reason.value.trim(),
    }
    const result = await internalQuoteApi.previewPackagingCopy(sourceId.value, body)
    if (ticket !== generation) return
    preview.value = result; request.value = body
  } catch (cause) { if (ticket === generation) error.value = getApiErrorMessage(cause) }
  finally { busy.value = false }
}
async function apply() {
  if (busy.value || !preview.value || !request.value) return
  const ticket = generation
  error.value = ''; busy.value = true
  try {
    ensureSaved()
    await internalQuoteApi.applyPackagingCopy(sourceId.value, { ...request.value, preview_token: preview.value.preview_token })
    if (ticket === generation) emit('copied')
  } catch (cause) {
    if (ticket === generation) { error.value = getApiErrorMessage(cause); resetPreview() }
  } finally { busy.value = false }
}
</script>

<template>
  <div class="packaging-backdrop" @click.self="!busy && emit('close')">
    <section class="packaging-dialog" role="dialog" aria-modal="true" aria-labelledby="packaging-copy-title" :aria-busy="loading || busy">
      <header class="packaging-heading">
        <div><h2 id="packaging-copy-title">仅复制包装</h2><p>先选已有包装资料的产品，再选要接收包装的产品。</p></div>
        <button type="button" :disabled="busy || loading" @click="refreshProducts">刷新状态</button>
      </header>
      <p>复用包材、纸箱、彩盒 / PDQ 尺寸及包装参数。接收款的产品名称、配件、数量、图片和其他部门资料保留，费用重新核算。</p>
      <p v-if="loading" role="status">正在读取各款最新包装状态…</p>
      <label class="packaging-source"><strong>从哪款复制</strong><select v-model="sourceId" :disabled="busy || loading" aria-label="包装来源产品">
        <option value="" disabled>请选择已有包装资料的产品</option>
        <option v-for="product in products" :key="product.quote_id" :value="product.quote_id">{{ productLabel(product) }}{{ product.archived ? ' · 已归档' : '' }}</option>
      </select></label>
      <div v-if="source?.packaging_copy" class="packaging-source-status" aria-label="来源包装资料">
        <strong>{{ productLabel(source) }}<span v-if="source.archived"> · 已归档</span></strong>
        <div class="packaging-counts"><span>包材 <b>{{ source.packaging_copy.material_count }}</b> 项</span><span>纸箱 <b>{{ source.packaging_copy.carton_count }}</b> 项</span><span>包装工序组 <b>{{ source.packaging_copy.packaging_group_count }}</b> 组</span><span>包装人工 <b>{{ source.packaging_copy.packaging_labor_hkd === null ? '待核算' : 'HKD ' + source.packaging_copy.packaging_labor_hkd }}</b></span></div>
        <p v-if="!sourceIssues.length" class="ready">{{ includeAssembly ? '业务部和装配部已保存，核算有效' : '业务部已保存，核算有效' }}</p>
        <p v-for="issue in sourceIssues" :key="issue" class="error" role="alert">{{ issue }}</p>
        <div v-if="source.packaging_copy.formula_recalculation_required"><button type="button" :disabled="busy || loading" @click="resolveSourceFormula">前往来源款处理</button><small>打开来源款的公式处理入口；重算需要填写原因并确认。</small></div>
      </div>
      <fieldset :disabled="busy || loading"><legend>复制到哪些款（接收方）</legend>
        <label v-for="product in candidates" :key="product.quote_id" class="packaging-target">
          <input v-model="targets" type="checkbox" :value="product.quote_id" :aria-label="'接收包装：' + productLabel(product)" :disabled="!!targetIssue(product)">
          <span><strong>{{ productLabel(product) }}</strong><small v-if="targetIssue(product)">{{ targetIssue(product) }}</small><small v-else>现有包材、纸箱及包装参数将被来源资料替换</small></span>
        </label>
      </fieldset>
      <label class="packaging-assembly"><input v-model="includeAssembly" type="checkbox" :disabled="busy || loading">同时复制装配部包装工序（保留接收款组装工序及人工基数）</label>
      <div class="packaging-direction" aria-label="包装复制方向"><strong>{{ source ? productLabel(source) : '请选择来源产品' }}</strong><span aria-hidden="true">→</span><strong>{{ receivers.length ? receivers.map(productLabel).join('、') : '请选择接收产品' }}</strong></div>
      <p class="packaging-scope">{{ includeAssembly ? '复制范围：包装资料＋包装工序；接收款包装人工按其自身人工基数重新核算。' : '复制范围：包装资料；不会复制装配部包装工序或包装人工。' }}</p>
      <label>复制说明<input v-model="reason" :disabled="busy" maxlength="1000" aria-label="包装复制说明"></label>
      <div v-if="preview" class="packaging-preview" role="status"><strong>复制预览：{{ preview.source_name }}</strong><div class="packaging-table"><table v-if="preview.material_details?.length"><thead><tr><th>包材 / 规格</th><th>用量</th><th>原币单价</th></tr></thead><tbody><tr v-for="(material, index) in preview.material_details" :key="index"><td>{{ material.item }} {{ material.specification }}</td><td>{{ material.quantity }}</td><td>{{ material.price }} {{ material.currency }}</td></tr></tbody></table></div><p v-for="target in preview.targets" :key="target.quote_id">{{ target.product_name }}：{{ target.packaging_material_count }} 项包材、{{ target.carton_count }} 项纸箱；{{ target.changed ? (target.replaces_existing ? '将替换已有包装资料' : '将写入包装资料') : '包装资料相同' }}</p><p>请核对上方复制方向，确认后写入所选接收款。</p></div>
      <p v-if="error" role="alert" class="error">{{ error }}</p>
      <div class="actions"><button type="button" :disabled="busy" @click="emit('close')">取消</button><button v-if="!preview" type="button" class="primary" :disabled="!canPreview" @click="showPreview">预览复制</button><button v-else type="button" class="primary" :disabled="busy" @click="apply">确认仅复制包装</button></div>
    </section>
  </div>
</template>

<style scoped>
.packaging-backdrop{position:fixed;inset:0;z-index:90;display:grid;place-items:center;background:#0f172a66;padding:20px}
.packaging-dialog{box-sizing:border-box;width:min(720px,100%);max-height:90vh;overflow:auto;border:1px solid #99f6e4;border-radius:14px;background:white;padding:24px;display:grid;gap:16px;color:#334155;font-size:13px;overflow-wrap:anywhere}
.packaging-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.packaging-heading button{flex-shrink:0}.packaging-dialog h2{margin:0 0 6px;color:#134e4a;font-size:20px}.packaging-dialog p{margin:0;line-height:1.7}
.packaging-dialog label{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.packaging-dialog input:not([type=checkbox]),.packaging-dialog select{flex:1;min-width:0;max-width:100%;border:1px solid #cbd5e1;border-radius:7px;padding:8px}.packaging-source{align-items:stretch!important;flex-direction:column}
.packaging-dialog fieldset{min-width:0;border:1px solid #cbd5e1;border-radius:8px;padding:12px;display:grid;gap:12px}.packaging-target{align-items:flex-start!important;flex-wrap:nowrap!important}.packaging-target input{margin-top:4px;flex-shrink:0}.packaging-target strong{font-weight:600}.packaging-dialog small{display:block;color:#64748b;margin-top:3px;line-height:1.5}
.packaging-assembly{flex-wrap:nowrap!important;align-items:flex-start!important}.packaging-assembly input{margin-top:3px;flex-shrink:0}.packaging-source-status{background:#f8fafc;border:1px solid #e2e8f0;padding:12px;border-radius:8px;display:grid;gap:8px}.packaging-counts{display:flex;gap:8px 20px;flex-wrap:wrap}.packaging-direction{display:flex;align-items:center;gap:12px;padding:12px;border:1px solid #99f6e4;border-radius:8px;background:#f0fdfa;color:#134e4a}.packaging-direction strong{flex:1;min-width:0}.packaging-scope{color:#64748b}.ready{color:#047857}
.actions{display:flex;justify-content:flex-end;gap:10px}.packaging-dialog button{padding:9px 14px;border:1px solid #99d5cc;border-radius:8px;background:#f0fdfa;color:#0f766e}.packaging-dialog button.primary{background:#0f766e;color:white}.packaging-dialog button:disabled{opacity:.5;cursor:not-allowed}.packaging-preview{background:#f0fdfa;border-radius:8px;padding:12px;display:grid;gap:8px}.packaging-table{overflow:auto}.packaging-table table{width:100%;border-collapse:collapse;text-align:left}.packaging-table th,.packaging-table td{padding:6px;border-bottom:1px solid #d5e0e2}.error{color:#b91c1c}
@media(max-width:600px){.packaging-backdrop{padding:12px}.packaging-dialog{padding:16px;max-height:94vh}.packaging-heading{flex-wrap:wrap}.packaging-direction{align-items:flex-start;flex-direction:column}.packaging-counts{gap:8px 12px}}
</style>
