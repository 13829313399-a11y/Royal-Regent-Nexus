import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useNotificationSound } from '@/composables/useNotificationSound'

type NotificationSound = ReturnType<typeof useNotificationSound>

const audioSpies = {
  resume: vi.fn(),
  close: vi.fn(),
  createGain: vi.fn(),
  createOscillator: vi.fn(),
  oscillatorStart: vi.fn(),
  oscillatorStop: vi.fn(),
}

class MockAudioContext {
  state: AudioContextState = 'suspended'
  currentTime = 0
  destination = {} as AudioDestinationNode

  resume = audioSpies.resume.mockImplementation(async () => {
    this.state = 'running'
  })

  close = audioSpies.close.mockResolvedValue(undefined)

  createGain = audioSpies.createGain.mockImplementation(() => ({
    connect: vi.fn(),
    gain: {
      setValueAtTime: vi.fn(),
      exponentialRampToValueAtTime: vi.fn(),
    },
  }))

  createOscillator = audioSpies.createOscillator.mockImplementation(() => ({
    type: 'sine',
    frequency: { setValueAtTime: vi.fn() },
    connect: vi.fn(),
    start: audioSpies.oscillatorStart,
    stop: audioSpies.oscillatorStop,
  }))
}

function mountSound() {
  let sound: NotificationSound | undefined
  const Harness = defineComponent({
    setup() {
      sound = useNotificationSound()
      return () => h('div')
    },
  })
  const wrapper = mount(Harness)
  return { wrapper, sound: () => sound! }
}

describe('useNotificationSound', () => {
  const originalAudioContext = window.AudioContext
  const originalWebkitAudioContext = (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext

  beforeEach(() => {
    window.localStorage.clear()
    vi.clearAllMocks()
    Object.defineProperty(window, 'AudioContext', { configurable: true, value: MockAudioContext })
    Reflect.deleteProperty(window as typeof window & { webkitAudioContext?: typeof AudioContext }, 'webkitAudioContext')
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    Object.defineProperty(window, 'AudioContext', { configurable: true, value: originalAudioContext })
    if (originalWebkitAudioContext) {
      Object.defineProperty(window, 'webkitAudioContext', { configurable: true, value: originalWebkitAudioContext })
    } else {
      Reflect.deleteProperty(window as typeof window & { webkitAudioContext?: typeof AudioContext }, 'webkitAudioContext')
    }
  })

  it('unlocks after a user gesture and plays a restrained two-tone sound', async () => {
    const { wrapper, sound } = mountSound()

    expect(sound().soundReady.value).toBe(false)
    document.dispatchEvent(new Event('pointerdown'))
    await flushPromises()

    expect(sound().soundReady.value).toBe(true)
    await expect(sound().playNotificationSound()).resolves.toBe(true)
    expect(audioSpies.createGain).toHaveBeenCalledTimes(1)
    expect(audioSpies.createOscillator).toHaveBeenCalledTimes(2)
    expect(audioSpies.oscillatorStart).toHaveBeenCalledTimes(2)
    expect(audioSpies.oscillatorStop).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('honors the three-second cooldown while preview remains available', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-18T08:00:00+08:00'))
    const { wrapper, sound } = mountSound()
    await sound().unlockSound()

    await expect(sound().playNotificationSound()).resolves.toBe(true)
    await expect(sound().playNotificationSound()).resolves.toBe(false)
    expect(audioSpies.createOscillator).toHaveBeenCalledTimes(2)

    await expect(sound().previewSound()).resolves.toBe(true)
    expect(audioSpies.createOscillator).toHaveBeenCalledTimes(4)

    await vi.advanceTimersByTimeAsync(3_001)
    await expect(sound().playNotificationSound()).resolves.toBe(true)
    expect(audioSpies.createOscillator).toHaveBeenCalledTimes(6)
    wrapper.unmount()
  })

  it('persists the sound switch and stays silent when disabled', async () => {
    const { wrapper, sound } = mountSound()
    await sound().unlockSound()
    await sound().setSoundEnabled(false)

    expect(window.localStorage.getItem('rr.notification.sound.enabled')).toBe('false')
    await expect(sound().playNotificationSound()).resolves.toBe(false)
    expect(audioSpies.createOscillator).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('degrades silently when audio or browser storage is unavailable', async () => {
    Object.defineProperty(window, 'AudioContext', { configurable: true, value: undefined })
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('storage disabled') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('storage disabled') })

    const { wrapper, sound } = mountSound()
    await expect(sound().unlockSound()).resolves.toBe(false)
    await expect(sound().playNotificationSound()).resolves.toBe(false)
    await expect(sound().setSoundEnabled(false)).resolves.toBeUndefined()
    expect(sound().soundReady.value).toBe(false)
    wrapper.unmount()
  })
})
