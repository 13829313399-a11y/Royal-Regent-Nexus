import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h, nextTick, ref, shallowRef } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { departmentModuleRegistry, type EnterpriseModule } from '@/data/enterpriseMock'
import { useHomePresentation } from '@/composables/useHomePresentation'
import { createHomeAppearance } from '@/composables/useHomeAppearance'
import { useAuthStore } from '@/stores/auth'
import type { AuthMeResponse } from '@/api/auth'
import HomeSearchText from '../HomeSearchText.vue'
import HomeModulePreview from '../HomeModulePreview.vue'
import ModuleCard from '@/components/modules/ModuleCard.vue'

const push = vi.hoisted(() => vi.fn())
vi.mock('vue-router', () => ({ useRouter: () => ({ push }), RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } }))
const base = departmentModuleRegistry.engineering.modules[0]!
function module(id: string, title: string, route: string | undefined = `/modules/${id}`): EnterpriseModule { return { ...base, id, title, summary: `${title}说明`, route, href: undefined, children: [{ label: '标签<测试>' }] } }
const alpha = module('a', '啤办登记')
const beta = module('b', 'BOM 工艺')
function harness(initial = [alpha, beta]) {
  const modules = shallowRef(initial)
  const scope = ref('user:group:huaxing:engineering')
  let state!: ReturnType<typeof useHomePresentation>
  const wrapper = mount(defineComponent({ setup() { state = useHomePresentation(modules, scope); return () => h('div') } }))
  return { state, modules, scope, wrapper }
}
beforeEach(() => { setActivePinia(createPinia()); push.mockClear() })
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

describe('home preview and search state', () => {
  it('uses current mapped objects, preserves order and falls back when a pinned result is filtered', () => {
    const { state, modules, wrapper } = harness()
    expect(state.featuredModule.value?.id).toBe('a')
    state.pin('b')
    modules.value = [alpha, { ...beta, route: '/carton-supplier' }]
    expect(state.featuredModule.value?.route).toBe('/carton-supplier')
    state.commitSearch('啤办')
    expect(state.filteredModules.value.map(item => item.id)).toEqual(['a'])
    expect(state.pinnedId.value).toBeNull()
    expect(state.featuredModule.value?.id).toBe('a')
    state.clearSearch()
    expect(state.filteredModules.value.map(item => item.id)).toEqual(['a', 'b'])
    wrapper.unmount()
  })
  it('does not replace a pinned target while hovering other modules and cancels obsolete timers', () => {
    vi.useFakeTimers()
    const { state, scope, wrapper } = harness()
    state.preview('b'); vi.advanceTimersByTime(139)
    expect(state.featuredModule.value?.id).toBe('a')
    vi.advanceTimersByTime(1)
    expect(state.featuredModule.value?.id).toBe('b')
    state.pin('b'); state.preview('a'); vi.advanceTimersByTime(150)
    expect(state.featuredModule.value?.id).toBe('b')
    state.unpin(); state.preview('b'); scope.value = 'user:huaxing:huaxing:engineering'
    vi.advanceTimersByTime(200)
    expect(state.featuredModule.value?.id).toBe('a')
    expect(state.pinnedId.value).toBeNull()
    wrapper.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })
  it('immediately drops revoked targets and closes a mobile dialog', () => {
    vi.useFakeTimers()
    const { state, modules, wrapper } = harness()
    state.pin('b'); state.dialogOpen.value = true
    modules.value = [alpha, { ...beta, route: undefined }]
    expect(state.pinnedId.value).toBeNull()
    expect(state.dialogOpen.value).toBe(false)
    state.preview('a'); modules.value = []
    vi.advanceTimersByTime(200)
    expect(state.featuredModule.value).toBeNull()
    wrapper.unmount()
  })
  it('does not filter IME intermediate text, supports tags and clears zero results', () => {
    const { state, wrapper } = harness()
    state.composing.value = true; state.commitSearch('pi')
    expect(state.filteredModules.value.length).toBe(2)
    state.composing.value = false; state.commitSearch('啤办')
    expect(state.filteredModules.value.length).toBe(1)
    state.commitSearch('<测试>')
    expect(state.filteredModules.value.length).toBe(2)
    state.commitSearch('不存在')
    expect(state.featuredModule.value).toBeNull()
    state.clearSearch()
    expect(state.filteredModules.value.length).toBe(2)
    wrapper.unmount()
  })
  it('keeps same-scope refresh choices and resets account, raw factory and department contexts', () => {
    const { state, modules, scope, wrapper } = harness()
    state.pin('b'); state.commitSearch('BOM')
    modules.value = [{ ...alpha }, { ...beta }]
    expect(state.pinnedId.value).toBe('b')
    for (const identity of ['u2:group:huaxing:engineering', 'u2:huaxing:huaxing:engineering', 'u2:huaxing:huaxing:qc']) {
      scope.value = identity
      expect(state.query.value).toBe('')
      expect(state.pinnedId.value).toBeNull()
      state.pin('b'); state.commitSearch('BOM')
    }
    wrapper.unmount()
  })
})

