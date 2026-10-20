<script setup lang="ts">
withDefaults(defineProps<{ rows: { id: string; label: string; quality: string; specification: string; unit: string; rule: string; required: number; received: number; remaining: number; progress: number; note?: string }[]; ruleLabel?: string }>(), { ruleLabel: '每箱个数' })
const format = (value: number) => value.toLocaleString('zh-CN', { maximumFractionDigits: 4 })
</script>
<template>
  <section class="carton-paper-detail" aria-label="纸品明细">
    <table class="w-full table-fixed text-left">
      <colgroup><col style="width:12%"><col style="width:12%"><col style="width:22%"><col style="width:10%"><col style="width:12%"><col style="width:10%"><col style="width:10%"><col style="width:12%"></colgroup>
      <thead><tr><th>纸品类型</th><th>纸质</th><th>规格</th><th>{{ ruleLabel }}</th><th class="text-right">纸品数量</th><th class="text-right">已入库</th><th class="text-right">待入库</th><th>入库进度</th></tr></thead>
      <tbody><tr v-for="row in rows" :key="row.id">
        <td data-label="纸品类型" class="font-semibold">{{ row.label }}<small v-if="row.note">{{ row.note }}</small></td>
        <td data-label="纸质" class="font-semibold">{{ row.quality }}</td><td data-label="规格">{{ row.specification }}</td><td :data-label="ruleLabel">{{ row.rule }}</td>
        <td data-label="纸品数量" class="text-right font-semibold">{{ format(row.required) }} {{ row.unit }}</td><td data-label="已入库" class="text-right font-semibold text-emerald-700">{{ format(row.received) }} {{ row.unit }}</td>
        <td data-label="待入库" class="text-right font-semibold" :class="row.remaining > 0 ? 'text-amber-700' : 'text-slate-500'">{{ format(row.remaining) }} {{ row.unit }}</td>
        <td data-label="入库进度"><div class="flex items-center gap-2"><span class="h-2 min-w-0 flex-1 overflow-hidden rounded-full bg-slate-200"><span class="block h-full rounded-full bg-emerald-600" :style="{ width: `${row.progress}%` }"></span></span><b class="shrink-0 text-[10px] text-slate-600">{{ row.progress }}%</b></div></td>
      </tr></tbody>
    </table>
  </section>
</template>
<style scoped>
.carton-paper-detail { min-width:0; overflow:hidden; border:1px solid var(--border); border-radius:12px; }
th { padding:10px; background:var(--muted); color:var(--muted-foreground); font-size:11px; font-weight:600; overflow-wrap:anywhere; }
td { padding:12px 10px; border-top:1px solid var(--border); font-size:12px; overflow-wrap:anywhere; font-variant-numeric:tabular-nums; }
small { display:block; margin-top:4px; color:var(--muted-foreground); font-size:10px; font-weight:400; }
@media(max-width:767px) { table,tbody,tr { display:block; } colgroup,thead { display:none; } tr { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); border-top:1px solid var(--border); padding:8px; gap:10px; } tr:first-child { border-top:0; } td { display:block; min-width:0; border:0; padding:4px; text-align:left; } td::before { display:block; content:attr(data-label); margin-bottom:5px; color:var(--muted-foreground); font-size:10px; font-weight:400; } }
</style>
