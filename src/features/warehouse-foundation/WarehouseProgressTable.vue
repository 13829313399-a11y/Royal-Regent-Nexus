<script setup lang="ts" generic="Row extends { id: string }">
import { computed, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'

const props = defineProps<{
  rows: Row[]
  columns: { key: string; label: string; numeric?: boolean }[]
  label: string
  searchPlaceholder: string
  searchText: (row: Row) => string
  emptyTitle: string
  emptyDescription: string
  filtered?: boolean
}>()

const query = ref('')
const page = ref(0)
const pageSize = 30
const matches = computed(() => {
  const terms = query.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean)
  return props.rows.filter(row => {
    const value = props.searchText(row).toLocaleLowerCase()
    return terms.every(term => value.includes(term))
  })
})
const visible = computed(() => matches.value.slice(page.value * pageSize, (page.value + 1) * pageSize))
watch([query, () => props.rows], () => { page.value = 0 })
</script>

<template>
  <div class="warehouse-progress">
    <div class="warehouse-progress-filters">
      <label class="warehouse-progress-search">
        查找记录
        <input v-model="query" type="search" :aria-label="`查找${label}`" :placeholder="searchPlaceholder" />
      </label>
      <slot name="filters" />
    </div>
    <div class="warehouse-table-scroll" role="region" :aria-label="label" :tabindex="visible.length ? 0 : undefined">
      <table role="table">
        <thead>
          <tr><th v-for="column in columns" :key="column.key" scope="col" :class="{ numeric: column.numeric }">{{ column.label }}</th></tr>
        </thead>
        <tbody role="rowgroup">
          <tr v-for="row in visible" :key="row.id" role="row">
            <td v-for="column in columns" :key="column.key" role="cell" :data-label="column.label" :class="{ numeric: column.numeric }">
              <slot name="cell" :row="row" :column="column.key" />
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="!matches.length" class="warehouse-empty" role="status">
      <h3>{{ query.trim() || filtered ? '暂无符合条件的记录' : emptyTitle }}</h3>
      <p>{{ query.trim() || filtered ? '调整搜索或筛选条件后重试。' : emptyDescription }}</p>
    </div>
    <footer class="warehouse-list-footer">
      <span aria-live="polite">共 {{ matches.length }} 条</span>
      <div v-if="matches.length > pageSize">
        <Button variant="outline" size="sm" :disabled="page === 0" @click="page--">上一页</Button>
        <Button variant="outline" size="sm" :disabled="(page + 1) * pageSize >= matches.length" @click="page++">下一页</Button>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.warehouse-progress { min-width: 0; }
.warehouse-progress-filters { display: flex; flex-wrap: wrap; align-items: end; gap: 12px; padding: 0 20px 16px; }
.warehouse-progress-filters label { display: grid; gap: 6px; min-width: 0; font-size: 12px; color: var(--muted-foreground); }
.warehouse-progress-search { flex: 1 1 280px; max-width: 480px; }
.warehouse-progress input, .warehouse-progress-filters :deep(select) { min-width: 0; width: 100%; min-height: 36px; padding: 6px 10px; border: 1px solid var(--border); border-radius: 8px; background: var(--background); color: var(--foreground); font: inherit; }
.warehouse-progress :is(input, div[tabindex]):focus-visible, .warehouse-progress-filters :deep(select:focus-visible) { outline: 2px solid var(--ring); outline-offset: -2px; }
.warehouse-progress table { min-width: 860px; text-align: left; }
.warehouse-progress th:last-child, .warehouse-progress td:last-child { text-align: right; }
.warehouse-progress .numeric { text-align: right; font-variant-numeric: tabular-nums; }
.warehouse-progress td { padding: 12px 20px; border-bottom: 1px solid var(--border); vertical-align: top; overflow-wrap: anywhere; }
.warehouse-progress tbody tr:hover { background: var(--accent); }
@media (max-width: 639px) {
  .warehouse-progress-filters { padding-inline: 16px; }
  .warehouse-progress input, .warehouse-progress-filters :deep(select) { min-height: 44px; font-size: 16px; }
  .warehouse-progress table, .warehouse-progress tbody { display: block; min-width: 0; }
  .warehouse-progress thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
  .warehouse-progress tbody tr { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin: 0 12px 10px; padding: 14px; border: 1px solid var(--border); border-radius: 8px; }
  .warehouse-progress td { padding: 0; border: 0; }
  .warehouse-progress td:first-child, .warehouse-progress td:last-child { grid-column: 1 / -1; }
  .warehouse-progress td:not(:first-child, :last-child)::before { content: attr(data-label); display: block; margin-bottom: 3px; color: var(--muted-foreground); }
  .warehouse-progress td.numeric { text-align: left; }
}
</style>
