<script setup lang="ts">
import { Copy, Layers3 } from '@lucide/vue'
import type { InternalQuoteBatchProduct, InternalQuoteStatus } from '@/types/internalQuoteDesk'

const props = withDefaults(defineProps<{
  products: InternalQuoteBatchProduct[]
  currentQuoteId: string
  canManage: boolean
  canCopyBaseline?: boolean
  copyBusyQuoteId: string
}>(), { canCopyBaseline: true })

const emit = defineEmits<{
  switch: [product: InternalQuoteBatchProduct]
  copyBaseline: [product: InternalQuoteBatchProduct]
  copyPackaging: []
}>()

const statusLabels: Record<InternalQuoteStatus, string> = {
  drafting: '填写中',
  pending_review: '填写中',
  fully_approved: '可提交',
  final_pending: '待审核',
  rejected: '已退回',
  released: '已通过',
  exported: '已输出',
  archived: '已归档',
}

const currentProduct = () => props.products.find((product) => product.quoteId === props.currentQuoteId)
const copyAllowed = (product: InternalQuoteBatchProduct | undefined) => Boolean(
  product
  && !product.isBaseline
  && props.canManage
  && props.canCopyBaseline !== false
  && !['final_pending', 'released', 'exported', 'archived'].includes(product.status),
)

function copyCurrentProduct() {
  const product = currentProduct()
  if (product && copyAllowed(product)) emit('copyBaseline', product)
}

function switchProduct(event: Event) {
  const quoteId = (event.target as HTMLSelectElement).value
  const product = props.products.find((item) => item.quoteId === quoteId)
  if (product && product.quoteId !== props.currentQuoteId) emit('switch', product)
}
</script>

<template>
  <section v-if="products.length > 1" class="quote-product-footer-actions" aria-label="批次产品操作">
    <label class="quote-product-footer-select"><span><Layers3 />选择产品</span><select :value="currentQuoteId" aria-label="选择报价产品" @change="switchProduct"><option v-for="product in products" :key="product.quoteId" :value="product.quoteId">{{ String(product.position).padStart(2, '0') }} · {{ product.productName }} · {{ statusLabels[product.status] }}{{ product.isBaseline ? ' · 基准款' : product.differsFromBaseline ? ' · 有差异' : ' · 同基准' }}</option></select></label>
    <button v-if="canManage" type="button" class="quote-product-footer-copy" :disabled="Boolean(copyBusyQuoteId)" @click="emit('copyPackaging')"><Copy />仅复制包装</button>
    <button
      v-if="copyAllowed(currentProduct())"
      type="button"
      class="quote-product-footer-copy"
      :disabled="Boolean(copyBusyQuoteId)"
      @click="copyCurrentProduct"
    >
      <Copy />{{ copyBusyQuoteId === currentQuoteId ? '复制中…' : '复制整份基准款' }}
    </button>
  </section>
</template>

<style scoped>
.quote-product-footer-actions{display:flex;min-width:0;align-items:center;gap:8px}.quote-product-footer-select{display:flex;min-width:0;align-items:center;gap:7px}.quote-product-footer-select>span{display:inline-flex;flex:0 0 auto;align-items:center;gap:4px;color:#0f766e;font-size:11px;font-weight:900}.quote-product-footer-select>span svg{width:14px}.quote-product-footer-select select{width:clamp(220px,25vw,330px);height:36px;min-width:0;border:1px solid #5eead4;border-radius:8px;background:#fff;padding:0 30px 0 10px;color:#0f766e;font-size:11px;font-weight:900;outline:none}.quote-product-footer-select select:focus{border-color:#0d9488;box-shadow:0 0 0 2px rgb(13 148 136/.12)}.quote-product-footer-copy{display:inline-flex;height:36px!important;flex:0 0 auto;align-items:center;justify-content:center;gap:5px;border:1px solid #5eead4!important;border-radius:8px!important;background:#f0fdfa!important;padding:0 10px!important;color:#0f766e!important;font-size:11px!important;font-weight:950!important}.quote-product-footer-copy svg{width:14px}.quote-product-footer-copy:disabled{cursor:wait;opacity:.5}
@media(max-width:900px){.quote-product-footer-actions{width:100%;flex-wrap:wrap}.quote-product-footer-select{flex:1}.quote-product-footer-select select{width:100%}}
</style>
