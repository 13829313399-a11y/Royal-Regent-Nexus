<script setup lang="ts">
import { computed } from 'vue'
import type { HandoverLine, HandoverPurchaseSource } from '@/api/materialHandover'
import { canonicalPurchasePrice, purchasePriceText } from '../warehouse-operations/purchasePrice'

const props = defineProps<{ source: HandoverPurchaseSource; line: HandoverLine }>()
const priceNote = computed(() => {
  const { line, source } = props
  const reference = source.purchase_price
  if (!line.unit_price || !reference || reference.unit_price === null) return ''
  if (!line.currency || !line.price_unit) return '原送货单的币种或计价单位待补。'
  if (line.currency !== reference.currency || line.price_unit !== reference.price_unit) {
    return '原送货单与采购的币种或计价单位不同，请核对。'
  }
  const original = canonicalPurchasePrice(line.unit_price)
  const purchase = canonicalPurchasePrice(reference.unit_price)
  if (original === undefined || purchase === undefined) return '原送货单与采购单价待核对。'
  return original === purchase ? '' : '原送货单与采购单价有差异，请核对。'
})
</script>

<template>
  <div class="purchase-details">
    <small>本系统已收 {{ source.received }}，采购尚欠 {{ source.remaining ?? '待核对' }} {{ source.unit }}。</small>
    <dl>
      <div><dt>采购单号</dt><dd>{{ source.order_no }}</dd></div>
      <div v-if="source.production_no"><dt>生产单号</dt><dd>{{ source.production_no }}</dd></div>
      <div v-if="source.plan_no"><dt>计划跟踪号</dt><dd>{{ source.plan_no }}</dd></div>
      <div v-if="source.contract_no"><dt>采购合同号</dt><dd>{{ source.contract_no }}</dd></div>
      <div v-if="source.ordered_quantity"><dt>采购下单量</dt><dd>{{ source.ordered_quantity }} {{ source.unit }}</dd></div>
      <div v-if="line.ordered_quantity"><dt>原单下单量</dt><dd>{{ line.ordered_quantity }} {{ line.unit }}</dd></div>
    </dl>
    <dl v-if="source.purchase_price" class="purchase-prices">
      <div><dt>当前追货表采购参考单价</dt><dd>{{ purchasePriceText(source.purchase_price.unit_price, source.purchase_price.price_unit) }}</dd></div>
      <div><dt>原送货单价</dt><dd>{{ line.unit_price ? `${line.unit_price} ${line.currency || '币种未注明'}／${line.price_unit || '计价单位未注明'}` : '未填写' }}</dd></div>
    </dl>
    <p v-if="priceNote" class="purchase-price-note" role="status">{{ priceNote }}</p>
  </div>
</template>

<style scoped>
.purchase-details{padding:10px 12px;border:1px solid var(--border);border-radius:8px;background:#f8faf9;min-width:0;overflow-wrap:anywhere}
.purchase-details small{display:block;color:#53665e;font-size:12px}
.purchase-details dl{display:flex;flex-wrap:wrap;gap:8px 18px;margin-top:8px}
.purchase-details dt{color:#53665e;font-size:12px}
.purchase-details dd{color:#233a35;font-variant-numeric:tabular-nums}
.purchase-details .purchase-prices{border-top:1px solid var(--border);padding-top:8px}
.purchase-price-note{color:#835f24;font-size:12px;margin-top:6px}
</style>
