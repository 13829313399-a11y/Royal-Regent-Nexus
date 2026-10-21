<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import SectionPanel from './MaterialsPanel.vue'
import type { BoardOrder, Data, Demand, MaterialRecord } from '@/api/indonesiaMaterials'
import Fields from './Fields.vue'
import { inputData, orderDefaults, orderFields, showStatus, setNumberText } from './forms'
import { useMaterials } from './workspace'
import { customerOptions, customerProducts, fixedCustomers } from './catalog'
import { useMaterialDraft } from './useDraft'
import { recordRef, restoreRecord } from './draftPersistence'
const ws = useMaterials()
const orderForm = ref<Data | null>(null)
const editing = ref<MaterialRecord>()
const selection = ref<{ mode: 'adjust' | 'recalculate' | 'allocate' | 'reallocate'; record: MaterialRecord; demand?: Demand } | null>(null)
const data = ref<Data>({})
const restoring = ref(false)
const draft = useMaterialDraft(() => orderForm.value ?? (selection.value ? data.value : null), {
  id: 'demand', capture: () => orderForm.value || selection.value ? { orderForm: orderForm.value, editing: recordRef(editing.value), selection: selection.value ? { mode: selection.value.mode, record: recordRef(selection.value.record), demandId: selection.value.demand?.id } : null, data: data.value } : null,
  async restore(saved) {
    const row = restoreRecord(ws.records, saved.editing, 'order')
    let chosen: typeof selection.value = null
    if (saved.selection) {
      const mode = saved.selection.mode
      if (!['adjust', 'recalculate', 'allocate', 'reallocate'].includes(mode)) throw new Error('需求草稿类型无法识别。')
      const source = restoreRecord(ws.records, saved.selection.record, mode === 'reallocate' ? 'allocation' : 'order')
      if (!source) throw new Error('原合同或分配记录已不可用，草稿仍保留。')
      const demand = ws.board.find(order => order.id === source.id)?.demands.find(item => item.id === saved.selection.demandId)
      if (saved.selection.demandId && !demand) throw new Error('原物料需求已变化，请核对；草稿仍保留。')
      chosen = { mode, record: source, demand }
    }
    restoring.value = true
    try { editing.value = row; selection.value = chosen; orderForm.value = saved.orderForm ? inputData(orderDefaults, saved.orderForm) : null; data.value = saved.data || {}; await nextTick() }
    finally { restoring.value = false }
  },
  reset: () => { orderForm.value = null; selection.value = null; editing.value = undefined },
})
function close() { if (draft.permitDiscard()) { orderForm.value = null; selection.value = null } }
const products = computed(() => customerProducts(ws.records, orderForm.value?.customer || ''))
const fields = computed(() => orderFields.map(field => {
  const result = { ...field, readonly: !!editing.value && ['customer', 'recipient', 'contract_no', 'item_no', 'batch'].includes(field.key) }
  if (field.key === 'customer') return { ...result, type: 'select' as const, options: customerOptions(ws.records, editing.value?.data.customer) }
  if (field.key === 'item_no') {
    const options = products.value.map(product => ({ value: String(product.data.code), label: `${product.data.code}${product.data.name ? ' · ' + product.data.name : ''}${!product.data.materials.length ? '（待配置物料）' : ''}` }))
    const historical = editing.value?.data.item_no
    if (historical && !options.some(option => option.value === historical)) options.push({ value: historical, label: `${historical}（历史货号）` })
    return { ...result, type: 'select' as const, options: [{ value: '', label: '请选择该客人的货号' }, ...options] }
  }
  return result
}))
watch(() => orderForm.value?.customer, (customer, previous) => { if (!restoring.value && orderForm.value && !editing.value && customer !== previous) orderForm.value.item_no = '' })
watch(() => orderForm.value?.item_no, code => {
  if (restoring.value || !orderForm.value || editing.value) return
  const product = products.value.find(row => row.data.code === code)
  if (product) orderForm.value.unit = product.data.unit
})
const sourceMaterial = computed(() => selection.value?.mode === 'reallocate'
  ? ws.record(selection.value.record.data.supply_id)?.data.material_id : selection.value?.demand?.material_id)
