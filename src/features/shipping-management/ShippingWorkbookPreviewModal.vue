<script setup lang="ts">
import { computed, ref, watch, type CSSProperties } from 'vue'
import { Download, FileSpreadsheet, X } from '@lucide/vue'
import type { WorkbookPreviewCell, WorkbookPreviewSheet } from '@/api/shippingMail'

const props = defineProps<{
  filename: string
  path?: string
  sheets: WorkbookPreviewSheet[]
  canDownload?: boolean
}>()

const emit = defineEmits<{
  close: []
  download: []
}>()

const activeIndex = ref(0)

watch(() => props.filename, () => {
  activeIndex.value = 0
})

const currentSheet = computed(() => props.sheets[activeIndex.value] ?? props.sheets[0] ?? null)
const columnCount = computed(() => {
  if (!currentSheet.value) return 0
  if (currentSheet.value.cells?.length) {
    return currentSheet.value.cells.reduce((max, row) => Math.max(max, row.length), 0)
  }
  return currentSheet.value.rows.reduce((max, row) => Math.max(max, row.length), 0)
})
const colWidths = computed(() => {
  const widths = currentSheet.value?.colWidths ?? []
  return Array.from({ length: columnCount.value }, (_, idx) => widths[idx] || 90)
})
const rowHeights = computed(() => currentSheet.value?.rowHeights ?? [])

function visibleCells(row: WorkbookPreviewCell[]) {
  return row.filter((cell) => !cell.skip)
}

function canOverflowRight(row: WorkbookPreviewCell[], index: number, cell: WorkbookPreviewCell) {
  if (cell.wrap || cell.v.includes('\n') || (cell.align && cell.align !== 'left')) return false
  const next = row[index + 1]
  if (!next) return true
  return !next.v && !next.bg && !next.border?.l && !cell.border?.r
}

function cellStyle(cell: WorkbookPreviewCell, row: WorkbookPreviewCell[], index: number): CSSProperties {
  const overflow = canOverflowRight(row, index, cell)
  return {
    backgroundColor: cell.bg || undefined,
    color: cell.color || '#111827',
    fontWeight: cell.bold ? 700 : 400,
    fontStyle: cell.italic ? 'italic' : 'normal',
    textDecoration: cell.underline ? 'underline' : 'none',
    fontSize: `${Math.round((cell.fontSize || 10) * 1.25)}px`,
    fontFamily: cell.fontFamily ? `"${cell.fontFamily}", "Microsoft YaHei", sans-serif` : '"Microsoft YaHei", sans-serif',
    textAlign: cell.align || 'left',
    verticalAlign: cell.valign || 'middle',
    whiteSpace: cell.wrap || cell.v.includes('\n') ? 'pre-wrap' : 'nowrap',
    overflow: overflow ? 'visible' : 'hidden',
    textOverflow: overflow ? 'clip' : 'ellipsis',
    padding: '2px 6px',
    borderTop: cell.border?.t || '1px solid #e5e7eb',
    borderRight: cell.border?.r || '1px solid #e5e7eb',
    borderBottom: cell.border?.b || '1px solid #e5e7eb',
    borderLeft: cell.border?.l || '1px solid #e5e7eb',
  }
}
</script>

<template>
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/45 p-3"
    role="dialog"
    aria-modal="true"
    aria-label="表格预览"
    @click.self="emit('close')"
  >
    <section class="flex max-h-[92vh] w-[96vw] max-w-[1440px] flex-col overflow-hidden rounded-xl border border-emerald-200 bg-white shadow-2xl">
      <header class="flex flex-wrap items-center justify-between gap-2 border-b border-emerald-100 bg-emerald-50/70 px-4 py-2.5">
        <div class="flex min-w-0 items-center gap-2">
          <FileSpreadsheet class="size-4 shrink-0 text-emerald-700" aria-hidden="true" />
          <div class="min-w-0">
            <h3 class="truncate text-[13px] font-bold text-emerald-950">{{ filename }}</h3>
            <p v-if="path" class="truncate text-[10px] text-slate-500">本地副本：{{ path }}</p>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <button
            v-if="canDownload"
            type="button"
            class="inline-flex h-7 items-center gap-1 rounded-md border border-emerald-200 bg-white px-2.5 text-[11px] font-semibold text-emerald-800 hover:bg-emerald-50"
            @click="emit('download')"
          >
            <Download class="size-3.5" />下载原文件
          </button>
          <button
            type="button"
            class="inline-flex h-7 items-center gap-1 rounded-md border border-slate-200 bg-white px-2.5 text-[11px] font-semibold text-slate-600 hover:bg-slate-50"
            aria-label="关闭表格预览"
            @click="emit('close')"
          >
            <X class="size-3.5" />关闭
          </button>
        </div>
      </header>

      <div v-if="sheets.length > 1" class="flex flex-wrap gap-1 border-b border-slate-100 bg-slate-50/70 px-4 py-1.5">
        <button
          v-for="(sheet, index) in sheets"
          :key="sheet.name"
          type="button"
          class="rounded px-2.5 py-1 text-[11px] font-semibold transition"
          :class="index === activeIndex ? 'bg-emerald-700 text-white' : 'bg-white text-slate-600 hover:bg-emerald-50'"
          @click="activeIndex = index"
        >
          {{ sheet.name }}
        </button>
      </div>

      <div class="min-h-[240px] flex-1 overflow-auto bg-slate-100/80 p-4">
        <div v-if="currentSheet && currentSheet.cells?.length" class="inline-block min-w-full rounded bg-white p-2 shadow-sm">
          <table class="border-collapse bg-white" style="table-layout: fixed;">
            <colgroup>
              <col v-for="(w, idx) in colWidths" :key="idx" :style="{ width: `${w}px` }">
            </colgroup>
            <tbody>
              <tr
                v-for="(row, rIndex) in currentSheet.cells"
                :key="rIndex"
                :style="{ height: rowHeights[rIndex] ? `${rowHeights[rIndex]}px` : undefined }"
              >
                <td
                  v-for="(cell, cIndex) in visibleCells(row)"
                  :key="cIndex"
                  :rowspan="cell.rs || undefined"
                  :colspan="cell.cs || undefined"
                  :style="cellStyle(cell, visibleCells(row), cIndex)"
                >{{ cell.v }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <table v-else-if="currentSheet && currentSheet.rows.length" class="w-full border-collapse bg-white text-[11px] text-slate-700">
          <tbody>
            <tr
              v-for="(row, rIndex) in currentSheet.rows"
              :key="rIndex"
              :class="rIndex === 0 ? 'bg-emerald-50/70 font-semibold text-emerald-950' : 'hover:bg-emerald-50/30'"
            >
              <td class="w-9 border border-slate-200 bg-slate-50 px-1.5 py-1 text-center text-[10px] tabular-nums text-slate-400">{{ rIndex + 1 }}</td>
              <td
                v-for="cIndex in columnCount"
                :key="cIndex"
                class="max-w-[260px] border border-slate-200 px-2 py-1 align-top tabular-nums"
              >
                {{ row[cIndex - 1] ?? '' }}
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else class="py-8 text-center text-[12px] text-slate-400">当前表格没有可预览的内容。</p>
      </div>
    </section>
  </div>
</template>
