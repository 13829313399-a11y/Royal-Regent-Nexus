import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import InternalQuoteEngineeringExportDialog from '../InternalQuoteEngineeringExportDialog.vue'
import InternalQuoteReplaceSourceDialog from '../InternalQuoteReplaceSourceDialog.vue'
const mocks = vi.hoisted(() => ({ getEngineeringExportOptions: vi.fn(), downloadEngineeringWorkbook: vi.fn(), previewImport: vi.fn(), confirmImport: vi.fn(), applySavedSections: vi.fn() }))
vi.mock('@/api/internalQuote', () => ({ internalQuoteApi: mocks }))
vi.mock('@/stores/internalQuoteDesk', () => ({ useInternalQuoteDeskStore: () => mocks }))
afterEach(() => { document.body.innerHTML = ''; vi.clearAllMocks() })
describe('engineering electronic selection', () => {
  it('binds replacement to the selected source and keeps the dialog open after a failed confirmation', async () => {
    mocks.previewImport.mockResolvedValue({ batch_id: 'preview-1', target_revision: 8, source_file_name: '新辅料.xlsx', row_count: 2, warnings: [], diff_summary: { replaced_file_name: '旧辅料.xlsx' } })
    mocks.confirmImport.mockRejectedValueOnce(new Error('版本已变化'))
    const wrapper = mount(InternalQuoteReplaceSourceDialog, { props: { quoteId: 'q1', sources: [{ id: 'source-1', file_name: '旧辅料.xlsx', department: 'engineering', import_type: 'auxiliary', editable: true, revision: 8 }] }, attachTo: document.body })
    await flushPromises()
    const file = new File(['content'], '新辅料.xlsx')
    const input = document.querySelector<HTMLInputElement>('input[type="file"]')!
    Object.defineProperty(input, 'files', { value: [file] })
    input.dispatchEvent(new Event('change', { bubbles: true })); await flushPromises()
    expect(mocks.previewImport).toHaveBeenCalledWith('q1', 'auxiliary', file, undefined, 'source-1')
    document.querySelector<HTMLButtonElement>('button.primary')!.click(); await flushPromises()
    expect(mocks.confirmImport).toHaveBeenCalledWith('q1', 'preview-1', 8, {})
    expect(wrapper.emitted('replaced')).toBeUndefined()
    expect(mocks.applySavedSections).not.toHaveBeenCalled()
    expect(document.querySelector('[role="alert"]')).not.toBeNull()
    mocks.confirmImport.mockResolvedValueOnce({ section: { department: 'engineering', revision: 9 } })
    document.querySelector<HTMLButtonElement>('button.primary')!.click(); await flushPromises()
    expect(mocks.applySavedSections).toHaveBeenCalledWith('q1', [{ department: 'engineering', revision: 9 }])
    expect(wrapper.emitted('replaced')).toHaveLength(1)
    wrapper.unmount()
  })
  it('selects individual rows, supports none/all, and passes the displayed revisions', async () => {
    mocks.getEngineeringExportOptions.mockResolvedValue({ header_revision: 8, electronic_revision: 3, items: [
      { id: '0', name: '灯', specification: 'LED', quantity: 1, supplier: 'A' },
      { id: '1', name: '电路板', specification: 'PCB', quantity: 1, supplier: 'B' },
    ] })
    mocks.downloadEngineeringWorkbook.mockResolvedValue(undefined)
    const wrapper = mount(InternalQuoteEngineeringExportDialog, { props: { quoteId: 'q1', fileName: '工程.xlsx' }, attachTo: document.body })
    await flushPromises()
    const inputs = Array.from(document.querySelectorAll<HTMLInputElement>('input[type="checkbox"]'))
    expect(inputs).toHaveLength(3)
    expect(inputs.every(i => i.checked)).toBe(true)
    inputs[1]!.click(); await flushPromises()
    expect(inputs[0]!.checked).toBe(false)
    document.querySelector<HTMLButtonElement>('button.primary')!.click(); await flushPromises()
    expect(mocks.downloadEngineeringWorkbook).toHaveBeenCalledWith('q1', '工程.xlsx', { header_revision: 8, electronic_revision: 3, electronic_selection: ['1'] })
    inputs[0]!.click(); await flushPromises()
    expect(inputs.every(i => i.checked)).toBe(true)
    inputs[0]!.click(); await flushPromises()
    expect(inputs.every(i => !i.checked)).toBe(true)
    wrapper.unmount()
  })
})
