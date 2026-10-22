<script setup lang="ts">
withDefaults(defineProps<{ lines: { id: string; label: string; location: string; available: number; unit: string; quantity: string | number; aria: string; context?: string; warning?: string; disabled?: boolean }[]; disabled?: boolean; replenishment?: boolean; dateLabel?: string; maxDate?: string }>(), { replenishment: true })
const responsibility = defineModel<'' | 'OWN' | 'SUPPLIER'>('responsibility', { default: '' })
const date = defineModel<string>('date', { default: '' })
const emit = defineEmits<{ quantity: [id: string, value: string] }>()
const format = (value: number) => value.toLocaleString('zh-CN', { maximumFractionDigits: 4 })
</script>
<template>
  <div class="space-y-4">
    <fieldset :disabled="disabled" class="grid gap-4 sm:grid-cols-2"><label v-if="replenishment" class="text-xs font-semibold text-slate-700">责任方 *<select v-model="responsibility" aria-label="补单责任方" required class="mt-2 h-10 w-full rounded-lg border bg-white px-3"><option value="" disabled>请选择责任方</option><option value="OWN">我方责任 · 按实际收货计费</option><option value="SUPPLIER">供应商责任 · 免费换补</option></select></label><label v-if="dateLabel" class="text-xs font-semibold text-slate-700">{{ dateLabel }} *<input v-model="date" :aria-label="dateLabel" type="date" required :max="maxDate" class="mt-2 h-10 w-full rounded-lg border bg-white px-3"></label></fieldset>
    <p v-if="replenishment && responsibility" class="text-xs leading-5 text-teal-700">{{ responsibility === 'SUPPLIER' ? '供应商责任：补货免费，不新增月结应付；入库沿用本次出库成本，原库存成本须先核实。' : '我方责任：补货按实际验收入库数量和单价计入月结一次；本次出库不重复收费。' }}</p>
    <section class="overflow-hidden rounded-xl border border-slate-200" aria-label="原收料与仓位"><table class="w-full table-fixed text-left text-xs"><thead class="bg-slate-50"><tr><th>纸品</th><th>出库仓位</th><th>可办理库存</th><th>{{ replenishment ? '本次补单 / 自动出库' : '本次退货数量' }}</th></tr></thead><tbody><tr v-for="line in lines" :key="line.id" class="border-t"><td data-label="纸品"><b>{{ line.label }}</b><p v-if="line.context" class="mt-1 text-slate-500">{{ line.context }}</p><p v-if="line.warning" class="mt-1 text-amber-800">{{ line.warning }}</p></td><td data-label="出库仓位">{{ line.location }}</td><td data-label="可办理库存">{{ format(line.available) }} {{ line.unit }}</td><td data-label="本次数量"><input :value="line.quantity" :aria-label="line.aria" type="number" min="0" :max="line.available" step="0.0001" :disabled="disabled || line.disabled || line.available <= 0" placeholder="0" class="h-9 w-full rounded-lg border bg-white px-2 disabled:bg-slate-50" @input="emit('quantity', line.id, ($event.target as HTMLInputElement).value)"><span>{{ line.unit }}</span></td></tr><tr v-if="!lines.length"><td colspan="4" class="text-slate-500">没有可直接办理的库存，请先核实原收料来源、现存数量和仓位。</td></tr></tbody></table></section>
  </div>
</template>
<style scoped>
th,td { padding:12px; overflow-wrap:anywhere; vertical-align:top; }
@media(max-width:639px) { table,tbody,tr,td { display:block; } thead { display:none; } tr { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); } td::before { display:block; content:attr(data-label); color:var(--muted-foreground); margin-bottom:5px; } }
</style>
