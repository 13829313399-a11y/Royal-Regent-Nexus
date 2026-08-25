import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { usePresenceHeartbeat } from '@/composables/usePresenceHeartbeat'
import { useAuthStore } from '@/stores/auth'

const sendHeartbeat = vi.hoisted(() => vi.fn())

vi.mock('@/api/directory', () => ({
  directoryApi: { sendHeartbeat },
}))

const Host = defineComponent({
  setup() {
    usePresenceHeartbeat()
    return () => null
  },
})

function currentUser() {
  return {
    id: 'member-1',
    username: 'member',
    display_name: '成员',
    roles: [],
    permissions: [],
    factory_scopes: [],
    department_scopes: [],
    grants: [],
    force_password_change: false,
  }
}

describe('presence heartbeat lifecycle', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0)
    sendHeartbeat.mockReset().mockResolvedValue({ status: 'ok', written: true, presence_state: 'online' })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.runOnlyPendingTimers()
    vi.useRealTimers()
  })

  it('sends immediately, repeats at 60 seconds, and stops after logout', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const authStore = useAuthStore()
    authStore.applySession(currentUser())
    const wrapper = mount(Host, { global: { plugins: [pinia] } })
    await flushPromises()
    expect(sendHeartbeat).toHaveBeenCalledTimes(1)

    vi.advanceTimersByTime(60_000)
    await flushPromises()
    expect(sendHeartbeat).toHaveBeenCalledTimes(2)

    authStore.clearSession()
    await flushPromises()
    vi.advanceTimersByTime(120_000)
    await flushPromises()
    expect(sendHeartbeat).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('prevents overlapping requests during repeated focus events', async () => {
    let resolveRequest: (() => void) | undefined
    sendHeartbeat.mockReturnValue(new Promise<void>((resolve) => { resolveRequest = resolve }))
    const pinia = createPinia()
    setActivePinia(pinia)
    useAuthStore().applySession(currentUser())
    const wrapper = mount(Host, { global: { plugins: [pinia] } })
    window.dispatchEvent(new Event('focus'))
    window.dispatchEvent(new Event('focus'))
    expect(sendHeartbeat).toHaveBeenCalledTimes(1)
    resolveRequest?.()
    await flushPromises()
    wrapper.unmount()
  })
})
