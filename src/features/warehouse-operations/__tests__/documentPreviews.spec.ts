import { afterEach, describe, expect, it, vi } from 'vitest'
import { DOMWrapper, flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import WarehouseDocumentPreview from '@/features/warehouse-foundation/WarehouseDocumentPreview.vue'
import { warehouseDocumentSpec, type WarehousePreviewKind } from '../documentPreviews'

let wrapper: VueWrapper | undefined
afterEach(() => { wrapper?.unmount(); wrapper = undefined; document.body.innerHTML = ''; vi.restoreAllMocks() })
async function open(kind: WarehousePreviewKind, semi = false) {
  wrapper = mount(WarehouseDocumentPreview, { attachTo: document.body, props: { spec: warehouseDocumentSpec(semi, kind), warehouseTitle: semi ? '半成品仓' : '布料仓' } })
  await flushPromises()
  return new DOMWrapper(document.body)
}
async function click(body: DOMWrapper<Element>, text: string) {
  await body.findAll('button').find(button => button.text() === text)!.trigger('click')
  await flushPromises()
}
function fact(body: DOMWrapper<Element>, label: string) {
  return body.findAll('dt').find(term => term.text() === label)!.element.nextElementSibling?.textContent
}

describe('fabric document previews', () => {
  it('preserves split receipts, original units and leading-zero roll codes through detail view and row deletion', async () => {
    const body = await open('receipt')
    await body.get('select[aria-label="物料分类"]').setValue('布料')
    await body.get('input[aria-label="送货单日期"]').setValue('2026-09-14')
    await body.get('input[aria-label="收货日期"]').setValue('2026-09-15')
    await body.get('input[aria-label="记账月份"]').setValue('2026-09')
    let first = body.get('fieldset[aria-label="分仓明细 1"]')
    await first.get('input[aria-label="卷号 / 包号"]').setValue('0001')
    await first.get('input[aria-label="该行实收数量"]').setValue('176')
    await first.get('input[aria-label="明细计量单位"]').setValue('码')
    await click(body, '添加分仓明细')
    const second = body.get('fieldset[aria-label="分仓明细 2"]')
    await second.get('input[aria-label="卷号 / 包号"]').setValue('0002')
    await second.get('input[aria-label="该行实收数量"]').setValue('170.25')
    await second.get('input[aria-label="明细计量单位"]').setValue('千克')
    await click(body, '查看填写内容')
    expect(fact(body, '送货单日期')).toBe('2026-09-14')
    expect(fact(body, '收货日期')).toBe('2026-09-15')
    expect(fact(body, '记账月份')).toBe('2026-09')
    expect(body.get('fieldset[aria-label="分仓明细 1"]').text()).toContain('0001')
    expect(body.get('fieldset[aria-label="分仓明细 2"]').text()).toContain('170.25')
    expect(body.get('fieldset[aria-label="分仓明细 2"]').text()).toContain('千克')
    expect(fact(body, '本次实收数量')).toBe('未填写')
    await click(body, '返回填写')
    first = body.get('fieldset[aria-label="分仓明细 1"]')
    await first.get('button[aria-label="移除分仓明细 1"]').trigger('click')
    expect(body.get('[role="alert"]').text()).toContain('已有填写')
    await click(body, '保留明细')
    expect(body.findAll('fieldset')).toHaveLength(2)
    await first.get('button[aria-label="移除分仓明细 1"]').trigger('click')
    await click(body, '确认移除')
    expect(body.findAll('fieldset')).toHaveLength(1)
    expect(body.get<HTMLInputElement>('input[aria-label="卷号 / 包号"]').element.value).toBe('0002')
    expect(body.get<HTMLInputElement>('input[aria-label="该行实收数量"]').element.value).toBe('170.25')
  })

  it('treats a zero entered only in a split row as content that must be protected on close', async () => {
    const body = await open('receipt')
    await body.get('input[aria-label="该行实收数量"]').setValue('0')
    expect((wrapper!.vm as unknown as { hasChanges: () => boolean }).hasChanges()).toBe(true)
    await click(body, '查看填写内容')
    expect(fact(body, '该行实收数量')).toBe('0')
    expect(fact(body, '本次实收数量')).toBe('未填写')
    await body.get('[aria-label="关闭单据预览"]').trigger('click')
    expect(wrapper!.emitted('close')).toBeUndefined()
    expect(body.get('[role="alert"]').text()).toContain('清空')
    await click(body, '关闭并清空')
    expect(wrapper!.emitted('close')).toHaveLength(1)
  })

  it('can remove all untouched rows and add a fresh blank row without inventing a zero quantity', async () => {
    const body = await open('receipt')
    await body.get('[aria-label="移除分仓明细 1"]').trigger('click')
    expect(body.findAll('fieldset')).toHaveLength(0)
    expect(body.text()).toContain('尚未填写分仓明细')
    expect((wrapper!.vm as unknown as { hasChanges: () => boolean }).hasChanges()).toBe(false)
    await click(body, '添加分仓明细')
    expect(body.get<HTMLInputElement>('input[aria-label="该行实收数量"]').element.value).toBe('')
  })

  it('keeps multiple demand allocations separate from the physical issue and never writes browser storage', async () => {
    const persist = vi.spyOn(Storage.prototype, 'setItem')
    const body = await open('issue')
    await body.get('select[aria-label="发料用途"]').setValue('加工发出')
    await body.get('input[aria-label="本次实发数量"]').setValue('100')
    await body.get('input[aria-label="该行实发数量"]').setValue('100')
    const first = body.get('fieldset[aria-label="用料分配 1"]')
    await first.get('input[aria-label="放产单号"]').setValue('FC-001')
    await first.get('input[aria-label="本次分配数量"]').setValue('40')
    await click(body, '添加用料分配')
    const second = body.get('fieldset[aria-label="用料分配 2"]')
    await second.get('input[aria-label="放产单号"]').setValue('FC-002')
    await second.get('input[aria-label="本次分配数量"]').setValue('60')
    await click(body, '查看填写内容')
    expect(fact(body, '本次实发数量')).toBe('100')
    expect(body.get('fieldset[aria-label="用料分配 1"]').text()).toContain('FC-001')
    expect(body.get('fieldset[aria-label="用料分配 2"]').text()).toContain('FC-002')
    expect(body.findAll('fieldset[aria-label^="发出明细"]')).toHaveLength(1)
    expect(persist).not.toHaveBeenCalled()
  })

  it('retains separate stock states and distinguishes an unknown price from a deliberately entered zero', async () => {
    const body = await open('stock')
    await body.get('select[aria-label="物料分类"]').setValue('线')
    await body.get('select[aria-label="质量情况"]').setValue('待检')
    await body.get('select[aria-label="暂停情况"]').setValue('已记录暂停')
    await body.get('select[aria-label="订单归属情况"]').setValue('共用物料')
    await click(body, '查看填写内容')
    expect(fact(body, '参考单价')).toBe('未填写')
    expect(fact(body, '账面数量')).toBe('未填写')
    expect(fact(body, '质量情况')).toBe('待检')
    expect(fact(body, '暂停情况')).toBe('已记录暂停')
    expect(fact(body, '订单归属情况')).toBe('共用物料')
    await click(body, '返回填写')
    await body.get('input[aria-label="参考单价"]').setValue('0')
    await click(body, '查看填写内容')
    expect(fact(body, '参考单价')).toBe('0')
    expect(fact(body, '币种')).toBe('未填写')
  })

  it('retains the existing semi-finished task and process fields without adding fabric rows', async () => {
    const body = await open('receipt', true)
    expect(body.find('input[aria-label="加工任务 / 原发出单"]').exists()).toBe(true)
    expect(body.find('input[aria-label="本轮交接编号"]').exists()).toBe(true)
    expect(body.find('input[aria-label="缸号"]').exists()).toBe(false)
    expect(body.find('select[aria-label="物料分类"]').exists()).toBe(false)
    expect(body.findAll('fieldset')).toHaveLength(0)
  })
})
