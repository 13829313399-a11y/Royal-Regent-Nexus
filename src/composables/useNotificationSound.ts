import { onMounted, onUnmounted, ref } from 'vue'

const SOUND_ENABLED_STORAGE_KEY = 'rr.notification.sound.enabled'
const LAST_SOUND_STORAGE_KEY = 'rr.notification.sound.last-played-at'
const SOUND_COOLDOWN_MS = 3_000

type BrowserAudioContext = AudioContext & {
  createGain(): GainNode
  createOscillator(): OscillatorNode
}

type AudioContextConstructor = new () => BrowserAudioContext

function readSoundPreference() {
  if (typeof window === 'undefined') return true
  try {
    return window.localStorage.getItem(SOUND_ENABLED_STORAGE_KEY) !== 'false'
  } catch {
    return true
  }
}

function readSharedLastSoundAt() {
  if (typeof window === 'undefined') return 0
  try {
    const storedValue = Number(window.localStorage.getItem(LAST_SOUND_STORAGE_KEY) || 0)
    return Number.isFinite(storedValue) ? storedValue : 0
  } catch {
    return 0
  }
}

function getAudioContextConstructor() {
  if (typeof window === 'undefined') return undefined
  const audioWindow = window as typeof window & {
    AudioContext?: AudioContextConstructor
    webkitAudioContext?: AudioContextConstructor
  }
  return audioWindow.AudioContext ?? audioWindow.webkitAudioContext
}

export function useNotificationSound() {
  const soundEnabled = ref(readSoundPreference())
  const soundReady = ref(false)
  let audioContext: BrowserAudioContext | undefined
  let lastPlayedAt = readSharedLastSoundAt()

  async function unlockSound() {
    if (!soundEnabled.value) return false
    const AudioContextClass = getAudioContextConstructor()
    if (!AudioContextClass) return false
    try {
      audioContext ??= new AudioContextClass()
      if (audioContext.state === 'suspended') {
        await audioContext.resume()
      }
      soundReady.value = audioContext.state === 'running'
      return soundReady.value
    } catch {
      soundReady.value = false
      return false
    }
  }

  async function setSoundEnabled(enabled: boolean) {
    soundEnabled.value = enabled
    if (typeof window !== 'undefined') {
      try {
        window.localStorage.setItem(SOUND_ENABLED_STORAGE_KEY, String(enabled))
      } catch {
        // Sound remains usable for the current tab when storage is unavailable.
      }
    }
    if (enabled) {
      await unlockSound()
    } else {
      soundReady.value = false
    }
  }

  async function toggleSound() {
    await setSoundEnabled(!soundEnabled.value)
  }

  async function playNotificationSound(ignoreCooldown = false) {
    if (!soundEnabled.value) return false
    const now = Date.now()
    const sharedLastPlayedAt = Math.max(lastPlayedAt, readSharedLastSoundAt())
    if (!ignoreCooldown && now - sharedLastPlayedAt < SOUND_COOLDOWN_MS) return false
    if (!soundReady.value || !audioContext) return false

    try {
      const gain = audioContext.createGain()
      gain.connect(audioContext.destination)
      gain.gain.setValueAtTime(0.0001, audioContext.currentTime)
      gain.gain.exponentialRampToValueAtTime(0.018, audioContext.currentTime + 0.035)
      gain.gain.exponentialRampToValueAtTime(0.0001, audioContext.currentTime + 0.54)

      const toneSchedule = [
        { frequency: 620, start: 0, duration: 0.18 },
        { frequency: 760, start: 0.24, duration: 0.24 },
      ]
      toneSchedule.forEach(({ frequency, start, duration }) => {
        const oscillator = audioContext!.createOscillator()
        oscillator.type = 'sine'
        oscillator.frequency.setValueAtTime(frequency, audioContext!.currentTime + start)
        oscillator.connect(gain)
        oscillator.start(audioContext!.currentTime + start)
        oscillator.stop(audioContext!.currentTime + start + duration)
      })

      lastPlayedAt = now
      try {
        window.localStorage.setItem(LAST_SOUND_STORAGE_KEY, String(now))
      } catch {
        // The in-memory cooldown still prevents repeated sound in this tab.
      }
      return true
    } catch {
      return false
    }
  }

  async function previewSound() {
    if (!soundEnabled.value || !await unlockSound()) return false
    return playNotificationSound(true)
  }

  function syncSoundPreference(event: StorageEvent) {
    if (event.key === SOUND_ENABLED_STORAGE_KEY && event.newValue !== null) {
      soundEnabled.value = event.newValue !== 'false'
    }
    if (event.key === LAST_SOUND_STORAGE_KEY && event.newValue) {
      lastPlayedAt = Math.max(lastPlayedAt, Number(event.newValue) || 0)
    }
  }

  function unlockFromUserGesture() {
    void unlockSound()
  }

  onMounted(() => {
    window.addEventListener('storage', syncSoundPreference)
    document.addEventListener('pointerdown', unlockFromUserGesture, { once: true })
    document.addEventListener('keydown', unlockFromUserGesture, { once: true })
  })

  onUnmounted(() => {
    window.removeEventListener('storage', syncSoundPreference)
    document.removeEventListener('pointerdown', unlockFromUserGesture)
    document.removeEventListener('keydown', unlockFromUserGesture)
    void audioContext?.close()
  })

  return {
    soundEnabled,
    soundReady,
    playNotificationSound,
    previewSound,
    setSoundEnabled,
    toggleSound,
    unlockSound,
  }
}
