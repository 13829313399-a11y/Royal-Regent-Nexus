<script setup lang="ts">
import { CalendarClock, Copy, Download, GitBranch, Minus, Pencil, Plus, Trash2, Truck, X, Zap } from '@lucide/vue'
import CartonOrderMoreMenu from './CartonOrderMoreMenu.vue'
import CartonOrderMenuItem from './CartonOrderMenuItem.vue'
type ActionKey = 'material' | 'correction' | 'edit' | 'merge' | 'copy' | 'split' | 'rush' | 'purchase' | 'date' | 'replenish' | 'append' | 'reduce' | 'adjust' | 'return-stock' | 'undo-replenish' | 'cancel' | 'delete'
defineProps<{ orderNo: string; disabled?: boolean; actions: { key: ActionKey; visible?: boolean; disabled?: boolean; label?: string; aria?: string; hint?: string; run: () => void }[] }>()
const opened = defineModel<boolean>('open', { default: false })
const config = {
  material: { label: '修改未送货纸品', icon: Pencil, tone: 'amber' }, correction: { label: '调整订单信息', icon: Pencil, tone: 'correction' },
  edit: { label: '修改订单', icon: Pencil, tone: 'neutral' }, merge: { label: '合单 · 新建合同', icon: GitBranch, tone: 'teal' },
  copy: { label: '复制订单信息', icon: Copy, tone: 'teal' }, split: { label: '拆单 / 拆分记录', icon: GitBranch, tone: 'teal' },
  rush: { label: '急单标记', icon: Zap, tone: 'danger' },
  purchase: { label: '采购单', icon: Download, tone: 'teal' }, date: { label: '调整交期', icon: CalendarClock, tone: 'blue' },
  replenish: { label: '补单（原数量不变）', icon: Plus, tone: 'teal' }, append: { label: '追加订单', icon: Plus, tone: 'amber' },
  reduce: { label: '减少未入库量', icon: Minus, tone: 'danger' }, adjust: { label: '调整订单', icon: Pencil, tone: 'neutral' },
  'return-stock': { label: '退货', icon: Truck, tone: 'danger' }, 'undo-replenish': { label: '撤销未发货补单', icon: X, tone: 'danger' },
  cancel: { label: '取消订单', icon: X, tone: 'danger' }, delete: { label: '删除订单', icon: Trash2, tone: 'danger' },
} as const
</script>
<template>
  <CartonOrderMoreMenu :order-no="orderNo" :disabled="disabled" v-model:open="opened">
    <template v-for="action in actions" :key="action.key"><CartonOrderMenuItem v-if="!('visible' in action) || action.visible" :disabled="disabled || action.disabled" :tone="config[action.key].tone" :aria-label="action.aria" :title="action.hint" @select="action.run()"><component :is="config[action.key].icon" class="size-3.5" />{{ action.label || config[action.key].label }}</CartonOrderMenuItem></template>
  </CartonOrderMoreMenu>
</template>
