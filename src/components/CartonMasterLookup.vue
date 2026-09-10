<script setup lang="ts">
import { computed, ref } from 'vue'
import type { MasterRecord } from '@/api/cartonMaster'
const props = defineProps<{ records: MasterRecord[]; customer: string; query: string; field: 'contract' | 'item' | 'product'; disabled?: boolean }>()
const emit = defineEmits<{ select: [row: MasterRecord] }>()
const root = ref<HTMLElement>(), open = ref(false)
const normalize = (text: string) => text.normalize('NFKC').toLowerCase().replace(/[\s_./-]+/g, '')
const matches = computed(() => {
  const term = normalize(props.query)
  if (!term) return []
  return props.records.filter(r => r.status === 'ACTIVE' && (props.field !== 'contract' || r.customer_code === props.customer) && r.kind === (props.field === 'contract' ? 'CONTRACT' : 'CONFIG'))
    .filter(r => normalize(props.field === 'product' ? r.data.product_name || '' : r.code).includes(term))
    .sort((a, b) => Number(b.preferred) - Number(a.preferred))
})
function leave(event: FocusEvent) {
  if (!root.value?.contains(event.relatedTarget as Node | null)) open.value = false
}
function choose(row: MasterRecord) {
  if (props.disabled) return
  emit('select', row)
  root.value?.querySelector('input')?.focus()
  open.value = false
}
</script>
<template>
  <div ref="root" class="self-start" @focusin="open = true" @input="open = true" @focusout="leave" @keydown.esc.stop="open = false">
    <div class="relative">
    <slot />
    <div v-if="open && !disabled && query.trim()" class="absolute left-0 top-full z-40 max-h-64 w-full min-w-64 overflow-y-auto rounded-lg border border-teal-200 bg-white p-1.5 shadow-lg" :aria-label="`${field === 'contract' ? '合同号' : field === 'item' ? '货号' : '产品名称'}基础资料候选`">
      <button v-for="row in matches.slice(0, 8)" :key="row.id" type="button" class="block w-full rounded-md p-2 text-left text-xs hover:bg-teal-50 focus:bg-teal-50 focus:outline-none" @click="choose(row)">
        <b class="break-all">{{ row.code }}<template v-if="field !== 'contract'"> · {{ row.data.product_name }} · {{ row.data.packing_name || '其他包装' }}</template></b>
        <div v-if="field === 'contract'" class="mt-1 break-all text-slate-500">关联货号：{{ row.data.item_nos?.join('、') || '暂无' }}</div>
        <template v-else><div v-for="(line, i) in row.data.lines" :key="i" class="mt-1 text-slate-500">{{ line.packaging_type }} · {{ line.paper_quality }} · {{ line.specification }} {{ line.dimension_unit }} · {{ line.unit }} · 每箱 {{ line.usage_quantity }} 件</div><span class="text-[10px] text-teal-700">选择后带出整套配置，请核对</span></template>
      </button>
      <p v-if="matches.length > 8" class="p-2 text-xs text-slate-500">还有 {{ matches.length - 8 }} 项，请继续输入缩小范围。</p>
      <p v-if="!matches.length" class="p-2 text-xs text-slate-500">暂无匹配资料，可继续手动填写。</p>
    </div>
    </div>
    <slot name="hint" />
  </div>
</template>
