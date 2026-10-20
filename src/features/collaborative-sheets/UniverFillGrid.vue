<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { createUniver, LocaleType, mergeLocales } from '@univerjs/presets'
import { UniverSheetsDrawingPreset } from '@univerjs/preset-sheets-drawing'
import drawingZhCN from '@univerjs/preset-sheets-drawing/locales/zh-CN'
import '@univerjs/preset-sheets-drawing/lib/index.css'
import { UniverSheetsCorePreset } from '@univerjs/preset-sheets-core'
import zhCN from '@univerjs/preset-sheets-core/locales/zh-CN'
import { LifecycleStages, type ICellData, type IDisposable, type IObjectMatrixPrimitiveType } from '@univerjs/core'
import type { ISetRangeValuesCommandParams, ISetRangeValuesMutationParams, ISetSelectionsOperationParams } from '@univerjs/sheets'
import '@univerjs/preset-sheets-core/lib/index.css'
import type { FillCell, FillChange, FillSheet, FillTaskDetail } from '@/api/collaborativeSheets'
import { canFill, clipboardRows, coordinates, parseInput } from './grid'
import { blockedTrialCommand, cellAt, mutationChanges, scalarCell, stageFillChanges, TRIAL_SHEET_ID, trialWorkbook, VALUE_MUTATION } from './univerAdapter'

const props = defineProps<{
  task: FillTaskDetail; sheet: FillSheet; changes: FillChange[]; remoteChanges?: FillChange[]; disabled: boolean; selected: string
  selectCell: (cell: FillCell) => boolean
  stageChanges: (batch: FillChange[]) => boolean
  beginCell?: (cell: FillCell) => void
  endCell?: (cell: FillCell) => void
}>()
const emit = defineEmits<{ error: [message: string]; editing: [value: boolean]; save: [] }>()
const host = ref<HTMLElement>(), failed = ref('')
const ready = ref(false), imageError = ref('')
let instance: ReturnType<typeof createUniver> | undefined
let listeners: IDisposable[] = [], alive = true, internal = false, editing = false
let previousChanges: FillChange[] = [], rejection = 0
const remoteAddresses = new Set<string>()
let confirmedInput: { row: number; column: number; change: FillChange } | undefined
let editingCell: FillCell | undefined
const imageCount = computed(() => props.sheet.cells.filter(c => c.image).length + (props.sheet.images?.length ?? 0))
const selectedImages = computed(() => {
  const position = coordinates(props.selected)
  if (!position) return []
  const cell = cellAt(props.sheet, ...position)
  return [...(cell.image ? [cell.image] : []), ...(props.sheet.images ?? []).filter(i => i.row === cell.row && i.column === cell.column).map(i => i.url)]
})
function report(message: string) { rejection++; emit('error', message) }
async function finishEditing(): Promise<boolean> {
  if (!instance || !editing) return true
  const before = rejection
  try {
    const ended = await instance.univerAPI.getActiveWorkbook()?.endEditingAsync(true)
    return ended !== false && rejection === before && !editing
  } catch { report('当前单元格尚未确认，请按 Enter 确认或 Esc 取消后重试。'); return false }
}
defineExpose({ finishEditing })

function syncChanges() {
  if (!instance || editing || !alive) return
  const addresses = new Set([...remoteAddresses, ...[...previousChanges, ...props.changes].filter(c => c.sheet === props.sheet.index).map(c => c.address)])
  remoteAddresses.clear()
  const matrix: IObjectMatrixPrimitiveType<ICellData> = {}
  const pending = new Map(props.changes.filter(c => c.sheet === props.sheet.index).map(c => [c.address, c.value]))
  for (const address of addresses) {
    const position = coordinates(address)
    if (!position) continue
    const [row, column] = position, original = cellAt(props.sheet, row, column)
    if (original.image) continue
    ;(matrix[row] ??= {})[column] = scalarCell(pending.has(address) ? pending.get(address)! : original.formula ? original.display : original.value)
  }
  previousChanges = props.changes.map(c => ({ ...c }))
  if (!addresses.size) return
  internal = true
  try {
    instance.univerAPI.syncExecuteCommand(VALUE_MUTATION, { unitId: instance.univerAPI.getActiveWorkbook()!.getId(), subUnitId: TRIAL_SHEET_ID, cellValue: matrix })
  } finally { internal = false }
}
watch(() => props.changes, syncChanges, { flush: 'post' })
watch(() => props.remoteChanges, batch => {
  for (const c of batch ?? []) if (c.sheet === props.sheet.index) remoteAddresses.add(c.address)
  syncChanges()
}, { flush: 'post' })

