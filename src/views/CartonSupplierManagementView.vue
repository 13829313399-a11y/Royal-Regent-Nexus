<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { cartonSupplierPortalApi as api, type PortalWorkspace, type PortalShipment, type ReceiveLine, type SupplierMember } from '@/api/cartonSupplierPortal'
import { cartonPositionsApi, type CartonLocation } from '@/api/cartonPositions'
import CartonReceiptAllocations from '@/components/CartonReceiptAllocations.vue'
const route = useRoute(); const app = useAppStore(); const auth = useAuthStore()
const factory = computed(() => String(route.query.factory || app.activeProductionFactory.id))
const data = ref<PortalWorkspace | null>(null); const locations = ref<CartonLocation[]>([]); const members = ref<SupplierMember[]>([])
const error = ref(''); const message = ref(''); const busy = ref(false); const loading = ref(false)
const active = ref<PortalShipment | null>(null); const received = ref<ReceiveLine[]>([])
const acceptanceDate = ref(new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' }))
const memberForm = reactive({ username: '', expected_revision: 0, status: 'ACTIVE' as 'ACTIVE' | 'INACTIVE', reason: '' })
const can = (permission: string) => ['carton', 'pmc-warehouse'].some(department => auth.can(permission, factory.value, department))
const canReceive = computed(() => can('carton_procurement:receipt_write') && can('carton_procurement:inventory_write'))
const canAttach = computed(() => can('carton_procurement:order_write'))
const canManage = computed(() => can('carton_procurement:master_manage') && can('carton_procurement:order_adjust'))
const canOpenExternal = computed(() => (auth.grants ?? []).some(grant =>
  (grant.role_code === 'admin' || grant.role_id === 'admin')
  && grant.factory_id === '*' && ['*', 'system'].includes(grant.department)))
let generation = 0
function failure(reason: unknown) { error.value = reason instanceof Error ? reason.message : '操作未完成，请核对后重试' }
async function load() {
  const token = ++generation, scope = factory.value; loading.value = true
  try {
    const [workspace, bins] = await Promise.all([api.workspace(scope, true), canReceive.value ? cartonPositionsApi.locations(scope) : Promise.resolve([])])
    if (token !== generation || scope !== factory.value) return
    data.value = workspace; locations.value = bins
    if (canManage.value) { const items = await api.members(scope); if (token === generation) members.value = items }
  } catch (reason) { if (token === generation) failure(reason) } finally { if (token === generation) loading.value = false }
}
onMounted(load)
watch(factory, () => { active.value = null; data.value = null; members.value = []; received.value = []; error.value = ''; message.value = ''; memberForm.username = ''; memberForm.expected_revision = 0; void load() })
function start(shipment: PortalShipment) {
  active.value = shipment; error.value = ''
  received.value = shipment.lines.map(line => ({ shipment_line_id: line.id, received_quantity: 0, damaged_quantity: 0, rejected_quantity: 0, unusable_quantity: 0, unit_price: Number(line.unit_price || 0), paper_quality: line.paper_quality, specification: line.specification, location_allocations: [], difference_reason: '' }))
}
const effective = (line: ReceiveLine) => Math.max(0, Number(line.received_quantity) - Number(line.damaged_quantity) - Number(line.rejected_quantity) - Number(line.unusable_quantity))
async function confirm() {
  if (!active.value || busy.value) return
  for (const line of received.value) {
    const quantity = effective(line)
    if (quantity <= 0) continue
    const allocations = line.location_allocations
    if (!allocations.length || allocations.some(part => !locations.value.some(location => location.id === part.location_id && location.status === 'ACTIVE') || !Number.isFinite(Number(part.quantity)) || Number(part.quantity) <= 0)) {
      error.value = '每条有效入库纸品必须选择有效仓位并填写分仓数量'; return
    }
    if (new Set(allocations.map(part => part.location_id)).size !== allocations.length || allocations.some(part => Math.abs(Number(part.quantity) * 10000 - Math.round(Number(part.quantity) * 10000)) > 0.000001) || Math.abs(allocations.reduce((sum, part) => sum + Number(part.quantity), 0) - quantity) > 0.000001) {
      error.value = '仓位不能重复，分仓数量最多四位小数，合计必须等于该纸品有效入库数量'; return
    }
  }
  busy.value = true; error.value = ''; const scope = factory.value, shipment = active.value
  try { await api.receive(shipment.id, { factory_id: scope, expected_revision: shipment.revision, acceptance_date: acceptanceDate.value, lines: received.value }); if (factory.value === scope) { active.value = null; received.value = []; message.value = '仓库核实已保存；有效实收已入库，未收到的纸品保留原待收需求。'; await load() } } catch (reason) { if (scope === factory.value) failure(reason) } finally { busy.value = false }
}
async function upload(orderId: string, event: Event) {
  const input = event.target as HTMLInputElement, file = input.files?.[0]
  if (!file || busy.value) return
  if (file.size > 10 * 1024 * 1024) { error.value = '单文件最多 10 MB'; input.value = ''; return }
  busy.value = true; error.value = ''; const scope = factory.value
  try { await api.upload(orderId, scope, file); if (scope === factory.value) { message.value = '附件已绑定订单；旧版本继续保留。'; await load() } } catch (reason) { failure(reason) } finally { busy.value = false; input.value = '' }
}
async function download(id: string, filename: string) { try { await api.download(id, factory.value, filename, true) } catch (reason) { failure(reason) } }
function editMember(member: SupplierMember) { memberForm.username = member.username; memberForm.expected_revision = member.revision; memberForm.status = member.status; memberForm.reason = '' }
async function saveMember() {
  if (busy.value) return
  busy.value = true; error.value = ''; const scope = factory.value
  try { const result = await api.member({ ...memberForm, factory_id: scope }); if (scope === factory.value) { members.value = result; memberForm.username = ''; memberForm.expected_revision = 0; memberForm.reason = ''; message.value = '供应商外部账号授权已更新。' } } catch (reason) { failure(reason) } finally { busy.value = false }
}
</script>
<template>
  <main class="min-h-screen bg-slate-50 p-4 text-slate-800 md:p-8">
    <header class="mb-6 flex flex-wrap items-center justify-between gap-3"><div><h1 class="text-2xl font-bold">供应商协同管理</h1><p class="mt-1 text-sm text-slate-500">{{ factory }} · {{ data?.supplier_name }} · 发货待收、订单附件与成员授权</p></div><div class="flex gap-3"><RouterLink :to="{ path: '/modules/pmc-warehouse/carton-procurement', query: { factory, tab: 'receipts' } }" class="rounded border bg-white p-2">返回纸箱协同</RouterLink><button :disabled="busy || loading" class="rounded border bg-white p-2" @click="load">刷新</button></div></header>
    <p v-if="error" role="alert" class="mb-4 rounded bg-red-50 p-3 text-red-700">{{ error }}</p><p v-if="message" role="status" class="mb-4 rounded bg-emerald-50 p-3 text-emerald-800">{{ message }}</p>
    <section class="mb-6 rounded-xl border bg-white p-4"><h2 class="mb-3 text-lg font-bold">供应商发货待收</h2><p class="mb-3 text-sm text-slate-500">供应商登记发货不会增加库存。仓库核对整张送货单的实际数量、差异、单价及仓位后一次入库。</p><article v-for="shipment in data?.shipments" :key="shipment.id" class="border-t py-3"><div class="flex justify-between gap-3"><strong>{{ shipment.delivery_note_no }} · {{ shipment.delivery_date }}</strong><button v-if="shipment.status === 'SENT' && canReceive" :disabled="busy" class="rounded bg-teal-700 px-3 py-2 text-sm text-white" @click="start(shipment)">核实实际收到</button><span v-else class="text-sm">{{ shipment.status === 'SENT' ? '等待仓库确认' : shipment.status === 'NOT_RECEIVED' ? '未收到，已退回' : '已核实入库' }} {{ shipment.receipt_status === 'REVERSED' ? '（收料已冲销）' : '' }}</span></div><p v-for="line in shipment.lines" :key="line.id" class="mt-1 text-sm">{{ line.customer_name }} · {{ line.contract_no }} · 客户 PO {{ line.customer_po || '未填写' }} · {{ line.item_no }} · {{ line.child_no }} · {{ line.packaging_type }} {{ line.specification }} · 发货 {{ line.quantity }} {{ line.unit }}</p></article><p v-if="data && !data.shipments.length" class="py-5 text-slate-500">暂无供应商发货单</p></section>
    <section class="mb-6 rounded-xl border bg-white p-4"><h2 class="mb-3 text-lg font-bold">订单资料 / PDF</h2><p class="mb-2 text-sm text-slate-500">仅支持 PDF、DOCX、XLSX、PPTX，单文件不超过 10 MB；相同文件名的新内容保留为新版本。附件仅供对应供应商已下单订单下载。</p><article v-for="order in data?.orders" :key="order.id" class="border-t py-3"><p class="font-semibold">{{ order.customer_name }} · {{ order.contract_no }} · PO {{ order.customer_po || '未填写' }} · {{ order.item_no }} · {{ order.order_no }}</p><div class="my-2 flex flex-wrap gap-3"><button v-for="file in order.attachments" :key="file.id" class="text-sm text-teal-700 underline" @click="download(file.id, file.filename)">{{ file.filename }} · v{{ file.version }}</button></div><input v-if="canAttach && order.status !== 'CANCELLED'" :aria-label="`${order.order_no} 上传资料`" :disabled="busy" type="file" accept=".pdf,.docx,.xlsx,.pptx" class="text-sm" @change="upload(order.id, $event)"></article></section>
    <section v-if="canManage" class="rounded-xl border bg-white p-4"><h2 class="mb-3 text-lg font-bold">供应商外部账号授权</h2><p class="mb-3 text-sm text-slate-500">按准确登录名开通东康供应商账号后，可自动查看同一供应商已下单的服务厂区；账号不属于内部厂区，也不获得内部订单、库存或月结权限。账号须先由受控开通流程建立，跨厂区开通仅系统管理员可操作。</p><div v-for="member in members" :key="member.id" class="flex items-center justify-between border-t py-2"><span>{{ member.display_name }}（{{ member.username }}）· {{ member.status === 'ACTIVE' ? '已开通' : '已停用' }}</span><button :disabled="busy" class="rounded border px-3 py-1" @click="editMember(member)">维护绑定</button></div><form class="mt-4 flex flex-wrap items-end gap-3" @submit.prevent="saveMember"><label class="text-sm">准确登录名<input v-model="memberForm.username" :disabled="busy || memberForm.expected_revision > 0" aria-label="绑定供应商登录名" required class="mt-1 block rounded border p-2"></label><label class="text-sm">状态<select v-model="memberForm.status" :disabled="busy" aria-label="供应商绑定状态" class="mt-1 block rounded border p-2"><option value="ACTIVE" :disabled="!canOpenExternal">开通</option><option value="INACTIVE">停用</option></select></label><label class="text-sm">授权 / 停用原因<input v-model="memberForm.reason" :disabled="busy" aria-label="供应商绑定原因" required minlength="4" class="mt-1 block rounded border p-2"></label><button :disabled="busy || (memberForm.status === 'ACTIVE' && !canOpenExternal)" class="rounded bg-teal-700 px-4 py-2 text-white">保存授权</button><button type="button" :disabled="busy" class="rounded border px-3 py-2" @click="memberForm.username = ''; memberForm.expected_revision = 0; memberForm.reason = ''">清空</button></form></section>
    <div v-if="active" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-3"><form role="dialog" aria-modal="true" aria-label="核实供应商实际送货" class="max-h-[94vh] w-full max-w-6xl overflow-auto rounded-xl bg-white p-5" @submit.prevent="confirm"><h2 class="text-lg font-bold">核实送货单 {{ active.delivery_note_no }}</h2><p class="my-2 text-sm text-amber-800">按整张送货单逐项确认。未实际收到请填 0 并说明；短收或不可用部分继续保留原订单待收需求，后续可重新发货。</p><label class="block text-sm">实际验收日期<input v-model="acceptanceDate" :disabled="busy" type="date" required aria-label="发货验收日期" class="ml-2 rounded border p-2"></label><article v-for="(row, index) in received" :key="row.shipment_line_id" class="mt-4 rounded-lg border p-3"><h3 class="font-semibold">{{ active.lines[index]?.child_no }} · {{ active.lines[index]?.contract_no }} · PO {{ active.lines[index]?.customer_po || '未填写' }} · {{ active.lines[index]?.item_no }} · {{ active.lines[index]?.packaging_type }} · 发货 {{ active.lines[index]?.quantity }} {{ active.lines[index]?.unit }}</h3><div class="mt-3 grid gap-3 sm:grid-cols-4"><label class="text-sm">实际收到<input v-model.number="row.received_quantity" :aria-label="`${row.shipment_line_id} 实收`" :disabled="busy" type="number" min="0" step="0.0001" :max="active.lines[index]?.quantity" required class="mt-1 w-full rounded border p-2"></label><label class="text-sm">破损<input v-model.number="row.damaged_quantity" :disabled="busy" type="number" min="0" step="0.0001" class="mt-1 w-full rounded border p-2"></label><label class="text-sm">拒收<input v-model.number="row.rejected_quantity" :disabled="busy" type="number" min="0" step="0.0001" class="mt-1 w-full rounded border p-2"></label><label class="text-sm">其他不可用<input v-model.number="row.unusable_quantity" :disabled="busy" type="number" min="0" step="0.0001" class="mt-1 w-full rounded border p-2"></label><label class="text-sm">入库单价 {{ active.lines[index]?.currency }}<input v-model.number="row.unit_price" :disabled="busy" type="number" min="0" step="0.000001" required class="mt-1 w-full rounded border p-2"></label><label class="text-sm">纸质<input v-model="row.paper_quality" :disabled="busy || Boolean(active.lines[index]?.paper_quality)" class="mt-1 w-full rounded border p-2"></label><label class="text-sm">规格<input v-model="row.specification" :disabled="busy || Boolean(active.lines[index]?.specification)" class="mt-1 w-full rounded border p-2"></label><label class="text-sm">差异原因<input v-model="row.difference_reason" :disabled="busy" :required="effective(row) !== Number(active.lines[index]?.quantity)" :aria-label="`${row.shipment_line_id} 差异原因`" class="mt-1 w-full rounded border p-2"></label></div><p class="my-2 font-semibold text-teal-700">有效入库 {{ effective(row) }} {{ active.lines[index]?.unit }}</p><CartonReceiptAllocations v-model="row.location_allocations" :effective="effective(row)" :locations="locations" :factory-id="factory" :disabled="busy" @created="load" /></article><p v-if="error" role="alert" class="my-3 text-red-700">{{ error }}</p><div class="mt-4 flex justify-end gap-3"><button type="button" :disabled="busy" class="rounded border px-4 py-2" @click="active = null">取消</button><button :disabled="busy" class="rounded bg-teal-700 px-4 py-2 text-white">{{ busy ? '正在保存…' : received.every(row => Number(row.received_quantity) === 0) ? '确认整单未收到并退回' : '确认实际收料并入库' }}</button></div></form></div>
  </main>
</template>
