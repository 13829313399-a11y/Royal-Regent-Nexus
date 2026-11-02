<script setup lang="ts">
import { computed } from 'vue'
import { calculateHuaxing360, H360_CATEGORIES, huaxing360Problems, selectHuaxing360Route, type Huaxing360Result } from '@/lib/customerPriceConverters/huaxingThreeSixty'
const props = defineProps<{ result: Huaxing360Result; disabled?: boolean }>()
const emit = defineEmits<{ changed: [] }>()
const calc = computed(() => calculateHuaxing360(props.result))
const problems = computed(() => huaxing360Problems(props.result))
function change() { props.result.review.confirmed = false; emit('changed') }
function route(event: Event) { selectHuaxing360Route(props.result, (event.target as HTMLSelectElement).value); emit('changed') }
function number(event: Event) { const v = (event.target as HTMLInputElement).value; return v.trim() === '' ? null : Number(v) }
</script>

<template>
  <section data-testid="huaxing-360-review" class="space-y-4 rounded-xl border border-teal-200 bg-white p-5">
    <div><h3 class="font-semibold text-slate-950">360（华兴临时）原表核对</h3><p class="mt-1 text-sm text-slate-600">以本次内部报价为准，按新版RZR客表分区输出；每行保留原名称、料重和金额，整套料重不乘出模套数。未完成核对时下列金额为已知成本小计。</p></div>
    <ul class="list-disc space-y-1 pl-5 text-xs text-slate-600"><li v-for="notice in result.notices" :key="notice">{{ notice }}</li></ul>
    <fieldset :disabled="disabled" class="space-y-4" @input="change">
      <div class="grid gap-3 md:grid-cols-3">
        <label class="text-sm">报客产品名称<input v-model="result.review.productName" aria-label="360产品名称" class="block w-full rounded border p-2"></label>
        <label class="text-sm">报价日期<input v-model="result.review.quoteDate" aria-label="360报价日期" type="date" class="block w-full rounded border p-2"></label>
        <label class="text-sm">版本<input v-model="result.review.revision" aria-label="360版本" class="block w-full rounded border p-2"></label>
        <label class="text-sm">制表人<input v-model="result.review.preparedBy" aria-label="360制表人" class="block w-full rounded border p-2"></label>
        <label class="text-sm">MOQ<input :value="result.review.moq" aria-label="360MOQ" type="number" min="1" class="block w-full rounded border p-2" @input="result.review.moq = number($event)"></label>
        <label class="text-sm">运输路线<select :value="result.review.route" aria-label="360运输路线" class="block w-full rounded border p-2" @change="route"><option v-for="f in result.freight" :key="f.key" :value="f.key">{{ f.label }} · HKD {{ f.hkd.toFixed(6) }}/件</option></select></label>
        <label class="text-sm">品牌系列（选填）<input v-model="result.review.brand" class="block w-full rounded border p-2"></label>
        <label class="text-sm">首次出货期（选填）<input v-model="result.review.firstEtd" class="block w-full rounded border p-2"></label>
        <label class="text-sm">模具数量（按原说明核对，可留空）<input :value="result.review.toolingCount" type="number" min="0" class="block w-full rounded border p-2" @input="result.review.toolingCount = number($event)"></label>
        <label class="text-sm">每柜数量（原表未提供，可留空）<input :value="result.review.quantityPerContainer" type="number" min="1" class="block w-full rounded border p-2" @input="result.review.quantityPerContainer = number($event)"></label>
      </div>
      <p class="text-xs text-slate-600">外箱 {{ result.carton.dimensions.map(n => n.toFixed(3)).join(' × ') }} inch；装箱数 {{ result.carton.quantity }}；彩盒 {{ result.colorBox.map(n => n.toFixed(3)).join(' × ') }} inch。损耗按{{ result.pricing.rates.scrap_include_labor === 1 ? '材料+人工' : '仅材料' }} × {{ (result.pricing.rates.scrap_rate! * 100).toFixed(2) }}%；加价 {{ (result.pricing.rates.markup_rate! * 100).toFixed(2) }}%。</p>
      <div class="overflow-x-auto"><table class="w-full text-left text-sm"><thead><tr><th>费用原文/原单元格</th><th>费用总额 USD</th><th>摊分数量（客户基础资料）</th><th>USD/件</th></tr></thead><tbody><tr v-for="(fee, i) in result.review.fees" :key="fee.source"><td class="py-2">{{ fee.description }}<br><small>{{ fee.source }} 原式分摊 {{ fee.sourceAllocation ?? '未识别' }} 件</small></td><td><input :value="fee.totalUsd" :aria-label="`${fee.source}费用USD`" type="number" min="0" step="any" class="w-32 rounded border p-2" @input="fee.totalUsd = number($event)"></td><td><span>{{ calc.fees[i]?.allocation.toLocaleString() }} 件</span><br><small class="text-slate-500">基础资料维护，重导入生效</small></td><td>{{ calc.fees[i]?.perUnitUsd.toFixed(6) }}</td></tr></tbody></table></div>
      <details open><summary class="cursor-pointer font-medium">原始费用逐项核对（{{ result.costs.length }}项）</summary><p class="my-2 text-xs text-amber-700">原表空白金额必须补入；输入0表示已含其他费用或不计。非空原金额只读，如有错误请修正原文件再导入。</p><div class="max-h-96 overflow-auto"><table class="w-full text-left text-sm"><thead><tr><th>来源</th><th>项目</th><th>分类</th><th>用量</th><th>原金额 HKD/件</th><th>USD/件</th></tr></thead><tbody><tr v-for="(cost, i) in result.costs" :key="cost.source" class="border-t"><td>{{ cost.source }}</td><td class="py-2">{{ cost.description }}</td><td><select v-model="cost.category" :disabled="!cost.needsCategory" class="rounded border p-1" @change="change"><option value="">待分类</option><option v-for="(label, key) in H360_CATEGORIES" :key="key" :value="key">{{ label }}</option></select></td><td>{{ cost.quantity }}</td><td><input v-if="cost.sourceHkd === null" :value="cost.amountHkd" :aria-label="`${cost.source}补录金额`" type="number" min="0" step="any" class="w-28 rounded border border-amber-400 p-2" @input="cost.amountHkd = number($event)"><span v-else>{{ cost.sourceHkd.toFixed(6) }}</span></td><td>{{ calc.costs[i]?.totalUsd.toFixed(6) }}</td></tr></tbody></table></div></details>
      <details><summary class="cursor-pointer font-medium">塑胶及啤工（{{ result.plastic.length }}行）</summary><div class="max-h-80 overflow-auto"><table class="w-full text-left text-sm"><thead><tr><th>零件</th><th>原料型 → 计价料型</th><th>整套克重</th><th>USD/kg</th><th>胶料USD</th><th>啤工USD</th></tr></thead><tbody><tr v-for="p in calc.plastic" :key="p.source" class="border-t"><td>{{ p.description }}</td><td>{{ p.material }} → {{ p.priceMaterial }}</td><td>{{ p.weightG }}</td><td>{{ p.price ?? '缺价' }}</td><td>{{ p.totalUsd.toFixed(6) }}</td><td>{{ p.moldingUsd.toFixed(6) }}</td></tr></tbody></table></div></details>
    </fieldset>
    <div class="grid gap-2 rounded bg-slate-50 p-3 text-sm sm:grid-cols-4"><span>材料 USD {{ calc.materialUsd.toFixed(6) }}</span><span>人工 USD {{ calc.laborUsd.toFixed(6) }}</span><span>出厂 USD {{ calc.exFactoryUsd.toFixed(6) }}</span><strong>{{ problems.length ? '已知成本小计' : '含本单全部费用FOB' }} USD {{ calc.finalUsd.toFixed(6) }}</strong></div>
    <ul v-if="problems.length" class="list-disc space-y-1 rounded bg-amber-50 p-4 pl-8 text-sm text-amber-800"><li v-for="problem in problems" :key="problem">{{ problem }}</li></ul>
    <label class="flex gap-2 text-sm font-medium"><input v-model="result.review.confirmed" type="checkbox" :disabled="disabled || problems.length > 0" aria-label="确认华兴360核对">已核对原始成本、料型对应、损耗基数、运输方式、费用USD及摊分数量，确认输出</label>
  </section>
</template>
