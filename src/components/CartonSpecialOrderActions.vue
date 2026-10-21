<script setup lang="ts">
import { computed } from 'vue'
import { DropdownMenuRoot, DropdownMenuTrigger, DropdownMenuPortal, DropdownMenuContent, DropdownMenuItem } from 'reka-ui'
import { ChevronDown, Pencil, ShieldCheck, Trash2, Truck, X } from '@lucide/vue'
import type { SpecialRequest } from '@/api/cartonSpecialRequests'

const props = withDefaults(defineProps<{ request: SpecialRequest; disabled?: boolean; detail?: boolean; receiving?: boolean }>(), { disabled: false })
const emit = defineEmits<{ action: [action?: 'receive' | 'edit' | 'adjust' | 'confirm' | 'cancel' | 'delete']; preview: []; 'close-preview': [] }>()
const permissions = computed(() => props.request.permissions)
const canConfirm = computed(() => props.request.status === 'SUBMITTED' && (permissions.value.can_confirm || permissions.value.can_send))
const canReceive = computed(() => (permissions.value.can_manual_receive || permissions.value.can_receive)
  && ['SENT', 'QUOTED', 'READY', 'PARTIALLY_RECEIVED'].includes(props.request.status)
  && props.request.lines.some(line => Number(line.quantity) > Number(line.received_quantity || 0)))
const hasMore = computed(() => permissions.value.can_edit || permissions.value.can_adjust || permissions.value.can_cancel || permissions.value.can_delete)
</script>

<template>
  <div class="grid w-full items-center gap-1" :class="receiving ? 'grid-cols-[5.5rem_2.5rem]' : 'grid-cols-[7.25rem_3.25rem_2.5rem]'" :aria-label="`${request.request_no} 操作`">
    <button v-if="canConfirm" type="button" :disabled="disabled" class="inline-flex h-8 items-center justify-center gap-1 whitespace-nowrap rounded-md bg-teal-700 px-2 text-[10px] font-bold text-white hover:bg-teal-800 disabled:opacity-40" @click="emit('action', 'confirm')"><ShieldCheck class="size-3.5" />确认并锁单</button>
    <button v-else-if="canReceive" type="button" :disabled="disabled" :aria-label="`登记 ${request.request_no} 收料`" class="inline-flex h-8 items-center justify-center gap-1 whitespace-nowrap rounded-md bg-teal-700 px-2 text-[10px] font-bold text-white hover:bg-teal-800 disabled:opacity-40" @click="emit('action', 'receive')"><Truck class="size-3.5" />登记收料</button>
    <DropdownMenuRoot v-if="hasMore && !receiving">
      <DropdownMenuTrigger :disabled="disabled" :aria-label="`更多 ${request.request_no} 订单操作`" class="col-start-2 row-start-1 inline-flex h-8 items-center justify-center gap-1 rounded-md border border-slate-200 bg-white px-1 text-[10px] font-bold text-slate-600 hover:bg-slate-100 disabled:opacity-40">更多<ChevronDown class="size-2.5" /></DropdownMenuTrigger>
      <DropdownMenuPortal><DropdownMenuContent align="end" :side-offset="4" class="z-[75] min-w-40 rounded-lg border border-slate-200 bg-white p-1 shadow-xl">
        <DropdownMenuItem v-if="permissions.can_edit" class="flex cursor-pointer items-center gap-2 rounded px-3 py-2 text-xs font-semibold text-slate-700 outline-none data-[highlighted]:bg-slate-50" @select="emit('action', 'edit')"><Pencil class="size-3.5" />修改订单</DropdownMenuItem>
        <DropdownMenuItem v-if="permissions.can_adjust" class="flex cursor-pointer items-center gap-2 rounded px-3 py-2 text-xs font-semibold text-slate-700 outline-none data-[highlighted]:bg-slate-50" @select="emit('action', 'adjust')"><Pencil class="size-3.5" />调整订单</DropdownMenuItem>
        <DropdownMenuItem v-if="permissions.can_cancel" class="flex cursor-pointer items-center gap-2 rounded px-3 py-2 text-xs font-semibold text-red-700 outline-none data-[highlighted]:bg-red-50" @select="emit('action', 'cancel')"><X class="size-3.5" />取消订单</DropdownMenuItem>
        <DropdownMenuItem v-if="permissions.can_delete" class="flex cursor-pointer items-center gap-2 rounded px-3 py-2 text-xs font-semibold text-red-700 outline-none data-[highlighted]:bg-red-50" @select="emit('action', 'delete')"><Trash2 class="size-3.5" />删除订单</DropdownMenuItem>
      </DropdownMenuContent></DropdownMenuPortal>
    </DropdownMenuRoot>
    <button v-if="!detail" type="button" :disabled="disabled" :aria-label="`查看订单 ${request.request_no} 明细`" title="悬停预览完整明细，单击后保持显示" class="row-start-1 inline-flex h-8 items-center justify-center rounded-md border border-slate-200 bg-white text-[10px] font-bold text-slate-600 hover:border-teal-300 hover:bg-teal-50 hover:text-teal-700 disabled:opacity-40" :class="receiving ? 'col-start-2' : 'col-start-3'" @mouseenter="!disabled && emit('preview')" @mouseleave="emit('close-preview')" @focus="!disabled && emit('preview')" @blur="emit('close-preview')" @click="emit('action')">明细</button>
  </div>
</template>
