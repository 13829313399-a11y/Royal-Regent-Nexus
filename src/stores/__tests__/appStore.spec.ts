import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { useAppStore } from '@/stores/app'

describe('app store factory context', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it.each([
    ['huakang-c', '华康C'],
    ['huakang-d', '华康D'],
  ] as const)('keeps %s as the active production factory', (factoryId, factoryName) => {
    const store = useAppStore()

    store.setActiveFactory(factoryId)

    expect(store.activeFactory).toMatchObject({
      id: factoryId,
      name: factoryName,
      shortName: factoryName,
    })
    expect(store.activeProductionFactory).toMatchObject({
      id: factoryId,
      name: factoryName,
      shortName: factoryName,
    })
    expect(store.activeProductionFactory.id).not.toBe('huaxing')
  })

  it('keeps the group context out of production modules', () => {
    const store = useAppStore()

    store.setActiveFactory('group')

    expect(store.activeFactory.id).toBe('group')
    expect(store.activeProductionFactory.id).toBe('huaxing')
  })
})
