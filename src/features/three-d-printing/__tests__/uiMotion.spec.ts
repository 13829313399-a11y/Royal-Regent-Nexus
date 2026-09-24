import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import LegacyDialog from '../components/LegacyDialog.vue'
import TdpButton from '../components/TdpButton.vue'

type ControlledAnimation = Animation & { finish: () => void }
let animations: ControlledAnimation[] = []
let originalAnimate: PropertyDescriptor | undefined
let originalMatchMedia: typeof window.matchMedia | undefined

beforeEach(() => {
  animations = []
  originalAnimate = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'animate')
  originalMatchMedia = window.matchMedia
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) { this.setAttribute('open', '') })
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) { this.removeAttribute('open') })
  window.matchMedia = vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })) as unknown as typeof window.matchMedia
  Object.defineProperty(HTMLDialogElement.prototype, 'animate', {
    configurable: true,
    value: vi.fn(() => {
      const animation = {
        onfinish: null as Animation['onfinish'],
        oncancel: null as Animation['oncancel'],
        cancel: vi.fn(),
        finish() { animation.onfinish?.(new Event('finish') as AnimationPlaybackEvent) },
      } as ControlledAnimation
      animations.push(animation)
      return animation
    }),
  })
})

afterEach(() => {
  if (originalAnimate) Object.defineProperty(HTMLDialogElement.prototype, 'animate', originalAnimate)
  else Reflect.deleteProperty(HTMLDialogElement.prototype, 'animate')
  if (originalMatchMedia) window.matchMedia = originalMatchMedia
  vi.restoreAllMocks()
})

describe('3D printing UI controls', () => {
  it('keeps the submit type and blocks clicks while busy', async () => {
    const submit = vi.fn()
    const wrapper = mount({
      components: { TdpButton },
      data: () => ({ busy: false }),
      methods: { submit },
      template: '<form @submit.prevent="submit"><TdpButton type="submit" :busy="busy">保存</TdpButton></form>',
    }, { attachTo: document.body })
    const button = wrapper.get('button')
    expect(button.attributes('type')).toBe('submit')
    await button.trigger('click')
    expect(submit).toHaveBeenCalledTimes(1)
    await wrapper.setData({ busy: true })
    expect(button.attributes('disabled')).toBeDefined()
    expect(button.attributes('aria-busy')).toBe('true')
    await button.trigger('click')
    expect(submit).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('keeps a rejected close request open and emits after-close only after exit', async () => {
    const wrapper = mount(LegacyDialog, { props: { title: '编辑记录', open: false }, slots: { default: '原草稿' } })
    await wrapper.setProps({ open: true })
    await flushPromises()
    animations[0]?.finish()
    await wrapper.get('button[aria-label="关闭"]').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
    expect(wrapper.get('dialog').attributes('open')).toBeDefined()
    await wrapper.setProps({ open: false })
    await flushPromises()
    expect(wrapper.find('dialog').exists()).toBe(true)
    expect(wrapper.emitted('after-close')).toBeUndefined()
    expect(wrapper.text()).toContain('原草稿')
    animations.at(-1)?.finish()
    await flushPromises()
    expect(wrapper.find('dialog').exists()).toBe(false)
    expect(wrapper.emitted('after-close')).toHaveLength(1)
    wrapper.unmount()
  })

  it('cancels an old exit when reopened', async () => {
    const wrapper = mount(LegacyDialog, { props: { title: '编辑记录', open: false }, slots: { default: '新草稿' } })
    await wrapper.setProps({ open: true })
    await flushPromises()
    await wrapper.setProps({ open: false })
    await flushPromises()
    const oldExit = animations.at(-1)!
    await wrapper.setProps({ open: true })
    await flushPromises()
    oldExit.finish()
    await flushPromises()
    expect(wrapper.get('dialog').attributes('open')).toBeDefined()
    expect(wrapper.text()).toContain('新草稿')
    expect(wrapper.emitted('after-close')).toBeUndefined()
    wrapper.unmount()
  })

  it('closes directly with reduced motion', async () => {
    window.matchMedia = vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })) as unknown as typeof window.matchMedia
    const wrapper = mount(LegacyDialog, { props: { title: '编辑记录', open: false } })
    await wrapper.setProps({ open: true })
    await flushPromises()
    expect(wrapper.get('dialog').attributes('open')).toBeDefined()
    await wrapper.setProps({ open: false })
    await flushPromises()
    expect(wrapper.find('dialog').exists()).toBe(false)
    expect(wrapper.emitted('after-close')).toHaveLength(1)
    expect(animations).toHaveLength(0)
    wrapper.unmount()
  })
})
