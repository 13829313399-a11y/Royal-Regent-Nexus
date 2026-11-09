<script setup lang="ts">
import { computed } from 'vue'
import type { InternalQuote } from '@/types/internalQuoteDesk'
const props = defineProps<{ quote: InternalQuote }>()
const issued = computed(() => props.quote.moduleVersion === 'v4' && props.quote.finalReleaseStatus === 'issued')
const complete = computed(() => props.quote.pricingComplete === true
  && !props.quote.incompleteSections?.length && (issued.value || (!props.quote.formulaRecalculationRequired
    && props.quote.sections.filter(s => s.isRequired && s.status !== 'not_applicable')
      .every(s => s.calculationStatus === 'valid' && s.dependencyStatus === 'current'))))
const price = computed(() => Number.isFinite(props.quote.factoryPriceHkd) ? props.quote.factoryPriceHkd : null)
</script>

<template>
  <div class="quote-total-card" role="status" aria-live="polite">
    <template v-if="complete && price !== null">
      <span>整单工厂成本</span>
      <strong>HKD {{ price.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</strong>
      <small>RMB {{ (price * quote.fxRmbHkd).toFixed(2) }} · USD {{ (price / quote.fxHkdUsd).toFixed(2) }}</small>
    </template>
    <template v-else>
      <span>整单工厂成本待确认</span><strong>待补全核价</strong>
      <small>请补齐各参与部门并保存重算后查看完整金额</small>
    </template>
  </div>
</template>

<style scoped>
.quote-total-card { display: grid; gap: 6px; min-width: 210px; padding: 16px 20px; border: 1px solid var(--border); border-radius: 14px; background: var(--card); text-align: right; }
.quote-total-card strong { color: var(--primary); font-size: 1.2rem; }
.quote-total-card small { color: var(--muted-foreground); }
@media (max-width: 640px) { .quote-total-card { min-width: 0; text-align: left; } }
</style>
