import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  clampSurfaceGeometry,
  defaultSurfaceGeometry,
  type AISurfaceGeometry,
} from './useWindowGeometry'

export type AISurfaceMode = 'EDGE' | 'FLOATING' | 'DOCKED_LEFT' | 'DOCKED_RIGHT' | 'FULLSCREEN_MOBILE'
type DesktopSurfaceMode = 'FLOATING' | 'DOCKED_LEFT' | 'DOCKED_RIGHT'

const STORAGE_KEY = 'rr:nexus-ai-surface:v3'
const LEGACY_STORAGE_KEYS = ['rr:nexus-ai-surface:v2', 'rr:nexus-ai-surface:v1'] as const
const DEFAULT_DOCK_WIDTH = 376
const DESKTOP_MODES = new Set<DesktopSurfaceMode>(['FLOATING', 'DOCKED_LEFT', 'DOCKED_RIGHT'])

interface StoredPreferences {
  version: 3
  mode: AISurfaceMode
  lastDesktopMode: DesktopSurfaceMode
  edgeY: number
  geometry: AISurfaceGeometry
  dockWidth: number
}

function finite(value: unknown, fallback: number) {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function mobileViewport() {
  return window.matchMedia?.('(max-width: 639px)').matches ?? window.innerWidth < 640
}

function clampDockWidth(value: number) {
  const maximum = mobileViewport() ? 720 : Math.min(720, window.innerWidth * 0.72)
  return Math.min(Math.max(value, 360), maximum)
}

export const useAISurfaceStore = defineStore('aiSurface', () => {
  const mode = ref<AISurfaceMode>('EDGE')
  const lastDesktopMode = ref<DesktopSurfaceMode>('DOCKED_RIGHT')
  const edgeY = ref(180)
  const geometry = ref<AISurfaceGeometry>(defaultSurfaceGeometry())
  const dockWidth = ref(DEFAULT_DOCK_WIDTH)
  const hydrated = ref(false)

  const edgeSide = computed<'left' | 'right'>(() => (
    lastDesktopMode.value === 'DOCKED_LEFT' ? 'left' : 'right'
  ))

  function hydrate() {
    if (hydrated.value) return
    hydrated.value = true
    try {
      const currentRaw = localStorage.getItem(STORAGE_KEY)
      const legacyEntry = LEGACY_STORAGE_KEYS
        .map((key) => ({ key, raw: localStorage.getItem(key) }))
        .find((entry) => Boolean(entry.raw))
      const legacyRaw = legacyEntry?.raw ?? null
      const isLegacy = !currentRaw && Boolean(legacyRaw)
      const storedRaw = currentRaw ?? legacyRaw
      if (!storedRaw) return
      const parsed = JSON.parse(storedRaw) as Partial<StoredPreferences>
      if (!parsed.geometry || typeof parsed.geometry !== 'object') return
      if (isLegacy) {
        const legacyVersion = legacyEntry?.key.endsWith(':v2') ? 2 : 1
        if (Number(parsed.version) !== legacyVersion) return
      } else if (Number(parsed.version) !== 3) return
      const storedMode = String(parsed.mode)
      const storedDesktopMode = String(parsed.lastDesktopMode)
      const restoredMode = ['EDGE', 'FLOATING', 'DOCKED_LEFT', 'DOCKED_RIGHT'].includes(storedMode)
        ? storedMode as AISurfaceMode
        : 'EDGE'
      const restoredDesktopMode = DESKTOP_MODES.has(storedDesktopMode as DesktopSurfaceMode)
        ? storedDesktopMode as DesktopSurfaceMode
        : 'DOCKED_RIGHT'
      // Layout preferences are origin-scoped. Reset legacy desktop geometry once so
      // localhost and production open the same canonical drawer after an upgrade.
      mode.value = isLegacy && restoredMode !== 'EDGE' ? 'DOCKED_RIGHT' : restoredMode
      lastDesktopMode.value = isLegacy ? 'DOCKED_RIGHT' : restoredDesktopMode
      edgeY.value = Math.min(Math.max(finite(parsed.edgeY, 180), 64), Math.max(64, window.innerHeight - 96))
      if (!isLegacy) {
        geometry.value = clampSurfaceGeometry({
          x: finite(parsed.geometry.x, geometry.value.x),
          y: finite(parsed.geometry.y, geometry.value.y),
          width: finite(parsed.geometry.width, geometry.value.width),
          height: finite(parsed.geometry.height, geometry.value.height),
        })
        dockWidth.value = clampDockWidth(finite(parsed.dockWidth, DEFAULT_DOCK_WIDTH))
      }
      if (isLegacy) {
        persist()
        LEGACY_STORAGE_KEYS.forEach((key) => localStorage.removeItem(key))
      }
    } catch {
      // Corrupt preferences are ignored; no conversation or business data is read here.
    }
  }

  function persist() {
    const payload: StoredPreferences = {
      version: 3,
      mode: mode.value === 'FULLSCREEN_MOBILE' ? 'EDGE' : mode.value,
      lastDesktopMode: lastDesktopMode.value,
      edgeY: edgeY.value,
      geometry: geometry.value,
      dockWidth: dockWidth.value,
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
  }

  function open() {
    hydrate()
    mode.value = mobileViewport() ? 'FULLSCREEN_MOBILE' : lastDesktopMode.value
  }

  function minimize() {
    if (DESKTOP_MODES.has(mode.value as DesktopSurfaceMode)) {
      lastDesktopMode.value = mode.value as DesktopSurfaceMode
    }
    mode.value = 'EDGE'
    persist()
  }

  function setMode(next: DesktopSurfaceMode) {
    lastDesktopMode.value = next
    mode.value = mobileViewport() ? 'FULLSCREEN_MOBILE' : next
    persist()
  }

  function setGeometry(next: AISurfaceGeometry, save = true) {
    geometry.value = clampSurfaceGeometry(next)
    if (save) persist()
  }

  function setDockWidth(next: number, save = true) {
    dockWidth.value = clampDockWidth(next)
    if (save) persist()
  }

  function setEdgeY(next: number) {
    edgeY.value = Math.min(Math.max(next, 48), Math.max(48, window.innerHeight - 96))
    persist()
  }

  function syncViewport() {
    geometry.value = clampSurfaceGeometry(geometry.value)
    const mobile = mobileViewport()
    if (!mobile) dockWidth.value = clampDockWidth(dockWidth.value)
    if (mobile && mode.value !== 'EDGE') mode.value = 'FULLSCREEN_MOBILE'
    else if (!mobile && mode.value === 'FULLSCREEN_MOBILE') mode.value = lastDesktopMode.value
  }

  return {
    mode,
    edgeY,
    edgeSide,
    geometry,
    dockWidth,
    hydrate,
    persist,
    open,
    minimize,
    setMode,
    setGeometry,
    setDockWidth,
    setEdgeY,
    syncViewport,
  }
})
