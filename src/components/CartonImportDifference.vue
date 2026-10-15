<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ message: string }>()
const comparison = computed(() => {
  const fields: { field: string; delivery: string; order: string }[] = []
  const remainder = props.message.replace(/([^：/；（）]+)（送货单：([^；]*?)；订单：([^）]*?)）/g, (_, field: string, delivery: string, order: string) => {
    const value = { field: field.trim(), delivery: delivery.trim(), order: order.trim() }
    if (!fields.some(row => JSON.stringify(row) === JSON.stringify(value))) fields.push(value)
    return ''
  }).replace(/^纸品不一致：/, '').replace(/[ /；]+/g, ' ').trim()
  return { fields, remainder }
})
</script>
<template>
  <template v-if="comparison.fields.length">
    <table class="w-full text-left text-xs" aria-label="送货资料差异">
      <thead class="text-slate-500"><tr><th class="pr-2">差异项</th><th class="pr-2">送货单</th><th>原订单</th></tr></thead>
      <tbody><tr v-for="row in comparison.fields" :key="JSON.stringify(row)"><th class="pr-2 font-medium">{{ row.field }}</th><td class="pr-2">{{ row.delivery }}</td><td>{{ row.order }}</td></tr></tbody>
    </table>
    <p v-if="comparison.remainder" class="mt-1">{{ comparison.remainder }}</p>
  </template>
  <span v-else>{{ message }}</span>
</template>
