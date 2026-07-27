<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  CircleAlert,
  Filter,
  GripVertical,
  Search,
  ShieldQuestion,
  Sparkles,
} from '@lucide/vue'
import type { InjectionMold, InjectionOrder } from '@/types/injectionSchedule'

const props = withDefaults(defineProps<{
  orders: InjectionOrder[]
  molds: InjectionMold[]
  planBaseAt?: string
  selectedOrderId?: string
}>(), {
  planBaseAt: '',
  selectedOrderId: '',
})

const emit = defineEmits<{
  select: [orderId: string]
  inspect: [orderId: string]
  openOrders: []
}>()

const query = ref('')
const priorityOnly = ref(false)
const moldById = computed(() => new Map(props.molds.map((mold) => [mold.id, mold])))

const visibleOrders = computed(() => {
  const normalizedQuery = query.value.trim().toLocaleLowerCase('zh-CN')
  return props.orders.filter((order) => {
    if (priorityOnly.value && order.priority !== 'P0' && order.priority !== 'P1') {
      return false
    }
    if (!normalizedQuery) return true
    const mold = moldById.value.get(order.moldId)
    return [
      order.orderNo,
      order.productName,
      order.moldId,
      order.itemNo ?? '',
      mold?.recommendedMachineClass ?? '',
    ].some((value) => value.toLocaleLowerCase('zh-CN').includes(normalizedQuery))
  })
})

function beginDrag(event: DragEvent, orderId: string) {
  event.dataTransfer?.setData('application/x-injection-order', orderId)
  event.dataTransfer?.setData('text/plain', orderId)
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
  }
  emit('select', orderId)
}

function dueCopy(order: InjectionOrder) {
  if (!order.deliveryDueAt) return '交期缺失'
  const dueDay = shanghaiDayOrdinal(order.deliveryDueAt)
  const businessDay = shanghaiDayOrdinal(props.planBaseAt)
  if (dueDay === null) return '交期待确认'
  if (businessDay === null) return '基准日期缺失'
  const days = Math.round((dueDay - businessDay) / 86_400_000)
  if (days < 0) return `已超 ${Math.abs(days)} 天`
  if (days === 0) return '今日到期'
  return `${days} 天后到期`
}

function shanghaiDayOrdinal(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(date)
  const year = Number(parts.find((part) => part.type === 'year')?.value)
  const month = Number(parts.find((part) => part.type === 'month')?.value)
  const day = Number(parts.find((part) => part.type === 'day')?.value)
  if (![year, month, day].every(Number.isFinite)) return null
  return Date.UTC(year, month - 1, day)
}

function priorityClass(priority: InjectionOrder['priority']) {
  return `priority priority--${priority.toLocaleLowerCase()}`
}

function moldNo(order: InjectionOrder) {
  return moldById.value.get(order.moldId)?.moldNo ?? order.moldId
}

function recommendationLabel(order: InjectionOrder) {
  return order.dataQualityFlags.find((flag) => flag.trim().length > 0)
    ?? '暂无已知资料阻断'
}
</script>

