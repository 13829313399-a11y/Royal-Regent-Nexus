<script setup lang="ts">
import { computed, ref } from 'vue'
import SectionPanel from './MaterialsPanel.vue'
import type { BoardOrder, Data, Demand, MaterialRecord } from '@/api/indonesiaMaterials'
import Fields from './Fields.vue'
import { inputData, orderDefaults, orderFields, showStatus, setNumberText } from './forms'
import { useMaterials } from './workspace'
const ws = useMaterials()
const orderForm = ref<Data | null>(null)
const editing = ref<MaterialRecord>()
const selection = ref<{ mode: 'adjust' | 'recalculate' | 'allocate' | 'reallocate'; record: MaterialRecord; demand?: Demand } | null>(null)
const data = ref<Data>({})
const fields = computed(() => orderFields.map(field => ({ ...field, readonly: !!editing.value && ['customer', 'recipient', 'contract_no', 'item_no', 'batch'].includes(field.key) })))
const sourceMaterial = computed(() => selection.value?.mode === 'reallocate'
  ? ws.record(selection.value.record.data.supply_id)?.data.material_id : selection.value?.demand?.material_id)
const targetDemands = computed(() => ws.board.find(row => row.id === data.value.order_id)?.demands.filter(row => row.material_id === sourceMaterial.value) ?? [])
const targetOrders = computed(() => ws.board.filter(row => row.demands.some(demand => demand.material_id === sourceMaterial.value)))
const supplies = computed(() => ws.kind('supply').filter(row => row.data.material_id === sourceMaterial.value))
function edit(row?: MaterialRecord) { selection.value = null; editing.value = row; orderForm.value = inputData(orderDefaults, row?.data); if (row) orderForm.value.reason = '' }
async function saveOrder() { if (orderForm.value && await ws.run('order_save', orderForm.value, editing.value)) orderForm.value = null }
function choose(mode: 'adjust' | 'recalculate' | 'allocate', order: BoardOrder, demand?: Demand) {
  const row = ws.record(order.id); if (!row) return
  orderForm.value = null; selection.value = { mode, record: row, demand }
  data.value = mode === 'adjust' ? { demand_id: demand?.id, quantity: demand?.quantity, reason: '' }
    : mode === 'allocate' ? { order_id: order.id, demand_id: demand?.id, supply_id: '', normal_quantity: '', spare_quantity: '0', reason: '' }
      : { reason: '' }
}
function reallocate(row: MaterialRecord) {
  orderForm.value = null; selection.value = { mode: 'reallocate', record: row }
  data.value = { order_id: '', demand_id: '', normal_quantity: '', spare_quantity: '0', reason: '' }
}
async function apply() {
  if (!selection.value) return
  const action = { adjust: 'demand_adjust', recalculate: 'order_recalculate', allocate: 'allocate', reallocate: 'reallocate' } as const
  if (await ws.run(action[selection.value.mode], data.value, selection.value.mode === 'allocate' ? undefined : selection.value.record)) selection.value = null
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
    <form v-if="orderForm" class="im-editor im-stack" @submit.prevent="saveOrder"><h3>{{ editing ? '编辑' : '新增' }}合同交付批次</h3><fieldset :disabled="!ws.canWrite || ws.locked" class="im-stack"><Fields :model="orderForm" :fields="fields" /><p v-if="editing" class="im-note">合同身份字段保留原值。数量或交期修改会按服务器规则重新核对需求与已分配数量，请填写变更原因。</p><button class="im-primary" type="submit">保存合同批次</button></fieldset><button type="button" :disabled="ws.busy || !!ws.pending" @click="orderForm = null">关闭表单</button></form>
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
      </fieldset><button type="button" :disabled="ws.busy || !!ws.pending" @click="selection = null">取消</button>
    </form>
    <h3 class="mt-6">分配台账</h3>
    <div v-if="ws.kind('allocation').length" class="im-scroll"><table><thead><tr><th>合同／批次／货号</th><th>物料／供应来源</th><th>正常／备品分配</th><th>已发正常／备品</th><th>操作</th></tr></thead><tbody><tr v-for="row in ws.kind('allocation')" :key="row.id"><td>{{ ws.orderName(row.data.order_id) }}</td><td>{{ ws.materialName(ws.record(row.data.supply_id)?.data.material_id) }}<br>{{ ws.record(row.data.supply_id)?.data.purchase_no }} / {{ ws.record(row.data.supply_id)?.data.batch }}</td><td>{{ row.data.normal_quantity }} / {{ row.data.spare_quantity }}</td><td>{{ row.data.shipped_normal ?? '0' }} / {{ row.data.shipped_spare ?? '0' }}</td><td><button type="button" :disabled="!ws.canWrite || ws.locked" @click="reallocate(row)">未发改绑</button></td></tr></tbody></table></div>
    <p v-else class="im-empty">暂无分配。选择合同物料行并分配其采购／回料来源。</p>
  </SectionPanel>
</template>
