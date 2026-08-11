import type { ColumnPreset, FactoryId } from '../types'
import type { SchedulingDensityMode } from './schedulingLayout'
import { defaultSchedulingDensity } from './schedulingLayout'
import {
  schedulingColumns,
  maxSchedulingFrozenWidth,
  schedulingColumnWidth,
  schedulingDefaultColumnOrder,
  schedulingFrozenKeysByPreset,
} from '../composables/useSchedulingColumns'

export const schedulingPreferencesVersion = 1
export const schedulingPreferencesStoragePrefix = 'rr:injection-scheduling:layout:v1'

export interface SchedulingLayoutPreference {
  preset: ColumnPreset
  density: SchedulingDensityMode
  customVisibleColumns: Record<string, boolean>
  columnWidths: Record<string, number>
  columnOrder: string[]
  frozenKeys: string[]
}

export interface SchedulingCustomPreset {
  id: string
  name: string
  layout: SchedulingLayoutPreference
}

export interface SchedulingPreferencesDocument extends SchedulingLayoutPreference {
  version: number
  activeCustomPresetId: string | null
  customPresets: SchedulingCustomPreset[]
}

const presets = new Set<ColumnPreset>(['planner', 'production', 'fit', 'full'])
const densities = new Set<SchedulingDensityMode>(['comfortable', 'compact'])
const knownColumnKeys = new Set(schedulingColumns.map((column) => String(column.key)))

export function createSchedulingPreferencesKey(userId: string, factoryId: FactoryId) {
  return `${schedulingPreferencesStoragePrefix}:${encodeURIComponent(userId)}:${factoryId}`
}

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null
}

function normalizePreset(value: unknown): ColumnPreset {
  return typeof value === 'string' && presets.has(value as ColumnPreset) ? value as ColumnPreset : 'planner'
}

function normalizeDensity(value: unknown): SchedulingDensityMode {
  return typeof value === 'string' && densities.has(value as SchedulingDensityMode) ? value as SchedulingDensityMode : defaultSchedulingDensity
}

function normalizeVisibility(value: unknown) {
  const source = record(value)
  if (!source) return {}
  return Object.fromEntries(Object.entries(source)
    .filter(([key, visible]) => knownColumnKeys.has(key) && typeof visible === 'boolean')) as Record<string, boolean>
}

function normalizeWidths(value: unknown) {
  const source = record(value)
  if (!source) return {}
  return Object.fromEntries(Object.entries(source)
    .filter(([key, width]) => knownColumnKeys.has(key) && typeof width === 'number' && Number.isFinite(width))
    .map(([key, width]) => [key, Math.max(54, Math.min(420, Math.round(width as number)))])) as Record<string, number>
}

function normalizeOrder(value: unknown) {
  const requested = Array.isArray(value) ? value.filter((key): key is string => typeof key === 'string' && knownColumnKeys.has(key)) : []
  const unique = [...new Set(requested)]
  return [...unique, ...schedulingDefaultColumnOrder.filter((key) => !unique.includes(key))]
}

function normalizeFrozenKeys(
  value: unknown,
  preset: ColumnPreset,
  order: readonly string[],
  visibility: Readonly<Record<string, boolean>>,
  widths: Readonly<Record<string, number>>,
) {
  const requested = Array.isArray(value)
    ? value.filter((key): key is string => typeof key === 'string' && knownColumnKeys.has(key))
    : [...schedulingFrozenKeysByPreset[preset]]
  const requestedSet = new Set(requested)
  let frozenWidth = 0
  return order.filter((key) => {
    if (!requestedSet.has(key)) return false
    const column = schedulingColumns.find((item) => String(item.key) === key)
    if (!column || !(visibility[key] ?? column.presets.includes(preset))) return false
    const nextWidth = frozenWidth + schedulingColumnWidth(key, widths)
    if (nextWidth > maxSchedulingFrozenWidth) return false
    frozenWidth = nextWidth
    return true
  })
}

export function normalizeSchedulingLayoutPreference(value: unknown): SchedulingLayoutPreference {
  const source = record(value) ?? {}
  const preset = normalizePreset(source.preset)
  const customVisibleColumns = normalizeVisibility(source.customVisibleColumns)
  const columnWidths = normalizeWidths(source.columnWidths)
  const columnOrder = normalizeOrder(source.columnOrder)
  return {
    preset,
    density: normalizeDensity(source.density),
    customVisibleColumns,
    columnWidths,
    columnOrder,
    frozenKeys: normalizeFrozenKeys(source.frozenKeys, preset, columnOrder, customVisibleColumns, columnWidths),
  }
}

function normalizeCustomPresets(value: unknown) {
  if (!Array.isArray(value)) return []
  const seen = new Set<string>()
  return value.flatMap((entry): SchedulingCustomPreset[] => {
    const source = record(entry)
    const id = typeof source?.id === 'string' ? source.id.trim().slice(0, 80) : ''
    const name = typeof source?.name === 'string' ? source.name.trim().slice(0, 40) : ''
    if (!id || !name || seen.has(id)) return []
    seen.add(id)
    return [{ id, name, layout: normalizeSchedulingLayoutPreference(source?.layout) }]
  }).slice(0, 8)
}

export function createSchedulingPreferencesDocument(
  layout: SchedulingLayoutPreference,
  customPresets: SchedulingCustomPreset[],
  activeCustomPresetId: string | null,
): SchedulingPreferencesDocument {
  const normalizedLayout = normalizeSchedulingLayoutPreference(layout)
  const normalizedPresets = normalizeCustomPresets(customPresets)
  return {
    version: schedulingPreferencesVersion,
    ...normalizedLayout,
    customPresets: normalizedPresets,
    activeCustomPresetId: normalizedPresets.some((preset) => preset.id === activeCustomPresetId) ? activeCustomPresetId : null,
  }
}

export function loadSchedulingPreferences(storage: Pick<Storage, 'getItem'>, userId: string, factoryId: FactoryId) {
  if (!userId.trim()) return null
  try {
    const raw = storage.getItem(createSchedulingPreferencesKey(userId, factoryId))
    if (!raw) return null
    const source = record(JSON.parse(raw))
    if (!source || source.version !== schedulingPreferencesVersion) return null
    return createSchedulingPreferencesDocument(
      normalizeSchedulingLayoutPreference(source),
      normalizeCustomPresets(source.customPresets),
      typeof source.activeCustomPresetId === 'string' ? source.activeCustomPresetId : null,
    )
  } catch {
    return null
  }
}

export function saveSchedulingPreferences(
  storage: Pick<Storage, 'setItem'>,
  userId: string,
  factoryId: FactoryId,
  preferences: SchedulingPreferencesDocument,
) {
  if (!userId.trim()) return false
  try {
    storage.setItem(createSchedulingPreferencesKey(userId, factoryId), JSON.stringify(preferences))
    return true
  } catch {
    return false
  }
}
