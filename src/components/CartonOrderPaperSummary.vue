<script setup lang="ts">
defineProps<{ count: number; required: string; received: string; remaining: string }>()
</script>
<template>
  <div aria-label="订单纸品汇总" class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-[11px] leading-5 text-slate-600">共 <b class="text-slate-900">{{ count }}</b> 项纸品；需求 <b class="text-slate-900">{{ required }}</b>，已入库 <b class="text-emerald-700">{{ received }}</b>，待入库 <b class="text-amber-700">{{ remaining }}</b>。入库数量来自实际收料记录，追加或减单只改变需求量，不改写既有入库流水。</div>
</template>
