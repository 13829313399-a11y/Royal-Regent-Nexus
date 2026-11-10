<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { customerOrderLedgerApi, type CustomerOrderLedgerLine } from '@/api/customerOrderLedger'
import { getApiErrorMessage } from './api'
import { sameReconciliationProduct } from './reconciliation'
export interface ExistingOrderSelection { enabled: boolean; lineId: string; expectedRevision: number; reason: string; target?: CustomerOrderLedgerLine }
const props = defineProps<{ factoryId: string; customerCode: string; productNo: string; eligible: boolean; disabled: boolean; modelValue: ExistingOrderSelection }>()
const emit = defineEmits<{ 'update:modelValue': [value: ExistingOrderSelection] }>()
const items = ref<CustomerOrderLedgerLine[]>([])
const loading = ref(false)
const error = ref('')
const query = ref('')
const page = ref(1)
const total = ref(0)
let sequence = 0
const pages = computed(() => Math.max(1, Math.ceil(total.value / 50)))
const selected = computed(() => items.value.find(item => item.id === props.modelValue.lineId))
function update(value: Partial<ExistingOrderSelection>) { emit('update:modelValue', { ...props.modelValue, ...value }) }
function reset() {
  sequence += 1; loading.value = false; items.value = []; error.value = ''; query.value = ''; page.value = 1; total.value = 0
  emit('update:modelValue', { enabled: false, lineId: '', expectedRevision: 0, reason: '' })
}
async function load(activate = false) {
  if (!props.eligible) return
  const token = ++sequence
  loading.value = true
  error.value = ''
  update({ enabled: activate || props.modelValue.enabled, lineId: '', expectedRevision: 0, target: undefined })
  try {
    const result = await customerOrderLedgerApi.list(props.factoryId, { customerCode: props.customerCode, view: 'all', q: query.value.trim(), page: page.value, pageSize: 50 })
    if (token !== sequence) return
    items.value = result.items.filter(item => item.factory_id === props.factoryId && item.customer_code === props.customerCode && sameReconciliationProduct(props.customerCode, item.product_no, props.productNo) && item.status === 'active')
    total.value = result.total
  } catch (failure) { if (token === sequence) { items.value = []; total.value = 0; error.value = getApiErrorMessage(failure) } }
  finally { if (token === sequence) loading.value = false }
}
function toggle(event: Event) {
  if (!(event.target as HTMLInputElement).checked) return reset()
  update({ enabled: true })
  void load(true)
}
function choose(event: Event) {
  const line = items.value.find(item => item.id === (event.target as HTMLSelectElement).value)
  update({ lineId: line?.id || '', expectedRevision: line?.revision || 0, target: line })
}
function search() { page.value = 1; void load() }
function go(next: number) { page.value = next; void load() }
watch(() => [props.factoryId, props.customerCode, props.productNo, props.eligible], reset)
onBeforeUnmount(() => { sequence += 1 })
</script>
<template>
  <fieldset class="existing-order" :disabled="disabled">
    <label class="check"><input :checked="modelValue.enabled" type="checkbox" :disabled="!eligible" @change="toggle">关联已有订单（正式 PO 补齐 / 修订）</label>
    <p class="muted">仅单条正式 PO 可关联同客户、匹配货号的有效订单，保留原订单、发送与走货记录。关联仅在“确认并保存订单”时生效。<template v-if="customerCode === 'edu'">EDU 历史货号仅按已支持的 F11/F12 四位尾码规则匹配，原始货号仍在下方展示。</template></p>
    <div v-if="modelValue.enabled" class="trial-stack">
      <div class="trial-actions"><label>搜索已有订单<input v-model="query" type="search" placeholder="参考号、PO 或完整货号" @keyup.enter="search"></label><Button type="button" variant="outline" :disabled="loading" @click="search">搜索</Button></div>
      <p v-if="error" class="notice error" role="alert">{{ error }}</p>
      <label>当前客户 · 货号 {{ productNo }}<select :value="modelValue.lineId" :disabled="loading" @change="choose"><option value="">{{ loading ? '正在读取…' : '请选择已有订单' }}</option><option v-for="item in items" :key="item.id" :value="item.id">{{ item.reference_no }} · {{ item.product_no }} · 数量 {{ item.quantity }}</option></select></label>
      <p v-if="!loading && !items.length" class="muted">当前页没有同货号的有效订单，可更换关键词或翻页查找。</p>
      <div class="pagination"><span>第 {{ page }} / {{ pages }} 页（查询共 {{ total }} 条）</span><Button type="button" variant="outline" :disabled="loading || page <= 1" @click="go(page - 1)">上一页</Button><Button type="button" variant="outline" :disabled="loading || page >= pages" @click="go(page + 1)">下一页</Button></div>
      <p v-if="selected" class="notice warning">将修订 {{ selected.reference_no }} / {{ selected.product_no }}，当前数量 {{ selected.quantity }}，当前修订 {{ selected.revision }}。</p>
      <label>正式 PO 核对原因（4–500 字）<textarea :value="modelValue.reason" rows="2" maxlength="500" @input="update({ reason: ($event.target as HTMLTextAreaElement).value })" /></label>
    </div>
  </fieldset>
</template>
<style scoped>.existing-order{border:1px solid var(--border);border-radius:9px;margin:20px 0;padding:16px}.existing-order>.muted{margin:10px 0}</style>
