import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick, ref } from 'vue'
import { Boxes } from '@lucide/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { HomeMotion } from '@/composables/useHomeAppearance'
import { useDetailMotion } from '../useDetailMotion'

function setup() {
  const mode = ref<HomeMotion>('expressive'), viewer = ref('A')
  let motion!: ReturnType<typeof useDetailMotion>
  const wrapper = mount(defineComponent({ setup() {
    motion = useDetailMotion(mode, () => viewer.value)
    return () => h('main', [h('span', { id: 'row' }), h('span', { id: 'detail' })])
  } }), { attachTo: document.body })
  vi.spyOn(HTMLElement.prototype, 'getClientRects').mockReturnValue([{}] as unknown as DOMRectList)
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
    const x = this.id === 'row' ? 40 : 280, y = 120
    return { x, y, top: y, left: x, width: 32, height: 32, right: x + 32, bottom: y + 32, toJSON: () => ({ x, y }) }
  })
  const descriptor = Object.getOwnPropertyDescriptor(Element.prototype, 'animate')
  Object.defineProperty(Element.prototype, 'animate', { configurable: true,
    value: () => ({ finished: new Promise(() => {}), cancel() {} }) })
  const row = wrapper.get('#row').element as HTMLElement, detail = wrapper.get('#detail').element as HTMLElement
  const launch = () => { motion.select('a', row, Boxes); motion.arrive('a', detail) }
  const layers = () => document.querySelectorAll('.rr-detail-glyph').length
  function dispose() {
    wrapper.unmount()
    if (descriptor) Object.defineProperty(Element.prototype, 'animate', descriptor)
    else Reflect.deleteProperty(Element.prototype, 'animate')
  }
  return { mode, viewer, row, detail, motion, launch, layers, dispose }
}
afterEach(() => vi.restoreAllMocks())

describe('local list and detail motion', () => {
  it('accepts only a confirmed matching row and has one cancellable return', () => {
    const t = setup()
    try {
      t.motion.arrive('a', t.detail); expect(t.layers()).toBe(0)
      t.motion.select('a', t.row, Boxes); t.motion.arrive('b', t.detail); expect(t.layers()).toBe(0)
      t.motion.arrive('a', t.detail); expect(t.layers()).toBe(1)
      t.motion.depart('a', t.detail); t.motion.invalidate('a'); expect(t.layers()).toBe(1)
      document.dispatchEvent(new Event('keydown')); expect(t.layers()).toBe(0)
      t.motion.depart('a', t.detail); expect(t.layers()).toBe(0)
    } finally { t.dispose() }
  })
  it('releases a removed detail and forgets a selection revoked by the business owner', async () => {
    const t = setup()
    try {
      t.launch(); expect(t.layers()).toBe(1)
      t.detail.remove(); await nextTick(); expect(t.layers()).toBe(0)
      t.motion.invalidate('a')
      t.row.after(t.detail); t.motion.arrive('a', t.detail); t.motion.depart('a', t.detail)
      expect(t.layers()).toBe(0)
    } finally { t.dispose() }
  })
  it('drops an in-flight glyph on preference or account changes and suppresses calm and off', () => {
    const t = setup()
    try {
      t.launch(); t.viewer.value = 'B'; expect(t.layers()).toBe(0)
      t.launch(); t.mode.value = 'off'; expect(t.layers()).toBe(0)
      t.launch(); expect(t.layers()).toBe(0)
      t.mode.value = 'calm'; t.launch(); expect(t.layers()).toBe(0)
    } finally { t.dispose() }
  })
})
