<script setup lang="ts">
import { onMounted } from 'vue'
import type { SplitReceiptInput } from '@/api/cartonOrderSplits'
defineProps<{ factory: string; lines: SplitReceiptInput[] }>()
const emit = defineEmits<{ 'update:confirmation': [value: string] }>()
onMounted(() => emit('update:confirmation', ''))
</script>
<template>
  <section role="alert" class="my-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm" aria-label="旧拆单待转换">
    <strong>此订单仍有旧数量分配记录</strong>
    <p class="mt-1">请返回订单的“拆单 / 拆分记录”，转为独立订单后分别收料。这里不再合并入库或分配子单数量。</p>
    <p class="mt-1 text-xs">已有待确认收料请先撤销草稿；已有送货请先核对并更正送货单。已有入库或领用的旧记录须核对历史账务。</p>
  </section>
</template>
