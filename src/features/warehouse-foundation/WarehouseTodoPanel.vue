<script setup lang="ts">
import { computed, useId, type Component } from 'vue'
import { RouterLink, type RouteLocationRaw } from 'vue-router'
import { ArrowUpRight, ChevronRight } from '@lucide/vue'

const props = defineProps<{
  title: string
  icon: Component
  unit?: string
  countLabel?: string
  action: string
  destination: RouteLocationRaw
  allLabel?: string
  empty: string
  error?: string
  loadingText?: string
  attention?: boolean
  wide?: boolean
  primaryAction?: boolean
  rows?: { id: string; title: string; context: string; subtitle?: string; quantity: string; date?: string; overdue?: boolean; to: RouteLocationRaw }[]
}>()
const heading = useId()
const count = computed(() => props.countLabel || (props.rows && `${props.rows.length}${props.unit ? ` ${props.unit}` : ''}`))
</script>

<template>
  <article class="warehouse-todo" :class="{ wide }" :aria-labelledby="heading">
    <header>
      <div class="warehouse-todo-heading">
        <h3 :id="heading"><component :is="icon" :size="17" aria-hidden="true" />{{ title }}</h3>
        <span v-if="count" class="warehouse-todo-count" :class="{ attention: attention && rows?.length }">{{ count }}</span>
      </div>
      <RouterLink :to="destination" :aria-label="allLabel || `查看全部${title}`">查看全部 <ArrowUpRight :size="13" aria-hidden="true" /></RouterLink>
    </header>
    <div v-if="rows && $slots.beforeRows" class="warehouse-todo-before"><slot name="beforeRows" /></div>
    <p v-if="error" class="warehouse-todo-empty warehouse-todo-error" role="alert">{{ error }}</p>
    <p v-else-if="!rows" class="warehouse-todo-empty" role="status">{{ loadingText || '正在读取…' }}</p>
    <p v-else-if="!rows.length" class="warehouse-todo-empty">{{ empty }}</p>
    <ul v-else class="warehouse-todo-list">
      <li v-for="row in rows.slice(0, 3)" :key="row.id">
        <RouterLink :to="row.to" class="warehouse-todo-row">
          <div class="warehouse-todo-identity">
            <strong>{{ row.title }}</strong><small v-if="row.subtitle" class="warehouse-todo-subtitle">{{ row.subtitle }}</small>
            <small v-if="!wide">{{ row.context }}</small>
            <slot name="rowEvidence" :id="row.id" />
          </div>
          <small v-if="wide" class="warehouse-todo-context">{{ row.context }}</small>
          <div class="warehouse-todo-quantity"><strong>{{ row.quantity }}</strong><small v-if="row.date" :class="{ overdue: row.overdue }">{{ row.date }}</small></div>
          <span class="warehouse-todo-action" :class="{ primary: primaryAction }">{{ action }}<ChevronRight :size="14" aria-hidden="true" /></span>
        </RouterLink>
      </li>
    </ul>
  </article>
</template>

<style scoped>
.warehouse-todo { min-width: 0; border: 1px solid var(--border); border-radius: 10px; background: var(--card); }
.warehouse-todo.wide { grid-column: 1 / -1; }
.warehouse-todo header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 12px; padding: 11px 14px; border-bottom: 1px solid var(--border); }
.warehouse-todo-heading, .warehouse-todo h3, .warehouse-todo header a, .warehouse-todo-action { display: flex; align-items: center; gap: 6px; }
.warehouse-todo-heading { gap: 8px; }
.warehouse-todo h3 { font-size: 15px; font-weight: 650; }
.warehouse-todo h3 svg, .warehouse-todo header a, .warehouse-todo-action { color: var(--primary); }
.warehouse-todo header a { font-size: 12px; min-height: 28px; white-space: nowrap; }
.warehouse-todo header a:hover { text-decoration: underline; }
.warehouse-todo-count { padding: 1px 7px; border-radius: 5px; font-size: 12px; white-space: nowrap; color: var(--primary); background: var(--accent); font-variant-numeric: tabular-nums; }
.warehouse-todo-count.attention { color: #92400e; background: #fef3c7; }
.warehouse-todo-empty { padding: 15px 14px 17px; font-size: 13px; color: var(--muted-foreground); }
.warehouse-todo-error { color: var(--destructive); }
.warehouse-todo-before { padding: 8px 14px 2px; }
.warehouse-todo-list > li + li { border-top: 1px solid var(--border); }
.warehouse-todo-row { display: grid; align-items: center; grid-template-columns: minmax(0, 1fr) auto; gap: 6px 12px; padding: 11px 14px; overflow-wrap: anywhere; }
.warehouse-todo-row:hover { background: var(--accent); }
.warehouse-todo a:focus-visible { outline: 2px solid var(--ring); outline-offset: -2px; border-radius: 5px; }
.warehouse-todo-row strong, .warehouse-todo-row small { display: block; }
.warehouse-todo-row strong { font-size: 13px; font-weight: 650; }
.warehouse-todo-row small { margin-top: 3px; font-size: 12px; color: var(--muted-foreground); }
.warehouse-todo-row .overdue { color: #9a3412; }
.warehouse-todo-quantity { text-align: right; font-variant-numeric: tabular-nums; }
.warehouse-todo-action { font-size: 12px; font-weight: 600; white-space: nowrap; grid-column: 2; justify-self: end; }
.warehouse-todo-action.primary { padding: 4px 7px; border-radius: 5px; background: var(--primary); color: var(--primary-foreground); }
.wide .warehouse-todo-context { grid-column: 1; }
@media (min-width: 1024px) {
  .warehouse-todo header, .warehouse-todo-row, .warehouse-todo-empty { padding-inline: 17px; }
  .warehouse-todo-row { grid-template-columns: minmax(0, 1fr) minmax(84px, max-content) auto; gap: 12px 16px; }
  .warehouse-todo-quantity { max-width: 150px; }
  .warehouse-todo-action { grid-column: auto; }
  .wide .warehouse-todo-row { grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr) minmax(0, .5fr) auto; }
  .wide .warehouse-todo-context { grid-column: auto; }
  .wide .warehouse-todo-quantity { max-width: none; }
}
</style>
