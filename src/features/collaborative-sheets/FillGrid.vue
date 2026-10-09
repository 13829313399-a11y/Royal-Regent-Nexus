<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { FillCell, FillChange, FillSheet, FillTaskDetail, SheetValue } from '@/api/collaborativeSheets'
import { clipboardText, columnName, rangeBounds } from './grid'

const props = defineProps<{
  task: FillTaskDetail
  sheet: FillSheet
  changes: FillChange[]
  selected: string
  text: string
  disabled: boolean
  selectCell: (cell: FillCell) => boolean
  commitEditor: () => boolean
  cancelEditor: () => void
  pasteCells: (cell: FillCell, text: string, literal?: { value: SheetValue }) => boolean
}>()
const emit = defineEmits<{ input: [text: string]; begin: []; save: []; textMode: [] }>()
const clipboardMime = 'application/x-rrn-sheet-cell+json'
const gridElement = ref<HTMLElement>()
const editing = ref('')
const composing = ref(false)
watch(() => props.selected, address => { if (address !== editing.value) editing.value = '' })
watch(() => props.disabled, disabled => { if (disabled) editing.value = '' })
const cells = computed(() => new Map(props.sheet.cells.map(c => [c.address, c])))
const pending = computed(() => new Map(props.changes.filter(c => c.sheet === props.sheet.index).map(c => [c.address, c.value])))
const fillRanges = computed(() => props.task.editable_ranges.filter(g => g.sheet === props.sheet.index).map(g => rangeBounds(g.range)).filter(b => b !== null))
const merged = computed(() => {
  const result = new Map<string, { rowspan: number; colspan: number; hidden: boolean }>()
  for (const range of props.sheet.merges) {
    const b = rangeBounds(range)
    if (!b) continue
    for (let r = b[0]; r <= b[2]; r++) for (let c = b[1]; c <= b[3]; c++) {
      result.set(`${columnName(c)}${r + 1}`, { rowspan: b[2] - b[0] + 1, colspan: b[3] - b[1] + 1, hidden: r !== b[0] || c !== b[1] })
    }
  }
  return result
})
const rows = computed(() => Array.from({ length: props.sheet.rows }, (_, row) =>
  Array.from({ length: props.sheet.columns }, (_, column) => {
    const address = `${columnName(column)}${row + 1}`
    const cell: FillCell = cells.value.get(address) ?? { address, row, column, value: null, display: '', formula: false, style: {} }
    const editable = props.task.status === 'open' && !cell.formula && fillRanges.value.some(b => row >= b[0] && column >= b[1] && row <= b[2] && column <= b[3])
    return { cell, merge: merged.value.get(address), editable }
  }),
))
function display(cell: FillCell) {
  if (!pending.value.has(cell.address)) return cell.display
  const value = pending.value.get(cell.address)
  return value === null ? '' : typeof value === 'boolean' ? (value ? 'TRUE' : 'FALSE') : String(value)
}
function entry(cell: FillCell) { return rows.value[cell.row]?.[cell.column] }
function focusCell(cell: FillCell) {
  void nextTick(() => gridElement.value?.querySelector<HTMLElement>(`[data-cell="${cell.address}"]`)?.focus({ preventScroll: false }))
}
function choose(cell: FillCell) {
  if (props.disabled || !props.selectCell(cell)) return false
  editing.value = ''; return true
}
function begin(cell: FillCell, replacement?: string) {
  if (!entry(cell)?.editable || !choose(cell)) return
  emit('begin')
  if (replacement !== undefined) emit('input', replacement)
  editing.value = cell.address
  void nextTick(() => {
    const input = gridElement.value?.querySelector<HTMLTextAreaElement>('textarea')
    input?.focus(); input?.setSelectionRange(input.value.length, input.value.length)
  })
}
function commit() {
  if (!props.commitEditor()) return false
  editing.value = ''; return true
}
function move(cell: FillCell, dr: number, dc: number, wrap = false) {
  let r = cell.row, c = cell.column
  for (let i = 0; i < props.sheet.rows * props.sheet.columns; i++) {
    r += dr; c += dc
    if (wrap && c >= props.sheet.columns) { c = 0; r++ }
    if (wrap && c < 0) { c = props.sheet.columns - 1; r-- }
    if (r < 0 || r >= props.sheet.rows || c < 0 || c >= props.sheet.columns) { focusCell(cell); return }
    const target = rows.value[r]![c]!
    if (target.merge?.hidden) continue
    if (choose(target.cell)) focusCell(target.cell)
    return
  }
}
function keydown(event: KeyboardEvent, cell: FillCell, inEditor = false) {
  if (event.isComposing || composing.value || props.disabled) return
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
    event.preventDefault(); if (commit()) emit('save'); return
  }
  if (inEditor && event.key === 'Escape') {
    event.preventDefault(); props.cancelEditor(); editing.value = ''; focusCell(cell); return
  }
  if (event.key === 'Tab' || (event.key === 'Enter' && !event.altKey && !event.ctrlKey && !event.metaKey)) {
    event.preventDefault()
    if (inEditor && !commit()) return
    if (!inEditor && !props.commitEditor()) return
    move(cell, event.key === 'Enter' ? (event.shiftKey ? -1 : 1) : 0, event.key === 'Tab' ? (event.shiftKey ? -1 : 1) : 0, event.key === 'Tab')
    return
  }
  if (inEditor) return
  const direction: Record<string, [number, number]> = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] }
  const delta = direction[event.key]
  if (delta) { event.preventDefault(); if (props.commitEditor()) move(cell, ...delta); return }
  if (event.key === 'F2') { event.preventDefault(); begin(cell); return }
  if (event.key === 'Delete' || event.key === 'Backspace') {
    event.preventDefault(); if (entry(cell)?.editable && choose(cell)) { emit('begin'); emit('input', ''); props.commitEditor() }; return
  }
  if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) { event.preventDefault(); begin(cell, event.key) }
  // Chinese input methods can report Process before compositionstart.
  if (event.key === 'Process' || event.keyCode === 229) begin(cell, '')
}
function paste(event: ClipboardEvent, cell: FillCell, inEditor = false) {
  const text = event.clipboardData?.getData('text/plain')
  if (text === undefined || props.disabled) return
  let literal: { value: SheetValue } | undefined
  try {
    const decoded = JSON.parse(event.clipboardData?.getData(clipboardMime) ?? '') as { value?: unknown }
    const value = decoded?.value
    if (value === null || typeof value === 'string' || typeof value === 'boolean' || (typeof value === 'number' && Number.isFinite(value))) literal = { value }
  } catch { /* External clipboard text uses ordinary TSV parsing. */ }
  if (inEditor && literal) {
    event.preventDefault()
    const input = event.target as HTMLTextAreaElement
    const raw = literal.value === null ? '' : String(literal.value)
    const start = input.selectionStart, end = input.selectionEnd
    if (typeof literal.value === 'string') emit('textMode')
    emit('input', input.value.slice(0, start) + raw + input.value.slice(end))
    void nextTick(() => input.setSelectionRange(start + raw.length, start + raw.length)); return
  }
  if (inEditor && !/[\t\r\n]/.test(text)) return
  event.preventDefault()
  if (!props.commitEditor()) return
  if (props.pasteCells(cell, text, literal)) { editing.value = ''; focusCell(cell) }
}
function copy(event: ClipboardEvent, cell: FillCell) {
  if (editing.value) return
  const value = pending.value.has(cell.address) ? pending.value.get(cell.address)! : cell.value
  event.clipboardData?.setData(clipboardMime, JSON.stringify({ value }))
  event.clipboardData?.setData('text/plain', clipboardText(value)); event.preventDefault()
}
</script>

