import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import InternalQuoteOutputTable from '../internal-quote/InternalQuoteOutputTable.vue'
import type { OutputLayout } from '@/api/internalQuoteOutput'
import type { RouteLocationNormalized } from 'vue-router'
import { clearQuoteNavigationGuards, guardQuoteNavigation } from '@/features/internal-quote/navigationGuard'

const mocks = vi.hoisted(() => ({ get: vi.fn(), preview: vi.fn(), save: vi.fn(), applySavedSections: vi.fn(), leave: vi.fn(), update: vi.fn() }))
vi.mock('@/api/internalQuoteOutput', () => ({ internalQuoteOutputApi: mocks }))
vi.mock('@/stores/internalQuoteDesk', () => ({ useInternalQuoteDeskStore: () => mocks }))
vi.mock('vue-router', () => ({ onBeforeRouteLeave: mocks.leave, onBeforeRouteUpdate: mocks.update }))

function layout(readOnly = false): OutputLayout {
  return {
    quote_id: 'quote-1', version_label: 'A-V1', base_token: 'a'.repeat(64), preview: false, read_only: readOnly,
    factory_price_hkd: '1.1765', quote_price_hkd: '1.5', formula_errors: [], warnings: [],
    groups: [{ id: 'engineering:materials/0', section: 'engineering', section_name: '工程部', category: '五金', label: '螺丝', editable: !readOnly,
      fields: [{ id: 'engineering:materials/0/item', label: '名称', kind: 'name', value: '螺丝', currency: '', nullable: false },
        { id: 'engineering:materials/0/unit_price_rmb', label: '原始单价', kind: 'price', value: '.5', currency: 'RMB', nullable: false }] }],
    sheets: [{ name: '报价明细', widths: [80, 100, 180, 120], rows: [{ index: 20, height: 22, cells: [
      { address: 'C20', column: 3, text: '2.0*6 螺丝（2pcs）', rowspan: 1, colspan: 1, style: {}, unavailable: false, binding: { group: 'engineering:materials/0', kind: 'name' } },
      { address: 'D20', column: 4, text: '1.1765', rowspan: 1, colspan: 1, style: {}, unavailable: false, binding: { group: 'engineering:materials/0', kind: 'price' } },
    ] }] }],
  }
}
const wrappers: ReturnType<typeof mount>[] = []
async function start() {
  const wrapper = mount(InternalQuoteOutputTable, { props: { quoteId: 'quote-1', collaborationRoute: '/quote-1/collaboration' },
    global: { stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } } })
  wrappers.push(wrapper)
  await flushPromises()
  return wrapper
}

