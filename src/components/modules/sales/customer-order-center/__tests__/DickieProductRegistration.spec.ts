import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProductRegistration from '../DickieProductRegistration.vue'
import type { CustomerOrderImportPreview } from '@/types/customerOrder'
const api = vi.hoisted(() => ({ catalog: vi.fn(), save: vi.fn(), history: vi.fn() }))
vi.mock('@/api/customerOrderProducts', () => ({ customerOrderProductsApi: api }))
const preview = { factory_id: 'huaxing', customer_code: 'dickie', preview_fingerprint: 'test-fingerprint',
  rows: [{ id: 'row1', product_no: '000123', product_name_zh: '', product_name_en: 'CURRENT PO NAME', units_per_carton: '12',
           item_sheet_name: '', issues: [{ code: 'unmapped_item_sheet' }] }],
  product_registration: { available: true, revision: 3, sha256: 'test', sheets: ['ITEM表', '恐龙蛋口水车Iteam表'], choices: [], applied: [], conflicts: [] },
} as unknown as CustomerOrderImportPreview
const catalog = { available: true, revision: 3, sha256: 'test', products: {}, can_write: true }
const button = (w: ReturnType<typeof mount>, label: string) => w.findAll('button').find(b => b.text() === label)!
async function open() {
  const w = mount(ProductRegistration, { props: { preview: structuredClone(preview), busy: false } })
  await flushPromises(); return w
}
async function fill(w: ReturnType<typeof mount>) {
  await w.get('select[aria-label="目标ITEM分类"]').setValue('ITEM表')
  await w.get('textarea[aria-label="产品核对原因"]').setValue('业务确认分类正确')
}
beforeEach(() => {
  vi.resetAllMocks()
  api.catalog.mockResolvedValue(structuredClone(catalog))
  api.history.mockResolvedValue({ total: 0, items: [] })
  api.save.mockResolvedValue({ ...catalog, revision: 4 })
})
describe('DickieProductRegistration', () => {
  it('loads only the scoped customer and never another factory', async () => {
    const w = mount(ProductRegistration, { props: { preview: { ...preview, factory_id: 'huakang-a' }, busy: false } })
    await flushPromises()
    expect(api.catalog).not.toHaveBeenCalled()
    expect(w.find('[data-testid="dickie-product-registration"]').exists()).toBe(false)
    w.unmount()
  })
  it('needs explicit classification and a reason for one-off use, never saves it', async () => {
    const w = await open()
    expect(button(w, '仅本次应用并重新预览').attributes('disabled')).toBeDefined()
    await fill(w)
    await w.get('input[aria-label="产品中文名称"]').setValue('测试产品')
    await button(w, '仅本次应用并重新预览').trigger('click')
    expect(api.save).not.toHaveBeenCalled()
    expect(w.emitted('apply')?.[0]?.[0]).toEqual([{ product_no: '000123', item_sheet_name: 'ITEM表',
      product_name_zh: '测试产品', product_name_en: 'CURRENT PO NAME', default_pack: '12', reason: '业务确认分类正确' }])
    w.unmount()
  })
  it('saves with the current version, can disable without deleting and refreshes preview', async () => {
    const w = await open(); await fill(w)
    await w.get('input[aria-label="启用货号规则"]').setValue(false)
    await button(w, '保存规则并重新预览').trigger('click'); await flushPromises()
    expect(api.save.mock.calls[0]![0]).toMatchObject({ expected_revision: 3, active: false, product_no: '000123', reason: '业务确认分类正确' })
    expect(w.emitted('refresh')).toHaveLength(1)
    w.unmount()
  })
  it('allows read-only one-off review but hides public-rule writes', async () => {
    api.catalog.mockResolvedValue({ ...catalog, can_write: false })
    const w = await open(); await fill(w)
    expect(w.text()).not.toContain('保存规则并重新预览')
    expect(button(w, '仅本次应用并重新预览').attributes('disabled')).toBeUndefined()
    w.unmount()
  })
  it('does not expose write controls before migration', async () => {
    api.catalog.mockResolvedValue({ ...catalog, available: false, can_write: false })
    const w = mount(ProductRegistration, { props: { preview: { ...preview, product_registration: { ...preview.product_registration!, available: false } }, busy: false } })
    await flushPromises()
    expect(w.text()).toContain('尚未执行迁移')
    expect(w.find('textarea[aria-label="产品核对原因"]').exists()).toBe(false)
    w.unmount()
  })
  it('refuses a stale catalog without enabling edits', async () => {
    api.catalog.mockResolvedValue({ ...catalog, revision: 4 })
    const w = await open()
    expect(w.text()).toContain('货号规则已更新')
    expect(w.find('textarea[aria-label="产品核对原因"]').exists()).toBe(false)
    w.unmount()
  })
  it('retains failed-save input but cannot overwrite after a concurrent change', async () => {
    api.save.mockRejectedValue({ isAxiosError: true, response: { status: 409, data: { detail: '货号规则已被更新' } } })
    const w = await open(); await fill(w)
    await button(w, '保存规则并重新预览').trigger('click'); await flushPromises()
    expect(w.text()).toContain('货号规则已被更新')
    expect((w.get('textarea[aria-label="产品核对原因"]').element as HTMLTextAreaElement).value).toBe('业务确认分类正确')
    expect(w.emitted('refresh')).toBeUndefined()
    w.unmount()
  })
  it('aborts obsolete reads on a factory change and does not accept a late response', async () => {
    let finish: ((v: typeof catalog) => void) | undefined
    api.catalog.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const w = mount(ProductRegistration, { props: { preview, busy: false } })
    await flushPromises()
    const signal = api.catalog.mock.calls[0]![0] as AbortSignal
    await w.setProps({ preview: { ...preview, factory_id: 'huakang-a' } })
    expect(signal.aborted).toBe(true)
    finish?.(catalog); await flushPromises()
    expect(w.text()).not.toContain('000123')
    expect(api.history).not.toHaveBeenCalled()
    w.unmount()
  })
  it('guards duplicate save clicks and respects other work in progress', async () => {
    const w = await open(); await fill(w)
    let finish: ((v: typeof catalog) => void) | undefined
    api.save.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    await button(w, '保存规则并重新预览').trigger('click')
    await button(w, '正在保存…').trigger('click')
    expect(api.save).toHaveBeenCalledTimes(1)
    finish?.(catalog); await flushPromises()
    await w.setProps({ busy: true })
    expect(button(w, '仅本次应用并重新预览').attributes('disabled')).toBeDefined()
    w.unmount()
  })
})
