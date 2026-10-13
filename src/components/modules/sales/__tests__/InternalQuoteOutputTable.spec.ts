import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import InternalQuoteOutputTable from '../internal-quote/InternalQuoteOutputTable.vue'
import type { OutputLayout } from '@/api/internalQuoteOutput'

const mocks = vi.hoisted(() => ({ get: vi.fn(), preview: vi.fn(), save: vi.fn(), applySavedSections: vi.fn(), leave: vi.fn(), update: vi.fn() }))
vi.mock('@/api/internalQuoteOutput', () => ({ internalQuoteOutputApi: mocks }))
vi.mock('@/stores/internalQuoteDesk', () => ({ useInternalQuoteDeskStore: () => mocks }))
vi.mock('vue-router', () => ({ onBeforeRouteLeave: mocks.leave, onBeforeRouteUpdate: mocks.update }))

function layout(readOnly = false): OutputLayout {
  return {
    quote_id: 'quote-1', version_label: 'A-V1', base_token: 'a'.repeat(64), preview: false, read_only: readOnly,
    factory_price_hkd: '1.1765', formula_errors: [], warnings: [],
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
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    mocks.get.mockResolvedValue(layout())
    mocks.preview.mockResolvedValue({ ...layout(), preview: true })
    mocks.save.mockResolvedValue({ quote: { id: 'quote-1' }, sections: [{ department: 'engineering', revision: 2 }] })
  })
  afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); vi.useRealTimers() })

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
    expect(mocks.leave.mock.calls[0]![0]()).toBe(false)
    expect(mocks.update.mock.calls[0]![0]()).toBe(false)
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
    expect(wrapper.text()).toContain('原始上传附件不附带')
  })
})
