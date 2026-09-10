<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'
import type { CartonLocation } from '@/api/cartonPositions'
const props = defineProps<{ modelValue?: string; locations: CartonLocation[]; factoryId: string; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [string]; created: [] }>()
const listId = useId(), query = ref('')
const places = computed(() => props.locations.filter(p => p.factory_id === props.factoryId && p.status !== 'INACTIVE'))
const normalize = (text: string) => text.normalize('NFKC').replace(/\s/g, '').toLowerCase()
watch(() => [props.modelValue, props.locations, props.factoryId] as const, () => {
  if (props.modelValue) query.value = props.locations.find(p => p.id === props.modelValue)?.label || ''
}, { immediate: true })
watch(() => props.factoryId, () => { query.value = ''; emit('update:modelValue', '') })
function input(event: Event) {
  query.value = (event.target as HTMLInputElement).value
  const matches = places.value.filter(p => normalize(p.label) === normalize(query.value))
  emit('update:modelValue', matches.length === 1 ? matches[0]!.id : '')
}
</script>
<template>
  <div class="min-w-40 space-y-1">
    <input :value="query" :list="listId" :disabled="disabled" aria-label="仓库及仓位" :aria-invalid="Boolean(query && !modelValue)" autocomplete="off" placeholder="输入搜索仓库／仓位" class="h-9 w-full min-w-0 rounded-lg border border-slate-200 bg-white px-2 text-xs outline-none focus:border-teal-500" @input="input">
    <datalist :id="listId"><option v-for="place in places" :key="place.id" :value="place.label" /></datalist>
    <p v-if="query && !modelValue && !disabled" class="text-[10px] text-red-600">请选择基础资料中已有的仓位</p>
  </div>
</template>
