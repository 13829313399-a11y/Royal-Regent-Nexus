<script setup lang="ts">
import type { SpreadsheetCell } from '@/api/spreadsheetMerge'
import { cellText, columnLabel } from './mergeHelpers'
withDefaults(defineProps<{ headers: string[]; rows: SpreadsheetCell[][]; startRow?: number; caption: string }>(), { startRow: 2 })
</script>

<template>
  <div class="sm-grid" tabindex="0" :aria-label="caption">
    <table>
      <caption class="sr-only">{{ caption }}</caption>
      <thead><tr><th scope="col">行</th><th v-for="(header, index) in headers" :key="index" scope="col"><span class="sm-column">{{ columnLabel(index) }}</span>{{ header }}</th></tr></thead>
      <tbody>
        <tr v-for="(row, index) in rows" :key="index"><th scope="row">{{ startRow + index }}</th><td v-for="(_, column) in headers" :key="column" :title="cellText(row[column])">{{ cellText(row[column]) || '—' }}</td></tr>
        <tr v-if="!rows.length"><td :colspan="headers.length + 1" class="sm-grid-empty">暂无数据行</td></tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.sm-grid { max-width: 100%; overflow: auto; border: 1px solid var(--border); border-radius: var(--radius); max-height: 340px; background: var(--card); }
table { border-collapse: separate; border-spacing: 0; min-width: 100%; width: max-content; font-size: 13px; }
th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border); border-right: 1px solid var(--border); max-width: 300px; min-width: 120px; white-space: pre-wrap; overflow-wrap: anywhere; vertical-align: top; font-variant-numeric: tabular-nums; }
thead th { position: sticky; top: 0; background: var(--muted); font-size: 12px; font-weight: 600; z-index: 1; }
th:first-child { min-width: 52px; width: 52px; color: var(--muted-foreground); background: var(--muted); }
tbody tr:last-child > * { border-bottom: 0; }
.sm-column { color: var(--muted-foreground); margin-right: 8px; font-size: 11px; }
.sm-grid-empty { text-align: center; padding: 24px; color: var(--muted-foreground); }
</style>