describe('home card and preview navigation', () => {
  it('preview does not navigate; Enter on a nested link never invokes the article handler', async () => {
    const wrapper = mount(ModuleCard, { props: { module: beta, previewable: true } })
    await wrapper.get('.home-preview-button').trigger('click')
    expect(wrapper.emitted('preview')).toHaveLength(1)
    expect(push).not.toHaveBeenCalled()
    await wrapper.get('a').trigger('keydown', { key: 'Enter' })
    expect(push).not.toHaveBeenCalled()
    await wrapper.trigger('keydown', { key: 'Enter' })
    expect(push).toHaveBeenCalledExactlyOnceWith(beta.route)
    wrapper.unmount()
  })
  it('keeps placeholders inert even when preview capability is requested', async () => {
    const placeholder = { ...alpha, route: undefined, href: undefined }
    const wrapper = mount(ModuleCard, { props: { module: placeholder, previewable: true } })
    expect(wrapper.attributes('role')).toBeUndefined()
    expect(wrapper.find('button, a').exists()).toBe(false)
    await wrapper.trigger('click'); await wrapper.trigger('keydown', { key: ' ' })
    expect(push).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('preserves route-only, internal-href and external-href actions', async () => {
    const wrapper = mount(HomeModulePreview, { props: { module: beta, pinned: false } })
    expect(wrapper.get('a').attributes('href')).toBe(beta.route)
    expect(wrapper.get('a').text()).toBe('查看模块')
    await wrapper.setProps({ module: { ...beta, route: undefined, href: '/carton-supplier' } })
    expect(wrapper.get('a').attributes('href')).toBe('/carton-supplier')
    await wrapper.setProps({ module: { ...beta, href: 'https://example.com/external' } })
    expect(wrapper.findAll('a')).toHaveLength(2)
    expect(wrapper.get('a[target="_blank"]').attributes('rel')).toBe('noreferrer')
    await wrapper.setProps({ module: { ...beta, route: undefined, href: undefined } })
    expect(wrapper.find('a').exists()).toBe(false)
    wrapper.unmount()
  })
  it('highlights hostile-looking search text without interpreting markup', () => {
    const wrapper = mount(HomeSearchText, { props: { text: '<img onerror="alert(1)"> BOM', query: '<img' } })
    expect(wrapper.get('mark').text()).toBe('<img')
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.text()).toBe('<img onerror="alert(1)"> BOM')
    wrapper.unmount()
  })
})

describe('home appearance preferences', () => {
  function preferences() {
    let state!: ReturnType<typeof createHomeAppearance>
    const enabled = ref(true)
    const wrapper = mount(defineComponent({ setup() { state = createHomeAppearance(enabled); return () => h('div') } }))
    return { state, enabled, wrapper }
  }
  function user(id: string) { useAuthStore().currentUser = { id } as AuthMeResponse }
  it('persists only validated enums and isolates preferences per account', () => {
    localStorage.clear(); user('a')
    const { state, wrapper } = preferences()
    state.motion.value = 'calm'; state.density.value = 'compact'
    expect(JSON.parse(localStorage.getItem('rrn:home-prism:v1:a')!)).toEqual({ version: 1, motion: 'calm', density: 'compact' })
    user('b'); expect(state.motion.value).toBe('expressive'); expect(state.density.value).toBe('comfortable')
    user('a'); expect(state.motion.value).toBe('calm'); expect(state.density.value).toBe('compact')
    wrapper.unmount()
  })
  it('handles corrupt or unavailable storage and never stores guest preferences', () => {
    localStorage.clear(); localStorage.setItem('rrn:home-prism:v1:a', '{bad')
    user('a'); const { state, wrapper } = preferences()
    expect(state.motion.value).toBe('expressive')
    const failingWrite = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('unavailable') })
    expect(() => { state.motion.value = 'off' }).not.toThrow()
    failingWrite.mockRestore(); useAuthStore().currentUser = null
    const count = localStorage.length
    state.density.value = 'compact'; expect(localStorage.length).toBe(count)
    wrapper.unmount()
  })
  it('system reduced motion wins and media listeners disconnect on leaving home', async () => {
    const media = { matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }
    vi.stubGlobal('matchMedia', () => media)
    const { state, enabled, wrapper } = preferences()
    state.motion.value = 'expressive'
    expect(state.effectiveMotion.value).toBe('off')
    enabled.value = false; await nextTick()
    expect(media.removeEventListener).toHaveBeenCalledWith('change', expect.any(Function))
    wrapper.unmount()
  })
  it('suspends home motion while the document is hidden and restores the saved choice', () => {
    const visibility = vi.spyOn(document, 'visibilityState', 'get')
    visibility.mockReturnValue('visible')
    vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }))
    const { state, wrapper } = preferences()
    state.motion.value = 'calm'
    visibility.mockReturnValue('hidden')
    document.dispatchEvent(new Event('visibilitychange'))
    expect(state.effectiveMotion.value).toBe('off')
    expect(state.motion.value).toBe('calm')
    visibility.mockReturnValue('visible')
    document.dispatchEvent(new Event('visibilitychange'))
    expect(state.effectiveMotion.value).toBe('calm')
    wrapper.unmount()
    visibility.mockRestore()
  })
})
