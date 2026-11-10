<script setup lang="ts">
import { computed } from 'vue'
import { quotePaperPrices } from '@/lib/internalQuotePaper'
import { quotePaperMaterialGroups, standardQuotePaperName } from '@/lib/internalQuotePaperMaterials'
const value = defineModel<string | undefined>()
const props = defineProps<{ snapshot?: Record<string, unknown>; fallback: unknown; disabled?: boolean; label?: string }>()
const options = computed(() => quotePaperPrices(props.snapshot))
const groups = computed(() => quotePaperMaterialGroups.map(group => ({
  label: group.label,
  options: group.names.flatMap(name => {
    const matches = options.value.filter(p => standardQuotePaperName(p.name) === name)
    return matches.length ? matches.map(p => ({ ...p, available: Number.isFinite(Number(p.price_factor_hkd)) && Number(p.price_factor_hkd) > 0 }))
      : [{ key: `pending:${name}`, name, price_factor_hkd: '', remark: '', available: false }]
  }),
})))
const customOptions = computed(() => options.value.filter(p => !standardQuotePaperName(p.name)))
</script>
<template>
  <label class="paper-select"><span>{{ label || '纸材' }}</span><select v-model="value" :disabled="disabled" :aria-label="label || '纸材选择'">
    <option :value="undefined">沿用原系数 {{ fallback }}</option>
    <option v-if="value && !options.some(p => p.key === value)" :value="value">原纸材已失效，请重新选择</option>
    <optgroup v-for="group in groups" :key="group.label" :label="group.label">
      <option v-for="p in group.options" :key="p.key" :value="p.key" :disabled="!p.available">{{ p.name }} · {{ p.available ? `${p.price_factor_hkd} HKD` : '待维护价格' }}</option>
    </optgroup>
    <optgroup v-if="customOptions.length" label="其他已维护材质">
      <option v-for="p in customOptions" :key="p.key" :value="p.key">{{ p.name }} · {{ p.price_factor_hkd }} HKD</option>
    </optgroup>
  </select><small>待维护价格的材质，请先在“本报价采用价目表”填写已确认的价格。</small></label>
</template>
<style scoped>
.paper-select { display:grid; gap:6px; margin:8px 0; min-width:140px; } select { padding:9px; border:1px solid var(--input); border-radius:7px; background:var(--card); color:var(--foreground); max-width:100%; } small { color:var(--muted-foreground); }
</style>
