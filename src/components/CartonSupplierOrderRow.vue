<script setup lang="ts">
export interface SupplierRowPresentation {
  orderNo: string; factory: string; kind: string; customer: string; identity: string; context: string
  items: string; product: string; marks: string; marksTone: string; marksHelp?: string
  orderDate: string; plannedDate: string; due: string; dueTone: string; differences: string[]
  progress: string; lines: { id: string; label: string; required: number; received: number; inTransit?: number; unit: string }[]
  status: string; statusTone: string; notice?: string; noticeTone?: string
}
defineProps<{ row: SupplierRowPresentation; selected: boolean; selectable: boolean }>()
const emit = defineEmits<{ select: [selected: boolean]; marks: []; preview: []; leave: []; detail: [] }>()
const format = (value: number) => value.toLocaleString('zh-CN', { maximumFractionDigits: 4 })
</script>
<template>
  <tr class="hover:bg-teal-50/40">
    <td data-label="选择"><input type="checkbox" :checked="selected" :aria-label="`选择订单 ${row.orderNo}`" :disabled="!selectable" class="size-4 accent-teal-700 disabled:cursor-not-allowed disabled:opacity-40" @change="emit('select', ($event.target as HTMLInputElement).checked)"></td>
    <td data-label="厂区 / 类型"><b class="text-teal-800">{{ row.factory }}</b><p class="mt-1 text-slate-600">{{ row.kind }}</p></td>
    <td data-label="客户 / 合同 / 单号"><b class="text-slate-900">{{ row.customer }}</b><p class="mt-1 font-semibold">{{ row.identity }}</p><p class="mt-1 text-slate-500">{{ row.context }}</p></td>
    <td data-label="货号 / 产品"><b>{{ row.items }}</b><p class="mt-1 text-slate-500">{{ row.product }}</p></td>
    <td data-label="箱唛资料"><button type="button" :aria-label="`查看订单 ${row.orderNo} 箱唛资料`" :title="row.marksHelp || '在订单明细中查看和下载箱唛资料'" class="rounded-lg px-2 py-1 font-semibold" :class="row.marksTone" @click="emit('marks')">{{ row.marks }}</button></td>
    <td data-label="日期 / 交期"><p class="text-slate-500">下单 {{ row.orderDate }}</p><p class="mt-1">计划 {{ row.plannedDate }}</p><span class="mt-1 block font-semibold" :class="row.dueTone">{{ row.due }}</span><details v-if="row.differences.length" class="mt-1 text-amber-700"><summary class="cursor-pointer font-semibold">承诺交期有差异</summary><p v-for="difference in row.differences" :key="difference" class="mt-1 leading-5">{{ difference }}</p></details></td>
    <td data-label="纸品 / 收货进度"><p class="mb-1 text-slate-500">{{ row.progress }}</p><div v-for="line in row.lines" :key="line.id" class="mb-1"><b>{{ line.label }}</b> {{ format(line.received) }} / {{ format(line.required) }} {{ line.unit }}<span v-if="line.inTransit && line.inTransit > 0" class="block text-amber-700">在途 {{ format(line.inTransit) }} {{ line.unit }}</span></div><span v-if="!row.lines.length" class="text-slate-400">无有效需求</span></td>
    <td data-label="订单状态"><span class="inline-flex rounded-lg px-2 py-1 font-bold ring-1 ring-inset" :class="row.statusTone">{{ row.status }}</span><p v-if="row.notice" class="mt-1" :class="row.noticeTone || 'text-amber-700'">{{ row.notice }}</p></td>
    <td data-label="操作" class="supplier-order-actions"><div class="flex flex-wrap justify-end gap-1"><slot name="actions" /><button type="button" :aria-label="`查看订单 ${row.orderNo} 明细`" title="悬停预览整单明细，单击后保持显示" aria-haspopup="dialog" class="rounded-lg border border-slate-200 bg-white px-3 py-1.5 font-semibold text-slate-700 hover:border-teal-300 hover:text-teal-700" @mouseenter="emit('preview')" @mouseleave="emit('leave')" @focus="emit('preview')" @blur="emit('leave')" @click="emit('detail')">明细</button></div></td>
  </tr>
</template>
