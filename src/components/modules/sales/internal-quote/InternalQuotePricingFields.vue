<script setup lang="ts">
import { computed } from 'vue'
import type { QuotePricingMetadata, SalesPricingComponent } from '@/lib/internalQuoteSectionPayload'

const props = withDefaults(defineProps<{
  mode?: 'standard' | 'component'
  components?: SalesPricingComponent[]
  mainMarkup?: number
  allowMarkupOverride?: boolean
  disabled?: boolean
}>(), {
  mode: 'standard',
  components: () => [],
  mainMarkup: 1.2,
  allowMarkupOverride: true,
  disabled: false,
})
const model = defineModel<QuotePricingMetadata>({ required: true })
const markupText = computed<string>({
  get: () => model.value.markup_override == null ? '' : String(model.value.markup_override),
  set: (value) => {
    const parsed = Number(value)
    if (!value || !Number.isFinite(parsed)) delete model.value.markup_override
    else model.value.markup_override = parsed
  },
})

function normalizeMarkup() {
  const parsed = Number(markupText.value)
  const mainMarkup = Number(props.mainMarkup)
  if (!Number.isFinite(parsed) || parsed <= 0 || parsed > 9.99 || Math.abs(parsed - mainMarkup) < .000001) {
    delete model.value.markup_override
    return
  }
  model.value.markup_override = Number(parsed.toFixed(2))
}
</script>

<template>
  <div class="quote-pricing-fields">
    <label v-if="mode === 'component'">
      <span>报价归属</span>
      <select v-model="model.pricing_component_id" :disabled="disabled" aria-label="报价分项归属">
        <option value="">默认：{{ components[0]?.name || '主体' }}</option>
        <option v-for="component in components" :key="component.id" :value="component.id">{{ component.name }}</option>
      </select>
    </label>
    <label v-else-if="allowMarkupOverride">
      <span>明细倍率</span>
      <input v-model="markupText" :disabled="disabled" type="number" min="0.01" max="9.99" step="0.01" :placeholder="`默认 ${Number(mainMarkup || 1.2).toFixed(2)}`" aria-label="明细倍率，留空跟随主倍率" @blur="normalizeMarkup">
      <small>{{ model.markup_override == null ? '跟随主倍率' : '已脱离主倍率' }}</small>
    </label>
  </div>
</template>

<style scoped>
.quote-pricing-fields{min-width:112px}.quote-pricing-fields label{display:grid;gap:3px}.quote-pricing-fields span,.quote-pricing-fields small{color:#64748b;font-size:9px;line-height:1.25}.quote-pricing-fields span{font-weight:800}.quote-pricing-fields select,.quote-pricing-fields input{width:100%;min-width:100px;border:1px solid #cbd5e1;border-radius:6px;background:#fff;padding:5px 6px;color:#0f172a;font-size:10px}.quote-pricing-fields small{color:#0f766e}
</style>
