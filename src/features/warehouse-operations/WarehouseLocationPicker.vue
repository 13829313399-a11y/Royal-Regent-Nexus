<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'
const props = defineProps<{ modelValue?: string; locations: { id: string; label: string; status?: string }[]; disabled?: boolean; label?: string }>()
const emit = defineEmits<{ 'update:modelValue': [string] }>()
const query = ref(''), input = ref<HTMLInputElement>(), listId = useId()
const places = computed(() => props.locations.filter(row => !row.status || row.status === 'ACTIVE'))
const normalized = (value: string) => value.normalize('NFKC').replace(/\s/g, '').toLowerCase()
watch(() => [props.modelValue, props.locations], () => {
  if (props.modelValue) query.value = places.value.find(row => row.id === props.modelValue)?.label ?? ''
}, { immediate: true })
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
    <small v-if="!places.length" role="status">没有可用仓位，请先在基础资料建立仓库和仓位。</small>
    <small v-else-if="query && !modelValue" role="alert">请选择已有仓位，不能直接填写新仓位。</small>
  </div>
</template>
<style scoped>
.warehouse-location-picker{min-width:0}.warehouse-location-picker input{width:100%;min-width:0;border:1px solid var(--border);border-radius:7px;padding:9px 10px;background:var(--card);color:var(--foreground);font:inherit}.warehouse-location-picker small{display:block;font-size:12px;color:#b45309;margin-top:5px}
</style>
