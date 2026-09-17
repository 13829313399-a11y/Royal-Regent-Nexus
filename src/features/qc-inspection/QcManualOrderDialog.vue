<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import type { QcInspectionOrder } from '@/api/qcInspection'
import { createQcRequestId, qcInspectionApi } from '@/api/qcInspection'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import { useQcInspectionWorkspace } from './context'

const props = defineProps<{ customers: string[]; orders: QcInspectionOrder[]; customer?: string }>()
const emit = defineEmits<{ close: []; saved: [order: QcInspectionOrder] }>()
const context = useQcInspectionWorkspace()
const dialog = ref<HTMLDialogElement>()
const saving = ref(false)
const error = ref('')
let submission: { fingerprint: string; requestId: string } | undefined
const duplicateAcknowledged = ref(false)
const form = reactive({ customer_name: props.customer || '', sales_contract_no: '', customer_po_no: '',
  customer_item_no: '', product_name: '', quantity: '', packing: '', carton_count: '',
  production_department: '', export_country_code: '', shipment_date: '', planned_inspection_date: '',
  inspection_agency: '', account_manager: '', note: '' })
const duplicates = computed(() => props.orders.filter((order) => order.sales_contract_no === form.sales_contract_no.trim()
  && order.customer_po_no === form.customer_po_no.trim() && order.customer_item_no === form.customer_item_no.trim()))
const fields: Array<{ key: keyof typeof form; label: string; required?: boolean; type?: string }> = [
  { key: 'customer_name', label: '客户', required: true }, { key: 'sales_contract_no', label: '合同号', required: true },
  { key: 'customer_po_no', label: '客户 PO', required: true }, { key: 'customer_item_no', label: '客户货号', required: true },
  { key: 'product_name', label: '产品名称' }, { key: 'quantity', label: '数量', required: true },
  { key: 'packing', label: '装箱资料' }, { key: 'carton_count', label: '箱数' },
  { key: 'shipment_date', label: '走货日期', type: 'date' }, { key: 'planned_inspection_date', label: '客户指定验货日期', type: 'date' },
  { key: 'inspection_agency', label: '验货机构' }, { key: 'account_manager', label: '香港跟客' },
  { key: 'production_department', label: '生产部门' }, { key: 'export_country_code', label: '出口国代码' },
]
onMounted(() => dialog.value?.showModal())
function close() { if (!saving.value) emit('close') }
async function save() {
  if (saving.value || !context.canOrderWrite.value) return
  error.value = ''
  if (['customer_name', 'sales_contract_no', 'customer_po_no', 'customer_item_no'].some(key => !form[key as keyof typeof form].trim())) {
    error.value = '请填写客户、合同号、客户 PO 和客户货号。'; return
  }
  if (!/^\d+(\.\d{1,4})?$/.test(form.quantity.trim()) || Number(form.quantity) <= 0) {
    error.value = '数量必须大于零，最多保留四位小数。'; return
  }
  if (duplicates.value.length && !duplicateAcknowledged.value) { error.value = '请先核对已有订单，并确认确需新增一次验货。'; return }
  if (!form.note.trim()) { error.value = '请填写临时加单原因。'; return }
  saving.value = true
  try {
    for (const key of Object.keys(form) as Array<keyof typeof form>) form[key] = form[key].trim()
    const payload = {
      ...form, quantity: form.quantity.trim(), export_country_code: form.export_country_code.trim().toUpperCase(),
      factory_id: context.factoryId.value, week_key: context.weekKey.value,
    }
    const fingerprint = JSON.stringify(payload)
    if (submission?.fingerprint !== fingerprint) submission = { fingerprint, requestId: createQcRequestId() }
    const order = await qcInspectionApi.createOrder(payload, submission.requestId)
    emit('saved', order)
  } catch (cause) { error.value = getApiErrorMessage(cause) }
  finally { saving.value = false }
}
</script>

<template>
  <dialog ref="dialog" class="qc-dialog" aria-labelledby="qc-add-title" @cancel.prevent="close">
    <header class="qc-dialog-header"><div><p class="qc-eyebrow">{{ context.factoryName.value }} · {{ context.weekKey.value }}</p><h2 id="qc-add-title">临时加单</h2><p class="qc-muted">保存后回到总排期。未填写客户验货日期时按走货日期排期，两者都为空才进入待安排。</p></div><Button variant="ghost" :disabled="saving" aria-label="关闭临时加单" @click="close">关闭</Button></header>
    <form class="qc-dialog-body" @submit.prevent="save">
      <div class="qc-form-grid">
        <label v-for="field in fields" :key="field.key" class="qc-field"><span>{{ field.label }} <b v-if="field.required" class="text-red-600">*</b></span><input v-model="form[field.key]" :type="field.type || 'text'" :required="field.required" :disabled="saving" :list="field.key === 'customer_name' ? 'qc-add-customers' : undefined" @input="duplicateAcknowledged = false"></label>
        <datalist id="qc-add-customers"><option v-for="name in customers" :key="name" :value="name" /></datalist>
        <label class="qc-field sm:col-span-2"><span>加单原因及备注 <b class="text-red-600">*</b></span><textarea v-model="form.note" required rows="3" :disabled="saving" /></label>
      </div>
      <div v-if="duplicates.length" class="qc-notice"><p>已有 {{ duplicates.length }} 条相同合同、PO 和货号的订单，请核对是否为重复加单。</p><label class="mt-2 flex items-center gap-2"><input v-model="duplicateAcknowledged" type="checkbox" :disabled="saving">确需新增一次独立验货</label></div>
      <p v-if="error" role="alert" class="qc-error">{{ error }}</p>
      <footer class="qc-dialog-footer"><Button type="button" variant="outline" :disabled="saving" @click="close">取消</Button><Button type="submit" :disabled="saving || !context.canOrderWrite.value">{{ saving ? '保存中…' : '保存临时单' }}</Button></footer>
    </form>
  </dialog>
</template>