onMounted(async () => {
  try {
    instance = createUniver({ locale: LocaleType.ZH_CN, locales: { [LocaleType.ZH_CN]: mergeLocales(zhCN, drawingZhCN) },
      presets: [UniverSheetsCorePreset({ container: host.value!, header: false, toolbar: false, contextMenu: false,
        formulaBar: false, footer: false, disableAutoFocus: true,
        sheets: { maxAutoHeightCount: 0 }, formula: { initialFormulaComputing: 0 } }), UniverSheetsDrawingPreset()],
    })
    const api = instance.univerAPI
    api.createWorkbook(trialWorkbook(props.task, props.sheet, props.changes))
    const worksheet = api.getActiveWorkbook()!.getActiveSheet()!
    // Imported images are display-only; all setup finishes before user input
    // is enabled, without weakening the normal mutation permission fence.
    try {
      if (imageCount.value) {
        if (api.getCurrentLifecycleStage() < LifecycleStages.Rendered) await new Promise<void>((resolve, reject) => {
          const timeout = setTimeout(() => { listener.dispose(); reject(new Error('Image renderer timed out')) }, 10_000)
          const listener = api.addEvent(api.Event.LifeCycleChanged, ({ stage }) => {
            if (stage >= LifecycleStages.Rendered) { clearTimeout(timeout); listener.dispose(); resolve() }
          })
          listeners.push(listener)
        })
        await new Promise<void>(resolve => requestAnimationFrame(() => resolve()))
      }
      for (const cell of props.sheet.cells.filter(c => c.image)) {
        if (!alive) return
        worksheet.setActiveRange(worksheet.getRange(cell.address))
        const inserted = await worksheet.getRange(cell.address).insertCellImageAsync(cell.image!)
        if (!inserted) throw new Error('Cell image renderer unavailable')
      }
      for (const img of props.sheet.images ?? []) {
        if (!alive) return
        const drawing = await worksheet.newOverGridImage().setSource(img.url).setRow(img.row).setColumn(img.column).setWidth(img.width).setHeight(img.height).buildAsync()
        if (!alive) return
        worksheet.insertImages([drawing])
      }
      worksheet.setActiveRange(worksheet.getRange('A1'))
    } catch { imageError.value = '部分图片未能加载，可选中图片格查看预览，或切换原版编辑器。原图仍保留在下载文件中。' }
    if (!alive) return
    previousChanges = props.changes.map(c => ({ ...c }))
    listeners.push(
      api.addEvent(api.Event.BeforeSheetEditStart, event => {
        if (props.disabled || !canFill(props.task, props.sheet, event.row, event.column)) {
          event.cancel = true; report('该单元格只读：仅可填写已分配范围，公式和合并区域内部不可修改。')
        } else { editingCell = cellAt(props.sheet, event.row, event.column); props.beginCell?.(editingCell) }
      }),
      api.addEvent(api.Event.SheetEditStarted, () => { confirmedInput = undefined; editing = true; emit('editing', true) }),
      api.addEvent(api.Event.BeforeSheetEditEnd, event => {
        confirmedInput = undefined
        if (!event.isConfirm) return
        try {
          if (props.disabled) throw new Error('正在处理，请稍后填写。')
          const cell = cellAt(props.sheet, event.row, event.column)
          const change = { sheet: props.sheet.index, address: cell.address, value: parseInput(event.value.toPlainText(), 'auto') }
          stageFillChanges(props.task, props.changes, [change])
          confirmedInput = { row: event.row, column: event.column, change }
        } catch (e) { event.cancel = true; report(e instanceof Error ? e.message : '填写内容无效。') }
      }),
      api.addEvent(api.Event.SheetEditEnded, event => {
        editing = false; emit('editing', false)
        const input = confirmedInput; confirmedInput = undefined
        // Univer may treat 00789 as unchanged when the old value is numeric 789.
        // Commit the original input even when its automatic conversion skipped a write.
        if (event.isConfirm && input) {
          api.syncExecuteCommand('sheet.command.set-range-values', {
            value: scalarCell(input.change.value),
            range: { startRow: input.row, endRow: input.row, startColumn: input.column, endColumn: input.column },
          })
        }
        if (editingCell) props.endCell?.(editingCell)
        editingCell = undefined
        queueMicrotask(syncChanges)
      }),
      // 1.0.3's facade SelectionChanged depends on a render-scoped selection service.
      // The public command event is reliable for both keyboard and mouse selection.
      api.addEvent(api.Event.CommandExecuted, event => {
        if (event.id !== 'sheet.operation.set-selections') return
        const params = event.params as ISetSelectionsOperationParams
        if (params.subUnitId !== TRIAL_SHEET_ID) return
        const range = params.selections[0]?.range
        if (range) props.selectCell(cellAt(props.sheet, range.startRow, range.startColumn))
      }),
      api.addEvent(api.Event.CellPointerUp, event => { props.selectCell(cellAt(props.sheet, event.row, event.column)) }),
      api.addEvent(api.Event.BeforeCommandExecute, event => {
        if (internal) return
        if (event.id === 'sheet.command.set-range-values' && confirmedInput) {
          const params = event.params as ISetRangeValuesCommandParams
          // redoUndoId identifies the native editor's commit, not clipboard/undo operations.
          if (params.redoUndoId) { params.value = scalarCell(confirmedInput.change.value); confirmedInput = undefined }
        }
        if (blockedTrialCommand(event.id)) {
          event.cancel = true; report('编辑器保留原表结构和格式，仅支持填写单元格内容。'); return
        }
        if (event.id !== VALUE_MUTATION) return
        const params = event.params as ISetRangeValuesMutationParams
        if (params.subUnitId !== TRIAL_SHEET_ID) return
        try {
          if (props.disabled) throw new Error('正在处理，请稍后填写。')
          if (!params.cellValue) throw new Error('编辑器不支持清空整张工作表。')
          const batch = mutationChanges(props.sheet, params.cellValue)
          if (!props.stageChanges(batch)) { event.cancel = true; rejection++; return }
          // All writes retain the original style. Only validated scalar values enter the canvas.
          const cells: IObjectMatrixPrimitiveType<ICellData> = {}
          for (const change of batch) {
            const [row, column] = coordinates(change.address)!
            ;(cells[row] ??= {})[column] = scalarCell(change.value)
          }
          params.cellValue = cells; params.isOverrideStyle = false
        } catch (e) { event.cancel = true; report(e instanceof Error ? e.message : '填写内容无效。') }
      }),
    )
    ready.value = true
  } catch (e) {
    failed.value = '新版编辑器加载失败，请返回原版继续填写。'
    emit('error', failed.value)
    console.error('Univer trial initialization failed', e)
    instance?.univer.dispose(); instance = undefined
  }
})

