import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import InternalQuoteMaterialsDialog from '@/components/modules/sales/internal-quote/InternalQuoteMaterialsDialog.vue'

function mountDialog() {
  return mount(InternalQuoteMaterialsDialog, {
    props: {
      open: true,
      productName: '测试产品',
      snapshot: {
        material_prices: {
          'ABS|750SW': '8.50',
          'PP|5090T': '7.80',
        },
      },
    },
    global: { stubs: { Teleport: true } },
  })
}

describe('InternalQuoteMaterialsDialog', () => {
  it('supports explicit add, edit and delete actions before saving the whole material list', async () => {
    const wrapper = mountDialog()

    expect(wrapper.get('[data-testid="add-quote-material"]').isVisible()).toBe(true)
    expect(wrapper.text()).toContain('料价清单（2/200）')

    await wrapper.get('[data-testid="edit-quote-material-0"]').trigger('click')
    await wrapper.get('[data-testid="quote-material-name-0"]').setValue('ABS 改')
    await wrapper.get('[data-testid="quote-material-price-0"]').setValue('9.25')
    await wrapper.get('[data-testid="finish-quote-material-0"]').trigger('click')

    await wrapper.get('[data-testid="delete-quote-material-1"]').trigger('click')
    await wrapper.get('[data-testid="add-quote-material"]').trigger('click')
    await wrapper.get('[data-testid="quote-material-name-1"]').setValue('TPR')
    await wrapper.get('[data-testid="quote-material-grade-1"]').setValue('透明橡胶料')
    await wrapper.get('[data-testid="quote-material-price-1"]').setValue('17')
    await wrapper.get('[data-testid="finish-quote-material-1"]').trigger('click')
    await wrapper.get('[data-testid="save-quote-materials"]').trigger('click')

    expect(wrapper.emitted('save')).toEqual([[
      [
        { material: 'ABS 改', grade: '750SW', price_hkd_lb: '9.25' },
        { material: 'TPR', grade: '透明橡胶料', price_hkd_lb: '17' },
      ],
    ]])
  })

  it('restores an existing row or removes a new row when editing is cancelled', async () => {
    const wrapper = mountDialog()

    await wrapper.get('[data-testid="edit-quote-material-0"]').trigger('click')
    await wrapper.get('[data-testid="quote-material-name-0"]').setValue('不保存的修改')
    await wrapper.get('[data-testid="cancel-quote-material-0"]').trigger('click')
    expect(wrapper.text()).toContain('ABS')
    expect(wrapper.text()).not.toContain('不保存的修改')

    await wrapper.get('[data-testid="add-quote-material"]').trigger('click')
    expect(wrapper.get('[data-testid="quote-material-name-2"]').exists()).toBe(true)
    await wrapper.get('[data-testid="cancel-quote-material-2"]').trigger('click')
    expect(wrapper.find('[data-testid="edit-quote-material-2"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('料价清单（2/200）')
  })

  it('keeps a duplicate row in edit mode and shows a validation message', async () => {
    const wrapper = mountDialog()

    await wrapper.get('[data-testid="edit-quote-material-1"]').trigger('click')
    await wrapper.get('[data-testid="quote-material-name-1"]').setValue('ABS')
    await wrapper.get('[data-testid="quote-material-grade-1"]').setValue('750SW')
    await wrapper.get('[data-testid="finish-quote-material-1"]').trigger('click')

    expect(wrapper.get('[role="alert"]').text()).toContain('材质和料型组合不能重复')
    expect(wrapper.get('[data-testid="quote-material-name-1"]').exists()).toBe(true)
    expect(wrapper.emitted('save')).toBeUndefined()
  })
})
