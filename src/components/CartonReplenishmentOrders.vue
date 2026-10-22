<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { cartonSupplierPortalApi as api, type PortalOrder } from '@/api/cartonSupplierPortal'
import { getApiErrorMessage } from '@/lib/http'
const props = withDefaults(defineProps<{ orders: (PortalOrder & { factory_id: string })[]; canApprove: boolean; viewerKey: string; acceptedOnly?: boolean; embedded?: boolean }>(), { acceptedOnly: false, embedded: false })
const emit = defineEmits<{ changed: [] }>()
const rows = computed(() => props.orders.flatMap(order => (order.replenishment_sources || [])
  .filter(source => !props.acceptedOnly || source.lines.length > 0 && source.lines.every(line => line.accepted))
  .map(source => ({ order, source }))))
const dates = ref<Record<string, string>>({}), busy = ref(''), error = ref('')
let generation = 0
watch(() => props.viewerKey, () => { generation++; dates.value = {}; busy.value = ''; error.value = '' })
async function accept(order: PortalOrder & { factory_id: string }, source: NonNullable<PortalOrder['replenishment_sources']>[number]) {
  if (busy.value || !props.canApprove || source.lines.some(line => line.shipping_blocked_reason)) return
  const day = dates.value[source.issue_id] || source.lines[0]?.promised_date || source.planned_date
  if (!day) { error.value = '请填写本补单承诺交期。'; return }
  const token = generation; busy.value = source.issue_id; error.value = ''
  try { await api.acceptBatch(order.factory_id, source.lines.map(line => ({ order_line_id: line.id, issue_id: source.issue_id, expected_revision: line.commitment_revision, promised_date: day }))); if (token === generation) emit('changed') }
  catch (reason) { if (token === generation) error.value = getApiErrorMessage(reason) }
  finally { if (token === generation) busy.value = '' }
}
</script>
<template>
  <section v-if="rows.length" :class="embedded ? 'mt-4 min-w-0 border-t border-slate-200 pt-4' : 'mt-4 rounded-xl border border-slate-200 bg-white p-4'" :aria-label="acceptedOnly ? '已接单补单承诺交期' : '补单接单与承诺交期'">
    <component :is="embedded ? 'p' : 'h3'" class="text-sm font-semibold">{{ acceptedOnly ? '已接单补单的承诺交期' : '补单接单与承诺交期' }}</component><p class="mt-1 text-xs text-slate-500">{{ acceptedOnly ? '待接单、异议或停止通知请在上方版本回执中处理。' : '每张 B 补单独立确认；普通采购承诺保留。' }}送货时在原 Excel 核对中选择对应补单。</p>
    <p v-if="error" role="alert" class="mt-2 text-sm text-red-700">{{ error }}</p>
    <article v-for="{ order, source } in rows" :key="source.issue_id" class="mt-3 flex flex-wrap items-end gap-3 border-t pt-3 text-xs">
      <div class="min-w-0 basis-48 flex-1 break-words [overflow-wrap:anywhere]"><b>{{ source.document_no }} · {{ source.responsibility === 'SUPPLIER' ? '供应商责任 · 免费换补' : '我方责任 · 按实际收货计费' }}</b><p class="mt-1 text-slate-600">{{ source.lines.find(line => line.shipping_blocked_reason)?.shipping_blocked_reason || (source.lines.every(line => line.accepted) ? '补单已接单' : '补单待接单') }}</p><p v-for="line in source.lines" :key="line.id" class="mt-1">{{ line.packaging_type }} · {{ line.specification }} · 未送 {{ line.remaining_to_ship }} {{ line.unit }} · 承诺 {{ line.promised_date || '待确认' }}</p></div>
      <template v-if="canApprove && !source.lines.some(line => line.shipping_blocked_reason) && ['PENDING_SUPPLIER', 'PARTIALLY_RECEIVED'].includes(order.status)"><label>本补单承诺交期<input v-model="dates[source.issue_id]" type="date" :aria-label="source.document_no + ' 补单承诺交期'" :disabled="!!busy" class="mt-1 block h-9 max-w-full rounded-lg border px-2" :placeholder="source.planned_date"></label><button type="button" :disabled="!!busy" :aria-label="source.document_no + (acceptedOnly ? ' 保存补单承诺' : ' 确认补单接单')" class="h-9 rounded-lg bg-teal-700 px-3 font-semibold text-white disabled:opacity-40" @click="accept(order, source)">{{ source.lines.every(line => line.accepted) ? '保存补单承诺' : '确认补单接单' }}</button></template>
    </article>
  </section>
</template>
