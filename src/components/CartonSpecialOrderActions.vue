<script setup lang="ts">
import CartonOrderOperations from '@/components/CartonOrderOperations.vue'
import { computed } from 'vue'
import { CalendarClock, Copy, Download, Minus, Pencil, Plus, ShieldCheck, Trash2, Truck, X } from '@lucide/vue'
import type { SpecialRequest } from '@/api/cartonSpecialRequests'
import { canAdjustSpecialRequest, canAppendSpecialRequest, type SpecialOrderAction } from '@/features/carton-procurement/specialOrderActions'

const props = withDefaults(defineProps<{ request: SpecialRequest; disabled?: boolean; detail?: boolean; receiving?: boolean; canCopy?: boolean }>(), { disabled: false, canCopy: true })
const emit = defineEmits<{ action: [action?: SpecialOrderAction]; preview: []; 'close-preview': [] }>()
const permissions = computed(() => props.request.permissions)
const immutableReplacement = computed(() => props.request.origin === 'REPLENISHMENT' || Boolean(props.request.replacement))
const canConfirm = computed(() => !immutableReplacement.value && !props.request.deleted && props.request.status === 'SUBMITTED' && (permissions.value.can_confirm || permissions.value.can_send))
const canReceive = computed(() => !props.request.deleted && (permissions.value.can_manual_receive || permissions.value.can_receive)
  && ['SENT', 'QUOTED', 'READY', 'PARTIALLY_RECEIVED'].includes(props.request.status)
  && props.request.lines.some(line => Number(line.quantity) > Number(line.received_quantity || 0)))
const canEdit = computed(() => !immutableReplacement.value && !props.request.deleted && props.request.status === 'SUBMITTED' && permissions.value.can_edit)
const canAdjust = computed(() => canAdjustSpecialRequest(props.request))
const canAppend = computed(() => canAppendSpecialRequest(props.request))
const canReduce = computed(() => canAdjust.value && props.request.lines.some(line => Number(line.quantity) > Number(line.received_quantity || 0)))
const canChangeMaterial = computed(() => canAdjust.value && props.request.lines.some(line => !props.request.shipments?.some(shipment => shipment.lines.some(paper => paper.request_line_id === line.id))))
const canCancel = computed(() => !immutableReplacement.value && !props.request.deleted && !['COMPLETED', 'CANCELLED'].includes(props.request.status) && permissions.value.can_cancel)
</script>

<template>
  <div class="grid w-full items-center gap-1" :class="receiving ? 'grid-cols-[5.5rem_2.5rem]' : 'grid-cols-[7.25rem_3.25rem_2.5rem]'" :aria-label="`${request.request_no} 操作`">
    <button v-if="canConfirm" type="button" :disabled="disabled" class="inline-flex h-8 items-center justify-center gap-1 whitespace-nowrap rounded-md bg-teal-700 px-2 text-[10px] font-bold text-white hover:bg-teal-800 disabled:opacity-40" @click="emit('action', 'confirm')"><ShieldCheck class="size-3.5" />确认并锁单</button>
    <button v-else-if="canReceive" type="button" :disabled="disabled" :aria-label="`登记 ${request.request_no} 收料`" class="inline-flex h-8 items-center justify-center gap-1 whitespace-nowrap rounded-md bg-teal-700 px-2 text-[10px] font-bold text-white hover:bg-teal-800 disabled:opacity-40" @click="emit('action', 'receive')"><Truck class="size-3.5" />登记收料</button>
    <button v-else type="button" :disabled="disabled" :aria-label="`管理 ${request.request_no} 采购单`" class="inline-flex h-8 items-center justify-center gap-1 whitespace-nowrap rounded-md bg-teal-700 px-2 text-[10px] font-bold text-white disabled:opacity-40" @click="emit('action', 'purchase')"><Download class="size-3.5" />采购单</button>
    <CartonOrderOperations v-if="!receiving" :order-no="request.request_no" :disabled="disabled" class="col-start-2 row-start-1" :actions="[
{ key: 'purchase', run: () => emit('action', 'purchase') },
{ key: 'material', visible: canChangeMaterial, disabled: disabled, run: () => { emit('action', 'material') } },
{ key: 'edit', visible: canEdit, disabled: disabled, run: () => { emit('action', 'edit') } },
{ key: 'copy', visible: canCopy, disabled: disabled, run: () => { emit('action', 'copy') } },
{ key: 'date', visible: canAdjust, disabled: disabled, run: () => { emit('action', 'date') } },
{ key: 'replenish', visible: !request.deleted && permissions.can_replenish, disabled: disabled, run: () => { emit('action', 'replenish') } },
{ key: 'append', visible: canAppend, disabled: disabled, run: () => { emit('action', 'append') } },
{ key: 'reduce', visible: canReduce, disabled: disabled, run: () => { emit('action', 'reduce') } },
{ key: 'adjust', visible: canAdjust, disabled: disabled, run: () => { emit('action', 'adjust') } },
{ key: 'return-stock', visible: !request.deleted && permissions.can_return_stock, disabled: disabled, run: () => { emit('action', 'return-stock') } },
{ key: 'undo-replenish', visible: immutableReplacement && !request.deleted && permissions.can_undo_replenish, disabled: disabled, run: () => { emit('action', 'undo-replenish') } },
{ key: 'cancel', visible: canCancel, disabled: disabled, run: () => { emit('action', 'cancel') } },
{ key: 'delete', visible: !immutableReplacement && !request.deleted && permissions.can_delete, disabled: disabled, run: () => { emit('action', 'delete') } }
]" />
    <button v-if="!detail" type="button" :disabled="disabled" :aria-label="`查看订单 ${request.request_no} 明细`" title="悬停预览完整明细，单击后保持显示" class="row-start-1 inline-flex h-8 items-center justify-center rounded-md border border-slate-200 bg-white text-[10px] font-bold text-slate-600 hover:border-teal-300 hover:bg-teal-50 hover:text-teal-700 disabled:opacity-40" :class="receiving ? 'col-start-2' : 'col-start-3'" @mouseenter="!disabled && emit('preview')" @mouseleave="emit('close-preview')" @focus="!disabled && emit('preview')" @blur="emit('close-preview')" @click="emit('action')">明细</button>
  </div>
</template>
