<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ code: string; components: Array<{ id: string; name: string }>; disabled?: boolean }>()
const model = defineModel<Record<string, unknown>>({ required: true })
const field = computed(() => props.code === 'engineering' ? 'molds' : 'rows')
const rows = computed(() => (Array.isArray(model.value[field.value]) ? model.value[field.value] : []) as Array<Record<string, unknown>>)
function assign(index: number, id: string) {
  model.value = { ...model.value, [field.value]: rows.value.map((row, i) => i === index ? { ...row, pricing_component_id: id } : row) }
}
</script>
<template>
  <details v-if="rows.length" class="quote-mapped-assignment">
    <summary>{{ code === 'engineering' ? '模具' : '喷油' }}明细分配 · {{ rows.length }} 行（当前产品全部分项）</summary>
    <p>映射一次后在此调整应用分项，无需重新上传；调整后点击保存。{{ code === 'engineering' ? '模具归属会联动到啤机明细，整套模具费用只保留一次。' : '' }}</p>
    <div><label v-for="(row,index) in rows" :key="index"><span>{{ row.mold_no }} {{ row.item || row.name || row.chinese_name || row.part_name || `明细 ${index + 1}` }}</span><select :value="row.pricing_component_id || components[0]?.id" :disabled="disabled" :aria-label="`明细 ${index + 1} 应用分项`" @change="assign(index, ($event.target as HTMLSelectElement).value)"><option v-for="component in components" :key="component.id" :value="component.id">{{ component.name }}</option></select></label></div>
  </details>
</template>
<style scoped>
.quote-mapped-assignment{margin:12px;border:1px solid #99f6e4;border-radius:8px;padding:12px;background:#f0fdfa}.quote-mapped-assignment summary{color:#0f766e;font-weight:700;cursor:pointer}.quote-mapped-assignment p{font-size:12px;color:#475569}.quote-mapped-assignment>div{max-height:360px;overflow:auto;display:grid;gap:6px}.quote-mapped-assignment label{display:flex;align-items:center;gap:12px;background:#fff;padding:8px}.quote-mapped-assignment label span{flex:1;font-size:12px}.quote-mapped-assignment select{min-width:160px;border:1px solid #cbd5e1;border-radius:6px;padding:6px;background:#fff}
</style>
