<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue'
import { cartonProcurementApi as api, type CartonHistoryOrderPreview, type CartonHistoryOrderImportResponse } from '@/api/cartonProcurement'
import { getApiErrorMessage } from '@/lib/http'
const props = defineProps<{ file: File; factoryId: string }>()
const emit = defineEmits<{ close: []; imported: [result: CartonHistoryOrderImportResponse] }>()
const preview = ref<CartonHistoryOrderPreview | null>(null), busy = ref(false), saving = ref(false), error = ref('')
let generation = 0
async function load() {
  const token = ++generation, factory = props.factoryId, file = props.file
  busy.value = true; error.value = ''; preview.value = null
  try { const result = await api.previewHistoryOrders(factory, file); if (generation === token) preview.value = result }
  catch (e) { if (token === generation) error.value = getApiErrorMessage(e) }
  finally { if (token === generation) busy.value = false }
}
async function submit() {
  if (busy.value || saving.value || !preview.value || preview.value.errors.length || !preview.value.orders.some(row => !row.duplicate)) return
  const token = generation, factory = props.factoryId
  saving.value = true; error.value = ''
  try {
    const result = await api.uploadHistoryOrders(factory, props.file, preview.value.source_fingerprint)
    if (token === generation && factory === props.factoryId) emit('imported', result)
  } catch (e) { if (token === generation) error.value = getApiErrorMessage(e) }
  finally { if (token === generation) saving.value = false }
}
watch(() => [props.factoryId, props.file], load, { immediate: true })
onBeforeUnmount(() => { generation++ })
</script>

<template>
  <div class="fixed inset-0 z-[75] flex items-center justify-center bg-slate-950/45 p-4">
    <section role="dialog" aria-modal="true" aria-label="历史订单导入核对" class="flex max-h-[90vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl bg-white shadow-xl">
      <header class="flex items-start justify-between gap-4 border-b p-5"><div><h2 class="font-bold">历史订单导入核对</h2><p class="mt-1 text-xs text-slate-500">{{ file.name }} · 先核对再导入。只建立订单需求，不生成收料、库存或供应商应结金额。</p></div><button type="button" :disabled="saving" aria-label="关闭历史订单预览" @click="emit('close')">关闭</button></header>
      <div class="space-y-4 overflow-auto p-5 text-xs">
        <p v-if="busy" role="status">正在识别订单、纸品数量和资料缺项…</p>
        <p v-if="error" role="alert" class="rounded-lg bg-red-50 p-3 text-red-700">{{ error }}</p>
        <template v-if="preview">
          <p v-if="preview.supplier_name" class="text-slate-600">纸箱供应商：{{ preview.supplier_name }}</p>
          <div class="flex flex-wrap gap-5 rounded-lg bg-teal-50 p-3"><b>{{ preview.group_count }} 张订单 / {{ preview.line_count }} 条纸品</b><span>资料完整 {{ preview.ready_count }} 张</span><span>待完善 {{ preview.draft_count }} 张</span><span>重复跳过 {{ preview.skipped_count }} 张</span></div>
          <p class="leading-6 text-slate-600">明确填写的纸品需求数量优先；产品数量或装箱数空白保持未记录。确认导入表示这些订单已在系统外下单，直接进入待收料，不重复生成采购单。纸质、规格可在入库时补齐；已在仓数量请另走期初库存。</p>
          <p class="leading-6 text-slate-600">原计划交期保持不变；原表已有客户交期则保留，缺少时按计划交期加该客户有效采购保护期补算，并在下方逐单提示。</p>
          <p class="leading-6 text-slate-600">主表 I、J 列填写每外箱净重、毛重（kg），只关联外箱。净重不含纸箱、配卡等包装，毛重为含包装的整箱总重量；未知留空。其他纸品的独立重量可填附加纸品明细。</p>
          <div v-if="preview.errors.length" class="rounded-lg border border-red-200 bg-red-50 p-3 text-red-700"><b>请修正文件后重新选择：</b><p v-for="(item, i) in preview.errors" :key="i" class="mt-1">{{ item }}</p></div>
          <div v-if="preview.warnings.length" class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-amber-800"><p v-for="(item, i) in preview.warnings" :key="i">{{ item }}</p></div>
          <article v-for="(order, index) in preview.orders" :key="index" class="overflow-hidden rounded-xl border" :class="order.duplicate ? 'opacity-60' : ''">
            <header class="flex flex-wrap justify-between gap-3 bg-slate-50 p-3"><div><b>{{ order.customer_name }} · {{ order.contract_no }} · {{ order.item_no }}</b><p v-if="order.customer_po" class="mt-1 text-teal-700">客户 PO {{ order.customer_po }}</p><p class="mt-1 text-slate-500">{{ order.product_name || '产品名称未记录' }} · 产品数量 {{ order.product_order_quantity ?? '未记录' }} · {{ order.source_rows.join('、') }}</p><p class="mt-1">下单 {{ order.order_date || '待补' }} · 计划交期 {{ order.due_date || '待补' }} · 客户交期 {{ order.customer_due_date || '未记录' }}</p></div><b>{{ order.duplicate ? '重复，跳过' : order.ready ? '历史已下单 · 待收料' : '待收料 · 入库前补资料' }}</b></header>
            <div class="overflow-x-auto"><table class="w-full min-w-[900px] text-left"><thead class="text-slate-500"><tr><th class="p-3">纸品类型</th><th class="p-3">纸质</th><th class="p-3">规格</th><th class="p-3 text-right">需求数量</th><th class="p-3 text-right">每箱个数</th><th class="p-3 text-right">每箱净重 kg</th><th class="p-3 text-right">每箱毛重 kg</th><th class="p-3">单价 / 币种</th></tr></thead><tbody><tr v-for="(line, i) in order.lines" :key="i" class="border-t"><td class="p-3">{{ line.packaging_type }}</td><td class="p-3">{{ line.paper_quality || '待补齐' }}</td><td class="p-3">{{ line.specification || '待补齐' }} {{ line.dimension_unit }}</td><td class="p-3 text-right font-bold text-teal-700">{{ line.required_quantity }} {{ line.unit }}</td><td class="p-3 text-right">{{ line.usage_quantity ?? '未记录' }}</td><td class="p-3 text-right">{{ line.net_weight_kg ?? '未记录' }}</td><td class="p-3 text-right">{{ line.gross_weight_kg ?? '未记录' }}</td><td class="p-3">{{ Number(line.unit_price) ? line.unit_price : '待核价' }} {{ line.currency }}</td></tr></tbody></table></div>
            <p v-for="(item, i) in order.warnings" :key="i" class="px-3 pb-2 text-amber-700">{{ item }}</p>
          </article>
        </template>
      </div>
      <footer class="flex flex-wrap items-center justify-between gap-3 border-t bg-slate-50 p-4 text-xs"><span>有错误先改 Excel；文件或基础资料发生变化时需要重新预览。</span><div class="flex gap-2"><button type="button" :disabled="busy || saving" class="rounded-lg border bg-white px-3 py-2" @click="load">重新核对</button><button type="button" :disabled="busy || saving || !preview || !!preview.errors.length || !preview.orders.some(row => !row.duplicate)" class="rounded-lg bg-teal-700 px-4 py-2 font-bold text-white disabled:opacity-40" @click="submit">{{ saving ? '正在导入…' : '确认历史已下单并导入' }}</button></div></footer>
    </section>
  </div>
</template>