<template>
  <aside class="order-pool" aria-labelledby="pending-order-pool-title">
    <header class="order-pool__heading">
      <h2 id="pending-order-pool-title">待排订单池</h2>
      <span>{{ orders.length }}</span>
    </header>

    <div class="order-pool__filters">
      <label class="search-field">
        <Search aria-hidden="true" />
        <span class="sr-only">搜索待排订单</span>
        <input v-model="query" type="search" placeholder="搜索模号 / 单号 / 名称">
      </label>
      <button
        type="button"
        class="filter-button"
        :aria-pressed="priorityOnly"
        @click="priorityOnly = !priorityOnly"
      >
        <Filter aria-hidden="true" />
        优先级
      </button>
    </div>

    <div class="order-pool__list" role="list" aria-label="可拖拽的待排订单">
      <article
        v-for="order in visibleOrders"
        :key="order.id"
        class="order-card"
        :class="{ 'order-card--selected': selectedOrderId === order.id }"
        role="listitem"
        draggable="true"
        :aria-label="`${order.priority}，订单${order.orderNo}，${order.productName}，欠数${order.outstandingShots}`"
        @dragstart="beginDrag($event, order.id)"
      >
        <button
          type="button"
          class="order-card__select"
          :aria-label="`选择${order.orderNo}进行机台匹配；${recommendationLabel(order)}`"
          :aria-pressed="selectedOrderId === order.id"
          @click="emit('select', order.id)"
        >
          <span class="order-card__drag" aria-hidden="true">
            <GripVertical />
          </span>
          <span class="order-card__body">
            <span class="order-card__topline">
              <span :class="priorityClass(order.priority)">{{ order.priority }}</span>
              <strong>{{ moldNo(order) }}</strong>
            </span>
            <span class="order-card__name">{{ order.productName }}</span>
            <span class="order-card__meta">
              <strong>欠 {{ order.outstandingShots.toLocaleString('zh-CN') }}</strong>
              <span :class="{ 'order-card__due--late': dueCopy(order).includes('已超') }">
                {{ dueCopy(order) }}
              </span>
              <small>货号 {{ order.itemNo || '—' }}</small>
            </span>
            <span class="order-card__footer">
              <span>{{ moldById.get(order.moldId)?.recommendedMachineClass ?? '机型待定' }}</span>
              <span>{{ moldById.get(order.moldId)?.armRequirement === 'double' ? '双臂' : '单臂/通用' }}</span>
              <small
                :title="recommendationLabel(order)"
                :class="{ 'order-card__quality--warning': order.dataQualityFlags.length > 0 }"
              >
                <ShieldQuestion v-if="order.dataQualityFlags.length > 0" aria-hidden="true" />
                <Sparkles v-else aria-hidden="true" />
                {{ recommendationLabel(order) }}
              </small>
            </span>
          </span>
        </button>
        <button
          type="button"
          class="order-card__inspect"
          :aria-label="`查看${order.orderNo}的智能匹配解释`"
          @click.stop="emit('inspect', order.id)"
        >
          <CircleAlert aria-hidden="true" />
        </button>
      </article>

      <div v-if="visibleOrders.length === 0" class="order-pool__empty">
        <CircleAlert aria-hidden="true" />
        <strong>没有符合条件的待排订单</strong>
        <span>清除搜索或优先级筛选后再试。</span>
      </div>
    </div>

    <footer class="order-pool__footer">
      <button type="button" @click="emit('openOrders')">
        <CircleAlert aria-hidden="true" />
        查看全部 {{ orders.length }} 条及资料风险
      </button>
    </footer>
  </aside>
</template>

<style scoped>
.order-pool {
  display: grid;
  min-width: 0;
  height: 100%;
  grid-template-rows: 52px auto minmax(0, 1fr) 36px;
  background: #fbfcfc;
}

.order-pool__heading {
  display: flex;
  align-items: center;
  gap: 9px;
  border-bottom: 1px solid #dde5e8;
  padding: 0 18px;
}

.order-pool__heading h2 {
  color: #0f172a;
  font-size: 18px;
  font-weight: 800;
}

.order-pool__heading span {
  display: inline-flex;
  height: 22px;
  min-width: 28px;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: #feecec;
  padding: 0 8px;
  color: #dc2626;
  font-size: 11px;
  font-weight: 800;
}

.order-pool__filters {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 9px;
  padding: 14px 18px 10px;
}

.search-field {
  display: flex;
  height: 42px;
  align-items: center;
  gap: 8px;
  border: 1px solid #dbe5e8;
  border-radius: 9px;
  background: #fff;
  padding: 0 11px;
}

.search-field:focus-within {
  border-color: #14b8a6;
  box-shadow: 0 0 0 3px rgb(20 184 166 / 14%);
}

.search-field svg,
.filter-button svg {
  width: 16px;
  height: 16px;
  flex: none;
}

.search-field svg {
  color: #94a3b8;
}

.search-field input {
  min-width: 0;
  flex: 1;
  border: 0;
  background: transparent;
  color: #0f172a;
  font-size: 12px;
  outline: none;
}

.search-field input::placeholder {
  color: #94a3b8;
}

.filter-button {
  display: inline-flex;
  height: 42px;
  align-items: center;
  gap: 6px;
  border: 1px solid #dbe5e8;
  border-radius: 9px;
  background: #fff;
  padding: 0 12px;
  color: #334155;
  font-size: 12px;
  font-weight: 700;
}

.filter-button:hover,
.filter-button[aria-pressed='true'] {
  border-color: #5eead4;
  background: #ecfdf8;
  color: #0f766e;
}

.filter-button:focus-visible {
  box-shadow: 0 0 0 3px rgb(20 184 166 / 18%);
  outline: none;
}

