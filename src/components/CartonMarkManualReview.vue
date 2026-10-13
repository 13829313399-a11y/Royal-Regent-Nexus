<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { cartonMarkApi } from '@/api/cartonMark'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'

export interface ManualReviewAsset {
  id: string; factory_id: string; file_name: string; kind: string; revision: number
  orders: { id: string; customer_name: string; contract_no: string; item_no: string; issue_id?: string }[]
}
const props = defineProps<{ sources: ManualReviewAsset[]; supplier?: boolean }>()
const emit = defineEmits<{ choose: []; saved: [id: string] }>()
const auth = useAuthStore()
const orderId = ref(''), error = ref(''), busy = ref(false)
let generation = 0, controller = new AbortController()
const factory = computed(() => props.sources[0]?.factory_id ?? '')
const canSubmit = computed(() => props.supplier ? auth.can('carton_supplier:edit', factory.value, '*') : ['pmc-warehouse', 'carton'].some(dep => auth.can('carton_mark:template_upload', factory.value, dep)))
const canApprove = computed(() => !props.supplier && ['pmc-warehouse', 'carton'].some(dep => auth.can('carton_mark:template_release', factory.value, dep)))
const orders = computed(() => (props.sources[0]?.orders ?? []).filter(order => props.sources.every(asset => asset.factory_id === factory.value && asset.orders.some(row => row.id === order.id && row.issue_id === order.issue_id))))
const order = computed(() => orders.value.find(row => row.id === orderId.value))
watch([() => props.sources, () => auth.currentUser?.id, () => auth.authorizationVersion], () => {
  generation++; controller.abort(); controller = new AbortController()
  busy.value = false; error.value = ''
  orderId.value = orders.value.length === 1 ? orders.value[0]!.id : ''
}, { immediate: true })
async function submit() {
  if (!canSubmit.value || busy.value || !order.value) return
  const token = generation
  busy.value = true; error.value = ''
  try {
    const record = await cartonMarkApi.submitManualReview({ factory_id: factory.value, order_id: order.value.id,
      issue_id: order.value.issue_id, assets: props.sources.map(({ id, revision }) => ({ id, revision })), approve: canApprove.value }, props.supplier, controller.signal)
    if (token === generation) emit('saved', record.id)
  } catch (cause) {
    if (token === generation) error.value = `${getApiErrorMessage(cause)}。如请求中断，请先刷新审核记录确认是否已保存。`
  } finally { if (token === generation) busy.value = false }
}
onBeforeUnmount(() => { generation++; controller.abort() })
</script>

<template>
  <section class="rounded-xl border border-amber-200 bg-white p-5 sm:p-6" aria-label="单 PDF / 图片人工审核">
    <h2 class="text-xl font-bold">单 PDF / 图片人工审核</h2>
    <p class="mt-2 text-sm leading-6 text-slate-600">选择订单的 PDF 或图片，有权限的内部审核人点击“审核通过”即可供 QC 使用。供应商提交后由内部审核人通过。</p>
    <p class="mt-2 text-sm leading-6 text-slate-500">PDF 可用于 QC 文字核对；图片暂用于人工对照和照片留档。</p>
    <button type="button" :disabled="busy" class="mt-4 rounded-lg border px-4 py-2 text-sm disabled:opacity-50" @click="emit('choose')">到资料库选择 PDF / 图片</button>
    <form v-if="sources.length" class="mt-4 space-y-4" @submit.prevent="submit">
      <ol class="list-inside list-decimal rounded-lg bg-slate-50 p-3 text-sm"><li v-for="source in sources" :key="source.id" class="break-all py-1">{{ source.file_name }}</li></ol>
      <p v-if="orders.length === 1 && order" class="rounded-lg bg-sky-50 p-3 text-sm">{{ order.customer_name }} · 合同 {{ order.contract_no }} · ITEM {{ order.item_no }}</p>
      <label v-else class="block text-sm font-semibold">本次审核的订单
        <select v-model="orderId" aria-label="人工审核关联订单" :disabled="busy" required class="mt-2 w-full rounded-lg border bg-white p-3">
          <option value="" disabled>请选择原文件共同关联的订单</option>
          <option v-for="row in orders" :key="row.id" :value="row.id">{{ row.customer_name }} · 合同 {{ row.contract_no }} · ITEM {{ row.item_no }}</option>
        </select>
      </label>
      <p v-if="!orders.length" role="alert" class="text-sm text-amber-800">原文件没有共同的明确订单关联，请先在资料库补齐或修正关联。</p>
      <p v-if="!canSubmit" class="text-sm text-amber-800">当前账号没有提交审核权限。</p>
      <button type="submit" :disabled="busy || !canSubmit || !order" class="rounded-lg bg-amber-700 px-5 py-3 font-semibold text-white disabled:opacity-50">{{ busy ? '正在保存…' : canApprove ? '审核通过' : '提交内部审核' }}</button>
      <p v-if="canApprove" class="text-xs text-slate-500">系统自动记录审核人、时间和本次资料版本。</p>
    </form>
    <p v-if="error" role="alert" class="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-800">{{ error }}</p>
  </section>
</template>
