<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { indonesiaMaterialsApi, type MaterialRecord } from '@/api/indonesiaMaterials'
import { getApiErrorMessage } from '@/lib/http'
import { useMaterials } from './workspace'
import { focusFollowup } from './focusFollowup'
import { receiptSummary } from './receiptSummary'
import { planningMaterials } from './planning'

const props = defineProps<{ blocked?: boolean }>()
const ws = useMaterials()
const root = ref<HTMLElement | null>(null)
const visible = ref(false), downloading = ref(false), error = ref(''), notice = ref('')
const syncing = ref(false)
const syncErrorOperation = ref('')
const customer = ref(''), recipient = ref('RRI'), warehouse = ref(''), itemNo = ref(''), search = ref('')
const selection = ref<string[]>([])
const customers = computed(() => [...new Set(ws.board.map(order => order.customer))].sort())
const orders = computed(() => ws.board.filter(order => order.customer === customer.value && order.recipient === recipient.value))
const pendingOrders = computed(() => orders.value.filter(order => (!itemNo.value || order.item_no === itemNo.value) && planningMaterials(order, ws.records).addedIds.length))
const pendingMaterials = computed(() => pendingOrders.value.reduce((total, order) => total + planningMaterials(order, ws.records).addedIds.length, 0))
const items = computed(() => [...new Set(orders.value.map(order => order.item_no))].sort())
const rows = computed(() => receiptSummary(orders.value.filter(order => !itemNo.value || order.item_no === itemNo.value), ws.records)
  .map(row => ({ ...row, available: row.valid && !pendingOrders.value.length })))