.order-pool__list {
  display: grid;
  align-content: start;
  gap: 8px;
  overflow-y: auto;
  padding: 4px 18px 12px;
  scrollbar-color: #a7b7bd transparent;
  scrollbar-width: thin;
}

.order-card {
  display: grid;
  min-height: 84px;
  grid-template-columns: minmax(0, 1fr) 28px;
  align-items: start;
  border: 1px solid #dbe5e8;
  border-radius: 11px;
  background: #fff;
  padding: 0 8px 0 0;
  transition: border-color 140ms ease, box-shadow 140ms ease, transform 140ms ease;
}

.order-card:hover,
.order-card--selected {
  border-color: #5eead4;
  box-shadow: 0 8px 20px -18px rgb(15 118 110 / 75%);
}

.order-card--selected {
  background: #f0fdfa;
}

.order-card:active {
  transform: translateY(1px);
}

.order-card__select {
  display: grid;
  min-width: 0;
  min-height: 82px;
  grid-template-columns: 23px minmax(0, 1fr);
  align-items: start;
  border: 0;
  border-radius: 10px 0 0 10px;
  background: transparent;
  padding: 10px 0 9px 5px;
  color: inherit;
  font: inherit;
  text-align: left;
}

.order-card__select:focus-visible {
  box-shadow: inset 0 0 0 2px #0f766e;
  outline: none;
}

.order-card__drag,
.order-card__inspect {
  display: flex;
  height: 32px;
  align-items: center;
  justify-content: center;
  color: #64748b;
}

.order-card__inspect {
  width: 28px;
  border: 0;
  border-radius: 7px;
  background: transparent;
}

.order-card__drag {
  width: 23px;
}

.order-card__inspect:hover {
  background: #e6f7f4;
  color: #0f766e;
}

.order-card__inspect:focus-visible {
  box-shadow: 0 0 0 2px #0f766e;
  outline: none;
}

.order-card__drag svg,
.order-card__inspect svg {
  width: 16px;
  height: 16px;
}

.order-card__body {
  display: block;
  min-width: 0;
}

.order-card__topline {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
}

.order-card__topline strong {
  overflow: hidden;
  color: #0f172a;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.priority {
  display: inline-flex;
  height: 19px;
  min-width: 30px;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  padding: 0 7px;
  font-size: 9px;
  font-weight: 800;
}

.priority--p0 { background: #feecec; color: #dc2626; }
.priority--p1 { background: #fff4d8; color: #b45309; }
.priority--p2 { background: #eaf1ff; color: #2563eb; }
.priority--p3 { background: #eef2f7; color: #64748b; }

.order-card__name {
  display: block;
  margin-top: 4px;
  overflow: hidden;
  color: #334155;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.order-card__meta,
.order-card__footer {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 7px;
}

.order-card__meta {
  margin-top: 5px;
  color: #2563eb;
  font-size: 10px;
}

.order-card__meta strong {
  font-weight: 800;
}

.order-card__meta small {
  overflow: hidden;
  color: #64748b;
  font-size: 9px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.order-card__due--late {
  color: #dc2626;
  font-weight: 700;
}

.order-card__footer {
  margin-top: 6px;
  color: #64748b;
  font-size: 9px;
}

.order-card__footer > span {
  border-radius: 999px;
  background: #f1f5f9;
  padding: 2px 6px;
}

.order-card__footer small {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  gap: 3px;
  overflow: hidden;
  color: #0f766e;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.order-card__footer small svg {
  width: 11px;
  height: 11px;
  flex: none;
}

.order-card__quality--warning {
  color: #b45309 !important;
}

.order-pool__empty {
  display: grid;
  justify-items: center;
  gap: 7px;
  padding: 48px 24px;
  color: #64748b;
  text-align: center;
}

.order-pool__empty svg {
  width: 28px;
  height: 28px;
  color: #0f766e;
}

.order-pool__empty strong {
  color: #334155;
  font-size: 13px;
}

.order-pool__empty span {
  font-size: 11px;
}

.order-pool__footer {
  display: flex;
  align-items: center;
  border-top: 1px solid #e8eef0;
  background: #e6f7f4;
  padding: 0 14px;
}

.order-pool__footer button {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 0;
  background: transparent;
  color: #0f766e;
  font-size: 10px;
  font-weight: 700;
}

.order-pool__footer button:focus-visible {
  outline: 2px solid #0f766e;
  outline-offset: 2px;
}

.order-pool__footer svg {
  width: 13px;
  height: 13px;
}
</style>