describe('output table source editing', () => {
  it('keeps the total visible and hides an outdated price while a new preview is pending', async () => {
    const wrapper = await start()
    expect(wrapper.get('.output-total-bar').text()).toContain('HKD 1.5000')
    await wrapper.get('[data-cell="D20"] button').trigger('click')
    await wrapper.get('input[aria-label="原始单价 RMB"]').setValue('.3')
    expect(wrapper.get('.output-total-bar').text()).toContain('待核算')
    mocks.preview.mockResolvedValue({ ...layout(), quote_price_hkd: '1.1', preview: true })
    await vi.advanceTimersByTimeAsync(700)
    expect(wrapper.get('.output-total-bar').text()).toContain('HKD 1.1000')
  })

  it('saves a price comment with its field and retains it on conflicts', async () => {
    const wrapper = await start()
    await wrapper.get('[data-cell="D20"] button').trigger('click')
    await wrapper.get('.output-note-button').trigger('click')
    await wrapper.get('textarea[aria-label="原始单价 调价批注"]').setValue('供应商口头降价')
    await vi.advanceTimersByTimeAsync(700)
    expect(mocks.preview).toHaveBeenCalledWith('quote-1', expect.objectContaining({ edits: [expect.objectContaining({
      field_id: 'engineering:materials/0/unit_price_rmb', value: '.5', annotation: { text: '供应商口头降价', image_attachment_ids: [], new_images: [] },
    })] }))
    mocks.save.mockRejectedValue(new Error('版本发生变化'))
    await wrapper.get('[data-testid="save-output-table"]').trigger('click')
    await flushPromises()
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('供应商口头降价')
    expect(wrapper.get('[data-testid="save-output-table"]').attributes('disabled')).toBeUndefined()
  })
  beforeEach(() => {
    clearQuoteNavigationGuards()
    vi.clearAllMocks()
    vi.useFakeTimers()
    mocks.get.mockResolvedValue(layout())
    mocks.preview.mockResolvedValue({ ...layout(), preview: true })
    mocks.save.mockResolvedValue({ quote: { id: 'quote-1' }, sections: [{ department: 'engineering', revision: 2 }] })
  })
  afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); clearQuoteNavigationGuards(); vi.useRealTimers() })

  it('edits the original currency price, not the displayed HKD line total, and preserves names and quantity', async () => {
    const wrapper = await start()
    await wrapper.get('[data-cell="D20"] button').trigger('click')
    const input = wrapper.get('input[aria-label="原始单价 RMB"]')
    expect((input.element as HTMLInputElement).value).toBe('.5')
    await input.setValue('.8')
    await vi.advanceTimersByTimeAsync(700)
    expect(mocks.preview).toHaveBeenCalledWith('quote-1', { base_token: 'a'.repeat(64), edits: [{ field_id: 'engineering:materials/0/unit_price_rmb', value: '.8' }] })
    await wrapper.get('[data-testid="save-output-table"]').trigger('click')
    await flushPromises()
    expect(mocks.save).toHaveBeenCalledWith('quote-1', expect.objectContaining({ edits: [{ field_id: 'engineering:materials/0/unit_price_rmb', value: '.8' }] }))
    expect(mocks.applySavedSections).toHaveBeenCalledWith('quote-1', [{ department: 'engineering', revision: 2 }])
    expect(wrapper.emitted('saved')).toHaveLength(1)
    expect(wrapper.get('[data-testid="save-output-table"]').attributes('disabled')).toBeDefined()
  })

  it('retains the local edits and original revision token after a conflict', async () => {
    const wrapper = await start()
    await wrapper.get('[data-cell="C20"] button').trigger('click')
    await wrapper.get('input[aria-label="名称"]').setValue('新螺丝')
    mocks.save.mockRejectedValue({ response: { status: 409, data: { detail: '报价已发生变化' } } })
    await wrapper.get('[data-testid="save-output-table"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('报价已发生变化')
    expect((wrapper.get('input[aria-label="名称"]').element as HTMLInputElement).value).toBe('新螺丝')
    expect(wrapper.get('[data-testid="save-output-table"]').attributes('disabled')).toBeUndefined()
    expect(mocks.applySavedSections).not.toHaveBeenCalled()
  })

  it('acknowledges a successful save even if reloading subsequently fails', async () => {
    const wrapper = await start()
    await wrapper.get('[data-cell="C20"] button').trigger('click')
    await wrapper.get('input[aria-label="名称"]').setValue('新螺丝')
    mocks.get.mockRejectedValue(new Error('读取失败'))
    await wrapper.get('[data-testid="save-output-table"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('修改已保存；表格尚未完整刷新')
    expect(wrapper.get('[data-testid="save-output-table"]').attributes('disabled')).toBeDefined()
    expect(mocks.applySavedSections).toHaveBeenCalledTimes(1)
  })

  it('does not publish a late preview over a newer draft', async () => {
    const wrapper = await start()
    let finish!: (value: OutputLayout) => void
    mocks.preview.mockReturnValueOnce(new Promise<OutputLayout>(resolve => { finish = resolve }))
    await wrapper.get('[data-cell="C20"] button').trigger('click')
    const input = wrapper.get('input[aria-label="名称"]')
    await input.setValue('第一次')
    await vi.advanceTimersByTimeAsync(700)
    await input.setValue('第二次')
    const old = layout(); old.sheets[0]!.rows[0]!.cells[1]!.text = '过期结果'
    finish(old)
    await flushPromises()
    expect(wrapper.text()).not.toContain('过期结果')
    expect((input.element as HTMLInputElement).value).toBe('第二次')
  })

  it('guards navigation and browser reload while a draft is unsaved', async () => {
    const wrapper = await start()
    await wrapper.get('[data-cell="C20"] button').trigger('click')
    await wrapper.get('input[aria-label="名称"]').setValue('未保存')
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const from = { fullPath: '/quote-1/summary' } as RouteLocationNormalized
    expect(await guardQuoteNavigation({ fullPath: '/quote-1/collaboration' } as RouteLocationNormalized, from)).toBe(false)
    expect(await guardQuoteNavigation({ fullPath: '/quote-2/summary' } as RouteLocationNormalized, from)).toBe(false)
    const event = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
    confirm.mockRestore()
  })

  it('keeps frozen cells read-only and links additions back to the same quotation', async () => {
    mocks.get.mockResolvedValue(layout(true))
    const wrapper = await start()
    expect(wrapper.find('[data-cell="C20"] button').exists()).toBe(false)
    expect(wrapper.text()).toContain('当前版本只读')
    expect(wrapper.get('a').attributes('href')).toBe('/quote-1/collaboration')
    expect(wrapper.text()).toContain('已上传的 Excel 原表随报价一起导出')
  })

  it('shows every source tab as read-only evidence even when the quotation is editable', async () => {
    const result = layout()
    const names = ['工模', '五金', '啤机', '装工', '喷油', '电子', '搪胶', '车缝', '车发']
    for (const name of names) result.sheets.push({
      ...result.sheets[0]!, name, widths: Array.from({ length: 27 }, () => 80),
      source: { file_name: `${name}.xlsx`, department: 'engineering' },
    })
    mocks.get.mockResolvedValue(result)
    const wrapper = await start()
    for (const name of names) {
      await wrapper.findAll('.output-tabs button').find(button => button.text() === name)!.trigger('click')
      expect(wrapper.text()).toContain(`原始报价：${name}.xlsx`)
      expect(wrapper.find('.output-cell-button').exists()).toBe(false)
      expect(wrapper.find('input.output-cell-input').exists()).toBe(false)
      expect(wrapper.findAll('thead th').at(-1)!.text()).toBe('AA')
    }
    expect(mocks.save).not.toHaveBeenCalled()
    expect(mocks.preview).not.toHaveBeenCalled()
  })
})
