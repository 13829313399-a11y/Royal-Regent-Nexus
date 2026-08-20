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
  it('immediately saves an edited row without closing the dialog', async () => {
    const wrapper = mountDialog()

    expect(wrapper.get('[data-testid="add-quote-material"]').isVisible()).toBe(true)
    expect(wrapper.text()).toContain('料价清单（2/200）')

    await wrapper.get('[data-testid="edit-quote-material-0"]').trigger('click')
    expect(wrapper.get('[data-testid="quote-material-price-0"]').attributes('step')).toBe('0.001')
    expect(wrapper.get('[data-testid="quote-material-price-0"]').attributes('min')).toBe('0.001')
    await wrapper.get('[data-testid="quote-material-name-0"]').setValue('ABS 改')
    await wrapper.get('[data-testid="quote-material-price-0"]').setValue('9.25')
    await wrapper.get('[data-testid="finish-quote-material-0"]').trigger('click')

    expect(wrapper.emitted('save')).toEqual([[
      [
        { material: 'ABS 改', grade: '750SW', price_hkd_lb: '9.25' },
        { material: 'PP', grade: '5090T', price_hkd_lb: '7.80' },
      ],
      { closeAfter: false },
    ]])
  })

  it('uses the footer action to save batch changes and close after success', async () => {
    const wrapper = mountDialog()

    await wrapper.get('[data-testid="delete-quote-material-1"]').trigger('click')
    await wrapper.get('[data-testid="save-quote-materials"]').trigger('click')

    expect(wrapper.emitted('save')).toEqual([[
      [{ material: 'ABS', grade: '750SW', price_hkd_lb: '8.50' }],
      { closeAfter: true },
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

  it('shows a server save error inside the dialog', () => {
    const wrapper = mount(InternalQuoteMaterialsDialog, {
      props: {
        open: true,
        productName: '测试产品',
        snapshot: { material_prices: { 'ABS|750SW': '8.50' } },
        externalError: '服务器保存失败，请重试。',
      },
      global: { stubs: { Teleport: true } },
    })

    expect(wrapper.get('[role="alert"]').text()).toContain('服务器保存失败')
  })
})
