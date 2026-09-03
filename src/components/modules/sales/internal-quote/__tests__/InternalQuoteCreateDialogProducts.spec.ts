import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import type { InternalQuoteCreatePayload } from '@/types/internalQuoteDesk'
import InternalQuoteCreateDialog from '../InternalQuoteCreateDialog.vue'

let wrapper: VueWrapper
afterEach(() => wrapper?.unmount())

async function createDialog() {
  wrapper = mount(InternalQuoteCreateDialog, {
    props: { open: true, mode: 'create', factoryId: 'huakang-b', customers: ['JustPlay', '普通客'],
      businessOwners: [{ id: 'owner', username: 'owner', displayName: '业务主管' }] },
    global: { stubs: { Teleport: true } },
  })
  await flushPromises()
  await wrapper.get('input[placeholder="例如 IQ-HX-2026-0716-06"]').setValue('IQ-JP-SERIES')
  await wrapper.get('.quote-product-name input').setValue('A款')
  return wrapper
}

function names(index: number) {
  return wrapper.findAll('.quote-product-components')[index]!.findAll('input[type="text"]')
    .map(input => (input.element as HTMLInputElement).value)
}
async function addProduct() {
  await wrapper.findAll('button').find(button => button.text() === '新增产品')!.trigger('click')
}

describe('JustPlay per-product component creation', () => {
  it('binds images to the selected component and does not copy them to B', async () => {
    await createDialog()
    await wrapper.get('input[value="series"]').setValue(true)
    await wrapper.get('[aria-label="第 1 款配件个数"]').setValue('2')
    const file = new File(['image'], '镜子.png', { type: 'image/png' })
    const input = wrapper.get('[aria-label="第 1 款配件2图片"]')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    await wrapper.get('[aria-label="移除第 1 款配件 1"]').trigger('click')
    expect(wrapper.get('.quote-component-asset').text()).not.toContain('镜子.png')
    await addProduct()
    await wrapper.findAll('.quote-product-name input')[1]!.setValue('B款')
    await wrapper.get('.quote-primary-button').trigger('click')
    const payload = wrapper.emitted('confirm')![0]![0] as InternalQuoteCreatePayload
    expect(payload.products![0]!.componentImageFiles?.[1]).toBe(file)
    expect(payload.products![1]!.componentImageFiles).toBeUndefined()
    expect(payload.products![0]!.imageFile).toBeNull()
    expect(wrapper.find('.quote-product-image').exists()).toBe(false)
  })
  it('copies the current first product into B and C, while keeping all edits independent', async () => {
    await createDialog()
    await wrapper.get('input[value="series"]').setValue(true)
    await wrapper.get('[aria-label="第 1 款配件个数"]').setValue('3')
    for (const [index, name] of ['镜子', '梳子', '发夹'].entries()) {
      await wrapper.get(`[aria-label="第 1 款配件 ${index + 1}名称"]`).setValue(name)
    }
    await addProduct()
    expect(names(1)).toEqual(['主体', '镜子', '梳子', '发夹'])
    await wrapper.get('[aria-label="第 2 款配件 1名称"]').setValue('B款镜子')
    await wrapper.get('[aria-label="第 2 款配件个数"]').setValue('1')
    await wrapper.get('[aria-label="第 1 款配件 2名称"]').setValue('A款梳子')
    await addProduct()
    expect(names(0)).toEqual(['主体', '镜子', 'A款梳子', '发夹'])
    expect(names(1)).toEqual(['主体', 'B款镜子'])
    expect(names(2)).toEqual(names(0))
    await wrapper.get('[aria-label="第 3 款配件 1名称"]').setValue('C款镜子')
    expect(names(0)[1]).toBe('镜子')
    const products = wrapper.findAll('.quote-product-name input')
    await products[1]!.setValue('B款')
    await products[2]!.setValue('C款')
    await wrapper.get('.quote-primary-button').trigger('click')
    const payload = wrapper.emitted('confirm')![0]![0] as InternalQuoteCreatePayload
    expect(payload.products?.map(product => product.pricingComponents)).toEqual([
      ['主体', '镜子', 'A款梳子', '发夹'], ['主体', 'B款镜子'], ['主体', 'C款镜子', 'A款梳子', '发夹'],
    ])
  })

  it('supports zero through 49 accessories without removing the main component', async () => {
    await createDialog()
    await wrapper.get('[aria-label="第 1 款配件个数"]').setValue('0')
    expect(names(0)).toEqual(['主体'])
    expect(wrapper.find('[aria-label="移除第 1 款配件 0"]').exists()).toBe(false)
    await wrapper.get('[aria-label="第 1 款配件个数"]').setValue('49')
    expect(names(0)).toHaveLength(50)
    expect(wrapper.findAll('button').find(button => button.text() === '新增配件')!.attributes('disabled')).toBeDefined()
  })

  it('rejects blank or duplicate names within a product instead of silently reducing the count', async () => {
    await createDialog()
    await wrapper.get('[aria-label="第 1 款配件 1名称"]').setValue(' ')
    await wrapper.get('.quote-primary-button').trigger('click')
    expect(wrapper.emitted('confirm')).toBeUndefined()
    expect(wrapper.text()).toContain('第 1 款必须填写主体及配件名称')
    await wrapper.get('[aria-label="第 1 款配件 1名称"]').setValue('主体')
    await wrapper.get('.quote-primary-button').trigger('click')
    expect(wrapper.text()).toContain('第 1 款的 JustPlay 分项名称不能重复')
  })

  it('initializes components again when reopening with the same customer', async () => {
    await createDialog()
    await wrapper.get('[aria-label="第 1 款配件个数"]').setValue('3')
    await wrapper.setProps({ open: false })
    await wrapper.setProps({ open: true })
    expect(names(0)).toEqual(['主体', '配件1'])
  })

  it('does not send JustPlay components after switching to an ordinary customer', async () => {
    await createDialog()
    await wrapper.findAll('.quote-form-grid select')[0]!.setValue('普通客')
    expect(wrapper.find('.quote-product-components').exists()).toBe(false)
    await wrapper.get('.quote-primary-button').trigger('click')
    const payload = wrapper.emitted('confirm')![0]![0] as InternalQuoteCreatePayload
    expect(payload.products![0]!.pricingComponents).toBeUndefined()
    expect(payload.pricingComponents).toEqual([])
  })

  it('also gives multi-region products independent copies', async () => {
    await createDialog()
    await wrapper.get('[aria-label="第 1 款配件 1名称"]').setValue('镜子')
    await wrapper.get('input[value="multi_region"]').setValue(true)
    expect(names(1)).toEqual(['主体', '镜子'])
    await wrapper.get('[aria-label="第 2 款配件 1名称"]').setValue('印尼配件')
    expect(names(0)).toEqual(['主体', '镜子'])
  })
})
