<script setup lang="ts">
import { ChevronDown, PackageOpen, ShieldQuestion, Trash2 } from '@lucide/vue'
import type { MoldRecord, OrderRecord } from '../types'
import { demandSourceMeta, moldEnrichmentStatusMeta, priorityMeta } from '../presentation/schedulingLabels'

const props = defineProps<{ orders: OrderRecord[]; molds: MoldRecord[]; open: boolean; canAppend: boolean; canEditDemand: boolean; appendDisabledReason: string }>()
const emit = defineEmits<{ toggle: []; view: [orderId: string]; append: [orderId: string]; edit: [orderId: string]; delete: [orderId: string] }>()
const number = new Intl.NumberFormat('zh-CN')
function moldFor(order: OrderRecord) { return props.molds.find((mold) => mold.id === order.moldId) }
function moldLabel(order: OrderRecord) { return moldFor(order)?.moldNo || String(order.lineage.source_mold_no || '待补模具') }
function sharedMoldMatched(order: OrderRecord) { return Boolean(order.moldDefinitionId) || order.lineage.mold_enrichment_status === 'MATCHED' }
function hasSchedulableMold(order: OrderRecord) { return Boolean(order.moldId || order.moldDefinitionId) }
function lineageText(order: OrderRecord, key: string, fallback: string) { const value = order.lineage[key]; return value === null || value === undefined || value === '' ? fallback : String(value) }
function machineClassLabel(order: OrderRecord) { const value = moldFor(order)?.aClass ?? order.lineage.machine_a_class; return value === null || value === undefined || value === '' ? '待复核' : `${String(value)}A` }
function moldStateLabel(order: OrderRecord) {
  if (sharedMoldMatched(order)) return `${moldEnrichmentStatusMeta('MATCHED').label} · 草案可排`
  const rawStatus = order.lineage.mold_enrichment_status
  return rawStatus ? moldEnrichmentStatusMeta(rawStatus).label : moldEnrichmentStatusMeta('PENDING').label
}
function appendTitle(order: OrderRecord) {
  if (!hasSchedulableMold(order)) return '共享模具资料待补齐，暂不能排到机台'
  return props.canAppend ? '预览并追加到选定机台末尾' : props.appendDisabledReason
}
</script>

<template>
  <section class="backlog-dock" :class="{ open }"><header><div><PackageOpen :size="16" /><strong>待排订单池</strong><span>{{ orders.length }} 条</span><em>下单表需求与手工需求共同进入排产草案</em></div><button :aria-expanded="open" @click="emit('toggle')"><span class="dock-chevron"><ChevronDown :size="16" /></span>{{ open ? '收起' : '展开' }}</button></header><div class="backlog-expand"><div><TransitionGroup v-if="open" name="backlog-card" tag="div" class="backlog-cards"><article v-for="order in orders" :key="order.id"><div class="priority" :class="priorityMeta(order.priorityCode).cssToken">{{ priorityMeta(order.priorityCode).label }}</div><div class="backlog-main"><strong>{{ moldLabel(order) }} · {{ order.productName }}</strong><span>{{ order.orderNo }} · {{ order.itemNo }} · {{ demandSourceMeta(order.sourceType).label }} · {{ moldStateLabel(order) }}</span></div><dl><div><dt>安数 / 净重</dt><dd>{{ machineClassLabel(order) }} · {{ moldFor(order)?.netWeightG ?? lineageText(order, 'mold_whole_shot_net_weight_g', '—') }}g</dd></div><div><dt>机械手 / 夹具</dt><dd>{{ moldFor(order)?.requiredArmType || lineageText(order, 'required_arm_type', '待补充') }} · {{ moldFor(order)?.requiredFixtureType || lineageText(order, 'required_fixture_type', '待补充') }}</dd></div><div><dt>欠数 / 交期</dt><dd>{{ number.format(order.outstandingQuantity) }} · <span :class="{ negative: (order.deliverySlackDays ?? 0) < 0 }">{{ order.deliveryDueDate }}</span></dd></div></dl><div class="backlog-card-actions"><button class="candidate-button" @click="emit('view', order.id)"><ShieldQuestion :size="14" />候选解释</button><button v-if="order.sourceType === 'MANUAL_PLANNING_DEMAND'" class="candidate-button" :disabled="!canEditDemand" @click="emit('edit', order.id)">修改需求</button><button class="candidate-button" :disabled="!canAppend || !hasSchedulableMold(order)" :title="appendTitle(order)" @click="emit('append', order.id)">追加到机台末尾</button><button class="candidate-button is-danger" :disabled="!canEditDemand" title="删除待排单" aria-label="删除待排单" @click="emit('delete', order.id)"><Trash2 :size="14" />删除</button></div></article><p v-if="!orders.length" key="empty" class="empty-copy">当前没有待排订单</p></TransitionGroup></div></div></section>
</template>
