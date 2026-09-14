import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it } from 'vitest'
import UvDrawer from '../components/UvDrawer.vue'

describe('UV lazy drawer keyboard lifecycle', () => {
  it('initially open drawer handles Escape and restores focus when unmounted', async () => {
    const trigger = document.createElement('button')
    document.body.append(trigger)
    trigger.focus()
    const wrapper = mount(UvDrawer, { props: { open: true, title: '报工' }, attachTo: document.body })
    await nextTick()
    expect(document.activeElement?.getAttribute('role')).toBe('dialog')
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(wrapper.emitted('close')).toHaveLength(1)
    wrapper.unmount()
    expect(document.activeElement).toBe(trigger)
    trigger.remove()
  })
})
