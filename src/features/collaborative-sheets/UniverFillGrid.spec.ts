import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import type { FillCell, FillChange, FillTaskDetail } from '@/api/collaborativeSheets'
import UniverFillGrid from './UniverFillGrid.vue'
import { stageFillChanges, TRIAL_SHEET_ID, VALUE_MUTATION } from './univerAdapter'

const engine = vi.hoisted(() => {
  const handlers = new Map<string, (event: any) => void>()
  return { handlers, dispose: vi.fn(), remove: vi.fn(), sync: vi.fn(), end: vi.fn(), create: vi.fn() }
})
vi.mock('@univerjs/presets', () => ({
  LocaleType: { ZH_CN: 'zhCN' },
  createUniver: () => ({ univer: { dispose: engine.dispose }, univerAPI: {
    Event: new Proxy({}, { get: (_, key) => key }), createWorkbook: engine.create, syncExecuteCommand: engine.sync,
    getActiveWorkbook: () => ({ getId: () => 'workbook', endEditingAsync: engine.end }),
    addEvent: (name: string, callback: (event: any) => void) => {
      engine.handlers.set(name, callback)
      return { dispose: () => { engine.remove(name); engine.handlers.delete(name) } }
    },
  } }),
}))
vi.mock('@univerjs/preset-sheets-core', () => ({ UniverSheetsCorePreset: vi.fn() }))
vi.mock('@univerjs/preset-sheets-core/locales/zh-CN', () => ({ default: {} }))

function task(): FillTaskDetail {
  return {
    id: 'task', title: '试验', original_name: '试验.xlsx', format: 'xlsx', factory_id: 'huaxing',
    owner_user_id: 'owner', owner_name: '上传人', status: 'open', revision: 1, is_owner: true,
    created_at: '', updated_at: '', grants: [], submissions: [], activity: [], editable_ranges: [{ sheet: 0, range: 'B2:C3' }],
    workbook: { warnings: [], sheets: [{ index: 0, name: '数据', rows: 3, columns: 3, merges: [], row_heights: {}, column_widths: {}, cells: [
      { address: 'B2', row: 1, column: 1, value: '00123', display: '00123', formula: false, style: {} },
      { address: 'C2', row: 1, column: 2, value: 5, display: '5', formula: true, style: {} },
    ] }] },
  }
}
let wrapper: VueWrapper | undefined
let stage: ReturnType<typeof vi.fn<(batch: FillChange[]) => boolean>>, select: ReturnType<typeof vi.fn<(cell: FillCell) => boolean>>
function render() {
  const detail = task()
  stage = vi.fn(batch => { stageFillChanges(detail, [], batch); return true }); select = vi.fn(() => true)
  wrapper = mount(UniverFillGrid, { props: { task: detail, sheet: detail.workbook.sheets[0]!, changes: [], selected: '', disabled: false, selectCell: select, stageChanges: stage } })
}
function fire(name: string, event: any = {}) { engine.handlers.get(name)!(event); return event }
beforeEach(() => { vi.clearAllMocks(); engine.handlers.clear(); engine.end.mockResolvedValue(true) })
afterEach(() => { wrapper?.unmount(); wrapper = undefined })

describe('Univer trial bridge', () => {
  it('preserves typed leading zeros and dates using the same scalar parser as paste', () => {
    render()
    for (const [text, value] of [['00789', '00789'], ['2026-10-09', '2026-10-09'], ['25%', 0.25]] as const) {
      fire('SheetEditStarted')
      fire('BeforeSheetEditEnd', { row: 1, column: 1, isConfirm: true, value: { toPlainText: () => text } })
      const event = fire('BeforeCommandExecute', { id: 'sheet.command.set-range-values', params: { redoUndoId: 'native', value: { v: 789, t: 2 } } })
      expect(event.params.value.v).toBe(value)
      fire('SheetEditEnded', { isConfirm: true })
    }
  })
  it('commits raw text even when native automatic conversion regarded it as unchanged', () => {
    render(); fire('SheetEditStarted')
    fire('BeforeSheetEditEnd', { row: 1, column: 1, isConfirm: true, value: { toPlainText: () => '00789' } })
    fire('SheetEditEnded', { isConfirm: true })
    expect(engine.sync).toHaveBeenCalledWith('sheet.command.set-range-values', expect.objectContaining({ value: expect.objectContaining({ v: '00789', t: 1 }) }))
  })
  it('blocks formula input before ending editing and retains the dirty editing signal', () => {
    render(); fire('SheetEditStarted')
    const event = fire('BeforeSheetEditEnd', { row: 1, column: 1, isConfirm: true, value: { toPlainText: () => '=1+1' } })
    expect(event.cancel).toBe(true); expect(stage).not.toHaveBeenCalled()
    expect(wrapper!.emitted('editing')).toEqual([[true]])
  })
  it('rejects readonly edit starts and all scalar mutations while busy', async () => {
    render()
    expect(fire('BeforeSheetEditStart', { row: 1, column: 2 }).cancel).toBe(true)
    await wrapper!.setProps({ disabled: true })
    expect(fire('BeforeCommandExecute', { id: VALUE_MUTATION, params: { subUnitId: TRIAL_SHEET_ID, cellValue: { 1: { 1: { v: 'new' } } } } }).cancel).toBe(true)
    expect(stage).not.toHaveBeenCalled()
  })
  it('stages mutations through workspace validation and strips transient formatting', () => {
    render()
    const event = fire('BeforeCommandExecute', { id: VALUE_MUTATION, params: { subUnitId: TRIAL_SHEET_ID, isOverrideStyle: true, cellValue: { 1: { 1: { v: '0099', s: { bl: 1 } } } } } })
    expect(stage).toHaveBeenCalledWith([{ sheet: 0, address: 'B2', value: '0099' }])
    expect(event.params.cellValue[1][1].s).toBeUndefined()
    expect(event.params.isOverrideStyle).toBe(false)
    stage.mockReturnValueOnce(false)
    expect(fire('BeforeCommandExecute', { id: VALUE_MUTATION, params: { subUnitId: TRIAL_SHEET_ID, cellValue: { 1: { 1: { v: 'blocked' } } } } }).cancel).toBe(true)
  })
  it('tracks mouse and keyboard selection for readonly labels and original image previews', () => {
    render()
    fire('CommandExecuted', { id: 'sheet.operation.set-selections', params: { subUnitId: TRIAL_SHEET_ID, selections: [{ range: { startRow: 1, startColumn: 1 } }] } })
    expect(select).toHaveBeenLastCalledWith(expect.objectContaining({ address: 'B2' }))
    fire('CellPointerUp', { row: 1, column: 2 })
    expect(select).toHaveBeenLastCalledWith(expect.objectContaining({ address: 'C2', formula: true }))
  })
  it('finishes the native edit before a save/switch and disposes all listeners and the engine', async () => {
    render(); fire('SheetEditStarted')
    engine.end.mockImplementation(async () => { fire('SheetEditEnded', { isConfirm: false }); return true })
    expect(await (wrapper!.vm as unknown as { finishEditing: () => Promise<boolean> }).finishEditing()).toBe(true)
    const count = engine.handlers.size
    wrapper!.unmount(); wrapper = undefined
    await flushPromises()
    expect(engine.remove).toHaveBeenCalledTimes(count); expect(engine.handlers.size).toBe(0)
    expect(engine.dispose).toHaveBeenCalledTimes(1)
  })
})
