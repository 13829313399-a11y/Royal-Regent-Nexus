<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { indonesiaMaterialsApi } from '@/api/indonesiaMaterials'
import { getApiErrorMessage } from '@/lib/http'
import { useMaterials } from './workspace'
import { focusFollowup } from './focusFollowup'
import { quantity } from './warehouseMatching'

const props = defineProps<{ blocked?: boolean }>()
const ws = useMaterials()
const root = ref<HTMLElement | null>(null)
const visible = ref(false), downloading = ref(false), error = ref(''), notice = ref('')
const customer = ref(''), recipient = ref('RRI'), warehouse = ref(''), itemNo = ref(''), search = ref(''), pendingOnly = ref(false)
const selection = ref<string[]>([])
const customers = computed(() => [...new Set(ws.board.map(order => order.customer))].sort())
const orders = computed(() => ws.board.filter(order => order.customer === customer.value && order.recipient === recipient.value))
const items = computed(() => [...new Set(orders.value.map(order => order.item_no))].sort())
const rows = computed(() => orders.value.flatMap(order => order.demands.map(demand => {
  const material = ws.record(demand.material_id)
  return { key: JSON.stringify([order.id, demand.id]), order, demand, material,
    available: material?.kind === 'material' && !material.data.deleted }
})))
const filtered = computed(() => {
  const term = search.value.trim().toLocaleLowerCase()
  return rows.value.filter(row => (!itemNo.value || row.order.item_no === itemNo.value)
    && (!pendingOnly.value || (quantity(row.demand.shortage) ?? 0n) > 0n)
    && (!term || [row.order.contract_no, row.order.po_no, row.order.item_no, row.material?.data.code, row.material?.data.name, row.material?.data.english_name].join(' ').toLocaleLowerCase().includes(term)))
})
const selectable = computed(() => filtered.value.filter(row => row.available))
const selected = computed(() => rows.value.filter(row => row.available && selection.value.includes(row.key)))
const allSelected = computed(() => selectable.value.length > 0 && selectable.value.every(row => selection.value.includes(row.key)))
const someSelected = computed(() => !allSelected.value && selectable.value.some(row => selection.value.includes(row.key)))
const hiddenSelected = computed(() => selected.value.filter(row => !filtered.value.some(item => item.key === row.key)).length)
const locked = computed(() => props.blocked || ws.locked || !ws.canWrite || downloading.value)
watch([customer, recipient], () => { selection.value = []; itemNo.value = ''; error.value = ''; notice.value = '' }, { flush: 'sync' })
watch(rows, value => { selection.value = selection.value.filter(key => value.some(row => row.key === key && row.available)) })
watch(() => ws.scopeEpoch, () => { visible.value = false; selection.value = []; customer.value = ''; warehouse.value = ''; search.value = ''; error.value = ''; notice.value = '' })
async function open(initialCustomer: string, initialRecipient: string, initialWarehouse: string) {
  if (props.blocked || ws.locked || !ws.canWrite) return
  customer.value = customers.value.includes(initialCustomer) ? initialCustomer : customer.value || (customers.value.length === 1 ? customers.value[0]! : '')
  recipient.value = initialRecipient
  warehouse.value = initialWarehouse
  visible.value = true
  await nextTick()
  focusFollowup(root.value)
}
function toggleAll(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  selection.value = checked ? [...new Set([...selection.value, ...selectable.value.map(row => row.key)])]
    : selection.value.filter(key => !selectable.value.some(row => row.key === key))
}
async function download() {
  if (locked.value || !customer.value || !selected.value.length || selected.value.length > 200) return
  const epoch = ws.scopeEpoch, factory = ws.factory
  const request = { factory_id: factory, customer: customer.value, recipient: recipient.value, warehouse: warehouse.value,
    selections: selected.value.map(row => ({ order_id: row.order.id, demand_id: row.demand.id })) }
  downloading.value = true; error.value = ''; notice.value = ''
  try {
    const blob = await indonesiaMaterialsApi.warehouseTemplate(request)
    if (epoch !== ws.scopeEpoch || factory !== ws.factory || !ws.canWrite) return
    const url = URL.createObjectURL(blob), link = document.createElement('a')
    try {
      link.href = url; link.download = '仓库实收回传模板.xlsx'; link.click()
    } finally { setTimeout(() => URL.revokeObjectURL(url), 1000) }
    notice.value = '模板已下载，填写黄色区域后由业务导入。'
  } catch (cause) { if (epoch === ws.scopeEpoch && factory === ws.factory) error.value = getApiErrorMessage(cause) }
  finally { downloading.value = false }
}
defineExpose({ open })
</script>

