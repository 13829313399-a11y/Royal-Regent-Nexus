<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import { cartonSupplierPortalApi as api, type PortalWorkspace, type PortalOrder, type PortalPaper } from '@/api/cartonSupplierPortal'
const memberships = ref<{ factory_id: string; supplier_name: string }[]>([])
const factory = ref('')
const workspace = ref<PortalWorkspace | null>(null)
const error = ref(''); const message = ref(''); const busy = ref(false)
const dates = reactive<Record<string, string>>({}); const quantities = reactive<Record<string, number>>({}); const selected = ref<string[]>([])
const deliveryNo = ref(''); const deliveryDate = ref(new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' }))
let generation = 0
const selectedPapers = computed(() => (workspace.value?.orders ?? []).flatMap(order => order.lines.filter(line => selected.value.includes(line.id)).map(line => ({ order, line }))))
const open = (order: PortalOrder) => ['PENDING_SUPPLIER', 'PARTIALLY_RECEIVED'].includes(order.status) && !order.awaiting_issue
function failure(reason: unknown) { error.value = reason instanceof Error ? reason.message : '操作未完成，请刷新后重试' }
async function load() {
  const token = ++generation, scope = factory.value
  if (!scope) return
  try { const data = await api.workspace(scope); if (token !== generation || factory.value !== scope) return; workspace.value = data; for (const order of data.orders) for (const line of order.lines) dates[line.id] = line.promised_date || order.planned_date }
  catch (reason) { if (token === generation) failure(reason) }
}
watch(factory, () => { workspace.value = null; selected.value = []; deliveryNo.value = ''; error.value = ''; message.value = ''; void load() })
onMounted(async () => { try { memberships.value = await api.memberships(); factory.value = memberships.value[0]?.factory_id ?? ''; if (!factory.value) error.value = '此账号尚未开通供应商协同，请联系内部管理员绑定厂区与供应商。' } catch (reason) { failure(reason) } })
async function accept(order: PortalOrder, line: PortalPaper) {
  if (busy.value) return
  if (!dates[line.id]) { error.value = '请填写承诺交期'; return }
  busy.value = true; error.value = ''; const scope = factory.value
  try { await api.accept(line, order, scope, dates[line.id]!); if (factory.value === scope) { message.value = `${line.child_no} 已确认接单`; await load() } } catch (reason) { failure(reason) } finally { busy.value = false }
}
async function ship() {
  if (busy.value) return
  error.value = ''
  if (!deliveryNo.value.trim() || !deliveryDate.value || !selectedPapers.value.length) { error.value = '请填写送货单号、送货日期并勾选本次发货纸品'; return }
  if (selectedPapers.value.some(({ order, line }) => !open(order) || !line.accepted || line.shipping_blocked_reason || !(Number(quantities[line.id]) > 0) || Number(quantities[line.id]) > Number(line.remaining_to_ship))) { error.value = '勾选纸品必须先接单，发货数量须大于 0 且不超过剩余未送'; return }
  busy.value = true
  try { await api.ship({ factory_id: factory.value, delivery_note_no: deliveryNo.value.trim(), delivery_date: deliveryDate.value, lines: selectedPapers.value.map(({ order, line }) => ({ order_line_id: line.id, issue_id: order.issue_id, quantity: Number(quantities[line.id]) })) }); selected.value = []; deliveryNo.value = ''; message.value = '发货已登记，等待仓库核实实际收到；尚未计入库存。'; await load() } catch (reason) { failure(reason) } finally { busy.value = false }
}
async function download(id: string, filename: string) { try { await api.download(id, factory.value, filename) } catch (reason) { failure(reason) } }
</script>
<template>
  <main class="min-h-screen bg-slate-50 p-4 text-slate-800 md:p-8">
    <header class="mb-6 flex flex-wrap items-center justify-between gap-4"><div><h1 class="text-2xl font-bold">纸箱供应商协同</h1><p class="mt-1 text-sm text-slate-500">{{ workspace?.supplier_name }} · 按纸品子单确认交期、分批发货</p></div><div class="flex items-center gap-3"><select v-model="factory" aria-label="供应厂区" :disabled="busy" class="rounded border p-2"><option v-for="item in memberships" :key="item.factory_id" :value="item.factory_id">{{ item.factory_id }}</option></select><button :disabled="busy" class="rounded border bg-white px-3 py-2" @click="load">刷新</button><AccountMenu /></div></header>
    <p v-if="error" role="alert" class="mb-4 rounded border border-red-200 bg-red-50 p-3 text-red-700">{{ error }}</p><p v-if="message" role="status" class="mb-4 rounded bg-emerald-50 p-3 text-emerald-800">{{ message }}</p>
    <section v-if="workspace" class="space-y-5">
      <article v-for="order in workspace.orders" :key="order.id" class="overflow-hidden rounded-xl border bg-white">
        <div class="border-b p-4"><h2 class="font-bold">{{ order.customer_name }} · 合同 {{ order.contract_no }} · 货号 {{ order.item_no }}</h2><p class="mt-1 text-sm">客户 PO：{{ order.customer_po || '未填写' }} · 订单 {{ order.order_no }} · {{ order.document_no }}</p><p class="mt-1 text-sm text-slate-500">{{ order.product_name }} · 计划交期 {{ order.planned_date }}</p><p v-if="order.awaiting_issue" class="mt-2 font-semibold text-amber-700">订单有尚未发行的变更，旧承诺暂停执行；请等待新版本发行后重新确认接单。</p><p v-else-if="!open(order)" class="mt-2 text-slate-500">{{ order.status === 'COMPLETED' ? '订单已收齐' : '订单已取消' }}，不可接单或发货。</p><div class="mt-2 flex flex-wrap gap-3"><button v-for="file in order.attachments" :key="file.id" class="text-sm text-teal-700 underline" @click="download(file.id, file.filename)">{{ file.filename }} · v{{ file.version }}</button></div></div>
        <div class="overflow-x-auto"><table class="w-full min-w-[950px] text-left text-sm"><thead class="bg-slate-50"><tr><th class="p-3">本次发货</th><th class="p-3">纸品子单 / 规格</th><th class="p-3">需求 / 已入库</th><th class="p-3">在途 / 剩余未送</th><th class="p-3">承诺交期</th><th class="p-3">发货数量</th></tr></thead><tbody class="divide-y"><tr v-for="line in order.lines" :key="line.id"><td class="p-3"><input v-model="selected" :value="line.id" type="checkbox" :aria-label="`选择发货 ${line.child_no}`" :disabled="busy || !open(order) || !line.accepted || Boolean(line.shipping_blocked_reason) || Number(line.remaining_to_ship) <= 0"></td><td class="p-3"><b>{{ line.packaging_type }} · {{ line.child_no }}</b><p class="mt-1 text-slate-500">{{ line.paper_quality }} · {{ line.specification }} {{ line.dimension_unit }}</p><p v-if="line.shipping_blocked_reason" class="mt-1 text-xs text-amber-700">{{ line.shipping_blocked_reason }}</p></td><td class="p-3">{{ line.required_quantity }} / {{ line.received_quantity }} {{ line.unit }}</td><td class="p-3">{{ line.in_transit_quantity }} / {{ line.remaining_to_ship }} {{ line.unit }}</td><td class="p-3"><input v-model="dates[line.id]" type="date" :aria-label="`${line.child_no} 承诺交期`" :disabled="busy || !open(order)" class="rounded border p-2"><button :disabled="busy || !open(order) || Number(line.required_quantity) <= 0" class="ml-2 rounded border border-teal-300 px-2 py-2 text-teal-700 disabled:opacity-40" @click="accept(order, line)">{{ line.accepted ? '更新承诺' : '确认接单' }}</button><p v-if="line.promised_date && !line.accepted" class="mt-1 text-xs text-amber-700">旧交期 {{ line.promised_date }}，需重新确认</p></td><td class="p-3"><input v-model.number="quantities[line.id]" type="number" min="0.0001" step="0.0001" :max="line.remaining_to_ship" :aria-label="`${line.child_no} 发货数量`" :disabled="busy || !selected.includes(line.id)" class="w-28 rounded border p-2"></td></tr></tbody></table></div>
      </article>
      <p v-if="!workspace.orders.length" class="rounded border bg-white p-8 text-center text-slate-500">暂无已下单订单；内部确认锁定后还需发行供应商采购单。</p>
      <form class="flex flex-wrap items-end gap-4 rounded-xl border border-teal-200 bg-white p-4" @submit.prevent="ship"><label class="text-sm">送货单号<input v-model="deliveryNo" :disabled="busy" aria-label="供应商送货单号" class="mt-1 block rounded border p-2" required></label><label class="text-sm">送货日期<input v-model="deliveryDate" :disabled="busy" type="date" aria-label="供应商送货日期" class="mt-1 block rounded border p-2" required></label><button :disabled="busy || !selectedPapers.length" class="rounded bg-teal-700 px-4 py-2 font-semibold text-white disabled:opacity-40">{{ busy ? '正在保存…' : `登记 ${selectedPapers.length} 条纸品发货` }}</button></form>
      <section class="rounded-xl border bg-white p-4"><h2 class="mb-3 text-lg font-bold">发货与仓库反馈</h2><article v-for="shipment in workspace.shipments" :key="shipment.id" class="border-t py-3"><p class="font-semibold">{{ shipment.delivery_note_no }} · {{ shipment.delivery_date }} · {{ shipment.status === 'SENT' ? '待仓库确认' : shipment.status === 'NOT_RECEIVED' ? '仓库未收到，已退回' : '仓库已核实' }}</p><p v-for="line in shipment.lines" :key="line.id" class="mt-1 text-sm">{{ line.child_no }} · {{ line.packaging_type }} · 发货 {{ line.quantity }} {{ line.unit }}<template v-for="accepted in shipment.acceptance_lines.filter(item => item.shipment_line_id === line.id)" :key="accepted.shipment_line_id"> · 实收 {{ accepted.received_quantity }} · 不可用 {{ Number(accepted.damaged_quantity) + Number(accepted.rejected_quantity) + Number(accepted.unusable_quantity) }} · {{ accepted.difference_reason }}</template></p></article></section>
    </section>
  </main>
</template>
