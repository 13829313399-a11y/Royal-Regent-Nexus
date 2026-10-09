import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import AssistantHost from '../AssistantHost.vue'
import { assistantApi } from '../api'
import type { Capabilities } from '../types'

vi.mock('vue-router', () => ({ useRoute: () => ({ name: 'dashboard', query: {}, meta: { title: '合成页面' } }) }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ currentUser: { id: 'test', identity: { employment_epoch: 1 } }, authorizationVersion: 1 }) }))
vi.mock('@/stores/app', () => ({ useAppStore: () => ({ activeFactoryId: 'group' }) }))
const PanelStub = defineComponent({
  props: ['mode', 'focusOnOpen'], emits: ['pointer-enter', 'pointer-leave', 'focus-change'],
  template: `<section data-test="panel" v-show="mode !== 'edge'" :data-autofocus="focusOnOpen" @pointerenter="$emit('pointer-enter', $event)" @pointerleave="$emit('pointer-leave', $event)"><input @focus="$emit('focus-change', true)" @blur="$emit('focus-change', false)" /></section>`,
})
let host: ReturnType<typeof mount>
const launcher = () => document.querySelector<HTMLButtonElement>('.yl-launcher')!
const panel = () => document.querySelector<HTMLElement>('[data-test="panel"]')!
async function pointer(el: Element, type: string, pointerType = 'mouse') {
  el.dispatchEvent(new PointerEvent(type, { pointerType, bubbles: false })); await nextTick()
}
async function tick(ms: number) { await vi.advanceTimersByTimeAsync(ms); await flushPromises() }
beforeEach(async () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  setActivePinia(createPinia()); localStorage.clear()
  Object.defineProperty(window, 'innerWidth', { value: 1280, writable: true, configurable: true })
  vi.spyOn(assistantApi, 'capabilities').mockResolvedValue({ enabled: true } as Capabilities)
  host = mount(AssistantHost, { attachTo: document.body, global: { stubs: { Panel: PanelStub } } })
  await flushPromises()
})
afterEach(() => { host.unmount(); document.body.innerHTML = ''; vi.useRealTimers(); vi.restoreAllMocks() })

describe('edge reveal', () => {
  it('starts collapsed, reveals on hover without stealing focus, and closes after leaving', async () => {
    expect(launcher().getAttribute('aria-expanded')).toBe('false')
    await pointer(launcher(), 'pointerenter'); await tick(150)
    expect(launcher().getAttribute('aria-expanded')).toBe('false')
    await tick(30)
    expect(launcher().getAttribute('aria-expanded')).toBe('true')
    expect(panel().dataset.autofocus).toBe('false')
    await pointer(launcher(), 'pointerleave'); await tick(550)
    expect(launcher().getAttribute('aria-expanded')).toBe('false')
  })
  it('allows crossing into the panel and cancels a pending collapse on re-entry', async () => {
    await pointer(launcher(), 'pointerenter'); await tick(180)
    await pointer(launcher(), 'pointerleave'); await tick(300)
    await pointer(panel(), 'pointerenter'); await tick(600)
    expect(launcher().getAttribute('aria-expanded')).toBe('true')
    await pointer(panel(), 'pointerleave'); await tick(300)
    await pointer(panel(), 'pointerenter'); await tick(600)
    expect(launcher().getAttribute('aria-expanded')).toBe('true')
    await pointer(panel(), 'pointerleave'); await tick(550)
    expect(launcher().getAttribute('aria-expanded')).toBe('false')
  })
  it('keeps an active editor open until focus also leaves the panel', async () => {
    await pointer(launcher(), 'pointerenter'); await tick(180)
    panel().querySelector('input')!.focus(); await nextTick()
    await pointer(launcher(), 'pointerleave'); await tick(1000)
    expect(launcher().getAttribute('aria-expanded')).toBe('true')
    panel().querySelector('input')!.blur(); await tick(550)
    expect(launcher().getAttribute('aria-expanded')).toBe('false')
  })
  it('ignores touch hover and short flyovers but retains click and shortcut access', async () => {
    await pointer(launcher(), 'pointerenter', 'touch'); await tick(500)
    expect(launcher().getAttribute('aria-expanded')).toBe('false')
    await pointer(launcher(), 'pointerenter'); await tick(100)
    await pointer(launcher(), 'pointerleave'); await tick(500)
    expect(launcher().getAttribute('aria-expanded')).toBe('false')
    launcher().click(); await nextTick()
    expect(launcher().getAttribute('aria-expanded')).toBe('true')
    expect(panel().dataset.autofocus).toBe('true')
    window.dispatchEvent(new KeyboardEvent('keydown', { altKey: true, code: 'KeyJ' })); await nextTick()
    expect(launcher().getAttribute('aria-expanded')).toBe('false')
  })
  it('leaves narrow-screen panels open after pointer exit', async () => {
    Object.defineProperty(window, 'innerWidth', { value: 390 })
    await pointer(launcher(), 'pointerenter'); await tick(500)
    expect(launcher().getAttribute('aria-expanded')).toBe('false')
    launcher().click(); await nextTick()
    await pointer(panel(), 'pointerleave'); await tick(1000)
    expect(launcher().getAttribute('aria-expanded')).toBe('true')
  })
})
