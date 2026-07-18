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
  gainSetValueAtTime: vi.fn(),
  gainExponentialRampToValueAtTime: vi.fn(),
  oscillatorFrequencySetValueAtTime: vi.fn(),
  oscillatorStart: vi.fn(),
  oscillatorStop: vi.fn(),
}

let latestAudioContext: MockAudioContext | undefined

class MockAudioContext {
  state: AudioContextState = 'suspended'
  currentTime = 0
  destination = {} as AudioDestinationNode

  constructor() {
    latestAudioContext = this
  }

  resume = audioSpies.resume.mockImplementation(async () => {
    this.state = 'running'
  })

  close = audioSpies.close.mockResolvedValue(undefined)

  createGain = audioSpies.createGain.mockImplementation(() => ({
    connect: vi.fn(),
    gain: {
      setValueAtTime: audioSpies.gainSetValueAtTime,
      exponentialRampToValueAtTime: audioSpies.gainExponentialRampToValueAtTime,
    },
  }))

  createOscillator = audioSpies.createOscillator.mockImplementation(() => ({
    type: 'sine',
    frequency: { setValueAtTime: audioSpies.oscillatorFrequencySetValueAtTime },
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
    latestAudioContext = undefined
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

  it('unlocks after a user gesture and plays a clearly audible, non-overlapping two-tone sound', async () => {
    const { wrapper, sound } = mountSound()

    expect(sound().soundReady.value).toBe(false)
    document.dispatchEvent(new Event('pointerdown'))
    await flushPromises()

    expect(sound().soundReady.value).toBe(true)
    await expect(sound().playNotificationSound()).resolves.toBe(true)
    expect(audioSpies.createGain).toHaveBeenCalledTimes(2)
    expect(audioSpies.createOscillator).toHaveBeenCalledTimes(2)
    expect(audioSpies.oscillatorStart).toHaveBeenCalledTimes(2)
    expect(audioSpies.oscillatorStop).toHaveBeenCalledTimes(2)

    const peakGainCalls = audioSpies.gainExponentialRampToValueAtTime.mock.calls
      .filter(([gain]) => gain > 0.0001)
    expect(peakGainCalls).toHaveLength(2)
    expect(peakGainCalls[0]?.[0]).toBeCloseTo(0.16)
    expect(peakGainCalls[1]?.[0]).toBeCloseTo(0.20)
    peakGainCalls.forEach(([gain]) => {
      expect(gain).toBeGreaterThanOrEqual(0.14)
      expect(gain).toBeLessThanOrEqual(0.24)
    })
    expect(audioSpies.gainSetValueAtTime).toHaveBeenNthCalledWith(1, 0.0001, 0)
    expect(audioSpies.gainSetValueAtTime).toHaveBeenNthCalledWith(2, 0.0001, 0.24)
    expect(peakGainCalls[0]?.[1]).toBeCloseTo(0.025)
    expect(peakGainCalls[1]?.[1]).toBeCloseTo(0.265)
    expect(audioSpies.gainExponentialRampToValueAtTime).toHaveBeenNthCalledWith(2, 0.0001, 0.18)
    expect(audioSpies.gainExponentialRampToValueAtTime).toHaveBeenNthCalledWith(4, 0.0001, 0.48)
    expect(audioSpies.oscillatorFrequencySetValueAtTime).toHaveBeenNthCalledWith(1, 620, 0)
    expect(audioSpies.oscillatorFrequencySetValueAtTime).toHaveBeenNthCalledWith(2, 760, 0.24)
    expect(audioSpies.oscillatorStart).toHaveBeenNthCalledWith(1, 0)
    expect(audioSpies.oscillatorStart).toHaveBeenNthCalledWith(2, 0.24)
    expect(audioSpies.oscillatorStop).toHaveBeenNthCalledWith(1, 0.18)
    expect(audioSpies.oscillatorStop).toHaveBeenNthCalledWith(2, 0.48)
    wrapper.unmount()
  })

  it('resumes a suspended audio context before playing a notification', async () => {
    const { wrapper, sound } = mountSound()
    await sound().unlockSound()
    expect(latestAudioContext).toBeTruthy()
    latestAudioContext!.state = 'suspended'
    audioSpies.resume.mockClear()

    await expect(sound().playNotificationSound()).resolves.toBe(true)

    expect(audioSpies.resume).toHaveBeenCalledTimes(1)
    expect(sound().soundReady.value).toBe(true)
    expect(audioSpies.createOscillator).toHaveBeenCalledTimes(2)
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
