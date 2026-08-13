<script setup lang="ts">
import { ClipboardPaste, Save } from '@lucide/vue'
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { qcInspectionApi } from '@/api/qcInspection'
import SectionPanel from '@/components/common/SectionPanel.vue'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import { useQcInspectionWorkspace } from './context'

const context = useQcInspectionWorkspace()
const router = useRouter()
const pasteText = ref('')
const errorMessage = ref('')
const parseMessage = ref('')
const saving = ref(false)

const form = reactive({
  customer_name: '',
  sales_contract_no: '',
  customer_po_no: '',
  customer_item_no: '',
  product_name: '',
  quantity: '',
  packing: '',
  carton_count: '',
  production_department: '',
  export_country_code: '',
  shipment_date: '',
  planned_inspection_date: '',
  inspection_agency: '',
  account_manager: '',
})

interface ManualOrderField {
  key: keyof typeof form
  label: string
  required: boolean
  placeholder?: string
  type?: 'text' | 'number' | 'date'
}

const fields: ManualOrderField[] = [
  { key: 'customer_name', label: '客户', required: true, placeholder: '客户名称' },
  { key: 'sales_contract_no', label: '合同号', required: true, placeholder: '公司销售合同号' },
  { key: 'customer_po_no', label: 'PO', required: true, placeholder: '保留原格式和前导零' },
  { key: 'customer_item_no', label: '客户货号', required: true, placeholder: '报告命名使用此货号' },
  { key: 'product_name', label: '产品名称', required: true, placeholder: '产品名称' },
  { key: 'quantity', label: '数量', required: true, placeholder: '正整数', type: 'number' },
  { key: 'packing', label: '装箱', required: false, placeholder: '按现有验货表原值填写' },
  { key: 'carton_count', label: '箱数', required: false, placeholder: '按现有验货表原值填写' },
  { key: 'production_department', label: '生产部门', required: false, placeholder: '生产部门或车间' },
  { key: 'export_country_code', label: '出口国代码', required: true, placeholder: '如 US、DE' },
  { key: 'shipment_date', label: '走货期', required: true, type: 'date' },
  { key: 'planned_inspection_date', label: '验货期', required: true, type: 'date' },
  { key: 'inspection_agency', label: '验货机构', required: false, placeholder: '可稍后补充' },
  { key: 'account_manager', label: '跟客人员', required: false, placeholder: '可稍后补充' },
]

function parsePastedRow() {
  errorMessage.value = ''
  parseMessage.value = ''
  const firstLine = pasteText.value.split(/\r?\n/).map((line) => line.trim()).find(Boolean)
  if (!firstLine) {
    errorMessage.value = '请先粘贴一行订单资料。'
    return
  }
  const values = firstLine.split(/\t|\s{2,}/).map((value) => value.trim())
  const keys = [
    'customer_name',
    'sales_contract_no',
    'customer_po_no',
    'customer_item_no',
    'product_name',
    'quantity',
    'export_country_code',
    'shipment_date',
    'planned_inspection_date',
  ] as const
  keys.forEach((key, index) => {
    if (values[index]) form[key] = values[index]!
  })
  form.export_country_code = form.export_country_code.toUpperCase()
  parseMessage.value = '已把首行资料填入表单，请逐项核对后再保存。'
}

function validate() {
  for (const field of fields) {
    if (field.required && !String(form[field.key]).trim()) return `请填写${field.label}`
  }
  if (!Number.isInteger(Number(form.quantity)) || Number(form.quantity) <= 0) return '数量必须是大于 0 的整数'
  if (!/^[A-Za-z]{2,3}$/.test(form.export_country_code.trim())) return '出口国请填写 2–3 位英文国家代码，例如 US、DE'
  return ''
}