<template>
  <form v-show="visible" ref="root" class="im-stack im-receipt-template" aria-label="下载订单实收模板" @submit.prevent="download">
    <div class="im-inline"><h3>选择订单与物料</h3><button type="button" :disabled="downloading" @click="visible = false">收起模板选择</button></div>
    <fieldset class="im-stack" :disabled="locked">
      <div class="im-fields">
        <label class="im-field"><span>模板客人 *</span><select v-model="customer" required><option value="">请选择客人</option><option v-for="name in customers" :key="name">{{ name }}</option></select></label>
        <label class="im-field"><span>模板接收方 *</span><select v-model="recipient"><option>RRI</option><option>RRM</option></select></label>
        <label class="im-field"><span>回传仓库</span><select v-model="warehouse"><option value="">由仓库填写</option><option>来料仓</option><option>胶件仓</option><option>半成品仓</option><option v-if="warehouse && !['来料仓', '胶件仓', '半成品仓'].includes(warehouse)">{{ warehouse }}</option></select></label>
        <label class="im-field"><span>筛选货号</span><select v-model="itemNo"><option value="">全部货号</option><option v-for="item in items" :key="item">{{ item }}</option></select></label>
      </div>
      <div class="im-inline">
        <label class="im-field im-template-search"><span>查找合同／PO／物料</span><input v-model="search" type="search" placeholder="合同、PO 或正式报关名称"></label>
        <label class="im-inline"><input v-model="pendingOnly" type="checkbox"><span>仅看剩余未送货</span></label>
      </div>
      <div v-if="filtered.length" class="im-scroll">
        <table><thead><tr><th><input type="checkbox" :checked="allSelected" :indeterminate="someSelected" aria-label="全选当前模板物料" @change="toggleAll"></th><th>合同／PO／货号</th><th>正式报关物料</th><th>单位</th><th>订单需求</th><th>已实收分配</th><th>剩余未送货</th></tr></thead>
          <tbody><tr v-for="row in filtered" :key="row.key" :data-template-demand="row.demand.id"><td><input v-model="selection" type="checkbox" :value="row.key" :disabled="!row.available" :aria-label="`选择模板物料 ${row.order.contract_no} ${row.order.po_no} ${row.demand.code}`"></td><td><strong>{{ row.order.contract_no }}</strong><small>PO {{ row.order.po_no || '未填写' }} · {{ row.order.item_no }}</small></td><td>{{ row.material?.data.name || row.demand.name }}<small>{{ row.material?.data.code || row.demand.code }} · {{ row.material?.data.specification || '未填写规格' }}</small><small v-if="!row.available" class="im-danger-text">物料资料不可用，请先核对</small></td><td>{{ row.demand.unit }}</td><td>{{ row.demand.quantity }}</td><td>{{ row.demand.coverage }}</td><td><strong>{{ row.demand.shortage }}</strong></td></tr></tbody>
        </table>
      </div>
      <p v-else class="im-empty">{{ customer ? '没有符合条件的合同物料，请调整筛选或先导入排期。' : '选择客人后显示合同物料。' }}</p>
      <p class="im-note">剩余＝订单需求－已实收分配（含备品），最低为 0；已出货不重复扣减。下载时按最新记录计算。</p>
      <div class="im-actions"><button class="im-primary" type="submit" :disabled="!selected.length || selected.length > 200">{{ downloading ? '正在生成模板…' : `下载所选 ${selected.length} 行 Excel` }}</button><span>灰色为系统资料，黄色为仓库填写；本次实收数量留空。</span><button v-if="selection.length" type="button" @click="selection = []">清空选择</button></div>
      <p v-if="hiddenSelected" class="im-note">另有 {{ hiddenSelected }} 行已选物料不在当前筛选结果中，仍会下载。</p>
      <p v-if="selected.length > 200" class="im-danger-text" role="alert">每次最多下载 200 行，请减少选择或分批下载。</p>
    </fieldset>
    <p v-if="error" class="im-danger-text" role="alert">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
  </form>
</template>
