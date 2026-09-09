<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { CartonCustomerResponse } from '@/api/cartonProcurement'
const props = defineProps<{ modelValue: string; customers: CartonCustomerResponse[]; canCreate: boolean; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [string]; create: [string] }>()
const query = ref(''), open = ref(false), root = ref<HTMLElement>()
const normalize = (value: string) => value.normalize('NFKC').trim().toLowerCase().replace(/\s+/g, '')
watch(() => [props.modelValue, props.customers] as const, () => {
  const row = props.customers.find(c => c.customer_code === props.modelValue)
  if (row) query.value = row.customer_name
}, { immediate: true })
const matches = computed(() => props.customers.filter(c => c.status === 'ACTIVE' && normalize(c.customer_name + ' ' + c.customer_code).includes(normalize(query.value))))
const existing = computed(() => props.customers.find(c => normalize(c.customer_name) === normalize(query.value)))
function input(event: Event) {
  query.value = (event.target as HTMLInputElement).value
  emit('update:modelValue', '')
  open.value = true
}
function choose(code: string) { emit('update:modelValue', code); root.value?.querySelector('input')?.focus(); open.value = false }
function leave(event: FocusEvent) { if (!root.value?.contains(event.relatedTarget as Node | null)) open.value = false }
</script>
<template>
  <div ref="root" class="relative space-y-1.5" @focusout="leave" @keydown.esc.stop="open = false">
    <label class="block space-y-1.5"><span class="text-[11px] font-bold text-slate-600">客户 *</span><input :value="query" aria-label="订单客户" autocomplete="off" :disabled="disabled" placeholder="输入客户名称搜索，再选择" class="h-10 w-full rounded-lg border border-slate-200 px-3 outline-none focus:border-teal-500 disabled:bg-slate-50" @input="input" @focus="open = true"></label>
    <div v-if="open && !disabled" class="absolute left-0 top-full z-40 max-h-64 w-full overflow-auto rounded-lg border border-teal-200 bg-white p-1.5 shadow-lg" aria-label="客户候选">
      <button v-for="row in matches" :key="row.id" type="button" :aria-label="`选择客户 ${row.customer_name}`" class="block w-full rounded-md p-2 text-left text-xs hover:bg-teal-50 focus:bg-teal-50" @click="choose(row.customer_code)">{{ row.customer_name }}</button>
      <p v-if="!matches.length" class="p-2 text-xs text-slate-500">没有匹配的启用客户。</p>
      <p v-if="existing?.status === 'INACTIVE'" class="p-2 text-xs text-amber-700">同名客户已停用，请联系有权限的人员核对启用。</p>
      <button v-if="canCreate && query.trim() && !existing" type="button" class="mt-1 block w-full rounded-md border border-teal-200 p-2 text-left text-xs text-teal-700" @click="open = false; emit('create', query.trim())">新增客户：{{ query.trim() }}</button>
      <p v-else-if="!canCreate && !matches.length && !existing" class="p-2 text-xs text-slate-500">请联系有高级维护权限的人员新增客户。</p>
    </div>
    <p v-if="query && !modelValue" class="text-[10px] text-amber-700">请从候选中选择，或新增并保存客户。</p>
  </div>
</template>
