<script setup lang="ts">
import { Pencil, X } from '@lucide/vue'
import { reactive, ref, watch } from 'vue'
import type { InternalQuoteHeaderUpdateRequest } from '@/api/internalQuote'
import type { InternalQuote, InternalQuoteBusinessOwner } from '@/types/internalQuoteDesk'

const props = withDefaults(defineProps<{
  open: boolean
  quote: InternalQuote
  businessOwners: InternalQuoteBusinessOwner[]
  customers: string[]
  busy?: boolean
  externalError?: string
}>(), { busy: false, externalError: '' })

const emit = defineEmits<{
  close: []
  confirm: [payload: InternalQuoteHeaderUpdateRequest]
}>()

const localError = ref('')
const form = reactive({
  productName: '', customer: '', quantity: 1, businessOwnerId: '', businessOwnerName: '',
  targetCustomerPrice: '无', targetDate: '', remark: '',
})

watch(() => [props.open, props.quote.headerRevision] as const, ([open]) => {
  if (!open) return
  localError.value = ''
  Object.assign(form, {
    productName: props.quote.productName,
    customer: props.quote.customer,
    quantity: props.quote.quantity,
    businessOwnerId: props.quote.businessOwnerId,
    businessOwnerName: props.quote.businessOwner,
    targetCustomerPrice: props.quote.targetCustomerPrice,
    targetDate: props.quote.targetDate,
    remark: props.quote.remark,
  })
}, { immediate: true })

function selectOwner() {
  form.businessOwnerName = props.businessOwners.find((owner) => owner.id === form.businessOwnerId)?.displayName ?? ''
}

function submit() {
  localError.value = ''
  if (!form.productName.trim() || !form.customer.trim()) {
    localError.value = '产品名称和客户不能为空。'
    return
  }
  if (!props.customers.includes(form.customer)) {
    localError.value = '请选择当前厂区客户资料中的客户。'
    return
  }
  if (!props.businessOwners.some((owner) => owner.id === form.businessOwnerId)) {
    localError.value = '请选择当前厂区具备审核权限的业务部人员。'
    return
  }
  if (!Number.isInteger(Number(form.quantity)) || Number(form.quantity) <= 0) {
    localError.value = '出货数量必须是大于 0 的整数。'
    return
  }
  if (!form.targetCustomerPrice.trim()) {
    localError.value = '客人未提供目标价时请填写“无”。'
    return
  }
  emit('confirm', {
    revision: props.quote.headerRevision,
    product_name: form.productName.trim(),
    customer: form.customer,
    qty: Number(form.quantity),
    business_owner_id: form.businessOwnerId,
    business_owner_name: form.businessOwnerName,
    target_customer_price: form.targetCustomerPrice.trim(),
    target_date: form.targetDate,
    remark: form.remark.trim(),
  })
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="quote-header-backdrop" @mousedown.self="emit('close')">
      <section class="quote-header-dialog" role="dialog" aria-modal="true" aria-labelledby="quote-header-title">
        <header><span><Pencil aria-hidden="true" /></span><div><h2 id="quote-header-title">修改报价资料</h2><p>{{ quote.quoteNo }} · {{ quote.versionLabel }} · revision {{ quote.headerRevision }}</p></div><button type="button" aria-label="关闭" @click="emit('close')"><X aria-hidden="true" /></button></header>
        <div class="quote-header-grid">
          <label class="wide"><span>产品名称</span><input v-model="form.productName" type="text"></label>
          <label><span>客户</span><select v-model="form.customer"><option v-for="customer in customers" :key="customer" :value="customer">{{ customer }}</option></select></label>
          <label><span>出货数量</span><input v-model.number="form.quantity" type="number" min="1" step="1"></label>
          <label class="wide"><span>业务负责人 / 全部分段审核人（仅业务部）</span><select v-model="form.businessOwnerId" @change="selectOwner"><option value="" disabled>请选择业务部审核人</option><option v-for="owner in businessOwners" :key="owner.id" :value="owner.id">{{ owner.displayName }}（{{ owner.username }}）</option></select></label>
          <label><span>客人目标价</span><input v-model="form.targetCustomerPrice" type="text"></label>
          <label><span>预计完成日期</span><input v-model="form.targetDate" type="date"></label>
          <label class="wide"><span>备注</span><textarea v-model="form.remark" rows="3" /></label>
        </div>
        <p v-if="localError || externalError" class="quote-header-error" role="alert">{{ localError || externalError }}</p>
        <footer><button type="button" :disabled="busy" @click="emit('close')">取消</button><button type="button" class="primary" :disabled="busy" @click="submit">{{ busy ? '保存中…' : '保存报价资料' }}</button></footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.quote-header-backdrop{position:fixed;z-index:1300;display:grid;inset:0;place-items:center;background:rgb(15 23 42/.52);padding:20px;backdrop-filter:blur(3px)}.quote-header-dialog{width:min(720px,100%);overflow:hidden;border:1px solid #cbd5e1;border-radius:16px;background:#fff;box-shadow:0 26px 80px rgb(15 23 42/.3)}.quote-header-dialog>header{display:grid;grid-template-columns:42px 1fr 34px;align-items:center;gap:11px;border-bottom:1px solid #e2e8f0;background:#f8fafc;padding:15px 17px}.quote-header-dialog>header>span{display:grid;width:40px;height:40px;place-items:center;border-radius:11px;background:#ccfbf1;color:#0f766e}.quote-header-dialog>header svg{width:19px}.quote-header-dialog h2{margin:0;color:#0f172a;font-size:17px}.quote-header-dialog header p{margin:3px 0 0;color:#64748b;font-size:10px}.quote-header-dialog header button{display:grid;width:32px;height:32px;place-items:center;border:1px solid #e2e8f0;border-radius:8px;background:#fff;color:#64748b}.quote-header-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:17px}.quote-header-grid label{display:grid;gap:6px}.quote-header-grid label.wide{grid-column:1/-1}.quote-header-grid span{color:#475569;font-size:10px;font-weight:900}.quote-header-grid input,.quote-header-grid select,.quote-header-grid textarea{width:100%;box-sizing:border-box;border:1px solid #dbe5ea;border-radius:8px;background:#fff;padding:9px 10px;color:#0f172a;font-size:12px;outline:none}.quote-header-grid input,.quote-header-grid select{height:38px}.quote-header-grid input:focus,.quote-header-grid select:focus,.quote-header-grid textarea:focus{border-color:#14b8a6;box-shadow:0 0 0 3px rgb(20 184 166/.1)}.quote-header-error{margin:0 17px;border:1px solid #fecaca;border-radius:8px;background:#fef2f2;padding:9px 11px;color:#b91c1c;font-size:11px}.quote-header-dialog>footer{display:flex;justify-content:flex-end;gap:8px;padding:15px 17px}.quote-header-dialog footer button{height:37px;border:1px solid #dbe5ea;border-radius:8px;background:#fff;padding:0 15px;color:#475569;font-size:11px;font-weight:900}.quote-header-dialog footer button.primary{border-color:#0f766e;background:#0f766e;color:#fff}.quote-header-dialog footer button:disabled{cursor:wait;opacity:.55}@media(max-width:620px){.quote-header-grid{grid-template-columns:1fr}.quote-header-grid label.wide{grid-column:auto}}
</style>
