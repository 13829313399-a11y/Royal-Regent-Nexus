<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { CartonCustomerResponse } from '@/api/cartonProcurement'
const props = defineProps<{ modelValue: string; customers: CartonCustomerResponse[]; knownCustomers?: CartonCustomerResponse[]; canCreate: boolean; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [string]; create: [string]; refresh: [] }>()
const query = ref(''), open = ref(false), composing = ref(false), root = ref<HTMLElement>()
const normalize = (value: string) => value.normalize('NFKC').trim().toLowerCase().replace(/\s+/g, '')
watch(() => [props.modelValue, props.customers] as const, () => {
  const row = props.customers.find(c => c.customer_code === props.modelValue)
  if (row) query.value = row.customer_name
}, { immediate: true })
const matches = computed(() => props.customers.filter(c => c.status === 'ACTIVE' && normalize(c.customer_name + ' ' + c.customer_code).includes(normalize(query.value))))
const exactMatch = (c: CartonCustomerResponse) => normalize(c.customer_name) === normalize(query.value)
  || normalize(c.customer_code) === normalize(query.value)
const existing = computed(() => props.customers.find(c => c.status === 'ACTIVE' && exactMatch(c))
  ?? (props.knownCustomers ?? props.customers).find(exactMatch))
const restricted = computed(() => existing.value?.status === 'ACTIVE'
  && !props.customers.some(c => c.customer_code === existing.value!.customer_code))
const duplicateNames = computed(() => {
  const counts = new Map<string, number>()
  for (const customer of props.customers.filter(c => c.status === 'ACTIVE')) {
    const name = normalize(customer.customer_name)
    counts.set(name, (counts.get(name) ?? 0) + 1)
  }
  return new Set([...counts].filter(([, count]) => count > 1).map(([name]) => name))
})
function input(event: Event) {
  query.value = (event.target as HTMLInputElement).value
  emit('update:modelValue', '')
  open.value = true
}
function finishInput() {
  if (props.disabled || composing.value) return
  const selected = props.customers.find(c => c.status === 'ACTIVE' && c.customer_code === props.modelValue)
  if (selected && query.value === selected.customer_name) return
  const key = normalize(query.value)
  const exact = key
    ? props.customers.filter(c => c.status === 'ACTIVE' && (normalize(c.customer_name) === key || normalize(c.customer_code) === key)) : []
  const row = exact.length === 1 ? exact[0] : undefined
  emit('update:modelValue', row?.customer_code ?? '')
  if (row) { query.value = row.customer_name; open.value = false }
}
function compositionEnd(event: CompositionEvent) { composing.value = false; input(event) }
function confirmByEnter(event: KeyboardEvent) {
  if (composing.value || event.isComposing) return
  event.preventDefault()
  event.stopPropagation()
  finishInput()
}
function choose(code: string) { emit('update:modelValue', code); root.value?.querySelector('input')?.focus(); open.value = false }
function leave(event: FocusEvent) {
  if (root.value?.contains(event.relatedTarget as Node | null)) return
  finishInput()
  open.value = false
}
</script>
<template>
  <div ref="root" class="self-start space-y-1.5" @focusout="leave" @keydown.esc.stop="open = false">
    <div class="relative">
    <label class="block space-y-1.5"><span class="text-[11px] font-bold text-slate-600">客户 *</span><input :value="query" aria-label="订单客户" autocomplete="off" :disabled="disabled" placeholder="输入客户名称或编号，回车或离开后关联" class="h-10 w-full rounded-lg border border-slate-200 px-3 outline-none focus:border-teal-500 disabled:bg-slate-50" @input="input" @keydown.enter="confirmByEnter" @compositionstart="composing = true" @compositionend="compositionEnd" @focus="open = true; emit('refresh')"></label>
    <div v-if="open && !disabled" class="absolute left-0 top-full z-40 max-h-64 w-full overflow-auto rounded-lg border border-teal-200 bg-white p-1.5 shadow-lg" aria-label="客户候选">
      <button v-for="row in matches" :key="row.id" type="button" :aria-label="`选择客户 ${row.customer_name}`" class="block w-full rounded-md p-2 text-left text-xs hover:bg-teal-50 focus:bg-teal-50" @click="choose(row.customer_code)">{{ row.customer_name }}<span v-if="duplicateNames.has(normalize(row.customer_name))" class="ml-2 text-[10px] text-slate-500">{{ row.customer_code }}</span></button>
      <p v-if="!matches.length" class="p-2 text-xs text-slate-500">没有匹配的启用客户。</p>
      <p v-if="existing?.status === 'INACTIVE'" class="p-2 text-xs text-amber-700">同名客户已停用，请联系有权限的人员核对启用。</p>
      <p v-else-if="restricted" class="p-2 text-xs text-amber-700">已有此客户，但当前客户授权未包含它；请刷新授权，或联系负责人、主管核对。</p>
      <button v-if="canCreate && query.trim() && !existing" type="button" class="mt-1 block w-full rounded-md border border-teal-200 p-2 text-left text-xs text-teal-700" @click="open = false; emit('create', query.trim())">新增客户：{{ query.trim() }}</button>
      <p v-else-if="!canCreate && !matches.length && !existing" class="p-2 text-xs text-slate-500">请联系有高级维护权限的人员新增客户。</p>
    </div>
    </div>
    <p v-if="query && !modelValue" class="text-[10px] text-amber-700">完整名称或编号可按回车或移到下一项自动关联；其他情况请从候选中选择，或新增并保存客户。</p>
  </div>
</template>
