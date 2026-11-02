<script setup lang="ts">
import { ref, watch } from 'vue'
import { DialogRoot, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { cartonOrderSplitsApi as api, type SplitRecord } from '@/api/cartonOrderSplits'
import { cartonOrderDivisionsApi, type DivisionContext, type OrderDivision } from '@/api/cartonOrderDivisions'
import { cartonPrintSplitsApi, printStatus, type PrintPlan } from '@/api/cartonPrintSplits'
import { createRandomUuid } from '@/lib/randomUuid'
import type { CartonOrderResponse } from '@/api/cartonProcurement'
import { getApiErrorMessage } from '@/lib/http'
import CartonIndependentSplitPanel from './CartonIndependentSplitPanel.vue'
const props = defineProps<{ order: CartonOrderResponse; canCreate: boolean; canConfirm: boolean }>()
const emit = defineEmits<{ close: []; changed: []; completed: [OrderDivision] }>()
const returnFocus = Array.from(document.querySelectorAll<HTMLButtonElement>('button[aria-label]'))
  .find(button => button.getAttribute('aria-label') === `更多 ${props.order.order_no} 订单操作`)
  ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null)
function restoreFocus(event: Event) {
  event.preventDefault()
  if (returnFocus?.isConnected) returnFocus.focus()
}
const data = ref<DivisionContext>(), error = ref(''), busy = ref(false), loading = ref(false)
let generation = 0
async function load() {
  const token = ++generation
  loading.value = true
  try { const value = await cartonOrderDivisionsApi.context(props.order.factory_id, props.order.order_no); if (token === generation) data.value = value }
  catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) loading.value = false }
}
watch(() => [props.order.factory_id, props.order.order_no], () => { data.value = undefined; error.value = ''; void load() }, { immediate: true })
async function cancel(plan: SplitRecord) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { await api.act(props.order.factory_id, plan, 'cancel', '撤销旧数量归属方案，保留历史记录'); emit('changed'); await load() }
  catch (cause) { error.value = getApiErrorMessage(cause) }
  finally { busy.value = false }
}
const withdrawalRequests = new Map<string, string>()
async function withdraw(plan: PrintPlan) {
  if (busy.value) return
  busy.value = true; error.value = ''
  const key = `${plan.id}:${plan.revision}`
  if (!withdrawalRequests.has(key)) withdrawalRequests.set(key, createRandomUuid())
  try { await cartonPrintSplitsApi.act(plan, 'withdraw', withdrawalRequests.get(key)!, '撤回旧提案，改用普通独立订单拆分'); emit('changed'); await load() }
  catch (cause) { error.value = getApiErrorMessage(cause) }
  finally { busy.value = false }
}
</script>
<template>
  <DialogRoot :open="true" @update:open="open => { if (!open && !busy) emit('close') }">
    <DialogOverlay class="fixed inset-0 z-50 bg-slate-950/40" />
    <DialogContent class="fixed left-1/2 top-1/2 z-50 flex max-h-[92dvh] w-[min(900px,96vw)] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-xl bg-white p-4 shadow-xl sm:p-5" @close-auto-focus="restoreFocus" @interact-outside="event => { if (busy) event.preventDefault() }" @escape-key-down="event => { if (busy) event.preventDefault() }">
      <div class="flex items-start justify-between gap-3"><div><DialogTitle class="text-lg font-bold">订单拆分 · {{ order.order_no }}</DialogTitle><DialogDescription class="mt-1 text-sm text-slate-500">{{ order.customer_name }} · 原合同 {{ order.contract_no }} · 货号 {{ order.item_no }}。原单扣减，子单独立送货、收料及库存核算。</DialogDescription></div><button type="button" :disabled="busy" aria-label="关闭拆单" class="shrink-0 whitespace-nowrap rounded border px-3 py-1" @click="emit('close')">关闭</button></div>
      <div class="mt-4 min-h-0 overflow-y-auto">
      <p v-if="loading" role="status" class="my-3 text-sm">正在核对拆分记录…</p>
      <p v-if="error" role="alert" class="my-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
      <p v-if="!canCreate" role="status" class="my-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">当前账号可查看记录；拆单需要订单维护权限和对应客户操作授权。已发送订单还需要订单调整或库存维护权限。</p>
      <button v-if="error && !data" type="button" class="mb-3 rounded-lg border px-3 py-2 text-sm" @click="load">重新读取</button>
      <CartonIndependentSplitPanel v-if="data && !loading" :order="order" :context="data" :can-create="canCreate" @busy="busy = $event" @completed="emit('completed', $event)" />
      <p v-if="data?.order_split?.source_order_no" class="mt-4 text-sm text-slate-600">本单来源：{{ data.order_split.source_contract_no }}（{{ data.order_split.source_order_no }}）</p>
      <details v-if="data?.order_split?.children.length" class="mt-4 rounded-lg border p-3 text-sm"><summary class="cursor-pointer font-semibold">已拆出的独立订单</summary><p v-for="child in data.order_split.children" :key="child.order_id" class="mt-2">{{ child.contract_no }} · {{ child.order_no }}</p></details>
      <article v-for="plan in data?.previous_proposals" :key="plan.id" class="mt-4 space-y-2 rounded-lg border border-amber-200 p-3 text-sm"><strong>此前拆单提案 · {{ printStatus[plan.status] }}</strong><p>{{ plan.contract_no }} → {{ plan.targets.map(t => t.contract_no).join('、') }}</p><p v-if="plan.status === 'WITHDRAWING'">已请求撤回，等待供应商在原待办确认收到。</p><button v-if="canCreate && ['DRAFT','SENT','DISPUTED'].includes(plan.status)" type="button" :disabled="busy" class="rounded-lg border px-3 py-2" @click="withdraw(plan)">{{ plan.status === 'DRAFT' ? '撤销旧草稿' : '请求撤回旧提案' }}</button></article>
      <details v-if="data?.plans.length" class="mt-4 rounded-lg border p-3 text-sm"><summary class="cursor-pointer font-semibold">旧数量分配记录 · {{ data.plans.length }} 份</summary><article v-for="plan in data.plans" :key="plan.id" class="mt-3 border-t pt-3"><p>{{ plan.status === 'CANCELLED' ? '已归档 / 撤销' : '待转为独立订单' }} · {{ plan.targets.map(t => t.contract_no).join('、') }}</p><p class="mt-1 text-xs text-slate-500">{{ plan.created_by_name }} · {{ plan.created_at.slice(0,10) }} · {{ plan.reason }}</p><button v-if="canCreate && plan.status !== 'CANCELLED'" type="button" :disabled="busy" class="mt-2 rounded border border-red-200 px-3 py-2 text-xs text-red-700" @click="cancel(plan)">撤销旧方案</button></article></details>
      </div>
    </DialogContent>
  </DialogRoot>
</template>
