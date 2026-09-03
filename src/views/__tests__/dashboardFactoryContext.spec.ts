import { shallowMount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { describe, expect, it } from 'vitest'
import DashboardView from '@/views/DashboardView.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import { useAppStore } from '@/stores/app'

describe('dashboard factory title', () => {
  it('shows the authenticated factory and follows manual selection including group', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useAppStore()
    store.syncAuthenticatedFactoryContext({ userId: 'a', primaryFactoryId: 'huakang-a' })
    const wrapper = shallowMount(DashboardView, { global: { plugins: [pinia] } })
    expect(wrapper.getComponent(PageHeader).props('title')).toBe('华康A · 运营总览')
    store.setActiveFactory('huadeng')
    await nextTick()
    expect(wrapper.getComponent(PageHeader).props('title')).toBe('华登 · 运营总览')
    store.setActiveFactory('group')
    await nextTick()
    expect(wrapper.getComponent(PageHeader).props('title')).toBe('集团运营总览')
    wrapper.unmount()
  })
})