<template>
  <div ref="gridElement" class="cs-grid-scroll" tabindex="0" aria-label="原表填写区域，可横向滚动">
    <table class="cs-grid" :aria-label="sheet.name">
      <colgroup>
        <col style="width: 42px" />
        <col v-for="c in sheet.columns" :key="c" :style="{ width: `${sheet.column_widths[String(c - 1)] ?? 100}px` }" />
      </colgroup>
      <thead><tr><th class="cs-corner" /><th v-for="c in sheet.columns" :key="c">{{ columnName(c - 1) }}</th></tr></thead>
      <tbody>
        <tr v-for="(row, index) in rows" :key="index" :style="{ height: `${sheet.row_heights[String(index)] ?? 25}px` }">
          <th scope="row">{{ index + 1 }}</th>
          <template v-for="{ cell, merge, editable } in row" :key="cell.address">
            <td v-if="!merge?.hidden" :rowspan="merge?.rowspan" :colspan="merge?.colspan"
              :style="cell.style" :class="{ 'cs-editable': editable, 'cs-selected': selected === cell.address, 'cs-changed': pending.has(cell.address) }"
              :data-cell="cell.address" :title="`${cell.address}${cell.formula ? ' · 公式（只读）' : editable ? ' · 可填写' : ' · 只读'}`"
              :tabindex="selected === cell.address || (!selected && cell.row === 0 && cell.column === 0) ? 0 : -1" :aria-label="`${cell.address} ${display(cell)} ${cell.formula ? '公式只读' : editable ? '可填写' : '只读'}`"
              @focus="!editing && choose(cell)" @click="editing !== cell.address && choose(cell)" @dblclick="begin(cell)"
              @keydown.self="keydown($event, cell)" @paste.self="paste($event, cell)" @copy="copy($event, cell)"
              @compositionstart.self="!editing && begin(cell, '')">
              <textarea v-if="editing === cell.address" class="cs-inline-input" :aria-label="`编辑 ${cell.address}`" :value="text" :disabled="disabled"
                @input="emit('input', ($event.target as HTMLTextAreaElement).value)" @keydown.stop="keydown($event, cell, true)"
                @paste="paste($event, cell, true)" @blur="!composing && commit()" @click.stop @dblclick.stop
                @compositionstart="composing = true" @compositionend="composing = false" />
              <span v-else>{{ display(cell) }}</span>
              <img v-if="cell.image" :src="cell.image" alt="原表产品图片" loading="lazy" />
              <img v-for="(img, i) in (sheet.images ?? []).filter(img => img.row === cell.row && img.column === cell.column)" :key="i"
                :src="img.url" alt="原表图片" :width="img.width" :height="img.height" loading="lazy" />
            </td>
          </template>
        </tr>
      </tbody>
    </table>
  </div>
</template>
