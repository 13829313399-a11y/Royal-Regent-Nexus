import { computed, onBeforeUnmount, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'

export type DimensionUnit = 'cm' | 'inch' | 'mm'
export interface DimensionPreferenceScope { userId: string; employmentEpoch: number }
export const dimensionPreferenceKey = (scope: DimensionPreferenceScope) =>
  `carton-dimension-unit:v1:${encodeURIComponent(scope.userId)}:${scope.employmentEpoch}`
export const dimensionUnitValue = (value: unknown): DimensionUnit | null =>
  value === 'cm' || value === 'inch' || value === 'mm' ? value : null

/** Personal browser preference; it never rewrites an existing paper's source unit. */
export function useDimensionPreference(
  scope: MaybeRefOrGetter<DimensionPreferenceScope | null>,
  fallback: MaybeRefOrGetter<string> = 'cm',
) {
  const saved = ref<DimensionUnit | null>(null), error = ref('')
  const key = computed(() => { const current = toValue(scope); return current ? dimensionPreferenceKey(current) : '' })
  function read() {
    saved.value = null; error.value = ''
    if (!key.value) return
    try { saved.value = dimensionUnitValue(window.localStorage.getItem(key.value)) } catch { /* Default remains usable. */ }
  }
  watch(key, read, { immediate: true, flush: 'sync' })
  const unit = computed(() => saved.value ?? dimensionUnitValue(toValue(fallback)) ?? 'cm')
  function setUnit(value: string) {
    const next = dimensionUnitValue(value)
    if (!next || !key.value) return
    saved.value = next; error.value = ''
    try { window.localStorage.setItem(key.value, next) }
    catch { error.value = '当前浏览器无法保存尺寸习惯，本次可用，重新打开后需再次设置。' }
  }
  const storageChanged = (event: StorageEvent) => {
    if (event.key === key.value || event.key === null) read()
  }
  window.addEventListener('storage', storageChanged)
  onBeforeUnmount(() => window.removeEventListener('storage', storageChanged))
  return { unit, error, setUnit }
}
