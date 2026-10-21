<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'
import { locationCategoryLabels, matchesLocationCategory } from './fabricLocationZones'
const props = defineProps<{ modelValue?: string; locations: { id: string; label: string; status?: string; category?: string }[]; category?: string; disabled?: boolean; label?: string }>()
const emit = defineEmits<{ 'update:modelValue': [string] }>()
const query = ref(''), input = ref<HTMLInputElement>(), listId = useId()
const choices = ref<HTMLDetailsElement>()
const places = computed(() => {
  const rows = props.locations.filter(row => (!row.status || row.status === 'ACTIVE') && matchesLocationCategory(row, props.category))
  return props.category ? rows.sort((a, b) => Number(!a.category) - Number(!b.category) || a.label.localeCompare(b.label, 'zh-CN', { numeric: true })) : rows
})
const normalized = (value: string) => value.normalize('NFKC').replace(/\s/g, '').toLowerCase()
const filteredPlaces = computed(() => places.value.filter(row => props.modelValue || normalized(row.label).includes(normalized(query.value))))
function selectPlace(id: string) {
  const place = places.value.find(row => row.id === id)
  if (props.disabled || !place) return
  query.value = place.label
  emit('update:modelValue', id)
  if (choices.value) choices.value.open = false
}
watch([() => props.modelValue, places], () => {
  if (props.modelValue && !props.disabled) {
    const selected = places.value.find(row => row.id === props.modelValue)
    query.value = selected?.label ?? ''
    if (!selected) emit('update:modelValue', '')
  }
}, { immediate: true })
watch(() => props.category, () => { if (!props.disabled && !props.modelValue) query.value = '' })
watch([query, () => props.modelValue, places, input], () => {
  input.value?.setCustomValidity(props.modelValue && places.value.some(row => row.id === props.modelValue) ? '' : '请选择基础资料中已启用的仓库和仓位')
}, { flush: 'post' })
function choose(event: Event) {
  query.value = (event.target as HTMLInputElement).value
  const matches = places.value.filter(row => normalized(row.label) === normalized(query.value))
  emit('update:modelValue', matches.length === 1 ? matches[0]!.id : '')
}
</script>
<template>
  <div class="warehouse-location-picker">
    <input ref="input" :value="query" :list="listId" required :disabled="disabled || !places.length" :aria-label="label || '目标仓位'" :aria-invalid="Boolean(query && !modelValue)" autocomplete="off" placeholder="搜索并选择已有仓库／仓位" @input="choose" />
    <datalist :id="listId"><option v-for="row in places" :key="row.id" :value="row.label" /></datalist>
  <details v-if="places.length && !disabled" ref="choices" class="location-touch-choices">
    <summary>点选仓位</summary>
    <div class="location-touch-list" :aria-label="`${label || '目标仓位'}候选`">
      <button v-for="row in filteredPlaces.slice(0, 50)" :key="row.id" type="button" :aria-pressed="modelValue === row.id" @click="selectPlace(row.id)">{{ row.label }}</button>
      <small v-if="!filteredPlaces.length">未找到仓位，请修改上方搜索文字。</small>
      <small v-else-if="filteredPlaces.length > 50">仅显示前 50 个仓位，可在上方输入架号缩小范围。</small>
    </div>
  </details>
    <small v-if="category === ''" role="status">先选择物料分类，再选择对应架位或区域。</small>
    <small v-else-if="!places.length" role="status">没有可用仓位，请先在基础资料建立或分类对应原料分区。</small>
    <small v-else-if="query && !modelValue" role="alert">请选择已有仓位，不能直接填写新仓位。</small>
    <small v-else-if="category" class="location-zone-hint">仅限{{ locationCategoryLabels[category] }}分区 · 请选择具体架／区</small>
  </div>
</template>
<style scoped>
.warehouse-location-picker{min-width:0}.warehouse-location-picker input{width:100%;min-width:0;border:1px solid var(--border);border-radius:7px;padding:9px 10px;background:var(--card);color:var(--foreground);font:inherit}.warehouse-location-picker small{display:block;font-size:12px;color:#b45309;margin-top:5px}
.warehouse-location-picker .location-zone-hint{color:var(--muted-foreground)}
.location-touch-choices{display:none}
@media(max-width:700px){
  .warehouse-location-picker input{min-height:44px;font-size:16px}
  .location-touch-choices{display:block;margin-top:6px}
  .location-touch-choices summary{display:flex;align-items:center;min-height:44px;padding:8px 12px;border:1px solid var(--border);border-radius:6px;cursor:pointer;font-size:14px;color:var(--primary)}
  .location-touch-list{display:grid;gap:6px;max-height:220px;overflow:auto;overscroll-behavior:contain;padding:8px 0}
  .location-touch-list button{white-space:normal;overflow-wrap:anywhere;text-align:left;min-height:44px;padding:10px;border:1px solid var(--border);border-radius:6px;background:var(--card);font-size:14px}
  .location-touch-list button[aria-pressed=true]{border-color:var(--primary);background:var(--accent)}
}
</style>