const filtered = computed(() => {
  const term = search.value.trim().toLocaleLowerCase()
  return rows.value.filter(row => !term || [row.material?.data.code, row.material?.data.name, row.material?.data.english_name, row.material?.data.specification, ...row.items].join(' ').toLocaleLowerCase().includes(term))
})
const selectable = computed(() => filtered.value.filter(row => row.available))
const selected = computed(() => rows.value.filter(row => row.available && selection.value.includes(row.key)))
const allSelected = computed(() => selectable.value.length > 0 && selectable.value.every(row => selection.value.includes(row.key)))
const someSelected = computed(() => !allSelected.value && selectable.value.some(row => selection.value.includes(row.key)))
const hiddenSelected = computed(() => selected.value.filter(row => !filtered.value.some(item => item.key === row.key)).length)
const locked = computed(() => props.blocked || ws.locked || !ws.canWrite || downloading.value || syncing.value)
watch([customer, recipient], () => { selection.value = []; itemNo.value = ''; error.value = ''; notice.value = '' }, { flush: 'sync' })
watch([customer, recipient, itemNo], () => { selection.value = rows.value.filter(row => row.available).map(row => row.key) }, { flush: 'post' })
watch(rows, value => { selection.value = selection.value.filter(key => value.some(row => row.key === key && row.available)) })
watch(() => ws.pending, (pending, previous) => {
  if (syncErrorOperation.value && previous?.operation_id === syncErrorOperation.value && pending?.operation_id !== syncErrorOperation.value) {
    error.value = ''; syncErrorOperation.value = ''
  }
})
watch(() => ws.scopeEpoch, () => { visible.value = false; selection.value = []; customer.value = ''; warehouse.value = ''; search.value = ''; error.value = ''; notice.value = ''; syncing.value = false })
async function open(initialCustomer: string, initialRecipient: string, initialWarehouse: string) {
  if (props.blocked || ws.locked || !ws.canWrite) return
  customer.value = customers.value.includes(initialCustomer) ? initialCustomer : customer.value || (customers.value.length === 1 ? customers.value[0]! : '')
  recipient.value = initialRecipient
  warehouse.value = initialWarehouse
  visible.value = true
  selection.value = rows.value.filter(row => row.available).map(row => row.key)
  await nextTick()
  focusFollowup(root.value)
}
function toggleAll(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  selection.value = checked ? [...new Set([...selection.value, ...selectable.value.map(row => row.key)])]
    : selection.value.filter(key => !selectable.value.some(row => row.key === key))
}
async function syncAll() {
  if (locked.value || !pendingOrders.value.length) return
  const epoch = ws.scopeEpoch, count = pendingOrders.value.length, additions = pendingMaterials.value
  const contracts: MaterialRecord[] = [], products = new Map<string, MaterialRecord>(), materials = new Map<string, MaterialRecord>()
  error.value = ''; notice.value = ''
  for (const order of pendingOrders.value) {
    const contract = ws.record(order.id), catalog = planningMaterials(order, ws.records)
    const added = catalog.addedIds.map(id => ws.record(id))
    if (!contract || !catalog.product || added.some(material => !material || material.data.deleted)) {
      error.value = '货号或物料资料不完整，请刷新清单后核对。'; return
    }
    contracts.push(contract); products.set(catalog.product.id, catalog.product)
    added.forEach(material => materials.set(material!.id, material!))
  }
  const versions = (records: MaterialRecord[]) => records.map(row => ({ id: row.id, expected_version: row.version }))
  const payload = { customer: customer.value, recipient: recipient.value, item_no: itemNo.value,
    orders: versions(contracts), products: versions([...products.values()]), materials: versions([...materials.values()]) }
  syncing.value = true
  try {
    const saved = await ws.run('order_materials_sync', payload)
    if (epoch !== ws.scopeEpoch) return
    if (!saved) { error.value = ws.error; syncErrorOperation.value = ws.pending?.action === 'order_materials_sync' ? ws.pending.operation_id : ''; return }
    notice.value = ws.loadError || pendingOrders.value.length
      ? '更新已提交，请刷新清单并核对剩余待同步合同后下载。'
      : `已更新 ${count} 张合同，补入 ${additions} 项物料，可直接勾选下载。`
    if (!ws.loadError && !pendingOrders.value.length) selection.value = rows.value.filter(row => row.available).map(row => row.key)
  } finally { if (epoch === ws.scopeEpoch) syncing.value = false }
}
async function refreshList() {
  if (locked.value) return
  const epoch = ws.scopeEpoch
  await ws.reload()
  if (epoch === ws.scopeEpoch) { error.value = ws.loadError; notice.value = '' }
}
async function download() {
  if (locked.value || !customer.value || !selected.value.length || selected.value.length > 200) return
  const epoch = ws.scopeEpoch, factory = ws.factory
  const request = { factory_id: factory, customer: customer.value, recipient: recipient.value, warehouse: warehouse.value,
    mode: 'summary' as const, item_no: itemNo.value, material_ids: selected.value.map(row => row.key) }
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
    <div class="im-inline"><h3>汇总未收物料</h3><button type="button" :disabled="locked" @click="visible = false">收起模板选择</button></div>
    <fieldset class="im-stack" :disabled="locked">
      <div class="im-fields">
        <label class="im-field"><span>模板客人 *</span><select v-model="customer" required><option value="">请选择客人</option><option v-for="name in customers" :key="name">{{ name }}</option></select></label>
        <label class="im-field"><span>模板接收方 *</span><select v-model="recipient"><option>RRI</option><option>RRM</option></select></label>
        <label class="im-field"><span>回传仓库</span><select v-model="warehouse"><option value="">由仓库填写</option><option>来料仓</option><option>胶件仓</option><option>半成品仓</option><option v-if="warehouse && !['来料仓', '胶件仓', '半成品仓'].includes(warehouse)">{{ warehouse }}</option></select></label>
        <label class="im-field"><span>筛选货号</span><select v-model="itemNo"><option value="">全部货号</option><option v-for="item in items" :key="item">{{ item }}</option></select><small>只筛选模板；回传按本客人／接收方全部未收合同建议分配。</small></label>
      </div>
      <div class="im-inline">
        <label class="im-field im-template-search"><span>查找物料</span><input v-model="search" type="search" placeholder="正式报关名称、规格或编码"></label>
      </div>
      <div v-if="pendingOrders.length" class="im-stack" role="status" aria-label="回料模板待同步合同">
        <div class="im-actions"><button type="button" class="im-primary" @click="syncAll">{{ syncing ? '正在更新合同物料…' : `更新全部合同物料（${pendingOrders.length} 张）` }}</button><span>待补入 {{ pendingMaterials }} 项物料</span></div>
        <p class="im-note">更新范围：{{ customer }} · {{ recipient }} · {{ itemNo || '全部货号' }}。物料搜索不缩小合同更新范围。</p>
        <details><summary>查看待更新合同</summary><div v-for="order in pendingOrders" :key="order.id" class="im-inline"><strong>{{ order.contract_no }}</strong><span>PO {{ order.po_no || '未填写' }} · {{ order.item_no }} · 新增 {{ planningMaterials(order, ws.records).addedIds.length }} 种</span></div></details>
      </div>
      <div v-if="filtered.length" class="im-scroll">
        <table><thead><tr><th><input type="checkbox" :checked="allSelected" :indeterminate="someSelected" aria-label="全选当前模板物料" @change="toggleAll"></th><th>正式报关物料</th><th>涉及合同</th><th>单位</th><th>需求合计</th><th>已实收分配</th><th>剩余未送货</th></tr></thead>
          <tbody><tr v-for="row in filtered" :key="row.key" :data-template-material="row.key"><td><input v-model="selection" type="checkbox" :value="row.key" :disabled="!row.available" :aria-label="`选择模板物料 ${row.material?.data.name || '资料需核对'} ${row.material?.data.specification || ''}`"></td><td>{{ row.material?.data.name || '物料资料需核对' }}<small>{{ row.material?.data.code || '无物料编码' }} · {{ row.material?.data.specification || '未填写规格' }}</small><small v-if="!row.valid" class="im-danger-text">物料资料或单位需核对</small></td><td>{{ row.orders.size }} 张<small>{{ [...row.items].join('、') }}</small></td><td>{{ row.material?.data.unit }}</td><td>{{ row.quantity }}</td><td>{{ row.coverage }}</td><td><strong>{{ row.remaining }}</strong></td></tr></tbody>
        </table>
      </div>
      <p v-else class="im-empty">{{ customer ? '没有符合条件的未收物料。' : '选择客人后汇总未收物料。' }}</p>
      <p class="im-note">同一物料合并未收需求，仓库无需分合同。回传后按最迟回料日建议分配，由业务确认。已实收分配（含备品）只扣一次。</p>
      <div class="im-actions"><button class="im-primary" type="submit" :disabled="!selected.length || selected.length > 200">{{ downloading ? '正在生成模板…' : `下载所选 ${selected.length} 行 Excel` }}</button><span>灰色为系统资料，黄色为仓库填写；本次实收数量留空。</span><button v-if="selection.length" type="button" @click="selection = []">清空选择</button></div>
      <p v-if="hiddenSelected" class="im-note">另有 {{ hiddenSelected }} 行已选物料不在当前筛选结果中，仍会下载。</p>
      <p v-if="selected.length > 200" class="im-danger-text" role="alert">每次最多下载 200 行，请减少选择或分批下载。</p>
    </fieldset>
    <p v-if="error" class="im-danger-text" role="alert">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
    <button v-if="error || ws.loadError" type="button" :disabled="locked" @click="refreshList">刷新合同清单</button>
  </form>
</template>
