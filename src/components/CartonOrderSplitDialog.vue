<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { DialogRoot, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { cartonOrderSplitsApi as api, type SplitContext, type SplitRecord, type SplitTargetInput } from '@/api/cartonOrderSplits'
import type { CartonOrderResponse } from '@/api/cartonProcurement'
import { getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'

const props = defineProps<{ order: CartonOrderResponse; canCreate: boolean; canConfirm: boolean }>()
const emit = defineEmits<{ close: []; changed: [] }>()
const data = ref<SplitContext | null>(null), error = ref(''), message = ref(''), busy = ref(false), loading = ref(false)
const targets = ref<SplitTargetInput[]>([]), reason = ref('按客户要求拆分合同归属'), warehouseChecked = ref<Record<string, boolean>>({})
let generation = 0
let requestId = createRandomUuid()
const stockTotal = (target: SplitTargetInput) => target.lines.reduce((sum, line) => sum + line.stock.reduce((n, part) => n + Number(part.quantity), 0), 0)
const live = computed(() => data.value?.plans.filter(plan => plan.status !== 'CANCELLED') ?? [])
function addTarget() {
  targets.value.push({ contract_no: '', customer_po: '', product_quantity: null,
    lines: (data.value?.lines ?? []).map(line => ({ order_line_id: line.order_line_id, pending_quantity: 0,
      stock: line.positions.map(position => ({ location_id: position.location_id!, expected_position_revision: position.position_revision!, quantity: 0 })) })) })
}
function calculate(target: SplitTargetInput) {
  if (props.order.quantity_basis === 'EXPLICIT') return
  target.lines.forEach((line, index) => {
    const packing = Number(data.value?.lines[index]?.usage_quantity)
    if (packing > 0 && Number(target.product_quantity) > 0) line.pending_quantity = Math.max(0,
      Math.ceil(Number(target.product_quantity) / packing) - line.stock.reduce((sum, part) => sum + Number(part.quantity), 0))
  })
}
async function load(reset = false) {
  const token = ++generation, scope = props.order.factory_id, number = props.order.order_no
  loading.value = true
  try {
    const result = await api.context(scope, number)
    if (token !== generation || scope !== props.order.factory_id || number !== props.order.order_no) return
    data.value = result
    if (reset) { targets.value = []; addTarget(); warehouseChecked.value = {}; requestId = createRandomUuid() }
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) loading.value = false }
}
watch(() => [props.order.factory_id, props.order.order_no], () => { error.value = ''; message.value = ''; void load(true) }, { immediate: true })
watch([targets, reason], () => { requestId = createRandomUuid() }, { deep: true })
async function save() {
  if (busy.value || !data.value || !props.canCreate) return
  error.value = ''; message.value = ''
  if (reason.value.trim().length < 4 || targets.value.some(target => !target.contract_no.trim())) {
    error.value = '请填写拆分合同和至少四字原因'; return
  }
  busy.value = true
  const scope = props.order.factory_id, number = props.order.order_no
  try {
    const record = await api.create(scope, number, { request_id: requestId, expected_revision: data.value.revision,
      reason: reason.value, targets: targets.value.map(target => ({ ...target, product_quantity: target.product_quantity || null,
        lines: target.lines.map(line => ({ ...line, stock: line.stock.filter(part => Number(part.quantity) > 0) })) })) })
    if (scope !== props.order.factory_id || number !== props.order.order_no) return
    message.value = record.status === 'PENDING_WAREHOUSE' ? '拆单已保存，库存归属等待仓库确认。' : '拆单已保存，后续收货按本方案核对分配。'
    emit('changed'); await load(true)
  } catch (cause) { if (scope === props.order.factory_id) error.value = getApiErrorMessage(cause) }
  finally { busy.value = false }
}
async function act(plan: SplitRecord, action: 'confirm' | 'cancel') {
  if (busy.value || reason.value.trim().length < 4 || action === 'confirm' && !warehouseChecked.value[plan.id]) return
  const scope = props.order.factory_id
  busy.value = true; error.value = ''; message.value = ''
  try {
    await api.act(scope, plan, action, reason.value)
    if (scope !== props.order.factory_id) return
    message.value = action === 'confirm' ? '仓库已确认，库存数量与金额按拆分去向转移。' : '拆单已整组撤销，原记录保留。'
    emit('changed'); await load(true)
  } catch (cause) { if (scope === props.order.factory_id) error.value = getApiErrorMessage(cause) }
  finally { busy.value = false }
}
</script>

<template>
  <DialogRoot :open="true" @update:open="open => { if (!open && !busy) emit('close') }">
    <DialogOverlay class="fixed inset-0 z-50 bg-slate-950/40" />
    <DialogContent class="fixed left-1/2 top-1/2 z-50 max-h-[92vh] w-[min(1100px,96vw)] -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-xl bg-white p-5 shadow-xl">
      <div class="flex items-start justify-between gap-3"><div><DialogTitle class="text-lg font-bold">订单拆分 · {{ order.order_no }}</DialogTitle><DialogDescription class="mt-1 text-sm text-slate-500">{{ order.customer_name }} · 原合同 {{ order.contract_no }} · 货号 {{ order.item_no }}。采购与送货保留原单，拆分记录负责数量归属。</DialogDescription></div><button type="button" :disabled="busy" aria-label="关闭拆单" class="rounded border px-3 py-1" @click="emit('close')">关闭</button></div>
      <p v-if="loading" class="my-3 text-sm">正在核对拆分与库存…</p>
      <p v-if="error" role="alert" class="my-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
      <p v-if="message" role="status" class="my-3 rounded-lg bg-teal-50 p-3 text-sm text-teal-800">{{ message }}</p>
      <p v-if="!canCreate" role="status" class="my-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">当前账号可查看拆分记录；新增拆单需要订单维护及订单调整权限，或订单维护及库存维护权限。请由有权限的仓管或主管操作。</p>
      <label class="my-4 block text-xs font-bold">操作原因<input v-model="reason" :disabled="busy" aria-label="拆单操作原因" maxlength="500" class="mt-1 h-9 w-full rounded border px-3"></label>
      <section v-if="data" class="space-y-3">
        <h3 class="font-bold">拆分记录 <span class="text-xs font-normal text-slate-500">{{ live.length }} 份有效方案</span></h3>
        <article v-for="plan in data.plans" :key="plan.id" class="rounded-lg border p-3 text-xs">
          <div class="flex flex-wrap justify-between gap-2"><strong>{{ plan.status === 'PENDING_WAREHOUSE' ? '待仓库确认' : plan.status === 'ACTIVE' ? '已生效' : '已撤销' }}</strong><span>{{ plan.created_by_name }} · {{ plan.created_at.slice(0, 10) }}</span></div>
          <div v-for="target in plan.targets" :key="target.contract_no + target.customer_po" class="mt-2"><strong>{{ target.contract_no }} · PO {{ target.customer_po || '未填写' }} · 产品 {{ target.product_quantity ?? '未记录' }}</strong><p v-for="line in target.lines" :key="line.target_line_id" class="mt-1 text-slate-600">{{ line.packaging_type }} {{ line.specification }}：分配待到 {{ line.pending_quantity }} {{ line.unit }}，剩余待到 {{ line.pending_remaining }} {{ line.unit }}，原库存 {{ line.stock.reduce((sum, part) => sum + Number(part.quantity), 0) }} {{ line.unit }}</p></div>
          <div v-if="plan.status !== 'CANCELLED'" class="mt-3 flex flex-wrap items-center gap-3">
            <template v-if="plan.status === 'PENDING_WAREHOUSE' && canConfirm"><label><input v-model="warehouseChecked[plan.id]" type="checkbox" :disabled="busy"> 仓库已核对可用库存及去向</label><button type="button" :disabled="busy || !warehouseChecked[plan.id] || reason.trim().length < 4" class="rounded bg-teal-700 px-3 py-2 text-white disabled:opacity-40" @click="act(plan, 'confirm')">确认库存拆分</button></template>
            <button v-if="canCreate" type="button" :disabled="busy || reason.trim().length < 4" class="rounded border border-red-200 px-3 py-2 text-red-700 disabled:opacity-40" @click="act(plan, 'cancel')">撤销该拆单</button>
          </div>
        </article>
      </section>
      <form v-if="data && canCreate" class="mt-5 space-y-4 border-t pt-4" @submit.prevent="save">
        <div class="flex justify-between"><h3 class="font-bold">新增拆分去向</h3><button type="button" :disabled="busy || targets.length >= 20" class="text-sm text-teal-700" @click="addTarget">＋增加合同／PO</button></div>
        <p class="text-xs text-slate-500">已领用部分不能拆。每条纸品的待到与库存数量合计应等于拆分需求；装箱取整增加需求须另行补充采购。分配按方案保存顺序、以合格实收量逐次完成。</p>
        <fieldset v-for="(target, index) in targets" :key="index" :disabled="busy" class="space-y-3 rounded-lg border bg-slate-50 p-3">
          <div class="grid items-end gap-3 sm:grid-cols-4"><label class="text-xs">拆分合同 *<input v-model="target.contract_no" required :aria-label="`拆分 ${index + 1} 合同`" class="mt-1 h-9 w-full rounded border bg-white px-2"></label><label class="text-xs">客户 PO<input v-model="target.customer_po" :aria-label="`拆分 ${index + 1} 客户 PO`" class="mt-1 h-9 w-full rounded border bg-white px-2"></label><label class="text-xs">产品数量{{ order.quantity_basis === 'EXPLICIT' ? '（可留空）' : ' *' }}<input v-model="target.product_quantity" :required="order.quantity_basis !== 'EXPLICIT'" type="number" min="0.000001" step="0.000001" :aria-label="`拆分 ${index + 1} 产品数量`" class="mt-1 h-9 w-full rounded border bg-white px-2" @input="calculate(target)"></label><button v-if="targets.length > 1" type="button" class="h-9 text-xs text-red-700" @click="targets.splice(index, 1)">移除此去向</button></div>
          <div v-for="(line, paperIndex) in target.lines" :key="line.order_line_id" class="grid gap-3 rounded border bg-white p-3 sm:grid-cols-[1.1fr_180px_1.5fr]">
            <div class="text-xs"><strong>{{ data.lines[paperIndex]?.packaging_type }} · {{ data.lines[paperIndex]?.paper_quality }}</strong><p class="mt-1">{{ data.lines[paperIndex]?.specification }}</p><p class="mt-1 text-teal-700">可分配待到 {{ data.lines[paperIndex]?.pending_available }} {{ data.lines[paperIndex]?.unit }}</p></div>
            <label class="text-xs">分配待到数量<input v-model="line.pending_quantity" required type="number" min="0" step="0.0001" :aria-label="`拆分 ${index + 1} 纸品 ${paperIndex + 1} 待到数量`" class="mt-1 h-9 w-full rounded border px-2"><span class="mt-1 block text-slate-500">{{ data.lines[paperIndex]?.unit }}<template v-if="target.product_quantity && data.lines[paperIndex]?.usage_quantity"> · 本去向需 {{ Math.ceil(Number(target.product_quantity) / Number(data.lines[paperIndex]?.usage_quantity)) }}</template></span></label>
            <div class="space-y-2 text-xs"><p class="font-semibold">拆分可用库存（待仓库确认）</p><label v-for="(part, positionIndex) in line.stock" :key="part.location_id" class="flex items-center justify-between gap-2"><span>{{ data.lines[paperIndex]?.positions[positionIndex]?.latest_location }} · 可用 {{ data.lines[paperIndex]?.positions[positionIndex]?.balance }}</span><input v-model="part.quantity" type="number" min="0" step="0.0001" :aria-label="`拆分 ${index + 1} 纸品 ${paperIndex + 1} 仓位 ${positionIndex + 1} 库存数量`" class="h-8 w-24 rounded border px-2" @input="calculate(target)"></label><p v-if="!line.stock.length" class="text-slate-400">暂无可用库存</p></div>
          </div>
        </fieldset>
        <div class="flex justify-end"><button :disabled="busy || loading" class="rounded-lg bg-teal-700 px-5 py-2 text-sm font-bold text-white disabled:opacity-40">{{ busy ? '正在保存…' : targets.some(target => stockTotal(target) > 0) ? '保存拆单，交仓库确认' : '保存待到拆分' }}</button></div>
      </form>
    </DialogContent>
  </DialogRoot>
</template>