const targetDemands = computed(() => ws.board.find(row => row.id === data.value.order_id)?.demands.filter(row => row.material_id === sourceMaterial.value) ?? [])
const targetOrders = computed(() => ws.board.filter(row => row.demands.some(demand => demand.material_id === sourceMaterial.value)))
const supplies = computed(() => ws.kind('supply').filter(row => row.data.material_id === sourceMaterial.value))
function edit(row?: MaterialRecord) { if (!draft.beforeOpen()) return; selection.value = null; editing.value = row; orderForm.value = inputData(orderDefaults, row?.data); if (row) orderForm.value.reason = ''; draft.accept() }
async function saveOrder() { if (orderForm.value) await draft.run('order_save', orderForm.value, editing.value, () => { orderForm.value = null }) }
function choose(mode: 'adjust' | 'recalculate' | 'allocate', order: BoardOrder, demand?: Demand) {
  const row = ws.record(order.id); if (!row) return
  if (!draft.beforeOpen()) return
  orderForm.value = null; selection.value = { mode, record: row, demand }
  data.value = mode === 'adjust' ? { demand_id: demand?.id, quantity: demand?.quantity, reason: '' }
    : mode === 'allocate' ? { order_id: order.id, demand_id: demand?.id, supply_id: '', normal_quantity: '', spare_quantity: '0', reason: '' }
      : { reason: '' }
  draft.accept()
}
function reallocate(row: MaterialRecord) {
  if (!draft.beforeOpen()) return
  orderForm.value = null; selection.value = { mode: 'reallocate', record: row }
  data.value = { order_id: '', demand_id: '', normal_quantity: '', spare_quantity: '0', reason: '' }
  draft.accept()
}
async function apply() {
  if (!selection.value) return
  const action = { adjust: 'demand_adjust', recalculate: 'order_recalculate', allocate: 'allocate', reallocate: 'reallocate' } as const
  await draft.run(action[selection.value.mode], data.value, selection.value.mode === 'allocate' ? undefined : selection.value.record, () => { selection.value = null })
}
</script>
<template>
  <SectionPanel title="合同物料需求与分配" subtitle="每个交付批次单独计算需求；正常量及免费备品量按来源分别绑定。预计供应的绑定不等于已齐料。">
    <template #action><button type="button" class="im-primary" :disabled="!ws.canWrite || ws.locked" @click="edit()">新增合同交付批次</button></template>
    <div class="im-summary-strip"><div><span>合同交付批次</span><strong>{{ ws.board.length }} <small>批</small></strong></div><div><span>合同物料需求</span><strong>{{ ws.board.reduce((total, row) => total + row.demands.length, 0) }} <small>项</small></strong></div><div><span>物料分配记录</span><strong>{{ ws.kind('allocation').length }} <small>条</small></strong></div></div>
    <div v-if="ws.board.length" class="im-stack"><article v-for="order in ws.board" :key="order.id" class="rounded-lg border border-border p-4">
      <div class="flex flex-wrap items-center justify-between gap-3"><h3>{{ order.customer }} / {{ order.recipient }} · {{ order.contract_no }} / {{ order.batch }} / {{ order.item_no }}</h3><div class="flex flex-wrap gap-2"><button type="button" :disabled="!ws.canWrite || ws.locked" @click="edit(ws.record(order.id))">编辑批次</button><button type="button" :disabled="!ws.canWrite || ws.locked" @click="choose('recalculate', order)">重新生成需求</button></div></div>
      <div v-if="order.demands.length" class="im-scroll"><table><thead><tr><th>物料</th><th>系统计算</th><th>最终需求</th><th>已绑定</th><th>实际覆盖／缺口</th><th>操作</th></tr></thead><tbody><tr v-for="demand in order.demands" :key="demand.id"><td>{{ demand.code }} · {{ demand.name }}</td><td>{{ demand.computed_quantity }} {{ demand.unit }}</td><td>{{ demand.quantity }} {{ demand.unit }}</td><td>{{ demand.allocated }}</td><td>{{ demand.coverage }} / {{ demand.shortage }}</td><td><div class="flex flex-wrap gap-2"><button type="button" :disabled="!ws.canWrite || ws.locked" @click="choose('adjust', order, demand)">调整需求</button><button type="button" :disabled="!ws.canWrite || ws.locked" @click="choose('allocate', order, demand)">分配供应</button></div></td></tr></tbody></table></div>
      <p v-else class="im-note">尚无有效需求，请补齐基础资料后重新生成。</p>
    </article></div>
    <p v-else-if="!orderForm" class="im-empty">暂无合同交付批次，可以手工新增或从统一排期导入。</p>
    <form v-if="orderForm" class="im-editor im-stack" @submit.prevent="saveOrder"><h3>{{ editing ? '编辑' : '新增' }}合同交付批次</h3><p v-if="!editing && !fixedCustomers(ws.records).length" class="im-message">请先到基础资料库新增本厂区固定客人，并配置其货号及物料用量。</p><fieldset :disabled="!ws.canWrite || ws.locked" class="im-stack"><Fields :model="orderForm" :fields="fields" /><p v-if="editing" class="im-note">合同身份字段保留原值。数量或交期修改会按服务器规则重新核对需求与已分配数量，请填写变更原因。</p><p v-else class="im-note">按当前厂区的固定客人和货号读取物料用量、日产能及运输参数；接收方单独选择。</p><div v-if="!editing && orderForm.item_no" class="im-recipe-preview"><h3>该货号的固定物料</h3><p v-for="product in products.filter(row => row.data.code === orderForm?.item_no)" :key="product.id"><span v-if="!product.data.materials.length">物料用量尚未配置，请先补齐资料。</span><span v-for="recipe in product.data.materials" :key="recipe.material_id">{{ ws.materialName(recipe.material_id) }} · 每件 {{ recipe.usage }} {{ ws.record(recipe.material_id)?.data.unit }}<br></span></p></div><button class="im-primary" type="submit">保存合同批次</button></fieldset><button type="button" :disabled="ws.busy || !!ws.pending" @click="close">关闭表单</button></form>
    <form v-if="selection" class="im-editor im-stack" @submit.prevent="apply">
      <h3>{{ ({ adjust: '调整最终需求', recalculate: '业务确认重新生成需求', allocate: '分配供应数量', reallocate: '未发物料改绑' })[selection.mode] }}</h3>
      <p v-if="selection.mode !== 'reallocate'">{{ ws.orderName(selection.record.id) }} <span v-if="selection.demand">· {{ selection.demand.code }} · {{ selection.demand.name }}</span></p>
      <p v-else>原合同：{{ ws.orderName(selection.record.data.order_id) }} · 已分配正常／备品 {{ selection.record.data.normal_quantity }} / {{ selection.record.data.spare_quantity }} · 已发正常／备品 {{ selection.record.data.shipped_normal ?? '0' }} / {{ selection.record.data.shipped_spare ?? '0' }}</p>
      <fieldset :disabled="!ws.canWrite || ws.locked" class="im-stack">
        <p v-if="selection.mode === 'recalculate'" class="im-message">将读取最新货号用量及计划参数，重新生成该批次需求快照。现有人工调整、已分配与已发记录由服务器核对；请核对变更原因后确认。</p>
        <label v-if="selection.mode === 'adjust'" class="im-field"><span>调整后的最终需求量 *</span><input :value="data.quantity" type="number" min="0" step="any" required @input="setNumberText(data, 'quantity', $event)"></label>
        <label v-if="selection.mode === 'allocate'" class="im-field"><span>同物料采购／回料来源 *</span><select v-model="data.supply_id" required><option value="">请选择供应批次</option><option v-for="supply in supplies" :key="supply.id" :value="supply.id">{{ supply.data.purchase_no }} / {{ supply.data.batch }} · {{ showStatus(supply.data.status) }} · 正常 {{ supply.data.normal_quantity }} / 备品 {{ supply.data.spare_quantity }}</option></select></label>
        <div v-if="selection.mode === 'reallocate'" class="im-fields"><label class="im-field"><span>目标合同交付批次 *</span><select v-model="data.order_id" required @change="data.demand_id = ''"><option value="">请选择合同</option><option v-for="order in targetOrders" :key="order.id" :value="order.id">{{ order.customer }} / {{ order.recipient }} · {{ ws.orderName(order.id) }}</option></select></label><label class="im-field"><span>目标物料需求 *</span><select v-model="data.demand_id" required><option value="">请选择需求</option><option v-for="demand in targetDemands" :key="demand.id" :value="demand.id">{{ demand.code }} · {{ demand.name }} · 缺口 {{ demand.shortage }}</option></select></label></div>
        <div v-if="selection.mode === 'allocate' || selection.mode === 'reallocate'" class="im-fields"><label class="im-field"><span>{{ selection.mode === 'reallocate' ? '转走' : '分配' }}正常量 *</span><input :value="data.normal_quantity" type="number" min="0" step="any" required @input="setNumberText(data, 'normal_quantity', $event)"></label><label class="im-field"><span>{{ selection.mode === 'reallocate' ? '转走' : '分配' }}备品量 *</span><input :value="data.spare_quantity" type="number" min="0" step="any" required @input="setNumberText(data, 'spare_quantity', $event)"></label></div>
        <label class="im-field"><span>业务原因{{ selection.mode !== 'allocate' ? ' *' : '（选填）' }}</span><textarea v-model="data.reason" :required="selection.mode !== 'allocate'" maxlength="500" /></label>
        <p v-if="selection.mode === 'allocate' || selection.mode === 'reallocate'" class="im-note">数量余量、需求上限与改绑限制由服务器核对，提交成功后刷新双方合同缺口。</p>
        <button class="im-primary" type="submit">确认保存</button>
      </fieldset><button type="button" :disabled="ws.busy || !!ws.pending" @click="close">取消</button>
    </form>
    <h3 class="mt-6">分配台账</h3>
    <div v-if="ws.kind('allocation').length" class="im-scroll"><table><thead><tr><th>合同／批次／货号</th><th>物料／供应来源</th><th>正常／备品分配</th><th>已发正常／备品</th><th>操作</th></tr></thead><tbody><tr v-for="row in ws.kind('allocation')" :key="row.id"><td>{{ ws.orderName(row.data.order_id) }}</td><td>{{ ws.materialName(ws.record(row.data.supply_id)?.data.material_id) }}<br>{{ ws.record(row.data.supply_id)?.data.purchase_no }} / {{ ws.record(row.data.supply_id)?.data.batch }}</td><td>{{ row.data.normal_quantity }} / {{ row.data.spare_quantity }}</td><td>{{ row.data.shipped_normal ?? '0' }} / {{ row.data.shipped_spare ?? '0' }}</td><td><button type="button" :disabled="!ws.canWrite || ws.locked" @click="reallocate(row)">未发改绑</button></td></tr></tbody></table></div>
    <p v-else class="im-empty">暂无分配。选择合同物料行并分配其采购／回料来源。</p>
  </SectionPanel>
</template>
