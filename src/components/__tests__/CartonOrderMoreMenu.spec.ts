import { defineComponent, ref } from 'vue'
import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import CartonOrderMoreMenu from '../CartonOrderMoreMenu.vue'
import CartonOrderMenuItem from '../CartonOrderMenuItem.vue'

const Harness = defineComponent({
  components: { CartonOrderMoreMenu, CartonOrderMenuItem },
  props: { disabled: Boolean },
  emits: ['action'],
  setup() { return { open: ref(false) } },
  template: `<CartonOrderMoreMenu v-model:open="open" order-no="ORDER-1" :disabled="disabled">
    <CartonOrderMenuItem disabled @select="$emit('action', 'edit')">修改订单</CartonOrderMenuItem>
    <CartonOrderMenuItem tone="teal" @select="$emit('action', 'copy')">复制订单信息</CartonOrderMenuItem>
    <CartonOrderMenuItem tone="danger" @select="$emit('action', 'cancel')">取消订单</CartonOrderMenuItem>
  </CartonOrderMoreMenu>`,
})

describe('shared carton order More menu', () => {
  let wrapper: ReturnType<typeof mount> | undefined
  afterEach(() => { wrapper?.unmount(); wrapper = undefined })

  it('opens by keyboard, skips unavailable actions and restores focus on Escape', async () => {
    wrapper = mount(Harness, { attachTo: document.body })
    const trigger = wrapper.get('button')
    ;(trigger.element as HTMLButtonElement).focus()
    await trigger.trigger('keydown', { key: 'ArrowDown' })
    await flushPromises()
    const body = new DOMWrapper(document.body)
    const items = body.findAll('[role="menuitem"]')
    expect(items[0]!.attributes('disabled')).toBeDefined()
    await items[0]!.trigger('click')
    expect(wrapper.emitted('action')).toBeUndefined()
    const menu = body.get('[role="menu"]')
    ;(menu.element as HTMLElement).focus()
    await vi.waitFor(() => expect(document.activeElement).toBe(items[1]!.element))
    await items[1]!.trigger('keydown', { key: 'ArrowDown' })
    await vi.waitFor(() => expect(document.activeElement).toBe(items[2]!.element))
    await body.get('[role="menu"]').trigger('keydown', { key: 'Escape' })
    await flushPromises()
    expect(body.find('[role="menu"]').exists()).toBe(false)
    await vi.waitFor(() => expect(document.activeElement).toBe(trigger.element))
    expect(wrapper.emitted('action')).toBeUndefined()
  })

  it('dispatches one selected action and closes the controlled menu', async () => {
    wrapper = mount(Harness, { attachTo: document.body })
    await wrapper.get('button').trigger('keydown', { key: 'Enter' })
    await flushPromises()
    const body = new DOMWrapper(document.body)
    await body.findAll('[role="menuitem"]')[1]!.trigger('click')
    await flushPromises()
    expect(wrapper.emitted('action')).toEqual([['copy']])
    expect(body.find('[role="menu"]').exists()).toBe(false)
  })

  it('closes an open menu when the action group becomes unavailable', async () => {
    wrapper = mount(Harness, { attachTo: document.body })
    await wrapper.get('button').trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(document.querySelector('[role="menu"]')).not.toBeNull()
    await wrapper.setProps({ disabled: true })
    await flushPromises()
    expect(document.querySelector('[role="menu"]')).toBeNull()
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    expect(wrapper.emitted('action')).toBeUndefined()
  })
})
