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

  it.each(['huakang-a', 'huakang-b', 'huakang-c', 'huakang-d', 'huadeng', 'huaxing'])(
    'initializes a new session to its registered factory %s', (primaryFactoryId) => {
      const store = useAppStore()
      store.setActiveFactory('huaxing')
      store.syncAuthenticatedFactoryContext({ userId: 'a', primaryFactoryId })
      expect(store.activeFactoryId).toBe(primaryFactoryId)
      expect(store.activeDepartmentId).toBe('engineering')
    },
  )

  it.each(['*', 'group', '', null, undefined, 'unknown-factory'])(
    'uses neutral group context for %s', (primaryFactoryId) => {
      const store = useAppStore()
      store.syncAuthenticatedFactoryContext({ userId: 'a', primaryFactoryId })
      expect(store.activeFactoryId).toBe('group')
    },
  )

  it('preserves manual selection until the official profile changes, then syncs only once', () => {
    const store = useAppStore()
    const context = { userId: 'a', primaryFactoryId: 'huakang-a' }
    store.syncAuthenticatedFactoryContext(context)
    store.setActiveFactory('huakang-c')
    store.syncAuthenticatedFactoryContext(context)
    expect(store.activeFactoryId).toBe('huakang-c')
    store.syncAuthenticatedFactoryContext({ ...context, primaryFactoryId: 'huadeng' })
    expect(store.activeFactoryId).toBe('huadeng')
    store.setActiveFactory('huakang-d')
    store.syncAuthenticatedFactoryContext({ ...context, primaryFactoryId: 'huadeng' })
    expect(store.activeFactoryId).toBe('huakang-d')
  })

  it('does not carry a selection across identities or a cleared session', () => {
    const store = useAppStore()
    store.syncAuthenticatedFactoryContext({ userId: 'a', primaryFactoryId: 'huakang-a' })
    store.setActiveFactory('huadeng')
    store.syncAuthenticatedFactoryContext({ userId: 'b', primaryFactoryId: 'huaxing' })
    expect(store.activeFactoryId).toBe('huaxing')
    store.setRequestedFactoryContext('huakang-c')
    store.resetAuthenticatedFactoryContext()
    expect(store.authenticatedFactoryContext).toBeNull()
    expect(store.requestedFactoryId).toBeNull()
    expect(store.activeFactoryId).toBe('group')
    store.syncAuthenticatedFactoryContext({ userId: 'a', primaryFactoryId: 'huakang-a' })
    expect(store.activeFactoryId).toBe('huakang-a')
  })

  it('honors a valid deep link even during profile updates, without applying it before authentication', () => {
    const store = useAppStore()
    store.setRequestedFactoryContext(['huadeng', 'huaxing'])
    expect(store.activeFactoryId).toBe('group')
    store.syncAuthenticatedFactoryContext({ userId: 'a', primaryFactoryId: 'huakang-a' })
    expect(store.activeFactoryId).toBe('huadeng')
    store.syncAuthenticatedFactoryContext({ userId: 'a', primaryFactoryId: 'huakang-c' })
    expect(store.activeFactoryId).toBe('huadeng')
    store.setRequestedFactoryContext(undefined)
    store.setActiveFactory('huakang-d')
    store.syncAuthenticatedFactoryContext({ userId: 'a', primaryFactoryId: 'huakang-c' })
    expect(store.activeFactoryId).toBe('huakang-d')
  })

  it.each(['not-a-factory', '*', '', null, undefined, 42, [], [null, 'huadeng']])(
    'rejects invalid requested factory %s', (requested) => {
      const store = useAppStore()
      store.setRequestedFactoryContext(requested)
      store.syncAuthenticatedFactoryContext({ userId: 'a', primaryFactoryId: 'huakang-b' })
      expect(store.requestedFactoryId).toBeNull()
      expect(store.activeFactoryId).toBe('huakang-b')
    },
  )
})