async function paste(event: ClipboardEvent) {
  // Use the existing bounded, atomic TSV parser; never import external formatting or formulas.
  event.preventDefault(); event.stopImmediatePropagation()
  const text = event.clipboardData?.getData('text/plain')
  if (props.disabled || text === undefined || !(await finishEditing()) || !alive) return
  const range = instance?.univerAPI.getActiveWorkbook()?.getActiveSheet()?.getSelection()?.getActiveRange()?.getRange()
  if (!range || !instance) return
  try {
    const rows = clipboardRows(text)
    if (rows.reduce((count, row) => count + row.length, 0) > 500) throw new Error('一次最多粘贴 500 格，请分批填写并保存。')
    const value: IObjectMatrixPrimitiveType<ICellData> = {}
    rows.forEach((line, r) => line.forEach((raw, c) => {
      ;(value[range.startRow + r] ??= {})[range.startColumn + c] = scalarCell(parseInput(raw, 'auto'))
    }))
    // The normal value command preserves Univer undo/redo; its mutation is checked atomically
    // by the same workspace draft validator as typing and the original grid.
    instance.univerAPI.syncExecuteCommand('sheet.command.set-range-values', { value })
  } catch (e) { report(e instanceof Error ? e.message : '粘贴失败。') }
}
function keydown(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && ['b', 'i', 'u'].includes(event.key.toLowerCase())) {
    event.preventDefault(); event.stopImmediatePropagation(); report('编辑器保留原表格式，仅支持填写内容。'); return
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
    event.preventDefault(); event.stopImmediatePropagation(); emit('save')
  }
}
onBeforeUnmount(() => {
  alive = false; listeners.forEach(listener => listener.dispose()); listeners = []
  instance?.univer.dispose(); instance = undefined; emit('editing', false)
})
</script>

<template>
  <section class="cs-univer-trial" aria-label="Univer 编辑器">
    <p v-if="!ready && !failed" role="status">正在加载表格{{ imageCount ? '和表内图片' : '' }}…</p>
    <p v-if="imageError" class="cs-warning">{{ imageError }}</p>
    <p v-if="failed" role="alert" class="cs-error">{{ failed }}</p>
    <div ref="host" class="cs-univer-canvas" :class="{ 'cs-univer-disabled': disabled || !ready }" @paste.capture="paste" @keydown.capture="keydown" />
    <div v-if="selectedImages.length" class="cs-univer-images" aria-label="选中单元格原图预览"><strong>{{ selected }} · 原图</strong><img v-for="(url, index) in selectedImages" :key="index" :src="url" alt="选中单元格原表图片" /></div>
  </section>
</template>

<style scoped>
.cs-univer-canvas { height: max(480px, calc(100vh - 310px)); width: 100%; min-width: 0; border: 1px solid #dbe2ea; position: relative; }
.cs-univer-disabled { pointer-events: none; opacity: .75; }
.cs-univer-images { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-start; padding: 12px; }
.cs-univer-images img { max-width: 360px; max-height: 300px; object-fit: contain; }
</style>
