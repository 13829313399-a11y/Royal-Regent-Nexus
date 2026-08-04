<script setup lang="ts">
import { ChevronDown, ChevronUp, PackageOpen, ShieldQuestion } from '@lucide/vue'
import type { MoldRecord, OrderRecord } from '../types'

const props = defineProps<{ orders: OrderRecord[]; molds: MoldRecord[]; open: boolean }>()
const emit = defineEmits<{ toggle: []; view: [orderId: string] }>()
const number = new Intl.NumberFormat('zh-CN')
function moldFor(order: OrderRecord) { return props.molds.find((mold) => mold.id === order.moldId) }
</script>

<template>
  <section class="backlog-dock" :class="{ open }"><header><div><PackageOpen :size="16" /><strong>待排订单池</strong><span>{{ orders.length }} 条</span><em>查看资格解释；草案任务可在计划表内拖放调度</em></div><button @click="emit('toggle')"><ChevronDown v-if="open" :size="16" /><ChevronUp v-else :size="16" />{{ open ? '收起' : '展开' }}</button></header><div v-if="open" class="backlog-cards"><article v-for="order in orders" :key="order.id"><div class="priority" :class="order.priorityCode.toLowerCase()">{{ order.priorityCode === 'CRITICAL' ? '特急' : order.priorityCode === 'URGENT' ? '加急' : '普通' }}</div><div class="backlog-main"><strong>{{ moldFor(order)?.moldNo ?? '未关联模具' }} · {{ order.productName }}</strong><span>{{ order.orderNo }} · {{ order.itemNo }}</span></div><dl><div><dt>安数 / 净重</dt><dd>{{ moldFor(order)?.aClass ? `${moldFor(order)?.aClass}A` : '待复核' }} · {{ moldFor(order)?.netWeightG ?? '—' }}g</dd></div><div><dt>机械手 / 夹具</dt><dd>{{ moldFor(order)?.requiredArmType || '待补充' }} · {{ moldFor(order)?.requiredFixtureType || '待补充' }}</dd></div><div><dt>欠数 / 交期</dt><dd>{{ number.format(order.outstandingQuantity) }} · <span :class="{ negative: (order.deliverySlackDays ?? 0) < 0 }">{{ order.deliveryDueDate }}</span></dd></div></dl><button class="candidate-button" @click="emit('view', order.id)"><ShieldQuestion :size="14" />候选解释</button></article><p v-if="!orders.length" class="empty-copy">当前没有待排订单</p></div></section>
</template>
