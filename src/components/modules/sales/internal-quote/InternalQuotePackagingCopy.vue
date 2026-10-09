<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { internalQuoteApi, type ApiPackagingCopyPreview, type ApiPackagingCopyRequest } from '@/api/internalQuote'
import { getApiErrorMessage } from '@/lib/http'
import type { InternalQuote, InternalQuoteBatchProduct } from '@/types/internalQuoteDesk'

const props = defineProps<{ quote: InternalQuote; products: InternalQuoteBatchProduct[]; hasUnsavedChanges?: () => boolean }>()
const emit = defineEmits<{ close: []; copied: [] }>()
const sourceId = ref(props.quote.id)
const targets = ref<string[]>([])
const includeAssembly = ref(false)
const reason = ref('同一报价单多款产品共用包装')
const preview = ref<ApiPackagingCopyPreview>()
const request = ref<ApiPackagingCopyRequest>()
const busy = ref(false)
const error = ref('')
const source = computed(() => props.products.find(row => row.quoteId === sourceId.value))
const candidates = computed(() => props.products.filter(row => row.quoteId !== sourceId.value))
const editable = (product: InternalQuoteBatchProduct) => ['drafting', 'rejected'].includes(product.status)
function ensureSaved() {
  if (props.hasUnsavedChanges?.()) throw new Error('当前页面还有未保存内容，请先保存当前款，再复制包装。')
}
watch([sourceId, targets, includeAssembly, reason], () => { preview.value = undefined; request.value = undefined }, { deep: true })
watch(sourceId, () => { targets.value = targets.value.filter(id => id !== sourceId.value) })
async function showPreview() {
  if (busy.value || !source.value || !targets.value.length) return
  error.value = ''; busy.value = true
  try {
    ensureSaved()
    const body: ApiPackagingCopyRequest = {
      revision: source.value.headerRevision,
      targets: props.products.filter(row => targets.value.includes(row.quoteId)).map(row => ({ quote_id: row.quoteId, revision: row.headerRevision })),
      include_assembly: includeAssembly.value, reason: reason.value.trim(),
    }
    preview.value = await internalQuoteApi.previewPackagingCopy(sourceId.value, body)
    request.value = body
  } catch (cause) { error.value = getApiErrorMessage(cause) }
  finally { busy.value = false }
}
async function apply() {
  if (busy.value || !preview.value || !request.value) return
  error.value = ''; busy.value = true
  try {
    ensureSaved()
    await internalQuoteApi.applyPackagingCopy(sourceId.value, { ...request.value, preview_token: preview.value.preview_token })
    emit('copied')
  } catch (cause) {
    error.value = getApiErrorMessage(cause)
    preview.value = undefined; request.value = undefined
  } finally { busy.value = false }
}
</script>

<template>
  <div class="packaging-backdrop" @click.self="!busy && emit('close')">
    <section class="packaging-dialog" role="dialog" aria-modal="true" aria-labelledby="packaging-copy-title">
      <h2 id="packaging-copy-title">仅复制包装</h2>
      <p>在本报价单内复用包材、纸箱、彩盒 / PDQ 尺寸及包装参数。目标款的产品和配件名称、数量、图片、其他部门资料及报价倍率保留，费用重新核算。</p>
      <label>来源产品<select v-model="sourceId" :disabled="busy" aria-label="包装来源产品"><option v-for="product in products" :key="product.quoteId" :value="product.quoteId">{{ product.productName }}{{ product.quoteId === quote.id ? ` · ${quote.versionLabel}` : '' }}</option></select></label>
      <fieldset :disabled="busy"><legend>接收包装的产品</legend><label v-for="product in candidates" :key="product.quoteId"><input v-model="targets" type="checkbox" :value="product.quoteId" :disabled="!editable(product)">{{ product.productName }}<small v-if="!editable(product)">当前不可覆盖，请先复制新版本</small></label></fieldset>
      <label><input v-model="includeAssembly" type="checkbox" :disabled="busy">同时复制装配部包装工序（保留目标款组装工序及人工基数）</label>
      <label>复制说明<input v-model="reason" maxlength="1000" :disabled="busy" aria-label="包装复制说明"></label>
      <div v-if="preview" class="packaging-preview" role="status"><strong>复制预览：{{ preview.source_name }}</strong><table v-if="preview.material_details?.length"><thead><tr><th>包材 / 规格</th><th>用量</th><th>原币单价</th></tr></thead><tbody><tr v-for="(material, index) in preview.material_details" :key="index"><td>{{ material.item }} {{ material.specification }}</td><td>{{ material.quantity }}</td><td>{{ material.price }} {{ material.currency }}</td></tr></tbody></table><p v-for="target in preview.targets" :key="target.quote_id">{{ target.product_name }}：{{ target.packaging_material_count }} 项包材、{{ target.carton_count }} 项纸箱；{{ target.changed ? (target.replaces_existing ? '将替换已有包装资料' : '将写入包装资料') : '包装资料相同' }}</p><p>确认后按以上范围复制到所选产品。</p></div>
      <p v-if="error" role="alert" class="error">{{ error }}</p>
      <div class="actions"><button type="button" :disabled="busy" @click="emit('close')">取消</button><button v-if="!preview" type="button" :disabled="busy || !targets.length || !reason.trim()" @click="showPreview">预览复制</button><button v-else type="button" :disabled="busy" @click="apply">确认仅复制包装</button></div>
    </section>
  </div>
</template>

<style scoped>
.packaging-backdrop{position:fixed;inset:0;z-index:90;display:grid;place-items:center;background:#0f172a66;padding:20px}.packaging-dialog{width:min(660px,100%);max-height:90vh;overflow:auto;border:1px solid #99f6e4;border-radius:14px;background:white;padding:24px;display:grid;gap:16px;color:#334155}.packaging-dialog h2{margin:0;color:#134e4a;font-size:20px}.packaging-dialog p{margin:0;font-size:13px;line-height:1.7}.packaging-dialog label{display:flex;align-items:center;gap:8px;font-size:13px;flex-wrap:wrap}.packaging-dialog input:not([type=checkbox]),.packaging-dialog select{flex:1;min-width:150px;border:1px solid #cbd5e1;border-radius:7px;padding:8px}.packaging-dialog fieldset{border:1px solid #cbd5e1;border-radius:8px;padding:12px;display:grid;gap:10px}.packaging-dialog small{color:#64748b}.actions{display:flex;justify-content:flex-end;gap:10px}.actions button{padding:9px 14px;border:1px solid #99d5cc;border-radius:8px;background:#f0fdfa;color:#0f766e}.actions button:disabled{opacity:.5;cursor:not-allowed}.packaging-preview{background:#f0fdfa;border-radius:8px;padding:12px;display:grid;gap:8px}.error{color:#b91c1c}
</style>
