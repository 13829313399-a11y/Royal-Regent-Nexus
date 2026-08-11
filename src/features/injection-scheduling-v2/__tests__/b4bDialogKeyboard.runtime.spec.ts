import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'

import ColumnPresetMenu from '../components/ColumnPresetMenu.vue'
import PublishPlanDialog from '../components/PublishPlanDialog.vue'
import { schedulingDefaultColumnOrder, schedulingPlannerColumnKeys } from '../composables/useSchedulingColumns'

const attached: Array<{ unmount: () => void }> = []

afterEach(() => {
  attached.splice(0).forEach((wrapper) => wrapper.unmount())
  document.body.innerHTML = ''
})

async function settleFocus() {
  await nextTick()
  await nextTick()
}

describe('B4b dialog and menu keyboard paths', () => {
  it('traps Tab in a dialog, closes on Escape, restores the opener and announces the dialog', async () => {
    const opener = document.createElement('button')
    opener.textContent = '发布计划'
    document.body.appendChild(opener)
    const wrapper = mount(PublishPlanDialog, {
      attachTo: document.body,
      global: { stubs: { Teleport: true } },
      props: { open: false, plan: null, taskCount: 1, canPublish: true, publishing: false, error: '' },
    })
    attached.push(wrapper)
    opener.focus()

    await wrapper.setProps({ open: true })
    await settleFocus()
    const closeButton = wrapper.get('button[aria-label="关闭发布确认"]')
    const confirmButton = wrapper.findAll('footer button')[1]!
    expect(document.activeElement).toBe(closeButton.element)
    expect(wrapper.get('[role="status"]').text()).toContain('发布确认已打开')

    ;(confirmButton.element as HTMLElement).focus()
    confirmButton.element.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true }))
    expect(document.activeElement).toBe(closeButton.element)

    ;(closeButton.element as HTMLElement).focus()
    closeButton.element.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true, cancelable: true }))
    expect(document.activeElement).toBe(confirmButton.element)

    closeButton.element.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }))
    expect(wrapper.emitted('close')).toHaveLength(1)
    await wrapper.setProps({ open: false })
    await settleFocus()
    expect(document.activeElement).toBe(opener)
  })

  it('does not close a busy dialog through Escape', async () => {
    const wrapper = mount(PublishPlanDialog, {
      attachTo: document.body,
      global: { stubs: { Teleport: true } },
      props: { open: true, plan: null, taskCount: 1, canPublish: true, publishing: true, error: '' },
    })
    attached.push(wrapper)
    await settleFocus()
    wrapper.get('.modal-backdrop').element.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }))
    expect(wrapper.emitted('close')).toBeUndefined()
  })

  it('adds menu semantics, Escape/focus recovery and outside-click close to column settings', async () => {
    const opener = document.createElement('button')
    opener.textContent = '列设置'
    document.body.appendChild(opener)
    const wrapper = mount(ColumnPresetMenu, {
      attachTo: document.body,
      props: {
        open: false,
        preset: 'planner',
        visibleKeys: [...schedulingPlannerColumnKeys],
        widths: {},
        columnOrder: schedulingDefaultColumnOrder,
      },
    })
    attached.push(wrapper)
    opener.focus()

    await wrapper.setProps({ open: true })
    await settleFocus()
    const menu = wrapper.get('[role="menu"]')
    const presetItems = wrapper.findAll('[role="menuitemradio"]')
    expect(menu.attributes('aria-label')).toBe('列设置菜单')
    expect(presetItems).toHaveLength(4)
    expect(presetItems[0]!.attributes('aria-checked')).toBe('true')
    expect(document.activeElement).toBe(presetItems[0]!.element)
    expect(wrapper.get('[role="status"]').text()).toContain('列设置菜单已打开')

    presetItems[0]!.element.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true, cancelable: true }))
    expect(document.activeElement).toBe(presetItems[1]!.element)
    const widthInput = wrapper.get<HTMLInputElement>('.width-input')
    widthInput.element.focus()
    const inputArrow = new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true, cancelable: true })
    widthInput.element.dispatchEvent(inputArrow)
    expect(inputArrow.defaultPrevented).toBe(false)
    expect(document.activeElement).toBe(widthInput.element)

    menu.element.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }))
    expect(wrapper.emitted('close')).toHaveLength(1)
    await wrapper.setProps({ open: false })
    await settleFocus()
    expect(document.activeElement).toBe(opener)

    opener.focus()
    await wrapper.setProps({ open: true })
    await settleFocus()
    const outsideButton = document.createElement('button')
    outsideButton.textContent = '其他操作'
    document.body.appendChild(outsideButton)
    outsideButton.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }))
    expect(wrapper.emitted('close')).toHaveLength(2)
    outsideButton.focus()
    await wrapper.setProps({ open: false })
    await settleFocus()
    expect(document.activeElement).toBe(outsideButton)
  })
})