async function saveOrder() {
  if (!context.canOrderWrite.value) return
  errorMessage.value = validate()
  if (errorMessage.value) return
  saving.value = true
  try {
    const order = await qcInspectionApi.createOrder({
      factory_id: context.factoryId.value,
      week_key: context.weekKey.value,
      customer_name: form.customer_name.trim(),
      sales_contract_no: form.sales_contract_no.trim(),
      customer_po_no: form.customer_po_no.trim(),
      customer_item_no: form.customer_item_no.trim(),
      product_name: form.product_name.trim(),
      quantity: Number(form.quantity),
      packing: form.packing.trim() || undefined,
      carton_count: form.carton_count.trim() || undefined,
      production_department: form.production_department.trim() || undefined,
      export_country_code: form.export_country_code.trim().toUpperCase(),
      shipment_date: form.shipment_date,
      planned_inspection_date: form.planned_inspection_date,
      inspection_agency: form.inspection_agency.trim() || undefined,
      account_manager: form.account_manager.trim() || undefined,
    })
    await context.refresh()
    await router.push({
      name: 'qc-inspection-order-detail',
      params: { orderId: order.id },
      query: { factory: context.factoryId.value, week: context.weekKey.value },
    })
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
    <SectionPanel title="新建临时验货订单" subtitle="系统保存后生成独立验货单号；合同号和客户货号不会被用作唯一键。">
      <div v-if="!context.canOrderWrite.value" class="mb-5 rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800">
        当前为只读访问，不能新增临时订单。
      </div>

      <form class="grid gap-4 sm:grid-cols-2" @submit.prevent="saveOrder">
        <label v-for="field in fields" :key="field.key" class="space-y-1.5" :class="{ 'sm:col-span-2': field.key === 'product_name' }">
          <span class="text-sm font-semibold text-slate-700">{{ field.label }} <b v-if="field.required" class="text-red-600">*</b></span>
          <input
            v-model="form[field.key]"
            :type="field.type || 'text'"
            :placeholder="field.placeholder"
            :required="field.required"
            :disabled="!context.canOrderWrite.value || saving"
            :min="field.type === 'number' ? 1 : undefined"
            class="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/15 disabled:bg-slate-50 disabled:text-slate-500"
            @blur="field.key === 'export_country_code' && (form.export_country_code = form.export_country_code.toUpperCase())"
          >
        </label>

        <p v-if="errorMessage" role="alert" class="sm:col-span-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{{ errorMessage }}</p>
        <div class="sm:col-span-2 flex justify-end">
          <Button type="submit" :disabled="!context.canOrderWrite.value || saving">
            <Save class="size-4" aria-hidden="true" />
            {{ saving ? '保存中…' : '保存并打开验货主单' }}
          </Button>
        </div>
      </form>
    </SectionPanel>

    <aside class="space-y-6">
      <SectionPanel title="粘贴快捷填充" subtitle="按字段顺序粘贴一行资料，解析结果必须人工核对。">
        <textarea
          v-model="pasteText"
          rows="7"
          :disabled="!context.canOrderWrite.value"
          placeholder="客户　合同号　PO　客户货号　产品名称　数量　出口国代码　走货期　验货期"
          class="w-full resize-y rounded-lg border border-slate-200 bg-white p-3 text-sm leading-6 outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-500/15 disabled:bg-slate-50"
        />
        <Button type="button" variant="outline" class="mt-3 w-full" :disabled="!context.canOrderWrite.value" @click="parsePastedRow">
          <ClipboardPaste class="size-4" aria-hidden="true" />解析首行
        </Button>
        <p v-if="parseMessage" class="mt-3 rounded-lg bg-teal-50 px-3 py-2 text-xs leading-5 text-teal-800">{{ parseMessage }}</p>
      </SectionPanel>

      <SectionPanel title="保存前检查">
        <ul class="space-y-2 text-sm leading-6 text-slate-600">
          <li>• PO 为必填文本，保留原格式和前导零。</li>
          <li>• 出口国使用英文国家代码。</li>
          <li>• 客户货号用于报告命名，不用合同号替代。</li>
          <li>• 验货结果和实际日期在主单详情录入。</li>
        </ul>
      </SectionPanel>
    </aside>
  </div>
</template>
