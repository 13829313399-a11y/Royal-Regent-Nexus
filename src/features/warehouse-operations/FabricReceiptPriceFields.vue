<script setup lang="ts">
import { computed } from 'vue'
import { Button } from '@/components/ui/button'
import type { ReceiptPriceInput } from '@/api/fabricReceiving'
import { receiptAmount, receiptQuantity } from './receiptQuantities'
import { canonicalPurchasePrice, purchasePriceText } from './purchasePrice'
const props = defineProps<{ quantity?: string; unit: string; reference?: string | null; label?: string }>()
const price = defineModel<string>('price', { required: true })
const currency = defineModel<NonNullable<ReceiptPriceInput['currency']>>('currency', { required: true })
const amount = computed(() => receiptAmount(props.quantity ?? '', price.value))
const referenceInput = computed(() => {
  const value = canonicalPurchasePrice(props.reference)
  return value !== undefined && receiptQuantity(value) !== undefined ? value : undefined
})

function copyReference() {
  if (referenceInput.value === undefined || price.value.trim()) return
  price.value = referenceInput.value
  currency.value = 'CNY'
}
</script>
<template>
  <section class="receipt-price-fields" :aria-label="`${label || ''}入库价格`">
    <label>本次入库单价（每 {{ unit }}）<input v-model="price" :aria-label="`${label || ''}入库单价`" inputmode="decimal" placeholder="选填，留空为未记录" maxlength="32" /></label>
    <label>币种<select v-model="currency" :aria-label="`${label || ''}入库币种`"><option value="">请选择</option><option value="CNY">人民币 CNY</option><option value="HKD">港币 HKD</option><option value="USD">美元 USD</option><option value="EUR">欧元 EUR</option></select></label>
    <div class="receipt-price-amount"><span>本次金额合计</span><strong>{{ price.trim() && currency && amount !== undefined ? `${amount} ${currency}` : '待填写单价与币种' }}</strong><small>实收合计 × 单价，整项四舍五入至两位小数</small></div>
    <div class="receipt-price-reference">
      <p>追货表采购参考单价 <strong>{{ purchasePriceText(reference, unit) }}</strong></p>
      <Button v-if="referenceInput !== undefined" variant="outline" size="sm" type="button" :disabled="!!price.trim()" @click="copyReference">带入人民币参考价</Button>
      <p v-else-if="reference">参考价超出入库单价填写范围，请核对。</p>
    </div>
    <p v-if="price.trim() && (amount === undefined || !currency)" role="note">请填写有效单价并选择币种；不同计价单位需先核对，不自动换算。</p>
  </section>
</template>
<style scoped>
.receipt-price-reference{grid-column:1/-1;display:flex;align-items:center;gap:8px 12px;flex-wrap:wrap}
.receipt-price-reference strong{color:#334155;font-variant-numeric:tabular-nums}
.receipt-price-fields{display:grid;grid-template-columns:1fr 1fr 1.5fr;align-items:start;gap:16px;padding:16px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;margin:16px 0}.receipt-price-amount{display:flex;flex-direction:column;gap:7px;font-size:12px;color:#64748b}.receipt-price-amount strong{font-size:16px;color:#0f766e;font-variant-numeric:tabular-nums}.receipt-price-amount small{font-size:11px}.receipt-price-fields p{grid-column:1/-1;font-size:11px;line-height:1.6;color:#64748b;margin:0}@media(max-width:650px){.receipt-price-fields{grid-template-columns:1fr}.receipt-price-fields p{grid-column:auto}}
</style>
