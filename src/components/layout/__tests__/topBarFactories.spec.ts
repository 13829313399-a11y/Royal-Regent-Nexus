import { shallowMount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TopBar from '@/components/layout/TopBar.vue'
import { factoryContexts, productionFactoryContextIds } from '@/data/enterpriseMock'
import { useAppStore } from '@/stores/app'

const routeState = vi.hoisted(() => ({
  path: '/modules/engineering',
  name: 'modules-department',
  params: { department: 'engineering' },
  query: { layout: 'cards', factory: 'huaxing' } as Record<string, string>,
}))
const routerReplaceMock = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  RouterLink: {
    name: 'RouterLink',
    props: ['to'],
    template: '<a><slot /></a>',
  },
  useRoute: () => routeState,
  useRouter: () => ({
    replace: routerReplaceMock,
  }),
}))

describe('TopBar factory switcher', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    routerReplaceMock.mockReset()
    routeState.query = { layout: 'cards', factory: 'huaxing' }
  })

  it('includes Huakang C and D in the complete production factory list', () => {
    const physicalFactoryIds = factoryContexts
      .filter((factory) => factory.id !== 'group')
      .map((factory) => factory.id)

    expect(productionFactoryContextIds).toEqual(physicalFactoryIds)
    expect(productionFactoryContextIds).toContain('huakang-c')
    expect(productionFactoryContextIds).toContain('huakang-d')
  })

  it.each([
    ['huakang-c', '华康C'],
    ['huakang-d', '华康D'],
  ] as const)('switches to %s and synchronizes the route factory query', async (factoryId, factoryLabel) => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useAppStore()
    const wrapper = shallowMount(TopBar, {
      global: {
        plugins: [pinia],
        stubs: {
          AccountMenu: true,
          NotificationCenter: true,
          RouteLoadingBar: true,
        },
      },
    })

    await wrapper.get(`button[aria-label="切换至${factoryLabel}"]`).trigger('click')

    expect(store.activeFactoryId).toBe(factoryId)
    expect(store.activeProductionFactory.id).toBe(factoryId)
    expect(routerReplaceMock).toHaveBeenCalledTimes(1)
    expect(routerReplaceMock).toHaveBeenCalledWith(expect.objectContaining({
      query: {
        layout: 'cards',
        factory: factoryId,
      },
    }))
  })
})
