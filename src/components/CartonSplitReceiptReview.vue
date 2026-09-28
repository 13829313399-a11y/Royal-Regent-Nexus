<script setup lang="ts">
import { ref, watch } from 'vue'
import { cartonOrderSplitsApi as api, type SplitReceiptInput, type SplitReceiptPreview } from '@/api/cartonOrderSplits'
import { getApiErrorMessage } from '@/lib/http'
const props = defineProps<{ factory: string; lines: SplitReceiptInput[] }>()
const emit = defineEmits<{ 'update:confirmation': [value: string] }>()
const preview = ref<SplitReceiptPreview | null>(null), checked = ref(false), error = ref(''), loading = ref(false)
let generation = 0
async function load() {
  const token = ++generation
  checked.value = false; preview.value = null; error.value = ''; emit('update:confirmation', ''); loading.value = true
  try {
    const result = await api.receiptPreview(props.factory, props.lines)
    if (token === generation) preview.value = result
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) loading.value = false }
}
watch(() => [props.factory, props.lines], load, { deep: true, immediate: true })
watch(checked, value => emit('update:confirmation', value ? preview.value?.confirmation ?? '' : ''))
</script>
<template>
  <section class="my-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm" aria-label="收货拆单分配核对">
    <strong>拆单分配核对</strong><button type="button" :disabled="loading" class="ml-3 text-xs text-teal-700" @click="load">刷新分配</button>
    <p v-if="loading" class="mt-1">正在核对拆分去向…</p><p v-if="error" role="alert" class="mt-1 text-red-700">{{ error }}</p>
    <p v-if="preview?.blocked_plans.length" role="alert" class="mt-1 text-red-700">原订单有拆单待仓库确认，请先在工作看板处理拆单。</p>
    <template v-else-if="preview?.allocations.length"><p class="mt-1 text-xs">按本次合格实收量分配，短收部分继续待到；送货单和入库来源保留。</p><p v-for="row in preview.allocations" :key="row.target_line_id" class="mt-1">{{ row.contract_no }} · PO {{ row.customer_po || '未填写' }} · {{ row.item_no }} · {{ row.packaging_type }}：{{ row.quantity }} {{ row.unit }}</p><label class="mt-3 flex items-center gap-2 font-semibold"><input v-model="checked" type="checkbox"> 仓库已核对以上拆分去向，确认分配本次有效入库</label></template>
    <p v-else-if="preview && !loading" class="mt-1 text-xs">本次实收没有待分配的拆单数量。</p>
  </section>
</template>
