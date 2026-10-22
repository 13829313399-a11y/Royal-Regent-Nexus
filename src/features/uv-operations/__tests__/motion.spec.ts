import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { provideUvMotionPreference } from '../composables/useUvMotionPreference'
import { useUvPresence } from '../composables/useUvPresence'

describe('UV motion preference and interrupted presentation', () => {
  let media: EventTarget & { matches: boolean }
  beforeEach(() => {
    localStorage.clear()
    media = Object.assign(new EventTarget(), { matches: false })
    vi.stubGlobal('matchMedia', vi.fn(() => media))
    vi.spyOn(document, 'hidden', 'get').mockReturnValue(false)
  })
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })

  it('isolates account preferences, rejects stored garbage, and responds to system/visibility changes', async () => {
    const user = ref<string|null>('a')
    let motion!: ReturnType<typeof provideUvMotionPreference>
    const wrapper = mount(defineComponent({ setup() { motion = provideUvMotionPreference(() => user.value); return () => h('div') } }))
    expect(motion.allowed.value).toBe(true)
    motion.setPreference('off')
    expect(localStorage.getItem('rr.uv.motion.v1.a')).toBe('off')
    user.value = 'b'; await nextTick(); expect(motion.allowed.value).toBe(true)
    localStorage.setItem('rr.uv.motion.v1.c', 'force-on')
    user.value = 'c'; await nextTick(); expect(motion.preference.value).toBe('system')
    media.matches = true; media.dispatchEvent(new Event('change')); expect(motion.allowed.value).toBe(false)
    media.matches = false; media.dispatchEvent(new Event('change'))
    vi.spyOn(document, 'hidden', 'get').mockReturnValue(true)
    document.dispatchEvent(new Event('visibilitychange')); expect(motion.allowed.value).toBe(false)
    user.value = 'a'; await nextTick(); expect(motion.preference.value).toBe('off')
    const remove = vi.spyOn(media, 'removeEventListener'), docRemove = vi.spyOn(document, 'removeEventListener')
    wrapper.unmount()
    expect(remove).toHaveBeenCalledWith('change', expect.any(Function))
    expect(docRemove).toHaveBeenCalledWith('visibilitychange', expect.any(Function))
  })

  it('falls back to per-account memory when storage is unavailable, with no anonymous disk writes', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('disabled') })
    const write = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('disabled') })
    const user = ref<string|null>(null)
    let motion!: ReturnType<typeof provideUvMotionPreference>
    const wrapper = mount(defineComponent({ setup() { motion = provideUvMotionPreference(() => user.value); return () => h('div') } }))
    motion.setPreference('off'); expect(write).not.toHaveBeenCalled()
    user.value = 'a'; await nextTick(); expect(motion.preference.value).toBe('system')
    motion.setPreference('off'); user.value = 'b'; await nextTick(); user.value = 'a'; await nextTick()
    expect(motion.preference.value).toBe('off'); wrapper.unmount()
  })

  it('cancels old close callbacks on reopen and settles immediately when motion is turned off', async () => {
    vi.useFakeTimers()
    let motion!: ReturnType<typeof provideUvMotionPreference>, presence!: ReturnType<typeof useUvPresence>
    const Child = defineComponent({ setup() { const element = ref<HTMLElement|null>(null); presence = useUvPresence(element); return () => h('div', { ref: element, style: '--uv-motion-dialog-enter:240ms;--uv-motion-leave:180ms' }) } })
    const wrapper = mount(defineComponent({ setup() { motion = provideUvMotionPreference(() => 'a'); return () => h(Child) } }), { attachTo: document.body })
    const staleClose = vi.fn(), close = vi.fn()
    presence.open(); await nextTick(); presence.close(staleClose); await nextTick()
    expect(presence.present.value).toBe(true)
    presence.open(); await nextTick(); await vi.advanceTimersByTimeAsync(300)
    expect(staleClose).not.toHaveBeenCalled(); expect(presence.phase.value).toBe('open')
    presence.close(close); await nextTick(); motion.setPreference('off')
    expect(presence.present.value).toBe(false); expect(close).toHaveBeenCalledTimes(1)
    motion.setPreference('system'); presence.open(); await nextTick()
    presence.close(staleClose); await nextTick(); wrapper.unmount()
    await vi.advanceTimersByTimeAsync(1000)
    expect(staleClose).not.toHaveBeenCalled(); expect(close).toHaveBeenCalledTimes(1)
  })

  it('keeps the newer memory preference when reads work but quota rejects writes', async () => {
    localStorage.setItem('rr.uv.motion.v1.quota-user', 'system')
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota') })
    const user=ref('quota-user')
    let motion!: ReturnType<typeof provideUvMotionPreference>
    const wrapper=mount(defineComponent({setup(){motion=provideUvMotionPreference(()=>user.value);return()=>h('div')}}))
    motion.setPreference('off');user.value='other';await nextTick();user.value='quota-user';await nextTick()
    expect(motion.preference.value).toBe('off');wrapper.unmount()
  })
})
