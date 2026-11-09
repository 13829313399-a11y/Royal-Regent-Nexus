<script setup lang="ts">
import { computed } from 'vue'
import { quotePaperPrices } from '@/lib/internalQuotePaper'
const value = defineModel<string | undefined>()
const props = defineProps<{ snapshot?: Record<string, unknown>; fallback: unknown; disabled?: boolean; label?: string }>()
const options = computed(() => quotePaperPrices(props.snapshot))
</script>
<template>
  <label class="paper-select"><span>{{ label || '纸材' }}</span><select v-model="value" :disabled="disabled" :aria-label="label || '纸材选择'">
    <option :value="undefined">沿用原系数 {{ fallback }}</option>
    <option v-if="value && !options.some(p => p.key === value)" :value="value">原纸材已失效，请重新选择</option>
    <option v-for="p in options" :key="p.key" :value="p.key">{{ p.name }} · {{ p.price_factor_hkd }} HKD</option>
  </select><small v-if="!options.length">可在“本报价采用价目表”维护纸材。</small></label>
</template>
<style scoped>
.paper-select { display:grid; gap:6px; margin:8px 0; min-width:140px; } select { padding:9px; border:1px solid var(--input); border-radius:7px; background:var(--card); max-width:100%; } small { color:var(--muted-foreground); }
</style>
