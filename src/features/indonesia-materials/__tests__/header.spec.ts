import { shallowMount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MaterialsHeader from '../MaterialsHeader.vue'
import { useAppStore } from '@/stores/app'
import { registerFactoryChangeGuard } from '@/lib/factoryChangeGuard'
import { factoryContexts } from '@/data/enterpriseMock'

const replace = vi.hoisted(() => vi.fn())
vi.mock('vue-router', () => ({
  RouterLink: { props: ['to'], template: '<a><slot /></a>' },
  useRoute: () => ({ path: '/modules/sales-business/indonesia-material-shipment', query: { factory: 'group', view: 'detail' }, hash: '#im-main' }),
  useRouter: () => ({ replace }),
}))
vi.mock('@/components/layout/AccountMenu.vue', () => ({ default: { template: '<span />' } }))
vi.mock('@/components/notifications/NotificationCenter.vue', () => ({ default: { template: '<span />' } }))

describe('materials workspace header', () => {
  beforeEach(() => { setActivePinia(createPinia()); replace.mockReset() })
  it('preserves group until explicitly selected and carries route context when changing factory', async () => {
    const store = useAppStore()
    store.setActiveFactory('group')
    const panel = shallowMount(MaterialsHeader, { props: { disabled: false } })
    try {
      const select = panel.get('select')
      expect(select.element.value).toBe('group')
      expect(select.findAll('option')).toHaveLength(factoryContexts.length)
      await select.setValue('huakang-c')
      expect(store.activeFactoryId).toBe('huakang-c')
      expect(replace).toHaveBeenCalledWith({ path: '/modules/sales-business/indonesia-material-shipment', query: { factory: 'huakang-c', view: 'detail' }, hash: '#im-main' })
    } finally { panel.unmount() }
  })
  it('restores the current factory when unsaved-work guard rejects switching', async () => {
    const store = useAppStore()
    store.setActiveFactory('huaxing')
    const unregister = registerFactoryChangeGuard(() => false)
    const panel = shallowMount(MaterialsHeader, { props: { disabled: false } })
    try {
      await panel.get('select').setValue('huadeng')
      expect(store.activeFactoryId).toBe('huaxing')
      expect(panel.get('select').element.value).toBe('huaxing')
      expect(replace).not.toHaveBeenCalled()
    } finally { unregister(); panel.unmount() }
  })
  it('disables scope switching during a pending operation without a duplicate search', async () => {
    const panel = shallowMount(MaterialsHeader, { props: { disabled: true } })
    try {
      expect(panel.get('select').element.disabled).toBe(true)
      expect(panel.find('input[type=search]').exists()).toBe(false)
    } finally { panel.unmount() }
  })
})
