<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { qcInspectionApi, type QcInspectionOrder } from '@/api/qcInspection'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import { useQcInspectionWorkspace } from './context'
import { effectiveInspectionDate } from './schedule'
const props = defineProps<{ order: QcInspectionOrder }>()
const emit = defineEmits<{ close: []; saved: [order: QcInspectionOrder] }>()
const context = useQcInspectionWorkspace()
const dialog = ref<HTMLDialogElement>()
const busy = ref(false)
const error = ref('')
const form = reactive({ planned_inspection_date: props.order.planned_inspection_date, shipment_date: props.order.shipment_date, reason: '' })
const effectiveDate = computed(() => effectiveInspectionDate(form))
onMounted(() => dialog.value?.showModal())
function close() { if (!busy.value) emit('close') }
async function save() {
  if (busy.value || !context.canOrderWrite.value) return
  busy.value = true; error.value = ''
  try {
    const saved = await qcInspectionApi.updateOrder(props.order.id, { ...form, reason: form.reason.trim(), factory_id: context.factoryId.value, expected_revision: props.order.revision })
    emit('saved', saved)
  } catch (cause) { error.value = getApiErrorMessage(cause) }
  finally { busy.value = false }
}
</script>
<template>
  <dialog ref="dialog" class="qc-dialog" aria-labelledby="qc-plan-title" @cancel.prevent="close">
    <header class="qc-dialog-header"><div><h2 id="qc-plan-title">调整排期</h2><p class="qc-muted">{{ order.inspection_no }} · {{ order.customer_name }} · {{ order.customer_item_no }}</p></div><Button variant="ghost" :disabled="busy" @click="close">关闭</Button></header>
    <form class="qc-dialog-body" @submit.prevent="save"><div class="qc-form-grid"><label class="qc-field"><span>客户指定验货日期</span><input v-model="form.planned_inspection_date" type="date" :disabled="busy"></label><label class="qc-field"><span>走货日期</span><input v-model="form.shipment_date" type="date" :disabled="busy"></label><label class="qc-field sm:col-span-2"><span>调整原因</span><textarea v-model="form.reason" required minlength="2" maxlength="500" :disabled="busy" rows="3" /></label></div><p class="qc-muted">客户验货日期留空时按走货日期排期，两者都为空才进入待安排。当前排期：{{ effectiveDate || '待安排' }}。实际验货结果在订单详情中登记。</p><p v-if="error" class="qc-error" role="alert">{{ error }}</p><footer class="qc-dialog-footer"><Button type="button" variant="outline" :disabled="busy" @click="close">取消</Button><Button type="submit" :disabled="busy || !context.canOrderWrite.value">保存排期</Button></footer></form>
  </dialog>
</template>
